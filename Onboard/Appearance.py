#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import with_statement

### Logging ###
import logging
_logger = logging.getLogger("Theme")
###############

from gettext import gettext as _
from xml.dom import minidom
import os
import re
import string
import sys
import ConfigParser as configparser

from Onboard             import Exceptions
from Onboard.utils       import hexstring_to_float

import Onboard.utils as utils

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class Theme:

    # core theme members
    # name, type, default
    attributes = [
            ["color_scheme_basename", "s", ""],
            ["key_style", "s", "flat"],
            ["roundrect_radius", "i", 0],
            ["key_fill_gradient", "i", 0],
            ["key_stroke_gradient", "i", 0],
            ["key_gradient_direction", "i", 0],
            ["key_label_font", "s", ""],
            ["key_label_overrides", "d", {}]   # dict {name:(key:group)}
            ]

    def __init__(self):
        self.modified = False

        self.filename = ""
        self.system = False          # True if this a system theme
        self.system_exists = False   # True if there exists a system
                                     #  theme with the same basename
        self.name = ""

        for name, type, default in self.attributes:
            setattr(self, name, default)

    @property
    def basename(self):
        return os.path.splitext(os.path.basename(self.filename))[0]

    def __eq__(self, other):
        if not other:
            return False
        for name, type, default in self.attributes:
            if getattr(self, name) != getattr(other, name):
                return False
        return True

    def __str__(self):
        return "name=%s, colors=%s, font=%s, radius=%d" % (self.name,
                                                self.color_scheme_basename,
                                                self.key_label_font,
                                                self.roundrect_radius)

    def apply(self, save=True):

        filename = self.get_color_scheme_filename()
        if not filename:
            _logger.error(_("Color scheme for theme '%s' not found") % self.filename)
            return False

        config.theme.set_color_scheme_filename(filename, save)
        for name, type, default in self.attributes:
            if name != "color_scheme_basename":
                getattr(config.theme, "set_" + name) \
                                 (getattr(self, name), save)

        return True

    def get_color_scheme_filename(self):
        filename = os.path.join(Theme.user_path(),
                                self.color_scheme_basename) + \
                                "." + ColorScheme.extension()
        if not os.path.isfile(filename):
            filename = os.path.join(Theme.system_path(),
                                    self.color_scheme_basename) + \
                                    "." + ColorScheme.extension()
        if not os.path.isfile(filename):
            return None
        return filename

    def set_color_scheme_filename(self, filename):
        self.color_scheme_basename = \
                             os.path.splitext(os.path.basename(filename ))[0]

    def get_superkey_label(self):
        t = self.key_label_overrides.get("LWIN")
        if t:
            return t[0] # assumes RWIN=LWIN
        return None

    def get_superkey_size_group(self):
        t = self.key_label_overrides.get("LWIN")
        if t:
            return t[1] # assumes RWIN=LWIN
        return None

    def set_superkey_label(self, label, size_group):
        tuples = self.key_label_overrides
        if label is None:
            if "LWIN" in tuples: del tuples["LWIN"]
            if "RWIN" in tuples: del tuples["RWIN"]
        else:
            tuples["LWIN"] = (label, size_group)
            tuples["RWIN"] = (label, size_group)
        self.key_label_overrides = tuples

    @staticmethod
    def system_to_user_filename(filename):
        # get user filename for the given system filename
        basename = os.path.splitext(os.path.basename(filename ))[0]
        return os.path.join(Theme.user_path(),
                                basename) + "." + Theme.extension()

    @staticmethod
    def build_user_filename(basename):
        return os.path.join(Theme.user_path(),
                                basename) + "." + Theme.extension()

    @staticmethod
    def build_system_filename(basename):
        return os.path.join(Theme.system_path(),
                                basename) + "." + Theme.extension()

    @staticmethod
    def system_path():
        return os.path.join(config.install_dir, "themes")

    @staticmethod
    def user_path():
        return os.path.join(config.user_dir, "themes")

    @staticmethod
    def extension():
        return "theme"

    @staticmethod
    def load_merged_themes():
        # Merge system and user themes.
        # User themes take precedence and hide system themes.
        system_themes = Theme.load_themes(True)
        user_themes = Theme.load_themes(False)
        themes = dict((t.basename, (t, None)) for t in system_themes)
        for t in user_themes:
            if t.basename in themes: # system theme hidden behind user theme?
                themes[t.basename] = (t, themes[t.basename][0]) # keep it around
            else:
                themes[t.basename] = (t, None)
        return themes

    @staticmethod
    def load_themes(system=False):
        themes = []

        if system:
            path = Theme.system_path()
        else:
            path = Theme.user_path()

        filenames = Theme.find_themes(path)
        for filename in filenames:
            theme = Theme.load(filename, system)
            themes.append(theme)
        return themes

    @staticmethod
    def find_themes(path):
        files = os.listdir(path)
        themes = []
        for filename in files:
            if filename.endswith(Theme.extension()):
                themes.append(os.path.join(path, filename))
        return themes


    @staticmethod
    def load(filename, system=False):

        result = None

        f = open(filename)
        try:
            domdoc = minidom.parse(f).documentElement
            try:
                theme = Theme()

                theme.name = domdoc.attributes["name"].value

                # "color_scheme" is the base file name of the color scheme
                text = utils.xml_get_text(domdoc, "color_scheme")
                if not text is None:
                    theme.color_scheme_basename = text

                # get key label overrides
                nodes = domdoc.getElementsByTagName("key_label_overrides")
                if nodes:
                    overrides = nodes[0]
                    tuples = {}
                    for override in overrides.getElementsByTagName("key"):
                        id = override.attributes["id"].value
                        node = override.attributes.get("label")
                        label = node.value if node else ""
                        node = override.attributes.get("group")
                        group = node.value if node else ""
                        tuples[id] = (label, group)
                    theme.key_label_overrides = tuples

                # read all other members
                for name, type, default in Theme.attributes:
                    if not name in ["color_scheme_basename",
                                    "key_label_overrides"]:
                        value = utils.xml_get_text(domdoc, name)
                        if not value is None:
                            if type == "i":
                                value = int(value)
                            setattr(theme, name, value)

                theme.filename = filename
                theme.system = system
                theme.system_exists = system
                result = theme
            except Exceptions.ThemeFileError, (exception):
                raise Exceptions.ThemeFileError(_("Error loading ")
                    + filename, chained_exception = exception)
            finally:
                domdoc.unlink()

        finally:
            f.close()

        return result

    def save_as(self, basename, name):
        self.filename = self.build_user_filename(basename)
        self.name = name
        self.save()

    def save(self):
        domdoc = minidom.Document()
        try:
            theme_element = domdoc.createElement("theme")
            theme_element.setAttribute("name", self.name)
            domdoc.appendChild(theme_element)

            for name, type, default in self.attributes:
                if name == "color_scheme_basename":
                    element = domdoc.createElement("color_scheme")
                    text = domdoc.createTextNode(self.color_scheme_basename)
                    element.appendChild(text)
                    theme_element.appendChild(element)
                elif name == "key_label_overrides":
                    overrides_element = domdoc.createElement("key_label_overrides")
                    theme_element.appendChild(overrides_element)
                    tuples = self.key_label_overrides
                    for key_id, values in tuples.items():
                        element = domdoc.createElement("key")
                        element.setAttribute("id", key_id)
                        element.setAttribute("label", values[0])
                        element.setAttribute("group", values[1])
                        overrides_element.appendChild(element)
                else:
                    value = getattr(self, name)
                    if type == "i":
                        value = str(value)
                    element = domdoc.createElement(name)
                    text = domdoc.createTextNode(value)
                    element.appendChild(text)
                    theme_element.appendChild(element)

            ugly_xml = domdoc.toprettyxml(indent='  ')
            pattern = re.compile('>\n\s+([^<>\s].*?)\n\s+</', re.DOTALL)
            pretty_xml = pattern.sub('>\g<1></', ugly_xml)

            with open(self.filename, "w") as f:
                f.write(pretty_xml.encode("UTF-8"))

        except Exception, (exception):
            raise Exceptions.ThemeFileError(_("Error loading ")
                + self.filename, chained_exception = exception)
        finally:
            domdoc.unlink()


class ColorScheme:
    def __init__(self):
        self.filename = ""
        self.system = False
        self.name = ""

        # all colors as 4 component arrays, rgba
        self.default_pane_fill_color = [0.0, 0.0, 0.0, 1.0]
        self.default_pane_fill_opacity = 1.0
        self.pane_fill_color = {}
        self.pane_fill_opacity = {}
        self.default_key_opacity = None
        self.key_opacity = {}
        self.key_defaults = {
                "fill":   [0.0, 0.0, 0.0, 1.0],
                "hover":  [0.0, 0.0, 0.0, 1.0],
                "pressed":[0.5, 0.5, 0.5, 1.0],
                "latched":[0.5, 0.5, 0.5, 1.0],
                "locked": [1.0, 0.0, 0.0, 1.0],
                "scanned":[0.45, 0.45, 0.7, 1.0],
                "stroke": [0.0, 0.0, 0.0, 1.0],
                "label":  [0.0, 0.0, 0.0, 1.0],
                }
        self.key_colors = {}

    @property
    def basename(self):
        return os.path.splitext(os.path.basename(self.filename))[0]

    def get_key_rgba(self, key_id, color_name):
        # get default color
        opacity = self.key_opacity.get(key_id)
        if not opacity is None:
            # if given, apply key opacity as alpha to all default colors
            rgba_default = self.key_defaults[color_name][:3] + [opacity]
        else:
            opacity = self.default_key_opacity
            if not opacity is None:
                rgba_default = self.key_defaults[color_name][:3] + [opacity]
            else:
                rgba_default = self.key_defaults[color_name]

        # Get set of colors defined for key_id
        colors = self.key_colors.get(key_id)
        if not colors:
            return rgba_default

        # Merge rgb and alpha components of whatever has been defined for
        # the key and take the rest from the default color.
        value = colors.get(color_name, rgba_default)
        if len(value) == 4:
            return value
        if len(value) == 3:
            return value + rgba_default[3:4]
        if len(value) == 1:
            return rgba_default[:3] + value

        assert(False)

    def get_pane_fill_rgba(self, pane_index):
        rgba = self.pane_fill_color.get(pane_index,
                                        self.default_pane_fill_color)
        rgba[3] = self.pane_fill_opacity.get(pane_index,
                                        self.default_pane_fill_opacity)
        return rgba

    @staticmethod
    def system_path():
        return os.path.join(config.install_dir, "themes")

    @staticmethod
    def user_path():
        return os.path.join(config.user_dir, "themes/")

    @staticmethod
    def extension():
        return "colors"

    @staticmethod
    def get_merged_color_schemes():
        # merge system and user color_schemes
        # user color_schemes take precedence and hide system color_schemes
        system_color_schemes = ColorScheme.load_color_schemes(True)
        user_color_schemes = ColorScheme.load_color_schemes(False)
        color_schemes = dict((t.basename, t) for t in system_color_schemes)
        for t in user_color_schemes:
            color_schemes[t.basename] = t
        return color_schemes

    @staticmethod
    def load_color_schemes(system=False):
        color_schemes = []

        if system:
            path = ColorScheme.system_path()
        else:
            path = ColorScheme.user_path()

        filenames = ColorScheme.find_color_schemes(path)
        for filename in filenames:
            color_scheme = ColorScheme.load(filename, system)
            color_schemes.append(color_scheme)
        return color_schemes

    @staticmethod
    def find_color_schemes(path):
        files = os.listdir(path)
        color_schemes = []
        for filename in files:
            if filename.endswith(ColorScheme.extension()):
                color_schemes.append(os.path.join(path, filename))
        return color_schemes

    @staticmethod
    def load(filename, system=False):

        color_scheme = None

        f = open(filename)
        try:
            cp = configparser.SafeConfigParser()
            domdoc = minidom.parse(f).documentElement
            try:
                color_scheme = ColorScheme()

                color_scheme.name = domdoc.attributes["name"].value

                # pane colors
                for i,pane in enumerate(domdoc.getElementsByTagName("pane")):
                    if pane.hasAttribute("fill"):
                        value = pane.attributes["fill"].value
                        rgba = [hexstring_to_float(value[1:3])/255,
                        hexstring_to_float(value[3:5])/255,
                        hexstring_to_float(value[5:7])/255,
                        1]
                        color_scheme.pane_fill_color[i] = rgba

                    if pane.hasAttribute("fill-opacity"):
                        value = float(pane.attributes["fill-opacity"].value)
                        color_scheme.pane_fill_opacity[i] = value

                # key colors
                for group in domdoc.getElementsByTagName("key_group"):

                    # default colors are applied to all keys
                    # not found in the color scheme
                    default_group = False
                    if group.hasAttribute("default"):
                        default_group = bool(group.attributes["default"].value)

                    # read key ids
                    text = "".join([n.data for n in group.childNodes])
                    ids = [x for x in re.split('\W+', text) if x]

                    key_defaults = color_scheme.key_defaults
                    key_colors   = color_scheme.key_colors

                    for attrib in key_defaults.keys():

                        # read color attribute
                        if group.hasAttribute(attrib):
                            value = group.attributes[attrib].value
                            rgb = [hexstring_to_float(value[1:3])/255,
                                   hexstring_to_float(value[3:5])/255,
                                   hexstring_to_float(value[5:7])/255]

                            if default_group:
                                value = key_defaults[attrib]
                                key_defaults[attrib] = rgb + value[3:4]
                            else:
                                for key_id in ids:
                                    colors = key_colors.get(key_id, {})
                                    value = colors.get(attrib, [.0,.0,.0])
                                    colors[attrib] = rgb + value[3:4]
                                    key_colors[key_id] = colors

                        # read opacity attribute
                        oattrib = attrib + "-opacity"
                        if group.hasAttribute(oattrib):
                            opacity = float(group.attributes[oattrib].value)
                            if default_group:
                                value = key_defaults[attrib]
                                key_defaults[attrib] = value[:3] + [opacity]
                            else:
                                for key_id in ids:
                                    colors = \
                                       key_colors.get(key_id, {})
                                    value = key_colors.get(attrib, [.0])
                                    if len(value) == 1:
                                        colors[attrib] = [opacity]
                                    else:
                                        colors[attrib] = value[:3] + [opacity]
                                    key_colors[key_id] = colors

                    # read main opacity setting
                    # applies to all colors that don't have their own opacity
                    if group.hasAttribute("opacity"):
                        value = float(group.attributes["opacity"].value)
                        if default_group:
                            color_scheme.default_key_opacity = value
                        else:
                            for key_id in ids:
                                color_scheme.key_opacity[key_id] = value

                color_scheme.filename = filename
                color_scheme.system = system

            except Exception, (exception):
                raise Exceptions.ColorSchemeFileError(_("Error loading ")
                    + filename, chained_exception = exception)
            finally:
                domdoc.unlink()
        finally:
            f.close()

        return color_scheme


