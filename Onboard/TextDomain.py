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
        self._domains = [
                         DomainTerminal(),
                         DomainURL(),
                         DomainPassword(),
                         DomainGenericText(),
                         DomainNOP()
                        ]

    def find_match(self, **kwargs):
        for domain in self._domains:
            if domain.matches(**kwargs):
                return domain
        return None  # should never happen, default domain always matches

    def get_nop_domain(self):
        return self._domains[-1]


class TextDomain:
    """ Abstract base class as a catch-all for domain specific functionalty. """

    def __init__(self):
        self._url_parser = PartialURLParser()

    def matches(self, **kwargs):
        # Weed out unity text entries that report being editable but don't
        # actually provide methods of the Atspi.Text interface.
        return "Text" in kwargs.get("interfaces", [])

    def init_domain(self):
        """ Called on being selected as the currently active domain. """
        pass

    def read_context(self, accessible):
        return NotImplementedError()

    def get_auto_separator(self, context):
        """
        Get word separator to add after inserting a prediction choice.

        Doctests:
        >>> d = DomainGenericText()
        >>> d.get_auto_separator("word http")
        ' '
        >>> d.get_auto_separator("word http://www")
        '.'
        >>> d.get_auto_separator("/etc")
        ''
        """
        separator = " "

        # split at whitespace to catch whole URLs/file names
        strings = context.split()
        if strings:
            string = strings[-1]
            if self._url_parser.is_maybe_url(string):
                separator = self._url_parser.get_auto_separator(string)
            else:
                # File name?
                if  "/" in string:
                    separator = ""

        return separator

    def get_text_begin_marker(self):
        return ""

    def is_keypress_feedback_allowed(self):
        return True

    def is_spell_check_allowed(self):
        return False


class DomainNOP(TextDomain):
    """ Do-nothing domain, no focused accessible. """

    def matches(self, **kwargs):
        return True

    def read_context(self, accessible):
        return "", "", 0, TextSpan(), False, 0

    def get_auto_separator(self, context):
        """ Get word separator to add after inserting a prediction choice. """
        return ""


class DomainPassword(DomainNOP):
    """ Do-nothing domain for password entries """

    def matches(self, **kwargs):
        return kwargs.get("role") == Atspi.Role.PASSWORD_TEXT

    def is_keypress_feedback_allowed(self):
        return False


class DomainGenericText(TextDomain):
    """ Default domain for generic text entry """

    def matches(self, **kwargs):
        return TextDomain.matches(self, **kwargs)

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
        begin_of_text = begin == 0
        begin_of_text_offset = 0

        return (context, line, line_cursor, cursor_span,
                begin_of_text, begin_of_text_offset)

    def is_spell_check_allowed(self):
        return True

    def get_text_begin_marker(self):
        return "<bot:txt>"


class DomainTerminal(TextDomain):
    """ Terminal entry, in particular gnome-terminal """

    _prompt_patterns = tuple(re.compile(p, re.UNICODE) for p in \
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
        return TextDomain.matches(self, **kwargs) and \
               kwargs.get("role") == Atspi.Role.TERMINAL

    def init_domain(self):
        pass

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
        begin_of_text = False
        begin_of_text_offset = None
        l = line[:line_cursor]
        for i in range(2):
            entry_start = self._find_prompt(l)
            context += l[entry_start:]
            if i == 0:
                line = line[entry_start:] # cut prompt from input line
                line_start  += entry_start
                line_cursor -= entry_start
            if entry_start:
                begin_of_text = True
                begin_of_text_offset = line_start
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

        return (context, line, line_cursor, cursor_span,
                begin_of_text, begin_of_text_offset)

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

    def get_text_begin_marker(self):
        return "<bot:term>"


class DomainURL(DomainGenericText):
    """ (Firefox) address bar """

    def matches(self,  **kwargs):
        attributes = kwargs.get("attributes")
        if attributes:
            # firefox url bar?
            if "urlbar" in attributes.get("class", ""):
                return True
        return False

    def get_auto_separator(self, context):
        """
        Get word separator to add after inserting a prediction choice.
        """
        return self._url_parser.get_auto_separator(context)

    def get_text_begin_marker(self):
        return "<bot:url>"

    def is_spell_check_allowed(self):
        return False


class PartialURLParser:
    """
    Parse partial URLs and predict separators.
    Parsing is neither complete nor RFC prove but probably doesn't
    have to be either. The goal is to save key strokes for the
    most common cases.

    Doctests:
    >>> p = PartialURLParser()
    >>> p.tokenize_url('http://user:pass@www.do-mai_n.nl/path/name.ext')
    ['http', '://', 'user', ':', 'pass', '@', 'www', '.', 'do-mai_n', '.', 'nl', '/', 'path', '/', 'name', '.', 'ext']

    """
    _gTLDs   = ["aero", "asia", "biz", "cat", "com", "coop", "info", "int",
               "jobs", "mobi", "museum", "name", "net", "org", "pro", "tel",
               "travel", "xxx"]
    _usTLDs = ["edu", "gov", "mil"]
    _ccTLDs = ["ac", "ad", "ae", "af", "ag", "ai", "al", "am", "an", "ao",
               "aq", "ar", "as", "at", "au", "aw", "ax", "az", "ba", "bb",
               "bd", "be", "bf", "bg", "bh", "bi", "bj", "bm", "bn", "bo",
               "br", "bs", "bt", "bv", "bw", "by", "bz", "ca", "cc", "cd",
               "cf", "cg", "ch", "ci", "ck", "cl", "cm", "cn", "co", "cr",
               "cs", "cu", "cv", "cx", "cy", "cz", "dd", "de", "dj", "dk",
               "dm", "do", "dz", "ec", "ee", "eg", "eh", "er", "es", "et",
               "eu", "fi", "fj", "fk", "fm", "fo", "fr", "ga", "gb", "gd",
               "ge", "gf", "gg", "gh", "gi", "gl", "gm", "gn", "gp", "gq",
               "gr", "gs", "gt", "gu", "gw", "gy", "hk", "hm", "hn", "hr",
               "ht", "hu", "id", "ie", "il", "im", "in", "io", "iq", "ir",
               "is", "it", "je", "jm", "jo", "jp", "ke", "kg", "kh", "ki",
               "km", "kn", "kp", "kr", "kw", "ky", "kz", "la", "lb", "lc",
               "li", "lk", "lr", "ls", "lt", "lu", "lv", "ly", "ma", "mc",
               "md", "me", "mg", "mh", "mk", "ml", "mm", "mn", "mo", "mp",
               "mq", "mr", "ms", "mt", "mu", "mv", "mw", "mx", "my", "mz",
               "na", "nc", "ne", "nf", "ng", "ni", "nl", "no", "np", "nr",
               "nu", "nz", "om", "pa", "pe", "pf", "pg", "ph", "pk", "pl",
               "pm", "pn", "pr", "ps", "pt", "pw", "py", "qa", "re", "ro",
               "rs", "ru", "rw", "sa", "sb", "sc", "sd", "se", "sg", "sh",
               "si", "sj", "sk", "sl", "sm", "sn", "so", "sr", "ss", "st",
               "su", "sv", "sy", "sz", "tc", "td", "tf", "tg", "th", "tj",
               "tk", "tl", "tm", "tn", "to", "tp", "tr", "tt", "tv", "tw",
               "tz", "ua", "ug", "uk", "us", "uy", "uz", "va", "vc", "ve",
               "vg", "vi", "vn", "vu", "wf", "ws", "ye", "yt", "yu", "za",
               "zm", "zw"]
    _TLDs = frozenset(_gTLDs + _usTLDs + _ccTLDs) 

    _schemes = ["http", "https", "ftp", "file"]
    _protocols = ["mailto", "apt"]
    _all_schemes = _schemes + _protocols

    _url_pattern = re.compile("([\w-]+)|(\W+)", re.UNICODE)

    def iter_url(self, url):
        return self._url_pattern.finditer(url)

    def tokenize_url(self, url):
        return[group for match in self.iter_url(url)
                     for group in match.groups() if not group is None]

    def is_maybe_url(self, context):
        """ 
        Is this maybe something looking like an URL? 

        Doctests:
        >>> d = PartialURLParser()
        >>> d.is_maybe_url("http")
        False
        >>> d.is_maybe_url("http:")
        True
        >>> d.is_maybe_url("http://www.domain.org")
        True
        """
        tokens = self.tokenize_url(context)
        if len(tokens) >= 2:
            token  = tokens[0]
            septok = tokens[1]
            if token in self._all_schemes and septok.startswith(":"):
                return True
        return False


    def get_auto_separator(self, context):
        """
        Get word separator to add after inserting a prediction choice.

        Doctests:
        >>> p = PartialURLParser()
        >>> p.get_auto_separator("http")
        '://'
        >>> p.get_auto_separator("www")
        '.'
        >>> p.get_auto_separator("http://www.domain")
        '.'
        >>> p.get_auto_separator("http://www.domain.org")
        '/'
        >>> p.get_auto_separator("http://www.domain.org/home")
        ''
        >>> p.get_auto_separator("mailto")
        ':'
        >>> p.get_auto_separator("file")
        ':///'
        >>> p.get_auto_separator("file:///home")
        ''
        """
        separator = " " # may be entering search terms, keep space as default
              
        SCHEME, PROTOCOL, DOMAIN, PATH = range(4)
        component = SCHEME
        last_septok = ""
        matches = self.iter_url(context)
        for match in matches:
            groups = match.groups()
            token  = groups[0]
            septok = groups[1]

            if septok:
                last_septok = septok

            if component == SCHEME:
                if token:
                    if token == "file":
                        separator = ":///"
                        component = PATH
                        continue
                    if token in self._schemes:
                        separator = "://"
                        component = DOMAIN
                        continue
                    elif token in self._protocols:
                        separator = ":"
                        component = PROTOCOL
                        continue
                    else:
                        component = DOMAIN

            if component == DOMAIN:
                if token:
                    separator = "."
                    if last_septok == "." and token in self._TLDs:
                        separator = "/"
                        component = PATH
                        continue

            if component == PATH:
                separator = ""

            if component == PROTOCOL:
                separator = ""

        return separator


class TextClassifier(osk.TextClassifier):
    """ Wrapper class for language detection. """
    def __init__(self):
        self._pattern = re.compile("\[(.*?)--.*?\]", re.UNICODE)

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


