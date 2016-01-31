# -*- coding: utf-8 -*-

# Copyright © 2012-2015 marmuta <marmvta@gmail.com>
#
# This file is part of Onboard.
#
# Onboard is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Onboard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


from __future__ import division, print_function, unicode_literals

from Onboard.AtspiStateTracker import AtspiStateTracker
from Onboard.utils             import Rect
from Onboard.Timer             import TimerOnce
from Onboard.definitions       import RepositionMethodEnum

### Logging ###
import logging
_logger = logging.getLogger("AutoShow")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################


class AutoShow(object):
    """
    Auto-show and hide Onboard.
    """

    # Delay from the last focus event until the keyboard is shown/hidden.
    # Raise it to reduce unnecessary transitions (flickering).
    # Lower it for more immediate reactions.
    SHOW_REACTION_TIME = 0.0
    HIDE_REACTION_TIME = 0.3

    _lock_visible = False
    _frozen = False
    _paused = False
    _keyboard = None
    _state_tracker = AtspiStateTracker()

    def __init__(self, keyboard):
        self._keyboard = keyboard
        self._auto_show_timer = TimerOnce()
        self._pause_timer = TimerOnce()
        self._thaw_timer = TimerOnce()
        self._active_accessible = None

    def reset(self):
        self._auto_show_timer.stop()
        self._pause_timer.stop()
        self._thaw_timer.stop()
        self._frozen = False
        self._paused = False

    def cleanup(self):
        self.reset()
        self.enable(False)  # disconnect atspi events

    def enable(self, enable):
        if enable:
            self._state_tracker.connect("text-entry-activated",
                                        self._on_text_entry_activated)
            self._state_tracker.connect("text-caret-moved",
                                        self._on_text_caret_moved)
        else:
            self._state_tracker.disconnect("text-entry-activated",
                                        self._on_text_entry_activated)
            self._state_tracker.disconnect("text-caret-moved",
                                        self._on_text_caret_moved)

        if enable:
            self._lock_visible = False
            self._frozen = False

    def is_paused(self):
        return self._paused

    def pause(self, duration = None):
        """
        Stop showing and hiding the keyboard window for longer time periods,
        e.g. after pressing a key on a physical keyboard.

        duration in seconds, None to pause forever.
        """
        self._paused = True
        self._pause_timer.stop()
        if not duration is None:
            self._pause_timer.start(duration, self.resume)

        # Discard pending hide/show actions.
        self._auto_show_timer.stop()

    def resume(self):
        """
        Allow hiding and showing the keyboard window again.
        """
        self._pause_timer.stop()
        self._paused = False

    def is_frozen(self):
        return self._frozen

    def freeze(self, thaw_time = None):
        """
        Disable showing and hiding the keyboard window for short periods,
        e.g. to skip unexpected focus events.
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
            self._on_thaw()
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

        # Stop pending auto-repositioning
        if lock:
            self._keyboard.stop_auto_positioning()

    def _on_text_caret_moved(self, event):
        """
        Show the keyboard on click of an already focused text entry
        (LP: 1078602). Do this only for single line text entries to
        still allow clicking longer documents without having onboard show up.
        """
        if config.auto_show.enabled and \
           not self._keyboard.is_visible():

            accessible = self._active_accessible
            if accessible:
                if self._state_tracker.is_single_line():
                    self._on_text_entry_activated(accessible)

    def _on_text_entry_activated(self, accessible):
        self._active_accessible = accessible
        active = bool(accessible)

        # show/hide the keyboard window
        if not active is None:
            # Always allow to show the window even when locked.
            # Mitigates right click on unity-2d launcher hiding
            # onboard before _lock_visible is set (Precise).
            if self._lock_visible:
                active = True

            if not self.is_paused() and \
               not self.is_frozen():
                self.show_keyboard(active)

            # The active accessible changed, stop trying to
            # track the position of the previous one.
            # -> less erratic movement during quick focus changes
            self._keyboard.stop_auto_positioning()

    def show_keyboard(self, show):
        """ Begin AUTO_SHOW or AUTO_HIDE transition """
        # Don't act on each and every focus message. Delay the start
        # of the transition slightly so that only the last of a bunch of
        # focus messages is acted on.
        delay = self.SHOW_REACTION_TIME if show else \
                self.HIDE_REACTION_TIME
        self._auto_show_timer.start(delay, self._begin_transition, show)

    def _begin_transition(self, show):
        self._keyboard.transition_visible_to(show)
        if show:
            self._keyboard.auto_position()
        self._keyboard.commit_transition()
        return False

    def get_repositioned_window_rect(self, view, home, limit_rects,
                                     test_clearance, move_clearance,
                                     horizontal = True, vertical = True):
        """
        Get the alternative window rect suggested by auto-show or None if
        no repositioning is required.
        """
        accessible = self._active_accessible
        if not accessible:
            return None

        acc_rect = self._state_tracker.get_accessible_extents(accessible)
        if acc_rect.is_empty() or \
           self._lock_visible:
            return None

        method = config.get_auto_show_reposition_method()
        x = None
        y = None

        # The home_rect doesn't include window decoration,
        # make sure to add decoration for correct clearance.
        rh = home.copy()
        window = view.get_kbd_window()
        if window:
            offset = window.get_client_offset()
            rh.w += offset[0]
            rh.h += offset[1]

        # "Follow active window" method
        if method == RepositionMethodEnum.REDUCE_POINTER_TRAVEL:
            frame = self._state_tracker.get_frame()
            app_rect = self._state_tracker.get_accessible_extents(frame) \
                        if frame else Rect()
            x, y = self._find_close_position(view, rh,
                                                app_rect, acc_rect, limit_rects,
                                                test_clearance, move_clearance,
                                                horizontal, vertical)

        # "Only move when necessary" method
        if method == RepositionMethodEnum.PREVENT_OCCLUSION:
            x, y = self._find_non_occluding_position(view, rh,
                                                acc_rect, limit_rects,
                                                test_clearance, move_clearance,
                                                horizontal, vertical)
        if not x is None:
            return Rect(x, y, home.w, home.h)
        else:
            return None

    def _find_close_position(self, view, home,
                             app_rect, acc_rect, limit_rects,
                             test_clearance, move_clearance,
                             horizontal = True, vertical = True):
        rh = home
        move_clearance = Rect(10, 10, 10, 10)

        # Leave a different clearance for the new, yet to be found, positions.
        ra = acc_rect.apply_border(*move_clearance)
        rp = app_rect.apply_border(*move_clearance)

        # candidate positions
        vp = []
        if vertical:
            xc = acc_rect.get_center()[0] - rh.w / 2
            if app_rect.w > rh.w:
                xc = max(xc, app_rect.left())
                xc = min(xc, app_rect.right() - rh.w)

            # below window
            vp.append([xc, rp.bottom(), app_rect])

            # above window
            vp.append([xc, rp.top() - rh.h, app_rect])

            # inside maximized window, y at home.y
            vp.append([xc, home.y, acc_rect])
            # vp.append([xc, rp.bottom()-ymargin, app_rect.deflate(rh.h+move_clearance[3]+ymargin)])

            # below text entry
            vp.append([xc, ra.bottom(), acc_rect])

            # above text entry
            vp.append([xc, ra.top() - rh.h, acc_rect])

        # limited, non-intersecting candidate rectangles
        rresult = None
        for p in vp:
            pl = view.limit_position(p[0], p[1],
                                     view.canvas_rect,
                                     limit_rects)
            r = Rect(pl[0], pl[1], rh.w, rh.h)
            ri = p[2]
            rcs = [ri, acc_rect] # collision rects
            if not any(r.intersects(rc) for rc in rcs):
                rresult = r
                break

        if rresult is None:
            # try again, this time horizontally and vertically
            rhtmp = Rect(vp[0][0], vp[0][1], home.w, home.h)
            return self._find_non_occluding_position(view, home,
                                                acc_rect, limit_rects,
                                                test_clearance, move_clearance,
                                                horizontal, vertical)
        else:
            return rresult.get_position()

    def _find_non_occluding_position(self, view, home,
                                     acc_rect, limit_rects,
                                     test_clearance, move_clearance,
                                     horizontal = True, vertical = True):
        rh = home

        # Leave some clearance around the accessible to account for
        # window frames and position errors of firefox entries.
        ra = acc_rect.apply_border(*test_clearance)

        if rh.intersects(ra):

            # Leave a different clearance for the new, yet to be found, positions.
            ra = acc_rect.apply_border(*move_clearance)
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
                pl = view.limit_position(p[0], p[1],
                                         view.canvas_rect,
                                         limit_rects)
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

