/*
 * Copyright © 2011 Gerd Kohlberger
 *
 * Onboard is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * Onboard is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#include "osk_module.h"
#include "osk_devices.h"

#include <gdk/gdkx.h>
#include <X11/extensions/XInput2.h>

typedef struct {
    PyObject_HEAD

    Display  *dpy;
    int       xi2_opcode;

    PyObject *event_handler;

} OskDevices;

typedef struct {
    PyObject    *handler;
    const gchar *type;
    int          id;
    int          detail;
} IdleData;

static char *init_kwlist[] = {
    "event_handler",
    NULL
};

static GdkFilterReturn osk_devices_event_filter (GdkXEvent  *gdk_xevent,
                                                 GdkEvent   *gdk_event,
                                                 OskDevices *dev);

static int osk_devices_select (OskDevices    *dev,
                               int            id,
                               unsigned char *mask,
                               unsigned int   mask_len);

OSK_REGISTER_TYPE (OskDevices, osk_devices, "Devices")

static int
osk_devices_init (OskDevices *dev, PyObject *args, PyObject *kwds)
{
    int event, error;
    int major = 2;
    int minor = 0;

    dev->dpy = GDK_DISPLAY_XDISPLAY (gdk_display_get_default ());

    if (!XQueryExtension (dev->dpy, "XInputExtension",
                          &dev->xi2_opcode, &event, &error))
    {
        PyErr_SetString (OSK_EXCEPTION, "failed initilaize XInput extension");
        return -1;
    }

    if (XIQueryVersion (dev->dpy, &major, &minor) == BadRequest)
    {
        PyErr_SetString (OSK_EXCEPTION, "XI2 not available");
        return -1;
    }

    if (!PyArg_ParseTupleAndKeywords (args, kwds,
                                      "|O", init_kwlist,
                                      &dev->event_handler))
        return -1;

    if (dev->event_handler)
    {
        unsigned char mask[2] = { 0, 0 };

        Py_INCREF (dev->event_handler);

        XISetMask (mask, XI_HierarchyChanged);

        osk_devices_select (dev, XIAllDevices, mask, sizeof (mask));

        gdk_window_add_filter (NULL,
                               (GdkFilterFunc) osk_devices_event_filter,
                               dev);
    }
    return 0;
}

static PyObject *
osk_devices_new (PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    return type->tp_alloc (type, 0);
}

static void
osk_devices_dealloc (OskDevices *dev)
{
    if (dev->event_handler)
    {
        unsigned char mask[2] = { 0, 0 };

        osk_devices_select (dev, XIAllDevices, mask, sizeof (mask));

        gdk_window_remove_filter (NULL,
                                  (GdkFilterFunc) osk_devices_event_filter,
                                  dev);

        Py_DECREF (dev->event_handler);
    }
    OSK_FINISH_DEALLOC (dev);
}

static gboolean
idle_call (IdleData *data)
{
    PyGILState_STATE state = PyGILState_Ensure ();
    PyObject *result;

    result = PyObject_CallFunction (data->handler, "sii",
                                    data->type,
                                    data->id,
                                    data->detail);
    if (result)
        Py_DECREF (result);
    else
        PyErr_Print ();

    Py_DECREF (data->handler);

    PyGILState_Release (state);

    g_slice_free (IdleData, data);

    return FALSE;
}

static void
osk_devices_call_event_handler (OskDevices *dev,
                                const char *type,
                                int         id,
                                int         detail)
{
    IdleData *data;

    Py_INCREF (dev->event_handler);

    data = g_slice_new (IdleData);
    data->handler = dev->event_handler;
    data->type = type;
    data->id = id;
    data->detail = detail;

    g_idle_add ((GSourceFunc) idle_call, data);
}

static int
osk_devices_select (OskDevices    *dev,
                    int            id,
                    unsigned char *mask,
                    unsigned int   mask_len)
{
    XIEventMask events;

    events.deviceid = id;
    events.mask = mask;
    events.mask_len = mask_len;

    gdk_error_trap_push ();
    XISelectEvents (dev->dpy, DefaultRootWindow (dev->dpy), &events, 1);
    gdk_flush ();

    return gdk_error_trap_pop () ? -1 : 0;
}

static int
osk_devices_translate_keycode (int              keycode,
                               XIGroupState    *group,
                               XIModifierState *mods)
{
    unsigned int keyval = 0;

    gdk_keymap_translate_keyboard_state (gdk_keymap_get_default (),
                                         keycode,
                                         mods->effective,
                                         group->effective,
                                         &keyval, NULL, NULL, NULL);
    return (int) keyval;
}

static GdkFilterReturn
osk_devices_event_filter (GdkXEvent  *gdk_xevent,
                          GdkEvent   *gdk_event,
                          OskDevices *dev)
{
    XGenericEventCookie *cookie = &((XEvent *) gdk_xevent)->xcookie;

    if (cookie->type == GenericEvent &&
        cookie->extension == dev->xi2_opcode &&
        XGetEventData (dev->dpy, cookie))
    {
        if (cookie->evtype == XI_HierarchyChanged)
        {
            XIHierarchyEvent *event = cookie->data;

            if ((event->flags & XISlaveAdded) ||
                (event->flags & XISlaveRemoved))
            {
                XIHierarchyInfo *info;
                int i;

                for (i = 0; i < event->num_info; i++)
                {
                    info = &event->info[i];

                    if (info->flags & XISlaveAdded)
                    {
                        osk_devices_call_event_handler (dev,
                                                        "DeviceAdded",
                                                        info->deviceid,
                                                        0);
                    }
                    else if (info->flags & XISlaveRemoved)
                    {
                        osk_devices_call_event_handler (dev,
                                                        "DeviceRemoved",
                                                        info->deviceid,
                                                        0);
                    }
                }
            }
        }
        else if (cookie->evtype == XI_ButtonPress)
        {
            XIDeviceEvent *event = cookie->data;

            osk_devices_call_event_handler (dev,
                                            "ButtonPress",
                                            event->deviceid,
                                            event->detail);
        }
        else if (cookie->evtype == XI_ButtonRelease)
        {
            XIDeviceEvent *event = cookie->data;

            osk_devices_call_event_handler (dev,
                                            "ButtonRelease",
                                            event->deviceid,
                                            event->detail);
        }
        else if (cookie->evtype == XI_KeyPress)
        {
            XIDeviceEvent *event = cookie->data;
            int            keyval;

            if (!(event->flags & XIKeyRepeat))
            {
                keyval = osk_devices_translate_keycode (event->detail,
                                                        &event->group,
                                                        &event->mods);
                if (keyval)
                    osk_devices_call_event_handler (dev,
                                                    "KeyPress",
                                                    event->deviceid,
                                                    keyval);
            }
        }
        else if (cookie->evtype == XI_KeyRelease)
        {
            XIDeviceEvent *event = cookie->data;
            int            keyval;

            keyval = osk_devices_translate_keycode (event->detail,
                                                    &event->group,
                                                    &event->mods);
            if (keyval)
                osk_devices_call_event_handler (dev,
                                                "KeyRelease",
                                                event->deviceid,
                                                keyval);
        }
        XFreeEventData (dev->dpy, cookie);
    }
    return GDK_FILTER_CONTINUE;
}

/**
 * osk_devices_get_info:
 * @id: Id of an input device (int)
 *
 * Get a list of all input devices on the system. Each list item
 * is a device info tuple, see osk_devices_get_info().
 * 
 * Returns: A list of device info tuples.
 */
static PyObject *
osk_devices_list (PyObject *self, PyObject *args)
{
    OskDevices   *dev = (OskDevices *) self;
    XIDeviceInfo *devices;
    int           i, n_devices;
    PyObject     *list;

    devices = XIQueryDevice (dev->dpy, XIAllDevices, &n_devices);

    list = PyList_New ((Py_ssize_t) n_devices);
    if (!list)
        goto error;

    for (i = 0; i < n_devices; i++)
    {
        PyObject *value = Py_BuildValue ("(siiiB)",
                                         devices[i].name,
                                         devices[i].deviceid,
                                         devices[i].use,
                                         devices[i].attachment,
                                         devices[i].enabled);
        if (!value)
            goto error;

        if (PyList_SetItem (list, i, value) < 0)
        {
            Py_DECREF (value);
            goto error;
        }
    }

    XIFreeDeviceInfo (devices);

    return list;

error:
    PyErr_SetString (OSK_EXCEPTION, "failed to get device list");

    Py_XDECREF (list);
    XIFreeDeviceInfo (devices);

    return NULL;
}

/**
 * osk_devices_get_info:
 * @id: Id of an input device (int)
 *
 * Get information about an input device. The device info is returned
 * as a tuple with 5 entries:
 *
 * 0: device name (string)
 * 1: device id (int)
 * 2: device type (int)
 * 3: id of the master this slave belongs to or
 *    the paired master if @id is a master device (int)
 * 4: device state: enabled or not (bool)
 *
 * Returns: A device info tuple.
 */
static PyObject *
osk_devices_get_info (PyObject *self, PyObject *args)
{
    OskDevices   *dev = (OskDevices *) self;
    XIDeviceInfo *devices;
    int           id, n_devices;
    PyObject     *value;

    if (!PyArg_ParseTuple (args, "i", &id))
        return NULL;

    gdk_error_trap_push ();
    devices = XIQueryDevice (dev->dpy, id, &n_devices);
    gdk_flush ();

    if (gdk_error_trap_pop ())
    {
        PyErr_SetString (OSK_EXCEPTION, "invalid device id");
        return NULL;
    }

    value = Py_BuildValue ("(siiiB)",
                           devices[0].name,
                           devices[0].deviceid,
                           devices[0].use,
                           devices[0].attachment,
                           devices[0].enabled);

    XIFreeDeviceInfo (devices);

    return value;
}

/**
 * osk_devices_attach:
 * @id:     Id of the device to attach (int)
 * @master: Id of a master device (int)
 *
 * Attaches the device with @id to @master.
 *
 */
static PyObject *
osk_devices_attach (PyObject *self, PyObject *args)
{
    OskDevices       *dev = (OskDevices *) self;
    XIAttachSlaveInfo info;
    int               id, master;

    if (!PyArg_ParseTuple (args, "ii", &id, &master))
        return NULL;

    info.type = XIAttachSlave;
    info.deviceid = id;
    info.new_master = master;

    gdk_error_trap_push ();
    XIChangeHierarchy (dev->dpy, (XIAnyHierarchyChangeInfo *) &info, 1);
    gdk_flush ();

    if (gdk_error_trap_pop ())
    {
        PyErr_SetString (OSK_EXCEPTION, "failed to attach device");
        return NULL;
    }
    Py_RETURN_NONE;
}

/**
 * osk_devices_detach:
 * @id: Id of the device to detach (int)
 *
 * Detaches an input device for its master. Detached devices
 * stop sending "core events".
 *
 */
static PyObject *
osk_devices_detach (PyObject *self, PyObject *args)
{
    OskDevices       *dev = (OskDevices *) self;
    XIDetachSlaveInfo info;
    int               id;

    if (!PyArg_ParseTuple (args, "i", &id))
        return NULL;

    info.type = XIDetachSlave;
    info.deviceid = id;

    gdk_error_trap_push ();
    XIChangeHierarchy (dev->dpy, (XIAnyHierarchyChangeInfo *) &info, 1);
    gdk_flush ();

    if (gdk_error_trap_pop ())
    {
        PyErr_SetString (OSK_EXCEPTION, "failed to detach device");
        return NULL;
    }
    Py_RETURN_NONE;
}

/**
 * osk_devices_open:
 * @id:  Id of the device to open (int)
 * @bev: Select for buttons events (bool)
 * @kev: Select for key events (bool)
 *
 * "Opens" a device. The device will send #ButtonPress, #ButtonRelease and
 * #KeyPress, #KeyRelease events to the #event_handler. If the calling
 * instance was constructed without the #event_handler keyword, this
 * function is a no-op.
 *
 */
static PyObject *
osk_devices_open (PyObject *self, PyObject *args)
{
    OskDevices   *dev = (OskDevices *) self;
    unsigned char mask[1] = { 0 };
    int           id;
    unsigned char bev, kev;

    if (!PyArg_ParseTuple (args, "iBB", &id, &bev, &kev))
        return NULL;

    if (dev->event_handler && (bev || kev))
    {
        if (bev)
        {
            XISetMask (mask, XI_ButtonPress);
            XISetMask (mask, XI_ButtonRelease);
        }

        if (kev)
        {
            XISetMask (mask, XI_KeyPress);
            XISetMask (mask, XI_KeyRelease);
        }

        if (osk_devices_select (dev, id, mask, sizeof (mask)) < 0)
        {
            PyErr_SetString (OSK_EXCEPTION, "failed to open device");
            return NULL;
        }
    }
    Py_RETURN_NONE;
}

/**
 * osk_devices_close:
 * @id: Id of the device to close (int)
 *
 * "Closes" a device. If the calling instance was constructed
 * without the #event_handler keyword or the device was not
 * previously opened, this function is a no-op.
 *
 */
static PyObject *
osk_devices_close (PyObject *self, PyObject *args)
{
    OskDevices   *dev = (OskDevices *) self;
    unsigned char mask[1] = { 0 };
    int           id;

    if (!PyArg_ParseTuple (args, "i", &id))
        return NULL;

    if (dev->event_handler)
    {
        if (osk_devices_select (dev, id, mask, sizeof (mask)) < 0)
        {
            PyErr_SetString (OSK_EXCEPTION, "failed to close device");
            return NULL;
        }
    }
    Py_RETURN_NONE;
}

static PyMethodDef osk_devices_methods[] = {
    { "list",     osk_devices_list,     METH_NOARGS,  NULL },
    { "get_info", osk_devices_get_info, METH_VARARGS, NULL },
    { "attach",   osk_devices_attach,   METH_VARARGS, NULL },
    { "detach",   osk_devices_detach,   METH_VARARGS, NULL },
    { "open",     osk_devices_open,     METH_VARARGS, NULL },
    { "close",    osk_devices_close,    METH_VARARGS, NULL },
    { NULL, NULL, 0, NULL }
};

