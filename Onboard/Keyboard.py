# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import sys
import gc

from gi.repository import GObject, Gtk, Gdk

from Onboard.KeyGtk       import *
from Onboard              import KeyCommon
from Onboard.KeyCommon    import StickyBehavior
from Onboard.MouseControl import MouseController
from Onboard.Scanner      import Scanner
from Onboard.utils        import Timer

try:
    from Onboard.utils import run_script, get_keysym_from_name, dictproperty
except DeprecationWarning:
    pass

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

### Logging ###
import logging
_logger = logging.getLogger("Keyboard")
###############


# enum of event types for key press/release
class EventType:
    class CLICK: pass
    class DOUBLE_CLICK: pass
    class DWELL: pass


class UnpressTimer(Timer):
    """ Redraw key unpressed after a short while """

    def __init__(self, keyboard):
        self._keyboard = keyboard
        self._key = None

    def start(self, key):
        self._key = key
        Timer.start(self, 0.08)

    def reset(self):
        Timer.stop(self)
        self.draw_unpressed()

    def on_timer(self):
        self.draw_unpressed()
        return False

    def draw_unpressed(self):
        if self._key:
            self._key.pressed = False
            self._keyboard.redraw([self._key])
            self._key = None


class Keyboard:
    """ Cairo based keyboard widget """

    color_scheme = None
    alt_locked = False
    layer_locked = False

### Properties ###

    # The number of pressed keys per modifier
    _mods = {1:0,2:0, 4:0,8:0, 16:0,32:0,64:0,128:0}
    def _get_mod(self, key):
        return self._mods[key]
    def _set_mod(self, key, value):
        self._mods[key] = value
        self._on_mods_changed()
    mods = dictproperty(_get_mod, _set_mod)

    # currently active layer
    def _get_active_layer_index(self):
        return config.active_layer_index
    def _set_active_layer_index(self, index):
        config.active_layer_index = index
    active_layer_index = property(_get_active_layer_index,
                                  _set_active_layer_index)

    def _get_active_layer(self):
        layers = self.get_layers()
        if not layers:
            return None
        index = self.active_layer_index
        if index < 0 or index >= len(layers):
            index = 0
        return layers[index]
    def _set_active_layer(self, layer):
        index = 0
        for i, layer in enumerate(self.get_layers()):
            if layer is layer:
                index = i
                break
        self.active_layer_index = index
    active_layer = property(_get_active_layer, _set_active_layer)

    def assure_valid_active_layer(self):
        """
        Reset layer index if it is out of range. e.g. due to
        loading a layout with fewer panes.
        """
        index = self.active_layer_index
        if index < 0 or index >= len(self.get_layers()):
            self.active_layer_index = 0

##################

    def __init__(self):
        self.layout = None
        self.scanner = None
        self.vk = None
        self.button_controllers = {}
        self.canvas_rect = Rect()

        self._unpress_timer = UnpressTimer(self)
        self._editing_snippet = False

        self.reset()

    def reset(self):
        #List of keys which have been latched.
        #ie. pressed until next non sticky button is pressed.
        self._latched_sticky_keys = []
        self._locked_sticky_keys = []

    def initial_update(self):
        """ called when the layout has been loaded """
        self.reset()

        self._connect_button_controllers()
        self.assure_valid_active_layer()
        self.update_ui()

    def _connect_button_controllers(self):
        """ connect button controllers to button keys """
        self.button_controllers = {}
        types = [BCMiddleClick, BCSingleClick, BCSecondaryClick, BCDoubleClick, BCDragClick,
                 BCHoverClick,
                 BCHide, BCShowClick, BCMove, BCPreferences, BCQuit,
                ]
        for key in self.layout.iter_keys():
            if key.is_layer_button():
                bc = BCLayer(self, key)
                bc.layer_index = key.get_layer_index()
                self.button_controllers[key] = bc
            else:
                for type in types:
                    if type.id == key.id:
                        self.button_controllers[key] = type(self, key)

    def enable_scanner(self, enable):
        """ Config callback for scanner.enabled changes. """
        if enable:
            self.scanner = Scanner(self._on_scanner_redraw,
                                   self._on_scanner_activate)
            if self.layout:
                self.scanner.update_layer(self.layout, self.active_layer)
            else:
                _logger.warning("Failed to update scanner. No layout.")
        else:
            if self.scanner:
                self.scanner.finalize()
                self.scanner = None

    def _on_scanner_enabled(self, enabled):
        """ Config callback for scanner.enabled changes. """
        self.enable_scanner(enabled)
        self.update_transparency()

    def _on_scanner_redraw(self, keys):
        """ Scanner callback for redraws. """
        self.redraw(keys)

    def _on_scanner_activate(self, key):
        """ Scanner callback for key activation. """
        self.key_down(key)
        self.key_up(key)

    def get_layers(self):
        if self.layout:
            return self.layout.get_layer_ids()
        return []

    def iter_keys(self, group_name=None):
        """ iterate through all keys or all keys of a group """
        if self.layout:
            return self.layout.iter_keys(group_name)
        else:
            return []

    def utf8_to_unicode(self, utf8Char):
        return ord(utf8Char.decode('utf-8'))

    def get_key_at_location(self, point):
        if self.layout:  # may be gone on exit
            return self.layout.get_key_at(point, self.active_layer)
        return None

    def cb_macroEntry_activate(self,widget,macroNo,dialog):
        self.set_new_macro(macroNo, gtk.RESPONSE_OK, widget, dialog)

    def set_new_macro(self,macroNo,response,macroEntry,dialog):
        if response == gtk.RESPONSE_OK:
            config.set_snippet(macroNo, macroEntry.get_text())

        dialog.destroy()

    def _on_mods_changed(self):
        raise NotImplementedError()

    def key_down(self, key, button = 1, event_type = EventType.CLICK):
        """ Press down on one of Onboard's key representations. """
        # Stop garbage collection delays until key release. They might cause
        # unexpected key repeats on slow systems.
        gc.disable()

        #self._press_time = time.time()
        if key.sensitive:
            # visually unpress the previous key
            self._unpress_timer.reset()

            key.pressed = True

            if not key.active:
                if self.mods[8]:
                    self.alt_locked = True
                    self.vk.lock_mod(8)

            if (not key.sticky or not key.active) and \
               key.action != KeyCommon.DELAYED_STROKE_ACTION:
                # press key
                self.send_key_down(key, button, event_type)

                # Modifier keys may change multiple keys -> redraw everything
                if key.is_modifier():
                    self.invalidate_keys()
                    self.redraw()

            self.redraw([key])

    def key_up(self, key, button = 1, event_type = EventType.CLICK):
        """ Release one of Onboard's key representations. """
        #duration = time.time() - self._press_time
        #print("key press duration {}ms".format(int(duration * 1000)))

        update = False

        if key.sensitive:

            # Was the key nothing but pressed before?
            extend_pressed_state = key.is_pressed_only()

            if key.sticky:
                self.step_sticky_key(key, button, event_type)
            else:
                update = self.release_non_sticky_key(key, button, event_type)

            # Skip updates for the common letter press to improve
            # responsiveness on slow systems.
            if update or \
               key.type == KeyCommon.BUTTON_TYPE:
                self.update_controllers()
                self.update_layout()

            # Is the key still nothing but pressed?
            extend_pressed_state = extend_pressed_state and key.is_pressed_only()

            # Draw key unpressed to remove the visual feedback.
            if extend_pressed_state and \
               not config.scanner.enabled:
                # Keep key pressed for a little longer for clear user feedback.
                self._unpress_timer.start(key)
            else:
                # Unpress now to avoid flickering of the
                # pressed color after key release.
                key.pressed = False
                self.redraw([key])

        gc.enable()

    def send_key_down(self, key, button, event_type):
        key_type = key.type
        modifier = key.modifier

        if key.action != KeyCommon.DELAYED_STROKE_ACTION:
            self.send_key_press(key, button, event_type)
        if key.action == KeyCommon.DOUBLE_STROKE_ACTION:
            self.send_key_release(key, button, event_type)

        if key_type == KeyCommon.LEGACY_MODIFIER_TYPE:
            # Modifier from legacy layout without key code?
            # Alt is special because is activates the window managers move mode.
            if modifier != 8: # not Alt?
                self.vk.lock_mod(modifier)

        if modifier:
            self.mods[modifier] += 1

    def send_key_up(self,key, button = 1, event_type = EventType.CLICK):
        key_type = key.type
        modifier = key.modifier

        if key.action == KeyCommon.DOUBLE_STROKE_ACTION or \
           key.action == KeyCommon.DELAYED_STROKE_ACTION:
            self.send_key_press(key, button, event_type)
        self.send_key_release(key)

        if key_type == KeyCommon.LEGACY_MODIFIER_TYPE:
            # Modifier from legacy layout without key code?
            # Alt is special because is activates the window managers move mode.
            if modifier != 8: # not Alt?
                self.vk.unlock_mod(modifier)

        if modifier:
            self.mods[modifier] -= 1

        if self.alt_locked:
            self.alt_locked = False
            self.vk.unlock_mod(8)

    def send_key_press(self, key, button, event_type):
        """ Actually generate a fake key press """
        key_type = key.type

        if key_type == KeyCommon.CHAR_TYPE:
            if sys.version_info.major == 2:
                char = self.utf8_to_unicode(char)
            else:
                char = ord(key.code)
            self.vk.press_unicode(char)

        elif key_type == KeyCommon.KEYSYM_TYPE:
            self.vk.press_keysym(key.code)
        elif key_type == KeyCommon.KEYPRESS_NAME_TYPE:
            self.vk.press_keysym(get_keysym_from_name(key.code))
        elif key_type == KeyCommon.MACRO_TYPE:
            snippet_id = int(key.code)
            mlabel, mString = config.snippets.get(snippet_id, (None, None))
            if mString:
                self.press_key_string(mString)

            # Block dialog in xembed mode.
            # Don't allow to open multiple dialogs in force-to-top mode.
            elif not config.xid_mode and \
                not self._editing_snippet:
                self.edit_snippet(snippet_id)
                self._editing_snippet = True

        elif key_type == KeyCommon.KEYCODE_TYPE:
            self.vk.press_keycode(key.code)

        elif key_type == KeyCommon.SCRIPT_TYPE:
            if not config.xid_mode:  # block settings dialog in xembed mode
                if key.code:
                    run_script(key.code)

        elif key_type == KeyCommon.BUTTON_TYPE:
            controller = self.button_controllers.get(key)
            if controller:
                controller.press(button, event_type)

    def send_key_release(self, key, button = 1, event_type = EventType.CLICK):
        """ Actually generate a fake key release """
        key_type = key.type
        if key_type == KeyCommon.CHAR_TYPE:
            if sys.version_info.major == 2:
                char = self.utf8_to_unicode(char)
            else:
                char = ord(key.code)
            self.vk.release_unicode(char)
        elif key_type == KeyCommon.KEYSYM_TYPE:
            self.vk.release_keysym(key.code)
        elif key_type == KeyCommon.KEYPRESS_NAME_TYPE:
            self.vk.release_keysym(get_keysym_from_name(key.code))
        elif key_type == KeyCommon.KEYCODE_TYPE:
            self.vk.release_keycode(key.code);
        if key_type == KeyCommon.MACRO_TYPE:
            pass
        elif key_type == KeyCommon.SCRIPT_TYPE:
            pass
        elif key_type == KeyCommon.BUTTON_TYPE:
            controller = self.button_controllers.get(key)
            if controller:
                controller.release(button, event_type)

    def press_key_string(self, keystr):
        """
        Send key presses for all characters in a unicode string
        and keep track of the changes in input_line.
        """
        capitalize = False

        keystr = keystr.replace("\\n", "\n")

        if self.vk:   # may be None in the last call before exiting
            for ch in keystr:
                if ch == "\b":   # backspace?
                    keysym = get_keysym_from_name("backspace")
                    self.vk.press_keysym  (keysym)
                    self.vk.release_keysym(keysym)

                elif ch == "\x0e":  # set to upper case at sentence begin?
                    capitalize = True

                elif ch == "\n":
                    # press_unicode("\n") fails in gedit.
                    # -> explicitely send the key symbol instead
                    keysym = get_keysym_from_name("return")
                    self.vk.press_keysym  (keysym)
                    self.vk.release_keysym(keysym)
                else:             # any other printable keys
                    self.vk.press_unicode(ord(ch))
                    self.vk.release_unicode(ord(ch))

        return capitalize

    def release_non_sticky_key(self, key, button, event_type):
        needs_layout_update = False

        # release key
        self.send_key_up(key, button, event_type)

        # Don't release latched modifiers for click buttons right now.
        # Keep modifier keys unchanged until the actual click happens
        # -> allow clicks with modifiers
        if not key.is_layer_button() and \
           not (key.type == KeyCommon.BUTTON_TYPE and \
            key.id in ["middleclick", "secondaryclick"]):
            # release latched modifiers
            self.release_latched_sticky_keys()

        # switch to layer 0 on (almost) any key release
        if not key.is_layer_button() and \
           not key.id in ["move", "showclick"] and \
           not self._editing_snippet:
            if self.active_layer_index != 0 and not self.layer_locked:
                self.active_layer_index = 0
                needs_layout_update = True
                self.redraw()

        return needs_layout_update

    def step_sticky_key(self, key, button, event_type):
        """
        One cycle step when pressing a sticky (latchabe/lockable)
        modifier key (all sticky keys except layer buttons).
        """
        active, locked = self.step_sticky_key_state(key,
                                                     key.active, key.locked,
                                                     button, event_type)
        # apply the new states
        was_active = key.active
        key.active = active
        key.locked = locked
        if active:
            if locked:
                if key in self._latched_sticky_keys:
                    self._latched_sticky_keys.remove(key)
                if not key in self._locked_sticky_keys:
                    self._locked_sticky_keys.append(key)
            else:
                if not key in self._latched_sticky_keys:
                    self._latched_sticky_keys.append(key)
                if key in self._locked_sticky_keys:
                    self._locked_sticky_keys.remove(key)
        else:
            if key in self._latched_sticky_keys:
                self._latched_sticky_keys.remove(key)
            if key in self._locked_sticky_keys:
                self._locked_sticky_keys.remove(key)

            if was_active:
                self.send_key_up(key)
                if key.is_modifier():
                    self.invalidate_keys()
                    self.redraw()   # redraw the whole keyboard

    def step_sticky_key_state(self, key, active, locked, button, event_type):
        """ One cycle step when pressing a sticky (latchabe/lockable) key """

        # double click usable?
        if event_type == EventType.DOUBLE_CLICK and \
           self._can_lock_on_double_click(key, event_type):

            # any state -> locked
            active = True
            locked = True

        # single click or unused double click
        else:
            # off -> latched or locked
            if not active:

                if self._can_latch(key):
                    active = True

                elif self._can_lock(key, event_type):
                    active = True
                    locked = True

            # latched -> locked
            elif not key.locked and \
                 self._can_lock(key, event_type):
                locked = True

            # latched or locked -> off
            else:
                active = False
                locked = False

        return active, locked

    def _can_latch(self, key):
        """
        Can sticky key enter latched state?
        Latched keys are automatically released when a
        non-sticky key is pressed.
        """
        behavior = self._get_sticky_key_behavior(key)
        return behavior in [StickyBehavior.CYCLE,
                            StickyBehavior.DOUBLE_CLICK,
                            StickyBehavior.LATCH_ONLY]

    def _can_lock(self, key, event_type):
        """
        Can sticky key enter locked state?
        Locked keys stay active until they are pressed again.
        """
        behavior = self._get_sticky_key_behavior(key)
        return behavior == StickyBehavior.CYCLE or \
               behavior == StickyBehavior.LOCK_ONLY or \
               behavior == StickyBehavior.DOUBLE_CLICK and \
               event_type == EventType.DOUBLE_CLICK

    def _can_lock_on_double_click(self, key, event_type):
        """
        Can sticky key enter locked state on double click?
        Locked keys stay active until they are pressed again.
        """
        behavior = self._get_sticky_key_behavior(key)
        return behavior == StickyBehavior.DOUBLE_CLICK and \
               event_type == EventType.DOUBLE_CLICK

    def _get_sticky_key_behavior(self, key):
        """ Return sticky behavior for the given key """
        # try the individual key id
        behavior = self._get_sticky_behavior_for(key.id)

        # default to the layout's behavior
        # CAPS was hard-coded here to LOCK_ONLY until v0.98.
        if behavior is None and \
           not key.sticky_behavior is None:
            behavior = key.sticky_behavior

        # try the key group
        if behavior is None:
            if key.is_modifier():
                behavior = self._get_sticky_behavior_for("modifiers")
            if key.is_layer_button():
                behavior = self._get_sticky_behavior_for("layers")

        # try the 'all' group
        if behavior is None:
            behavior = self._get_sticky_behavior_for("all")

        # else fall back to hard coded default
        if not StickyBehavior.is_valid(behavior):
            behavior = StickyBehavior.CYCLE

        return behavior

    def _get_sticky_behavior_for(self, group):
        behavior = None
        value = config.keyboard.sticky_key_behavior.get(group)
        if value:
            try:
                behavior = StickyBehavior.from_string(value)
            except KeyError:
                _logger.warning("Invalid sticky behavior '{}' for key '{}'" \
                              .format(value, key.id))
        return behavior

    def has_latched_sticky_keys(self, except_keys = None):
        """ any sticky keys latched? """
        return len(self._latched_sticky_keys) > 0

    def release_latched_sticky_keys(self, except_keys = None):
        """ release latched sticky (modifier) keys """
        if len(self._latched_sticky_keys) > 0:
            for key in self._latched_sticky_keys[:]:
                if not except_keys or not key in except_keys:
                    self.send_key_up(key)
                    self._latched_sticky_keys.remove(key)
                    key.active = False

            # modifiers may change many key labels -> redraw everything
            self.invalidate_keys()
            self.redraw()

    def release_locked_sticky_keys(self):
        """ release locked sticky (modifier) keys """
        if len(self._locked_sticky_keys) > 0:
            for key in self._locked_sticky_keys[:]:
                self.send_key_up(key)
                self._locked_sticky_keys.remove(key)
                key.active = False
                key.locked = False
                key.pressed = False

            # modifiers may change many key labels -> redraw everything
            self.invalidate_keys()
            self.redraw()

    def update_ui(self):
        """
        Force update of everything.
        Relatively expensive, don't call this while typing.
        """
        self.update_controllers()
        self.update_layout()
        self.update_font_sizes()
        self.invalidate_keys()
        self.invalidate_shadows()

    def update_controllers(self):
        # update buttons
        for controller in list(self.button_controllers.values()):
            controller.update()

    def update_layout(self):
        layout = self.layout
        if not layout:
            return

        # show/hide layers
        layers = layout.get_layer_ids()
        if layers:
            layout.set_visible_layers([layers[0], self.active_layer])

        # notify the scanner about layer changes
        if self.scanner:
            self.scanner.update_layer(layout, self.active_layer)

        # recalculate items rectangles
        self.canvas_rect = Rect(0, 0,
                                self.get_allocated_width(),
                                self.get_allocated_height())
        rect = self.canvas_rect.deflate(config.get_frame_width())
        #keep_aspect = config.xid_mode and self.supports_alpha()
        keep_aspect = False
        layout.fit_inside_canvas(rect, keep_aspect)

        # Give toolkit dependent keyboardGTK a chance to
        # update the aspect ratio of the main window
        self.on_layout_updated()

    def on_outside_click(self):
        """
        Called by outside click polling.
        Keep this as Francesco likes to have modifiers
        reset when clicking outside of onboard.
        """
        self.release_latched_sticky_keys()

    def on_cancel_outside_click(self):
        """ Called when outside click polling times out. """
        pass

    def get_mouse_controller(self):
        if config.mousetweaks and \
           config.mousetweaks.is_active():
            return config.mousetweaks
        return config.clickmapper

    def cleanup(self):
        # reset still latched and locked modifier keys on exit
        self.release_latched_sticky_keys()
        self.release_locked_sticky_keys()
        self._unpress_timer.stop()

        for key in self.iter_keys():
            if key.pressed and key.type in \
                [KeyCommon.CHAR_TYPE,
                 KeyCommon.KEYSYM_TYPE,
                 KeyCommon.KEYPRESS_NAME_TYPE,
                 KeyCommon.KEYCODE_TYPE]:

                # Release still pressed enter key when onboard gets killed
                # on enter key press.
                _logger.debug("Releasing still pressed key '{}'" \
                              .format(key.id))
                self.send_key_up(key)

        # Somehow keyboard objects don't get released
        # when switching layouts, there are still
        # excess references/memory leaks somewhere.
        # We need to manually release virtkey references or
        # Xlib runs out of client connections after a couple
        # dozen layout switches.
        self.vk = None
        self.layout = None  # free the memory

    def find_keys_from_ids(self, key_ids):
        if self.layout is None:
            return []
        return self.layout.find_ids(key_ids)

    def edit_snippet(self, snippet_id):
        dialog = Gtk.Dialog(_("New snippet"),
                            self.get_toplevel(), 0,
                            (Gtk.STOCK_CANCEL,
                             Gtk.ResponseType.CANCEL,
                             _("_Save snippet"),
                             Gtk.ResponseType.OK))

        # Don't hide dialog behind the keyboard in force-to-top mode.
        if config.window.force_to_top:
            dialog.set_position(Gtk.WindowPosition.NONE)

        dialog.set_default_response(Gtk.ResponseType.OK)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      spacing=12, border_width=5)
        dialog.get_content_area().add(box)

        msg = Gtk.Label(_("Enter a new snippet for this button:"),
                        xalign=0.0)
        box.add(msg)

        label_entry = Gtk.Entry(hexpand=True)
        text_entry  = Gtk.Entry(hexpand=True)
        label_label = Gtk.Label(_("_Button label:"),
                                xalign=0.0,
                                use_underline=True,
                                mnemonic_widget=label_entry)
        text_label  = Gtk.Label(_("S_nippet:"),
                                xalign=0.0,
                                use_underline=True,
                                mnemonic_widget=text_entry)

        grid = Gtk.Grid(row_spacing=6, column_spacing=3)
        grid.attach(label_label, 0, 0, 1, 1)
        grid.attach(text_label, 0, 1, 1, 1)
        grid.attach(label_entry, 1, 0, 1, 1)
        grid.attach(text_entry, 1, 1, 1, 1)
        box.add(grid)

        dialog.connect("response", self.cb_dialog_response, \
                       snippet_id, label_entry, text_entry)
        label_entry.grab_focus()
        dialog.show_all()

    def cb_dialog_response(self, dialog, response, snippet_id, \
                           label_entry, text_entry):
        if response == Gtk.ResponseType.OK:
            label = label_entry.get_text()
            text = text_entry.get_text()

            if sys.version_info.major == 2:
                label = label.decode("utf-8")
                text = text.decode("utf-8")

            config.set_snippet(snippet_id, (label, text))
        dialog.destroy()
        self._editing_snippet = False


class ButtonController(object):
    """
    MVC inspired controller that handles events and the resulting
    state changes of buttons.
    """
    def __init__(self, keyboard, key):
        self.keyboard = keyboard
        self.key = key

    def press(self, button, event_type):
        """ button pressed """
        pass

    def long_press(self, button):
        """ button pressed long """
        pass

    def release(self, button, event_type):
        """ button released """
        pass

    def update(self):
        """ asynchronous ui update """
        pass

    def can_dwell(self):
        """ can start dwelling? """
        return False

    def can_long_press(self):
        """ can start long press? """
        return False

    def set_visible(self, visible):
        if self.key.visible != visible:
            self.key.visible = visible
            self.keyboard.redraw([self.key])

    def set_sensitive(self, sensitive):
        if self.key.sensitive != sensitive:
            self.key.sensitive = sensitive
            self.keyboard.redraw([self.key])

    def set_active(self, active = None):
        if not active is None and self.key.active != active:
            self.key.active = active
            self.keyboard.redraw([self.key])

    def set_locked(self, locked = None):
        if not locked is None and self.key.locked != locked:
            self.key.active = locked
            self.key.locked = locked
            self.keyboard.redraw([self.key])


class BCClick(ButtonController):
    """ Controller for click buttons """
    def release(self, button, event_type):
        mc = self.keyboard.get_mouse_controller()
        if self.is_active():
            # stop click mapping, resets to primary button and single click
            mc.set_click_params(MouseController.PRIMARY_BUTTON,
                                MouseController.CLICK_TYPE_SINGLE)
        else:
            # Exclude click type buttons from the click mapping
            # to be able to reliably cancel the click.
            # -> They will receive only single left clicks.
            rects = self.keyboard.get_click_type_button_rects()
            config.clickmapper.set_exclusion_rects(rects)

            # start the click mapping
            mc.set_click_params(self.button, self.click_type)

    def update(self):
        mc = self.keyboard.get_mouse_controller()
        self.set_active(self.is_active())
        self.set_sensitive(
            mc.supports_click_params(self.button, self.click_type))

    def is_active(self):
        mc = self.keyboard.get_mouse_controller()
        return mc.get_click_button() == self.button and \
               mc.get_click_type() == self.click_type

class BCSingleClick(BCClick):
    id = "singleclick"
    button = MouseController.PRIMARY_BUTTON
    click_type = MouseController.CLICK_TYPE_SINGLE

class BCMiddleClick(BCClick):
    id = "middleclick"
    button = MouseController.MIDDLE_BUTTON
    click_type = MouseController.CLICK_TYPE_SINGLE

class BCSecondaryClick(BCClick):
    id = "secondaryclick"
    button = MouseController.SECONDARY_BUTTON
    click_type = MouseController.CLICK_TYPE_SINGLE

class BCDoubleClick(BCClick):
    id = "doubleclick"
    button = MouseController.PRIMARY_BUTTON
    click_type = MouseController.CLICK_TYPE_DOUBLE

class BCDragClick(BCClick):
    id = "dragclick"
    button = MouseController.PRIMARY_BUTTON
    click_type = MouseController.CLICK_TYPE_DRAG

    def release(self, button, event_type):
        BCClick. release(self, button, event_type)
        self.keyboard.show_touch_handles(show = self.can_show_handles(),
                                         auto_hide = False)

    def update(self):
        active = self.key.active
        BCClick.update(self)

        if active and not self.key.active:
            # hide the touch handles
            self.keyboard.show_touch_handles(self.can_show_handles())

    def can_show_handles(self):
        return self.is_active() and \
               config.mousetweaks and config.mousetweaks.is_active() and \
               not config.xid_mode

class BCHoverClick(ButtonController):

    id = "hoverclick"

    def release(self, button, event_type):
        config.enable_hover_click(not config.mousetweaks.is_active())

    def update(self):
        available = bool(config.mousetweaks)
        active    = config.mousetweaks.is_active() \
                    if available else False

        self.set_sensitive(available and \
                           not config.lockdown.disable_hover_click)
        # force locked color for better visibility
        self.set_locked(active)
        #self.set_active(config.mousetweaks.is_active())

    def can_dwell(self):
        return not (config.mousetweaks and config.mousetweaks.is_active())


class BCHide(ButtonController):

    id = "hide"

    def release(self, button, event_type):
        self.keyboard.set_visible(False)

    def update(self):
        self.set_sensitive(not config.xid_mode) # insensitive in XEmbed mode


class BCShowClick(ButtonController):

    id = "showclick"

    def release(self, button, event_type):
        config.keyboard.show_click_buttons = not config.keyboard.show_click_buttons

        # enable hover click when the key was dwell-activated
        # disabled for now, seems too confusing
        if False:
            if event_type == EventType.DWELL and \
               config.keyboard.show_click_buttons and \
               not config.mousetweaks.is_active():
                config.enable_hover_click(True)

    def update(self):
        allowed = not config.lockdown.disable_click_buttons

        self.set_visible(allowed)

        # Don't show active state. Toggling the click column
        # should be enough feedback.
        #self.set_active(config.keyboard.show_click_buttons)

        # show/hide click buttons
        show_click = config.keyboard.show_click_buttons and allowed
        layout = self.keyboard.layout
        if layout:
            for item in layout.iter_items():
                if item.group == 'click':
                    item.visible = show_click
                elif item.group == 'noclick':
                    item.visible = not show_click

    def can_dwell(self):
        return not config.mousetweaks or not config.mousetweaks.is_active()


class BCMove(ButtonController):

    id = "move"

    def press(self, button, event_type):
        self.keyboard.start_move_window()

    def long_press(self, button):
        self.keyboard.show_touch_handles(True)

    def release(self, button, event_type):
        self.keyboard.stop_move_window()

    def update(self):
        self.set_visible(not config.has_window_decoration() and \
                         not config.xid_mode)

    def can_long_press(self):
        return not config.xid_mode


class BCLayer(ButtonController):
    """ layer switch button, switches to layer <layer_index> when released """

    layer_index = None

    def _get_id(self):
        return "layer" + str(self.layer_index)
    id = property(_get_id)

    def release(self, button, event_type):
        keyboard = self.keyboard

        active_before = keyboard.active_layer_index == self.layer_index
        locked_before = active_before and keyboard.layer_locked

        active, locked = keyboard.step_sticky_key_state(
                                       self.key,
                                       active_before, locked_before,
                                       button, event_type)

        keyboard.active_layer_index = self.layer_index \
                                      if active else 0

        keyboard.layer_locked       = locked \
                                      if self.layer_index else False

        if active_before != active:
            keyboard.redraw()

    def update(self):
        # don't show active state for layer 0, it'd be visible all the time
        active = self.key.get_layer_index() != 0 and \
                 self.key.get_layer_index() == self.keyboard.active_layer_index
        self.set_active(active)
        self.set_locked(active and self.keyboard.layer_locked)


class BCPreferences(ButtonController):

    id = "settings"

    def release(self, button, event_type):
        run_script("sokSettings")

    def update(self):
        self.set_visible(not config.xid_mode and \
                         not config.running_under_gdm and \
                         not config.lockdown.disable_preferences)


class BCQuit(ButtonController):

    id = "quit"

    def release(self, button, event_type):
        self.keyboard.emit_quit_onboard()

    def update(self):
        self.set_visible(not config.xid_mode and \
                         not config.lockdown.disable_quit)

