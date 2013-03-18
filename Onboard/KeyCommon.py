# -*- coding: UTF-8 -*-
"""
KeyCommon hosts the abstract classes for the various types of Keys.
UI-specific keys should be defined in KeyGtk or KeyKDE files.
"""

from __future__ import division, print_function, unicode_literals

from math import pi

from Onboard.utils import Rect, brighten, \
                          LABEL_MODIFIERS, Modifiers
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
    WORD_TYPE,
    CORRECTION_TYPE,
) = tuple(range(1, 11))

(
    SINGLE_STROKE_ACTION,  # press on button down, release on up (default)
    DELAYED_STROKE_ACTION, # press+release on button up (MENU)
    DOUBLE_STROKE_ACTION,  # press+release on button down and up, (CAPS, NMLK)
) = tuple(range(3))

actions = {
           "single-stroke"  : SINGLE_STROKE_ACTION,
           "delayed-stroke" : DELAYED_STROKE_ACTION,
           "double-stroke"  : DOUBLE_STROKE_ACTION,
          }

class StickyBehavior:
    """ enum for sticky key behaviors """
    (
        CYCLE,
        DOUBLE_CLICK,
        LATCH_ONLY,
        LOCK_ONLY,
    ) = tuple(range(4))

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

class ImageSlot:
    NORMAL = 0
    ACTIVE = 1

class KeyCommon(LayoutItem):
    """
    library-independent key class. Specific rendering options
    are stored elsewhere.
    """

    # extended id for key specific theme tweaks
    # e.g. theme_id=DELE.numpad (with id=DELE)
    theme_id = None

    # extended id for layout specific tweaks
    # e.g. "hide.wordlist", for hide button in wordlist mode
    svg_id = None

    # optional id of a sublayout used as long-press popup
    popup_id = None

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

    # True when action was triggered e.g. key-strokes were sent on press
    activated = False

    # Size to draw the label text in Pango units
    font_size = 1

    # Labels which are displayed by this key
    labels = None  # {modifier_mask : label, ...}

    # label that is currently displayed by this key
    label = ""

    # smaller label of a currently invisible modifier level
    secondary_label = ""

    # Images displayed by this key (optional)
    image_filenames = None

    # horizontal label alignment
    label_x_align = config.DEFAULT_LABEL_X_ALIGN

    # vertical label alignment
    label_y_align = config.DEFAULT_LABEL_Y_ALIGN

    # label margin (x, y)
    label_margin = config.LABEL_MARGIN

    # tooltip text
    tooltip = None

    # can show label popup
    label_popup = True

###################

    def __init__(self):
        LayoutItem.__init__(self)

    def configure_label(self, mod_mask):
        SHIFT = Modifiers.SHIFT
        labels = self.labels

        if labels is None:
            self.label = self.secondary_label = ""
            return

        # primary label
        label = labels.get(mod_mask)
        if label is None:
            mask = mod_mask & LABEL_MODIFIERS
            label = labels.get(mask)

        # secondary label, usually the label of the shift state
        secondary_label = None
        if not label is None:
            if mod_mask & SHIFT:
                mask = mod_mask & ~SHIFT
            else:
                mask = mod_mask | SHIFT

            secondary_label = labels.get(mask)
            if secondary_label is None:
                mask = mask & LABEL_MODIFIERS
                secondary_label = labels.get(mask)

            # Only keep secondary labels that show different characters
            if not secondary_label is None and \
               secondary_label.upper() == label.upper():
                secondary_label = None

        if label is None:
            # legacy fallback for 0.98 behavior and virtkey until 0.61.0
            if mod_mask & Modifiers.SHIFT:
                if mod_mask & Modifiers.ALTGR and 129 in labels:
                    label = labels[129]
                elif 1 in labels:
                    label = labels[1]
                elif 2 in labels:
                    label = labels[2]

            elif mod_mask & Modifiers.ALTGR and 128 in labels:
                label = labels[128]

            elif mod_mask & Modifiers.CAPS:  # CAPS lock
                if 2 in labels:
                    label = labels[2]
                elif 1 in labels:
                    label = labels[1]

        if label is None:
            label = labels.get(0)

        if label is None:
            label = ""

        self.label = label
        self.secondary_label = secondary_label

    def draw_label(self, context = None):
        raise NotImplementedError()

    def set_labels(self, labels):
        self.labels = labels
        self.configure_label(0)

    def get_label(self):
        return self.label

    def get_secondary_label(self):
        return self.secondary_label

    def is_active(self):
        return not self.type is None

    def get_id(self):
        return ""

    def set_id(self, id, theme_id = None, svg_id = None):
        self.theme_id, self.id = self.split_id(id)
        if theme_id:
            self.theme_id = theme_id
        self.svg_id = self.id if not svg_id else svg_id

    @staticmethod
    def split_id(value):
        """
        The theme id has the form <id>.<arbitrary identifier>, where
        the identifier should be a descripttion of the location of
        the key relative to its surroundings, e.g. 'DELE.next-to-backspace'.
        Don't use layout names or layer ids for the theme id, they lose
        their meaning when layouts are copied or renamed by users.
        """
        theme_id = value
        id = value.split(".")[0]
        return theme_id, id

    def build_theme_id(self, prefix = None):
        if prefix is None:
            prefix = self.id
        theme_id = prefix
        comps = self.theme_id.split(".")[1:]
        if comps:
            theme_id += "." + comps[0] 
        return theme_id

    def is_layer_button(self):
        return self.id.startswith("layer")

    def is_prediction_key(self):
        return self.id.startswith("prediction")

    def is_correction_key(self):
        return self.id.startswith("correction") or \
               self.id in ["expand-corrections"]

    def is_word_suggestion(self):
        return self.is_prediction_key() or self.is_correction_key()

    def is_modifier(self):
        """
        Modifiers are all latchable/lockable non-button keys:
        "LWIN", "RTSH", "LFSH", "RALT", "LALT",
        "RCTL", "LCTL", "CAPS", "NMLK"
        """
        return bool(self.modifier)

    def is_button(self):
        return self.type == BUTTON_TYPE

    def is_pressed_only(self):
        return self.pressed and not (self.active or \
                                     self.locked or \
                                     self.scanned)

    def is_text_changing(self):
        return not self.is_modifier() and \
               self.type in [KEYCODE_TYPE,
                             KEYSYM_TYPE,
                             CHAR_TYPE,
                             KEYPRESS_NAME_TYPE,
                             MACRO_TYPE,
                             WORD_TYPE,
                             CORRECTION_TYPE]

    def is_return(self):
        id = self.id
        return id == "RTRN" or \
               id == "KPEN"

    def get_layer_index(self):
        assert(self.is_layer_button())
        return int(self.id[5:])

    def get_popup_layout(self):
        if self.popup_id:
            return self.find_sublayout(self.popup_id)
        return None

    def can_show_label_popup(self):
        return not self.is_modifier() and \
               not self.is_layer_button() and \
               not self.type is None and \
               bool(self.label_popup)


class RectKeyCommon(KeyCommon):
    """ An abstract class for rectangular keyboard buttons """

    # Optional key_style to override the default theme's style.
    style = None

    # Toggles for what gets drawn.
    show_face = True
    show_border = True
    show_label = True

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

    def align_label(self, label_size, key_size, ltr = True):
        """ returns x- and yoffset of the aligned label """
        label_x_align = self.label_x_align
        label_y_align = self.label_y_align
        if not ltr:  # right to left script?
            label_x_align = 1.0 - label_x_align
        xoffset = label_x_align * (key_size[0] - label_size[0])
        yoffset = label_y_align * (key_size[1] - label_size[1])
        return xoffset, yoffset

    def align_secondary_label(self, label_size, key_size, ltr = True):
        """ returns x- and yoffset of the aligned label """
        label_x_align = 0.97
        label_y_align = 0.0
        if not ltr:  # right to left script?
            label_x_align = 1.0 - label_x_align
        xoffset = label_x_align * (key_size[0] - label_size[0])
        yoffset = label_y_align * (key_size[1] - label_size[1])
        return xoffset, yoffset

    def align_popup_indicator(self, label_size, key_size, ltr = True):
        """ returns x- and yoffset of the aligned label """
        label_x_align = 1.0
        label_y_align = self.label_y_align
        if not ltr:  # right to left script?
            label_x_align = 1.0 - label_x_align
        xoffset = label_x_align * (key_size[0] - label_size[0])
        yoffset = label_y_align * (key_size[1] - label_size[1])
        return xoffset, yoffset

    def get_style(self):
        if not self.style is None:
            return self.style
        return config.theme_settings.key_style

    def get_light_direction(self):
        return config.theme_settings.key_gradient_direction * pi / 180.0

    def get_fill_color(self):
        return self._get_color("fill")

    def get_stroke_color(self):
        return self._get_color("stroke")

    def get_label_color(self):
        return self._get_color("label")

    def get_secondary_label_color(self):
        return self._get_color("secondary-label")

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
        return LayoutItem.get_rect(self)

    def get_canvas_fullsize_rect(self):
        """ Get bounding box of the key at 100% size in canvas coordinates """
        return self.context.log_to_canvas_rect(self.get_fullsize_rect())

    def get_unpressed_rect(self):
        """ 
        Get bounding box in logical coordinates.
        Just the relatively static unpressed rect withough fake key action.
        """
        rect = self.get_fullsize_rect()
        return self._apply_key_size(rect)

    def get_rect(self):
        """ Get bounding box in logical coordinates """
        return self.get_sized_rect()

    def get_sized_rect(self, horizontal = None):
        rect = self.get_fullsize_rect()

        # fake physical key action
        if self.pressed:
            key_style = self.get_style()
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

        return self._apply_key_size(rect, horizontal)

    @staticmethod
    def _apply_key_size(rect, horizontal = None):
        """ shrink keys to key_size """
        size = config.theme_settings.key_size / 100.0
        bx = rect.w * (1.0 - size) / 2.0
        by = rect.h * (1.0 - size) / 2.0

        if horizontal is None:
            horizontal = rect.h < rect.w

        if horizontal:
            # keys with aspect > 1.0, e.g. space, shift
            bx = by
        else:
            # keys with aspect < 1.0, e.g. click, move, number block + and enter 
            by = bx

        return rect.deflate(bx, by)


    def get_label_rect(self, rect = None):
        """ Label area in logical coordinates """
        if rect is None:
            rect = self.get_rect()
        style = self.get_style()
        if style == "dish":
            rect = rect.deflate(*config.DISH_KEY_BORDER)
            rect.y -= config.DISH_KEY_Y_OFFSET
            return rect
        else:
            return rect.deflate(*self.label_margin)

    def get_canvas_label_rect(self):
        log_rect = self.get_label_rect()
        return self.context.log_to_canvas_rect(log_rect)


class InputlineKeyCommon(RectKeyCommon):
    """ An abstract class for InputLine keyboard buttons """

    line = ""
    word_infos = None
    cursor = 0

    def __init__(self, name, border_rect):
        RectKeyCommon.__init__(self, name, border_rect)

    def get_label(self):
        return ""


