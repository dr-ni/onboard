# -*- coding: utf-8 -*-
""" GTK keyboard widget """

from __future__ import division, print_function, unicode_literals

import cairo

from gi.repository          import Gdk, Gtk, Pango, PangoCairo

from Onboard.utils          import Rect, Timer, roundrect_arc
from Onboard.WindowUtils    import limit_window_position, \
                                   get_monitor_rects, \
                                   canvas_to_root_window_rect, \
                                   physical_to_mohitor_pixel_size
from Onboard.TouchInput     import TouchInput
from Onboard                import KeyCommon
from Onboard.Layout         import LayoutRoot, LayoutPanel
from Onboard.LayoutView     import LayoutView
from Onboard.KeyGtk         import RectKey

import Onboard.osk as osk

### Logging ###
import logging
_logger = logging.getLogger(__name__)
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

# prepare mask for faster access
BUTTON123_MASK = Gdk.ModifierType.BUTTON1_MASK | \
                 Gdk.ModifierType.BUTTON2_MASK | \
                 Gdk.ModifierType.BUTTON3_MASK


class TouchFeedback:
    """ Display magnified labels as touch feedback """

    def __init__(self):
        self._visible_key_feedback_popups = {}
        self._key_feedback_popup_pool = []

    def show(self, key, view):
        if not key in self._visible_key_feedback_popups:  # not already shown?
            r = key.get_canvas_border_rect()
            root_rect = canvas_to_root_window_rect(view, r)
            toplevel = view.get_toplevel()

            popup = self._get_free_key_feedback_popup()
            if popup is None:
                popup = KeyFeedbackPopup()
                popup.set_transient_for(toplevel)
                self._key_feedback_popup_pool.append(popup)
                popup.realize()

            # Set window size
            w_mm = h_mm = config.keyboard.touch_feedback_size
            w, h = physical_to_mohitor_pixel_size(popup, (w_mm, h_mm),
                                                         (100, 100))
            popup.set_default_size(w, h)
            popup.resize(w, h)

            popup.set_key(key)
            popup.position_at(root_rect.x + root_rect.w * 0.5,
                              root_rect.y, 0.5, 1.0)
            popup.supports_alpha = view.supports_alpha
            popup.set_opacity(toplevel.get_opacity())
            popup.show_all()

            self._visible_key_feedback_popups[key] = popup

    def hide(self, key = None):
        keys = [key] if key else list(self._visible_key_feedback_popups.keys())
        for _key in keys:
            popup = self._visible_key_feedback_popups.get(_key)
            if popup:
                popup.hide()
                popup.set_key(None)
                del self._visible_key_feedback_popups[_key]

    def _get_free_key_feedback_popup(self):
        """ Get a currently unused one from the pool of popups. """
        for popup in self._key_feedback_popup_pool:
            if not popup.get_key():
                return popup
        return None


class KeyboardPopup(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self,
                            skip_taskbar_hint=True,
                            skip_pager_hint=True,
                            has_resize_grip=False,
                            urgency_hint=False,
                            decorated=False,
                            accept_focus=False,
                            opacity=1.0)

        self.set_keep_above(True)

        # use transparency if available
        screen = Gdk.Screen.get_default()
        visual = screen.get_rgba_visual()
        self.supports_alpha = False
        if visual:
            self.set_visual(visual)
            self.override_background_color(Gtk.StateFlags.NORMAL,
                                           Gdk.RGBA(0, 0, 0, 0))
            self.supports_alpha = True

    def position_at(self, x, y, x_align, y_align):
        """
        Align the window with the given point.
        x, y in root window coordinates.
        """
        rect = Rect.from_position_size(self.get_position(), self.get_size())
        rect = rect.align_at_point(x, y, x_align, y_align)
        rect = self.limit_to_workarea(rect)
        x, y = rect.get_position()

        self.move(x, y)

    def limit_to_workarea(self, rect, x_mon, y_mon):
        screen = self.get_screen()
        mon = screen.get_monitor_at_point(x_mon, y_mon)
        area = screen.get_monitor_workarea(mon)
        area = Rect(area.x, area.y, area.width, area.height)
        return rect.intersection(area)

    def limit_to_workarea(self, rect):
        visible_rect = Rect(0, 0, rect.w, rect.h)

        x, y = limit_window_position(rect.x, rect.y, visible_rect,
                                     get_monitor_rects(self.get_screen()))
        return Rect(x, y, rect.w, rect.h)


class KeyFeedbackPopup(KeyboardPopup):

    _pango_layout = None
    _osk_util = osk.Util()

    def __init__(self):
        KeyboardPopup.__init__(self)
        self._key = None
        self.connect("realize", self._on_realize_event)
        self.connect("draw", self._on_draw)

    def _on_realize_event(self, user_data):
        win = self.get_window()
        win.set_override_redirect(True)

        # set minimal input shape for the popup to become click-through
        self._osk_util.set_input_rect(win, 0, 0, 1, 1)

    def _on_draw(self, widget, context):
        if not KeyFeedbackPopup._pango_layout:
            KeyFeedbackPopup._pango_layout = Pango.Layout(context=Gdk.pango_context_get())

        rect = Rect(0, 0, self.get_allocated_width(), 
                          self.get_allocated_height())
        label_rect = rect.deflate(rect.w/10.0)

        # background
        fill = self._key.get_fill_color()
        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.paint()
        context.restore()
        context.set_source_rgba(*fill)
        roundrect_arc(context, rect, config.CORNER_RADIUS)
        context.fill()

        # draw label/image
        label_color = self._key.get_label_color()
        pixbuf = self._key.get_image(label_rect.w, label_rect.h)
        if pixbuf:
            self._draw_image(context, pixbuf, label_rect, label_color)
        else:
            label = self._key.get_label()
            if label:
                if label == " ":
                    label = "␣"
                self._draw_text(context, label, label_rect, label_color)

    def _draw_text(self, context, text, rect, rgba):
        layout = self._pango_layout
        layout.set_text(text, -1)

        # find text extents
        font_description = Pango.FontDescription( \
                                        config.theme_settings.key_label_font)
        base_extents = self._calc_base_layout_extents(layout, font_description)

        # scale label to the available rect
        font_size = self._calc_font_size(rect, base_extents)
        font_description.set_size(max(1, font_size))
        layout.set_font_description(font_description)

        # center
        w, h = layout.get_size()
        w /= Pango.SCALE
        h /= Pango.SCALE
        offset = rect.align_rect(Rect(0, 0, w, h)).get_position()

        # draw
        context.move_to(*offset)
        context.set_source_rgba(*rgba)
        PangoCairo.show_layout(context, layout)

    def _draw_image(self, context, pixbuf, rect, rgba):
        Gdk.cairo_set_source_pixbuf(context, pixbuf, rect.x, rect.y)
        pattern = context.get_source()
        context.rectangle(*rect)
        context.set_source_rgba(*rgba)
        context.mask(pattern)
        context.new_path()

    @staticmethod
    def _calc_font_size(rect, base_extents):
        size_for_maximum_width  = rect.w / base_extents[0]
        size_for_maximum_height = rect.h / base_extents[1]
        if size_for_maximum_width < size_for_maximum_height:
            return int(size_for_maximum_width)
        else:
            return int(size_for_maximum_height)

    @staticmethod
    def _calc_base_layout_extents(layout, font_description):
        BASE_FONTDESCRIPTION_SIZE = 10000000

        font_description.set_size(BASE_FONTDESCRIPTION_SIZE)
        layout.set_font_description(font_description)

        w, h = layout.get_size()   # In Pango units
        w = w or 1.0
        h = h or 1.0
        extents = (w / (Pango.SCALE * BASE_FONTDESCRIPTION_SIZE),
                   h / (Pango.SCALE * BASE_FONTDESCRIPTION_SIZE))
        return extents

    def get_key(self):
        return self._key

    def set_key(self, key):
        self._key = key


class AlternativeKeysPopup(KeyboardPopup, LayoutView, TouchInput):

    MAX_KEY_COLUMNS  = 8  # max number of keys in one row
    IDLE_CLOSE_DELAY = 0  # seconds of inactivity until window closes

    def __init__(self, keyboard, notify_done_callback):
        self._layout = None
        self._notify_done_callback = notify_done_callback

        KeyboardPopup.__init__(self)
        LayoutView.__init__(self, keyboard)
        TouchInput.__init__(self)

        self.connect("draw",                 self._on_draw)
        self.connect("destroy",              self._on_destroy_event)

        self._close_timer = Timer()
        self.start_close_timer()

    def cleanup(self):
        self.stop_close_timer()
        LayoutView.cleanup(self)  # deregister from keyboard

    def get_toplevel(self):
        return self

    def get_layout(self):
        return self._layout

    def get_frame_width(self):
        return self._frame_width

    def create_layout(self, source_key, alternatives, color_scheme):
        keys = []
        context = source_key.context

        # calculate border around the layout
        canvas_border = context.scale_log_to_canvas((1, 1))
        self._frame_width = 7 + min(canvas_border)
        frame_width = self.get_frame_width()
        frame_size  = frame_width, frame_width

        # parse alterantives into lines
        lines, ncolumns = self.parse_alternatives(alternatives)
        nrows = len(lines)
        spacing     = (1, 1)

        # calc canvas size
        rect = source_key.get_canvas_border_rect()
        layout_canvas_rect = Rect(frame_size[0], frame_size[1],
                              rect.w * ncolumns + spacing[0] * (ncolumns - 1),
                              rect.h * nrows + spacing[1] * (nrows - 1))

        canvas_rect = layout_canvas_rect.inflate(*frame_size)

        # subdive into logical rectangles for the keys
        layout_rect = context.canvas_to_log_rect(layout_canvas_rect)
        key_rects = layout_rect.subdivide(ncolumns, nrows, *spacing)

        # create the keys, slots for empty labels are skipped
        count = 0
        for i, line in enumerate(lines):
            for j, label in enumerate(line):
                slot = i * ncolumns + j
                if label:
                    key = RectKey("_alternative" + str(count), key_rects[slot])
                    key.group  = "alternatives"
                    key.color_scheme = color_scheme
                    if label == "-x-":
                        key.labels = {}
                        key.image_filename = "close.svg"
                        key.type = KeyCommon.BUTTON_TYPE
                    else:
                        key.labels = {0: label}
                        key.code  = label[0]
                        key.type = KeyCommon.CHAR_TYPE
                    keys.append(key)
                    count += 1

        item = LayoutPanel()
        item.border  = 0
        item.set_items(keys)
        layout = LayoutRoot(item)
        layout.fit_inside_canvas(layout_canvas_rect)
        self._layout = layout
        self.update_labels()

        self.color_scheme = color_scheme

        # set window size
        w, h = canvas_rect.get_size()
        self.set_default_size(w + 1, h + 1)

    def parse_alternatives(self, alternatives):
        """
        Split alternatives into lines, support newlines and
        append a close button.
        """
        if "\n" in alternatives:
            return self.parse_free_format(alternatives)
        else:
            return self.parse_fixed(alternatives)

    def parse_fixed(self, alternatives):
        max_columns = self.MAX_KEY_COLUMNS
        min_columns = max_columns // 2

        # find the number of columns with the best packing,
        # i.e. the least number of empty slots.
        n = len(alternatives) + 1    # +1 for close button
        max_mod = 0
        ncolumns = max_columns
        for i in range(max_columns, min_columns, -1):
            m = n % i
            if m == 0:
                max_mod = m
                ncolumns = i
                break
            if max_mod < m:
                max_mod = m
                ncolumns = i

        # limit to len for the single row case
        ncolumns = min(n, ncolumns)

        # cut the input into lines of the newly found optimal length
        lines = []
        line = []
        column = 0
        for value in alternatives:
            line.append(value)
            column += 1
            if column >= ncolumns:
                lines.append(line)
                line = []
                column = 0

        # append slot for close button
        n = len(line)
        line.extend([""]*(ncolumns - (n+1)))
        line.append("-x-")
        lines.append(line)

        return lines, ncolumns

    def parse_free_format(self, alternatives):
        max_columns = self.MAX_KEY_COLUMNS

        lines = []
        line = None
        ncolumns = 0

        for value in alternatives + ["-x-"]:
            if value == "\n" or \
               line and len(line) >= max_columns:
                if line:
                    lines.append(line)
                line = None

            if not value in ["\n"]:
                if value == "-x-":
                    if not line:
                        line = []
                    n = len(line)
                    line.extend([""]*(ncolumns - (n+1)))
                    line.append(value)
                    ncolumns = max(ncolumns, len(line))
                else:
                    if not line:
                        line = []
                    line.append(value)
                    ncolumns = max(ncolumns, len(line))

        if line:
            lines.append(line)

        return lines, ncolumns

    def handle_realize_event(self):
        self.get_window().set_override_redirect(True)
        super(AlternativeKeysPopup, self).handle_realize_event()

    def _on_destroy_event(self, user_data):
        self.cleanup()

    def on_enter_notify(self, widget, event):
        self.stop_close_timer()

    def on_leave_notify(self, widget, event):
        self.start_close_timer()

    def on_input_sequence_begin(self, sequence):
        self.stop_close_timer()
        key = self.get_key_at_location(sequence.point)
        if key:
            sequence.active_key = key
            self.keyboard.key_down(key, self, sequence)

    def on_input_sequence_update(self, sequence):
        if sequence.state & BUTTON123_MASK:
            key = self.get_key_at_location(sequence.point)

            # drag-select new active key
            active_key = sequence.active_key
            if sequence.active_key != key and \
               (not active_key or not active_key.activated):
                sequence.active_key = key
                self.keyboard.key_up(active_key, self, sequence, False)
                self.keyboard.key_down(key, self, sequence, False)

    def on_input_sequence_end(self, sequence):
        key = sequence.active_key
        if key:
            keyboard = self.keyboard
            keyboard.key_up(key, self, sequence)

            Timer(config.UNPRESS_DELAY, self.close_window)
        else:
            self.close_window()

    def _on_draw(self, widget, context):
        decorated = LayoutView.draw(self, widget, context)

    def draw_window_frame(self, context, lod):
        corner_radius = config.CORNER_RADIUS
        border_rgba = self.get_popup_window_rgba("border")
        alpha = border_rgba[3]

        colors = [
                  [[0.5, 0.5, 0.5, alpha], 0  , 1],
                  [border_rgba,            1.5, 2.0],
                 ]

        rect = Rect(0, 0, self.get_allocated_width(),
                          self.get_allocated_height())

        for rgba, pos, width in colors:
            r = rect.deflate(width)
            roundrect_arc(context, r, corner_radius)
            context.set_line_width(width)
            context.set_source_rgba(*rgba)
            context.stroke()

    def close_window(self):
        self._notify_done_callback()

    def start_close_timer(self):
        if self.IDLE_CLOSE_DELAY:
            self._close_timer.start(self.IDLE_CLOSE_DELAY, self.close_window)

    def stop_close_timer(self):
        self._close_timer.stop()

