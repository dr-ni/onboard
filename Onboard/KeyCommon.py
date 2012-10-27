# -*- coding: UTF-8 -*-
"""
KeyCommon hosts the abstract classes for the various types of Keys.
UI-specific keys should be defined in KeyGtk or KeyKDE files.
"""

from __future__ import division, print_function, unicode_literals

from Onboard.utils import Rect, brighten
from Onboard.Layout import LayoutItem

### Logging ###
import logging
_logger = logging.getLogger("KeyCommon")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

(
    CHAR_TYPE,
    KEYSYM_TYPE,
    KEYCODE_TYPE,
    MACRO_TYPE,
    SCRIPT_TYPE,
    KEYPRESS_NAME_TYPE,
    BUTTON_TYPE,
    LEGACY_MODIFIER_TYPE,
) = tuple(range(1, 9))

(
    SINGLE_STROKE_ACTION,  # press on button down, release on up (default)
    DOUBLE_STROKE_ACTION,  # press+release on button down and up, (CAPS, NMLK)
    DELAYED_STROKE_ACTION, # press+release on button up (MENU)
) = tuple(range(1, 4))

actions = {"single-stroke"  : SINGLE_STROKE_ACTION,
           "double-stroke"  : DOUBLE_STROKE_ACTION,
           "delayed-stroke" : DELAYED_STROKE_ACTION,
          }

class StickyBehavior:
    """ enum for sticky key behaviors """
    (
        CYCLE,
        DOUBLE_CLICK,
        LATCH_ONLY,
        LOCK_ONLY,
    ) = tuple(range(1, 5))

    values = {"cycle"    : CYCLE,
              "dblclick" : DOUBLE_CLICK,
              "latch"    : LATCH_ONLY,
              "lock"     : LOCK_ONLY,
             }

    @staticmethod
    def from_string(str_value):
        """ Raises KeyError """
        return StickyBehavior.values[str_value]

    @staticmethod
    def is_valid(value):
        return value in StickyBehavior.values.values()


class LOD:
    """ enum for level of detail """
    (
        MINIMAL,    # clearly visible reduced detail, fastest
        REDUCED,    # slightly reduced detail
        FULL,       # full detail
    ) = tuple(range(3))


class KeyCommon(LayoutItem):
    """
    library-independent key class. Specific rendering options
    are stored elsewhere.
    """

    # extended id for key specific theme tweaks
    # e.g. theme_id=DELE.1 (with id=DELE)
    theme_id = None

    # Type of action to do when key is pressed.
    action = None

    # Type of key stroke to send
    type = None

    # Data used in sending key strokes.
    code = None

    # Keys that stay stuck when pressed like modifiers.
    sticky = False

    # Behavior if sticky is enabled, see StickyBehavior.
    sticky_behavior = None

    # modifier bit
    modifier = None

    # True when key is being hovered over (not implemented yet)
    prelight = False

    # True when key is being pressed.
    pressed = False

    # True when key stays 'on'
    active = False

    # True when key is sticky and pressed twice.
    locked = False

    # True when Onboard is in scanning mode and key is highlighted
    scanned = False

    # False if the key should be ignored by the scanner
    scannable = True

    # Determines scanning order
    scan_priority = 0

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

    def draw_label(self, context = None):
        raise NotImplementedError()

    def get_label(self):
        return self.labels[self.label_index]

    def is_active(self):
        return not self.type is None

    def get_id(self):
        return ""

    def set_id(self, value):
        self.theme_id, self.id = self.split_id(value)

    @staticmethod
    def split_id(value):
        """
        The theme id has the form <id>.<arbitrary identifier>, where
        the identifier should be a descripttion of the location of
        the key, e.g. 'DELE.next-to-backspace'.
        Don't use layout names or layer ids for the theme id, layouts
        may be copied and renamed by users.
        """
        theme_id = value
        id = value.split(".")[0]
        return theme_id, id

    def is_layer_button(self):
        return self.id.startswith("layer")

    def is_modifier(self):
        """
        Modifiers are all latchable/lockable keys:
        "LWIN", "RTSH", "LFSH", "RALT", "LALT",
        "RCTL", "LCTL", "CAPS", "NMLK"
        """
        return bool(self.modifier)

    def is_pressed_only(self):
        return self.pressed and not (self.active or \
                                     self.locked or \
                                     self.scanned)

    def get_layer_index(self):
        assert(self.is_layer_button())
        return int(self.id[5:])

class RectKeyCommon(KeyCommon):
    """ An abstract class for rectangular keyboard buttons """

    def __init__(self, id, border_rect):
        KeyCommon.__init__(self)
        self.id = id
        self.colors = {}
        self.context.log_rect = border_rect \
                                if not border_rect is None else Rect()

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
        return self._get_color("fill")

    def get_stroke_color(self):
        return self._get_color("stroke")

    def get_label_color(self):
        return self._get_color("label")

    def get_dwell_progress_color(self):
        return self._get_color("dwell-progress")

    def get_dwell_progress_canvas_rect(self):
        rect = self.get_label_rect().inflate(0.5)
        return self.context.log_to_canvas_rect(rect)

    def _get_color(self, element):
        color_key = (element, self.prelight, self.pressed,
                              self.active, self.locked,
                              self.sensitive, self.scanned)
        rgba = self.colors.get(color_key)
        if not rgba:
            if self.color_scheme:
                rgba = self.color_scheme.get_key_rgba(self, element)
            elif element == "label":
                rgba = [0.0, 0.0, 0.0, 1.0]
            else:
                rgba = [1.0, 1.0, 1.0, 1.0]
            self.colors[color_key] = rgba
        return rgba

    def get_fullsize_rect(self):
        """ Get bounding box of the key at 100% size in logical coordinates """
        rect = LayoutItem.get_rect(self)

        return rect

    def get_canvas_fullsize_rect(self):
        """ Get bounding box of the key at 100% size in canvas coordinates """
        return self.context.log_to_canvas_rect(self.get_fullsize_rect())

    def get_rect(self):
        """ Get bounding box in logical coordinates """
        rect = self.get_fullsize_rect()

        # fake physical key action
        if self.pressed:
            key_style = config.theme_settings.key_style
            if key_style == "gradient":
                k = 0.2
                rect.x += k
                rect.y += 2 * k
                rect.w - 2 * k
                rect.h - k
            elif key_style == "dish":
                k = 0.45
                rect.x += k
                rect.y += 2 * k
                rect.w - 2 * k
                rect.h - k

        # shrink keys to key_size
        #
        size = config.theme_settings.key_size / 100.0
        bx = rect.w * (1.0 - size) / 2.0
        by = rect.h * (1.0 - size) / 2.0
        # keys with aspect < 1.0, e.g. click, move, number block + and enter
        if rect.h > rect.w:
            by = bx
        # keys with aspect > 1.0, e.g. space, shift
        if rect.h < rect.w:
            bx = by
        return rect.deflate(bx, by)

    def get_label_rect(self):
        """ Label area in logical coordinates """
        rect = self.get_rect()
        if config.theme_settings.key_style == "dish":
            rect = rect.deflate(*config.DISH_KEY_BORDER)
            rect.y -= config.DISH_KEY_Y_OFFSET
            return rect
        else:
            return rect.deflate(*config.LABEL_MARGIN)

