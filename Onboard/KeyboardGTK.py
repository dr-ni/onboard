# -*- coding: utf-8 -*-
""" GTK specific keyboard class """

from __future__ import division, print_function, unicode_literals

import os
import time
from math import sin, pi, ceil

import cairo
from gi.repository import GObject, Gdk, Gtk, GLib

from Onboard.utils             import Rect, Timer, FadeTimer, \
                                      roundrect_arc, roundrect_curve, \
                                      gradient_line, brighten, timeit, \
                                      LABEL_MODIFIERS, Modifiers
from Onboard.WindowUtils       import WindowManipulator, Handle, \
                                      InputSequence, POINTER_SEQUENCE
from Onboard.Keyboard          import Keyboard, EventType
from Onboard.KeyGtk            import Key
from Onboard.KeyCommon         import LOD
from Onboard.TouchHandles      import TouchHandles
from Onboard.AtspiStateTracker import AtspiStateTracker

### Logging ###
import logging
_logger = logging.getLogger("KeyboardGTK")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

# Gnome introspection calls are surprisingly expensive
# -> prepare stuff for faster access
BUTTON123_MASK = Gdk.ModifierType.BUTTON1_MASK | \
                 Gdk.ModifierType.BUTTON2_MASK | \
                 Gdk.ModifierType.BUTTON3_MASK


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
        self._keyboard.update_ui_no_resize()
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


class HideInputLineTimer(Timer):
    """
    Temporarily hides the input line when the pointer touches it.
    """
    def __init__(self, keyboard):
        self._keyboard = keyboard

    def handle_motion(self, sequence):
        """
        Handle pointer motion.
        """
        point = sequence.point

        # Hide inputline when the pointer touches it.
        # Show it again when leaving the area.
        for key in self._keyboard.get_text_displays():
            rect = key.get_canvas_border_rect()
            if rect.is_point_within(point):
                if not self.is_running():
                    self.start(0.3)
            else:
                self.stop()
                self._keyboard.hide_input_line(False)

    def on_timer(self):
        """ Hide the input line after delay """
        self._keyboard.hide_input_line(True)
        return False


class AutoShow(object):
    """
    Auto-show and hide Onboard.
    """

    # Delay from the last focus event until the keyboard is shown/hidden.
    # Raise it to reduce unnecessary transitions (flickering).
    # Lower it for more immediate reactions.
    SHOW_REACTION_TIME = 0.0
    HIDE_REACTION_TIME = 0.3

    _keyboard = None
    _lock_visible = False
    _frozen = False

    def __init__(self, keyboard, state_tracker):
        self._keyboard = keyboard
        self._state_tracker = state_tracker
        self._auto_show_timer = Timer()
        self._thaw_timer = Timer()

    def cleanup(self):
        self._auto_show_timer.stop()
        self._thaw_timer.stop()

    def enable(self, enable):
        if enable:
            self._state_tracker.connect("text-entry-activated",
                                        self._on_text_entry_activated)
        else:
            self._state_tracker.disconnect("text-entry-activated",
                                           self._on_text_entry_activated)

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

    def _on_text_entry_activated(self, accessible):
        active = bool(accessible)

        # show/hide the keyboard window
        if not active is None:
            # Always allow to show the window even when locked.
            # Mitigates right click on unity-2d launcher hiding
            # onboard before _lock_visible is set (Precise).
            if self._lock_visible:
                active = True

            if not self.is_frozen():
                self.show_keyboard(active)

        # reposition the keyboard window
        if active and \
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
        rect = self._state_tracker.get_extents()
        if not rect.is_empty() and \
           not self._lock_visible:
            return self._get_window_rect_for_accessible_rect(home, rect)
        return None

    def _get_window_rect_for_accessible_rect(self, home, rect):
        """
        Find new window position based on the screen rect of
        the focused text entry.
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

        # Leave some clearance around the widget to account for
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
        WindowManipulator.__init__(self)

        self.atspi_state_tracker = AtspiStateTracker()
        self.auto_show           = AutoShow(self, self.atspi_state_tracker)
        self.auto_show.enable(config.is_auto_show_enabled())

        Keyboard.__init__(self)
        WindowManipulator.__init__(self)

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

        self._input_sequences = {}

        self.inactivity_timer = InactivityTimer(self)

        self.touch_handles = TouchHandles()
        self.touch_handles_hide_timer = Timer()
        self.touch_handles_fade = FadeTimer()
        self.touch_handles_auto_hide = True

        self._aspect_ratio = None
        self._first_draw = True
        self._lod = LOD.FULL
        self._font_sizes_valid = False
        self._last_canvas_shadow_rect = Rect()
        self._shadow_quality_valid = False

        self._hide_input_line_timer = HideInputLineTimer(self)

        self._transition_timer = Timer()
        self._transition_state = TransitionState()
        self._transition_state.visible.value = 0.0
        self._transition_state.active.value = 1.0

        self._language_menu = LanguageMenu(self)

        #self.set_double_buffered(False)
        self.set_app_paintable(True)

        # no tooltips when embedding, gnome-screen-saver flickers (Oneiric)
        if not config.xid_mode:
            self.set_has_tooltip(True) # works only at window creation -> always on

        self._multi_touch_enabled = config.keyboard.multi_touch_enabled
        event_mask = Gdk.EventMask.BUTTON_PRESS_MASK | \
                     Gdk.EventMask.BUTTON_RELEASE_MASK | \
                     Gdk.EventMask.POINTER_MOTION_MASK | \
                     Gdk.EventMask.LEAVE_NOTIFY_MASK | \
                     Gdk.EventMask.ENTER_NOTIFY_MASK
        if self._multi_touch_enabled:
            event_mask |= Gdk.EventMask.TOUCH_MASK
        self.add_events(event_mask)


        self.connect("parent-set",           self._on_parent_set)
        self.connect("draw",                 self._on_draw)
        self.connect("button-press-event",   self._on_mouse_button_press)
        self.connect("button_release_event", self._on_mouse_button_release)
        self.connect("motion-notify-event",  self._on_motion)
        self.connect("query-tooltip",        self._on_query_tooltip)
        self.connect("enter-notify-event",   self._on_mouse_enter)
        self.connect("leave-notify-event",   self._on_mouse_leave)
        self.connect("configure-event",      self._on_configure_event)
        self.connect("touch-event",          self._on_touch_event)

        self.update_resize_handles()
        self._update_double_click_time()

        self.show()

    def on_layout_loaded(self):
        """ called when the layout has been loaded """
        Keyboard.on_layout_loaded(self)
        self.invalidate_shadow_quality()

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

        # free xserver memory
        self.invalidate_keys()
        self.invalidate_shadows()

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

    def reset_lod(self):
        """ Reset to full level of detail """
        if self._lod != LOD.FULL:
            self._lod = LOD.FULL
            self.invalidate_keys()
            self.invalidate_shadows()
            self.invalidate_font_sizes()
            self.redraw()

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
        if self.has_latched_sticky_keys() or \
           config.wp.enabled:
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

    def on_drag_activated(self):
        self._lod = LOD.MINIMAL

    def on_drag_done(self):
        """ Overload for WindowManipulator """
        window = self.get_drag_window()
        if window:
            window.on_user_positioning_done()

        self.reset_lod()

    def get_always_visible_rect(self):
        """
        Returns the bounding rectangle of all move buttons
        in canvas coordinates.
        Overload for WindowManipulator
        """
        keys = self.find_items_from_ids(["move"])
        bounds = None
        for key in keys:
            r = key.get_canvas_border_rect()
            if not bounds:
                bounds = r
            else:
                bounds = bounds.union(r)

        return bounds

    def get_move_button_rect(self):
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
        if self.canvas_rect.w != self.get_allocated_width() or \
           self.canvas_rect.h != self.get_allocated_height():
            self.update_layout()
            self.touch_handles.update_positions(self.canvas_rect)
            self.invalidate_keys()
            if self._lod == LOD.FULL:
                self.invalidate_shadows()
            self.invalidate_font_sizes()

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

    def do_set_cursor_at(self, point, hit_key = None):
        """ Set/reset the cursor for frame resize handles """
        if not config.xid_mode:
            allow_drag_cursors = not config.has_window_decoration() and \
                                 not hit_key
            self.set_drag_cursor_at(point, allow_drag_cursors)

    def _on_mouse_button_press(self, widget, event):
        if self._multi_touch_enabled:
            source_device = event.get_source_device()
            source = source_device.get_source()
            #print("_on_mouse_button_press",source)
            if source == Gdk.InputSource.TOUCHSCREEN:
                return

        if event.type == Gdk.EventType.BUTTON_PRESS:
            sequence = InputSequence()
            sequence.init_from_button_event(event)

            self._input_sequence_begin(sequence)

    def _on_motion(self, widget, event):
        if self._multi_touch_enabled:
            source_device = event.get_source_device()
            source = source_device.get_source()
            #print("_on_motion",source)
            if source == Gdk.InputSource.TOUCHSCREEN:
                return

        sequence = self._input_sequences.get(POINTER_SEQUENCE)
        if sequence is None:
            sequence = InputSequence()

        sequence.init_from_motion_event(event)

        self._input_sequence_update(sequence)

    def _on_mouse_button_release(self, widget, event):
        sequence = self._input_sequences.get(POINTER_SEQUENCE)
        if not sequence is None:
            sequence.point      = (event.x, event.y)
            sequence.root_point = (event.x_root, event.y_root)
            sequence.time       = event.time

            self._input_sequence_end(sequence)

    def _on_long_press(self, key, button):
        controller = self.button_controllers.get(key)
        controller.long_press(button)

    def stop_long_press(self):
        self._long_press_timer.stop()

    def _on_touch_event(self, widget, event):
        source_device = event.get_source_device()
        source = source_device.get_source()
        #print("_on_touch_event",source)
        if source != Gdk.InputSource.TOUCHSCREEN:
            return

        touch = event.touch
        id = str(touch.sequence)

        event_type = event.type
        if event_type == Gdk.EventType.TOUCH_BEGIN:
            sequence = InputSequence()
            sequence.init_from_touch_event(touch, id)

            self._input_sequence_begin(sequence)

        elif event_type == Gdk.EventType.TOUCH_UPDATE:
            sequence = self._input_sequences.get(id)
            sequence.point = (touch.x, touch.y)
            sequence.root_point = (touch.x_root, touch.y_root)

            self._input_sequence_update(sequence)

        else:
            if event_type == Gdk.EventType.TOUCH_END:
                pass

            elif event_type == Gdk.EventType.TOUCH_CANCEL:
                pass

            sequence = self._input_sequences.get(id)
            self._input_sequence_end(sequence)

#        print(event_type, self._input_sequences)

    def _input_sequence_begin(self, sequence):
        """ Button press/touch begin """
        self._input_sequences[sequence.id] = sequence
#        print("_input_sequence_begin", self._input_sequences)

        self.stop_click_polling()
        self.stop_dwelling()
        point = sequence.point
        key = None

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
            if WindowManipulator.handle_press(self, sequence):
                return True

        # bail if we are in scanning mode
        if config.scanner.enabled:
            return True

        # press the key
        if key:
            # single click?
            if self._last_click_key != key or \
               sequence.time - self._last_click_time > self._double_click_time:
                self.key_down(key, sequence.button)

                # start long press detection
                controller = self.button_controllers.get(key)
                if controller and controller.can_long_press():
                    self._long_press_timer.start(1.0, self._on_long_press,
                                                 key, sequence.button)
            # double click?
            else:
                self.key_down(key, sequence.button, EventType.DOUBLE_CLICK)

            self._last_click_key = key
            self._last_click_time = sequence.time

        sequence.active_key = key

        return True

    def _input_sequence_update(self, sequence):
        """ Pointer motion/touch update """
        #print("_input_sequence_update", self._input_sequences)
        point = sequence.point
        hit_key = None

        # hit-test touch handles first
        hit_handle = None
        if self.touch_handles.active:
            hit_handle = self.touch_handles.hit_test(point)
            self.touch_handles.set_prelight(hit_handle)

        # hit-test keys
        if hit_handle is None:
            hit_key = self.get_key_at_location(point)

        if sequence.state & BUTTON123_MASK:

            # move/resize
            # fallback=False for faster system resizing (LP: #959035)
            fallback = True #self.is_moving() or config.window.force_to_top

            # move/resize
            WindowManipulator.handle_motion(self, sequence, fallback = fallback)

            # stop long press when drag threshold has been overcome
            if self.is_drag_active():
                self.stop_long_press()

        else:
            if not hit_handle is None:
                # handle hovered over -> extend its visible time
                self.start_touch_handles_auto_show()

            # Show/hide the input line
            self._hide_input_line_timer.handle_motion(sequence)

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

    def _input_sequence_end(self, sequence):
        """ Button release/touch end """
        del self._input_sequences[sequence.id]
        #print("_input_sequence_end", self._input_sequences)

        if sequence.active_key and \
           not config.scanner.enabled:
            self.key_up(sequence.active_key)

        self.stop_drag()
        self._long_press_timer.stop()

        # reset cursor when there was no cursor motion
        point = sequence.point
        hit_key = self.get_key_at_location(point)
        self.do_set_cursor_at(point, hit_key)

        # reset touch handles
        self.reset_touch_handles()
        self.start_touch_handles_auto_show()

    def has_input_sequences(self):
        """ Are any touches still ongoing? """
        return bool(self._input_sequences)

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
            size, size_mm = self.get_monitor_dimensions()
            self.touch_handles.set_monitor_dimensions(size, size_mm)
            self.touch_handles.update_positions(self.canvas_rect)

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

    def get_monitor_dimensions(self):
        window = self.get_window()
        screen = self.get_screen()
        if window and screen:
            monitor = screen.get_monitor_at_window(window)
            r = screen.get_monitor_geometry(monitor)
            size = (r.width, r.height)
            size_mm = (screen.get_monitor_width_mm(monitor),
                       screen.get_monitor_height_mm(monitor))

            # Nexus7 simulation
            device = None       # keep this at None
            if device == 0:     # dimension unavailable
                size_mm = 0, 0
            if device == 1:     # Nexus 7, as it should report
                size = 1280, 800
                size_mm = 150, 94

            return size, size_mm
        else:
            return None, None

    def get_min_window_size(self):
        min_mm = (50, 20)  # just large enough to grab with a 3 finger gesture
        size, size_mm = self.get_monitor_dimensions()
        w = size[0] * min_mm[0] / size_mm[0] \
            if size_mm[0] else 150
        h = size[1] * min_mm[1] / size_mm[1] \
            if size_mm[0] else 100
        return w, h

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
        # When queuing all handles for drawing, the background under
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
        if not Gtk.cairo_should_draw_window(context, self.get_window()):
            return

        lod = self._lod

        # lazily update font sizes and labels
        if not self._font_sizes_valid:
            self.update_labels(lod)

        draw_rect = self._get_draw_rect(context)

        # draw background
        decorated = self._draw_background(context, lod)

        # On first run quickly overwrite the background only.
        # This gives a slightly smoother startup, with desktop remnants
        # flashing through for a shorter time.
        if self._first_draw:
            self._first_draw = False
            #self.queue_draw()
            #return

        if not self.layout:
            return

        # draw layer 0 and None-layer background
        layer_ids = self.layout.get_layer_ids()
        if config.window.transparent_background:
            alpha = 0.0
        elif decorated:
            alpha = self._get_background_rgba()[3]
        else:
            alpha = 1.0
        self._draw_layer_key_background(context, alpha, None, lod)
        if layer_ids:
            self._draw_layer_key_background(context, alpha, layer_ids[0], lod)

        # run through all visible layout items
        for item in self.layout.iter_visible_items():
            if item.layer_id:
                self._draw_layer_background(context, item, layer_ids, decorated)

            # draw key
            if item.is_key() and \
               draw_rect.intersects(item.get_canvas_border_rect()):
                if lod == LOD.FULL:
                    item.draw_cached(context)
                else:
                    item.draw(context, lod)

        # draw touch handles (enlarged move and resize handles)
        if self.touch_handles.active:
            corner_radius = config.CORNER_RADIUS if decorated else 0
            self.touch_handles.set_corner_radius(corner_radius)
            self.touch_handles.draw(context)

    def _draw_background(self, context, lod):
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
                self._clear_background(context)
                transparent_bg = True
            else:
                plain_bg = True

        elif config.has_window_decoration():
            # decorated window
            if win.supports_alpha and \
               config.window.transparent_background:
                self._clear_background(context)
            else:
                plain_bg = True

        else:
            # undecorated window
            if win.supports_alpha:
                self._clear_background(context)
                if not config.window.transparent_background:
                    transparent_bg = True
            else:
                plain_bg = True

        if plain_bg:
            self._draw_plain_background(context)
        if transparent_bg:
            self._draw_transparent_background(context, lod)

        return transparent_bg

    def _clear_background(self, context):
        """
        Clear the whole gtk background.
        Makes the whole strut transparent in xembed mode.
        """
        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.paint()
        context.restore()

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

    def _draw_transparent_background(self, context, lod):
        """ fill with the transparent background color """
        # draw on the potentially aspect-corrected frame around the layout
        rect = self.layout.get_canvas_border_rect()
        rect = rect.inflate(config.get_frame_width())
        corner_radius = config.CORNER_RADIUS

        fill = self._get_background_rgba()

        fill_gradient = config.theme_settings.background_gradient
        if lod == LOD.MINIMAL or \
           fill_gradient == 0:
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

        docked = config.window.docking_enabled
        if docked:
            context.rectangle(*rect)
        else:
            roundrect_arc(context, rect, corner_radius)
        context.fill()

        if not docked:
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

    def _draw_layer_key_background(self, context, alpha = 1.0,
                                   layer_id = None, lod = LOD.FULL):
        self._draw_dish_key_background(context, alpha, layer_id)
        self._draw_shadows(context, layer_id, lod)

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

    def _draw_shadows(self, context, layer_id, lod):
        """
        Draw drop shadows for all keys.
        """
        if not config.theme_settings.key_shadow_strength:
            return

        # auto-select shadow quality
        if not self._shadow_quality_valid:
            quality = self.probe_shadow_performance(context)
            Key.set_shadow_quality(quality)
            self._shadow_quality_valid = True

        # draw shadows
        context.save()
        self.set_shadow_scale(context, lod)

        draw_rect = self._get_draw_rect(context)
        for item in self.layout.iter_layer_keys(layer_id):
            if draw_rect.intersects(item.get_canvas_border_rect()):
                item.draw_shadow_cached(context)

        context.restore()

    def invalidate_shadow_quality(self):
        self._shadow_quality_valid = False

    def probe_shadow_performance(self, context):
        """
        Select shadow quality based on the estimated render time of
        the first layer's shadows.
        """
        probe_begin = time.time()
        quality = None

        layout = self.layout
        max_total_time = 0.03  # upper limit refreshing all key's shadows [s]
        max_probe_keys = 10
        keys = None
        for layer_id in layout.get_layer_ids():
            layer_keys = list(layout.iter_layer_keys(layer_id))
            num_first_layer_keys = len(layer_keys)
            keys = layer_keys[:max_probe_keys]
            break

        if keys:
            for quality, (steps, alpha) in enumerate(Key._shadow_presets):
                begin = time.time()
                for key in keys:
                    key.create_shadow_surface(context, steps, 0.1)
                elapsed = time.time() - begin
                estimate = elapsed / len(keys) * num_first_layer_keys
                _logger.debug("Probing shadow performance: "
                              "estimated full refresh time {:6.1f}ms "
                              "at quality {}." \
                              .format(estimate * 1000,
                                      quality))
                if estimate > max_total_time:
                    break

            _logger.info("Probing shadow performance took {:.1f}ms. "
                         "Selecting quality {}." \
                         .format((time.time() - probe_begin) * 1000,
                                 quality))
        return quality

    def set_shadow_scale(self, context, lod):
        """
        Shadows aren't normally refreshed while resizing.
        -> scale the cached ones to fit the new canvas size.
        Occasionally refresh them anyway if scaling becomes noticeable.
        """
        r  = self.canvas_rect
        if lod < LOD.FULL:
            rl = self._last_canvas_shadow_rect
            scale_x = r.w / rl.w
            scale_y = r.h / rl.h

            # scale in a reasonable range? -> draw stretched shadows
            smin = 0.8
            smax = 1.2
            if smax > scale_x > smin and \
               smax > scale_y > smin:
                context.scale(scale_x, scale_y)
            else:
                # else scale is too far out -> refresh shadows
                self.invalidate_shadows()
                self._last_canvas_shadow_rect = r
        else:
            self._last_canvas_shadow_rect = r

    def _get_draw_rect(self, context):
        clip_rect = Rect.from_extents(*context.clip_extents())

        # Draw a little more than just the clip_rect.
        # Prevents glitches around pressed keys in at least classic theme.
        extra_size = self.layout.context.scale_log_to_canvas((2.0, 2.0))
        return clip_rect.inflate(*extra_size)

    def invalidate_font_sizes(self):
        """
        Update font_sizes at the next possible chance.
        """
        self._font_sizes_valid = False

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
        super(KeyboardGTK, self)._on_mods_changed()

    def redraw(self, keys = None, invalidate = True):
        """
        Queue redrawing for individual keys or the whole keyboard.
        """
        if keys is None:
            self.queue_draw()
        elif len(keys) == 0:
            pass
        else:
            area = None
            for key in keys:
                rect = key.get_canvas_border_rect()
                area = area.union(rect) if area else rect

                # assume keys need to be refreshed when actively redrawn
                # e.g. for pressed state changes, dwell progress updates...
                if invalidate:
                    key.invalidate_key()

            # account for stroke width, anti-aliasing
            if self.layout:
                extra_size = keys[0].get_extra_render_size()
                area = area.inflate(*extra_size)

            self.queue_draw_area(*area)

    def process_updates(self):
        """ Draw now, synchronously. """
        window = self.get_window()
        if window:
            window.process_updates(True)

    def update_labels(self, lod = LOD.FULL):
        """
        Cycles through each group of keys and set each key's
        label font size to the maximum possible for that group.
        """
        mod_mask = self.get_mod_mask()
        context = self.create_pango_context()

        if lod == LOD.FULL: # don't configure labels while dragging
            changed_keys = set(self.configure_labels())
        else:
            changed_keys = set()

        for keys in self.layout.get_key_groups().values():
            max_size = 0
            for key in keys:
                best_size = key.get_best_font_size(context, mod_mask)
                if best_size:
                    if not max_size or best_size < max_size:
                        max_size = best_size

            for key in keys:
                if key.font_size != max_size:
                    key.font_size = max_size
                    changed_keys.add(key)

        self._font_sizes_valid = True
        return tuple(changed_keys)

    def configure_labels(self, keys = None):
        """
        Update key labels according to the active modifier state.
        """
        changed_keys = []
        mod_mask = self.get_mod_mask()
        context = self.create_pango_context()

        if keys is None:
            keys = self.layout.iter_keys()

        for key in keys:
            old_label = key.get_label()
            key.configure_label(mod_mask)
            if key.get_label() != old_label:
                changed_keys.append(key)

        return changed_keys

    def emit_quit_onboard(self, data=None):
        _logger.debug("Entered emit_quit_onboard")
        self.get_kbd_window().emit("quit-onboard")

    def get_kbd_window(self):
        return self.get_parent()

    def get_click_type_button_screen_rects(self):
        """
        Returns bounding rectangles of all click type buttons
        in root window coordinates.
        """
        keys = self.find_items_from_ids(["singleclick",
                                         "secondaryclick",
                                         "middleclick",
                                         "doubleclick",
                                         "dragclick"])
        return [self.get_key_screen_rect(key) for key in keys]

    def get_key_screen_rect(self, key):
        """
        Returns bounding rectangles of key in in root window coordinates.
        """
        r = key.get_canvas_border_rect()
        x0, y0 = self.get_window().get_root_coords(r.x, r.y)
        x1, y1 = self.get_window().get_root_coords(r.x + r.w,
                                                   r.y + r.h)
        return Rect(x0, y0, x1 - x0, y1 -y0)

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
        When the systems font dpi setting changes, our pango layout object
        still caches the old setting, leading to wrong font scaling.
        Refresh the pango layout object.
        """
        _logger.info("Refreshing pango layout, new font dpi setting is '{}'" \
                .format(Gtk.Settings.get_default().get_property("gtk-xft-dpi")))

        Key.reset_pango_layout()

    def set_dock_mode(self, mode, expand):
        window = self.get_kbd_window()
        if window:
            window.set_dock_mode(mode, expand)

    def show_snippets_dialog(self, snippet_id):
        """ Show dialog for creating a new snippet """

        # turn off AT-SPI listeners to prevent D-BUS deadlocks (Quantal).
        self.on_focusable_gui_opening()

        dialog = Gtk.Dialog(_("New snippet"),
                            self.get_toplevel(), 0,
                            (Gtk.STOCK_CANCEL,
                             Gtk.ResponseType.CANCEL,
                             _("_Save snippet"),
                             Gtk.ResponseType.OK))

        # Don't hide dialog behind the keyboard in force-to-top mode.
        if config.window.force_to_top:
            dialog.set_position(Gtk.WindowPosition.NONE)

        dialog.set_default_response(Gtk.ResponseType.OK)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      spacing=12, border_width=5)
        dialog.get_content_area().add(box)

        msg = Gtk.Label(_("Enter a new snippet for this button:"),
                        xalign=0.0)
        box.add(msg)

        label_entry = Gtk.Entry(hexpand=True)
        text_entry  = Gtk.Entry(hexpand=True)
        label_label = Gtk.Label(_("_Button label:"),
                                xalign=0.0,
                                use_underline=True,
                                mnemonic_widget=label_entry)
        text_label  = Gtk.Label(_("S_nippet:"),
                                xalign=0.0,
                                use_underline=True,
                                mnemonic_widget=text_entry)

        grid = Gtk.Grid(row_spacing=6, column_spacing=3)
        grid.attach(label_label, 0, 0, 1, 1)
        grid.attach(text_label, 0, 1, 1, 1)
        grid.attach(label_entry, 1, 0, 1, 1)
        grid.attach(text_entry, 1, 1, 1, 1)
        box.add(grid)

        dialog.connect("response", self._on_snippet_dialog_response, \
                       snippet_id, label_entry, text_entry)
        label_entry.grab_focus()
        dialog.show_all()

    def _on_snippet_dialog_response(self, dialog, response, snippet_id, \
                                    label_entry, text_entry):
        if response == Gtk.ResponseType.OK:
            label = label_entry.get_text()
            text = text_entry.get_text()

            if sys.version_info.major == 2:
                label = label.decode("utf-8")
                text = text.decode("utf-8")

            config.set_snippet(snippet_id, (label, text))
        dialog.destroy()

        self.on_snippets_dialog_closed()

        # Reenable AT-SPI keystroke listeners.
        # Delay this until the dialog is really gone.
        GObject.idle_add(self.on_focusable_gui_closed)

    def show_language_menu(self, key, button):
        self._language_menu.popup(key, button)


class LanguageMenu:
    """ Popup menu for the language button """

    def __init__(self, keyboard):
        self._keyboard = keyboard

    def popup(self, key, button):
        self._keyboard.on_focusable_gui_opening()

        max_mru_languages = config.word_suggestions.max_recent_languages
        all_mru_lang_ids = config.word_suggestions.recent_languages

        languagedb = self._keyboard._languagedb
        lang_ids = set(languagedb.get_language_ids())
        active_lang_id = self._keyboard.get_active_lang_id()

        mru_lang_ids    = [id for id in all_mru_lang_ids if id in lang_ids] \
                          [:max_mru_languages]
        other_lang_ids   = set(lang_ids).difference(mru_lang_ids)

        other_lang_names = [languagedb.get_language_full_name(id) \
                           for id in other_lang_ids]
        # language sub menu
        lang_menu = Gtk.Menu()
        for name, lang_id in sorted(zip(other_lang_names, other_lang_ids)):
            item = Gtk.MenuItem.new_with_label(name)
            item.connect("activate", self._on_other_language_activated, lang_id)
            lang_menu.append(item)

        # popup menu
        menu = Gtk.Menu()

        item = Gtk.CheckMenuItem.new_with_mnemonic(_("_System Language"))
        item.set_draw_as_radio(True)
        item.set_active(not active_lang_id)
        item.connect("activate", self._on_language_activated, "")
        menu.append(item)

        item = Gtk.SeparatorMenuItem.new()
        menu.append(item)

        for lang_id in mru_lang_ids:
            name = languagedb.get_language_full_name(lang_id)
            item = Gtk.CheckMenuItem.new_with_label(name)
            item.set_draw_as_radio(True)
            item.set_active(lang_id == active_lang_id)
            item.connect("activate", self._on_language_activated, lang_id)
            menu.append(item)

        if other_lang_ids:
            if mru_lang_ids:
                item = Gtk.MenuItem.new_with_mnemonic(_("Other _Languages"))
            else:
                item = Gtk.MenuItem.new_with_mnemonic(_("_Languages"))
            item.set_submenu(lang_menu)
            menu.append(item)

        if lang_ids:
            item = Gtk.SeparatorMenuItem.new()
            menu.append(item)

        item = Gtk.CheckMenuItem.new_with_mnemonic(_("_Auto-detect Language"))
        menu.append(item)

        menu.connect("unmap", self._language_menu_unmap)
        menu.show_all()

        menu.popup(None, None, self._language_menu_positioning_func,
                   key, button, Gtk.get_current_event_time())

    def _language_menu_unmap(self, menu):
        Timer(0.5, self._keyboard.on_focusable_gui_closed)

    def _language_menu_positioning_func(self, menu, key):
        r = self._keyboard.get_key_screen_rect(key)
        x = r.right() - menu.get_allocated_width()
        return x, r.bottom(), True

    def _on_language_activated(self, menu, lang_id):
        self._keyboard.on_active_lang_id_changed(lang_id)

    def _on_other_language_activated(self, menu, lang_id):
        if lang_id:  # empty string = system default
            self._set_mru_lang_id(lang_id)
        self._keyboard.on_active_lang_id_changed(lang_id)

    def _set_mru_lang_id(self, lang_id):
        max_recent_languages = config.word_suggestions.max_recent_languages
        recent_languages = config.word_suggestions.recent_languages
        if lang_id in recent_languages:
            recent_languages.remove(lang_id)
        recent_languages.insert(0, lang_id)
        recent_languages = recent_languages[:max_recent_languages]
        config.word_suggestions.recent_languages = recent_languages

