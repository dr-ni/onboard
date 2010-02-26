# -*- coding: latin-1 -*-

import sys
import os, errno
import codecs
import unicodedata
import re
from contextlib import contextmanager, closing
from traceback import print_exc
import dbus

### Logging ###
import logging
_logger = logging.getLogger("WordPredictor")
###############


class WordInfo:

    def __init__(self):
        self.reset()

    def reset(self):
        self.start = 0
        self.end   = 0
        self.word  = u""
        self.needs_update = True

        self.exact_match = False
        self.partial_match = False
        self.ignored = False

    def set_info(self, exact_match, partial_match, ignored):
        self.exact_match = exact_match
        self.partial_match = partial_match
        self.ignored = ignored
        self.needs_update = False

    def __str__(self):
        return  "'%s' %d-%d unknown=%s exact=%s partial=%s ignored=%s" % \
                 (self.word,self.start, self.end,
                 self.unknown, self.exact_match, \
                 self.partial_match, self.ignored)

class InputLine:

    all_words = re.compile(u"(?:[\w]|[-'])+", re.UNICODE)

    def __init__(self):
        self.reset()

    def reset(self):
        self.line = u""
        self.cursor = 0
        self.valid = True

        self.word_infos = {}
        self.labels = []
        self.label_count = 0

    def is_valid(self):
        return self.valid

    def is_empty(self):
        return len(self.line) == 0

    def insert(self, s):
        self.line   = self.line[:self.cursor] + s + self.line[self.cursor:]
        self.labels = self.labels[:self.cursor] + [0]*len(s) + self.labels[self.cursor:]
        self.move_cursor(len(s))

    def delete_left(self, n=1):  # backspace
        self.line = self.line[:self.cursor-n] + self.line[self.cursor:]
        self.labels = self.labels[:self.cursor-n] + self.labels[self.cursor:]
        self.move_cursor(-n)

    def delete_right(self, n=1): # delete
        self.line = self.line[:self.cursor] + self.line[self.cursor+n:]
        self.labels = self.labels[:self.cursor] + self.labels[self.cursor+n:]
        self.update_word_infos()

    def move_cursor(self, n):
        if n != 1: # going backwards or over larger stretches?
            wi = self.get_word_info_at_cursor()
            if wi:
                wi.needs_update = True  # force re-retrieval of word info

        self.cursor += n

        # moving into unknown territory -> suggest reset
        if self.cursor < 0:
            self.cursor = 0
            self.valid = False
        if self.cursor > len(self.line):
            self.cursor = len(self.line)
            self.valid = False

        self.update_word_infos()

    def get_context(self):
        return self.line[:self.cursor]

#    def get_all_words(self):
#        return self.all_words.findall(self.line)

#    def get_word_before_cursor(self):
#        return self.get_last_word(self.line[:self.cursor])

#    def get_last_word(self, s):
#        return re.search(u"([\w]|[-'])*$", s, re.UNICODE).group()

    def get_word_info_at_cursor(self):
        for wi in self.word_infos.values():
            if wi.start <= self.cursor and self.cursor <= wi.end:
                return wi
        return None

    def iter_outdated_word_infos(self):
        for wi in self.word_infos.values():
            if wi.needs_update:
                yield wi

    def get_word_infos(self):
        return sorted(self.word_infos.values(), key=lambda x: x.start)

    def update_word_infos(self):

        # mark words with unique labels
        # "abc def" -> [1,1,1,0,2,2,2]
        self._label_words()

        # associate labeled segments with WordInfo objects
        # [1,1,1,0,2,2,2] -> [wi(0,3,1),wi(4,7,2)]
        wis = {}
        for start, end, label in self._iter_labels():
            word = self.line[start:end]
            wi = self.word_infos.get(label)
            if not wi or wi.word != word:
                wi = WordInfo()
            wi.start, wi.end, wi.word = start, end, word
            wis[label] = wi
        self.word_infos = wis
        #print [x.known for x in self.word_infos.values()]


    def _label_words(self):
        used_labels = {}
        for match in self.all_words.finditer(self.line):
            label = None
            for i in xrange(match.start(), match.end()):
                if self.labels[i]:
                    label = self.labels[i]
                    break
            if not label or label in used_labels:
                self.label_count += 1
                label = self.label_count
            used_labels[label] = True
            for i in xrange(match.start(), match.end()):
                self.labels[i] = label

    def _iter_labels(self):
        # find label segments
        label = 0
        for i,l in enumerate(self.labels + [0]):
            if l:
                if label != l:
                    start = i
                    label = l
            elif label:
                yield start, i, label
                label = 0


    @staticmethod
    def is_printable(char):
        """
        True for printable keys including whitespace as defined for isprint().
        Word prediction uses this to filter for printable keys.
        """
        if char == u"\t":
            return True
        return not unicodedata.category(char) in ('Cc','Cf','Cs','Co',
                                                  'Cn','Zl','Zp')

    @staticmethod
    def is_junk(token):
        """ check if the word is worthy to be remembered """
        #if len(word) < 2:      # no, allow one letter words like 'a', 'I'
        #    return "Too short"

        if re.match(r"^[\d]", token, re.UNICODE):
            return "Must not start with a number"

        if not re.match(r"^([\w]|[-'])*$", token, re.UNICODE):
            return "Not all alphanumeric"

        if re.search(r"((.)\2{3,})", token, re.UNICODE):
            return "More than 3 repeated characters"

        return None


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
        self.prefix = u""
        self.suffix = u""

    def set_end_of_word(self, val=True):
        self.end_of_word = val;

    def build_prefix(self, char):
        """ return string to insert before sending keypress char """
        self.prefix = u""
        self.suffix = u""
        if self.space_added:  # did we previously add a trailing space?
            self.space_added = False

            if   char in u",:;":
                self.prefix = self.BACKSPACE
                self.suffix = " "

            elif char in u".?!":
                self.prefix = self.BACKSPACE
                self.suffix = " " + self.CAPITALIZE

        return self.prefix

    def build_suffix(self):
        """ add additional characters after the key press"""
        if self.end_of_word:
            self.space_added = True
            self.end_of_word = False
            return u" "
        else:
            return self.suffix


class WordPredictor:
    """ word completion and word prediction """

    def __init__(self):
        self.service = None
        self.dictionaries = []
        self.autolearn_dictionary = None
        self.frequency_time_ratio = 50  # 0=100% frequency, 100=100% time

        # possibly remove accents from international characters
        # e.g. åáéíóúäöü becomes aaeiouaou
        #self.translation_map = unaccent_map()  # simplifies spanish typing
        self.translation_map = identity_map()  # exact matches

    def predict(self, context_line, frequency_time_ratio = 0):
        """ runs the completion/prediction """

        choices = []
        for retry in range(2):
            with self.get_service() as service:
                if service:
                    choices = service.predict(["lm:system:en",
                                               "lm:user:en",
                                              ], context_line, 50)
                break

        return choices

    def learn_text(self, text, allow_new_words):
        """ add words to the auto-learn dictionary"""
        if self.autolearn_dictionary:
            for retry in range(2):
                with self.get_service() as service:
                    if service:
                        tokens = service.learn_text(["lm:user:en",
                                                    ], text, allow_new_words)
                break

    def tokenize_context(self, text):
        """ let the service find the words in text """
        for retry in range(2):
            with self.get_service() as service:
                if service:
                    tokens = service.tokenize_context(text)
            break
        return tokens

    def get_last_context_token(self, text):
        """ return the very last (partial) word in text """
        tokens = self.tokenize_context(text[-1024:])
        if len(tokens):
            return tokens[-1]
        else:
            return ""

    @contextmanager
    def get_service(self):
        try:
            if not self.service:
                bus = dbus.SessionBus()
                self.service = bus.get_object("org.gnome.PredictionService",
                                               "/WordPredictor")
        except dbus.DBusException:
            #print_exc()
            _logger.error("Failed to acquire D-Bus prediction service")
            self.service = None
            yield None
        else:
            try:
                yield self.service
            except dbus.DBusException:
                print_exc()
                _logger.error("D-Bus call failed. Retrying.")
                self.service = None

    def get_word_information(self, word):
        """
        Return information about dictionaries where the word is defined in.
        May add word weight, frequency, etc later as needed.
        Todo: change return value to something dbus friendly
        """
        info = []
        if word:
            for dic in reversed(self.dictionaries):
                if dic.lookup_word(word):
                    info.append({"name" : dic.name,
                                 "filename" : dic.filename,
                                 "writable" : dic.writable})
        return info


    def load_dictionaries(self, system_dict_files, user_dict_files, autolearn_dict_file):
        #return
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
        self.name = u""
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
        nf = 0
        fields = []
        try:
            with closing(codecs.open(self.filename, encoding='utf-8')) as f:
                s = f.read()
            nf = len(s[:s.find(u"\n")].split(u",")) # determine number of fields
            fields = s.replace(u",",u"\n").splitlines()
            del s
        except IOError, e:
            _logger.warning("Failed to load dictionary '%s': %s (%d)" %
                            (self.filename, os.strerror(e.errno), e.errno))
        if fields:
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


    def lookup_word(self, word):
        return self.lookup_word_index(word) >= 0

    def lookup_word_index(self, word):
        words    = self.words
        transmap = self.translation_map

        key   = word.translate(transmap)

        start = self.bisect_left(words, key, lambda x: x.translate(transmap))
        for i in xrange(start, len(words)):
            if words[i] == word:
                return i
        return -1

    def find_completion_matches(self, prefix, limit, frequency_time_ratio):
        words    = self.words
        freqs    = self.freqs
        times    = self.times
        transmap = self.translation_map

        prefix_tr  = prefix.translate(transmap)

        # binary search for the first match
        start = self.bisect_left(words, prefix_tr, lambda x: x.translate(transmap))

        # collect all subsequent matches
        max_freq = 0
        i = start
        for i in xrange(start, len(words)):
            if not words[i].translate(transmap).startswith(prefix_tr):
                break
            max_freq = max(freqs[i], max_freq)
        ai = range(start, i)

        # exhaustive search to verify results
        if 0:
            matches = [words[i] for i in ai]
            print u"'%s' %d matches: %s" % (prefix_tr, len(matches),
                                            str(matches[:5]))
            ai = [i for i in xrange(len(words)) \
                    if words[i].translate(transmap).startswith(prefix_tr)]
            matches = [words[i] for i in ai]
            print u"'%s' %d matches: %s" % (prefix_tr, len(matches),
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

        return dict(m)


    def learn_words(self, words):
        for word in words:
            self.learn_word(word)

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

                break
