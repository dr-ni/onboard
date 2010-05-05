# -*- coding: UTF-8 -*-

### Logging ###
import logging
_logger = logging.getLogger("OnboardGtk")
###############

import sys
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
        
        # create main window
        if config.xid_mode:    # XEmbed mode for gnome-screensaver?
            self._window = KbdPlugWindow()

            # write xid to stdout
            sys.stdout.write('%d\n' % self._window.get_id())
            sys.stdout.flush()
        else:
            self._window = KbdWindow()

        # this object is the source of all layout info and where we send key presses to be emulated.

        _logger.info("Getting user settings")

        self.load_layout(config.layout_filename)
        config.layout_filename_notify_add(self.load_layout)

        # connect notifications for keyboard map and group changes
        self.keymap = gtk.gdk.keymap_get_default()
        self.keymap.connect("keys-changed", self.cb_keys_changed) # map changes
        gtk.gdk.event_handler_set(cb_any_event, self)          # group changes

        self.status_icon = Indicator(self._window)
        # Show or hide the status icon depending on the value stored in gconf

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

    def cb_keys_changed(self, *args):
        self.update_layout()
        
    def cb_vk_timer(self):
        if self.keyboard.vk:
            self.update_layout(force_update=True)
            gobject.source_remove(self.vk_timer)
            return False
        return True
    
    # Methods concerning the application
    def clean(self):
        self.keyboard.clean()
        self._window.hide()

    def quit(self, widget=None):
        self.clean()
        gtk.main_quit()

    def update_layout(self, force_update=False):
        if self.keyboard:
            try:
                state = None
                if self.keyboard.vk:
                    self.keyboard.vk.reload() # reload keyboard names
                    state = (self.keyboard.vk.get_layout_symbols(),
                             self.keyboard.vk.get_current_group_name())
            except virtkey.error:
                #traceback.print_exc(file=sys.stdout) 
                self.keyboard.reset_vk()
                force_update = True 
                _logger.warning("Keyboard layout changed, but retrieving "
                                "keyboard information failed")
                
            if self.keyboard_state != state or force_update:
                self.keyboard_state = state
                self.load_layout(config.layout_filename)

    def load_layout(self, filename):
        _logger.info("Loading keyboard layout from " + filename)
        if self.keyboard:
            self.keyboard.clean()
        self.keyboard = KeyboardSVG(filename)
        self._window.set_keyboard(self.keyboard)

        # if there is no X keyboard, poll until it appears
        if not self.keyboard._vk:
            self.vk_timer = gobject.timeout_add_seconds(1, self.cb_vk_timer)


def cb_any_event(event, onboard):
    # XkbStateNotify maps to gtk.gdk.NOTHING
    # https://bugzilla.gnome.org/show_bug.cgi?id=156948
    if event.type == gtk.gdk.NOTHING:
        onboard.cb_keys_changed()
    gtk.main_do_event(event)


