#Config singleton

### Logging ###
import logging
logger = logging.getLogger("Config")
###############

import gconf
import os

from optparse import OptionParser

from Onboard.utils import get_install_dir

KEYBOARD_WIDTH_GCONF_KEY  = "/apps/onboard/width"
KEYBOARD_HEIGHT_GCONF_KEY = "/apps/onboard/height"
LAYOUT_FILENAME_GCONF_KEY = "/apps/onboard/layout_filename"

KEYBOARD_DEFAULT_HEIGHT = 800
KEYBOARD_DEFAULT_HEIGHT = 300

class Config (object):
    """
    Singleton Class to encapsulate the gconf stuff and check values.
    """

    _geometry_change_callbacks = []
    _layout_change_callbacks = []
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
                self.geometry_change_notify_cb)
        self.gconf_client.notify_add(KEYBOARD_HEIGHT_GCONF_KEY, 
                self.geometry_change_notify_cb)

        if (options.size):
            size = options.size.split("x")
            self.window.set_default_size(int(size[0]),int(size[1]))

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

    def layout_filename_change_notify_add(self, callback):
        self._layout_filename_change_callbacks.append(callback)

    def _layout_filename_notify_change_cb(self, client, cxion_id, entry, user_data):
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

    def geometry_change_notify_add(self, callback):
        self._geometry_change_callbacks.append(callback)

    def geometry_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self._geometry_change_callbacks:
            cb(self.keyboard_width, self.keyboard_height)

    #### keyboard_height ####
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

    #### keyboard_width ####
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

