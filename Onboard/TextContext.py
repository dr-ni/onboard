# -*- coding: utf-8 -*-
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
#
# Copyright © 2012, marmuta
#
# This file is part of Onboard.

from __future__ import division, print_function, unicode_literals

import time
import unicodedata

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, "
                   "word suggestions not fully functional"))

from Onboard.AtspiStateTracker import AtspiStateTracker, AtspiStateType
from Onboard.TextDomain        import TextDomains 
from Onboard.TextChanges       import TextChanges, TextSpan
from Onboard.utils             import Timer
from Onboard                   import KeyCommon

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

### Logging ###
import logging
_logger = logging.getLogger("WordPrediction")
###############

# keycodes
class KeyCode:
    Return   = 36
    KP_Enter = 104
    C        = 54

# modifiers
class Mod:
    CAPS     = 0x1
    SHIFT    = 0x2
    CTRL     = 0x4


class TextContext:
    """
    Keep track of the current text context and intecept typed key events.
    """

    def cleanup(self):
        pass

    def reset(self):
        pass

    def can_insert_text(self):
        return NotImplementedError()

    def insert_text_at_cursor(self, text):
        return NotImplementedError()

    def delete_text_before_cursor(self, length = 1):
        return NotImplementedError()

    def get_context(self):
        raise NotImplementedError()

    def get_line(self):
        raise NotImplementedError()

    def get_line_cursor_pos(self):
        raise NotImplementedError()

    def get_changes(self):
        raise NotImplementedError()

    def clear_changes(self):
        raise NotImplementedError()


class AtspiTextContext(TextContext):
    """
    Keep track of the current text context with AT-SPI
    """

    _state_tracker = AtspiStateTracker()

    def __init__(self, wp):
        self._wp = wp
        self._accessible = None
        self._can_insert_text = False

        self._text_domains = TextDomains()
        self._text_domain = self._text_domains.get_nop_domain()

        self._changes = TextChanges()
        self._entering_text = False

        self._context = ""
        self._last_context = None
        self._line = ""
        self._last_line = None
        self._line_cursor = 0
        self._span_at_cursor = TextSpan()

        self._update_context_timer = Timer()

    def cleanup(self):
        self._register_atspi_listeners(False)

    def enable(self, enable):
        self._register_atspi_listeners(enable)

    def get_text_domain(self):
        return self._text_domain

    def get_context(self):
        """
        Returns the predictions context, i.e. some range of
        text before the cursor position.
        """
        return self._context \
               if self._accessible else ""

    def get_line(self):
        return self._line \
               if self._accessible else ""

    def get_line_cursor_pos(self):
        return self._line_cursor \
               if self._accessible else 0

    def get_line_past_cursor(self):
        return self._line[self._line_cursor:] \
               if self._accessible else ""

    def get_span_at_cursor(self):
        return self._span_at_cursor \
               if self._accessible else None

    def get_cursor(self):
        return self._span_at_cursor.begin() \
               if self._accessible else 0

    def get_changes(self):
        return self._changes

    def clear_changes(self):
        self._changes.clear()

    def can_insert_text(self):
        """
        Can delete or insert text into the accessible?
        """
        #return False # support for inserting is spotty: not in firefox, terminal
        return bool(self._accessible) and self._can_insert_text

    def delete_text_before_cursor(self, length = 1):
        """ Delete directly, without going through faking key presses. """
        offset = self._accessible.get_caret_offset()
        self._accessible.delete_text(offset - length, offset)

    def insert_text_at_cursor(self, text):
        """
        Insert directly, without going through faking key presses.
        Fails for terminal and firefox, unfortunately.
        """
        offset = self._accessible.get_caret_offset()
        self._accessible.insert_text(offset, text, -1)

    def _register_atspi_listeners(self, register = True):
        st = self._state_tracker
        if register:
            st.connect("text-entry-activated", self._on_text_entry_activated)
            st.connect("text-changed", self._on_text_changed)
            st.connect("text-caret-moved", self._on_text_caret_moved)
            st.connect("key-pressed", self._on_key_pressed)
        else:
            st.disconnect("text-entry-activated", self._on_text_entry_activated)
            st.disconnect("text-changed", self._on_text_changed)
            st.disconnect("text-caret-moved", self._on_text_caret_moved)
            st.disconnect("key-pressed", self._on_key_pressed)

    def get_accessible_capabilities(accessible, **kwargs):
        can_insert_text = False
        attributes = kwargs.get("attributes", {})
        interfaces = kwargs.get("interfaces", [])

        if accessible:

            # Can insert text via Atspi?
            # Advantages: - faster, no individual key presses
            #             - full trouble-free insertion of all unicode characters
            if "EditableText" in interfaces:
                # Support for atspi text insertion is spotty.
                # Firefox, LibreOffice Writer, gnome-terminal don't support it,
                # even if they claim to implement the EditableText interface.

                # Allow direct text insertion by gtk widgets
                if "toolkit" in attributes and attributes["toolkit"] == "gtk":
                   can_insert_text = True

        return can_insert_text

    def _on_text_entry_activated(self, accessible):
        #print("_on_text_entry_activated", accessible)
        # keep track of the active accessible asynchronously
        self._accessible = accessible
        self._entering_text = False

        # select text domain matching this accessible
        state = self._state_tracker.get_state() \
                if self._accessible else {}
        self._text_domain = self._text_domains.find_match(**state)
        self._text_domain.init_domain()

        # determine capabilities of this accessible
        self._can_insert_text = self.get_accessible_capabilities(**state)

        # log accessible info
        if 0:#_logger.isEnabledFor(logging.DEBUG):
            print()
            print("Accessible focused: ")
            if self._accessible:
                state = self._state_tracker.get_state()
                for key, value in sorted(state.items()):
                    msg = str(key) + "="
                    if key == "state-set":
                        msg += repr(AtspiStateType.to_strings(value))
                    else:
                        msg += str(value)
                    print(msg)
                print("text_domain", "=", self._text_domain)
                print("can_insert_text", "=", self._can_insert_text)
                print()
            else:
                print("None")
                print()

        self._update_context()

        self._wp.on_text_entry_activated()

    def _on_text_changed(self, event):
        pos    = event.pos
        length = event.length
        insert = event.insert
        delete = not insert

        char_count = None
        if self._accessible:
            try:
                char_count = self._accessible.get_character_count()
            except: # gi._glib.GError: The application no longer exists
                    # when closing a tab in gnome-terminal.
                char_count = None

        if not char_count is None:
            # record the change
            spans_to_update = []
            if insert:
                #print("insert", pos, length)
                if self._entering_text:
                    if self._wp.is_typing() or length < 30:
                        # Remember all of the insertion, might have been
                        # a pressed snippet or wordlist button.
                        include_length = -1
                    else:
                        # Remember only the first few characters.
                        # Large inserts can be paste, reload or scroll
                        # operations. Only learn the first word of these.
                        include_length = 2
                else:
                    # Remember nothing, just update existing spans.
                    include_length = None

                spans_to_update = self._changes.insert(pos, length,
                                                      include_length)

            elif delete:
                #print("delete", pos, length)
                spans_to_update = self._changes.delete(pos, length,
                                                       self._entering_text)

            # update text of the modified spans
            for span in spans_to_update:
                # Get some more text around the span to hopefully
                # include whole words at beginning and end.
                begin = max(span.begin() - 100, 0)
                end = min(span.end() + 100, char_count)
                span.text = Atspi.Text.get_text(self._accessible, begin, end)
                span.text_pos = begin
                begin =span.begin()

            print(self._changes)

            self._update_context()

    def _on_text_caret_moved(self, event):
        self._update_context()

    def _on_key_pressed(self, event):
        keycode = event.hw_code
        modifiers = event.modifiers

        if self._accessible:
            role = self._state_tracker.get_role()

            # End recording and learn when pressing [Return]
            # in a terminal because text that is scrolled out of view
            # is lost. Also don't record and learn terminal output.
            self._entering_text = True
            if role == Atspi.Role.TERMINAL:
                if keycode == KeyCode.Return or \
                   keycode == KeyCode.KP_Enter:
                    self._entering_text = False
                    self._wp.commit_changes()
                elif keycode == KeyCode.C and modifiers & Mod.CTRL:
                    self._entering_text = False
                    self._wp.discard_changes()

    def _update_context(self):
        self._update_context_timer.start(0.01, self.on_text_context_changed)

    def on_text_context_changed(self):
        (self._context,
         self._line,
         self._line_cursor,
         self._span_at_cursor) = self._text_domain.read_context(self._accessible)

        if self._last_context != self._context or \
           self._last_line != self._line:
            self._last_context = self._context
            self._last_line    = self._line
            self._wp.on_text_context_changed()
        return False


class InputLine(TextContext):
    """
    Track key presses ourselves.
    Advantage: Doesn't require AT-SPI
    Problems:  Misses key repeats,
               Doesn't know about keymap translations before events are
               delivered to their destination, i.e records wrong key
               strokes when changing keymaps.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.line = ""
        self.cursor = 0
        self.valid = True

        self.word_infos = {}

    def is_valid(self):
        return self.valid

    def is_empty(self):
        return len(self.line) == 0

    def insert(self, s):
        self.line   = self.line[:self.cursor] + s + self.line[self.cursor:]
        self.move_cursor(len(s))

    def delete_left(self, n=1):  # backspace
        self.line = self.line[:self.cursor-n] + self.line[self.cursor:]
        self.move_cursor(-n)

    def delete_right(self, n=1): # delete
        self.line = self.line[:self.cursor] + self.line[self.cursor+n:]

    def move_cursor(self, n):
        self.cursor += n

        # moving into unknown territory -> suggest reset
        if self.cursor < 0:
            self.cursor = 0
            self.valid = False
        if self.cursor > len(self.line):
            self.cursor = len(self.line)
            self.valid = False

    def get_context(self):
        return self.line[:self.cursor]

    def get_line(self):
        return self.line

    def get_line_cursor_pos(self):
        return self.cursor

    @staticmethod
    def is_printable(char):
        """
        True for printable keys including whitespace as defined for isprint().
        """
        if char == "\t":
            return True
        return not unicodedata.category(char) in ('Cc','Cf','Cs','Co',
                                                  'Cn','Zl','Zp')
    def track_sent_key(self, key, mods):
        """
        Sync input_line with single key presses.
        WORD_ACTION and MACRO_ACTION do this in press_key_string.
        """
        end_editing = False

        if config.wp.stealth_mode:
            return  True

        id = key.id.upper()
        char = key.get_label()
        #print  id," '"+char +"'",key.action_type
        if char is None or len(char) > 1:
            char = ""

        if key.action_type == KeyCommon.WORD_ACTION:
            pass # don't reset input on word insertion

        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            pass  # simply pressing a modifier shouldn't stop the word

        elif key.action_type == KeyCommon.BUTTON_ACTION:
            pass

        elif key.action_type == KeyCommon.KEYSYM_ACTION:
            if   id == 'ESC':
                self.reset()
            end_editing = True

        elif key.action_type == KeyCommon.KEYPRESS_NAME_ACTION:
            if   id == 'DELE':
                self.delete_right()
            elif id == 'LEFT':
                self.move_cursor(-1)
            elif id == 'RGHT':
                self.move_cursor(1)
            else:
                end_editing = True

        elif key.action_type == KeyCommon.KEYCODE_ACTION:
            if   id == 'RTRN':
                char = "\n"
            elif id == 'SPCE':
                char = " "
            elif id == 'TAB':
                char = "\t"

            if id == 'BKSP':
                self.delete_left()
            elif self.is_printable(char):
                if mods[4]:  # ctrl+key press?
                    end_editing = True
                else:
                    self.insert(char)
            else:
                end_editing = True
        else:
            end_editing = True

        if not self.is_valid(): # cursor moved outside known range?
            end_editing = True

        #print end_editing,"'%s' " % self.line, self.cursor
        return end_editing

