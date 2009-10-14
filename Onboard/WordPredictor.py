# -*- coding: latin-1 -*-

import sys
import os, errno
import codecs
import unicodedata
import re

from Onboard import KeyCommon

### Logging ###
import logging
_logger = logging.getLogger("WordPredictor")
###############


(WORD_MODE) = range(1)  # later maybe SENTENCE_MODE, SNIPPET_MODE


class InputLine:

    def __init__(self):
        self.reset()

    def reset(self):
        self.line = u""

    def append(self, s):
        self.line += s

    def backspace(self):
        self.line = self.line[:-1]

    def get_last_word(self):
        return re.search(u"([\w]|[-'])*$", self.line, re.UNICODE).group()

    def get_all_words(self):
        return re.findall(u"(?:[\w]|[-'])+", self.line, re.UNICODE)


class Punctuator:
    """
    Mainly adds and removes spaces around punctuation depending on
    the action immediately after word completion.
    """

    def __init__(self, input_line):
        self.input = input_line
        self.reset()

    def reset(self):
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

                if   char in u",;":
                    keystr = u"\b" + char + " "

                elif char in u".:?!":
                    keystr = u"\b" + char + " " + "U"  # U for upper case

                self.space_added = False

        self.input.append(keystr)
        return keystr

    def after_key_press(self, key):
        """ add additional characters after the key press"""
        keystr = u""
        if self.end_of_word:
            keystr = u" "
            self.space_added = True
            self.end_of_word = False

        self.input.append(keystr)
        return keystr


class WordPredictor:
    """ more like a word end predictor or word completer at the moment. """

    def __init__(self, input_line):
        self.input = input_line
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
        system_dict_files = ["dictionaries/en.dict"]
        user_dict_files   = [autolearn_dict_file]

        # autolearn dictionary must be in set of active dictionaries
        if autolearn_dict_file not in user_dict_files:
            autolearn_dict_file = None
            _logger.warning("No auto learn dictionary selected. "
                            "Please setup auto-learning first.")

        # load dictionaries
        for filename in system_dict_files:
            d = Dictionary(filename, False, self.translation_map)
            self.dictionaries.append(d)
        for filename in user_dict_files:
            d = Dictionary(filename,  True, self.translation_map)
            self.dictionaries.append(d)
            if filename == autolearn_dict_file:
                self.autolearn_dictionary = d


    def key_pressed(self, key, mods, auto_learn=False):
        """ runs the completion/prediction on each key press """

        reset = False

        if key.action_type == KeyCommon.WORD_ACTION:
            pass # don't reset input on word insertion

        elif key.action_type == KeyCommon.KEYCODE_ACTION:

            name = key.get_name().upper()
            char = key.get_label().decode("utf-8")

            if name == 'RTRN':
                char = u"\n"
            if name == 'SPCE':
                char = u" "
            if name == 'TAB':
                char = u"\t"

            if   name == 'BKSP':
                self.input.backspace()

            elif name in ("SPCE", "TAB") or \
                 char in u".,:;?![](){}/\\#""|":
                self.input.append(char)

            elif key.is_printable():
                if mods[4]:  # ignore ctrl+key presses
                    reset = True
                else:
                    self.input.append(char)
            else:
                reset = True

        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            pass  # simply pressing a modifier shouldn't stop the word

        else:
            reset = True

        if reset:
            # try to learn all words of the input line
            if auto_learn:
                for word in self.input.get_all_words():
                    self.learn_word(word)
            self.input.reset()

        self.match_input = self.input.get_last_word()
        self.matches = self.find_completion_matches(self.match_input)
#        print "'%s'" % self.input.line
        return self.matches


    def get_match_remainder(self, index):
        """ returns the rest of matches[index] that hasn't been typed yet """
        return self.matches[index][len(self.match_input):]


    def find_completion_matches(self, _input):

        # order of dictionaries is important: last match wins
        m = {}
        if _input:
            for dic in self.dictionaries:
                m.update(dic.find_completion_matches(_input, 50))

        # final sort by weight (frequency)
        matches = sorted(m.items(), key=lambda x: x[1], reverse=True)

        return [x[0] for x in matches]


    def learn_word(self, word):
        """ add word to the auto-learn dictionary"""

        if self.autolearn_dictionary:
            # has to have at least two characters
            # must not start with a number
            # has to be all alphanumeric
            if len(word) > 1 and \
               re.match(u"^[\D]([\w]|[-'])*$", word, re.UNICODE):
                self.autolearn_dictionary.learn_word(word)


    def save_dictionaries(self):
        for d in self.dictionaries:
            if d.modified:
                d.save()



class Dictionary:

    def __init__(self, filename, _writable, transmap):
        self.filename = filename
        self.modified = False
        self.writable = _writable
        self.translation_map = transmap
        self.words = []
        self.weights = []
        self.count = 0  # total number of words including duplicates

        self.load()

    def __del__(self):
        if self.modified:
            self.save()

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

        # sort on startup to sync with binary search
        # can't really store presorted dictionaries:
        # - system locale may change, possibly altering collation sequence
        # - translation map may change based on selected dictionaries
        ai = range(len(self.words))
        ai.sort(key=lambda i: self.words[i].translate(self.translation_map))
        self.words   = [self.words  [i] for i in ai]
        self.weights = [self.weights[i] for i in ai]
        self.count = sum(self.weights)

        #print self.words[:100]
        #print self.words


    def save(self):
        words   = self.words
        weights = self.weights

        if self.modified or \
           not os.path.exists(self.filename):
            _logger.info("saving '%s'" % self.filename)


            lines = ["%s,%d\n" % (words[i], weights[i])
                     for i in xrange(len(words))]
            try:
                basename, ext = os.path.splitext(self.filename)
                tempfile = basename + ".tmp"
                with codecs.open(tempfile, "wt", encoding='utf-8') as f:
                    f.writelines(lines)

                if os.path.exists(self.filename):
                    os.rename(self.filename, self.filename + ".bak")
                os.rename(tempfile, self.filename)

                self.modified = False

            except IOError, e:
                _logger.warning("Failed to save dictionary '%s': %s (%d)" %
                                (self.filename, os.strerror(e.errno), e.errno))


    def find_completion_matches(self, _input, limit):
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


    def learn_word(self, word):
        # search for an exact match
        i = self.bisect_left(self.words, word, lambda x: x)
        if i < len(self.words) and self.words[i] == word:
            self.weights[i] += 1
            _logger.info("strengthened word '%s' count %d" % (word, self.weights[i]))
        else:
            # Array insert...ugh, probably the best compromise though.
            # By the time the list grows big enough for inserts to become an
            # issue, new words will be increasingly rare. So for now stick
            # with a single data structure for both, potentially large, but read-only
            # system dictionaries and smaller, writable user dictionaries.
            self.words.insert(i, word)
            self.weights.insert(i, 1)
            _logger.info("learned new word '%s' count %d" % (word, 1))
        self.count += 1
        self.modified = True


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


#self.trie = Trie()
#for word,weight in self.rows:
#    self.trie.add(word, weight)

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


