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

        self.layout = self._load_layout(layout_filename, color_scheme_filename)

        self.initial_update()

    def destruct(self):
        config.kbd_render_mixin.destruct(self)
        Keyboard.destruct(self)

    def cleanup(self):
        config.kbd_render_mixin.cleanup(self)
        Keyboard.cleanup(self)

    def _load_layout(self, layout_filename, color_scheme_filename):
        self.layout_dir = os.path.dirname(layout_filename)
        self.svg_cache = {}
        layout = None

        if color_scheme_filename:
            self.color_scheme = ColorScheme.load(color_scheme_filename)

        f = open(layout_filename)
        try:
            dom = minidom.parse(f).documentElement

            # check layout format
            format = 1.0
            if dom.hasAttribute("format"):
               format = float(dom.attributes["format"].value)

            if format >= 2.0:   # layout-tree format
                items = self._parse_dom_node(dom)
            else:
                items = self._parse_legacy_layout(dom)

            if items:
                layout = items[0]
        finally:
            f.close()

        self.svg_cache = {} # Free the memory
        return layout

    def _parse_dom_node(self, dom_node, parent_item = None):
        """ Recursive function to parse all dom nodes of the layout tree """
        items = []
        for child in dom_node.childNodes:
            if child.nodeType == minidom.Node.ELEMENT_NODE:
                if child.tagName == u"box":
                    item = self._parse_box(child)
                elif child.tagName == u"panel":
                    item = self._parse_panel(child)
                elif child.tagName == u"key":
                    item = self._parse_key(child, parent_item)
                else:
                    if child.tagName == u"column":    # scanning column
                        self._parse_scan_column(child, parent_item)
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
            item.layer_id = node.attributes["layer"].value
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

    def _parse_scan_column(self, node, parent):
        column = []
        for scanKey in node.getElementsByTagName("scankey"):
            column.append(scanKey.attributes["id"].value)
        columns = parent.scan_columns
        if not columns:
            columns = []
        columns.append(column)
        parent.scan_columns = columns

    def _parse_key(self, node, parent):
        key = RectKey()
        key.parent = parent # assign parent early to make get_filename() work

        # parse standard layout item attributes
        self._parse_dom_node_item(node, key)

        attributes = dict(node.attributes.items())
        self._init_key(key, attributes)

        # get key geometry from the closest svg file
        filename = key.get_filename()
        if not filename:
            _logger.warning(_("Ignoring key '{}'."
                              " No svg filename defined.").format(key.theme_id))
        else:
            svg_keys = self._get_svg_keys(filename)
            svg_key = None
            if svg_keys:
                svg_key = svg_keys.get(key.id)
                if not svg_key:
                    _logger.warning(_("Ignoring key '{}'."
                                      " Not found in '{}'.") \
                                    .format(key.theme_id, filename))
                else:
                    key.location = svg_key.location
                    key.geometry = svg_key.geometry
                    key.context.log_rect = Rect(svg_key.location[0],
                                                svg_key.location[1],
                                                svg_key.geometry[0],
                                                svg_key.geometry[1])
                    return key

        return None  # ignore keys not found in an svg file

    def _init_key(self, key, attributes):
        # Re-parse the id to distinguish between the short key_id
        # and the optional longer theme_id.
        # The theme id has the form <id>.<arbitrary identifier>, where
        # the identifier may be the name of the layout layer the key is
        # defined in, e.g. 'DELE.compact-alpha'.
        value = attributes["id"]
        key.id = value.split(".")[0]
        key.theme_id = value


        if "char" in attributes:
            key.action = attributes["char"]
            key.action_type = KeyCommon.CHAR_ACTION
        elif "keysym" in attributes:
            value = attributes["keysym"]
            key.action_type = KeyCommon.KEYSYM_ACTION
            if value[1] == "x":#Deals for when keysym is hex
                key.action = string.atoi(value,16)
            else:
                key.action = string.atoi(value,10)
        elif "keypress_name" in attributes:
            key.action = attributes["keypress_name"]
            key.action_type = KeyCommon.KEYPRESS_NAME_ACTION
        elif "modifier" in attributes:
            try:
                key.action = modifiers[attributes["modifier"]]
            except KeyError, (strerror):
                raise Exception("Unrecognised modifier %s in" \
                    "definition of %s" (strerror, key.id))
            key.action_type = KeyCommon.MODIFIER_ACTION

        elif "macro" in attributes:
            key.action = attributes["macro"]
            key.action_type = KeyCommon.MACRO_ACTION
        elif "script" in attributes:
            key.action = attributes["script"]
            key.action_type = KeyCommon.SCRIPT_ACTION
        elif "keycode" in attributes:
            key.action = string.atoi(
                attributes["keycode"])
            key.action_type = KeyCommon.KEYCODE_ACTION
        elif "button" in attributes:
            key.action = key.id[:]
            key.action_type = KeyCommon.BUTTON_ACTION
        elif "draw_only" in attributes and \
             attributes["draw_only"].lower() == "true":
            key.action = None
            key.action_type = None
        else:
            raise Exceptions.LayoutFileError(key.id
                + " key does not have an action defined")

        # get the size group of the key
        if "group" in attributes:
            group_name = attributes["group"]
        else:
            group_name = "_default"

        # get the optional image filename
        if "image" in attributes:
            key.image_filename = attributes["image"]

        labels = [u"",u"",u"",u"",u""]
        #if label specified search for modified labels.
        if "label" in attributes:
            labels[0] = attributes["label"]
            if "cap_label" in attributes:
                labels[1] = attributes["cap_label"]
            if "shift_label" in attributes:
                labels[2] = attributes["shift_label"]
            if "altgr_label" in attributes:
                labels[3] = attributes["altgr_label"]
            if "altgrNshift_label" in attributes:
                labels[4] = \
                    attributes["altgrNshift_label"]
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

        if "font_offset_x" in attributes:
            offset_x = float(attributes["font_offset_x"])
        else:
            offset_x = config.DEFAULT_LABEL_OFFSET[0]

        if "font_offset_y" in attributes:
            offset_y = \
                float(attributes["font_offset_y"])
        else:
            offset_y = config.DEFAULT_LABEL_OFFSET[1]
        key.label_offset = (offset_x, offset_y)

        if "label_x_align" in attributes:
            key.label_x_align = float(attributes["label_x_align"])
        if "label_y_align" in attributes:
            key.label_y_align = float(attributes["label_y_align"])

        if "sticky" in attributes:
            sticky = attributes["sticky"].lower()
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

        if "tooltip" in attributes:
            key.tooltip = attributes["tooltip"]

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
        if self.color_scheme:
            get_key_rgba = self.color_scheme.get_key_rgba
            key.rgba                = get_key_rgba(key, "fill")
            key.hover_rgba          = get_key_rgba(key, "hover")
            key.pressed_rgba        = get_key_rgba(key, "pressed")
            key.latched_rgba        = get_key_rgba(key, "latched")
            key.locked_rgba         = get_key_rgba(key, "locked")
            key.scanned_rgba        = get_key_rgba(key, "scanned")
            key.stroke_rgba         = get_key_rgba(key, "stroke")
            key.label_rgba          = get_key_rgba(key, "label")
            key.dwell_progress_rgba = get_key_rgba(key, "dwell-progress")
            key.color_scheme = self.color_scheme

            is_key_default_color = self.color_scheme.is_key_default_color
            key.pressed_rgba_is_default = is_key_default_color(key, "pressed")



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


    # --------------------------------------------------------------------------
    # Legacy pane layout support
    # --------------------------------------------------------------------------
    def _parse_legacy_layout(self, dom_node):

        # parse panes
        panes = []
        is_scan = False
        for i, pane_node in enumerate(dom_node.getElementsByTagName("pane")):
            item = LayoutPanel()
            item.layer_id = "layer {}".format(i)

            item.id       = pane_node.attributes["id"].value
            item.filename = pane_node.attributes["filename"].value

            # parse keys
            keys = []
            for node in pane_node.getElementsByTagName("key"):
                keys.append(self._parse_key(node, item))
            item.set_items(keys)

            # parse scan columns
            for node in pane_node.getElementsByTagName("column"):
                self._parse_scan_column(node, item)
                is_scan = True

            panes.append(item)

        layer_area = LayoutPanel()
        layer_area.id = "layer_area"
        layer_area.set_items(panes)

        # find the most frequent key width
        histogram = {}
        for key in layer_area.iter_keys():
            w = key.get_border_rect().w
            histogram[w] = histogram.get(w, 0) + 1
        most_frequent_width = max(zip(histogram.values(), histogram.keys()))[1] \
                              if histogram else 18

        # Legacy onboard had automatic tab-keys for pane switching.
        # Simulate this by generating layer buttons from scratch.
        keys = []
        group = "__layer_buttons__"
        widen = 1.4 if not is_scan else 1.0
        rect = Rect(0, 0, most_frequent_width * widen, 20)

        key = RectKey()
        attributes = {}
        attributes["id"]     = "hide"
        attributes["group"]  = group
        attributes["label"]  = "Hide"
        attributes["button"] = "true"
        self._init_key(key, attributes)
        key.location = (rect.x, rect.y)
        key.geometry = (rect.w, rect.h)
        key.context.log_rect = rect
        keys.append(key)

        key = RectKey()
        attributes = {}
        attributes["id"]     = "move"
        attributes["group"]  = group
        attributes["image"]  = "move.svg"
        attributes["button"] = "true"
        self._init_key(key, attributes)
        key.location = (rect.x, rect.y)
        key.geometry = (rect.w, rect.h)
        key.context.log_rect = rect
        keys.append(key)

        if len(panes) > 1:
            for i, pane in enumerate(panes):
                key = RectKey()
                attributes = {}
                attributes["id"]     = "layer{}".format(i)
                attributes["group"]  = group
                attributes["label"]  = pane.id
                attributes["button"] = "true"
                self._init_key(key, attributes)
                key.location = (rect.x, rect.y)
                key.geometry = (rect.w, rect.h)
                key.context.log_rect = rect

                keys.append(key)

        layer_switch_column = LayoutBox()
        layer_switch_column.horizontal = False
        layer_switch_column.set_items(keys)

        layout = LayoutBox()
        layout.border = 1
        layout.spacing = 2
        layout.set_items([layer_area, layer_switch_column])

        return [layout]



