 # -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import time
from math import sqrt
import cairo
from gi.repository import GObject, GdkX11, Gdk, Gtk

from Onboard.utils       import Rect, CallOnce
from Onboard.WindowUtils import Orientation, WindowRectTracker, \
                                set_unity_property
from Onboard.IconPalette import IconPalette
from Onboard.Keyboard    import DockMode

import Onboard.osk as osk

### Logging ###
import logging
_logger = logging.getLogger("KbdWindow")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################


class KbdWindowBase:
    """
    Very messy class holds the keyboard widget. The mess is the docked
    window support which is disable because of numerous metacity bugs.
    """
    keyboard_widget = None
    icp = None

    def __init__(self):
        _logger.debug("Entered in __init__")

        self._osk_util   = osk.Util()
        self._osk_struts = osk.Struts()

        self.application = None
        self.supports_alpha = False

        self._visible = False
        self._sticky = False
        self._iconified = False
        self._maximized = False

        self._docking_enabled = False
        self._docking_edge = None
        self._docking_rect = Rect()
        self._monitor_workarea = {}

        self._opacity = 1.0
        self._default_resize_grip = self.get_has_resize_grip()
        self._force_to_top = False

        self._known_window_rects = []
        self._written_window_rects = {}
        self._wm_quirks = None

        self.set_accept_focus(False)
        self.set_app_paintable(True)
        self.set_keep_above(True)
        #Gtk.Settings.get_default().set_property("gtk-touchscreen-mode", True)

        Gtk.Window.set_default_icon_name("onboard")
        self.set_title(_("Onboard"))

        self.connect("window-state-event",      self._cb_window_state_event)
        self.connect("visibility-notify-event", self._cb_visibility_notify)
        self.connect('screen-changed',          self._cb_screen_changed)
        self.connect('composited-changed',      self._cb_composited_changed)
        self.connect("realize",                 self._cb_realize_event)
        self.connect("unrealize",               self._cb_unrealize_event)
        self.connect("map",                     self._cb_map_event)
        self.connect("unmap",                   self._cb_unmap_event)

        self.detect_window_manager()
        self.check_alpha_support()
        self.update_unrealized_options()

        _logger.debug("Leaving __init__")

    def cleanup(self):
        pass

    def _cb_realize_event(self, user_data):
        # Disable maximize function (LP #859288)
        # unity:    no effect, but double click on top bar unhides anyway
        # unity-2d: works and avoids the bug
        if self.get_window():
            self.get_window().set_functions(Gdk.WMFunction.RESIZE | \
                                            Gdk.WMFunction.MOVE | \
                                            Gdk.WMFunction.MINIMIZE | \
                                            Gdk.WMFunction.CLOSE)
        set_unity_property(self)

    def _cb_screen_changed(self, widget, old_screen=None):
        self.detect_window_manager()
        self.check_alpha_support()
        self.queue_draw()

    def _cb_composited_changed(self, widget):
        self.detect_window_manager()
        self.check_alpha_support()
        self.queue_draw()

    def detect_window_manager(self):
        """ Detect the WM and select WM specific behavior. """

        wm = config.quirks
        if not wm:
            # Returns None on X error BadWindow (LP: 1016980)
            # Keep the same quirks as before in that case.
            wm = self._osk_util.get_current_wm_name()

        if wm:
            self._wm_quirks = None
            for cls in [WMQuirksCompiz, WMQuirksMetacity, WMQuirksMutter]:
                if cls.wm == wm.lower():
                    self._wm_quirks = cls()
                    break

        if not self._wm_quirks:
            self._wm_quirks = WMQuirksDefault()

        _logger.debug("window manager: {}".format(wm))
        _logger.debug("quirks selected: {}" \
                                       .format(str(self._wm_quirks.__class__)))
        return True

    def check_alpha_support(self):
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        self.supports_alpha = visual and screen.is_composited()

        if self.keyboard_widget:
            self.keyboard_widget.supports_alpha = self.supports_alpha

        _logger.debug("screen changed, supports_alpha={}" \
                       .format(self.supports_alpha))

        # Unity may start onboard early, where there is no compositing
        # enabled yet. If we set the visual later the window never becomes
        # transparent -> do it as soon as there is an rgba visual.
        if visual:
            self.set_visual(visual)
            if self.keyboard_widget:
                self.keyboard_widget.set_visual(visual)

            # full transparency for the window background
            self.override_background_color(Gtk.StateFlags.NORMAL,
                                           Gdk.RGBA(0, 0, 0, 0))
            if self.keyboard_widget:
                self.keyboard_widget.override_background_color(Gtk.StateFlags.NORMAL,
                                           Gdk.RGBA(0, 0, 0, 0))
        else:
            _logger.info(_("no window transparency available;"
                           " screen doesn't support alpha channels"))
        return False

    def _init_window(self):
        self.update_window_options()
        self.show()

    def _cb_realize_event(self, user_data):
        """ Gdk window created """
        # Disable maximize function (LP #859288)
        # unity:    no effect, but double click on top bar unhides anyway
        # unity-2d: works and avoids the bug
        self.get_window().set_functions(Gdk.WMFunction.RESIZE | \
                                        Gdk.WMFunction.MOVE | \
                                        Gdk.WMFunction.MINIMIZE | \
                                        Gdk.WMFunction.CLOSE)

        set_unity_property(self)

        if not config.xid_mode:   # not when embedding
            force_to_top = config.window.force_to_top
            if force_to_top:
                self.get_window().set_override_redirect(True)
            self._force_to_top = force_to_top

            self.update_taskbar_hint()
            self.restore_window_rect(startup = True)

        # set min window size for unity MT grab handles
        if self.keyboard_widget:
            geom = Gdk.Geometry()
            geom.min_width, geom.min_height = self.keyboard_widget.get_min_window_size()
            self.set_geometry_hints(self, geom, Gdk.WindowHints.MIN_SIZE)

    def _cb_unrealize_event(self, user_data):
        """ Gdk window destroyed """
        self.update_unrealized_options()

    def _cb_map_event(self, user_data):
        pass

    def _cb_unmap_event(self, user_data):
        # Turn off struts in case this unmap is in response to
        # changes in window options, force-to-top in particular.
        if config.is_docking_enabled():
            self._set_docking_struts(False)

    def update_unrealized_options(self):
        if not config.xid_mode:   # not when embedding
            self.set_decorated(config.window.window_decoration)
            self.set_type_hint(self._wm_quirks.get_window_type_hint(self))

    def update_window_options(self, startup = False):
        if not config.xid_mode:   # not when embedding

            recreate = False

            # Window decoration?
            decorated = config.window.window_decoration
            if decorated != self.get_decorated():
                recreate = True

            # force_to_top?
            force_to_top = config.window.force_to_top
            if force_to_top != self._force_to_top:
                recreate = True

            # (re-)create the gdk window?
            if recreate:

                visible = None
                if self.get_realized(): # not starting up?
                    visible = self.is_visible()
                    self.hide()
                    self.unrealize()

                self.realize()

                if not visible is None:
                    Gtk.Window.set_visible(self, visible)

            # Show the resize gripper?
            if config.has_window_decoration():
                self.set_has_resize_grip(self._default_resize_grip)
            else:
                self.set_has_resize_grip(False)

            self.update_sticky_state()

    def update_sticky_state(self):
        if not config.xid_mode:
            # Always on visible workspace?
            sticky = config.get_sticky_state()
            if self._sticky != sticky:
                self._sticky = sticky
                if sticky:
                    self.stick()
                else:
                    self.unstick()

            if self.icp:
                self.icp.update_sticky_state()

    def update_taskbar_hint(self):
        self._wm_quirks.update_taskbar_hint(self)

    def is_visible(self):
        if not self.get_mapped():
            return False
        return self._visible

    def set_visible(self, visible):
        # Lazily show the window for smooth startup,
        # in particular with force-to-top mode enabled.
        if not self.get_realized():
            self._init_window()

        # Make sure the move button stays visible
        # Do this on hiding the window, because the window position
        # is unreliable when unhiding.
        if not visible and \
           self.can_move_into_view():
            self.move_home_rect_into_view()

        self._wm_quirks.set_visible(self, visible)
        self.on_visibility_changed(visible)

    def on_visibility_changed(self, visible):

        self._visible = visible

        # untity starts onboard before the desktops
        # workarea has settled, rest it here on hiding,
        # as we know our struts are gone at this point.
        if not visible:
            self._monitor_workarea = {}

        if visible:
            self.set_icp_visible(False)
            self.update_sticky_state()
        else:
            # show the icon palette
            if config.is_icon_palette_in_use():
                self.set_icp_visible(True)

        # update indicator menu for unity and unity2d
        # not necessary but doesn't hurt in gnome-shell, gnome classic
        if self.application:
            status_icon = self.application.status_icon
            if status_icon:
                status_icon.update_menu_items()

            service = self.application.service_keyboard
            if service:
                service.PropertiesChanged(service.IFACE,
                                          {'Visible': visible}, ['Visible'])

    def set_opacity(self, opacity, force_set = False):
        # Only set the opacity on visible windows.
        # Metacity with compositing shows an unresponsive
        # ghost of the window when trying to set opacity
        # while it's hidden (LP: #929513).
        _logger.debug("setting opacity to {}, force_set={}, "
                      "visible={}" \
                      .format(opacity, force_set, self.is_visible()))
        if force_set:
            Gtk.Window.set_opacity(self, opacity)
        else:
            if self.is_visible():
                Gtk.Window.set_opacity(self, opacity)
            self._opacity = opacity

    def get_opacity(self):
        return self._opacity

    def is_maximized(self):
        return self._maximized

    def is_iconified(self):
        # Force-to-top windows are ignored by the window manager
        # and cannot be in iconified state.
        if config.window.force_to_top:
            return False

        return self._iconified

    def set_icp_visible(self, visible):
        """ Show/hide the icon palette """
        if self.icp:
            if visible:
                self.icp.show()
            else:
                self.icp.hide()

    def _cb_visibility_notify(self, widget, event):
        """
        Metacity with compositing sometimes ignores set_opacity()
        immediately after unhiding. Set it here to be sure it sticks.
        """
        if event.state != Gdk.VisibilityState.FULLY_OBSCURED:
            self.set_opacity(self._opacity)

    def _cb_window_state_event(self, widget, event):
        """
        This is the callback that gets executed when the user hides the
        onscreen keyboard by using the minimize button in the decoration
        of the window.
        Fails to be called when iconifying in gnome-shell (Oneiric).
        Fails to be called when iconifying in unity (Precise).
        Still keep it around for sticky changes.
        """
        _logger.debug("window_state_event: {}, {}" \
                      .format(event.changed_mask, event.new_window_state))

        if event.changed_mask & Gdk.WindowState.MAXIMIZED:
            self._maximized = bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)

        if event.changed_mask & Gdk.WindowState.ICONIFIED:
            self._iconified = bool(event.new_window_state & Gdk.WindowState.ICONIFIED)
            self._on_iconification_state_changed(self._iconified)

        if event.changed_mask & Gdk.WindowState.STICKY:
            self._sticky = bool(event.new_window_state & Gdk.WindowState.STICKY)

    def _on_iconification_state_changed(self, iconified):
            visible = not iconified
            was_visible = self.is_visible()

            self.on_visibility_changed(visible)

            # Cancel visibility transitions still in progress
            self.keyboard_widget.transition_visible_to(visible, 0.0)

            if was_visible != visible:
                if visible:
                    # Hiding may have left the window opacity at 0.
                    # Ramp up the opacity when unminimized by
                    # clicking the (unity) launcher.
                    self.keyboard_widget.update_transparency()

                # - Unminimizing from unity-2d launcher is a user
                #   triggered unhide -> lock auto-show visible.
                # - Minimizing while locked visible -> unlock
                self.keyboard_widget.lock_auto_show_visible(visible)

            return

    def on_transition_done(self, visible_before, visible_now):
        pass

    def set_keyboard_widget(self, keyboard_widget):
        _logger.debug("Entered in set_keyboard")
        self.keyboard_widget = keyboard_widget
        self.add(self.keyboard_widget)
        self.check_alpha_support()

        if self.icp:
            self.icp.set_layout_view(keyboard_widget)

    def do_set_gravity(self, edgeGravity):
        '''
        This will place the window on the edge corresponding to the edge gravity
        '''
        _logger.debug("Entered in do_set_gravity")
        self.edgeGravity = edgeGravity
        width, height = self.get_size()

        geom = self.get_screen().get_monitor_geometry(0)
        eg = self.edgeGravity

        x = 0
        y = 0
        if eg == Gdk.Gravity.SOUTH:
            y = geom.height - height
            y += 29 #to account for panel.

        self.move(x, y)

        GObject.idle_add(self.do_set_strut)

    def do_set_strut(self):
        _logger.debug("Entered in do_set_strut")
        propvals = [0,0,0,0,0,0,0,0,0,0,0,0]
        """propvals = [0,#left
                0, #right
                0, #top
                300,#bottom
                0,#left_start_y
                0,#left_end_y
                0,#right_start_y
                0,#right_end_y
                0,#top_start_x
                0,#top_end_x
                0,#bottom_start_x
                3000]#bottom_end_x"""

        screen = self.get_screen()
        biggestHeight = 0
        for n in range(screen.get_n_monitors()):
            tempHeight = screen.get_monitor_geometry(n).height
            if biggestHeight < tempHeight:
                biggestHeight = tempHeight

        geom = self.get_screen().get_monitor_geometry(0)
        eg = self.edgeGravity
        x, y = self.window.get_origin()

        width,height = self.get_size()

        if eg == Gdk.Gravity.NORTH:
            propvals[2] = height + y
            propvals[9] = width
        elif eg == Gdk.Gravity.SOUTH and y != 0:
            #propvals[2] = y
            #propvals[9] = geom.width - 1
            propvals[3] = biggestHeight - y
            propvals[11] = width - 1

            # tell window manager to not overlap buttons with maximized window
            self.window.property_change("_NET_WM_STRUT_PARTIAL",
                                        "CARDINAL",
                                        32,
                                        Gdk.PropMode.REPLACE,
                                        propvals)
        self.queue_resize_no_redraw()

    def can_move_into_view(self):
        return not config.xid_mode and \
           not config.has_window_decoration() and \
           not config.is_docking_enabled() and \
           bool(self.keyboard_widget)


class KbdWindow(KbdWindowBase, WindowRectTracker, Gtk.Window):

    # Minimum window size (for resizing in system mode, see handle_motion())
    MINIMUM_SIZE = 20

    home_rect = None

    def __init__(self):
        self._last_ignore_configure_time = None
        self._last_configures = []

        Gtk.Window.__init__(self,
                            urgency_hint = False,
                            width_request=self.MINIMUM_SIZE,
                            height_request=self.MINIMUM_SIZE)
        WindowRectTracker.__init__(self)

        GObject.signal_new("quit-onboard", KbdWindow,
                           GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_BOOLEAN, ())

        KbdWindowBase.__init__(self)

        self.restore_window_rect(startup = True)

        self.connect("delete-event", self._on_delete_event)
        self.connect("configure-event", self._on_configure_event)
        # Connect_after seems broken in Quantal, the callback is never called.
        #self.connect_after("configure-event", self._on_configure_event_after)

        once = CallOnce(100).enqueue  # call at most once per 100ms
        rect_changed = lambda x: once(self._on_config_rect_changed)
        config.window.position_notify_add(rect_changed)
        config.window.size_notify_add(rect_changed)

    def cleanup(self):
        WindowRectTracker.cleanup(self)
        KbdWindowBase.cleanup(self)
        if self.icp:
            self.icp.cleanup()
            self.icp.destroy()
            self.icp = None

    def on_visibility_changed(self, visible):
        if not self._visible and visible and \
           not config.is_docking_enabled() and \
           not config.xid_mode:
            self.move_resize(*self.get_current_rect()) # sync position

        KbdWindowBase.on_visibility_changed(self, visible)

    def _on_config_rect_changed(self):
        """ Gsettings position or size changed """
        if not config.xid_mode and \
           not config.is_docking_enabled():
            orientation = self.get_screen_orientation()
            rect = self.read_window_rect(orientation)

            # Only apply the new rect if it isn't the one we just wrote to
            # gsettings. Someone has to have manually changed the values
            # in gsettings to allow moving the window.
            rects = list(self._written_window_rects.values())
            if not any(rect == r for r in rects):
                self.restore_window_rect()

    def on_user_positioning_begin(self):
        self.stop_save_position_timer()
        self.keyboard_widget.freeze_auto_show()

    def on_user_positioning_done(self):
        self.update_window_rect()

        #self.detect_docking()
        if config.is_docking_enabled():
            self.write_docking_size(self.get_size())
            self.update_docking()
        else:
            self.update_home_rect()

        # Thaw auto show after a short delay to stop the window
        # from hiding due to spurios focus events after a system resize.
        self.keyboard_widget.thaw_auto_show(1.0)

    def detect_docking(self):
        if self.keyboard_widget.was_moving():
            config.window.docking_enabled = False

    def _on_configure_event(self, widget, event):
        self.update_window_rect()

        if not config.is_docking_enabled():
            # Connect_after seems broken in Quantal, but we still need to
            # get in after the default configure handler is done. Try to run
            # _on_configure_event_after in an idle handler instead.
            GObject.idle_add(self._on_configure_event_after, widget, event.copy())

    def _on_configure_event_after(self, widget, event):
        """
        Run this after KeyboardWidget's configure handler.
        After resizing Keyboard.update_layout() has to be called before
        limit_position() or the window jumps when it was close
        to the opposite screen edge of the resize handle.
        """
        # Configure event due to user positioning?
        result = self._filter_configure_event(self._window_rect)
        if result == 0:
            self.update_home_rect()

    def _filter_configure_event(self, rect):
        """
        Returns 0 for detected user positioning/sizing.
        Multiple defenses against false positives, i.e.
        window movement by autoshow, screen rotation, whathaveyou.
        """

        # There is no user positioning in xembed mode.
        if config.xid_mode:
            return -1

        # There is no system provided way to move/resize in
        # force-to-top mode. Solely rely on on_user_positioning_done().
        if config.window.force_to_top:
            return -2

        # There is no user positioning for invisible windows.
        if not self.is_visible():
            return -3

        # There is no user positioning for iconified windows.
        if self.is_iconified():
            return -4

        # There is no user positioning for maximized windows.
        if self.is_maximized():
            return -5

        # Remember past n configure events.
        now = time.time()
        max_events = 4
        self._last_configures = self._last_configures[-(max_events - 1):]

        # Same rect as before?
        if len(self._last_configures) and \
           self._last_configures[-1][0] == rect:
            return 1

        self._last_configures.append([rect, now])

        # Only just started?
        if len(self._last_configures) < max_events:
            return 2

        # Did we just move the window by auto-show?
        if not self._last_ignore_configure_time is None and \
           time.time() - self._last_ignore_configure_time < 0.5:
            return 3

        # Is the new window rect one of our known ones?
        if self.is_known_rect(self._window_rect):
            return 4

        # Dragging the decorated frame doesn't produce continous
        # configure-events anymore as in Oneriric (Precise).
        # Disable all affected checks based on this.
        # The home rect will probably get lost occasionally.
        if not config.has_window_decoration():

            # Less than n configure events in the last x seconds?
            first = self._last_configures[0]
            intervall = now - first[1]
            if intervall > 1.0:
                return 5

            # Is there a jump > threshold in past positions?
            r0 = self._last_configures[-1][0]
            r1 = self._last_configures[-2][0]
            dx = r1.x - r0.x
            dy = r1.y - r0.y
            d = sqrt(dx * dx + dy * dy)
            if d > 50:
                self._last_configures = [] # restart
                return 6

        return 0

    def ignore_configure_events(self):
        self._last_ignore_configure_time = time.time()

    def remember_rect(self, rect):
        """
        Remember the last 3 rectangles of auto-show repositioning.
        Time and order of configure events is somewhat unpredictable,
        so don't rely only on a single remembered rect.
        """
        self._known_window_rects = self._known_window_rects[-2:]
        self._known_window_rects.append(rect)

    def get_known_rects(self):
        """
        Return all rects that may have resulted from internal
        window moves, not from user controlled drag operations.
        """
        rects = self._known_window_rects

        co = config.window.landscape
        rects.append(Rect(co.x, co.y, co.width, co.height))

        co = config.window.portrait
        rects.append(Rect(co.x, co.y, co.width, co.height))

        rects.append(self.home_rect)
        return rects

    def is_known_rect(self, rect):
        """
        The home rect should be updated in response to user positiong/resizing.
        However we are unable to detect the end of window movement/resizing
        when window decoration is enabled. Instead we check if the current
        window rect is different from the ones auto-show knows and assume
        the user has changed it in this case.
        """
        return any(rect == r for r in self.get_known_rects())

    def move_home_rect_into_view(self):
        """
        Make sure the home rect is valid, move it if necessary.
        This function may be called even if the window is invisible.
        """
        rect = self._window_rect.copy()
        x, y = rect.x, rect.y
        _x, _y = self.keyboard_widget.limit_position(x, y)
        if _x != x or _y != y:
            self.update_home_rect()

    def update_home_rect(self):
        if config.is_docking_enabled():
            return

        # update home rect
        rect = self._window_rect.copy()

        # Make sure the move button stays visible
        if self.can_move_into_view():
            rect.x, rect.y = self.keyboard_widget.limit_position(rect.x, rect.y)

        self.home_rect = rect.copy()
        self.start_save_position_timer()

    def get_current_rect(self):
        """
        Returns the window rect with auto-show
        repositioning taken into account.
        """
        if self.keyboard_widget and \
           config.is_auto_show_enabled():
            rect = self.keyboard_widget.auto_show \
                       .get_repositioned_window_rect(self.home_rect)
            if rect:
                return rect
        return self.home_rect

    def on_restore_window_rect(self, rect):
        """
        Overload for WindowRectTracker.
        """
        if config.is_docking_enabled():
            if self.is_visible():
                rect = self.get_docking_rect()
            else:
                rect = self.get_docking_hideout_rect()
        else:
            self.home_rect = rect.copy()

            # check for alternative auto-show position
            r = self.get_current_rect()
            if r != self.home_rect:
                # remember our rects to distinguish from user move/resize
                self.remember_rect(r)
                rect = r

        return rect

    def on_save_window_rect(self, rect):
        """
        Overload for WindowRectTracker.
        """
        # Ignore <rect> (self._window_rect), it may just be a temporary one
        # set by auto-show. Save the user selected home_rect instead.
        return self.home_rect

    def read_window_rect(self, orientation):
        """
        Read orientation dependent rect.
        Overload for WindowRectTracker.
        """
        if orientation == Orientation.LANDSCAPE:
            co = config.window.landscape
        else:
            co = config.window.portrait
        rect = Rect(co.x, co.y, co.width, co.height)
        return rect

    def write_window_rect(self, orientation, rect):
        """
        Write orientation dependent rect.
        Overload for WindowRectTracker.
        """
        # There are separate rects for normal and rotated screen (tablets).
        if orientation == Orientation.LANDSCAPE:
            co = config.window.landscape
        else:
            co = config.window.portrait

        # remember that we wrote this rect to gsettings
        self._written_window_rects[orientation] = rect.copy()

        # write to gsettings and trigger notifications
        co.settings.delay()
        co.x, co.y, co.width, co.height = rect
        co.settings.apply()

    def get_orientation_config_object(self):
        orientation = self.get_screen_orientation()
        if orientation == Orientation.LANDSCAPE:
            co = config.window.landscape
        else:
            co = config.window.portrait
        return co

    def write_docking_size(self, size):
        co = self.get_orientation_config_object()
        expand = self.get_docking_expand()

        # write to gsettings and trigger notifications
        co.settings.delay()
        if not expand:
            co.dock_width = size[0]
        co.dock_height = size[1]
        co.settings.apply()

    def on_transition_done(self, visible_before, visible_now):
        if visible_now:
            self.update_docking()

    def on_screen_size_changed(self, screen):
        """ Screen rotation, etc. """
        if config.is_docking_enabled():
            # Can't correctly position the window while struts are active
            # -> turn them off for a moment
            self._set_docking_struts(False)
            keyboard_widget = self.keyboard_widget
            self._was_visible = self.is_visible()
            if keyboard_widget:
                keyboard_widget.transition_visible_to(False, 0.0)
                keyboard_widget.commit_transition()

        WindowRectTracker.on_screen_size_changed(self, screen)

    def on_screen_size_changed_delayed(self, screen):
        if config.is_docking_enabled():
            self._monitor_workarea = {}

            # The keyboard size may have changed, draw with the new size now,
            # while it's still in the hideout, so we don't have to watch.
            self.restore_window_rect()
            self.keyboard_widget.process_updates()

            keyboard = self.keyboard_widget
            if keyboard and self._was_visible:
                keyboard.transition_visible_to(True, 0.0, 0.4)
                keyboard.commit_transition()
        else:
            self.restore_window_rect()

    def limit_size(self, rect):
        """
        Limits the given window rect to fit on screen.
        """
        if self.keyboard_widget:
            return self.keyboard_widget.limit_size(rect)
        return rect

    def _emit_quit_onboard(self, event, data=None):
        self.emit("quit-onboard")

    def _on_delete_event(self, event, data=None):
        if config.lockdown.disable_quit:
            if self.keyboard_widget:
                return True
        else:
            self._emit_quit_onboard(event)

    def update_docking(self, force_update = False):
        enable = config.is_docking_enabled()
        rect   = self.get_docking_rect()

        if self._docking_enabled != enable or \
           (self._docking_enabled and \
            self._docking_rect != rect
           ):
            self.enable_docking(enable)

    def enable_docking(self, enable):
        #print("enable_docking", enable)
        if enable:
            self._set_docking_struts(True,
                                     config.window.docking_edge)
            self.restore_window_rect() # knows about docking
        else:
            self.restore_window_rect()
            self._set_docking_struts(False)

    def _set_docking_struts(self, enable, edge = None):
        #print("_set_docking_struts", enable, edge, self.get_realized())
        if not self.get_realized():
            # no window, no xid
            return

        win = self.get_window()
        xid = win.get_xid()

        if not enable:
            self._docking_enabled = False
            self._docking_edge = edge
            self._docking_rect = Rect()
            self._osk_struts.clear(xid)
            return

        area, geom = self.get_docking_monitor_rects()

        rect = self.get_docking_rect()
        if edge: # Bottom
            top    = 0
            bottom = geom.h - area.bottom() + rect.h
        else:    # Top
            top    = area.top() + rect.h
            bottom = 0

        struts = [0, 0, top, bottom, 0, 0, 0, 0, 0, 0, 0,0]
        self._osk_struts.set(xid, struts)

        self._docking_enabled = True
        self._docking_edge = edge
        self._docking_rect = rect

    def get_docking_size(self):
        co = self.get_orientation_config_object()
        return co.dock_width, co.dock_height

    def get_docking_expand(self):
        co = self.get_orientation_config_object()
        return co.dock_width, co.dock_height

    def get_docking_rect(self):
        area, geom = self.get_docking_monitor_rects()
        edge = config.window.docking_edge

        width, height = self.get_docking_size()
        rect = Rect(area.x, 0, area.w, height)
        if edge: # Bottom
            rect.y = area.y + area.h - height
        else:    # Top
            rect.y = area.y

        expand = self.get_docking_size()
        if expand:
            rect.w = area.w
            rect.x = area.x
        else:
            rect.w = min(width, area.w)
            rect.x = rect.x + (area.w - rect.w) // 2
        return rect

    def get_docking_hideout_rect(self, reference_rect = None):
        area, geom = self.get_docking_monitor_rects()
        rect = self.get_docking_rect()
        hideout = rect

        mcx, mcy = geom.get_center()
        if reference_rect:
            cx, cy = reference_rect.get_center()
        else:
            cx, cy = rect.get_center()
        clearance = 10
        if cy > mcy:
            hideout.y = geom.bottom() + clearance  # below Bottom
        else:
            hideout.y = geom.top() - rect.h - clearance # above Top

        return hideout

    def get_docking_monitor_rects(self):
        screen = self.get_screen()
        mon = self.get_docking_monitor()

        area = self._monitor_workarea.get(mon)
        if area is None:
            # Save the workarea  in the beginning, so we don't
            # have to check if our strut is already installed.
            area = screen.get_monitor_workarea(mon)
            area = Rect(area.x, area.y, area.width, area.height)
            self._monitor_workarea[mon] = area

        geom = screen.get_monitor_geometry(mon)
        geom = Rect(geom.x, geom.y, geom.width, geom.height)

        return area, geom

    def get_docking_monitor(self):
        screen = self.get_screen()
        return screen.get_primary_monitor()


class KbdPlugWindow(KbdWindowBase, Gtk.Plug):
    def __init__(self):
        Gtk.Plug.__init__(self)

        KbdWindowBase.__init__(self)

    def toggle_visible(self):
        pass


class WMQuirksDefault:
    """ Miscellaneous window managers, no special quirks """
    wm = None

    @staticmethod
    def set_visible(window, visible):
        if window.is_iconified():
            if visible and \
               not config.xid_mode:
                window.deiconify()
                window.present()
        else:
            Gtk.Window.set_visible(window, visible)

    @staticmethod
    def update_taskbar_hint(window):
        window.set_skip_taskbar_hint(True)

    @staticmethod
    def get_window_type_hint(window):
        return Gdk.WindowTypeHint.NORMAL


class WMQuirksCompiz(WMQuirksDefault):
    """ Unity with Compiz """
    wm = "compiz"

    @staticmethod
    def get_window_type_hint(window):
        if config.window.force_to_top:
            # NORMAL keeps Onboard on top of fullscreen firefox (LP: 1035578)
            return Gdk.WindowTypeHint.NORMAL
        else:
            if config.is_docking_enabled():
                # repel unity MT touch handles
                return Gdk.WindowTypeHint.DOCK
            else:
                if config.window.window_decoration:
                    # Keep showing the minimize button
                    return Gdk.WindowTypeHint.NORMAL
                else:
                    # don't get resized by compiz's grid plugin (LP: 893644)
                    return Gdk.WindowTypeHint.UTILITY


class WMQuirksMutter(WMQuirksDefault):
    """ Gnome-shell """

    wm = "mutter"

    @staticmethod
    def set_visible(window, visible):
        if window.is_iconified() and visible:
            # When minimized, Mutter doesn't react when asked to
            # remove WM_STATE_HIDDEN. Once the window was minimized
            # by title bar button it cannot be unhidden by auto-show.
            # The only workaround I found is re-mapping it (Precise).
            window.unmap()
            window.map()

        WMQuirksDefault.set_visible(window, visible)


class WMQuirksMetacity(WMQuirksDefault):
    """ Unity-2d, Gnome Classic """

    wm = "metacity"

    @staticmethod
    def set_visible(window, visible):
        # Metacity is good at iconifying. Take advantage of that
        # and get onboard minimized to the task list when possible.
        if not config.xid_mode and \
           not config.window.force_to_top and \
           not config.has_unhide_option():
            if visible:
                window.deiconify()
                window.present()
            else:
                window.iconify()
        else:
            WMQuirksDefault.set_visible(window, visible)

    @staticmethod
    def update_taskbar_hint(window):
        window.set_skip_taskbar_hint(config.xid_mode or \
                                     config.window.force_to_top or \
                                     config.has_unhide_option())

