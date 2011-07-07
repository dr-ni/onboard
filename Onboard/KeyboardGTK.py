### Logging ###
import logging
_logger = logging.getLogger("KeyboardGTK")
###############

import os
import ctypes

from gi.repository import GObject, Gdk, Gtk

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class KeyboardGTK(Gtk.DrawingArea):

    scanning_time_id = None

    def __init__(self):
        Gtk.DrawingArea.__init__(self)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK)

        self.connect("draw",                 self.expose)
        self.connect("button_press_event",   self._cb_mouse_button_press)
        self.connect("button_release_event", self._cb_mouse_button_release)
        self.connect("leave-notify-event",   self._cb_mouse_leave)
        self.connect("configure-event",      self._cb_configure_event)

    def clean(self):
        pass

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
        if self.active:
            if self.scanningActive:
                self.active = None
                self.scanningActive = None
            else:
                self.release_key(self.active)
            self.queue_draw()

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
        Gdk.pointer_grab(self.get_window(),
                         True,
                         Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK,
                         None, None,
                         event.time)

        if event.type == Gdk.EventType.BUTTON_PRESS:
            self.active = None#is this doing anything
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
                #TODO tabkeys should work like the others
                for key in self.tabKeys:
                    self.is_key_pressed(key, widget, event)
                context = self.get_window().cairo_create()
                if self.activePane:
                    key = self.activePane.get_key_at_location(
                        (event.x, event.y), context)
                else:
                    key = self.basePane.get_key_at_location(
                        (event.x, event.y), context)
                if key:
                    self.press_key(key)
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

