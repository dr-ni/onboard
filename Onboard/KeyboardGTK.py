""" GTK specific keyboard class """

import os
import ctypes

from gi.repository import GObject, Gdk, Gtk

from Onboard.utils import Rect

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
       # self.set_double_buffered(False)
        self.set_has_tooltip(True)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.ENTER_NOTIFY_MASK)

        self.connect("draw",                 self.draw)
        self.connect("button_press_event",   self._cb_mouse_button_press)
        self.connect("button_release_event", self._cb_mouse_button_release)
        self.connect("motion-notify-event",  self._cb_motion)
        self.connect("query-tooltip",        self._cb_query_tooltip)
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
            self.on_outside_click()
            return False

        return True

    def _cb_configure_event(self, widget, user_data):
        self.canvas_rect = Rect(0, 0,
                                self.get_allocated_width(),
                                self.get_allocated_height())
        self.update_layout()

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
                self.queue_draw()
            else:
                self.release_key(self.active_key)

        # another terrible hack
        # start a high frequency timer to detect clicks outside of onboard
        self.start_click_polling()
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
                key = self.get_key_at_location((event.x, event.y))
                self.active_key = key
                if key:
                    self.press_key(key, event.button)
        return True

    def _cb_mouse_button_release(self,widget,event):
        if self.active_key:
            self.release_key(self.active_key)
            self.active_key = None
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

    def _cb_motion(self, widget, event):
        if event.state & (Gdk.ModifierType.BUTTON1_MASK \
                        | Gdk.ModifierType.BUTTON2_MASK
                        | Gdk.ModifierType.BUTTON3_MASK):
            # move button pressed?
            if self.move_start_position:
                rootwin = Gdk.get_default_root_window()
                dunno, x, y, mods = rootwin.get_pointer()
                wx, wy = (self.move_start_position[0] + x,
                          self.move_start_position[1] + y)
                window = self.get_window().get_parent()
                window.move(wx, wy)

    def _cb_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        key = self.get_key_at_location((x, y))
        if key:
            if key.tooltip:
                r = Gdk.Rectangle()
                r.x, r.y, r.width, r.height = key.get_canvas_rect().to_list()
                tooltip.set_tip_area(r)   # no effect in oneiric?
                tooltip.set_text(key.tooltip)
                return True
        return False


    def draw(self, widget, context):
        #_logger.debug("Draw: clip_extents=" + str(context.clip_extents()))

        clip_rect = Rect.from_extents(*context.clip_extents())
        get_layer_fill_rgba = self.color_scheme.get_layer_fill_rgba

        # paint background
        context.set_source_rgba(*get_layer_fill_rgba(0))
        context.paint()

        layer_ids = self.layout.get_layer_ids()
        for item in self.layout.iter_visible_items():
            if item.layer_id:

                # draw layer background
                layer_index = layer_ids.index(item.layer_id)
                rect = item.parent.get_canvas_rect()

                context.rectangle(*rect)
                context.set_source_rgba(*get_layer_fill_rgba(layer_index))
                context.fill()

            if item.is_key() and \
               clip_rect.intersects(item.get_canvas_rect()):
               # print "drawing ", item.id
                item.draw(context)
                item.draw_image(context)
                item.draw_font(context)

        return True

    def _on_mods_changed(self):
        _logger.info("Modifiers have been changed")
        self.update_font_sizes()

    def redraw(self, key = None):
        """
        Queue redrawing for a just a single key or the whold keyboard.
        """
        if key:
            rect = key.get_border_rect()
            rect = rect.inflate(2.0) # account for stroke width, anti-aliasing
            rect = key.context.log_to_canvas_rect(rect)
            self.queue_draw_area(*rect)
        else:
            self.queue_draw()


    def update_font_sizes(self):
        """
        Cycles through each group of keys and set each key's
        label font size to the maximum possible for that group.
        """
        context = self.create_pango_context()
        for keys in self.layout.get_key_groups().values():

            max_size = 0
            for key in keys:
                key.configure_label(self.mods)
                best_size = key.get_best_font_size(context)
                if best_size:
                    if not max_size or best_size < max_size:
                        max_size = best_size

            for key in keys:
                key.font_size = max_size

    def emit_quit_onboard(self, data=None):
        _logger.debug("Entered emit_quit_onboard")
        self.get_parent().emit("quit-onboard")

