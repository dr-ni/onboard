#!/usr/bin/python
# -*- coding: utf-8 -*-

from gi.repository import Gtk, Pango

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
    builder = Gtk.Builder()
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

        Gtk.Window.set_default_icon_name("onboard")
        self.window.set_title(_("Onboard Preferences"))

        self.status_icon_toggle = builder.get_object("status_icon_toggle")
        self.status_icon_toggle.set_active(config.show_status_icon)
        config.show_status_icon_notify_add(self.status_icon_toggle.set_active)

        self.start_minimized_toggle = builder.get_object(
            "start_minimized_toggle")
        self.start_minimized_toggle.set_active(config.start_minimized)
        config.start_minimized_notify_add(
            self.start_minimized_toggle.set_active)

        self.icon_palette_toggle = builder.get_object("icon_palette_toggle")
        self.icon_palette_toggle.set_active(config.icp.in_use)
        config.icp.in_use_notify_add(self.icon_palette_toggle.set_active)

        self.modeless_gksu_toggle = builder.get_object("modeless_gksu_toggle")
        self.modeless_gksu_toggle.set_active(config.modeless_gksu)
        config.modeless_gksu_notify_add(self.modeless_gksu_toggle.set_active)

        self.onboard_xembed_toggle = builder.get_object("onboard_xembed_toggle")
        self.onboard_xembed_toggle.set_active(config.onboard_xembed_enabled)
        config.onboard_xembed_enabled_notify_add(self.onboard_xembed_toggle.set_active)

        # layout view
        self.layout_view = builder.get_object("layout_view")
        self.layout_view.append_column(Gtk.TreeViewColumn(None,
                                                          Gtk.CellRendererText(),
                                                          markup=0))

        self.user_layout_root = os.path.join(config.user_dir, "layouts/")
        if not os.path.exists(self.user_layout_root):
            os.makedirs(self.user_layout_root)

        self.update_layoutList()

        # theme view
        self.theme_view = builder.get_object("theme_view")
        self.theme_view.append_column(Gtk.TreeViewColumn(None,
                                                         Gtk.CellRendererText(),
                                                         markup=0))
        self.delete_theme_button = builder.get_object("delete_theme_button")
        self.delete_theme_button
        self.customize_theme_button = \
                                   builder.get_object("customize_theme_button")

        user_theme_root = Theme.user_path()
        if not os.path.exists(user_theme_root):
            os.makedirs(user_theme_root)

        self.update_themeList()

        # Snippets
        self.snippet_list = SnippetList()
        builder.get_object("snippet_scrolled_window").add(self.snippet_list)

        # Scanning
        builder.get_object("scanning_check").set_active(config.enable_scanning)

        builder.get_object("interval_spin").set_value(
            config.scanning_interval/1000)

        self.settings_notebook = builder.get_object("settings_notebook")
        self.settings_notebook.set_current_page(config.current_settings_page)
        self.window.show_all()
        self.modeless_gksu_toggle.hide() # hidden until gksu moves to gsettings

        self.window.set_keep_above(not mainwin)

        self.window.connect("destroy", Gtk.main_quit)
        builder.connect_signals(self)

        _logger.info("Entering mainloop of Onboard-settings")
        Gtk.main()

    def on_settings_notebook_switch_page(self, widget, gpage, page_num):
        config.current_settings_page = page_num

    def on_snippet_add_button_clicked(self, event):
        _logger.info("Snippet add button clicked")
        self.snippet_list.append("","")

    def on_snippet_remove_button_clicked(self, event):
        _logger.info("Snippet remove button clicked")
        self.snippet_list.remove_selected()

    def on_status_icon_toggled(self,widget):
        config.show_status_icon = widget.get_active()

    def on_start_minimized_toggled(self,widget):
        config.start_minimized = widget.get_active()

    def on_icon_palette_toggled(self, widget):
        config.icp.in_use = widget.get_active()

    def on_modeless_gksu_toggled(self, widget):
        config.modeless_gksu = widget.get_active()

    def on_xembed_onboard_toggled(self, widget):
        if widget.get_active(): # the user has enabled the option
                config.onboard_xembed_enabled = True
                config.gss.embedded_keyboard_enabled = True
                config.set_xembed_command_string_to_onboard()
        else:
            config.onboard_xembed_enabled = False
            config.gss.embedded_keyboard_enabled = False


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
            _("Enter name for personalised layout"), self.window)
        if new_layout_name:
            vk = virtkey()
            keyboard = KeyboardSVG(vk, config.layout_filename,
                                       config.theme.color_scheme_filename)
            layout_xml = utils.create_layout_XML(new_layout_name,
                                                 vk,
                                                 keyboard)
            utils.save_layout_XML(layout_xml, self.user_layout_root)
            self.update_layoutList()
            self.open_user_layout_dir()

    def on_scanning_check_toggled(self, widget):
        config.enable_scanning = widget.get_active()

    def on_interval_spin_value_changed(self, widget):
        config.scanning_interval = int(widget.get_value()*1000)

    def on_close_button_clicked(self, widget):
        self.window.destroy()
        Gtk.main_quit()

    def update_layoutList(self):
        self.layoutList = Gtk.ListStore(str, str)
        self.layout_view.set_model(self.layoutList)

        self.update_layouts(os.path.join(config.install_dir, "layouts"))
        self.update_layouts(self.user_layout_root)

    def cb_selected_layout_changed(self):
        self.update_layouts(self.user_layout_root)

    def on_add_button_clicked(self, event):
        chooser = Gtk.FileChooserDialog(title=_("Add Layout"),
                                        parent=self.window,
                                        action=Gtk.FileChooserAction.OPEN,
                                        buttons=(Gtk.STOCK_CANCEL,
                                                 Gtk.ResponseType.CANCEL,
                                                 Gtk.STOCK_OPEN,
                                                 Gtk.ResponseType.OK))
        filterer = Gtk.FileFilter()
        filterer.add_pattern("*.sok")
        filterer.add_pattern("*.onboard")
        filterer.set_name(_("Onboard layout files"))
        chooser.add_filter(filterer)

        filterer = Gtk.FileFilter()
        filterer.add_pattern("*")
        filterer.set_name(_("All files"))
        chooser.add_filter(filterer)

        response = chooser.run()
        if response == Gtk.ResponseType.OK:
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
            os.remove("%s/%s" % (os.path.dirname(filename), p.attributes['filename'].value))#todo get onboard to deal with not having a layout.
        config.layout_filename = self.layoutList[0][1] \
                                 if len(self.layoutList) else ""
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


    def on_new_theme_button_clicked(self, widget):
        while True:
            new_name = show_ask_string_dialog(
                _("Enter a name for the new theme:"), self.window)
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

    def on_delete_theme_button_clicked(self, widget):
        theme = self.get_selected_theme()
        if theme and not theme.system:
            if self.get_hidden_theme(theme):
                question = _("Revert selected theme to Onboard defaults?")
            else:
                question = _("Delete selected theme file?")
            reply = show_confirmation_dialog(question, self.window)
            if reply == True:
                # be sure the file hasn't been deleted from outside already
                if os.path.exists(theme.filename):
                    os.remove(theme.filename)

                # find a neighboring theme to select after deletion
                if not self.get_hidden_theme(theme): # will row disappear?
                    near_theme = self.find_neighbor_theme(theme)
                    config.theme_filename = near_theme.filename \
                                            if near_theme else ""

                self.update_themeList()

                # notify gsettings clients
                theme = self.get_selected_theme()
                if theme:
                    theme.apply()


    def find_neighbor_theme(self, theme):
        themes = self.get_sorted_themes()
        for i,tpl in enumerate(themes):
            if theme.basename == tpl[0].basename:
                if i < len(themes)-1:
                    return themes[i+1][0]
                else:
                    return themes[i-1][0]
        return None

    def on_customize_theme_button_clicked(self, widget):
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
        self.themeList = Gtk.ListStore(str, str)
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
        if it_selection:
            path = self.themeList.get_path(it_selection)
            self.theme_view.scroll_to_cell(path)

        self.update_theme_buttons()

    def update_theme_buttons(self):
        theme = self.get_selected_theme()

        if theme and (self.get_hidden_theme(theme) or theme.system):
            self.delete_theme_button.set_label(Gtk.STOCK_REVERT_TO_SAVED)
        else:
            self.delete_theme_button.set_label(Gtk.STOCK_DELETE)

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

    current_page = 0

    def __init__(self, settings, theme):

        self.original_theme = theme
        self.theme = copy.deepcopy(theme)

        builder = LoadUI("settings_theme_dialog")

        self.dialog = builder.get_object("customize_theme_dialog")

        self.theme_notebook = builder.get_object("theme_notebook")

        self.key_style_combobox = builder.get_object("key_style_combobox")
        self.color_scheme_combobox = builder.get_object("color_scheme_combobox")
        self.font_combobox = builder.get_object("font_combobox")
        self.font_attributes_view = builder.get_object("font_attributes_view")
        self.roundrect_radius_scale = builder.get_object(
                                               "roundrect_radius_scale")
        self.gradients_box = builder.get_object("gradients_box")
        self.key_fill_gradient_scale = builder.get_object(
                                               "key_fill_gradient_scale")
        self.key_stroke_gradient_scale = builder.get_object(
                                               "key_stroke_gradient_scale")
        self.key_gradient_direction_scale = builder.get_object(
                                               "key_gradient_direction_scale")
        self.revert_button = builder.get_object("revert_button")
        self.superkey_label_combobox = builder.get_object(
                                               "superkey_label_combobox")
        self.superkey_label_size_checkbutton = builder.get_object(
                                            "superkey_label_size_checkbutton")
        self.superkey_label_model = builder.get_object("superkey_label_model")

        self.update_ui()

        self.dialog.set_transient_for(settings.window)
        self.theme_notebook.set_current_page(ThemeDialog.current_page)

        builder.connect_signals(self)

    def run(self):
        # do response processing ourselves to stop the
        # revert button from closing the dialog
        self.dialog.set_modal(True)
        self.dialog.show()
        Gtk.main()
        self.dialog.destroy()
        return self.theme

    def on_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.DELETE_EVENT:
            pass
        if response_id == \
            self.dialog.get_response_for_widget(self.revert_button):

            # revert changes and keep the dialog open
            self.theme = copy.deepcopy(self.original_theme)
            self.update_ui()
            self.theme.apply()
            return

        Gtk.main_quit()

    def update_ui(self):
        self.in_update = True

        self.update_key_styleList()
        self.update_color_schemeList()
        self.update_fontList()
        self.update_font_attributesList()
        self.roundrect_radius_scale.set_value(self.theme.roundrect_radius)
        self.key_fill_gradient_scale.set_value(self.theme.key_fill_gradient)
        self.key_stroke_gradient_scale. \
                set_value(self.theme.key_stroke_gradient)
        self.key_gradient_direction_scale. \
                set_value(self.theme.key_gradient_direction)
        self.update_superkey_labelList()
        self.superkey_label_size_checkbutton. \
                set_active(bool(self.theme.get_superkey_size_group()))

        self.update_sensivity()

        self.in_update = False

    def update_sensivity(self):
        self.revert_button.set_sensitive(not self.theme == self.original_theme)

        has_gradient = self.theme.key_style != "flat"
        self.gradients_box.set_sensitive(has_gradient)
        self.superkey_label_size_checkbutton.\
                      set_sensitive(bool(self.theme.get_superkey_label()))

    def update_key_styleList(self):
        self.key_styleList = Gtk.ListStore(str,str)
        self.key_style_combobox.set_model(self.key_styleList)
        cell = Gtk.CellRendererText()
        self.key_style_combobox.clear()
        self.key_style_combobox.pack_start(cell, True)
        self.key_style_combobox.add_attribute(cell, 'markup', 0)

        self.key_styles = [[_("Flat"), "flat"],
                           [_("Gradient"), "gradient"],
                           #[_("Dish"), "dish"]
                           ]
        for name, id in self.key_styles:
            it = self.key_styleList.append((name, id))
            if id == self.theme.key_style:
                self.key_style_combobox.set_active_iter(it)

    def update_color_schemeList(self):
        self.color_schemeList = Gtk.ListStore(str,str)
        self.color_scheme_combobox.set_model(self.color_schemeList)
        cell = Gtk.CellRendererText()
        self.color_scheme_combobox.clear()
        self.color_scheme_combobox.pack_start(cell, True)
        self.color_scheme_combobox.add_attribute(cell, 'markup', 0)

        self.color_schemes = ColorScheme.get_merged_color_schemes()
        color_scheme_filename = self.theme.get_color_scheme_filename()
        for color_scheme in sorted(self.color_schemes.values(),
                                   key=lambda x: x.name):
            it = self.color_schemeList.append((
                      format_list_item(color_scheme.name, color_scheme.system),
                      color_scheme.filename))
            if color_scheme.filename == color_scheme_filename:
                self.color_scheme_combobox.set_active_iter(it)

    def update_fontList(self):
        self.fontList = Gtk.ListStore(str,str)
        self.font_combobox.set_model(self.fontList)
        cell = Gtk.CellRendererText()
        self.font_combobox.clear()
        self.font_combobox.pack_start(cell, True)
        self.font_combobox.add_attribute(cell, 'markup', 0)
        self.font_combobox.set_row_separator_func(
                                    self.font_combobox_row_separator_func,
                                    None)

        widget = Gtk.DrawingArea()
        context = widget.create_pango_context()
        families = []#[(font.get_name(), font.get_name()) \
                    #for font in context.list_families()]
        widget.destroy()

        families.sort(key=lambda x: x[0])
        families = [(_("Default"), "Normal"),
                    ("-", "-")] + families
        fd = Pango.FontDescription(self.theme.key_label_font)
        family = fd.get_family()
        for f in families:
            it = self.fontList.append(f)
            if  f[1] == family or \
               (f[1] == "Normal" and not family):
                self.font_combobox.set_active_iter(it)

    def font_combobox_row_separator_func(self, model, iter, data):
        return model.get_value(iter, 0) == "-"

    def update_font_attributesList(self):
        treeview = self.font_attributes_view

        if not treeview.get_columns():
            liststore = Gtk.ListStore(bool, str, str)
            self.font_attributesList = liststore
            treeview.set_model(liststore)

            column_toggle = Gtk.TreeViewColumn("Toggle")
            column_text = Gtk.TreeViewColumn("Text")
            treeview.append_column(column_toggle)
            treeview.append_column(column_text)

            cellrenderer_toggle = Gtk.CellRendererToggle()
            column_toggle.pack_start(cellrenderer_toggle, False)
            column_toggle.add_attribute(cellrenderer_toggle, "active", 0)

            cellrenderer_text = Gtk.CellRendererText()
            column_text.pack_start(cellrenderer_text, True)
            column_text.add_attribute(cellrenderer_text, "text", 1)
            cellrenderer_toggle.connect("toggled", self.on_font_attributesList_toggle,
                         liststore)

        liststore = treeview.get_model()
        liststore.clear()

        fd = Pango.FontDescription(self.theme.key_label_font)
        items = [[fd.get_weight() == Pango.Weight.BOLD,
                  _("Bold"), "bold"],
                 [fd.get_style() == Pango.Style.ITALIC,
                  _("Italic"), "italic"],
                 [fd.get_stretch() == Pango.Stretch.CONDENSED,
                  _("Condensed"), "condensed"],
                ]
        for checked, name, id in items:
            it = liststore.append((checked, name, id))
            if id == "":
                treeview.set_active_iter(it)

    def update_superkey_labelList(self):
        self.superkey_label_model.clear()
        self.superkey_labels = [["",      _("Default")],
                                [_(""), _("Ubuntu Logo")]
                               ]

        for label, descr in self.superkey_labels:
            self.superkey_label_model.append((label, descr))

        label = self.theme.get_superkey_label()
        self.superkey_label_combobox.get_child().set_text(label if label else "")

    def on_theme_notebook_switch_page(self, widget, gpage, page_num):
        ThemeDialog.current_page = page_num

    def on_key_style_combobox_changed(self, widget):
        value = self.key_styleList.get_value( \
                            self.key_style_combobox.get_active_iter(),1)
        self.theme.key_style = value
        config.theme.key_style = value
        self.update_sensivity()

    def on_roundrect_value_changed(self, widget):
        radius = int(widget.get_value())
        config.theme.roundrect_radius = radius
        self.theme.roundrect_radius = radius
        self.update_sensivity()

    def on_color_scheme_combobox_changed(self, widget):
        filename = self.color_schemeList.get_value( \
                               self.color_scheme_combobox.get_active_iter(),1)
        self.theme.set_color_scheme_filename(filename)
        config.theme.color_scheme_filename = filename
        self.update_sensivity()

    def on_key_fill_gradient_value_changed(self, widget):
        value = int(widget.get_value())
        config.theme.key_fill_gradient = value
        self.theme.key_fill_gradient = value
        self.update_sensivity()

    def on_key_stroke_gradient_value_changed(self, widget):
        value = int(widget.get_value())
        config.theme.key_stroke_gradient = value
        self.theme.key_stroke_gradient = value
        self.update_sensivity()

    def on_key_gradient_direction_value_changed(self, widget):
        value = int(widget.get_value())
        config.theme.key_gradient_direction = value
        self.theme.key_gradient_direction = value
        self.update_sensivity()

    def on_font_combobox_changed(self, widget):
        if not self.in_update:
            self.store_key_label_font()
            self.update_sensivity()

    def on_font_attributesList_toggle(self, widget, path, model):
        model[path][0] = not model[path][0]
        self.store_key_label_font()
        self.update_sensivity()

    def store_key_label_font(self):
        font = self.fontList.get_value(self.font_combobox.get_active_iter(),1)
        for row in self.font_attributesList:
            if row[0]:
                font += " " + row[2]

        self.theme.key_label_font = font
        config.theme.key_label_font = font

    def on_superkey_label_combobox_changed(self, widget):
        self.store_superkey_label_override()
        self.update_sensivity()

    def on_superkey_label_size_checkbutton_toggled(self, widget):
        self.store_superkey_label_override()
        self.update_sensivity()

    def store_superkey_label_override(self):
        label = self.superkey_label_combobox.get_child().get_text()
        if not label:
            label = None   # removes the override
        checked = self.superkey_label_size_checkbutton.get_active()
        size_group = config.SUPERKEY_SIZE_GROUP if checked else ""
        self.theme.set_superkey_label(label, size_group)
        config.theme.key_label_overrides = self.theme.key_label_overrides

if __name__=='__main__':
    s = Settings(True)
