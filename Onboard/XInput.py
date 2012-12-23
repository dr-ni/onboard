# -*- coding: utf-8 -*-

# Copyright © 2012, marmuta
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

from __future__ import division, print_function, unicode_literals

from gi.repository import Gdk

from Onboard.utils import EventSource

import Onboard.osk as osk

import logging
logger = logging.getLogger(__name__)


class XIEventType:
    """ enum of XInput events """
    DeviceChanged     = 1
    KeyPress          = 2
    KeyRelease        = 3
    ButtonPress       = 4
    ButtonRelease     = 5
    Motion            = 6
    Enter             = 7
    Leave             = 8
    FocusIn           = 9
    FocusOut          = 10
    HierarchyChanged  = 11
    PropertyEvent     = 12
    RawKeyPress       = 13
    RawKeyRelease     = 14
    RawButtonPress    = 15
    RawButtonRelease  = 16
    RawMotion         = 17
    TouchBegin        = 18
    TouchUpdate       = 19
    TouchEnd          = 20
    TouchOwnership    = 21
    RawTouchBegin     = 22
    RawTouchUpdate    = 23
    RawTouchEnd       = 24

    # extra non-XI events
    DeviceAdded       = 1100
    DeviceRemoved     = 1101


class XIEventMask:
    """ enum of XInput event masks """
    DeviceChangedMask     = 1 << XIEventType.DeviceChanged
    KeyPressMask          = 1 << XIEventType.KeyPress
    KeyReleaseMask        = 1 << XIEventType.KeyRelease
    ButtonPressMask       = 1 << XIEventType.ButtonPress
    ButtonReleaseMask     = 1 << XIEventType.ButtonRelease
    MotionMask            = 1 << XIEventType.Motion
    EnterMask             = 1 << XIEventType.Enter
    LeaveMask             = 1 << XIEventType.Leave
    FocusInMask           = 1 << XIEventType.FocusIn
    FocusOutMask          = 1 << XIEventType.FocusOut
    HierarchyChangedMask  = 1 << XIEventType.HierarchyChanged
    PropertyEventMask     = 1 << XIEventType.PropertyEvent
    RawKeyPressMask       = 1 << XIEventType.RawKeyPress
    RawKeyReleaseMask     = 1 << XIEventType.RawKeyRelease
    RawButtonPressMask    = 1 << XIEventType.RawButtonPress
    RawButtonReleaseMask  = 1 << XIEventType.RawButtonRelease
    RawMotionMask         = 1 << XIEventType.RawMotion
    TouchBeginMask        = 1 << XIEventType.TouchBegin
    TouchUpdateMask       = 1 << XIEventType.TouchUpdate
    TouchEndMask          = 1 << XIEventType.TouchEnd
    TouchOwnershipMask    = 1 << XIEventType.TouchOwnership
    RawTouchBeginMask     = 1 << XIEventType.RawTouchBegin
    RawTouchUpdateMask    = 1 << XIEventType.RawTouchUpdate
    RawTouchEndMask       = 1 << XIEventType.RawTouchEnd

    TouchMask             = TouchBeginMask | \
                            TouchUpdateMask | \
                            TouchEndMask

    RawTouchMask          = RawTouchBeginMask | \
                            RawTouchUpdateMask | \
                            RawTouchEndMask

class XIDeviceType:
    """ enum of XInput device types """
    MasterPointer  = 1
    MasterKeyboard = 2
    SlavePointer   = 3
    SlaveKeyboard  = 4
    FloatingSlave  = 5


class XITouchMode:
    DirectTouch    = 1
    DependentTouch = 2


class XIDeviceManager(EventSource):
    """
    XInput device manager singleton.
    """

    blacklist = ["Virtual core XTEST pointer",
                 "Virtual core XTEST keyboard",
                 "Power Button"]

    def __new__(cls, *args, **kwargs):
        """
        Singleton magic.
        """
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls, *args, **kwargs)
            cls.self.construct()
        return cls.self

    def __init__(self):
        """
        Called multiple times, do not use. In particular don't
        call base class constructors here.
        """
        pass

    def construct(self):
        """
        Singleton constructor, runs only once.
        """
        EventSource.__init__(self, ["device-event"])

        self._devices = {}

        self._osk_devices = osk.Devices(event_handler=self._device_event_handler)
        self.update_devices()

    def lookup_device_id(self, device_id):
        return self._devices.get(device_id)

    def lookup_config_string(self, device_config_string):
        for device in self.get_pointer_devices():
            if device.get_config_string() == device_config_string:
                return device

    def get_devices(self):
        return self._devices.values()

    def get_pointer_devices(self):
        return [device for device in self._devices.values() \
                if device.is_pointer()]

    def get_slave_pointer_devices(self):
        return [device for device in self.get_pointer_devices() \
                if not device.is_master()]

    def get_master_pointer_devices(self):
        return [device for device in self.get_pointer_devices() \
                if device.is_master()]

    def update_devices(self):
        devices = {}
        for info in self._osk_devices.list():
            device = XIDevice()
            device._device_manager = self
            (
                device.name,
                device.id,
                device.use,
                device.master,
                device.enabled,
                device.vendor,
                device.product,
                touch_mode,
            ) = info
            device.source = XIDevice.classify_source(device.name, device.use,
                                                      touch_mode)
            if not device.name in self.blacklist:
                devices[device.id] = device

        self._devices = devices

    def select_events(self, device, mask):
        self._osk_devices.select_events(device.id, mask)

    def unselect_events(self, device):
        self._osk_devices.unselect_events(device.id)

    def _device_event_handler(self, event):
        """
        Handler Handlerfor XI2 events.
        """
        device = self.lookup_device_id(event.device_id)
        if not device:
            return

        source_device = self.lookup_device_id(event.source_id)
        if not source_device:
            return
        event.set_source_device(source_device)

        self.emit("device-event", event)


class XIDevice(object):
    """
    XInput device.
    """
    name         = None
    id           = None
    use          = None
    master       = None
    enabled      = None
    vendor       = None
    product      = None
    source       = None

    _device_manager = None

    def select_events(self, mask):
        self._device_manager.select_events(self, mask)

    def unselect_events(self):
        self._device_manager.unselect_events(self)

    def get_source(self):
        return self.source

    @staticmethod
    def classify_source(name, use, touch_mode):
        """
        Logic taken from GDK, gdk/x11/gdkdevicemanager-xi2.c
        """
        if use == XIDeviceType.MasterKeyboard or \
           use == XIDeviceType.SlaveKeyboard:
            input_source = Gdk.InputSource.KEYBOARD
        elif use == XIDeviceType.SlavePointer and \
            touch_mode:
            if touch_mode == XITouchMode.DirectTouch:
                input_source = Gdk.InputSource.TOUCHSCREEN
            else:
                input_source = Gdk.InputSource.TOUCHPAD
        else:
            name = name.lower()
            if "eraser" in name:
                input_source = Gdk.InputSource.ERASER
            elif "cursor" in name:
                input_source = Gdk.InputSource.CURSOR
            elif "wacom" in name or \
                 "pen" in name:   # uh oh, false positives?
                input_source = Gdk.InputSource.PEN
            else:
                input_source = Gdk.InputSource.MOUSE
        return input_source

    # methods inherited from Gerd's scanner device.
    def is_master(self):
        """
        Is this a master device?
        """
        return self.use == XIDeviceType.MasterPointer or \
               self.use == XIDeviceType.MasterKeyboard

    def is_pointer(self):
        """
        Is this device a pointer?
        """
        return self.use == XIDeviceType.MasterPointer or \
               self.use == XIDeviceType.SlavePointer

    def get_config_string(self):
        """
        Get a configuration string for the device.
        Format: VID:PID:USE

        """
        return "{:04X}:{:04X}:{!s}".format(self.vendor,
                                           self.product,
                                           self.use)

