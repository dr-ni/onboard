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
    unsigned int modifier;
} OskUtilGrabInfo;

typedef struct {
    PyObject_HEAD
    OskUtilGrabInfo *info;
} OskUtil;

OSK_REGISTER_TYPE (OskUtil, osk_util, "Util")

void
stop_convert_click(OskUtilGrabInfo* info);

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
    util->info->button = 0;

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
        g_free (util->info);
        util->info = NULL;

    }

    OSK_FINISH_DEALLOC (util);
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
            /* Consume original event */
            XAllowEvents (bev->display, GrabModeSync, bev->time);

            if (event->type == ButtonRelease)
            {
                unsigned int button = info->button;
                stop_convert_click(info);

                /* Synthesize button click */
                XTestFakeButtonEvent (bev->display, button, True, CurrentTime);
                XTestFakeButtonEvent (bev->display, button, False, 100);

            }
            return GDK_FILTER_REMOVE;
        }
    }
    return GDK_FILTER_CONTINUE;
}


void
stop_convert_click(OskUtilGrabInfo* info)
{
    if (info->button)
    {
        /* Remove grab and filter */
        XUngrabButton (info->display,
                       Button1,
                       info->modifier,
                       DefaultRootWindow (info->display));

        gdk_window_remove_filter (NULL,
                                  (GdkFilterFunc) osk_util_event_filter,
                                  info);
        info->button = 0;
        info->display = NULL;
    }

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
    unsigned int     modifier;

    if (!PyArg_ParseTuple (args, "I", &button))
        return NULL;

    if (button < 1 || button > 3)
    {
        PyErr_SetString (OSK_EXCEPTION, "unsupported button number");
        return NULL;
    }

    /* cancel the click ? */
    if (button == 1)
    {
        stop_convert_click(info);
        Py_RETURN_NONE;
    }

    /* click convert in progress? */
    if (info->button)
        stop_convert_click(info);

    dpy = GDK_DISPLAY_XDISPLAY (gdk_display_get_default ());
    modifier = get_modifier_state (dpy);

    gdk_error_trap_push ();
    XGrabButton (dpy, Button1, modifier,
                 DefaultRootWindow (dpy), True,
                 ButtonPressMask | ButtonReleaseMask,
                 GrabModeSync, GrabModeAsync, None, None);
    gdk_flush ();

    if (gdk_error_trap_pop ())
    {
        PyErr_SetString (OSK_EXCEPTION, "failed to grab button");
        return NULL;
    }

    info->display = dpy;
    info->button = button;
    info->modifier = modifier;

    gdk_window_add_filter (NULL, (GdkFilterFunc) osk_util_event_filter, info);

    Py_RETURN_NONE;
}

static PyObject *
osk_util_get_convert_click_button (PyObject *self)
{
    OskUtil *util = (OskUtil*) self;
    return PyInt_FromLong(util->info->button);
}

static PyMethodDef osk_util_methods[] = {
    { "convert_primary_click", osk_util_convert_primary_click, METH_VARARGS, NULL },
    { "get_convert_click_button", osk_util_get_convert_click_button, METH_NOARGS, NULL },
    { NULL, NULL, 0, NULL }
};
