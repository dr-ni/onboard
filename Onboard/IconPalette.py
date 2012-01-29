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

from Onboard.utils import Orientation, WindowRectTracker, \
                          Handle, WindowManipulator, \
                          Rect, round_corners

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

        # load the onboard icon
        self.icon = self._load_icon()

        self.update_sticky_state()

    def cleanup(self):
        WindowRectTracker.cleanup(self)

    def _on_configure_event(self, widget, user_data):
        self.update_window_rect()

    def update_sticky_state(self):
        if not config.xid_mode:
            if config.get_sticky_state():
                self.stick()
            else:
                self.unstick()

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

    def get_drag_handles(self):
        """ Overload for WindowManipulator """
        return (Handle.SOUTH_EAST, )

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
        if Gtk.cairo_should_draw_window(cr, self.get_window()):
            width = float(self.get_allocated_width())
            height = float(self.get_allocated_height())

            cr.save()
            cr.scale(width / self.icon_size[0], height / self.icon_size[1])
            cr.set_source_surface(self.icon, 0, 0)
            cr.paint()
            cr.restore()

            if Gdk.Screen.get_default().is_composited():
                cr.set_operator(cairo.OPERATOR_CLEAR)
                round_corners(cr, 8, 0, 0, width, height)
                cr.set_operator(cairo.OPERATOR_OVER)

            return True
        return False

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


