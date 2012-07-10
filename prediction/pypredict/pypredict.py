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
from __future__ import with_statement
import sys
import re
import codecs
from math import log

import lm
from lm import overlay, linint, loglinint

class _BaseModel:

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


class DynamicModel(lm.DynamicModel, _BaseModel):
    pass

class DynamicModelKN(lm.DynamicModelKN, _BaseModel):
    pass

class CachedDynamicModel(lm.CachedDynamicModel, _BaseModel):
    pass


def split_sentences(text, disambiguate=False):
    """ split text into sentences """

    filtered = text.replace("\r"," ") # remove carriage returns from Moby Dick

    # split into sentence fragments
    fragments = re.findall("""  .*?
                                  (?:
                                    [.;:!?](?:(?=[\s])|\") # punctuation
                                    | \s*\\n\s*\\n          # double newline
                                    | <s>                   # sentence end mark
                                  )
                              | .+$                    # last sentence fragment
                           """, filtered, re.UNICODE|re.DOTALL|re.VERBOSE)

    # filter fragments
    sentences = []
    for fragment in fragments:
        # not only newlines? remove fragments with only double newlines
        if not re.match(u"^\s*\n+\s*$", fragment, re.UNICODE):

            # remove <s>
            sentence = re.sub(u"<s>", u"", fragment)

            # remove newlines and double spaces
            sentence = re.sub(u"\s+", u" ", sentence)

            sentence = sentence.strip()

            # add <s> sentence separators if the end of the sentence is
            # ambiguous - required by the split_corpus tool where the
            # result of split_sentences is saved to a text file and later
            # fed back to split_sentences again.
            if disambiguate:
                if not re.search(u"[.;:!?]\"?$", sentence, re.UNICODE):
                    sentence += u" <s>"

            sentences.append(sentence)

    return sentences


def tokenize_sentence(sentence):

    iterator = re.finditer(u"""
    (                                     # <unk>
      (?:^|(?<=\s))
        \S*(.)\\2{3,}\S*                  # char repeated more than 3 times
      (?=\s|$)
    ) |
    (                                     # <num>
      (?:[-+]?\d+(?:[.,]\d+)*)            # anything numeric looking
      | (?:[.,]\d+)
    ) |
    (                                     # word
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

    tokens = []
    spans = []

    for match in iterator:
        groups = match.groups()
        if groups[3]:
            tokens.append(groups[3])
            spans.append(match.span())
        elif groups[2]:
            tokens.append(u"<num>")
            spans.append(match.span())
        elif groups[0]:
            tokens.append(u"<unk>")
            spans.append(match.span())

    return tokens, spans

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

        t, spans = tokenize_sentence(sentence)

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


def read_corpus(filename, encoding=None):
    """ read corpus, encoding may be 'utf-8', 'latin-1', etc. """

    if encoding:
        encodings = [encoding]
    else:
        encodings = ['utf-8', 'latin-1']

    for i,enc in enumerate(encodings):
        try:
            text = codecs.open(filename, encoding=enc).read()
        except UnicodeDecodeError,err:
            #print err
            if i == len(encodings)-1: # all encodings failed?
                raise err
            continue   # silently retry with the next encoding
        break

    return text

def read_vocabulary(filename, encoding=None):
    """
    read vocabulary, encoding may be 'utf-8', 'latin-1', etc.
    expects one word per line.
    """
    text = read_corpus(filename, encoding)
    return text.split("\n")

def extract_vocabulary(tokens, min_count=1, max_words=0):
    m = {}
    for t in tokens:
        m[t] = m.get(t, 0) + 1
    items = [x for x in m.items() if x[1] >= min_count]
    items = sorted(items, key=lambda x: x[1], reverse=True)
    if max_words:
        return items[:max_words]
    else:
        return items

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
def ksr(query_model, learn_model, sentences, limit, progress=None):
    total_chars, pressed_keys = simulate_typing(query_model, learn_model, sentences, limit, progress)
    saved_keystrokes = total_chars - pressed_keys
    return saved_keystrokes * 100.0 / total_chars if total_chars else 0

def simulate_typing(query_model, learn_model, sentences, limit, progress=None):

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
            choices = query_model.predict(context, limit)

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

        # learn the sentence
        if learn_model:
            tokens = tokenize_context(sentence)
            learn_model.learn_tokens(tokens)

        # progress feedback
        if progress:
            progress(i, len(sentences), total_chars, pressed_keys)

    return total_chars, pressed_keys


from contextlib import contextmanager

@contextmanager
def timeit(s, out=sys.stdout):
    import time, gc

    if out:
        gc.collect()
        gc.collect()
        gc.collect()

        t = time.time()
        text = s if s else "timeit"
        out.write(u"%-15s " % text)
        out.flush()
        yield None
        out.write(u"%10.3fms\n" % ((time.time() - t)*1000))
    else:
        yield None




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


