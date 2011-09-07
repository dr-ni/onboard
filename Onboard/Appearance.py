#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Module for theme related classes.
"""

from __future__ import with_statement

### Logging ###
import logging
_logger = logging.getLogger("Theme")
###############

from gettext import gettext as _
from xml.dom import minidom
import os
import re

from Onboard             import Exceptions
from Onboard.utils       import hexstring_to_float

import Onboard.utils as utils

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class Theme:
    """
    Theme controls the visual appearance of Onboards keyboard window.
    """
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
        self.is_system = False       # True if this a system theme
        self.system_exists = False   # True if there exists a system
                                     #  theme with the same basename
        self.name = ""

        # create attributes
        for name, _type, default in self.attributes:
            setattr(self, name, default)

    @property
    def basename(self):
        """ Returns the file base name of the theme. """
        return os.path.splitext(os.path.basename(self.filename))[0]

    def __eq__(self, other):
        if not other:
            return False
        for name, _type, _default in self.attributes:
            if getattr(self, name) != getattr(other, name):
                return False
        return True

    def __str__(self):
        return "name=%s, colors=%s, font=%s, radius=%d" % (self.name,
                                                self.color_scheme_basename,
                                                self.key_label_font,
                                                self.roundrect_radius)

    def apply(self, save=True):
        """ Applies the theme to config properties/gsettings. """
        filename = self.get_color_scheme_filename()
        if not filename:
            _logger.error(_("Color scheme for theme '%s' not found")
                            % self.filename)
            return False

        config.theme.set_color_scheme_filename(filename, save)
        for name, _type, _default in self.attributes:
            if name != "color_scheme_basename":
                getattr(config.theme, "set_" + name) \
                                 (getattr(self, name), save)

        return True

    def get_color_scheme_filename(self):
        """ Returns the filename of the themes color scheme."""
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
        """ Set the filename of the color_scheme. """
        self.color_scheme_basename = \
                             os.path.splitext(os.path.basename(filename ))[0]

    def get_superkey_label(self):
        """ Returns the (potentially overridden) label of the super keys. """
        override = self.key_label_overrides.get("LWIN")
        if override:
            return override[0] # assumes RWIN=LWIN
        return None

    def get_superkey_size_group(self):
        """
        Returns the (potentially overridden) size group of the super keys.
        """
        override = self.key_label_overrides.get("LWIN")
        if override:
            return override[1] # assumes RWIN=LWIN
        return None

    def set_superkey_label(self, label, size_group):
        """ Sets or clears the override for left and right super key labels. """
        tuples = self.key_label_overrides
        if label is None:
            if "LWIN" in tuples:
                del tuples["LWIN"]
            if "RWIN" in tuples:
                del tuples["RWIN"]
        else:
            tuples["LWIN"] = (label, size_group)
            tuples["RWIN"] = (label, size_group)
        self.key_label_overrides = tuples

    @staticmethod
    def system_to_user_filename(filename):
        """ Returns the user filename for the given system filename. """
        basename = os.path.splitext(os.path.basename(filename ))[0]
        return os.path.join(Theme.user_path(),
                                basename) + "." + Theme.extension()

    @staticmethod
    def build_user_filename(basename):
        """
        Returns a fully qualified filename pointing into the user directory
        """
        return os.path.join(Theme.user_path(),
                                basename) + "." + Theme.extension()

    @staticmethod
    def build_system_filename(basename):
        """
        Returns a fully qualified filename pointing into the system directory
        """
        return os.path.join(Theme.system_path(),
                                basename) + "." + Theme.extension()

    @staticmethod
    def user_path():
        """ Returns the path of the user directory for themes. """
        return os.path.join(config.user_dir, "themes")

    @staticmethod
    def system_path():
        """ Returns the path of the system directory for themes. """
        return os.path.join(config.install_dir, "themes")

    @staticmethod
    def extension():
        """ Returns the file extension of theme files """
        return "theme"

    @staticmethod
    def load_merged_themes():
        """
        Merge system and user themes.
        User themes take precedence and hide system themes.
        """
        system_themes = Theme.load_themes(True)
        user_themes = Theme.load_themes(False)
        themes = dict((t.basename, (t, None)) for t in system_themes)
        for theme in user_themes:
            # system theme hidden behind user theme?
            if theme.basename in themes:
                # keep the system theme behind the user theme
                themes[theme.basename] = (theme, themes[theme.basename][0])
            else:
                themes[theme.basename] = (theme, None)
        return themes

    @staticmethod
    def load_themes(is_system=False):
        """ Load all themes from either the user or the system directory. """
        themes = []

        if is_system:
            path = Theme.system_path()
        else:
            path = Theme.user_path()

        filenames = Theme.find_themes(path)
        for filename in filenames:
            theme = Theme.load(filename, is_system)
            themes.append(theme)
        return themes

    @staticmethod
    def find_themes(path):
        """
        Returns the full path names of all themes found in the given path.
        """
        files = os.listdir(path)
        themes = []
        for filename in files:
            if filename.endswith(Theme.extension()):
                themes.append(os.path.join(path, filename))
        return themes


    @staticmethod
    def load(filename, is_system=False):
        """ Load a theme and return a new theme object. """

        result = None

        _file = open(filename)
        try:
            domdoc = minidom.parse(_file).documentElement
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
                        key_id = override.attributes["id"].value
                        node = override.attributes.get("label")
                        label = node.value if node else ""
                        node = override.attributes.get("group")
                        group = node.value if node else ""
                        tuples[key_id] = (label, group)
                    theme.key_label_overrides = tuples

                # read all other members
                for name, _type, _default in Theme.attributes:
                    if not name in ["color_scheme_basename",
                                    "key_label_overrides"]:
                        value = utils.xml_get_text(domdoc, name)
                        if not value is None:
                            if _type == "i":
                                value = int(value)
                            setattr(theme, name, value)

                theme.filename = filename
                theme.is_system = is_system
                theme.system_exists = is_system
                result = theme
            except Exceptions.ThemeFileError, (ex):
                raise Exceptions.ThemeFileError(_("Error loading ")
                    + filename, chained_exception = ex)
            finally:
                domdoc.unlink()

        finally:
            _file.close()

        return result

    def save_as(self, basename, name):
        """ Save this theme under a new name. """
        self.filename = self.build_user_filename(basename)
        self.name = name
        self.save()

    def save(self):
        """ Save this theme. """

        domdoc = minidom.Document()
        try:
            theme_element = domdoc.createElement("theme")
            theme_element.setAttribute("name", self.name)
            domdoc.appendChild(theme_element)

            for name, _type, _default in self.attributes:
                if name == "color_scheme_basename":
                    element = domdoc.createElement("color_scheme")
                    text = domdoc.createTextNode(self.color_scheme_basename)
                    element.appendChild(text)
                    theme_element.appendChild(element)
                elif name == "key_label_overrides":
                    overrides_element = \
                            domdoc.createElement("key_label_overrides")
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
                    if _type == "i":
                        value = str(value)
                    element = domdoc.createElement(name)
                    text = domdoc.createTextNode(value)
                    element.appendChild(text)
                    theme_element.appendChild(element)

            ugly_xml = domdoc.toprettyxml(indent='  ')
            pattern = re.compile('>\n\s+([^<>\s].*?)\n\s+</', re.DOTALL)
            pretty_xml = pattern.sub('>\g<1></', ugly_xml)

            with open(self.filename, "w") as _file:
                _file.write(pretty_xml.encode("UTF-8"))

        except Exception, (ex):
            raise Exceptions.ThemeFileError(_("Error loading ")
                + self.filename, chained_exception = ex)
        finally:
            domdoc.unlink()


class ColorScheme:
    """
    ColorScheme defines the colors of onboards keyboard.
    Each key or groups of keys may have their own individual colors.
    Any color definition may be omitted. Undefined colors fall back
    to color scheme defaults first, then to hard coded default colors.
    """
    def __init__(self):
        self.filename = ""
        self.is_system = False
        self.name = ""

        # all colors are 4 component arrays, rgba
        self.default_layer_fill_color = [0.0, 0.0, 0.0, 1.0]
        self.default_layer_fill_opacity = 1.0
        self.layer_fill_color = {}
        self.layer_fill_opacity = {}
        self.default_key_opacity = None
        self.key_opacity = {}
        self.key_defaults = {
                "fill":   [0.0, 0.0, 0.0, 1.0],
                "hover":  [0.0, 0.0, 0.0, 1.0],
                "pressed":[0.6, 0.6, 0.6, 1.0],
                "latched":[0.5, 0.5, 0.5, 1.0],
                "locked": [1.0, 0.0, 0.0, 1.0],
                "scanned":[0.45, 0.45, 0.7, 1.0],
                "stroke": [0.0, 0.0, 0.0, 1.0],
                "label":  [0.0, 0.0, 0.0, 1.0],
                }
        self.key_colors = {}

    @property
    def basename(self):
        """ Returns the file base name of the color scheme. """
        return os.path.splitext(os.path.basename(self.filename))[0]

    def get_key_rgba(self, key, color_name):
        """
        Returns the color of the given name for the given key.

        @type  key_id: str
        @param key_id: key identifier as defined in the layout.
        @type  color_name: str
        @param color_name: One of "fill", "stroke", "pressed", ...
                           See self.key_defaults for all possible names.
        """
        # Get set of colors defined for key_id
        colors = self.key_colors.get(key.theme_id, {}) # try special theme id
        if not colors:
            colors = self.key_colors.get(key.id, {})   # fall back to regular id

        # Special case: don't show latched state for layer buttons
        if key.is_layer_button():
            if color_name in ["latched"] and \
               not color_name in colors:
                   color_name = "fill"

        # get default color
        opacity = self.key_opacity.get(key.theme_id) # try special theme id
        if opacity is None:
            opacity = self.key_opacity.get(key.id)   # fall back to regular id

        if not opacity is None:
            # if given, apply key opacity as alpha to all default colors
            rgba_default = self.key_defaults[color_name][:3] + [opacity]
        else:
            opacity = self.default_key_opacity
            if not opacity is None:
                rgba_default = self.key_defaults[color_name][:3] + [opacity]
            else:
                rgba_default = self.key_defaults[color_name]

        # Special case: default color of layer buttons is the layer fill color
        # The color scheme can override this default.
        if key.is_layer_button() and \
           color_name == "fill" and \
           not color_name in colors:
            layer_index = key.get_layer_index()
            rgba_default = self.get_layer_fill_rgba(layer_index)

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

    def get_layer_fill_rgba(self, layer_index):
        """
        Returns the background fill color of the layer with the given index.
        """
        rgba = self.layer_fill_color.get(layer_index,
                                        self.default_layer_fill_color)
        rgba[3] = self.layer_fill_opacity.get(layer_index,
                                        self.default_layer_fill_opacity)
        return rgba

    @staticmethod
    def user_path():
        """ Returns the path of the user directory for color schemes. """
        return os.path.join(config.user_dir, "themes/")

    @staticmethod
    def system_path():
        """ Returns the path of the system directory for color schemes. """
        return os.path.join(config.install_dir, "themes")

    @staticmethod
    def extension():
        """ Returns the file extension of color scheme files """
        return "colors"

    @staticmethod
    def get_merged_color_schemes():
        """
        Merge system and user color schemes.
        User color schemes take precedence and hide system color schemes.
        """
        system_color_schemes = ColorScheme.load_color_schemes(True)
        user_color_schemes = ColorScheme.load_color_schemes(False)
        color_schemes = dict((t.basename, t) for t in system_color_schemes)
        for scheme in user_color_schemes:
            color_schemes[scheme.basename] = scheme
        return color_schemes

    @staticmethod
    def load_color_schemes(is_system=False):
        """
        Load all color schemes from either the user or the system directory.
        """
        color_schemes = []

        if is_system:
            path = ColorScheme.system_path()
        else:
            path = ColorScheme.user_path()

        filenames = ColorScheme.find_color_schemes(path)
        for filename in filenames:
            color_scheme = ColorScheme.load(filename, is_system)
            color_schemes.append(color_scheme)
        return color_schemes

    @staticmethod
    def find_color_schemes(path):
        """
        Returns the full path names of all color schemes found in the given path.
        """
        files = os.listdir(path)
        color_schemes = []
        for filename in files:
            if filename.endswith(ColorScheme.extension()):
                color_schemes.append(os.path.join(path, filename))
        return color_schemes

    @staticmethod
    def load(filename, is_system=False):
        """ Load a color scheme and return it as a new object. """

        color_scheme = None

        _file = open(filename)
        try:
            domdoc = minidom.parse(_file).documentElement
            try:
                color_scheme = ColorScheme()
                color_scheme.name = domdoc.attributes["name"].value

                # layer colors
                layers = domdoc.getElementsByTagName("layer")
                if not layers: 
                    # Still accept "pane" for backwards compatibility
                    layers = domdoc.getElementsByTagName("pane")
                for i, layer in enumerate(layers):
                    attrib = "fill"
                    if layer.hasAttribute(attrib):
                        value = layer.attributes[attrib].value
                        rgba = [hexstring_to_float(value[1:3])/255,
                        hexstring_to_float(value[3:5])/255,
                        hexstring_to_float(value[5:7])/255,
                        1]
                        color_scheme.layer_fill_color[i] = rgba

                    oattrib = attrib + "-opacity"
                    if layer.hasAttribute(oattrib):
                        opacity = float(layer.attributes[oattrib].value)
                        color_scheme.layer_fill_opacity[i] = opacity

                # key colors
                used_keys = {}
                for group in domdoc.getElementsByTagName("key_group"):

                    # default colors are applied to all keys
                    # not found in the color scheme
                    default_group = False
                    if group.hasAttribute("default"):
                        default_group = bool(group.attributes["default"].value)

                    # read key ids
                    text = "".join([n.data for n in group.childNodes])
                    ids = [x for x in re.findall('\w+(?:[.][\w-]+)?', text) if x]

                    # check for duplicate key definitions
                    for key_id in ids:
                        if key_id in used_keys:
                            raise ValueError(_("Duplicate key_id '{}' found "
                              "in color scheme file. "
                              "Key_ids must occur only once."
                             .format(key_id)))
                    used_keys.update(zip(ids, ids))

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
                                    value = colors.get(attrib, [.0, .0, .0])
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
                                    colors = key_colors.get(key_id, {})
                                    value = colors.get(attrib, [1])
                                    if len(value) == 1: # no rgb yet?
                                        colors[attrib] = [opacity]
                                    else:
                                        colors[attrib] = value[:3] + [opacity]
                                    key_colors[key_id] = colors

                    # read main opacity setting
                    # applies to all colors that don't have their own opacity set
                    if group.hasAttribute("opacity"):
                        value = float(group.attributes["opacity"].value)
                        if default_group:
                            color_scheme.default_key_opacity = value
                        else:
                            for key_id in ids:
                                color_scheme.key_opacity[key_id] = value

                color_scheme.filename = filename
                color_scheme.is_system = is_system

            except Exception, (ex):
                raise Exceptions.ColorSchemeFileError(_("Error loading ")
                    + filename, chained_exception = ex)
            finally:
                domdoc.unlink()
        finally:
            _file.close()

        return color_scheme


