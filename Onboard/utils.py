#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import with_statement

import os
import re
import traceback
import colorsys
from subprocess import Popen
from math import pi
from gettext import gettext as _

from gi.repository import GObject, Gtk, Gdk


### Logging ###
import logging
_logger = logging.getLogger("utils")
###############

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

def toprettyxml(domdoc):
    ugly_xml = domdoc.toprettyxml(indent='  ')
    # Join lines with text elements with their tag lines
    pattern = re.compile('>\n\s+([^<>\s].*?)\n\s+</', re.DOTALL)
    pretty_xml = pattern.sub('>\g<1></', ugly_xml)

    # Work around http://bugs.python.org/issue5752
    pretty_xml = re.sub(
           '"[^"]*"',
           lambda m: m.group(0).replace("\n", "&#10;"),
           pretty_xml)

    # remove empty lines
    pretty_xml = os.linesep.join( \
                    [s for s in pretty_xml.splitlines() if s.strip()])
    return pretty_xml


def dec_to_hex_colour(dec):
    hexString = hex(int(255*dec))[2:]
    if len(hexString) == 1:
        hexString = "0" + hexString

    return hexString

def xml_get_text(dom_node, tag_name):
    """ extract text from a dom node """
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
    return float(int(hexString, 16))

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

    error_dlg = Gtk.MessageDialog(type=Gtk.MessageType.ERROR,
                                  message_format=error_string,
                                  buttons=Gtk.ButtonsType.OK)
    error_dlg.run()
    error_dlg.destroy()

def show_ask_string_dialog(question, parent=None):
    question_dialog = Gtk.MessageDialog(type=Gtk.MessageType.QUESTION,
                                        buttons=Gtk.ButtonsType.OK_CANCEL)
    if parent:
        question_dialog.set_transient_for(parent)
    question_dialog.set_markup(question)
    entry = Gtk.Entry()
    entry.connect("activate", lambda event:
        question_dialog.response(Gtk.ResponseType.OK))
    question_dialog.get_message_area().add(entry)
    question_dialog.show_all()
    response = question_dialog.run()
    text = entry.get_text() if response == Gtk.ResponseType.OK else None
    question_dialog.destroy()
    return text

def show_confirmation_dialog(question, parent=None):
    """
    Show this dialog to ask confirmation before executing a task.

    """
    dlg = Gtk.MessageDialog(type=Gtk.MessageType.QUESTION,
                            message_format=question,
                            buttons=Gtk.ButtonsType.YES_NO)
    if parent:
        dlg.set_transient_for(parent)
    response = dlg.run()
    dlg.destroy()
    return response == Gtk.ResponseType.YES

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
            GObject.source_remove(self.timer)
            self.timer = None

        if not self.timer and self.callbacks:
            self.timer = GObject.timeout_add(self.delay, self.cb_timer)

    def cb_timer(self):
        for callback, args in self.callbacks.items():
            try:
                callback(*args)
            except:
                traceback.print_exc()

        self.callbacks.clear()
        self.timer = None
        return False



class Rect:
    """
    Simple rectangle class.
    Left and top are included, right and bottom excluded.
    Attributes can be accessed by name or by index, e.g. rect.x or rect[0].
    """

    attributes = ("x", "y", "w", "h")

    def __init__(self, x = 0, y = 0, w = 0, h = 0):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def __len__(self):
        return 4

    def __getitem__(self, index):
        """ Collection interface for rvalues, unpacking with '*' operator """
        return getattr(self, self.attributes[index])

    def __setitem__(self, index, value):
        """ Collection interface for lvalues """
        return setattr(self, self.attributes[index], value)

    def __str__(self):
        return "Rect(" + \
            " ".join(a+"="+str(getattr(self, a)) for a in self.attributes) + \
            ")"

    @staticmethod
    def from_extents(x0, y0, x1, y1):
        """
        New Rect from two points.
        x0 and y0 are considered inside, x1 and y1 are just outside the Rect.
        """
        return Rect(x0, y0, x1 - x0, y1 - y0)

    @staticmethod
    def from_position_size(position, size):
        """
        New Rect from two tuples.
        """
        return Rect(position[0], position[1], size[0], size[1])

    @staticmethod
    def from_points(p0, p1):
        """
        New Rect from two points, left-top and right-botton.
        The former lies inside, while the latter is considered to be
        just outside the rect.
        """
        return Rect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1])

    def to_extents(self):
        return self.x, self.y , self.x + self.w, self.y + self.h

    def to_position_size(self):
        return (self.x, self.y), (self.w, self.h)

    def to_list(self):
        return [getattr(self, attr) for attr in self.attributes]

    def copy(self):
        return Rect(self.x, self.y, self.w, self.h)

    def is_empty(self):
        return self.w <= 0 or self.h <= 0

    def get_position(self):
        return (self.x, self.y)

    def get_size(self):
        return (self.w, self.h)

    def get_center(self):
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def top(self):
        return self.y

    def left(self):
        return self.x

    def right(self):
        return self.x + self.w

    def bottom(self):
        return self.y + self.h

    def point_inside(self, point):
        """ True, if the given point lies inside the rectangle """
        if self.x <= point[0] and \
           self.x + self.w > point[0] and \
           self.y <= point[1] and \
           self.y + self.h > point[1]:
            return True
        return False

    def round(self):
        return Rect(round(self.x), round(self.y), round(self.w), round(self.h))

    def offset(self, dx, dy):
        """
        Returns a new Rect which is moved by dx and dy.
        """
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def inflate(self, dx, dy = None):
        """
        Returns a new Rect which is larger by dx and dy on all sides.
        """
        if dy is None:
            dy = dx
        return Rect(self.x-dx, self.y-dy, self.w+2*dx, self.h+2*dy)

    def deflate(self, dx, dy = None):
        """
        Returns a new Rect which is smaller by dx and dy on all sides.
        """
        if dy is None:
            dy = dx
        return Rect(self.x+dx, self.y+dy, self.w-2*dx, self.h-2*dy)

    def intersects(self, rect):
        return not self.intersection(rect).is_empty()

    def intersection(self, rect):
       x0 = max(self.x, rect.x)
       y0 = max(self.y, rect.y)
       x1 = min(self.x + self.w,  rect.x + rect.w)
       y1 = min(self.y + self.h,  rect.y + rect.h)
       if x0 > x1 or y0 > y1:
           return Rect()
       else:
           return Rect(x0, y0, x1 - x0, y1 - y0)

    def union(self, rect):
       x0 = min(self.x, rect.x)
       y0 = min(self.y, rect.y)
       x1 = max(self.x + self.w,  rect.x + rect.w)
       y1 = max(self.y + self.h,  rect.y + rect.h)
       return Rect(x0, y0, x1 - x0, y1 - y0)

    def align_inside_rect(self, rect, x_align = 0.5, y_align = 0.5):
        """ Returns a new Rect with the aspect ratio of self,
            that fits inside the given rectangle.
        """
        if self.is_empty() or rect.is_empty():
            return Rect()

        src_aspect = self.w / float(self.h)
        dst_aspect = rect.w / float(rect.h)

        result = rect.copy()
        if dst_aspect > src_aspect:
            result.w = rect.h * src_aspect
            result.x = x_align * (rect.w - result.w)
        else:
            result.h = rect.w / src_aspect
            result.y = y_align * (rect.h - result.h)
        return result


def brighten(amount, r, g, b, a=0.0):
    """ Make the given color brighter by amount a [-1.0...1.0] """
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l += amount
    if l > 1.0:
        l = 1.0
    if l < 0.0:
        l = 0.0
    return list(colorsys.hls_to_rgb(h, l, s)) + [a]


def roundrect_arc(context, rect, r = 15):
    x0,y0 = rect.x, rect.y
    x1,y1 = x0 + rect.w, y0 + rect.h

    # top left
    context.move_to(x0+r, y0)

    # top right
    context.line_to(x1-r,y0)
    context.arc(x1-r, y0+r, r, -pi/2, 0)

    # bottom right
    context.line_to(x1, y1-r)
    context.arc(x1-r, y1-r, r, 0, pi/2)

    # bottom left
    context.line_to(x0+r, y1)
    context.arc(x0+r, y1-r, r, pi/2, pi)

    # top left
    context.line_to(x0, y0+r)
    context.arc(x0+r, y0+r, r, pi, pi*1.5)

    context.close_path ()


def roundrect_curve(context, rect, r_pct = 100):
    # Uses B-splines, for less even looks than with arcs, but
    # still allows for approximate circles at r_pct = 100.
    x0, y0 = rect.x, rect.y
    x1, y1 = rect.x + rect.w, rect.y + rect.h
    w, h   = rect.w, rect.h

    r = min(w, h) * min(r_pct/100.0, 0.5) # full range at 50%
    k = (r-1) * r_pct/200.0 # position of control points for circular curves

    # top left
    context.move_to(x0+r, y0)

    # top right
    context.line_to(x1-r,y0)
    context.curve_to(x1-k, y0, x1, y0+k, x1, y0+r)

    # bottom right
    context.line_to(x1, y1-r)
    context.curve_to(x1, y1-k, x1-k, y1, x1-r, y1)

    # bottom left
    context.line_to(x0+r, y1)
    context.curve_to(x0+k, y1, x0, y1-k, x0, y1-r)

    # top left
    context.line_to(x0, y0+r)
    context.curve_to(x0, y0+k, x0+k, y0, x0+r, y0)

    context.close_path ()


def round_corners(cr, w, h, r):
    """
    Paint 4 round corners.
    """
    # top-left
    cr.curve_to (0, r, 0, 0, r, 0)
    cr.line_to (0, 0)
    cr.close_path()
    cr.fill()
    # top-right
    cr.curve_to (w, r, w, 0, w - r, 0)
    cr.line_to (w, 0)
    cr.close_path()
    cr.fill()
    # bottom-left
    cr.curve_to (r, h, 0, h, 0, h - r)
    cr.line_to (0, h)
    cr.close_path()
    cr.fill()
    # bottom-right
    cr.curve_to (w, h - r, w, h, w - r, h)
    cr.line_to (w, h)
    cr.close_path()
    cr.fill()


# window corners
class Corner:
    NORTH_WEST = Gdk.WindowEdge.NORTH_WEST
    NORTH = Gdk.WindowEdge.NORTH
    NORTH_EAST = Gdk.WindowEdge.NORTH_EAST
    WEST = Gdk.WindowEdge.WEST
    EAST = Gdk.WindowEdge.EAST
    SOUTH_WEST = Gdk.WindowEdge.SOUTH_WEST
    SOUTH = Gdk.WindowEdge.SOUTH
    SOUTH_EAST   = Gdk.WindowEdge.SOUTH_EAST

cursor_types = {
    Corner.NORTH_WEST : Gdk.CursorType.TOP_LEFT_CORNER,
    Corner.NORTH      : Gdk.CursorType.TOP_SIDE,
    Corner.NORTH_EAST : Gdk.CursorType.TOP_RIGHT_CORNER,
    Corner.WEST       : Gdk.CursorType.LEFT_SIDE,
    Corner.EAST       : Gdk.CursorType.RIGHT_SIDE,
    Corner.SOUTH_WEST : Gdk.CursorType.BOTTOM_LEFT_CORNER,
    Corner.SOUTH      : Gdk.CursorType.BOTTOM_SIDE,
    Corner.SOUTH_EAST : Gdk.CursorType.BOTTOM_RIGHT_CORNER}

class WindowManipulator(object):
    """
    Adds resize and move capability to windows.
    Meant for resizing windows without decoration or resize gripper.
    """
    drag_start_offset = None
    drag_start_rect = None
    drag_resize_edge = None

    def get_resize_frame_rect(self):
        return Rect(0, 0,
                    self.get_allocated_width(),
                    self.get_allocated_height())

    def get_drag_window(self):
        return self

    def get_always_visible_rect(self):
        """ Rectangle in canvas coordinates that must not leave the screen. """
        return None

    def handle_press(self, point, allow_move = False):
        hit = self._hit_test_frame(point)
        if not hit is None:
            self.start_resize_window(hit)
            return True

        if allow_move:
            self.start_move_window()
            return True

        return False

    def handle_motion(self):
        """ handle dragging for window move and resize """
        if not self.is_dragging():
            return

        rootwin = Gdk.get_default_root_window()
        dunno, pointer_x, pointer_y, mods = rootwin.get_pointer()
        wx, wy = (pointer_x - self.drag_start_offset[0],
                  pointer_y - self.drag_start_offset[1])

        if self.drag_resize_edge is None:
            # move window
            x, y = self._limit_position(wx, wy)
            w, h = None, None
        else:
            # resize window
            wmin = hmin = 12  # minimum window size
            rect = self.drag_start_rect
            x0, y0, x1, y1 = rect.to_extents()
            w, h = rect.get_size()

            if self.drag_resize_edge in [Corner.NORTH,
                                         Corner.NORTH_WEST,
                                         Corner.NORTH_EAST]:
                y0 = min(wy, y1 - hmin)
            if self.drag_resize_edge in [Corner.WEST,
                                         Corner.NORTH_WEST,
                                         Corner.SOUTH_WEST]:
                x0 = min(wx, x1 - wmin)
            if self.drag_resize_edge in [Corner.EAST,
                                         Corner.NORTH_EAST,
                                         Corner.SOUTH_EAST]:
                x1 = max(wx + w, x0 + wmin)
            if self.drag_resize_edge in [Corner.SOUTH,
                                         Corner.SOUTH_WEST,
                                         Corner.SOUTH_EAST]:
                y1 = max(wy + h, y0 + wmin)

            x, y, w, h = x0, y0, x1 -x0, y1 - y0

        self._move_resize(x, y, w, h)

    def set_drag_cursor_at(self, point, enable = True):
        cursor_type = None
        if enable:
            cursor_type = self.get_drag_cursor_at(point)

        # set/reset cursor
        if not cursor_type is None:
            cursor = Gdk.Cursor(cursor_type)
            if cursor:
                self.get_window().set_cursor(cursor)
        else:
            self.get_window().set_cursor(None)

    def get_drag_cursor_at(self, point):
        hit = self.drag_resize_edge
        if hit is None:
           hit = self._hit_test_frame(point)
        if not hit is None:
            return cursor_types[hit]
        return None

    def start_move_window(self):
        # begin_move_drag fails for window type hint "DOCK"
        # window.begin_move_drag(1, x, y, Gdk.CURRENT_TIME)

        self.start_drag()

    def stop_move_window(self):
        self.stop_drag()

    def start_resize_window(self, edge):
        # begin_resize_drag fails for window type hint "DOCK"
        #self.get_drag_window().begin_resize_drag (edge, 1, x, y, 0)

        self.start_drag()
        self.drag_resize_edge = edge

    def start_drag(self):
        rootwin = Gdk.get_default_root_window()
        window = self.get_drag_window()
        dunno, pointer_x, pointer_y, mask = rootwin.get_pointer()
        x, y = window.get_position()
        self.drag_start_offset = (pointer_x - x, pointer_y - y)
        self.drag_start_rect = Rect.from_position_size(window.get_position(),
                                                       window.get_size())
    def stop_drag(self):
        if self.is_dragging():
            self.drag_start_offset = None
            self.drag_resize_edge = None
            self.move_into_view()

    def is_dragging(self):
        return bool(self.drag_start_offset)

    def move_into_view(self):
        """
        If the window has somehow ended up off-screen,
        move the always-visible-rect back into view.
        """
        window = self.get_drag_window()
        x, y = window.get_window().get_root_origin()
        x, y = window.get_position()
        _x, _y = self._limit_position(x, y)
        if _x != x or _y != y:
            self._move_resize(_x, _y)

    def _hit_test_frame(self, point):
        corner_size = 10
        edge_size = 5
        canvas_rect = self.get_resize_frame_rect()

        w = min(canvas_rect.w / 2, corner_size)
        h = min(canvas_rect.h / 2, corner_size)

        # try corners first
        hit_rect = Rect(canvas_rect.x, canvas_rect.y, w, h)
        if hit_rect.point_inside(point):
            return Corner.NORTH_WEST

        hit_rect.x = canvas_rect.w - w
        if hit_rect.point_inside(point):
            return Corner.NORTH_EAST

        hit_rect.y = canvas_rect.h - h
        if hit_rect.point_inside(point):
            return Corner.SOUTH_EAST

        hit_rect.x = 0
        if hit_rect.point_inside(point):
            return Corner.SOUTH_WEST

        # then check the edges
        w = h = edge_size
        if point[0] < w:
            return Corner.WEST
        if point[0] > canvas_rect.w - w:
            return Corner.EAST
        if point[1] < h:
            return Corner.NORTH
        if point[1] > canvas_rect.h - h:
            return Corner.SOUTH

        return None

    def _move_resize(self, x, y, w = None, h = None):
        window = self.get_drag_window()
        _win = window.get_window()
        if w is None:
            window.move(x, y)
            #print "move ", x, y, " position ", window.get_position(), " origin ", _win.get_origin(), " root origin ", _win.get_root_origin()
        else:
            window.get_window().move_resize(x, y, w, h)

    def _limit_position(self, x, y):
        """
        Limits the given window position, so that the current
        always_visible_rect stays fully in view.
        """
        rootwin = Gdk.get_default_root_window()

        # display limits
        limits = Rect.from_position_size(rootwin.get_position(),
                                  (rootwin.get_width(), rootwin.get_height()))

        # rect, that has to be visible, in canvas coordinates
        r = self.get_always_visible_rect()
        if not r is None:
            r = r.round()

            # Transform the always-visible rect to become relative to the
            # window position, i.e. take window decoration in account.
            window = self.get_drag_window()
            position = window.get_position()  # fails right after unhide
            #position = window.get_window().get_root_origin()
            origin = window.get_window().get_origin()
            if len(origin) == 3:   # What is the first parameter for? Gdk bug?
                origin = origin[1:]
            r = r.offset(origin[0] - position[0], origin[1] - position[1])

            x = max(x, limits.left() - r.left())
            x = min(x, limits.right() - r.right())
            y = max(y, limits.top() - r.top())
            y = min(y, limits.bottom() - r.bottom())

        return x, y


class Timer(object):
    """
    Simple wrapper around gobject's timer API
    Overload on_timer in derived classes.
    For one-shot timers return False there.
    """
    _timer = None

    def start(self, delay):
        """ delay in seconds """
        self.stop()
        ms = int(delay * 1000)
        self._timer = GObject.timeout_add(ms, self._cb_timer)

    def stop(self):
        if not self._timer is None:
            GObject.source_remove(self._timer)
            self._timer = None

    def _cb_timer(self):
        if not self.on_timer():
            self.stop()
            return False
        return True

    def on_timer(self):
        return True


class DelayedLauncher(Timer):
    """
    Launches a process after a certain delay.
    Used for launching mousetweaks.
    """
    args = None

    def launch_delayed(self, args, delay):
        self.args = args
        self.start(delay)

    def on_timer(self):
        _logger.debug(_("launching '{}'") \
                        .format(" ".join(self.args)))
        try:
            Popen(self.args)
        except OSError as e:
            _logger.warning(_("Failed to execute '{}', {}") \
                            .format(" ".join(self.args), e))
        return False


