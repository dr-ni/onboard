# -*- coding: latin-1 -*-

import sys
import os, errno
import codecs
import unicodedata

from Onboard import KeyCommon

### Logging ###
import logging
_logger = logging.getLogger("WordPredictor")
###############


(WORD_MODE) = range(1)  # later maybe SENTENCE_MODE, SNIPPET_MODE


class Punctuator:
    """
    Mainly adds and removes spaces around punctuation depending on
    the action immediately after word completion.
    """

    def __init__(self):
        self.end_of_word = False
        self.space_added = False

    def set_end_of_word(self, val=True):
        self.end_of_word = val;

    def before_key_press(self, key):
        """ replace key with a different string of key presses """
        keystr = u""
        if self.space_added:  # did we previously add a trailing space?
            if key.action_type == KeyCommon.KEYCODE_ACTION:

                char = key.get_label().decode("utf-8")
                name = key.get_name().upper()

                if   char in (","):
                    keystr = u"\b" + char + u" "

                elif char in (".",":",";","?","!"):
                    keystr = u"\b" + char + " " + "U"  # U for upper case

                self.space_added = False

        return keystr

    def after_key_press(self, key):
        """ add additional characters after the key press"""
        keystr = u""
        if self.end_of_word:
            keystr = u" "
            self.space_added = True
            self.end_of_word = False

        return keystr


class WordPredictor:

    def __init__(self):
        self.input = u""
        self.matches = []
        self.mode = WORD_MODE
        self.dictionaries = []
        self.autolearn_dictionary = None

        # possibly remove accents from international characters
        # e.g. åáéíóúäöü becomes aaeiouaou
        #self.translation_map = unaccent_map()  # simplifies spanish typing
        self.translation_map = identity_map()  # exact matches

        # todo: settings
        autolearn_dict_file = "%s/.sok/dictionaries/user.dict" % os.path.expanduser("~")
        active_dict_files = ["dictionaries/en.dict", autolearn_dict_file]

        # autolearn dictionary must be in set of active dictionaries
        if autolearn_dict_file not in active_dict_files:
            autolearn_dict_file = None
            _logger.warning("No auto learn dictionary selected. Please setup auto learning first.")

        # load dictionaries
        for filename in active_dict_files:
            d = Dictionary(filename, self.translation_map)
            self.dictionaries.append(d)
            if filename == autolearn_dict_file:
                self.autolearn_dictionary = d


    def key_pressed(self, key, mods):
        """ runs the completion/prediction on each key press """

        reset = False

        if key.action_type == KeyCommon.KEYCODE_ACTION:

            name = key.get_name().upper()
            char = key.get_label().decode("utf-8")
            if len(char) > 1:
                char = u""

            if   name == 'BKSP':
                self.input = self.input[:-1]

            elif name in ("SPCE", "TAB") or \
                 char in (".",",",":",";","?","!"):
                if self.mode != WORD_MODE:
                    self.input += char
                else:
                    reset = True

            elif key.is_printable():
                if not mods[4]:  # ignore ctrl+key presses
                    self.input +=char
            else:
                reset = True
        else:
            reset = True

        if reset:
            self.input = u""

        self.matches = self.find_matches(self.input)
        return self.matches


    def find_matches(self, _input):

        # order of dictionaries is important: last match wins
        m = {}
        if _input:
            for dic in self.dictionaries:
                d = dic.find_matches(_input, 50)
                m.update(d)

        # final sort by weight (frequency)
        matches = sorted(m.items(), key=lambda x: x[1], reverse=True)
        #print _input, matches[:5]

        return [x[0] for x in matches]


    def get_match_remainder(self, index):
        """ returns the rest of match[index] that hasn't been typed yet """
        return self.matches[index][len(self.input):]


class Dictionary:

    def __init__(self, filename, transmap):
        self.filename = filename
        self.translation_map = transmap
        self.words = []
        self.weights = []
        self.count = 0  # total number of words including duplicates

        self.load()

    def load(self):

        # load dictionary as unicode
        fields = []
        try:
            fields = codecs.open(self.filename, encoding='utf-8').read() \
                                   .replace(u",",u"\n").splitlines()
        except IOError, e:
            _logger.warning("Failed to load dictionary '%s': %s (%d)" %
                            (self.filename, os.strerror(e.errno), e.errno))

        # two flat lists are most memory efficient
        # with ~1000000 spanish words:
        # - Trie       - >600MB
        # - 2d-List    - ~170MB
        # - 2x 1d-List - ~100MB
        self.words   = fields[0::2]  # every second element is a word
        self.weights = [int(w) for w in fields[1::2]] # convert weights to ints
        del fields

        # temporarily sort on startup to sync with binary search
        ai = range(len(self.words))
        #ai.sort(key=lambda i: self.words[i])
        ai.sort(key=lambda i: self.words[i].translate(self.translation_map))
        self.words   = [self.words  [i] for i in ai]
        self.weights = [self.weights[i] for i in ai]
        self.count = sum(self.weights)

        #self.rows = dict(zip(self.words, self.weights))
        #self.rows = zip(self.words, self.weights)
        #self.words   = []
        #self.weights = []

        #self.trie = Trie()
        #for word,weight in self.rows:
        #    self.trie.add(word, weight)

        #print self.words[:100]
        #print self.words

    def find_matches(self, _input, limit):
        words    = self.words
        weights  = self.weights
        transmap = self.translation_map
        prefix   = _input.translate(transmap)

        # binary search for the first match
        start = self.bisect_left(words, prefix, lambda x: x.translate(transmap))

        # collect all subsequent matches
        ai = []
        for i in xrange(start, len(words)):
            if not words[i].translate(transmap).startswith(prefix):
                break
            ai.append(i)

        # exhaustive search to verify results
        if 0:
            matches = [words[i] for i in ai]
            print u"'%s' %d matches: %s" % (prefix, len(matches),
                                            str(matches[:5]))
            ai = [i for i in xrange(len(words)) \
                    if words[i].translate(transmap).startswith(prefix)]
            matches = [words[i] for i in ai]
            print u"'%s' %d matches: %s" % (prefix, len(matches),
                                            str(matches[:5]))

        # sort matches by weight (word frequency)
        ai.sort(key=lambda i: weights[i], reverse=True)

        # limit number of results, normalize weights and
        # return as map {word:weight}
        return dict((words[i], float(weights[i]) / self.count) \
                    for i in ai[:limit])

    def bisect_left(self, a, prefix, value_func, lo=0, hi=None):
        """
            Binary search based on python's bisect.bisect_left.
            cmp_func returns True if x is less than the search key.
        """
        if lo < 0:
            raise ValueError('lo must be non-negative')
        if hi is None:
            hi = len(a)
        while lo < hi:
            mid = (lo+hi)//2
            if value_func(a[mid]) < prefix: lo = mid+1
            else: hi = mid
        return lo


class unaccent_map(dict):
    """
    Unicode translation map for use with string.translate().
    It tries to replace language dependent special
    characters with their closest latin equivalent.
    """
    def __missing__(self, key):
        char = key
        decomp = unicodedata.decomposition(unichr(key)).split()
        try:
            char = int(decomp[0], 16)
        except (IndexError, ValueError):
            pass
        self[key] = char
        return char

class identity_map(dict):
    """
    Nop translation map for use with string.translate().
    """
    def __missing__(self, key):
        self[key] = key
        return key


class Trie:  # not yet used; too slow, high memory usage
    def __init__(self):
        self.root = [None, {}]

    def add(self, key, value):
        node = self.root
        for c in key:
            node = node[1].setdefault(c, [None, {}])
        node[0] = value # value!=None marks the end of a complete word

    def findall(self, prefix): #
        node = self.root
        for c in prefix:
            node = node[1].get(c)
            if node == None:
                return []

        matches = []
        self.traverse(node, prefix, lambda x,y: matches.append((x,y)))
        return matches

    def traverse(self, node, key, func):
        if node is not None:
            if node[0] is not None:
                func(key, node[0])
            for c,child in node[1].iteritems():
                self.traverse(child, key+c, func)


