#!/usr/bin/python
import gtk
import gconf
import gobject

from virtkey import virtkey

from Onboard.KeyboardSVG import KeyboardSVG
import Onboard.utils as utils

import shutil


from xml.parsers.expat import ExpatError
from xml.dom import minidom

import os
import os.path
import gettext

### Logging ###
import logging
_logger = logging.getLogger("Settings")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

from gettext import gettext as _
#setup gettext
app="onboard-settings"
gettext.textdomain(app)
gettext.bindtextdomain(app)
#gtk.glade.textdomain(app)
#gtk.glade.bindtextdomain(app)

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class Settings:
    def __init__(self,mainwin):
        _logger.debug("Entered in __init__")

        builder = gtk.Builder()
        builder.add_from_file(os.path.join(config.install_dir, "data", 
            "settings.ui"))

        self.window = builder.get_object("settings_window")

        self.layout_view = builder.get_object("layout_view")
        self.snippet_number_box = builder.get_object("snippet_number_box")
        self.snippet_text_box = builder.get_object("snippet_text_box")
        self.snippet_delete_box = builder.get_object("snippet_delete_box")

        self.gconfClient = gconf.client_get_default()


        self.layout_view.append_column(gtk.TreeViewColumn(None, gtk.CellRendererText(), markup = 0))


        self.user_layout_root = "%s/.sok/layouts/" % os.path.expanduser("~")
        if not os.path.exists(self.user_layout_root):
            os.makedirs(self.user_layout_root)


        self.update_layoutList()

        self.on_snippets_changed()#Populate the snippet list

        self.icon_toggle = builder.get_object("icon_toggle")
        self.icon_toggle.set_active(config.show_trayicon)
        config.show_trayicon_notify_add(self.icon_toggle.set_active)

        self.start_minimized_toggle = builder.get_object(
            "start_minimized_toggle")
        self.start_minimized_toggle.set_active(config.start_minimized)
        config.start_minimized_notify_add(
            self.start_minimized_toggle.set_active)

        self.icon_palette_toggle = builder.get_object("icon_palette_toggle")
        self.icon_palette_toggle.set_active(config.icp_in_use)
        config.icp_in_use_change_notify_add(
            self.icon_palette_toggle.set_active)

        builder.get_object("scanning_check").set_active(config.scanning)

        builder.get_object("interval_spin").set_value(
            config.scanning_interval/1000)

        self.window.show()

        self.window.set_keep_above(not mainwin)

        builder.connect_signals(self)

        _logger.info("Entering mainloop of onboard-settings")
        gtk.main()

    def on_snippets_changed(self):

        for child in self.snippet_number_box.get_children():
            if child.__class__ is gtk.Entry:
                self.snippet_number_box.remove(child)

        for child in self.snippet_text_box.get_children():
            if child.__class__ is gtk.Entry:
                self.snippet_text_box.remove(child)

        for child in self.snippet_delete_box.get_children():
            if child.__class__ is gtk.Button:
                self.snippet_delete_box.remove(child)

        self.snippet_indices = []
        for n in range(len(config.snippets)):
            snippet = config.snippets[n]
            if snippet:
                self.snippet_indices.append(n)

                numberEntry = gtk.Entry()
                numberEntry.set_text(str(n))
                numberEntry.connect("activate",self.cb_snippet_numberEntry_activate,n)
                numberEntry.set_size_request(5, 30)
                self.snippet_number_box.pack_start(numberEntry,False,False,5)
                numberEntry.show()

                textEntry = gtk.Entry()
                textEntry.set_text(snippet)
                textEntry.connect("activate",self.cb_snippet_textEntry_activate,n)
                textEntry.set_size_request(-1, 30)
                self.snippet_text_box.pack_start(textEntry,False,False,5)
                textEntry.show()

                deleteButton = gtk.Button(stock=gtk.STOCK_DELETE)
                deleteButton.connect("clicked",self.cb_snippet_deleteButton_clicked,n)
                self.snippet_delete_box.pack_start(deleteButton,False,False,5)
                deleteButton.show()


    def cb_snippet_numberEntry_activate(self,widget,currentNumber):

        newNo = int(widget.get_text())

        if not newNo in self.snippet_indices:
            li = self.gconfClient.get_list("/apps/onboard/snippets",gconf.VALUE_STRING)

            if newNo > (len(li) - 1):
                for n in range(len(li) - (newNo - 1)):
                    li.append("")
            text = li[currentNumber]

            li[currentNumber] = ""
            li[newNo] = text

            self.gconfClient.set_list("/apps/onboard/snippets",gconf.VALUE_STRING,li)

            self.on_snippets_changed()
        else:
            dialog = gtk.MessageDialog(self.window,type=gtk.MESSAGE_WARNING,buttons=gtk.BUTTONS_OK,message_format=_("Snippet already assigned to this number"))
            dialog.run()
            widget.set_text(str(currentNumber))
            dialog.destroy()



    def cb_snippet_textEntry_activate(self,widget,currentNumber):
        li = self.gconfClient.get_list("/apps/onboard/snippets",gconf.VALUE_STRING)

        li[currentNumber] = widget.get_text()

        self.gconfClient.set_list("/apps/onboard/snippets",gconf.VALUE_STRING,li)

        self.on_snippets_changed()




    def cb_snippet_deleteButton_clicked(self,widget,currentNumber):
        li = self.gconfClient.get_list("/apps/onboard/snippets",gconf.VALUE_STRING)

        li[currentNumber] = ""

        self.gconfClient.set_list("/apps/onboard/snippets",gconf.VALUE_STRING,li)

        self.on_snippets_changed()

    def on_icon_toggled(self,widget):
        config.show_trayicon = widget.get_active()

    def on_start_minimized_toggled(self,widget):
        config.start_minimized = widget.get_active()

    def on_icon_palette_toggled(self, widget):
        config.icp_in_use = widget.get_active()

    def open_user_layout_dir(self):
        if os.path.exists('/usr/bin/nautilus'):
            os.system(("nautilus --no-desktop %s" %self.user_layout_root))
        elif os.path.exists('/usr/bin/thunar'):
            os.system(("thunar %s" %self.user_layout_root))
        else:
            print _("No file manager to open layout folder")

    def on_layout_folder_button_clicked(self,widget):
        self.open_user_layout_dir()

    def on_personalise_button_clicked(self, widget):
        dialog = snippetDialog(self.window,
                            _("Enter name for personalised layout")) #recycling
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            text = dialog.snippetEntry.get_text()
            keyboard = KeyboardSVG(config.layout_filename)
            utils.create_layout_XML(text, virtkey(), keyboard)
            self.update_layoutList()
            self.open_user_layout_dir()

        dialog.destroy()

    def on_scanning_check_toggled(self, widget):
        config.scanning = widget.get_active()

    def on_interval_spin_value_changed(self, widget):
        config.scanning_interval = int(widget.get_value()*1000)

    def on_close_button_clicked(self, widget):
        self.window.destroy()
        gtk.main_quit()

    def update_layoutList(self):
        self.layoutList = gtk.ListStore(str,str)
        self.layout_view.set_model(self.layoutList)

        self.get_soks(os.path.join(config.install_dir, "layouts"))
        self.get_soks(self.user_layout_root)


    def cb_selected_layout_changed(self):
        self.get_soks(self.user_layout_root)

    def cb_snippetList_drag_drop(self, widget, event,thing1,thing2,thing3):
        gobject.idle_add(self.snippetList_changed)#To make sure gtk has finished changing the value of snippetList before updating gconf.

    def snippetList_changed(self, *args, **kargs):
        self.on_snippets_changed()

    def on_snippet_add_button_clicked(self, event):

        dialog = snippetDialog(self.window,_("Enter text for snippet"))

        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            text = dialog.snippetEntry.get_text()

            l = self.gconfClient.get_list("/apps/onboard/snippets",gconf.VALUE_STRING)

            if self.snippet_indices:
                if len(l) <= (self.snippet_indices[-1] +1):
                    l.append(text)
                else:
                    l[self.snippet_indices[-1] + 1] = text
            else:
                l.append(text)
            self.gconfClient.set_list("/apps/onboard/snippets",gconf.VALUE_STRING, l)

        dialog.destroy()

        self.on_snippets_changed()




    def on_add_button_clicked(self, event):#todo filtering
        chooser = gtk.FileChooserDialog(title=None,action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                      buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        filterer = gtk.FileFilter()
        filterer.add_pattern("*.sok")
        chooser.add_filter(filterer)
        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            filename = chooser.get_filename()


            f = open(filename)
            sokdoc = minidom.parse(f).documentElement
            for p in sokdoc.getElementsByTagName("pane"):
                fn = p.attributes['filename'].value

                shutil.copyfile("%s/%s" % (os.path.dirname(filename), fn), "%s%s" % (self.user_layout_root, fn))


            shutil.copyfile(filename,"%s%s" % (self.user_layout_root, os.path.basename(filename)))

            self.update_layoutList()
        chooser.destroy()


    def on_remove_button_clicked(self, event):
        filename = self.layoutList.get_value(self.layout_view.get_selection().get_selected()[1],1)

        f = open(filename)
        sokdoc = minidom.parse(f).documentElement
        f.close()

        os.remove(filename)

        for p in sokdoc.getElementsByTagName("pane"):
            os.remove("%s/%s" % (os.path.dirname(filename), p.attributes['filename'].value))#todo get sok to deal with not having a layout.
        config.layout_filename = ""
        self.update_layoutList()



    def get_soks(self, path):

        files = os.listdir(path)

        soks = []
        for f in files:
            if f[-4:] == ".sok":
                filename = "%s/%s" % (path,f)
                file_object = open(filename)
                try:
                    sokdoc = minidom.parse(file_object).documentElement

                    if os.access(filename,os.W_OK):
                        it = self.layoutList.append(("<i>%s</i>"
                            % sokdoc.attributes["id"].value, filename))
                    else:
                        it = self.layoutList.append((
                            sokdoc.attributes["id"].value, filename))

                    if filename == config.layout_filename:
                        self.layout_view.get_selection().select_iter(it)
                except ExpatError,(strerror):
                    print "XML in %s %s" % (filename, strerror)
                except KeyError,(strerror):
                    print "key %s required in %s" % (strerror,filename)

                file_object.close()

    def find_soks(self, path):
        files = os.listdir(path)
        soks = []
        for f in files:
            if f[-4:] == ".sok":
                soks.append(f)
        return soks

    def on_layout_view_released(self, widget, event):
        config.layout_filename = self.layoutList.get_value(
                widget.get_selection().get_selected()[1],1)

class snippetDialog(gtk.MessageDialog):
    def __init__(self,parent,message):
        gtk.MessageDialog.__init__(self,parent,gtk.MESSAGE_QUESTION)
        self.add_buttons(gtk.STOCK_OK,gtk.RESPONSE_OK,
                    gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.snippetEntry = gtk.Entry()
        self.snippetEntry.connect("activate", self.cb_snippetEntry_activated)
        self.vbox.pack_end(self.snippetEntry)
        self.set_markup(message)

    def cb_snippetEntry_activated(self, event):
        self.response(gtk.RESPONSE_OK)



if __name__=='__main__':
    s = Settings(True)
