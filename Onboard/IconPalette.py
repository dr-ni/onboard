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
logger = logging.getLogger("IconPalette")
#logger.setLevel(logging.DEBUG)
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

DRAG_THRESHOLD = 8 # in pixels; 8 is the default gtk value

RESIZE_AREA_SIZE = 20 # Use a fictive but sensible size

class IconPalette(gtk.Window):

    """ Set to true by kbdwindow, when kbdwindow is visible """
    forbid_showing   = False 

    """ Store whether the last click event was by button 1 """
    _button1_pressed = False 

    """ needed in the motion event callback to ignore little movements """
    _button1_press_x_pos = 0     
    _button1_press_y_pos = 0

    """ 
    Used to determine whether button press is a click 
    (releaseTime - pressTime < clickTime)
    """
    _button1_press_time = 1  

    """ when configuring: whether it is a resize or a move """
    _is_press_in_resize_area = False 

    def __init__(self):
        gtk.Window.__init__(self)

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
        self.image_pixbuf = gtk.gdk.pixbuf_new_from_file( \
                join(config.install_dir, "data/onboard.svg"))
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

        config.icp_in_use_change_notify_add(self._cb_icp_in_use)
        config.icp_size_change_notify_add(self.resize)
        config.icp_position_change_notify_add(self.move)

        gobject.signal_new("activated", IconPalette, gobject.SIGNAL_RUN_LAST,
                gobject.TYPE_BOOLEAN, ())

    def _is_click_in_resize_area(self, event):
        response = False
        if config.icp_width - RESIZE_AREA_SIZE < event.x \
           and event.x < config.icp_width \
           and config.icp_height - RESIZE_AREA_SIZE < event.y \
           and event.y < config.icp_height:
            response = True
        return response

    def _cb_start_click_or_move_resize(self, widget, event):
        logger.debug("Entered in _cb_start_click_or_move_resize()")
        if not event.button == 1: # we are only interested in button 1 events
            return
        self._button1_pressed = True
        logger.debug("passed self._button1_pressed = True")
        self._is_press_in_resize_area = self._is_click_in_resize_area(event)

        # event.time is needed in the buttonrelease callback, to determine
        # whether it is a click
        self._button1_press_time = event.time 
        # needed to check whether movement is below threshold
        self._button1_press_x_pos = event.x_root 
        self._button1_press_y_pos = event.y_root

    def _cb_move_resize_action(self, widget, event):
        logger.debug("Entered in _cb_move_resize_action()")
        # we are only interested in button 1 events
        if not self._button1_pressed: 
            return
        logger.debug("passed _button1_pressed")
        if abs(event.x_root - self._button1_press_x_pos) < DRAG_THRESHOLD \
        and abs(event.y_root - self._button1_press_y_pos) < DRAG_THRESHOLD:
            return  # we ignore movements smaller than the threshold
        logger.debug("passed  ignore small movement")
        if self._is_press_in_resize_area:
            logger.debug("Entering begin_resize_drag()")
            self.begin_resize_drag(gtk.gdk.WINDOW_EDGE_SOUTH_EAST, 1,
                                   int(event.x_root), int(event.y_root), 
                                   event.time)
        else:
            logger.debug("Entering begin_move_drag()")
            self.begin_move_drag(1, int(event.x_root), int(event.y_root), 
                                 event.time)
        # REMARK: begin_resize_drag() and begin_move_drag() seem to run
        # asynchronously: in other words, if there is code after them, it will
        # in most cases run before the move or the resize have finished.
        # To execute code after begin_resize_drag() and begin_move_drag(),
        # the callback of the configure event can probably be used.

    def _cb_scale_and_save(self, event, user_data):
        logger.debug("Entered in _cb_scale_and_save()")
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
        logger.debug("Entered in _cb_draw_resize_grip()")
        self.get_style().paint_resize_grip(self.window, \
                               gtk.STATE_NORMAL, \
                               None, None, None, \
                               gtk.gdk.WINDOW_EDGE_SOUTH_EAST, \
                               config.icp_width - RESIZE_AREA_SIZE, \
                               config.icp_height - RESIZE_AREA_SIZE, \
                               RESIZE_AREA_SIZE, RESIZE_AREA_SIZE)

    def _cb_click_action(self, widget, event):
        logger.debug("Entered in _cb_click_action")
        if not event.button == 1: # we are only interested in button 1 events
            return
        self._button1_pressed = False
        self._is_press_in_resize_area = False
        if abs(event.x_root - self._button1_press_x_pos) < DRAG_THRESHOLD \
        and abs(event.y_root - self._button1_press_y_pos) < DRAG_THRESHOLD:
            self.do_hide()
            self.emit("activated")

    def do_show(self):
        self.move(config.icp_x_position, config.icp_y_position) 
        # self.move() is necessary; otherwise under some
        # circumstances that I don't understand yet, the icp does not
        # reappear where it disappeared (probably position in wm != position 
        # in X)
        self.show_all()

    def do_hide(self):
        self.hide_all()

    def _cb_icp_in_use(self, use_icp):
        if use_icp:
            if self.forbid_showing:
                self.do_hide()
            else:
                self.do_show()
        else:
            self.do_hide()


if __name__ == "__main__":
    iconPalette = IconPalette()
    iconPalette.do_show()
    gtk.main()



