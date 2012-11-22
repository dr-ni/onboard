# -*- coding: utf-8 -*-
""" GTK specific keyboard class """

from __future__ import division, print_function, unicode_literals

from Onboard.utils        import Rect, Timer

### Logging ###
import logging
_logger = logging.getLogger("AtspiAutoShow")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, auto-hide won't be available"))


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
                Atspi.EventListener.register_no_data(self._on_atspi_caret_moved,
                                                     "object:text-caret-moved")
                self._atspi_listeners_registered = True

        else:
            if self._atspi_listeners_registered:
                Atspi.EventListener.deregister_no_data(self._on_atspi_global_focus,
                                                     "focus")
                Atspi.EventListener.deregister_no_data(self._on_atspi_object_focus,
                                                     "object:state-changed:focused")
                Atspi.EventListener.deregister_no_data(self._on_atspi_caret_moved,
                                                     "object:text-caret-moved")
                self._atspi_listeners_registered = False

    def _on_atspi_caret_moved(self, event):
        """
        Show the keyboard on click of an already focused text entry
        (LP: 1078602). Do this only for single line text entries to
        still allow clicking longer documents without having onboard show up.
        """
        if config.auto_show.enabled and \
           not self._keyboard.is_visible():
            accessible = event.source

            if event.source is self._focused_accessible:
                try:
                    state = accessible.get_state_set()
                except: # private exception gi._glib.GError when gedit became unresponsive
                    _logger.warning("AtspiAutoShow: Invalid accessible,"
                                    " failed to get state set")
                    return

                if state.contains(Atspi.StateType.SINGLE_LINE):
                    self._on_atspi_focus(event, True)

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
                   not self.is_frozen() and \
                   not config.is_docking_enabled():
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


