import gtk

class SnippetList(gtk.HBox):

    def __init__(self):
        gtk.HBox.__init__(self)

        self.number_box = gtk.VBox()
        self.pack_start(self.number_box)
        self.number_box.pack_start(gtk.Label("Number"))

        self.pack_start(gtk.VSeparator())

        self.snippet_box = gtk.VBox()
        self.pack_start(self.snippet_box)
        self.snippet_box.pack_start(gtk.Label("Snippet Text"))
        
        self.pack_start(gtk.VSeparator())

        self.delete_box = gtk.VBox()
        self.pack_end(self.delete_box)

if __name__=='__main__':
    window = gtk.Window()
    window.add(SnippetList())
    window.show_all()
    gtk.main()
