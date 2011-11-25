""" GTK specific keyboard class """

import os
import time
from math import sin, pi, sqrt

import cairo
from gi.repository import GObject, Gdk, Gtk

from Onboard.Keyboard import Keyboard
from Onboard.utils    import Rect, Handle, WindowManipulator, Timer, \
                             round_corners, roundrect_arc, roundrect_curve

from gettext import gettext as _

### Logging ###
import logging
_logger = logging.getLogger("KeyboardGTK")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, auto-hide won't be available"))

# enum of transition targets
class Transition:
    class SHOW: pass
    class HIDE: pass
    class AUTOSHOW: pass
    class AUTOHIDE: pass
    class ACTIVATE: pass
    class INACTIVATE: pass


class TouchHandle(object):
    """ Enlarged drag handle for resizing or moving """
    id = None
    size = (40, 40)
    rect = None
    scale = 1.0   # scale of handle relative to resize handles
    shadow_size = 4.5
    shadow_offset = (0.0, 3.0)

    prelight = False
    pressed = False

    def __init__(self, id):
        self.id = id

    def get_shadow_rect(self):
        rect = self.rect.inflate(self.shadow_size)
        rect.w += self.shadow_offset[0]
        rect.h += self.shadow_offset[1]
        return rect

    def draw(self, context):
        xc, yc = self.rect.get_center()
        if self.pressed:
            xc += 1.0
            yc += 1.0

        w, h = self.rect.get_size()
        radius = w / 2.0
        if self.pressed:
            alpha_factor = 1.5
        else:
            alpha_factor = 1.0

        context.new_path()

        # shadow
        context.push_group()

        r0 =  radius * 0.0
        r  =  radius + self.shadow_size
        x, y = xc + self.shadow_offset[0], yc + self.shadow_offset[1]
        alpha = 0.15 * alpha_factor
        g = radius / r
        pat = cairo.RadialGradient(x, y, r0, x, y, r)
        pat.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, alpha)
        pat.add_color_stop_rgba(g, 0.0, 0.0, 0.0, alpha)
        pat.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
        context.set_source (pat)
        context.arc(x, y, r, 0, 2.0 * pi)
        context.fill()

        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        context.arc(xc, yc, radius, 0, 2.0 * pi)
        context.fill()
        context.restore()

        context.pop_group_to_source()
        context.paint();

        # handle area
        alpha = 0.3  * alpha_factor
        if self.pressed:
            context.set_source_rgba(0.78, 0.33, 0.17, alpha)
        elif self.prelight:
            context.set_source_rgba(0.98, 0.53, 0.37, alpha)
        else:
            context.set_source_rgba(0.78, 0.33, 0.17, alpha)

        context.arc(xc, yc, radius, 0, 2.0 * pi)
        context.fill_preserve()
        context.set_line_width(radius / 15.0)
        context.stroke()

        # arrows
        angle = 0.0
        if self.id in [Handle.WEST,
                           Handle.EAST]:
            angle = pi / 2.0
        if self.id in [Handle.NORTH,
                           Handle.SOUTH]:
            angle = 0.0
        if self.id in [Handle.NORTH_WEST,
                           Handle.SOUTH_EAST]:
            angle = -pi / 4.0
        if self.id in [Handle.NORTH_EAST,
                           Handle.SOUTH_WEST]:
            angle = pi / 4.0

        scale = radius / 2.0 / self.scale
        num_arrows = 4 if self.id == Handle.MOVE else 2
        angle_step = 2.0 * pi / num_arrows

        context.save()

        for i in xrange(num_arrows):
            m = cairo.Matrix()
            m.translate(xc, yc)
            m.rotate(angle + i * angle_step)
            m.scale(scale, scale)

            # arrow distance from center
            if self.id is Handle.MOVE:
                m.translate(0, 0.9)
            else:
                m.translate(0, 0.35)

            context.set_matrix(m)
            self.draw_arrow(context)

        context.restore()

    def draw_arrow(self, context):
        context.move_to( 0.0, 0.5)
        context.line_to( 0.5, 0.0)
        context.line_to(-0.5, 0.0)
        context.close_path()

        context.set_source_rgba(1.0, 1.0, 1.0, 0.8)
        context.fill_preserve()

        context.set_source_rgba(0.0, 0.0, 0.0, 0.8)
        context.set_line_width(0)
        context.stroke()

    def update_position(self, canvas_rect):
        w, h = self.size
        w = min(w, canvas_rect.w / 3.0)
        w = min(w, canvas_rect.h / 3.0)
        h = w
        self.scale = 1.0

        xc, yc = canvas_rect.get_center()
        if self.id is Handle.MOVE:  # move handle?
            d = min(canvas_rect.w - 2.0 * w, canvas_rect.h - 2.0 * h)
            self.scale = 1.3
            w = min(w * self.scale, d)
            h = min(h * self.scale, d)

        if self.id in [Handle.WEST,
                           Handle.NORTH_WEST,
                           Handle.SOUTH_WEST]:
            x = canvas_rect.left()
        if self.id in [Handle.NORTH,
                           Handle.NORTH_WEST,
                           Handle.NORTH_EAST]:
            y = canvas_rect.top()
        if self.id in [Handle.EAST,
                           Handle.NORTH_EAST,
                           Handle.SOUTH_EAST]:
            x = canvas_rect.right() - w
        if self.id in [Handle.SOUTH,
                           Handle.SOUTH_WEST,
                           Handle.SOUTH_EAST]:
            y = canvas_rect.bottom() - h

        if self.id in [Handle.MOVE, Handle.EAST, Handle.WEST]:
            y = yc - h / 2.0
        if self.id in [Handle.MOVE, Handle.NORTH, Handle.SOUTH]:
            x = xc - w / 2.0

        self.rect = Rect(x, y, w, h)

    def hit_test(self, point):
        if not self.rect:
            return False

        xc, yc = self.rect.get_center()
        radius = self.rect.w / 2.0
        dx = xc - point[0]
        dy = yc - point[1]
        d = sqrt(dx*dx + dy*dy)
        return d <= radius

    def redraw(self, window):
        if self.rect:
            window.queue_draw_area(*self.get_shadow_rect())

class TouchHandles(object):
    """ Full set of resize and move handles """
    active = False
    opacity = 1.0
    rect = None

    def __init__(self):
        handles = []
        handles.append(TouchHandle(Handle.MOVE))
        handles.append(TouchHandle(Handle.NORTH_WEST))
        handles.append(TouchHandle(Handle.NORTH))
        handles.append(TouchHandle(Handle.NORTH_EAST))
        handles.append(TouchHandle(Handle.EAST))
        handles.append(TouchHandle(Handle.SOUTH_EAST))
        handles.append(TouchHandle(Handle.SOUTH))
        handles.append(TouchHandle(Handle.SOUTH_WEST))
        handles.append(TouchHandle(Handle.WEST))
        self.handles = handles

    def update_positions(self, canvas_rect):
        self.rect = canvas_rect
        for handle in self.handles:
            handle.update_position(canvas_rect)

    def draw(self, context, background_rgba):
        context.push_group()

        for handle in self.handles:
            handle.draw(context)

        context.pop_group_to_source()
        context.paint_with_alpha (self.opacity);

    def redraw(self, window):
        if self.rect:
            for handle in self.handles:
                handle.redraw(window)

    def hit_test(self, point):
        if self.active:
            for handle in self.handles:
                if handle.hit_test(point):
                    return handle.id

    def set_prelight(self, handle_id, window = None):
        for handle in self.handles:
            prelight = handle.id == handle_id and not handle.pressed
            if handle.prelight != prelight:
                handle.prelight = prelight
                if window:
                    window.queue_draw_area(*handle.rect)

    def set_pressed(self, handle_id, window = None):
        for handle in self.handles:
            pressed = handle.id == handle_id
            if handle.pressed != pressed:
                handle.pressed = pressed
                if window:
                    window.queue_draw_area(*handle.rect)


class FadeTimer(Timer):
    """ Fades between two values """

    start_value = None
    target_value = None

    def fade_to(self, start_value, target_value, duration,
                callback = None, *callback_args):
        """
        Start value fade.
        duration: fade time in seconds, 0 for immediate value change
        """
        self.start_value = start_value
        self.target_value = target_value
        self._start_time = time.time()
        self._duration = duration
        self._callback = callback
        self._callback_args = callback_args

        self.start(0.05)

    def on_timer(self):
        elapsed = time.time() - self._start_time
        if self._duration:
            lin_progress = min(1.0, elapsed / self._duration)
        else:
            lin_progress = 1.0
        sin_progress = (sin(lin_progress * pi - pi / 2.0) + 1.0) / 2.0
        self.value = sin_progress * (self.target_value - self.start_value) + \
                  self.start_value

        done = lin_progress >= 1.0
        if self._callback:
            self._callback(self.value, done, *self._callback_args)

        return not done


class InactivityTimer(Timer):
    """
    Waits for the inactivity delay and transitions between
    active and inactive state.
    Inactivity here means, the pointer has left the keyboard window
    """
    _keyboard = None
    _active = False

    def __init__(self, keyboard):
        self._keyboard = keyboard

    def is_enabled(self):
        window = self._keyboard.get_kbd_window()
        if not window:
            return False
        screen = window.get_screen()
        return screen and  screen.is_composited() and \
               config.enable_inactive_transparency and \
               not config.xid_mode

    def is_active(self):
        return self._active

    def begin_transition(self, active):
        self._active = active
        if active:
            Timer.stop(self)
            self._keyboard.begin_transition(Transition.ACTIVATE)
        else:
            if not config.xid_mode:
                Timer.start(self, config.inactive_transparency_delay)

    def on_timer(self):
        self._keyboard.begin_transition(Transition.INACTIVATE)
        return False


class AutoHideTimer(Timer):
    """
    Delays hiding and showing the window a little, in the hope
    that all at-spi focus messages have arrived until then.
    """
    _keyboard = None
    _visible = True

    def __init__(self, keyboard):
        self._keyboard = keyboard

    def set_visible(self, visible):
        self._visible = visible
        self.start(0.1)

    def on_timer(self):
        if self._visible:
            self._keyboard.begin_transition(Transition.AUTOSHOW)
        else:
            self._keyboard.begin_transition(Transition.AUTOHIDE)
        return False


class AtspiAutoHide(object):
    """
    Auto-hide and show Onboard based on at-spi focus events.
    """

    _atspi_listeners_registered = False
    _focused_accessible = None
    _lock_visible = False

    def __init__(self, transition_target):
        self.autohide_timer = AutoHideTimer(transition_target)
        self.update()

    def cleanup(self):
        self._register_atspi_listeners(False)

    def is_enabled(self):
        return not config.xid_mode and \
               config.auto_hide

    def lock_visible(self, lock):
        self._lock_visible = lock

    def update(self):
        enable = self.is_enabled()
        self._register_atspi_listeners(enable)
        self.autohide_timer.set_visible(not enable)

    def _register_atspi_listeners(self, register = True):
        if not "Atspi" in globals():
            return

        if register:
            if not self._atspi_listeners_registered:
                Atspi.EventListener.register_no_data(self._on_atspi_global_focus,
                                                     "focus")
                Atspi.EventListener.register_no_data(self._on_atspi_object_focus,
                                                     "object:state-changed:focused")
                self._atspi_listeners_registered = True

        else:
            if self._atspi_listeners_registered:
                Atspi.EventListener.deregister_no_data(self._on_atspi_global_focus,
                                                     "focus")
                Atspi.EventListener.deregister_no_data(self._on_atspi_object_focus,
                                                     "object:state-changed:focused")
                self._atspi_listeners_registered = False

    def _on_atspi_global_focus(self, event):
        self._on_atspi_focus(event, True)

    def _on_atspi_object_focus(self, event):
        self._on_atspi_focus(event)

    def _on_atspi_focus(self, event, focus_received = False):
        if config.auto_hide:
            accessible = event.source
            #print accessible.get_name(), accessible.get_state_set().states, accessible.get_role(), accessible.get_role_name(), event.detail1

            focused = focus_received or event.detail1   # received focus?
            editable = self._is_accessible_editable(accessible)
            visible =  focused and editable

            show = visible
            if focused:
                self._focused_accessible = accessible
            elif not focused and self._focused_accessible == accessible:
                self._focused_accessible = None
            else:
                show = None
            if not show is None and \
               not self._lock_visible:
                self.autohide_timer.set_visible(show)

    def _is_accessible_editable(self, accessible):
        role = accessible.get_role()
        state = accessible.get_state_set()

        if role in [Atspi.Role.TEXT,
                    Atspi.Role.TERMINAL,
                    Atspi.Role.DATE_EDITOR,
                    Atspi.Role.PASSWORD_TEXT,
                    Atspi.Role.EDITBAR,
                    Atspi.Role.ENTRY,
                    Atspi.Role.DOCUMENT_TEXT,
                    Atspi.Role.DOCUMENT_EMAIL,
                    Atspi.Role.SPIN_BUTTON,
                   ]:
            if role in [Atspi.Role.TERMINAL] or \
               state.contains(Atspi.StateType.EDITABLE):
                return True
        return False


class AutoReleaseTimer(Timer):
    """
    Releases latched and locked modifiers after a period of inactivity.
    Inactivity here means no keys are pressed.
    """
    _keyboard = None

    def __init__(self, keyboard):
        self._keyboard = keyboard

    def start(self):
        self.stop()
        delay = config.lockdown.release_modifiers_delay
        if delay:
            Timer.start(self, delay)

    def on_timer(self):
        self._keyboard.release_latched_sticky_keys()
        self._keyboard.release_locked_sticky_keys()
        self._keyboard.active_layer_index = 0
        self._keyboard.update_ui()
        self._keyboard.redraw()
        return False


class KeyboardGTK(Gtk.DrawingArea, WindowManipulator):

    scanning_time_id = None

    DWELL_ACTIVATED = -1

    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        WindowManipulator.__init__(self)

        self.active_key = None
        self.click_detected = False
        self.click_timer = None
        self.dwell_timer = None
        self.dwell_key = None
        self.last_dwelled_key = None

        self.window_fade = FadeTimer()
        self.touch_handles_fade = FadeTimer()
        self.touch_handles = TouchHandles()
        self.inactivity_timer = InactivityTimer(self)
        self.auto_hide = AtspiAutoHide(self)
        self.auto_release = AutoReleaseTimer(self)

        self._aspect_ratio = None

        # self.set_double_buffered(False)
        self.set_app_paintable(True)

        # no tool-tips when embedding, gnome-screen-saver flickers (Oneiric)
        if not config.xid_mode:
            self.set_has_tooltip(True) # works only at window creation -> always on

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.ENTER_NOTIFY_MASK
                        )

        self.connect("parent-set",           self._on_parent_set)
        self.connect("draw",                 self._on_draw)
        self.connect("button-press-event",   self._on_mouse_button_press)
        self.connect("button_release_event", self._on_mouse_button_release)
        self.connect("motion-notify-event",  self._on_motion)
        self.connect("query-tooltip",        self._on_query_tooltip)
        self.connect("enter-notify-event",   self._on_mouse_enter)
        self.connect("leave-notify-event",   self._on_mouse_leave)
        self.connect("configure-event",      self._on_configure_event)

    def _on_parent_set(self, widget, old_parent):
        win = self.get_kbd_window()
        if win:
            self.update_transparency()

    def cleanup(self):
        # stop timer callbacks for unused, but not yet destructed keyboards
        self.touch_handles_fade.stop()
        self.window_fade.stop()
        self.inactivity_timer.stop()
        self.auto_release.stop()
        self.auto_hide.cleanup()
        self.stop_click_polling()

    def update_auto_hide(self):
        self.auto_hide.update()

    def start_click_polling(self):
        self.stop_click_polling()
        return
        self.click_timer = GObject.timeout_add(2, self._on_click_timer)
        self.click_detected = False

    def stop_click_polling(self):
        if self.click_timer:
            GObject.source_remove(self.click_timer)
            self.click_timer = None

    def _on_click_timer(self):
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

    def update_transparency(self):
        self.begin_transition(Transition.ACTIVATE)
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(False)

    def update_inactive_transparency(self):
        if self.inactivity_timer.is_enabled():
            self.begin_transition(Transition.INACTIVATE)

    def get_transition_target_opacity(self, transition):
        transparency = 0

        if transition in [Transition.ACTIVATE]:
            transparency = config.transparency

        elif transition in [Transition.SHOW,
                            Transition.AUTOSHOW]:
            if not self.inactivity_timer.is_enabled() or \
               self.inactivity_timer.is_active():
                transparency = config.transparency
            else:
                transparency = config.inactive_transparency

        elif transition in [Transition.HIDE,
                            Transition.AUTOHIDE]:
            transparency = 100

        elif transition == Transition.INACTIVATE:
            transparency = config.inactive_transparency

        return 1.0 - transparency / 100.0

    def begin_transition(self, transition):
        """ Start the transition to a different opacity """
        window = self.get_kbd_window()
        if window:
            duration = 0.4
            if transition in [Transition.SHOW,
                              Transition.HIDE,
                              Transition.AUTOSHOW,
                              Transition.ACTIVATE]:
                duration = 0.15

            if transition in [Transition.SHOW,
                              Transition.AUTOSHOW]:
                window.set_visible(True)

            opacity = self.get_transition_target_opacity(transition)
            _logger.debug(_("setting keyboard opacity to {}%") \
                                .format(opacity))

            # no fade delay for non-composited screens (unity-2d)
            screen = window.get_screen()
            if screen and not screen.is_composited():
                duration = 0
                opacity = 1.0

            start_opacity = window.get_opacity()
            self.window_fade.fade_to(start_opacity, opacity, duration,
                                      self.on_window_opacity, transition)

    def on_window_opacity(self, opacity, done, transition):
        window = self.get_kbd_window()
        if window:
            window.set_opacity(opacity)
            if done:
                if transition in [Transition.HIDE,
                                  Transition.AUTOHIDE]:
                    window.set_visible(False)

    def toggle_visible(self):
        """ main method to show/hide onboard manually"""
        window = self.get_kbd_window()
        if window:
            show = not window.is_visible()
            if show:
                self.begin_transition(Transition.SHOW)
            else:
                self.begin_transition(Transition.HIDE)

            # If ther user unhides onboard, don't hide it until
            # he manually hides it again
            if self.auto_hide.is_enabled():
                self.auto_hide.lock_visible(show)

    def get_drag_window(self):
        """ Overload for WindowManipulator """
        return self.get_kbd_window()

    def get_always_visible_rect(self):
        """
        Returns the bounding rectangle of all move buttons
        in canvas coordinates.
        Overload for WindowManipulator
        """
        keys = self.find_keys_from_ids(["move"])
        bounds = None
        for key in keys:
            r = key.get_canvas_border_rect()
            if not bounds:
                bounds = r
            else:
                bounds = bounds.union(r)

        return bounds

    def _on_configure_event(self, widget, user_data):
        self.update_layout()

    def _on_mouse_enter(self, widget, event):
        self.release_active_key() # release move key

        # stop inactivity timer
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(True)

        # Force into view for system drag mode.
        #if not config.xid_mode and \
        #   not config.window_decoration and \
        #   not config.force_to_top:
        #    GObject.idle_add(self.force_into_view)

    def _on_mouse_leave(self, widget, event):
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

        # start inactivity timer
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(False)

        self.stop_dwelling()

        return True

    def _on_motion(self, widget, event):
        cursor_type = None
        point = (event.x, event.y)
        hit_key = None

        # hit test touch handles first, then the keys
        hit = None
        if self.touch_handles.active:
            hit = self.touch_handles.hit_test(point)
            self.touch_handles.set_prelight(hit, self)
        if hit is None:
            hit_key = self.get_key_at_location(point)

        if event.state & (Gdk.ModifierType.BUTTON1_MASK |
                          Gdk.ModifierType.BUTTON2_MASK |
                          Gdk.ModifierType.BUTTON3_MASK):

            # move/resize
            if event.state & Gdk.ModifierType.BUTTON1_MASK:
                self.handle_motion(event, fallback = True)

        else:
            # start dwelling if we have entered a dwell-enabled key
            if hit_key and \
               hit_key.sensitive and \
               not self.is_dwelling() and \
               not self.already_dwelled(hit_key):

                controller = self.button_controllers.get(hit_key)
                if controller and controller.can_dwell():
                    self.start_dwelling(hit_key)

        # cancel dwelling when the hit key changes
        if self.dwell_key and self.dwell_key != hit_key or \
           self.last_dwelled_key and self.last_dwelled_key != hit_key:
            self.cancel_dwelling()

        self.do_set_cursor_at(point, hit_key)

    def do_set_cursor_at(self, point, hit_key = None):
        """ Set/reset the cursor for frame resize handles """
        if not config.xid_mode:

            if hit_key is None:
                hit_key = self.get_key_at_location(point)

            allow_drag_cursors = not config.has_window_decoration() and \
                                 not hit_key
            self.set_drag_cursor_at(point, allow_drag_cursors)

    def _on_mouse_button_press(self,widget,event):
        Gdk.pointer_grab(self.get_window(),
                         False,
                         Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK |
                         Gdk.EventMask.POINTER_MOTION_MASK,
                         None, None, event.time)

        self.stop_click_polling()
        self.stop_dwelling()

        if event.type == Gdk.EventType.BUTTON_PRESS:  # why?

            key = None
            point = (event.x, event.y)

            # hit-test handles, then keys
            hit_handle = None
            if self.touch_handles.active:
                hit_handle = self.touch_handles.hit_handle_test(point)
                self.touch_handles.set_pressed(hit_handle, self)
            if hit_handle is None:
                key = self.get_key_at_location(point)

            # enable/disable the drag threshold
            if hit_handle:
                self.enable_drag_protection(False)
            elif key and key.id == "move":
                # Move key needs to support long press;
                # always use the drag threshold.
                self.enable_drag_protection(True)
                self.reset_drag_protection()
            else:
                self.enable_drag_protection(config.drag_protection)

            # handle resizing
            if not key and \
               not config.has_window_decoration() and \
               not config.xid_mode:
                if self.handle_press(event):
                    return True

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
                    self.press_key(key, event.button)

        return True

    def _on_mouse_button_release(self, widget, event):
        Gdk.pointer_ungrab(event.time)
        self.release_active_key()
        self.stop_drag()

        point = (event.x, event.y)
        self.do_set_cursor_at(point)  # reset cursor when there was no cursor motion

        if self.touch_handles.active:
            self.touch_handles.set_prelight(None, self)
            self.touch_handles.set_pressed(None, self)

    def press_key(self, key, button = 1):
        Keyboard.press_key(self, key, button)
        self.auto_release.start()

    def is_dwelling(self):
        return not self.dwell_key is None

    def already_dwelled(self, key):
        return self.last_dwelled_key is key

    def start_dwelling(self, key):
        self.cancel_dwelling()
        self.dwell_key = key
        self.last_dwelled_key = key
        key.start_dwelling()
        self.dwell_timer = GObject.timeout_add(50, self._on_dwell_timer)

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

    def _on_dwell_timer(self):
        if self.dwell_key:
            self.redraw(self.dwell_key)

            if self.dwell_key.is_done():
                key = self.dwell_key
                self.stop_dwelling()

                self.press_key(key, self.DWELL_ACTIVATED)
                self.release_key(key, self.DWELL_ACTIVATED)

                return False
        return True

    def release_active_key(self):
        if self.active_key:
            self.release_key(self.active_key)
            self.active_key = None
        return True

    def reset_scan(self, scanning=None):
        """ Between scans and when value of scanning changes. """
        if self.active_scan_key:
            self.active_scan_key.scanned = False
        if self.scanning_time_id:
            GObject.source_remove(self.scanning_time_id)
            self.scanning_time_id = None

        self.scanning_x = None
        self.scanning_y = None
        self.queue_draw()

    def _on_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if config.show_tooltips:
            key = self.get_key_at_location((x, y))
            if key:
                if key.tooltip:
                    r = Gdk.Rectangle()
                    r.x, r.y, r.width, r.height = key.get_canvas_rect().to_list()
                    tooltip.set_tip_area(r)   # no effect in oneiric?
                    tooltip.set_text(_(key.tooltip))
                    return True
        return False

    def _on_draw(self, widget, context): 
        #_logger.debug("Draw: clip_extents=" + str(context.clip_extents()))
        #self.get_window().set_debug_updates(True)

        if not Gtk.cairo_should_draw_window(context, self.get_window()):
            return

        from utils import timeit
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

                    if self.color_scheme:
                        rgba = self.color_scheme.get_layer_fill_rgba(layer_index)
                    else:
                        rgba = [0.5, 0.5, 0.5, 0.9]
                    context.set_source_rgba(*rgba)

                    context.fill()

                    self.draw_dish_key_background(context, 1.0, item.layer_id)

            # draw key
            if item.is_key() and \
               clip_rect.intersects(item.get_canvas_rect()):
                item.draw(context)
                item.draw_image(context)
                item.draw_label(context)

        # draw move and resize handles
        if self.touch_handles.active:
            rect = self.layout.get_canvas_border_rect()
            rgba = self.get_layer_fill_rgba(0)[:3] + [0.5]
            self.touch_handles.update_positions(rect)
            self.touch_handles.draw(context, rgba)

    def show_touch_handles(self, show):
        if show:
            self.touch_handles.active = True
            start, end = 0.0, 1.0
        else:
            start, end = 1.0, 0.0

        if self.touch_handles_fade.target_value != end:
            self.touch_handles_fade.fade_to(start, end, 0.2,
                                      self.on_touch_handles_opacity)

    def on_touch_handles_opacity(self, opacity, done):
        if done and opacity < 0.1:
            self.touch_handles.active = False

        # redraw the window
        self.touch_handles.opacity = opacity
        self.touch_handles.redraw(self)

    def hit_test_move_resize(self, point):
        hit = self.touch_handles.hit_test(point)
        if hit is None:
            hit = WindowManipulator.hit_test_move_resize(self, point)
        return hit

    def draw_background(self, context):
        """ Draw keyboard background """
        win = self.get_kbd_window()

        if config.xid_mode:
            # xembed mode
            # Disable transparency in lightdm and g-s-s for now.
            # There are too many issues and there is no real
            # visual improvement.
            if False and \
               win.supports_alpha:
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
        # Not necessary anymore when having a transparent
        # window background color (override_background_color()).
        # Keep this until more testing has been done.
        return

        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.paint()
        context.restore()

    def get_layer_fill_rgba(self, layer_index):
        if self.color_scheme:
            return self.color_scheme.get_layer_fill_rgba(layer_index)
        else:
            return [0.5, 0.5, 0.5, 1.0]

    def draw_transparent_background(self, context, decorated = True):
        """ fill with layer 0 color + background_transparency """
        layer0_rgba = self.get_layer_fill_rgba(0)
        background_alpha = 1.0 - config.background_transparency / 100.0
        rgba = layer0_rgba[:3] + [background_alpha]
        context.set_source_rgba(*rgba)

        # draw on the potentially aspect-corrected frame around the layout
        rect = self.layout.get_canvas_border_rect()
        rect = rect.inflate(config.get_frame_width())
        corner_radius = 10

        if decorated:
            roundrect_arc(context, rect, corner_radius)
        else:
            context.rectangle(*rect)
        context.fill()

        if decorated:
            # inner decoration line
            rect = rect.deflate(1)
            if decorated:
                roundrect_arc(context, rect, corner_radius)
            else:
                context.rectangle(*rect)
            context.stroke()

        self.draw_dish_key_background(context, background_alpha)

    def draw_plain_background(self, context, layer_index = 0):
        """ fill with plain layer 0 color; no alpha support required """
        rgba = self.get_layer_fill_rgba(layer_index)
        context.set_source_rgba(*rgba)
        context.paint()

        self.draw_dish_key_background(context)

    def draw_dish_key_background(self, context, alpha = 1.0, layer_id = None):
        """
        Black background, following the contours of neighboring keys,
        to simulate the opening in the keyboard plane.
        """
        if config.theme_settings.key_style == "dish":
            context.set_source_rgba(0, 0, 0, alpha)
            v = self.layout.context.scale_log_to_canvas((0.5, 0.5))

            if layer_id is None:
                generator = self.layout.iter_visible_items()
            else:
                generator = self.layout.iter_layer_items(layer_id)

            for item in generator:
                if item.is_key():
                    rect = item.get_canvas_border_rect()
                    rect = rect.inflate(*v)
                    roundrect_curve(context, rect, 10)
                    context.fill()

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

    def get_click_type_button_rects(self):
        """
        Returns bounding rectangles of all click type buttons
        in root window coordinates.
        """
        keys = self.find_keys_from_ids(["singleclick",
                                        "secondaryclick",
                                        "middleclick",
                                        "doubleclick",
                                        "dragclick"])
        rects = []
        for key in keys:
            r = key.get_canvas_border_rect()
            x0, y0 = self.get_window().get_root_coords(r.x, r.y)
            x1, y1 = self.get_window().get_root_coords(r.x + r.w,
                                                       r.y + r.h)
            rects.append((x0, y0, x1 - x0, y1 -y0))

        return rects

    def on_layout_updated(self):
        # experimental support for keeping window aspect ratio
        # Currently, in Oneiric, neither lightdm, nor gnome-screen-saver
        # appear to honor these hints.

        aspect_ratio = None
        if config.keep_aspect_ratio:
            log_rect = self.layout.get_border_rect()
            aspect_ratio = log_rect.w / float(log_rect.h)
            aspect_ratio = self.layout.get_log_aspect_ratio()

        if self._aspect_ratio != aspect_ratio:
            window = self.get_kbd_window()
            if window:
                geom = Gdk.Geometry()
                if aspect_ratio is None:
                    window.set_geometry_hints(self, geom, 0)
                else:
                    geom.min_aspect = geom.max_aspect = aspect_ratio
                    window.set_geometry_hints(self, geom, Gdk.WindowHints.ASPECT)

                self._aspect_ratio = aspect_ratio

