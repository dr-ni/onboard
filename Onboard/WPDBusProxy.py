import dbus
from contextlib import contextmanager, closing

import Onboard.pypredict as pypredict

import logging
_logger = logging.getLogger(__name__)


class WPDBusProxy:
    """ Low level word predictor, D-Bus glue code. """

    def __init__(self):
        self._proxy = None
        self.recency_ratio = 50  # 0=100% frequency, 100=100% time

    def set_models(self, system_models, user_models, auto_learn_models):

        # auto-learn language model must be part of the user models
        for model in auto_learn_models:
            if model not in user_models:
                auto_learn_models = None
                _logger.warning("No auto learn model selected. "
                                "Please setup learning first.")
                break

        self.models = system_models + user_models
        self.auto_learn_models = auto_learn_models

    def predict(self, context, case_insensitive = False,
                               accent_insensitive = False,
                               ignore_capitalized = False,
                               ignore_non_capitalized = False):
        """ Find completion/prediction choices. """
        LanguageModel = pypredict.LanguageModel
        options = 0
        if case_insensitive:
            options |= LanguageModel.CASE_INSENSITIVE
        if accent_insensitive:
            options |= LanguageModel.ACCENT_INSENSITIVE
        if ignore_capitalized:
            options |= LanguageModel.IGNORE_CAPITALIZED
        if ignore_non_capitalized:
            options |= LanguageModel.IGNORE_NON_CAPITALIZED

        return self._call_method("predict", [],
                                 self.models, context, 50, options)

        return choices

    def learn_text(self, text, allow_new_words):
        """ Count n-grams and add words to the auto-learn models. """
        if self.auto_learn_models:
            self._call_method("learn_text", None,
                              self.auto_learn_models, text, allow_new_words)

    def lookup_text(self, text):
        """
        Return WordInfo objects for each word in text
        """
        # split text into words and lookup each word
        # counts are 0 for no match, 1 for exact match or -n for partial matches
        tokens, counts = self._call_method("lookup_text", ([], []),
                                           self.models, text)
        return tokens, counts

    def tokenize_text(self, text):
        """
        Let the service find the words in text.
        """
        if 1:
            # avoid the D-Bus round-trip while we can
            tokens, spans = pypredict.tokenize_text(text)
        else:
            tokens, spans = self._call_method("tokenize_text", ([], []),
                                              text)
        return tokens, spans

    def tokenize_text_pythonic(self, text):
        """
        Let the service find the words in text.
        Return python types instead of dbus.Array/String/... .

        Doctests:
        # whitspace have to be respected in spans
        >>> p = WPService()
        >>> p.tokenize_text_pythonic("abc  def")
        (['abc', 'def'], [(0, 3), (5, 8)])
        """
        tokens, spans = self.tokenize_text(text)
        return( [unicode_str(t) for t in tokens],
                [(int(s[0]), int(s[1])) for s in spans] )

    def tokenize_context(self, text):
        """ let the service find the words in text """
        tokens = []
        if 1:
            # avoid the D-Bus round-trip while we can
            tokens = pypredict.tokenize_context(text)
        else:
            tokens = self._call_method("tokenize_context", [],
                                       text)
        return tokens

    def get_model_names(self, _class):
        """ Return the names of the available models. """
        names = self._call_method("get_model_names", [],
                                  _class)
        return [str(name) for name in names]

    def get_last_context_token(self, text):
        """ return the very last (partial) word in text """
        tokens = self.tokenize_context(text[-1024:])
        if len(tokens):
            return tokens[-1]
        else:
            return ""

    def _call_method(self, method, default_result, *args):
        """
        Call D-Bus method. Retry once in case the service
        isn't available right away.
        """
        result = default_result
        for retry in range(2):
            with self.get_service() as service:
                if service:
                    result = getattr(service, method)(*args)
            break
        return result

    @contextmanager
    def get_service(self):
        try:
            if not self._proxy:
                bus = dbus.SessionBus()
                self._proxy = bus.get_object("org.onboard.WordPrediction",
                                              "/WordPredictor")
        except dbus.DBusException:
            _logger.error("Failed to acquire D-Bus prediction service")
            self._proxy = None
            yield None
        else:
            try:
                yield self._proxy
            except dbus.DBusException:
                print_exc()
                _logger.error("D-Bus call failed. Retrying.")
                self._proxy = None


