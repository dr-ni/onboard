# -*- coding: UTF-8 -*-

import cairo
import pango
import colorsys

from math import floor, pi, sin, cos, sqrt

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
PangoUnscale = 1.0/pango.SCALE

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

        context.move_to(*pane_context.log_to_canvas(
                            (location[0] + self.label_offset[0]),
                             location[1] + self.label_offset[1]))

        layout = self.get_pango_layout(context, self.get_label(), 
                                                self.font_size)
        context.set_source_rgba(*self.label_rgba)
        context.show_layout(layout)

    @staticmethod
    def get_pango_layout(context, text, font_size):
        if Key.pango_layout is None: # work around memory leak (gnome #599730)
            Key.pango_layout = context.create_layout()
        layout = Key.pango_layout

        Key.prepare_pango_layout(layout, text, font_size)
        context.update_layout(layout)
        return layout

    @staticmethod
    def prepare_pango_layout(layout, text, font_size):
        if not text is None:
            layout.set_text(text)
        font_description = pango.FontDescription(config.key_label_font)
        font_description.set_size(font_size)
        layout.set_font_description(font_description)


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

        context.set_source_rgba(self.get_fill_color())
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

    def paint_font(self, pane_context, context = None):
        location = self.location

        layout = self.get_pango_layout(context, self.get_label(), 
                                                self.font_size)

        #now put it in the centre of the keycap
        #w,h=layout.get_size()
        #leftmargin=0.5*((self.geometry[0]* scale[0])-(w * PangoUnscale))
        #topmargin=0.5*((self.geometry[1]* scale[1])-(h * PangoUnscale))
        position = (location[0] + self.label_offset[0],
                    location[1] + self.label_offset[1])

        stroke_gradient   = config.key_stroke_gradient / 100.0
        if config.key_style != "flat" and stroke_gradient:
            fill = self.get_fill_color()
            d = 0.5  # fake emboss distance

            # shadow
            alpha = self.get_gradient_angle()
            xo = d * cos(alpha)
            yo = d * sin(alpha)
            rgba = self.brighten(-stroke_gradient*.5, *fill) # darker
            context.set_source_rgba(*rgba)
            x,y = pane_context.log_to_canvas((position[0]+xo, position[1]+yo))

            context.move_to(x,y)
            context.show_layout(layout)

            # highlight
            alpha = pi + self.get_gradient_angle()
            xo = d * cos(alpha)
            yo = d * sin(alpha)
            rgba = self.brighten(+stroke_gradient*.5, *fill) # brighter
            context.set_source_rgba(*rgba)
            x,y = pane_context.log_to_canvas((position[0]+xo, position[1]+yo))

            context.move_to(x,y)
            context.show_layout(layout)

            #context.move_to(x,y)
            #context.line_to(x+5,y+5)
            #context.set_source_rgba(1.0,0.0,0.0,1.0)
            #context.stroke()

        x,y = pane_context.log_to_canvas(position)
        context.move_to(x,y)
        context.set_source_rgba(*self.label_rgba)
        context.show_layout(layout)

    def get_gradient_angle(self):
        return -pi/2.0 - 2*pi * config.key_gradient_direction / 360.0

    def paint(self, pane_context, context):

        x0,y0 = pane_context.log_to_canvas(self.location)
        w,h   = pane_context.scale_log_to_canvas(self.geometry)
        t     = pane_context.scale_log_to_canvas((1.0, 1.0))
        line_width = (t[0] + t[1]) / 2.0
        fill = self.get_fill_color()

        if config.key_style == "flat":
            # old style key
            self.build_rect_path(context, x0, y0, w, h)
            context.set_source_rgba(*fill)
            context.fill_preserve()
            context.set_source_rgba(*self.stroke_rgba)
            context.set_line_width(line_width)
            context.stroke()

        elif config.key_style == "gradient":
            self.paint_gradient_key(context, x0, y0, w, h, fill, line_width)

        elif config.key_style == "dish":
            self.paint_dish_key(context, x0, y0, w, h, fill, line_width)


    def paint_dish_key(self, context, x0, y0, w, h, fill, line_width):
        # simple gradients for fill and stroke
        fill_gradient   = config.key_fill_gradient / 100.0
        stroke_gradient = config.key_stroke_gradient / 100.0
        alpha = self.get_gradient_angle()
        # unfinished

    def paint_gradient_key(self, context, x0, y0, w, h, fill, line_width):
        #if not self.name in ["RTSH", "SPCE"]:
        #    return

        # simple gradients for fill and stroke
        fill_gradient   = config.key_fill_gradient / 100.0
        stroke_gradient = config.key_stroke_gradient / 100.0
        alpha = self.get_gradient_angle()

        self.build_rect_path(context, x0, y0, w, h)
        gline = self.get_gradient_line(x0, y0, w, h, alpha)

        # fill
        if fill_gradient:
            pat = cairo.LinearGradient (*gline)
            rgba = self.brighten(+fill_gradient*.5, *fill)
            pat.add_color_stop_rgba(0, *rgba)
            rgba = self.brighten(-fill_gradient*.5, *fill)
            pat.add_color_stop_rgba(1, *rgba)
            context.set_source (pat)
        else: # take gradient from color scheme (not implemented)
            context.set_source_rgba(*fill)

        context.fill_preserve()

        # stroke
        if stroke_gradient:
            stroke = fill
            pat = cairo.LinearGradient (*gline)
            rgba = self.brighten(+stroke_gradient*.5, *stroke)
            pat.add_color_stop_rgba(0, *rgba)
            rgba = self.brighten(-stroke_gradient*.5, *stroke)
            pat.add_color_stop_rgba(1, *rgba)
            context.set_source (pat)
        else:
            context.set_source_rgba(*self.stroke_rgba)

        context.set_line_width(line_width)
        context.stroke()

        #context.move_to(*gline[:2])
        #context.line_to(*gline[2:4])
        #context.set_source_rgba(1.0,0.0,0.0,1.0)
        #context.stroke()

    def build_rect_path(self, context, x0, y0, w, h):
        r = config.roundrect_radius
        if r:
            self.roundrect(context, x0, y0, w, h, r)
        else:
            context.rectangle(x0, y0, w, h)

    def roundrect(self, context, x, y, w, h, r_pct = 100):
        # Uses B-Splines for less even look than arcs but
        # still allows for approximate circles at r_pct = 100.
        x0,y0 = x,y
        x1,y1 = x+w,y+h

        r = min(w, h) * min(r_pct/100.0, 0.5) # full range at 50%
        k = (r-1) * r_pct/200.0 # position of control points for circular curves

        # top left
        context.move_to(x0+r, y0)

        # top right
        context.line_to(x1-r,y0)
        context.curve_to(x1-k, y0, x1, y0+k, x1, y0+r)

        # bottom right
        context.line_to(x1, y1-r)
        context.curve_to(x1, y1-k, x1-k, y1, x1-r, y1)

        # bottom left
        context.line_to(x0+r, y1)
        context.curve_to(x0+k, y1, x0, y1-k, x0, y1-r)

        # top left
        context.line_to(x0, y0+r)
        context.curve_to(x0, y0+k, x0+k, y0, x0+r, y0)

        context.close_path ()

    def get_gradient_line(self, x0, y0, w, h, alpha):
        # Find gradient start and end points.
        # Line end points follow the largest extent of the rotated rectangle.
        # The gradient reaches across the entire key.
        a = w / 2.0
        b = h / 2.0
        coords = [(-a, -b), (a, -b), (a, b), (-a, b)]
        vx = [c[0]*cos(alpha)-c[1]*sin(alpha) for c in coords]
        dx = max(vx) - min(vx)
        r = dx / 2.0
        return (r * cos(alpha) + x0 + a,
                r * sin(alpha) + y0 + b,
               -r * cos(alpha) + x0 + a,
               -r * sin(alpha) + y0 + b)

    def brighten(self, amount, r, g, b, a=0.0):
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        l += amount
        if l > 1.0:
            l = 1.0
        if l < 0.0:
            l = 0.0
        return list(colorsys.hls_to_rgb(h, l, s)) + [a]

    def get_best_font_size(self, pane_context, context):
        """
        Get the maximum font possible that would not cause the label to
        overflow the boundaries of the key.
        """
        layout = pango.Layout(context)
        self.prepare_pango_layout(layout, self.get_label(), 
                                          BASE_FONTDESCRIPTION_SIZE)

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

class FixedFontMixin:
    """ Font size independent of text length """

    def __init__(self):
        self.initial_paint = True

    def get_best_font_size(self, pane_context, context):
        return FixedFontMixin.calc_font_size(pane_context, self.geometry)

    def paint_font(self, pane_context, context = None):

        if self.initial_paint:
            self.initial_paint = False

            # center label vertically
            layout = self.get_pango_layout(context, self.get_label(), 
                                                    self.font_size)
            self.label_offset = (self.label_offset[0],
                          WordKey.calc_label_offset(pane_context, layout, 
                                                    self.geometry)[1])

    @staticmethod
    def calc_font_size(pane_context, size):
        # font size is based on the height of the template key
        font_size = int(pane_context.scale_log_to_canvas_y(
                                 size[1] * pango.SCALE) * 0.4)
        return font_size

    @staticmethod
    def calc_text_size(pane_context, layout, size, text):
        layout.set_text(text)
        label_width, label_height = layout.get_size()
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

    def paint_font(self, pane_context, context):
        FixedFontMixin.paint_font(self, pane_context, context)

        layout = self.get_pango_layout(context, self.line,
                                                self.font_size)

        pc = pane_context
        l = pc.log_to_canvas_x(self.location[0] + self.label_offset[0])
        t = pc.log_to_canvas_y(self.location[1] + self.label_offset[1])
        r = pc.log_to_canvas_x(self.location[0] + self.geometry[0] \
                                         - self.label_offset[0])
        b = pc.log_to_canvas_y(self.location[1] + self.geometry[1] \
                                         - self.label_offset[1])

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

        layout.set_attributes(attrs)

        # get x position of every character
        widths = []
        char_x = []
        iter = layout.get_iter()
        while True:
            e = iter.get_char_extents()
            char_x.append(e[0]/pango.SCALE)
            widths.append(e[2]/pango.SCALE)
            if not iter.next_char():
                char_x.append((e[0]+e[2])/pango.SCALE)
                break

        # find first (left-most) character that fits into the available space
        start = 0
        while True:
            cursor_x = char_x[self.cursor - start]
            if cursor_x < r - l:
                break
            start += 1

        # draw text clipped to available rectangle
        context.set_source_rgba(*self.label_rgba)
        context.rectangle(l, t, r-l, b-t)
        context.save()
        context.clip()
        context.move_to(l-char_x[start], t)
        context.show_layout(layout)
        context.restore()

        # reset attributes; layout is reused by all keys due to memory leak
        layout.set_attributes(pango.AttrList())

