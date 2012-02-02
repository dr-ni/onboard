# -*- coding: UTF-8 -*-

from __future__ import division, print_function, unicode_literals

### Logging ###
import logging
_logger = logging.getLogger("OnboardGtk")
###############

import sys
import time
import traceback
import signal
import gettext
import os.path
from gettext import gettext as _
import virtkey

from gi.repository import GObject, Gdk, Gtk


from Onboard.Indicator import Indicator

from Onboard.Keyboard import Keyboard
from Onboard.KeyGtk import *
from Onboard.KbdWindow import KbdWindow, KbdPlugWindow
from Onboard.KeyboardSVG import KeyboardSVG
from Onboard.utils       import show_confirmation_dialog, CallOnce, timeit
from Onboard.Appearance import Theme


### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

import Onboard.KeyCommon
import Onboard.utils as utils

#setup gettext
app="onboard"
gettext.textdomain(app)
gettext.bindtextdomain(app)

DEFAULT_FONTSIZE = 10

class OnboardGtk(object):
    """
    This class is a mishmash of things that I didn't have time to refactor in to seperate classes.
    It needs a lot of work.
    The name comes from onboards original working name of simple onscreen keyboard.
    """

    """ Window holding the keyboard widget """
    _window = None

    """ The keyboard widget """
    keyboard = None

    restart = False

    def __init__(self, main=True):
        sys.path.append(os.path.join(config.install_dir, 'scripts'))

        self.init()

        if main:
            # Release enter key when killing onboard by
            # pressing 'killall onboard' in the console.
            # -> Disabled: This gets onboard stuck on exit in
            # gnome-screensaver until the pointer moves over the keyboard.
            # May be a GTK bug, disabled for now (Oneiric).
            #signal.signal(signal.SIGTERM, self.on_signal)

            # exit on Ctrl+C
            # This almost works, but still requires a motion event
            # or somthing similar to actually quit.
            sys.excepthook = self.excepthook

            _logger.info("Entering mainloop of onboard")
            try:
                Gtk.main()
            except KeyboardInterrupt:
                self.do_quit_onboard()

    def excepthook(self, type, value, traceback):
        """
        Exit onboard on Ctrl+C press.
        """
        if type is KeyboardInterrupt:
            self.do_quit_onboard()
        else:
            sys.__excepthook__(type, value, traceback)

    def init(self):
        self.keyboard_state = None
        self.vk_timer = None
        self.reset_vk()
        self._connections = []
        self._window = None
        self.status_icon = None

        # load the initial layout
        _logger.info("Loading initial layout")
        self.reload_layout()

        # create the main window
        if config.xid_mode:    # XEmbed mode for gnome-screensaver?
            self._window = KbdPlugWindow()

            # write xid to stdout
            sys.stdout.write('%d\n' % self._window.get_id())
            sys.stdout.flush()
        else:
            self._window = KbdWindow()
            self.do_connect(self._window, "quit-onboard",
                            lambda x: self.do_quit_onboard())

        self._window.application = self
        self._window.set_keyboard(self.keyboard)

        # Handle command line options x, y, size after window creation
        # because the rotation code needs the window's screen.
        if not config.xid_mode:
            rect = self._window.get_rect().copy()
            options = config.options
            if options.size:
                size = options.size.split("x")
                rect.w = int(size[0])
                rect.h = int(size[1])
            if not options.x is None:
                rect.x = options.x
            if not options.y is None:
                rect.y = options.y

            if rect != self._window.get_rect():
                orientation = self._window.get_screen_orientation()
                self._window.write_window_rect(orientation, rect)
                self._window.restore_window_rect() # move/resize early

        # show/hide the window
        self.keyboard.set_startup_visibility()

        # connect notifications for keyboard map and group changes
        self.keymap = Gdk.Keymap.get_default()
        self.do_connect(self.keymap, "keys-changed", self.cb_keys_changed) # map changes
        Gdk.event_handler_set(cb_any_event, self)          # group changes

        # connect config notifications here to keep config from holding
        # references to keyboard objects.
        once = CallOnce(50).enqueue  # delay callbacks by 50ms
        reload_layout       = lambda x: once(self.reload_layout_and_present)
        update_ui           = lambda x: once(self.update_ui)
        redraw              = lambda x: once(self.keyboard.redraw)
        update_transparency = lambda x: once(self.keyboard.update_transparency)
        update_inactive_transparency = \
                              lambda x: once(self.keyboard.update_inactive_transparency)

        # general
        config.auto_show.enabled_notify_add(lambda x: \
                                    self.keyboard.update_auto_show())

        # window
        config.window.window_state_sticky_notify_add(lambda x: \
                                   self._window.update_sticky_state())
        config.window.window_decoration_notify_add(self._cb_recreate_window)
        config.window.force_to_top_notify_add(self._cb_recreate_window)
        config.window.keep_aspect_ratio_notify_add(update_ui)

        config.window.transparency_notify_add(update_transparency)
        config.window.background_transparency_notify_add(redraw)
        config.window.transparent_background_notify_add(update_ui)
        config.window.enable_inactive_transparency_notify_add(update_transparency)
        config.window.inactive_transparency_notify_add(update_inactive_transparency)

        # layout
        config.layout_filename_notify_add(reload_layout)

        # theme
        #config.gdi.gtk_theme_notify_add(self.on_gtk_theme_changed)
        config.theme_notify_add(self.on_theme_changed)
        config.key_label_font_notify_add(reload_layout)
        config.key_label_overrides_notify_add(reload_layout)
        config.theme_settings.color_scheme_filename_notify_add(reload_layout)
        config.theme_settings.key_label_font_notify_add(reload_layout)
        config.theme_settings.key_label_overrides_notify_add(reload_layout)
        config.theme_settings.key_size_notify_add(update_ui) # for label size
        config.theme_settings.theme_attributes_notify_add(redraw)

        # snippets
        config.snippets_notify_add(reload_layout)

        # universal access
        config.enable_scanning_notify_add(lambda x: \
                                     self.keyboard.reset_scan())
        config.window.resize_handles_notify_add(lambda x: \
                                    self.keyboard.update_resize_handles())

        # misc
        config.show_click_buttons_notify_add(update_ui)
        config.lockdown.lockdown_notify_add(update_ui)
        config.clickmapper.state_notify_add(update_ui)
        if config.mousetweaks:
            config.mousetweaks.state_notify_add(update_ui)

        # create status icon
        # Indicator is a singleton to allow recreating the keyboard
        # window on changes to the "force_to_top" setting.
        self.status_icon = Indicator()
        self.status_icon.set_keyboard_window(self._window)
        self.do_connect(self.status_icon, "quit-onboard",
                        lambda x: self.do_quit_onboard())

        # Callbacks to use when icp or status icon is toggled
        config.show_status_icon_notify_add(self.show_hide_status_icon)
        config.icp.in_use_notify_add(self.cb_icp_in_use_toggled)

        self.show_hide_status_icon(config.show_status_icon)


        # Minimize to IconPalette if running under GDM
        if 'RUNNING_UNDER_GDM' in os.environ:
            config.icp.in_use = True
            config.show_status_icon = False

        # unity-2d needs the skip-task-bar hint set before the first mapping.
        self.show_hide_taskbar()


        # Check gnome-screen-saver integration
        # onboard_xembed_enabled                False True     True      True
        # config.gss.embedded_keyboard_enabled  any   False    any       False
        # config.gss.embedded_keyboard_command  any   empty    !=onboard ==onboard
        # Action:                               nop   enable   Question1 Question2
        #                                             silently
        if not config.xid_mode and \
           config.onboard_xembed_enabled:

            # If it appears, that nothing has touched the gss keys before,
            # silently enable gss integration with onboard.
            if not config.gss.embedded_keyboard_enabled and \
               not config.gss.embedded_keyboard_command:
                config.enable_gss_embedding(True)

            # If onboard is configured to be embedded into the unlock screen
            # dialog, and the embedding command is different from onboard, ask
            # the user what to do
            elif not config.is_onboard_in_xembed_command_string():
                question = _("Onboard is configured to appear with the dialog to "
                             "unlock the screen; for example to dismiss the "
                             "password-protected screensaver.\n\n"
                             "However the system is not configured anymore to use "
                             "Onboard to unlock the screen. A possible reason can "
                             "be that another application configured the system to "
                             "use something else.\n\n"
                             "Would you like to reconfigure the system to show "
                             "Onboard when unlocking the screen?")
                reply = show_confirmation_dialog(question)
                if reply == True:
                    config.enable_gss_embedding(True)
                else:
                    config.onboard_xembed_enabled = False
            else:
                if not config.gss.embedded_keyboard_enabled:
                    question = _("Onboard is configured to appear with the dialog "
                                 "to unlock the screen; for example to dismiss "
                                 "the password-protected screensaver.\n\n"
                                 "However this function is disabled in the system.\n\n"
                                 "Would you like to activate it?")
                    reply = show_confirmation_dialog(question)
                    if reply == True:
                        config.enable_gss_embedding(True)
                    else:
                        config.onboard_xembed_enabled = False

        # check if gnome accessibility is enabled for auto-show
        if config.auto_show.enabled and \
            not config.check_gnome_accessibility(self._window):
            config.auto_show.enabled = False

    def do_connect(self, instance, signal, handler):
        handler_id = instance.connect(signal, handler)
        self._connections.append((instance, handler_id))

    def on_signal(self, signum, frame):
        if signum == signal.SIGTERM:
            _logger.debug("SIGTERM received")
            self.cleanup()
            sys.exit(1)

    # Method concerning the taskbar
    def show_hide_taskbar(self):
        """
        This method shows or hides the taskbard depending on whether there
        is an alternative way to unminimize the Onboard window.
        This method should be called every time such an alternative way
        is activated or deactivated.
        """
        if config.icp.in_use or \
           config.show_status_icon:
            self._window.set_property('skip-taskbar-hint', True)
        else:
            self._window.set_property('skip-taskbar-hint', False)


    # Method concerning the icon palette
    def cb_icp_in_use_toggled(self, icp_in_use):
        """
        This is the callback that gets executed when the user toggles
        the gsettings key named in_use of the icon_palette. It also
        handles the showing/hiding of the taskar.
        """
        _logger.debug("Entered in on_icp_in_use_toggled")
        self.show_hide_icp()
        _logger.debug("Leaving on_icp_in_use_toggled")

    def show_hide_icp(self):
        if self._window.icp:
            show = config.is_icon_palette_in_use()
            if show:
                # Show icon palette if appropriate and handle visibility of taskbar.
                if not self._window.is_visible():
                    self._window.icp.show()
                self.show_hide_taskbar()
            else:
                # Show icon palette if appropriate and handle visibility of taskbar.
                if not self._window.is_visible():
                    self._window.icp.hide()
                self.show_hide_taskbar()

    # Methods concerning the status icon
    def show_hide_status_icon(self, show_status_icon):
        """
        Callback called when gsettings detects that the gsettings key specifying
        whether the status icon should be shown or not is changed. It also
        handles the showing/hiding of the taskar.
        """
        if show_status_icon:
            self.status_icon.set_visible(True)
        else:
            self.status_icon.set_visible(False)
        self.show_hide_icp()
        self.show_hide_taskbar()

    def cb_status_icon_clicked(self,widget):
        """
        Callback called when status icon clicked.
        Toggles whether Onboard window visibile or not.

        TODO would be nice if appeared to iconify to taskbar
        """
        self.keyboard.toggle_visible()


    # keyboard layout changes
    def cb_keys_changed(self, *args):
        self.reload_layout()

    def cb_vk_timer(self):
        """
        Timer callback for polling until virtkey becomes valid.
        """
        if self.get_vk():
            self.reload_layout(force_update=True)
            GObject.source_remove(self.vk_timer)
            self.vk_timer = None
            return False
        return True

    def update_ui(self):
        if self.keyboard:
            self.keyboard.update_ui()
            self.keyboard.redraw()

    def on_gtk_theme_changed(self, gtk_theme = None):
        """
        Switch onboard themes in sync with gtk-theme changes.
        """
        config.update_theme_from_system_theme()

    def on_gtk_font_dpi_changed(self):
        """
        Refresh the key's pango layout objects so that they can adapt
        to the new system dpi setting.
        """
        if self.keyboard:
            self.keyboard.refresh_pango_layouts()
        self.update_ui()

        return False

    def on_theme_changed(self, theme):
        config.apply_theme()
        self.reload_layout()

    def reload_layout_and_present(self):
        """
        Reload the layout and briefly show the window
        with active transparency
        """
        self.reload_layout(force_update = True)
        if self.keyboard:
            self.keyboard.update_transparency()

    def reload_layout(self, force_update=False):
        """
        Checks if the X keyboard layout has changed and
        (re)loads Onboards layout accordingly.
        """
        keyboard_state = (None, None)

        vk = self.get_vk()
        if vk:
            try:
                vk.reload() # reload keyboard names
                keyboard_state = (vk.get_layout_symbols(),
                                  vk.get_current_group_name())
            except virtkey.error:
                #traceback.print_exc(file=sys.stdout)
                self.reset_vk()
                force_update = True
                _logger.warning("Keyboard layout changed, but retrieving "
                                "keyboard information failed")

        if self.keyboard_state != keyboard_state or force_update:
            self.keyboard_state = keyboard_state
            self.load_layout(config.layout_filename,
                             config.theme_settings.color_scheme_filename)

        # if there is no X keyboard, poll until it appears (if ever)
        if not vk and not self.vk_timer:
            self.vk_timer = GObject.timeout_add_seconds(1, self.cb_vk_timer)

    def load_layout(self, layout_filename, color_scheme_filename):
        _logger.info("Loading keyboard layout from " + layout_filename)
        if (color_scheme_filename):
            _logger.info("Loading color scheme from " + color_scheme_filename)
        if self.keyboard:
            self.keyboard.cleanup()

        # Fix for LP: #897678, onBoard shifts after changing Language Layout
        # The idea is to no longer recreate the keyboard widget and
        # instead just update its contents. This solves a couple of
        # weird positioning bugs when the keyboard widget changes while
        # the main window is hidden.
        # This is messy but works for now. Trunk will have to replace
        # KeyboardSVG with proper widget-independent loading code.
        vk = self.get_vk()
        keyboard = KeyboardSVG(vk, layout_filename,
                                    color_scheme_filename)
        if not self.keyboard:
            self.keyboard = keyboard
        layout, color_scheme = keyboard.layout, keyboard.color_scheme
        keyboard.cleanup()

        if self.keyboard and keyboard:
            self.keyboard.vk = vk
            self.keyboard.layout = layout
            self.keyboard.color_scheme = color_scheme
            self.keyboard.initial_update()
            self.keyboard.update_ui()
            self.keyboard.redraw()


    def get_vk(self):
        if not self._vk:
            try:
                # may fail if there is no X keyboard (LP: 526791)
                self._vk = virtkey.virtkey()

            except virtkey.error as e:
                t = time.time()
                if t > self._vk_error_time + .2: # rate limit to once per 200ms
                    _logger.warning("vk: "+str(e))
                    self._vk_error_time = t

        return self._vk

    def reset_vk(self):
        self._vk = None
        self._vk_error_time = 0


    # Methods concerning the application
    def do_quit_onboard(self, restart = False):
        _logger.debug("Entered do_quit_onboard")
        self.restart = restart
        if not restart:
            self.final_cleanup()
        self.cleanup()
        Gtk.main_quit()

    def cleanup(self):
        config.cleanup()

        # Make an effort to disconnect all handlers. This may
        # still not be enough to remove all references to windows
        # but it ought to reduce the chances of side-effects when
        # restarting due to changes to the window type hint.
        for instance, handler_id in self._connections:
            instance.disconnect(handler_id)

        if self.keyboard:
            self.keyboard.cleanup()
            self._window.keyboard.destroy()  # necessary?
        self.status_icon.set_keyboard_window(None)
        self._window.cleanup()
        self._window.destroy()
        self._window = None

    def final_cleanup(self):
        config.final_cleanup()

    def _cb_recreate_window(self, value):
        # Window type hint can only be set on window creation.
        # Same on gnome-shell for window decoration.
        # -> force restart
        self.do_quit_onboard(restart=True)

def cb_any_event(event, onboard):
    # Update layout on keyboard group changes
    # XkbStateNotify maps to Gdk.EventType.NOTHING
    # https://bugzilla.gnome.org/show_bug.cgi?id=156948

    # Hide bug in Oneirics GTK3
    # Suppress ValueError: invalid enum value: 4294967295
    type = None
    try:
        type = event.type
    except ValueError:
        pass

    if 0: # debug
        a = [event, event.type]
        if type == Gdk.EventType.VISIBILITY_NOTIFY:
            a += [event.state]
        if type == Gdk.EventType.CONFIGURE:
            a += [event.x, event.y, event.width, event.height]
        print(*a)

    if type == Gdk.EventType.NOTHING:
        onboard.reload_layout()

    elif type == Gdk.EventType.SETTING:
        if event.setting.name == "gtk-theme-name":
            onboard.on_gtk_theme_changed()
        elif event.setting.name in ["gtk-xft-dpi",
                                    "gtk-xft-antialias"
                                    "gtk-xft-hinting",
                                    "gtk-xft-hintstyle"]:
            # Update the cached pango layout object here or Onboard
            # doesn't get those settings, in particular the font dpi.
            # For some reason the font sizes are still off when running
            # this immediately. Delay it a little.
            GObject.idle_add(onboard.on_gtk_font_dpi_changed)

    Gtk.main_do_event(event)

