import gobject
import gtk

from Onboard.utils import show_error_dialog

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

### Logging ###
import logging
_logger = logging.getLogger("SnippetList")
###############


class SnippetList(gtk.TreeView):

    def __init__(self):
        snippet_store = SnippetStore()
        gtk.TreeView.__init__(self, snippet_store)
        self.set_headers_visible(True)

        number_renderer = gtk.CellRendererSpin()
        number_renderer.set_property("editable", True)
        number_renderer.connect("edited", self.on_number_edited)
        number_renderer.set_property("adjustment",
            gtk.Adjustment(step_incr = 1, upper = 1000))
        number_column = gtk.TreeViewColumn("Button Number", number_renderer)
        number_column.set_attributes(number_renderer, text=0)
        self.append_column(number_column)

        text_renderer = gtk.CellRendererText()
        text_renderer.set_property("editable", True)
        text_renderer.connect("edited", self.on_text_edited)
        text_column = gtk.TreeViewColumn("Snippet Text", text_renderer)
        text_column.set_attributes(text_renderer, text=1)
        text_column.set_expand(True)
        self.append_column(text_column)

    def on_number_edited(self, cell, path, new_text, user_data=None):
        model = self.get_model()
        try:
            number = int(new_text)
        except ValueError:
            show_error_dialog("Must be an integer number")
            return

        # Make sure number not taken
        iter = model.get_iter_first()
        while (iter):
            if number == model.get_value(iter, 0) \
                    and model.get_path(iter)[0] != int(path):
                show_error_dialog("Snippet assigned to button %d" % number)
                return
            iter = model.iter_next(iter)

        model[path][0] = number

    def on_text_edited(self, cell, path, new_text, user_data=None):
        self.get_model()[path][1] = new_text

    def append(self, text):
        self.get_model().append(text)

    def remove_selected(self):
        (model, iter) = self.get_selection().get_selected()
        if iter:
            model.remove(iter)

class SnippetStore(gtk.ListStore):
    def __init__(self):
        gtk.ListStore.__init__(self, gobject.TYPE_INT, gobject.TYPE_STRING)
        self.set_sort_column_id(0, gtk.SORT_ASCENDING)

        for index in range(len(config.snippets)):
            text = config.snippets[index]
            if text:
                gtk.ListStore.append(self, (index, text))

        config.snippet_notify_add(self._on_snippet_changed)

    def _on_snippet_changed(self, number):
        # Unset snippets can either not exist or be zero length string as gconf
        # doesn't allow null elements of lists.
        try:
            text = config.snippets[number]
        except (IndexError):
            text = ""

        _logger.info("Changing snippet %d to %s" % (number, text))

        iter = self.get_iter_first()
        while (iter):
            if number == self.get_value(iter, 0):
                if text != "":
                    self.set_value(iter, 1, text)
                else:
                    # Remove snippet from store
                    _logger.info("Removing %d from snippet store" % (number))
                    gtk.ListStore.remove(self, iter)
                return
            iter = self.iter_next(iter)

        # New snippet.
        if text:
            gtk.ListStore.append(self, (number, text))

    def append(self, text):
        # Find the largest button number
        number = -1
        iter = self.get_iter_first()
        while (iter):
            number = self.get_value(iter, 0)
            iter = self.iter_next(iter)
        config.set_snippet(number + 1, text)

    def remove(self, iter):
        number = self.get_value(iter, 0)
        text   = self.get_value(iter, 1)
        _logger.info("Deleting snippet %d" % number)
        config.del_snippet(number)

    def __getitem__(self, index):
        """
        Wraps the rows in a snippet object that causes changes to be reflected
        in the config singleton
        """
        snippet_as_list = gtk.ListStore.__getitem__(self, index)
        return Snippet(snippet_as_list)

class Snippet:
    def __init__(self, snippet_as_list):
        self.snippet_as_list = snippet_as_list

    def _get_number(self):
        return self.snippet_as_list[0]
    def _set_number(self, value):
        _logger.info("changing snippet %d to %d" % (self.number, value))
        config.del_snippet(self.number)
        self.snippet_as_list[0] = value
        config.set_snippet(self.number, self.text)
    number = property(_get_number)

    def _get_text(self):
        return self.snippet_as_list[1]
    def _set_text(self, value):
        config.set_snippet(self.number, value)
        self.snippet_as_list[1] = value
    text = property(_get_text)

    def __getitem__(self, index):
        return self.snippet_as_list[index]

    def __setitem__(self, index, value):
        if index == 0:
            self._set_number(value)
        elif index == 1:
            self._set_text(value)
        else:
            raise IndexError()

def _on_remove_clicked(*args):
    snippet_list.remove_selected()
    remove_button.set_sensitive(False)

def _on_add_clicked(*args):
    snippet_list.append("blah")

def _on_cursor_changed(*args):
    remove_button.set_sensitive(True)

if __name__=='__main__':
    window = gtk.Window()
    vbox = gtk.VBox()
    window.add(vbox)
    snippet_list = SnippetList()
    snippet_list.connect("cursor-changed", _on_cursor_changed)
    vbox.pack_start(snippet_list)
    add_button = gtk.Button(stock=gtk.STOCK_ADD)
    add_button.connect("clicked", _on_add_clicked)
    vbox.pack_start(add_button)
    remove_button = gtk.Button(stock=gtk.STOCK_REMOVE)
    remove_button.set_sensitive(False)
    remove_button.connect("clicked", _on_remove_clicked)
    vbox.pack_start(remove_button)
    window.connect("delete-event", gtk.main_quit)
    window.show_all()
    gtk.main()
