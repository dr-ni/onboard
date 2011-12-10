
import cairo
from gi.repository       import GObject, Gdk, Gtk

from Onboard.IconPalette import IconPalette
from Onboard.utils import Rect

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

    def __init__(self):
        _logger.debug("Entered in __init__")

        self.application = None
        self.keyboard = None

        self.supports_alpha = False
        self._default_resize_grip = self.get_has_resize_grip()
        self._visibility_state = 0
        self._iconified = False
        self._sticky = False

        self.set_accept_focus(False)
        self.set_app_paintable(True)
        self.set_keep_above(True)
        #Gtk.Settings.get_default().set_property("gtk-touchscreen-mode", True)

        self.grab_remove()

        Gtk.Window.set_default_icon_name("onboard")
        self.set_title(_("Onboard"))

        config.geometry_notify_add(lambda x: self.resize(config.width, config.height))
        self.set_default_size(config.width, config.height)
        config.position_notify_add(lambda x: self.move(config.x, config.y))
        self.move(config.x, config.y)
        self.home_rect = Rect(config.x, config.y, config.width, config.height)

        self.connect("window-state-event", self.cb_window_state_event)
        self.connect("visibility-notify-event", self.cb_visibility_notify)
        self.connect('screen-changed', self._cb_screen_changed)
        self.connect('composited-changed', self._cb_composited_changed)

        self.check_alpha_support()

        self.update_window_options() # for set_type_hint, set_decorated
        self.show_all()
        self.update_window_options() # for set_override_redirect

        self.set_visible(config.is_visible_on_start())

        _logger.debug("Leaving __init__")

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
                    if config.window_decoration:
                        self.set_type_hint(Gdk.WindowTypeHint.NORMAL)
                    else:
                        # Stop grid plugin from resizing onboard and getting
                        # it stuck. Turns off the ability to maximize too.
                        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
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
        # via window decoration.
        return Gtk.Window.get_visible(self) and \
               not self._visibility_state & \
                                Gdk.VisibilityState.FULLY_OBSCURED and \
               not self._iconified

    def toggle_visible(self):
        self.set_visible(not self.is_visible())

    def set_visible(self, visible):
        # Make sure the move button is visible
        # Do this on hiding the window, because the window position
        # is unreliable when unhiding.
        if not visible and \
           self.can_move_into_view():
            self.keyboard.move_into_view()

        # Gnome-shell in Oneiric doesn't send window-state-event when
        # iconifying. Hide and show the window instead.
        Gtk.Window.set_visible(self, visible)
        if visible:
            if not config.xid_mode:
                # Deiconify in unity, no use in gnome-shell
                # Not in xembed mode, it kills typing in lightdm.
                self.present()

        self.on_visibility_changed(visible)

    def on_visibility_changed(self, visible):
        if visible:
            self.set_icp_visible(False)
            self.update_sticky_state()
            #self.move(config.x, config.y) # to be sure that the window manager places it correctly
        else:
            # show the icon palette
            if config.icp.in_use:
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

    def cb_visibility_notify(self, widget, event):
        """
        Don't rely on window state events only. Gnome-shell doesn't 
        send them when minimizing.
        """
        _logger.debug("Entered in cb_visibility_notify")
        self._visibility_state = event.state
        self.on_visibility_changed(self.is_visible())

    def cb_window_state_event(self, widget, event):
        """
        This is the callback that gets executed when the user hides the
        onscreen keyboard by using the minimize button in the decoration
        of the window.
        """
        _logger.debug("Entered in cb_window_state_event")
        if event.changed_mask & Gdk.WindowState.ICONIFIED:
            if event.new_window_state & Gdk.WindowState.ICONIFIED:
                self._iconified = True
            else:
                self._iconified = False
            self.on_visibility_changed(self.is_visible())

        if event.changed_mask & Gdk.WindowState.STICKY:
            self._sticky = bool(event.new_window_state & Gdk.WindowState.STICKY)
            
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

    def on_user_positioning_done(self):
        self.home_rect = \
            Rect.from_position_size(self.get_position(),
                                    self.get_size())


class KbdWindow(KbdWindowBase, Gtk.Window):
    def __init__(self):
        self._position = None
        self._origin = None

        Gtk.Window.__init__(self)

        self.icp = IconPalette()
        self.icp.connect("activated", self.cb_icon_palette_acticated)

        self.connect("delete-event", self._on_delete_event)
        self.connect("configure-event", self._on_configure_event)

        KbdWindowBase.__init__(self)

    def cb_icon_palette_acticated(self, widget):
        self.keyboard.toggle_visible()

    def _on_configure_event(self, widget, user_data):
        self.update_position()

    def move(self, x, y):
        Gtk.Window.move(self, x, y)
        if self.is_visible():
            self._position = x, y
            self._origon = self.get_window().get_origin()

    def get_position(self):
        if self._position:
            return self._position
        else:
            return Gtk.Window.get_position(self)

    def get_origin(self):
        if self._origin:
            return self._origin
        else:
            return self.get_window().get_origin()

    def update_position(self, position = None):
        if self.is_visible():
            self._position = Gtk.Window.get_position(self)
            self._origin = self.get_window().get_origin()

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
        config.x = x
        config.y = y
        config.width = width
        config.height = height

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


