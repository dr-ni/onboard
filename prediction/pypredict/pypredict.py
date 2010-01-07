#!/usr/bin/env python

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: marmuta <marmvta@gmail.com>
#

import re
import codecs
from math import log

import lm
from lm import overlay, linint, loglinint

class _BaseModel:
    pass

class DynamicModel(lm.DynamicModel, _BaseModel):

    def learn_tokens(self, tokens, allow_new_words=True):
        for i,token in enumerate(tokens):
            for n in xrange(self.order):
                if i+n+1 <= len(tokens):
                    assert(n == len(tokens[i:i+n+1])-1)
                    self.count_ngram(tokens[i:i+n+1], allow_new_words)

    def get_counts(self):
        counts = [0]*self.order
        totals = [0]*self.order
        for ng in self.iter_ngrams():
            counts[len(ng[0])-1] +=  1
            totals[len(ng[0])-1] += ng[1]
        return counts, totals


class CacheModel(lm.CacheModel, _BaseModel):

    def learn_tokens(self, tokens, allow_new_words):
        pass


def split_sentences(text):
    """ split text into sentences """

    filtered = text.replace("\r"," ") # remove carriage returns from Moby Dick

    # split into sentences
    # split at punctuation or double newline
    sentences = re.findall(""".*?(?:[\.;:!?](?=[\s\"])  # punctuation
                                  | \s*\\n\s*\\n)   # double newline
                              | .+$                 # last sentence fragment
                           """, filtered, re.UNICODE|re.DOTALL|re.VERBOSE)
    return sentences


def tokenize_text(text):
    """ Split text into word tokens.
        The result is ready for use in learn_tokens().

        Sentence begins, if detected, are marked with "<s>".
        Numbers are replaced with the number marker <num>.
        Other tokens that could confuse the prediction, etc are
        replaced with the unknown word marker "<unk>".

        Examples, text -> tokens:
            "We saw whales"  -> ["We", "saw", "whales"]
            "We saw whales " -> ["We", "saw", "whales"]
            "Hello there! We saw 5 whales "
                             -> ["Hello", "there", "<s>",
                                 "We", "saw", "<num>", "whales"]
    """

    tokens = []
    sentences = split_sentences(text)
    for i,sentence in enumerate(sentences):

        # split into words
        groups = re.findall(u"""
        ( 
          (?:^|(?<=\s))
            \S*(.)\\2{3,}\S*                        # char repeated more than 3 times
          (?=\s|$)
        ) |                      
        (
          (?:[-+]?\d+(?:[.,]\d+)*)            # anything numeric looking
          | (?:[.,]\d+)
        ) |
        (
          (?:[-]{0,2}                         # allow command line options
            [^\W\d]\w*(?:[-'][\w]+)*[-']?)    # word, not starting with a digit
          | <unk> | <s> | </s> | <num>        # pass through control words
          | (?:^|(?<=\s))
              (?:
                [\+\-\*/=\<>&\^]=? | =        # common space-delimited operators
              | !=                            # ! conflicts with sentence end
              | \|
              ) 
            (?=\s|$)
        )
        """, sentence, re.UNICODE|re.DOTALL|re.VERBOSE)

        t = []
        for group in groups:
            if group[0]:
                t.append(u"<unk>")
            elif group[2]:
                t.append(u"<num>")
            elif group[3]:
                t.append(group[3])

        # sentence begin?
        if i > 0:
            tokens.extend([u"<s>"] + t) # prepend sentence begin marker
        else:
            tokens.extend(t)

    return tokens


def tokenize_context(text):
    """ Split text into word tokens + prefix.
        The result is ready for use in predict().
    """
    tokens = tokenize_text(text)
    if not re.match(u"""
                  ^$                              # empty string
                | .*[-'\w]$                       # word at the end
                | (?:^|.*\s)[\+\-\*/=\<>&\^|]=?$  # operator, equal sign
                | .*(\S)\\1{3,}$                  # anything repeated > 3 times
                """, text, re.UNICODE|re.DOTALL|re.VERBOSE):
        tokens += [u""]
    return tokens


def read_corpus(filename, encoding='latin-1'):
    """ read corpus, alternative encoding e.g. 'utf-8' """
    return codecs.open(filename, encoding='latin-1').read()

def extract_vocabulary(tokens, min_count=1, max_words=0):
    m = {}
    for t in tokens:
        m[t] = m.get(t, 0) + 1
    items = [x for x in m.items() if x[1] >= min_count]
    items = sorted(items, key=lambda x: x[1], reverse=True)
    if max_words:
        return items[:max_words]
    else:
        return items[:max_words]

def filter_tokens(tokens, vocabulary):
    v = set(vocabulary)
    return [t if t in v else u"<unk>" for t in tokens]

def entropy(model, tokens, order=None):

    if not order:
        order = model.order  # fails for non-ngram models, specify order manually

    ngram_count = 0
    entropy = 0
    word_count = len(tokens)

    # extract n-grams of maximum length
    for i in xrange(len(tokens)):
        b = max(i-(order-1),0)
        e = min(i-(order-1)+order, len(tokens))
        ngram = tokens[b:e]
        if len(ngram) != 1:
            p = model.get_probability(ngram)
            if p == 0:
                print word_count, ngram,p
            e = log(p, 2) if p else float("infinity")
            entropy += e
            ngram_count += 1

    entropy = -entropy/word_count if word_count else 0
    try:
        perplexity = 2 ** entropy
    except:
        perplexity = 0

    return entropy, perplexity


# keystroke savings rate
def ksr(model, sentences, limit, progress=None):
    total_chars, pressed_keys = simulate_typing(model, sentences, limit, progress)
    saved_keystrokes = total_chars - pressed_keys
    return saved_keystrokes * 100.0 / total_chars if total_chars else 0

def simulate_typing(model, sentences, limit, progress=None):

    total_chars = 0
    pressed_keys = 0

    for i,sentence in enumerate(sentences):
        inputline = u""

        cursor = 0
        while cursor < len(sentence):
            context = tokenize_context(u". " + inputline) # simulate sentence begin
            prefix = context[len(context)-1] if context else ""
            prefix_to_end = sentence[len(inputline)-len(prefix):]
            target_word = re.search(u"^([\w]|[-'])*", prefix_to_end, re.UNICODE).group()
            choices = model.predict(context, limit)

            if 0:  # step mode for debugging
                print "cursor=%d total_chars=%d pressed_keys=%d" % (cursor, total_chars, pressed_keys)
                print "sentence= '%s'" % sentence
                print "inputline='%s'" % inputline
                print "prefix='%s'" % prefix
                print "prefix_to_end='%s'" % prefix_to_end
                print "target_word='%s'" % (target_word)
                print "context=", context
                print "choices=", choices
                raw_input()

            if target_word in choices:
                added_chars = len(target_word) - len(prefix)
                if added_chars == 0: # still right after insertion point?
                    added_chars = 1  # continue with next character
            else:
                added_chars = 1

            for k in range(added_chars):
                inputline += sentence[cursor]
                cursor += 1
                total_chars += 1

            pressed_keys += 1

        # progress feedback
        if progress:
            progress(i, len(sentences), total_chars, pressed_keys)

    return total_chars, pressed_keys


from contextlib import contextmanager

@contextmanager
def timeit(s):
    import sys, time, gc
    gc.collect()
    gc.collect()
    gc.collect()
    t = time.time()
    text = s if s else "timeit"
    sys.stdout.write(u"%-15s " % text)
    sys.stdout.flush()
    yield None
    sys.stdout.write(u"%10.3fms\n" % ((time.time() - t)*1000))




if __name__ == '__main__':
    import test_pypredict
    test_pypredict.test()

    a = [u".", u". ", u" . ", u"a. ", u"a. b"]
    for text in a:
        print "split_sentences('%s'): %s" % (text, repr(split_sentences(text)))

    for text in a:
        print "tokenize_text('%s'): %s" % (text, repr(tokenize_text(text)))

    for text in a:
        print "tokenize_context('%s'): %s" % (text, repr(tokenize_context(text)))
    
    print tokenize_text(u"psum = 0;")




