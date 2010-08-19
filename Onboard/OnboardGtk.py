# -*- coding: UTF-8 -*-

### Logging ###
import logging
_logger = logging.getLogger("OnboardGtk")
###############

import sys
import time
import traceback
import gobject
gobject.threads_init()

import gtk
import virtkey
import gettext
import os.path

from gettext import gettext as _

from Onboard.Indicator import Indicator
from Onboard.Keyboard import Keyboard
from Onboard.KeyGtk import *
from Onboard.Pane import Pane
from Onboard.KbdWindow import KbdWindow, KbdPlugWindow
from Onboard.KeyboardSVG import KeyboardSVG
from Onboard.utils       import show_confirmation_dialog


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

    def __init__(self, main=True):
        sys.path.append(os.path.join(config.install_dir, 'scripts'))

        self.keyboard_state = None
        self.vk_timer = None
        self.reset_vk()

        # create main window
        if config.xid_mode:    # XEmbed mode for gnome-screensaver?
            self._window = KbdPlugWindow()

            # write xid to stdout
            sys.stdout.write('%d\n' % self._window.get_id())
            sys.stdout.flush()
        else:
            self._window = KbdWindow()
            self._window.connect_object("quit-onboard",
                                        self.do_quit_onboard, None)

        _logger.info("Getting user settings")

        # load the initial layout
        self.update_layout()
        config.layout_filename_notify_add(self.load_layout)

        # connect notifications for keyboard map and group changes
        self.keymap = gtk.gdk.keymap_get_default()
        self.keymap.connect("keys-changed", self.cb_keys_changed) # map changes
        gtk.gdk.event_handler_set(cb_any_event, self)          # group changes

        # create status icon
        self.status_icon = Indicator(self._window)
        if self.status_icon.is_appindicator():
            self.status_icon.connect("quit-onboard", self.do_quit_onboard)

        # Callbacks to use when icp or status icon is toggled
        config.show_status_icon_notify_add(self.show_hide_status_icon)
        config.icp_in_use_change_notify_add(self.cb_icp_in_use_toggled)

        self.show_hide_status_icon(config.show_status_icon)

        self.show_hide_taskbar()


        # Minimize to IconPalette if running under GDM
        if os.environ.has_key('RUNNING_UNDER_GDM'):
            config.icp_in_use = True
            config.show_status_icon = False
            self.show_hide_taskbar()


        # If onboard is configured to be embedded into the unlock screen
        # dialog, and the embedding command is not set to onboard, ask
        # the user what to do
        if config.onboard_xembed_enabled:
            if not config.is_onboard_in_xembed_command_string():
                question = _("Onboard is configured to appear with the dialog to unlock the screen; for example to dismiss the password-protected screensaver.\n\nHowever the system is not configured anymore to use onboard to unlock the screen. A possible reason can be that another application configured the system to use something else.\n\nWould you like to reconfigure the system to show onboard when unlocking the screen?")
                reply = show_confirmation_dialog(question)
                if reply == True:
                    config.onboard_xembed_enabled = True
                    config.gss_xembed_enabled = True
                    config.set_xembed_command_string_to_onboard()
                else:
                    config.onboard_xembed_enabled = False
            else:
                if not config.gss_xembed_enabled:
                    question = _("Onboard is configured to appear with the dialog to unlock the screen; for example to dismiss the password-protected screensaver.\n\nHowever this function is disabled in the system.\n\nWould you like to activate it?")
                    reply = show_confirmation_dialog(question)
                    if reply == True:
                        config.onboard_xembed_enabled = True
                        config.gss_xembed_enabled = True
                        config.set_xembed_command_string_to_onboard()
                    else:
                        config.onboard_xembed_enabled = False


        if main:
            _logger.info("Entering mainloop of onboard")
            gtk.main()
            self.clean()


    # Method concerning the taskbar
    def show_hide_taskbar(self):
        """
        This method shows or hides the taskbard depending on whether there
        is an alternative way to unminimize the onboard window.
        This method should be called every time such an alternative way
        is activated or deactivated.
        """
        if config.icp_in_use or \
           config.show_status_icon:
            self._window.set_property('skip-taskbar-hint', True)
        else:
            self._window.set_property('skip-taskbar-hint', False)


    # Method concerning the icon palette
    def cb_icp_in_use_toggled(self, icp_in_use):
        """
        This is the callback that gets executed when the user toggles
        the gconf key named in_use of the icon_palette. It also
        handles the showing/hiding of the taskar.
        """
        _logger.debug("Entered in on_icp_in_use_toggled")
        if icp_in_use:
            # Show icon palette if appropriate and handle visibility of taskbar.
            if self._window.hidden:
                self._window.icp.do_show()
            self.show_hide_taskbar()
        else:
            # Show icon palette if appropriate and handle visibility of taskbar.
            if self._window.hidden:
                self._window.icp.do_hide()
            self.show_hide_taskbar()
        _logger.debug("Leaving on_icp_in_use_toggled")


    # Methods concerning the status icon
    def show_hide_status_icon(self, show_status_icon):
        """
        Callback called when gconf detects that the gconf key specifying
        whether the status icon should be shown or not is changed. It also
        handles the showing/hiding of the taskar.
        """
        if show_status_icon:
            self.status_icon.set_visible(True)
            self.show_hide_taskbar()
        else:
            self.status_icon.set_visible(False)
            self.show_hide_taskbar()

    def cb_status_icon_clicked(self,widget):
        """
        Callback called when status icon clicked.
        Toggles whether onboard window visibile or not.

        TODO would be nice if appeared to iconify to taskbar
        """
        if self._window.hidden: self._window.deiconify()
        else: self._window.iconify()


    # Methods concerning the listening to keyboard layout changes
    def cb_keys_changed(self, *args):
        self.update_layout()

    def cb_vk_timer(self):
        """
        Timer callback for polling until virtkey becomes valid.
        """
        if self.get_vk():
            self.update_layout(force_update=True)
            gobject.source_remove(self.vk_timer)
            self.vk_timer = None
            return False
        return True

    def update_layout(self, force_update=False):
        """
        Checks if the X keyboard layout has changed and
        (re)loads onboards layout accordingly.
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
            self.load_layout(config.layout_filename)

        # if there is no X keyboard, poll until it appears
        if not vk and not self.vk_timer:
            self.vk_timer = gobject.timeout_add_seconds(1, self.cb_vk_timer)

    def load_layout(self, filename):
        _logger.info("Loading keyboard layout from " + filename)
        if self.keyboard:
            self.keyboard.clean()
        self.keyboard = KeyboardSVG(self.get_vk(), filename)
        self._window.set_keyboard(self.keyboard)

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
    def clean(self):
        self.keyboard.clean()
        self._window.hide()

    def quit(self, widget=None):
        self.clean()
        gtk.main_quit()

    def do_quit_onboard(self, data=None):
        _logger.debug("Entered do_quit_onboard")
        self._window.save_size_and_position()
        gtk.main_quit()


def cb_any_event(event, onboard):
    # XkbStateNotify maps to gtk.gdk.NOTHING
    # https://bugzilla.gnome.org/show_bug.cgi?id=156948
    if event.type == gtk.gdk.NOTHING:
        onboard.update_layout()
    gtk.main_do_event(event)


