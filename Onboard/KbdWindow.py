# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import cairo
from gi.repository import GObject, GdkX11, Gdk, Gtk, Wnck

from Onboard.utils       import Rect, Timer, CallOnce
from Onboard.WindowUtils import Orientation, WindowRectTracker
from Onboard.IconPalette import IconPalette

from gettext import gettext as _

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
    keyboard = None

    def __init__(self):
        _logger.debug("Entered in __init__")

        self.application = None
        self.supports_alpha = False

        self._visible = False
        self._sticky = False
        self._default_resize_grip = self.get_has_resize_grip()

        self.known_window_rects = []

        self.set_accept_focus(False)
        self.set_app_paintable(True)
        self.set_keep_above(True)
        #Gtk.Settings.get_default().set_property("gtk-touchscreen-mode", True)

        Gtk.Window.set_default_icon_name("onboard")
        self.set_title(_("Onboard"))

        self.connect("window-state-event", self._cb_window_state_event)
        self.connect('screen-changed', self._cb_screen_changed)
        self.connect('composited-changed', self._cb_composited_changed)

        self.check_alpha_support()

        self.realize()
        self.update_window_options() # for set_type_hint, set_decorated
        self.show_all()              # show early for wnck
        self.update_window_options() # for set_override_redirect

        self._wnck_window = None

        GObject.idle_add(self._init_wnck)

        _logger.debug("Leaving __init__")

    def _init_wnck(self):
        """
        Find onboard's wnck window and listen on it for minimize events.
        Gtk3 window-state-event fails to notify about this (Precise).
        """
        if not self._wnck_window:
            screen = Wnck.Screen.get_default()
            screen.force_update()

            win = self.get_window()
            xid = win.get_xid() if win else None

            self._wnck_window = Wnck.Window.get(xid) if xid else None
            _logger.debug("Found wnck window {xid}, {wnck_window}" \
                          .format(xid = xid, wnck_window = self._wnck_window))
            if not self._wnck_window:
                _logger.warning("Wnck window for xid {xid} not found".format(xid = xid))

            if self._wnck_window:
                self._wnck_window.connect("state-changed", self._cb_wnck_state_changed)

    def cleanup(self):
        pass

    def _cb_screen_changed(self, widget, old_screen=None):
        self.check_alpha_support()
        self.queue_draw()

    def _cb_composited_changed(self, widget):
        self.check_alpha_support()
        self.queue_draw()

    def check_alpha_support(self):
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        self.supports_alpha = visual and screen.is_composited()

        _logger.debug(_("screen changed, supports_alpha={}") \
                       .format(self.supports_alpha))

        # Unity may start onboard early, where there is no compositing
        # enabled yet. If we set the visual later the window never becomes
        # transparent -> do it as soon as there is an rgba visual.
        if visual:
            self.set_visual(visual)
            if self.keyboard:
                self.keyboard.set_visual(visual)

            # full transparency for the window background
            self.override_background_color(Gtk.StateFlags.NORMAL,
                                           Gdk.RGBA(0, 0, 0, 0))
            if self.keyboard:
                self.keyboard.override_background_color(Gtk.StateFlags.NORMAL,
                                           Gdk.RGBA(0, 0, 0, 0))
        else:
            _logger.info(_("no window transparency available;"
                           " screen doesn't support alpha channels"))
        return False

    def update_window_options(self):
        if not config.xid_mode:   # not when embedding

            # Window decoration?
            decorated = config.window.window_decoration
            if decorated != self.get_decorated():
                self.set_decorated(decorated)

            # Disable maximize function (LP #859288)
            # unity:    no effect, but the bug doesn't occure here anyway
            # unity-2d: works and avoids the bug
            if self.get_window():
                self.get_window().set_functions(Gdk.WMFunction.RESIZE | \
                                                Gdk.WMFunction.MOVE | \
                                                Gdk.WMFunction.MINIMIZE | \
                                                Gdk.WMFunction.CLOSE)

            # Force to top?
            if config.window.force_to_top:
                if not self.get_mapped():
                   self.set_type_hint(Gdk.WindowTypeHint.DOCK)
                if self.get_window():
                    self.get_window().set_override_redirect(True)
            else:
                if not self.get_mapped():
                    self.set_type_hint(Gdk.WindowTypeHint.NORMAL)
                if self.get_window():
                    self.get_window().set_override_redirect(False)

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

    def is_visible(self):
        if not self.get_mapped():
            return False
        return self._visible

    def set_visible(self, visible):
        # Make sure the move button stays visible
        # Do this on hiding the window, because the window position
        # is unreliable when unhiding.
        if not visible and \
           self.can_move_into_view():
            self.keyboard.move_into_view()

        # Gnome-classic refuses to iconify override-redirect windows
        # Hide and show the window instead.
        # Unity and gnome-shell don't show launchers then anyway.
        if config.window.force_to_top:
            Gtk.Window.set_visible(self, visible)
        else:
            # unity: iconify keeps an icon the launcher when
            #        there is no status indicator
            if visible:
                self.deiconify()
            else:
                self.iconify()

        if visible:
            if not config.xid_mode:
                # Deiconify in unity, no use in gnome-shell
                # Not in xembed mode, it kills typing in lightdm.
                self.present()

        self.on_visibility_changed(visible)

    def on_visibility_changed(self, visible):
        self._visible = visible

        if visible:
            self.set_icp_visible(False)
            self.update_sticky_state()
            #self.move(config.x, config.y) # to be sure that the window manager places it correctly
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

    def set_icp_visible(self, visible):
        """ Show/hide the icon palette """
        if self.icp:
            if visible:
                self.icp.show()
            else:
                self.icp.hide()

    def _cb_window_state_event(self, widget, event):
        """
        This is the callback that gets executed when the user hides the
        onscreen keyboard by using the minimize button in the decoration
        of the window.
        Fails to be called when iconifying in gnome-shell (Oneiric).
        Fails to be called when iconifying in unity (Precise).
        Still keep it around for sticky changes.
        """
        if event.changed_mask & Gdk.WindowState.STICKY:
            self._sticky = bool(event.new_window_state & Gdk.WindowState.STICKY)

    def _cb_wnck_state_changed(self, wnck_window, changed_mask, new_state):
        """
        Wnck appears to be the only working way to get notified when
        the window is minimized/restored (Precise).
        """
        _logger.debug("wnck_state_changed: {}, {}, {}" \
                      .format(wnck_window, changed_mask, new_state))

        if changed_mask & Wnck.WindowState.MINIMIZED:
            visible = not bool(new_state & Wnck.WindowState.MINIMIZED)

            if self.is_visible() != visible:
                # Hiding may have left the window opacity at 0.
                # Ramp up the opacity when unminimized by
                # clicking the (unity) launcher.
                if visible:
                    self.keyboard.update_transparency()

                self.on_visibility_changed(visible)

    def set_keyboard(self, keyboard):
        _logger.debug("Entered in set_keyboard")
        if self.keyboard:
            self.remove(self.keyboard)
        self.keyboard = keyboard
        self.add(self.keyboard)
        self.check_alpha_support()
        self.keyboard.show()
        self.queue_draw()

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
           bool(self.keyboard)


class KbdWindow(KbdWindowBase, WindowRectTracker, Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self)
        WindowRectTracker.__init__(self)

        self.icp = IconPalette()
        self.icp.connect("activated", self._on_icon_palette_acticated)

        self.connect("delete-event", self._on_delete_event)
        self.connect("configure-event", self._on_configure_event)

        self.restore_window_rect()

        KbdWindowBase.__init__(self)

        once = CallOnce(100).enqueue  # call at most once per 100ms
        rect_changed = lambda x: once(self.on_config_rect_changed)
        config.window.position_notify_add(rect_changed)
        config.window.size_notify_add(rect_changed)

    def cleanup(self):
        WindowRectTracker.cleanup(self)
        if self.icp:
            self.icp.cleanup()

    def _on_icon_palette_acticated(self, widget):
        self.keyboard.toggle_visible()

    def _on_configure_event(self, widget, user_data):
        self.update_window_rect()

    def on_user_positioning_begin(self):
        self.stop_save_position_timer()

    def on_user_positioning_done(self):
        self.update_window_rect()

    def update_window_rect(self):
        WindowRectTracker.update_window_rect(self)

        if self.is_visible():

            # update home rect
            rect = self._window_rect.copy()
            if not self.is_known_rect(rect):

                # Make sure the move button stays visible
                if self.can_move_into_view():
                    rect.x, rect.y = self.keyboard.limit_position(rect.x, rect.y)

                self.home_rect = rect

    def on_config_rect_changed(self):
        """ Gsettings position or size changed """
        orientation = self.get_screen_orientation()
        rect = self.read_window_rect(orientation)

        # Only apply the new rect if it isn't the one we just wrote to
        # gesettings. Someone has to have manually changed the values
        # in gsettings to allow moving the window.
        if not self.is_known_rect(rect):
            self.restore_window_rect()

    def is_known_rect(self, rect):
        """
        The home rect should be updated in response to user positiong/resizing.
        However we are unable to detect the end of window movement/resizing
        when window decoration is enabled. Instead we check if the current
        window rect is different from the ones auto-show knows and assume
        the user has changed it in this case.
        """
        rects = [self.home_rect] + self.known_window_rects
        return not all(rect != r for r in rects)

    def on_restore_window_rect(self, rect):
        """
        Overload for WindowRectTracker.
        """
        self.home_rect = rect

        # check for alternative auto-show position
        if self.keyboard and \
           config.is_auto_show_enabled():
            r = self.keyboard.auto_show.get_repositioned_window_rect(rect)
            if r:
                # remember our rects to distinguish from user move/resize
                self.known_window_rects = [r]
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

        config.settings.delay()
        co.x, co.y, co.width, co.height = rect
        config.settings.apply()

    def _emit_quit_onboard(self, event, data=None):
        self.emit("quit-onboard")

    def _on_delete_event(self, event, data=None):
        if config.lockdown.disable_quit:
            if self.keyboard:
                return True
        else:
            self._emit_quit_onboard(event)


class KbdPlugWindow(KbdWindowBase, Gtk.Plug):
    def __init__(self):
        Gtk.Plug.__init__(self)

        self.icp = None

        KbdWindowBase.__init__(self)

    def toggle_visible(self):
        pass


# Do this only once, not in KbdWindow's constructor.
# The main window is recreated when the the "force_to_top"
# setting changes.
GObject.signal_new("quit-onboard", KbdWindow,
                   GObject.SIGNAL_RUN_LAST,
                   GObject.TYPE_BOOLEAN, ())


