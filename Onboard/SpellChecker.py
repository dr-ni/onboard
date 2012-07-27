
# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import os
import subprocess

### Logging ###
import logging
_logger = logging.getLogger("SpellChecker")
###############


class SpellChecker:
    def __init__(self):
        self._backend = None

    def set_backend(self, backend):
        """ Switch spell check backend on the fly """
        if backend == 1:
            _class = aspell
        else:
            _class = hunspell

        if not self._backend or \
           not type(self._backend) == _class:
            self._backend = _class()

    def find_corrections(self, word, caret_offset):
        span = None
        suggestions = []
        if self._backend:
            results = self._backend.query(word)
            # hunspell splits words at underscores and then
            # returns results for multiple words.
            # -> find the one at the current caret offset.
            for result in results:
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

    def get_supported_dict_ids(self):
        """
        Return raw supported dictionary ids.
        """
        raise NotImplementedError()


class hunspell(SCBackend):
    """
    Hunspell backend.

    Doctests:
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
        args = ["hunspell", "-a", "-i UTF-8"]
        if 0 and languange:
            args += ["-d ", languange]
        self._p = subprocess.Popen(args,
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   close_fds=True)
        self._p.stdout.readline() # skip header line

    def get_supported_dict_ids(self):
        """
        Return raw supported dictionary ids.
        They may not all be valid language ids, e.g. en-GB for myspell dicts.
        """
        dict_ids = []
        try:
            p = subprocess.Popen(["hunspell", "-D"],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 close_fds=True)
            out, err = p.communicate("") # send something to shut hunspell down

            # scrape the dict_ids from stderr
            in_dicts = False
            for line in err.decode("UTF-8").split("\n"):
                if in_dicts:
                    if not "/" in line:
                        break

                    # extract language id
                    lang_id = os.path.basename(line)
                    if not lang_id.lower().startswith("hyph"):
                        dict_ids.append(lang_id)

                if line.startswith("AVAILABLE DICTIONARIES"): # not translated?
                    in_dicts = True

        except OSError as e:
            _logger.error(_format("Failed to execute '{}', {}", \
                            " ".join(self.args), e))
        return dict_ids


class aspell(SCBackend):
    """
    Aspell backend.

    Doctests:
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

    def get_supported_dict_ids(self):
        """
        Return raw supported dictionary ids.
        """
        dict_ids = []
        try:
            dict_ids = subprocess.check_output(["aspell", "dump", "dicts"]) \
                                .decode("UTF-8").split("\n")
        except OSError as e:
            _logger.error(_format("Failed to execute '{}', {}", \
                            " ".join(self.args), e))
        return [id for id in dict_ids if id]

