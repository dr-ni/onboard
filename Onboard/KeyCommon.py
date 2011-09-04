# -*- coding: UTF-8 -*-
"""
KeyCommon hosts the abstract classes for the various types of Keys.
UI-specific keys should be defined in KeyGtk or KeyKDE files.
"""

from math import sqrt

from Onboard.utils import Rect
from Onboard.Layout import LayoutItem

### Logging ###
import logging
_logger = logging.getLogger("KeyCommon")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

BASE_PANE_TAB_HEIGHT = 40

(CHAR_ACTION, KEYSYM_ACTION, KEYCODE_ACTION, MODIFIER_ACTION, MACRO_ACTION,
    SCRIPT_ACTION, KEYPRESS_NAME_ACTION, BUTTON_ACTION) = range(1,9)


class KeyCommon(LayoutItem):
    """
    library-independent key class. Specific rendering options
    are stored elsewhere.
    """

    # indexed id for key specific theme tweaks
    # e.g. theme_id=DELE.1 (with id=DELE)
    theme_id = None

    # Size group of the key
    group = None

    # Type of action to do when key is pressed.
    action_type = None

    # Data used in action.
    action = None

    # True when key is being pressed.
    pressed = False

    # True when key stays 'on'
    latched = False

    # When key is sticky and pressed twice.
    locked = False

    # Keys that stay stuck when pressed like modifiers.
    sticky = False

    # True when Onboard is in scanning mode and key is highlighted
    beingScanned = False

    # Size to draw the label text in Pango units
    font_size = 1

    # Index in labels that is currently displayed by this key
    label_index = 0

    # Labels which are displayed by this key
    labels = None

    # Image displayed by this key (optional)
    image_filename = None

    # Cached pixbuf object of the image
    image_pixbuf = None

    # horizontal label alignment
    label_x_align = config.DEFAULT_LABEL_X_ALIGN

    # vertical label alignment
    label_y_align = config.DEFAULT_LABEL_Y_ALIGN

    # tooltip text
    tooltip = None

###################

    def __init__(self):
        LayoutItem.__init__(self)

    def configure_label(self, mods):
        if mods[1]:
            if mods[128] and self.labels[4]:
                self.label_index = 4
            elif self.labels[2]:
                self.label_index = 2
            elif self.labels[1]:
                self.label_index = 1
            else:
                self.label_index = 0

        elif mods[128] and self.labels[3]:
            self.label_index = 3

        elif mods[2]:
            if self.labels[1]:
                self.label_index = 1
            else:
                self.label_index = 0
        else:
            self.label_index = 0

    def draw_font(self, context = None):
        raise NotImplementedError()

    def get_label(self):
        return self.labels[self.label_index]

    def is_active(self):
        return not self.action_type is None

    def get_id(self):
        return ""

    def is_layer_button(self):
        return self.id.startswith("layer")

    def get_layer_index(self):
        assert(self.is_layer_button())
        return int(self.id[5:])

class RectKeyCommon(KeyCommon):
    """ An abstract class for rectangular keyboard buttons """

    # Coordinates of the key on the keyboard
    location = None

    # Width and height of the key
    geometry = None

    # Fill colour of the key
    rgba = None

    # Mouse over colour of the key
    hover_rgba   = None

    # Pushed down colour of the key
    pressed_rgba   = None

    # On colour of modifier key
    latched_rgba = None

    # Locked colour of modifier key
    locked_rgba  = None

    # Colour for key being scanned
    scanned_rgba  = None

    # Outline colour of the key in flat mode
    stroke_rgba = None

    # Four tuple with values between 0 and 1 containing label color
    label_rgba = None

    def __init__(self, id, location, geometry):
        KeyCommon.__init__(self)
        self.id = id
        self.location = location
        self.geometry = geometry

    def get_id(self):
        return self.id

    def draw(self, context = None):
        pass

    def align_label(self, label_size, key_size):
        """ returns x- and yoffset of the aligned label """
        xoffset = self.label_x_align * (key_size[0] - label_size[0])
        yoffset = self.label_y_align * (key_size[1] - label_size[1])
        return xoffset, yoffset

    def get_fill_color(self):
        if self.pressed:
            fill = self.pressed_rgba
        elif self.locked:
            fill = self.locked_rgba
        elif self.latched:
            fill = self.latched_rgba
        elif self.beingScanned:
            fill = self.scanned_rgba
        else:
            fill = self.rgba
        return fill

    def get_border_rect(self):
        """ Bounding rectangle in logical coordinates """
        return Rect(self.location[0],
                    self.location[1],
                    self.geometry[0],
                    self.geometry[1])

    def get_label_rect(self):
        """ Label area in logical coordinates """
        rect = self.get_rect()
        return rect.deflate(config.LABEL_MARGIN[0], config.LABEL_MARGIN[1])

