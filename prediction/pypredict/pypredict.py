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
import lm

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
    p = re.compile("""(?:[\.;:!?][\s\"])  # punctuation
                    | (?:\s*\\n\s*\\n)    # double newline
                   """,re.UNICODE|re.DOTALL|re.VERBOSE)
    sentences = p.split(filtered)
    sentences = re.split("""(?xus)(?:[\.;:!?][\s\"])  # punctuation
                                | (?:\s*\\n\s*\\n)    # double newline
                         """, filtered)


def tokenize_text(text):
    """ Split text into word tokens.
        The result is ready for use in learn_tokens().

        Sentence begins, if detected are marked with "<s>".
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

        # split into word
        groups = re.findall(u"""([^\W\d]\w*(?:[-'][\w]+)*[-']?) # word, not starting with a digit
                              | ((?:[-+]?\d+(?:[.,]\d+)*)|(?:[.,]\d+)) # number
                             """, sentence, re.UNICODE|re.DOTALL|re.VERBOSE)
        
        # replace unwanted tokens with <unk>
        t = []
        for group in groups:
            if group[1]:
                t.append(u"<num>")
            else:
                if group[0] and is_junk(group[0]):
                    t.append(u"<unk>")
                else:
                    t.append(group[0])

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
    if re.match(u".*[^-'\w]$", text, re.UNICODE|re.DOTALL):
        tokens += [u""]
    return tokens


def is_junk(token):
    """ check if the word is worthy to be remembered """
#    if len(word) < 2:      # no, allow one letter words like 'a', 'I'
#        return "Too short"

#    if re.match(r"^[\d]", token, re.UNICODE|re.DOTALL):
#        return "Must not start with a number"

#    if not re.match(r"^([\w]|[-'])*$", token, re.UNICODE|re.DOTALL):
#        return "Not all alphanumeric"

    if re.search(r"((.)\2{3,})", token, re.UNICODE|re.DOTALL):
        return "More than 3 repeated characters"

    return None


def read_corpus(filename, encoding='latin-1'):
    """ read corpus, alternative encoding e.g. 'utf-8' """
    return codecs.open(filename, encoding='latin-1').read()


from contextlib import contextmanager
import sys

@contextmanager
def timeit(s):
    import time, gc
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
    a = ["", "abc", "-", "1", "-3", "+4", "123.456", "123,456",
         "100,000.00", "100.000,00", ".5",
         u"We saw wha",
         u"We saw whales",
         u"We saw whales ",
         u"Hello there! We saw whales ",
         u"Hello there! We saw 5 whales ",
         u"Hello there! We #?/=$ saw 5 whales ",
         u".",
         u". ",
         u". sentence.",
         u"sentence.",
         u"sentence. ",
         u"sentence. sentence.",
         u""""double quotes" 'single quotes'""",
         u"(parens) [brackets] {braces}",
         u"repeats: a aa aaa aaaa aaaaa",
         u"www", u"123", u"www.",u"www,", u"www ",
         u"\nnewline ",
         u"dash-dash", u"dash-",
         u"single quote's", u"single quote'",
        ]

    for text in a:
        print "split_sentences('%s'): %s" % (text, repr(split_sentences(text)))

    for text in a:
        print "tokenize_text('%s'): %s" % (text, repr(tokenize_text(text)))

    for text in a:
        print "tokenize_context('%s'): %s" % (text, repr(tokenize_context(text)))

    print tokenize_text(u".")    
    print tokenize_text(u". ")    
    print tokenize_text(u" . ")
    print tokenize_text(u"a. ")
    print tokenize_text(u"a. b")
    
    
    
    
