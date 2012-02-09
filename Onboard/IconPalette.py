#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright © 2008 Francesco Fumanti <francesco.fumanti@gmx.net>
#
# This file is part of Onboard.
#
# Onboard is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Onboard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from __future__ import division, print_function, unicode_literals

from os.path import join
from traceback import print_exc

from gi.repository import GObject, Gdk, Gtk

import cairo

from Onboard.utils       import Rect, round_corners, roundrect_arc, \
                                hexstring_to_float
from Onboard.WindowUtils import WindowManipulator, WindowRectTracker, \
                                Orientation
from Onboard.KeyGtk      import RectKey 

### Logging ###
import logging
_logger = logging.getLogger("IconPalette")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

from gettext import gettext as _

class IconPalette(Gtk.Window, WindowRectTracker, WindowManipulator):
    """
    Class that creates a movable and resizable floating window without
    decorations. The window shows the icon of onboard scaled to fit to the
    window and a resize grip that honors the desktop theme in use.

    Onboard offers an option to the user to make the window appear
    whenever the user hides the onscreen keyboard. The user can then
    click on the window to hide it and make the onscreen keyboard
    reappear.
    """

    __gsignals__ = {
        str('activated') : (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ())
    }

    """ Minimum size of the IconPalette """
    MINIMUM_SIZE = 20

    _keyboard = None

    def __init__(self):

        self._last_pos = None

        Gtk.Window.__init__(self,
                            skip_taskbar_hint=True,
                            skip_pager_hint=True,
                            decorated=False,
                            accept_focus=False,
                            opacity=0.75,
                            width_request=self.MINIMUM_SIZE,
                            height_request=self.MINIMUM_SIZE)

        WindowRectTracker.__init__(self)
        WindowManipulator.__init__(self)

        self.set_keep_above(True)
        self.set_has_resize_grip(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)

        # use transparency if available
        visual = Gdk.Screen.get_default().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # set up event handling
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK)

        self.connect("button-press-event",   self._on_button_press_event)
        self.connect("motion-notify-event",  self._on_motion_notify_event)
        self.connect("button-release-event", self._on_button_release_event)
        self.connect("draw",                 self._on_draw)
        self.connect("configure-event",      self._on_configure_event)

        # don't get resized by compiz grid plugin (LP: 893644)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        # create Gdk resources before moving or resizing the window
        self.realize()

        # default coordinates of the iconpalette on the screen
        self.restore_window_rect()

        config.icp.size_notify_add(lambda x: self.restore_window_rect())
        config.icp.position_notify_add(lambda x: self.restore_window_rect())
        config.icp.resize_handles_notify_add(lambda x: self.update_resize_handles())

        # load the onboard icon
        self.icon = self._load_icon()

        self.update_sticky_state()
        self.update_resize_handles()

    def cleanup(self):
        WindowRectTracker.cleanup(self)

    def set_keyboard(self, keyboard):
        self._keyboard = keyboard
        self.queue_draw()

    def get_color_scheme(self):
        if self._keyboard:
            return self._keyboard.color_scheme
        return None

    def _on_configure_event(self, widget, user_data):
        self.update_window_rect()

    def update_sticky_state(self):
        if not config.xid_mode:
            if config.get_sticky_state():
                self.stick()
            else:
                self.unstick()

    def update_resize_handles(self):
        """ Tell WindowManipulator about the active resize handles """
        self.set_drag_handles(config.icp.resize_handles)

    def _load_icon(self):
        """
        Load the onboard icon and create a cairo surface.
        """
        theme = Gtk.IconTheme.get_default()
        pixbuf = None

        if theme.has_icon("onboard"):
            try:
                pixbuf = theme.load_icon("onboard", 192, 0)
            except:
                print_exc() # bug in oneiric: unsupported icon format svg
                _logger.error(_("Failed to load Onboard icon."))

        if not pixbuf:
            pixbuf = self.render_icon_pixbuf(Gtk.STOCK_MISSING_IMAGE,
                                             Gtk.IconSize.DIALOG)

        self.icon_size = (pixbuf.get_width(), pixbuf.get_height())

        icon = self.get_window().create_similar_surface(cairo.CONTENT_COLOR_ALPHA,
                                                        self.icon_size[0],
                                                        self.icon_size[1])
        cr = cairo.Context(icon)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()

        return icon

    def get_drag_threshold(self):
        """ Overload for WindowManipulator """
        return config.get_drag_threshold()

    def _on_button_press_event(self, widget, event):
        """
        Save the pointer position.
        """
        if event.button == 1 and event.window == self.get_window():
            self.enable_drag_protection(True)
            self.handle_press(event, move_on_background = True)
            if self.is_moving():
                self.reset_drag_protection() # force threshold
        return False

    def _on_motion_notify_event(self, widget, event):
        """
        Move the window if the pointer has moved more than the DND threshold.
        """
        self.handle_motion(event)
        self.set_drag_cursor_at((event.x, event.y))
        return False

    def _on_button_release_event(self, widget, event):
        """
        Save the window geometry, hide the IconPalette and
        emit the "activated" signal.
        """
        result = False

        if event.button == 1 and \
           event.window == self.get_window() and \
           not self.is_drag_active():
            self.emit("activated")
            result = True

        self.stop_drag()
        self.set_drag_cursor_at((event.x, event.y))

        return result

    def _on_draw(self, widget, cr):
        """
        Draw the onboard icon.
        """
        if not Gtk.cairo_should_draw_window(cr, self.get_window()):
            return False
        
        width = float(self.get_allocated_width())
        height = float(self.get_allocated_height())

        if False:
            # draw onboard's icon
            cr.save()
            cr.scale(width / self.icon_size[0], height / self.icon_size[1])
            cr.set_source_surface(self.icon, 0, 0)
            cr.paint()
            cr.restore()

            if Gdk.Screen.get_default().is_composited():
                cr.set_operator(cairo.OPERATOR_CLEAR)
                round_corners(cr, 8, 0, 0, width, height)
                cr.set_operator(cairo.OPERATOR_OVER)

        else:
            keys = [RectKey("icon" + str(i)) for i in range(4)]
            color_scheme = self.get_color_scheme()

            # Default colors for the case when none of the icon keys 
            # are defined in the color scheme.
            background_rgba =  [1.0, 1.0, 1.0, 1.0]
            fill_rgbas      = [[0.9, 0.7, 0.0, 0.75],
                               [1.0, 1.0, 1.0, 1.0],
                               [1.0, 1.0, 1.0, 1.0],
                               [0.0, 0.54, 1.0, 1.0]]
            stroke_rgba     =  [0.0, 0.0, 0.0, 1.0]
            label_rgba      =  [0.0, 0.0, 0.0, 1.0]

            themed = False
            if color_scheme:
                if any(color_scheme.is_key_in_schema(key) for key in keys):
                    themed = True

            # clear background
            cr.save()
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.paint()
            cr.restore()

            # draw background color
            background_rgba = list(color_scheme.get_window_fill_rgba("icp"))

            if Gdk.Screen.get_default().is_composited():
                background_rgba[3] *= 0.75
                cr.set_source_rgba(*background_rgba)

                rect = Rect(0, 0, width, height)
                corner_radius = min(width, height) * 0.1

                roundrect_arc(cr, rect, corner_radius)
                cr.fill()

                # decoration frame
                line_rect = rect.deflate(2)
                cr.set_line_width(2)
                roundrect_arc(cr, line_rect, corner_radius)
                cr.stroke()
            else:
                cr.set_source_rgba(*background_rgba)
                cr.paint()

            # four rounded rectangles
            rects = Rect(0.0, 0.0, 100.0, 100.0).deflate(5) \
                                                .subdivide(2, 2, 6)
            cr.save()
            cr.scale(width / 100., height / 100.0)
            cr.select_font_face ("sans-serif")
            cr.set_line_width(2)

            for i, key in enumerate(keys):
                rect = rects[i]

                if themed:
                    fill_rgba   = color_scheme.get_key_rgba(key, "fill")
                    stroke_rgba  = color_scheme.get_key_rgba(key, "stroke")
                    label_rgba   = color_scheme.get_key_rgba(key, "label")
                else:
                    fill_rgba   = fill_rgbas[i]

                roundrect_arc(cr, rect, 5)
                cr.set_source_rgba(*fill_rgba)
                cr.fill_preserve()

                cr.set_source_rgba(*stroke_rgba)
                cr.stroke()

                if i == 0 or i == 3:
                    if i == 0:
                        letter = "O"
                    else:
                        letter = "B"

                    cr.set_font_size(25)
                    x_bearing, y_bearing, _width, _height, \
                    x_advance, y_advance = cr.text_extents(letter)
                    r = rect.align_rect(Rect(0, 0, _width, _height),
                                             0.3, 0.33)
                    cr.move_to(r.x - x_bearing, r.y - y_bearing)
                    cr.set_source_rgba(*label_rgba)
                    cr.show_text(letter)
                    cr.new_path()
                    
            cr.restore()
    
        return True

    def show(self):
        """
        Override Gtk.Widget.hide() to save the window geometry.
        """
        Gtk.Window.show(self)
        self.update_sticky_state()

    def hide(self):
        """
        Override Gtk.Widget.hide() to save the window geometry.
        """
        Gtk.Window.hide(self)

    def read_window_rect(self, orientation):
        """
        Read orientation dependent rect.
        Overload for WindowRectTracker.
        """
        if orientation == Orientation.LANDSCAPE:
            co = config.icp.landscape
        else:
            co = config.icp.portrait
        rect = Rect(co.x, co.y, co.width, co.height)
        return rect

    def write_window_rect(self, orientation, rect):
        """
        Write orientation dependent rect.
        Overload for WindowRectTracker.
        """
        # There are separate rects for normal and rotated screen (tablets).
        if orientation == Orientation.LANDSCAPE:
            co = config.icp.landscape
        else:
            co = config.icp.portrait

        config.settings.delay()
        co.x, co.y, co.width, co.height = rect
        config.settings.apply()


def icp_activated(self):
    Gtk.main_quit()

if __name__ == "__main__":
    icp = IconPalette()
    icp.show()
    icp.connect("activated", icp_activated)
    Gtk.main()


