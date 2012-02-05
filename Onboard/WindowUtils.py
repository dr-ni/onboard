# -*- coding: utf-8 -*-
""" Window manipulation and other helpers """

from __future__ import division, print_function, unicode_literals

import time
from math import sqrt
from gettext import gettext as _

from gi.repository import GObject, Gtk, Gdk

from Onboard.utils import Rect, Timer

### Logging ###
import logging
from functools import reduce
_logger = logging.getLogger("WindowUtils")
###############

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

Handle.EDGES  =   (Handle.WEST,
                   Handle.NORTH,
                   Handle.EAST,
                   Handle.SOUTH)

Handle.CORNERS =  (Handle.NORTH_WEST,
                   Handle.NORTH_EAST,
                   Handle.SOUTH_EAST,
                   Handle.SOUTH_WEST)

Handle.RESIZERS = (Handle.NORTH_WEST,
                   Handle.NORTH,
                   Handle.NORTH_EAST,
                   Handle.EAST,
                   Handle.SOUTH_EAST,
                   Handle.SOUTH,
                   Handle.SOUTH_WEST,
                   Handle.WEST)

Handle.ALL = Handle.RESIZERS + (Handle.MOVE, )

Handle.CURSOR_TYPES = {
    Handle.NORTH_WEST : Gdk.CursorType.TOP_LEFT_CORNER,
    Handle.NORTH      : Gdk.CursorType.TOP_SIDE,
    Handle.NORTH_EAST : Gdk.CursorType.TOP_RIGHT_CORNER,
    Handle.WEST       : Gdk.CursorType.LEFT_SIDE,
    Handle.EAST       : Gdk.CursorType.RIGHT_SIDE,
    Handle.SOUTH_WEST : Gdk.CursorType.BOTTOM_LEFT_CORNER,
    Handle.SOUTH      : Gdk.CursorType.BOTTOM_SIDE,
    Handle.SOUTH_EAST : Gdk.CursorType.BOTTOM_RIGHT_CORNER,
    Handle.MOVE       : Gdk.CursorType.FLEUR}

Handle.IDS = {
    Handle.NORTH_WEST : "NW",
    Handle.NORTH      : "N",
    Handle.NORTH_EAST : "NE",
    Handle.EAST       : "E",
    Handle.SOUTH_WEST : "SW",
    Handle.SOUTH      : "S",
    Handle.SOUTH_EAST : "SE",
    Handle.WEST       : "W",
    Handle.MOVE       : "M"}

Handle.RIDS = {
    "NW" : Handle.NORTH_WEST,
    "N"  : Handle.NORTH,
    "NE" : Handle.NORTH_EAST,
    "E"  : Handle.EAST,
    "SW" : Handle.SOUTH_WEST,
    "S"  : Handle.SOUTH,
    "SE" : Handle.SOUTH_EAST,
    "W"  : Handle.WEST,
    "M"  : Handle.MOVE}


class WindowManipulator(object):
    """
    Adds resize and move capability to windows.
    Meant for resizing windows without decoration or resize gripper.

    Quirks to remember:

    Keyboard window:
        - Always use threshold when move button was pressed
          in order to support long press to show the touch handles.
        - Never use the threshold for the enlarged touch handles.
          They are only temporarily visible and thus don't need protection.

    IconPalette:
        - Always use threshold when trying to move, otherwise
          clicking to unhide the keyboard window won't work.
    """
    hit_frame_width = 10           # size of resize corners and edges
    drag_protection = True         # enable protection threshold
    temporary_unlock_delay = 6.0   # seconds until protection threshold returns
                                   #  counts from drag end in fallback mode
                                   #  counts from drag start in system mode
                                   #  (unfortunately)
    _temporary_unlock_time = None

    _drag_start_pointer = None
    _drag_start_offset  = None
    _drag_start_rect    = None
    _drag_handle        = None
    _drag_active        = False  # has window move/resize actually started yet?
    _drag_threshold     = 8
    _drag_snap_threshold = 16


    def __init__(self):
        self._drag_handles = Handle.RESIZERS

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

    def get_drag_handles(self):
        return self._drag_handles

    def set_drag_handles(self, handles):
        self._drag_handles = handles

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
            return Handle.CURSOR_TYPES[hit]
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
        canvas_rect = self.get_resize_frame_rect()
        handles = self.get_drag_handles()

        w = min(canvas_rect.w / 2, self.hit_frame_width)
        h = min(canvas_rect.h / 2, self.hit_frame_width)

        x, y = point
        x0, y0, x1, y1 = canvas_rect.to_extents()

        # try corners first
        for handle in handles:
            if handle == Handle.NORTH_WEST:
                if x >= x0 and x < x0 + w and \
                   y >= y0 and y < y0 + h:
                    return handle

            if handle == Handle.NORTH_EAST:
                if x <= x1 and x > x1 - w and \
                   y >= y0 and y < y0 + h:
                    return handle

            if handle == Handle.SOUTH_EAST:
                if x <= x1 and x > x1 - w and \
                   y <= y1 and y > y1 - h:
                    return handle

            if handle == Handle.SOUTH_WEST:
                if x >= x0 and x < x0 + w and \
                   y <= y1 and y > y1 - h:
                    return handle

        # then check the edges
        for handle in handles:
            if handle == Handle.WEST:
                if x < x0 + w:
                    return handle
            if handle == Handle.EAST:
                if x > x1 - w:
                    return handle
            if handle == Handle.NORTH:
                if y < y0 + h:
                    return handle
            if handle == Handle.SOUTH:
                if y > y1 - h:
                    return handle

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


class Orientation:
    """ enum for screen orientation """

    class LANDSCAPE: pass
    class PORTRAIT: pass

class WindowRectTracker:
    """
    Keeps track of the window rectangle when moving/resizing.
    Gtk only updates the position and size asynchrounously on
    configure events and hidden windows return invalid values.
    Auto-show et al need valid values from get_position and
    get_size at all times.
    """
    def __init__(self):
        self._window_rect = None
        self._origin = None
        self._screen_orientation = None
        self._save_position_timer = Timer()

        # init detection of screen "rotation"
        screen = self.get_screen()
        screen.connect('size-changed', self._on_screen_size_changed)

    def cleanup(self):
        self.stop_save_position_timer()
        self.save_window_rect()

    def move(self, x, y):
        """
        Overload Gtk.Window.move to reliably keep track of
        the window position.
        """
        self._window_rect.x, self._window_rect.y = x, y
        Gtk.Window.move(self, x, y)
        if self.is_visible():
            self._origin = self.get_window().get_origin()

    def resize(self, w, h):
        """
        Overload Gtk.Window.size to reliably keep track of
        the window size.
        """
        self._window_rect.w, self._window_rect.h = w, h
        Gtk.Window.resize(self, w, h)

    def move_resize(self, x, y, w, h):
        win = self.get_window()
        if win:
            win.move_resize(x, y, w, h)
            self._window_rect = Rect(x, y, w, h)
            if self.is_visible():
                self._origin = win.get_origin()

    def get_position(self):
        if self._window_rect is None:
            return Gtk.Window.get_position(self)
        else:
            return self._window_rect.get_position()

    def get_size(self):
        if self._window_rect is None:
            return Gtk.Window.get_size(self)
        else:
            return self._window_rect.get_size()

    def get_origin(self):
        if self._origin is None:
            return self.get_window().get_origin()
        else:
            return self._origin

    def get_rect(self):
        return self._window_rect

    def is_visible(self):
        """ This is overloaded in KbdWindow """
        return Gtk.Window.get_visible(self)

    def _on_screen_size_changed(self, screen):
        """ detect screen rotation (tablets)"""
        self.stop_save_position_timer()

        self.save_window_rect()
        self.restore_window_rect()

    def get_screen_orientation(self):
        """
        Current orientation of the screen (tablet rotation).
        Only the aspect ratio is taken into account at this time.
        This appears to cover more cases than loocking at monitor rotation,
        in particular with multi-monitor screens.
        """
        screen = self.get_screen()
        if screen.get_width() >= screen.get_height():
            return Orientation.LANDSCAPE
        else:
            return Orientation.PORTRAIT

    def update_window_rect(self):
        """
        Call this on configure event, the only time when
        get_position, get_size, etc. can be trusted.
        """
        if self.is_visible():
            self._window_rect = Rect.from_position_size(Gtk.Window.get_position(self),
                                                        Gtk.Window.get_size(self))
            self._origin      = self.get_window().get_origin()
            self._screen_orientation = self.get_screen_orientation()

            self.start_save_position_timer()

    def restore_window_rect(self):
        """
        Restore window size and position.
        """
        orientation = self.get_screen_orientation()
        rect = self.read_window_rect(orientation)

        self._screen_orientation = orientation
        self._window_rect = rect
        _logger.debug("restore_window_rect {rect}, {orientation}" \
                      .format(rect = rect, orientation = orientation))

        # Give the derived class a chance to modify the rect,
        # for example to correct the position for auto-show.
        rect = self.on_restore_window_rect(rect)

        # move/resize the window
        self.set_default_size(rect.w, rect.h)
        self.move(rect.x, rect.y)
        self.resize(rect.w, rect.h)

    def on_restore_window_rect(self, rect):
        return rect

    def save_window_rect(self):
        """
        Save window size and position.
        """
        # Give the derived class a chance to modify the rect,
        # for example to override it for auto-show.
        rect = self.on_save_window_rect(self._window_rect)

        orientation = self._screen_orientation
        self.write_window_rect(orientation, rect)

        _logger.debug("save_window_rect {rect}, {orientation}" \
                      .format(rect = rect, orientation = orientation))

    def on_save_window_rect(self, rect):
        return rect

    def read_window_rect(self, orientation, rect):
        """
        Read orientation dependent rect.
        Overload this in derived classes.
        """
        raise NotImplementedError()

    def write_window_rect(self, orientation, rect):
        """
        Write orientation dependent rect.
        Overload this in derived classes.
        """
        raise NotImplementedError()

    def start_save_position_timer(self):
        """
        Trigger saving position and size to gsettings
        Delay this a few seconds to avoid excessive disk writes.

        Remember the current rect and rotation as the screen may have been
        rotated when the saving happens.
        """
        self._save_position_timer.start(5, self.save_window_rect)

    def stop_save_position_timer(self):
        self._save_position_timer.stop()


