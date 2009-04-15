import gobject
import gtk

from Onboard.utils import show_error_dialog

class SnippetList(gtk.TreeView):

    def __init__(self):
        list_store = gtk.ListStore(gobject.TYPE_INT, gobject.TYPE_STRING)
        gtk.TreeView.__init__(self, list_store)
        self.set_headers_visible(True)
        list_store.set_sort_column_id(0, gtk.SORT_ASCENDING)

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
        model = self.get_model()
        iter = model.get_iter_first()
        
        # Find the largest button number
        number = -1
        while (iter):
            number = model.get_value(iter, 0)
            iter = model.iter_next(iter)

        self.get_model().append((number + 1, text))

    def remove_selected(self):
        (model, iter) = self.get_selection().get_selected()
        if iter:
            model.remove(iter)

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
