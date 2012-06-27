
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
        return self._spell.query(word)


class SCBackend:
    """ Base class of all spellchecker backends """

    def query(self, word):
        result = []

        self._p.stdin.write((word + "\n").encode("UTF-8"))
        self._p.stdin.flush()
        s = self._p.stdout.readline().decode("UTF-8")
        print(s)
        s = s.strip().lower()
        self._p.stdout.readline() # skip empty line

        if s[:1] == "&":
            result = s.split(':')[1].strip().split(', ')

        return result
 

class hunspell(SCBackend):
    """
    >>> sp = hunspell("en_US")
    >>> sp.query("test")
    []
    """
    def __init__(self, dict = None):
        args = ["hunspell"]
        if dict:
            args.append("-d " + dict)
        self._p = subprocess.Popen(args,
                                   stdin=subprocess.PIPE, 
                                   stdout=subprocess.PIPE,
                                   close_fds=True)
        self._p.stdout.readline() # skip header line

class aspell(SCBackend):
    """
    >>> sp = aspell("en_US")
    >>> sp.query("test")
    []
    """
    def __init__(self, dict = None):
        args = ["aspell", "-a"]
        if dict:
            args.append("-d " + dict)
        self._p = subprocess.Popen(args,
                                   stdin=subprocess.PIPE, 
                                   stdout=subprocess.PIPE,
                                   close_fds=True)
        self._p.stdout.readline() # skip header line
 
