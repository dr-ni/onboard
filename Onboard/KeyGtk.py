# -*- coding: UTF-8 -*-

import cairo
from gi.repository import Gdk, Pango, PangoCairo
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
PangoUnscale = 1.0 / Pango.SCALE

class Key(KeyCommon):
    pango_layout = None

    def __init__(self):
        KeyCommon.__init__(self)

    def get_best_font_size(self, scale, context):
        """
        Get the maximum font possible that would not cause the label to
        overflow the boundaries of the key.
        """

        raise NotImplementedException()

    def get_pango_layout(self, context, font_size):
        if self.pango_layout is None: # work around memory leak (gnome #599730)
            # use PangoCairo.create_layout once it works with gi (pango >= 1.29.1)
            self.pango_layout = Pango.Layout(context=Gdk.pango_context_get())

        self.prepare_pango_layout(self.pango_layout, font_size)

        return self.pango_layout

    def prepare_pango_layout(self, layout, font_size):
        layout.set_text(self.labels[self.label_index], -1)
        font_description = Pango.FontDescription(config.key_label_font)
        font_description.set_size(font_size)
        layout.set_font_description(font_description)

    def paint_font(self, scale, location, context):
        layout = self.get_pango_layout(context, self.font_size)

        #now put it in the centre of the keycap
        w,h=layout.get_size()
        leftmargin=0.5*((self.geometry[0]* scale[0])-(w * PangoUnscale))
        topmargin=0.5*((self.geometry[1]* scale[1])-(h * PangoUnscale))

        context.move_to(location[0] * scale[0] + leftmargin,
                        location[1] * scale[1]+ topmargin)
        context.set_source_rgba(*self.label_rgba)
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

        context.set_source_rgba(self.get_fill_color())
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

    def paint_font(self, scale, context):
        location = self.location

        # Unsuccessful tries to coax cairo into using subpixel positioning
        #context.set_antialias(cairo.ANTIALIAS_SUBPIXEL)

        ## see http://lists.freedesktop.org/archives/cairo/2007-February/009688.html
        #pango_context = layout.get_context()
        #fo = cairo.FontOptions()
        #fo.set_antialias(cairo.ANTIALIAS_DEFAULT)
        #fo.set_hint_style(cairo.HINT_STYLE_NONE)
        #fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
        #pangocairo.context_set_font_options(pango_context, fo)

        layout = self.get_pango_layout(context, self.font_size)

        #now put it in the centre of the keycap
        w,h=layout.get_size()
        leftmargin=0.5*((self.geometry[0]* scale[0])-(w * PangoUnscale))
        topmargin=0.5*((self.geometry[1]* scale[1])-(h * PangoUnscale))

        stroke_gradient   = config.key_stroke_gradient / 100.0
        if config.key_style != "flat" and stroke_gradient:
            fill = self.get_fill_color()
            d = 0.5  # fake emboss distance

            alpha = self.get_gradient_angle()
            xo = d * cos(alpha)
            yo = d * sin(alpha)
            rgba = self.brighten(-stroke_gradient*.5, *fill) # dark
            context.set_source_rgba(*rgba)
            context.move_to((location[0]+xo) * scale[0] + leftmargin,
                            (location[1]+yo) * scale[1] + topmargin)
            PangoCairo.show_layout(context, layout)

            alpha = pi + self.get_gradient_angle()
            xo = d * cos(alpha)
            yo = d * sin(alpha)
            rgba = self.brighten(+stroke_gradient*.5, *fill) # bright
            context.set_source_rgba(*rgba)
            x = (location[0]+xo) * scale[0] + leftmargin
            y = (location[1]+yo) * scale[1] + topmargin

            context.move_to(x,y)
            PangoCairo.show_layout(context, layout)

            #context.move_to(x,y)
            #context.line_to(x+5,y+5)
            #context.set_source_rgba(1.0,0.0,0.0,1.0)
            #context.stroke()

        context.move_to(location[0] * scale[0] + leftmargin,
                        location[1] * scale[1] + topmargin)
        context.set_source_rgba(*self.label_rgba)
        PangoCairo.show_layout(context, layout)


    def get_gradient_angle(self):
        return -pi/2.0 - 2*pi * config.key_gradient_direction / 360.0

    def paint(self, scale, context = None):

        x0,y0 = self.location[0]*scale[0], self.location[1]*scale[1]
        x1,y1 = x0 + self.geometry[0]*scale[0], y0 +self.geometry[1]*scale[1]
        w, h  = self.geometry[0] * scale[0], self.geometry[1] * scale[1]
        line_width = (scale[0] + scale[1])/4.0
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

    def get_gradient_line_(self, x0, y0, w, h, alpha):
        # Find gradient start and end points.
        # Line endpoints follows an ellipse.
        # Rotated gradients cover only the middle part of long keys.
        a = w / 2.0           # radii of ellipse around center
        b = h / 2.0
        k = b * cos(alpha)
        l = a * sin(alpha)
        r = a*b/sqrt(k*k + l*l)  # point on ellipse in polar coords
        return (r * cos(alpha) + x0 + a,
                r * sin(alpha) + y0 + b,
               -r * cos(alpha) + x0 + a,
               -r * sin(alpha) + y0 + b)

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

    def get_best_font_size(self, scale, context):
        """
        Get the maximum font possible that would not cause the label to
        overflow the boundaries of the key.
        """
        layout = Pango.Layout(context)
        self.prepare_pango_layout(layout, BASE_FONTDESCRIPTION_SIZE)

        # In Pango units
        label_width, label_height = layout.get_size()

        size_for_maximum_width = (self.geometry[0] - config.LABEL_MARGIN[0]) \
                * Pango.SCALE \
                * scale[0] \
                * BASE_FONTDESCRIPTION_SIZE \
            / label_width

        size_for_maximum_height = (self.geometry[1] - config.LABEL_MARGIN[1]) \
                * Pango.SCALE \
                * scale[1] \
                * BASE_FONTDESCRIPTION_SIZE \
            / label_height

        if size_for_maximum_width < size_for_maximum_height:
            return int(size_for_maximum_width)
        else:
            return int(size_for_maximum_height)


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


