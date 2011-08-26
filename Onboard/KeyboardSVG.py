#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import with_statement

### Logging ###
import logging
_logger = logging.getLogger("KeyboardSVG")
###############

from gettext import gettext as _
from xml.dom import minidom
import os
import re
import string
import sys

from Onboard             import Exceptions
from Onboard             import KeyCommon
from Onboard.KeyGtk      import RectKey
from Onboard.Keyboard    import Keyboard
from Onboard.KeyboardGTK import KeyboardGTK
from Onboard.Layout      import LayoutBox, LayoutPanel
from Onboard.Appearance  import ColorScheme
from Onboard.utils       import hexstring_to_float, modifiers, Rect

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class KeyboardSVG(config.kbd_render_mixin, Keyboard):
    """
    Keyboard layout loaded from an SVG file.
    """

    def __init__(self, vk, layout_filename, color_scheme_filename):
        config.kbd_render_mixin.__init__(self)
        Keyboard.__init__(self, vk)

        self.svg_cache = {}
        self.color_scheme = None

        self.layout = self._load_layout(layout_filename, color_scheme_filename)

        self.initial_update()

    def destruct(self):
        config.kbd_render_mixin.destruct(self)
        Keyboard.destruct(self)

    def clean(self):
        config.kbd_render_mixin.clean(self)
        Keyboard.clean(self)

    def _load_layout(self, layout_filename, color_scheme_filename):
        self.layout_dir = os.path.dirname(layout_filename)
        self.svg_cache = {}
        layout = None

        self.color_scheme = None
        if color_scheme_filename:
            self.color_scheme = ColorScheme.load(color_scheme_filename)

        f = open(layout_filename)
        try:
            dom = minidom.parse(f).documentElement
            items = self._parse_dom_node(dom)
            if items:
                layout = items[0]
        finally:
            f.close()

        self.svg_cache = {} # Free the memory
        return layout

    def _parse_dom_node(self, dom_node, parent_item = None):
        """ Recursive function to parse one dom node of the layout tree """
        items = []
        for child in dom_node.childNodes:
            if child.nodeType == minidom.Node.ELEMENT_NODE:
                if child.tagName == u"box":
                    item = self._parse_box(child)
                elif child.tagName == u"panel":
                    item = self._parse_panel(child)
                elif child.tagName == u"layer":
                    item = self._parse_layer(child)
                elif child.tagName == u"key":
                    item = self._parse_key(child, parent_item)
                else:
                    item = None

                if item:
                    item.parent = parent_item
                    item.items = self._parse_dom_node(child, item)
                    items.append(item)

        return items

    def _parse_dom_node_item(self, node, item):
        """ Parses common properties of all LayoutItems """
        if node.hasAttribute("id"):
            item.id = node.attributes["id"].value
        if node.hasAttribute("layer"):
            item.layer = node.attributes["layer"].value
        if node.hasAttribute("filename"):
            item.filename = node.attributes["filename"].value
        if node.hasAttribute("visible"):
            item.visible = node.attributes["visible"].value
        if node.hasAttribute("border"):
            item.border = float(node.attributes["border"].value)

    def _parse_box(self, node):
        item = LayoutBox()
        self._parse_dom_node_item(node, item)
        if node.hasAttribute("orientation"):
            item.horizontal = \
                node.attributes["orientation"].value.lower() == "horizontal"
        if node.hasAttribute("spacing"):
            item.spacing = float(node.attributes["spacing"].value)
        return item

    def _parse_panel(self, node):
        item = LayoutPanel()
        self._parse_dom_node_item(node, item)
        return item

    def _parse_layer(self, node):
        item = LayoutLayer()
        self._parse_dom_node_item(node, item)
        return item

    def _parse_key(self, node, parent):
        key = RectKey()
        key.parent = parent # assign parent early to make get_filename() work

        id = node.attributes["id"].value
        key.id = id

        if node.hasAttribute("char"):
            key.action = node.attributes["char"].value
            key.action_type = KeyCommon.CHAR_ACTION
        elif node.hasAttribute("keysym"):
            value = node.attributes["keysym"].value
            key.action_type = KeyCommon.KEYSYM_ACTION
            if value[1] == "x":#Deals for when keysym is hex
                key.action = string.atoi(value,16)
            else:
                key.action = string.atoi(value,10)
        elif node.hasAttribute("keypress_name"):
            key.action = node.attributes["keypress_name"].value
            key.action_type = KeyCommon.KEYPRESS_NAME_ACTION
        elif node.hasAttribute("modifier"):
            try:
                key.action = modifiers[
                            node.attributes["modifier"].value]
            except KeyError, (strerror):
                raise Exception("Unrecognised modifier %s in" \
                    "definition of %s" (strerror, key.id))
            key.action_type = KeyCommon.MODIFIER_ACTION

        elif node.hasAttribute("macro"):
            key.action = node.attributes["macro"].value
            key.action_type = KeyCommon.MACRO_ACTION
        elif node.hasAttribute("script"):
            key.action = node.attributes["script"].value
            key.action_type = KeyCommon.SCRIPT_ACTION
        elif node.hasAttribute("keycode"):
            key.action = string.atoi(
                node.attributes["keycode"].value)
            key.action_type = KeyCommon.KEYCODE_ACTION
        elif node.hasAttribute("button"):
            key.action = key.id[:]
            key.action_type = KeyCommon.BUTTON_ACTION
        elif node.hasAttribute("draw_only") and \
             node.attributes["draw_only"].value.lower() == "true":
            key.action = None
            key.action_type = None
        else:
            raise Exceptions.LayoutFileError(key.id
                + " key does not have an action defined")

        # get the size group of the key
        if node.hasAttribute("group"):
            group_name = node.attributes["group"].value
        else:
            group_name = "_default"

        labels = [u"",u"",u"",u"",u""]
        #if label specified search for modified labels.
        if node.hasAttribute("label"):
            labels[0] = node.attributes["label"].value
            if node.hasAttribute("cap_label"):
                labels[1] = node.attributes["cap_label"].value
            if node.hasAttribute("shift_label"):
                labels[2] = node.attributes["shift_label"].value
            if node.hasAttribute("altgr_label"):
                labels[3] = node.attributes["altgr_label"].value
            if node.hasAttribute("altgrNshift_label"):
                labels[4] = \
                    node.attributes["altgrNshift_label"].value
        # If key is a macro (snippet) generate label from number.
        elif key.action_type == KeyCommon.MACRO_ACTION:
            label, text = config.snippets.get(string.atoi(key.action), \
                                                       (None, None))
            if not label:
                labels[0] = u"%s\n%s" % (_("Snippet"), key.action)
            else:
                labels[0] = label.replace(u"\\n", u"\n")
        # Get labels from keyboard.
        else:
            if key.action_type == KeyCommon.KEYCODE_ACTION:
                if self.vk: # xkb keyboard found?
                    labDic = self.vk.labels_from_keycode(key.action)
                    labDic = [x.decode("UTF-8") for x in labDic]
                    labels = (labDic[0],labDic[2],labDic[1],
                                            labDic[3],labDic[4])
                else:
                    if key.id.upper() == "SPCE":
                        labels = [u"No X keyboard found, retrying..."]*5
                    else:
                        labels = [u"?"]*5

        # Translate labels - Gettext behaves oddly when translating
        # empty strings
        key.labels = [ lab and _(lab) or None for lab in labels ]

        # replace label and size group with the themes overrides
        label_overrides = config.theme.key_label_overrides
        override = label_overrides.get(key.id)
        if override:
            olabel, ogroup = override
            if olabel:
                key.labels = [olabel[:] for l in key.labels]
                if ogroup:
                    group_name = ogroup[:]

        key.group = group_name

        if node.hasAttribute("font_offset_x"):
            offset_x = \
                float(node.attributes["font_offset_x"].value)
        else:
            offset_x = config.DEFAULT_LABEL_OFFSET[0]

        if node.hasAttribute("font_offset_y"):
            offset_y = \
                float(node.attributes["font_offset_y"].value)
        else:
            offset_y = config.DEFAULT_LABEL_OFFSET[1]
        key.label_offset = (offset_x, offset_y)

        if node.hasAttribute("label_x_align"):
            key.label_x_align = float(node.attributes["label_x_align"].value)
        if node.hasAttribute("label_y_align"):
            key.label_y_align = float(node.attributes["label_y_align"].value)

        if node.hasAttribute("sticky"):
            sticky = node.attributes["sticky"].value.lower()
            if sticky == "true":
                key.sticky = True
            elif sticky == "false":
                key.sticky = False
            else:
                raise Exception( "'sticky' attribute had an"
                    "invalid value: %s when parsing key %s"
                    % (sticky, key.id))
        else:
            key.sticky = False

        if node.hasAttribute("tooltip"):
            key.tooltip = node.attributes["tooltip"].value

        # old colors as fallback
        rgba = [0.9, 0.85, 0.7]
        key.rgba         = rgba
        key.hover_rgba   = rgba
        key.pressed_rgba = rgba
        key.latched_rgba = [0.5, 0.5, 0.5, 1.0]
        key.locked_rgba  = [1.0, 0.0, 0.0, 1.0]
        key.scanned_rgba = [0.45, 0.45, 0.7, 1.0]
        key.stroke_rgba  = [0.0, 0.0, 0.0, 1.0]
        key.label_rgba   = [0.0, 0.0, 0.0, 1.0]

        # get colors from color scheme
        color_scheme = self.color_scheme
        if color_scheme:
            key.rgba         = color_scheme.get_key_rgba(key, "fill")
            key.hover_rgba   = color_scheme.get_key_rgba(key, "hover")
            key.pressed_rgba = color_scheme.get_key_rgba(key, "pressed")
            key.latched_rgba = color_scheme.get_key_rgba(key, "latched")
            key.locked_rgba  = color_scheme.get_key_rgba(key, "locked")
            key.scanned_rgba = color_scheme.get_key_rgba(key, "scanned")
            key.stroke_rgba  = color_scheme.get_key_rgba(key, "stroke")
            key.label_rgba   = color_scheme.get_key_rgba(key, "label")

        # get key geometry from the closest svg file
        filename = key.get_filename()
        if filename:
            svg_keys = self._get_svg_keys(filename)
            if svg_keys:
                svg_key = svg_keys.get(key.id)
                if svg_key:
                    key.location = svg_key.location
                    key.geometry = svg_key.geometry
                    key.context.log_rect = Rect(svg_key.location[0],
                                                svg_key.location[1],
                                                svg_key.geometry[0],
                                                svg_key.geometry[1])
                    return key

        return None  # ignore keys not found in an svg file


    def _get_svg_keys(self, filename):
        svg_keys = self.svg_cache.get(filename)
        if svg_keys is None:
            svg_keys = self._load_svg_keys(filename)
            self.svg_cache[filename] = svg_keys # Don't load it again next time

        return svg_keys

    def _load_svg_keys(self, filename):
        filename = os.path.join(self.layout_dir, filename)
        try:
            with open(filename) as svg_file:
                svg_dom = minidom.parse(svg_file).documentElement
                svg_keys = self._parse_svg(svg_dom)

        except Exception, (exception):
            raise Exceptions.LayoutFileError(_("Error loading ")
                + filename, chained_exception = exception)

        return svg_keys

    def _parse_svg(self, svg_dom):
        keys = {}
        for rect in svg_dom.getElementsByTagName("rect"):
            id = rect.attributes["id"].value

            pos  = (float(rect.attributes['x'].value),
                    float(rect.attributes['y'].value))
            size = (float(rect.attributes['width'].value),
                    float(rect.attributes['height'].value))

            # Use RectKey as cache for svg provided properties.
            # This key instance doesn't enter the layout and will
            # be discarded after the layout tree has been loaded.
            key = RectKey(id, pos, size)

            keys[id] = key

        return keys

