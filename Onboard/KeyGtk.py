# -*- coding: UTF-8 -*-

import pango

from math import floor

from Onboard.KeyCommon import *

### Logging ###
import logging
_logger = logging.getLogger("KeyGTK")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

BASE_FONTDESCRIPTION_SIZE = 10000000

class Key(KeyCommon):
    def __init__(self):
        KeyCommon.__init__(self)

    def get_best_font_size(self, scale, context):
        """
        Get the maximum font possible that would not cause the label to
        overflow the boundaries of the key.
        """

        raise NotImplementedException()

    def paint_font(self, scale, location, context):

        context.move_to((location[0] + self.label_offset[0]) * scale[0],
                        (location[1] + self.label_offset[1]) * scale[1])

        context.set_source_rgba(self.label_rgba[0], self.label_rgba[1],
                                self.label_rgba[2], self.label_rgba[3])
        layout = context.create_layout()
        layout.set_text(self.labels[self.label_index])
        font_description = pango.FontDescription()
        font_description.set_size(self.font_size)
        font_description.set_family("Normal")
        layout.set_font_description(font_description)
        context.update_layout(layout)
        context.show_layout(layout)


class TabKey(Key, TabKeyCommon):
    def __init__(self, keyboard, width, pane):
        TabKeyCommon.__init__(self, keyboard, width, pane)
        Key.__init__(self)

    def paint(self, context = None):
        TabKeyCommon.paint(self, context)
        context.rectangle(self.keyboard.kbwidth,
                          self.height * self.index + BASE_PANE_TAB_HEIGHT, self.width, self.height)

        if self.pane == self.keyboard.activePane and self.stuckOn:
            context.set_source_rgba(1, 0, 0,1)
        else:
            context.set_source_rgba(float(self.pane.rgba[0]), float(self.pane.rgba[1]),float(self.pane.rgba[2]),float(self.pane.rgba[3]))

        context.fill()


class BaseTabKey(Key, BaseTabKeyCommon):
    def __init__(self, keyboard, width):
        BaseTabKeyCommon.__init__(self, keyboard, width)
        Key.__init__(self)

    ''' this class has no UI-specific code at all. Why? '''
    def paint(self,context):
        #We don't paint anything here because we want it to look like the base pane.
        pass

class LineKey(Key, LineKeyCommon):
    def __init__(self, name, coordList, fontCoord, rgba):
        LineKeyCommon.__init__(self, name, coordList, fontCoord, rgba)
        Key.__init__(self)

    def point_within_key(self, location, scale, context):
        """Cairo specific, hopefully fast way of doing this"""

        context = widget.window.cairo_create()
        self.draw_path(scale[0], scale[1], context)
        return context.in_fill(location[0], location[1])

    def paint(self, scale, context):
        self.draw_path(scale, context)

        if (self.stuckOn):
            context.set_source_rgba(1.0, 0.0, 0.0,1.0)
        elif (self.on):
            context.set_source_rgba(0.5, 0.5, 0.5,1.0)
        elif (self.beingScanned):
            context.set_source_rgba(0.45,0.45,0.7,1.0)
        else:
            context.set_source_rgba(self.rgba[0], self.rgba[1],self.rgba[2],self.rgba[3])

        context.fill_preserve()
        context.set_source_rgb(0, 0, 0)
        context.stroke()

    def draw_path(self, scale, context):
        ''' currently this method contains all the LineKey
            painting code. '''

        LineKeyCommon.paint(self, scale, context = None)
        c = 2
        context.move_to(self.coordList[0] * scale[0],
                        self.coordList[1] * scale[1])

        while not c == len(self.coordList):
            xp1 = self.coordList[c+1] * scale[0]
            yp1 = self.coordList[c+2] * scale[1]
            try:
                if self.coordList[c] == "L":
                    c +=3
                    context.line_to(xp1,yp1)
                else:
                    xp2 = self.coordList[c+3] * scale[0]
                    yp2 = self.coordList[c+4] * scale[1]
                    xp3 = self.coordList[c+5] * scale[0]
                    yp3 = self.coordList[c+6] * scale[1]
                    context.curve_to(xp1,yp1,xp2,yp2,xp3,yp3)
                    c += 7

            except TypeError, (strerror):
                print yp1
                print strerror



    def paint_font(self, scale, context = None):
        Key.paint_font(self, scale, self.fontCoord, context)



class RectKey(Key, RectKeyCommon):
    def __init__(self, name, location, geometry, rgba):
        RectKeyCommon.__init__(self, name, location, geometry, rgba)

    def point_within_key(self, location, scale, context):
        return RectKeyCommon.point_within_key(self, location, scale)

    def paint(self, scale, context = None):

        context.rectangle(self.location[0] * scale[0],
                          self.location[1] * scale[1],
                          self.geometry[0] * scale[0],
                          self.geometry[1] * scale[1])

        if (self.stuckOn):
            context.set_source_rgba(1, 0, 0,1)
        elif (self.on):
            context.set_source_rgba(0.5, 0.5, 0.5,1)
        elif (self.beingScanned):
            context.set_source_rgba(0.45,0.45,0.7,1)
        else:
            context.set_source_rgba(self.rgba[0], self.rgba[1],self.rgba[2],self.rgba[3])

        context.fill_preserve()
        context.set_source_rgb(0, 0, 0)
        context.stroke()

    def paint_font(self, scale, context = None):
        Key.paint_font(self, scale, self.location, context)

    def get_best_font_size(self, scale, context):
        """
        Get the maximum font possible that would not cause the label to
        overflow the boundaries of the key.
        """

        layout = pango.Layout(context)
        layout.set_text(self.labels[self.label_index])
        font_description = pango.FontDescription()
        font_description.set_size(BASE_FONTDESCRIPTION_SIZE)
        font_description.set_family("Normal")
        layout.set_font_description(font_description)

        # In Pango units
        label_width, label_height = layout.get_size()

        size_for_maximum_width = (self.geometry[0] - config.LABEL_MARGIN[0]) \
                * pango.SCALE \
                * scale[0] \
                * BASE_FONTDESCRIPTION_SIZE \
            / label_width

        size_for_maximum_height = (self.geometry[1] - config.LABEL_MARGIN[1]) \
                * pango.SCALE \
                * scale[1] \
                * BASE_FONTDESCRIPTION_SIZE \
            / label_height

        if size_for_maximum_width < size_for_maximum_height:
            return int(floor(size_for_maximum_width))
        else:
            return int(floor(size_for_maximum_height))

