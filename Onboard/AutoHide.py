# -*- coding: utf-8 -*-

# Copyright © 2014 marmuta <marmvta@gmail.com>
#
# This file is part of Onboard.
#
# Onboard is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Onboard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""
Hide the keyboard on incoming physical keyboard events.
"""

from __future__ import division, print_function, unicode_literals


from Onboard.utils         import EventSource
from Onboard.XInput        import XIDeviceManager, XIEventType, XIEventMask

### Logging ###
import logging
_logger = logging.getLogger("AutoHide")
###############

from Onboard.Config import Config
config = Config()


class AutoHide(EventSource):
    """
    Hide Onboard when a physical keyboard is being used.
    """

    def __init__(self, keyboard):
        # There is only button-release to subscribe to currently,
        # as this is all CSButtonRemapper needs to detect the end of a click.
        EventSource.__init__(self, ["button-release"])

        self._keyboard = keyboard
        self._device_manager = None
        self._keyboard_slave_devices = None

    def cleanup(self):
        self._register_xinput_events(False)

    def is_enabled(self):
        return self._device_manager is not None

    def enable(self, enable, use_gtk=False):
        self.register_input_events(enable, use_gtk)

    def register_input_events(self, register, use_gtk=False):
        self._register_xinput_events(False)
        if register:
            if not use_gtk:  # can't do this with gtk yet
                if not self._register_xinput_events(True):
                    _logger.warning(
                        "XInput event source failed to initialize, "
                        "falling back to GTK.")

    def _register_xinput_events(self, register):
        """ Setup XInput event handling """
        success = True

        if register:
            self._device_manager = XIDeviceManager()
            if self._device_manager.is_valid():
                self._device_manager.connect("device-event",
                                             self._on_device_event)
                self._device_manager.connect("device-grab",
                                             self._on_device_grab)
                self._select_xinput_devices()
            else:
                success = False
                self._device_manager = None
        else:

            if self._device_manager:
                self._device_manager.disconnect("device-event",
                                                self._on_device_event)
                self._device_manager.disconnect("device-grab",
                                                self._on_device_grab)
                self._unselect_xinput_devices()
                self._device_manager = None

        return success

    def _select_xinput_devices(self):
        """ Select keyboard devices and the events we want to listen to. """

        self._unselect_xinput_devices()

        event_mask = XIEventMask.KeyPressMask | \
                     XIEventMask.KeyReleaseMask

        devices = self._device_manager.get_client_keyboard_attached_slaves()
        _logger.info("listening to keyboard devices: {}"
                     .format([(d.name, d.id, d.get_config_string())
                              for d in devices]))
        for device in devices:
            try:
                self._device_manager.select_events(None, device, event_mask)
            except Exception as ex:
                _logger.warning("Failed to select events for device "
                                "{id}: {ex}"
                                .format(id=device.id, ex=ex))
        self._keyboard_slave_devices = devices

    def _unselect_xinput_devices(self):
        if self._keyboard_slave_devices:
            for device in self._keyboard_slave_devices:
                try:
                    self._device_manager.unselect_events(None, device)
                except Exception as ex:
                    _logger.warning("Failed to unselect events for device "
                                    "{id}: {ex}"
                                    .format(id=device.id, ex=ex))
            self._keyboard_slave_devices = None

    def _on_device_grab(self, device, event):
        """ Someone grabbed/relased a device. Update our device list. """
        self._select_xinput_devices()

    def _on_device_event(self, event):
        """
        Handler for XI2 events.
        """
        event_type = event.xi_type

        # re-select devices on changes to the device hierarchy
        if event_type in XIEventType.HierarchyEvents or \
           event_type == XIEventType.DeviceChanged:
            self._select_xinput_devices()
            return

        if event_type == XIEventType.KeyPress or \
           event_type == XIEventType.KeyRelease:

            if not self._keyboard.is_auto_show_paused():
                if _logger.isEnabledFor(logging.INFO):
                    device = event.get_source_device()
                    device_name = device.name if device else "None"
                    _logger.info("Hiding keyboard and pausing "
                                "auto-show due to physical key-{} "
                                "{} from device '{}' ({})"
                                .format("press"
                                        if event_type == XIEventType.KeyPress
                                        else "release",
                                        event.keyval,
                                        device_name,
                                        event.source_id))

                if self._keyboard.is_visible():
                    if config.are_word_suggestions_enabled():
                        self._keyboard.discard_changes()

                    self._keyboard.set_visible(False)

            duration = config.auto_show.hide_on_key_press_pause
            if duration:
                if duration < 0.0:  # negative means auto-hide is off
                    duration = None
                self._keyboard.pause_auto_show(duration)

            return


