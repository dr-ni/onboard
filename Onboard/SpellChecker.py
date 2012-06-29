
# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import subprocess

### Logging ###
import logging
_logger = logging.getLogger("SpellChecker")
###############


class SpellChecker:
    def __init__(self):
        self._spell = hunspell()
        #self._spell = aspell()

    def find_corrections(self, word, caret_offset):
        results = self._spell.query(word)
        # hunspell splits words at underscores and then
        # returns results for multiple words.
        # -> find the one at the current caret offset.
        span = None
        suggestions = []
        for result in results:
            print(result[0][1], caret_offset)
            if result[0][0] > caret_offset:
                break
            suggestions = result[1]
            span = result[0]
        return span, suggestions 


class SCBackend:
    """ Base class of all spellchecker backends """

    def query(self, text):
        """
        Query for spelling suggestions.
        Text may contain one or more words. Each word generates its own
        list of suggestions. The spell checker backend decides about
        word boundaries.

        Doctests:
        # one prediction token, two words for the spell checker
        >>> sp = hunspell("en_US")
        >>> q = sp.query("conter_trop")
        >>> q  # doctest: +ELLIPSIS
        [[[0, 6, 'conter'], [...
        >>> len(q)
        2
        """
        results = []
        #print("< '" +  text + "'")
        self._p.stdin.write((text + "\n").encode("UTF-8"))
        self._p.stdin.flush()
        while True:
            s = self._p.stdout.readline().decode("UTF-8")
            s = s.strip()
            if not s:
                break
            #print("> '" +  line + "'")
            if s[:1] == "&":
                sections = s.split(":")
                a = sections[0].split()
                begin = int(a[3])
                end   = begin + len(a[1])
                span = [begin, end, a[1]] # begin, end, word
                suggestions = sections[1].strip().split(', ')
                results.append([span, suggestions])

        return results


class hunspell(SCBackend):
    """
    # known word
    >>> sp = hunspell("en_US")
    >>> sp.query("test")
    []

    # unknown word
    >>> sp = hunspell("en_US")
    >>> sp.query("jdaskljasd")  # doctest: +ELLIPSIS
    [[...
    """
    def __init__(self, languange = None):
        args = ["hunspell"]
        if 0 and languange:
            args += ["-d ", languange]
        self._p = subprocess.Popen(args,
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   close_fds=True)
        self._p.stdout.readline() # skip header line


class aspell(SCBackend):
    """
    # known word
    >>> sp = aspell("en_US")
    >>> sp.query("test")
    []

    # unknown word
    >>> sp = aspell("en_US")
    >>> sp.query("jdaskljasd")  # doctest: +ELLIPSIS
    [[...
    """
    def __init__(self, languange = None):
        args = ["aspell", "-a"]
        if languange:
            args += ["-l", languange]
        self._p = subprocess.Popen(args,
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   close_fds=True)
        self._p.stdout.readline() # skip header line

