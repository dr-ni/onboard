""" GTK specific keyboard class """

import os
import time
from math import sin, pi

import cairo
from gi.repository import GObject, Gdk, Gtk

from Onboard.utils import Rect, round_corners, roundrect_arc, \
                          WindowManipulator, Timer

from gettext import gettext as _

### Logging ###
import logging
_logger = logging.getLogger("KeyboardGTK")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, auto-hide won't be available"))


class Transition:
    SHOW       = 1
    HIDE       = 2
    AUTOSHOW   = 3
    AUTOHIDE   = 4
    ACTIVATE   = 5
    INACTIVATE = 6

class OpacityFadeTimer(Timer):
    """ Fades between the widgets current and a given target opacity """

    _widget = None
    _callback = None
    _callback_args = ()

    def set_widget(self, widget):
        self._widget = widget

    def fade_to(self, target_opacity, duration,
                callback = None, *callback_args):
        """
        Start opacity fade.
        duration: fade time in seconds, 0 for immediate opacity change
        """
        self._start_opacity = self._widget.get_opacity()
        self._target_opacity = target_opacity
        self._start_time = time.time()
        self._duration = duration
        self._callback = callback
        self._callback_args = callback_args

        self.start(0.05)

    def on_timer(self):
        elapsed = time.time() - self._start_time
        if self._duration:
            lin_progress = min(1.0, elapsed / self._duration)
        else:
            lin_progress = 1.0
        sin_progress = (sin(lin_progress * pi - pi / 2.0) + 1.0) / 2.0
        opacity = sin_progress * (self._target_opacity - self._start_opacity) + \
                  self._start_opacity
        self._widget.set_opacity(opacity)

        if lin_progress >= 1.0:
            if self._callback:
                self._callback(*self._callback_args)
            return False

        return True


class InactivityTimer(Timer):
    """
    Waits for the inactivity delay and
    transitions between active and inactive state.
    """
    _keyboard = None
    _active = False

    def __init__(self, keyboard):
        self._keyboard = keyboard

    def is_enabled(self):
        window = self._keyboard.get_kbd_window()
        if not window:
            return False
        screen = window.get_screen()
        return screen and  screen.is_composited() and \
               config.enable_inactive_transparency and \
               not config.xid_mode

    def is_active(self):
        return self._active

    def transition_to(self, active):
        if active:
            Timer.stop(self)
            self._keyboard.transition_to(Transition.ACTIVATE)
        else:
            if not config.xid_mode:
                Timer.start(self, config.inactive_transparency_delay)
        self._active = active

    def on_timer(self):
        self._keyboard.transition_to(Transition.INACTIVATE)
        return False


class AutoHideTimer(Timer):
    """
    Delays hiding and showing the window a little, in the hope
    that all at-spi focus messages have arrived until then.
    """
    _keyboard = None
    _visible = True

    def __init__(self, keyboard):
        self._keyboard = keyboard

    def set_visible(self, visible):
        self._visible = visible
        self.start(0.1)

    def on_timer(self):
        if self._visible:
            self._keyboard.transition_to(Transition.AUTOSHOW)
        else:
            self._keyboard.transition_to(Transition.AUTOHIDE)
        return False


class AtspiAutoHide(object):
    """ 
    Auto-hide and show Onboard based on at-spi focus events.
    """

    _atspi_listeners_registered = False
    _focused_accessible = None

    def __init__(self, transition_target):
        self.autohide_timer = AutoHideTimer(transition_target)
        self.update()

    def cleanup(self):
        self._register_atspi_listeners(False)

    def update(self):
        self._register_atspi_listeners(config.auto_hide)

    def _register_atspi_listeners(self, register = True):
        if not "Atspi" in globals():
            return

        if register:
            if not self._atspi_listeners_registered:
                Atspi.EventListener.register_no_data(self._on_atspi_global_focus,
                                                     "focus")
                Atspi.EventListener.register_no_data(self._on_atspi_object_focus,
                                                     "object:state-changed:focused")
                self._atspi_listeners_registered = True

        else:
            if self._atspi_listeners_registered:
                Atspi.EventListener.deregister_no_data(self._on_atspi_global_focus,
                                                     "focus")
                Atspi.EventListener.deregister_no_data(self._on_atspi_object_focus,
                                                     "object:state-changed:focused")
                self._atspi_listeners_registered = False

    def _on_atspi_global_focus(self, event):
        self._on_atspi_focus(event, True)

    def _on_atspi_object_focus(self, event):
        self._on_atspi_focus(event)

    def _on_atspi_focus(self, event, focus_received = False):
        if config.auto_hide:
            accessible = event.source
            #print accessible.get_name(), accessible.get_state_set().states, accessible.get_role(), accessible.get_role_name(), event.detail1

            focused = focus_received or event.detail1   # received focus?
            editable = self._is_accessible_editable(accessible)
            visible =  focused and editable

            if focused:
                self._focused_accessible = accessible
                self.autohide_timer.set_visible(visible)
            elif not focused and self._focused_accessible == accessible:
                self._focused_accessible = None
                self.autohide_timer.set_visible(visible)

    def _is_accessible_editable(self, accessible):
        role = accessible.get_role()
        state = accessible.get_state_set()

        if role in [Atspi.Role.TEXT,
                    Atspi.Role.TERMINAL,
                    Atspi.Role.DATE_EDITOR,
                    Atspi.Role.PASSWORD_TEXT,
                    Atspi.Role.EDITBAR,
                    Atspi.Role.ENTRY,
                    Atspi.Role.DOCUMENT_TEXT,
                    Atspi.Role.DOCUMENT_EMAIL,
                    Atspi.Role.SPIN_BUTTON,
                   ]:
            if role in [Atspi.Role.TERMINAL] or \
               state.contains(Atspi.StateType.EDITABLE):
                return True
        return False


class KeyboardGTK(Gtk.DrawingArea, WindowManipulator):

    scanning_time_id = None

    DWELL_ACTIVATED = -1

    def __init__(self):
        Gtk.DrawingArea.__init__(self)

        self.active_key = None
        self.click_detected = False
        self.click_timer = None
        self.opacity_fade = OpacityFadeTimer()
        self.inactivity_timer = InactivityTimer(self)
        self.dwell_timer = None
        self.dwell_key = None
        self.last_dwelled_key = None
        self.auto_hide = AtspiAutoHide(self)

        # self.set_double_buffered(False)
        self.set_app_paintable(True)

        # not tool-tips when embedding, gnome-screen-saver flickers (Oneiric)
        if not config.xid_mode:
            self.set_has_tooltip(True) # works only at window creation -> always on

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.ENTER_NOTIFY_MASK)

        self.connect("parent-set",           self._cb_parent_set)
        self.connect("draw",                 self.draw)
        self.connect("button_press_event",   self._cb_mouse_button_press)
        self.connect("button_release_event", self._cb_mouse_button_release)
        self.connect("motion-notify-event",  self._cb_motion)
        self.connect("query-tooltip",        self._cb_query_tooltip)
        self.connect("enter-notify-event",   self._cb_mouse_enter)
        self.connect("leave-notify-event",   self._cb_mouse_leave)
        self.connect("configure-event",      self._cb_configure_event)

    def _cb_parent_set(self, widget, old_parent):
        win = self.get_kbd_window()
        if win:
            self.opacity_fade.set_widget(win)
            self.update_transparency()

    def cleanup(self):
        self.auto_hide.cleanup()
        self.stop_click_polling()

    def update_auto_hide(self):
        self.auto_hide.update()

    def start_click_polling(self):
        self.stop_click_polling()
        self.click_timer = GObject.timeout_add(2, self._cb_click_timer)
        self.click_detected = False

    def stop_click_polling(self):
        if self.click_timer:
            GObject.source_remove(self.click_timer)
            self.click_timer = None

    def _cb_click_timer(self):
        """ poll for mouse click outside of onboards window """
        rootwin = Gdk.get_default_root_window()
        dunno, x, y, mask = rootwin.get_pointer()
        if mask & (Gdk.ModifierType.BUTTON1_MASK |
                   Gdk.ModifierType.BUTTON2_MASK |
                   Gdk.ModifierType.BUTTON3_MASK):
            self.click_detected = True
        elif self.click_detected:
            # button released anywhere outside of onboards control
            self.stop_click_polling()
            self.on_outside_click()
            return False

        return True

    def update_transparency(self):
        self.transition_to(Transition.ACTIVATE)
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.transition_to(False)

    def update_inactive_transparency(self):
        if self.inactivity_timer.is_enabled():
            self.transition_to(Transition.INACTIVATE)

    def get_transition_target_opacity(self, transition):
        transparency = 0

        if transition in [Transition.ACTIVATE]:
            transparency = config.transparency

        elif transition in [Transition.SHOW,
                            Transition.AUTOSHOW]:
            if not self.inactivity_timer.is_enabled() or \
               self.inactivity_timer.is_active():
                transparency = config.transparency
            else:
                transparency = config.inactive_transparency

        elif transition in [Transition.HIDE,
                            Transition.AUTOHIDE]:
            transparency = 100

        elif transition == Transition.INACTIVATE:
            transparency = config.inactive_transparency

        return 1.0 - transparency / 100.0

    def transition_to(self, transition):
        window = self.get_kbd_window()
        if window:
            duration = 0.4
            if transition in [Transition.SHOW,
                              Transition.HIDE,
                              Transition.AUTOSHOW,
                              Transition.ACTIVATE]:
                duration = 0.15

            if transition in [Transition.SHOW,
                              Transition.AUTOSHOW]:
                if self.inactivity_timer.is_enabled():
                    self.inactivity_timer.transition_to(False)
                window.set_visible(True)

            opacity = self.get_transition_target_opacity(transition)
            _logger.debug(_("setting keyboard opacity to {}%") \
                                .format(opacity))

            # no fade for non-composited screens (unity-2d)
            screen = window.get_screen()
            if screen and not screen.is_composited():
                duration = 0
                opacity = 1.0

            self.opacity_fade.fade_to(opacity, duration,
                                      self.on_final_opacity, transition)

    def on_final_opacity(self, transition):
        if transition in [Transition.HIDE,
                          Transition.AUTOHIDE]:
            window = self.get_kbd_window()
            if window:
                window.set_visible(False)

    def toggle_visible(self):
        """ main method to show/hide onboard manually"""
        window = self.get_kbd_window()
        if window:
            if window.is_visible():
                self.transition_to(Transition.HIDE)
            else:
                self.transition_to(Transition.SHOW)

    def get_drag_window(self):
        """ overloaded for WindowManipulator """
        return self.get_kbd_window()

    def _cb_configure_event(self, widget, user_data):
        self.canvas_rect = Rect(0, 0,
                                self.get_allocated_width(),
                                self.get_allocated_height())
        self.update_layout()

    def _cb_mouse_enter(self, widget, event):
        self.release_active_key() # release move key

        # stop inactivity timer
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.transition_to(True)

    def _cb_mouse_leave(self, widget, event):
        """
        horrible.  Grabs pointer when key is pressed, released when cursor
        leaves keyboard
        """
        Gdk.pointer_ungrab(event.time)
        if self.active_key:
            if self.active_scan_key:
                self.active_key = None
                self.active_scan_key = None
                self.queue_draw()
            else:
                self.release_key(self.active_key)

        # another terrible hack
        # start a high frequency timer to detect clicks outside of onboard
        self.start_click_polling()

        # start inactivity timer
        if self.inactivity_timer.is_enabled():
            self.inactivity_timer.transition_to(False)

        self.stop_dwelling()

        return True

    def _cb_motion(self, widget, event):
        cursor_type = None
        point = (event.x, event.y)

        hit_key = self.get_key_at_location(point)

        if event.state & (Gdk.ModifierType.BUTTON1_MASK |
                          Gdk.ModifierType.BUTTON2_MASK |
                          Gdk.ModifierType.BUTTON3_MASK):

            # drag operation in progress?
            self.handle_motion()
        else:
            # start dwelling if we have entered a dwell-enabled key
            if hit_key and \
               not self.is_dwelling() and \
               not self.already_dwelled(hit_key):
                controller = self.button_controllers.get(hit_key)
                if controller and controller.can_dwell() and \
                   hit_key.sensitive:
                    self.start_dwelling(hit_key)

        # cancel dwelling when the hit key changes
        if self.dwell_key and self.dwell_key != hit_key or \
           self.last_dwelled_key and self.last_dwelled_key != hit_key:
            self.cancel_dwelling()

        # find cursor for frame resize handles
        enable_drag_cursor = not config.xid_mode  and \
                             not config.has_window_decoration() and \
                             not hit_key
        self.set_drag_cursor_at(point, enable_drag_cursor)

    def _cb_mouse_button_press(self,widget,event):
        Gdk.pointer_grab(self.get_window(),
                         False,
                         Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK |
                         Gdk.EventMask.POINTER_MOTION_MASK,
                         None, None, event.time)

        self.stop_click_polling()
        self.stop_dwelling()

        if event.type == Gdk.EventType.BUTTON_PRESS:  # why?

            key = self.get_key_at_location((event.x, event.y))
            if not key and \
               not config.has_window_decoration() and \
               not config.xid_mode:
                if self.handle_press((event.x, event.y)):
                    return True

            if config.enable_scanning and \
               self.get_scan_columns() and \
               (not key or key.get_layer()):

                if self.scanning_time_id:
                    if not self.scanning_y == None:
                        self.press_key(self.active_scan_key)
                        self.release_key(self.active_scan_key)
                        GObject.source_remove(self.scanning_time_id)
                        self.reset_scan()
                    else:
                        self.scanning_y = -1
                        GObject.source_remove(self.scanning_time_id)
                        self.scanning_time_id = GObject.timeout_add(
                                config.scanning_interval, self.scan_tick)
                else:
                    self.scanning_time_id = GObject.timeout_add(
                        config.scanning_interval, self.scan_tick)
                    self.scanning_x = -1
            else:
                self.active_key = key
                if key:
                    self.press_key(key, event.button)

        return True

    def _cb_mouse_button_release(self,widget,event):
        Gdk.pointer_ungrab(event.time)
        self.release_active_key()
        self.stop_drag()

    def is_dwelling(self):
        return not self.dwell_key is None

    def already_dwelled(self, key):
        return self.last_dwelled_key is key

    def start_dwelling(self, key):
        self.cancel_dwelling()
        self.dwell_key = key
        self.last_dwelled_key = key
        key.start_dwelling()
        self.dwell_timer = GObject.timeout_add(50, self._cb_dwell_timer)

    def cancel_dwelling(self):
        self.stop_dwelling()
        self.last_dwelled_key = None

    def stop_dwelling(self):
        if self.dwell_timer:
            GObject.source_remove(self.dwell_timer)
            self.dwell_timer = None
            self.redraw(self.dwell_key)
            self.dwell_key.stop_dwelling()
            self.dwell_key = None

    def _cb_dwell_timer(self):
        if self.dwell_key:
            self.redraw(self.dwell_key)

            if self.dwell_key.is_done():
                key = self.dwell_key
                self.stop_dwelling()

                self.press_key(key, self.DWELL_ACTIVATED)
                self.release_key(key, self.DWELL_ACTIVATED)

                return False
        return True

    def release_active_key(self):
        if self.active_key:
            self.release_key(self.active_key)
            self.active_key = None
        return True

    def reset_scan(self, scanning=None):
        """ Between scans and when value of scanning changes. """
        if self.active_scan_key:
            self.active_scan_key.beingScanned = False
        if self.scanning_time_id:
            GObject.source_remove(self.scanning_time_id)
            self.scanning_time_id = None

        self.scanning_x = None
        self.scanning_y = None
        self.queue_draw()

    def _cb_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if config.show_tooltips:
            key = self.get_key_at_location((x, y))
            if key:
                if key.tooltip:
                    r = Gdk.Rectangle()
                    r.x, r.y, r.width, r.height = key.get_canvas_rect().to_list()
                    tooltip.set_tip_area(r)   # no effect in oneiric?
                    tooltip.set_text(_(key.tooltip))
                    return True
        return False


    def draw(self, widget, context):
        #_logger.debug("Draw: clip_extents=" + str(context.clip_extents()))

        clip_rect = Rect.from_extents(*context.clip_extents())

        # draw background
        self.draw_background(context)

        # run through all visible layout items
        layer_ids = self.layout.get_layer_ids()
        for item in self.layout.iter_visible_items():
            if item.layer_id:

                # draw layer background
                layer_index = layer_ids.index(item.layer_id)
                parent = item.parent
                if parent and \
                   layer_index != 0:
                    rect = parent.get_canvas_rect()
                    context.rectangle(*rect.inflate(1))
                    rgba = self.color_scheme.get_layer_fill_rgba(layer_index)
                    context.set_source_rgba(*rgba)
                    context.fill()

            # draw key
            if item.is_key() and \
               clip_rect.intersects(item.get_canvas_rect()):
                item.draw(context)
                item.draw_image(context)
                item.draw_font(context)

        return True

    def draw_background(self, context):
        """ Draw keyboard background """
        win = self.get_kbd_window()

        if config.xid_mode:
            # xembed mode
            # Disable transparency in lightdm and g-s-s for now.
            # There are too many issues and there is no real
            # visual improvement.
            if False and \
               win.supports_alpha:
                self.clear_background(context)
                self.draw_transparent_background(context, decorated = True)
            else:
                self.draw_plain_background(context)

        elif config.has_window_decoration():
            # decorated window
            if win.supports_alpha and \
               config.transparent_background:
                self.clear_background(context)
            else:
                self.draw_plain_background(context)

        else:
            # undecorated window
            if win.supports_alpha:
                self.clear_background(context)
                if not config.transparent_background:
                    self.draw_transparent_background(context, decorated = True)
            else:
                self.draw_plain_background(context)

    def clear_background(self, context):
        """
        Clear the whole gtk background.
        Makes the whole strut transparent in xembed mode.
        """
        context.save()
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.paint()
        context.restore()

    def draw_transparent_background(self, context, decorated = True):
        """ fill with layer 0 color + background_transparency """
        layer0_rgba = self.color_scheme.get_layer_fill_rgba(0)
        background_alpha = 1.0 - config.background_transparency / 100.0
        rgba = layer0_rgba[:3] + [background_alpha]
        context.set_source_rgba(*rgba)

        # draw on the potentially aspect-corrected frame around the layout
        rect = self.layout.get_canvas_border_rect()
        rect = rect.inflate(config.get_frame_width())
        corner_radius = 10

        if decorated:
            roundrect_arc(context, rect, corner_radius)
        else:
            context.rectangle(*rect)
        #context.fill_preserve()
        context.fill()

        if decorated:
            # outer decorated line
            #context.set_source_rgba(*layer0_rgba)
            #context.stroke()

            # inner decorated line
            rect = rect.deflate(1)
            if decorated:
                roundrect_arc(context, rect, corner_radius)
            else:
                context.rectangle(*rect)
            context.stroke()


    def draw_plain_background(self, context):
        """ fill with plain layer 0 color; no alpha support required """
        rgba = self.color_scheme.get_layer_fill_rgba(0)
        context.set_source_rgba(*rgba)
        context.paint()

    def _on_mods_changed(self):
        _logger.info("Modifiers have been changed")
        self.update_font_sizes()

    def redraw(self, key = None):
        """
        Queue redrawing for a just a single key or the whold keyboard.
        """
        if key:
            rect = key.get_border_rect()
            rect = rect.inflate(2.0) # account for stroke width, anti-aliasing
            rect = key.context.log_to_canvas_rect(rect)
            self.queue_draw_area(*rect)
        else:
            self.queue_draw()


    def update_font_sizes(self):
        """
        Cycles through each group of keys and set each key's
        label font size to the maximum possible for that group.
        """
        context = self.create_pango_context()
        for keys in self.layout.get_key_groups().values():

            max_size = 0
            for key in keys:
                key.configure_label(self.mods)
                best_size = key.get_best_font_size(context)
                if best_size:
                    if not max_size or best_size < max_size:
                        max_size = best_size

            for key in keys:
                key.font_size = max_size

    def emit_quit_onboard(self, data=None):
        _logger.debug("Entered emit_quit_onboard")
        self.get_kbd_window().emit("quit-onboard")

    def get_kbd_window(self):
        return self.get_parent()

