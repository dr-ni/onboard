# -*- coding: utf-8 -*-
"""
Dwelling control via mousetweaks and general mouse support functions.
"""

import dbus
from dbus.mainloop.glib import DBusGMainLoop

from gi.repository.Gio import Settings, SettingsBindFlags
from gi.repository import GLib, GObject, Gtk

from Onboard.ConfigUtils import ConfigObject
import osk

### Logging ###
import logging
_logger = logging.getLogger("MouseControl")
###############


class MouseController(GObject.GObject):
    """ Abstract base class for mouse controllers """

    PRIMARY_BUTTON   = 1
    MIDDLE_BUTTON    = 2
    SECONDARY_BUTTON = 3

    CLICK_TYPE_SINGLE = 3
    CLICK_TYPE_DOUBLE = 2
    CLICK_TYPE_DRAG   = 1

    # Public interface

    def set_click_params(self, button, click_type):
        raise NotImplementedException()

    def get_click_button(self):
        raise NotImplementedException()

    def get_click_type(self):
        raise NotImplementedException()


class ClickMapper(MouseController):
    """
    Onboards built-in mouse click mapper.
    Mapps secondary or middle button to the primary button.
    """
    def __init__(self):
        MouseController.__init__(self)

        self._osk_util = osk.Util()
        self._button = self.PRIMARY_BUTTON
        self._click_type = self.CLICK_TYPE_SINGLE

    def set_click_params(self, button, click_type):
        self._set_next_mouse_click(button)
        self._click_type = click_type

    def get_click_button(self):
        return self._button

    def get_click_type(self):
        return self._click_type

    def _set_next_mouse_click(self, button):
        """
        Converts the next mouse left-click to the click
        specified in @button. Possible values are 2 and 3.
        """
        self._button = button
        if not button == self.PRIMARY_BUTTON:
            try:
                    self._osk_util.convert_primary_click(button)
            except osk.error as error:
                _logger.warning(error)
                self._button = self.PRIMARY_BUTTON


class Mousetweaks(ConfigObject, MouseController):
    """ Mousetweaks settings, D-bus control and signal handling """

    CLICK_TYPE_RIGHT  = 0

    MOUSE_A11Y_SCHEMA_ID = "org.gnome.desktop.a11y.mouse"

    MT_DBUS_NAME  = "org.gnome.Mousetweaks"
    MT_DBUS_PATH  = "/org/gnome/Mousetweaks"
    MT_DBUS_IFACE = "org.gnome.Mousetweaks"
    MT_DBUS_PROP  = "ClickType"

    def __init__(self):
        self._click_type_callbacks = []

        ConfigObject.__init__(self)
        MouseController.__init__(self)

        # Use D-bus main loop by default
        DBusGMainLoop(set_as_default=True)

        # create main window
        self._bus = dbus.SessionBus()
        self._bus.add_signal_receiver(self._on_name_owner_changed,
                                      "NameOwnerChanged",
                                      dbus.BUS_DAEMON_IFACE,
                                      arg0=self.MT_DBUS_NAME)

        # Initial state
        proxy = self._bus.get_object(dbus.BUS_DAEMON_NAME, dbus.BUS_DAEMON_PATH)
        result = proxy.NameHasOwner(self.MT_DBUS_NAME, dbus_interface=dbus.BUS_DAEMON_IFACE)
        self._set_connection(bool(result))

        # maybe hide it and restore original state on exit
        self._old_click_type_window_visible = self.click_type_window_visible
        #self.click_type_window_visible = False

    def _init_keys(self):
        """ Create gsettings key descriptions """

        self.gspath = self.MOUSE_A11Y_SCHEMA_ID
        self.sysdef_section = None

        self.add_key("dwell-click-enabled", False)
        self.add_key("dwell-time", 1.2)
        self.add_key("click-type-window-visible", False)

    def _set_connection(self, active):
        ''' Update interface object, state and notify listeners '''
        if active:
            proxy = self._bus.get_object(self.MT_DBUS_NAME, self.MT_DBUS_PATH)
            self._iface = dbus.Interface(proxy, dbus.PROPERTIES_IFACE)
            self._iface.connect_to_signal("PropertiesChanged",
                                          self._on_click_type_prop_changed)
            self._click_type = self._iface.Get(self.MT_DBUS_IFACE, self.MT_DBUS_PROP)
        else:
            self._iface = None
            self._click_type = self.CLICK_TYPE_SINGLE

    def _on_name_owner_changed(self, name, old, new):
        '''
        The daemon has de/registered the name.
        Called when dwell-click-enabled changes in gsettings.
        '''
        self._set_connection(old == "")

    def _on_click_type_prop_changed(self, iface, changed_props, invalidated_props):
        ''' Either we or someone else has change the click-type. '''
        if changed_props.has_key(self.MT_DBUS_PROP):
            self._click_type = changed_props.get(self.MT_DBUS_PROP)

            # notify listeners
            for callback in self._click_type_callbacks:
                callback(self._click_type)

    def _get_mt_click_type(self):
        return self._click_type;

    def _set_mt_click_type(self, click_type):
        if click_type != self._click_type:# and self.is_active():
            self._click_type = click_type
            self._iface.Set(self.MT_DBUS_IFACE, self.MT_DBUS_PROP, click_type)

    ##########
    # Public
    ##########

    def state_notify_add(self, callback):
        """ Convenience function to subscribes to all notifications """
        self.dwell_click_enabled_notify_add(callback)
        self.click_type_notify_add(callback)

    def click_type_notify_add(self, callback):
        self._click_type_callbacks.append(callback)

    def is_active(self):
        return self.dwell_click_enabled

    def set_active(self, active):
        self.dwell_click_enabled = active


    def set_click_params(self, button, click_type):
        mt_click_type = click_type
        if button == self.SECONDARY_BUTTON:
            mt_click_type = self.CLICK_TYPE_RIGHT
        self._set_mt_click_type(mt_click_type)

    def get_click_button(self):
        mt_click_type = self._get_mt_click_type()
        if mt_click_type == self.CLICK_TYPE_RIGHT:
            return self.SECONDARY_BUTTON
        return self.PRIMARY_BUTTON

    def get_click_type(self):
        mt_click_type = self._get_mt_click_type()
        if mt_click_type == self.CLICK_TYPE_RIGHT:
            return self.CLICK_TYPE_SINGLE
        return mt_click_type


