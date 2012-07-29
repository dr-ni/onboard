
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
        if backend == 0:
            _class = hunspell
        else:
            _class = aspell

        if not self._backend or \
           not type(self._backend) == _class:
            self._backend = _class()

    def set_dict_ids(self, dict_ids):
        if self._backend and \
           not dict_ids == self._backend.get_active_dict_ids():
            self._backend.stop()
            if dict_ids:
                self._backend.start(dict_ids)

    def find_corrections(self, word, caret_offset):
        span = None
        suggestions = []
        if self._backend:
            results = self._backend.query(word)
            # hunspell splits words at underscores and then
            # returns results for multiple sub-words.
            # -> find the sub-word at the current caret offset.
            for result in results:
                if result[0][0] > caret_offset:
                    break
                suggestions = result[1]
                span = result[0]

        return span, suggestions

    def get_supported_dict_ids(self):
        return self._backend.get_supported_dict_ids()


class SCBackend:
    """ Base class of all spellchecker backends """

    def __init__(self, dict_ids = None):
        self._active_dicts = None
        self._p = None

    def start(self, dict_ids = None):
        self._active_dicts = dict_ids

    def stop(self):
        print("stop", self._p)
        if self._p:
            self._p.terminate()
            self._p.wait()
            self._p = None

    def query(self, text):
        """
        Query for spelling suggestions.
        Text may contain one or more words. Each word generates its own
        list of suggestions. The spell checker backend decides about
        word boundaries.

        Doctests:
        # one prediction token, two words for the spell checker
        >>> sp = hunspell(["en_US"])
        >>> q = sp.query("conter_trop")
        >>> q  # doctest: +ELLIPSIS
        [[[0, 6, 'conter'], [...
        >>> len(q)
        2
        """
        results = []

        # Check if the process is still running, it might have
        # exited on start due to an unknown dictinary name.
        if self._p and not self._p.poll() is None:
            self._p = None

        if self._p:
            
            self._p.stdin.write(("^" + text + "\n").encode("UTF-8"))
            self._p.stdin.flush()
            while True:
                s = self._p.stdout.readline().decode("UTF-8")
                s = s.strip()
                if not s:
                    break
                if s[:1] == "&":
                    sections = s.split(":")
                    a = sections[0].split()
                    begin = int(a[3]) - 1 # -1 for the prefixed ^
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

    def get_active_dict_ids(self):
        """
        Return active dictionary ids.
        """
        return self._active_dicts


class hunspell(SCBackend):
    """
    Hunspell backend.

    Doctests:
    # known word
    >>> sp = hunspell(["en_US"])
    >>> sp.query("test")
    []

    # unknown word
    >>> sp = hunspell(["en_US"])
    >>> sp.query("jdaskljasd")  # doctest: +ELLIPSIS
    [[...
    """
    def __init__(self, dict_ids = None):
        SCBackend.__init__(self, dict_ids)
        if dict_ids:
            self.start(dict_ids)

    def start(self, dict_ids = None):
        super(hunspell, self).start(dict_ids)

        args = ["hunspell", "-a", "-i", "UTF-8"]
        if dict_ids:
            args += ["-d", ",".join(dict_ids)]

        try:
            self._p = subprocess.Popen(args,
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       close_fds=True)
            self._p.stdout.readline() # skip header line
            print("hunspell.start", dict_ids)
        except OSError as e:
            _logger.error(_format("Failed to execute '{}', {}", \
                            " ".join(args), e))
            self._p = None

    def get_supported_dict_ids(self):
        """
        Return raw supported dictionary ids.
        They may not all be valid language ids, e.g. en-GB for myspell dicts.
        """
        dict_ids = []
        args = ["hunspell", "-D"]

        try:
            p = subprocess.Popen(args,
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
                            " ".join(args), e))
        return dict_ids


class aspell(SCBackend):
    """
    Aspell backend.

    Doctests:
    # known word
    >>> sp = aspell(["en_US"])
    >>> sp.query("test")
    []

    # unknown word
    >>> sp = aspell(["en_US"])
    >>> sp.query("jdaskljasd")  # doctest: +ELLIPSIS
    [[...
    """
    def __init__(self, dict_ids = None):
        SCBackend.__init__(self, dict_ids)
        if dict_ids:
            self.start(dict_ids)

    def start(self, dict_ids = None):
        super(aspell, self).start(dict_ids)

        args = ["aspell", "-a"]
        if dict_ids:
            args += ["-l", ",".join(dict_ids)]

        try:
            self._p = subprocess.Popen(args,
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       close_fds=True)
            self._p.stdout.readline() # skip header line
            print("aspell.start", dict_ids)
        except OSError as e:
            _logger.error(_format("Failed to execute '{}', {}", \
                            " ".join(args), e))
            self._p = None

    def get_supported_dict_ids(self):
        """
        Return raw supported dictionary ids.
        """
        dict_ids = []
        args = ["aspell", "dump", "dicts"]
        try:
            dict_ids = subprocess.check_output(args) \
                                .decode("UTF-8").split("\n")
        except OSError as e:
            _logger.error(_format("Failed to execute '{}', {}", \
                            " ".join(args), e))
        return [id for id in dict_ids if id]

