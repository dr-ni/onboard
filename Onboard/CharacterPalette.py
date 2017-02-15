# -*- coding: utf-8 -*-

# Copyright © 2017 marmuta <marmvta@gmail.com>
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

import logging
_logger = logging.getLogger(__name__)

from Onboard.Layout            import (LayoutPanel, ScrolledLayoutPanel,
                                       RectangleItem)
from Onboard.KeyGtk            import FlatKey
from Onboard.KeyCommon         import ImageSlot, ImageStyle
from Onboard                   import KeyCommon
from Onboard.UnicodeData       import (UnicodeData,
                                       emoji_filename_from_sequence)

from Onboard.Config import Config
config = Config()


EMOJI_IMAGE_MARGIN = (3, 3)


class CharacterPaletteKey(FlatKey):
    pass


class PaletteHeaderKey(FlatKey):
    palette_panel = None

    def get_style(self):
        # No gradient when active to match the background rectangle.
        if self.is_active_only():
            return "flat"
        return super(PaletteHeaderKey, self).get_style()

    def get_fill_color(self):
        # Show active state with the inactive fill color.
        # In inactive state the key is transparent (FlatKey).
        state = {} if self.is_active_only() else None
        return self.get_color("fill", state)

    def __build_rect_path(self, context, rect):
        # Only round top corners.
        r = rect.copy()
        r.y -= 1
        self.build_rect_path_custom(context, r, 0b1100)

    def on_release(self, view, button, event_type):
        self.palette_panel.set_active_category_index(self.code)


class CharacterPaletteBackground(RectangleItem):

    def get_fill_color(self):
        return (0, 0, 0, 1)
        return (0.125, 0.125, 0.125, 1)
    pass


class CharacterGridPanel(ScrolledLayoutPanel):
    keyboard = None
    sequences = []
    has_emoji = False
    key_border_rect = None
    key_group = None
    color_scheme = None
    background_rgba = None

    def __init__(self):
        super(CharacterGridPanel, self).__init__()

        self._key_rects = []
        self._key_slots = []

        # cache for keys, including expensively rendered images
        self._key_pool = {}

    def update_log_rect(self):
        self.set_clip_rect(self.get_canvas_border_rect())
        super(CharacterGridPanel, self).update_log_rect()

    def update_content(self):
        spacing = (0, 0)

        key_rects, bounds = self.get_rect().flow_layout(
            self.key_border_rect, len(self.sequences), *spacing, False)

        self._key_slots = [None] * len(key_rects)
        self._key_rects = key_rects
        self.lock_y_axis(True)
        self.set_scroll_rect(bounds)

    def on_damage(self, damage_rect):
        keys_to_redraw = [self]
        for i, rect in enumerate(self._key_rects):
            if damage_rect.intersects(rect):
                key = self._key_slots[i]
                if key  is None:
                    key = self._get_key(i)
                    self._key_slots[i] = key
                # keys_to_redraw.append(key)
            else:
                self._key_slots[i] = None

        self.set_items([key for key in self._key_slots if key is not None])

        if keys_to_redraw:
            layout = self.keyboard.layout
            if layout:
                layout.invalidate_font_sizes()
                layout.invalidate_caches()

                self.keyboard.redraw(keys_to_redraw)

    def _get_key(self, index):
        id = "_palette_character" + str(index)
        label = self.sequences[index]

        try:
            key = self._key_pool[label]
        except KeyError:
            key = self._create_key(id, label, self._key_rects[index],
                                   self.key_group, self.color_scheme,
                                   self.has_emoji)

            # only cache emoji keys, as these are the most expensive ones
            if self.has_emoji:
                self._key_pool[label] = key

        key.set_id(id)

        return key

    @staticmethod
    def _create_key(id, label, key_border_rect, key_group,
                    color_scheme, has_emoji):
        key = CharacterPaletteKey()

        key.type = KeyCommon.CHAR_TYPE
        key.code = label
        key.action = KeyCommon.DELAYED_STROKE_ACTION
        key.set_border_rect(key_border_rect)
        if len(label) <= 2:
            key.group = key_group
        else:
            key.group = id
        key.color_scheme = color_scheme

        if has_emoji:
            fn = emoji_filename_from_sequence(label)
            if fn:
                key.image_filenames = {ImageSlot.NORMAL : fn}
                key.image_style = ImageStyle.MULTI_COLOR
                key.label_margin = EMOJI_IMAGE_MARGIN

        if not key.image_filenames:
            key.labels = {0: label}

        key.can_draw_cached = False

        return key


class CharacterPalettePanel(LayoutPanel):
    """ Emoji/symbol palette """

    def __init__(self):
        LayoutPanel.__init__(self)
        self.keyboard = None
        self._unicode_data = UnicodeData()
        self._character_grid = None
        self._header_keys = None
        self._active_category_index = -1
        self._character_grid = None

    def update_log_rect(self):
        self.update_content()
        super(CharacterPalettePanel, self).update_log_rect()

    def update_content(self):
        if self._header_keys is None:
            self.create_header_content()

    def create_header_content(self):
        background = self.find_id("character-palette")
        header_template = self.find_id("palette-header-template")
        key_template = self.find_id("palette-key-template")
        keys = []

        if not background or \
           not header_template or \
           not key_template:
            return []

        color_scheme = key_template.color_scheme
        remaining_rect = background.get_rect().copy()

        # create header keys
        headers = self.get_header_labels()
        ks, r = self._create_header_keys(
            remaining_rect,
            header_template.get_border_rect(),
            "_" + self.content_type + "_header",
            color_scheme, headers)
        keys += ks
        remaining_rect.h -= r.h

        # create background rectangle
        # bg = CharacterPaletteBackground()
        # bg.set_border_rect(remaining_rect)
        # bg.color_scheme = color_scheme

        # create scrolled panel with grid of keys
        grid = CharacterGridPanel()
        grid.set_id("_character_grid")
        grid.set_border_rect(remaining_rect)
        grid.keyboard = self.keyboard
        grid.sequences = []
        grid.key_border_rect = key_template.get_border_rect()
        grid.key_group = "_" + self.content_type
        grid.color_scheme = color_scheme
        grid.has_emoji = self.content_type == "emoji"

        self.set_items([background, header_template,
                        key_template, grid] + keys)

        self._character_grid = grid
        self._header_keys = keys

        self.set_active_category_index(0)

    def _create_header_keys(self, palette_rect, header_key_border_rect,
                            header_key_group, color_scheme, sequence):
        spacing = (0, 0)

        header_rect = palette_rect.copy()
        header_rect.y = palette_rect.bottom() - header_key_border_rect.h
        header_rect.h = header_key_border_rect.h
        key_rects = header_rect.subdivide(len(sequence), 1, *spacing)

        keys = []
        for i, label in enumerate(sequence):
            key = PaletteHeaderKey("_palette_header" + str(i))
            key.type = KeyCommon.BUTTON_TYPE
            key.code  = i
            key.set_border_rect(key_rects[i])
            key.group = header_key_group
            key.color_scheme = color_scheme
            key.unlatch_layer = False
            key.palette_panel = self

            self.configure_header_key(key, label)

            keys.append(key)

        return keys, header_rect

    def configure_header_key(self, key, label):
        key.labels = {0: label}
        key.label_margin = (1, 1)

    def set_active_category_index(self, index):
        if self._active_category_index != index:
            self._active_category_index = index

            # update header keys
            keys_to_redraw = []
            for key in self._header_keys:
                active = (key.code == self._active_category_index)
                if key.active != active:
                    key.active = active
                    keys_to_redraw.append(key)

            self._character_grid.sequences = \
                self.get_grid_labels(self._active_category_index)

            self._character_grid.update_content()

            self.keyboard.layout.invalidate_font_sizes()
            self.keyboard.layout.invalidate_caches()

            self.keyboard.redraw(keys_to_redraw + [self._character_grid])


class EmojiPalettePanel(CharacterPalettePanel):
    """ Emoji palette """

    content_type = "emoji"

    def get_header_labels(self):
        return self._unicode_data.get_emoji_categories()  # + ["⭐"]

    def get_grid_labels(self, category):
        return self._unicode_data.get_emoji(category)

    def configure_header_key(self, key, label):
        fn = emoji_filename_from_sequence(label)
        if fn:
            key.image_filenames = {ImageSlot.NORMAL : fn}
            key.image_style = ImageStyle.DESATURATED
            key.label_margin = EMOJI_IMAGE_MARGIN

        if not key.image_filenames:
            super(EmojiPalettePanel, self).configure_header_key(key, label)


class SymbolPalettePanel(CharacterPalettePanel):
    """ Symbol palette """

    content_type = "symbols"

    def get_header_labels(self):
        return self._unicode_data.get_symbol_categories()

    def get_grid_labels(self, category):
        return self._unicode_data.get_symbols(category)

