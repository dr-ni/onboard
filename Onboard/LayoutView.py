# -*- coding: utf-8 -*-
""" Keyboard layout view """

from __future__ import division, print_function, unicode_literals

import os
import time
from math import pi

import cairo
from gi.repository         import Gtk

from Onboard.utils         import Rect, Timer, \
                                  roundrect_arc, roundrect_curve, \
                                  gradient_line, brighten, timeit
from Onboard.KeyGtk        import Key
from Onboard.KeyCommon     import LOD

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
        self._font_sizes_valid = False
        self._shadow_quality_valid = False
        self._last_canvas_shadow_rect = Rect()
        
        keyboard.register_view(self)

    def cleanup(self):
        keyboard.deregister_view(self)

        # free xserver memory
        self.invalidate_keys()
        self.invalidate_shadows()

    def on_layout_loaded(self):
        """ called when the layout has been loaded """
        self.invalidate_shadow_quality()

    def get_layout(self):
        return self.keyboard.layout

    def get_color_scheme(self):
        return self.keyboard.color_scheme

    def invalidate_font_sizes(self):
        """
        Update font_sizes at the next possible chance.
        """
        self._font_sizes_valid = False

    def invalidate_keys(self):
        """
        Clear cached key patterns, e.g. after resizing,
        change of theme settings.
        """
        layout = self.get_layout()
        if layout:
            for item in layout.iter_keys():
                item.invalidate_key()

    def invalidate_shadows(self):
        """
        Clear cached shadow patterns, e.g. after resizing,
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
            self.invalidate_keys()
            self.invalidate_shadows()
            self.invalidate_font_sizes()
            self.redraw()

    def redraw(self, keys = None, invalidate = True):
        """
        Queue redrawing for individual keys or the whole keyboard.
        """
        if keys is None:
            self.queue_draw()
        elif len(keys) == 0:
            pass
        else:
            area = None
            for key in keys:
                rect = key.get_canvas_border_rect()
                area = area.union(rect) if area else rect

                # assume keys need to be refreshed when actively redrawn
                # e.g. for pressed state changes, dwell progress updates...
                if invalidate:
                    key.invalidate_key()

            # account for stroke width, anti-aliasing
            if self.get_layout():
                extra_size = keys[0].get_extra_render_size()
                area = area.inflate(*extra_size)

            self.queue_draw_area(*area)

    def redraw_labels(self, invalidate = True):
        self.redraw(self.update_labels(), invalidate)

    def has_input_sequences(self):
        return False

    def update_transparency(self):
        pass

    def process_updates(self):
        """ Draw now, synchronously. """
        window = self.get_window()
        if window:
            window.process_updates(True)

    def draw(self, widget, context):
        if not Gtk.cairo_should_draw_window(context, self.get_window()):
            return

        lod = self._lod

        # lazily update font sizes and labels
        if not self._font_sizes_valid:
            self.update_labels(lod)

        draw_rect = self.get_damage_rect(context)

        # draw background
        decorated = self._draw_background(context, lod)

        layout = self.get_layout()
        if not layout:
            return

        # draw layer 0 and None-layer background
        layer_ids = layout.get_layer_ids()
        if config.window.transparent_background:
            alpha = 0.0
        elif decorated:
            alpha = self._get_background_rgba()[3]
        else:
            alpha = 1.0
        self._draw_layer_key_background(context, alpha, None, lod)
        if layer_ids:
            self._draw_layer_key_background(context, alpha, layer_ids[0], lod)

        # run through all visible layout items
        for item in layout.iter_visible_items():
            if item.layer_id:
                self._draw_layer_background(context, item, layer_ids, decorated)

            # draw key
            if item.is_key() and \
               draw_rect.intersects(item.get_canvas_border_rect()):
                if lod == LOD.FULL:
                    item.draw_cached(context)
                else:
                    item.draw(context, lod)

        return decorated

    def _draw_background(self, context, lod):
        """ Draw keyboard background """
        transparent_bg = False
        plain_bg = False

        if config.xid_mode:
            # xembed mode
            # Disable transparency in lightdm and g-s-s for now.
            # There are too many issues and there is no real
            # visual improvement.
            if False and \
               self.supports_alpha:
                self._clear_background(context)
                transparent_bg = True
            else:
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

    def _get_layer_fill_rgba(self, layer_index):
        color_scheme = self.get_color_scheme()
        if color_scheme:
            return color_scheme.get_layer_fill_rgba(layer_index)
        else:
            return [0.5, 0.5, 0.5, 1.0]

    def _get_background_rgba(self):
        """ layer 0 color * background_transparency """
        layer0_rgba = self._get_layer_fill_rgba(0)
        background_alpha = config.window.get_background_opacity()
        background_alpha *= layer0_rgba[3]
        return layer0_rgba[:3] + [background_alpha]

    def _draw_transparent_background(self, context, lod):
        """ fill with the transparent background color """
        corner_radius = config.CORNER_RADIUS
        rect = self._get_aspect_frame_rect()
        fill = self._get_background_rgba()

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

        docked = config.is_docking_expanded()
        if docked:
            context.rectangle(*rect)
        else:
            roundrect_arc(context, rect, corner_radius)
        context.fill()

        if not docked:
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
            self._draw_layer_key_background(context, 1.0, item.layer_id)

    def _draw_layer_key_background(self, context, alpha = 1.0,
                                   layer_id = None, lod = LOD.FULL):
        self._draw_dish_key_background(context, alpha, layer_id)
        self._draw_shadows(context, layer_id, lod)

    def _draw_dish_key_background(self, context, alpha = 1.0, layer_id = None):
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

            for item in layout.iter_layer_keys(layer_id):
                rect = item.get_canvas_fullsize_rect()
                rect = rect.inflate(*enlargement)
                roundrect_curve(context, rect, corner_radius)
                context.fill()

            context.pop_group_to_source()
            context.paint_with_alpha(alpha);

    def _draw_shadows(self, context, layer_id, lod):
        """
        Draw drop shadows for all keys.
        """
        if not config.theme_settings.key_shadow_strength:
            return

        # auto-select shadow quality
        if not self._shadow_quality_valid:
            quality = self.probe_shadow_performance(context)
            Key.set_shadow_quality(quality)
            self._shadow_quality_valid = True

        # draw shadows
        context.save()
        self.set_shadow_scale(context, lod)

        draw_rect = self.get_damage_rect(context)
        layout = self.get_layout()
        for item in layout.iter_layer_keys(layer_id):
            if draw_rect.intersects(item.get_canvas_border_rect()):
                item.draw_shadow_cached(context)

        context.restore()

    def probe_shadow_performance(self, context):
        """
        Select shadow quality based on the estimated render time of
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
                              "at quality {}." \
                              .format(estimate * 1000,
                                      quality))
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
        r  = self._get_aspect_frame_rect()
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

    def _get_aspect_frame_rect(self):
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
        return rect

    def get_frame_width(self):
        return config.get_frame_width()

    def update_labels(self, lod = LOD.FULL):
        """
        Iterates through all key groups and set each key's
        label font size to the maximum possible for that group.
        """
        changed_keys = set()
        layout = self.get_layout()

        mod_mask = self.keyboard.get_mod_mask()


        if layout:
            context = self.create_pango_context()

            if lod == LOD.FULL: # no label changes necessary while dragging

                for key in layout.iter_keys():
                    old_label = key.get_label()
                    key.configure_label(mod_mask)
                    if key.get_label() != old_label:
                        changed_keys.add(key)

            for keys in layout.get_key_groups().values():
                max_size = 0
                for key in keys:
                    best_size = key.get_best_font_size(context, mod_mask)
                    if best_size:
                        if not max_size or best_size < max_size:
                            max_size = best_size

                for key in keys:
                    if key.font_size != max_size:
                        key.font_size = max_size
                        changed_keys.add(key)

        self._font_sizes_valid = True
        return tuple(changed_keys)

    def get_key_at_location(self, point):
        layout = self.get_layout()
        keyboard = self.keyboard
        if layout and keyboard:  # may be gone on exit
            return layout.get_key_at(point, keyboard.active_layer)
        return None

