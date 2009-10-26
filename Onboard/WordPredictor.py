# -*- coding: latin-1 -*-

import sys
import os, errno
import codecs
import unicodedata
import re

### Logging ###
import logging
_logger = logging.getLogger("WordPredictor")
###############


class InputLine:

    def __init__(self):
        self.reset()

    def reset(self):
        self.line = u""
        self.cursor = 0
        self.valid = True

    def is_valid(self):
        return self.valid

    def insert(self, s):
        self.line = self.line[:self.cursor] + s + self.line[self.cursor:]
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

    def get_all_words(self):
        return re.findall(u"(?:[\w]|[-'])+", self.line, re.UNICODE)

    def get_word_before_cursor(self):
        return self.get_last_word(self.line[:self.cursor])

    def get_last_word(self, s):
        return re.search(u"([\w]|[-'])*$", s, re.UNICODE).group()

    def is_printable(self, char):
        """
        True for printable keys including whitespace as defined for isprint().
        Word completion uses this to filter for printable keys.
        """
        if char == u"\t":
            return True
        return not unicodedata.category(char) in ('Cc','Cf','Cs','Co',
                                                  'Cn','Zl','Zp')

class Punctuator:
    """
    Mainly adds and removes spaces around punctuation depending on
    the action immediately after word completion.
    """
    BACKSPACE  = u"\b"
    CAPITALIZE = u"\x0e"  # abuse U+000E SHIFT OUT to signal upper case

    def __init__(self):
        self.reset()

    def reset(self):
        self.end_of_word = False
        self.space_added = False

    def set_end_of_word(self, val=True):
        self.end_of_word = val;

    def before_key_press(self, char):
        upper_case = False

        """ replace key with a different string of key presses """
        keystr = u""
        if self.space_added:  # did we previously add a trailing space?

            if   char in u",:;":
                keystr = self.BACKSPACE + char + " "

            elif char in u".?!":
                keystr = self.BACKSPACE + char + " " + self.CAPITALIZE

            self.space_added = False

        return keystr

    def after_key_press(self):
        """ add additional characters after the key press"""
        keystr = u""
        if self.end_of_word:
            keystr = u" "
            self.space_added = True
            self.end_of_word = False

        return keystr


class WordPredictor:
    """ more like a word end predictor or word completer at the moment. """

    def __init__(self):
        self.matches = []
        self.dictionaries = []
        self.autolearn_dictionary = None
        self.frequency_time_ratio = 50  # 0=100% frequency, 100=100% time

        # possibly remove accents from international characters
        # e.g. åáéíóúäöü becomes aaeiouaou
        #self.translation_map = unaccent_map()  # simplifies spanish typing
        self.translation_map = identity_map()  # exact matches

    def find_choices(self, input_line, frequency_time_ratio):
        """ runs the completion/prediction """
        self.match_input = input_line.get_word_before_cursor()
        self.matches = self.find_completion_matches(self.match_input,
                                                    frequency_time_ratio)
        return self.matches


    def get_match_remainder(self, index):
        """ returns the rest of matches[index] that hasn't been typed yet """
        return self.matches[index][len(self.match_input):]


    def find_completion_matches(self, _input, frequency_time_ratio):

        # order of dictionaries is important: last match wins
        m = {}
        if _input:
            for dic in self.dictionaries:
                m.update(dic.find_completion_matches(_input, 50, \
                                                     frequency_time_ratio))

        # final sort by weight (frequency)
        matches = sorted(m.items(), key=lambda x: x[1], reverse=True)

        return [x[0] for x in matches]


    def learn_words(self, words):
        """ add words to the auto-learn dictionary"""
        if self.autolearn_dictionary:
            for word in words:
                why = self.is_junk(word)
                if why:
                    _logger.info("rejecting word '%s': %s." % (word,why))
                else:
                    self.autolearn_dictionary.learn_word(word)

    def is_junk(self, word):
        """ find out if the word is worthy to be remembered """
        if len(word) < 2:
            return "Too short"

        if re.match(r"^[\d]", word, re.UNICODE):
            return "Must not start with a number"

        if not re.match(r"^([\w]|[-'])*$", word, re.UNICODE):
            return "Not all alphanumeric"

        if re.search(r"((.)\2{3,})", word, re.UNICODE):
            return "More than 3 repeated characters"

        return None

    def load_dictionaries(self, system_dict_files, user_dict_files, autolearn_dict_file):
        """ load dictionaries and blacklist """
        self.dictionaries = []

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


    def save_dictionaries(self):
        """ save modified dictionaries """
        for d in self.dictionaries:
            if d.modified:
                d.save()



class Dictionary:
    """
    On-disk format of a dictionary:
    word,frequency[,time]

    The time (of last use) column is optional and if missing, the whole
    column is assumed to be 0. Readonly system dictionaries come with two
    columns to save some disk space. User dictionaries always include the
    third column to allow prioritizing of recently used words.
    """

    def __init__(self, filename, _writable, transmap):
        self.filename = filename
        self.modified = False
        self.writable = _writable
        self.translation_map = transmap
        self.words = []
        self.freqs = []                # word frequencies
        self.times = []                # time (of last use)
        self.count = 0     # total number of words including duplicates

        self.load()

    def load(self):

        _logger.info("loading dictionary '%s'" % self.filename)

        # load dictionary as unicode
        fields = []
        try:
            s = codecs.open(self.filename, encoding='utf-8').read()
            nf = len(s[:s.find(u"\n")].split(u",")) # determine number of fields
            fields = s.replace(u",",u"\n").splitlines()
            del s
        except IOError, e:
            _logger.warning("Failed to load dictionary '%s': %s (%d)" %
                            (self.filename, os.strerror(e.errno), e.errno))

        # two flat lists are most memory efficient
        # with ~1000000 spanish words:
        # - Trie       - >600MB
        # - 2d-List    - ~170MB
        # - 2x 1d-List - ~100MB
        self.words = fields[0::nf]             # every nf element is a word
        self.freqs = [int(w) for w in fields[1::nf]] # frequenciess to ints
        if nf >= 3:
            self.times = [int(w) for w in fields[2::nf]]
        else:
            self.times = [0]*len(self.words)
        del fields

        # sort on load to sync with binary search
        # can't really store presorted dictionaries:
        # - system locale may change, possibly altering collation sequence
        # - translation map may change based on selected dictionaries
        ai = range(len(self.words))
        ai.sort(key=lambda i: self.words[i].translate(self.translation_map))
        self.words = [self.words  [i] for i in ai]
        self.freqs = [self.freqs[i] for i in ai]
        self.times = [self.times  [i] for i in ai]

        # precalculate attributes
        self.count = sum(self.freqs)  # sum of all word frequencies
        self.time  = max(self.times)  # max time of use, +1 = next new time

        #print self.words[:100]
        #print self.words


    def save(self):

        if self.modified or \
           not os.path.exists(self.filename):
            _logger.info("saving dictionary '%s'" % self.filename)

            words = self.words
            freqs = self.freqs
            times = self.times
            lines = ["%s,%d,%d\n" % (words[i], freqs[i], times[i])
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


    def find_completion_matches(self, _input, limit, frequency_time_ratio):
        words    = self.words
        freqs    = self.freqs
        times    = self.times
        transmap = self.translation_map

        prefix   = _input.translate(transmap)

        # binary search for the first match
        start = self.bisect_left(words, prefix, lambda x: x.translate(transmap))

        # collect all subsequent matches
        max_freq = 0
        i = start
        for i in xrange(start, len(words)):
            if not words[i].translate(transmap).startswith(prefix):
                break
            max_freq = max(freqs[i], max_freq)
        ai = range(start, i)

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

        # sort matches by time
        ai.sort(key=lambda i: times[i])

        # transform time into an array with one step per unique time value
        # [2,4,4,5,8,8,8] -> [0,1,1,2,3,3,3]
        time_weights = []
        last_time  = -1
        time_count = -1
        for i,j in enumerate(ai):
            if last_time != times[j]:
                last_time = times[j]
                time_count += 1
            time_weights.append(time_count)

        # Linearly interpolate between normalized word frequency
        # (word probability) and time_weight.
        # Frequency is normalized to the total number of words.
        # The transformed time is normalized to the maximum normalized
        # weight of the match set -> at a frequency_time_ratio of 50%, the
        # most frequent word and the most recent word have roughly equal
        # weights.
        freq_ratio  = float(100 - frequency_time_ratio) / 100.0
        time_ratio  = float(      frequency_time_ratio) / 100.0
        total_words = float(self.count)
        freq_fact   = freq_ratio * 1.0 / total_words \
                      if total_words else 0
        time_fact   = time_ratio * 1.0 / time_count * max_freq / total_words \
                      if total_words and time_count else 0

        weights = [freq_fact * freqs[j] + time_fact * time_weights[i] \
                                         for i,j in enumerate(ai)]
        # sort matches by weight
        a = zip(weights, ai)
        a.sort(reverse=True)

        # limit number of results and return as map {word:weight}
        m = [(words[x[1]], x[0]) for x in a[:limit]]
        #print m[:5]
        return dict(m)


    def learn_word(self, word):

        self.count += 1
        self.time  += 1         # time is an ever increasing integer
        self.modified = True

        # search for an exact match
        i = self.bisect_left(self.words, word, lambda x: x)
        if i < len(self.words) and self.words[i] == word:
            self.freqs[i] += 1
            self.times[i] = self.time
            _logger.info("strengthened word '%s' count %d time %d" % (word, self.freqs[i], self.times[i]))
        else:
            # Array insert...ugh, probably ok here though.
            # By the time the list grows big enough for inserts to become an
            # issue, new words will be increasingly rare. So for now stick
            # with a single data structure for both, potentially large, but
            # read-only system dictionaries and smaller, writable user
            # dictionaries.
            self.words.insert(i, word)
            self.freqs.insert(i, 1)
            self.times.insert(i, self.time)
            _logger.info("learned new word '%s' count %d time %d" % (word, 1, self.time))


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


