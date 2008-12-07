#Config singleton

### Logging ###
import logging
logger = logging.getLogger("Config")
logger.setLevel(logging.WARNING)
###############

import gconf
import os

from optparse import OptionParser

from Onboard.utils import get_install_dir

KEYBOARD_WIDTH_GCONF_KEY    = "/apps/onboard/width"
KEYBOARD_HEIGHT_GCONF_KEY   = "/apps/onboard/height"
LAYOUT_FILENAME_GCONF_KEY   = "/apps/onboard/layout_filename"
X_POSITION_GCONF_KEY        = "/apps/onboard/horizontal_position"
Y_POSITION_GCONF_KEY        = "/apps/onboard/vertical_position"
SCANNING_GCONF_KEY          = "/apps/onboard/enable_scanning"
SCANNING_INTERVAL_GCONF_KEY = "/apps/onboard/scanning_interval"

KEYBOARD_DEFAULT_HEIGHT   = 800
KEYBOARD_DEFAULT_WIDTH    = 300

SCANNING_DEFAULT_INTERVAL = 750

class Config (object):
    """
    Singleton Class to encapsulate the gconf stuff and check values.
    """

    gconf_client = gconf.client_get_default()

    def __new__(cls, *args, **kwargs): 
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls)
        cls.self._init()
        return cls.self

    def _init(self):
        logger.info("Parsing commandline options")
        parser = OptionParser()
        parser.add_option("-l", "--layout", dest="filename",
                help="Specify layout .sok file")
        parser.add_option("-x", dest="x", help="x coord of window")
        parser.add_option("-y", dest="y", help="y coord of window")
        parser.add_option("-s", "--size", dest="size", 
                help="size widthxheight")
        (options,args) = parser.parse_args()            

        self.gconf_client.add_dir("/apps/onboard", gconf.CLIENT_PRELOAD_NONE)
        self.gconf_client.notify_add(KEYBOARD_WIDTH_GCONF_KEY,
                self._geometry_change_notify_cb)
        self.gconf_client.notify_add(KEYBOARD_HEIGHT_GCONF_KEY, 
                self._geometry_change_notify_cb)

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
            filename = self.gconf_client.get_string(LAYOUT_FILENAME_GCONF_KEY)

        if filename and not os.path.exists(filename):
            logger.warning("Can't load %s loading default layout instead" %
                filename)
            filename = ''

        if not filename:
            filename = os.path.join(get_install_dir(), 
                    "layouts", "Default.sok")

        if not os.path.exists(filename):
            raise Exception("Unable to find layout %s" % filename)
        self.__filename = filename

        self.gconf_client.notify_add(LAYOUT_FILENAME_GCONF_KEY,
                self._layout_filename_notify_change_cb)

    ######## Layout #########
    _layout_change_callbacks   = []
    def layout_filename_change_notify_add(self, callback):
        self._layout_filename_change_callbacks.append(callback)

    def _layout_filename_notify_change_cb(self, client, cxion_id, entry, 
            user_data):
        filename = self.gconf_client.get_string(LAYOUT_FILENAME_GCONF_KEY)
        if not os.path.exists(filename):
            logger.warning("layout %s does not exist" % filename)
        else:
            self.__filename = filename

    def _get_layout_filename(self):
        return self.__filename
    def _set_layout_filename(self):
        raise NotImplementedError()
    layout_filename = property(_get_layout_filename, _set_layout_filename)

    ####### Geometry ########
    _geometry_change_callbacks = []
    def _get_keyboard_height(self):
        height = self.gconf_client.get_int(KEYBOARD_HEIGHT_GCONF_KEY)
        if height and height > 1:
            return height
        else:
            return KEYBOARD_DEFAULT_HEIGHT
    def _set_keyboard_height(self, value):
        if value > 1:
            self.gconf_client.set_int(KEYBOARD_HEIGHT_GCONF_KEY, value)
    keyboard_height = property(_get_keyboard_height, _set_keyboard_height)

    def _get_keyboard_width(self):
        width = self.gconf_client.get_int(KEYBOARD_WIDTH_GCONF_KEY)
        if width and width > 1:
            return width
        else:
            return KEYBOARD_DEFAULT_WIDTH
    def _set_keyboard_width(self, value):
        if value > 1:
            self.gconf_client.set_int(KEYBOARD_WIDTH_GCONF_KEY, value)
    keyboard_width  = property(_get_keyboard_width, _set_keyboard_width)

    def geometry_change_notify_add(self, callback):
        self._geometry_change_callbacks.append(callback)

    def _geometry_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._geometry_change_callbacks:
            cb(self.keyboard_width, self.keyboard_height)


    ####### Position ########
    _position_change_callbacks = []
    def _get_x_position(self):
        return self.gconf_client.get_int(X_POSITION_GCONF_KEY)
    def _set_x_position(self, value):
        self.gconf_client.set_int(X_POSITION_GCONF_KEY, value)
    x_position = property(_get_x_position, _set_x_position)

    def _get_y_position(self):
        return self.gconf_client.get_int(Y_POSITION_GCONF_KEY)
    def _set_y_position(self, value):
        self.gconf_client.set_int(Y_POSITION_GCONF_KEY, value)
    y_position = property(_get_y_position, _set_y_position)

    def position_change_notify_add(self, callback):
        self._position_change_callbacks.append(callback)

    def _position_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._position_change_callbacks:
            cb(self.x_position, self.y_position)

    ####### Scanning ########
    _scanning_callbacks = []
    def _get_scanning(self):
        return self.gconf_client.get_bool(SCANNING_GCONF_KEY)
    def _set_scanning(self, value):
        return self.gconf_client.set_bool(SCANNING_GCONF_KEY, value)
    scanning = property(_get_scanning, _set_scanning)

    def scanning_notify_add(self, callback):
        self._scanning_callbacks.append(callback)

    def _scanning_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._scanning_callbacks:
            cb(self.scanning)

    ## Scanning interval ####
    _scanning_interval_callbacks = []
    def _get_scanning_interval(self):
        interval = self.gconf_client.get_int(SCANNING_INTERVAL_GCONF_KEY)
        if interval and interval > 0:
            return interval
        else:
            return SCANNING_DEFAULT_INTERVAL
    def _set_scanning_interval(self, value):
        return self.gconf_client.set_int(SCANNING_INTERVAL_GCONF_KEY, value)
    scanning_interval = property(_get_scanning_interval, _set_scanning_interval)

    def scanning_interval_notify_add(self, callback):
        self._scanning_interval_callbacks.append(callback)

    def _scanning_interval_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._scanning_interval_callbacks:
            cb(self.scanning_interval)
