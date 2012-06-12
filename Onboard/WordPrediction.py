# -*- coding: latin-1 -*-

from __future__ import division, print_function, unicode_literals

import sys
import os, errno
import codecs
import unicodedata
import re
from contextlib import contextmanager, closing
from traceback import print_exc
import dbus

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, "
                   "word prediction may not be fully functional"))

from Onboard              import KeyCommon
from Onboard.AtspiUtils   import AtspiStateTracker
from Onboard.utils        import CallOnce, unicode_str

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

### Logging ###
import logging
_logger = logging.getLogger("WordPrediction")
###############


class WordPrediction:
    """ Keyboard mixin for word prediction """

    def __init__(self):

        # prepare text contexts
        self.input_line = InputLine()
        self.atspi_text_context = AtspiTextContext(self, self.atspi_state_tracker)
        self.text_context = None

        self.punctuator = Punctuator()
        self.predictor  = None

        self.word_choices = []
        self.word_infos = []

        self._hide_input_line = False

    def on_layout_loaded(self):
        self.enable_word_prediction(config.wp.enabled)

    def send_press_key(self, key, button, event_type):
        if key.action_type == KeyCommon.WORD_ACTION:
            s  = self._get_match_remainder(key.action) # unicode
            if config.wp.auto_punctuation and \
               button != 3: # right click suppresses punctuation
                self.punctuator.set_end_of_word()
            self.press_key_string(s)

    def enable_word_prediction(self, enable):
        if enable:
            # only load dictionaries if there is a
            # dynamic or static wordlist in the layout
            if self.find_keys_from_ids(("wordlist", "word0")):
                self.predictor = WordPredictor()
                self.apply_prediction_profile()
        else:
            if self.predictor:
                self.predictor.save_dictionaries()
            self.predictor = None

        # show/hide word-prediction buttons
        for item in self.layout.iter_items():
            if item.group in ("inputline", "wordlist", "word", "wpbutton"):
                item.visible = enable

        # Init text context tracking.
        # Keep track in and write to both contexts in parallel,
        # but read only from the active one.
        if self.text_context:
            self.text_context.cleanup() # deregister AT-SPI listeners
        if enable:
            if True:
                self.text_context = self.atspi_text_context
            else:
                self.text_context = self.input_line
            self.text_context.enable(True) # register AT-SPI listerners
        else:
            self.text_context = None

    def update_key_ui(self):
        self.update_inputline()
        self.update_wordlists()

        self.update_layout()

    def update_wordlists(self):
        if self.predictor:
            for item in self.find_keys_from_ids(["wordlist"]):
                word_template = item.find_ids(["word"])
                word_template = word_template[0] if word_template else None
                word_keys = self.create_wordlist_keys(self.word_choices,
                                                item.get_rect(), item.context,
                                                word_template)
                fixed_keys = item.find_ids(["word", "wordlistbg"])
                item.set_items(fixed_keys + word_keys)
                self.redraw([item])

    def find_word_choices(self):
        """ word prediction: find choices, only once per key press """
        self.word_choices = []
        if self.predictor:
            context = self.text_context.get_context()
            self.word_choices = self.predictor.predict(context)
            #print "line='%s'" % self.text_context.get_line()

            # update word information for the input line display
            self.word_infos = self.predictor.get_word_infos( \
                                               self.text_context.get_line())

    def on_text_context_changed(self):
        """ The text of the target widget changed or the cursor moved """
        self.find_word_choices()
        self.update_key_ui()

    def _get_match_remainder(self, index):
        """ returns the rest of matches[index] that hasn't been typed yet """
        if not self.predictor:
            return ""
        text = self.text_context.get_context()
        word_prefix = self.predictor.get_last_context_token(text)
        #print self.word_choices[index], word_prefix
        return self.word_choices[index][len(word_prefix):]

    def commit_input_line(self):
        """ word prediction: try to learn all words and clear the input line """
        if self.text_context is self.input_line:
            if self.predictor and config.wp.can_auto_learn():
                self.predictor.learn_text(self.text_context.get_line(), True)

        self.reset_text_context()
        self.punctuator.reset()
        self.word_choices = []

    def reset_text_context(self):
        """
        Reset all contexts and cancel whatever has accumulated for learning.
        """
        self.atspi_text_context.reset()
        self.input_line.reset()

    def apply_prediction_profile(self):
        if self.predictor:
            # todo: settings
            system_models = ["lm:system:en"]
            user_models = ["lm:user:en"]
            auto_learn_model = user_models
            self.predictor.set_models(system_models,
                                      user_models,
                                      auto_learn_model)

    def send_punctuation_prefix(self, key):
        if config.wp.auto_punctuation:
            if key.action_type == KeyCommon.KEYCODE_ACTION:
                char = key.get_label()
                prefix = self.punctuator.build_prefix(char) # unicode
                self.press_key_string(prefix)

    def send_punctuation_suffix(self):
        """
        Type the last part of the punctuation and possibly enable
        handle capitalization for the next key press
        """
        if config.wp.auto_punctuation:
            suffix = self.punctuator.build_suffix() # unicode
            if suffix and self.press_key_string(suffix):

                # unlatch left shift
                for key in self.find_keys_from_ids(["LFSH"]):
                    if key.active:
                        key.active = False
                        key.locked = False
                        if key in self._latched_sticky_keys:
                            self._latched_sticky_keys.remove(key)
                        if key in self._locked_sticky_keys:
                            self._locked_sticky_keys.remove(key)

                # latch right shift for capitalization
                for key in self.find_keys_from_ids(["RTSH"]):
                    key.active = True
                    key.locked = False
                    if not key in self._latched_sticky_keys:
                        self._latched_sticky_keys.append(key)
                self.vk.lock_mod(1)
                self.mods[1] = 1   # shift
                self.redraw()   # redraw the whole keyboard

    def hide_input_line(self, hide = True):
        """
        Temporarily hide the input line to access keys below it.
        """
        self._hide_input_line = hide
        self.update_inputline()

    def update_inputline(self):
        """ Refresh the GUI displaying the current line's content """
        if self.predictor:
            for key in self.find_keys_from_ids(["inputline"]):
                if self._hide_input_line:
                    key.visible = False
                else:
                    line = self.text_context.get_line()
                    if line:
                        key.raise_to_top()
                        key.visible = True
                    else:
                        line = u""
                        key.visible = False

                    key.set_content(line, self.word_infos,
                                    self.text_context.get_line_cursor_pos())
                self.redraw([key])
                # print [(x.start, x.end) for x in word_infos]

    def show_input_line_on_key_release(self, key):
        if self._hide_input_line and \
           not self._key_intersects_input_line(key):
            self._hide_input_line = False

    def _key_intersects_input_line(self, key):
        """ Check if key shares space with the input line. """
        for item in self.find_keys_from_ids(["inputline"]):
            if item.get_border_rect().intersects(key.get_border_rect()):
                return True
        return False


class TextContext:
    """
    Keep track of the current text context and intecept typed key events.
    """

    def cleanup(self):
        pass

    def reset(self):
        pass

    def track_sent_key(key, mods):
        return False

    def get_context(self):
        raise NotImplementedError()

    def get_line(self):
        raise NotImplementedError()

    def get_line_cursor_pos(self):
        raise NotImplementedError()


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
        self.line = u""
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
        if char == u"\t":
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
            char = u""

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
                char = u"\n"
            elif id == 'SPCE':
                char = u" "
            elif id == 'TAB':
                char = u"\t"

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


class AtspiTextContext(TextContext):
    """
    Keep track of the current text context with AT-SPI
    """

    _keyboard = None
    _state_tracker = None
    _atspi_listeners_registered = False
    _accessible = None

    _context = ""
    _last_context = None
    _line = ""
    _last_line = None
    _line_cursor = 0


    def __init__(self, keyboard, state_tracker):
        self._keyboard = keyboard
        self._state_tracker = state_tracker
        self._call_once = CallOnce(100).enqueue  # delay callbacks

    def cleanup(self):
        self._register_atspi_listeners(False)
        self.state_tracker = None

    def enable(self, enable):
        self._register_atspi_listeners(enable)

    def _register_atspi_listeners(self, register = True):
        # register with atspi state tracker
        if register:
            self._state_tracker.connect("text-entry-activated",
                                        self._on_text_entry_activated)
        else:
            self._state_tracker.disconnect("text-entry-activated",
                                           self._on_text_entry_activated)

        if register:
            if not self._atspi_listeners_registered:
                Atspi.EventListener.register_no_data(self._on_text_changed,
                                                    "object:text-changed")
                Atspi.EventListener.register_no_data(self._on_text_caret_moved,
                                                    "object:text-caret-moved")
                self._atspi_listeners_registered = True
        else:
            if self._atspi_listeners_registered:

                Atspi.EventListener.deregister_no_data(self._on_text_changed,
                                                     "object:text-changed")
                Atspi.EventListener.deregister_no_data(self._on_text_caret_moved,
                                                     "object:text-caret-moved")
                self._atspi_listeners_registered = False

    def _on_keystroke(self, event, data):
        #print("_on_keystroke", event.modifiers, event.hw_code, event.type, event.event_string)
        return False # don't consume event

    def _on_pointer_button(self, event, data):
        #if event.id in [1, 2]:
         #   self._update_context()
        return False # don't consume event

    def _on_text_changed(self, event):
        if event.source is self._accessible:
            print("_on_text_changed", event.detail1, event.detail2, event.source, event.type)
            change_position = event.detail1
            changed_length = event.detail2
            self._update_context()
        return False

    def _on_text_caret_moved(self, event):
        if event.source is self._accessible:
            print("_on_text_caret_moved", event.detail1, event.detail2, event.source, event.type, event.source.get_name(), event.source.get_role())
            caret = event.detail1
            self._update_context()
        return False

    def _on_text_entry_activated(self, accessible, active):
        #print("_on_text_entry_activated", accessible, active)
        if accessible and active:
            self._accessible = accessible
        else:
            self._accessible = None
        self._update_context()

    def get_context(self):
        """
        Returns the predictions context, i.e. same range of
        text before the cursor position.
        """
        return self._context

    def get_line(self):
        return self._line

    def get_line_cursor_pos(self):
        return self._line_cursor

    def _update_context(self):
        self._call_once(self._do_update_context)

    def _do_update_context(self):
        self._context, self._line, self._line_cursor = \
                                 self._read_context(self._accessible)

        if self._last_context != self._context or \
           self._last_line != self._line:
            self._last_context = self._context
            self._lasr_line    = self._line

            #print(repr(self.get_context()))
            self._keyboard.on_text_context_changed()

    def _read_context(self, accessible):
        context = ""
        line = ""
        line_cursor = -1

        if accessible:
            offset = accessible.get_caret_offset()
            role = self._state_tracker.get_role()

            r = accessible.get_text_at_offset(offset,
                                Atspi.TextBoundaryType.LINE_START)
            line = unicode_str(r.content).replace("\n","")
            line_cursor = max(offset - r.start_offset, 0)

            if role == Atspi.Role.TERMINAL:
                # remove prompt from the current or previous lines
                l = line[:line_cursor]
                for i in range(2):
                    line_start = self._find_prompt(l)
                    context = context + l[line_start:]
                    if i == 0:
                        line = line[line_start:] # cut prompt from input line
                    if line_start:
                        break

                    # no prompt yet -> let context reach
                    # across one more line break
                    r = accessible.get_text_before_offset(offset,
                                        Atspi.TextBoundaryType.LINE_START)
                    l = unicode_str(r.content)

                # remove newlines
                context = context.replace("\n","")

            elif role == Atspi.Role.PASSWORD_TEXT:
                context = ""

            else:
                content = Atspi.Text.get_text(accessible,
                                              max(offset - 256, 0), offset)
                context = unicode_str(content)

        return context, line, line_cursor

    def _find_prompt(self, context):
        """
        Search for a prompt and return the offset where the user input starts.
        Until we find a better way just look for some common prompt patterns.
        """
        if not hasattr(self, "_compiled_patterns"):
            patterns = [
                        "^gdb$ ",
                        "^>>> ", # python
                        "^In \[[0-9]*\]: ",   # ipython
                        "^:",    # vi command mode
                        "^/",    # vi search
                        "^\?",   # vi reverse search
                        "\$ ",   # generic prompt
                        "# ",    # root prompt
                       ]
            self._compiled_patterns = [re.compile(p) for p in patterns]

        for pattern in self._compiled_patterns:
            match = pattern.search(context)
            if match:
                return match.end()
        return 0


class Punctuator:
    """
    Punctiation assistance. Mainly adds and removes spaces around
    punctuation depending on the user action immediately after word completion.
    """
    BACKSPACE  = u"\b"
    CAPITALIZE = u"\x0e"  # abuse U+000E SHIFT OUT to signal upper case

    def __init__(self):
        self.reset()

    def reset(self):
        self.end_of_word = False
        self.space_added = False
        self.prefix = u""
        self.suffix = u""

    def set_end_of_word(self, val=True):
        self.end_of_word = val;

    def build_prefix(self, char):
        """ return string to insert before sending keypress char """
        self.prefix = u""
        self.suffix = u""
        if self.space_added:  # did we previously add a trailing space?
            self.space_added = False

            if   char in u",:;":
                self.prefix = self.BACKSPACE
                self.suffix = " "

            elif char in u".?!":
                self.prefix = self.BACKSPACE
                self.suffix = " " + self.CAPITALIZE

        return self.prefix

    def build_suffix(self):
        """ add additional characters after the key press"""
        if self.end_of_word:
            self.space_added = True
            self.end_of_word = False
            return u" "
        else:
            return self.suffix


class WordPredictor:
    """ Low level word predictor, D-Bus glue code. """

    def __init__(self):
        self.service = None
        self.recency_ratio = 50  # 0=100% frequency, 100=100% time

    def set_models(self, system_models, user_models, auto_learn_models):

        # auto learn language model must be part of the user models
        for model in auto_learn_models:
            if model not in user_models:
                auto_learn_models = None
                _logger.warning("No auto learn model selected. "
                                "Please setup learning first.")
                break

        self.models = system_models + user_models
        self.auto_learn_models = auto_learn_models

    def predict(self, context_line):
        """ runs the completion/prediction """

        choices = []
        for retry in range(2):
            with self.get_service() as service:
                if service:
                    choices = service.predict(self.models, context_line, 50)
                break

        return choices

    def learn_text(self, text, allow_new_words):
        """ Count n-grams and add words to the auto-learn models. """
        if self.auto_learn_models:
            for retry in range(2):
                with self.get_service() as service:
                    if service:
                        tokens = service.learn_text(self.auto_learn_models,
                                                    text, allow_new_words)
                break

    def get_word_infos(self, text):
        """
        Return WordInfo objects for each word in text
        """

        # split text into words and lookup each word
        # count is 0 for no match, 1 for exact match or -n for partial matches
        tokens = []
        counts = []
        for retry in range(2):
            with self.get_service() as service:
                if service:
                    tokens, counts = service.lookup_text(self.models, text)
            break

        wis = []
        for i,t in enumerate(tokens):
            start, end, token = t
            word = text[start:end]
            wi = WordInfo(start, end, word)
            wi.exact_match   = any(count == 1 for count in counts[i])
            wi.partial_match = any(count  < 0 for count in counts[i])
            wi.ignored       = word != token
            wis.append(wi)

        return wis

    def tokenize_context(self, text):
        """ let the service find the words in text """
        for retry in range(2):
            with self.get_service() as service:
                if service:
                    tokens = service.tokenize_context(text)
            break
        return tokens

    def get_last_context_token(self, text):
        """ return the very last (partial) word in text """
        tokens = self.tokenize_context(text[-1024:])
        if len(tokens):
            return tokens[-1]
        else:
            return ""


    @contextmanager
    def get_service(self):
        try:
            if not self.service:
                bus = dbus.SessionBus()
                self.service = bus.get_object("org.freedesktop.WordPrediction",
                                               "/WordPredictor")
        except dbus.DBusException:
            #print_exc()
            _logger.error("Failed to acquire D-Bus prediction service")
            self.service = None
            yield None
        else:
            try:
                yield self.service
            except dbus.DBusException:
                print_exc()
                _logger.error("D-Bus call failed. Retrying.")
                self.service = None

class WordInfo:
    """ Word level information about found matches """

    exact_match = False
    partial_match = False
    ignored = False

    def __init__(self, start, end, word):
        self.start = start
        self.end   = end
        self.word  = word

    def __str__(self):
        return  "'%s' %d-%d unknown=%s exact=%s partial=%s ignored=%s" % \
                 (self.word, self.start, self.end,
                 self.unknown, self.exact_match, \
                 self.partial_match, self.ignored)

