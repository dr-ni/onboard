# -*- coding: latin-1 -*-

from __future__ import division, print_function, unicode_literals

import sys
import os, errno
import time
import codecs
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
from Onboard.utils        import CallOnce, unicode_str, Timer
from Onboard.TextContext  import AtspiTextContext, InputLine

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

### Logging ###
import logging
_logger = logging.getLogger("WordPrediction")
###############


class WordPrediction:
    """ Keyboard mix-in for word prediction """

    def __init__(self):

        # prepare text contexts
        self.input_line = InputLine()
        self.atspi_text_context = AtspiTextContext(self, self.atspi_state_tracker)
        self.text_context = None
        self.learn_strategy = LearnStrategyLRU(self)

        self.punctuator = Punctuator()
        self.predictor  = None

        self.word_choices = []
        self.word_infos = []

        self._hide_input_line = False

    def cleanup(self):
        self.commit_changes()
        if self.text_context:
            self.text_context.cleanup()

    def on_layout_loaded(self):
        self.enable_word_prediction(config.wp.enabled)

    def send_press_key(self, key, button, event_type):
        if key.action_type == KeyCommon.WORD_ACTION:
            s  = self._get_match_remainder(key.action) # unicode
            if config.wp.auto_punctuation and \
               button != 3: # right click suppresses punctuation
                self.punctuator.set_end_of_word()
            if s:
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
        self.text_context = self.atspi_text_context
        self.text_context.enable(enable) # register AT-SPI listerners

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

    def _get_match_remainder(self, index):
        """ returns the rest of matches[index] that hasn't been typed yet """
        if not self.predictor:
            return ""
        text = self.text_context.get_context()
        word_prefix = self.predictor.get_last_context_token(text)
        #print self.word_choices[index], word_prefix
        return self.word_choices[index][len(word_prefix):]

    def on_text_entry_activated(self):
        """ A different target widget has been focused """
        self.commit_changes()
        self.learn_strategy.on_text_entry_activated()

    def on_text_context_changed(self):
        """ The text of the target widget changed or the cursor moved """
        self.find_word_choices()
        self.update_key_ui()
        self.learn_strategy.on_text_context_changed()

    def commit_changes(self):
        """ Learn all accumulated changes and clear them """
        self.learn_strategy.commit_changes()
        self.discard_changes() # clear inputline too
        return # outdated

        if self.text_context is self.input_line:
            if self.predictor and config.wp.can_auto_learn():
                self.predictor.learn_text(self.text_context.get_line(), True)

        self.reset_text_context()
        self.punctuator.reset()
        self.word_choices = []

    def discard_changes(self):
        """
        Reset all contexts and cancel whatever has accumulated for learning.
        """
        self.atspi_text_context.reset()
        self.input_line.reset()

    def learn_spans(self, spans):
        if self.predictor and config.wp.can_auto_learn():
            self.predictor.learn_spans(spans, True)

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
                if prefix:
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
                        line = ""
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


class LearnStrategyLRU:
    """
    Delay learning individual spans of changed text to reduce the
    rate of junk entering the language model.
    """

    LEARN_DELAY  = 60  # seconds from last modification until spans are learned
    POLLING_TIME =  2  # seconds between polling for timed-out spans

    def __init__(self, wp):
        self._wp = wp
        self._timer = Timer()

    def commit_changes(self):
        """ Learn and remove all changes """
        self._timer.stop()
        text_context = self._wp.text_context
        if text_context:
            changes = text_context.get_changes() # by reference
            spans = changes.get_spans() # by reference
            if spans:
                self._wp.learn_spans(spans)
                changes.clear()


    def commit_expired_changes(self):
        """
        Learn and remove expired changes.
        Keep the most recent span untouched,
        so it can be worked on indefinitely.
        """
        changes = self._wp.text_context.get_changes()
        spans = changes.get_spans()

        return changes.get_spans()

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
        self._wp.learn_spans(expired_spans)

        return changes.get_spans()

    def on_text_entry_activated(self):
        pass

    def on_text_context_changed(self):
        changes = self._wp.text_context.get_changes()
        #print("on_text_context_changed", changes.get_spans(), changes.is_empty(), self._timer.is_running())
        if not changes.is_empty() and \
           not self._timer.is_running():
            # begin polling for text changes to learn every x seconds
            self._timer.start(self.POLLING_TIME, self._poll_changes)

    def _poll_changes(self):
        remaining_spans = self.commit_expired_changes()
        return len(remaining_spans) != 0


class Punctuator:
    """
    Punctiation assistance. Mainly adds and removes spaces around
    punctuation depending on the user action immediately after word completion.
    """
    BACKSPACE  = "\b"
    CAPITALIZE = "\x0e"  # abuse U+000E SHIFT OUT to signal upper case

    def __init__(self):
        self.reset()

    def reset(self):
        self.end_of_word = False
        self.space_added = False
        self.prefix = ""
        self.suffix = ""

    def set_end_of_word(self, val=True):
        self.end_of_word = val;

    def build_prefix(self, char):
        """ return string to insert before sending keypress char """
        self.prefix = ""
        self.suffix = ""
        if self.space_added:  # did we previously add a trailing space?
            self.space_added = False

            if   char in ",:;":
                self.prefix = self.BACKSPACE
                self.suffix = " "

            elif char in ".?!":
                self.prefix = self.BACKSPACE
                self.suffix = " " + self.CAPITALIZE

        return self.prefix

    def build_suffix(self):
        """ add additional characters after the key press"""
        if self.end_of_word:
            self.space_added = True
            self.end_of_word = False
            return " "
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

    def learn_spans(self, spans, allow_new_words):
        token_sets = self._get_learn_tokens(spans)
        learn_texts = [" ".join(tokens) for tokens in token_sets]
        print("learning", learn_texts)

    def _get_learn_tokens(self, text_spans):
        """
        Get disjoint sets of tokens to learn.
        Tokens of overlapping adjacent spans are joined.
        Span tokens at this point ought to overlap not more than a single token.

        Doctests:
        >>> import Onboard.TextContext as tc
        >>> p = WordPredictor()
        >>> p._get_learn_tokens([tc.TextSpan(14, 2, "word1 word2 word3")])
        [['word3']]
        >>> p._get_learn_tokens([tc.TextSpan( 3, 1, "word1 word2 word3"),
        ...                      tc.TextSpan(14, 2, "word1 word2 word3")])
        [['word1'], ['word3']]
        >>> p._get_learn_tokens([tc.TextSpan( 3, 4, "word1 word2 word3"),
        ...                      tc.TextSpan(10, 1, "word1 word2 word3"),
        ...                      tc.TextSpan(14, 2, "word1 word2 word3")])
        [['word1', 'word2', 'word3']]
        """
        text_spans = sorted(text_spans, key=lambda x: (x.begin(), x.end()))
        token_sets = []
        span_sets = []

        for text_span in text_spans:
            # Tokenize with one additional token in front so we can
            # spot and join adjacent token sets.
            tokens, spans, span_before = self._tokenize_span(text_span)

            merged = False
            if token_sets and tokens:
                prev_tokens = token_sets[-1]
                prev_spans  = span_sets[-1]
                link_span = span_before if span_before else spans[0]
                for i, prev_span in enumerate(prev_spans):
                    if prev_span == link_span:
                        k = i + 1 if span_before else i
                        token_sets[-1] = prev_tokens[:k] + tokens
                        span_sets[-1]  = prev_spans [:k] + spans
                        merged = True

            if not merged:
                token_sets.append(tokens)
                span_sets.append(spans)

        return token_sets

    def _tokenize_span(self, text_span, prepend_tokens = 0):
        """
        Extend spans text to word boundaries and return as tokens.
        Include <prepend_tokens> before the span.

        Doctests:
        >>> import Onboard.TextContext as tc
        >>> p = WordPredictor()
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
        offset = text_span.text_begin()

        tokens, spans = self.tokenize_text(text_span.get_text())
        assert(len(tokens) == len(spans))

        itokens = []
        begin  = text_span.begin() - offset
        end    = text_span.end() - offset
        for i, s in enumerate(spans):
            if begin < s[1] and end > s[0]: # intersects?
                itokens.append(i)

        if prepend_tokens and itokens:
            first = itokens[0]
            n = min(prepend_tokens, first)
            itokens = list(range(first - n, first)) + itokens

        # Return an additional span for linking with other token sets:
        # span of the token before the first returned token.
        span_before = None
        if itokens and itokens[0] > 0:
            k = itokens[0] - 1
            span_before = (offset + spans[k][0], offset + spans[k][1])

        return([unicode_str(tokens[i]) for i in itokens],
               [(offset + spans[i][0], offset + spans[i][1]) for i in itokens],
               span_before)

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

    def tokenize_text(self, text):
        """ let the service find the words in text """
        for retry in range(2):
            with self.get_service() as service:
                if service:
                    tokens, spans = service.tokenize_text(text)
            break
        return tokens, spans

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

