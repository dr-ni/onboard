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
#include "osk_util.h"

#include <signal.h>
#include <glib-unix.h>

#include <gdk/gdkx.h>
#include <X11/Xatom.h>
#include <X11/extensions/XTest.h>
#include <X11/extensions/XTest.h>



#define MAX_GRAB_DURATION 15   // max time to hold a pointer grab [s]


typedef struct {
    Display *xdisplay;
    unsigned int button;
    unsigned int click_type;
    unsigned int drag_started;
    unsigned int modifier;
    Bool         enable_conversion;
    PyObject*    exclusion_rects;
    PyObject*    click_done_callback;
    guint        grab_release_timer;
} OskUtilGrabInfo;

typedef struct {
    PyObject_HEAD

    GdkDisplay *display;
    Atom atom_net_active_window;
    PyObject* signal_callbacks[_NSIG];
    PyObject* onboard_toplevels;

    Atom* watched_root_properties;
    int  num_watched_root_properties;
    PyObject* root_property_callback;

    OskUtilGrabInfo *info;
} OskUtil;

static void stop_convert_click(OskUtilGrabInfo* info);
static Display* get_x_display(OskUtil* util);

OSK_REGISTER_TYPE (OskUtil, osk_util, "Util")

static int
osk_util_init (OskUtil *util, PyObject *args, PyObject *kwds)
{
    util->info = g_new0 (OskUtilGrabInfo, 1);
    util->info->button = PRIMARY_BUTTON;
    util->info->click_type = CLICK_TYPE_SINGLE;
    util->info->enable_conversion = True;
    util->display = gdk_display_get_default ();

    Display* xdisplay = get_x_display(util);
    if (xdisplay) // not on wayland?
    {
        int nop;

        util->atom_net_active_window = \
                                XInternAtom (xdisplay, "_NET_ACTIVE_WINDOW", True);
        if (!XTestQueryExtension (xdisplay, &nop, &nop, &nop, &nop))
        {
            PyErr_SetString (OSK_EXCEPTION, "failed initialize XTest extension");
            return -1;
        }

        /* send events inspite of other grabs */
        XTestGrabControl (xdisplay, True);
    }

    return 0;
}

static void
osk_util_dealloc (OskUtil *util)
{
    int i;

    if (util->info)
    {
        stop_convert_click(util->info);
        g_free (util->info);
        util->info = NULL;
    }

    for (i=0; i<G_N_ELEMENTS(util->signal_callbacks); i++)
    {
        Py_XDECREF(util->signal_callbacks[i]);
        util->signal_callbacks[i] = NULL;
    }

    Py_XDECREF(util->onboard_toplevels);
    util->onboard_toplevels = NULL;

    Py_XDECREF(util->root_property_callback);
    util->root_property_callback = NULL;

    PyMem_Free(util->watched_root_properties);

    OSK_FINISH_DEALLOC (util);
}

static Display*
get_x_display (OskUtil* util)
{
    if (GDK_IS_X11_DISPLAY (util->display)) // not on wayland?
        return GDK_DISPLAY_XDISPLAY (util->display);
    return NULL;
}

static void
notify_click_done(PyObject* callback)
{
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

    //printf("event %d", event->type);
    if (event->type == ButtonPress || event->type == ButtonRelease)
    {
        XButtonEvent *bev = (XButtonEvent *) event;
        if (bev->button == Button1)
        {
            unsigned int button = info->button;
            unsigned int click_type = info->click_type;
            Bool drag_started = info->drag_started;
            PyObject* callback = info->click_done_callback;
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

                    /* Faked button presses on the touch screen off the Nexus 7
                     * are offset by a couple of hundred pixels.
                     * Move the pointer to the actual click position. */
                    XTestFakeMotionEvent(bev->display, -1, bev->x_root, bev->y_root, CurrentTime);

                    /* Synthesize button click */
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

                    // notify python that the click is done
                    notify_click_done(callback);
                }
            }
            Py_XDECREF(callback);
        }
    }
    return GDK_FILTER_CONTINUE;
}

static Bool
start_grab(OskUtilGrabInfo* info)
{
    gdk_error_trap_push ();
    XGrabButton (info->xdisplay, Button1, info->modifier,
                 DefaultRootWindow (info->xdisplay),
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
    gdk_error_trap_push();
    XUngrabButton(info->xdisplay,
                  Button1,
                  info->modifier,
                  DefaultRootWindow(info->xdisplay));
    gdk_error_trap_pop_ignored();
}

static void
stop_convert_click(OskUtilGrabInfo* info)
{
    if (info->xdisplay)
    {
        gdk_window_remove_filter (NULL,
                                  (GdkFilterFunc) osk_util_event_filter,
                                  info);
        stop_grab(info);
    }
    info->button = PRIMARY_BUTTON;
    info->click_type = CLICK_TYPE_SINGLE;
    info->drag_started = False;
    info->xdisplay = NULL;

    Py_XDECREF(info->exclusion_rects);
    info->exclusion_rects = NULL;

    Py_XDECREF(info->click_done_callback);
    info->click_done_callback = NULL;

    if (info->grab_release_timer)
        g_source_remove (info->grab_release_timer);
    info->grab_release_timer = 0;
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

static
gboolean grab_release_timer_callback(gpointer user_data)
{
    OskUtilGrabInfo* info = (OskUtilGrabInfo*) user_data;

    PyObject* callback = info->click_done_callback;
    Py_XINCREF(callback);
    notify_click_done(callback);
    Py_XDECREF(callback);

    stop_convert_click(info);
    
    info->grab_release_timer = 0;

    return False;
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
    info->xdisplay = dpy;
    info->modifier = modifier;
    Py_XINCREF(callback);         /* Add a reference to new callback */
    Py_XDECREF(info->click_done_callback);   /* Dispose of previous callback */
    info->click_done_callback = callback;    /* Remember new callback */

    if (!start_grab(info))
    {
        stop_convert_click(info);
        PyErr_SetString (OSK_EXCEPTION, "failed to grab button");
        return NULL;
    }

    // Make sure the grab can't get stuck for long. On the Nexus 7 this
    // is a frequent occurrence.
    info->grab_release_timer = g_timeout_add_seconds(MAX_GRAB_DURATION,
                                                     grab_release_timer_callback,
                                                     info);

    gdk_window_add_filter (NULL, (GdkFilterFunc) osk_util_event_filter, info);

    Py_RETURN_NONE;
}

static PyObject *
osk_util_enable_click_conversion (PyObject *self, PyObject *args)
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

static PyObject *
osk_util_set_x_property (PyObject *self, PyObject *args)
{
    OskUtil *util = (OskUtil*) self;
    int wid;
    char* property_name;
    PyObject* property_value;

    Display* xdisplay = get_x_display(util);
    if (xdisplay == NULL)
    {
        PyErr_SetString(PyExc_TypeError, "Not an X display");
        return NULL;
    }

    if (!PyArg_ParseTuple (args, "isO:set_x_property",
                           &wid, &property_name, &property_value))
        return NULL;

    Atom value_name  = XInternAtom(xdisplay, property_name, False);

    if (PyInt_Check(property_value))
    {
        guint32 int_value = (guint32) PyInt_AsLong(property_value);
        XChangeProperty (xdisplay, wid,
                         value_name, XA_CARDINAL, 32, PropModeReplace,
                         (guchar*) &int_value, 1);
    }
    else if (PyUnicode_Check(property_value))
    {
        PyObject* string_value = PyUnicode_AsUTF8String(property_value);
        if (!string_value)
        {
            PyErr_SetString(PyExc_ValueError, "failed to encode value as utf-8");
            return NULL;
        }
        Atom atom_value = XInternAtom(xdisplay,
                               PyString_AsString(string_value), False);
        XChangeProperty (xdisplay, wid,
                         value_name, XA_ATOM, 32, PropModeReplace,
                         (guchar*) &atom_value, 1);

        Py_DECREF(string_value);
    }
    else
    {
        PyErr_SetString(PyExc_TypeError, "Unsupported value type");
        return NULL;
    }
    Py_RETURN_NONE;
}

static gboolean
signal_handler(gpointer user_data)
{
    PyObject* callback = (PyObject*) user_data;
    PyObject* arglist = NULL;
    PyObject* result  = PyObject_CallObject(callback, arglist);
    Py_XDECREF(arglist);
    Py_XDECREF(result);
    return True;
}

static PyObject *
osk_util_set_unix_signal_handler (PyObject *self, PyObject *args)
{
    OskUtil *util = (OskUtil*) self;
    int signal = 0;
    PyObject*        callback = NULL;

    if (!PyArg_ParseTuple (args, "IO", &signal, &callback))
        return NULL;

    Py_XINCREF(callback);              /* Add a reference to new callback */
    Py_XDECREF(util->signal_callbacks[signal]); /* Dispose of previous callback */
    util->signal_callbacks[signal] = callback;  /* Remember new callback */

    g_unix_signal_add(signal, signal_handler, callback);

    Py_RETURN_NONE;
}


static Window
get_xid_of_gtkwidget(PyObject* widget)
{
    Window xid = None;
    if (widget)
    {
        PyObject* gdk_win = PyObject_CallMethod(widget, "get_window", NULL);
        if (gdk_win)
        {
            if (gdk_win != Py_None)
            {
                PyObject* _xid = PyObject_CallMethod(gdk_win, 
                                                    "get_xid", NULL);
                if (_xid)
                {
                    xid = (Window)PyLong_AsLong(_xid);
                    Py_DECREF(_xid);
                }
            }
            Py_DECREF(gdk_win);
        }
    }
    return xid;
}

/* Replacement for gdk_x11_screen_get_active_window().
 * The gdk original somehow failed repeatetly with X error BadWindow on
 * Francesco's system.
 */
static Window
osk_util_get_active_window (OskUtil* util)
{
    Display* xdisplay = get_x_display(util);
    Window result = None;
    Atom actual_type;
    gint actual_format;
    gulong nwindows;
    gulong nleft;
    guchar *data = NULL;

    Window root = DefaultRootWindow (xdisplay);

    gdk_error_trap_push ();
    if (XGetWindowProperty (xdisplay, root,
                util->atom_net_active_window,
                0, 1, False, XA_WINDOW,
                &actual_type, &actual_format,
                &nwindows, &nleft, &data)
            == Success)
    {
        if ((actual_type == XA_WINDOW) && (actual_format == 32) && (data))
        {
            Window window = *(Window *) data;
            if (window != None)
                result = window;
        }
    }

    if (gdk_error_trap_pop ())
        result = None;

    if (data)
        XFree (data);

    return result;
}


// Raise Onboard's windows on top of unity dash and full-screen windows.
static void
raise_windows_to_top (OskUtil *util)
{
    Display* xdisplay = get_x_display(util);

    // find xid of the active window (_NET_ACTIVE_WINDOW)
    Window parent_xid = None;
    Window active_xid = osk_util_get_active_window(util);
    if (active_xid != None)
    {
        // Is the active window unity dash or unity-2d dash?
        gdk_error_trap_push ();
        XTextProperty text_prop = {NULL};
        int ret = XGetWMName(xdisplay, active_xid, &text_prop);
        if (!gdk_error_trap_pop () && ret)
        {
            if (// Precise
                strcmp((char*)text_prop.value, "launcher") == 0 ||
                strcmp((char*)text_prop.value, "Dash") == 0 ||
                strcmp((char*)text_prop.value, "unity-2d-shell") == 0 ||
                // Quantal
                strcmp((char*)text_prop.value, "unity-launcher") == 0 ||
                strcmp((char*)text_prop.value, "unity-dash") == 0
                )
            {
                //printf("%s, 0x%x\n", text_prop.value, active_xid);
                parent_xid = active_xid;
            }
        }
    }

    // Loop through onboard's toplevel windows.
    int i;
    int n = PySequence_Length(util->onboard_toplevels);
    for (i = 0; i < n; i++)
    {
        PyObject* window = PySequence_GetItem(util->onboard_toplevels, i);
        if (window == NULL)
            break;

        Window xid = get_xid_of_gtkwidget(window);
        if (xid)
        {
            // Raise onboard.
            // TransientForHint=None seems to be enough to rise over
            // full-screen windows.
            //printf("raising on top of 0x%x\n", parent_xid);
            XSetTransientForHint (xdisplay, xid, parent_xid);
            XRaiseWindow(xdisplay, xid);
        }
    }
}

static GdkFilterReturn
event_filter_keep_windows_on_top (GdkXEvent *gdk_xevent,
                                  GdkEvent  *gdk_event,
                                  OskUtil   *util)
{
    XEvent *event = gdk_xevent;

    if (event->type == PropertyNotify)
    {
        XPropertyEvent *e = (XPropertyEvent *) event;
        if (e->atom == util->atom_net_active_window)
        {
            raise_windows_to_top(util);
        }
    }
    return GDK_FILTER_CONTINUE;
}

static PyObject *
osk_util_keep_windows_on_top (PyObject *self, PyObject *args)
{
    OskUtil *util = (OskUtil*) self;
    PyObject* windows = NULL;

    Display* xdisplay = get_x_display(util);
    if (xdisplay == NULL)
        Py_RETURN_NONE;

    if (!PyArg_ParseTuple (args, "O", &windows))
        return NULL;

    if (!PySequence_Check(windows))
    {
        PyErr_SetString(PyExc_ValueError, "expected sequence type");
        return NULL;
    }

    GdkWindow* root = gdk_get_default_root_window();

    XSelectInput(xdisplay, GDK_WINDOW_XID(root), PropertyChangeMask);

    Py_XINCREF(windows);
    Py_XDECREF(util->onboard_toplevels);
    util->onboard_toplevels = windows;

    // raise windows immediately on top of existing full-screen windows
    raise_windows_to_top(util);

    // install filter to raise them again when top-levels are activated
    gdk_window_add_filter (root,
                           (GdkFilterFunc) event_filter_keep_windows_on_top,
                           util);
    Py_RETURN_NONE;
}

static GdkFilterReturn
event_filter_root_property_notify (GdkXEvent *gdk_xevent,
                                   GdkEvent  *gdk_event,
                                   OskUtil   *util)
{
    XEvent *event = gdk_xevent;

    if (event->type == PropertyNotify)
    {
        XPropertyEvent *e = (XPropertyEvent *) event;
        int i;
        Atom* atoms = util->watched_root_properties;
        PyObject* callback = util->root_property_callback;
        for (i=0; i<util->num_watched_root_properties; i++)
        {
            if (e->atom == atoms[i])
            {
                char* name = XGetAtomName(e->display, e->atom);
                PyObject* arglist = Py_BuildValue("(s)", name);
                PyObject* result  = PyObject_CallObject(callback, arglist);
                Py_XDECREF(arglist);
                Py_XDECREF(result);
                XFree(name);
            }
        }

    }
    return GDK_FILTER_CONTINUE;
}

static PyObject *
osk_util_connect_root_property_notify (PyObject *self, PyObject *args)
{
    OskUtil *util = (OskUtil*) self;
    PyObject* properties = NULL;
    PyObject* callback = NULL;

    Display* xdisplay = get_x_display(util);
    if (xdisplay == NULL)
        Py_RETURN_NONE;

    if (!PyArg_ParseTuple (args, "OO", &properties, &callback))
        return NULL;

    if (!PySequence_Check(properties))
    {
        PyErr_SetString(PyExc_ValueError, "expected sequence type");
        return NULL;
    }

    int n = PySequence_Length(properties);
    util->watched_root_properties = (Atom*) PyMem_Realloc(
                          util->watched_root_properties, sizeof(Atom) * n);
    util->num_watched_root_properties = 0;

    int i;
    for (i = 0; i < n; i++)
    {
        PyObject* property = PySequence_GetItem(properties, i);
        if (property == NULL)
            break;
        if (!PyUnicode_Check(property))
        {
            PyErr_SetString(PyExc_ValueError, "elements must be unicode strings");
            return NULL;
        }
        PyObject* str_prop = PyUnicode_AsUTF8String(property);
        if (!str_prop)
        {
            PyErr_SetString(PyExc_ValueError, "failed to encode value as utf-8");
            return NULL;
        }

        char* str = PyString_AsString(str_prop);
        Atom atom = XInternAtom(xdisplay, str, True);
        util->watched_root_properties[i] = atom;   // may be None

        Py_DECREF(str_prop);
        Py_DECREF(property);
    }
    util->num_watched_root_properties = n;

    Py_XINCREF(callback);                 /* Add a reference to new callback */
    Py_XDECREF(util->root_property_callback); /* Dispose of previous callback */
    util->root_property_callback = callback;    /* Remember new callback */

    GdkWindow* root = gdk_get_default_root_window();

    XSelectInput(xdisplay, GDK_WINDOW_XID(root), PropertyChangeMask);

    // install filter to raise them again when top-levels are activated
    gdk_window_add_filter (root,
                           (GdkFilterFunc) event_filter_root_property_notify,
                           util);
    Py_RETURN_NONE;
}

static PyObject*
get_window_name(Display* display, Window window)
{
    XTextProperty prop;
    int len;
    char **list = NULL;
    PyObject* result = NULL;
    Atom _NET_WM_NAME = XInternAtom(display, "_NET_WM_NAME", True);

    gdk_error_trap_push ();
    if(!XGetTextProperty(display, window, &prop, _NET_WM_NAME) || prop.nitems == 0)
        if(!XGetWMName(display, window, &prop) || prop.nitems == 0)
            return NULL;

    if (gdk_error_trap_pop ())
    {
        Py_RETURN_NONE;
    }

    if(prop.encoding == XA_STRING)
    {
        result = PyUnicode_FromString((char*)prop.value);
    }
    else if(!XmbTextPropertyToTextList(display, &prop, &list, &len) && len > 0)
    {
        result = PyUnicode_FromString(list[0]);
        XFreeStringList(list);
    }
    XFree(prop.value);

    return result;
}

static PyObject *
osk_util_get_current_wm_name (PyObject *self)
{
    OskUtil *util = (OskUtil*) self;
    PyObject* result = NULL;

    Display* xdisplay = get_x_display(util);
    if (xdisplay == NULL)
        Py_RETURN_NONE;

    Atom _NET_SUPPORTING_WM_CHECK = 
                        XInternAtom(xdisplay, "_NET_SUPPORTING_WM_CHECK", True);
    if (_NET_SUPPORTING_WM_CHECK != None)
    {
        GdkWindow*    root = gdk_get_default_root_window();
        Atom          actual_type;
        int           actual_format;
        unsigned long nwindows, nleft;
        Window        *xwindows;

        XGetWindowProperty (xdisplay, GDK_WINDOW_XID(root),
                            _NET_SUPPORTING_WM_CHECK, 0L, UINT_MAX, False, 
                            XA_WINDOW, &actual_type, &actual_format,
                            &nwindows, &nleft, (unsigned char **) &xwindows);
        if (actual_type == XA_WINDOW && nwindows > 0 && xwindows[0] != None)
            result = get_window_name(xdisplay, xwindows[0]);

        XFree(xwindows);
    }

    if (result)
        return result;
    Py_RETURN_NONE;
}

static PyObject *
osk_util_remove_atom_from_property(PyObject *self, PyObject *args)
{
    OskUtil *util = (OskUtil*) self;
    PyObject* window = NULL;
    PyObject* result = NULL;
    char* property_name = NULL;
    char* value_name = NULL;

    Display* xdisplay = get_x_display(util);
    if (xdisplay == NULL)
    {
        PyErr_SetString(PyExc_TypeError, "Not an X display");
        return NULL;
    }

    if (!PyArg_ParseTuple (args, "Oss", &window, &property_name, &value_name))
        return NULL;

    Atom property_atom = XInternAtom(xdisplay, property_name, True);
    Atom value_atom    = XInternAtom(xdisplay, value_name, True);
    Window xwindow = get_xid_of_gtkwidget(window);
    if (property_atom != None &&
        value_atom != None &&
        xwindow)
    {
        Atom          actual_type;
        int           actual_format;
        unsigned long nstates, nleft;
        Atom         *states;

        // Get all current states
        XGetWindowProperty (xdisplay, xwindow, property_atom, 
                            0L, 12L, False, 
                            XA_ATOM, &actual_type, &actual_format,
                            &nstates, &nleft, (unsigned char **) &states);
        if (actual_type == XA_ATOM)
        {
            int i, new_len;
            Atom new_states[12];
            Bool value_found = False;

            for (i=0, new_len=0; i<nstates; i++)
                if (states[i] == value_atom)
                    value_found = True;
                else
                    new_states[new_len++] = states[i];

            // Set the new states without value_atom
            if (value_found)
                XChangeProperty (xdisplay, xwindow, property_atom, XA_ATOM,
                               32, PropModeReplace, (guchar*) new_states, new_len);

            result = PyBool_FromLong(value_found);
        }
        XFree(states);
    }

    if (result)
        return result;
    Py_RETURN_NONE;
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
        osk_util_enable_click_conversion,
        METH_VARARGS, NULL },
    { "set_x_property",
        osk_util_set_x_property,
        METH_VARARGS, NULL },
    { "set_unix_signal_handler",
        osk_util_set_unix_signal_handler,
        METH_VARARGS, NULL },
    { "keep_windows_on_top",
        osk_util_keep_windows_on_top,
        METH_VARARGS, NULL },
    { "connect_root_property_notify",
        osk_util_connect_root_property_notify,
        METH_VARARGS, NULL },
    { "get_current_wm_name",
        (PyCFunction) osk_util_get_current_wm_name,
        METH_NOARGS, NULL },
    { "remove_atom_from_property",
        (PyCFunction) osk_util_remove_atom_from_property,
        METH_VARARGS, NULL },
    { NULL, NULL, 0, NULL }
};
