# -*- coding: utf-8 -*-

# Copyright © 2012, Gerd Kohlberger
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

import osk
import logging

from Onboard.Config    import Config
from Onboard.KeyCommon import KeyCommon
from Onboard.utils     import Timer, show_new_device_dialog

logger = logging.getLogger(__name__)
config = Config()

"""
Methods and terminology from:
 - Colven, Judge, 2006: Switch access to technology. A comprehensive guide.
 - GOK: The GNOME On-screen Keyboard.
"""

class Chunker(object):
    """
    Base class for all chunker objects.

    Organizes keys into groups and provides methods
    to travers and highlight them.

    Hierarchy:
      Chunker --> FlatChunker --> GroupChunker
    """

    def __init__(self):
        logger.debug("Chunker.__init__()")

        """ Hierarchy of keys (list). """
        self._chunks = None

        """ The index of the active chunk. """
        self._index = 0

        """ The number of chunks at the current level. """
        self._length = 0

        """ A stack of (index, len) tuples. """
        self._path = []

        """ Number of times the current level has been scanned """
        self.cycles = 0

    def __del__(self):
        logger.debug("Chunker.__del__()")

    def chunk(self, layout, layer):
        """
        Abstract: Splits the keys on a layer into chunks
        """
        raise NotImplementedError()

    def get_current_object(self):
        """
        Get the list/key the chunker points to.
        """
        level = self._chunks

        for p in self._path:
            index = p[0]
            level = level[index]

        return level[self._index]

    def _highlight_rec(self, obj, hl, keys):
        """
        Recursively sets the highlight on all keys below obj.
        """
        if isinstance(obj, list):
            for o in obj:
                self._highlight_rec(o, hl, keys)
        else:
            if hl != obj.scanned:
                obj.scanned = hl
                keys.append(obj)

    def highlight(self, hl, root=None):
        """
        Highlight or clear the current chunk.
        """
        keys = []

        if not root:
            root = self.get_current_object()

        self._highlight_rec(root, hl, keys)

        return keys

    def highlight_all(self, hl):
        """
        Highlight or clear all keys
        """
        return self.highlight(hl, self._chunks)

    def next(self):
        """
        Move to the next chunk on the current level.
        """
        next = (self._index + 1) % self._length

        if next < self._index:
            self.cycles += 1

        self._index = next

    def previous(self):
        """
        Move to the previous chunk on the current level.
        """
        prev = (self._index - 1) % self._length

        if prev > self._index:
            self.cycles += 1

        self._index = prev

    def can_descend(self):
        return isinstance(self.get_current_object(), list)

    def descend(self):
        """
        Move down/into the hierarchy.
        Returns False if a key is reached.
        """
        obj = self.get_current_object()

        while isinstance(obj, list):
            self._path.append((self._index, self._length))
            self._index = 0
            self._length = len(obj)
            self.cycles = 0

            if self._length == 1:
                obj = obj[0]
                continue
            return True

        return False

    def get_key(self):
        """
        Returns the current key or None.
        """
        obj = self.get_current_object()

        if not isinstance(obj, list):
            return obj

        return None

    def reset(self):
        """
        Sets the chunker to its initial state.
        """
        self.cycles  = 0
        self._index  = 0
        self._length = len(self._chunks)
        self._path   = []

    def is_reset(self):
        """
        Is the chunker in its initial state.
        """
        return not self._index and \
               not self.cycles and \
               not len(self._path)


class FlatChunker(Chunker):
    """
    Chunks a layer based on key location.
    """
    def compare_keys(self, a, b):
        """
        Sort keys by y and then x position
        """
        rect_a = a.get_border_rect().int()
        rect_b = b.get_border_rect().int()

        y = rect_a.y - rect_b.y
        if y != 0:
            return y

        return rect_a.x - rect_b.x

    def chunk(self, layout, layer):
        """
        Create a list of scannable keys and sort it.
        """
        self._chunks = filter(lambda k: k.scannable, layout.iter_layer_keys(layer, False))
        self._chunks.extend(filter(lambda k: k.scannable, layout.iter_layer_keys(None)))
        self._chunks.sort(cmp=self.compare_keys)
        self._length = len(self._chunks)


class GroupChunker(FlatChunker):
    """
    Chunks a layer based on priority and key location.
    """
    def compare_keys(self, a, b):
        """
        Sort keys by priority and location.
        """
        p = a.scan_priority - b.scan_priority
        if p != 0:
            return p

        return super(GroupChunker, self).compare_keys(a, b)

    def chunk(self, layout, layer):
        """
        Create a nested list of keys.
        """
        last_priority = None
        last_y = None
        chunks = []

        # populates 'self._chunks' with a flat sorted list of keys
        # using the compare_keys method of this class
        super(GroupChunker, self).chunk(layout, layer)

        # creates a new nested chunk list with the following layout:
        # A list of 'priority groups' where each members is a
        # list of 'scan rows' in which each member is a key.
        for key in self._chunks:

            if key.scan_priority != last_priority:
                last_priority = key.scan_priority
                last_y = None
                group = []
                chunks.append(group)

            rect = key.get_border_rect().int()

            if rect.y != last_y:
                last_y = rect.y
                row = []
                group.append(row)

            row.append(key)

        # if we have only 1 priority group, strip it
        if len(chunks) == 1:
            self._chunks = chunks[0]
        else:
            self._chunks = chunks

        self._length = len(self._chunks)


class ScanMode(Timer):
    """
    Base class for all scanning modes.

    Specifies how the scanner moves between chunks of keys
    and when to activate them. Scan mode subclasses define
    a set of actions they support and the base class translates
    input device events into scan actions. Subclasses must
    instantiate a Chunker object that best fits their needs.

    Hierarchy:
        ScanMode --> AutoScan --> UserScan
                              --> OverScan
    """

    """ Scanner actions """
    ACTION_UNHANDLED  = 0
    ACTION_STEP       = 1
    ACTION_STEP_START = 2
    ACTION_STEP_STOP  = 3

    """ Time between key activation flashes (in sec) """
    ACTIVATION_FLASH_INTERVAL = 0.1

    """ Number of key activation flashes """
    ACTIVATION_FLASH_COUNT = 4

    def __init__(self, redraw_callback, activate_callback):
        super(ScanMode, self).__init__()

        logger.debug("ScanMode.__init__()")

        """ Activation timer instance """
        self._activation_timer = Timer()

        """ Counter for key flash animation """
        self._flash = 0

        """ Callback for key redraws """
        self._redraw_callback = redraw_callback

        """ Callback for key activation """
        self._activate_callback = activate_callback

        """ A Chunker instance """
        self.chunker = None

    def __del__(self):
        logger.debug("ScanMode.__del__()")

    def map_actions(self, detail, pressed):
        """
        Abstract: Convert input events into scan actions.
        """
        raise NotImplementedError()

    def do_action(self, action):
        """
        Abstract: Handle scan actions.
        """
        raise NotImplementedError()

    def scan(self):
        """
        Abstract: Move between chunks.
        """
        raise NotImplementedError()

    def create_chunker(self):
        """
        Abstract: Creates a chunker instance.
        """
        raise NotImplementedError()

    def handle_event(self, event, device, detail):
        """
        Translates device events into scan actions.
        """
        # Ignore events during key activation
        if self._activation_timer.is_running():
            return

        # Either a button nr. or a keycode
        if config.scanner.device_map[0] == 'B':
            map = int(config.scanner.device_map[1])
        else:
            map = int(config.scanner.device_map)

        if event in ["ButtonPress", "KeyPress"]:
            action = self.map_actions(map, detail, True)
        elif event in ["ButtonRelease", "KeyRelease"]:
            action = self.map_actions(map, detail, False)
        else:
            action = self.ACTION_UNHANDLED

        if action != self.ACTION_UNHANDLED:
            self.do_action(action)

    def on_timer(self):
        """
        Override: Timer() callback.
        """
        return self.scan()

    def max_cycles_reached(self):
        """
        Checks if the maximum number of scan cycles is reached.
        """
        return self.chunker.cycles >= config.scanner.cycles

    def set_layer(self, layout, layer):
        """
        Set the layer that should be scanned.
        """
        self.reset()
        self.chunker = self.create_chunker()
        self.chunker.chunk(layout, layer)

    def _on_activation_timer(self, key):
        """
        Timer callback: flashes the key and finally activates it.
        """
        if self._flash > 0:
            key.scanned = not key.scanned
            self._flash -= 1
            self.redraw([key])
            return True
        else:
            self._activate_callback(key)
            self.chunker.reset()
            return False

    def activate(self):
        """
        Triggers animation and then activates the key.
        """
        key = self.chunker.get_key()
        if key:
            self._flash = self.ACTIVATION_FLASH_COUNT
            self._activation_timer.start(self.ACTIVATION_FLASH_INTERVAL,
                                         self._on_activation_timer,
                                         key)

    def reset(self):
        """
        Stop scanning and clear all highlights.
        """
        if self.is_running():
            self.stop()

        if self.chunker:
            keys = self.chunker.highlight_all(False)
            self.redraw(keys)

    def redraw(self, keys=None):
        """
        Update a key or the entire keyboard.
        """
        self._redraw_callback(keys)

    def finalize(self):
        self.reset()
        # release ref on _on_activation_timer callback
        self._activation_timer = None


class AutoScan(ScanMode):
    """
    Automatic scan mode for 1 switch. Starts scanning on
    switch press and moves through a hierarchy of chunks.
    """
    def create_chunker(self):
        return GroupChunker()

    def map_actions(self, map, detail, is_press):
        if detail == map and is_press:
            return self.ACTION_STEP

        return self.ACTION_UNHANDLED

    def scan(self):
        keys = self.chunker.highlight(False)
        self.redraw(keys)
        self.chunker.next()

        if self.max_cycles_reached():
            self.chunker.reset()
            return False
        else:
            keys = self.chunker.highlight(True)
            self.redraw(keys)
            return True

    def do_action(self, action):
        if not self.is_running():
            # Start scanning
            keys = self.chunker.highlight(True)
            self.redraw(keys)
            self.start(config.scanner.interval)
        else:
            # Subsequent clicks
            self.stop()
            keys = self.chunker.highlight(False)
            self.redraw(keys)

            if self.chunker.descend():
                # Move one level down
                keys = self.chunker.highlight(True)
                self.redraw(keys)
                self.start(config.scanner.interval)
            else:
                # Activate
                self.activate()


class UserScan(AutoScan):
    """
    Automatic scan mode for 1 switch. Like AutoScan but
    the scanner progresses only during switch press.
    """
    def map_actions(self, map, detail, is_press):
        if detail == map and is_press:
            return self.ACTION_STEP_START
        elif detail == map and not is_press:
            return self.ACTION_STEP_STOP

        return self.ACTION_UNHANDLED

    def do_action(self, action):
        if action == self.ACTION_STEP_START:
            if not self.chunker.is_reset():
                # Every press except the initial
                keys = self.chunker.highlight(False)
                self.redraw(keys)
                self.chunker.descend()

            keys = self.chunker.highlight(True)
            self.redraw(keys)
            self.start(config.scanner.interval)

        elif action == self.ACTION_STEP_STOP:
            # Every release
            self.stop()
            if not self.chunker.can_descend():
                # Activate
                keys = self.chunker.highlight(False)
                self.redraw(keys)
                self.activate()


class OverScan(AutoScan):
    """
    Automatic scan mode for 1 switch. Does fast forward
    scanning in a flat hierarchy with slow backtracking.
    """
    def __init__(self, redraw_callback, activate_callback):
        super(OverScan, self).__init__(redraw_callback, activate_callback)

        self._step = -1
        self._fast = True

    def create_chunker(self):
        return FlatChunker()

    def scan(self):
        self.redraw(self.chunker.highlight(False))
        if self._step > 0:
            # Backtrack
            self.chunker.previous()
            self._step -= 1
            self.redraw(self.chunker.highlight(True))
        else:
            # Fast forward
            self.chunker.next()
            if self.max_cycles_reached():
                # Abort
                self.chunker.reset()
                return False
            self.redraw(self.chunker.highlight(True))
            if not self._fast:
                self.stop()
                self.do_action(None)
        return True

    def do_action(self, action):
        if not self.is_running():
            # Start
            self._fast = True
            self._step = -1
            self.redraw(self.chunker.highlight(True))
            self.start(config.scanner.interval_fast)
        else:
            # Subsequent clicks
            if self._step >= 0:
                # Activate
                self.stop()
                self.redraw(self.chunker.highlight(False))
                self.activate()
            else:
                # Backtrack
                self._step = config.scanner.backtrack
                self._fast = False
                self.chunker.cycles = 0
                self.start(config.scanner.interval)


class Scanner(object):
    """
    Main controller class for keyboard scanning. Manages
    ScanMode and ScanDevices objects and provides the
    public interface for the scanner.
    """

    """ Scan modes """
    MODE_AUTOSCAN = 0
    MODE_USERSCAN = 1
    MODE_OVERSCAN = 2

    def __init__(self, redraw_callback, activate_callback):
        logger.debug("Scanner.__init__()")

        """ A scan mode instance """
        self.mode = self._get_scan_mode(config.scanner.mode,
                                        redraw_callback,
                                        activate_callback)

        """ A scan device instance """
        self.device = ScanDevice(self.mode.handle_event)

        """ The active layer """
        self.layer = None

        """ The keyboard layout """
        self.layout = None

        config.scanner.mode_notify_add(self._mode_notify)

    def __del__(self):
        logger.debug("Scanner.__del__()")

    def _mode_notify(self, mode):
        """
        Callback for scanner.mode configuration changes.
        """
        rcb = self.mode._redraw_callback
        acb = self.mode._activate_callback

        self.mode.finalize()
        self.mode = self._get_scan_mode(mode, rcb, acb)
        self.mode.set_layer(self.layout, self.layer)

        self.device._event_handler = self.mode.handle_event

    def _get_scan_mode(self, mode, redraw_callback, activate_callback):
        """
        Create a ScanMode instance for 'mode'.
        """
        if mode == self.MODE_AUTOSCAN:
            return AutoScan(redraw_callback, activate_callback)

        elif mode == self.MODE_USERSCAN:
            return UserScan(redraw_callback, activate_callback)

        elif mode == self.MODE_OVERSCAN:
            return OverScan(redraw_callback, activate_callback)

        else:
            logger.warning("Unknown scan mode requested.")
            return None

    def update_layer(self, layout, layer):
        """
        Notifies the scanner the active layer has changed.
        """
        self.layout = layout
        self.layer = layer
        self.mode.set_layer(layout, layer)

    def finalize(self):
        """
        Call this before closing Onboard to ensure devices are reattached.
        """
        config.scanner._mode_notify_callbacks.remove(self._mode_notify)
        self.device.finalize()
        self.mode.finalize()


class ScanDevice(object):
    """
    Input device manager class.

    Manages input devices on the system and deals with
    PnP related event. The actual press/release events
    are forwarded to a ScanMode instance.
    """

    """ XI2 device types """
    MASTER_POINTER  = 1
    MASTER_KEYBOARD = 2
    SLAVE_POINTER   = 3
    SLAVE_KEYBOARD  = 4
    FLOATING_SLAVE  = 5

    """ XI2 device info fields """
    NAME    = 0
    ID      = 1
    SOURCE  = 2
    USE     = 3
    MASTER  = 4
    ENABLED = 5

    """ Default virtual core ids (masters) """
    DEFAULT_VCP_ID = 2
    DEFAULT_VCK_ID = 3

    """ Device name blacklist """
    blacklist = ["Virtual core pointer",
                 "Virtual core keyboard",
                 "Virtual core XTEST pointer",
                 "Virtual core XTEST keyboard",
                 "Power Button"]

    """ Configuration names for core/master devices """
    core_names = ["Default pointer",
                  "Default keyboard"]

    def __init__(self, event_handler):
        logger.debug("ScanDevice.__init__()")

        """ Opened device tuple (device id, master id) """
        self._opened = None

        """ Whether the opened device is detached """
        self._floating = False

        """ Event handler for device events """
        self._event_handler = event_handler

        """ Devices object from osk extension """
        self.devices = osk.Devices(event_handler=self._device_event_handler)

        config.scanner.device_name_notify_add(self._device_name_notify)
        config.scanner.device_detach_notify_add(self._device_detach_notify)

        self._device_name_notify(config.scanner.device_name)

    def __del__(self):
        logger.debug("ScanDevice.__del__()")

    def _device_event_handler(self, event, device_id, detail):
        """
        Handler for XI2 events.
        """
        if event == "DeviceAdded":
            info = self.devices.get_info(device_id)
            if not self.is_master(info):
                name = [info[self.NAME], ':', str(info[self.USE])]
                if config.scanner.device_name == ''.join(name):
                    self.open(info[self.ID], info[self.MASTER], info[self.USE])
                else:
                    show_new_device_dialog(info[self.NAME],
                                           info[self.USE],
                                           self.is_pointer(info))

        elif event == "DeviceRemoved":
            if self._opened and self._opened[0] == device_id:
                self._opened = None
                self._floating = False
                config.scanner.device_name = core_names[0]

        elif event == "DeviceChanged":
            if config.scanner.device_name == self.core_names[1]:
                if self._opened[1] == device_id:
                    info = self.devices.get_info(detail)
                    if self.is_useable(info):
                        self.open(detail, device_id, info[self.USE])

        else:
            self._event_handler(event, device_id, detail)

    def _device_detach_notify(self, detach):
        """
        Callback for the scanner.device_detach configuration changes.
        """
        if detach:
            if not self._floating:
                self.devices.detach(self._opened[0])
                self._floating = True
        else:
            if self._floating:
                self.devices.attach(*self._opened)
                self._floating = False

    def _device_name_notify(self, name):
        """
        Callback for the scanner.device_name configuration changes.
        """
        if name == self.core_names[0]:
            self.open(self.DEFAULT_VCP_ID,
                      self.DEFAULT_VCP_ID,
                      self.MASTER_POINTER)

        elif name == self.core_names[1]:
            source = self.devices.get_info(self.DEFAULT_VCK_ID)[self.SOURCE]
            self.open(source, self.DEFAULT_VCK_ID, self.SLAVE_KEYBOARD)

        else:
            config_info = name.split(':')

            if len(config_info) != 2:
                logger.warning("Malformed device-name string.")
                config.scanner.device_name = self.core_names[0]
                # it seems config notifications don't work from
                # within the handler, so we recurse.
                self._device_name_notify(config.scanner.device_name)
                return

            for info in self.devices.list():
                if info[self.NAME] == config_info[0] and \
                   info[self.USE] == int(config_info[1]):
                    self.open(info[self.ID], info[self.MASTER], info[self.USE])
                    break

    def open(self, device_id, master_id, use):
        """
        Select for events and optionally detach it from its master device.
        """
        self.close()

        select = use == self.MASTER_POINTER or \
                 use == self.SLAVE_POINTER

        try:
            self.devices.open(device_id, select, not select)
            self._opened = (device_id, master_id)
        except:
            logger.warning("Failed to open device", device_id)
            return

        if config.scanner.device_detach:
            self.devices.detach(device_id)
            self._floating = True

    def close(self):
        """
        Stop using the currently open device.
        """
        if self._floating:
            self.devices.attach(*self._opened)
            self._floating = False

        if self._opened:
            self.devices.close(self._opened[0])
            self._opened = None

    def finalize(self):
        config.scanner._device_name_notify_callbacks.remove(self._device_name_notify)
        config.scanner._device_detach_notify_callbacks.remove(self._device_detach_notify)
        self.close()
        self._event_handler = None
        self.devices = None

    @staticmethod
    def is_master(info):
        """
        Is this a master device?
        """
        return info[ScanDevice.USE] == ScanDevice.MASTER_POINTER or \
               info[ScanDevice.USE] == ScanDevice.MASTER_KEYBOARD

    @staticmethod
    def is_pointer(info):
        """
        Is this device a pointer?
        """
        return info[ScanDevice.USE] == ScanDevice.MASTER_POINTER or \
               info[ScanDevice.USE] == ScanDevice.SLAVE_POINTER

    @staticmethod
    def is_useable(info):
        """
        Checks whether the device is enabled and not blacklisted.
        """
        return (info[ScanDevice.NAME] not in ScanDevice.blacklist) and \
                info[ScanDevice.ENABLED]

    @staticmethod
    def list():
        """
        List of useable devices.
        """
        return filter(ScanDevice.is_useable, osk.Devices().list())

