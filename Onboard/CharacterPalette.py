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

import os
import logging
_logger = logging.getLogger(__name__)

from Onboard.Layout            import (LayoutPanel, ScrolledLayoutPanel,
                                       RectangleItem)
from Onboard.KeyGtk            import FlatKey
from Onboard.KeyCommon         import ImageSlot, ImageStyle
from Onboard                   import KeyCommon
from Onboard.UnicodeData       import UnicodeData

from Onboard.Config import Config
config = Config()


EMOJI_IMAGE_MARGIN = (3, 3)


def emoji_filename_from_sequence(label):
    fn = ""
    for c in label:
        cp = ord(c)
        if cp not in (0x200D, 0xfe0f):
            if fn:
                fn += "-"
            fn += hex(cp)[2:]
    return fn + ".svg"


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
    characters = ""
    has_emoji = False
    key_rect = None
    key_group = None
    color_scheme = None
    background_rgba = None

    def update_log_rect(self):
        self.set_clip_rect(self.get_canvas_border_rect())
        super(CharacterGridPanel, self).update_log_rect()

    def update_content(self):
        # create content
        keys = []
        if self.characters:
            keys, r = self._create_content(self.get_border_rect(),
                                           self.key_rect,
                                           self.key_group,
                                           self.color_scheme,
                                           self.characters,
                                           self.has_emoji)

        item = CharacterPaletteBackground()
        item.set_border_rect(self.get_border_rect())
        item.color_scheme = self.color_scheme

        self.set_items([item] + keys)

    @staticmethod
    def _create_content(grid_rect, key_rect, key_group,
                        color_scheme, sequence, has_emoji):
        spacing = (0, 0)

        key_rects, bounds = grid_rect.flow_layout(key_rect, len(sequence),
                                                  *spacing, True)
        keys = []

        for i, label in enumerate(sequence):
            id = "_palette_character" + str(i)
            key = CharacterPaletteKey()
            key.type = KeyCommon.CHAR_TYPE
            key.code  = label
            key.action = KeyCommon.DELAYED_STROKE_ACTION
            key.set_border_rect(key_rects[i])
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

            keys.append(key)

        return keys, bounds


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
            self.create_keys()

    def create_keys(self):
        background = self.find_id("character-palette")
        header_template = self.find_id("palette-header-template")
        key_template = self.find_id("palette-key-template")
        keys = []

        if not background or \
           not header_template or \
           not key_template:
            return []

        color_scheme = key_template.color_scheme
        remaining_rect = background.get_border_rect().copy()

        # create header keys
        headers = self.get_header_labels()
        ks, r = self._create_header_keys(
            remaining_rect,
            header_template.get_border_rect(),
            "_" + self.content_type + "_header",
            color_scheme, headers)
        keys += ks
        remaining_rect.h -= r.h

        # create scrolled panel with grid of keys
        item = CharacterGridPanel()
        item.set_id("_character_grid")
        item.set_border_rect(remaining_rect)
        item.characters = ""
        item.key_rect = key_template.get_border_rect()
        item.key_group = "_" + self.content_type
        item.color_scheme = color_scheme
        item.has_emoji = self.content_type == "emoji"

        self.set_items([background, header_template,
                        key_template, item] + keys)

        self._character_grid = item
        self._header_keys = keys

        self.set_active_category_index(0)

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

            self._character_grid.characters = \
                self.get_grid_labels(self._active_category_index)

            self._character_grid.update_content()

            self.keyboard.layout.invalidate_font_sizes()
            self.keyboard.layout.invalidate_caches()

            self.keyboard.redraw(keys_to_redraw + [self._character_grid])

    def _create_header_keys(self, palette_rect, header_key_rect,
                            header_key_group, color_scheme, sequence):
        spacing = (0, 0)

        header_rect = palette_rect.copy()
        header_rect.y = palette_rect.bottom() - header_key_rect.h
        header_rect.h = header_key_rect.h
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


class EmojiPalettePanel(CharacterPalettePanel):
    """ Emoji palette """

    content_type = "emoji"

    def get_header_labels(self):
        return self._unicode_data.get_emoji_categories()  # + ["⭐"]

    def get_grid_labels(self, category):
        emoji = self._unicode_data.get_emoji(category)
        return self._filter_images_exist(emoji)

    def configure_header_key(self, key, label):
        fn = emoji_filename_from_sequence(label)
        if fn:
            key.image_filenames = {ImageSlot.NORMAL : fn}
            key.image_style = ImageStyle.DESATURATED
            key.label_margin = EMOJI_IMAGE_MARGIN

        if not key.image_filenames:
            super(EmojiPalettePanel, self).configure_header_key(key, label)

    def _filter_images_exist(self, emoji_sequences):
        """
        Drop emoji sequences that have no corresponding EmojiOne image file.
        """
        results = []
        for sequence in emoji_sequences:
            image_filename = emoji_filename_from_sequence(sequence)
            path = config.get_image_filename(image_filename)
            if os.path.isfile(path):
                results.append(sequence)
        return results


class SymbolPalettePanel(CharacterPalettePanel):
    """ Symbol palette """

    content_type = "symbols"

    def get_header_labels(self):
        return self._unicode_data.get_symbol_categories()

    def get_grid_labels(self, category):
        return self._unicode_data.get_symbols(category)

