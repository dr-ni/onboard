
from gi.repository import GObject, Gtk

from gettext import gettext as _

from Onboard.utils import show_error_dialog

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

### Logging ###
import logging
_logger = logging.getLogger("SnippetList")
###############

DEFAULT_SNIPPET_LABEL = _("<Enter label>")
DEFAULT_SNIPPET_TEXT  = _("<Enter text>")

class TextRenderer(Gtk.CellRendererText):
    def get_data(s):
        return "abc"

class SnippetList(Gtk.TreeView):

    def __init__(self):
        Gtk.TreeView.__init__(self, model = SnippetStore())

        self.set_headers_visible(True)

        adj = Gtk.Adjustment(step_increment=1, upper=1000)
        number_renderer = Gtk.CellRendererSpin(editable=True, adjustment=adj)
        number_renderer.connect("edited", self.on_number_edited)
        number_column = Gtk.TreeViewColumn(title=_("Button Number"),
                                           cell_renderer=number_renderer,
                                           text=0)
        self.append_column(number_column)

        text_renderer = TextRenderer(editable=True)
        text_renderer.connect("edited", self.on_label_edited)
        text_column = Gtk.TreeViewColumn(title=_("Button Label"),
                                         cell_renderer=text_renderer,
                                         text=1)
        text_column.set_expand(True)
        text_column.set_cell_data_func(text_renderer, self.label_data_func)
        self.append_column(text_column)

        text_renderer = Gtk.CellRendererText(editable=True)
        text_renderer.connect("edited", self.on_text_edited)
        text_column = Gtk.TreeViewColumn(title=_("Snippet Text"),
                                         cell_renderer=text_renderer,
                                         text=2)
        text_column.set_expand(True)
        text_column.set_cell_data_func(text_renderer, self.text_data_func)
        self.append_column(text_column)

    def label_data_func(self, treeviewcolumn, cell_renderer, model, iter, data):
        value = model.get_value(iter, 1)
        if not value:
            value = DEFAULT_SNIPPET_LABEL
        cell_renderer.set_property('text', value)

    def text_data_func(self, treeviewcolumn, cell_renderer, model, iter, data):
        value = model.get_value(iter, 2)
        if not value:
            value = DEFAULT_SNIPPET_TEXT
        cell_renderer.set_property('text', value)

    def on_number_edited(self, cell, path, new_text, user_data=None):
        model = self.get_model()
        try:
            number = int(new_text)
        except ValueError:
            show_error_dialog(_("Must be an integer number"))
            return

        # Make sure number not taken
        iter = model.get_iter_first()
        while (iter):
            if number == model.get_value(iter, 0) \
                    and model.get_path(iter).to_string() != path:
                show_error_dialog(_("Snippet %d is already in use.") % number)
                return
            iter = model.iter_next(iter)

        model[path][0] = number

    def on_label_edited(self, cell, path, new_text, user_data=None):
        self.get_model()[path][1] = new_text

    def on_text_edited(self, cell, path, new_text, user_data=None):
        self.get_model()[path][2] = new_text

    def append(self, label, text):
        self.get_model().append(label, text)

    def remove_selected(self):
        (model, iter) = self.get_selection().get_selected()
        if iter:
            model.remove(iter)

class SnippetStore(Gtk.ListStore):
    def __init__(self):
        Gtk.ListStore.__init__(self, GObject.TYPE_INT, GObject.TYPE_STRING,
                                     GObject.TYPE_STRING)
        self.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        for number, (label, text) in sorted(config.snippets.items()):
            Gtk.ListStore.append(self, (number, label, text))

        config.snippet_notify_add(self._on_snippet_changed)

    def _on_snippet_changed(self, number):
        # Unset snippets don't exist anymore and have to be removed from
        # the list store.
        try:
            label, text = config.snippets[number]
        except (KeyError):
            label = None
            text = None

        _logger.info("Changing snippet %d to %s, %s" % (number, label, text))

        iter = self.get_iter_first()
        while (iter):
            if number == self.get_value(iter, 0):
                if not text is None:
                    self.set_value(iter, 1, label)
                    self.set_value(iter, 2, text)
                else:
                    # Remove snippet from store
                    _logger.info("Removing %d from snippet store" % (number))
                    Gtk.ListStore.remove(self, iter)
                return
            iter = self.iter_next(iter)

        # New snippet.
        if not text is None:
            Gtk.ListStore.append(self, (number, label, text))

    def append(self, label, text):
        # Find the largest button number
        number = -1
        iter = self.get_iter_first()
        while (iter):
            number = self.get_value(iter, 0)
            iter = self.iter_next(iter)
        config.set_snippet(number + 1, (label, text))

    def remove(self, iter):
        number = self.get_value(iter, 0)
        _logger.info("Deleting snippet %d" % number)
        config.del_snippet(number)

    def __getitem__(self, index):
        """
        Wraps the rows in a snippet object that causes changes to be reflected
        in the config singleton
        """
        snippet_as_list = Gtk.ListStore.__getitem__(self, index)
        return Snippet(snippet_as_list)

class Snippet:
    def __init__(self, snippet_as_list):
        self.snippet_as_list = snippet_as_list

    def _get_number(self):
        return self.snippet_as_list[0]
    def _set_number(self, value):
        _logger.info("changing snippet %d to %d" % (self.number, value))
        label, text = self.label, self.text
        config.del_snippet(self.number)
        self.snippet_as_list[0] = value
        config.set_snippet(self.number, (label, text))
    number = property(_get_number)

    def _get_label(self):
        return self.snippet_as_list[1]
    def _set_label(self, value):
        if value == DEFAULT_SNIPPET_LABEL:
            value = ""
        config.set_snippet(self.number, (value, self.text))
        self.snippet_as_list[1] = value
    label = property(_get_label)

    def _get_text(self):
        return self.snippet_as_list[2]
    def _set_text(self, value):
        if value == DEFAULT_SNIPPET_TEXT:
            value = ""
        config.set_snippet(self.number, (self.label, value))
        self.snippet_as_list[2] = value
    text = property(_get_text)

    def __getitem__(self, index):
        return self.snippet_as_list[index]

    def __setitem__(self, index, value):
        if index == 0:
            self._set_number(value)
        elif index == 1:
            self._set_label(value)
        elif index == 2:
            self._set_text(value)
        else:
            raise IndexError()

def _on_remove_clicked(*args):
    snippet_list.remove_selected()
    remove_button.set_sensitive(False)

def _on_add_clicked(*args):
    snippet_list.append("label", "text")

def _on_cursor_changed(*args):
    remove_button.set_sensitive(True)

if __name__=='__main__':
    window = Gtk.Window()
    box = Gtk.Box()
    window.add(box)
    snippet_list = SnippetList()
    snippet_list.connect("cursor-changed", _on_cursor_changed)
    box.add(snippet_list)
    add_button = Gtk.Button(stock=Gtk.STOCK_ADD)
    add_button.connect("clicked", _on_add_clicked)
    box.add(add_button)
    remove_button = Gtk.Button(stock=Gtk.STOCK_REMOVE)
    remove_button.set_sensitive(False)
    remove_button.connect("clicked", _on_remove_clicked)
    box.add(remove_button)
    window.connect("delete-event", Gtk.main_quit)
    window.show_all()
    Gtk.main()
