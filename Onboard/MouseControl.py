# -*- coding: utf-8 -*-
"""
Dwelling control via mousetweaks and general mouse support functions.
"""

from __future__ import division, print_function, unicode_literals

try:
    import dbus
except ImportError:
    pass

from gi.repository.Gio import Settings, SettingsBindFlags
from gi.repository import GLib, GObject, Gtk

from Onboard.utils import DelayedLauncher
from Onboard.ConfigUtils import ConfigObject
import Onboard.osk as osk

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

    def supports_click_params(self, button, click_type):
        raise NotImplementedError()

    def set_click_params(self, button, click_type):
        raise NotImplementedError()

    def get_click_button(self):
        raise NotImplementedError()

    def get_click_type(self):
        raise NotImplementedError()


class ClickMapper(MouseController):
    """
    Onboards built-in mouse click mapper.
    Maps secondary or middle button to the primary button.
    """
    def __init__(self):
        MouseController.__init__(self)

        self._osk_util = osk.Util()
        self._click_done_notify_callbacks = []
        self._exclusion_rects = []

    def cleanup(self):
        self._click_done_notify_callbacks = []

    def supports_click_params(self, button, click_type):
        return True

    def set_click_params(self, button, click_type):
        self._set_next_mouse_click(button, click_type)

    def get_click_button(self):
        try:
            button = self._osk_util.get_convert_click_button()
        except osk.error as error:
            button = self.PRIMARY_BUTTON
        return button

    def get_click_type(self):
        try:
            click_type = self._osk_util.get_convert_click_type()
        except osk.error as error:
            click_type = self.CLICK_TYPE_SINGLE
        return click_type

    def _set_next_mouse_click(self, button, click_type):
        """
        Converts the next mouse left-click to the click
        specified in @button. Possible values are 2 and 3.
        """
        try:
            self._osk_util.convert_primary_click(button, click_type,
                                                 self._exclusion_rects,
                                                 self._on_click_done)
        except osk.error as error:
            _logger.warning(error)
            self._button = self.PRIMARY_BUTTON

    def state_notify_add(self, callback):
        self._click_done_notify_callbacks.append(callback)

    def _on_click_done(self):
        # update click type buttons
        for callback in self._click_done_notify_callbacks:
            callback(None)

    def set_exclusion_rects(self, rects):
        self._exclusion_rects = rects


class Mousetweaks(ConfigObject, MouseController):
    """ Mousetweaks settings, D-bus control and signal handling """

    CLICK_TYPE_RIGHT  = 0
    CLICK_TYPE_MIDDLE = 4

    MOUSE_A11Y_SCHEMA_ID = "org.gnome.desktop.a11y.mouse"
    MOUSETWEAKS_SCHEMA_ID = "org.gnome.mousetweaks"

    MT_DBUS_NAME  = "org.gnome.Mousetweaks"
    MT_DBUS_PATH  = "/org/gnome/Mousetweaks"
    MT_DBUS_IFACE = "org.gnome.Mousetweaks"
    MT_DBUS_PROP  = "ClickType"

    def __init__(self):
        self._click_type_callbacks = []

        if not "dbus" in globals():
            raise ImportError("python-dbus unavailable")

        ConfigObject.__init__(self)
        MouseController.__init__(self)

        self.launcher = DelayedLauncher()
        self._daemon_running_notify_callbacks = []

        # Check if mousetweaks' schema is installed.
        # Raises SchemaError if it isn't.
        self.mousetweaks = ConfigObject(None, self.MOUSETWEAKS_SCHEMA_ID)

        # connect to session bus
        self._bus = dbus.SessionBus()
        self._bus.add_signal_receiver(self._on_name_owner_changed,
                                      "NameOwnerChanged",
                                      dbus.BUS_DAEMON_IFACE,
                                      arg0=self.MT_DBUS_NAME)
        # Initial state
        proxy = self._bus.get_object(dbus.BUS_DAEMON_NAME, dbus.BUS_DAEMON_PATH)
        result = proxy.NameHasOwner(self.MT_DBUS_NAME, dbus_interface=dbus.BUS_DAEMON_IFACE)
        self._set_connection(bool(result))

    def _init_keys(self):
        """ Create gsettings key descriptions """

        self.schema = self.MOUSE_A11Y_SCHEMA_ID
        self.sysdef_section = None

        self.add_key("dwell-click-enabled", False)
        self.add_key("dwell-time", 1.2)
        self.add_key("dwell-threshold", 10)
        self.add_key("click-type-window-visible", False)

    def on_properties_initialized(self):
        ConfigObject.on_properties_initialized(self)

        # launch mousetweaks on startup if necessary
        if not self._iface and \
           self.dwell_click_enabled:
            self._launch_daemon(0.5)

    def cleanup(self):
        self._daemon_running_notify_callbacks = []

    def _launch_daemon(self, delay):
        self.launcher.launch_delayed(["mousetweaks"], delay)

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
        active = old == ""
        if active:
            self.launcher.stop()
        self._set_connection(active)

        # update hover click button
        for callback in self._daemon_running_notify_callbacks:
            callback(active)

    def daemon_running_notify_add(self, callback):
        self._daemon_running_notify_callbacks.append(callback)

    def _on_click_type_prop_changed(self, iface, changed_props, invalidated_props):
        ''' Either we or someone else has change the click-type. '''
        if self.MT_DBUS_PROP in changed_props:
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
        self.daemon_running_notify_add(callback)

    def click_type_notify_add(self, callback):
        self._click_type_callbacks.append(callback)

    def is_active(self):
        return self.dwell_click_enabled and bool(self._iface)

    def set_active(self, active):
        self.dwell_click_enabled = active

        # try to launch mousetweaks if it isn't running yet
        if active and not self._iface:
            self._launch_daemon(1.0)
        else:
            self.launcher.stop()

    def supports_click_params(self, button, click_type):
        # mousetweaks since 3.3.90 supports middle click button too.
        return True

    def set_click_params(self, button, click_type):
        mt_click_type = click_type
        if button == self.SECONDARY_BUTTON:
            mt_click_type = self.CLICK_TYPE_RIGHT
        if button == self.MIDDLE_BUTTON:
            mt_click_type = self.CLICK_TYPE_MIDDLE
        self._set_mt_click_type(mt_click_type)

    def get_click_button(self):
        mt_click_type = self._get_mt_click_type()
        if mt_click_type == self.CLICK_TYPE_RIGHT:
            return self.SECONDARY_BUTTON
        if mt_click_type == self.CLICK_TYPE_MIDDLE:
            return self.MIDDLE_BUTTON
        return self.PRIMARY_BUTTON

    def get_click_type(self):
        mt_click_type = self._get_mt_click_type()
        if mt_click_type in [self.CLICK_TYPE_RIGHT, self.CLICK_TYPE_MIDDLE]:
            return self.CLICK_TYPE_SINGLE
        return mt_click_type


