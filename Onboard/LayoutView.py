# -*- coding: utf-8 -*-

# Copyright © 2012-2017 marmuta <marmvta@gmail.com>
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

""" Keyboard layout view """

from __future__ import division, print_function, unicode_literals

import time
from math import pi

import cairo
from Onboard.Version import require_gi_versions
require_gi_versions()
from gi.repository         import Gtk, Gdk, GdkPixbuf

from Onboard.utils         import Rect, \
                                  roundrect_arc, roundrect_curve, \
                                  gradient_line, brighten, \
                                  unicode_str
from Onboard.WindowUtils   import get_monitor_dimensions
from Onboard.KeyGtk        import Key
from Onboard.KeyCommon     import LOD
from Onboard.definitions   import UIMask


### Logging ###
import logging
_logger = logging.getLogger("LayoutView")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class LayoutView:
    """
    Viewer for a tree of layout items.
    """

    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.supports_alpha = False

        self._lod = LOD.FULL
        self._shadow_quality_valid = False
        self._last_canvas_shadow_rect = Rect()

        self._starting_up = True
        self._keys_pre_rendered = False

        self.keyboard.register_view(self)

    def cleanup(self):
        self.keyboard.deregister_view(self)

        # free xserver memory
        self.invalidate_keys()
        self.invalidate_shadows()

    def handle_realize_event(self):
        self.update_touch_input_mode()
        self.update_input_event_source()

    def on_layout_loaded(self):
        """ Layout has been loaded. """
        self.invalidate_shadow_quality()

    def get_layout(self):
        return self.keyboard.layout

    def get_color_scheme(self):
        return self.keyboard.color_scheme

    def invalidate_for_resize(self, lod=LOD.FULL):
        layout = self.get_layout()
        if layout:
            self.invalidate_keys()
            if self._lod == LOD.FULL:
                self.invalidate_shadows()
            layout.invalidate_font_sizes()
            # self.invalidate_label_extents()
            self.keyboard.invalidate_for_resize()

    def invalidate_keys(self):
        """
        Clear cached key surfaces, e.g. after resizing,
        change of theme settings.
        """
        layout = self.get_layout()
        if layout:
            for item in layout.iter_keys():
                item.invalidate_key()

    def invalidate_images(self):
        """
        Clear cached images, e.g. after changing window_scaling_factor.
        """
        layout = self.get_layout()
        if layout:
            for item in layout.iter_keys():
                item.invalidate_image()

    def invalidate_shadows(self):
        """
        Clear cached shadow surfaces, e.g. after resizing,
        change of theme settings.
        """
        layout = self.get_layout()
        if layout:
            for item in layout.iter_keys():
                item.invalidate_shadow()

    def invalidate_shadow_quality(self):
        self._shadow_quality_valid = False

    def invalidate_label_extents(self):
        """
        Clear cached resolution independent label extents, e.g.
        after changes to the systems font dpi setting (gtk-xft-dpi).
        """
        layout = self.get_layout()
        if layout:
            for item in layout.iter_keys():
                item.invalidate_label_extents()

    def reset_lod(self):
        """ Reset to full level of detail """
        if self._lod != LOD.FULL:
            self._lod = LOD.FULL
            self.invalidate_for_resize()
            self.keyboard.invalidate_context_ui()
            self.keyboard.invalidate_canvas()
            self.keyboard.commit_ui_updates()

    def is_visible(self):
        return None

    def set_visible(self, visible):
        pass

    def toggle_visible(self):
        pass

    def raise_to_top(self):
        pass

    def redraw(self, items=None, invalidate=True):
        """
        Queue redrawing for individual keys or the whole keyboard.
        """
        if items is None:
            self.queue_draw()

        elif len(items) == 0:
            pass

        else:
            area = None
            for item in items:
                rect = item.get_canvas_border_rect()
                area = area.union(rect) if area else rect

                # assume keys need to be refreshed when actively redrawn
                # e.g. for pressed state changes, dwell progress updates...
                if invalidate and \
                   item.is_key():
                    item.invalidate_key()

            # account for stroke width, anti-aliasing
            if self.get_layout():
                extra_size = items[0].get_extra_render_size()
                area = area.inflate(*extra_size)

            self.queue_draw_area(*area)

    def redraw_labels(self, invalidate=True):
        self.redraw(self.update_labels(), invalidate)

    def update_transparency(self):
        pass

    def update_input_event_source(self):
        self.register_input_events(True, config.is_event_source_gtk())

    def update_touch_input_mode(self):
        self.set_touch_input_mode(config.keyboard.touch_input)

    def can_delay_sequence_begin(self, sequence):
        """
        Veto gesture delay for move buttons. Have the keyboard start
        moving right away and not lag behind the pointer.
        """
        layout = self.get_layout()
        if layout:
            for item in layout.find_ids(["move"]):
                if item.is_path_visible() and \
                   item.is_point_within(sequence.point):
                    return False
        return True

    def show_touch_handles(self, show, auto_hide):
        pass

    def apply_ui_updates(self, mask):
        if mask & UIMask.SIZE:
            self.invalidate_for_resize()

    def update_layout(self):
        pass

    def process_updates(self):
        """ Draw now, synchronously. """
        window = self.get_window()
        if window:
            window.process_updates(True)

    def render(self, context):
        """ Pre-render key surfaces for instant initial drawing. """

        layout = self.get_layout()
        if not layout:
            return

        # lazily update font sizes and labels
        if not layout.get_font_sizes_valid():
            self.update_labels()

        self._auto_select_shadow_quality(context)

        # run through all visible layout items
        for item in layout.iter_visible_items():
            if item.is_key():
                item.draw_shadow_cached(context)
                item.draw_cached(context)

        self._keys_pre_rendered = True

    def _can_draw_cached(self, lod):
        """
        Draw cached key surfaces?

        On first startup draw cached only if keys were pre-rendered, i.e. the
        time to render keys was hidden before the window was shown.

        We can't easily pre-render keys in xembed mode because the window size
        is unknown in advance. Draw there once uncached instead (faster).
        """
        return (lod == LOD.FULL) and \
               (not self._starting_up or self._keys_pre_rendered)

    def draw(self, widget, cr):
        if not Gtk.cairo_should_draw_window(cr, widget.get_window()):
            return

        layout = self.get_layout()
        if not layout:
            return

        lod = self._lod
        draw_cached = self._can_draw_cached(lod)

        # lazily update font sizes and labels
        if not layout.get_font_sizes_valid():
            self.update_labels(lod)

        # draw background
        decorated = self._draw_background(cr, lod)

        # draw layer 0 and None-layer background
        layer_ids = layout.get_layer_ids()
        if config.window.transparent_background:
            alpha = 0.0
        elif decorated:
            alpha = self.get_background_rgba()[3]
        else:
            alpha = 1.0
        self._draw_layer_key_background(cr, alpha,
                                        None, None, lod)
        if layer_ids:
            self._draw_layer_key_background(cr, alpha,
                                            None, layer_ids[0], lod)

        # Yet another context; this one helps pass all the
        # accumulated values for easier in-tree drawing.
        class DrawingContext:
            def draw_layer_background(self, item):
                self.view._draw_layer_background(self.cr, item,
                                                 layer_ids, decorated)
        context = DrawingContext()
        context.cr = cr
        context.draw_rect = self.get_damage_rect(cr)
        context.lod = lod
        context.draw_cached = draw_cached
        context.view = self

        # draw all visible layout items
        layout.draw_tree(context)

        self._starting_up = False

        return decorated

    def _draw_background(self, context, lod):
        """ Draw keyboard background """
        transparent_bg = False
        plain_bg = False

        if config.is_keep_xembed_frame_aspect_ratio_enabled():
            if self.supports_alpha:
                self._clear_xembed_background(context)
                transparent_bg = True
            else:
                plain_bg = True

        elif config.xid_mode:
            # xembed mode
            # Disable transparency in lightdm and g-s-s for now.
            # There are too many issues and there is no real
            # visual improvement.
            plain_bg = True

        elif config.has_window_decoration():
            # decorated window
            if self.supports_alpha and \
               config.window.transparent_background:
                self._clear_background(context)
            else:
                plain_bg = True

        else:
            # undecorated window
            if self.supports_alpha:
                self._clear_background(context)
                if not config.window.transparent_background:
                    transparent_bg = True
            else:
                plain_bg = True

        if plain_bg:
            self._draw_plain_background(context)
        if transparent_bg:
            self._draw_transparent_background(context, lod)

        return transparent_bg

    def _clear_background(self, context):
        """
        Clear the whole gtk background.
        Makes the whole strut transparent in xembed mode.
        """
        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.paint()
        context.restore()

    def _clear_xembed_background(self, context):
        """ fill with plain layer 0 color; no alpha support required """
        rect = Rect(0, 0, self.get_allocated_width(),
                          self.get_allocated_height())

        # draw background image
        if config.get_xembed_background_image_enabled():
            pixbuf = self._get_xembed_background_image()
            if pixbuf:
                src_size = (pixbuf.get_width(), pixbuf.get_height())
                x, y = 0, rect.bottom() - src_size[1]
                Gdk.cairo_set_source_pixbuf(context, pixbuf, x, y)
                context.paint()

        # draw solid colored bar on top (with transparency, usually)
        rgba = config.get_xembed_background_rgba()
        if rgba is None:
            rgba = self.get_background_rgba()
            rgba[3] = 0.5
        context.set_source_rgba(*rgba)
        context.rectangle(*rect)
        context.fill()

    def _get_xembed_background_image(self):
        """ load the desktop background image in Unity """
        try:
            pixbuf = self._xid_background_image
        except AttributeError:
            size, size_mm = get_monitor_dimensions(self)
            filename = config.get_desktop_background_filename()
            if not filename or \
               size[0] <= 0 or size[1] <= 0:
                pixbuf = None
            else:
                try:
                    # load image
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)

                    # Scale image to mimic the behavior of gnome-screen-saver.
                    # Take the largest, aspect correct, centered rectangle
                    # that fits on the monitor.
                    rm = Rect(0, 0, size[0], size[1])
                    rp = Rect(0, 0, pixbuf.get_width(), pixbuf.get_height())
                    ra = rm.inscribe_with_aspect(rp)
                    pixbuf = pixbuf.new_subpixbuf(*ra)
                    pixbuf = pixbuf.scale_simple(size[0], size[1],
                                                GdkPixbuf.InterpType.BILINEAR)
                except Exception as ex: # private exception gi._glib.GError when
                                        # librsvg2-common wasn't installed
                    _logger.error("_get_xembed_background_image(): " + \
                                unicode_str(ex))
                    pixbuf = None

            self._xid_background_image = pixbuf

        return pixbuf

    def _draw_transparent_background(self, context, lod):
        """ fill with the transparent background color """
        corner_radius = config.CORNER_RADIUS
        rect = self.get_keyboard_frame_rect()
        fill = self.get_background_rgba()

        if self.can_draw_sidebars():
            self._draw_side_bars(context)

        fill_gradient = config.theme_settings.background_gradient
        if lod == LOD.MINIMAL or \
           fill_gradient == 0:
            context.set_source_rgba(*fill)
        else:
            fill_gradient /= 100.0
            direction = config.theme_settings.key_gradient_direction
            alpha = -pi/2.0 + pi * direction / 180.0
            gline = gradient_line(rect, alpha)

            pat = cairo.LinearGradient (*gline)
            rgba = brighten(+fill_gradient*.5, *fill)
            pat.add_color_stop_rgba(0, *rgba)
            rgba = brighten(-fill_gradient*.5, *fill)
            pat.add_color_stop_rgba(1, *rgba)
            context.set_source (pat)

        if config.xid_mode:
            frame = False
        else:
            frame = self.can_draw_frame()

        if frame:
            roundrect_arc(context, rect, corner_radius)
        else:
            context.rectangle(*rect)

        context.fill()

        if frame:
            self.draw_window_frame(context, lod)
            self.draw_keyboard_frame(context, lod)

    def _draw_side_bars(self, context):
        """
        Transparent bars left and right of the aspect corrected
        keyboard frame.
        """
        rgba = self.get_background_rgba()
        rgba[3] = 0.5
        rwin = Rect(0, 0,
                    self.get_allocated_width(),
                    self.get_allocated_height())
        rframe = self.get_keyboard_frame_rect()

        if rwin.w > rframe.w:
            r = rframe.copy()
            context.set_source_rgba(*rgba)
            context.set_line_width(0)

            r.x = rwin.left()
            r.w = rframe.left() - rwin.left()
            context.rectangle(*r)
            context.fill()

            r.x = rframe.right()
            r.w = rwin.right() - rframe.right()
            context.rectangle(*r)
            context.fill()

    def can_draw_frame(self):
        """ overloaded in KeyboardWidget """
        return True

    def can_draw_sidebars(self):
        """ overloaded in KeyboardWidget """
        return False

    def draw_window_frame(self, context, lod):
        pass

    def draw_keyboard_frame(self, context, lod):
        """ draw frame around the (potentially aspect corrected) keyboard """
        corner_radius = config.CORNER_RADIUS
        rect = self.get_keyboard_frame_rect()
        fill = self.get_background_rgba()

        # inner decoration line
        line_rect = rect.deflate(1)
        roundrect_arc(context, line_rect, corner_radius)
        context.stroke()

    def _draw_plain_background(self, context, layer_index = 0):
        """ fill with plain layer 0 color; no alpha support required """
        rgba = self._get_layer_fill_rgba(layer_index)
        context.set_source_rgba(*rgba)
        context.paint()

    def _draw_layer_background(self, context, item, layer_ids, decorated):
        # layer background
        layer_index = layer_ids.index(item.layer_id)
        parent = item.parent
        if parent and \
           layer_index != 0:
            rect = parent.get_canvas_rect()
            context.rectangle(*rect.inflate(1))

            color_scheme = self.get_color_scheme()
            if color_scheme:
                rgba = color_scheme.get_layer_fill_rgba(layer_index)
            else:
                rgba = [0.5, 0.5, 0.5, 0.9]
            context.set_source_rgba(*rgba)
            context.fill()

            # per-layer key background
            self._draw_layer_key_background(context, 1.0, item, item.layer_id)

    def _draw_layer_key_background(self, context, alpha = 1.0, item = None,
                                   layer_id = None, lod = LOD.FULL):
        self._draw_dish_key_background(context, alpha, item, layer_id)
        self._draw_shadows(context, layer_id, lod)

    def _draw_dish_key_background(self, context, alpha = 1.0, item = None,
                                  layer_id = None):
        """
        Black background following the contours of key clusters
        to simulate the opening in the keyboard plane.
        """
        if config.theme_settings.key_style == "dish":
            layout = self.get_layout()
            context.push_group()

            context.set_source_rgba(0, 0, 0, 1)
            enlargement = layout.context.scale_log_to_canvas((0.8, 0.8))
            corner_radius = layout.context.scale_log_to_canvas_x(2.4)

            if item is None:
                item = layout

            for key in item.iter_layer_keys(layer_id):
                rect = key.get_canvas_fullsize_rect()
                rect = rect.inflate(*enlargement)
                roundrect_curve(context, rect, corner_radius)
                context.fill()

            context.pop_group_to_source()
            context.paint_with_alpha(alpha);

    def _draw_shadows(self, context, layer_id, lod):
        """
        Draw drop shadows for all keys.
        """
        # Shadows are drawn at odd positions when resizing while
        # docked and extended with side bars visible.
        # -> Turn them off while resizing. Improves rendering speed a bit too.
        if lod < LOD.FULL:
            return
        if not config.theme_settings.key_shadow_strength:
            return

        self._auto_select_shadow_quality(context)

        context.save()
        self.set_shadow_scale(context, lod)

        draw_rect = self.get_damage_rect(context)
        layout = self.get_layout()
        for item in layout.iter_layer_keys(layer_id):
            if draw_rect.intersects(item.get_canvas_border_rect()):
                item.draw_shadow_cached(context)

        context.restore()

    def _auto_select_shadow_quality(self, context):
        """ auto-select shadow quality """
        if not self._shadow_quality_valid:
            quality = self._probe_shadow_performance(context)
            Key.set_shadow_quality(quality)
            self._shadow_quality_valid = True

    def _probe_shadow_performance(self, context):
        """
        Determine shadow quality based on the estimated render time of
        the first layer's shadows.
        """
        probe_begin = time.time()
        quality = None

        layout = self.get_layout()
        max_total_time = 0.03  # upper limit refreshing all key's shadows [s]
        max_probe_keys = 10
        keys = None
        for layer_id in layout.get_layer_ids():
            layer_keys = list(layout.iter_layer_keys(layer_id))
            num_first_layer_keys = len(layer_keys)
            keys = layer_keys[:max_probe_keys]
            break

        if keys:
            for quality, (steps, alpha) in enumerate(Key._shadow_presets):
                begin = time.time()
                for key in keys:
                    key.create_shadow_surface(context, steps, 0.1)
                elapsed = time.time() - begin
                estimate = elapsed / len(keys) * num_first_layer_keys
                _logger.debug("Probing shadow performance: "
                              "estimated full refresh time {:6.1f}ms "
                              "at quality {}, {} steps." \
                              .format(estimate * 1000,
                                      quality, steps))
                if estimate > max_total_time:
                    break

            _logger.info("Probing shadow performance took {:.1f}ms. "
                         "Selecting quality {}." \
                         .format((time.time() - probe_begin) * 1000,
                                 quality))
        return quality

    def set_shadow_scale(self, context, lod):
        """
        Shadows aren't normally refreshed while resizing.
        -> scale the cached ones to fit the new canvas size.
        Occasionally refresh them anyway if scaling becomes noticeable.
        """
        r  = self.get_keyboard_frame_rect()
        if lod < LOD.FULL:
            rl = self._last_canvas_shadow_rect
            scale_x = r.w / rl.w
            scale_y = r.h / rl.h

            # scale in a reasonable range? -> draw stretched shadows
            smin = 0.8
            smax = 1.2
            if smax > scale_x > smin and \
               smax > scale_y > smin:
                context.scale(scale_x, scale_y)
            else:
                # else scale is too far out -> refresh shadows
                self.invalidate_shadows()
                self._last_canvas_shadow_rect = r
        else:
            self._last_canvas_shadow_rect = r

    def _get_layer_fill_rgba(self, layer_index):
        color_scheme = self.get_color_scheme()
        if color_scheme:
            return color_scheme.get_layer_fill_rgba(layer_index)
        else:
            return [0.5, 0.5, 0.5, 1.0]

    def get_background_rgba(self):
        """ layer 0 color * background_transparency """
        layer0_rgba = self._get_layer_fill_rgba(0)
        background_alpha = config.window.get_background_opacity()
        background_alpha *= layer0_rgba[3]
        return layer0_rgba[:3] + [background_alpha]

    def get_popup_window_rgba(self, element = "border"):
        color_scheme = self.get_color_scheme()
        if color_scheme:
            rgba = color_scheme.get_window_rgba("key-popup", element)
        else:
            rgba = [0.8, 0.8, 0.8, 1.0]
        background_alpha = config.window.get_background_opacity()
        background_alpha *= rgba[3]
        return rgba[:3] + [background_alpha]

    def get_damage_rect(self, context):
        clip_rect = Rect.from_extents(*context.clip_extents())

        # Draw a little more than just the clip_rect.
        # Prevents glitches around pressed keys in at least classic theme.
        layout = self.get_layout()
        if layout:
            extra_size = layout.context.scale_log_to_canvas((2.0, 2.0))
        else:
            extra_size = 0, 0
        return clip_rect.inflate(*extra_size)

    def get_keyboard_frame_rect(self):
        """
        Rectangle of the potentially aspect-corrected
        frame around the layout.
        """
        layout = self.get_layout()
        if layout:
            rect = layout.get_canvas_border_rect()
            rect = rect.inflate(self.get_frame_width())
        else:
            rect = Rect(0, 0, self.get_allocated_width(),
                              self.get_allocated_height())
        return rect.int()

    def is_docking_expanded(self):
        return self.window.docking_enabled and self.window.docking_expanded


    def update_labels(self, lod = LOD.FULL):
        """
        Iterate through all key groups and set each key's
        label font size to the maximum possible for that group.
        """
        changed_keys = set()
        layout = self.get_layout()

        mod_mask = self.keyboard.get_mod_mask()

        if layout:
            if lod == LOD.FULL:  # no label changes necessary while dragging

                # update label text
                for key in layout.iter_keys():
                    old_label = key.get_label()
                    key.configure_label(mod_mask)
                    if key.get_label() != old_label:
                        changed_keys.add(key)

            # update font sizes
            for keys in layout.get_key_groups().values():
                max_size = 0
                for key in keys:
                    best_size = key.get_best_font_size(mod_mask)
                    if best_size:
                        if key.ignore_group:
                            if key.font_size != best_size:
                                key.font_size = best_size
                                changed_keys.add(key)
                        else:
                            if not max_size or best_size < max_size:
                                max_size = best_size

                for key in keys:
                    if key.font_size != max_size and \
                       not key.ignore_group:
                        key.font_size = max_size
                        changed_keys.add(key)

        layout.set_font_sizes_valid(True)

        return tuple(changed_keys)

    def get_key_at_location(self, point):
        layout = self.get_layout()
        keyboard = self.keyboard
        if layout and keyboard:  # may be gone on exit
            return layout.get_key_at(point, keyboard.get_active_layer_ids())
        return None

    def get_xid(self):
        # Zesty, X, Gtk 3.22: XInput select_events() on self leads to
        # LP: #1636252. On the first call to get_xid() of a child widget,
        # Gtk creates a new native X Window with broken transparency.
        # The toplevel window ought to always have a native X window, so
        # we'll pick that one instead and skip on-the fly creation.
        # TouchInput isn't used for anything other than full client areas
        # yet, so in principle this shouldn't be a problem.

        toplevel = self.get_toplevel()
        if toplevel:
            topwin = toplevel.get_window()
            if topwin:
                return topwin.get_xid()
        return 0


