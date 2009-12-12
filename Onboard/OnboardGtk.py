# -*- coding: UTF-8 -*-

### Logging ###
import logging
_logger = logging.getLogger("OnboardGtk")
###############

import sys
import gobject
gobject.threads_init()

import gtk
import virtkey
import gettext
import os.path

from gettext import gettext as _

from Onboard.Keyboard import Keyboard
from Onboard.KeyGtk import *
from Onboard.Pane import Pane
from Onboard.KbdWindow import KbdWindow
from Onboard.KeyboardSVG import KeyboardSVG


### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

import Onboard.KeyCommon

# can't we just import Onboard.utils and then use Onboard.utils.run_script ?
from Onboard.utils import run_script

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
    _window = KbdWindow()

    def __init__(self, main=True):
        sys.path.append(os.path.join(config.install_dir, 'scripts'))

        # this object is the source of all layout info and where we send key presses to be emulated.

        _logger.info("Getting user settings")

        self.load_layout(config.layout_filename)
        config.layout_filename_notify_add(self.load_layout)

        _logger.info("Creating status icon")
        #Create menu for status icon
        uiManager = gtk.UIManager()

        actionGroup = gtk.ActionGroup('UIManagerExample')
        actionGroup.add_actions([('Quit', gtk.STOCK_QUIT, _('_Quit'), None,
                                  _('Quit onBoard'), self.quit),
                                 ('Settings', gtk.STOCK_PREFERENCES, _('_Settings'), None, _('Show settings'), self.cb_settings_item_clicked)])

        uiManager.insert_action_group(actionGroup, 0)

        uiManager.add_ui_from_string("""<ui>
                        <popup>
                            <menuitem action="Settings"/>
                            <menuitem action="Quit"/>
                        </popup>
                    </ui>""")
        status_icon_menu = uiManager.get_widget("/ui/popup")

        # Create the status icon
        self.status_icon = gtk.status_icon_new_from_file(
                os.path.join(config.install_dir, "data", "onboard.svg"))
        self.status_icon.connect("activate", self.cb_status_icon_clicked)
        self.status_icon.connect("popup-menu", self.cb_status_icon_menu,
                status_icon_menu)

        # Show or hide the status icon depending on the value stored in gconf
        self.show_hide_status_icon(config.show_status_icon)

        # Callbacks to use when icp or status icon is toggled
        config.show_status_icon_notify_add(self.show_hide_status_icon)
        config.icp_in_use_change_notify_add(self.cb_icp_in_use_toggled)

        self.show_hide_taskbar()


        # Minimize to IconPalette if running under GDM
        if os.environ.has_key('RUNNING_UNDER_GDM'):
            config.icp_in_use = True
            config.show_status_icon = False
            self.show_hide_taskbar()

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

    def cb_settings_item_clicked(self,widget):
        """
        Callback called when setting button clicked in the status icon menu.
        """
        run_script("sokSettings")

    def cb_status_icon_menu(self,status_icon, button, activate_time,status_icon_menu):
        """
        Callback called when status icon right clicked.  Produces menu.
        """
        status_icon_menu.popup(None, None, gtk.status_icon_position_menu,
             button, activate_time, status_icon)

    def cb_status_icon_clicked(self,widget):
        """
        Callback called when status icon clicked.
        Toggles whether onboard window visibile or not.

        TODO would be nice if appeared to iconify to taskbar
        """
        if self._window.hidden: self._window.do_deiconify()
        else: self._window.do_iconify()


    # Methods concerning the application
    def clean(self):
        self.keyboard.clean()
        self._window.hide()

    def quit(self, widget=None):
        self.clean()
        gtk.main_quit()
            
    def load_layout(self, filename):
        _logger.info("Loading keyboard layout from " + filename)
        self.keyboard = KeyboardSVG(filename)
        self._window.set_keyboard(self.keyboard)
