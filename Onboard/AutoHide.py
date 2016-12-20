# -*- coding: utf-8 -*-

# Copyright © 2014, 2016 marmuta <marmvta@gmail.com>
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

"""
Hide the keyboard on incoming physical keyboard events.
"""

from Onboard.GlobalKeyListener  import GlobalKeyListener

import logging
_logger = logging.getLogger("AutoHide")

from Onboard.Config import Config
config = Config()


class AutoHide:
    """
    Hide Onboard when a physical keyboard is being used.
    """

    def __init__(self, keyboard):
        self._keyboard = keyboard
        self._key_listener = None

    def cleanup(self):
        self._register_events(False)

    def is_enabled(self):
        return self._key_listener is not None

    def enable(self, enable):
        self._register_events(enable)

    def _register_events(self, register):
        if register:
            if not self._key_listener:
                self._key_listener = GlobalKeyListener()
                self._key_listener.connect("key-press", self._on_key_press)
        else:
            if self._key_listener:
                self._key_listener.disconnect("key-press", self._on_key_press)
            self._key_listener = None

    def _on_key_press(self, event):
        # hide on key-press
        if config.is_auto_hide_on_keypress_enabled():
            if not self._keyboard.is_auto_show_paused():
                self._key_listener.log_key_event(
                    event, "Hiding keyboard and pausing " "auto-show ")

                if self._keyboard.is_visible():
                    if config.are_word_suggestions_enabled():
                        self._keyboard.discard_changes()

                    self._keyboard.set_visible(False)

            duration = config.auto_show.hide_on_key_press_pause
            if duration:
                if duration < 0.0:  # negative means auto-hide is off
                    duration = None
                self._keyboard.pause_auto_show(duration)


