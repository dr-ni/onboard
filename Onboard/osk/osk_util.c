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
#include "osk_util.h"

#include <gdk/gdkx.h>
#include <X11/extensions/XTest.h>

typedef struct {
    Display *display;
    unsigned int button;
    unsigned int click_type;
    unsigned int drag_started;
    unsigned int modifier;
    Bool enable_conversion;
    PyObject* exclusion_rects;
    PyObject* callback;
} OskUtilGrabInfo;

typedef struct {
    PyObject_HEAD
    OskUtilGrabInfo *info;
} OskUtil;

OSK_REGISTER_TYPE (OskUtil, osk_util, "Util")

void
stop_convert_click(OskUtilGrabInfo* info);
static Bool
start_grab(OskUtilGrabInfo* info);
static void
stop_grab(OskUtilGrabInfo* info);

static int
osk_util_init (OskUtil *util, PyObject *args, PyObject *kwds)
{
    Display *dpy;
    int      nop;

    util->info = g_new (OskUtilGrabInfo, 1);
    if (!util->info)
    {
        PyErr_SetString (OSK_EXCEPTION, "failed allocate OskUtilGrabInfo");
        return -1;
    }
    util->info->display = NULL;
    util->info->button = PRIMARY_BUTTON;
    util->info->click_type = CLICK_TYPE_SINGLE;
    util->info->drag_started = False;
    util->info->enable_conversion = True;
    util->info->exclusion_rects = NULL;
    util->info->callback = NULL;

    dpy = GDK_DISPLAY_XDISPLAY (gdk_display_get_default ());

    if (!XTestQueryExtension (dpy, &nop, &nop, &nop, &nop))
    {
        PyErr_SetString (OSK_EXCEPTION, "failed initialize XTest extension");
        return -1;
    }

    /* send events inspite of other grabs */
    XTestGrabControl (dpy, True);

    return 0;
}

static PyObject *
osk_util_new (PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    return type->tp_alloc (type, 0);
}

static void
osk_util_dealloc (OskUtil *util)
{
    if (util->info)
    {
        stop_convert_click(util->info);
        g_free (util->info);
        util->info = NULL;
    }

    OSK_FINISH_DEALLOC (util);
}

static
void notify_click_done(PyObject* callback)
{
    // Tell Onboard that the click has been performed.
    if (callback)
    {
        PyObject* arglist = NULL; //Py_BuildValue("(i)", arg);
        PyObject* result  = PyObject_CallObject(callback, arglist);
        Py_XDECREF(arglist);
        Py_XDECREF(result);
    }
}

static Bool
can_convert_click(OskUtilGrabInfo* info, int x_root, int y_root)
{
    if (!info->enable_conversion)
        return False;

    // Check if the the given point (x_root, y_root) lies
    // within any of the exclusion rectangles.
    if (info->exclusion_rects)
    {
        int i;
        int n = PySequence_Length(info->exclusion_rects);
        for (i = 0; i < n; i++)
        {
            PyObject* rect = PySequence_GetItem(info->exclusion_rects, i);
            if (rect == NULL)
                break;
            int m = PySequence_Length(rect);
            if (m != 4)
                break;

            PyObject* item;

            item = PySequence_GetItem(rect, 0);
            int x = PyInt_AsLong(item);
            Py_DECREF(item);

            item = PySequence_GetItem(rect, 1);
            int y = PyInt_AsLong(item);
            Py_DECREF(item);

            item = PySequence_GetItem(rect, 2);
            int w = PyInt_AsLong(item);
            Py_DECREF(item);

            item = PySequence_GetItem(rect, 3);
            int h = PyInt_AsLong(item);
            Py_DECREF(item);

            Py_DECREF(rect);

            if (x_root >= x && x_root < x + w &&
                y_root >= y && y_root < y + h)
            {
                return False;
            }
        }
    }

    return True;
}

static GdkFilterReturn
osk_util_event_filter (GdkXEvent       *gdk_xevent,
                       GdkEvent        *gdk_event,
                       OskUtilGrabInfo *info)
{
    XEvent *event = gdk_xevent;

    if (event->type == ButtonPress || event->type == ButtonRelease)
    {
        XButtonEvent *bev = (XButtonEvent *) event;
        if (bev->button == Button1)
        {
            unsigned int button = info->button;
            unsigned int click_type = info->click_type;
            Bool drag_started = info->drag_started;
            PyObject* callback = info->callback;
            Py_XINCREF(callback);

            // Don't convert the click if any of the click buttons was hit
            if (!can_convert_click(info, bev->x_root, bev->y_root))
            {
                /* Replay original event.
                 * This will usually give a regular left click.
                 */
                XAllowEvents (bev->display, ReplayPointer, bev->time);

                /*
                 * Don't stop the grab here, Onboard controls the
                 * cancellation from the python side. I does so by
                 * explicitely setting the convert click to
                 * PRIMARY_BUTTON, CLICK_TYPE_SINGLE.
                 */
            }
            else
            {
                /* Consume original event */
                XAllowEvents (bev->display, AsyncPointer, bev->time);

                if (event->type == ButtonRelease)
                {
                    stop_convert_click(info);

                    /* Synthesize button click */
                    unsigned long delay = 40;
                    switch (click_type)
                    {
                        case CLICK_TYPE_SINGLE:
                            XTestFakeButtonEvent (bev->display, button, True, CurrentTime);
                            XTestFakeButtonEvent (bev->display, button, False, 50);
                            break;

                        case CLICK_TYPE_DOUBLE:
                            XTestFakeButtonEvent (bev->display, button, True, CurrentTime);
                            XTestFakeButtonEvent (bev->display, button, False, delay);
                            XTestFakeButtonEvent (bev->display, button, True, delay);
                            XTestFakeButtonEvent (bev->display, button, False, delay);
                            break;

                        case CLICK_TYPE_DRAG:
                            if (!drag_started)
                            {
                                XTestFakeButtonEvent (bev->display, button, True, CurrentTime);
                                info->drag_started = True;
                            }
                            else
                            {
                                XTestFakeButtonEvent (bev->display, button, False, CurrentTime);
                            }
                            break;
                    }

                    notify_click_done(callback);
                }
            }
            Py_XDECREF(callback);
        }
        //return GDK_FILTER_REMOVE;
    }
    return GDK_FILTER_CONTINUE;
}


static Bool
start_grab(OskUtilGrabInfo* info)
{
    gdk_error_trap_push ();
    XGrabButton (info->display, Button1, info->modifier,
                 DefaultRootWindow (info->display),
                 False, // owner_events == False: Onboard itself can be clicked
                 ButtonPressMask | ButtonReleaseMask,
                 GrabModeSync, GrabModeAsync, None, None); 
        gdk_flush ();

    if (gdk_error_trap_pop ())
    {
        stop_convert_click(info);
        return False;
    }
    return True;
}

static void
stop_grab(OskUtilGrabInfo* info)
{
        /* Remove grab and filter */
        XUngrabButton (info->display,
                       Button1,
                       info->modifier,
                       DefaultRootWindow (info->display));
}

void
stop_convert_click(OskUtilGrabInfo* info)
{
    if (info->display)
    {
        gdk_window_remove_filter (NULL,
                                  (GdkFilterFunc) osk_util_event_filter,
                                  info);
        stop_grab(info);
    }
    info->button = PRIMARY_BUTTON;
    info->click_type = CLICK_TYPE_SINGLE;
    info->drag_started = False;
    info->display = NULL;

    Py_XDECREF(info->exclusion_rects);
    info->exclusion_rects = NULL;

    Py_XDECREF(info->callback);
    info->callback = NULL; 
}

static unsigned int
get_modifier_state (Display *dpy)
{
    Window root, child;
    int x, y, x_root, y_root;
    unsigned int mask = 0;

    XQueryPointer (dpy, DefaultRootWindow (dpy),
                   &root, &child, &x_root, &y_root, &x, &y, &mask);

    /* remove mouse button states */
    return mask & 0xFF;
}

/**
 * osk_util_convert_primary_click:
 * @button: Button number to convert (unsigned int)
 *
 * Converts the next mouse "left-click" to a @button click.
 */
static PyObject *
osk_util_convert_primary_click (PyObject *self, PyObject *args)
{
    OskUtil *util = (OskUtil*) self;
    OskUtilGrabInfo *info = util->info;
    Display         *dpy;
    unsigned int     button;
    unsigned int     click_type;
    unsigned int     modifier;
    PyObject*        exclusion_rects = NULL;
    PyObject*        callback = NULL;

    if (!PyArg_ParseTuple (args, "II|OO", &button,
                                          &click_type,
                                          &exclusion_rects,
                                          &callback))
        return NULL;

    if (button < 1 || button > 3)
    {
        PyErr_SetString (OSK_EXCEPTION, "unsupported button number");
        return NULL;
    }

    stop_convert_click(info);

    if (exclusion_rects)
    {
        if (!PySequence_Check(exclusion_rects))
        {
            PyErr_SetString(PyExc_ValueError, "expected sequence type");
            return False;
        }
        Py_INCREF(exclusion_rects);
        info->exclusion_rects = exclusion_rects;
    }

    /* cancel the click ? */
    if (button == PRIMARY_BUTTON && 
        click_type == CLICK_TYPE_SINGLE)
    {
        Py_RETURN_NONE;
    }

    dpy = GDK_DISPLAY_XDISPLAY (gdk_display_get_default ());
    modifier = get_modifier_state (dpy);

    info->button = button;
    info->click_type = click_type;
    info->display = dpy;
    info->modifier = modifier;
    Py_XINCREF(callback);         /* Add a reference to new callback */
    Py_XDECREF(info->callback);   /* Dispose of previous callback */
    info->callback = callback;    /* Remember new callback */

    if (!start_grab(info))
    {
        stop_convert_click(info);
        PyErr_SetString (OSK_EXCEPTION, "failed to grab button");
        return NULL;
    }

    gdk_window_add_filter (NULL, (GdkFilterFunc) osk_util_event_filter, info);

    Py_RETURN_NONE;
}

static PyObject *
osk_enable_click_conversion (PyObject *self, PyObject *args)
{
    OskUtil *util = (OskUtil*) self;
    OskUtilGrabInfo *info = util->info;
    Bool     enable;

    if (!PyArg_ParseTuple (args, "B", &enable))
        return NULL;

    info->enable_conversion = enable;

    Py_RETURN_NONE;
}

static PyObject *
osk_util_get_convert_click_button (PyObject *self)
{
    OskUtil *util = (OskUtil*) self;
    return PyInt_FromLong(util->info->button);
}

static PyObject *
osk_util_get_convert_click_type (PyObject *self)
{
    OskUtil *util = (OskUtil*) self;
    return PyInt_FromLong(util->info->click_type);
}

static PyMethodDef osk_util_methods[] = {
    { "convert_primary_click", 
        osk_util_convert_primary_click, 
        METH_VARARGS, NULL },
    { "get_convert_click_button", 
        (PyCFunction)osk_util_get_convert_click_button, 
        METH_NOARGS, NULL },
    { "get_convert_click_type", 
        (PyCFunction)osk_util_get_convert_click_type, 
        METH_NOARGS, NULL },
    { "enable_click_conversion", 
        osk_enable_click_conversion, 
        METH_VARARGS, NULL },
    { NULL, NULL, 0, NULL }
};
