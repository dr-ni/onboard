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
    PyObject_HEAD

} OskUtil;

typedef struct {
    unsigned int button;
    unsigned int modifier;
} OskUtilGrabInfo;

OSK_REGISTER_TYPE (OskUtil, osk_util, "Util")

static int
osk_util_init (OskUtil *util, PyObject *args, PyObject *kwds)
{
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
                /* Remove grab and filter */
                XUngrabButton (GDK_DISPLAY (),
                               Button1, info->modifier,
                               GDK_ROOT_WINDOW ());

                gdk_window_remove_filter (NULL,
                                          (GdkFilterFunc) osk_util_event_filter,
                                          info);

                /* Synthesize button click */
                XTestFakeButtonEvent (bev->display, info->button, True, CurrentTime);
                XTestFakeButtonEvent (bev->display, info->button, False, 100);

                g_free (info);
            }
            return GDK_FILTER_REMOVE;
        }
    }
    return GDK_FILTER_CONTINUE;
}

static unsigned int
get_modifier_state (void)
{
    Window root, child;
    int x, y, x_root, y_root;
    unsigned int mask = 0;

    XQueryPointer (GDK_DISPLAY (), GDK_ROOT_WINDOW (),
                   &root, &child, &x_root, &y_root, &x, &y, &mask);

    /* remove mouse button states */
    return mask & 0xFF;
}

/**
 * osk_util_convert_primary_click:
 * @button: Button number to convert (unsigned int)
 *
 *
 */
static PyObject *
osk_util_convert_primary_click (PyObject *self, PyObject *args)
{
    OskUtilGrabInfo *info;
    unsigned int     button;
    unsigned int     modifier;

    if (!PyArg_ParseTuple (args, "I", &button))
        return NULL;

    if (button < 2 || button > 3)
    {
        PyErr_SetString (OSK_EXCEPTION, "unsupported button number");
        return NULL;
    }

    modifier = get_modifier_state ();

    gdk_error_trap_push ();
    XGrabButton (GDK_DISPLAY (), Button1, modifier,
                 GDK_ROOT_WINDOW (), True,
                 ButtonPressMask | ButtonReleaseMask,
                 GrabModeSync, GrabModeAsync, None, None);
    gdk_flush ();

    if (gdk_error_trap_pop ())
    {
        PyErr_SetString (OSK_EXCEPTION, "failed to grab button");
        return NULL;
    }

    info = g_new (OskUtilGrabInfo, 1);
    info->button = button;
    info->modifier = modifier;

    gdk_window_add_filter (NULL, (GdkFilterFunc) osk_util_event_filter, info);

    Py_RETURN_NONE;
}

static PyMethodDef osk_util_methods[] = {
    { "convert_primary_click", osk_util_convert_primary_click, METH_VARARGS, NULL },
    { NULL, NULL, 0, NULL }
};
