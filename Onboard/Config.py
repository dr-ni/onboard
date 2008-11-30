#Config singleton

### Logging ###
import logging
logger = logging.getLogger("Config")
###############

import gconf

KEYBOARD_WIDTH_GCONF_KEY  = "/apps/onboard/width"
KEYBOARD_HEIGHT_GCONF_KEY = "/apps/onboard/height"

KEYBOARD_DEFAULT_HEIGHT = 800
KEYBOARD_DEFAULT_HEIGHT = 300

class Config (object):
    """
    Singleton Class to encapsulate the gconf stuff and check values.
    """

    geometry_change_callbacks = []
    gconf_client = gconf.client_get_default()


    def __new__(cls, *args, **kwargs): 
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls)

        cls.self._init()

        return cls.self

    def _init(self):
        self.gconf_client.notify_add(KEYBOARD_WIDTH_GCONF_KEY,
                self.geometry_change_notify_cb)
        self.gconf_client.notify_add(KEYBOARD_HEIGHT_GCONF_KEY, 
                self.geometry_change_notify_cb)

 
    def geometry_change_notify_add(self, callback):
        self.geometry_change_callbacks.append(callback)

    def geometry_change_notify_cb(self, client, cxion_id, entry, user_data):
        for cb in self.geometry_change_callbacks:
            cb(self.keyboard_width, self.keyboard_height)

    #### keyboard_height ####
    def get_keyboard_height(self):
        height = self.gconf_client.get_int(KEYBOARD_HEIGHT_GCONF_KEY)
        if height and height > 1:
            return height
        else:
            return KEYBOARD_DEFAULT_HEIGHT
    def set_keyboard_height(self, value):
        if value > 1:
            self.gconf_client.set_int(KEYBOARD_HEIGHT_GCONF_KEY, value)
    keyboard_height = property(get_keyboard_height, set_keyboard_height)

    #### keyboard_width ####
    def get_keyboard_width(self):
        width = self.gconf_client.get_int(KEYBOARD_WIDTH_GCONF_KEY)
        if width and width > 1:
            return width
        else:
            return KEYBOARD_DEFAULT_WIDTH
    def set_keyboard_width(self, value):
        if value > 1:
            self.gconf_client.set_int(KEYBOARD_WIDTH_GCONF_KEY, value)
    keyboard_width  = property(get_keyboard_width, set_keyboard_width)

