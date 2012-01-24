# -*- coding: utf-8 -*-
""" GTK specific keyboard class """

from __future__ import division, print_function, unicode_literals

import os
import time
from math import pi, sqrt, sin, cos, log, pow

import cairo
from gi.repository import GObject, Gdk, Gtk

from Onboard.Keyboard import Keyboard, EventType
from Onboard.utils    import Rect, Handle, WindowManipulator, \
                             Timer, timeit, FadeTimer, \
                             round_corners, roundrect_arc, roundrect_curve
from Onboard.KeyGtk import Key

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

# enum of opacity transitions
class Transition:
    class SHOW: pass
    class HIDE: pass
    class AUTO_SHOW: pass
    class AUTO_HIDE: pass
    class ACTIVATE: pass
    class DEACTIVATE: pass


class TouchHandle(object):
    """ Enlarged drag handle for resizing or moving """

    id = None
    prelight = False
    pressed = False
    corner_radius = 0     # radius of the outer corners (window edges)

    _size = (40, 40)
    _rect = None
    _scale = 1.0   # scale of handle relative to resize handles
    _shadow_size = 4
    _shadow_offset = (0.0, 3.0)

    _handle_angles = {}  # dictionary at class scope!
    _edge_handles =   [Handle.EAST,
                       Handle.SOUTH,
                       Handle.WEST,
                       Handle.NORTH]
    _corner_handles = [Handle.SOUTH_EAST,
                       Handle.SOUTH_WEST,
                       Handle.NORTH_WEST,
                       Handle.NORTH_EAST]

    def __init__(self, id):
        self.id = id

        # initialize angles
        if not self._handle_angles:
            for i, h in enumerate(self._edge_handles):
                self._handle_angles[h] = i * pi / 2.0
            for i, h in enumerate(self._corner_handles):
                self._handle_angles[h] = i * pi / 2.0 + pi /  4.0
            self._handle_angles[Handle.MOVE] = 0.0

    def get_rect(self):
        rect = self._rect
        if not rect is None and \
           self.pressed:
            rect = rect.offset(1.0, 1.0)
        return rect

    def get_radius(self):
        w, h = self.get_rect().get_size()
        return min(w, h) / 2.0

    def get_shadow_rect(self):
        rect = self.get_rect().inflate(self._shadow_size+1)
        rect.w += self._shadow_offset[0]
        rect.h += self._shadow_offset[1]
        return rect

    def get_arrow_angle(self):
        return self._handle_angles[self.id]

    def is_edge_handle(self):
        return self.id in self._edge_handles

    def is_corner_handle(self):
        return self.id in self._corner_handles

    def update_position(self, canvas_rect):
        w, h = self._size
        w = min(w, canvas_rect.w / 3.0)
        w = min(w, canvas_rect.h / 3.0)
        h = w
        self._scale = 1.0

        xc, yc = canvas_rect.get_center()
        if self.id is Handle.MOVE:  # move handle?
            d = min(canvas_rect.w - 2.0 * w, canvas_rect.h - 2.0 * h)
            self._scale = 1.4
            w = min(w * self._scale, d)
            h = min(h * self._scale, d)

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

        self._rect = Rect(x, y, w, h)

    def hit_test(self, point):
        rect = self.get_rect()
        if rect and rect.is_point_within(point):
            _win = self._window.get_window()
            if _win:
                context = _win.cairo_create()
                self.build_handle_path(context)
                return context.in_fill(*point)
        return False

        radius = self.get_radius()
        xc, yc = rect.get_center()
        dx = xc - point[0]
        dy = yc - point[1]
        d = sqrt(dx*dx + dy*dy)
        return d <= radius

    def draw(self, context):
        if self.pressed:
            alpha_factor = 1.5
        else:
            alpha_factor = 1.0

        context.new_path()

        self.draw_handle_shadow(context, alpha_factor)
        self.draw_handle(context, alpha_factor)
        self.draw_arrows(context)

    def draw_handle(self, context, alpha_factor):
        radius = self.get_radius()
        line_width = radius / 15.0

        alpha = 0.4  * alpha_factor
        if self.pressed:
            context.set_source_rgba(0.78, 0.33, 0.17, alpha)
        elif self.prelight:
            context.set_source_rgba(0.98, 0.53, 0.37, alpha)
        else:
            context.set_source_rgba(0.78, 0.33, 0.17, alpha)

        self.build_handle_path(context)
        context.fill_preserve()
        context.set_line_width(line_width)
        context.stroke()

    def draw_handle_shadow(self, context, alpha_factor):
        rect = self.get_rect()
        radius = self.get_radius()
        xc, yc = rect.get_center()
        alpha = 0.15 * alpha_factor

        context.save()

        # There is a massive performance boost for groups when clipping is used.
        # Integer limits are again dramatically faster (x4) then using floats.
        # for 1000x draw_drop_shadow:
        #     with clipping: ~300ms, without: ~11000ms
        context.rectangle(*self.get_shadow_rect().int())
        context.clip()

        context.push_group()

        # draw the shadow
        context.push_group_with_content(cairo.CONTENT_ALPHA)
        self.build_handle_path(context)
        context.set_source_rgba(0.0, 0.0, alpha)
        context.fill()
        group = context.pop_group()
        self.draw_drop_shadow(context, group,
                              (xc, yc), radius,
                              self._shadow_size,
                              self._shadow_offset)

        # cut out the handle area, because the handle is transparent
        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.set_source_rgba(0.0, 0.0, 0.0, 1.0)
        self.build_handle_path(context)
        context.fill()
        context.restore()

        context.pop_group_to_source()
        context.paint()

        context.restore()

    def draw_drop_shadow(self, cr, pattern, origin, radius, shadow_size, offset):
        n = shadow_size
        for i in range(n):
            #k = i
            #k = -log(max(i, 0.1)) / log(10) * n / 2.0 + n / 2.0
            k = (1.0-sin(i*pi/2.0/n)) * n
            _scale = (radius + k) / radius
            cr.save()
            cr.translate(*origin)
            cr.scale(_scale, _scale)
            cr.translate(-origin[0], -origin[1])
            cr.translate(*offset)
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.04)
            cr.mask(pattern)
            cr.restore()

    def draw_arrows(self, context):
        radius = self.get_radius()
        xc, yc = self.get_rect().get_center()
        scale = radius / 2.0 / self._scale * 1.2
        num_arrows = 4 if self.id == Handle.MOVE else 2
        angle = self.get_arrow_angle()
        angle_step = 2.0 * pi / num_arrows

        context.save()

        for i in range(num_arrows):
            m = cairo.Matrix()
            m.translate(xc, yc)
            m.rotate(angle + i * angle_step)
            m.scale(scale, scale)

            # arrow distance from center
            if self.id is Handle.MOVE:
                m.translate(0.9, 0)
            else:
                m.translate(0.30, 0)

            context.set_matrix(m)
            self.draw_arrow(context)

        context.restore()

    def draw_arrow(self, context):
        context.move_to( 0.0, -0.5)
        context.line_to( 0.5,  0.0)
        context.line_to( 0.0,  0.5)
        context.close_path()

        context.set_source_rgba(1.0, 1.0, 1.0, 0.8)
        context.fill_preserve()

        context.set_source_rgba(0.0, 0.0, 0.0, 0.8)
        context.set_line_width(0)
        context.stroke()

    def build_handle_path(self, context):
        rect = self.get_rect()
        xc, yc = rect.get_center()
        radius = self.get_radius()
        corner_radius = self.corner_radius

        angle = self.get_arrow_angle()
        m = cairo.Matrix()
        m.translate(xc, yc)
        m.rotate(angle)

        if self.is_edge_handle():
            p0 = m.transform_point(radius, -radius)
            p1 = m.transform_point(radius, radius)
            context.arc(xc, yc, radius, angle + pi / 2.0, angle + pi / 2.0 + pi)
            context.line_to(*p0)
            context.line_to(*p1)
            context.close_path()
        elif self.is_corner_handle():
            m.rotate(-pi / 4.0)  # rotate to SOUTH_EAST

            context.arc(xc, yc, radius, angle + 3 * pi / 4.0,
                                        angle + 5 * pi / 4.0)
            pt = m.transform_point(radius, -radius)
            context.line_to(*pt)

            if corner_radius:
                # outer corner, following the rounded window corner
                pt  = m.transform_point(radius,  radius - corner_radius)
                ptc = m.transform_point(radius - corner_radius,
                                        radius - corner_radius)
                context.line_to(*pt)
                context.arc(ptc[0], ptc[1], corner_radius,
                            angle - pi / 4.0,  angle + pi / 4.0)
            else:
                pt = m.transform_point(radius,  radius)
                context.line_to(*pt)

            pt = m.transform_point(-radius,  radius)
            context.line_to(*pt)
            context.close_path()
        else:
            context.arc(xc, yc, radius, 0, 2.0 * pi)

    def redraw(self, window):
        self._window = window
        rect = self.get_shadow_rect()
        if rect:
            window.queue_draw_area(*rect)


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

    def draw(self, context):
        context.push_group()

        for handle in self.handles:
            handle.draw(context)

        context.pop_group_to_source()
        context.paint_with_alpha(self.opacity);

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
                    window.queue_draw_area(*handle.get_rect())

    def set_pressed(self, handle_id, window = None):
        for handle in self.handles:
            pressed = handle.id == handle_id
            if handle.pressed != pressed:
                handle.pressed = pressed
                handle.redraw(window)

    def set_corner_radius(self, corner_radius):
        for handle in self.handles:
            handle.corner_radius = corner_radius

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
        self._keyboard.begin_transition(Transition.DEACTIVATE)
        return False


class AtspiAutoShow(object):
    """
    Auto-show and hide Onboard based on at-spi focus events.
    """

    _atspi_listeners_registered = False
    _focused_accessible = None
    _lock_visible = False
    _keyboard = None

    def __init__(self, keyboard):
        self._keyboard = keyboard
        self._auto_show_timer = Timer()

    def cleanup(self):
        self._register_atspi_listeners(False)

    def enable(self, enable):
        self._register_atspi_listeners(enable)

    def lock_visible(self, lock):
        self._lock_visible = lock

    def set_visible(self, visible):
        """ Begin AUTO_SHOW or AUTO_HIDE transition """
        # Don't react to each and every focus message. Delay the start 
        # of the transition slightly so that only the last of a bunch of
        # focus messages is acted on.
        self._auto_show_timer.start(0.1, self._begin_transition, visible)

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
        if config.auto_show.auto_show_enabled:
            accessible = event.source
            
            self._log_accessible(accessible)

            if accessible:
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

                # reposition the keyboard window
                if show and self._focused_accessible:
                    acc = self._focused_accessible
                    ext = acc.get_extents(Atspi.CoordType.SCREEN)
                    rect = Rect(ext.x, ext.y, ext.width, ext.height)
                    if not rect.is_empty() and \
                       not self._lock_visible:
                        self.on_reposition(rect)

                # show/hide the wiundow
                if not show is None and \
                   not self._lock_visible:
                    self.set_visible(show)

    def _begin_transition(self, show):
        if show:
            self._keyboard.begin_transition(Transition.AUTO_SHOW)
        else:
            self._keyboard.begin_transition(Transition.AUTO_HIDE)
        return False

    def on_reposition(self, rect):
        window = self._keyboard.get_kbd_window()
        if window:
            mode = "nooverlap"
            x = y = None
            home = window.home_rect

            if mode == "closest":
                x, y = rect.left(), rect.bottom()
            if mode == "vertical":
                x, y = rect.left(), rect.bottom()
                _x, y = window.get_position()
            if mode == "nooverlap":
                x, y = self.find_non_occluding_position(rect, home)

            if not x is None:
                x, y = self._keyboard.limit_position(x, y, self._keyboard.canvas_rect)

                # remember our rects to distinguish from user move/resize
                window.known_window_rects = [Rect(x, y, home.w, home.h)]
                window.move(x, y)


    def find_non_occluding_position(self, acc_rect, home):

        # Leave some margin around the accessible to account for
        # window frames and position errors of firefox entries.
        rect = acc_rect.inflate(0, config.auto_show.unoccluded_margin)

        if home.intersects(rect):
            cx, cy = rect.get_center()
            hcx, hcy = home.get_center()
            dir = hcy > cy  # true = up
            for i in range(2):
                x = home.left()
                if dir:
                    # move up
                    y = rect.top() - home.h
                else:
                    # move down
                    y = rect.bottom()
                x, y = self._keyboard.limit_position(x, y,
                                                     self._keyboard.canvas_rect)

                r = Rect(x, y, home.w, home.h)
                if not rect.intersects(r):
                    return x, y

                dir = not dir

        return home.top_left()

    def _is_accessible_editable(self, accessible):
        """ Is this an accessible onboard should be shown for? """
        role = accessible.get_role()
        state = accessible.get_state_set()

        if role in [Atspi.Role.TEXT,
                    Atspi.Role.TERMINAL,
                    Atspi.Role.DATE_EDITOR,
                    Atspi.Role.PASSWORD_TEXT,
                    Atspi.Role.EDITBAR,
                    Atspi.Role.ENTRY,
                    Atspi.Role.DOCUMENT_TEXT,
                    Atspi.Role.DOCUMENT_FRAME,
                    Atspi.Role.DOCUMENT_EMAIL,
                    Atspi.Role.SPIN_BUTTON,
                   ]:
            if role in [Atspi.Role.TERMINAL] or \
               state.contains(Atspi.StateType.EDITABLE):
                return True
        return False

    def _log_accessible(self, accessible):
        if _logger.isEnabledFor(logging.DEBUG):
            msg = "At-spi focus event: "
            if not accessible:
                msg += "accessible=".format(accessible)
            else:
                state_set = accessible.get_state_set()
                editable = state_set.contains(Atspi.StateType.EDITABLE) \
                           if state_set else None
                ext = accessible.get_extents(Atspi.CoordType.SCREEN)
                extents   = Rect(ext.x, ext.y, ext.width, ext.height)

                msg += "name={name}, role={role}({role_name}), " \
                       "editable={editable}, states={states}, " \
                       "extents={extents}]" \
                        .format(name=accessible.get_name(),
                                role = accessible.get_role(),
                                role_name = accessible.get_role_name(),
                                editable = editable,
                                states = state_set.states,
                                # ValueError: invalid enum value: 47244640264
                                #state_set = state_set.get_states() \
                                #            if state_set else None,
                                extents = extents \
                               )
            _logger.debug(msg)

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
        delay = config.keyboard.sticky_key_release_delay
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

    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        WindowManipulator.__init__(self)

        self.active_key = None

        self._active_event_type = None
        self._last_click_time = 0
        self._last_click_key = None

        self._outside_click_detected = False
        self._outside_click_timer = None
        self._long_press_timer = Timer()
        self._auto_release_timer = AutoReleaseTimer(self)

        self.dwell_timer = None
        self.dwell_key = None
        self.last_dwelled_key = None

        self.window_fade = FadeTimer()
        self.inactivity_timer = InactivityTimer(self)
        self.auto_show = AtspiAutoShow(self)

        self.touch_handles = TouchHandles()
        self.touch_handles_hide_timer = Timer()
        self.touch_handles_fade = FadeTimer()

        self._aspect_ratio = None
        self._first_draw = True

        # self.set_double_buffered(False)
        self.set_app_paintable(True)

        # no tooltips when embedding, gnome-screen-saver flickers (Oneiric)
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

    def initial_update(self):
        pass

    def _on_parent_set(self, widget, old_parent):
        win = self.get_kbd_window()
        if win:
            self.update_transparency()

    def cleanup(self):
        # stop timer callbacks for unused, but not yet destructed keyboards
        self.touch_handles_fade.stop()
        self.touch_handles_hide_timer.stop()
        self.window_fade.stop()
        self.inactivity_timer.stop()
        self._long_press_timer.stop()
        self._auto_release_timer.stop()
        self.auto_show.cleanup()
        self.stop_click_polling()
        self.inactivity_timer.stop()

    def update_auto_show(self, startup = False):
        """
        Turn on/off auto-show and show/hide the window accordingly.
        """
        enable = config.is_auto_show_enabled()
        self.auto_show.enable(enable)

        # Show the keyboard when turning off auto-show.
        # Hide the keyboard when turning on auto-show.
        #   (Fix this when we know how to get the active accessible)
        # Hide the keyboard on start when start-minimized is set
        #
        # start_minimized            False True  False True
        # auto_show                  False False True  True
        # --------------------------------------------------
        # window visible on start    True  False False False
        # window visible later       True  True  False False
        if startup:
            visible = config.is_visible_on_start()
            self.get_kbd_window().set_visible(visible)
        else:
            visible = not enable
        self.auto_show.set_visible(visible)

    def start_click_polling(self):
        self.stop_click_polling()
        self._outside_click_timer = GObject.timeout_add(2, self._on_click_timer)
        self._outside_click_detected = False

    def stop_click_polling(self):
        if self._outside_click_timer:
            GObject.source_remove(self._outside_click_timer)
            self._outside_click_timer = None

    def _on_click_timer(self):
        """ poll for mouse click outside of onboards window """
        rootwin = Gdk.get_default_root_window()
        dunno, x, y, mask = rootwin.get_pointer()
        if mask & (Gdk.ModifierType.BUTTON1_MASK |
                   Gdk.ModifierType.BUTTON2_MASK |
                   Gdk.ModifierType.BUTTON3_MASK):
            self._outside_click_detected = True
        elif self._outside_click_detected:
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
            self.begin_transition(Transition.DEACTIVATE)

    def get_transition_target_opacity(self, transition):
        transparency = 0

        if transition in [Transition.ACTIVATE]:
            transparency = config.transparency

        elif transition in [Transition.SHOW,
                            Transition.AUTO_SHOW]:
            if not self.inactivity_timer.is_enabled() or \
               self.inactivity_timer.is_active():
                transparency = config.transparency
            else:
                transparency = config.inactive_transparency

        elif transition in [Transition.HIDE,
                            Transition.AUTO_HIDE]:
            transparency = 100

        elif transition == Transition.DEACTIVATE:
            transparency = config.inactive_transparency

        return 1.0 - transparency / 100.0

    def begin_transition(self, transition):
        """ Start the transition to a different opacity """
        window = self.get_kbd_window()
        if window:
            duration = 0.3
            if transition in [Transition.SHOW,
                              Transition.HIDE,
                              Transition.AUTO_SHOW,
                              Transition.ACTIVATE]:
                duration = 0.15

            if transition in [Transition.SHOW,
                              Transition.AUTO_SHOW]:
                window.set_visible(True)

            opacity = self.get_transition_target_opacity(transition)
            _logger.debug(_("setting keyboard opacity to {}") \
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
                                  Transition.AUTO_HIDE]:
                    window.set_visible(False)

    def toggle_visible(self):
        """ main method to show/hide onboard manually"""
        window = self.get_kbd_window()
        visible = not window.is_visible() if window else False
        self.set_visible(visible)

        # If the user unhides onboard, don't auto-hide it until
        # he manually hides it again
        if config.is_auto_show_enabled():
            self.auto_show.lock_visible(visible)

    def set_visible(self, visible):
        """ main method to show/hide onboard manually"""
        window = self.get_kbd_window()
        if window:
            if visible:
                self.begin_transition(Transition.SHOW)
            else:
                self.begin_transition(Transition.HIDE)

    def get_drag_window(self):
        """ Overload for WindowManipulator """
        return self.get_kbd_window()

    def get_drag_threshold(self):
        """ Overload for WindowManipulator """
        return config.get_drag_threshold()

    def on_drag_initiated(self):
        """ Overload for WindowManipulator """
        window = self.get_drag_window()
        if window:
            window.on_user_positioning_begin()

    def on_drag_done(self):
        """ Overload for WindowManipulator """
        window = self.get_drag_window()
        if window:
            window.on_user_positioning_done()

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
        self.update_font_sizes()
        self.touch_handles.update_positions(self.canvas_rect)

    def _on_mouse_enter(self, widget, event):
        self.release_active_key() # release move key

        # stop inactivity timer
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(True)

        # Force into view for WindowManipulator's system drag mode.
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
                self.release_active_key()

        # another terrible hack
        # start a high frequency timer to detect clicks outside of onboard
        self.start_click_polling()

        # start inactivity timer
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(False)

        self.stop_dwelling()
        self.reset_touch_handles()

        return True

    def _on_motion(self, widget, event):
        cursor_type = None
        point = (event.x, event.y)
        hit_key = None

        # hit-test touch handles first
        hit_handle = None
        if self.touch_handles.active:
            hit_handle = self.touch_handles.hit_test(point)
            self.touch_handles.set_prelight(hit_handle, self)

        # hit-test keys
        if hit_handle is None:
            hit_key = self.get_key_at_location(point)

        if event.state & (Gdk.ModifierType.BUTTON1_MASK |
                          Gdk.ModifierType.BUTTON2_MASK |
                          Gdk.ModifierType.BUTTON3_MASK):

            # move/resize
            if event.state & Gdk.ModifierType.BUTTON1_MASK:
                self.handle_motion(event, fallback = True)

            # stop long press when drag threshold has been overcome
            if self.is_drag_active():
                self.stop_long_press()

        else:
            if not hit_handle is None:
                # handle hovered over -> extend its visible time
                self.start_touch_handles_auto_show()

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

            allow_drag_cursors = not config.has_window_decoration() and \
                                 not hit_key
            self.set_drag_cursor_at(point, allow_drag_cursors)

    def _on_mouse_button_press(self, widget, event):
        Gdk.pointer_grab(self.get_window(),
                         False,
                         Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK |
                         Gdk.EventMask.POINTER_MOTION_MASK,
                         None, None, event.time)

        self.stop_click_polling()
        self.stop_dwelling()

        key = None
        point = (event.x, event.y)

        if event.type == Gdk.EventType.BUTTON_PRESS:
            # hit-test touch handles first
            hit_handle = None
            if self.touch_handles.active:
                hit_handle = self.touch_handles.hit_test(point)
                self.touch_handles.set_pressed(hit_handle, self)
                if not hit_handle is None:
                    # handle clicked -> stop auto-show until button release
                    self.stop_touch_handles_auto_show()
                else:
                    # no handle clicked -> hide them now
                    self.show_touch_handles(False)

            # hit-test keys
            if hit_handle is None:
                key = self.get_key_at_location(point)

            # enable/disable the drag threshold
            if not hit_handle is None:
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

            # start/stop scanning
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
                # press the key
                self.active_key = key
                if key:
                    double_click_time = Gtk.Settings.get_default() \
                            .get_property("gtk-double-click-time")

                    # single click?
                    if self._last_click_key != key or \
                       event.time - self._last_click_time > double_click_time:
                        self.press_key(key, event.button)

                        # start long press detection
                        controller = self.button_controllers.get(key)
                        if controller and controller.can_long_press():
                            self._long_press_timer.start(1.0, self._on_long_press,
                                                        key, event.button)
                    # double click?
                    else:
                        self.press_key(key, event.button, EventType.DOUBLE_CLICK)

                    self._last_click_key = key
                    self._last_click_time = event.time

        return True

    def _on_long_press(self, key, button):
        controller = self.button_controllers.get(key)
        controller.long_press(button)

    def stop_long_press(self):
        self._long_press_timer.stop()

    def _on_mouse_button_release(self, widget, event):
        Gdk.pointer_ungrab(event.time)
        self.release_active_key()
        self.stop_drag()
        self._long_press_timer.stop()

        # reset cursor when there was no cursor motion
        point = (event.x, event.y)
        hit_key = self.get_key_at_location(point)
        self.do_set_cursor_at(point, hit_key)

        # reset touch handles
        self.reset_touch_handles()
        self.start_touch_handles_auto_show()

    def press_key(self, key, button = 1, event_type = EventType.CLICK):
        Keyboard.press_key(self, key, button, event_type)
        self._auto_release_timer.start()
        self._active_event_type = event_type

    def release_key(self, key, button = 1, event_type = None):
        if event_type is None:
            event_type = self._active_event_type
        Keyboard.release_key(self, key, button, event_type)
        self._active_event_type = None

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

                self.press_key(key, 0, EventType.DWELL)
                self.release_key(key, 0, EventType.DWELL)

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

        clip_rect = Rect.from_extents(*context.clip_extents())

        # draw background
        decorated = self.draw_background(context)

        # On first run quickly overwrite the background only.
        # This gives a slightly smoother startup with desktop remnants
        # flashing though for a shorter time.
        if self._first_draw:
            self._first_draw = False
            self.queue_draw()
            return

        if not self.layout:
            return

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

        # draw touch handles (enlarged move and resize handles)
        if self.touch_handles.active:
            corner_radius = config.CORNER_RADIUS if decorated else 0
            self.touch_handles.set_corner_radius(corner_radius)
            self.touch_handles.draw(context)

    def show_touch_handles(self, show):
        """ 
        Show/hide the enlarged resize/move handels.
        Initiates an opacity fade.
        """
        if show and config.lockdown.disable_touch_handles:
            return

        if show:
            self.touch_handles.set_prelight(None, self)
            self.touch_handles.set_pressed(None, self)
            self.touch_handles.active = True
            start, end = 0.0, 1.0
        else:
            self.stop_touch_handles_auto_show()
            start, end = 1.0, 0.0

        if self.touch_handles_fade.target_value != end:
            self.touch_handles_fade.fade_to(start, end, 0.2,
                                      self.on_touch_handles_opacity)

    def reset_touch_handles(self):
        if self.touch_handles.active:
            self.touch_handles.set_prelight(None, self)
            self.touch_handles.set_pressed(None, self)

    def start_touch_handles_auto_show(self):
        """ (re-) starts the timer to hide touch handles """
        if self.touch_handles.active:
            self.touch_handles_hide_timer.start(3.5,
                                                self.show_touch_handles, False)

    def stop_touch_handles_auto_show(self):
        """ stops the timer to hide touch handles """
        self.touch_handles_hide_timer.stop()

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

        decorated = False

        if config.xid_mode:
            # xembed mode
            # Disable transparency in lightdm and g-s-s for now.
            # There are too many issues and there is no real
            # visual improvement.
            if False and \
               win.supports_alpha:
                self.clear_background(context)
                decorated = True
                self.draw_transparent_background(context, decorated)
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
                    decorated = True
                    self.draw_transparent_background(context, decorated)
            else:
                self.draw_plain_background(context)

        return decorated

    def clear_background(self, context):
        """
        Clear the whole gtk background.
        Makes the whole strut transparent in xembed mode.
        """
        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.paint()
        context.restore()

    def get_layer_fill_rgba(self, layer_index):
        if self.color_scheme:
            return self.color_scheme.get_layer_fill_rgba(layer_index)
        else:
            return [0.5, 0.5, 0.5, 1.0]

    def get_background_rgba(self):
        """ layer 0 color * background_transparency """
        layer0_rgba = self.get_layer_fill_rgba(0)
        background_alpha = 1.0 - config.background_transparency / 100.0
        background_alpha *= layer0_rgba[3]
        return layer0_rgba[:3] + [background_alpha]

        background_alpha = 1.0 - config.background_transparency / 100.0

    def draw_transparent_background(self, context, decorated = True):
        """ fill with the transparent background color """
        rgba = self.get_background_rgba()
        context.set_source_rgba(*rgba)

        # draw on the potentially aspect-corrected frame around the layout
        rect = self.layout.get_canvas_border_rect()
        rect = rect.inflate(config.get_frame_width())
        corner_radius = config.CORNER_RADIUS

        if decorated:
            roundrect_arc(context, rect, corner_radius)
        else:
            context.rectangle(*rect)
        context.fill()

        if decorated:
            # inner decoration line
            line_rect = rect.deflate(1)
            roundrect_arc(context, line_rect, corner_radius)
            context.stroke()

        self.draw_dish_key_background(context, rgba[3])

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
            context.push_group()

            context.set_source_rgba(0, 0, 0, 1)
            enlargement = self.layout.context.scale_log_to_canvas((0.8, 0.8))
            corner_radius = self.layout.context.scale_log_to_canvas_x(2.4)

            if layer_id is None:
                generator = self.layout.iter_visible_items()
            else:
                generator = self.layout.iter_layer_items(layer_id)

            for item in generator:
                if item.is_key():
                    rect = item.get_canvas_border_rect()
                    rect = rect.inflate(*enlargement)
                    roundrect_curve(context, rect, corner_radius)
                    context.fill()

            context.pop_group_to_source()
            context.paint_with_alpha(alpha);

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
        for keys in list(self.layout.get_key_groups().values()):

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

    def refresh_pango_layouts(self):
        """
        When the systems font dpi setting changes our pango layout object,
        it still caches the old setting, leading to wrong font scaling.
        Refresh the pango layout object.
        """
        _logger.info(_("Refreshing pango layout, new font dpi setting is '{}'") \
                .format(Gtk.Settings.get_default().get_property("gtk-xft-dpi")))

        Key.reset_pango_layout()
