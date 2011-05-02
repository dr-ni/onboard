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

from Onboard             import Exceptions
from Onboard.utils       import hexstring_to_float, \
                                unpack_name_value_tuples, pack_name_value_tuples

import Onboard.utils as utils

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class Theme:
    # name, type, default
    attributes = [
            ["color_scheme_basename", "s", ""],
            ["key_style", "s", "flat"],
            ["roundrect_radius", "i", 0],
            ["key_fill_gradient", "i", 0],
            ["key_stroke_gradient", "i", 0],
            ["key_gradient_direction", "i", 0],
            ["key_label_font", "s", ""],
            ["key_label_overrides", "s", ""],
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

    def apply(self):

        filename = self.get_color_scheme_filename()
        if not filename:
            _logger.error(_("Color scheme for theme '%s' not found") % self.filename)
            return False

        config.color_scheme_filename = filename
        for name, type, default in self.attributes:
            if name != "color_scheme_basename":
                setattr(config, name, getattr(self, name))

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
        tuples = unpack_name_value_tuples(self.key_label_overrides)
        t = tuples.get("LWIN")
        if t:
            return t[0] # assumes RWIN=LWIN
        return None

    def get_superkey_size_group(self):
        tuples = unpack_name_value_tuples(self.key_label_overrides)
        t = tuples.get("LWIN")
        if t:
            return t[1] # assumes RWIN=LWIN
        return None

    def set_superkey_label(self, label, size_group):
        tuples = unpack_name_value_tuples(self.key_label_overrides)
        if label is None:
            if "LWIN" in tuples: del tuples["LWIN"]
            if "RWIN" in tuples: del tuples["RWIN"]
        else:
            tuples["LWIN"] = (label, size_group)
            tuples["RWIN"] = (label, size_group)
        self.key_label_overrides = pack_name_value_tuples(tuples)

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
    def system_path():
        return os.path.join(config.install_dir, "themes")

    @staticmethod
    def user_path():
        return "%s/.sok/themes/" % os.path.expanduser("~")

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

                for name, type, default in Theme.attributes:
                    if name != "color_scheme_basename":
                        value = utils.xml_get_text(domdoc, name)
                        if not value is None:
                            if type == "i":
                                value = int(value)
                            setattr(theme, name, value)

                theme.filename = filename
                theme.system = system
                theme.system_exists = system
                result = theme
            except Exception, (exception):
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
        cr = "\n"
        text = r"""<?xml version="1.0"?>""" + cr
        text +=r"""<theme name="%s">""" % self.name + cr

        for name, type, default in self.attributes:
            if name == "color_scheme_basename":
                text += r"""    <color_scheme>%s</color_scheme>""" \
                        % self.color_scheme_basename + cr
            else:
                value = getattr(self, name)
                if type == "i":
                    value = int(value)
                text += r"""    <%s>%s</%s>""" \
                        % (name, value, name) + cr

        text +=r"""</theme>""" + cr

        with open(self.filename, "w") as f:
            f.write(text)


class ColorScheme:
    def __init__(self):
        self.filename = ""
        self.system = False
        self.name = ""

        # all colors as 4 component arrays, rgba
        self.default_pane_fill_color = [0.0, 0.0, 0.0, 1.0]
        self.default_pane_fill_opacity = 1.0
        self.default_key_fill_color = [0.0, 0.0, 0.0, 1.0]
        self.default_key_fill_opacity = 1.0
        self.default_key_stroke_color = [0.0, 0.0, 0.0, 1.0]
        self.default_key_stroke_opacity = 1.0
        self.default_key_label_color = [0.0, 0.0, 0.0, 1.0]
        self.pane_fill_color = {}
        self.pane_fill_opacity = {}
        self.key_fill_opacity = {}
        self.key_fill_color = {}
        self.key_stroke_color = {}
        self.key_stroke_opacity = {}
        self.key_label_color = {}

    @property
    def basename(self):
        return os.path.splitext(os.path.basename(self.filename))[0]

    def get_key_fill_color_rgba(self, key_id):
        rgba = self.key_fill_color.get(key_id,
                                        self.default_key_fill_color)
        rgba[3] = self.key_fill_opacity.get(key_id,
                                        self.default_key_fill_opacity)
        return rgba

    def get_key_stroke_color_rgba(self, key_id):
        rgba = self.key_stroke_color.get(key_id,
                                        self.default_key_stroke_color)
        rgba[3] = self.key_stroke_opacity.get(key_id,
                                        self.default_key_stroke_opacity)
        return rgba

    def get_key_label_rgba(self, key_id):
        return self.key_label_color.get(key_id, self.default_key_label_color)

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
        return "%s/.sok/themes/" % os.path.expanduser("~")

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

                    default = False
                    if group.hasAttribute("default"):
                        default = bool(group.attributes["default"].value)

                    text = "".join([n.data for n in group.childNodes])
                    ids = [x for x in re.split('\W+', text) if x]

                    if group.hasAttribute("fill"):
                        value = group.attributes["fill"].value
                        rgba = [hexstring_to_float(value[1:3])/255,
                        hexstring_to_float(value[3:5])/255,
                        hexstring_to_float(value[5:7])/255,
                        1]#not bothered for now

                        if default:
                            color_scheme.default_key_fill_color = rgba
                        for key_id in ids:
                            color_scheme.key_fill_color[key_id] = rgba

                    if group.hasAttribute("stroke"):
                        value = group.attributes["stroke"].value
                        rgba = [hexstring_to_float(value[1:3])/255,
                        hexstring_to_float(value[3:5])/255,
                        hexstring_to_float(value[5:7])/255,
                        1]#not bothered for now

                        if default:
                            color_scheme.default_key_stroke_color = rgba
                        for key_id in ids:
                            color_scheme.key_stroke_color[key_id] = rgba

                    if group.hasAttribute("label"):
                        value = group.attributes["label"].value
                        rgba = [hexstring_to_float(value[1:3])/255,
                        hexstring_to_float(value[3:5])/255,
                        hexstring_to_float(value[5:7])/255,
                        1]#not bothered for now

                        if default:
                            color_scheme.default_key_label_color = rgba
                        for key_id in ids:
                            color_scheme.key_label_color[key_id] = rgba

                    if group.hasAttribute("fill-opacity"):
                        value = float(group.attributes["fill-opacity"].value)
                        if default:
                            color_scheme.default_key_fill_opacity = value
                        for key_id in ids:
                            color_scheme.key_fill_opacity[key_id] = value

                    if group.hasAttribute("stroke-opacity"):
                        value = float(group.attributes["stroke-opacity"].value)
                        if default:
                            color_scheme.default_key_stroke_opacity = value
                        for key_id in ids:
                            color_scheme.key_stroke_opacity[key_id] = value

                color_scheme.filename = filename
                color_scheme.system = system

            except Exception, (exception):
                raise Exceptions.ColorSchemeFileError(_("Error loading ")
                    + color_scheme_filename, chained_exception = exception)
            finally:
                domdoc.unlink()
        finally:
            f.close()

        return color_scheme


