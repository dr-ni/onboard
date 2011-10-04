""" GTK specific keyboard class """

import os
import time
from math import sin, pi

import cairo
from gi.repository import GObject, Gdk, Gtk

from Onboard.utils import Rect, round_corners, roundrect_arc

from gettext import gettext as _

### Logging ###
import logging
_logger = logging.getLogger("KeyboardGTK")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

# window corners for resizing without decoration
NORTH_WEST = Gdk.WindowEdge.NORTH_WEST
NORTH = Gdk.WindowEdge.NORTH
NORTH_EAST = Gdk.WindowEdge.NORTH_EAST
WEST = Gdk.WindowEdge.WEST
EAST = Gdk.WindowEdge.EAST
SOUTH_WEST = Gdk.WindowEdge.SOUTH_WEST
SOUTH = Gdk.WindowEdge.SOUTH
SOUTH_EAST   = Gdk.WindowEdge.SOUTH_EAST 

cursor_types = {
    NORTH_WEST : Gdk.CursorType.TOP_LEFT_CORNER,
    NORTH      : Gdk.CursorType.TOP_SIDE,
    NORTH_EAST : Gdk.CursorType.TOP_RIGHT_CORNER,
    WEST       : Gdk.CursorType.LEFT_SIDE,
    EAST       : Gdk.CursorType.RIGHT_SIDE,
    SOUTH_WEST : Gdk.CursorType.BOTTOM_LEFT_CORNER,
    SOUTH      : Gdk.CursorType.BOTTOM_SIDE,
    SOUTH_EAST : Gdk.CursorType.BOTTOM_RIGHT_CORNER}

class Timer(object):
    _timer = None

    def start(self, delay):
        self.stop()
        ms = int(delay * 1000)
        self._timer = GObject.timeout_add(ms, self._cb_timer)

    def stop(self):
        if not self._timer is None:
            GObject.source_remove(self._timer)
            self._timer = None

    def _cb_timer(self):
        if not self.on_timer():
            self.stop()
            return False
        return True

    def on_timer(self):
        return True


class OpacityFadeTimer(Timer):

    def __init__(self, widget):
        self._widget = widget

    def fade_to(self, target_opacity, duration):
        """
        Start opacity fade.
        duration: fade time in seconds
        """
        self._start_opacity = self._widget.get_opacity()
        self._target_opacity = target_opacity
        self._start_time = time.time()
        self._duration = duration
        self.start(0.05)

    def on_timer(self):
        elapsed = time.time() - self._start_time
        lin_progress = min(1.0, elapsed / self._duration)
        sin_progress = (sin(lin_progress * pi - pi / 2.0) + 1.0) / 2.0
        opacity = sin_progress * (self._target_opacity - self._start_opacity) + \
                  self._start_opacity
        self._widget.set_opacity(opacity)
        return lin_progress < 1.0


class Opacify(Timer):
    def __init__(self):
        self._widget = None

    def set_widget(self, widget):
        self._widget = widget
        self.opacity_fade = OpacityFadeTimer(widget)

    def is_enabled(self):
        if not self._widget:
            return False
        screen = self._widget.get_screen()
        return screen and  screen.is_composited() and \
               (config.opacity != 100 or \
                config.inactive_opacity != 100) and \
               not config.xid_mode

    def transition_to(self, active):
        if active:
            Timer.stop(self)
            self.apply_active_opacity()
        else:
            if not config.xid_mode:
                Timer.start(self, config.opacify_delay)

    def on_timer(self):
        self.apply_inactive_opacity()
        return False

    def apply_active_opacity(self):
        self._fade_to(config.opacity, True)

    def apply_inactive_opacity(self):
        self._fade_to(config.inactive_opacity, False)

    def _fade_to(self, opacity, fast = False):
        if self._widget:
            screen = self._widget.get_screen()
            if self._widget and screen and  screen.is_composited():
                _logger.debug(_("setting keyboard opacity to {}%") \
                                    .format(opacity))
                self.opacity_fade.fade_to(opacity / 100.0, 0.15 if fast else 0.4)


class KeyboardGTK(Gtk.DrawingArea):

    scanning_time_id = None

    DWELL_ACTIVATED = -1

    def __init__(self):
        Gtk.DrawingArea.__init__(self)

        self.active_key = None
        self.click_detected = False
        self.click_timer = None
        self.opacify = Opacify()
        self.dwell_timer = None
        self.dwell_key = None
        self.last_dwelled_key = None

        self.drag_start_position = None
        self.drag_start_rect = None
        self.drag_resize_edge = None

        # self.set_double_buffered(False)
        self.set_app_paintable(True)

        # not tool-tips when embedding, gnome-screen-saver flickers (Oneiric)
        if not config.xid_mode: 
            self.set_has_tooltip(True) # works only at window creation -> always on

        visual = Gdk.Screen.get_default().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.ENTER_NOTIFY_MASK)

        self.connect("parent-set",           self._cb_parent_set)
        self.connect("draw",                 self.draw)
        self.connect("button_press_event",   self._cb_mouse_button_press)
        self.connect("button_release_event", self._cb_mouse_button_release)
        self.connect("motion-notify-event",  self._cb_motion)
        self.connect("query-tooltip",        self._cb_query_tooltip)
        self.connect("enter-notify-event",   self._cb_mouse_enter)
        self.connect("leave-notify-event",   self._cb_mouse_leave)
        self.connect("configure-event",      self._cb_configure_event)

    def cleanup(self):
        self.stop_click_polling()

    def _cb_parent_set(self, widget, old_parent):
        win = self.get_kbd_window()
        if win:
            self.opacify.set_widget(win)
            if self.opacify.is_enabled():
                self.opacify.transition_to(False)

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

    def update_opacity(self):
        self.opacify.apply_active_opacity()
        self.opacify.transition_to(False)

    def update_inactive_opacity(self):
        self.opacify.apply_inactive_opacity()

    def _cb_configure_event(self, widget, user_data):
        self.canvas_rect = Rect(0, 0,
                                self.get_allocated_width(),
                                self.get_allocated_height())
        self.update_layout()

    def _cb_mouse_enter(self, widget, event):
        self.release_active_key() # release move key
        if self.opacify.is_enabled():
            self.opacify.transition_to(True)

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

        if self.opacify.is_enabled():
            self.opacify.transition_to(False)

        self.stop_dwelling()

        return True

    def _cb_mouse_button_press(self,widget,event):
        Gdk.pointer_grab(self.get_window(),
                         False,
                         Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK |
                         Gdk.EventMask.POINTER_MOTION_MASK,
                         None, None, event.time)

        self.stop_click_polling()

        key = self.get_key_at_location((event.x, event.y))
        if not key and \
           not config.has_window_decoration() and \
           not config.xid_mode:
            hit = self._hit_test_frame((event.x, event.y))
            if not hit is None:
                self.start_resize_window(hit)
                return True

        if event.type == Gdk.EventType.BUTTON_PRESS:
            if config.enable_scanning and \
               self.get_scan_columns() and \
               (not key or key.get_layer()):

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
                self.active_key = key
                if key:
                    self.stop_dwelling()
                    self.press_key(key, event.button)

        return True

    def _cb_mouse_button_release(self,widget,event):
        Gdk.pointer_ungrab(event.time)
        self.release_active_key()

        if self.is_dragging():
            self.stop_drag()

    def is_dwelling(self):
        return not self.dwell_key is None

    def already_dwelled(self, key):
        return self.last_dwelled_key is key

    def start_dwelling(self, key):
        self.cancel_dwelling()
        self.dwell_key = key
        self.last_dwelled_key = key
        key.start_dwelling()
        self.dwell_timer = GObject.timeout_add(50, self._cb_dwell_timer)

    def cancel_dwelling(self):
        self.stop_dwelling()
        self.last_dwelled_key = None

    def stop_dwelling(self):
        if self.dwell_timer:
            GObject.source_remove(self.dwell_timer)
            self.dwell_timer = None
            self.redraw(self.dwell_key)
            self.dwell_key.stop_dwelling()
            self.dwell_key = None

    def _cb_dwell_timer(self):
        if self.dwell_key:
            self.redraw(self.dwell_key)

            if self.dwell_key.is_done():
                key = self.dwell_key
                self.stop_dwelling()

                self.press_key(key, self.DWELL_ACTIVATED)
                self.release_key(key, self.DWELL_ACTIVATED)

                return False
        return True

    def _cb_motion(self, widget, event):
        cursor_type = None
        point = (event.x, event.y)

        hit_key = self.get_key_at_location(point)

        if event.state & (Gdk.ModifierType.BUTTON1_MASK |
                          Gdk.ModifierType.BUTTON2_MASK |
                          Gdk.ModifierType.BUTTON3_MASK):

            # drag operation in progress?
            if self.is_dragging():
                self._handle_drag()
        else:
            # start dwelling if we have entered a dwell-enabled key
            if hit_key and \
               not self.is_dwelling() and \
               not self.already_dwelled(hit_key):
                controller = self.button_controllers.get(hit_key)
                if controller and controller.can_dwell() and \
                   hit_key.sensitive:
                    self.start_dwelling(hit_key)

        # cancel dwelling when the hit key changes
        if self.dwell_key and self.dwell_key != hit_key or \
           self.last_dwelled_key and self.last_dwelled_key != hit_key:
            self.cancel_dwelling()

        # find cursor for frame resize handles
        if not config.xid_mode:   # not when embedding
            if not config.has_window_decoration() and \
               not hit_key:
                hit = self.drag_resize_edge
                if hit is None:
                   hit = self._hit_test_frame(point)
                if not hit is None:
                    cursor_type = cursor_types[hit]

        # set/reset cursor
        if not cursor_type is None:
            cursor = Gdk.Cursor(cursor_type)
            if cursor:
                self.get_window().set_cursor(cursor)
        else:
            self.get_window().set_cursor(None)

    def release_active_key(self):
        if self.active_key:
            self.release_key(self.active_key)
            self.active_key = None
        return True

    def reset_scan(self, scanning=None):
        """ Between scans and when value of scanning changes. """
        if self.active_scan_key:
            self.active_scan_key.beingScanned = False
        if self.scanning_time_id:
            GObject.source_remove(self.scanning_time_id)
            self.scanning_time_id = None

        self.scanning_x = None
        self.scanning_y = None
        self.queue_draw()

    def _cb_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if config.show_tooltips:
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
        # begin_move_drag fails for window type hint "DOCK"
        # window.begin_move_drag(1, x, y, Gdk.CURRENT_TIME)

        self.start_drag()

    def stop_move_window(self):
        self.stop_drag()

    def start_resize_window(self, edge):
        # begin_resize_drag fails for window type hint "DOCK"
        #self.get_kbd_window().begin_resize_drag (edge, 1, x, y, 0)

        self.start_drag()
        self.drag_resize_edge = edge

    def start_drag(self):
        rootwin = Gdk.get_default_root_window()
        window = self.get_kbd_window()
        dunno, x, y, mask = rootwin.get_pointer()
        wx, wy = window.get_position()
        self.drag_start_position = (wx-x, wy-y)
        self.drag_start_rect = Rect.from_position_size(window.get_position(),
                                                       window.get_size())

    def stop_drag(self):
        self.drag_start_position = None
        self.drag_resize_edge = None

    def is_dragging(self):
        return bool(self.drag_start_position)

    def _handle_drag(self):
        """ handle dragging for window move and resize """
        rootwin = Gdk.get_default_root_window()
        window = self.get_kbd_window()
        dunno, rx, ry, mods = rootwin.get_pointer()
        wx, wy = (self.drag_start_position[0] + rx,
                  self.drag_start_position[1] + ry)

        if self.drag_resize_edge is None:
            # move window
            window.move(wx, wy)
        else:
            # resize window
            wmin = hmin = 12  # minimum window size
            x0, y0, x1, y1 = self.drag_start_rect.to_extents()
            w, h = self.drag_start_rect.get_size()

            if self.drag_resize_edge in [NORTH, NORTH_WEST, NORTH_EAST]:
                y0 = min(wy, y1 - hmin)
            if self.drag_resize_edge in [WEST, NORTH_WEST, SOUTH_WEST]:
                x0 = min(wx, x1 - wmin)
            if self.drag_resize_edge in [EAST, NORTH_EAST, SOUTH_EAST]:
                x1 = max(wx + w, x0 + wmin)
            if self.drag_resize_edge in [SOUTH, SOUTH_WEST, SOUTH_EAST]:
                y1 = max(wy + h, y0 + wmin)

            w = window.get_window()
            w.move_resize(x0, y0, x1 -x0, y1 - y0)

    def _hit_test_frame(self, point):
        corner_size = 10
        edge_size = 5
        canvas_rect = self.canvas_rect

        w = min(canvas_rect.w / 2, corner_size)
        h = min(canvas_rect.h / 2, corner_size)

        # try corners first
        hit_rect = Rect(canvas_rect.x, canvas_rect.y, w, h)
        if hit_rect.point_inside(point):
            return NORTH_WEST

        hit_rect.x = canvas_rect.w - w
        if hit_rect.point_inside(point):
            return NORTH_EAST

        hit_rect.y = canvas_rect.h - h
        if hit_rect.point_inside(point):
            return SOUTH_EAST

        hit_rect.x = 0
        if hit_rect.point_inside(point):
            return SOUTH_WEST

        # then check the edges
        w = h = edge_size
        if point[0] < w:
            return WEST
        if point[0] > canvas_rect.w - w:
            return EAST
        if point[1] < h:
            return NORTH
        if point[1] > canvas_rect.h - h:
            return SOUTH

        return None


    def draw(self, widget, context):
        #_logger.debug("Draw: clip_extents=" + str(context.clip_extents()))

        clip_rect = Rect.from_extents(*context.clip_extents())

        # draw background
        self.draw_background(context)

        # run through all visible layout items
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
                    rgba = self.color_scheme.get_layer_fill_rgba(layer_index)
                    context.set_source_rgba(*rgba)
                    context.fill()

            # draw key
            if item.is_key() and \
               clip_rect.intersects(item.get_canvas_rect()):
                item.draw(context)
                item.draw_image(context)
                item.draw_font(context)

        return True

    def draw_background(self, context):
        """ Draw keyboard background """
        win = self.get_kbd_window()

        if config.xid_mode:
            # xembed mode
            if win.supports_alpha:
                self.clear_background(context)
                self.draw_transparent_background(context, decorated = True)
            else:
                self.draw_plain_background(context)

        elif config.has_window_decoration():
            # decorated window
            if win.supports_alpha and \
               config.transparent_background:
                self.clear_background(context)
            else:
                self.draw_plain_background(context)

        else:
            # undecorated window
            if win.supports_alpha:
                self.clear_background(context)
                if not config.transparent_background:
                    self.draw_transparent_background(context, decorated = True)
            else:
                self.draw_plain_background(context)

    def clear_background(self, context):
        """
        Clear the whole gtk background.
        Makes the whole strut transparent in xembed mode.
        """
        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.paint()
        context.restore()

    def draw_transparent_background(self, context, decorated = True):
        """ fill with layer 0 color + background_opacity """
        layer0_rgba = self.color_scheme.get_layer_fill_rgba(0)
        background_opacity = config.background_opacity / 100.0

        rgba = layer0_rgba[:3] + [background_opacity]
        context.set_source_rgba(*rgba)

        # draw on the potentially aspect-corrected frame around the layout
        rect = self.layout.get_canvas_border_rect()
        rect = rect.inflate(config.get_frame_width())
        corner_radius = 10

        if decorated:
            roundrect_arc(context, rect, corner_radius)
        else:
            context.rectangle(*rect)
        #context.fill_preserve()
        context.fill()

        if decorated:
            # outer decorated line
            #context.set_source_rgba(*layer0_rgba)
            #context.stroke()

            # inner decorated line
            rect = rect.deflate(1)
            if decorated:
                roundrect_arc(context, rect, corner_radius)
            else:
                context.rectangle(*rect)
            context.stroke()


    def draw_plain_background(self, context):
        """ fill with plain layer 0 color; no alpha support required """
        rgba = self.color_scheme.get_layer_fill_rgba(0)
        context.set_source_rgba(*rgba)
        context.paint()

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

