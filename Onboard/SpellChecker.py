
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

    def find_corrections(self, word):
        results = self._spell.query(word)
        # hunspell splits words at underscores and then 
        # returns results for multiple words.
        # -> ignore all but the last result
        if results:
            return results[-1]
        return []


class SCBackend:
    """ Base class of all spellchecker backends """

    def query(self, text):
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
                results.append(s.split(':')[1].strip().split(', '))

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
 
