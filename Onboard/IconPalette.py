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

import gtk
import gobject

### Logging ###
import logging
_logger = logging.getLogger("IconPalette")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

DRAG_THRESHOLD = 8 # in pixels; 8 is the default gtk value

RESIZE_AREA_SIZE = 20 # Use a fictive but sensible size

class IconPalette(gtk.Window):
    """
    Class that creates a movable and resizable floating window without
    decorations.  The window shows the icon of onboard scaled to fit to the
    window and a resize grip that honors the desktop theme in use.

    Onboard offers an option to the user to make the window appear
    whenever the user hides the onscreen keyboard.  The user can then
    click on the window to hide it and make the onscreen keyboard
    reappear.
    """

    """Store whether the last click event was by button 1."""
    _button1_pressed = False

    """
    Needed in the motion-notify-event callback to ignore little movements
    and in the button-release-event callback to determine whether a click
    happened.
    """
    _button1_press_x_pos = 0
    _button1_press_y_pos = 0

    """When configuring: whether it is a resize or a move."""
    _is_press_in_resize_area = False

    def __init__(self):
        gtk.Window.__init__(self)
        _logger.debug("Entered in __init__")

        # create iconpalette starting by an inherited gtk.window
        self.set_accept_focus(False)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_property('skip-taskbar-hint', True)
        self.set_resizable(True)
        self.set_geometry_hints(self,
            20, 20,            # minimum width, height
            -1, -1,            # maximum width, height
            config.icp_width,  # base width
            config.icp_height, # base height
             1,  1,            # width, height resize increment
            -1, -1)            # min, max aspect ratio
        self.set_border_width(0)
        self.set_app_paintable(True)

        # default coordinates of the iconpalette on the screen
        self.move(config.icp_x_position, config.icp_y_position)
        self.resize(config.icp_width, config.icp_height)

        # set up attributes for content of icon palette
        icon_theme = gtk.icon_theme_get_default()
        if icon_theme.has_icon("onboard"):
            self.image_pixbuf = icon_theme.load_icon("onboard", 192, 0)
        else:
            _logger.error("Can't find onboard icon")
            self.image_pixbuf = self.render_icon(gtk.STOCK_MISSING_IMAGE,
                gtk.ICON_SIZE_DIALOG)
        self.icp_image = gtk.Image()
        self.image_box = gtk.Fixed()
        self.image_box.put(self.icp_image, 0, 0)
        self.add(self.image_box)

        # set up event handling
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK
                      | gtk.gdk.BUTTON_RELEASE_MASK
                      | gtk.gdk.BUTTON1_MOTION_MASK)
        self.connect("button-press-event", self._cb_start_click_or_move_resize)
        self.connect("motion-notify-event", self._cb_move_resize_action)
        self.connect("button-release-event", self._cb_click_action)
        self.connect("configure-event", self._cb_scale_and_save)
        self.connect("expose-event", self._cb_draw_resize_grip)

        config.icp_size_change_notify_add(self.resize)
        config.icp_position_change_notify_add(self.move)

        gobject.signal_new("activated", IconPalette, gobject.SIGNAL_RUN_LAST,
                gobject.TYPE_BOOLEAN, ())
        _logger.debug("Leaving __init__")

    def _is_click_in_resize_area(self, event):
        """Check whether the event occurred in the resize grip."""
        _logger.debug("Entered in _is_click_in_resize_area")
        response = False
        if config.icp_width - RESIZE_AREA_SIZE < event.x \
           and event.x < config.icp_width \
           and config.icp_height - RESIZE_AREA_SIZE < event.y \
           and event.y < config.icp_height:
            response = True
        return response

    def _cb_start_click_or_move_resize(self, widget, event):
        """
        This is the callback for the button-press-event.

        It initiates the variables used during the moving and resizing
        of the IconPalette window; and used to determine whether the
        button-press and button-release sequence can be considered a
        button click.
        """
        _logger.debug("Entered in _cb_start_click_or_move_resize()")
        if not event.button == 1: # we are only interested in button 1 events
            return
        self._button1_pressed = True
        _logger.debug("passed self._button1_pressed = True")
        self._is_press_in_resize_area = self._is_click_in_resize_area(event)

        # needed to check whether movement is below threshold
        self._button1_press_x_pos = event.x_root
        self._button1_press_y_pos = event.y_root

    def _cb_move_resize_action(self, widget, event):
        """
        This is the callback for the motion-notify-event.

        Depending on whether the button press occurred on the content of
        the window or on the resize grip, it asynchronuously calls
        gtk.Window.begin_move_drag() or gtk.Window.begin_resize_drag().
        """
        _logger.debug("Entered in _cb_move_resize_action()")
        # we are only interested in button 1 events
        if not self._button1_pressed:
            return
        _logger.debug("passed _button1_pressed")
        if abs(event.x_root - self._button1_press_x_pos) < DRAG_THRESHOLD \
        and abs(event.y_root - self._button1_press_y_pos) < DRAG_THRESHOLD:
            return  # we ignore movements smaller than the threshold
        _logger.debug("passed  ignore small movement")
        if self._is_press_in_resize_area:
            _logger.debug("Entering begin_resize_drag()")
            self.begin_resize_drag(gtk.gdk.WINDOW_EDGE_SOUTH_EAST, 1,
                                   int(event.x_root), int(event.y_root),
                                   event.time)
        else:
            _logger.debug("Entering begin_move_drag()")
            self.begin_move_drag(1, int(event.x_root), int(event.y_root),
                                 event.time)
        # REMARK: begin_resize_drag() and begin_move_drag() seem to run
        # asynchronously: in other words, if there is code after them, it will
        # in most cases run before the move or the resize have finished.
        # To execute code after begin_resize_drag() and begin_move_drag(),
        # the callback of the configure-event can probably be used.

    def _cb_scale_and_save(self, event, user_data):
        """
        This is the callback for the configure-event.

        It saves the geometry of the IconPalette window to the gconf keys
        by using the Config singleton.

        It scales the content of the IconPalette window to make it fit to
        the new window size.
        """
        _logger.debug("Entered in _cb_scale_and_save()")
        if self.get_property("visible"):
            # save size and position
            config.icp_width, config.icp_height = self.get_size()
            config.icp_x_position, config.icp_y_position = self.get_position()

            # draw content (does not draw resize grip)
            scaled_image_pixbuf = self.image_pixbuf.scale_simple(config.icp_width, \
                                                      config.icp_height, \
                                                      gtk.gdk.INTERP_BILINEAR)
            resize_grip_area = scaled_image_pixbuf.subpixbuf( \
                                        config.icp_width - RESIZE_AREA_SIZE, \
                                        config.icp_height - RESIZE_AREA_SIZE, \
                                        RESIZE_AREA_SIZE, RESIZE_AREA_SIZE)
            resize_grip_area.fill(0x00000000) # make transparent
            self.icp_image.set_from_pixbuf(scaled_image_pixbuf)
            del resize_grip_area
            del scaled_image_pixbuf
        # REMARK: After clicking on the iconpalette, another configure event
        # arrives after the iconpalette has been hidden and a wrong position
        # gets stored in the config keys. Therefore the visibility check.

    def _cb_draw_resize_grip(self, event, user_data):
        """
        This is the callback for the expose-event.

        It is responsible for drawing the resize grip.
        """
        _logger.debug("Entered in _cb_draw_resize_grip()")
        self.get_style().paint_resize_grip(self.window, \
                               gtk.STATE_NORMAL, \
                               None, self, None, \
                               gtk.gdk.WINDOW_EDGE_SOUTH_EAST, \
                               config.icp_width - RESIZE_AREA_SIZE, \
                               config.icp_height - RESIZE_AREA_SIZE, \
                               RESIZE_AREA_SIZE, RESIZE_AREA_SIZE)

    def _cb_click_action(self, widget, event):
        """
        This is the callback for the button-release-event.

        If the button-release occurs around the coordinates of the preceding
        button-press, it is considered to be a click (regardless of the
        time passed between the button-press and button-release).  The
        IconPalette gets hidden and the custom activated-event is emitted.
        """
        _logger.debug("Entered in _cb_click_action")
        if not event.button == 1: # we are only interested in button 1 events
            return
        self._button1_pressed = False
        self._is_press_in_resize_area = False
        if abs(event.x_root - self._button1_press_x_pos) < DRAG_THRESHOLD \
        and abs(event.y_root - self._button1_press_y_pos) < DRAG_THRESHOLD:
            self.do_hide()
            self.emit("activated")

    def do_show(self):
        """Show the IconPalette at the correct position on the desktop."""
        _logger.debug("Entered in do_show")
        self.move(config.icp_x_position, config.icp_y_position)
        # self.move() is necessary; otherwise under some
        # circumstances that I don't understand yet, the icp does not
        # reappear where it disappeared (probably position in wm != position
        # in X)
        self.show_all()

    def do_hide(self):
        """Hide the IconPalette."""
        _logger.debug("Entered in do_hide")
        self.hide_all()


if __name__ == "__main__":
    iconPalette = IconPalette()
    iconPalette.do_show()
    gtk.main()



