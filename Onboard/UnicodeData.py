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
        [0, "α", "αβγδεζηθικλμνξοπρςστυφχψω"],        # Greek
        [1, "Α", "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"],

        [0, "ℝ", "ℝℂℕℙℚℤ"                             # math & physics
                 "∅∃∄∈∉∀∑∥∦∡⊾∞"
                 "∩∪⊂⊃⊄⊅⊈⊉⊆⊇…"
                 "≤≥≦≧≨≩"
                 "≁≂≃≄≅≆≇≈≉≊≋≌≍"
                 "√∛∜"
                 "∫∬∭"
                 "℃℉№"
         ],
        [0, "²₂", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾"                   # super- and subscript
                  "ⁱ"
         ],
        [1, "₂", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎"
                 "ₐₑₒₓₔₕₖₗₘₙₚₛₜ"
         ],
        [0, "€", "$₠₡₢₣₤₥₦₧₨₩₪₫€₭₮₯₰₱₲₳₴₵₶₷₸₹₺₻₼₽₾"   # currency
                 ""
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

    def get_symbol_data(self, content_type):
        if content_type == "emoji":
            from Onboard.emoji_data import emoji_data
            return SymbolData(emoji_data)
        elif content_type == "symbols":
            return SymbolData(self._symbol_data)
        return None


class SymbolData:

    def __init__(self, symbol_data):
        self. _symbol_data = symbol_data

    def get_category_labels(self):
        return [label for level, label, data
                in self._symbol_data
                if level == 0]

    def get_subcategories(self):
        """ Walk along all subcategories. """
        return self._symbol_data

    @staticmethod
    def get_subcategory_sequences(data):
        if isinstance(data, str):
            return data
        else:
            return [item if isinstance(item, str) else item[0]
                    for item in data]


