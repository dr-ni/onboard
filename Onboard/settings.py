#!/usr/bin/python
import gtk
import gobject

from virtkey import virtkey

from Onboard             import Exceptions
from Onboard.KeyboardSVG import KeyboardSVG
from Onboard.SnippetList import SnippetList
from Onboard.utils       import show_ask_string_dialog, show_confirmation_dialog
from Onboard.Appearance  import Theme, ColorScheme

import Onboard.utils as utils

import shutil

from xml.parsers.expat import ExpatError
from xml.dom import minidom

import os
import os.path
import gettext
import copy

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

def LoadUI(filebase):
    builder = gtk.Builder()
    builder.add_from_file(os.path.join(config.install_dir, filebase+".ui"))
    return builder

def format_list_item(text, issystem):
    if issystem:
        return "<i>{0}</i>".format(text)
    return text

    
class Settings:
    def __init__(self,mainwin):

        self.themes = {}       # cache of theme objects

        # Do not run if running under GDM
        if os.environ.has_key('RUNNING_UNDER_GDM'):
            return
            
        builder = LoadUI("settings")
        self.window = builder.get_object("settings_window")

        # init layout view
        self.layout_view = builder.get_object("layout_view")
        self.layout_view.append_column(gtk.TreeViewColumn(None, gtk.CellRendererText(), markup = 0))

        self.user_layout_root = "%s/.sok/layouts/" % os.path.expanduser("~")
        if not os.path.exists(self.user_layout_root):
            os.makedirs(self.user_layout_root)

        self.update_layoutList()

        # init theme view
        self.theme_view = builder.get_object("theme_view")
        self.theme_view.append_column(
                  gtk.TreeViewColumn(None, gtk.CellRendererText(), markup = 0))
        self.delete_theme_button = builder.get_object("delete_theme_button")
        self.customize_theme_button = \
                                   builder.get_object("customize_theme_button")

        user_theme_root = Theme.user_path()
        if not os.path.exists(user_theme_root):
            os.makedirs(user_theme_root)

        self.update_themeList()


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
            vk = virtkey()
            keyboard = KeyboardSVG(vk, config.layout_filename)
            layout_xml = utils.create_layout_XML(new_layout_name,
                                                 vk,
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

    def find_layouts(self, path):
        files = os.listdir(path)
        layouts = []
        for filename in files:
            if filename.endswith(".sok") or filename.endswith(".onboard"):
                layouts.append(os.path.join(path, filename))
        return layouts

    def on_layout_view_cursor_changed(self, widget):
        it = self.layout_view.get_selection().get_selected()[1]
        if it:
            config.layout_filename = self.layoutList.get_value(it,1)


    def on_new_theme_button_clicked(self, event):        
        while True:
            new_name = show_ask_string_dialog(
                _("Please enter a name for the new theme"), self.window)
            if not new_name:
                return

            new_filename = Theme.build_user_filename(new_name)
            if not os.path.exists(new_filename):
                break

            question = _("The theme file already exists.\n'%s'"
                         "\n\nOverwrite it anyway?" % new_filename)
            if show_confirmation_dialog(question, self.window):
                break
                
        theme = self.get_selected_theme()
        if not theme:
            theme = Theme()
        theme.save_as(new_name, new_name)
        config.theme_filename = theme.filename
        self.update_themeList()
                                                       
    def on_delete_theme_button_clicked(self, event):
        theme = self.get_selected_theme()
        if theme and not theme.system:
            if self.get_hidden_theme(theme):
                question = _("Reset current theme"
                             " to its default values?")
            else:
                question = _("Delete the current theme file?")
            reply = show_confirmation_dialog(question, self.window)
            if reply == True:
                # be sure the file hasn't been deleted from outside already
                if os.path.exists(theme.filename):
                    os.remove(theme.filename)

                # find a neighboring theme to select after deletion
                if not self.get_hidden_theme(theme): # would the row disappear?
                    near_theme = self.find_neighbor_theme(theme)
                    config.theme_filename = near_theme.filename \
                                            if near_theme else ""

                self.update_themeList()

    def find_neighbor_theme(self, theme):
        themes = self.get_sorted_themes()
        for i,tpl in enumerate(themes):
            if theme.basename == tpl[0].basename:
                if i < len(themes)-1:
                    return themes[i+1][0]
                else:
                    return themes[i-1][0]
        return None

    def on_customize_theme_button_clicked(self, event):
        self.customize_theme()

    def on_theme_view_row_activated(self, treeview, path, view_column):
        self.customize_theme()
        
    def on_theme_view_cursor_changed(self, widget):
        theme = self.get_selected_theme()
        if theme:
            theme.apply()
            config.theme_filename = theme.filename
        self.update_theme_buttons()
        
    def get_sorted_themes(self):
        #return sorted(self.themes.values(), key=lambda x: x[0].name)
        system = [x for x in self.themes.values() if x[0].system or x[1]]
        user = [x for x in self.themes.values() if not (x[0].system or x[1])]
        return sorted(system, key=lambda x: x[0].name.lower()) + \
               sorted(user, key=lambda x: x[0].name.lower())

    def find_theme_index(self, theme):
        themes = self.get_sorted_themes()
        for i,tpl in enumerate(themes):
            if theme.basename == tpl[0].basename:
                return i
        return -1

    def customize_theme(self):
        theme = self.get_selected_theme()
        if theme:
            system_theme = self.themes[theme.basename][1]            

            dialog = ThemeDialog(self, theme)
            modified_theme = dialog.run()
            
            #print str(theme)
            #print str(modified_theme)
            #print str(system_theme)
            
            if modified_theme == system_theme:
                # same as the system theme, so delete the user theme
                _logger.info("Deleting theme '%s'" % theme.filename)
                if os.path.exists(theme.filename):
                    os.remove(theme.filename)

            elif not modified_theme == theme: 
                # save as user theme
                modified_theme.save_as(theme.basename, theme.name)
                _logger.info("Saved theme '%s'" % theme.filename)

        self.update_themeList()
            
    def update_themeList(self):
        self.themeList = gtk.ListStore(str,str)
        self.theme_view.set_model(self.themeList)

        self.themes = Theme.load_merged_themes()

        theme_basename = \
               os.path.splitext(os.path.basename(config.theme_filename))[0]
        it_selection = None
        for theme,hidden_theme in self.get_sorted_themes():
            it = self.themeList.append((
                         format_list_item(theme.name, theme.system), 
                         theme.filename))
            if theme.basename == theme_basename:
                self.theme_view.get_selection().select_iter(it)
                it_selection = it

        # scroll to selection
        path = self.themeList.get_path(it_selection)
        self.theme_view.scroll_to_cell(path)
        
        self.update_theme_buttons()

    def update_theme_buttons(self):
        theme = self.get_selected_theme()

        if self.get_hidden_theme(theme):
            self.delete_theme_button.set_label(_("Reset"))
        else:
            self.delete_theme_button.set_label(_("Delete"))

        self.delete_theme_button.set_sensitive(bool(theme) and not theme.system)
        self.customize_theme_button.set_sensitive(bool(theme))

    def get_hidden_theme(self, theme):
        if theme:
            return self.themes[theme.basename][1]
        return None

    def get_selected_theme(self):
        filename = self.get_selected_theme_filename()
        if filename:
            basename = os.path.splitext(os.path.basename(filename))[0]
            if basename in self.themes:
                return self.themes[basename][0]
        return None

    def get_selected_theme_filename(self):
        sel = self.theme_view.get_selection().get_selected()[1]
        if sel:
            return self.themeList.get_value(sel,1)
        return None



class ThemeDialog:
    def __init__(self, settings, theme):

        self.original_theme = theme
        self.theme = copy.copy(theme)
        
        builder = LoadUI("settings_theme_dialog")

        self.dialog = builder.get_object("customize_theme_dialog")
        self.color_scheme_view = builder.get_object("color_scheme_view")
        
        self.color_scheme_view.append_column(
                  gtk.TreeViewColumn(None, gtk.CellRendererText(), markup = 0))
        self.font_combobox = builder.get_object("font_combobox")
        self.roundrect_radius_scale = builder.get_object(
                                                "roundrect_radius_hscale")
        self.revert_button = builder.get_object("revert_button")
        
        self.update_ui()
        
        builder.get_object("close_button").grab_default()
        self.dialog.set_position(gtk.WIN_POS_CENTER_ON_PARENT)
        self.dialog.set_transient_for(settings.window)
        
        builder.connect_signals(self)

    def run(self):
        # do response processing ourselves to stop the 
        # revert button from closing the dialog
        self.dialog.set_modal(True)
        self.dialog.show()
        gtk.main()
        self.dialog.destroy()
        return self.theme
    
    def on_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_DELETE_EVENT:
            pass
        if response_id == \
            self.dialog.get_response_for_widget(self.revert_button):

            # revert changes and keep the dialog open
            self.theme = copy.copy(self.original_theme)
            self.theme.apply()
            self.update_ui()
            return
         
        gtk.main_quit()

    def update_ui(self):
        self.update_color_schemeList()
        self.update_fontList()
        self.roundrect_radius_scale.set_value(self.theme.roundrect_radius)
        self.update_buttons()

    def update_buttons(self):
        self.revert_button.set_sensitive(not self.theme == self.original_theme)

    def update_color_schemeList(self):
        self.color_schemeList = gtk.ListStore(str,str)
        self.color_scheme_view.set_model(self.color_schemeList)

        self.color_scheme = ColorScheme.get_merged_color_schemes()
        color_scheme_filename = self.theme.get_color_scheme_filename()
        for color_scheme in sorted(self.color_scheme.values(), 
                                   key=lambda x: x.name):
            it = self.color_schemeList.append((
                      format_list_item(color_scheme.name, color_scheme.system),
                      color_scheme.filename))
            if color_scheme.filename == color_scheme_filename:
                self.color_scheme_view.get_selection().select_iter(it)

    def update_fontList(self):
        self.fontList = gtk.ListStore(str,str)
        self.font_combobox.set_model(self.fontList)
        cell = gtk.CellRendererText()
        self.font_combobox.clear()
        self.font_combobox.pack_start(cell, True)
        self.font_combobox.add_attribute(cell, 'text', 0)
#        .set_row_separator_func

        widget = gtk.DrawingArea() 
        context = widget.create_pango_context()
        families = [(font.get_name(), font.get_name()) for font in context.list_families()]
        widget.destroy()

        families.sort(key=lambda x: x[0])
        families = [(_("Default"), 
                    "")] + families

        for family in families:
            it = self.fontList.append(family)
            if family[1] == self.theme.key_label_font:
                self.font_combobox.set_active_iter(it)

    def on_color_scheme_view_cursor_changed(self, widget):
        filename = self.color_schemeList.get_value(
                widget.get_selection().get_selected()[1],1)
        self.theme.set_color_scheme_filename(filename)
        config.color_scheme_filename = filename
        self.update_buttons()

    def on_roundrect_adjustment_value_changed(self, widget):
        radius = int(widget.get_value())
        config.roundrect_radius = radius
        self.theme.roundrect_radius = radius
        self.update_buttons()

    def on_font_combobox_changed(self, widget):
        font = self.fontList.get_value(self.font_combobox.get_active_iter(),1)
        self.theme.key_label_font = font
        config.key_label_font = font
        self.update_buttons()


if __name__=='__main__':
    s = Settings(True)
