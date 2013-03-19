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

import sys
import os, errno
import locale
import time
import codecs
import re
from traceback import print_exc

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, "
                   "word prediction may not be fully functional"))

import Onboard.pypredict as pypredict

from Onboard                   import KeyCommon
from Onboard.TextContext       import AtspiTextContext, InputLine
from Onboard.TextChanges       import TextSpan
from Onboard.SpellChecker      import SpellChecker
from Onboard.LanguageSupport   import LanguageDB
from Onboard.Layout            import LayoutPanel
from Onboard.AtspiStateTracker import AtspiStateTracker
from Onboard.WPEngine          import WPLocalEngine
from Onboard.utils             import CallOnce, unicode_str, Timer, TimerOnce, \
                                      get_keysym_from_name

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

### Logging ###
import logging
_logger = logging.getLogger(__name__)
###############


class WordSuggestions:
    """ Keyboard mix-in for word prediction """

    def __init__(self):

        self.input_line = InputLine()
        self.atspi_text_context = AtspiTextContext(self)
        self.text_context = self.atspi_text_context  # initialize for doctests
        self._learn_strategy = LearnStrategyLRU(self)

        self._languagedb = LanguageDB(self)
        self._spell_checker = SpellChecker(self._languagedb)
        self._punctuator = Punctuator(self)
        self._wpengine  = None

        self._correction_choices = []
        self._correction_span = None
        self._prediction_choices = []
        self.word_infos = []

        self._hide_input_line = False
        self._word_list_bars = []
        self._text_displays = []

        self._focusable_count = 0

    def cleanup(self):
        self.commit_changes()
        if self.text_context:
            self.text_context.cleanup()
        if self._wpengine:
            self._wpengine.cleanup()

    def on_layout_loaded(self):
        self._word_list_bars = self.find_items_from_classes((WordListPanel,))
        self._text_displays = self.find_items_from_ids(("inputline",))
        self.enable_word_suggestions(config.are_word_suggestions_enabled())

    def enable_word_suggestions(self, enable):

        # show/hide word-prediction buttons
        for item in self.get_word_list_bars():
            item.visible = enable
        for item in self.get_text_displays():
            item.visible = enable

        # show/hide other word list dependent layout items
        layout = self.layout
        if layout:
            for item in layout.iter_global_items():
                if item.group == 'wordlist':
                    item.visible = enable
                elif item.group == 'nowordlist':
                    item.visible = not enable

        self.update_wp_engine()
        self.update_spell_checker()

    def update_wp_engine(self):
        enable = config.is_typing_assistance_enabled()

        if enable:
            # only enable if there is a wordlist in the layout
            if self.get_word_list_bars():
                self._wpengine = WPLocalEngine()
                self.apply_prediction_profile()
        else:
            if self._wpengine:
                self._wpengine.cleanup()
            self._wpengine = None

        # Init text context tracking.
        # Keep track in and write to both contexts in parallel,
        # but read only from the active one.
        self.text_context = self.atspi_text_context
        self.text_context.enable(enable) # register AT-SPI listerners

    def on_word_suggestions_enabled(self, enabled):
        """ Config callback for word_suggestions.enabled changes. """
        self.enable_word_suggestions(config.are_word_suggestions_enabled())
        self.invalidate_ui()
        self.commit_ui_updates()

    def apply_prediction_profile(self):
        if self._wpengine:
            lang_id = self.get_lang_id()
            system_lang_id = self._languagedb \
                             .find_system_model_language_id(lang_id)

            system_models  = ["lm:system:" + system_lang_id]
            user_models    = ["lm:user:" + lang_id]
            scratch_models = ["lm:mem"]

            persistent_models = system_models + user_models
            models = system_models + user_models + scratch_models
            auto_learn_models = user_models

            _logger.info("selecting language models: "
                         "system={} user={} auto_learn={}" \
                        .format(repr(system_models),
                                repr(user_models),
                                repr(auto_learn_models)))

            # auto-learn language model must be part of the user models
            for model in auto_learn_models:
                if model not in user_models:
                    auto_learn_models = None
                    _logger.warning("No auto learn model selected. "
                                    "Please setup learning first.")
                    break

            self._wpengine.set_models(persistent_models,
                                      auto_learn_models,
                                      scratch_models)

            # Make sure to load the language models, so there is no
            # delay on first key press. Don't burden the startup
            # with this either, run it a little delayed.
            TimerOnce(1, self._wpengine.load_models)

    def get_system_model_names(self):
        """ Union of all system and user models """
        return self._wpengine.get_model_names("system")

    def get_merged_model_names(self):
        """ Union of all system and user models """
        names = []
        if self._wpengine:
            system_models = set(self._wpengine.get_model_names("system"))
            user_models = set(self._wpengine.get_model_names("user"))
            names = list(system_models.union(user_models))
        return names

    def get_lang_id(self):
        """
        Current language id; never None.
        """
        lang_id = self.get_active_lang_id()
        if not lang_id:
            lang_id = locale.getdefaultlocale()[0]
        return lang_id

    def get_active_lang_id(self):
        """
        Current language id; None for system default language.
        """
        return config.typing_assistance.active_language

    def on_active_lang_id_changed(self):
        self.update_spell_checker()
        self.apply_prediction_profile()
        self.invalidate_context_ui()
        self.commit_ui_updates()

    def set_active_lang_id(self, lang_id):
        config.typing_assistance.active_language = lang_id
        self.on_active_lang_id_changed()

    def get_word_list_bars(self):
        """
        Return all word list bars, so we don't have
        to look for them all the time.
        """
        return self._word_list_bars

    def get_text_displays(self):
        """
        Return all text feedback items, so we don't have
        to look for them all the time.
        """
        return self._text_displays

    def get_spellchecker_dicts(self):
        return self._spell_checker.get_supported_dict_ids()

    def send_key_up(self, key, button, event_type):
        key_type = key.type
        if key_type == KeyCommon.CORRECTION_TYPE:
            self._insert_correction_choice(key, key.code)

        elif key_type == KeyCommon.WORD_TYPE:
            # no punctuation assistance on right click
            self._insert_prediction_choice(key, key.code, button != 3)

        if key_type in [KeyCommon.WORD_TYPE,
                        KeyCommon.CORRECTION_TYPE,
                        KeyCommon.MACRO_TYPE]:
            self.text_context.on_onboard_typing(key, self.get_mod_mask())

    def on_before_key_press(self, key):
        if not key.is_modifier() and not key.is_button():
            self._punctuator.on_before_press(key)
        self.text_context.on_onboard_typing(key, self.get_mod_mask())

    def on_after_key_release(self, key):
        self._punctuator.on_after_release(key)
        if not key.is_correction_key():
            self.expand_corrections(False)

    def enter_caps_mode(self):
        """
        Do what has to be done so that the next pressed
        character will be capitalized.
        """
        lfsh_keys = self.find_items_from_ids(["LFSH"])
        rtsh_keys = self.find_items_from_ids(["RTSH"])

        # unlatch all shift keys
        for key in rtsh_keys + lfsh_keys:
            if key.active:
                key.active = False
                key.locked = False
                if key in self._latched_sticky_keys:
                    self._latched_sticky_keys.remove(key)
                if key in self._locked_sticky_keys:
                    self._locked_sticky_keys.remove(key)
            self.redraw([key])

        # Latch right shift for capitalization,
        # if there is no right shift latch left shift instead.
        shift_keys = rtsh_keys if rtsh_keys else lfsh_keys
        for key in shift_keys:
            if not key.active:
                key.active = True
                if not key in self._latched_sticky_keys:
                    self._latched_sticky_keys.append(key)
                self.redraw([key])

        self._key_synth.lock_mod(1)
        self.mods[1] = 1   # shift
        self.redraw_labels(False)

    def on_spell_checker_changed(self):
        self.update_spell_checker()
        self.commit_ui_updates()

    def update_spell_checker(self):
        # select the backend
        backend = config.typing_assistance.spell_check_backend \
                  if config.is_spell_checker_enabled() \
                  else None
        self._spell_checker.set_backend(backend)

        if not backend is None:
            # chose dicts
            lang_id = self.get_lang_id()
            dict_ids = [lang_id] if lang_id else []
            self._spell_checker.set_dict_ids(dict_ids)

        self.invalidate_context_ui()

    def update_suggestions_ui(self):
        self._update_correction_choices()
        self._update_prediction_choices()
        keys_to_redraw = self.update_inputline()
        keys_to_redraw.extend(self.update_wordlists())
        return keys_to_redraw

    def update_wordlists(self):
        keys_to_redraw = []
        items = self.get_word_list_bars()
        for item in items:
            keys = item.create_keys(self._correction_choices,
                                    self._prediction_choices)
            keys_to_redraw.extend(keys)

        # layout changed, but doesn't know it yet
        # -> invalidate all item caches
        if self.layout:
            self.layout.invalidate_caches()

        for key in keys_to_redraw:
            key.configure_label(0)

        return items + keys_to_redraw

    def update_language_ui(self):
        return []

    def _has_suggestions(self):
        return bool(self._correction_choices or self._prediction_choices)

    def expand_corrections(self, expand):
        # collapse all expanded corrections
        for item in self.find_items_from_classes((WordListPanel)):
            if item.are_corrections_expanded():
                item.expand_corrections(expand)
                self.redraw([item])

    def _insert_correction_choice(self, key, choice_index):
        """ spelling correction clicked """
        span = self._correction_span # span to correct
        with self.suppress_modifiers():
            self._replace_text(span.begin(), span.end(),
                               self.text_context.get_span_at_cursor().begin(),
                               self._correction_choices[choice_index])

    def _insert_prediction_choice(self, key, choice_index, allow_separator):
        """ prediction choice clicked """
        deletion, insertion = \
                self._get_prediction_choice_remainder(choice_index)

        separator = ""
        if config.wp.punctuation_assistance and \
           allow_separator:
            # simulate the change
            cursor_span = self.text_context.get_span_at_cursor()
            context = self._simulate_insertion(cursor_span, deletion, insertion)

            # should we add a separator character after the inserted word?
            domain = self.text_context.get_text_domain()
            separator = domain.get_auto_separator(context)

        # type remainder/replace word and possibly add separator
        added_separator = self._replace_text_at_cursor(deletion, insertion,
                                                       separator)
        self._punctuator.set_added_separator(added_separator)

    def _simulate_insertion(self, cursor_span, deletion, insertion):
        """
        Return the context up to cursor_span with deletion
        and insertion applied.

        Doctests:
        >>> ws = WordSuggestions()
        >>> ws._simulate_insertion(TextSpan(0, 0, ""), "", "")
        ''
        >>> ws._simulate_insertion(TextSpan(0, 0, ""), "", "local")
        'local'
        >>> ws._simulate_insertion(TextSpan(8, 0, ""), "log", "")
        ''
        >>> ws._simulate_insertion(TextSpan(0, 0, ""), "log", "local")
        'local'
        >>> ws._simulate_insertion(TextSpan(6, 0, "/var/l"), "", "og")
        '/var/log'
        >>> ws._simulate_insertion(TextSpan(8, 0, "/var/log"), "log", "local")
        '/var/local'
        >>> ws._simulate_insertion(TextSpan(8, 0, "/var/log"), "log", "")
        '/var/'
        """
        context = cursor_span.get_text_until_span()
        if deletion:
            context = context[:-len(deletion)]
        context += insertion
        return context

    def _update_correction_choices(self):
        self._correction_choices = []
        self._correction_span = None

        if self._spell_checker and \
           config.are_spelling_suggestions_enabled() and \
           self.can_spell_check():
            word_span = self._get_word_to_spell_check()
            if word_span:
                (self._correction_choices,
                self._correction_span,
                auto_capitalization) = \
                            self._find_correction_choices(word_span, False)

    def _find_correction_choices(self, word_span, auto_capitalize):
        """
        Find spelling suggestions for the word at or before the cursor.

        Doctests:
        >>> ws = WordSuggestions()
        >>> f = ws._find_correction_choices
        >>> ws._spell_checker.set_backend(0)
        >>> ws._spell_checker.set_dict_ids(["en_US"])
        True

        # auto-capitalization
        >>> f(TextSpan(0, 7, "Jupiter"), True)
        ([], None, None)
        >>> f(TextSpan(0, 7, "jupiter"), True)             # doctest: +ELLIPSIS
        (['Jupiter', ...], TextSpan(0, 7, 'jupiter', 0, None), 'Jupiter')
        >>> f(TextSpan(0, 7, "jupiter-orbit"), True)       # doctest: +ELLIPSIS
        (['Jupiter', ...], TextSpan(0, 7, 'jupiter', 0, None), 'Jupiter')
        >>> f(TextSpan(0, 3, "usa"), True)                 # doctest: +ELLIPSIS
        (['USA', ...], TextSpan(0, 3, 'usa', 0, None), 'USA')
        >>> f(TextSpan(0, 3, "Usa"), True)                 # doctest: +ELLIPSIS
        (['USA', ...], TextSpan(0, 3, 'Usa', 0, None), 'USA')
        """
        correction_choices = []
        correction_span = None
        auto_capitalization = None

        text_begin = word_span.text_begin()
        word = word_span.get_span_text()
        cursor = self.text_context.get_cursor()
        offset = cursor - text_begin # cursor offset into the word

        span, choices = \
                self._spell_checker.find_corrections(word, offset)
        if choices:
            correction_choices = choices
            correction_span = TextSpan(span[0] + text_begin,
                                       span[1] - span[0],
                                       span[2],
                                       span[0] + text_begin)

            # See if there is a valid upper caps variant for
            # auto-capitalization.
            if auto_capitalize:
                choice = correction_choices[0]
                if word.upper() == choice.upper():
                    auto_capitalization = choice

                elif word and word[0].islower():
                    word_caps = word.capitalize()
                    span, choices = self._spell_checker. \
                            find_corrections(word_caps, offset)
                    if not choices:
                        auto_capitalization = word_caps

        #print("_find_correction_choices", word_span, word_span.get_text(), self._correction_choices, self._correction_span)
        return correction_choices, correction_span, auto_capitalization

    def _update_prediction_choices(self):
        """ word prediction: find choices, only once per key press """
        self._prediction_choices = []
        text_context = self.text_context

        if self._wpengine:

            context = text_context.get_context()
            if context: # don't load models on startup
                max_choices = config.wp.max_word_choices
                bot_context = text_context.get_bot_context()
                bot_marker = text_context.get_text_begin_marker()
                tokens = self._wpengine.tokenize_context(bot_context)

                case_insensitive, ignore_non_caps, \
                capitalize, drop_capitalized = \
                       self._get_prediction_options(tokens,
                                                    bool(self.mods[1]),
                                                    bot_marker)

                _choices = self._wpengine.predict(bot_context,
                            max_choices * 2,
                            case_insensitive = case_insensitive,
                            accent_insensitive = config.wp.accent_insensitive,
                            ignore_non_capitalized = ignore_non_caps)

                choices = []
                for choice in _choices:
                    # Filter out begin of text markers that sneak in as
                    # high frequency unigrams.
                    if choice.startswith("<bot:"):
                        continue

                    # Drop upper caps spelling in favor of a lower caps one.
                    # Auto-capitalization may elect to upper caps on insertion.
                    if drop_capitalized:
                        choice_lower = choice.lower()
                        if choice != choice_lower and \
                           self._wpengine.word_exists(choice_lower):
                            continue

                    choices.append(choice)

                choices = choices[:max_choices]

                # Make all words start upper case
                if capitalize:
                    choices = self._capitalize_choices(choices)
            else:
                choices = []

            self._prediction_choices = choices

            # update word information for the input line display
            #self.word_infos = self.get_word_infos(self.text_context.get_line())

    @staticmethod
    def _get_prediction_options(tokens, shift, bot_marker = None):
        """
        Determine prediction options.

        Doctests:
        >>> get_options = WordSuggestions._get_prediction_options

        # mid-sentence, no tokens
        >>> get_options([], False)
        (False, False, False, False)

        # mid-sentence, lowercase
        >>> get_options(["<s>", "Word", "prefix"], False)
        (True, False, False, True)

        # mid-sentence, capitalized
        >>> get_options(["<s>", "Word", "Prefix"], False)
        (False, True, False, False)

        # mid-sentence, empty prefix
        >>> get_options(["<s>", "Word", ""], False)
        (True, False, False, False)

        # mid-sentence, empty prefix, with shift
        >>> get_options(["<s>", "Word", ""], True)
        (False, True, False, False)

        # sentence begin, lowercase
        >>> get_options(["<s>", "prefix"], False)
        (True, False, False, False)

        # sentence begin, capitalized
        >>> get_options(["<s>", "Prefix"], False)
        (True, False, True, False)

        # sentence begin, empty prefix
        >>> get_options(["<s>", ""], False)
        (True, False, False, False)

        # sentence begin, empty prefix, with shift
        >>> get_options(["<s>", ""], True)
        (True, False, True, False)

        # sentence begin with bot marker.
        >>> get_options(["<bot:txt>", "Prefix"], True, "<bot:txt>")
        (True, False, True, False)
        """
        if tokens:
            prefix = tokens[-1]
            sentence_begin = len(tokens) >= 2 and \
                             (tokens[-2] == "<s>" or \
                              bool(bot_marker) and tokens[-2] == bot_marker)
            capitalized = bool(prefix) and prefix[0].isupper()
            empty_prefix = not bool(prefix)

            case_insensitive = not (not sentence_begin and capitalized or \
                                    not sentence_begin and shift)

            ignore_non_caps  = not sentence_begin and \
                               (capitalized or empty_prefix and shift)

            capitalize       = sentence_begin and (capitalized or shift)

            drop_capitalized = not sentence_begin and \
                               not capitalized \
                               and not empty_prefix
        else:
            capitalize = False
            case_insensitive = False
            ignore_non_caps  = False
            drop_capitalized = False

        return case_insensitive, ignore_non_caps, capitalize, drop_capitalized

    def get_word_infos(self, text):
        wis = []
        if text.rstrip():  # don't load models on startup
            tokens, counts = self._wpengine.lookup_text(text)
            for i,t in enumerate(tokens):
                start, end, token = t
                word = text[start:end]
                wi = WordInfo(start, end, word)
                wi.exact_match   = any(count == 1 for count in counts[i])
                wi.partial_match = any(count  < 0 for count in counts[i])
                wi.ignored       = word != token
                if self._spell_checker:
                    wi.spelling_errors = \
                            self._spell_checker.find_incorrect_spans(word)
                wis.append(wi)

        return wis

    @staticmethod
    def _capitalize_choices(choices):
        """
        Set first letters to upper case and remove
        double entries created that way.

        Doctests:
        >>> WordSuggestions._capitalize_choices(["word1", "Word1", "Word2", "word3"])
        ['Word1', 'Word2', 'Word3']
        """
        results = []
        seen = set()

        for choice in choices:
            if choice:
                choice = choice.capitalize()
                if not choice in seen:
                    results.append(choice)
                    seen.add(choice)
        return results

    def _get_prediction_choice_remainder(self, choice_index):
        """ returns the rest of matches[index] that hasn't been typed yet """
        deletion = ""
        insertion = ""
        if self._wpengine:
            text = self.text_context.get_context()
            word_prefix = self._wpengine.get_last_context_token(text)
            choice = self._prediction_choices[choice_index]
            remainder = choice[len(word_prefix):]

            # no case change?
            if word_prefix + remainder == choice:
                insertion = remainder
            else:
                deletion = word_prefix
                insertion = choice

        return deletion, insertion

    def _get_word_to_spell_check(self):
        """
        Get the word to be spell checked.

        Doctests:
        >>> wp = WordSuggestions()
        >>> wp._wpengine = WPLocalEngine()
        >>> tc = wp.text_context

        # cursor at word end - suppress spelling suggestions while still typing
        >>> tc._span_at_cursor = TextSpan(8, 0, "binomial proportion")
        >>> wp.is_typing = lambda : True  # simulate typing
        >>> print(wp._get_word_to_spell_check())
        None
        """
        cursor_span  = self.text_context.get_span_at_cursor()
        word_span = self._get_word_before_span(cursor_span)

        # Don't pop up spelling corrections if we're
        # currently typing the word.
        cursor = self.text_context.get_cursor()
        if word_span and \
           word_span.end() == cursor and \
           self.is_typing():
            word_span = None

        return word_span

    def _get_word_before_span(self, span):
        """
        Get the word at or before the span.

        Doctests:
        >>> wp = WordSuggestions()
        >>> wp._wpengine = WPLocalEngine()
        >>> tc = wp.text_context

        # cursor right in the middle of a word
        >>> wp._get_word_before_span(TextSpan(15, 0, "binomial proportion"))
        TextSpan(9, 10, 'proportion', 9, None)

        # text at offset
        >>> wp._get_word_before_span(TextSpan(25, 0, "binomial proportion", 10))
        TextSpan(19, 10, 'proportion', 19, None)

        # cursor after whitespace - get the previous word
        >>> wp._get_word_before_span(TextSpan(9, 0, "binomial  proportion"))
        TextSpan(0, 8, 'binomial', 0, None)
        """
        word_span = None
        if span and self._wpengine:
            tokens, spans = self._wpengine.tokenize_text(span.get_text())

            cursor = span.begin()
            text_begin = span.text_begin()
            local_cursor = span.begin() - text_begin

            itoken = None
            for i, s in enumerate(spans):
                if s[0] > local_cursor:
                    break
                itoken = i

            if not itoken is None:
                token = unicode_str(tokens[itoken])

                # We're only looking for actual words
                if not token in ["<unk>", "<num>", "<s>"]:
                    b = spans[itoken][0] + text_begin
                    e = spans[itoken][1] + text_begin
                    word_span = TextSpan(b, e-b, token, b)

        return word_span

    def _replace_text(self, begin, end, cursor, new_text):
        """
        Replace text from <begin> to <end> with <new_text>,
        """
        if self.text_context.can_insert_text():
            self._replace_text_direct(begin, end, cursor, new_text)
        else:
            self._replace_text_key_strokes(begin, end, cursor, new_text)

    def _replace_text_direct(self, begin, end, cursor, new_text):
        """
        Replace text from <begin> to <end> with <new_text>,
        """
        self.text_context.delete_text(begin, end - begin)
        self.text_context.insert_text(begin, new_text)

    def _replace_text_key_strokes(self, begin, end, cursor, new_text):
        """
        Replace text from <begin> to <end> with <new_text>,
        """
        with self.suppress_modifiers():
            length = end - begin
            offset = cursor - end  # offset of cursor to word end

            # delete the old word
            if offset >= 0:
                self.press_keysym("left", offset)
                self.press_keysym("backspace", length)
            else:
                self.press_keysym("delete", abs(offset))
                self.press_keysym("backspace", length - abs(offset))

            # insert the new word
            self._key_synth.press_key_string(new_text)

            # move cursor back
            if offset >= 0:
                self.press_keysym("right", offset)

    def _replace_text_at_cursor(self, deletion, insertion, auto_separator = ""):
        """
        Insert a word (-remainder) and add a separator character as needed.
        """
        added_separator = ""
        cursor_span = self.text_context.get_span_at_cursor()
        if auto_separator:
            next_char = cursor_span.get_text(cursor_span.end(),
                                             cursor_span.end() + 1)
            remaining_line = self.text_context.get_line_past_cursor()

            # insert space if the cursor was on a non-space character or
            # the cursor was at the end of the line. The end of the line
            # in the terminal (e.g. in vim) may mean lot's of spaces until
            # the final new line.
            if next_char != auto_separator or \
               remaining_line.isspace():
                added_separator = auto_separator

        with self.suppress_modifiers():
            if insertion:
                self._replace_text(cursor_span.begin() - len(deletion),
                                   cursor_span.begin(),
                                   cursor_span.begin(),
                                   insertion)
            if auto_separator:
                if added_separator:
                    self.press_key_string(auto_separator)
                else:
                    self.press_keysym("right") # just skip over the existing space

        return added_separator

    def press_keysym(self, key_name, count = 1):
        keysym = get_keysym_from_name(key_name)
        for i in range(count):
            self._key_synth.press_keysym  (keysym)
            self._key_synth.release_keysym(keysym)

    def on_text_entry_deactivated(self):
        """ The current accessible lost focus. """
        self.commit_changes()

    def on_text_entry_activated(self):
        """ A different target widget has been focused """
        self._learn_strategy.on_text_entry_activated()

    def on_text_inserted(self, insertion_span, cursor_offset):
        """ Synchronous callback for text insertion """

        # auto-correction
        if config.is_auto_capitalization_enabled() and \
           self.can_auto_correct():
            word_span = self._get_word_to_auto_correct(insertion_span)
            if word_span:
                self._auto_correct_at(word_span, cursor_offset)

    def on_text_context_changed(self):
        """
        Asynchronous callback for generic context changes.
        The text of the target widget changed or the cursor moved.
        Use this for low priority display stuff.
        """
        self.expand_corrections(False)
        self.invalidate_context_ui()
        self.commit_ui_updates()
        self._learn_strategy.on_text_context_changed()

    def has_changes(self):
        """ Are there any changes to learn? """
        return self.text_context and \
               self.text_context.has_changes()

    def commit_changes(self):
        """ Learn all accumulated changes and clear them """
        if self.has_changes():
            self._learn_strategy.commit_changes()
        self._clear_changes()  # clear input line too

    def discard_changes(self):
        """
        Discard all changes that have accumulated for learning.
        """
        _logger.info("discarding changes")
        self._learn_strategy.discard_changes()
        self._clear_changes()

    def _clear_changes(self):
        """
        Reset all contexts and clear all changes.
        """
        self.atspi_text_context.clear_changes()
        self.atspi_text_context.reset()
        self.input_line.reset()

        # Clear the spell checker cache, new words may have
        # been added from somewhere.
        if self._spell_checker:
            self._spell_checker.invalidate_query_cache()

    def update_inputline(self):
        """ Refresh the GUI displaying the current line's content """
        keys_to_redraw = []
        layout = self.layout  # may be None on exit
        if layout and self._wpengine:
            for key in self.get_text_displays():
                if not config.word_suggestions.show_context_line or \
                   self._hide_input_line:
                    if key.visible:
                        layout.set_item_visible(key, False)
                        keys_to_redraw.append(key)
                else:
                    line = self.text_context.get_line()
                    if line:
                        key.raise_to_top()
                        layout.set_item_visible(key, True)
                    else:
                        line = ""
                        layout.set_item_visible(key, False)

                    key.set_content(line, self.word_infos,
                                    self.text_context.get_line_cursor_pos())
                    keys_to_redraw.append(key)

        return keys_to_redraw

    def hide_input_line(self, hide = True):
        """
        Temporarily hide the input line to access keys below it.
        """
        if self._hide_input_line != hide:
            self._hide_input_line = hide
            self.redraw(self.update_inputline())

    def show_input_line_on_key_release(self, key):
        if self._hide_input_line and \
           not self._key_intersects_input_line(key):
            self._hide_input_line = False

    def _key_intersects_input_line(self, key):
        """ Check if key rect is intersecting the input line. """
        for item in self.get_text_displays():
            if item.get_border_rect().intersects(key.get_border_rect()):
                return True
        return False

    def can_give_keypress_feedback(self):
        """ Password entries may block feedback to prevent eavesdropping. """
        domain = self.text_context.get_text_domain()
        if domain and not domain.can_give_keypress_feedback():
            return False
        return True

    def can_spell_check(self):
        """ No spell checking for passwords, URLs, etc. """
        domain = self.text_context.get_text_domain()
        if domain and domain.can_spell_check():
            return True
        return False

    def can_auto_correct(self):
        """ No spell checking for passwords, URLs, etc. """
        domain = self.text_context.get_text_domain()
        if domain and domain.can_auto_correct():
            return True
        return False

    def on_focusable_gui_opening(self):
        """
        Turn off AT-SPI listeners while there is a dialog open.
        Onboard and occationally the whole desktop tend to lock up otherwise.
        Call this before dialog/popop menus are opened by Onboard itself.
        """
        if self._focusable_count == 0:
            AtspiStateTracker().freeze()
        self._focusable_count += 1

    def on_focusable_gui_closed(self):
        """
        Call this after dialogs/menus have been closed.
        """
        self._focusable_count -= 1
        if self._focusable_count == 0:
            # Re-enable AT-SPI listeners
            AtspiStateTracker().thaw()

    def _auto_correct_at(self, word_span, cursor_offset):
        """
        Auto-capitalize/correct a word_span.
        """
        correction_span, replacement = \
           self._find_auto_correction(word_span,
                                      True,
                                      config.typing_assistance.auto_correction)
        if replacement:
            with self.suppress_modifiers():
                self._replace_text(correction_span.begin(),
                                   correction_span.end(),
                                   cursor_offset,
                                   replacement)

    def _find_auto_correction(self, word_span, auto_capitalize, auto_correct):
        """
        Doctests:
        >>> wp = WordSuggestions()
        >>> wp._spell_checker.set_backend(0)
        >>> wp._spell_checker.set_dict_ids(["en_US"])
        True

        # auto-capitalization
        >>> wp._find_auto_correction(TextSpan(0, 7, "jupiter ..."), True, False)
        (TextSpan(0, 7, 'jupiter', 0, None), 'Jupiter')
        >>> wp._find_auto_correction(TextSpan(0, 3, "usa ..."), True, False)
        (TextSpan(0, 3, 'usa', 0, None), 'USA')
        >>> wp._find_auto_correction(TextSpan(2, 3, "  Usa ..."), True, False)
        (TextSpan(0, 3, 'Usa', 0, None), 'USA')
        """

        (correction_choices,
         correction_span,
         auto_capitalization) = \
              self._find_correction_choices(word_span, auto_capitalize)

        replacement = auto_capitalization
        if not replacement and \
           correction_choices and \
           auto_correct:

            MIN_AUTO_CORRECT_LENGTH = 2
            MAX_STRING_DISTANCE = 2

            word = word_span.get_span_text()
            if len(word) > MIN_AUTO_CORRECT_LENGTH:
                choice = correction_choices[0] # rely on spell checker for now
                distance = self._string_distance(word, choice)
                if distance <= MAX_STRING_DISTANCE:
                    replacement = choice

        return correction_span, replacement

    def _get_word_to_auto_correct(self, insertion_span):
        # find position of last word end with added space
        char_before = insertion_span.get_char_before_span()
        text = char_before + insertion_span.get_span_text()
        match = re.search("\S\s+\S*$", text)
        if match:
            span = insertion_span.copy()
            span.length = 0
            span.pos = insertion_span.begin() + match.start() + 1
            if char_before:
                span.pos -= 1
            return self._get_word_before_span(span)
        return None

    @staticmethod
    def _string_distance(s1, s2):
        """ Levenshtein string distance """
        len1 = len(s1)
        len2 = len(s2)
        last_row = None
        row = list(range(1, len2 + 1)) + [0]
        for ri in range(len1):
            last_row = row
            row = [0] * len2 + [ri + 1]
            for ci in range(len2):
                d = int(s1[ri] != s2[ci])
                row[ci] = min(row[ci - 1] + 1,
                              last_row[ci] + 1,
                              last_row[ci - 1] + d)
        return row[len2 - 1]


class LearnStrategy:
    """
    Base class of learn strategies.
    """

    def __init__(self, tokenize = None):
        self._tokenize = tokenize if tokenize \
                         else pypredict.tokenize_text  # no D-Bus for tests

    def _learn_spans(self, spans, bot_marker = "", bot_offset = None):
        if config.wp.can_auto_learn():
            texts = self._get_learn_texts(spans, bot_marker, bot_offset)

            #_logger.info("learning " + repr(texts))

            engine = self._wp._wpengine
            for text in texts:
                engine.learn_text(text, True)

    def _learn_scratch_spans(self, spans):
        if config.wp.can_auto_learn():
            engine = self._wp._wpengine
            engine.clear_scratch_models()
            if spans:
                texts = self._get_learn_texts(spans)

                for text in texts:
                    engine.learn_scratch_text(text)

    def _get_learn_texts(self, spans, bot_marker = "", bot_offset = None):
        token_sets = self._get_learn_tokens(spans, bot_marker, bot_offset)
        return [" ".join(tokens) for tokens in token_sets]

    def _get_learn_tokens(self, text_spans,
                          bot_marker = "", bot_offset = None):
        """
        Get disjoint sets of tokens to learn.
        Tokens of overlapping or adjacent spans are joined.
        Expected overlap is at most one word at begin and end.

        Doctests:
        >>> p = LearnStrategy()

        # single span
        >>> p._get_learn_tokens([TextSpan(14, 2, "word1 word2 word3")])
        [['word3']]

        # multiple distinct spans
        >>> p._get_learn_tokens([TextSpan( 3, 1, "word1 word2 word3"),
        ...                      TextSpan(14, 2, "word1 word2 word3")])
        [['word1'], ['word3']]

        # multiple joined spans
        >>> p._get_learn_tokens([TextSpan( 3, 4, "word1 word2 word3"),
        ...                      TextSpan(10, 1, "word1 word2 word3"),
        ...                      TextSpan(14, 2, "word1 word2 word3")])
        [['word1', 'word2', 'word3']]

        # single span with preceding sentence begin
        >>> p._get_learn_tokens([TextSpan(9, 2, "word1. word2 word3")])
        [['<s>', 'word2']]

        # Multiple joined spans across sentence marker.
        >>> p._get_learn_tokens([TextSpan(2, 2, "word1. word2 word3"),
        ...                      TextSpan(9, 2, "word1. word2 word3")])
        [['word1', '<s>', 'word2']]

        # Begin of text marker, generic text.
        >>> p._get_learn_tokens([TextSpan(2, 2, "word1 word2")], "<bot:txt>", 0)
        [['<bot:txt>', 'word1']]
        >>> p._get_learn_tokens([TextSpan(8, 2, "word1 word2")], "<bot:txt>", 0)
        [['word2']]

        # Begin of text marker, terminal.
        >>> p._get_learn_tokens([TextSpan(9, 2, "prompt$ word1 word2")],
        ...                               "<bot:term>", 8)
        [['<bot:term>', 'word1']]
        >>> p._get_learn_tokens([TextSpan(11, 2, "prompt$   word1 word2")],
        ...                               "<bot:term>", 8)
        [['<bot:term>', 'word1']]
        >>> p._get_learn_tokens([TextSpan(13, 2, "prompt$ 123 word1 word2")],
        ...                               "<bot:term>", 8)
        [['word1']]
        >>> p._get_learn_tokens([TextSpan(15, 2, "prompt$ word1 word2")],
        ...                               "<bot:term>", 8)
        [['word2']]
        """
        text_spans = sorted(text_spans, key=lambda x: (x.begin(), x.end()))
        token_sets = []
        span_sets = []

        for text_span in text_spans:
            # Tokenize with one additional token in front so we can
            # spot and join adjacent token sets.
            tokens, spans, span_before = self._tokenize_span(text_span)

            merged = False
            if tokens:
                # Do previous tokens to merge with exist?
                if token_sets:
                    prev_tokens = token_sets[-1]
                    prev_spans  = span_sets[-1]
                    link_span = span_before if span_before else spans[0]
                    for i, prev_span in enumerate(prev_spans):
                        if prev_span == link_span:
                            k = i + 1 if span_before else i
                            token_sets[-1] = prev_tokens[:k] + tokens
                            span_sets[-1]  = prev_spans [:k] + spans
                            merged = True

                # No previous tokens exist, the current ones are the
                # very first tokens at lowest offset.
                else:
                    # prepend begin-of-text marker
                    if bot_marker and \
                       not bot_offset is None:
                        if span_before is None or \
                           span_before[1] < bot_offset <= spans[0][0]:
                            tokens = [bot_marker] + tokens
                            spans = [(-1, -1)] + spans # dummy span, don't use

            if not merged and \
               len(tokens):
                token_sets.append(tokens)
                span_sets.append(spans)

        return token_sets

    def _tokenize_span(self, text_span, prepend_tokens = 0):
        """
        Extend spans text to word boundaries and return as tokens.
        Include <prepend_tokens> before the span.

        Doctests:
        >>> import Onboard.TextContext as tc
        >>> p = LearnStrategy()
        >>> p._tokenize_span(tc.TextSpan(0, 1, "word1 word2 word3"))
        (['word1'], [(0, 5)], None)
        >>> p._tokenize_span(tc.TextSpan(16, 1, "word1 word2 word3"))
        (['word3'], [(12, 17)], (6, 11))
        >>> p._tokenize_span(tc.TextSpan(8, 12, "word1 word2 word3"))
        (['word2', 'word3'], [(6, 11), (12, 17)], (0, 5))
        >>> p._tokenize_span(tc.TextSpan(5, 1, "word1 word2 word3"))
        ([], [], None)
        >>> p._tokenize_span(tc.TextSpan(4, 1, "word1 word2 word3"))
        (['word1'], [(0, 5)], None)
        >>> p._tokenize_span(tc.TextSpan(6, 1, "word1 word2 word3"))
        (['word2'], [(6, 11)], (0, 5))

        - text at offset
        >>> p._tokenize_span(tc.TextSpan(108, 1, "word1 word2 word3", 100))
        (['word2'], [(106, 111)], (100, 105))

        - prepend tokens
        >>> p._tokenize_span(tc.TextSpan(13, 1, "word1 word2 word3"), 1)
        (['word2', 'word3'], [(6, 11), (12, 17)], (0, 5))
        >>> p._tokenize_span(tc.TextSpan(1, 1, "word1 word2 word3"), 1)
        (['word1'], [(0, 5)], None)
        """
        tokens, spans = self._tokenize(text_span.get_text())

        itokens = []
        offset = text_span.text_begin()
        begin  = text_span.begin() - offset
        end    = text_span.end() - offset
        for i, s in enumerate(spans):
            if begin < s[1] and end > s[0]: # intersects?
                itokens.append(i)

        if prepend_tokens and itokens:
            first = itokens[0]
            n = min(prepend_tokens, first)
            itokens = list(range(first - n, first)) + itokens
        elif itokens:
            # Always include a preceding sentence marker to link
            # upper case words with it when learning.
            first = itokens[0]
            if first > 0 and \
               tokens[first - 1] == "<s>":
                itokens.insert(0, first - 1)

        # Return an additional span for linking with other token lists:
        # span of the token before the first returned token.
        span_before = None
        if itokens and itokens[0] > 0:
            k = itokens[0] - 1
            span_before = (offset + spans[k][0], offset + spans[k][1])

        return([unicode_str(tokens[i]) for i in itokens],
               [(offset + spans[i][0], offset + spans[i][1]) for i in itokens],
               span_before)


class LearnStrategyLRU(LearnStrategy):
    """
    Delay learning individual spans of changed text to reduce the
    rate of junk entering the language model.
    """

    LEARN_DELAY  = 60  # seconds from last modification until spans are learned
    POLLING_TIME =  2  # seconds between polling for timed-out spans

    def __init__(self, wp):
        LearnStrategy.__init__(self,
                               lambda text: wp._wpengine.tokenize_text(text))
        self._wp = wp
        self._timer = Timer()

        self._insert_count = 0
        self._delete_count = 0
        self._rate_limiter = CallOnce(500)

    def reset(self):
        self._timer.stop()
        self._rate_limiter.stop()

        self._insert_count = 0
        self._delete_count = 0

    def commit_changes(self):
        """ Learn and remove all changes """
        self.reset()

        text_context = self._wp.text_context
        changes = text_context.get_changes()
        spans = changes.get_spans() # by reference
        if spans:
            engine = self._wp._wpengine
            if engine:
                bot_marker = text_context.get_text_begin_marker()
                bot_offset = text_context.get_begin_of_text_offset()
                self._learn_spans(spans, bot_marker, bot_offset)
                engine.clear_scratch_models() # clear short term memory

        changes.clear()

    def discard_changes(self):
        """ Learn and remove all changes """
        self.reset()

    def commit_expired_changes(self):
        """
        Learn and remove spans that have reached their timeout.
        Keep the most recent span untouched,so it can be
        worked on indefinitely.
        """
        changes = self._wp.text_context.get_changes()
        spans = changes.get_spans()

        # find most recently update span
        most_recent = None
        for span in spans:
            if not most_recent or \
               most_recent.last_modified < span.last_modified:
                most_recent = span

        # learn expired spans
        expired_spans = []
        for span in list(spans):
            if not span is most_recent and \
               time.time() - span.last_modified >= self.LEARN_DELAY:
                expired_spans.append(span)
                changes.remove_span(span)
        self._learn_spans(expired_spans)

        return changes.get_spans()

    def on_text_entry_activated(self):
        pass

    def on_text_context_changed(self):
        changes = self._wp.text_context.get_changes()

        if not changes.is_empty():
            self._handle_timed_learning()
        self._maybe_update_scratch_models()

    def _handle_timed_learning(self):
        changes = self._wp.text_context.get_changes()
        if not changes.is_empty() and \
           not self._timer.is_running():
            # begin polling for text changes to learn every x seconds
            if 0:  # disabled for now
                self._timer.start(self.POLLING_TIME, self._poll_changes)

    def _poll_changes(self):
        remaining_spans = self.commit_expired_changes()
        return len(remaining_spans) != 0

    def _maybe_update_scratch_models(self):
        """
        Update short term memory if the time is right.
        This may be time consuming, so we try to limit the
        frequency of updates.
        """
        if self._wp._wpengine:
            text_context = self._wp.text_context
            changes = text_context.get_changes()

            # Whitespace inserted or delete to whitespace?
            inserted = self._insert_count < changes.insert_count
            deleted = self._delete_count < changes.delete_count
            if inserted or deleted:
                # cursor inside a word?
                cursor_span = text_context.get_span_at_cursor()
                if cursor_span:
                    char = cursor_span.get_char_before_span()
                    in_word = char.isalnum() or char in ["-"]
                else:
                    in_word = False

                if not in_word:
                    # run now, or guaranteed very soon, but not too often
                    self._rate_limiter.enqueue(self._update_scratch_memory,
                                               deleted)

    def _update_scratch_memory(self, update_ui):
        """
        Update short term memory of changes that haven't been learned yet.
        """
        changes = self._wp.text_context.get_changes()
        spans = changes.get_spans() # by reference
        self._learn_scratch_spans(spans)
        self._insert_count = changes.insert_count
        self._delete_count = changes.delete_count

        # reflect the model change in the wordlist, e.g. when deleting new words
        if update_ui:
            self._wp.invalidate_context_ui()
            self._wp.commit_ui_updates()


class Punctuator:
    """
    Punctiation assistance. Mainly adds and removes spaces around
    punctuation depending on the user action immediately after word completion.
    """
    def __init__(self, wp):
        self._wp = wp
        self.reset()

    def reset(self):
        self._added_separator = False
        self._separator_removed = False
        self._capitalize = False

    def set_added_separator(self, separator = ""):
        self._added_separator = separator;

    def on_before_press(self, key):
        if config.wp.punctuation_assistance and \
           self._added_separator and \
           (key.type == KeyCommon.KEYCODE_TYPE or \
            key.type == KeyCommon.KEYSYM_TYPE or \
            key.type == KeyCommon.CHAR_TYPE):
            self._added_separator = False

            char = key.get_label()
            if   char in [",", ":", ";", ")", "}", "]",
                          "’",
                          "”", "»", '›', # language dependent :/
                         ]:
                self.delete_at_cursor()
                self._separator_removed = True

            elif char in [".", "?", "!"]:
                self.delete_at_cursor()
                self._separator_removed = True
                if config.is_auto_capitalization_enabled():
                    self._capitalize = True

    def on_after_release(self, key):
        """
        Type the last part of the punctuation and possibly
        enable capitalization for the next key press
        """
        if config.wp.punctuation_assistance:
            if self._separator_removed:
                self._separator_removed = False
                # No direct insertion here. Space must always arrive last,
                # i.e. after the released key was generated.
                self._wp.press_keysym("space")

            if self._capitalize:
                self._capitalize = False
                self._wp.enter_caps_mode()

    def delete_at_cursor(self):
        text_context = self._wp.text_context
        if text_context.can_insert_text():
            text_context.delete_text_before_cursor()
        else:
            with self._wp.suppress_modifiers():
                self._wp.press_keysym("backspace")

class WordInfo:
    """ Word level information about found matches """

    exact_match = False
    partial_match = False
    ignored = False
    spelling_errors = None

    def __init__(self, start, end, word):
        self.start = start
        self.end   = end
        self.word  = word
        self.spelling_errors = None

    def __str__(self):
        return  "'{}' {}-{} unknown={} exact={} partial={} ignored={} " \
                "spelling_errors={}".format(self.word,
                                            self.start, self.end,
                                            self.unknown, self.exact_match,
                                            self.partial_match, self.ignored,
                                            self.spelling_errors)


from gi.repository        import Gdk, Pango
from Onboard.KeyGtk       import RectKey, FullSizeKey, BarKey, WordKey
from Onboard.utils        import Rect
from Onboard.Layout       import LayoutBox

class WordListPanel(LayoutPanel):
    """ Panel populated with correction and prediction keys at run-time """

    # Place all dynamically created suggestions into their own
    # group to prevent font_size changes forced by unrelated keys.
    SUGGESTIONS_GROUP = "_suggestion_"

    def __init__(self):
        LayoutPanel.__init__(self)
        self._correcions_expanded = False

    def get_max_non_expanded_corrections(self):
        return 1

    def expand_corrections(self, expand):
        self._correcions_expanded = expand

    def are_corrections_expanded(self):
        return self._correcions_expanded

    def _get_button_width(self, button):
        return button.get_initial_border_rect().w * \
               config.theme_settings.key_size / 100.0

    def create_keys(self, correction_choices, prediction_choices):
        """
        Dynamically create a variable number of buttons
        for word correction and prediction.
        """
        spacing = config.WORDLIST_BUTTON_SPACING[0]
        wordlist = self._get_child_button("wordlist")
        fixed_background = list(self.find_ids(["wordlist",
                                               "prediction",
                                               "correction"]))
        fixed_buttons    = list(self.find_ids(["expand-corrections",
                                               "language",
                                               "hide"]))
        if not wordlist:
            return []

        key_context = wordlist.context
        wordlist_rect = wordlist.get_rect()
        rect = wordlist_rect.copy()

        buttons = []
        button = self._get_child_button("hide")
        if button and button.visible:
            button_width = self._get_button_width(button)
            rect.w -= button_width
            buttons.append((button, button_width, 1))

        if 1:
            button = self._get_child_button("language")
            if button and button.visible:
                button_width = self._get_button_width(button)
                rect.w -= button_width
                #rect.x += button_width
                buttons.append((button, button_width, 1))

        # font size is based on the height of the word list background
        font_size = WordKey().calc_font_size(key_context, rect.get_size())

        # hide the wordlist background when corrections create their own
        wordlist.set_visible(not correction_choices)

        # create correction keys
        keys, used_rect = self._create_correction_keys( \
                                        correction_choices,
                                        rect, wordlist,
                                        key_context, font_size)
        rect.x += spacing + used_rect.w
        rect.w -= spacing + used_rect.w

        # create prediction keys
        if not self.are_corrections_expanded():
            keys += self._create_prediction_keys(prediction_choices, rect,
                                                 key_context, font_size)

        # move the buttons to the end of the bar
        if buttons:
            rw = wordlist_rect.copy()
            for button, button_width, align in buttons:
                r = rw.copy()
                r.w = button_width
                if align == -1:
                    r.x = rw.left() - button_width
                    rw.x += button_width
                    rw.w -= button_width
                elif align == 1:
                    r.x = rw.right() - button_width
                    rw.w -= button_width
                button.set_border_rect(r)

        # finally add all keys to the panel
        color_scheme = fixed_buttons[0].color_scheme
        for key in keys:
            key.color_scheme = color_scheme
        self.set_items(fixed_background + keys + fixed_buttons)

        return keys

    def _create_correction_keys(self, correction_choices, rect, wordlist,
                                    key_context, font_size):
        """
        Create all correction keys.
        """

        choices_rect = rect.copy()
        wordlist_rect = wordlist.get_rect()
        section_spacing = 1
        if not self.are_corrections_expanded():
            section_spacing += wordlist.get_fullsize_rect().w - wordlist_rect.w
            section_spacing = max(section_spacing, wordlist_rect.h * 0.1)

        # get button to expand/close the corrections
        show_button = len(correction_choices) > 1
        button_width = 0
        button = self._get_child_button("expand-corrections")
        if button and show_button:
            button_width = self._get_button_width(button)
            choices_rect.w -= button_width + section_spacing

        # get template key for tooltips
        template = self._get_child_button("correction")

        # partition choices
        n = self.get_max_non_expanded_corrections()
        choices = correction_choices[:n]
        expanded_choices = correction_choices[n:] \
                           if self.are_corrections_expanded() else []

        # create unexpanded correction keys
        keys, used_rect = self._create_correction_choices(choices, choices_rect,
                                           key_context, font_size, 0, template)
        exp_keys = []
        bg_keys = []
        if keys:
            if button:
                if show_button:
                    # Move the expand button to the end
                    # of the unexpanded corrections.
                    r = used_rect.copy()
                    r.x = used_rect.right()
                    r.w = button_width
                    button.set_border_rect(r)
                    button.set_visible(True)

                    used_rect.w += r.w
                else:
                    button.set_visible(False)

            # create background keys
            if self.are_corrections_expanded():
                x_split = wordlist_rect.right()
            else:
                x_split = used_rect.right()

            r = wordlist_rect.copy()
            r.w = x_split - r.x
            key = FullSizeKey("correctionsbg", r)
            key.sensitive = False
            bg_keys.append(key)

            r = wordlist_rect.copy()
            r.w = r.right() - x_split - section_spacing
            r.x = x_split + section_spacing
            key = FullSizeKey("predictionsbg", r)
            key.sensitive = False
            bg_keys.append(key)

            used_rect.w += section_spacing

            # create expanded correction keys
            if expanded_choices:
                exp_rect = choices_rect.copy()
                exp_rect.x += used_rect.w
                exp_rect.w -= used_rect.w
                exp_keys, exp_used_rect = self._create_correction_choices( \
                                         expanded_choices, exp_rect,
                                         key_context, font_size, len(choices))
                keys += exp_keys
                used_rect.w += exp_used_rect.w
        else:
            if button:
                button.set_visible(False)

        return bg_keys + keys + exp_keys, used_rect

    def _get_child_button(self, id):
        items = list(self.find_ids([id]))
        if items:
            return items[0]
        return None

    def _create_correction_choices(self, choices, rect,
                                   key_context, font_size,
                                   start_index = 0, template = None):
        """
        Dynamically create a variable number of buttons for word correction.
        """
        spacing = config.WORDLIST_BUTTON_SPACING[0]
        button_infos, filled_up, xend = self._fill_rect_with_choices(choices,
                                                rect, key_context, font_size)

        # create buttons
        keys = []
        x, y = 0.0, 0.0
        for i, bi in enumerate(button_infos):
            w = bi.w

            # create key
            r = Rect(rect.x + x, rect.y + y, w, rect.h)
            key = WordKey("", r)
            key.id = "correction" + str(i)
            key.group = self.SUGGESTIONS_GROUP
            key.labels = {0 : bi.label[:]}
            key.font_size = font_size
            key.type = KeyCommon.CORRECTION_TYPE
            key.code = start_index + i
            if template:
                key.tooltip = template.tooltip
            keys.append(key)

            x += w + spacing  # move to begin of next button

        # return the actually used rect for all correction keys
        if keys:
            x -= spacing
        used_rect = rect.copy()
        used_rect.w = x

        return keys, used_rect

    def _create_prediction_keys(self, choices, wordlist_rect,
                               key_context, font_size):
        """
        Dynamically create a variable number of buttons for word prediction.
        """
        keys = []
        spacing = config.WORDLIST_BUTTON_SPACING[0]

        button_infos, filled_up, xend = self._fill_rect_with_choices( \
                                choices, wordlist_rect, key_context, font_size)
        if button_infos:
            all_spacings = (len(button_infos)-1) * spacing

            if filled_up:
                # Find a stretch factor that fills the remaining space
                # with only expandable items.
                length_nonexpandables = sum(bi.w for bi in button_infos \
                                            if not bi.expand)
                length_expandables = sum(bi.w for bi in button_infos \
                                         if bi.expand)
                length_target = wordlist_rect.w - length_nonexpandables \
                                - all_spacings
                scale = length_target / length_expandables \
                             if length_expandables else 1.0
            else:
                # Find the stretch factor that fills the available
                # space with all items.
                scale = (wordlist_rect.w - all_spacings) / \
                              float(xend - all_spacings - spacing)
            #scale = 1.0  # no stretching, left aligned

            # create buttons
            x,y = 0.0, 0.0
            for i, bi in enumerate(button_infos):
                w = bi.w

                # scale either all buttons or only the expandable ones
                if not filled_up or bi.expand:
                    w *= scale

                # create the word key with the generic id "prediction<n>"
                key = WordKey("prediction" + str(i), Rect(wordlist_rect.x + x,
                                               wordlist_rect.y + y,
                                               w, wordlist_rect.h))
                key.group = self.SUGGESTIONS_GROUP
                key.labels = {0 : bi.label[:]}
                key.font_size = font_size
                key.type = KeyCommon.WORD_TYPE
                key.code = i
                keys.append(key)

                x += w + spacing  # move to begin of next button

        return keys

    def _fill_rect_with_choices(self, choices, rect, key_context, font_size):
        spacing = config.WORDLIST_BUTTON_SPACING[0]
        x, y = 0.0, 0.0

        context = Gdk.pango_context_get()
        pango_layout = WordKey.get_pango_layout(None, font_size)
        button_infos = []
        filled_up = False
        for i,choice in enumerate(choices):

            # text extent in Pango units -> button size in logical units
            pango_layout.set_text(choice, -1)
            label_width, _label_height = pango_layout.get_size()
            label_width = key_context.scale_canvas_to_log_x(
                                                label_width / Pango.SCALE)
            w = label_width + config.WORDLIST_LABEL_MARGIN[0] * 2

            expand = w >= rect.h
            if not expand:
                w = rect.h

            # reached the end of the available space?
            if x + w > rect.w:
                filled_up = True
                break

            class ButtonInfo: pass
            bi = ButtonInfo()
            bi.label_width = label_width
            bi.w = w
            bi.expand = expand  # can stretch into available space?
            bi.label = choice[:]

            button_infos.append(bi)

            x += w + spacing  # move to begin of next button

        if button_infos:
            x -= spacing

        return button_infos, filled_up, x



