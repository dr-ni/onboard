#!/usr/bin/env python


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


import pygtk
import gtk

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

ICON_FILE_WITH_PATH    = "/usr/share/onboard/data/onboard.svg"
GROWBOX_FILE_WITH_PATH = "/usr/share/onboard/data/growbox.gif"

DRAG_THRESHOLD = 8 # in pixels; 8 is the default gtk value


class IconPalette(gtk.Window):

    def __init__(self):
        gtk.Window.__init__(self)

        # get size and position stored in gconf
        self.icpXPos = config.icp_x_position
        self.icpYPos = config.icp_y_position
        self.icpWidth = config.icp_width
        self.icpHeight = config.icp_height


        # create iconpalette starting by the inherited gtk.window
        self.set_accept_focus(False)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_property('skip-taskbar-hint', True)
        self.set_resizable(True)
        self.set_geometry_hints(self,20,20,     # minimum width, height
                                -1,-1,          # maximum width, height
                                self.icpWidth,  # base width
                                self.icpHeight, # base height
                                1,1,            # width, height resize increment
                                -1,-1)          # min, max aspect ratio
        self.set_border_width(0)

        # default coordinates of the iconpalette on the screen
        self.move(self.icpXPos, self.icpYPos)

        # setup content of the iconpalette
        self.iconPixbuf = gtk.gdk.pixbuf_new_from_file(ICON_FILE_WITH_PATH)
        self.growboxPixbuf = gtk.gdk.pixbuf_new_from_file(GROWBOX_FILE_WITH_PATH)
        self.growboxSize = self.growboxPixbuf.get_width() # growbox is a square
        iconPixbufScaled = self.iconPixbuf.scale_simple(self.icpWidth,
                                                        self.icpHeight,
                                                        gtk.gdk.INTERP_BILINEAR)
        self.growboxPixbuf.copy_area(0, 0,
                                     self.growboxSize, self.growboxSize,
                                     iconPixbufScaled,
                                     self.icpWidth - self.growboxSize,
                                     self.icpHeight - self.growboxSize)
        self.icpImage = gtk.Image()
        self.icpImage.set_from_pixbuf(iconPixbufScaled)
        self.align = gtk.Fixed()
        self.align.put(self.icpImage, 0, 0)
        self.add(self.align)

        # set up event handling
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK
                      | gtk.gdk.BUTTON_RELEASE_MASK
                      | gtk.gdk.BUTTON1_MOTION_MASK)
        self.connect("button-press-event", self._cb_start_click_or_move_resize)
        self.connect("motion-notify-event", self._cb_move_resize_action)
        self.connect("configure-event", self._cb_redraw_and_save)
        self.connect("button-release-event", self._cb_click_action)

        # set up flags and variables needed by the callbacks
        self.forbidShowing = False # is set to true by kbdwindow, when kbdwindow is visible
        self.button1Pressed   = False # for the callbacks to immediately return if it is not a button 1 events
        self.button1PressXPos = 0     # needed in the motion event callback to ignore little movements
        self.button1PressYPos = 0
        self.button1PressTime = 1     # to determine whether it is a click (releaseTime - pressTime < clickTime)
        self.pressInResizeArea = False # when configuring: whether it is a resize or a move

        # specify what functions should handle changes in the gconf keys of the icon palette
        config.icp_in_use_change_notify_add(self.do_in_use_gconf_toggled)
        config.icp_size_change_notify_add(self.resize)
        config.icp_position_change_notify_add(self.move)

    def _is_click_in_growbox(self, event):
        response = False
        width, height = self.get_size()
        if width - self.growboxSize < event.x and event.x < width  and \
           height - self.growboxSize < event.y  and event.y < height:
            response = True
        return response

    def _cb_start_click_or_move_resize(self, widget, event):
        # print "_cb_start_click_or_move_resize"
        if not event.button == 1: # we are only interested in button 1 events
            return
        self.button1Pressed = True
        self.button1PressTime = event.time # needed in the buttonrelease callback, to determine whether it is a click
        self.button1PressXPos = event.x_root # needed to check whether movement is below threshold
        self.button1PressYPos = event.y_root
        self.pressInResizeArea = self._is_click_in_growbox(event)

    def _cb_move_resize_action(self, widget, event):
        # print "_cb_move_resize_action"
        if not self.button1Pressed: # we are only interested in button 1 events
            return

        if abs(event.x_root - self.button1PressXPos) < DRAG_THRESHOLD \
        and abs(event.y_root - self.button1PressYPos) < DRAG_THRESHOLD:
            return      # we ignore movements smaller than the threshold

        if self.pressInResizeArea:
            iconPixbufScaled = self.iconPixbuf.scale_simple(self.icpWidth,
                                            self.icpHeight,
                                            gtk.gdk.INTERP_BILINEAR)
            self.icpImage.set_from_pixbuf(iconPixbufScaled) # draw content without growbox; it is nicer here
            self.begin_resize_drag(gtk.gdk.WINDOW_EDGE_SOUTH_EAST, 1,
                                   int(event.x_root), int(event.y_root), event.time)
        else:
            self.begin_move_drag(1, int(event.x_root), int(event.y_root), event.time)
        # REMARK: begin_resize_drag() and begin_move_drag() seem to run
        # asynchronally: in other words, if there is code after them, it will
        # in most cases  run before the move or the resize have finished.
        # To execute code after begin_resize_drag() and begin_move_drag(),
        # the callback of the configure event can probably be used.

    def _cb_redraw_and_save(self, event, user_data):
        # print "_cb_redraw_and_save"
        self.button1Pressed = False
        self.icpWidth, self.icpHeight = self.get_size()
        self.icpXPos, self.icpYPos = self.get_position()

        # Draw content of iconPalette
        iconPixbufScaled = self.iconPixbuf.scale_simple(self.icpWidth, self.icpHeight, gtk.gdk.INTERP_BILINEAR)
        self.growboxPixbuf.copy_area(0, 0,
                                     self.growboxSize, self.growboxSize,
                                     iconPixbufScaled,
                                     self.icpWidth - self.growboxSize,
                                     self.icpHeight - self.growboxSize)
        self.icpImage.set_from_pixbuf(iconPixbufScaled)

        # Store new values to gconf keys
        if config.icp_width != self.icpWidth: config.icp_width = self.icpWidth
        if config.icp_height != self.icpHeight: config.icp_height = self.icpHeight
        if config.icp_x_position != self.icpXPos: config.icp_x_position = self.icpXPos
        if config.icp_y_position != self.icpYPos: config.icp_y_position = self.icpYPos

    def _cb_click_action(self, widget, event):
        # print "_cb_click_action"
        if not event.button == 1: # we are only interested in button 1 events
            return
        if abs(event.x_root - self.button1PressXPos) < DRAG_THRESHOLD \
        and abs(event.y_root - self.button1PressYPos) < DRAG_THRESHOLD:
            self.iconify
            self._run_click_callbacks() # contains callbacks added by other modules
        self.button1Pressed = False


    def do_show(self):
        self.move(self.icpXPos, self.icpYPos) # necessary otherwise under some
        # circumstances that I don't understand yet, the icp does not
        # reappear where it disappeared (probably position in wm != position in X)
        self.show_all()

    def do_hide(self):
        self.hide_all()


    def do_in_use_gconf_toggled(self, cnxn_id=None, entry=None, user_data=None, thing=None):
        # print "do_in_use_gconf_toggled"
        if config.icp_in_use:
            if self.forbidShowing:
                self.do_hide()
            else:
                self.do_show()
        else:
            self.do_hide()


    # setup a way to pass from other modules what has to happen when
    # the icp is clicked
    _click_on_icp_callbacks = []

    def add_click_callback(self, callback):
        self._click_on_icp_callbacks.append(callback)

    def _run_click_callbacks(self):
        for callback in self._click_on_icp_callbacks:
            callback()



if __name__ == "__main__":
    iconPalette = IconPalette()
    iconPalette.do_show()
    gtk.main()



