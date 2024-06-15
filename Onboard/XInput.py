# -*- coding: utf-8 -*-

# Copyright © 2012-2017 marmuta <marmvta@gmail.com>
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

import sys
import copy

from Onboard.Version        import require_gi_versions
require_gi_versions()
from gi.repository          import Gdk

from Onboard.utils          import EventSource, unicode_str
from Onboard.definitions    import UINPUT_DEVICE_NAME

import Onboard.osk as osk

import logging
_logger = logging.getLogger(__name__)


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
    SlaveAttached     = 1102
    SlaveDetached     = 1103

    HierarchyEvents = (DeviceAdded, DeviceRemoved, SlaveAttached, SlaveDetached)


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

    blacklist = ("Virtual core XTEST keyboard",
                 UINPUT_DEVICE_NAME,
                 "Power Button")
    last_device_blacklist = ("Virtual core XTEST pointer")

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
        EventSource.__init__(self, ["device-event", "device-grab",
                                    "devices-updated"])

        self._devices = {}
        self._osk_devices = None
        try:
            self._osk_devices = osk.Devices(event_handler = \
                                            self._on_device_event)
        except Exception as ex:
            _logger.warning("Failed to create osk.Devices: " + \
                            unicode_str(ex))

        self._last_motion_device_id = None
        self._last_click_device_id = None
        self._last_device_blacklist_ids = []

        self._grabbed_devices_ids = set()

        if self.is_valid():
            self.update_devices()

    def is_valid(self):
        return not self._osk_devices is None

    def lookup_device_id(self, device_id):
        return self._devices.get(device_id)

    def lookup_config_string(self, device_config_string):
        for device in self.get_pointer_devices():
            if device.get_config_string() == device_config_string:
                return device

    def get_client_pointer(self):
        """ Return client pointer device """
        device_id = self._osk_devices.get_client_pointer()
        return self.lookup_device_id(device_id)

    def get_client_keyboard(self):
        """ Return client keyboard device """
        client_pointer = self.get_client_pointer()
        device_id = client_pointer.attachment
        return self.lookup_device_id(device_id)

    def get_devices(self):
        return self._devices.values()

    def get_pointer_devices(self):
        return [device for device in self._devices.values() \
                if device.is_pointer()]

    def get_client_pointer_slaves(self):
        """
        All slaves of the client pointer, with and without device grabs.
        """
        client_pointer = self.get_client_pointer()
        return [device for device in self.get_pointer_devices() \
                if not device.is_master() and \
                   device.attachment == client_pointer.id]

    def get_client_pointer_attached_slaves(self):
        """
        Slaves that are currently attached to the client pointer.
        """
        devices = self.get_client_pointer_slaves()
        devices = [d for d in devices if not d.is_floating() and \
                                         not self.is_grabbed(d)]
        return devices

    def get_keyboard_devices(self):
        return [device for device in self._devices.values() \
                if device.is_keyboard()]

    def get_client_keyboard_slaves(self):
        """
        All slaves of the keyboard paired with the client pointer,
        with and without device grabs.
        """
        client_keyboard = self.get_client_keyboard()
        return [device for device in self.get_keyboard_devices() \
                if not device.is_master() and \
                   device.attachment == client_keyboard.id]

    def get_client_keyboard_attached_slaves(self):
        """
        Slaves that are currently attached to the keyboard paired
        with the client pointer.
        """
        devices = self.get_client_keyboard_slaves()
        devices = [d for d in devices if not d.is_floating() and \
                                         not self.is_grabbed(d)]
        return devices

    def get_master_pointer_devices(self):
        return [device for device in self.get_pointer_devices() \
                if device.is_master()]

    def update_devices(self):
        devices = {}
        self._last_device_blacklist_ids = []

        for info in self._osk_devices.list():
            device = XIDevice()
            device._device_manager = self
            (
                device.name,
                device.id,
                device.use,
                device.attachment,
                device.enabled,
                device.vendor,
                device.product,
                device.touch_mode,
            ) = info
            device.source = XIDevice.classify_source(device.name, device.use,
                                                     device.touch_mode)

            if sys.version_info.major == 2:
                device.name = unicode_str(device.name)

            if not device.name in self.blacklist:
                devices[device.id] = device

            if device.name in self.last_device_blacklist:
                self._last_device_blacklist_ids.append(device.id)

        self._devices = devices

        self._last_click_device_id = None
        self._last_motion_device_id = None

        # notify listeners about the previous devices becoming invalid
        self.emit("devices-updated")

    def select_events(self, window, device, mask):
        if window is None:  # use root window?
            xid = 0
        else:
            xid = window.get_xid()
            if not xid:
                return False

        self._osk_devices.select_events(xid, device.id, mask)
        return True

    def unselect_events(self, window, device):
        if window is None:  # use root window?
            xid = 0
        else:
            xid = window.get_xid()
            if not xid:
                return False

        self._osk_devices.unselect_events(xid, device.id)
        return True

    def attach_device(self, device, master_id):
        self.attach_device_id(device.id, master_id)

    def detach_device(self, device):
        self.detach_device_id(device.id)

    def attach_device_id(self, device_id, master_id):
        self._osk_devices.attach(device_id, master_id)

    def detach_device_id(self, device_id):
        self._osk_devices.detach(device_id)

    def grab_device(self, device):
        self.grab_device_id(device.id) # raises osk.error
        self.emit("device-grab", device, True)

    def ungrab_device(self, device):
        self.ungrab_device_id(device.id) # raises osk.error
        self.emit("device-grab", device, False)

    def is_grabbed(self, device):
        return device.id in self._grabbed_devices_ids

    def grab_device_id(self, device_id):
        self._osk_devices.grab_device(device_id, 0)

        assert(not device_id in self._grabbed_devices_ids)
        self._grabbed_devices_ids.add(device_id)

    def ungrab_device_id(self, device_id):
        self._grabbed_devices_ids.discard(device_id)
        self._osk_devices.ungrab_device(device_id)

    def get_last_click_device(self):
        id = self._last_click_device_id
        if id is None:
            return None
        return self.lookup_device_id(id)

    def get_last_motion_device(self):
        id = self._last_motion_device_id
        if id is None:
            return None
        return self.lookup_device_id(id)

    def _on_device_event(self, event):
        """
        Handler for XI2 events.
        """
        event_type = event.xi_type
        device_id = event.device_id
        source_id = event.source_id

        # update our device objects on changes to the device hierarchy
        if event_type in XIEventType.HierarchyEvents or \
           event_type == XIEventType.DeviceChanged:
            self.update_devices()

        # simulate gtk source device
        if source_id:
            source_device = self.lookup_device_id(source_id)
            if not source_device:
                return
        else:
            source_device = None
        event.set_source_device(source_device)

        ## debug, simulate touch-screen
        if 0 and \
           device_id == 11:
            if not self._disguise_as_touch_event(event, False):
                return

        # remember recently used device ids for CSFloatingSlave
        if not source_id in self._last_device_blacklist_ids:
            if event_type == XIEventType.Motion:
                self._last_motion_device_id = source_id
            elif event_type == XIEventType.ButtonPress or \
                 event_type == XIEventType.TouchBegin:
                self._last_click_device_id = source_id

        # forward the event to all listeners
        for callback in self._callbacks["device-event"]:
            # Copy event to isolate callbacks from each other (LP: 1421840)
            ev = copy.copy(event)
            callback(ev)

    def _disguise_as_touch_event(self, event, wacom_mode=False):
        """
        Disguise a pointer event as touch event.
        For debugging purposes only.

        Set wacom_mode=True to simulate pointer events coming
        from a "touch screen" device that only sends pointer events.
        This is the default case for wacom touch screens due to
        gestures being enabled, see LP #1297692.
        """
        device = self.lookup_device_id(event.source_id)
        device.name         = "Touch-Screen"
        device.source       = Gdk.InputSource.TOUCHSCREEN
        device.touch_mode   = XITouchMode.DirectTouch

        if event.xi_type == XIEventType.Motion and \
           not event.state & (Gdk.ModifierType.BUTTON1_MASK | \
                                Gdk.ModifierType.BUTTON2_MASK | \
                                Gdk.ModifierType.BUTTON3_MASK):
            return False  # discard event

        if not wacom_mode:
            if event.xi_type == XIEventType.ButtonPress:
                event.xi_type = XIEventType.TouchBegin
                event.type = Gdk.EventType.TOUCH_BEGIN
            if event.xi_type == XIEventType.ButtonRelease:
                event.xi_type = XIEventType.TouchEnd
                event.type = Gdk.EventType.TOUCH_END
            if event.xi_type == XIEventType.Motion:
                event.xi_type = XIEventType.TouchUpdate
                event.type = Gdk.EventType.TOUCH_UPDATE

            event.sequence = 10  # single touch only

        event.button = 1

        return True  # allow event


class XIDevice(object):
    """
    XInput device wrapper.
    """
    name         = None
    id           = None
    use          = None
    attachment   = None  # master for slaves, paired master for masters
    enabled      = None
    vendor       = None
    product      = None
    source       = None
    touch_mode   = None

    _device_manager = None

    def __repr__(self):
        return "{}(id={}, attachment={}, name={}, source={} )" \
                .format(type(self).__name__,
                        repr(self.id),
                        repr(self.attachment),
                        repr(self.name),
                        repr(self.source),
                       )

    def __str__(self):
        return "{}(id={} attachment={} use={} touch_mode={} source={} name={} " \
               "vendor=0x{:04x} product=0x{:04x} enabled={})" \
                .format(type(self).__name__,
                        self.id,
                        self.attachment,
                        self.use,
                        self.touch_mode,
                        self.get_source().value_name,
                        self.name,
                        self.vendor,
                        self.product,
                        self.enabled,
                       )

    def get_source(self):
        """
        Return Gdk.InputSource for compatibility with Gtk event handling.
        """
        return self.source

    @staticmethod
    def classify_source(name, use, touch_mode):
        """
        Determine the source type (Gdk.InputSource) of the device.
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
            name = unicode_str(name.lower())
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

    def is_touch_screen(self):
        """
        Touch screen device?
        """
        return self.source == Gdk.InputSource.TOUCHSCREEN

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

    def is_keyboard(self):
        """
        Is this device a keyboard?
        """
        return self.use == XIDeviceType.MasterKeyboard or \
               self.use == XIDeviceType.SlaveKeyboard

    def is_floating(self):
        """
        Is this device detached?
        """
        return self.use == XIDeviceType.FloatingSlave

    def get_config_string(self):
        """
        Get a configuration string for the device.
        Format: VID:PID:USE

        """
        return "{:04X}:{:04X}:{!s}".format(self.vendor,
                                           self.product,
                                           self.use)

class XIDeviceEventLogger:
    """
    Facilities for logging device events.
    Has little overhead when logging is disabled.
    """

    def __init__(self):
        if not _logger.isEnabledFor(logging.DEBUG):
            self.log_event = self._log_event_stub

    def _log_device_event(self, event):
        if not event.xi_type in [ XIEventType.TouchUpdate,
                                  XIEventType.Motion]:
            self.log_event("Device event: dev_id={} src_id={} xi_type={} "
                          "xid_event={}({}) x={} y={} x_root={} y_root={} "
                          "button={} state={} sequence={}"
                          "".format(event.device_id,
                                    event.source_id,
                                    event.xi_type,
                                    event.xid_event,
                                    self.get_xid(),
                                    event.x, event.y,
                                    event.x_root, event.y_root,
                                    event.button, event.state,
                                    event.sequence,
                                   )
                         )

            device = event.get_source_device()
            self.log_event("Source device: " + str(device))

    @staticmethod
    def log_event(msg, *args):
        _logger.event(msg.format(*args))

    @staticmethod
    def _log_event_stub(msg, *args):
        pass


