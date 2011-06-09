import gobject
import gtk
import os

import Onboard.utils as utils

### Logging ###
import logging
_logger = logging.getLogger("Indicator")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

from gettext import gettext as _

class Indicator(gobject.GObject):

    __gsignals__ = {
        'quit-onboard' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
    }

    "Keyboard window managed by this indicator"
    _keyboard_window = None

    "Encapsulated appindicator instance"
    _indicator = None

    "Encapsulated GtkStatusIcon instance"
    _status_icon = None

    "Menu attached to indicator"
    _menu = None

    def __init__(self, keyboard_window):

        gobject.GObject.__init__(self)

        self._keyboard_window = keyboard_window

        self._keyboard_window.connect("window-state-event", self._on_keyboard_window_state_change)

        self._menu = gtk.Menu()
        show_item = gtk.MenuItem(_("_Show Onboard"))
        show_item.connect_object("activate",
            Indicator._toggle_keyboard_window_state, self)
        self._menu.append(show_item)
        hide_item = gtk.MenuItem(_("_Hide Onboard"))
        hide_item.connect_object("activate",
            Indicator._toggle_keyboard_window_state, self)
        self._menu.append(hide_item)

        settings_item = gtk.ImageMenuItem(stock_id=gtk.STOCK_PREFERENCES)
        settings_item.connect("activate", self._on_settings_clicked)
        self._menu.append(settings_item)

        quit_item = gtk.ImageMenuItem(stock_id=gtk.STOCK_QUIT)
        quit_item.connect("activate", self._emit_quit_onboard)
        self._menu.append(quit_item)
        self._menu.show_all()

        if keyboard_window.hidden:
            hide_item.hide()
        else:
            show_item.hide()

        try:
            self._init_indicator()
        except ImportError:
            _logger.info("appindicator not available, falling back on"
                " GtkStatusIcon")
            self._init_status_icon()
        self.set_visible(False)

    def _init_indicator(self):
        import appindicator
        self._indicator = appindicator.Indicator(
            "Onboard",
            "onboard",
            appindicator.CATEGORY_APPLICATION_STATUS)
        self._indicator.set_menu(self._menu)


    def _init_status_icon(self):
        self._status_icon = gtk.status_icon_new_from_icon_name("onboard")
        self._status_icon.connect_object("activate",
            Indicator._toggle_keyboard_window_state, self)
        self._status_icon.connect("popup-menu", self._on_status_icon_popup_menu,
            self._menu)

    def set_visible(self, visible):
        if self._status_icon:
            # Then we've falled back to using GtkStatusIcon
            self._status_icon.set_visible(visible)
        else:
            self._set_indicator_active(visible)

    def _on_settings_clicked(self, widget):
        utils.run_script("sokSettings")

    def _on_status_icon_popup_menu(self, status_icon, button, activate_time,
            status_icon_menu):
        """
        Callback called when status icon right clicked.  Produces menu.
        """
        status_icon_menu.popup(None, None, gtk.status_icon_position_menu,
            button, activate_time, status_icon)

    def _toggle_keyboard_window_state(self):
        if self._keyboard_window.hidden:
            self._keyboard_window.deiconify()
        else:
            self._keyboard_window.iconify()

    def _set_indicator_active(self, active):
        try:
            import appindicator
        except ImportError:
            pass
        else:
            if active:
                self._indicator.set_status(appindicator.STATUS_ACTIVE)
            else:
                self._indicator.set_status(appindicator.STATUS_PASSIVE)

    def _on_keyboard_window_state_change(self, window, event):
        if window.hidden:
            self._menu.get_children()[0].show()
            self._menu.get_children()[1].hide()
        else:
            self._menu.get_children()[0].hide()
            self._menu.get_children()[1].show()

    def _emit_quit_onboard(self, data=None):
        _logger.debug("Entered _emit_quit_onboard")
        self.emit("quit-onboard")

    def is_appindicator(self):
        if self._indicator:
            return True
        else:
            return False

gobject.type_register(Indicator)
