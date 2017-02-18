#!/usr/bin/python3
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


def emoji_filename_from_sequence(label):
    return emoji_filename_from_codepoints([ord(c) for c in label])


def emoji_filename_from_codepoints(codepoints):
    fn = ""
    for cp in codepoints:
        if cp not in (0x200D, 0xfe0f):
            if fn:
                fn += "-"
            fn += (hex(cp)[2:]).zfill(4)
    return fn + ".svg"


class UnicodeData:
    """
    Singleton class providing emoji data and general Unicode information.
    """

    _symbol_data = [
        [0, "α", "αβγδεζηθικλμνξοπρςστυφχψω"        # Greek
                 "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"],

        [0, "ℝ", "ℝℂℕℙℚℤ"                           # math & physics
                 "∅∃∄∈∉∀∑∥∦∡⊾∞"
                 "∩∪⊂⊃⊄⊅⊈⊉⊆⊇…"
                 "≤≥≦≧≨≩"
                 "≁≂≃≄≅≆≇≈≉≊≋≌≍"
                 "√∛∜"
                 "∫∬∭"
                 "℃℉№"
         ],
        [0, "€", "$₠₡₢₣₤₥₦₧₨₩₪₫€₭₮₯₰₱₲₳₴₵₶₷₸₹₺₻₼₽₾"   # currency
                 ""
         ],
        [0, "²₂", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾"                 # super- and subscript
                  "ⁱ"
                  "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎"
                  "ₐₑₒₓₔₕₖₗₘₙₚₛₜ"
         ],
    ]

    def __new__(cls, *args, **kwargs):
        """
        Singleton magic.
        """
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls, *args, **kwargs)
            cls.self.construct()
        return cls.self

    def __init__(self):
        """
        Called multiple times, don't use this.
        """
        pass

    def construct(self):
        """
        Singleton constructor, runs only once.
        """
        pass

    def cleanup(self):
        pass

    def get_category_labels(self, content_type):
        return [label for level, label, data
                in self._get_symbol_data(content_type)
                if level == 0]

    def get_subcategory_labels(self, content_type):
        return [label for level, label, data
                in self._get_symbol_data(content_type)]

    def get_subcategories(self, content_type, category):
        results = []
        for label, data in self._iter_category(content_type, category):
            results.append(self._get_subcategory_sequences(data))
        return results

    def get_sequences(self, content_type, category):
        results = []
        for label, data in self._iter_category(content_type, category):
            results.extend(self._get_subcategory_sequences(data))
        return results

    @staticmethod
    def _get_subcategory_sequences(data):
        if isinstance(data, str):
            return data
        else:
            return [sequence for sequence, children in data]

    def _iter_category(self, content_type, category):
        """ Walk along the subcategories of category """
        i = -1
        for level, label, data in self._get_symbol_data(content_type):
            if level == 0:
                i += 1
                if i > category:
                    break

            if i == category:
                yield label, data

    def _get_symbol_data(self, content_type):
        if content_type == "emoji":
            from Onboard.emoji_data import emoji_data
            return emoji_data
        elif content_type == "symbols":
            return self._symbol_data
        return None


