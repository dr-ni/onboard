""" GTK specific keyboard class """

import os
import ctypes

import cairo
from gi.repository import GObject, Gdk, Gtk

from Onboard.utils import Rect

from gettext import gettext as _

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
        self.active_key = None
        self.opacity_timer = None
        self.click_timer = None
        self.click_detected = False
        self.move_start_position = None
       # self.set_double_buffered(False)
        self.set_has_tooltip(True)
        self.set_app_paintable(True)

        visual = Gdk.Screen.get_default().get_rgba_visual()
        if visual:
            self.set_visual(visual)

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
        self.connect("enter-notify-event",   self._cb_mouse_enter)
        self.connect("leave-notify-event",   self._cb_mouse_leave)
        self.connect("configure-event",      self._cb_configure_event)

        if self.is_opacify_enabled():
            self.start_opacity_timer()

    def cleanup(self):
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
        dunno, x, y, mask = rootwin.get_pointer()
        if mask & (Gdk.ModifierType.BUTTON1_MASK |
                   Gdk.ModifierType.BUTTON2_MASK |
                   Gdk.ModifierType.BUTTON3_MASK):
            self.click_detected = True
        elif self.click_detected:
            # button released anywhere outside of onboards control
            self.stop_click_polling()
            self.on_outside_click()
            return False

        return True

    def is_opacify_enabled(self):
        screen = self.get_screen()
        return screen and  screen.is_composited() and \
               (config.opacity != 100 or \
               config.inactive_opacity != 100)

    def set_keyboard_opacity(self, opacity):
        wnd = self.get_kbd_window()
        screen = self.get_screen()
        if wnd and screen and  screen.is_composited():
            _logger.debug(_("setting keyboard opacity to {}%") \
                                .format(opacity))
            wnd.set_opacity(opacity / 100.0)

    def update_opacity(self):
        self.start_opacity_timer()

    def update_inactive_opacity(self):
        self.set_keyboard_opacity(config.inactive_opacity)

    def start_opacity_timer(self):
        if not config.xid_mode:
            self.stop_opacity_timer()
            delay = int(config.opacify_delay * 1000)
            self.opacity_timer = GObject.timeout_add(delay,
                                                     self._cb_opacity_timer)

    def stop_opacity_timer(self):
        if not config.xid_mode:
            if self.opacity_timer:
                GObject.source_remove(self.opacity_timer)
                self.opacity_timer = None
            self.set_keyboard_opacity(config.opacity)

    def _cb_opacity_timer(self):
        self.set_keyboard_opacity(config.inactive_opacity)
        GObject.source_remove(self.opacity_timer)
        self.opacity_timer = None

    def _cb_configure_event(self, widget, user_data):
        self.canvas_rect = Rect(0, 0,
                                self.get_allocated_width(),
                                self.get_allocated_height())
        self.update_layout()

    def _cb_mouse_enter(self, widget, event):
        self.release_active_key() # release move key
        if self.is_opacify_enabled():
            self.stop_opacity_timer()

    def _cb_mouse_leave(self, widget, event):
        """
        horrible.  Grabs pointer when key is pressed, released when cursor
        leaves keyboard
        """
        Gdk.pointer_ungrab(event.time)
        if self.active_key:
            if self.active_scan_key:
                self.active_key = None
                self.active_scan_key = None
                self.queue_draw()
            else:
                self.release_key(self.active_key)

        # another terrible hack
        # start a high frequency timer to detect clicks outside of onboard
        self.start_click_polling()

        if self.is_opacify_enabled():
            self.start_opacity_timer()
        return True

    def _cb_mouse_button_press(self,widget,event):
        Gdk.pointer_grab(self.get_window(),
                         False,
                         Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK |
                         Gdk.EventMask.POINTER_MOTION_MASK,
                         None, None, event.time)

        self.stop_click_polling()

        if event.type == Gdk.EventType.BUTTON_PRESS:
            if config.enable_scanning:
                if self.scanning_time_id:
                    if not self.scanning_y == None:
                        self.press_key(self.active_scan_key)
                        self.release_key(self.active_scan_key)
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
                elif not self.get_kbd_window().has_decoration():
                    self.start_move_window()
        return True

    def _cb_mouse_button_release(self,widget,event):
        Gdk.pointer_ungrab(event.time)
        self.release_active_key()

        if self.move_start_position:
            self.stop_move_window()

    def release_active_key(self):
        if self.active_key:
            self.release_key(self.active_key)
            self.active_key = None
        return True

    #Between scans and when value of scanning changes.
    def reset_scan(self, scanning=None):
        if self.active_scan_key:
            self.active_scan_key.beingScanned = False
        if self.scanning_time_id:
            GObject.source_remove(self.scanning_time_id)
            self.scanning_time_id = None

        self.scanning_x = None
        self.scanning_y = None
        self.queue_draw()

    def _cb_motion(self, widget, event):
        if event.state & (Gdk.ModifierType.BUTTON1_MASK |
                          Gdk.ModifierType.BUTTON2_MASK |
                          Gdk.ModifierType.BUTTON3_MASK):

            # move button pressed?
            if self.move_start_position:
                rootwin = Gdk.get_default_root_window()
                window = self.get_kbd_window()
                dunno, x, y, mods = rootwin.get_pointer()
                wx, wy = (self.move_start_position[0] + x,
                          self.move_start_position[1] + y)
                window.move(wx, wy)
            pass

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

    def start_move_window(self):
        rootwin = Gdk.get_default_root_window()
        window = self.get_kbd_window()
        dunno, x, y, mask = rootwin.get_pointer()

        # begin_move_drag fails for window type hint "DOCK"
        # window.begin_move_drag(1, x, y, Gdk.CURRENT_TIME)

        wx, wy = window.get_position()
        self.move_start_position = (wx-x, wy-y)

    def stop_move_window(self):
        self.move_start_position = None

    def is_dragging(self):
        return bool(self.move_start_position)

    def draw(self, widget, context):
        #_logger.debug("Draw: clip_extents=" + str(context.clip_extents()))

        clip_rect = Rect.from_extents(*context.clip_extents())
        get_layer_fill_rgba = self.color_scheme.get_layer_fill_rgba

        # paint background
        win = self.get_kbd_window()
        if win.get_transparent():
            context.save()
            context.set_source_rgba(1.0, 1.0, 1.0, 0.0)
            context.set_operator(cairo.OPERATOR_SOURCE)
            context.paint()
            context.restore()
        else:
            context.set_source_rgba(*get_layer_fill_rgba(0))
            context.paint()

        layer_ids = self.layout.get_layer_ids()
        for item in self.layout.iter_visible_items():
            if item.layer_id:

                # draw layer background
                layer_index = layer_ids.index(item.layer_id)
                parent = item.parent
                if parent and \
                   layer_index != 0:
                    rect = parent.get_canvas_rect()
                    context.rectangle(*rect.inflate(1))
                    context.set_source_rgba(*get_layer_fill_rgba(layer_index))
                    context.fill()

            if item.is_key() and \
               clip_rect.intersects(item.get_canvas_rect()):
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
        self.get_kbd_window().emit("quit-onboard")

    def get_kbd_window(self):
        return self.get_parent()

