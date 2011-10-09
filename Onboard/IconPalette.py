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

from os.path import join
from traceback import print_exc

from gi.repository import GObject, Gdk, Gtk

import cairo
import math

### Logging ###
import logging
_logger = logging.getLogger("IconPalette")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

from gettext import gettext as _

class IconPalette(Gtk.Window):
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
        'activated' : (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ())
    }

    """ Minimum size of the IconPalette """
    MINIMUM_SIZE = 20

    def __init__(self):

        Gtk.Window.__init__(self,
                            skip_taskbar_hint=True,
                            skip_pager_hint=True,
                            decorated=False,
                            accept_focus=False,
                            opacity=0.75,
                            width_request=self.MINIMUM_SIZE,
                            height_request=self.MINIMUM_SIZE)

        self.set_keep_above(True)

        # use transparency if available
        visual = Gdk.Screen.get_default().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # set up event handling
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.BUTTON1_MOTION_MASK)

        self.connect("button-press-event",   self._cb_button_press_event)
        self.connect("motion-notify-event",  self._cb_motion_notify_event)
        self.connect("button-release-event", self._cb_button_release_event)
        self.connect("draw",                 self._cb_draw)

        # get the DND threshold and save a squared version
        dnd = Gtk.Settings.get_default().get_property("gtk-dnd-drag-threshold")
        self.threshold_squared = dnd * dnd

        # create Gdk resources before moving or resizing the window
        self.realize()

        # default coordinates of the iconpalette on the screen
        self.move(config.icp.x, config.icp.y)
        self.resize(config.icp.width, config.icp.height)

        config.icp.size_notify_add(lambda x:
            self.resize(config.icp.width, config.icp.height))
        config.icp.position_notify_add(lambda x:
            self.move(config.icp.x, config.icp.y))

        # load the onboard icon
        self.icon = self._load_icon()

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

    def _is_move(self, x, y):
        dx, dy = x - self._last_pos[0], y - self._last_pos[1]
        distance = dx * dx + dy * dy
        return distance * distance > self.threshold_squared

    def _cb_button_press_event(self, widget, event):
        """
        Save the pointer position.
        """
        if event.button == 1 and event.window == self.get_window():
            self._last_pos = (event.x_root, event.y_root)
        return False

    def _cb_motion_notify_event(self, widget, event):
        """
        Move the window if the pointer has moved more than the DND threshold.
        """
        if event.window == self.get_window() and \
           self._is_move(event.x_root, event.y_root):
            self.begin_move_drag(1, event.x_root, event.y_root, event.time)
            return True
        return False

    def _cb_button_release_event(self, widget, event):
        """
        Save the window geometry, hide the IconPalette and
        emit the "activated" signal.
        """
        if event.button == 1 and event.window == self.get_window():
            self.emit("activated")
            return True
        return False

    def _paint_corners(self, cr, w, h):
        """
        Paint 3 round corners.
        """
        cr.set_operator(cairo.OPERATOR_CLEAR)
        # corner radius
        r = 8.0
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
        cr.set_operator(cairo.OPERATOR_OVER)

    def _cb_draw(self, widget, cr):
        """
        Draw the onboard icon.
        """
        if Gtk.cairo_should_draw_window(cr, self.get_window()):
            width = float(self.get_allocated_width())
            height = float(self.get_allocated_height())

            cr.save()
            cr.scale(width / self.icon_size[0], height / self.icon_size[1])
            cr.set_source_surface(self.icon, 0, 0)
            cr.paint()
            cr.restore()

            if Gdk.Screen.get_default().is_composited():
                self._paint_corners(cr, width, height)

            return True
        return False

    def hide(self):
        """
        Override Gtk.Widget.hide() to save the window geometry.
        """
        if Gtk.Window.get_visible(self):
            config.icp.width, config.icp.height = self.get_size()
            config.icp.x, config.icp.y = self.get_position()
            Gtk.Window.hide(self)


def icp_activated(self):
    Gtk.main_quit()

if __name__ == "__main__":
    icp = IconPalette()
    icp.show()
    icp.connect("activated", icp_activated)
    Gtk.main()


