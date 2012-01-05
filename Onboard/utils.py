#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import with_statement

import sys
import os
import time
import re
import traceback
import colorsys
from subprocess import Popen
from math import pi, sqrt, sin
from contextlib import contextmanager
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
    # Parse a list of tuples into a dictionary
    # Sample list: ['LWIN:label:super', ...]
    # ":" in a value must be escaped as "\:"
    # "\" in a value must be escaped as "\\"
    result = {}

    # Awkward fixed regexes; todo: Allow arbirary number of values
    if num_values == 1:
        pattern = re.compile(r"""([^\s:]+)             # name
                                 : ((?:\\.|[^\\:])*)   # first value
                             """, re.VERBOSE)
    elif num_values == 2:
        pattern = re.compile(r"""([^\s:]+)             # name
                                 : ((?:\\.|[^\\:])*)   # first value
                                 : ((?:\\.|[^\\:])*)   # second value
                             """, re.VERBOSE)
    else:
        assert(False)  # unsupported number of values

    for text in _list:
        tuples = pattern.findall(text)
        if tuples:
            a = []
            for t in tuples[0]:
                t = t.replace("\\\\", "\\")   # unescape backslash
                t = t.replace("\\:", ":")     # unescape separator
                a.append(t)

            if key_type == str:
                item = {a[0] : (a[1:])}
            elif key_type == int:
                item = {int(a[0]) : (a[1:])}
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

    def __eq__(self, other):
        return self.x == other.x and \
               self.y == other.y and \
               self.w == other.w and \
               self.h == other.h

    def __ne__(self, other):
        return self.x != other.x or \
               self.y != other.y or \
               self.w != other.w or \
               self.h != other.h

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

    def top_left(self):
        return self.x, self.y

    def is_point_within(self, point):
        """ True, if the given point lies inside the rectangle """
        if self.x <= point[0] and \
           self.x + self.w > point[0] and \
           self.y <= point[1] and \
           self.y + self.h > point[1]:
            return True
        return False

    def round(self):
        return Rect(round(self.x), round(self.y), round(self.w), round(self.h))

    def int(self):
        return Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    def offset(self, dx, dy):
        """
        Returns a new Rect, displace by dx and dy.
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

    def grow(self, fx, fy = None):
        """ 
        Returns a new Rect with its size multiplied by fx, fy.
        """
        if fy is None:
            fy = fx
        w = self.w * fx
        h = self.h * fy
        return Rect(self.x + (self.w - w) / 2.0,
                    self.y + (self.h - h) / 2.0,
                    w, h)

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
    # Uses B-splines for less even looks than with arcs, but
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


def round_corners(cr, r, x, y, w, h):
    """
    Paint 4 round corners.
    Currently x, y are ignored and assumed to be 0.
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
class Handle:
    NORTH_WEST = Gdk.WindowEdge.NORTH_WEST
    NORTH = Gdk.WindowEdge.NORTH
    NORTH_EAST = Gdk.WindowEdge.NORTH_EAST
    WEST = Gdk.WindowEdge.WEST
    EAST = Gdk.WindowEdge.EAST
    SOUTH_WEST = Gdk.WindowEdge.SOUTH_WEST
    SOUTH = Gdk.WindowEdge.SOUTH
    SOUTH_EAST   = Gdk.WindowEdge.SOUTH_EAST
    class MOVE: pass

cursor_types = {
    Handle.NORTH_WEST : Gdk.CursorType.TOP_LEFT_CORNER,
    Handle.NORTH      : Gdk.CursorType.TOP_SIDE,
    Handle.NORTH_EAST : Gdk.CursorType.TOP_RIGHT_CORNER,
    Handle.WEST       : Gdk.CursorType.LEFT_SIDE,
    Handle.EAST       : Gdk.CursorType.RIGHT_SIDE,
    Handle.SOUTH_WEST : Gdk.CursorType.BOTTOM_LEFT_CORNER,
    Handle.SOUTH      : Gdk.CursorType.BOTTOM_SIDE,
    Handle.SOUTH_EAST : Gdk.CursorType.BOTTOM_RIGHT_CORNER,
    Handle.MOVE       : Gdk.CursorType.FLEUR}


class WindowManipulator(object):
    """
    Adds resize and move capability to windows.
    Meant for resizing windows without decoration or resize gripper.

    Quirks to remember:

    Keyboard window:
        - Always use threshold when move button was pressed,
          in order to support long press to show the touch handles.
        - Never use the threshold for the enlarged touch handles.
          They are only temporarily visible and thus don't need protection.

    IconPalette:
        - Always use threshold when trying to move, otherwise
          clicking to unhide the keyboard window won't work.
    """
    _drag_start_pointer = None
    _drag_start_offset  = None
    _drag_start_rect    = None
    _drag_handle        = None
    _drag_active        = False  # has window move/resize actually started yet?
    _drag_threshold     = 8
    _drag_snap_threshold = 16

    drag_protection = True         # wether dragging is threshold protected
    temporary_unlock_delay = 6.0   # seconds until threshold protection returns
                                   #  counts from drag end in fallback mode
                                   #  counts from drag start in system mode
                                   #  (unfortunately)
    _temporary_unlock_time = None

    def __init__(self):
        pass

    def enable_drag_protection(self, enable):
        self.drag_protection = enable

    def reset_drag_protection(self):
        self._temporary_unlock_time = None

    def get_resize_frame_rect(self):
        return Rect(0, 0,
                    self.get_allocated_width(),
                    self.get_allocated_height())

    def get_drag_window(self):
        return self

    def get_drag_threshold(self):
        return 8

    def get_always_visible_rect(self):
        """ Rectangle in canvas coordinates that must not leave the screen. """
        return None

    def handle_press(self, event, move_on_background = False):
        point = (event.x, event.y)
        root_point = (event.x_root, event.y_root)

        hit = self.hit_test_move_resize(point)
        if not hit is None:
            if hit == Handle.MOVE:
                self.start_move_window(root_point)
            else:
                self.start_resize_window(hit, root_point)
            return True

        if move_on_background:
            self.start_move_window(root_point)
            return True

        return False

    def handle_motion(self, event, fallback = False):
        if not self.is_drag_initiated():
            return

        snap_to_cursor = False
        dx = event.x_root - self._drag_start_pointer[0]
        dy = event.y_root - self._drag_start_pointer[1]

        # distance threshold, protection from accidental drags
        if not self._drag_active:
            d = sqrt(dx*dx + dy*dy)

            drag_active = not self.drag_protection

            if self.drag_protection:
                # snap off for temporary unlocking
                if self._temporary_unlock_time is None and \
                   d > self._drag_threshold:
                    self._temporary_unlock_time = 1

                    # Snap to cursor position for large drag thresholds
                    # Dragging is smoother without snapping, but for large
                    # thresholds, the cursor ends up far away from the
                    # window and there is a danger of windows going offscreen.
                    if d >= self._drag_snap_threshold:
                        snap_to_cursor = True
                    else:
                        self._drag_start_offset[0] += dx
                        self._drag_start_offset[1] += dy

                if not self._temporary_unlock_time is None:
                    drag_active = True
            else:
                self._temporary_unlock_time = 1 # unlock for touch handles too

            self._drag_active |= drag_active

        # move/resize
        if self._drag_active:
            if fallback:
                self._handle_motion_fallback(dx, dy)
            else:
                self._handle_motion_system(dx, dy, snap_to_cursor, event)

    def _handle_motion_system(self, dx, dy, snap_to_cursor, event):
        """
        Let the window manager do the moving
        This fixes issues like not reaching edges at high move speed
        and not being able to snap off a maximized window.
        Does nothing for window type hint "DOCK".
        """
        window = self.get_drag_window()
        if window:
            x = event.x_root
            y = event.y_root
            if self.is_moving():
                if snap_to_cursor:
                    x, y = x - dx, y - dy # snap to cursor
                window.begin_move_drag(1, x, y, event.time)
            elif self.is_resizing():

                # compensate for weird begin_resize_drag behaviour
                # Catch up to the mouse cursor
                if snap_to_cursor:
                    if not self._drag_start_rect.is_point_within((x, y)):
                        x, y = x + dx, y + dy

                window.begin_resize_drag(self._drag_handle, 1,
                                         x, y, event.time)
        # There appears to be no reliable way to detect the end of the drag,
        # but we have to stop the drag somehow. Do it here.
        self.stop_drag()

    def _handle_motion_fallback(self, dx, dy):
        """ handle dragging for window move and resize """
        if not self.is_drag_initiated():
            return

        wx = self._drag_start_pointer[0] + dx - self._drag_start_offset[0]
        wy = self._drag_start_pointer[1] + dy - self._drag_start_offset[1]

        if self._drag_handle == Handle.MOVE:
            # move window
            x, y = self.limit_position(wx, wy)
            w, h = None, None
        else:
            # resize window
            wmin = hmin = 20  # minimum window size
            rect = self._drag_start_rect
            x0, y0, x1, y1 = rect.to_extents()
            w, h = rect.get_size()

            if self._drag_handle in [Handle.NORTH,
                                     Handle.NORTH_WEST,
                                     Handle.NORTH_EAST]:
                y0 = min(wy, y1 - hmin)
            if self._drag_handle in [Handle.WEST,
                                     Handle.NORTH_WEST,
                                     Handle.SOUTH_WEST]:
                x0 = min(wx, x1 - wmin)
            if self._drag_handle in [Handle.EAST,
                                     Handle.NORTH_EAST,
                                     Handle.SOUTH_EAST]:
                x1 = max(wx + w, x0 + wmin)
            if self._drag_handle in [Handle.SOUTH,
                                     Handle.SOUTH_WEST,
                                     Handle.SOUTH_EAST]:
                y1 = max(wy + h, y0 + wmin)

            x, y, w, h = x0, y0, x1 -x0, y1 - y0

        self._move_resize(x, y, w, h)

    def set_drag_cursor_at(self, point, allow_drag_cursors = True):
        """ set the mouse cursor """
        window = self.get_window()
        if not window:
            return

        cursor_type = None
        if allow_drag_cursors or \
           not self._drag_handle is None:    # already dragging a handle?
            cursor_type = self.get_drag_cursor_at(point)

        # set/reset cursor
        if not cursor_type is None:
            cursor = Gdk.Cursor(cursor_type)
            if cursor:
                window.set_cursor(cursor)
        else:
            window.set_cursor(None)

    def get_drag_cursor_at(self, point):
        hit = self._drag_handle
        if hit is None:
           hit = self.hit_test_move_resize(point)
        if not hit is None and \
           not hit == Handle.MOVE or self.is_drag_active(): # delay it for move
            return cursor_types[hit]
        return None

    def start_move_window(self, point = None):
        self.start_drag(point)
        self._drag_handle = Handle.MOVE

    def stop_move_window(self):
        self.stop_drag()

    def start_resize_window(self, handle, point = None):
        self.start_drag(point)
        self._drag_handle = handle

    def start_drag(self, point = None):

        # Find the pointer position for the occasions, when this is
        # not being called from an event (move button).
        if not point:
            rootwin = Gdk.get_default_root_window()
            dunno, x_root, y_root, mask = rootwin.get_pointer()
            point = (x_root, y_root)

        # rmember pointer and window positions
        window = self.get_drag_window()
        x, y = window.get_position()
        self._drag_start_pointer = point
        self._drag_start_offset = [point[0] - x, point[1] - y]
        self._drag_start_rect = Rect.from_position_size(window.get_position(),
                                                        window.get_size())
        # not yet actually moving the window
        self._drag_active = False

        # get the threshold
        self._drag_threshold = self.get_drag_threshold()

        # check if the temporary threshold unlocking has expired
        if not self.drag_protection or \
           not self._temporary_unlock_time is None and \
           time.time() - self._temporary_unlock_time > \
                         self.temporary_unlock_delay:
            self._temporary_unlock_time = None

        # give keyboard window a chance to react
        self.on_drag_initiated()

    def stop_drag(self):
        if self.is_drag_initiated():

            if self._temporary_unlock_time is None:
                # snap back to start position
                if self.drag_protection:
                    self._move_resize(*self._drag_start_rect)
            else:
                # restart the temporary unlock period
                self._temporary_unlock_time = time.time()

            self._drag_start_offset = None
            self._drag_handle = None
            self._drag_active = False

            self.move_into_view()

            # give keyboard window a chance to react
            self.on_drag_done()

    def on_drag_initiated(self):
        """
        User controlled drag has begun.
        overload this in derived classes.
        """
        pass

    def on_drag_done(self):
        """
        User controlled drag ended.
        overload this in derived classes.
        """
        pass

    def is_drag_initiated(self):
        """ Button pressed down on a drag handle, not yet actually dragging """
        return bool(self._drag_start_offset)

    def is_drag_active(self):
        """ Are we actually moving/resizing """
        return self.is_drag_initiated() and self._drag_active

    def is_moving(self):
        return self.is_drag_initiated() and self._drag_handle == Handle.MOVE

    def is_resizing(self):
        return self.is_drag_initiated() and self._drag_handle  != Handle.MOVE

    def move_into_view(self):
        """
        If the window has somehow ended up off-screen,
        move the always-visible-rect back into view.
        """
        window = self.get_drag_window()
        x, y = window.get_position()
        _x, _y = self.limit_position(x, y)
        if _x != x or _y != y:
            self._move_resize(_x, _y)

    def force_into_view(self):
        self.move_into_view()
        if False:  # Only for system drag, not needed when using fallback mode
            GObject.idle_add(self._do_force_into_view)

    def _do_force_into_view(self):
        """ Works mostly, but occasionally the window disappears... """
        window = self.get_drag_window()
        x, y = window.get_position()
        _x, _y = self.limit_position(x, y)
        if _x != x or _y != y:
            window.hide()
            self._move_resize(_x, _y)
            window.show()

    def get_display_limits(self):
        rootwin = Gdk.get_default_root_window()
        return Rect.from_position_size(rootwin.get_position(),
                                (rootwin.get_width(), rootwin.get_height()))

    def limit_position(self, x, y, visible_rect = None):
        """
        Limits the given window position, so that the current
        always_visible_rect stays fully in view.
        """
        limits = self.get_display_limits()

        # rect, that has to be visible, in canvas coordinates
        r = visible_rect
        if r is None:
            r = self.get_always_visible_rect()

        if not r is None:
            r = r.round()

            # Transform the always-visible rect to become relative to the
            # window position, i.e. take window decoration into account.
            window = self.get_drag_window()
            position = window.get_position() # careful, fails right after unhide
            origin = window.get_origin()
            if len(origin) == 3:   # What is the first parameter for? Gdk bug?
                origin = origin[1:]
            r.x += origin[0] - position[0]
            r.y += origin[1] - position[1]

            x = max(x, limits.left() - r.left())
            x = min(x, limits.right() - r.right())
            y = max(y, limits.top() - r.top())
            y = min(y, limits.bottom() - r.bottom())

        return x, y

    def hit_test_move_resize(self, point):
        corner_size = 10
        edge_size = 5
        canvas_rect = self.get_resize_frame_rect()

        w = min(canvas_rect.w / 2, corner_size)
        h = min(canvas_rect.h / 2, corner_size)

        # try corners first
        hit_rect = Rect(canvas_rect.x, canvas_rect.y, w, h)
        if hit_rect.is_point_within(point):
            return Handle.NORTH_WEST

        hit_rect.x = canvas_rect.w - w
        if hit_rect.is_point_within(point):
            return Handle.NORTH_EAST

        hit_rect.y = canvas_rect.h - h
        if hit_rect.is_point_within(point):
            return Handle.SOUTH_EAST

        hit_rect.x = canvas_rect.x
        if hit_rect.is_point_within(point):
            return Handle.SOUTH_WEST

        # then check the edges
        w = h = edge_size
        if point[0] < w:
            return Handle.WEST
        if point[0] > canvas_rect.w - w:
            return Handle.EAST
        if point[1] < h:
            return Handle.NORTH
        if point[1] > canvas_rect.h - h:
            return Handle.SOUTH

        return None

    def _move_resize(self, x, y, w = None, h = None):
        window = self.get_drag_window()
        _win = window.get_window()
        if w is None:
            self._insert_edge_move(window, x, y)
            window.move(x, y)
            #print "move ", x, y, " position ", window.get_position(), " origin ", _win.get_origin(), " root origin ", _win.get_root_origin()
        else:
            if hasattr(window, "move_resize"):
                window.move_resize(x, y, w, h) # keyboard window
            else:
                window.get_window().move_resize(x, y, w, h) # icon palette


    def _insert_edge_move(self, window, x, y):
        """
        Compiz and potentially other window managers silently ignore
        moves outside of some screen edges. When hitting the edge at
        high speed, onboard gets stuck some distance away from it.
        Fix this by inserting an intermediate move right to the edge.
        Does not help with the edge below unity bar.
        """
        limits = self.get_display_limits()
        one_more_x = x
        one_more_y = y
        pos = window.get_position()
        size = window.get_size()

        if pos[0] > limits.left() and \
           x      < limits.left():
            one_more_x = limits.left()
        if pos[0] + size[0] < limits.right() and \
           x      + size[0] > limits.right():
            one_more_x = limits.right()
        if pos[1] > limits.top() and \
           y      < limits.top():
            one_more_y = limits.top()
        if pos[1] + size[1] < limits.bottom() and \
           y      + size[1] > limits.bottom():
            one_more_x = limits.right()

        if one_more_x != x or one_more_y != y:
            window.move(one_more_x, one_more_y)


@contextmanager
def timeit(s, out=sys.stdout):
    import time, gc

    if out:
        gc.collect()
        gc.collect()
        gc.collect()

        t = time.time()
        text = s if s else "timeit"
        out.write(u"%-15s " % text)
        out.flush()
        yield None
        out.write(u"%10.3fms\n" % ((time.time() - t)*1000))
    else:
        yield None


class Timer(object):
    """
    Simple wrapper around gobject's timer API
    Overload on_timer in derived classes.
    For one-shot timers return False there.
    """
    _timer = None
    _callback = None
    _callback_args = None

    def __init__(self, delay = None, callback = None, *callback_args):
        self._callback = callback
        self._callback_args = callback_args

        if not delay is None:
            self.start(delay)

    def start(self, delay, callback = None, *callback_args):
        """ 
        Delay in seconds.
        Uses second granularity if delay is of type int.
        Uses medium resolution timer if delay is of type float.
        """
        if callback:
            self._callback = callback
            self._callback_args = callback_args

        self.stop()

        if type(delay) == int:
            self._timer = GObject.timeout_add_seconds(delay, self._cb_timer)
        else:
            ms = int(delay * 1000.0)
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
        if self._callback:
            return self._callback(*self._callback_args)
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


class FadeTimer(Timer):
    """ Fades between two values, e.g. opacities"""

    start_value = None
    target_value = None

    def fade_to(self, start_value, target_value, duration,
                callback = None, *callback_args):
        """
        Start value fade.
        duration: fade time in seconds, 0 for immediate value change
        """
        self.start_value = start_value
        self.target_value = target_value
        self._start_time = time.time()
        self._duration = duration
        self._callback = callback
        self._callback_args = callback_args

        self.start(0.05)

    def on_timer(self):
        elapsed = time.time() - self._start_time
        if self._duration:
            lin_progress = min(1.0, elapsed / self._duration)
        else:
            lin_progress = 1.0
        sin_progress = (sin(lin_progress * pi - pi / 2.0) + 1.0) / 2.0
        self.value = sin_progress * (self.target_value - self.start_value) + \
                  self.start_value

        done = lin_progress >= 1.0
        if self._callback:
            self._callback(self.value, done, *self._callback_args)

        return not done


class TreeItem(object):
    """
    Abstract base class of tree nodes.
    Base class of nodes in  layout- and color scheme tree.
    """

    # id string of the item
    id = None

    # parent item in the tree
    parent = None

    # child items
    items = ()

    def set_items(self, items):
        self.items = items
        for item in items:
            item.parent = self

    def find_ids(self, ids):
        """ find all items with matching id """
        items = []
        for item in self.iter_items():
            if item.id in ids:
                items.append(item)
        return items

    def iter_items(self):
        """
        Iterates through all items of the tree.
        """
        yield self

        for item in self.items:
            for child in item.iter_depth_first():
                yield child

    def iter_depth_first(self):
        """
        Iterates depth first through the tree.
        """
        for item in self.items:
            for child in item.iter_depth_first():
                yield child

        yield self

    def iter_to_root(self):
        item = self
        while item:
            yield item
            item = item.parent


