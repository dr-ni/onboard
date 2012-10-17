# -*- coding: utf-8 -*-
""" GTK specific keyboard class """

from __future__ import division, print_function, unicode_literals

import os
import time
from math import sin, pi

import cairo
from gi.repository import GObject, Gdk, Gtk, GLib

from Onboard.utils        import Rect, Timer, FadeTimer, \
                                 roundrect_arc, roundrect_curve, \
                                 gradient_line, brighten
from Onboard.WindowUtils  import WindowManipulator, Handle
from Onboard.Keyboard     import Keyboard, EventType
from Onboard.KeyGtk       import Key
from Onboard.TouchHandles import TouchHandles

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

# Gnome introspection calls are surprisingly expensive
# -> prepare stuff for faster access
BUTTON123_MASK = Gdk.ModifierType.BUTTON1_MASK | \
                 Gdk.ModifierType.BUTTON2_MASK | \
                 Gdk.ModifierType.BUTTON3_MASK

class AbortDrawing(Exception):
    pass


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
               config.is_inactive_transparency_enabled() and \
               config.window.enable_inactive_transparency and \
               not config.xid_mode

    def is_active(self):
        return self._active

    def begin_transition(self, active):
        self._active = active
        if active:
            Timer.stop(self)
            if self._keyboard.transition_active_to(True):
                self._keyboard.commit_transition()
        else:
            if not config.xid_mode:
                Timer.start(self, config.window.inactive_transparency_delay)

    def on_timer(self):
        self._keyboard.transition_active_to(False)
        self._keyboard.commit_transition()
        return False


class AtspiAutoShow(object):
    """
    Auto-show and hide Onboard based on at-spi focus events.
    """

    # Delay from the last focus event until the keyboard is shown/hidden.
    # Raise it to reduce unnecessary transitions (flickering).
    # Lower it for more immediate reactions.
    SHOW_REACTION_TIME = 0.0
    HIDE_REACTION_TIME = 0.3

    _atspi_listeners_registered = False
    _focused_accessible = None
    _lock_visible = False
    _frozen = False
    _keyboard = None

    def __init__(self, keyboard):
        self._keyboard = keyboard
        self._auto_show_timer = Timer()
        self._thaw_timer = Timer()

    def cleanup(self):
        self._register_atspi_listeners(False)
        self._auto_show_timer.stop()
        self._thaw_timer.stop()

    def enable(self, enable):
        self._register_atspi_listeners(enable)
        if enable:
            self._lock_visible = False
            self._frozen = False

    def is_frozen(self):
        return self._frozen

    def freeze(self, thaw_time = None):
        """
        Stop showing and hiding the keyboard window.
        thaw_time in seconds, None to freeze forever.
        """
        self._frozen = True
        self._thaw_timer.stop()
        if not thaw_time is None:
            self._thaw_timer.start(thaw_time, self._on_thaw)

        # Discard pending hide/show actions.
        self._auto_show_timer.stop()

    def thaw(self, thaw_time = None):
        """
        Allow hiding and showing the keyboard window again.
        thaw_time in seconds, None to thaw immediately.
        """
        self._thaw_timer.stop()
        if thaw_time is None:
            self._thaw()
        else:
            self._thaw_timer.start(thaw_time, self._on_thaw)

    def _on_thaw(self):
        self._thaw_timer.stop()
        self._frozen = False
        return False

    def lock_visible(self, lock, thaw_time = 1.0):
        """
        Lock window permanetly visible in response to the user showing it.
        Optionally freeze hiding/showing for a limited time.
        """
        # Permanently lock visible.
        self._lock_visible = lock

        # Temporarily stop showing/hiding.
        if thaw_time:
            self.freeze(thaw_time)

        # Leave the window in its current state,
        # discard pending hide/show actions.
        self._auto_show_timer.stop()

    def show_keyboard(self, show):
        """ Begin AUTO_SHOW or AUTO_HIDE transition """
        # Don't act on each and every focus message. Delay the start
        # of the transition slightly so that only the last of a bunch of
        # focus messages is acted on.
        delay = self.SHOW_REACTION_TIME if show else \
                self.HIDE_REACTION_TIME
        self._auto_show_timer.start(delay, self._begin_transition, show)

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
        if config.auto_show.enabled:
            accessible = event.source
            focused = bool(focus_received) or bool(event.detail1) # received focus?

            self._log_accessible(accessible, focused)

            if accessible:
                editable = self._is_accessible_editable(accessible)
                visible =  focused and editable

                show = visible
                if focused:
                    self._focused_accessible = accessible
                elif not focused and self._focused_accessible == accessible:
                    self._focused_accessible = None
                else:
                    show = None

                # show/hide the window
                if not show is None:
                    # Always allow to show the window even when locked.
                    # Mitigates right click on unity-2d launcher hiding
                    # onboard before _lock_visible is set (Precise).
                    if self._lock_visible:
                        show = True

                    if not self.is_frozen():
                        self.show_keyboard(show)

                # reposition the keyboard window
                if show and \
                   self._focused_accessible and \
                   not self._lock_visible and \
                   not self.is_frozen():
                    self.update_position()

    def _begin_transition(self, show):
        self._keyboard.transition_visible_to(show)
        self._keyboard.commit_transition()
        return False

    def update_position(self):
        window = self._keyboard.get_kbd_window()
        if window:
            rect = self.get_repositioned_window_rect(window.home_rect)

            if rect is None:
                # move back home
                rect = window.home_rect

            # remember rects to distimguish from user move/resize
            window.remember_rect(rect)

            if window.get_position() != rect.get_position():
                window.move(rect.x, rect.y)

    def get_repositioned_window_rect(self, home):
        """
        Get the alternative window rect suggested by auto-show or None if
        no repositioning is required.
        """
        accessible = self._focused_accessible
        if accessible:

            try:
                ext = accessible.get_extents(Atspi.CoordType.SCREEN)
            except: # private exception gi._glib.GError when
                    # right clicking onboards unity2d launcher (Precise)
                _logger.info("AtspiAutoHide: Invalid accessible,"
                             " failed to get extents")
                return None

            rect = Rect(ext.x, ext.y, ext.width, ext.height)

            if not rect.is_empty() and \
               not self._lock_visible:
                return self._get_window_rect_for_accessible_rect(home, rect)

        return None

    def _get_window_rect_for_accessible_rect(self, home, rect):
        """
        Find new window position based on the screen rect of the accessible.
        """
        mode = "nooverlap"
        x = y = None

        if mode == "closest":
            x, y = rect.left(), rect.bottom()
        if mode == "vertical":
            x, y = home.left(), rect.bottom()
            x, y = self._find_non_occluding_position(home, rect, True)
        if mode == "nooverlap":
            x, y = self._find_non_occluding_position(home, rect)

        if not x is None:
            return Rect(x, y, home.w, home.h)
        else:
            return None

    def _find_non_occluding_position(self, home, acc_rect,
                                     vertical = True, horizontal = True):

        # Leave some clearance around the accessible to account for
        # window frames and position errors of firefox entries.
        ra = acc_rect.apply_border(*config.auto_show.widget_clearance)
        rh = home.copy()

        # The home_rect doesn't include window decoration, 
        # make sure to add decoration for correct clearance.
        window = self._keyboard.get_kbd_window()
        if window:
            position = window.get_position() # careful, fails right after unhide
            origin = window.get_origin()
            rh.w += origin[0] - position[0]
            rh.h += origin[1] - position[1]

        if rh.intersects(ra):
            x, y = rh.get_position()

            # candidate positions
            vp = []
            if horizontal:
                vp.append([ra.left() - rh.w, y])
                vp.append([ra.right(), y])
            if vertical:
                vp.append([x, ra.top() - rh.h])
                vp.append([x, ra.bottom()])

            # limited, non-intersecting candidate rectangles
            vr = []
            for p in vp:
                pl = self._keyboard.limit_position( p[0], p[1],
                                                  self._keyboard.canvas_rect)
                r = Rect(pl[0], pl[1], rh.w, rh.h)
                if not r.intersects(ra):
                    vr.append(r)

            # candidate with smallest center-to-center distance wins
            chx, chy = rh.get_center()
            dmin = None
            rmin = None
            for r in vr:
                cx, cy = r.get_center()
                dx, dy = cx - chx, cy - chy
                d2 = dx * dx + dy * dy
                if dmin is None or dmin > d2:
                    dmin = d2
                    rmin = r

            if not rmin is None:
                return rmin.get_position()

        return None, None

    def _is_accessible_editable(self, accessible):
        """ Is this an accessible onboard should be shown for? """
        try:
            role = accessible.get_role()
            state = accessible.get_state_set()
        except: # private exception gi._glib.GError when gedit became unresponsive
            _logger.info("AtspiAutoHide: Invalid accessible,"
                         " failed to get role and state set")
            return False

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
                    Atspi.Role.COMBO_BOX,
                    Atspi.Role.DATE_EDITOR,
                    Atspi.Role.PARAGRAPH,      # LibreOffice Writer
                    Atspi.Role.HEADER,
                    Atspi.Role.FOOTER,
                   ]:
            if role in [Atspi.Role.TERMINAL] or \
               state.contains(Atspi.StateType.EDITABLE):
                return True
        return False

    def _log_accessible(self, accessible, focused):
        if _logger.isEnabledFor(logging.DEBUG):
            msg = "At-spi focus event: focused={}, ".format(focused)
            if not accessible:
                msg += "accessible={}".format(accessible)
            else:
                try:
                    role = accessible.get_role()
                except: # private exception gi._glib.GError when gedit became unresponsive
                    role = None

                try:
                    role_name = accessible.get_role_name()
                except: # private exception gi._glib.GError when gedit became unresponsive
                    role_name = None

                try:
                    state_set = accessible.get_state_set()
                    states = state_set.states
                    editable = state_set.contains(Atspi.StateType.EDITABLE) \
                               if state_set else None
                except: # private exception gi._glib.GError when gedit became unresponsive
                    states = None
                    editable = None

                try:
                    ext = accessible.get_extents(Atspi.CoordType.SCREEN)
                    extents   = Rect(ext.x, ext.y, ext.width, ext.height)
                except: # private exception gi._glib.GError when gedit became unresponsive
                    extents = None

                msg += "name={name}, role={role}({role_name}), " \
                       "editable={editable}, states={states}, " \
                       "extents={extents}]" \
                        .format(name=accessible.get_name(),
                                role = role,
                                role_name = role_name,
                                editable = editable,
                                states = states,
                                extents = extents \
                               )
            _logger.debug(msg)

class StateVariable:
    """ A variable taking part in opacity transitions """
    value        = 0.0
    start_value  = 0.0
    target_value = 0.0
    start_time   = 0.0
    duration     = 0.0
    done         = False

    def start_transition(self, target, duration):
        """ Begin transition """
        self.start_value = self.value
        self.target_value = target
        self.start_time = time.time()
        self.duration = duration
        self.done = False

    def update(self):
        """
        Update self.value based on the elapsed time since start_transition.
        """
        range = self.target_value - self.start_value
        if range and self.duration:
            duration = self.duration * abs(range)
            elapsed  = time.time() - self.start_time
            lin_progress = min(1.0, elapsed / duration)
        else:
            lin_progress = 1.0
        sin_progress = (sin(lin_progress * pi - pi / 2.0) + 1.0) / 2.0
        self.value = self.start_value + sin_progress * range
        self.done = lin_progress >= 1.0


class TransitionState:
    """ Set of all state variables involved in opacity transitions. """

    def __init__(self):
        self.visible = StateVariable()
        self.active  = StateVariable()
        self._vars = [self.visible, self.active]

    def update(self):
        for var in self._vars:
            var.update()

    def is_done(self):
        return all(var.done for var in self._vars)

    def get_max_duration(self):
        return max(x.duration for x in self._vars)

class KeyboardGTK(Gtk.DrawingArea, Keyboard, WindowManipulator):

    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        Keyboard.__init__(self)
        WindowManipulator.__init__(self)

        self.active_key = None

        self._active_event_type = None
        self._last_click_time = 0
        self._last_click_key = None

        self._outside_click_timer = Timer()
        self._outside_click_detected = False
        self._outside_click_start_time = None

        self._long_press_timer = Timer()
        self._auto_release_timer = AutoReleaseTimer(self)

        self.dwell_timer = None
        self.dwell_key = None
        self.last_dwelled_key = None

        self.inactivity_timer = InactivityTimer(self)
        self.auto_show = AtspiAutoShow(self)
        self.auto_show.enable(config.is_auto_show_enabled())

        self.touch_handles = TouchHandles()
        self.touch_handles_hide_timer = Timer()
        self.touch_handles_fade = FadeTimer()
        self.touch_handles_auto_hide = True

        self._aspect_ratio = None
        self._first_draw = True

        self._transition_timer = Timer()
        self._transition_state = TransitionState()
        self._transition_state.visible.value = 0.0
        self._transition_state.active.value = 1.0

        self.set_double_buffered(False)
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

        self.update_resize_handles()
        self._update_double_click_time()

        self.show()

    def initial_update(self):
        """ called when the layout has been loaded """
        Keyboard.initial_update(self)

    def _on_parent_set(self, widget, old_parent):
        win = self.get_kbd_window()
        if win:
            self.touch_handles.set_window(win)

    def cleanup(self):

        # Enter-notify isn't called when resizing without crossing into
        # the window again. Do it here on exit, at the latest, to make sure
        # the home_rect is updated before is is saved later.
        self.stop_system_drag()

        # stop timer callbacks for unused, but not yet destructed keyboards
        self.touch_handles_fade.stop()
        self.touch_handles_hide_timer.stop()
        self._transition_timer.stop()
        self.inactivity_timer.stop()
        self._long_press_timer.stop()
        self._auto_release_timer.stop()
        self.auto_show.cleanup()
        self.stop_click_polling()

        Keyboard.cleanup(self)

    def set_startup_visibility(self):
        win = self.get_kbd_window()
        assert(win)

        # Show the keyboard when turning off auto-show.
        # Hide the keyboard when turning on auto-show.
        #   (Fix this when we know how to get the active accessible)
        # Hide the keyboard on start when start-minimized is set.
        # Start with active transparency if the inactivity_timer is enabled.
        #
        # start_minimized            False True  False True
        # auto_show                  False False True  True
        # --------------------------------------------------
        # window visible on start    True  False False False

        visible = config.is_visible_on_start()

        # Start with low opacity to stop opacity flashing
        # when inactive transparency is enabled.
        screen = self.get_screen()
        if screen and screen.is_composited() and \
            self.inactivity_timer.is_enabled():
            win.set_opacity(0.05, True) # keep it slightly visible just in case

        # transition to initial opacity
        self.transition_visible_to(visible, 0.0)
        self.transition_active_to(True, 0.0)
        self.commit_transition()

        # kick off inactivity timer, i.e. inactivate on timeout
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(False)

        # Be sure to initially show/hide window and icon palette
        win.set_visible(visible)

    def update_resize_handles(self):
        """ Tell WindowManipulator about the active resize handles """
        self.set_drag_handles(config.window.resize_handles)

    def update_auto_show(self):
        """
        Turn on/off auto-show in response to user action (preferences)
        and show/hide the window accordingly.
        """
        enable = config.is_auto_show_enabled()
        self.auto_show.enable(enable)
        self.auto_show.show_keyboard(not enable)

    def update_transparency(self):
        """
        Updates transparencies in response to user action.
        Temporarily presents the window with active transparency when
        inactive transparency is enabled.
        """
        self.transition_active_to(True)
        self.commit_transition()
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(False)
        else:
            self.inactivity_timer.stop()
        self.redraw() # for background transparency

    def update_inactive_transparency(self):
        if self.inactivity_timer.is_enabled():
            self.transition_active_to(False)
            self.commit_transition()

    def _update_double_click_time(self):
        """ Scraping the bottom of the barrel to speed up key presses """
        self._double_click_time = Gtk.Settings.get_default() \
                        .get_property("gtk-double-click-time")

    def transition_visible_to(self, visible, duration = None):
        if duration is None:
            if visible:
                # No duration when showing. Don't fight with compiz in unity.
                duration = 0.0
            else:
                duration = 0.3
        return self._init_transition(self._transition_state.visible,
                                     visible, duration)

    def transition_active_to(self, active, duration = None):
        if duration is None:
            if active:
                duration = 0.15
            else:
                duration = 0.3
        return self._init_transition(self._transition_state.active,
                                     active, duration)

    def _init_transition(self, var, target_value, duration):

        # No fade delay for screens that can't fade (unity-2d)
        screen = self.get_screen()
        if screen and not screen.is_composited():
            duration = 0.0

        target_value = 1.0 if target_value else 0.0

        # Transition not yet in progress?
        if var.target_value != target_value:
            var.start_transition(target_value, duration)
            return True
        return False

    def commit_transition(self):
        duration = self._transition_state.get_max_duration()
        if duration == 0.0:
            self._on_transition_step()
        else:
            self._transition_timer.start(0.05, self._on_transition_step)

    def _on_transition_step(self):
        state = self._transition_state
        state.update()

        active_opacity    = config.window.get_active_opacity()
        inactive_opacity  = config.window.get_inactive_opacity()
        invisible_opacity = 0.0

        opacity  = inactive_opacity + state.active.value * \
                   (active_opacity - inactive_opacity)
        opacity *= state.visible.value
        window = self.get_kbd_window()
        if window:
            window.set_opacity(opacity)

            visible = state.visible.value > 0.0
            if window.is_visible() != visible:
                window.set_visible(visible)

                # _on_mouse_leave does not start the inactivity timer
                # while the pointer remains inside of the window. Do it
                # here when hiding the window.
                if not visible and \
                   self.inactivity_timer.is_enabled():
                    self.inactivity_timer.begin_transition(False)

        return not state.is_done()

    def toggle_visible(self):
        """ main method to show/hide onboard manually """
        self.set_visible(not self.is_visible())

    def is_visible(self):
        """ is the keyboard window currently visible? """
        window = self.get_kbd_window()
        return window.is_visible() if window else False

    def set_visible(self, visible):
        """ main method to show/hide onboard manually """
        self.lock_auto_show_visible(visible)  # pause auto show
        self.transition_visible_to(visible, 0.0)

        # briefly present the window
        if visible and self.inactivity_timer.is_enabled():
            self.transition_active_to(True, 0.0)
            self.inactivity_timer.begin_transition(False)

        self.commit_transition()

    def lock_auto_show_visible(self, visible):
        """
        If the user unhides onboard, don't auto-hide it until
        he manually hides it again.
        """
        if config.is_auto_show_enabled():
            self.auto_show.lock_visible(visible)

    def freeze_auto_show(self, thaw_time = None):
        """
        Stop both, hiding and showing.
        """
        if config.is_auto_show_enabled():
            self.auto_show.freeze(thaw_time)

    def thaw_auto_show(self, thaw_time = None):
        """
        Reenable both, hiding and showing.
        """
        if config.is_auto_show_enabled():
            self.auto_show.thaw(thaw_time)

    def start_click_polling(self):
        if self.has_latched_sticky_keys():
            self._outside_click_timer.start(0.01, self._on_click_timer)
            self._outside_click_detected = False
            self._outside_click_start_time = time.time()

    def stop_click_polling(self):
        self._outside_click_timer.stop()

    def _on_click_timer(self):
        """ poll for mouse click outside of onboards window """
        rootwin = Gdk.get_default_root_window()
        dunno, x, y, mask = rootwin.get_pointer()
        if mask & BUTTON123_MASK:
            self._outside_click_detected = True
        elif self._outside_click_detected:
            # button released anywhere outside of onboard's control
            self.stop_click_polling()
            self.on_outside_click()
            return False

        # stop after 30 seconds
        if time.time() - self._outside_click_start_time > 30.0:
            self.stop_click_polling()
            self.on_cancel_outside_click()
            return False

        return True

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

    def hit_test_move_resize(self, point):
        """ Overload for WindowManipulator """
        hit = self.touch_handles.hit_test(point)
        if hit is None:
            hit = WindowManipulator.hit_test_move_resize(self, point)
        return hit

    def _on_configure_event(self, widget, user_data):
        self.update_layout()
        self.update_font_sizes()
        self.touch_handles.update_positions(self.canvas_rect)
        self.invalidate_keys()
        self.invalidate_shadows()

    def _on_mouse_enter(self, widget, event):
        self._update_double_click_time()

        # ignore event if a mouse button is held down
        # we get the event once the button is released
        if event.state & BUTTON123_MASK:
            return

        # There is no standard way to detect the end of the drag in
        # system mode. End it here, better late than never.
        # Delay it until after the last configure event when resizing.
        # Otherwise the layout hasn't been recalculated for the new size yet
        # and limit_position() makes the window jump to unexpected positions.
        GObject.idle_add(self.stop_system_drag)

        # stop inactivity timer
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(True)

        # stop click polling
        self.stop_click_polling()

        # Force into view for WindowManipulator's system drag mode.
        #if not config.xid_mode and \
        #   not config.window.window_decoration and \
        #   not config.window.force_to_top:
        #    GObject.idle_add(self.force_into_view)

    def _on_mouse_leave(self, widget, event):
        # ignore event if a mouse button is held down
        # we get the event once the button is released
        if event.state & BUTTON123_MASK:
            return

        # Ignore leave events when the cursor hasn't acually left
        # our window. Fixes window becoming idle-transparent while
        # typing into firefox awesomebar.
        # Can't use event.mode as that appears to be broken and
        # never seems to become GDK_CROSSING_GRAB (Precise).
        if self.canvas_rect.is_point_within((event.x, event.y)):
            return

        # start a timer to detect clicks outside of onboard
        self.start_click_polling()

        # start inactivity timer
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.begin_transition(False)

        self.stop_dwelling()
        self.reset_touch_handles()

    def _on_motion(self, widget, event):
        point = (event.x, event.y)
        hit_key = None

        # hit-test touch handles first
        hit_handle = None
        if self.touch_handles.active:
            hit_handle = self.touch_handles.hit_test(point)
            self.touch_handles.set_prelight(hit_handle)

        # hit-test keys
        if hit_handle is None:
            hit_key = self.get_key_at_location(point)

        if event.state & BUTTON123_MASK:

            # fallback=False for faster system resizing (LP: #959035)
            fallback = self.is_moving() or config.window.force_to_top

            # move/resize
            WindowManipulator.handle_motion(self, event, fallback = fallback)

            # stop long press when drag threshold has been overcome
            if self.is_drag_active():
                self.stop_long_press()

        else:
            if not hit_handle is None:
                # handle hovered over -> extend its visible time
                self.start_touch_handles_auto_show()

            # start dwelling if we have entered a dwell-enabled key
            if hit_key and \
               hit_key.sensitive:
                controller = self.button_controllers.get(hit_key)
                if controller and controller.can_dwell() and \
                   not self.is_dwelling() and \
                   not self.already_dwelled(hit_key) and \
                   not config.scanner.enabled and \
                   not config.lockdown.disable_dwell_activation:
                    self.start_dwelling(hit_key)

            self.do_set_cursor_at(point, hit_key)

        # cancel dwelling when the hit key changes
        if self.dwell_key and self.dwell_key != hit_key or \
           self.last_dwelled_key and self.last_dwelled_key != hit_key:
            self.cancel_dwelling()

    def do_set_cursor_at(self, point, hit_key = None):
        """ Set/reset the cursor for frame resize handles """
        if not config.xid_mode:
            allow_drag_cursors = not config.has_window_decoration() and \
                                 not hit_key
            self.set_drag_cursor_at(point, allow_drag_cursors)

    def _on_mouse_button_press(self, widget, event):
        self.stop_click_polling()
        self.stop_dwelling()

        key = None
        point = (event.x, event.y)

        if event.type == Gdk.EventType.BUTTON_PRESS:
            # hit-test touch handles first
            hit_handle = None
            if self.touch_handles.active:
                hit_handle = self.touch_handles.hit_test(point)
                self.touch_handles.set_pressed(hit_handle)
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
            if key is None and \
               not config.has_window_decoration() and \
               not config.xid_mode:
                if WindowManipulator.handle_press(self, event):
                    return True

            # bail if we are in scanning mode
            if config.scanner.enabled:
                return True

            # press the key
            self.active_key = key
            if key:
                # single click?
                if self._last_click_key != key or \
                   event.time - self._last_click_time > self._double_click_time:
                    self.key_down(key, event.button)

                    # start long press detection
                    controller = self.button_controllers.get(key)
                    if controller and controller.can_long_press():
                        self._long_press_timer.start(1.0, self._on_long_press,
                                                    key, event.button)
                # double click?
                else:
                    self.key_down(key, event.button, EventType.DOUBLE_CLICK)

                self._last_click_key = key
                self._last_click_time = event.time

        return True

    def _on_mouse_button_release(self, widget, event):
        if not config.scanner.enabled:
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

    def _on_long_press(self, key, button):
        controller = self.button_controllers.get(key)
        controller.long_press(button)

    def stop_long_press(self):
        self._long_press_timer.stop()

    def key_down(self, key, button = 1, event_type = EventType.CLICK):
        Keyboard.key_down(self, key, button, event_type)
        self._auto_release_timer.start()
        self._active_event_type = event_type

    def key_up(self, key, button = 1, event_type = None):
        if event_type is None:
            event_type = self._active_event_type
        Keyboard.key_up(self, key, button, event_type)
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
            self.redraw([self.dwell_key])
            self.dwell_key.stop_dwelling()
            self.dwell_key = None

    def _on_dwell_timer(self):
        if self.dwell_key:
            self.redraw([self.dwell_key])

            if self.dwell_key.is_done():
                key = self.dwell_key
                self.stop_dwelling()

                self.key_down(key, 0, EventType.DWELL)
                self.key_up(key, 0, EventType.DWELL)

                return False
        return True

    def release_active_key(self):
        if self.active_key:
            self.key_up(self.active_key)
            self.active_key = None
        return True

    def _on_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if config.show_tooltips and \
           not self.is_drag_initiated():
            key = self.get_key_at_location((x, y))
            if key:
                if key.tooltip:
                    r = Gdk.Rectangle()
                    r.x, r.y, r.width, r.height = key.get_canvas_rect()
                    tooltip.set_tip_area(r)   # no effect in oneiric?
                    tooltip.set_text(_(key.tooltip))
                    return True
        return False

    def show_touch_handles(self, show, auto_hide = True):
        """
        Show/hide the enlarged resize/move handels.
        Initiates an opacity fade.
        """
        if show and config.lockdown.disable_touch_handles:
            return

        if show:
            self.touch_handles.set_prelight(None)
            self.touch_handles.set_pressed(None)
            self.touch_handles.active = True
            self.touch_handles_auto_hide = auto_hide
            start, end = 0.0, 1.0
        else:
            self.stop_touch_handles_auto_show()
            start, end = 1.0, 0.0

        if self.touch_handles_fade.target_value != end:
            self.touch_handles_fade.time_step = 0.025
            self.touch_handles_fade.fade_to(start, end, 0.2,
                                      self._on_touch_handles_opacity)

    def reset_touch_handles(self):
        if self.touch_handles.active:
            self.touch_handles.set_prelight(None)
            self.touch_handles.set_pressed(None)

    def start_touch_handles_auto_show(self):
        """ (re-) starts the timer to hide touch handles """
        if self.touch_handles.active and self.touch_handles_auto_hide:
            self.touch_handles_hide_timer.start(3.5,
                                                self.show_touch_handles, False)

    def stop_touch_handles_auto_show(self):
        """ stops the timer to hide touch handles """
        self.touch_handles_hide_timer.stop()

    def _on_touch_handles_opacity(self, opacity, done):
        if done and opacity < 0.1:
            self.touch_handles.active = False

        self.touch_handles.opacity = opacity

        # Convoluted workaround for a weird cairo glitch (Precise).
        # When queuing all handles for drawing the background under
        # the move handle is clipped erroneously and remains transparent.
        # -> Divide handles up into two groups, draw only one
        #    group at a time and fade with twice the frequency.
        if 0:
            self.touch_handles.redraw()
        else:
            for handle in self.touch_handles.handles:
                if bool(self.touch_handles_fade.iteration & 1) != \
                   (handle.id in [Handle.MOVE, Handle.NORTH, Handle.SOUTH]):
                    handle.redraw()

            if done:
                # draw the missing final step
                GObject.idle_add(self._on_touch_handles_opacity, 1.0, False)

    def _on_draw(self, widget, context):
        #self.get_window().set_debug_updates(True)
        surface = None

        try:
            self._maybe_abort_drawing(context)

            x, y, w, h = Rect.from_extents(*context.clip_extents())

            # Do double buffering ourselves so we can abort
            # drawing without leaving partial changes behind.
            window = self.get_window()
            surface = window.create_similar_surface( \
                          cairo.CONTENT_COLOR_ALPHA, w, h)
            buf_cr = cairo.Context(surface)
            buf_cr.translate(-x, -y)

            # draw
            self._draw(widget, buf_cr)

            # paint the buffer
            context.save()
            context.set_source_surface(surface, x, y)
            context.set_operator(cairo.OPERATOR_SOURCE)
            context.paint()
            context.restore()

        except AbortDrawing:
            pass

        if not surface is None:
            surface.finish()

    def _draw(self, widget, context):
        if not Gtk.cairo_should_draw_window(context, self.get_window()):
            return

        clip_rect = Rect.from_extents(*context.clip_extents())

        # Draw a little more than just the clip_rect.
        # Prevents glitches around pressed keys in at least classic theme.
        extra_size = self.layout.context.scale_log_to_canvas((2.0, 2.0))
        draw_rect = clip_rect.inflate(*extra_size)

        # draw background
        decorated = self._draw_background(context)

        # On first run quickly overwrite the background only.
        # This gives a slightly smoother startup, with desktop remnants
        # flashing through for a shorter time.
        if self._first_draw:
            self._first_draw = False
            self.queue_draw()
            return

        if not self.layout:
            return

        self._maybe_abort_drawing(context)

        # draw layer 0 and None-layer background
        layer_ids = self.layout.get_layer_ids()
        if config.window.transparent_background:
            alpha = 0.0
        elif decorated:
            alpha = self._get_background_rgba()[3]
        else:
            alpha = 1.0
        self._draw_layer_key_background(context, alpha, None)
        if layer_ids:
            self._draw_layer_key_background(context, alpha, layer_ids[0])

        # run through all visible layout items
        for item in self.layout.iter_visible_items():
            self._maybe_abort_drawing(context)

            if item.layer_id:
                self._draw_layer_background(context, item, layer_ids, decorated)

            # draw key
            if item.is_key() and \
               draw_rect.intersects(item.get_canvas_border_rect()):
                item.draw_cached(context, self.canvas_rect)

        # draw touch handles (enlarged move and resize handles)
        if self.touch_handles.active:
            corner_radius = config.CORNER_RADIUS if decorated else 0
            self.touch_handles.set_corner_radius(corner_radius)
            self.touch_handles.draw(context)

    def _maybe_abort_drawing(self, context):
        events_pending = GLib.main_context_default().pending()
        if self.active_key and events_pending:
            clip_rect = Rect.from_extents(*context.clip_extents())
            self.queue_draw_area(*clip_rect)
            raise AbortDrawing()

    def _draw_background(self, context):
        """ Draw keyboard background """
        win = self.get_kbd_window()

        transparent_bg = False
        plain_bg = False

        if config.xid_mode:
            # xembed mode
            # Disable transparency in lightdm and g-s-s for now.
            # There are too many issues and there is no real
            # visual improvement.
            if False and \
               win.supports_alpha:
                transparent_bg = True
            else:
                plain_bg = True

        elif config.has_window_decoration():
            # decorated window
            if win.supports_alpha and \
               config.window.transparent_background:
                pass
            else:
                plain_bg = True

        else:
            # undecorated window
            if win.supports_alpha:
                if not config.window.transparent_background:
                    transparent_bg = True
            else:
                plain_bg = True

        if plain_bg:
            self._draw_plain_background(context)
        if transparent_bg:
            self._draw_transparent_background(context)

        return transparent_bg

    def _get_layer_fill_rgba(self, layer_index):
        if self.color_scheme:
            return self.color_scheme.get_layer_fill_rgba(layer_index)
        else:
            return [0.5, 0.5, 0.5, 1.0]

    def _get_background_rgba(self):
        """ layer 0 color * background_transparency """
        layer0_rgba = self._get_layer_fill_rgba(0)
        background_alpha = config.window.get_background_opacity()
        background_alpha *= layer0_rgba[3]
        return layer0_rgba[:3] + [background_alpha]

    def _draw_transparent_background(self, context, decorated = True):
        """ fill with the transparent background color """
        # draw on the potentially aspect-corrected frame around the layout
        rect = self.layout.get_canvas_border_rect()
        rect = rect.inflate(config.get_frame_width())
        corner_radius = config.CORNER_RADIUS

        fill = self._get_background_rgba()

        fill_gradient = config.theme_settings.background_gradient
        if fill_gradient == 0:
            context.set_source_rgba(*fill)
        else:
            fill_gradient /= 100.0
            direction = config.theme_settings.key_gradient_direction
            alpha = -pi/2.0 + pi * direction / 180.0
            gline = gradient_line(rect, alpha)

            pat = cairo.LinearGradient (*gline)
            rgba = brighten(+fill_gradient*.5, *fill)
            pat.add_color_stop_rgba(0, *rgba)
            rgba = brighten(-fill_gradient*.5, *fill)
            pat.add_color_stop_rgba(1, *rgba)
            context.set_source (pat)

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

    def _draw_plain_background(self, context, layer_index = 0):
        """ fill with plain layer 0 color; no alpha support required """
        rgba = self._get_layer_fill_rgba(layer_index)
        context.set_source_rgba(*rgba)
        context.paint()

    def _draw_layer_background(self, context, item, layer_ids, decorated):
        # layer background
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

            # per-layer key background
            self._draw_layer_key_background(context, 1.0, item.layer_id)

    def _draw_layer_key_background(self, context, alpha = 1.0, layer_id = None):
        self._draw_dish_key_background(context, alpha, layer_id)
        self._draw_shadows(context, layer_id)

    def _draw_dish_key_background(self, context, alpha = 1.0, layer_id = None):
        """
        Black background following the contours of key clusters
        to simulate the opening in the keyboard plane.
        """
        if config.theme_settings.key_style == "dish":
            context.push_group()

            context.set_source_rgba(0, 0, 0, 1)
            enlargement = self.layout.context.scale_log_to_canvas((0.8, 0.8))
            corner_radius = self.layout.context.scale_log_to_canvas_x(2.4)

            for item in self.layout.iter_layer_keys(layer_id):
                rect = item.get_canvas_fullsize_rect()
                rect = rect.inflate(*enlargement)
                roundrect_curve(context, rect, corner_radius)
                context.fill()

            context.pop_group_to_source()
            context.paint_with_alpha(alpha);

    def _draw_shadows(self, context, layer_id = None):
        """
        Draw drop shadows for all keys.
        """
        for item in self.layout.iter_layer_keys(layer_id):
            item.draw_shadow_cached(context, self.canvas_rect)

    def invalidate_keys(self):
        """
        Clear cached key patterns, e.g. after resizing,
        change of theme settings.
        """
        if self.layout:
            for item in self.layout.iter_keys():
                item.invalidate_key()

    def invalidate_shadows(self):
        """
        Clear cached shadow patterns, e.g. after resizing,
        change of theme settings.
        """
        if self.layout:
            for item in self.layout.iter_keys():
                item.invalidate_shadow()

    def _on_mods_changed(self):
        _logger.info("Modifiers have been changed")
        self.update_font_sizes()

    def redraw(self, keys = None):
        """
        Queue redrawing for individual keys or the whole keyboard.
        """
        if keys:
            area = None
            for key in keys:
                rect = key.get_canvas_border_rect()
                area = area.union(rect) if area else rect

                # assume keys need to be refreshed when actively redrawn
                # e.g. for pressed state changes, dwell progress updates...
                key.invalidate_key()

            # account for stroke width, anti-aliasing
            if self.layout:
                extra_size = keys[0].get_extra_render_size()
                area = area.inflate(*extra_size)

            self.queue_draw_area(*area)
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
        if config.is_keep_aspect_ratio_enabled():
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
        _logger.info("Refreshing pango layout, new font dpi setting is '{}'" \
                .format(Gtk.Settings.get_default().get_property("gtk-xft-dpi")))

        Key.reset_pango_layout()

