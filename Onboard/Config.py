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

ICP_IN_USE_GCONF_KEY     = "/apps/onboard/icon_palette/in_use"
ICP_WIDTH_GCONF_KEY      = "/apps/onboard/icon_palette/width"
ICP_HEIGHT_GCONF_KEY     = "/apps/onboard/icon_palette/height"
ICP_X_POSITION_GCONF_KEY = "/apps/onboard/icon_palette/horizontal_position"
ICP_Y_POSITION_GCONF_KEY = "/apps/onboard/icon_palette/vertical_position"

ICP_DEFAULT_HEIGHT   = 80
ICP_DEFAULT_WIDTH    = 80
ICP_DEFAULT_X_POSITION = 40
ICP_DEFAULT_Y_POSITION = 300

class Config (object):
    """
    Singleton Class to encapsulate the gconf stuff and check values.
    """

    _gconf_client = gconf.client_get_default()

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

        self._gconf_client.add_dir("/apps/onboard", gconf.CLIENT_PRELOAD_NONE)
        self._gconf_client.notify_add(KEYBOARD_WIDTH_GCONF_KEY, self._geometry_change_notify_cb)
        self._gconf_client.notify_add(KEYBOARD_HEIGHT_GCONF_KEY, self._geometry_change_notify_cb)

        self._gconf_client.notify_add(ICP_IN_USE_GCONF_KEY, self._icp_in_use_change_notify_cb)
        self._gconf_client.notify_add(ICP_WIDTH_GCONF_KEY, self._icp_size_change_notify_cb)
        self._gconf_client.notify_add(ICP_HEIGHT_GCONF_KEY, self._icp_size_change_notify_cb)
        self._gconf_client.notify_add(ICP_X_POSITION_GCONF_KEY, self._icp_position_change_notify_cb)
        self._gconf_client.notify_add(ICP_X_POSITION_GCONF_KEY, self._icp_position_change_notify_cb)

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
            logger.warning("Can't load %s loading default layout instead" %
                filename)
            filename = ''

        if not filename:
            filename = os.path.join(get_install_dir(),
                    "layouts", "Default.sok")

        if not os.path.exists(filename):
            raise Exception("Unable to find layout %s" % filename)
        self.__filename = filename

        self._gconf_client.notify_add(LAYOUT_FILENAME_GCONF_KEY,
                self._layout_filename_notify_change_cb)

#        self.useIconPalette = self._gconf_client.get_bool(ICP_IS_ACTIVE_GCONF_KEY)

    ######## Layout #########
    _layout_change_callbacks   = []
    def layout_filename_change_notify_add(self, callback):
        self._layout_filename_change_callbacks.append(callback)

    def _layout_filename_notify_change_cb(self, client, cxion_id, entry,
            user_data):
        filename = self._gconf_client.get_string(LAYOUT_FILENAME_GCONF_KEY)
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
        height = self._gconf_client.get_int(KEYBOARD_HEIGHT_GCONF_KEY)
        if height and height > 1:
            return height
        else:
            return KEYBOARD_DEFAULT_HEIGHT
    def _set_keyboard_height(self, value):
        if value > 1:
            self._gconf_client.set_int(KEYBOARD_HEIGHT_GCONF_KEY, value)
    keyboard_height = property(_get_keyboard_height, _set_keyboard_height)

    def _get_keyboard_width(self):
        width = self._gconf_client.get_int(KEYBOARD_WIDTH_GCONF_KEY)
        if width and width > 1:
            return width
        else:
            return KEYBOARD_DEFAULT_WIDTH
    def _set_keyboard_width(self, value):
        if value > 1:
            self._gconf_client.set_int(KEYBOARD_WIDTH_GCONF_KEY, value)
    keyboard_width  = property(_get_keyboard_width, _set_keyboard_width)

    def geometry_change_notify_add(self, callback):
        self._geometry_change_callbacks.append(callback)

    def _geometry_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._geometry_change_callbacks:
            cb(self.keyboard_width, self.keyboard_height)


    ####### Position ########
    _position_change_callbacks = []
    def _get_x_position(self):
        return self._gconf_client.get_int(X_POSITION_GCONF_KEY)
    def _set_x_position(self, value):
        self._gconf_client.set_int(X_POSITION_GCONF_KEY, value)
    x_position = property(_get_x_position, _set_x_position)

    def _get_y_position(self):
        return self._gconf_client.get_int(Y_POSITION_GCONF_KEY)
    def _set_y_position(self, value):
        self._gconf_client.set_int(Y_POSITION_GCONF_KEY, value)
    y_position = property(_get_y_position, _set_y_position)

    def position_change_notify_add(self, callback):
        self._position_change_callbacks.append(callback)

    def _position_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._position_change_callbacks:
            cb(self.x_position, self.y_position)

    ####### Scanning ########
    _scanning_callbacks = []
    def _get_scanning(self):
        return self._gconf_client.get_bool(SCANNING_GCONF_KEY)
    def _set_scanning(self, value):
        return self._gconf_client.set_bool(SCANNING_GCONF_KEY, value)
    scanning = property(_get_scanning, _set_scanning)

    def scanning_notify_add(self, callback):
        self._scanning_callbacks.append(callback)

    def _scanning_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._scanning_callbacks:
            cb(self.scanning)

    ## Scanning interval ####
    _scanning_interval_callbacks = []
    def _get_scanning_interval(self):
        interval = self._gconf_client.get_int(SCANNING_INTERVAL_GCONF_KEY)
        if interval and interval > 0:
            return interval
        else:
            return SCANNING_DEFAULT_INTERVAL
    def _set_scanning_interval(self, value):
        return self._gconf_client.set_int(SCANNING_INTERVAL_GCONF_KEY, value)
    scanning_interval = property(_get_scanning_interval, _set_scanning_interval)

    def scanning_interval_notify_add(self, callback):
        self._scanning_interval_callbacks.append(callback)

    def _scanning_interval_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._scanning_interval_callbacks:
            cb(self.scanning_interval)


    ####### IconPalette aka icp ########

    # iconPalette activation option
    def _icp_get_in_use(self):
        """
        iconPalette visible getter.
        """
        return self._gconf_client.get_bool(ICP_IN_USE_GCONF_KEY)

    def _icp_set_in_use(self, value):
        """
        iconPalette visible setter.
        """
        return self._gconf_client.set_bool(ICP_IN_USE_GCONF_KEY, value)

    icp_in_use = property(_icp_get_in_use, _icp_set_in_use)

    # callback for when the iconPalette gets activated/deactivated
    _icp_in_use_change_callbacks = []

    def icp_in_use_change_notify_add(self, callback):
        """
        Register callback to be run when the setting about using
        the IconPalette changes.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._icp_in_use_change_callbacks.append(callback)

    def _icp_in_use_change_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve iconPalette visibility notifications from gconf and run callbacks.
        """
        # print "_icp_in_use_change_notify_cb"
        for callback in self._icp_in_use_change_callbacks:
            callback()


    # iconPalette size
    def _icp_get_width(self):
        """
        iconPalette width getter.
        """
        width = self._gconf_client.get_int(ICP_WIDTH_GCONF_KEY)
        if width:
            return width
        else:
            return ICP_DEFAULT_WIDTH

    def _icp_set_width(self, value):
        """
        iconPalette width setter.
        """
        if value > 0:
            self._gconf_client.set_int(ICP_WIDTH_GCONF_KEY, int(value))

    icp_width  = property(_icp_get_width, _icp_set_width)

    def _icp_get_height(self):
        """
        iconPalette height getter.
        """
        height = self._gconf_client.get_int(ICP_HEIGHT_GCONF_KEY)
        if height:
            return height
        else:
            return ICP_DEFAULT_HEIGHT

    def _icp_set_height(self, value):
        """
        iconPalette height setter.
        """
        if value > 0:
            self._gconf_client.set_int(ICP_HEIGHT_GCONF_KEY, int(value))

    icp_height = property(_icp_get_height, _icp_set_height)

    _icp_size_change_notify_callbacks = []

    def icp_size_change_notify_add(self, callback):
        """
        Register callback to be run when the size of the iconPalette
        changes.

        Callbacks are called with the new size as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._icp_size_change_notify_callbacks.append(callback)

    def _icp_size_change_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve size change notifications from gconf and run callbacks.
        """
        # print "_icp_size_change_notify_cb"
        for callback in self._icp_size_change_notify_callbacks:
            callback(self.icp_width, self.icp_height)


    # iconPalette position
    def _icp_get_x_position(self):
        """
        iconPalette x position getter.
        """
        x_pos = self._gconf_client.get_int(ICP_X_POSITION_GCONF_KEY)
        if x_pos:
            return x_pos
        else:
            return ICP_DEFAULT_X_POSITION

    def _icp_set_x_position(self, value):
        """
        iconPalette x position setter.
        """
        if value > 0:
            self._gconf_client.set_int(ICP_X_POSITION_GCONF_KEY, int(value))

    icp_x_position = property(_icp_get_x_position, _icp_set_x_position)

    def _icp_get_y_position(self):
        """
        iconPalette y position getter.
        """
        y_pos = self._gconf_client.get_int(ICP_Y_POSITION_GCONF_KEY)
        if y_pos:
            return y_pos
        else:
            return ICP_DEFAULT_Y_POSITION

    def _icp_set_y_position(self, value):
        """
        iconPalette y position setter.
        """
        if value > 0:
            self._gconf_client.set_int(ICP_Y_POSITION_GCONF_KEY, int(value))

    icp_y_position = property(_icp_get_y_position, _icp_set_y_position)

    _icp_position_change_notify_callbacks = []

    def icp_position_change_notify_add(self, callback):
        """
        Register callback to be run when the position of the
        iconPalette changes.

        Callbacks are called with the new position as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._icp_position_change_notify_callbacks.append(callback)

    def _icp_position_change_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve position change notifications from gconf and run callbacks.
        """
        # print "_icp_position_change_notify_cb"
        for callback in self._icp_position_change_notify_callbacks:
            callback(self.icp_x_position, self.icp_y_position)

