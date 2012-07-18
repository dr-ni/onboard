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

import re

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, "
                   "word suggestions not fully functional"))

from Onboard.TextChanges  import TextSpan
from Onboard.utils        import unicode_str

import Onboard.osk as osk

### Logging ###
import logging
_logger = logging.getLogger("TextDomain")
###############


class TextDomains:
    """ Collection of all recognized text domains. """

    def __init__(self):
        # default domain has to be last
        self._domains = [DomainTerminal(),
                         DomainPassword(),
                         DomainGenericText(),
                         DomainNOP()]

    def find_match(self, **kwargs):
        for domain in self._domains:
            if domain.matches(**kwargs):
                return domain
        return None  # should never happen, default domain always matches

    def get_nop_domain(self):
        return self._domains[-1]


class TextDomain:
    """ Abstract base class as a catch-all for domain specific functionalty. """

    def matches(self, **kwargs):
        return NotImplementedError()

    def read_context(self, accessible):
        return NotImplementedError()


class DomainNOP(TextDomain):
    """ Do-nothing domain, no focused accessible. """

    def matches(self, **kwargs):
        return False

    def read_context(self, accessible):
        return "", "", 0, None


class DomainPassword(DomainNOP):
    """ Do-nothing domain for password entries """

    def matches(self, **kwargs):
        return kwargs["role"] == Atspi.Role.PASSWORD_TEXT


class DomainGenericText(TextDomain):
    """ Default domain for generic text entry """

    def matches(self, **kwargs):
        return True

    def read_context(self, accessible):
        """ Extract prediction context from the accessible """
        offset = accessible.get_caret_offset()
        r = accessible.get_text_at_offset(offset,
                            Atspi.TextBoundaryType.LINE_START)

        line = unicode_str(r.content).replace("\n","")
        line_cursor = max(offset - r.start_offset, 0)

        count = accessible.get_character_count()
        begin = max(offset - 256, 0)
        end   = min(offset + 100, count)
        text = Atspi.Text.get_text(accessible, begin, end)

        text = unicode_str(text)
        cursor_span = TextSpan(offset, 0, text, begin)
        context = text[:offset - begin]

        return context, line, line_cursor, cursor_span


class DomainTerminal(TextDomain):
    """ Terminal entry, in particular gnome-terminal """

    _prompt_patterns = tuple(re.compile(p) for p in \
                             ("^gdb$ ",
                              "^>>> ", # python
                              "^In \[[0-9]*\]: ",   # ipython
                              "^:",    # vi command mode
                              "^/",    # vi search
                              "^\?",   # vi reverse search
                              "\$ ",   # generic prompt
                              "# ",    # root prompt
                             )
                            )

    def matches(self, **kwargs):
        return kwargs["role"] == Atspi.Role.TERMINAL

    def read_context(self, accessible):
        """ Extract prediction context from the accessible """
        offset = accessible.get_caret_offset()

        r = accessible.get_text_at_offset(offset,
                            Atspi.TextBoundaryType.LINE_START)
        line = unicode_str(r.content).replace("\n","")
        line_start = r.start_offset
        line_cursor = offset - line_start

        # remove prompt from the current or previous lines
        context = ""
        l = line[:line_cursor]
        for i in range(2):
            entry_start = self._find_prompt(l)
            context = context + l[entry_start:]
            if i == 0:
                line = line[entry_start:] # cut prompt from input line
                line_start  += entry_start
                line_cursor -= entry_start
            if entry_start:
                break

            # no prompt yet -> let context reach
            # across one more line break
            r = accessible.get_text_before_offset(offset,
                                Atspi.TextBoundaryType.LINE_START)
            l = unicode_str(r.content)

        # remove newlines
        context = context.replace("\n","")

        #cursor_span = TextSpan(offset, 0, text, begin)
        cursor_span = TextSpan(offset, 0, line, line_start)

        return context, line, line_cursor, cursor_span

    def _find_prompt(self, context):
        """
        Search for a prompt and return the offset where the user input starts.
        Until we find a better way just look for some common prompt patterns.
        """
        for pattern in self._prompt_patterns:
            match = pattern.search(context)
            if match:
                return match.end()
        return 0


class TextClassifier(osk.TextClassifier):
    """ Wrapper class for language detection. """
    def __init__(self):
        self._pattern = re.compile("\[(.*?)--.*?\]")

        self._ok = self.init_exttextcat( \
                        '/usr/share/libexttextcat/fpdb.conf',
                        '/usr/share/libexttextcat/')
        if not self._ok:
            _logger.warning("Language classifier unavailable."
                            "check if libexttextcat is installed.")

    def detect_language(self, text):
        language = ""

        if len(text) >= 100: # Arbitrary limit above which the detection
                             # seems confident about a simgle language.
            languages = self.classify_language(text)
            if len(languages) == 1: # no second thoughts?
                language = languages[0]

        return language

    def classify_language(self, text):
        languages = []

        if self._ok:
            result = osk.TextClassifier.classify_language(self, text)
            languages = self._pattern.findall(result)

        return languages


