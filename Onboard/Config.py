"""
File containing Config singleton.
"""

### Logging ###
import logging
__logger__ = logging.getLogger("Config")
__logger__.setLevel(logging.WARNING)
###############

import gconf
import os
import sys

from optparse import OptionParser

from Onboard.utils import get_install_dir

KEYBOARD_WIDTH_GCONF_KEY    = "/apps/onboard/width"
KEYBOARD_HEIGHT_GCONF_KEY   = "/apps/onboard/height"
LAYOUT_FILENAME_GCONF_KEY   = "/apps/onboard/layout_filename"
X_POSITION_GCONF_KEY        = "/apps/onboard/horizontal_position"
Y_POSITION_GCONF_KEY        = "/apps/onboard/vertical_position"
SCANNING_GCONF_KEY          = "/apps/onboard/enable_scanning"
SCANNING_INTERVAL_GCONF_KEY = "/apps/onboard/scanning_interval"
SNIPPETS_GCONF_KEY          = "/apps/onboard/snippets"
SHOW_TRAYICON_GCONF_KEY     = "/apps/onboard/trayicon"

KEYBOARD_DEFAULT_HEIGHT   = 800
KEYBOARD_DEFAULT_WIDTH    = 300

SCANNING_DEFAULT_INTERVAL = 750

GTK_KBD_MIXIN_MOD = "Onboard.KeyboardGTK"
GTK_KBD_MIXIN_CLS = "KeyboardGTK"
CLUTTER_KBD_MIXIN_MOD = "Onboard.KeyboardClutter"
CLUTTER_KBD_MIXIN_CLS = "KeyboardClutter"

class Config (object):
    """
    Singleton Class to encapsulate the gconf stuff and check values.
    """
    _gconf_client = gconf.client_get_default()

    """ 
    String representation of the module containing the Keyboard mixin
    used to draw keyboard
    """
    _kbd_render_mixin_mod = GTK_KBD_MIXIN_MOD

    """ 
    String representation of the keyboard mixin used to draw keyboard.
    """
    _kbd_render_mixin_cls = GTK_KBD_MIXIN_CLS

    """ Width of sidebar buttons """
    SIDEBARWIDTH = 60

    def __new__(cls, *args, **kwargs): 
        """
        Singleton magic.
        """
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls)
            cls.self._init()
        return cls.self

    def _init(self):
        """
        Singleton constructor, should only run once.
        """

        __logger__.info("Parsing commandline options")
        parser = OptionParser()
        parser.add_option("-l", "--layout", dest="filename",
                help="Specify layout .sok file")
        parser.add_option("-x", type="int", dest="x", help="x coord of window")
        parser.add_option("-y", type="int", dest="y", help="y coord of window")
        parser.add_option("-s", "--size", dest="size",
                help="size widthxheight")
        parser.add_option("--use-clutter", action="store_true", 
            dest="clutter", help="Use clutter OpenGL interface (EXPERIMENTAL)")
        options = parser.parse_args()[0]

        self._gconf_client.add_dir("/apps/onboard", gconf.CLIENT_PRELOAD_NONE)
        self._gconf_client.notify_add(KEYBOARD_WIDTH_GCONF_KEY,
                self._geometry_notify_cb)
        self._gconf_client.notify_add(KEYBOARD_HEIGHT_GCONF_KEY, 
                self._geometry_notify_cb)

        if (options.size):
            size = options.size.split("x")
            self.width  = int(size[0])
            self.height = int(size[1])

        if (options.x):
            self.x_position = int(options.x)
        if (options.y):
            self.y_position = int(options.y)

        # Find layout
        if options.filename:
            filename = options.filename
        else:
            filename = self._gconf_client.get_string(LAYOUT_FILENAME_GCONF_KEY)

        if filename and not os.path.exists(filename):
            __logger__.warning("Can't load %s loading default layout instead" %
                filename)
            filename = ''

        if not filename:
            filename = os.path.join(get_install_dir(), 
                    "layouts", "Default.sok")

        if not os.path.exists(filename):
            raise Exception("Unable to find layout %s" % filename)
        self.__filename = filename

        self._gconf_client.notify_add(LAYOUT_FILENAME_GCONF_KEY,
                self._layout_filename_notify_cb)
        self._gconf_client.notify_add(X_POSITION_GCONF_KEY,
                self._position_notify_cb)
        self._gconf_client.notify_add(Y_POSITION_GCONF_KEY,
                self._position_notify_cb)
        self._gconf_client.notify_add(SCANNING_GCONF_KEY,
                self._scanning_notify_cb)
        self._gconf_client.notify_add(SCANNING_INTERVAL_GCONF_KEY,
                self._scanning_interval_notify_cb)
        self._gconf_client.notify_add(SHOW_TRAYICON_GCONF_KEY,
                self._show_trayicon_notify_cb)

        if options.clutter:
            __logger__.info("Rendering with Clutter")
            self._kbd_render_mixin_mod = CLUTTER_KBD_MIXIN_MOD
            self._kbd_render_mixin_cls = CLUTTER_KBD_MIXIN_CLS
        else:
            __logger__.info("Rendering with GTK")


    ######## Layout #########
    _layout_filename_notify_callbacks   = []
    def layout_filename_notify_add(self, callback):
        """
        Register callback to be run when layout filename changes.

        Callbacks are called with the layout filename as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._layout_filename_notify_callbacks.append(callback)

    def _layout_filename_notify_cb(self, client, cxion_id, entry, 
            user_data):
        """
        Recieve layout change notifications from gconf and check the file is
        valid before calling callbacks.
        """
        filename = self._gconf_client.get_string(LAYOUT_FILENAME_GCONF_KEY)
        if not os.path.exists(filename):
            __logger__.warning("layout %s does not exist" % filename)
        else:
            self.__filename = filename

        for callback in self._layout_filename_notify_callbacks:
            callback(filename)

    def _get_layout_filename(self):
        """
        Layout filename getter.
        """
        return self.__filename
    def _set_layout_filename(self, value):
        """
        Layout filename setter, TODO.

        @type  value: str
        @param value: Absolute path to the layout description file.
        """
        raise NotImplementedError()
    layout_filename = property(_get_layout_filename, _set_layout_filename)

    ####### Geometry ########
    _geometry_notify_callbacks = []
    def _get_keyboard_height(self):
        """
        Keyboard height getter, check height is greater than 1.
        """
        height = self._gconf_client.get_int(KEYBOARD_HEIGHT_GCONF_KEY)
        if height and height > 1:
            return height
        else:
            return KEYBOARD_DEFAULT_HEIGHT
    def _set_keyboard_height(self, value):
        """
        Keyboard height setter, check height is greater than 1.
        """
        if value > 1:
            self._gconf_client.set_int(KEYBOARD_HEIGHT_GCONF_KEY, value)
    keyboard_height = property(_get_keyboard_height, _set_keyboard_height)

    def _get_keyboard_width(self):
        """
        Keyboard width getter, check width is greater than 1.
        """
        width = self._gconf_client.get_int(KEYBOARD_WIDTH_GCONF_KEY)
        if width and width > 1:
            return width
        else:
            return KEYBOARD_DEFAULT_WIDTH
    def _set_keyboard_width(self, value):
        """
        Keyboard width setter, check width is greater than 1.
        """
        if value > 1:
            self._gconf_client.set_int(KEYBOARD_WIDTH_GCONF_KEY, value)
    keyboard_width  = property(_get_keyboard_width, _set_keyboard_width)

    def geometry_notify_add(self, callback):
        """
        Register callback to be run when the keyboard geometry changes.

        Callbacks are called with the new geomtery as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._geometry_notify_callbacks.append(callback)

    def _geometry_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve geometry change notifications from gconf and run callbacks.
        """
        for callback in self._geometry_notify_callbacks:
            callback(self.keyboard_width, self.keyboard_height)

    ####### Position ########
    _position_notify_callbacks = []
    def _get_x_position(self):
        """
        Keyboard x position getter.
        """
        return self._gconf_client.get_int(X_POSITION_GCONF_KEY)
    def _set_x_position(self, value):
        """
        Keyboard x position setter.
        """
        self._gconf_client.set_int(X_POSITION_GCONF_KEY, value)
    x_position = property(_get_x_position, _set_x_position)

    def _get_y_position(self):
        """
        Keyboard y position getter.
        """
        return self._gconf_client.get_int(Y_POSITION_GCONF_KEY)
    def _set_y_position(self, value):
        """
        Keyboard y position setter.
        """
        self._gconf_client.set_int(Y_POSITION_GCONF_KEY, value)
    y_position = property(_get_y_position, _set_y_position)

    def position_notify_add(self, callback):
        """
        Register callback to be run when the keyboard position changes.

        Callbacks are called with the new position as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._position_notify_callbacks.append(callback)

    def _position_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve position change notifications from gconf and run callbacks.
        """
        for callback in self._position_notify_callbacks:
            callback(self.x_position, self.y_position)

    ####### Scanning ########
    _scanning_callbacks = []
    def _get_scanning(self):
        """
        Scanning mode active getter.
        """
        return self._gconf_client.get_bool(SCANNING_GCONF_KEY)
    def _set_scanning(self, value):
        """
        Scanning mode active setter.
        """
        return self._gconf_client.set_bool(SCANNING_GCONF_KEY, value)
    scanning = property(_get_scanning, _set_scanning)

    def scanning_notify_add(self, callback):
        """
        Register callback to be run when the scanning mode changes.

        Callbacks are called with the new value as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._scanning_callbacks.append(callback)

    def _scanning_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve scanning mode change notifications from gconf and run callbacks.
        """
        for callback in self._scanning_callbacks:
            callback(self.scanning)

    ## Scanning interval ####
    _scanning_interval_callbacks = []
    def _get_scanning_interval(self):
        """
        Scanning interval time getter.
        """
        interval = self._gconf_client.get_int(SCANNING_INTERVAL_GCONF_KEY)
        if interval and interval > 0:
            return interval
        else:
            return SCANNING_DEFAULT_INTERVAL
    def _set_scanning_interval(self, value):
        """
        Scanning interval time getter.
        """
        return self._gconf_client.set_int(SCANNING_INTERVAL_GCONF_KEY, value)
    scanning_interval = property(_get_scanning_interval, _set_scanning_interval)

    def scanning_interval_notify_add(self, callback):
        """
        Register callback to be run when the scanning interval time changes.

        Callbacks are called with the new time as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._scanning_interval_callbacks.append(callback)

    def _scanning_interval_notify_cb(self, client, cxion_id, entry, 
            user_data):
        """
        Recieve scanning interval change notifications from gconf and run
        callbacks.
        """
        for callback in self._scanning_interval_callbacks:
            callback(self.scanning_interval)

    ####### Snippets #######
    _snippets_callbacks = []
    def _get_snippets(self):
        """
        List of snippets getter.
        """
        return self._gconf_client.get_list(SNIPPETS_GCONF_KEY,
                gconf.VALUE_STRING)
    def _set_snippets(self, value):
        """
        List of snippets setter.
        """
        self._gconf_client.set_list(SNIPPETS_GCONF_KEY, gconf.VALUE_STRING,
                value)
    snippets = property(_get_snippets, _set_snippets)

    def set_snippet(self, index, value):
        """
        Set a snippet in the snippet list.  Enlarge the list if not big
        enough.

        @type  index: int
        @param index: index of the snippet to set.
        @type  value: str
        @param value: Contents of the new snippet.
        """
        snippets = self.snippets
        for n in range(1 + index - len(snippets)):
            snippets.append("")
        snippets[index] = value
        self.snippets = snippets

    def snippets_notify_add(self, callback):
        """
        Register callback to be run when the snippets list changes.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._snippets_callbacks.append(callback)

    def _snippets_notify_cb(self, client, cxion_id, entry, 
            user_data):
        """
        Recieve snippets list notifications from gconf and run callbacks.
        """
        for callback in self._snippets_callbacks:
            callback(self.snippets)

    ####### Trayicon #######
    _show_trayicon_callbacks = []
    def _get_show_trayicon(self):
        """
        Trayicon visible getter.
        """
        return self._gconf_client.get_bool(SHOW_TRAYICON_GCONF_KEY)
    def _set_show_trayicon(self, value):
        """
        Trayicon visible setter.
        """
        return self._gconf_client.set_bool(SHOW_TRAYICON_GCONF_KEY, value)
    show_trayicon = property(_get_show_trayicon, _set_show_trayicon)

    def show_trayicon_notify_add(self, callback):
        """
        Register callback to be run when the trayicon visibility changes.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._show_trayicon_callbacks.append(callback)

    def _show_trayicon_notify_cb(self, client, cxion_id, entry, 
            user_data):
        """
        Recieve trayicon visibility notifications from gconf and run callbacks.
        """
        for callback in self._show_trayicon_callbacks:
            callback(self.show_trayicon)

    def _get_kbd_render_mixin(self):
        __import__(self._kbd_render_mixin_mod)
        return getattr(sys.modules[self._kbd_render_mixin_mod],
                self._kbd_render_mixin_cls)
    kbd_render_mixin = property(_get_kbd_render_mixin)
