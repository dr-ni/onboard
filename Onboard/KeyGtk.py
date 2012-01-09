# -*- coding: UTF-8 -*-

from __future__ import division, print_function, unicode_literals

import time
from math import floor, pi, sin, cos, sqrt

import cairo
from gi.repository import Gdk, Pango, PangoCairo, GdkPixbuf


from Onboard.KeyCommon import *
from Onboard.utils import brighten, roundrect_curve

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
    _pango_layout = None

    def __init__(self):
        KeyCommon.__init__(self)

    def get_best_font_size(self, context):
        """
        Get the maximum font possible that would not cause the label to
        overflow the boundaries of the key.
        """

        raise NotImplementedException()

    @staticmethod
    def reset_pango_layout():
        Key._pango_layout = None

    @staticmethod
    def get_pango_layout(context, text, font_size):
        if Key._pango_layout is None: # work around memory leak (gnome #599730)
            # use PangoCairo.create_layout once it works with gi (pango >= 1.29.1)
            Key._pango_layout = Pango.Layout(context=Gdk.pango_context_get())
            #Key._pango_layout = PangoCairo.create_layout(context)
        layout = Key._pango_layout

        Key.prepare_pango_layout(layout, text, font_size)
        #context.update_layout(layout)
        return layout

    @staticmethod
    def prepare_pango_layout(layout, text, font_size):
        if text is None:
            text = ""
        layout.set_text(text, -1)
        font_description = Pango.FontDescription(config.theme_settings.key_label_font)
        font_description.set_size(max(1,font_size))
        layout.set_font_description(font_description)


class DwellProgress(object):

    # dwell time in seconds
    dwell_delay = 4

    # time of dwell start
    dwell_start_time = None

    def is_dwelling(self):
        return not self.dwell_start_time is None

    def is_done(self):
        return time.time() > self.dwell_start_time + self.dwell_delay

    def start_dwelling(self):
        self.dwell_start_time = time.time()

    def stop_dwelling(self):
        self.dwell_start_time = None

    def draw(self, context):
        if self.is_dwelling():
            rect = self.get_label_rect().inflate(0.5)
            rect = self.context.log_to_canvas_rect(rect)
            xc, yc = rect.get_center()

            radius = min(rect.w, rect.h) / 2.0

            alpha0 = -pi / 2.0
            k = (time.time() - self.dwell_start_time) / self.dwell_delay
            k = min(k, 1.0)
            alpha = k * pi * 2.0

            context.move_to(xc, yc)
            context.arc(xc, yc, radius, alpha0, alpha0 + alpha)
            context.close_path()

            rgba = self.get_dwell_progress_color()
            context.set_source_rgba(*rgba)
            context.fill_preserve()

            context.set_source_rgba(0,0,0,1)
            context.set_line_width(0)
            context.stroke()


class RectKey(Key, RectKeyCommon, DwellProgress):

    _image_pixbuf = None
    _requested_image_size = None

    def __init__(self, id="", border_rect = None):
        Key.__init__(self)
        RectKeyCommon.__init__(self, id, border_rect)

    def is_key(self):
        """ Returns true if self is a key. """
        return True

    def draw_label(self, context = None):
        # Skip cairo errors when drawing labels with font size 0
        # This may happen for hidden keys and keys with bad size groups.
        if self.font_size == 0:
            return

        label = self.get_label()
        if not label:
            return

        layout = self.get_pango_layout(context, label, self.font_size)
        log_rect = self.get_label_rect()
        src_size = layout.get_size()
        src_size = (src_size[0] * PangoUnscale, src_size[1] * PangoUnscale)

        for x, y, rgba, last in self._label_iterations(src_size, log_rect):
            # draw dwell progress after fake emboss, before final label
            if last:
                DwellProgress.draw(self, context)
            context.move_to(x, y)
            context.set_source_rgba(*rgba)
            PangoCairo.show_layout(context, layout)

    def draw_image(self, context):
        """ Draws the keys optional image. """
        if not self.image_filename:
            return

        rect = self.context.log_to_canvas_rect(self.get_label_rect())
        if rect.w < 1 or rect.h < 1:
            return

        pixbuf = self.get_image(rect.w, rect.h)
        if not pixbuf:
            return

        log_rect = self.get_label_rect()
        src_size = (pixbuf.get_width(), pixbuf.get_height())

        for x, y, rgba, last in self._label_iterations(src_size, log_rect):
            # draw dwell progress after fake emboss, before final image
            if last:
                DwellProgress.draw(self, context)

            # Draw the image in the themes label color.
            # Only the alpha channel of the image is used.
            Gdk.cairo_set_source_pixbuf(context, pixbuf, x, y)
            pattern = context.get_source()
            context.rectangle(*rect)
            context.set_source_rgba(*rgba)
            context.mask(pattern)
            context.new_path()

    def _label_iterations(self, src_size, log_rect):
        canvas_rect = self.context.log_to_canvas_rect(log_rect)
        xoffset, yoffset = self.align_label(
                 (src_size[0], src_size[1]),
                 (canvas_rect.w, canvas_rect.h))
        x = int(canvas_rect.x + xoffset)
        y = int(canvas_rect.y + yoffset)

        stroke_gradient   = config.theme_settings.key_stroke_gradient / 100.0
        if config.theme_settings.key_style != "flat" and stroke_gradient:
            root = self.get_layout_root()
            fill = self.get_fill_color()
            d = 0.4  # fake emboss distance
            #d = max(src_size[1] * 0.02, 0.0)
            max_offset = 2

            # shadow
            alpha = self.get_gradient_angle()
            xo = root.context.scale_log_to_canvas_x(d * cos(alpha))
            yo = root.context.scale_log_to_canvas_y(d * sin(alpha))
            xo = min(int(round(xo)), max_offset)
            yo = min(int(round(yo)), max_offset)
            rgba = brighten(-stroke_gradient*.25, *fill) # darker
            yield x + xo, y + yo, rgba, False

            # highlight
            alpha = pi + self.get_gradient_angle()
            xo = root.context.scale_log_to_canvas_x(d * cos(alpha))
            yo = root.context.scale_log_to_canvas_y(d * sin(alpha))
            xo = min(int(round(xo)), max_offset)
            yo = min(int(round(yo)), max_offset)
            rgba = brighten(+stroke_gradient*.25, *fill) # brighter
            yield x + xo, y + yo, rgba, False

        rgba = self.get_label_color()
        yield x, y, rgba, True


    def draw(self, context):

        rect = self.get_canvas_rect()
        root = self.get_layout_root()
        t    = root.context.scale_log_to_canvas((1.0, 1.0))
        line_width = (t[0] + t[1]) / 2.0

        fill = self.get_fill_color()

        key_style = config.theme_settings.key_style
        if key_style == "flat":
            # old style key from before theming was added
            self.build_rect_path(context, rect)
            context.set_source_rgba(*fill)
            context.fill_preserve()
            context.set_source_rgba(*self.get_stroke_color())
            context.set_line_width(line_width)
            context.stroke()

        elif key_style == "gradient":
            self.draw_gradient_key(context, rect, fill, line_width)

        elif key_style == "dish":
            self.draw_dish_key(context, rect, fill, line_width)



    def draw_gradient_key(self, context, rect, fill, line_width):
        # simple gradients for fill and stroke
        fill_gradient   = config.theme_settings.key_fill_gradient / 100.0
        stroke_gradient = config.theme_settings.key_stroke_gradient / 100.0
        alpha = self.get_gradient_angle()

        self.build_rect_path(context, rect)
        gline = self.get_gradient_line(rect, alpha)

        # fill
        if fill_gradient:
            pat = cairo.LinearGradient (*gline)
            rgba = brighten(+fill_gradient*.5, *fill)
            pat.add_color_stop_rgba(0, *rgba)
            rgba = brighten(-fill_gradient*.5, *fill)
            pat.add_color_stop_rgba(1, *rgba)
            context.set_source (pat)
        else: # take gradient from color scheme (not implemented)
            context.set_source_rgba(*fill)

        context.fill_preserve()

        # stroke
        if stroke_gradient:
            stroke = fill
            pat = cairo.LinearGradient (*gline)
            rgba = brighten(+stroke_gradient*.5, *stroke)
            pat.add_color_stop_rgba(0, *rgba)
            rgba = brighten(-stroke_gradient*.5, *stroke)
            pat.add_color_stop_rgba(1, *rgba)
            context.set_source (pat)
        else:
            context.set_source_rgba(*self.get_stroke_color())

        context.set_line_width(line_width)
        context.stroke()


    def draw_dish_key(self, context, rect, fill, line_width):
        # parameters for the base rectangle
        w, h = rect.get_size()
        xc, yc = rect.get_center()
        radius_pct = config.theme_settings.roundrect_radius
        radius_pct = max(radius_pct, 2) # too much +-1 fudging for square corners
        r, k = self.get_curved_rect_params(rect, radius_pct)

        base_rgba = brighten(-0.200, *fill)
        stroke_gradient = config.theme_settings.key_stroke_gradient / 100.0
        light_dir = config.theme_settings.key_gradient_direction / 180.0 * pi

        # lambert lighting
        edge_colors = []
        for edge in range(4):
            normal_dir = edge * pi / 2.0   # 0 = light from top
            I = cos(normal_dir - light_dir) * stroke_gradient * 0.8
            edge_colors.append(brighten(I, *base_rgba))

        # parameters for the top rectangle, key face
        border = self.context.scale_log_to_canvas(config.DISH_KEY_BORDER)
        offset_top = self.context.scale_log_to_canvas_y(config.DISH_KEY_Y_OFFSET)
        rect_top = rect.deflate(*border).offset(0, -offset_top)
        top_radius_scale = rect_top.h / float(rect.h)
        r_top, k_top = self.get_curved_rect_params(rect_top,
                                                radius_pct * top_radius_scale)

        context.save()
        context.translate(xc , yc)

        # edge sections, edge 0 = top
        for edge in range(4):
            if edge % 2:
                p = (h/2.0, w/2.0)
                p_top = [rect_top.h/2.0, rect_top.w/2.0]
            else:
                p = (w/2.0, h/2.0)
                p_top = [rect_top.w/2.0, rect_top.h/2.0]

            m = cairo.Matrix()
            m.rotate(edge * pi / 2.0)
            p0     = m.transform_point(-p[0] + r - 1, -p[1]) # -1 to fill gaps
            p1     = m.transform_point( p[0] - r + 1, -p[1])
            p0_top = m.transform_point( p_top[0] - r_top + 1, -p_top[1] + 1)
            p1_top = m.transform_point(-p_top[0] + r_top - 1, -p_top[1] + 1)
            p0_top = (p0_top[0], p0_top[1] - offset_top)
            p1_top = (p1_top[0], p1_top[1] - offset_top)

            context.set_source_rgba(*edge_colors[edge])
            context.move_to(p0[0], p0[1])
            context.line_to(p1[0], p1[1])
            context.line_to(*p0_top)
            context.line_to(*p1_top)
            context.close_path()
            context.fill()


        # corner sections
        for edge in range(4):
            if edge % 2:
                p = (h/2.0, w/2.0)
                p_top = [rect_top.h/2.0, rect_top.w/2.0]
            else:
                p = (w/2.0, h/2.0)
                p_top = [rect_top.w/2.0, rect_top.h/2.0]

            m = cairo.Matrix()
            m.rotate(edge * pi / 2.0)
            p1     = m.transform_point( p[0] - r, -p[1])
            p2     = m.transform_point( p[0],     -p[1] + r)
            pk0    = m.transform_point( p[0] - k, -p[1])
            pk1    = m.transform_point( p[0],     -p[1] + k)
            p0_top = m.transform_point( p_top[0] - r_top, -p_top[1])
            p2_top = m.transform_point( p_top[0],         -p_top[1] + r_top)
            p0_top = (p0_top[0], p0_top[1] - offset_top)
            p2_top = (p2_top[0], p2_top[1] - offset_top)

            # Fake Gouraud shading: draw a gradient between mid points
            # of the lines connecting the base to the top rectangle.
            gline = ((p1[0] + p0_top[0]) / 2.0, (p1[1] + p0_top[1]) / 2.0,
                     (p2[0] + p2_top[0]) / 2.0, (p2[1] + p2_top[1]) / 2.0)
            pat = cairo.LinearGradient (*gline)
            pat.add_color_stop_rgba(0.0, *edge_colors[edge])
            pat.add_color_stop_rgba(1.0, *edge_colors[(edge + 1) % 4])
            context.set_source (pat)

            context.move_to(*p1)
            context.curve_to(pk0[0], pk0[1], pk1[0], pk1[1], p2[0], p2[1])
            context.line_to(*p2_top)
            context.line_to(*p0_top)
            context.close_path()
            context.fill()

        context.restore()

        # the key face (smaller top rectangle)
        # Simulate the concave key dish with a gradient that has
        # a sligthly brighter middle section.
        if self.id == "SPCE":
            angle = pi / 2.0  # space has a convex top
        else:
            angle = 0.0       # all others are concave
        fill_gradient   = config.theme_settings.key_fill_gradient / 100.0
        dark_rgba = brighten(-fill_gradient*.5, *fill)
        bright_rgba = brighten(+fill_gradient*.5, *fill)
        gline = self.get_gradient_line(rect, angle)

        pat = cairo.LinearGradient (*gline)
        pat.add_color_stop_rgba(0.0, *dark_rgba)
        pat.add_color_stop_rgba(0.5, *bright_rgba)
        pat.add_color_stop_rgba(1.0, *dark_rgba)
        context.set_source (pat)

        self.build_rect_path(context, rect_top, top_radius_scale)
        context.fill()

    def get_curved_rect_params(self, rect, r_pct):
        w, h = rect.get_size()
        r = min(w, h) * min(r_pct / 100.0, 0.5) # full range at 50%
        k = (r-1) * r_pct/200.0 # position of control points for circular curves
        return r, k

    def build_rect_path(self, context, rect, radius_scale = 1.0):
        roundness = config.theme_settings.roundrect_radius * radius_scale
        if roundness:
            roundrect_curve(context, rect, roundness)
        else:
            context.rectangle(*rect)

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
        return -pi/2.0 + 2*pi * config.theme_settings.key_gradient_direction / 360.0

    def get_best_font_size(self, context):
        """
        Get the maximum font size that would not cause the label to
        overflow the boundaries of the key.
        """
        layout = Pango.Layout(context)
        self.prepare_pango_layout(layout, self.get_label(),
                                          BASE_FONTDESCRIPTION_SIZE)

        rect = self.get_label_rect()

        # In Pango units
        label_width, label_height = layout.get_size()
        if label_width == 0: label_width = 1

        size_for_maximum_width = self.context.scale_log_to_canvas_x(
                (rect.w - config.LABEL_MARGIN[0]*2) \
                * Pango.SCALE \
                * BASE_FONTDESCRIPTION_SIZE) \
            / label_width

        size_for_maximum_height = self.context.scale_log_to_canvas_y(
                (rect.h - config.LABEL_MARGIN[1]*2) \
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
            return None

        if not self._image_pixbuf or \
           int(self._requested_image_size[0]) != int(width) or \
           int(self._requested_image_size[1]) != int(height):

            self._image_pixbuf = None

            filename = config.get_image_filename(self.image_filename)
            if filename:
                _logger.debug("loading image '{}'".format(filename))
                self._image_pixbuf = GdkPixbuf.Pixbuf. \
                               new_from_file_at_size(filename, width, height)
                if self._image_pixbuf:
                    self._requested_image_size = (width, height)

        return self._image_pixbuf


