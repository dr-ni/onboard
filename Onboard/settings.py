#!/usr/bin/python
import gtk
import gobject

from virtkey import virtkey

from Onboard.KeyboardSVG import KeyboardSVG
from Onboard.SnippetList import SnippetList
from Onboard.utils       import show_ask_string_dialog

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
app="onboard"
gettext.textdomain(app)
gettext.bindtextdomain(app)

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class Settings:
    def __init__(self,mainwin):

        # Do not run if running under GDM
        if os.environ.has_key('RUNNING_UNDER_GDM'):
            return

        builder = gtk.Builder()
        builder.add_from_file(os.path.join(config.install_dir, \
            "settings.ui"))

        self.window = builder.get_object("settings_window")

        self.layout_view = builder.get_object("layout_view")

        self.layout_view.append_column(gtk.TreeViewColumn(None, gtk.CellRendererText(), markup = 0))


        self.user_layout_root = "%s/.sok/layouts/" % os.path.expanduser("~")
        if not os.path.exists(self.user_layout_root):
            os.makedirs(self.user_layout_root)

        self.update_layoutList()

        self.status_icon_toggle = builder.get_object("status_icon_toggle")
        self.status_icon_toggle.set_active(config.show_status_icon)
        config.show_status_icon_notify_add(self.status_icon_toggle.set_active)

        self.start_minimized_toggle = builder.get_object(
            "start_minimized_toggle")
        self.start_minimized_toggle.set_active(config.start_minimized)
        config.start_minimized_notify_add(
            self.start_minimized_toggle.set_active)

        self.icon_palette_toggle = builder.get_object("icon_palette_toggle")
        self.icon_palette_toggle.set_active(config.icp_in_use)
        config.icp_in_use_change_notify_add(
            self.icon_palette_toggle.set_active)

        self.modeless_gksu_toggle = builder.get_object("modeless_gksu_toggle")
        self.modeless_gksu_toggle.set_active(config.modeless_gksu)
        config.modeless_gksu_notify_add(self.modeless_gksu_toggle.set_active)

        self.onboard_xembed_toggle = builder.get_object("onboard_xembed_toggle")
        self.onboard_xembed_toggle.set_active(config.onboard_xembed_enabled)
        config.onboard_xembed_notify_add(self.onboard_xembed_toggle.set_active)

        # Snippets
        self.snippet_list = SnippetList()
        builder.get_object("snippet_scrolled_window").add(self.snippet_list)

        # Scanning
        builder.get_object("scanning_check").set_active(config.scanning)

        builder.get_object("interval_spin").set_value(
            config.scanning_interval/1000)

        self.window.show_all()

        self.window.set_keep_above(not mainwin)

        self.window.connect("destroy", gtk.main_quit)
        builder.connect_signals(self)

        _logger.info("Entering mainloop of onboard-settings")
        gtk.main()

    def on_snippet_add_button_clicked(self, event):
        _logger.info("Snippet add button clicked")
        snippet_text = show_ask_string_dialog(_("Enter text for snippet"))
        if snippet_text != None: self.snippet_list.append(snippet_text)

    def on_snippet_remove_button_clicked(self, event):
        _logger.info("Snippet remove button clicked")
        self.snippet_list.remove_selected()

    def on_status_icon_toggled(self,widget):
        config.show_status_icon = widget.get_active()

    def on_start_minimized_toggled(self,widget):
        config.start_minimized = widget.get_active()

    def on_icon_palette_toggled(self, widget):
        config.icp_in_use = widget.get_active()

    def on_modeless_gksu_toggled(self, widget):
        config.modeless_gksu = widget.get_active()

    def on_xembed_onboard_toggled(self, widget):
        if widget.get_active(): # the user has enabled the option
                config.onboard_xembed_enabled = True
                config.gss_xembed_enabled = True
                config.set_xembed_command_string_to_onboard()
        else:
            config.onboard_xembed_enabled = False
            config.gss_xembed_enabled = False


    def open_user_layout_dir(self):
        if os.path.exists('/usr/bin/nautilus'):
            os.system(("nautilus --no-desktop %s" %self.user_layout_root))
        elif os.path.exists('/usr/bin/thunar'):
            os.system(("thunar %s" %self.user_layout_root))
        else:
            print _("No file manager to open layout folder")

    def on_layout_folder_button_clicked(self, widget):
        self.open_user_layout_dir()

    def on_personalise_button_clicked(self, widget):
        new_layout_name = show_ask_string_dialog(
            _("Enter name for personalised layout"))
        if new_layout_name:
            keyboard = KeyboardSVG(config.layout_filename)
            layout_xml = utils.create_layout_XML(new_layout_name,
                                                 virtkey(),
                                                 keyboard)
            utils.save_layout_XML(layout_xml, self.user_layout_root)
            self.update_layoutList()
            self.open_user_layout_dir()

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

        self.update_layouts(os.path.join(config.install_dir, "layouts"))
        self.update_layouts(self.user_layout_root)

    def cb_selected_layout_changed(self):
        self.update_layouts(self.user_layout_root)

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



    def update_layouts(self, path):

        filenames = self.find_layouts(path)

        layouts = []
        for filename in filenames:
            file_object = open(filename)
            try:
                sokdoc = minidom.parse(file_object).documentElement

                value = sokdoc.attributes["id"].value
                if os.access(filename, os.W_OK):
                    layouts.append((value.lower(),
                                   "<i>{0}</i>".format(value),
                                   filename))
                else:
                    layouts.append((value.lower(), value, filename))

            except ExpatError,(strerror):
                print "XML in %s %s" % (filename, strerror)
            except KeyError,(strerror):
                print "key %s required in %s" % (strerror,filename)

            file_object.close()

        for key, value, filename in sorted(layouts):
            it = self.layoutList.append((value, filename))
            if filename == config.layout_filename:
                self.layout_view.get_selection().select_iter(it)

    @staticmethod
    def find_layouts(path):
        files = os.listdir(path)
        layouts = []
        for filename in files:
            if filename.endswith(".sok") or filename.endswith(".onboard"):
                layouts.append(os.path.join(path, filename))
        return layouts

    def on_layout_view_released(self, widget, event):
        config.layout_filename = self.layoutList.get_value(
                widget.get_selection().get_selected()[1],1)


if __name__=='__main__':
    s = Settings(True)
