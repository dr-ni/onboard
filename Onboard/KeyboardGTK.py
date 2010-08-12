### Logging ###
import logging
_logger = logging.getLogger("KeyboardGTK")
###############

import gtk
import gobject
import pango

import os
import ctypes

import Onboard.X11 as X11

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class KeyboardGTK(gtk.DrawingArea):

    scanning_time_id = None

    def __init__(self):
        gtk.DrawingArea.__init__(self)
        self.click_timer = None
        self.click_detected = False
        self.saved_pointer_buttons = {}

        self.add_events(gtk.gdk.BUTTON_PRESS_MASK
                      | gtk.gdk.BUTTON_RELEASE_MASK
                      | gtk.gdk.LEAVE_NOTIFY_MASK
                      | gtk.gdk.ENTER_NOTIFY_MASK)

        self.connect("expose_event",         self.expose)
        self.connect("button_press_event",   self._cb_mouse_button_press)
        self.connect("button_release_event", self._cb_mouse_button_release)
        self.connect("enter-notify-event",   self._cb_mouse_enter)
        self.connect("leave-notify-event",   self._cb_mouse_leave)
        self.connect("configure-event",      self._cb_configure_event)
        config.scanning_notify_add(self.reset_scan)

    def clean(self):
        self.stop_click_polling()
        self.reset_pointer_buttons()

    def start_click_polling(self):
        self.stop_click_polling()
        self.click_timer = gobject.timeout_add(20, self._cb_click_timer)
        self.click_detected = False

    def stop_click_polling(self):
        if self.click_timer:
            gobject.source_remove(self.click_timer)
            self.click_timer = None

    def _cb_click_timer(self):
        """ poll for mouse click outside of onboards window """
        rootwin = self.get_screen().get_root_window()
        x, y, mods = rootwin.get_pointer()
        if mods & (gtk.gdk.BUTTON1_MASK
                 | gtk.gdk.BUTTON2_MASK
                 | gtk.gdk.BUTTON3_MASK):
            self.click_detected = True
        elif self.click_detected:
            # button released anywhere outside of onboards control
            self.stop_click_polling()
            self.reset_pointer_buttons()
            return False

        return True

    def _cb_configure_event(self, widget, user_data):
        size = self.get_allocation()
        self.kbwidth = size.width - config.SIDEBARWIDTH # to allow for sidebar
        self.height = size.height

        # For key label size calculations
        pango_context = self.create_pango_context()
        for pane in [self.basePane,] + self.panes:
            pane.on_size_changed(self.kbwidth, self.height, pango_context)
            pane.configure_labels(self.mods, pango_context)

    def _cb_mouse_enter(self, widget, grabbed):
        self.stop_click_polling()
        return True

    def _cb_mouse_leave(self, widget, grabbed):
        """
        horrible.  Grabs pointer when key is pressed, released when cursor
        leaves keyboard
        """

        gtk.gdk.pointer_ungrab()
        if self.active:
            if self.scanningActive:
                self.active = None
                self.scanningActive = None
            else:
                self.release_key(self.active)
            self.queue_draw()

        # another terrible hack
        # start a high frequency timer to detect clicks outside of onboard
        self.start_click_polling()
        return True

    def _cb_mouse_button_release(self,widget,event):
        if self.active:
            #self.active.on = False
            self.release_key(self.active)
            if len(self.stuck) > 0:
                for stick in self.stuck:
                    self.release_key(stick)
                self.stuck = []
            self.active = None

        self.queue_draw()
        return True

    def _cb_mouse_button_press(self,widget,event):
        gtk.gdk.pointer_grab(self.window, True)
        self.stop_click_polling()

        if event.type == gtk.gdk.BUTTON_PRESS:
            self.active = None#is this doing anything

            if config.scanning and self.basePane.columns:
                if self.scanning_time_id:
                    if not self.scanning_y == None:
                        self.press_key(self.scanningActive)
                        gobject.source_remove(self.scanning_time_id)
                        self.reset_scan()
                    else:
                        self.scanning_y = -1
                        gobject.source_remove(self.scanning_time_id)
                        self.scanning_time_id = gobject.timeout_add(
                                config.scanning_interval, self.scan_tick)
                else:
                    self.scanning_time_id = gobject.timeout_add(
                        config.scanning_interval, self.scan_tick)
                    self.scanning_x = -1
            else:
                #TODO tabkeys should work like the others
                for key in self.tabKeys:
                    self.is_key_pressed(key, widget, event)
                context = self.window.cairo_create()
                if self.activePane:
                    key = self.activePane.get_key_at_location(
                        (event.x, event.y), context)
                else:
                    key = self.basePane.get_key_at_location(
                        (event.x, event.y), context)
                if key: self.press_key(key)
        return True

    #Between scans and when value of scanning changes.
    def reset_scan(self, scanning=None):
        if self.scanningActive:
            self.scanningActive.beingScanned = False
        if self.scanning_time_id:
            gobject.source_remove(self.scanning_time_id)
            self.scanning_time_id = None

        self.scanning_x = None
        self.scanning_y = None
        self.queue_draw()

    def expose(self, widget, event):
        context = widget.window.cairo_create()
        context.set_line_width(1.1)

        context.set_source_rgba(float(self.basePane.rgba[0]),
                    float(self.basePane.rgba[1]),
                    float(self.basePane.rgba[2]),
                    float(self.basePane.rgba[3]))#get from .sok
        context.paint()


        self.basePane.paint(context)

        if (self.activePane):

            context.rectangle(0, 0, self.kbwidth, self.height)
            context.set_source_rgba(float(self.activePane.rgba[0]),
                        float(self.activePane.rgba[1]),
                        float(self.activePane.rgba[2]),
                        float(self.activePane.rgba[3]))#get from .sok
            context.fill()
            self.activePane.paint(context)

        for key in self.tabKeys:
            key.paint(context)

        return True

    def _on_mods_changed(self):
        _logger.info("Modifiers have been changed")
        context = self.create_pango_context()
        for pane in [self.basePane,] + self.panes:
            pane.configure_labels(self.mods, context)

    def map_pointer_button(self, button):
        """ map the given button to the primary button """
        assert(button in [2,3])

        if X11.libX11 and X11.libXi:
            self.reset_pointer_buttons()

            for display, device in self.iterate_x_pointers():
                buttons = (ctypes.c_ubyte*1024)()
                num_buttons = X11.XGetDeviceButtonMapping(display, device,
                                                      buttons,
                                                      buttons._length_)
                if num_buttons >= 3:
                    buttons_copy = (ctypes.c_ubyte*buttons._length_) \
                                   .from_buffer_copy(buttons)
                    self.saved_pointer_buttons[device[0].device_id] = \
                                                     (buttons_copy, num_buttons)
                    tmp = buttons[0]
                    buttons[0] = buttons[button-1]
                    buttons[button-1] = tmp
                    X11.XSetDeviceButtonMapping(display, device,
                                            buttons, num_buttons)

    def reset_pointer_buttons(self):
        if X11.libX11 and X11.libXi:
            if self.saved_pointer_buttons:
                for display, device in self.iterate_x_pointers():
                    buttons, num_buttons = self.saved_pointer_buttons.get(
                                                    device[0].device_id, (None, 0))
                    if buttons:
                        X11.XSetDeviceButtonMapping(display, device,
                                                buttons, num_buttons)
            self.saved_pointer_buttons = {}

    def iterate_x_pointers(self):
        """ iterates xinput pointer devices """
        display = X11.XOpenDisplay(os.getenv("DISPLAY"))
        if display:
            num_devices = ctypes.c_int(0)
            device_infos = X11.XListInputDevices(display, num_devices)
            if device_infos:
                for i in range(num_devices.value):
                    device_info = device_infos[i]
                    if device_info.use == X11.IsXExtensionPointer:
                        device = X11.XOpenDevice(display, device_info.id)
                        if device:
                            yield display, device
                            X11.XCloseDevice(display, device)

                X11.XFreeDeviceList(device_infos)
            X11.XCloseDisplay(display)

