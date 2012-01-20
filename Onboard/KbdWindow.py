# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import cairo
from gi.repository import GObject, GdkX11, Gdk, Gtk, Wnck

from Onboard.IconPalette import IconPalette
from Onboard.utils import Rect, Timer, CallOnce

from gettext import gettext as _

### Logging ###
import logging
_logger = logging.getLogger("KbdWindow")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################


class SavePositionTimer(Timer):
    """ Saving size and position a few seconds delayed. """

    def __init__(self, keyboard):
        self._keyboard = keyboard

    def start(self):
        Timer.start(self, 5)

    def on_timer(self):
        self._keyboard.save_size_and_position()
        return False


class KbdWindowBase:
    """
    Very messy class holds the keyboard widget. The mess is the docked
    window support which is disable because of numerous metacity bugs.
    """

    def __init__(self):
        _logger.debug("Entered in __init__")

        self.application = None
        self.keyboard = None

        self.supports_alpha = False
        self._default_resize_grip = self.get_has_resize_grip()
        self._visible = False
        self._sticky = False
        self._save_position_timer = SavePositionTimer(self)

        self.known_window_rects = []

        self.set_accept_focus(False)
        self.set_app_paintable(True)
        self.set_keep_above(True)
        #Gtk.Settings.get_default().set_property("gtk-touchscreen-mode", True)

        self.grab_remove()

        Gtk.Window.set_default_icon_name("onboard")
        self.set_title(_("Onboard"))

        self.set_default_size(config.width, config.height)
        self.move(config.x, config.y)
        self.home_rect = Rect(config.x, config.y, config.width, config.height)

        self.connect("window-state-event", self.cb_window_state_event)
        self.connect('screen-changed', self._cb_screen_changed)
        self.connect('composited-changed', self._cb_composited_changed)

        self.check_alpha_support()

        self.update_window_options() # for set_type_hint, set_decorated
        self.show_all()
        self.update_window_options() # for set_override_redirect

        self._wnck_window = None

        # show the main window
        #self.set_visible(config.is_visible_on_start())

        GObject.idle_add(self.init_wnck)

        _logger.debug("Leaving __init__")

    def init_wnck(self):
        screen = Wnck.Screen.get_default()
        screen.force_update()
        win = self.get_window()
        xid = win.get_xid() if win else None
        self._wnck_window = Wnck.Window.get(xid) if xid else None
        _logger.debug("Found wnck window {xid}, {wnck_window}" \
                      .format(xid = xid, wnck_window = self._wnck_window))

        if self._wnck_window:
            self._wnck_window.connect("state-changed", self.cb_wnck_state_changed)

    def cleanup(self):
        self._save_position_timer.stop()

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
            decorated = config.window_decoration
            if decorated != self.get_decorated():
                self.set_decorated(decorated),

            # Force to top?
            if config.force_to_top:
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
        # Make sure the move button is visible
        # Do this on hiding the window, because the window position
        # is unreliable when unhiding.
        if not visible and \
           self.can_move_into_view():
            self.keyboard.move_into_view()

        # Gnome-classic refuses to iconify override-redirect windows
        # Hide and show the window instead.
        # Unity and gnome-shell don't show launchers then anyway.
        if config.force_to_top:
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

    def cb_window_state_event(self, widget, event):
        """
        This is the callback that gets executed when the user hides the
        onscreen keyboard by using the minimize button in the decoration
        of the window.
        Fails to be called when iconifying in gnome-shell, Oneiric.
        Fails to be called when iconifying in unity (Precise).
        Still keep it around for sticky changes.
        """
        _logger.debug("Entered in cb_window_state_event")

        if event.changed_mask & Gdk.WindowState.STICKY:
            self._sticky = bool(event.new_window_state & Gdk.WindowState.STICKY)

    def cb_wnck_state_changed(self, wnck_window, changed_mask, new_state):
        """
        Wnck appears to be the only working way to get notified when
        the window is minimized/restored (Precise).
        """
        _logger.debug("wnck_state_changed", wnck_window, changed_mask, new_state)

        if changed_mask & Wnck.WindowState.MINIMIZED:
            if new_state & Wnck.WindowState.MINIMIZED:
                visible = False
            else:
                visible = True

                # Ramp up the window opacity when unminimized by
                # pressing the (unity) launcher.
                self.keyboard.set_visible(True)

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

class WindowRectTracker:
    """
    Keeps track of the window rectangle when moving/resizing.
    Gtk only updates the position and size asynchrounously on
    configure events. We need valid values for get_position
    and get_size at all times.
    """

    def __init__(self):
        self._position = None
        self._size = None
        self._origin = None

    def move(self, x, y):
        """
        Overload Gtk.Window.move to reliably keep track of
        the window position.
        """
        Gtk.Window.move(self, x, y)
        if self.is_visible():
            self._position = x, y
            self._origin = self.get_window().get_origin()

    def move_resize(self, x, y, w, h):
        win = self.get_window()
        if win:
            win.move_resize(x, y, w, h)
            if self.is_visible():
                self._position = x, y
                self._size = w, h
                self._origin = win.get_origin()

    def get_position(self):
        if self._position is None:
            return Gtk.Window.get_position(self)
        else:
            return self._position

    def get_size(self):
        if self._size is None:
            return Gtk.Window.get_size(self)
        else:
            return self._size

    def get_origin(self):
        if self._origin is None:
            return self.get_window().get_origin()
        else:
            return self._origin

    def update_position(self, position = None):
        if self.is_visible():
            self._position = Gtk.Window.get_position(self)
            self._size     = Gtk.Window.get_size(self)
            self._origin   = self.get_window().get_origin()


class KbdWindow(KbdWindowBase, WindowRectTracker, Gtk.Window):
    def __init__(self):
        WindowRectTracker.__init__(self)
        Gtk.Window.__init__(self)

        self.icp = IconPalette()
        self.icp.connect("activated", self._on_icon_palette_acticated)

        self.connect("delete-event", self._on_delete_event)
        self.connect("configure-event", self._on_configure_event)

        KbdWindowBase.__init__(self)

        once = CallOnce(100).enqueue  # delay callbacks
        rect_changed = lambda x: once(self.on_config_rect_changed)
        config.geometry_notify_add(rect_changed)
        config.position_notify_add(rect_changed)

    def _on_icon_palette_acticated(self, widget):
        self.keyboard.toggle_visible()

    def _on_configure_event(self, widget, user_data):
        self.update_position()

    def on_user_positioning_begin(self):
        self.stop_save_position_timer()

    def on_user_positioning_done(self):
        self.update_position()

    def update_position(self, position = None):
        WindowRectTracker.update_position(self)

        if self.is_visible():
            # update home rect
            rect = Rect.from_position_size(self.get_position(),
                                           self.get_size())
            if self.update_home_rect(rect):
                if self.keyboard.is_drag_initiated():
                    self.start_save_position_timer()

    def on_config_rect_changed(self):
        """ Gsettings position changed """
        rect = Rect(config.x, config.y, config.width, config.height)

        # Only apply the new rect if it isn't the one we just wrote to
        # gesettings. Someone has to have manually changed the values
        # in gsettings to allow moving the window.
        if self.update_home_rect(rect):
            self.move_resize(*rect)

    def update_home_rect(self, rect):
        """
        The home rect should be updated in response to user positiong/resizing.
        However we are unable to detect the end of window movement/resizing
        when window decoration is enabled. Instead we check if the current
        window rect is not one of the ones auto-show knows of and assume
        the user has changed it in this case.
        """
        rects = [self.home_rect] + self.known_window_rects
        if all(rect != r for r in rects):
            self.home_rect = rect
            return True
        return False

    def start_save_position_timer(self):
        """
        Trigger saving position and size to gsettings
        Delay this a few seconds to avoid excessive disk writes.
        """
        self._save_position_timer.start()

    def stop_save_position_timer(self):
        self._save_position_timer.stop()

    def save_size_and_position(self):
        """
        Save size and position into the corresponding gsettings keys.
        """
        _logger.debug("Entered in save_size_and_position")
        #x, y = self.get_position()
        #width, height = self.get_size()
        x, y, width, height = self.home_rect.to_list()

        # Make sure that the move button is visible on next start
        if self.can_move_into_view():
            x, y = self.keyboard.limit_position(x, y)

        # store new value only if it is different to avoid infinite loop
        config.settings.delay()
        config.x = x
        config.y = y
        config.width = width
        config.height = height
        config.settings.apply()

    def _emit_quit_onboard(self, event, data=None):
        self.emit("quit-onboard")

    def _on_delete_event(self, event, data=None):
        if config.lockdown.disable_quit:
            if self.keyboard:
                return True
                self.keyboard.set_visible(False)
        else:
            self._emit_quit_onboard(event)


class KbdPlugWindow(KbdWindowBase, Gtk.Plug):
    def __init__(self):
        Gtk.Plug.__init__(self)

        self.icp = None

        KbdWindowBase.__init__(self)

    def toggle_visible(self):
        pass

# Do this only once, not in KbdWindows constructor.
# The main window may be recreated when changing
# the "force_to_top" setting.
GObject.signal_new("quit-onboard", KbdWindow,
                   GObject.SIGNAL_RUN_LAST,
                   GObject.TYPE_BOOLEAN, ())


