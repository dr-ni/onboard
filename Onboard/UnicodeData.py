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

from Onboard.emoji_data import emoji_data


class UnicodeData:
    """
    Singleton class providing emoji data and general Unicode information.
    """

    _symbol_data = [
        ["α", "αβγδεζηθικλμνξοπρςστυφχψω"        # Greek
              "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"],

        ["ℝ", "ℝℂℕℙℚℤ"                           # math & physics
              "∅∃∄∈∉∀∑∥∦∡⊾∞"
              "∩∪⊂⊃⊄⊅⊈⊉⊆⊇…"
              "≤≥≦≧≨≩"
              "≁≂≃≄≅≆≇≈≉≊≋≌≍"
              "√∛∜"
              "∫∬∭"
              "℃℉№"
         ],
        ["€", "$₠₡₢₣₤₥₦₧₨₩₪₫€₭₮₯₰₱₲₳₴₵₶₷₸₹₺₻₼₽₾"   # currency
              ""
         ],
        ["²₂", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾"                 # super- and subscript
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

    def get_emoji_categories(self):
        return [label for label, data in self._get_emoji_data()]

    def get_emoji(self, category):
        return tuple(sequence
                     for sequence, data in self._get_emoji_data()[category][1])

    def _get_emoji_data(self):
        return emoji_data

    def get_symbol_categories(self):
        return [label for label, data in self._get_symbol_data()]

    def get_symbols(self, category):
        return tuple(self._get_symbol_data()[category][1])

    def _get_symbol_data(self):
        return self._symbol_data


