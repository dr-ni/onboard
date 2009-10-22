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

    keyboard = None

    def __init__(self, main=True):
        sys.path.append(os.path.join(config.install_dir, 'scripts'))

        # this object is the source of all layout info and where we send key presses to be emulated.

        _logger.info("Getting user settings")

        self.load_layout(config.layout_filename)
        config.layout_filename_notify_add(self.load_layout)

        # connect notifications here to keep config from holding 
        # references of keyboard objects. 
        config.scanning_notify_add(lambda x: \
                                     self.keyboard.reset_scan())
        config.auto_learn_notify_add(lambda x: \
                                     self.keyboard.cb_set_auto_learn(x))
        config.auto_punctuation_notify_add(lambda x: \
                                     self.keyboard.cb_set_auto_punctuation(x))
        config.auto_save_interval_notify_add(lambda x: \
                                     self.keyboard.cb_set_auto_save_interval(x))
        config.frequency_time_ratio_notify_add(lambda x: \
                                     self.keyboard.cb_set_frequency_time_ratio(x))

        self._window.connect("destroy", self.cb_window_destroy)
        
        _logger.info("Creating trayicon")
        #Create menu for trayicon
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
        trayMenu = uiManager.get_widget("/ui/popup")

        # Create the trayicon
        self.statusIcon = gtk.status_icon_new_from_file(
                os.path.join(config.install_dir, "data", "onboard.svg"))
        self.statusIcon.connect("activate", self.cb_status_icon_clicked)
        self.statusIcon.connect("popup-menu", self.cb_status_icon_menu,
                trayMenu)

        _logger.info("Showing window")
        self._window.hidden = False
        self._window.do_show()
        
        config.show_trayicon_notify_add(self.do_set_trayicon)

        if config.show_trayicon:
            _logger.info("Showing trayicon")
            self.hide_status_icon()
            self.show_status_icon()
        else:
            self.hide_status_icon()

        if main:
            _logger.info("Entering mainloop of onboard")
            gtk.main()

    def cb_window_destroy(self, widget):
        _logger.info("Window is being destroyed")
        self.clean()

    def cb_settings_item_clicked(self,widget):
        """
        Callback called when setting button clicked in the trayicon menu.
        """
        run_script("sokSettings")

    def cb_status_icon_menu(self,status_icon, button, activate_time,trayMenu):
        """
        Callback called when trayicon right clicked.  Produces menu.
        """
        trayMenu.popup(None, None, gtk.status_icon_position_menu,
             button, activate_time, status_icon)

    def do_set_trayicon(self, show_trayicon):
        """
        Callback called when gconf detects that the gconf key specifying
        whether the trayicon should be shown or not is changed.
        """
        if show_trayicon:
            self.show_status_icon()
        else:
            self.hide_status_icon()

    def show_status_icon(self):
        """
        Shows the status icon.  When it is shown we set a wm hint so that
        onboard does not appear in the taskbar.
        """
        self.statusIcon.set_visible(True)
        self._window.set_property('skip-taskbar-hint', True)

    def hide_status_icon(self):
        """
        The opposite of the above.
        """
        self.statusIcon.set_visible(False)
        self._window.set_property('skip-taskbar-hint', False)

    def cb_status_icon_clicked(self,widget):
        """
        Callback called when trayicon clicked.
        Toggles whether onboard window visibile or not.

        TODO would be nice if appeared to iconify to taskbar
        """
        if self._window.hidden: self._window.do_show()
        else: self._window.do_hide()

    def clean(self): #Called when sok is gotten rid off.
        self.keyboard.destruct()
        self._window.hide()

    def quit(self, widget=None):
        self._window.destroy()

    def load_layout(self, filename):
        _logger.info("Loading keyboard layout from " + filename)

        # try to prevent resource leaks when switching layouts
        if self.keyboard:
            self.keyboard.destruct()

        self.keyboard = KeyboardSVG(filename)
        self._window.set_keyboard(self.keyboard)
