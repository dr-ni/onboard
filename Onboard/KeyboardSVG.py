# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

### Logging ###
import logging
_logger = logging.getLogger("KeyboardSVG")
###############

import os
import re
import sys
import shutil
from gettext import gettext as _
from xml.dom import minidom

from Onboard             import Exceptions
from Onboard             import KeyCommon
from Onboard.KeyGtk      import RectKey
from Onboard.Keyboard    import Keyboard
from Onboard.KeyboardGTK import KeyboardGTK
from Onboard.Layout      import LayoutBox, LayoutPanel
from Onboard.Appearance  import ColorScheme
from Onboard.utils       import hexstring_to_float, modifiers, Rect, toprettyxml

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class KeyboardSVG(config.kbd_render_mixin, Keyboard):
    """
    Keyboard layout loaded from an SVG file.
    """

    format = 2.0

    def __init__(self, vk, layout_filename, color_scheme_filename):
        config.kbd_render_mixin.__init__(self)
        Keyboard.__init__(self, vk)

        self.svg_cache = {}

        self.layout = self._load_layout(layout_filename, color_scheme_filename)

        self.initial_update()

    def initial_update(self):
        config.kbd_render_mixin.initial_update(self)
        Keyboard.initial_update(self)

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
                _logger.warning(_("Loading legacy layout format '{}'. "
                            "Please consider upgrading to current format '{}'"
                            ).format(format, self.format))
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
                if child.tagName == "box":
                    item = self._parse_box(child)
                elif child.tagName == "panel":
                    item = self._parse_panel(child)
                elif child.tagName == "key":
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
        if node.hasAttribute("group"):
            item.group = node.attributes["group"].value
        if node.hasAttribute("layer"):
            item.layer_id = node.attributes["layer"].value
        if node.hasAttribute("filename"):
            item.filename = node.attributes["filename"].value
        if node.hasAttribute("visible"):
            item.visible = node.attributes["visible"].value == "true"
        if node.hasAttribute("border"):
            item.border = float(node.attributes["border"].value)
        if node.hasAttribute("expand"):
            item.expand = node.attributes["expand"].value == "true"

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

    def _parse_key(self, node, parent):
        key = RectKey()
        key.parent = parent # assign parent early to make get_filename() work

        # parse standard layout item attributes
        self._parse_dom_node_item(node, key)

        attributes = dict(list(node.attributes.items()))
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
                    key.set_border_rect(svg_key.get_border_rect().copy())
                    return key

        return None  # ignore keys not found in an svg file

    def _init_key(self, key, attributes):
        # Re-parse the id to distinguish between the short key_id
        # and the optional longer theme_id.
        key.set_id(attributes["id"])

        if "char" in attributes:
            key.action = attributes["char"]
            key.action_type = KeyCommon.CHAR_ACTION
        elif "keysym" in attributes:
            value = attributes["keysym"]
            key.action_type = KeyCommon.KEYSYM_ACTION
            if value[1] == "x":#Deals for when keysym is hex
                key.action = int(value,16)
            else:
                key.action = int(value,10)
        elif "keypress_name" in attributes:
            key.action = attributes["keypress_name"]
            key.action_type = KeyCommon.KEYPRESS_NAME_ACTION
        elif "modifier" in attributes:
            try:
                key.action = modifiers[attributes["modifier"]]
            except KeyError as xxx_todo_changeme:
                (strerror) = xxx_todo_changeme
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
            key.action = int(attributes["keycode"])
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

        labels = ["","","","",""]
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
            label, text = config.snippets.get(int(key.action), \
                                                       (None, None))
            tooltip = _("Snippet {}").format(key.action)
            if not label:
                #labels[0] = u"%s\n%s" % (_("Snippet"), key.action)
                #labels[0] = "     ({})     ".format(key.action)
                labels[0] = "     --     "
                # Snippet n, unassigned - click to edit
                tooltip += _(", unassigned")
            else:
                labels[0] = label.replace("\\n", "\n")
            key.tooltip = tooltip

        # Get labels from keyboard.
        else:
            if key.action_type == KeyCommon.KEYCODE_ACTION:
                if self.vk: # xkb keyboard found?
                    labDic = self.vk.labels_from_keycode(key.action)
                    if sys.version_info.major == 2:
                        labDic = [x.decode("UTF-8") for x in labDic]
                    labels = (labDic[0],labDic[2],labDic[1],
                                            labDic[3],labDic[4])
                else:
                    if key.id.upper() == "SPCE":
                        labels = ["No X keyboard found, retrying..."]*5
                    else:
                        labels = ["?"]*5

        # Translate labels - Gettext behaves oddly when translating
        # empty strings
        key.labels = [ lab and _(lab) or None for lab in labels ]

        # replace label and size group with the themes overrides
        label_overrides = config.theme_settings.key_label_overrides
        override = label_overrides.get(key.id)
        if override:
            olabel, ogroup = override
            if olabel:
                key.labels = [olabel[:] for l in key.labels]
                if ogroup:
                    group_name = ogroup[:]


        key.group = group_name

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

        if "scannable" in attributes:
            if attributes["scannable"].lower() == 'false':
                key.scannable = False

        if "scan_priority" in attributes:
            key.scan_priority = int(attributes["scan_priority"])

        if "tooltip" in attributes:
            key.tooltip = attributes["tooltip"]

        key.color_scheme = self.color_scheme



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

        except Exception as xxx_todo_changeme1:
            (exception) = xxx_todo_changeme1
            raise Exceptions.LayoutFileError(_("Error loading ")
                + filename, chained_exception = exception)

        return svg_keys

    def _parse_svg(self, svg_dom):
        keys = {}
        for rect in svg_dom.getElementsByTagName("rect"):
            id = rect.attributes["id"].value

            rect = Rect(float(rect.attributes['x'].value),
                        float(rect.attributes['y'].value),
                        float(rect.attributes['width'].value),
                        float(rect.attributes['height'].value))

            # Use RectKey as cache for svg provided properties.
            # This key instance doesn't enter the layout and will
            # be discarded after the layout tree has been loaded.
            key = RectKey(id, rect)

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
                key = self._parse_key(node, item)                
                if key:
                    # some keys have changed since Onboard 0.95
                    if key.id == "middleClick":
                        key.set_id("middleclick")
                        key.action_type = KeyCommon.BUTTON_ACTION
                    if key.id == "secondaryClick":
                        key.set_id("secondaryclick")
                        key.action_type = KeyCommon.BUTTON_ACTION
                        
                    keys.append(key)
                    
            item.set_items(keys)

            # check for scan columns
            if pane_node.getElementsByTagName("column"):
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
        most_frequent_width = max(list(zip(list(histogram.values()), list(histogram.keys()))))[1] \
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
        attributes["image"]  = "close.svg"
        attributes["button"] = "true"
        attributes["scannable"] = "false"
        self._init_key(key, attributes)
        key.set_border_rect(rect.copy())
        keys.append(key)

        key = RectKey()
        attributes = {}
        attributes["id"]     = "move"
        attributes["group"]  = group
        attributes["image"]  = "move.svg"
        attributes["button"] = "true"
        attributes["scannable"] = "false"
        self._init_key(key, attributes)
        key.set_border_rect(rect.copy())
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
                key.set_border_rect(rect.copy())
                keys.append(key)

        layer_switch_column = LayoutBox()
        layer_switch_column.horizontal = False
        layer_switch_column.set_items(keys)

        layout = LayoutBox()
        layout.border = 1
        layout.spacing = 2
        layout.set_items([layer_area, layer_switch_column])

        return [layout]

    @staticmethod
    def copy_layout(src_filename, dst_filename):
        src_dir = os.path.dirname(src_filename)
        dst_dir, name_ext = os.path.split(dst_filename)
        dst_basename, ext = os.path.splitext(name_ext)
        _logger.info(_("copying layout '{}' to '{}'") \
                     .format(src_filename, dst_filename))

        domdoc = None
        svg_filenames = {}
        fallback_layers = {}

        with open(src_filename) as f:
            domdoc = minidom.parse(f)
            keyboard_node = domdoc.documentElement

            # check layout format
            format = 1.0
            if keyboard_node.hasAttribute("format"):
               format = float(keyboard_node.attributes["format"].value)
            keyboard_node.attributes["id"] = dst_basename

            if format < 2.0:   # layout-tree format
                raise Exceptions.LayoutFileError( \
                    _("copy_layouts failed, unsupported layout format '{}'.") \
                    .format(format))
            else:
                # replace the basename of all svg filenames
                for node in KeyboardSVG._iter_dom_nodes(keyboard_node):
                    if KeyboardSVG.is_layout_node(node):
                        if node.hasAttribute("filename"):
                            filename = node.attributes["filename"].value

                            # Create a replacement layer name for the unlikely
                            # case  that the svg-filename doesn't contain a
                            # layer section (as in path/basename-layer.ext).
                            fallback_layer_name = fallback_layers.get(filename,
                                         "Layer" + str(len(fallback_layers)))
                            fallback_layers[filename] = fallback_layer_name

                            # replace the basename of this filename
                            new_filename = KeyboardSVG._replace_basename( \
                                 filename, dst_basename, fallback_layer_name)

                            node.attributes["filename"].value = new_filename
                            svg_filenames[filename] = new_filename

        if domdoc:
            # write the new layout file
            with open(dst_filename, "w") as f:
                xml = toprettyxml(domdoc)
                f.write(xml.encode("UTF-8"))

                # copy the svg files
                for src, dst in list(svg_filenames.items()):

                    dir, name = os.path.split(src)
                    if not dir:
                        src = os.path.join(src_dir, name)
                    dir, name = os.path.split(dst)
                    if not dir:
                        dst = os.path.join(dst_dir, name)

                    _logger.info(_("copying svg file '{}' to '{}'") \
                                 .format(src, dst))
                    shutil.copyfile(src, dst)

    @staticmethod
    def remove_layout(filename):
        for fn in KeyboardSVG.get_layout_svg_filenames(filename):
            os.remove(fn)
        os.remove(filename)

    @staticmethod
    def get_layout_svg_filenames(filename):
        results = []
        domdoc = None
        with open(filename) as f:
            domdoc = minidom.parse(f).documentElement

        if domdoc:
            filenames = {}
            for node in KeyboardSVG._iter_dom_nodes(domdoc):
                if KeyboardSVG.is_layout_node(node):
                    if node.hasAttribute("filename"):
                        fn = node.attributes["filename"].value
                        filenames[fn] = fn

            layout_dir, name = os.path.split(filename)
            results = []
            for fn in list(filenames.keys()):
                dir, name = os.path.split(fn)
                results.append(os.path.join(layout_dir, name))

        return results

    @staticmethod
    def _replace_basename(filename, new_basename, fallback_layer_name):
        dir, name_ext = os.path.split(filename)
        name, ext = os.path.splitext(name_ext)
        components = name.split("-")
        if components:
            basename = components[0]
            if len(components) > 1:
                layer = components[1]
            else:
                layer = fallback_layer_name
            return "{}-{}{}".format(new_basename, layer, ext)
        return ""

    @staticmethod
    def is_layout_node(dom_node):
        return dom_node.tagName in ["box", "panel", "key"]

    @staticmethod
    def _iter_dom_nodes(dom_node):
        """ Recursive generator function to traverse aa dom tree """
        yield dom_node

        for child in dom_node.childNodes:
            if child.nodeType == minidom.Node.ELEMENT_NODE:
                for node in KeyboardSVG._iter_dom_nodes(child):
                    yield node

