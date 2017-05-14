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

from Onboard.Layout            import (LayoutPanel, ScrolledLayoutPanel)
from Onboard.KeyGtk            import FlatKey
from Onboard.KeyCommon         import ImageSlot, ImageStyle
from Onboard                   import KeyCommon
from Onboard.UnicodeData       import (UnicodeData,
                                       emoji_filename_from_sequence)
from Onboard.utils             import Rect

from Onboard.Config import Config
config = Config()


EMOJI_IMAGE_MARGIN = (1.5, 2.5)
EMOJI_HEADER_MARGIN = (2.5, 3.5)

FAVORITE_EMOJI_ID = "favourite-emoji"
SEARCH_EMOJI_ID = "search-emoji"


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
        palette_panel = self.get_parent()
        palette_panel.scroll_to_category_index(self.code)


class PaletteFavoritesKey(PaletteHeaderKey):

    def on_release(self, view, button, event_type):
        print("fav")


class CharacterGridPanel(ScrolledLayoutPanel):
    symbol_data = None
    keyboard = None
    has_emoji = False
    key_border_rect = None
    key_group = None
    color_scheme = None
    background_rgba = None

    def __init__(self):
        super(CharacterGridPanel, self).__init__()

        self._key_labels = []
        self._key_rects = []
        self._key_slots = []
        self._key_pool = {}
        self._separator_rects = []
        self._category_rects = []
        self._category_key_rects = []

    def get_fill_color(self):
        return (0, 0, 0, 1)

    def update_log_rect(self):
        self.set_clip_rect(self.get_canvas_border_rect())
        super(CharacterGridPanel, self).update_log_rect()

    def update_content(self):
        flow_rect = self.get_rect()
        flow_rect.w = 0
        key_rect = self.key_border_rect
        key_spacing = (0, 0)
        subcategory_spacing = key_rect.w * 0.25
        key_labels = []
        key_rects = []
        separator_rects = []
        bounding_box = None
        category_rect = None

        subcategories = self.symbol_data.get_subcategories()

        for i, (level, label, data) in enumerate(subcategories):
            sequences = self.symbol_data.get_subcategory_sequences(data)

            rects, bounds = flow_rect.flow_layout(
                key_rect, len(sequences), *key_spacing, True, True)

            key_labels.extend(sequences)
            key_rects.extend(rects)
            bounding_box = bounding_box.union(bounds) \
                if bounding_box is not None else bounds

            # keep track of category bounds (spanning multiple subcategories)
            if level == 0:  # start of category?
                if i > 0:
                    self._category_rects.append(category_rect)
                    self._category_key_rects.append(key_rects)
                category_rect = bounds
            category_rect = category_rect.union(bounds)

            flow_rect.x += bounds.w

            # separator
            if i < len(subcategories) - 1:
                r = flow_rect.copy()
                r.w = subcategory_spacing
                r = r.grow(0.125, 0.75)
                separator_rects.append(r)

            flow_rect.x += subcategory_spacing

        self._category_rects.append(category_rect)
        self._category_key_rects.append(key_rects)

        self._key_labels = key_labels
        self._key_slots = [None] * len(key_rects)
        self._key_rects = key_rects
        self._separator_rects = separator_rects

        self.lock_y_axis(True)
        self.set_scroll_rect(bounding_box)

    def is_background_at(self, log_point):
        for r in self._key_rects:
            if r.is_point_within(log_point):
                return False
        return True

    def scroll_to_category(self, category_index):
        x = 0
        if category_index >= 0 and \
           category_index < len(self._category_rects):
            x = self._category_rects[category_index].x
        self.set_scroll_offset(-x, 0)

    def on_scroll_offset_changed(self):
        offset = -self.get_scroll_offset()[0]
        category_index = 0
        for i, r in enumerate(self._category_rects):
            if offset < r.x:
                break
            category_index = i

        character_panel = self.get_parent()
        character_panel.set_active_category_index(category_index)

    def on_damage(self, damage_rect):
        key_slots = self._key_slots
        items = []

        for ic, category_rect in enumerate(self._category_rects):
            if damage_rect.intersects(category_rect):

                category_key_rects = self._category_key_rects[ic]
                for i, rect in enumerate(category_key_rects):
                    if damage_rect.intersects(rect):
                        key = key_slots[i]
                        if key is None:
                            key = self._get_key(i)
                            key_slots[i] = key
                        items.append(key)
                    else:
                        key_slots[i] = None

        self.set_items(items)

        layout = self.keyboard.layout
        if layout:
            if not self.has_emoji:
                layout.invalidate_font_sizes()
            layout.invalidate_caches()

            self.keyboard.redraw([self])

    def _get_key(self, index):
        id = "_palette_character" + str(index)
        label = self._key_labels[index]

        try:
            key = self._key_pool[label]
        except KeyError:
            key = self._create_key(id, label, self._key_rects[index],
                                   self.key_group, self.color_scheme,
                                   self.has_emoji)

            # only cache emoji keys, as these are the most expensive ones
            if 0:  # self.has_emoji:
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

    def draw_tree(self, context):
        super(CharacterGridPanel, self).draw_tree(context)

        key_context = self.scrolled_context
        clip_rect = self.get_canvas_rect()

        draw_separators(context.cr,
                        clip_rect,
                        [key_context.log_to_canvas_rect(r)
                         for r in self._separator_rects])


class CharacterPalettePanel(LayoutPanel):
    """ Emoji/symbol palette """

    def __init__(self):
        LayoutPanel.__init__(self)
        self.keyboard = None
        self._symbol_data = UnicodeData().get_symbol_data(self.content_type)
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

        # take rect at 100% key size
        remaining_rect = background.get_fullsize_rect().copy()

        # create header keys
        headers = self._symbol_data.get_category_labels() + self.extra_labels
        ks, r = self._create_header_keys(
            remaining_rect,
            header_template.get_border_rect(),
            "_" + self.content_type + "_header",
            color_scheme, headers)
        keys += ks
        remaining_rect.h -= r.h

        # create scrolled panel with grid of keys
        grid = CharacterGridPanel()
        grid.symbol_data = self._symbol_data
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

        grid.update_content()
        self.scroll_to_category_index(0)

    def _create_header_keys(self, palette_rect, header_key_border_rect,
                            header_key_group, color_scheme, sequence):
        spacing = (0, 0)

        header_rect = palette_rect.copy()
        header_rect.y = palette_rect.bottom() - header_key_border_rect.h
        header_rect.h = header_key_border_rect.h
        key_rects = header_rect.subdivide(len(sequence), 1, *spacing)

        keys = []
        for i, label in enumerate(sequence):
            if self.is_favorites_index(i, len(sequence)):
                id_ = FAVORITE_EMOJI_ID
                key = PaletteFavoritesKey(id_)
            else:
                id_ = "_palette_header" + str(i)
                key = PaletteHeaderKey(id_)
            key.type = KeyCommon.BUTTON_TYPE
            key.code  = i
            key.set_border_rect(key_rects[i])
            key.group = header_key_group
            key.color_scheme = color_scheme
            key.unlatch_layer = False

            self.configure_header_key(key, label)

            keys.append(key)

        return keys, header_rect

    def configure_header_key(self, key, label):
        key.labels = {0: label}
        key.label_margin = (1, 1)

    def set_active_category_index(self, index):
        if self._active_category_index != index:
            self._active_category_index = index

            keys_to_redraw = []
            for key in self._header_keys:
                active = (key.code == self._active_category_index)
                if key.active != active:
                    key.active = active
                    keys_to_redraw.append(key)

            self.keyboard.redraw(keys_to_redraw)

    def scroll_to_category_index(self, index):
        self.set_active_category_index(index)
        self._character_grid.scroll_to_category(self._active_category_index)

    def is_favorites_index(self, index, num_keys):
        return False


class EmojiPalettePanel(CharacterPalettePanel):
    """ Emoji palette """

    content_type = "emoji"
    extra_labels = []  # "⭐"

    def configure_header_key(self, key, label):
        fn = emoji_filename_from_sequence(label)
        if fn:
            key.image_filenames = {ImageSlot.NORMAL : fn}
            key.label_margin = EMOJI_IMAGE_MARGIN
            key.label_margin = EMOJI_HEADER_MARGIN

            if label in self.extra_labels:
                key.image_style = ImageStyle.MULTI_COLOR
            else:
                key.image_style = ImageStyle.DESATURATED

        if not key.image_filenames:
            super(EmojiPalettePanel, self).configure_header_key(key, label)

    def on_visibility_changed(self, visible):
        super(CharacterPalettePanel, self).on_visibility_changed(visible)
        if visible:
            self.keyboard.show_symbol_search(self.content_type)
        else:
            self.keyboard.hide_symbol_search()

    def is_favorites_index(self, index, num_keys):
        return False  # index == num_keys - 1


class SymbolPalettePanel(CharacterPalettePanel):
    """ Symbol palette """

    content_type = "symbols"
    extra_labels = []


def draw_separators(cr, clip_rect, rects):
    import cairo

    if not rects:
        return

    rgba = (0.3, 0.3, 0.3, 1.0)
    dark_rgba = (0, 0, 0, 1)
    bright_rgba = rgba

    r = rects[0]
    pat = cairo.LinearGradient(r.x, r.top(), r.x, r.bottom())
    pat.add_color_stop_rgba(0.0, *dark_rgba)
    pat.add_color_stop_rgba(0.5, *bright_rgba)
    pat.add_color_stop_rgba(1.0, *dark_rgba)
    cr.set_source(pat)
    cr.set_line_width(2)

    for rect in rects:
        if clip_rect.intersects(rect):
            xc = rect.get_center_x()
            cr.move_to(xc, rect.top())
            cr.line_to(xc, rect.bottom())
            cr.stroke()


