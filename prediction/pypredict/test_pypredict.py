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

import unittest
from lm import *
from pypredict import *

class TestTokenization(unittest.TestCase):

    def __init__(self, test, text, result):
        unittest.TestCase.__init__(self, test)
        self.training_text = text
        self.result = result

    def test_tokenize_text(self):
        tokens, spans = tokenize_text(self.training_text)
        self.assertEqual(tokens, self.result,
                         "test '%s': '%s' != '%s'" %
                         (self.training_text, repr(tokens), repr(self.result)))

    def test_tokenize_context(self):
        tokens = tokenize_context(self.training_text)
        self.assertEqual(tokens, self.result,
                         "test '%s': '%s' != '%s'" %
                         (self.training_text, repr(tokens), repr(self.result)))

    def test_split_sentences(self):
        sentences, spans = split_sentences(self.training_text)
        self.assertEqual(sentences, self.result,
                         "test '%s': '%s' != '%s'" %
                         (self.training_text, repr(sentences), repr(self.result)))

class TestModel(unittest.TestCase):

    def __init__(self, test, order):
        unittest.TestCase.__init__(self, test)
        self.order = order

    def setUp(self):
        # text snippets from MOBY DICK By Herman Melville from Project Gutenberg
        self.training_text = u"""
            No, when I go to sea, I go as a simple sailor, right before the mast,
            plumb down into the forecastle, aloft there to the royal mast-head.
            True, they rather order me about some, and make me jump from spar to
            spar, like a grasshopper in a May meadow. And at first, this sort
            of thing is unpleasant enough. And more than all,
            if just previous to putting your hand into the tar-pot, you have been
            lording it as a country schoolmaster, making the tallest boys stand
            in awe of you. The transition is a keen one, I assure you, from a
            schoolmaster to a sailor, and requires a strong decoction of Seneca and
            the Stoics to enable you to grin and bear it. But even this wears off in
            time.
            """
        self.testing_text = u"""
            I now took the measure of the bench, and found that it was a foot too
            short; but that could be mended with a chair. I then placed the
            first bench lengthwise along the only clear space against the wall,
            leaving a little interval between, for my back to settle down in. But I
            soon found that there came such a draught of cold air over me from under
            the sill of the window, that this plan would never do at all, especially
            as another current from the rickety door met the one from the window,
            and both together formed a series of small whirlwinds in the immediate
            vicinity of the spot where I had thought to spend the night.
            """
        #self.training_text = u"Mary has a little lamb. Mary has a little lamb."
        #self.training_text = self.testing_text = u"a <s>"
        #self.training_text = self.testing_text = u"a b <s> c"
        #self.training_text = self.testing_text = u"a b c"
        self.training_tokens, _spans = tokenize_text(self.training_text)
        self.testing_tokens, _spans = tokenize_text(self.testing_text)
#        print
#        print self.training_tokens
#        model = DynamicModel(3)
#        model.smoothing = "kneser-ney"
#        model.learn_tokens(self.training_tokens)
#        for ng in model.iter_ngrams():
#            print ng
#        print model.predictp([u'a', u''], filter=False)
#        print self.model.predictp([u'a', u'b', u''], -1, False)

    def test_psum_dynamic_model_witten_bell(self):
        model = DynamicModel(self.order)
        model.smoothing = "witten-bell"
        model.learn_tokens(self.training_tokens)
        self.probability_sum(model)

    def test_psum_dynamic_model_absolute_discounting(self):
        model = DynamicModel(self.order)
        model.smoothing = "abs-disc"
        model.learn_tokens(self.training_tokens)
        self.probability_sum(model)

    def test_psum_dynamic_model_kneser_ney(self):
        model = DynamicModelKN(self.order)
        model.smoothing = "kneser-ney"
        model.learn_tokens(self.training_tokens)
        self.probability_sum(model)

    def test_psum_dynamic_model(self):
        model = CachedDynamicModel(self.order)
        model.smoothing = "abs-disc"
        model.learn_tokens(self.training_tokens)
        self.probability_sum(model)

    def test_psum_overlay_model(self): # this sums to 1.0 only for identical models
        model = DynamicModel(self.order)
        model.learn_tokens(self.training_tokens)
        self.probability_sum(overlay([model, model]))

    def test_psum_linint_model(self):
        model = DynamicModel(self.order)
        model.learn_tokens(self.training_tokens)
        self.probability_sum(linint([model, model]))

    def test_psum_loglinint_model(self):
        model = DynamicModel(self.order)
        model.learn_tokens(self.training_tokens)
        self.probability_sum(loglinint([model, model]))

    def probability_sum(self, model):
        # test sum of probabilities for multiple predictions
        num_tests = 0
        num_bad = 0
        num_with_zero = 0

        for i,t in enumerate(self.testing_tokens):
            context = self.testing_tokens[:i] + [u""]
            choices = model.predictp(context, filter=False, normalize=True)
            psum = sum(x[1] for x in choices)

            num_tests += 1
            eps = 1e-6

            if abs(1.0 - psum) > eps:
                num_bad += 1
                if num_bad == 1:
                    print
                print "order %d, pos %d: probabilities don't sum to 1.0; psum=%10f, #results=%6d, context='%s'" % \
                      (self.order, num_tests, psum, len(choices), repr(context[-4:]))

            zerocount = sum(1 for word,p in choices if p == 0)
            if zerocount:
                num_with_zero += 1
                print "order %d, pos %d: %d words with zero probability; psum=%10f, #results=%6d, context='%s'" % \
                      (self.order, num_tests, zerocount, psum, len(choices), repr(context[-4:]))

        self.assertEqual(num_tests, num_tests-num_bad,
                         "order %d, probabilities don't sum to 1.0 for %d of %d predictions" % \
                         (self.order, num_bad, num_tests))

        self.assertEqual(num_tests, num_tests-num_with_zero,
                         "order %d, zero probabilities in %d of %d predictions" % \
                         (self.order, num_with_zero, num_tests))



def test():

    # input-text, text-tokens, context-tokens, sentences
    tests = [
         ["", [], [], []],
         ["abc", [u"abc"], [u"abc"], [u"abc"]],
         #["-", [], [], [u"-"]],
         ["1", [u"<num>"], [u"<num>"], [u"1"]],
         [u"123", [u'<num>'], [u'<num>'], [u"123"]],
         ["-3", [u"<num>"], [u"<num>"], [u"-3"]],
         ["+4", [u"<num>"], [u"<num>"], [u"+4"]],
         ["123.456", [u"<num>"], [u"<num>"], [u"123.456"]],
         ["123,456", [u"<num>"], [u"<num>"], [u"123,456"]],
         ["100,000.00", [u"<num>"], [u"<num>"], [u"100,000.00"]],
         ["100.000,00", [u"<num>"], [u"<num>"], [u"100.000,00"]],
         [".5", [u"<num>"], [u"<num>"], [u".5"]],
         ["-option --option", ['-option', '--option'], ['-option', '--option'],
             ['-option --option']],
         [u"We saw wha", [u'We', u'saw', u'wha'], [u'We', u'saw', u'wha'],
             [u'We saw wha']],
         [u"We saw whales", [u'We', u'saw', u'whales'],
             [u'We', u'saw', u'whales'],
             [u'We saw whales']],
         [u"We saw whales ", [u'We', u'saw', u'whales'],
             [u'We', u'saw', u'whales', u''],
             [u'We saw whales']],
         [u"We  saw     whales", [u'We', u'saw', u'whales'],
             [u'We', u'saw', u'whales'],
             [u'We  saw     whales']],
         [u"Hello there! We saw whales ",
             [u'Hello', u'there', u'<s>', u'We', u'saw', u'whales'],
             [u'Hello', u'there', u'<s>', u'We', u'saw', u'whales', u''],
             [u'Hello there!', u'We saw whales']],
         [u"Hello there! We saw 5 whales ",
             [u'Hello', u'there', u'<s>', u'We', u'saw', u'<num>', u'whales'],
             [u'Hello', u'there', u'<s>', u'We', u'saw', u'<num>', u'whales', u''],
             [u'Hello there!', u'We saw 5 whales']],
         [u"Hello there! We #?/=$ saw 5 whales ",
             [u'Hello', u'there', u'<s>', u'We', u'saw', u'<num>', u'whales'],
             [u'Hello', u'there', u'<s>', u'We', u'saw', u'<num>', u'whales', u''],
             [u'Hello there!', u'We #?/=$ saw 5 whales']],
         [u".", [], [u''], [u'.']],
         [u". ", [u'<s>'], [u'<s>', u''], [u'.', u'']],
         [u". sentence.", [u'<s>', u'sentence'], [u'<s>', u'sentence', u''],
             [u'.', u'sentence.']],
         [u"sentence.", [u'sentence'], [u'sentence', u''], [u'sentence.']],
         [u"sentence. ", [u'sentence', u'<s>'], [u'sentence', u'<s>', u''],
             [u'sentence.', u'']],
         [u"sentence. sentence.", [u'sentence', u'<s>', u'sentence'],
             [u'sentence', u'<s>', u'sentence', u''],
             [u'sentence.', u'sentence.']],
         [u'sentence "quote." sentence.',
             [u'sentence', u'quote', u'<s>', u'sentence'],
             [u'sentence', u'quote', u'<s>', u'sentence', u''],
             [u'sentence "quote."', u'sentence.']],
         [u"sentence <s>", [u'sentence'], [u'sentence', u''], [u'sentence']],
         [u"<unk> <s> </s> <num>", [u'<unk>', u'<s>', u'</s>', u'<num>'],
             [u'<unk>', u'<s>', u'</s>', u'<num>', u''],
             [u'<unk>', u'</s> <num>']],
         [u""""double quotes" 'single quotes'""",
             [u'double', u'quotes', u'single', u"quotes'"],
             [u'double', u'quotes', u'single', u"quotes'"],
             [u'"double quotes" \'single quotes\'']],
         [u"(parens) [brackets] {braces}",
             [u'parens', u'brackets', u'braces'],
             [u'parens', u'brackets', u'braces', u''],
             [u'(parens) [brackets] {braces}']],
         [u"repeats: a aa aaa aaaa aaaaa",
             [u'repeats', u'<s>', u'a', u'aa', u'aaa', u'<unk>', u'<unk>'],
             [u'repeats', u'<s>', u'a', u'aa', u'aaa', u'<unk>', u'<unk>'],
             [u'repeats:', u'a aa aaa aaaa aaaaa']],
         [u"www", [u'www'], [u'www'], [u'www']],
         [u"www.", [u'www'], [u'www', u''], [u'www.']],
         [u"www,", [u'www'], [u'www', u''], [u'www,']],
         [u"www ", [u'www'], [u'www', u''], [u'www']],
         [u"\nnewline ", [u'newline'], [u'newline', u''], [u'newline']],
         [u"double\n\nnewline ", [u'double', u'<s>', u'newline'],
         [u'double', u'<s>', u'newline', u''], [u'double', u'newline']],
         [u"dash-dash", [u"dash-dash"], [u"dash-dash"], [u"dash-dash"]],
         [u"dash-", [u'dash-'], [u'dash-'], [u'dash-']],
         [u"single quote's", [u'single', u"quote's"], [u'single', u"quote's"],
             [u"single quote's"]],
         [u"single quote'", [u'single', u"quote'"], [u'single', u"quote'"],
             [u"single quote'"]],
         [u"under_score's", [u"under_score's"], [u"under_score's"],
             [u"under_score's"]],
         [u"= + - * / < > & ^",
             [u'=', u'+', u'-', u'*', u'/', u'<', u'>', u'&', u'^'],
             [u'=', u'+', u'-', u'*', u'/', u'<', u'>', u'&', u'^'],
             [u'= + - * / < > & ^']],
         [u"|", [u'|'], [u'|'], [u'|']],
         [u"== += -= *= /= != <= >= &= ^=",
             [u'==', u'+=', u'-=', u'*=', u'/=', u'!=', u'<=', u'>=', u'&=', u'^='],
             [u'==', u'+=', u'-=', u'*=', u'/=', u'!=', u'<=', u'>=', u'&=', u'^='],
             [u'== += -= *= /= != <= >= &= ^=']],
         [u"<", [u'<'], [u'<'], [u'<']],
         #[u"=== ==== =====", [], [], [u'=== ==== =====']],
         #[u"<<", [], [], [u'<<']],
         #[u"<<<", [], [], [u'<<<']],
        ]

    suites = []

    suite = unittest.TestSuite()
    test_methods = unittest.TestLoader().getTestCaseNames
    for i,a in enumerate(tests):
        suite.addTest(TestTokenization('test_tokenize_text', a[0], a[1]))
        suite.addTest(TestTokenization('test_tokenize_context', a[0], a[2]))
        suite.addTest(TestTokenization('test_split_sentences', a[0], a[3]))
    suites.append(suite)

    suite = unittest.TestSuite()
    test_methods = unittest.TestLoader().getTestCaseNames(TestModel)
    for order in range(2,5+1):
        for method in test_methods:
            suite.addTest(TestModel(method, order))
    suites.append(suite)

    #suite = unittest.TestLoader().loadTestsFromTestCase(TestModel)

    alltests = unittest.TestSuite(suites)
    unittest.TextTestRunner(verbosity=2).run(alltests)

    #print tokenize_text(u"psum = 0;")

if __name__ == '__main__':
    test()
