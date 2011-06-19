#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import with_statement

import os
import string
import re
import traceback

import gobject
import gtk

from xml.dom import minidom

modifiers = {"shift":1,
             "caps":2,
             "control":4,
             "mod1":8,
             "mod2":16,
             "mod3":32,
             "mod4":64,
             "mod5":128}


modDic = {"LWIN" : ("Win",64),
          "RTSH" : ("⇧".decode('utf-8'), 1),
          "LFSH" : ("⇧".decode('utf-8'), 1),
          "RALT" : ("Alt Gr", 128),
          "LALT" : ("Alt", 8),
          "RCTL" : ("Ctrl", 4),
          "LCTL" : ("Ctrl", 4),
          "CAPS" : ("CAPS", 2),
          "NMLK" : ("Nm\nLk",16)}

otherDic = {"RWIN" : "Win",
            "MENU" : "Menu",
            "BKSP" : "⇦".decode("utf-8"),
            "RTRN" : "Return",
            "TAB" : "Tab",
            "INS":"Ins",
            "HOME":"Hm",
            "PGUP": "Pg\nUp",
            "DELE":"Del",
            "END":"End",
            "PGDN":"Pg\nDn",
            "UP":  "↑".decode("utf-8"),
            "DOWN":"↓".decode("utf-8"),
            "LEFT" : "←".decode("utf-8"),
            "RGHT" : "→".decode("utf-8"),
            "KP0" : "0",
            "KP1" : "1",
            "KP2" : "2",
            "KP3" : "3",
            "KP4" : "4",
            "KP5" : "5",
            "KP6" : "6",
            "KP7" : "7",
            "KP8" : "8",
            "KP9" : "9",
            "KPDL":"Del",
            "KPEN": "Ent" }

funcKeys = (("ESC",65307),
            ("F1",65470),
            ("F2",65471),
            ("F3",65472),
            ("F4", 65473),
            ("F5", 65474),
            ("F6",65475),
            ("F7",65476),
            ("F8",65477),
            ("F9",65478),
            ("F10",65479),
            ("F11", 65480),
            ("F12", 65481),
            ("Prnt", 65377),
            ("Scroll", 65300),
            ("Pause", 65299))

keysyms = {"space" : 65408,
           "insert" : 0xff63,
           "home" : 0xff50,
           "page_up" : 0xff55,
           "page_down" : 0xff56,
           "end" :0xff57,
           "delete" : 0xffff,
           "return" : 65293,
           "backspace" : 65288,
           "left" : 0xff51,
           "up" : 0xff52,
           "right" : 0xff53,
           "down" : 0xff54,}

def get_keysym_from_name(name):
    return keysyms[name]

def run_script(script):
    a =__import__(script)
    a.run()

def create_layout_XML(name, vk, keyboard):
    "Reads layout stored within Onboard and outputs it to XML"
    doc = minidom.Document()

    from Onboard.Config import Config
    config = Config()   # config singleton

    keyboard_element = doc.createElement("keyboard")
    keyboard_element.setAttribute("id", name)
    doc.appendChild(keyboard_element)

    template_file \
        = open(os.path.join(config.install_dir, "layouts", "template.svg"))
    template = minidom.parse(template_file)
    template_file.close()

    layout_xml = {}
    for pane in [keyboard.basePane] + keyboard.panes:
        pane_xml = minidom.parseString(template.toxml())
        _create_pane_xml(pane, doc, pane_xml, vk, name)
        svg_filename = "{0}-{1}.svg".format(name, pane.name)
        layout_xml[svg_filename] = pane_xml

    layout_xml[name + ".onboard"] = doc
    return layout_xml

def toprettyxml(doc):
    # Work around http://bugs.python.org/issue5752
    pretty_xml = doc.toprettyxml()
    pretty_xml = re.sub(
           '"[^"]*"',
           lambda m: m.group(0).replace("\n", "&#10;"),
           pretty_xml)
    return pretty_xml

def save_layout_XML(layout_xml, target):
    for filename, doc in layout_xml.items():
        with open(os.path.join(target, filename), "w") as target_file:
            pretty_xml = toprettyxml(doc)
            target_file.write(pretty_xml)

def _create_pane_xml(pane, doc, svgDoc, vk, name):
    """
    @type   pane: Onboard.Pane.Pane
    @param  pane: Pane object that we are creating xml for.

    @type   doc: xml.dom.minidom.Document
    @param  doc: DOM of .onboard layout file.

    @type   svgDoc: xml.dom.minidom.Document.
    @param  svgDoc: DOM of this panes SVG file.

    @type   vk:     Virtkey.Virtkey

    @type   name:   str
    @param  name:   Name of layout to be created.

    """
    from Onboard import KeyGtk
    from Onboard import KeyCommon

    config_element  = _make_pane_config_xml(doc, pane.name,
                        "%s-%s.svg" % (name,pane.name),pane.rgba)

    doc.documentElement.appendChild(config_element)
    svgDoc.documentElement.setAttribute("width", str(pane.size[0]))
    svgDoc.documentElement.setAttribute("height", str(pane.size[1]))

    for group_name, group in pane.key_groups.items():
        for key in group:
            if isinstance(key,KeyGtk.RectKey):
                svgDoc.documentElement.appendChild(make_xml_rect(doc, key))
                doc.toxml()
                config_element.appendChild(_make_key_xml(doc, key, group_name))
                doc.toxml()
            elif key.__class__ == KeyGtk.LineKey:
                print "funky keys not yet implemented"


def _make_pane_config_xml(doc,ident,filename,rgba):

    pane_element = doc.createElement("pane")

    pane_element.setAttribute("id", ident)
    pane_element.setAttribute("filename", filename)
    pane_element.setAttribute("backgroundRed", str(rgba[0]))
    pane_element.setAttribute("backgroundGreen", str(rgba[1]))
    pane_element.setAttribute("backgroundBlue", str(rgba[2]))
    pane_element.setAttribute("backgroundAlpha", str(rgba[3]))

    return pane_element

def make_xml_rect(doc, key):
    rect_element = doc.createElement("rect")

    rect_element.setAttribute("id",     key.name)
    rect_element.setAttribute("x",      str(key.location[0]))
    rect_element.setAttribute("y",      str(key.location[1]))
    rect_element.setAttribute("width",  str(key.geometry[0]))
    rect_element.setAttribute("height", str(key.geometry[1]))
    rgba = [int(colour * 255) for colour in key.rgba]
    rect_element.setAttribute("style",
        "fill:#{0[0]:02x}{0[1]:02x}{0[2]:02x};stroke:#000000;".format(rgba))

    return rect_element

def dec_to_hex_colour(dec):
    hexString = hex(int(255*dec))[2:]
    if len(hexString) == 1:
        hexString = "0" + hexString

    return hexString

def _make_key_xml(doc, key, group):

    # utils.py ought to be a leaf node in the import graph.
    # If there have to be cyclic project imports, at least do them lazily here.
    from Onboard.Config import Config
    import KeyCommon

    config = Config()   # config singleton

    key_element = doc.createElement("key")
    key_element.setAttribute("group", group)

    if key.name in otherDic:
        key_element.setAttribute("label", otherDic[key.name]);
    key_element.setAttribute("id", key.name)

    if key.action_type != KeyCommon.KEYCODE_ACTION \
            and key.action_type != KeyCommon.MACRO_ACTION:
        if key.labels:
            if key.labels[0]:
                key_element.setAttribute("label",             key.labels[0])
            if key.labels[1]:
                key_element.setAttribute("cap_label",         key.labels[1])
            if key.labels[2]:
                key_element.setAttribute("shift_label",       key.labels[2])
            if key.labels[3]:
                key_element.setAttribute("altgr_label",       key.labels[3])
            if key.labels[4]:
                key_element.setAttribute("altgrNshift_label", key.labels[4])

    if key.action_type == KeyCommon.CHAR_ACTION:
        key_element.setAttribute("char", key.action)
    elif key.action_type == KeyCommon.KEYSYM_ACTION:
        key_element.setAttribute("keysym", str(key.action))
    elif key.action_type == KeyCommon.KEYPRESS_NAME_ACTION:
        key_element.setAttribute("keypress_name", str(key.action))
    elif key.action_type == KeyCommon.KEYCODE_ACTION:
        key_element.setAttribute("keycode", str(key.action))
    elif key.action_type == KeyCommon.MODIFIER_ACTION:
        for k,val in modifiers.items():
            if key.action == val:
                key_element.setAttribute("modifier", k)
    elif key.action_type == KeyCommon.MACRO_ACTION:
        key_element.setAttribute("macro", str(key.action))
    elif key.action_type == KeyCommon.SCRIPT_ACTION:
        key_element.setAttribute("script", key.action)

    if key.label_offset != config.DEFAULT_LABEL_OFFSET:
        key_element.setAttribute("font_offset_x", str(key.label_offset[0]))
        key_element.setAttribute("font_offset_y", str(key.label_offset[1]))

    if key.sticky:
        key_element.setAttribute("sticky", "true")
    else:
        key_element.setAttribute("sticky", "false")


    return key_element


def xml_get_text(dom_node, tag_name):
    nodelist = dom_node.getElementsByTagName(tag_name)
    if not nodelist:
        return None
    rc = []
    for node in nodelist[0].childNodes:
        if node.nodeType == node.TEXT_NODE:
            rc.append(node.data)
    return ''.join(rc).strip()
 
def matmult(m, v):
    """ Matrix-vector multiplication """
    nrows = len(m)
    w = [None] * nrows
    for row in range(nrows):
        w[row] = reduce(lambda x,y: x+y, map(lambda x,y: x*y, m[row], v))
    return w

def hexstring_to_float(hexString):
    return float(string.atoi(hexString,16))

class dictproperty(object):
    """ Property implementation for dictionaries """

    class _proxy(object):

        def __init__(self, obj, fget, fset, fdel):
            self._obj = obj
            self._fget = fget
            self._fset = fset
            self._fdel = fdel

        def __getitem__(self, key):
            if self._fget is None:
                raise TypeError, "can't read item"
            return self._fget(self._obj, key)

        def __setitem__(self, key, value):
            if self._fset is None:
                raise TypeError, "can't set item"
            self._fset(self._obj, key, value)

        def __delitem__(self, key):
            if self._fdel is None:
                raise TypeError, "can't delete item"
            self._fdel(self._obj, key)

    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        self._fget = fget
        self._fset = fset
        self._fdel = fdel
        self.__doc__ = doc

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self._proxy(obj, self._fget, self._fset, self._fdel)

def show_error_dialog(error_string):
    """ Show an error dialog """

    error_dlg = gtk.MessageDialog(type=gtk.MESSAGE_ERROR,
                                  message_format=error_string,
                                  buttons=gtk.BUTTONS_OK)
    error_dlg.run()
    error_dlg.destroy()

def show_ask_string_dialog(question, parent=None):
    question_dialog = gtk.MessageDialog(type=gtk.MESSAGE_QUESTION,
                                        buttons=gtk.BUTTONS_OK_CANCEL)
    if parent:
        question_dialog.set_transient_for(parent)
    question_dialog.set_markup(question)
    entry = gtk.Entry()
    entry.connect("activate", lambda event:
        question_dialog.response(gtk.RESPONSE_OK))
    question_dialog.vbox.pack_end(entry)
    question_dialog.show_all()
    response = question_dialog.run()
    text = entry.get_text() if response == gtk.RESPONSE_OK else None
    question_dialog.destroy()
    return text

def show_confirmation_dialog(question, parent=None):
    """
    Show this dialog to ask confirmation before executing a task.

    """
    dlg = gtk.MessageDialog(type=gtk.MESSAGE_QUESTION,
                                  message_format=question,
                                  buttons=gtk.BUTTONS_YES_NO)
    if parent:
        dlg.set_transient_for(parent)
    response = dlg.run()
    dlg.destroy()
    if response == gtk.RESPONSE_YES:
#        print "yes"
        return True
    else:
#        print "no"
        return False

def unpack_name_value_list(_list, num_values=2, key_type = str):
    # Parse the list into a dictionary
    # Sample list: ['LWIN:label:super', ...]
    # ":" in a value must be escaped as "\:"
    # "\" in a value must be escaped as "\\"
    result = {}
    if num_values == 2:
        pattern = re.compile(r"""([^\s:]+)             # name
                                 : ((?:\\.|[^\\:])*)   # first value
                                 : ((?:\\.|[^\\:])*)   # second value
                             """, re.VERBOSE)
        for text in _list:
            tuples = pattern.findall(text)
            if tuples:
                a = []
                for t in tuples[0]:
                    t = t.replace("\\\\", "\\")   # unescape backslash
                    t = t.replace("\\:", ":")     # unescape separator
                    a.append(t)

                if key_type == str:
                    item = {a[0].upper():(a[1], a[2])}
                elif key_type == int:
                    item = {int(a[0]):(a[1], a[2])}
                else:
                    assert(False)
                result.update(item)
    return result

def pack_name_value_list(tuples, field_sep=":", name_sep=":"):
    result = []
    for t in tuples.items():
        text = str(t[0])
        sep = name_sep
        for value in t[1]:
            value = value.replace("\\", "\\\\")   # escape backslash
            value = value.replace(sep, "\\"+sep)  # escape separator
            text += sep + '%s' % value
            sep = field_sep
        result.append(text)
    return result

# existing entries in text1 will be kept or overwritten by text2
def merge_tuple_strings(text1, text2):
    tuples1 = unpack_name_value_tuples(text1)
    tuples2 = unpack_name_value_tuples(text2)
    for key,values in tuples2.items():
        tuples1[key] = values
    return pack_name_value_tuples(tuples1)


# call each <callback> during <delay> only once
class CallOnce(object):

    def __init__(self, delay=20, delay_forever=False):
        self.callbacks = {}
        self.timer = None
        self.delay = delay
        self.delay_forever = delay_forever

    def enqueue(self, callback, *args):
        if not callback in self.callbacks:
            self.callbacks[callback] = args
        else:
            #print "CallOnce: ignored ", callback, args
            pass

        if self.delay_forever and self.timer:
            gobject.source_remove(self.timer)
            self.timer = None

        if not self.timer and self.callbacks:
            self.timer = gobject.timeout_add(self.delay, self.cb_timer)

    def cb_timer(self):
        for callback, args in self.callbacks.items():
            try:
                callback(*args)
            except:
                traceback.print_exc()

        self.callbacks.clear()
        gobject.source_remove(self.timer)
        self.timer = None
        return False

