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
    pango_layout = None

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

        if self.pango_layout is None: # work around memory leak (gnome #599730)
            self.pango_layout = context.create_layout()
        self.pango_layout.set_text(self.get_label())
        font_description = pango.FontDescription()
        font_description.set_size(self.font_size)
        font_description.set_family("Normal")
        self.pango_layout.set_font_description(font_description)
        context.update_layout(self.pango_layout)
        context.show_layout(self.pango_layout)


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
        if label_width == 0: label_width = 1

        size_for_maximum_width = pane_context.scale_log_to_canvas_x(
                (self.geometry[0] - config.LABEL_MARGIN[0]) \
                * pango.SCALE \
                * BASE_FONTDESCRIPTION_SIZE) \
            / label_width

        size_for_maximum_height = pane_context.scale_log_to_canvas_y(
                (self.geometry[1] - config.LABEL_MARGIN[1]) \
                * pango.SCALE \
                * BASE_FONTDESCRIPTION_SIZE) \
            / label_height

        if size_for_maximum_width < size_for_maximum_height:
            return int(floor(size_for_maximum_width))
        else:
            return int(floor(size_for_maximum_height))

pango_layout = None
class FixedFontMixin:

    @staticmethod
    def calc_font_size(pane_context, size):
        # font size is based on the height of the template key
        font_size = int(pane_context.scale_log_to_canvas_y(
                                 size[1] * pango.SCALE) * 0.4)
        return font_size

    @staticmethod
    def get_pango_layout(pane_context, context, size):
        """ offset for centered label """
        global pango_layout
        font_size = FixedFontMixin.calc_font_size(pane_context, size)
        if pango_layout is None: # work around memory leak (gnome #599730)
            pango_layout = context.create_layout()
        font_description = pango.FontDescription()
        font_description.set_family("Normal")
        font_description.set_size(font_size)
        pango_layout.set_font_description(font_description)
        context.update_layout(pango_layout)
        return pango_layout

    @staticmethod
    def calc_text_size(pane_context, pane_layout, size, text):
        """ offset for centered label """
        # center text
        pango_layout.set_text(text) # for maximum y-extent
        label_width, label_height = pango_layout.get_size()
        log_width  = pane_context.scale_canvas_to_log_x(
                                            label_width / pango.SCALE)
        log_height = pane_context.scale_canvas_to_log_y(
                                            label_height / pango.SCALE)
        return log_width,log_height

    @staticmethod
    def calc_label_offset(pane_context, pango_layout, size, text ="Tg"):
        """ offset for centered label """
        log_width,log_height = FixedFontMixin.calc_text_size(pane_context,
                                        pango_layout, size, text)
        xoffset = (size[0] - log_width ) / 2
        yoffset = (size[1] - log_height) / 2
        return xoffset,yoffset

    def __init__(self):
        self.initial_paint = True

    def get_best_font_size(self, pane_context, context):
        return FixedFontMixin.calc_font_size(pane_context, self.geometry)

    def paint_font(self, pane_context, context = None):

        # center label vertically
        if self.initial_paint:
            self.initial_paint = False
            pango_layout = FixedFontMixin.get_pango_layout(pane_context, context, self.geometry)
            self.label_offset = (self.label_offset[0],
              WordKey.calc_label_offset(pane_context, pango_layout, self.geometry)[1])



class WordKey(FixedFontMixin, RectKey):
    def __init__(self, name, location, geometry, rgba):
        FixedFontMixin.__init__(self)
        RectKey.__init__(self, name, location, geometry, rgba)

    def paint_font(self, pane_context, context = None):
        FixedFontMixin.paint_font(self, pane_context, context)
        RectKey.paint_font(self, pane_context, context)


class InputLineKey(FixedFontMixin, RectKey, InputLineKeyCommon):

    cursor = 0
    last_cursor = 0

    def __init__(self, name, location, geometry, rgba):
        FixedFontMixin.__init__(self)
        RectKey.__init__(self, name, location, geometry, rgba)
        self.word_infos = []

    def set_content(self, line, word_infos, cursor):
        self.line = line
        self.word_infos = word_infos
        self.last_cursor = self.cursor
        self.cursor = cursor

    def paint_font(self, pc, cr):
        FixedFontMixin.paint_font(self, pc, cr)

        pango_layout = FixedFontMixin.get_pango_layout(pc, cr,
                                                       self.geometry)

        l = pc.log_to_canvas_x(self.location[0] + self.label_offset[0])
        t = pc.log_to_canvas_y(self.location[1] + self.label_offset[1])
        r = pc.log_to_canvas_x(self.location[0] + self.geometry[0] \
                                         - self.label_offset[0])
        b = pc.log_to_canvas_y(self.location[1] + self.geometry[1] \
                                         - self.label_offset[1])

        pango_layout.set_text(self.line)

        # set text colors, highlight unknown words
        attrs = pango.AttrList()
        for wi in self.word_infos:
            # highlight only up to cursor if this is the current word
            cursor_in_word = (wi.start < self.cursor and self.cursor <= wi.end)
            end = wi.end
            if cursor_in_word:
                end = self.cursor
            attr = None
            if wi.ignored:
                attr = pango.AttrForeground(0, 256*256-1, 256*256-1, wi.start, end)
            elif not wi.exact_match:
                if wi.partial_match:
                    attr = pango.AttrForeground(256*256-1, 256*256-1, 0, wi.start, end)
                else:
                    attr = pango.AttrForeground(256*256-1, 0, 0, wi.start, end)
            if attr:
                attrs.insert(attr)
        #print [(wi.exact_match,wi.partial_match,wi.ignored) for wi in self.word_infos]

        pango_layout.set_attributes(attrs)
        #print pango_layout.get_cursor_pos(0)
        #print pango_layout.get_cursor_pos(len(self.line))

        # get x position of every character
        widths = []
        char_x = []
        iter = pango_layout.get_iter()
        while True:
            e = iter.get_char_extents()
            char_x.append(e[0]/pango.SCALE)
            widths.append(e[2]/pango.SCALE)
            if not iter.next_char():
                char_x.append((e[0]+e[2])/pango.SCALE)
                break
        #print "draw",self.cursor,char_x,r - l

        # find first (left-most) character that fits into the available space
        start = 0
        while True:
            cursor_x = char_x[self.cursor - start]
            if cursor_x < r - l:
                break
            start += 1
        #print start, self.cursor,char_x[start]

        # draw text clipped to available rectangle
        cr.set_source_rgba(self.label_rgba[0], self.label_rgba[1],
                           self.label_rgba[2], self.label_rgba[3])
        cr.rectangle(l, t, r-l, b-t)
        cr.save()
        cr.clip()
        cr.move_to(l-char_x[start], t)
        cr.show_layout(pango_layout)
        #cr.reset_clip()
        cr.restore()

