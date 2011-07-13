""" GTK specific keyboard class """

import os
import ctypes

from gi.repository import GObject, Gdk, Gtk

### Logging ###
import logging
_logger = logging.getLogger("KeyboardGTK")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class KeyboardGTK(Gtk.DrawingArea):

    scanning_time_id = None

    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        self.click_timer = None
        self.active_key = None
        self.click_detected = False

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.ENTER_NOTIFY_MASK)

        self.connect("draw",                 self.expose)
        self.connect("button_press_event",   self._cb_mouse_button_press)
        self.connect("button_release_event", self._cb_mouse_button_release)
        self.connect("leave-notify-event",   self._cb_mouse_leave)
        self.connect("configure-event",      self._cb_configure_event)

    def clean(self):
        self.stop_click_polling()

    def start_click_polling(self):
        self.stop_click_polling()
        self.click_timer = GObject.timeout_add(2, self._cb_click_timer)
        self.click_detected = False

    def stop_click_polling(self):
        if self.click_timer:
            GObject.source_remove(self.click_timer)
            self.click_timer = None

    def _cb_click_timer(self):
        """ poll for mouse click outside of onboards window """
        rootwin = Gdk.get_default_root_window()
        dunno, x, y, mods = rootwin.get_pointer()
        if mods & (Gdk.ModifierType.BUTTON1_MASK
                 | Gdk.ModifierType.BUTTON2_MASK
                 | Gdk.ModifierType.BUTTON3_MASK):
            self.click_detected = True
        elif self.click_detected:
            # button released anywhere outside of onboards control
            self.stop_click_polling()
            self.next_mouse_click_button = None
            self.update_ui()
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

    def _cb_mouse_leave(self, widget, event):
        """
        horrible.  Grabs pointer when key is pressed, released when cursor
        leaves keyboard
        """

        Gdk.pointer_ungrab(event.time)
        if self.active_key:
            if self.scanningActive:
                self.active_key = None      
                self.scanningActive = None
            else:
                self.release_key(self.active_key)
            self.queue_draw()

        # another terrible hack
        # start a high frequency timer to detect clicks outside of onboard
        self.start_click_polling()
        return True

    def _cb_mouse_button_release(self,widget,event):
        if self.active_key:
            #self.active_key.on = False
            self.release_key(self.active_key)
            self.active_key = None

        self.queue_draw()
        return True

    def _cb_mouse_button_press(self,widget,event):
        Gdk.pointer_grab(self.get_window(),
                         True,
                         Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK,
                         None, None,
                         event.time)
        self.stop_click_polling()

        if event.type == Gdk.EventType.BUTTON_PRESS:
            if config.enable_scanning and self.basePane.columns:
                if self.scanning_time_id:
                    if not self.scanning_y == None:
                        self.press_key(self.scanningActive)
                        GObject.source_remove(self.scanning_time_id)
                        self.reset_scan()
                    else:
                        self.scanning_y = -1
                        GObject.source_remove(self.scanning_time_id)
                        self.scanning_time_id = GObject.timeout_add(
                                config.scanning_interval, self.scan_tick)
                else:
                    self.scanning_time_id = GObject.timeout_add(
                        config.scanning_interval, self.scan_tick)
                    self.scanning_x = -1
            else:
                context = self.get_window().cairo_create()
                key = self.get_key_at_location((event.x, event.y), context)
                if key: 
                    self.press_key(key, event.button)
        return True 

    #Between scans and when value of scanning changes.
    def reset_scan(self, scanning=None):
        if self.scanningActive:
            self.scanningActive.beingScanned = False
        if self.scanning_time_id:
            GObject.source_remove(self.scanning_time_id)
            self.scanning_time_id = None

        self.scanning_x = None
        self.scanning_y = None
        self.queue_draw()

    def expose(self, widget, context):
        context.set_source_rgba(*self.basePane.rgba)
        context.paint()
        self.basePane.paint(context)

        if (self.activePane):
            context.rectangle(0, 0, self.kbwidth, self.height)
            context.set_source_rgba(*self.activePane.rgba)
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

