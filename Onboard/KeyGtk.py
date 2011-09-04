# -*- coding: UTF-8 -*-

import cairo
from gi.repository import Gdk, Pango, PangoCairo, GdkPixbuf
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

    def get_best_font_size(self, key_context, context):
        """
        Get the maximum font possible that would not cause the label to
        overflow the boundaries of the key.
        """

        raise NotImplementedException()

    @staticmethod
    def get_pango_layout(context, text, font_size):
        if Key.pango_layout is None: # work around memory leak (gnome #599730)
            # use PangoCairo.create_layout once it works with gi (pango >= 1.29.1)
            Key.pango_layout = Pango.Layout(context=Gdk.pango_context_get())
            #Key.pango_layout = PangoCairo.create_layout(context)
        layout = Key.pango_layout

        Key.prepare_pango_layout(layout, text, font_size)
        #context.update_layout(layout)
        return layout

    @staticmethod
    def prepare_pango_layout(layout, text, font_size):
        if text is None:
            text = ""
        layout.set_text(text, -1)
        font_description = Pango.FontDescription(config.theme.key_label_font)
        font_description.set_size(font_size)
        layout.set_font_description(font_description)


class RectKey(Key, RectKeyCommon):
    def __init__(self, id="", location=(0,0), geometry=(0,0)):
        RectKeyCommon.__init__(self, id, location, geometry)

    def draw_font(self, context = None):
        # Skip cairo errors when drawing labels with font size 0
        # This may happen for hidden keys and keys with bad size groups.
        if self.font_size == 0:
            return

        key_context = self.context

        layout = self.get_pango_layout(context, self.get_label(),
                                                self.font_size)
        # label alignment
        label_size = layout.get_size()
        label_area = self.get_label_rect()
        label_canvas = self.context.log_to_canvas_rect(label_area)
        xoffset, yoffset = self.align_label(
                 (label_size[0] * PangoUnscale, label_size[1] * PangoUnscale),
                 (label_canvas.w, label_canvas.h))

        stroke_gradient   = config.theme.key_stroke_gradient / 100.0
        if config.theme.key_style != "flat" and stroke_gradient:
            fill = self.get_fill_color()
            d = 0.5  # fake emboss distance

            # shadow
            alpha = self.get_gradient_angle()
            xo = d * cos(alpha)
            yo = d * sin(alpha)
            rgba = self.brighten(-stroke_gradient*.5, *fill) # darker
            context.set_source_rgba(*rgba)

            x,y = key_context.log_to_canvas((label_area.x+xo, label_area.y+yo))
            context.move_to(xoffset + x, yoffset + y)
            PangoCairo.show_layout(context, layout)

            # highlight
            alpha = pi + self.get_gradient_angle()
            xo = d * cos(alpha)
            yo = d * sin(alpha)
            rgba = self.brighten(+stroke_gradient*.5, *fill) # brighter
            context.set_source_rgba(*rgba)

            x,y = key_context.log_to_canvas((label_area.x+xo, label_area.y+yo))
            context.move_to(xoffset + x, yoffset + y)
            PangoCairo.show_layout(context, layout)

        context.set_source_rgba(*self.label_rgba)
        context.move_to(label_canvas.x + xoffset, label_canvas.y + yoffset)
        PangoCairo.show_layout(context, layout)

    def draw_image(self, context):
        """ Draws the keys optional image. """
        if not self.image_filename:
            return

        rect = self.context.log_to_canvas_rect(self.get_label_rect())
        pixbuf = self.get_image(rect.w, rect.h)
        if pixbuf:
            xoffset, yoffset = self.align_label(
                     (pixbuf.get_width(), pixbuf.get_height()),
                     (rect.w, rect.h))

            # Draw the image in the themes label color.
            # Only the alpha channel of the image is used.
            Gdk.cairo_set_source_pixbuf(context, pixbuf,
                                        xoffset+rect.x,
                                        yoffset+rect.y)
            pattern = context.get_source()
            context.rectangle(*rect)
            context.set_source_rgba(*self.label_rgba)
            context.mask(pattern)
            context.new_path()


    def draw(self, context):

        key_context = self.context
        rect = key_context.log_to_canvas_rect(self.get_rect())
        t    = key_context.scale_log_to_canvas((1.0, 1.0))
        line_width = (t[0] + t[1]) / 2.0
        fill = self.get_fill_color()

        if config.theme.key_style == "flat":
            # old style key from before theming was added
            self.build_rect_path(context, rect)
            context.set_source_rgba(*fill)
            context.fill_preserve()
            context.set_source_rgba(*self.stroke_rgba)
            context.set_line_width(line_width)
            context.stroke()

        elif config.theme.key_style == "gradient":
            self.draw_gradient_key(context, rect, fill, line_width)

        elif config.theme.key_style == "dish":
            self.draw_dish_key(context, rect, fill, line_width)


    def draw_dish_key(self, context, rect, fill, line_width):
        # simple gradients for fill and stroke
        fill_gradient   = config.theme.key_fill_gradient / 100.0
        stroke_gradient = config.theme.key_stroke_gradient / 100.0
        alpha = self.get_gradient_angle()
        # unfinished

    def draw_gradient_key(self, context, rect, fill, line_width):
        # simple gradients for fill and stroke
        fill_gradient   = config.theme.key_fill_gradient / 100.0
        stroke_gradient = config.theme.key_stroke_gradient / 100.0
        alpha = self.get_gradient_angle()

        self.build_rect_path(context, rect)
        gline = self.get_gradient_line(rect, alpha)

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

    def build_rect_path(self, context, rect):
        roundness = config.theme.roundrect_radius
        if roundness:
            self.roundrect(context, rect, roundness)
        else:
            context.rectangle(*rect)

    def roundrect(self, context, rect, r_pct = 100):
        # Uses B-Splines for less even look than arcs but
        # still allows for approximate circles at r_pct = 100.
        x0, y0 = rect.x, rect.y
        x1, y1 = rect.x + rect.w, rect.y + rect.h
        w, h   = rect.w, rect.h

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

    def get_gradient_line(self, rect, alpha):
        # Find gradient start and end points.
        # Line end points follow the largest extent of the rotated rectangle.
        # The gradient reaches across the entire key.
        x0, y0, w, h = rect.x, rect.y, rect.w, rect.h
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

    def get_gradient_angle(self):
        return -pi/2.0 - 2*pi * config.theme.key_gradient_direction / 360.0

    def brighten(self, amount, r, g, b, a=0.0):
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        l += amount
        if l > 1.0:
            l = 1.0
        if l < 0.0:
            l = 0.0
        return list(colorsys.hls_to_rgb(h, l, s)) + [a]

    def get_best_font_size(self, context):
        """
        Get the maximum font size that would not cause the label to
        overflow the boundaries of the key.
        """
        layout = Pango.Layout(context)
        self.prepare_pango_layout(layout, self.get_label(),
                                          BASE_FONTDESCRIPTION_SIZE)

        # In Pango units
        label_width, label_height = layout.get_size()
        if label_width == 0: label_width = 1

        size_for_maximum_width = self.context.scale_log_to_canvas_x(
                (self.geometry[0] - config.LABEL_MARGIN[0]*2) \
                * Pango.SCALE \
                * BASE_FONTDESCRIPTION_SIZE) \
            / label_width

        size_for_maximum_height = self.context.scale_log_to_canvas_y(
                (self.geometry[1] - config.LABEL_MARGIN[1]*2) \
                * Pango.SCALE \
                * BASE_FONTDESCRIPTION_SIZE) \
            / label_height

        if size_for_maximum_width < size_for_maximum_height:
            return int(size_for_maximum_width)
        else:
            return int(size_for_maximum_height)

    def get_image(self, width, height):
        """
        Get the cached image pixbuf object. Load it if necessary.
        Width and height in canvas coordinates.
        """
        if not self.image_filename:
            return

        pixbuf = self.image_pixbuf
        if not pixbuf or \
           pixbuf.get_width()  != width or \
           pixbuf.get_height() != height:

            self.image_pixbuf = None

            filename = config.get_image_filename(self.image_filename)
            if filename:
                self.image_pixbuf = GdkPixbuf.Pixbuf. \
                               new_from_file_at_size(filename, width, height)
                p = self.image_pixbuf
        return self.image_pixbuf


