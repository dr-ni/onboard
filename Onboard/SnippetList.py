import gobject
import gtk

class SnippetList(gtk.TreeView):

    def __init__(self):
        list_store = gtk.ListStore(gobject.TYPE_INT, gobject.TYPE_STRING)
        gtk.TreeView.__init__(self, list_store)
        self.set_headers_visible(True)
        list_store.set_sort_column_id(0, gtk.SORT_ASCENDING)

        number_renderer = gtk.CellRendererText()
        number_renderer.set_property("editable", True)
        number_renderer.connect("edited", self.on_number_edited)
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
        try:
            self.get_model()[path][0] = int(new_text)
        except ValueError:
            dialog = gtk.MessageDialog(parent=self.get_toplevel(),
                flags=gtk.DIALOG_MODAL,
                type=gtk.MESSAGE_ERROR,
                buttons=gtk.BUTTONS_OK,
                message_format="Must be an integer number")
            dialog.run()
            dialog.destroy()

    def on_text_edited(self, cell, path, new_text, user_data=None):
        self.get_model()[path][1] = new_text

    def add_after_selected(self, text):
        self.get_model().append((0, text))

    def remove_selected(self):
        pass

"""
def _on_remove_clicked(*args):
    snippet_list.remove_selected()

def _on_add_clicked(*args):
    snippet_list.add_after_selected("blah")

if __name__=='__main__':
    window = gtk.Window()
    vbox = gtk.VBox()
    window.add(vbox)
    snippet_list = SnippetList()
    vbox.pack_start(snippet_list)
    add_button = gtk.Button(stock=gtk.STOCK_ADD)
    add_button.connect("clicked", _on_add_clicked)
    vbox.pack_start(add_button)
    remove_button = gtk.Button(stock=gtk.STOCK_REMOVE)
    remove_button.connect("clicked", _on_remove_clicked)
    vbox.pack_start(remove_button)
    window.connect("delete-event", gtk.main_quit)
    window.show_all()
    gtk.main()
"""
