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

    def get_best_font_size(self, pane_context, context):
        """
        Get the maximum font possible that would not cause the label to
        overflow the boundaries of the key.
        """

        raise NotImplementedException()

    def paint_font(self, pane_context, location, context):

        context.move_to(pane_context.log_to_canvas_x(
                                          location[0] + self.label_offset[0]),
                        pane_context.log_to_canvas_y(
                                          location[1] + self.label_offset[1]))

        context.set_source_rgba(self.label_rgba[0], self.label_rgba[1], 
                                self.label_rgba[2], self.label_rgba[3])        
        layout = context.create_layout()
        layout.set_text(self.get_label())
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

    def point_within_key(self, location, pane_context, context):
        """Cairo specific, hopefully fast way of doing this"""

        context = widget.window.cairo_create()
        self.draw_path(pane_context, context)
        return context.in_fill(location[0], location[1])

    def paint(self, pane_context, context):
        self.draw_path(pane_context, context)

        color = self.get_fill_color()
        context.set_source_rgba(color[0], color[1], color[2], color[3])

        context.fill_preserve()
        context.set_source_rgb(0, 0, 0)
        context.stroke()

    def draw_path(self, pane_context, context):
        ''' currently this method contains all the LineKey 
            painting code. '''

        LineKeyCommon.paint(self, pane_context, context = None)
        c = 2
        context.move_to(pane_context.log_to_canvas_x(self.coordList[0]), 
                        pane_context.log_to_canvas_y(self.coordList[1]))

        while not c == len(self.coordList):
            xp1 = pane_context.log_to_canvas_x(self.coordList[c+1])
            yp1 = pane_context.log_to_canvas_y(self.coordList[c+2])
            try:
                if self.coordList[c] == "L":
                    c +=3
                    context.line_to(xp1,yp1)
                else:   
                    xp2 = pane_context.log_to_canvas_x(self.coordList[c+3])
                    yp2 = pane_context.log_to_canvas_y(self.coordList[c+4])
                    xp3 = pane_context.log_to_canvas_x(self.coordList[c+5])
                    yp3 = pane_context.log_to_canvas_y(self.coordList[c+6])
                    context.curve_to(xp1,yp1,xp2,yp2,xp3,yp3)
                    c += 7

            except TypeError, (strerror):
                print yp1
                print strerror

                

    def paint_font(self, pane_context, context = None):
        Key.paint_font(self, pane_context, self.fontCoord, context)


    
class RectKey(Key, RectKeyCommon):
    def __init__(self, name, location, geometry, rgba):
        RectKeyCommon.__init__(self, name, location, geometry, rgba)

    def point_within_key(self, location, pane_context, context):
        return RectKeyCommon.point_within_key(self, location, pane_context)

    def paint(self, pane_context, context = None):
        
        context.rectangle(pane_context.log_to_canvas_x(self.location[0]),
                          pane_context.log_to_canvas_y(self.location[1]),
                          pane_context.scale_log_to_canvas_x(self.geometry[0]),
                          pane_context.scale_log_to_canvas_y(self.geometry[1]))

        color = self.get_fill_color()
        context.set_source_rgba(color[0], color[1], color[2], color[3])

        context.fill_preserve()
        context.set_source_rgb(0, 0, 0)
        context.stroke()

    def paint_font(self, pane_context, context = None):
        Key.paint_font(self, pane_context, self.location, context)

    def get_best_font_size(self, pane_context, context):
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
        
        size_for_maximum_width = pane_context.scale_log_to_canvas_x(
                (self.geometry[0] - config.LABEL_MARGIN[0]) \
                * pango.SCALE \
                * BASE_FONTDESCRIPTION_SIZE) \
            / label_width

        size_for_maximum_height = pane_context.scale_log_to_canvas_x(
                (self.geometry[1] - config.LABEL_MARGIN[1]) \
                * pango.SCALE \
                * BASE_FONTDESCRIPTION_SIZE) \
            / label_height

        if size_for_maximum_width < size_for_maximum_height:
            return int(floor(size_for_maximum_width))
        else:
            return int(floor(size_for_maximum_height))
        
