# -*- coding: latin-1 -*-

from __future__ import division, print_function, unicode_literals

import time
import re
import unicodedata

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, "
                   "word prediction may not be fully functional"))

from Onboard.AtspiUtils   import AtspiStateTracker
from Onboard.utils        import CallOnce, unicode_str
from Onboard              import KeyCommon

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

### Logging ###
import logging
_logger = logging.getLogger("WordPrediction")
###############


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

    def get_changes(self):
        raise NotImplementedError()

    def clear_changes(self):
        raise NotImplementedError()


class TextSpan:
    """
    Span of text

    Doctests:
    >>> span = TextSpan(3, 2, "0123456789")
    >>> span.get_span_text()
    '34'
    >>> span.get_text_until_span()
    '01234'
    >>> span.get_text_from_span()
    '3456789'
    """

    def __init__(self, pos = 0, length = 0, text = "", text_pos = 0):
        self.pos = pos
        self.length = length
        self.text = text
        self.text_pos = text_pos
        self.last_modified = None

    def begin(self):
        return self.pos

    def end(self):
        return self.pos + self.length

    def is_empty(self):
        return self.length == 0

    def contains(self, pos):
        return self.pos <= pos < self.pos + self.length

    def intersects(self, span):
        return not self.intersection(span).is_empty()

    def intersection(self, span):
       p0 = max(self.pos, span.pos)
       p1 = min(self.pos + self.length,  span.pos + span.length)
       if p0 > p1:
           return TextSpan()
       else:
           return TextSpan(p0, p1 - p0)

    def union_inplace(self, span):
        """
        Join two spans, result in self.

        Doctests:
        - adjacent spans
        >>> a = TextSpan(2, 3, "0123456789")
        >>> b = TextSpan(5, 2, "0123456789")
        >>> a.union_inplace(b)                         # doctest: +ELLIPSIS
        TextSpan(2, 5, '23456', '0123456789', ...

        - intersecting spans
        >>> a = TextSpan(2, 3, "0123456789")
        >>> b = TextSpan(4, 2, "0123456789")
        >>> a.union_inplace(b)                         # doctest: +ELLIPSIS
        TextSpan(2, 4, '2345', '0123456789', ...
        """
        begin = min(self.begin(), span.begin())
        end   = max(self.end(),   span.end())
        length = end - begin
        middle = length // 2
        self.text   = self.text[:middle - self.text_pos] + \
                      span.text[middle - span.text_pos:]
        self.pos    = begin
        self.length = length
        self.last_modified = max(self.last_modified if self.last_modified else 0,
                                 span.last_modified if span.last_modified else 0)
        return self

    def get_text(self):
        """ Returns the whole available text """
        return self.text

    def get_span_text(self):
        """ Returns just the part of the that is covered by the span """
        return self.text[self.pos - self.text_pos:self.end() - self.text_pos]

    def get_text_until_span(self):
        """
        Returns the beginning of the whole available text,
        ending with and including the span.
        """
        return self.text[:self.end() - self.text_pos]

    def get_text_from_span(self):
        """
        Returns the end of the whole available text,
        starting from and including the span.
        """
        return self.text[self.pos - self.text_pos:]

    def __repr__(self):
        return "TextSpan({}, {}, '{}', '{}', {}" \
                .format(self.pos, self.length, self.get_span_text(),
                        re.escape(self.get_text()), self.last_modified)


class TextChanges:
    __doc__ = """
    Collection of text spans yet to be learned

    Example:
    >>> c = TextChanges()
    >>> c.insert(0, 1) # IGNORE_RESULT
    >>> c.get_span_ranges()
    [[0, 1]]

    Doctests:
    - insert and extend span
    >>> c = TextChanges()
    >>> c.insert(0, 1) # IGNORE_RESULT
    >>> c.get_span_ranges()
    [[0, 1]]
    >>> c.insert(0, 1) # IGNORE_RESULT
    >>> c.get_span_ranges()
    [[0, 2]]

    - extend at beginning and end
    >>> c = TextChanges()
    >>> c.insert(0, 1); c.insert(1, 1); c.insert(0, 3) # IGNORE_RESULT
    >>> c.get_span_ranges()
    [[0, 5]]

    - insert separated by at least one character -> multiple spans
    >>> c = TextChanges()
    >>> c.insert(1, 1); c.insert(0, 1) # IGNORE_RESULT
    >>> c.get_span_ranges()
    [[0, 1], [2, 1]]

    - add and delete in single span
    >>> c = TextChanges()
    >>> c.insert(0, 1); # IGNORE_RESULT
    >>> c.delete(0, 1); # IGNORE_RESULT
    >>> c.get_span_ranges()
    [[0, 0]]

    - join spans when deleting
    >>> c = TextChanges()
    >>> c.insert(0, 1); c.insert(2, 1) # IGNORE_RESULT
    >>> c.delete(2, 1);                # IGNORE_RESULT
    >>> c.delete(1, 1);                # IGNORE_RESULT
    >>> c.get_span_ranges()
    [[0, 1]]

    - remove spans fully contained in the deleted range
    >>> c = TextChanges()
    >>> c.insert(2, 1); c.insert(4, 1) # IGNORE_RESULT
    >>> c.delete(0, 5);                # IGNORE_RESULT
    >>> c.get_span_ranges()
    [[0, 0]]

    - partially delete span
    >>> tests = [ # span after deletion
    ...          [[2, 3], [0, 5], [[0, 0]] ],
    ...          [[3, 3], [0, 5], [[0, 1]] ],
    ...          [[4, 3], [0, 5], [[0, 2]] ],
    ...          [[5, 3], [0, 5], [[0, 3]] ],
    ...          [[6, 3], [0, 5], [[0, 0], [1, 3]] ]]
    ...            # span before deletion
    ...          [[0, 3], [4, 5], [[0, 3]] ],
    ...          [[1, 3], [4, 5], [[1, 3]] ],
    ...          [[2, 3], [4, 5], [[2, 2]] ],
    ...          [[3, 3], [4, 5], [[3, 1]] ],
    ...          [[4, 3], [4, 5], [[4, 0]] ]]
    >>> for test in tests:
    ...     c = TextChanges()
    ...     _ = c.insert(*test[0]); _ = c.delete(*test[1])
    ...     if c.get_span_ranges() != test[2]:
    ...        "test: " + repr(test) + " result: " + repr(c.get_span_ranges())

    """.replace('IGNORE_RESULT', 'doctest: +ELLIPSIS\n    T...')

    def __init__(self):
        self.clear()

    def is_empty(self):
        return len(self._spans) == 0

    def get_spans(self):
        return self._spans

    def remove_span(self, span):
        self._spans.remove(span)

    def clear(self):
        self._spans = []

    def insert(self, pos, length):
        """
        Record insertion.
        """
        end = pos + length

        # shift all existing spans after position
        for span in self._spans:
            if span.pos > pos:
                span.pos += length

        span = self.find_span_at(pos)
        if span:
            span.length += length
        else:
            span = TextSpan(pos, length);
            self._spans.append(span)
        span.last_modified = time.time()

        return span

    def delete(self, pos, length):
        """
        Record deletion.
        """
        begin = pos
        end   = pos + length

        for span in list(self._spans):
            if span.pos >= pos:          # span begins after deletion point?
                k = end - span.begin()   # intersecting length
                if k >= 0:
                    span.pos += k
                    span.length -= k
                span.pos -= length       # shift by deleted length

                # remove spans fully contained in the deleted range
                if span.length < 0:
                    self._spans.remove(span)
            else:                        # span begins before deletion point
                k = span.end() - begin   # intersecting length
                if k >= 0:
                    span.length -= k

        # apply to the affected text span
        span = self.find_span_excluding(pos)
        if not span:
            # Create empty span when deleting too, because this
            # is still a change that can result in a word to learn.
            span = TextSpan(pos, 0);
            self._spans.append(span)

        span = self.join_adjacent_spans(span)
        span.last_modified = time.time()

        return span

    def join_adjacent_spans(self, tracked_span = None):
        """
        join text spans that are touching each other

        Doctests:
        >>> c = TextChanges()
        >>> c._spans.append(TextSpan(0, 1))
        >>> c._spans.append(TextSpan(2, 4))
        >>> c._spans.append(TextSpan(1, 1))
        >>> c._spans.append(TextSpan(10, 3))
        >>> c._spans.append(TextSpan(8, 2))
        >>> c.join_adjacent_spans()
        >>> c.get_span_ranges()
        [[0, 6], [8, 5]]
        """
        spans = sorted(self._spans, key=lambda x: (x.begin(), x.end()))
        new_spans = []
        slast = None
        for s in spans:
            if slast and \
               slast.end() >= s.begin():
                slast.union_inplace(s)
                if tracked_span is s:
                    tracked_span = slast
            else:
                new_spans.append(s)
                slast = s

        self._spans = new_spans

        return tracked_span

    def find_span_at(self, pos):
        """
        Doctests:
        - find empty spans (text deleted):
        >>> c = TextChanges()
        >>> c.insert(0, 0)      # doctest: +ELLIPSIS
        TextSpan(...
        >>> c.find_span_at(0)   # doctest: +ELLIPSIS
        TextSpan(0, 0,...
        """
        for span in self._spans:
            if span.pos <= pos <= span.pos + span.length:
                return span
        return None

    def find_span_excluding(self, pos):
        """
        Doctests:
        - find empty spans (text deleted):
        >>> c = TextChanges()
        >>> c.insert(0, 0)             # doctest: +ELLIPSIS
        TextSpan(...
        >>> c.find_span_excluding(0)   # doctest: +ELLIPSIS
        TextSpan(0, 0,...

        - don't match the end
        >>> c = TextChanges()
        >>> c.insert(0, 1)      # doctest: +ELLIPSIS
        TextSpan(...
        >>> c.find_span_excluding(1)   # doctest: +ELLIPSIS

        """
        for span in self._spans:
            if span.pos == pos or \
               span.pos <= pos < span.pos + span.length:
                return span
        return None

    def get_span_ranges(self):
        return sorted([[span.pos, span.length] for span in self._spans])

    def __repr__(self):
        return "TextChanges " + repr([str(span) for span in self._spans])


class AtspiTextContext(TextContext):
    """
    Keep track of the current text context with AT-SPI
    """

    _wp = None
    _state_tracker = None
    _atspi_listeners_registered = False
    _accessible = None

    _context = ""
    _last_context = None
    _line = ""
    _last_line = None
    _line_cursor = 0


    def __init__(self, wp, state_tracker):
        self._wp = wp
        self._state_tracker = state_tracker
        self._call_once = CallOnce(100).enqueue  # delay callbacks
        self._changes = TextChanges()

    def cleanup(self):
        self._register_atspi_listeners(False)
        self.state_tracker = None

    def enable(self, enable):
        self._register_atspi_listeners(enable)

    def get_context(self):
        """
        Returns the predictions context, i.e. some range of
        text before the cursor position.
        """
        return self._context

    def get_line(self):
        return self._line

    def get_line_cursor_pos(self):
        return self._line_cursor

    def get_changes(self):
        return self._changes

    def clear_changes(self):
        self._changes.clear()

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

                # these don't seem to do anything...
                Atspi.EventListener.register_no_data(self._on_text_insert,
                                                    "object:text-insert")
                Atspi.EventListener.register_no_data(self._on_text_remove,
                                                    "object:text-remove")
                Atspi.EventListener.register_no_data(self._on_text_update,
                                                    "object:text-update")

                self._atspi_listeners_registered = True
        else:
            if self._atspi_listeners_registered:

                Atspi.EventListener.deregister_no_data(self._on_text_changed,
                                                    "object:text-changed")
                Atspi.EventListener.deregister_no_data(self._on_text_caret_moved,
                                                    "object:text-caret-moved")

                Atspi.EventListener.deregister_no_data(self._on_text_insert,
                                                    "object:text-insert")
                Atspi.EventListener.deregister_no_data(self._on_text_remove,
                                                    "object:text-remove")
                Atspi.EventListener.deregister_no_data(self._on_text_update,
                                                    "object:text-update")
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
            #print("_on_text_changed", event.detail1, event.detail2, event.source, event.type, event.type.endswith("delete"))
            pos    = event.detail1
            length = event.detail2
            insert = event.type.endswith("insert")
            delete = event.type.endswith("delete")

            self._update_context()

            if insert and length > 1:
                # We can't tell at this point if a large insertion
                # is a reult of user action or not. Terminal output
                # for example shouldn't be recorded as changes we
                # want to learn. -> Give up and learn what we have so far.
                self._wp.commit_changes()
            else:
                # record the change
                span = None
                if insert:
                    print("insert", pos, length)
                    span = self._changes.insert(pos, length)
                elif delete:
                    print("delete", pos, length)
                    span = self._changes.delete(pos, length)
                else:
                    _logger.error("_on_text_changed: unknown event type '{}'" \
                                  .format(event.type))

                # update text of the span
                if span:
                    # Get some more text around the span to hopefully
                    # include whole words at beginning and end.
                    begin = max(span.begin() - 100, 0)
                    end = span.end() + 100
                    span.text = Atspi.Text.get_text(self._accessible, begin, end)
                    span.text_pos = begin

                print(self._changes)

        return False

    def _on_text_insert(self, event):
        if event.source is self._accessible:
            print("_on_text_insert", event.detail1, event.detail2, event.detail3, event.source, event.type)
        return False

    def _on_text_remove(self, event):
        if event.source is self._accessible:
            print("_on_text_remove", event.detail1, event.detail2, event.detail3, event.source, event.type)
        return False

    def _on_text_update(self, event):
        if event.source is self._accessible:
            print("_on_text_update", event.detail1, event.detail2, event.detail3, event.detail4, event.source, event.type)
        return False

    def _on_text_caret_moved(self, event):
        if event.source is self._accessible:
        #    print("_on_text_caret_moved", event.detail1, event.detail2, event.source, event.type, event.source.get_name(), event.source.get_role())
            caret = event.detail1
            self._update_context()
        return False

    def _on_text_entry_activated(self, accessible, active):
        #print("_on_text_entry_activated", accessible, active)
        if accessible and active:
            self._accessible = accessible
        else:
            self._accessible = None

        self._wp.on_text_entry_activated()

        self._update_context()

    def _update_context(self):
        self._context, self._line, self._line_cursor = \
                                 self._read_context(self._accessible)
        self._call_once(self.on_text_context_changed)

    def on_text_context_changed(self):
        if self._last_context != self._context or \
           self._last_line != self._line:
            self._last_context = self._context
            self._lasr_line    = self._line

            #print(repr(self.get_context()))
            self._wp.on_text_context_changed()

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

