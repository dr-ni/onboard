/*
 * Copyright © 2011 Gerd Kohlberger
 * Copyright © 2012 marmuta
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
#include <X11/Xatom.h>
#include <X11/extensions/XInput2.h>

#define XI_PROP_PRODUCT_ID "Device Product ID"


static unsigned int
translate_event_type (unsigned int xi_type);

static unsigned int
translate_state (XIModifierState *mods_state,
                 XIButtonState   *buttons_state,
                 XIGroupState    *group_state);

//------------------------------------------------------------------------
// DeviceEvent
// -----------------------------------------------------------------------

#define OSK_DEVICE_ADDED_EVENT   1100
#define OSK_DEVICE_REMOVED_EVENT 1101

typedef struct {
    PyObject_HEAD

    Display*     display;
    Window       xid_event;
    unsigned int xi_type;
    unsigned int type;
    unsigned int device_id;
    unsigned int source_id;
    double       x;
    double       y;
    double       x_root;
    double       y_root;
    unsigned int button;
    unsigned int state;
    unsigned int keyval;
    unsigned int sequence;
    unsigned int time;
    PyObject*    touch;

    PyObject*    source_device;

} OskDeviceEvent;

OSK_REGISTER_TYPE_WITH_MEMBERS (OskDeviceEvent, osk_device_event, "DeviceEvent")

static int
osk_device_event_init (OskDeviceEvent* self, PyObject *args, PyObject *kwds)
{
    self->xid_event = None;
    self->device_id = 0;
    self->source_id = 0;
    self->touch = Py_None;
    Py_INCREF(self->touch);
    self->source_device = Py_None;
    Py_INCREF(self->source_device);
    return 0;
}

static void
osk_device_event_dealloc (OskDeviceEvent* self)
{
    Py_DECREF(self->touch);
    Py_DECREF(self->source_device);
    OSK_FINISH_DEALLOC (self);
}

static OskDeviceEvent*
new_device_event (void)
{
    OskDeviceEvent *ev = PyObject_New(OskDeviceEvent, &osk_device_event_type);
    if (ev)
    {
        osk_device_event_type.tp_init((PyObject*) ev, NULL, NULL);
        return ev;
    }
    return NULL;
}

static PyObject *
osk_device_event_get_time (OskDeviceEvent* self, PyObject *args)
{
    return PyLong_FromUnsignedLong(self->time);
}

static PyObject *
osk_device_event_set_source_device (OskDeviceEvent* self, PyObject* value)
{
    Py_DECREF(self->source_device);
    self->source_device = value;
    Py_INCREF(self->source_device);
    Py_RETURN_NONE;
}

static PyObject *
osk_device_event_get_source_device (OskDeviceEvent* self, PyObject *args)
{
    Py_INCREF(self->source_device);
    return self->source_device;
}

static PyMethodDef osk_device_event_methods[] = {
    { "get_time",
      (PyCFunction) osk_device_event_get_time, METH_NOARGS,  NULL },
    { "get_source_device",
      (PyCFunction) osk_device_event_get_source_device, METH_NOARGS,  NULL },
    { "set_source_device",
      (PyCFunction) osk_device_event_set_source_device, METH_O,  NULL },
    { NULL, NULL, 0, NULL }
};

static PyMemberDef osk_device_event_members[] = {
    {"xid_event", T_UINT, offsetof(OskDeviceEvent, xid_event), READONLY, NULL },
    {"xi_type", T_UINT, offsetof(OskDeviceEvent, xi_type), READONLY, NULL },
    {"type", T_UINT, offsetof(OskDeviceEvent, type), READONLY, NULL },
    {"device_id", T_UINT, offsetof(OskDeviceEvent, device_id), READONLY, NULL },
    {"source_id", T_UINT, offsetof(OskDeviceEvent, source_id), READONLY, NULL },
    {"x", T_DOUBLE, offsetof(OskDeviceEvent, x), RESTRICTED, NULL },
    {"y", T_DOUBLE, offsetof(OskDeviceEvent, y), RESTRICTED, NULL },
    {"x_root", T_DOUBLE, offsetof(OskDeviceEvent, x_root), READONLY, NULL },
    {"y_root", T_DOUBLE, offsetof(OskDeviceEvent, y_root), READONLY, NULL },
    {"button", T_UINT, offsetof(OskDeviceEvent, button), READONLY, NULL },
    {"state", T_UINT, offsetof(OskDeviceEvent, state), READONLY, NULL },
    {"keyval", T_UINT, offsetof(OskDeviceEvent, keyval), READONLY, NULL },
    {"sequence", T_UINT, offsetof(OskDeviceEvent, sequence), READONLY, NULL },
    {"time", T_UINT, offsetof(OskDeviceEvent, time), READONLY, NULL },
    {"touch", T_OBJECT, offsetof(OskDeviceEvent, touch), READONLY, NULL },
    {NULL}
};

static PyGetSetDef osk_device_event_getsetters[] = {
    {NULL}
};


//------------------------------------------------------------------------
// Devices
// -----------------------------------------------------------------------

typedef struct {
    PyObject_HEAD

    Display  *dpy;
    int       xi2_opcode;
    Atom      atom_product_id;

    PyObject *event_handler;
    int       num_active_touches;
} OskDevices;

typedef struct {
    PyObject       *handler;
    OskDeviceEvent *event;
} IdleData;


static GdkFilterReturn osk_devices_event_filter (GdkXEvent  *gdk_xevent,
                                                 GdkEvent   *gdk_event,
                                                 OskDevices *dev);

static int osk_devices_select (OskDevices    *dev,
                               int            id,
                               unsigned char *mask,
                               unsigned int   mask_len);

OSK_REGISTER_TYPE (OskDevices, osk_devices, "Devices")

static char *init_kwlist[] = {
    "event_handler",
    NULL
};

static int
osk_devices_init (OskDevices *dev, PyObject *args, PyObject *kwds)
{
    int event, error;
    int major = 2;
    int minor = 2;

    dev->dpy = GDK_DISPLAY_XDISPLAY (gdk_display_get_default ());

    if (!XQueryExtension (dev->dpy, "XInputExtension",
                          &dev->xi2_opcode, &event, &error))
    {
        PyErr_SetString (OSK_EXCEPTION, "failed to initialize XInput extension");
        return -1;
    }

    // XIQueryVersion fails with X error BadValue if this isn't
    // the client's very first call. Someone, probably GTK is
    // successfully calling it before us, so just ignore the
    // error and move on.
    gdk_error_trap_push ();
    Status status = XIQueryVersion (dev->dpy, &major, &minor);
    gdk_error_trap_pop_ignored ();
    if (status == BadRequest)
    {
        PyErr_SetString (OSK_EXCEPTION, "XI2 not available");
        return -1;
    }
    if (major * 1000 + minor < 2002)
    {
        PyErr_SetString (OSK_EXCEPTION, "XI 2.2 not supported");
        return -1;
    }

    if (!PyArg_ParseTupleAndKeywords (args, kwds,
                                      "|O", init_kwlist,
                                      &dev->event_handler))
    {
        return -1;
    }

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

    dev->atom_product_id = XInternAtom(dev->dpy, XI_PROP_PRODUCT_ID, False);
    dev->num_active_touches = 0;

    return 0;
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

    result = PyObject_CallFunction (data->handler, "O", data->event);
    if (result)
        Py_DECREF (result);
    else
        PyErr_Print ();

    Py_DECREF (data->event);
    Py_DECREF (data->handler);

    PyGILState_Release (state);

    g_slice_free (IdleData, data);

    return FALSE;
}

static void
osk_devices_call_event_handler (OskDevices *dev, OskDeviceEvent* event)
{
    IdleData *data;

    data = g_slice_new (IdleData);
    data->handler = dev->event_handler;
    data->event = event;

    Py_INCREF (data->handler);
    Py_INCREF (data->event);

    g_idle_add ((GSourceFunc) idle_call, data);
}

static void
osk_devices_call_event_handler_device (OskDevices *dev,
                                       int         type,
                                       Display     *display,
                                       int         device_id,
                                       int         source_id
)
{
    OskDeviceEvent *ev = new_device_event();
    if (ev)
    {
        ev->display = display;
        ev->xi_type = type;
        ev->type = translate_event_type(type);
        ev->device_id = device_id;
        ev->source_id = source_id;

        osk_devices_call_event_handler (dev, ev);

        Py_DECREF(ev);
    }
}

static void
osk_devices_call_event_handler_pointer (OskDevices  *dev,
                                        int          type,
                                        Display     *display,
                                        Window       xid_event,
                                        int          device_id,
                                        int          source_id,
                                        double       x,
                                        double       y,
                                        double       x_root,
                                        double       y_root,
                                        unsigned int button,
                                        unsigned int state,
                                        unsigned int sequence,
                                        unsigned int time
)
{
    OskDeviceEvent *ev = new_device_event();
    if (ev)
    {
        ev->display = display;
        ev->xid_event = xid_event;
        ev->xi_type = type;
        ev->type = translate_event_type(type);
        ev->device_id = device_id;
        ev->source_id = source_id;
        ev->x = x;
        ev->y = y;
        ev->x_root = x_root;
        ev->y_root = y_root;
        ev->button = button;
        ev->state = state;
        ev->sequence = sequence;
        ev->time = time;

        // Link event to itself in the touch property for
        // compatibility with GDK touch events.
        Py_DECREF(ev->touch);
        ev->touch = (PyObject*) ev;
        Py_INCREF(ev->touch);

        osk_devices_call_event_handler (dev, ev);

        Py_DECREF(ev);
    }
}

static void
osk_devices_call_event_handler_key (OskDevices *dev,
                                    int         type,
                                    Display*    display,
                                    int         device_id,
                                    int         keyval
)
{
    OskDeviceEvent *ev = new_device_event();
    if (ev)
    {
        ev->display = display;
        ev->xi_type = type;
        ev->type = translate_event_type(type);
        ev->device_id = device_id;
        ev->keyval = keyval;

        osk_devices_call_event_handler (dev, ev);

        Py_DECREF(ev);
    }
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

/*
 * Translate XInput event type to GDK event type.
 * */
static unsigned int
translate_event_type (unsigned int xi_type)
{
    unsigned int type;

    switch (xi_type)
    {
        case XI_TouchBegin:
        case XI_RawTouchBegin:
            type = GDK_TOUCH_BEGIN; break;
        case XI_TouchUpdate:
        case XI_RawTouchUpdate:
            type = GDK_TOUCH_UPDATE; break;
        case XI_TouchEnd:
        case XI_RawTouchEnd:
            type = GDK_TOUCH_END; break;

        default: type = 0; break;
    }
    return type;
}

/*
 * Translate XInput state to GDK event state.
 * */
static unsigned int
translate_state (XIModifierState *mods_state,
                 XIButtonState   *buttons_state,
                 XIGroupState    *group_state)
{
    unsigned int state = 0;
    static unsigned int gdk_masks[] = {GDK_BUTTON1_MASK,
                                       GDK_BUTTON2_MASK,
                                       GDK_BUTTON3_MASK,
                                       GDK_BUTTON4_MASK,
                                       GDK_BUTTON5_MASK};

    if (mods_state)
        state = mods_state->effective;

    if (buttons_state)
    {
        int n = MIN (G_N_ELEMENTS(gdk_masks), buttons_state->mask_len * 8);
        int i;
        for (i = 0; i < n; i++)
            if (XIMaskIsSet (buttons_state->mask, i))
                state |= gdk_masks[i];
    }

    if (group_state)
        state |= (group_state->effective) << 13;

    return state;
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

/*
 * Handler for pointer events and first touch events.
 * Returns window coordinates and valid window in event.xid_event, but
 * is unable to return correct coordinates for subsequent multiple touches.
 */
static Bool
handle_pointer_event (int evtype, XIEvent* xievent, OskDevices* dev)
{
    const int MASTER_POINTER_DEVICE = 2;

    switch (evtype)
    {
        case XI_Motion:
        case XI_ButtonPress:
        case XI_ButtonRelease:
        case XI_TouchBegin:
        case XI_TouchUpdate:
        case XI_TouchEnd:
        case XI_RawTouchBegin:
        case XI_RawTouchUpdate:
        case XI_RawTouchEnd:
        case XI_RawMotion:
        case XI_RawButtonPress:
        case XI_RawButtonRelease:
        {
            XIDeviceEvent *event = (XIDeviceEvent*) xievent;

            if (evtype == XI_ButtonPress ||
                evtype == XI_RawButtonPress ||
                evtype == XI_TouchBegin ||
                evtype == XI_RawTouchBegin)
            {
            }

            Window win = DefaultRootWindow (dev->dpy);
            Window             root;
            Window             child;
            double             root_x;
            double             root_y;
            double             win_x;
            double             win_y;
            XIButtonState      buttons;
            XIModifierState    mods;
            XIGroupState       group;

            gdk_error_trap_push ();
            while (win)
            {
                XIQueryPointer(dev->dpy,
                               MASTER_POINTER_DEVICE,
                               win,
                               &root,
                               &child,
                               &root_x,
                               &root_y,
                               &win_x,
                               &win_y,
                               &buttons,
                               &mods,
                               &group);
                if (child == None)
                    break;
                win = child;
            }
            if (!gdk_error_trap_pop ())
            {
                unsigned int button;
                if (evtype == XI_ButtonPress ||
                    evtype == XI_ButtonRelease)
                    button = event->detail;
                else
                    button = 0;

                unsigned int state = translate_state (&mods,
                                                      &buttons,
                                                      &group);
                unsigned int sequence;
                if (evtype == XI_TouchBegin ||
                    evtype == XI_TouchUpdate ||
                    evtype == XI_TouchEnd)
                {
                    sequence = event->detail;
                    win_x = event->event_x;
                    win_y = event->event_y;
                    root_x = event->root_x;
                    root_y = event->root_y;
                }
                else if (evtype == XI_RawTouchBegin ||
                         evtype == XI_RawTouchUpdate ||
                         evtype == XI_RawTouchEnd)
                {
                    sequence = event->detail;
                }
                else
                    sequence = 0;

                osk_devices_call_event_handler_pointer (dev,
                                                        evtype,
                                                        event->display,
                                                        win,
                                                        event->deviceid,
                                                        event->sourceid,
                                                        win_x,
                                                        win_y,
                                                        root_x,
                                                        root_y,
                                                        button,
                                                        state,
                                                        sequence,
                                                        event->time);
            }
            return True;  // handled
        }
    }
    return False;
}

/*
 * Handler for second and further touches.
 * Returns correct touch coordinates, but only as root coordinates and
 * without valid window (event.xid_event).
 */
static Bool
handle_multitouch_event (int evtype, XIEvent* xievent, OskDevices* dev)
{
    switch (evtype)
    {
        case XI_Motion:
        case XI_ButtonPress:
        case XI_ButtonRelease:
        case XI_TouchBegin:
        case XI_TouchUpdate:
        case XI_TouchEnd:
        {
            XIDeviceEvent *event = (XIDeviceEvent*) xievent;

            unsigned int button = 0;
            if (evtype == XI_ButtonPress ||
                evtype == XI_ButtonRelease)
                button = event->detail;

            unsigned int sequence = 0;
            if (evtype == XI_TouchBegin ||
                evtype == XI_TouchUpdate ||
                evtype == XI_TouchEnd)
                sequence = event->detail;

            unsigned int state = translate_state (&event->mods,
                                                  &event->buttons,
                                                  &event->group);

            osk_devices_call_event_handler_pointer (dev,
                                                    evtype,
                                                    event->display,
                                                    event->event,
                                                    event->deviceid,
                                                    event->sourceid,
                                                    event->event_x,
                                                    event->event_y,
                                                    event->root_x,
                                                    event->root_y,
                                                    button,
                                                    state,
                                                    sequence,
                                                    event->time);
            return True; // handled
        }
    }
    return False;
}

static GdkFilterReturn
osk_devices_event_filter (GdkXEvent  *gdk_xevent,
                          GdkEvent   *gdk_event,
                          OskDevices *dev)
{
    XGenericEventCookie *cookie = &((XEvent *) gdk_xevent)->xcookie;

    if (cookie->type == GenericEvent && cookie->extension == dev->xi2_opcode)
    {
        int evtype = cookie->evtype;
        XIEvent *event = cookie->data;

//        XIDeviceEvent *e = cookie->data;
//        printf("did %d evtype %d type %d  detail %d\n", e->deviceid, evtype, e->type, e->detail);

        Bool handled = False;
        if (dev->num_active_touches == 0)
            handled = handle_pointer_event(evtype, event, dev);
        else
            handled = handle_multitouch_event(evtype, event, dev);

        if (evtype == XI_TouchBegin || evtype == XI_RawTouchBegin)
            dev->num_active_touches++;
        else if (evtype == XI_TouchEnd || evtype == XI_RawTouchEnd)
            if (--dev->num_active_touches < 0)
                dev->num_active_touches = 0;   // be defensive

        if (handled)
            return GDK_FILTER_CONTINUE;

        switch (evtype)
        {
            case XI_HierarchyChanged:
            {
                XIHierarchyEvent *event = cookie->data;

                if ((event->flags & XISlaveAdded) ||
                    (event->flags & XISlaveRemoved))
                {
                    XIHierarchyInfo *info;
                    int              i;

                    for (i = 0; i < event->num_info; i++)
                    {
                        info = &event->info[i];

                        if (info->flags & XISlaveAdded)
                        {
                            osk_devices_call_event_handler_device (dev,
                                                            OSK_DEVICE_ADDED_EVENT,
                                                            event->display,
                                                            info->deviceid,
                                                            0);
                        }
                        else if (info->flags & XISlaveRemoved)
                        {
                            osk_devices_call_event_handler_device (dev,
                                                            OSK_DEVICE_REMOVED_EVENT,
                                                            event->display,
                                                            info->deviceid,
                                                            0);
                        }
                    }
                }
                break;
            }

            case XI_DeviceChanged:
            {
                XIDeviceChangedEvent *event = cookie->data;

                if (event->reason == XISlaveSwitch)
                    osk_devices_call_event_handler_device (dev,
                                                           evtype,
                                                           event->display,
                                                           event->deviceid,
                                                           event->sourceid);
                break;
            }

            case XI_KeyPress:
            {
                XIDeviceEvent *event = cookie->data;
                int            keyval;

                if (!(event->flags & XIKeyRepeat))
                {
                    keyval = osk_devices_translate_keycode (event->detail,
                                                            &event->group,
                                                            &event->mods);
                    if (keyval)
                        osk_devices_call_event_handler_key (dev,
                                                            evtype,
                                                            event->display,
                                                            event->deviceid,
                                                            keyval);
                }
                break;
            }

            case XI_KeyRelease:
            {
                XIDeviceEvent *event = cookie->data;
                int            keyval;

                keyval = osk_devices_translate_keycode (event->detail,
                                                        &event->group,
                                                        &event->mods);
                if (keyval)
                    osk_devices_call_event_handler_key (dev,
                                                        evtype,
                                                        event->display,
                                                        event->deviceid,
                                                        keyval);
                break;
            }
        }
    }

    return GDK_FILTER_CONTINUE;
}

static Bool
osk_devices_get_product_id (OskDevices   *dev,
                            int           id,
                            unsigned int *vendor_id,
                            unsigned int *product_id)
{
    Status         rc;
    Atom           act_type;
    int            act_format;
    unsigned long  nitems, bytes;
    unsigned char *data;

    *vendor_id  = 0;
    *product_id = 0;

    gdk_error_trap_push ();
    rc = XIGetProperty (dev->dpy, id, dev->atom_product_id,
                        0, 2, False, XA_INTEGER,
                        &act_type, &act_format, &nitems, &bytes, &data);
    gdk_error_trap_pop_ignored ();

    if (rc == Success && nitems == 2 && act_format == 32)
    {
        guint32 *data32 = (guint32 *) data;

        *vendor_id  = *data32;
        *product_id = *(data32 + 1);

        XFree (data);

        return True;
    }

    return False;
}

static int
get_touch_mode (XIAnyClassInfo **classes, int num_classes)
{
    int i;
    for (i = 0; i < num_classes; i++)
    {
        XITouchClassInfo *class = (XITouchClassInfo*) classes[i];
        if (class->type == XITouchClass)
        {
            if (class->num_touches)
            {
                if (class->mode == XIDirectTouch ||
                    class->mode == XIDependentTouch)
                {
                    return class->mode;
                }
            }
        }
    }

    return 0;
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
        PyObject    *value;
        unsigned int vid, pid;
        XIDeviceInfo *device = devices + i;

        osk_devices_get_product_id (dev, device->deviceid, &vid, &pid);

        value = Py_BuildValue ("(siiiBiii)",
                               device->name,
                               device->deviceid,
                               device->use,
                               device->attachment,
                               device->enabled,
                               vid, pid,
                               get_touch_mode(device->classes,
                                              device->num_classes));
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
 * as a tuple.
 *
 * 0: name (string)
 * 1: id (int)
 * 2: type/use (int)
 * 3: attachment/master id (int)
 * 4: enabled (bool)
 * 5: vendor id (int)
 * 6: product id (int)
 *
 * Returns: A device info tuple.
 */
static PyObject *
osk_devices_get_info (PyObject *self, PyObject *args)
{
    OskDevices   *dev = (OskDevices *) self;
    XIDeviceInfo *devices;
    PyObject     *value;
    int           id, n_devices;
    unsigned int  vid, pid;

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

    osk_devices_get_product_id (dev, id, &vid, &pid);

    value = Py_BuildValue ("(siiiBii)",
                           devices[0].name,
                           devices[0].deviceid,
                           devices[0].use,
                           devices[0].attachment,
                           devices[0].enabled,
                           vid, pid);

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
 * osk_devices_select_events:
 * @id:  Id of the device to select events for (int)
 * @event_mask: Bit mask of XI events to select (long)
 *
 * Selects XInput events for a device. The device will send the selected
 * events to the #event_handler. If the calling instance was constructed
 * without the #event_handler keyword, this function is a no-op.
 */
static PyObject *
osk_devices_select_events (PyObject *self, PyObject *args)
{
    OskDevices   *dev = (OskDevices *) self;
    unsigned char mask[4] = { 0, 0, 0, 0};
    int           id;
    unsigned long event_mask;

    if (!PyArg_ParseTuple (args, "il", &id, &event_mask))
        return NULL;

    if (dev->event_handler)
    {
        int i;
        int nbits = MIN(sizeof(event_mask), sizeof(mask)) * 8;
        for (i = 0; i < nbits; i++)
        {
            if (event_mask & 1<<i)
                XISetMask (mask, i);
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
 * osk_devices_unselect_events:
 * @id: Id of the device to close (int)
 *
 * "Closes" a device. If the calling instance was constructed
 * without the #event_handler keyword or the device was not
 * previously opened, this function is a no-op.
 *
 */
static PyObject *
osk_devices_unselect_events (PyObject *self, PyObject *args)
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
    { "list",            osk_devices_list,            METH_NOARGS,  NULL },
    { "get_info",        osk_devices_get_info,        METH_VARARGS, NULL },
    { "attach",          osk_devices_attach,          METH_VARARGS, NULL },
    { "detach",          osk_devices_detach,          METH_VARARGS, NULL },
    { "select_events",   osk_devices_select_events,   METH_VARARGS, NULL },
    { "unselect_events", osk_devices_unselect_events, METH_VARARGS, NULL },
    { NULL, NULL, 0, NULL }
};

