# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import sys
import gc

from gi.repository import GObject, Gtk, Gdk, Atspi

from Onboard.KeyGtk       import *
from Onboard              import KeyCommon
from Onboard.KeyCommon    import StickyBehavior
from Onboard.MouseControl import MouseController
from Onboard.Scanner      import Scanner
from Onboard.utils        import Timer, Modifiers
from Onboard.canonical_equivalents import *

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
    (
        CLICK,
        DOUBLE_CLICK,
        DWELL,
    ) = range(3)

# enum dock mode
class DockMode:
    (
        FLOATING,
        BOTTOM,
        TOP,
    ) = range(3)


class UnpressTimers:
    """ Redraw keys unpressed after a short while. """

    def __init__(self, keyboard):
        self._keyboard = keyboard
        self._timers = {}

    def start(self, key):
        timer = self._timers.get(key)
        if not timer:
            timer = Timer()
            self._timers[key] = timer
        timer.start(config.UNPRESS_DELAY, self.on_timer, key)

    def stop(self, key):
        timer = self._timers.get(key)
        if timer:
            timer.stop()
            del self._timers[key]

    def stop_all(self):
        for timer in self._timers.values():
            Timer.stop(timer)
        self._timers = {}

    def reset(self, key):
        timer = self._timers.get(key)
        if timer:
            timer.stop()
            self.unpress(key)

    def on_timer(self, key):
        self.unpress(key)
        self.stop(key)
        return False

    def unpress(self, key):
        if key.pressed:
            key.pressed = False
            self._keyboard.redraw([key])


class KeySynthVirtkey:
    """ Synthesize key strokes with python-virtkey """

    def __init__(self, vk):
        self._vk = vk

    def cleanup(self):
        self._vk = None

    def press_unicode(self, char):
        if sys.version_info.major == 2:
            code_point = self.utf8_to_unicode(char)
        else:
            code_point = ord(char)
        self._vk.press_unicode(code_point)

    def release_unicode(self, char):
        if sys.version_info.major == 2:
            code_point = self.utf8_to_unicode(char)
        else:
            code_point = ord(char)
        self._vk.release_unicode(code_point)

    def press_keysym(self, keysym):
        self._vk.press_keysym(keysym)

    def release_keysym(self, keysym):
        self._vk.release_keysym(keysym)

    def press_keycode(self, keycode):
        self._vk.press_keycode(keycode)

    def release_keycode(self, keycode):
        self._vk.release_keycode(keycode)

    def lock_mod(self, mod):
        self._vk.lock_mod(mod)

    def unlock_mod(self, mod):
        self._vk.unlock_mod(mod)

    def press_key_string(self, keystr):
        """
        Send key presses for all characters in a unicode string
        and keep track of the changes in input_line.
        """
        capitalize = False

        keystr = keystr.replace("\\n", "\n")

        if self._vk:   # may be None in the last call before exiting
            for ch in keystr:
                if ch == "\b":   # backspace?
                    keysym = get_keysym_from_name("backspace")
                    self.press_keysym  (keysym)
                    self.release_keysym(keysym)

                elif ch == "\x0e":  # set to upper case at sentence begin?
                    capitalize = True

                elif ch == "\n":
                    # press_unicode("\n") fails in gedit.
                    # -> explicitely send the key symbol instead
                    keysym = get_keysym_from_name("return")
                    self.press_keysym  (keysym)
                    self.release_keysym(keysym)
                else:             # any other printable keys
                    self.press_unicode(ch)
                    self.release_unicode(ch)

        return capitalize


class KeySynthAtspi(KeySynthVirtkey):
    """ Synthesize key strokes with AT-SPI """

    def __init__(self, vk):
        super(KeySynthAtspi, self).__init__(vk)

    def press_key_string(self, string):
        #print("press_key_string")
        Atspi.generate_keyboard_event(0, string, Atspi.KeySynthType.STRING)

    def press_keysym(self, keysym):
        #print("press_keysym")
        Atspi.generate_keyboard_event(keysym, "", Atspi.KeySynthType.SYM |
                                                  Atspi.KeySynthType.PRESS)
    def release_keysym(self, keysym):
        #print("release_keysym")
        Atspi.generate_keyboard_event(keysym, "", Atspi.KeySynthType.SYM |
                                                  Atspi.KeySynthType.RELEASE)
    def press_keycode(self, keycode):
        #print("press_keycode")
        Atspi.generate_keyboard_event(keycode, "", Atspi.KeySynthType.PRESS)

    def release_keycode(self, keycode):
        #print("release_keycode")
        Atspi.generate_keyboard_event(keycode, "", Atspi.KeySynthType.RELEASE)


class Keyboard:
    """ Cairo based keyboard widget """

    color_scheme = None

    _layer_locked = False
    _last_alt_key = None
    _alt_locked = False
    _key_synth   = None

### Properties ###

    # The number of pressed keys per modifier
    _mods = {1:0,2:0, 4:0,8:0, 16:0,32:0,64:0,128:0}
    def _get_mod(self, key):
        return self._mods[key]
    def _set_mod(self, key, value):
        self._mods[key] = value
        self.on_mods_changed()
    mods = dictproperty(_get_mod, _set_mod)

    def on_mods_changed(self):
        pass

    def get_mod_mask(self):
        """ Bit-mask of curently active modifers. """
        return sum(mask for mask in (1<<bit for bit in range(8)) \
                   if self.mods[mask])  # bit mask of current modifiers

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
        self.editing_snippet = False

        self._layout_views = []

        self._unpress_timers = UnpressTimers(self)

        self._key_synth = None
        self._key_synth_virtkey = None
        self._key_synth_atspi = None

        self.reset()

    def reset(self):
        #List of keys which have been latched.
        #ie. pressed until next non sticky button is pressed.
        self._latched_sticky_keys = []
        self._locked_sticky_keys = []
        self._can_cycle_modifiers = True

    def register_view(self, layout_view):
        self._layout_views.append(layout_view)

    def deregister_view(self, layout_view):
        if layout_view in self._layout_views:
            self._layout_views.remove(layout_view)

    def redraw(self, keys = None, invalidate = True):
        for view in self._layout_views:
            view.redraw(keys, invalidate)

    def process_updates(self):
        for view in self._layout_views:
            view.process_updates()

    def redraw_labels(self, invalidate = True):
        for view in self._layout_views:
            view.redraw_labels(invalidate)

    def has_input_sequences(self):
        for view in self._layout_views:
            if view.has_input_sequences():
                return True
        return False

    def update_transparency(self):
        for view in self._layout_views:
            view.update_transparency()

    def show_touch_handles(self, show, auto_hide = True):
        for view in self._layout_views:
            view.show_touch_handles(show, auto_hide)

    def on_layout_loaded(self):
        """ called when the layout has been loaded """
        self.reset()

        self._connect_button_controllers()
        self.assure_valid_active_layer()

        # Update Onboard to show the initial modifiers
        keymap = Gdk.Keymap.get_default()
        if keymap:
            mod_mask = keymap.get_modifier_state()
            self.set_modifiers(mod_mask)

        self.update_ui()
        self.redraw()

    def init_key_synth(self, vk):
        self._key_synth_virtkey = KeySynthVirtkey(vk)
        self._key_synth_atspi = KeySynthAtspi(vk)

        if config.keyboard.key_synth: # == KeySynth.ATSPI:
            self._key_synth = self._key_synth_atspi
        else: # if config.keyboard.key_synth == KeySynth.VIRTKEY:
            self._key_synth = self._key_synth_virtkey

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

    def cb_macroEntry_activate(self,widget,macroNo,dialog):
        self.set_new_macro(macroNo, gtk.RESPONSE_OK, widget, dialog)

    def set_new_macro(self,macroNo,response,macroEntry,dialog):
        if response == gtk.RESPONSE_OK:
            config.set_snippet(macroNo, macroEntry.get_text())

        dialog.destroy()

    def key_down(self, key, view = None,
                 button = 1, event_type = EventType.CLICK):
        """ Press down on one of Onboard's key representations. """
        # Stop garbage collection delays until key release. They might cause
        # unexpected key repeats on slow systems.
        gc.disable()

        if key.sensitive:
            # visually unpress the previous key
            self._unpress_timers.reset(key)

            key.pressed = True

            if not key.active:
                if self.mods[8]:
                    self._alt_locked = True
                    if self._last_alt_key:
                        self.send_key_press(self._last_alt_key, None, button, event_type)
                    self._key_synth.lock_mod(8)

            action = self.get_key_action(key)
            can_send_key = (not key.sticky or not key.active) and \
                           action != KeyCommon.DELAYED_STROKE_ACTION

            # Get drawing behind us now, so it can't delay processing key_up()
            # and cause unwanted key repeats on slow systems.
            self.redraw([key])
            self.process_updates()

            if can_send_key:
                # press key
                self.send_key_down(key, view, button, event_type)

            # Modifier keys may change multiple keys
            # -> redraw all dependent keys
            # no danger of key repeats plus more work to do
            # -> redraw asynchronously
            if key.is_modifier():
                if can_send_key:
                    self.redraw_labels(False)
            else:
                # Multi-touch: temporarily stop cycling modifiers if
                # a non-modifier key was pressed. This way we get both,
                # cycling latched and locked state with single presses
                # and press-only action for multi-touch modifer + key press.
                self._can_cycle_modifiers = False

    def key_up(self, key, view = None, button = 1,
               event_type = EventType.CLICK, cancel_send_key = False):
        """ Release one of Onboard's key representations. """
        update = False

        if key.sensitive:

            # Was the key nothing but pressed before?
            extend_pressed_state = key.is_pressed_only()

            # not cancelled due to long press?
            if not cancel_send_key:
                if key.sticky:
                    # Multi-touch release?
                    if key.is_modifier() and \
                       not self._can_cycle_modifiers:
                        can_send_key = True
                    else: # single touch/click
                        can_send_key = self.step_sticky_key(key, button, event_type)

                    if can_send_key:
                        self.send_key_up(key, view)
                        if key.is_modifier():
                            self.redraw_labels(False)
                else:
                    update = self.release_non_sticky_key(key, view, button, event_type)

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
                self._unpress_timers.start(key)
            else:
                # Unpress now to avoid flickering of the
                # pressed color after key release.
                key.pressed = False
                self.redraw([key])

        # Was this the final touch sequence?
        if not self.has_input_sequences():
            self._can_cycle_modifiers = True
            gc.enable()

    def key_long_press(self, key, view = None, button = 1):
        """ Long press of one of Onboard's key representations. """
        long_pressed = False
        key_type = key.type

        if key_type == KeyCommon.BUTTON_TYPE:
            # Buttons decide for themselves what is to happen.
            controller = self.button_controllers.get(key)
            if controller:
                controller.long_press(view, button)
        else:
            # All other keys get hard-coded long press menus
            # (where available).
            action = self.get_key_action(key)
            if action == KeyCommon.DELAYED_STROKE_ACTION:
                label = key.get_label()
                alternatives = self.find_canonical_equivalents(label)
                if alternatives:
                    view.show_alternative_keys_popup(key, alternatives)
                long_pressed = True

        return long_pressed

    def find_canonical_equivalents(self, char):
        return canonical_equivalents.get(char)

    def send_key_down(self, key, view, button, event_type):
        key_type = key.type
        modifier = key.modifier

        if modifier == 8: # Alt
            self._last_alt_key = key
        else:
            action = self.get_key_action(key)
            if action != KeyCommon.DELAYED_STROKE_ACTION:
                self.send_key_press(key, view, button, event_type)
            if action == KeyCommon.DOUBLE_STROKE_ACTION:
                self.send_key_release(key, view, button, event_type)

        if modifier:
            # Increment this before lock_mod() to skip
            # updating keys a second time in set_modifiers().
            self.mods[modifier] += 1

            # Alt is special because is activates the window manager's move mode.
            if modifier != 8: # not Alt?
                self._key_synth.lock_mod(modifier)

    def send_key_up(self, key, view = None, button = 1, event_type = EventType.CLICK):
        key_type = key.type
        modifier = key.modifier

        if modifier == 8: # Alt
            pass
        else:
            action = self.get_key_action(key)
            if action == KeyCommon.DOUBLE_STROKE_ACTION or \
               action == KeyCommon.DELAYED_STROKE_ACTION:
                if key_type == KeyCommon.CHAR_TYPE:
                    # allow to use Atspi for char keys
                    self._key_synth.press_key_string(key.code)
                else:
                    self.send_key_press(key, view, button, event_type)
                    self.send_key_release(key, view, button, event_type)
            else:
                self.send_key_release(key, view, button, event_type)

        if modifier:
            # Decrement this before unlock_mod() to skip
            # updating keys a second time in set_modifiers().
            self.mods[modifier] -= 1

            # Alt is special because it activates the window managers move mode.
            if modifier != 8: # not Alt?
                self._key_synth.unlock_mod(modifier)

        if self._alt_locked:
            self._alt_locked = False
            if self._last_alt_key:
                self.send_key_release(self._last_alt_key, None, button, event_type)
            self._key_synth.unlock_mod(8)

    def send_key_press(self, key, view, button, event_type):
        """ Actually generate a fake key press """
        key_type = key.type

        if key_type == KeyCommon.CHAR_TYPE:
            self._key_synth.press_unicode(key.code)

        elif key_type == KeyCommon.KEYSYM_TYPE:
            self._key_synth.press_keysym(key.code)
        elif key_type == KeyCommon.KEYPRESS_NAME_TYPE:
            self._key_synth.press_keysym(get_keysym_from_name(key.code))
        elif key_type == KeyCommon.MACRO_TYPE:
            snippet_id = int(key.code)
            mlabel, mString = config.snippets.get(snippet_id, (None, None))
            if mString:
                self._key_synth.press_key_string(mString)

            # Block dialog in xembed mode.
            # Don't allow to open multiple dialogs in force-to-top mode.
            elif not config.xid_mode and \
                not self.editing_snippet:
                view.edit_snippet(snippet_id)
                self.editing_snippet = True

        elif key_type == KeyCommon.KEYCODE_TYPE:
            self._key_synth.press_keycode(key.code)

        elif key_type == KeyCommon.SCRIPT_TYPE:
            if not config.xid_mode:  # block settings dialog in xembed mode
                if key.code:
                    run_script(key.code)

        elif key_type == KeyCommon.BUTTON_TYPE:
            controller = self.button_controllers.get(key)
            if controller:
                controller.press(view, button, event_type)

    def send_key_release(self, key, view, button = 1, event_type = EventType.CLICK):
        """ Actually generate a fake key release """
        key_type = key.type
        if key_type == KeyCommon.CHAR_TYPE:
            self._key_synth.release_unicode(key.code)
        elif key_type == KeyCommon.KEYSYM_TYPE:
            self._key_synth.release_keysym(key.code)
        elif key_type == KeyCommon.KEYPRESS_NAME_TYPE:
            self._key_synth.release_keysym(get_keysym_from_name(key.code))
        elif key_type == KeyCommon.KEYCODE_TYPE:
            self._key_synth.release_keycode(key.code);
        if key_type == KeyCommon.MACRO_TYPE:
            pass
        elif key_type == KeyCommon.SCRIPT_TYPE:
            pass
        elif key_type == KeyCommon.BUTTON_TYPE:
            controller = self.button_controllers.get(key)
            if controller:
                controller.release(view, button, event_type)

    def release_non_sticky_key(self, key, view, button, event_type):
        needs_layout_update = False

        # release key
        self.send_key_up(key, view, button, event_type)

        # Don't release latched modifiers for click buttons right now.
        # Keep modifier keys unchanged until the actual click happens
        # -> allow clicks with modifiers
        if not key.is_layer_button() and \
           not (key.type == KeyCommon.BUTTON_TYPE and \
           key.id in ["middleclick", "secondaryclick"]):
            # release latched modifiers
            self.release_latched_sticky_keys(only_unpressed = True)

        # switch to layer 0 on (almost) any key release
        if not key.is_layer_button() and \
           not key.id in ["move", "showclick"] and \
           not self.editing_snippet:
            if self.active_layer_index != 0 and not self._layer_locked:
                self.active_layer_index = 0
                self.update_visible_layers()
                needs_layout_update = True
                self.redraw()

        return needs_layout_update

    def set_modifiers(self, mod_mask):
        """
        Sync Onboard with modifiers from the given modifier mask.
        Used to sync changes to system modifier state with Onboard.
        """
        for mod_bit in (1<<bit for bit in range(8)):
            # Limit to the locking modifiers only. Updating for all modifiers would
            # be desirable, but Onboard busily flashing keys and using CPU becomes
            # annoying while typing on a hardware keyboard.
            if mod_bit & (Modifiers.CAPS | Modifiers.NUMLK):
                self.set_modifier(mod_bit, bool(mod_mask & mod_bit))

    def set_modifier(self, mod_bit, active):
        """
        Update Onboard to reflect the state of the given modifier.
        """
        # find all keys assigned to the modifier bit
        keys = []
        for key in self.layout.iter_keys():
            if key.modifier == mod_bit:
                keys.append(key)

        active_onboard = bool(self._mods[mod_bit])

        if active and not active_onboard:
            # modifier was turned on
            self._mods[mod_bit] += 1
            for key in keys:
                if key.sticky:
                    self.step_sticky_key(key, 1, EventType.CLICK)

        elif not active and active_onboard:
            # modifier was turned off
            self._mods[mod_bit] = 0
            for key in keys:
                if key in self._latched_sticky_keys:
                    self._latched_sticky_keys.remove(key)
                if key in self._locked_sticky_keys:
                    self._locked_sticky_keys.remove(key)
                key.active = False
                key.locked = False

        if active != active_onboard:
            self.redraw(keys)
            self.redraw_labels(False)

    def step_sticky_key(self, key, button, event_type):
        """
        One cycle step when pressing a sticky (latchabe/lockable)
        modifier key (all sticky keys except layer buttons).
        """
        needs_update = False

        active, locked = self.step_sticky_key_state(key,
                                                     key.active, key.locked,
                                                     button, event_type)
        # apply the new states
        was_active  = key.active
        deactivated = False
        key.active  = active
        key.locked  = locked
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

            deactivated = was_active

        return deactivated

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
                _logger.warning("Invalid sticky behavior '{}' for group '{}'" \
                              .format(value, group))
        return behavior

    def get_key_action(self, key):
        action = key.action
        if action is None:
            if key.type == KeyCommon.BUTTON_TYPE:
                action = KeyCommon.SINGLE_STROKE_ACTION
            else:
                label = key.get_label()
                alternatives = self.find_canonical_equivalents(label)
                if len(label) == 1 and label.isalpha() or bool(alternatives):
                    action = config.keyboard.default_key_action
                else:
                    action = KeyCommon.SINGLE_STROKE_ACTION
                
        return action

    def has_latched_sticky_keys(self, except_keys = None):
        """ any sticky keys latched? """
        return len(self._latched_sticky_keys) > 0

    def release_latched_sticky_keys(self, except_keys = None,
                                    only_unpressed = False):
        """ release latched sticky (modifier) keys """
        if len(self._latched_sticky_keys) > 0:
            for key in self._latched_sticky_keys[:]:
                if not except_keys or not key in except_keys:
                    # Don't release still pressed modifiers, they may be
                    # part of a multi-touch key combination.
                    if not only_unpressed or not key.pressed:
                        self.send_key_up(key)
                        self._latched_sticky_keys.remove(key)
                        key.active = False
                        self.redraw([key])

            # modifiers may change many key labels -> redraw everything
            self.redraw_labels(False)

    def release_locked_sticky_keys(self):
        """ release locked sticky (modifier) keys """
        if len(self._locked_sticky_keys) > 0:
            for key in self._locked_sticky_keys[:]:
                self.send_key_up(key)
                self._locked_sticky_keys.remove(key)
                key.active = False
                key.locked = False
                key.pressed = False
                self.redraw([key])

            # modifiers may change many key labels -> redraw everything
            self.redraw_labels(False)

    def update_ui(self):
        """
        Force update of everything.
        Relatively expensive, don't call this while typing.
        """
        self.update_controllers()
        self.update_visible_layers()

        for view in self._layout_views:
            view.update_ui()

    def update_ui_no_resize(self):
        """
        Update everything assuming key sizes don't change.
        Doesn't invalidate cached surfaces.
        """
        self.update_controllers()
        self.update_visible_layers()
        for view in self._layout_views:
            view.update_ui_no_resize()

    def update_layout(self):
        """
        Update layout, key sizes are probably changing.
        """
        for view in self._layout_views:
            view.update_layout()

    def update_controllers(self):
        """ update button states """
        for controller in self.button_controllers.values():
            controller.update()

    def update_visible_layers(self):
        """ show/hide layers """
        layout = self.layout
        if layout:
            layers = layout.get_layer_ids()
            if layers:
                layout.set_visible_layers([layers[0], self.active_layer])

        # notify the scanner about layer changes
        if self.scanner:
            self.scanner.update_layer(layout, self.active_layer)

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

        # NumLock is special, keep its state on exit
        if not config.keyboard.sticky_key_release_delay:
            for key in self._locked_sticky_keys[:]:
                if key.modifier == Modifiers.NUMLK:
                    self._locked_sticky_keys.remove(key)

        self.release_locked_sticky_keys()

        self._unpress_timers.stop_all()

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
        if self._key_synth_virtkey:
            self._key_synth_virtkey.cleanup()
        if self._key_synth_atspi:
            self._key_synth_atspi.cleanup()
        self.layout = None  # free the memory

    def find_keys_from_ids(self, key_ids):
        if self.layout is None:
            return []
        return self.layout.find_ids(key_ids)


class ButtonController(object):
    """
    MVC inspired controller that handles events and the resulting
    state changes of buttons.
    """
    def __init__(self, keyboard, key):
        self.keyboard = keyboard
        self.key = key

    def press(self, view, button, event_type):
        """ button pressed """
        pass

    def long_press(self, view, button):
        """ button pressed long """
        pass

    def release(self, view, button, event_type):
        """ button released """
        pass

    def update(self):
        """ asynchronous ui update """
        pass

    def can_dwell(self):
        """ can start dwelling? """
        return False

    def set_visible(self, visible):
        if self.key.visible != visible:
            layout = self.keyboard.layout
            layout.set_item_visible(self.key, visible)
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
    def release(self, view, button, event_type):
        mc = self.keyboard.get_mouse_controller()
        if self.is_active():
            # stop click mapping, resets to primary button and single click
            mc.set_click_params(MouseController.PRIMARY_BUTTON,
                                MouseController.CLICK_TYPE_SINGLE)
        else:
            # Exclude click type buttons from the click mapping
            # to be able to reliably cancel the click.
            # -> They will receive only single left clicks.
            rects = view.get_click_type_button_rects()
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

    def release(self, view, button, event_type):
        BCClick.release(self, view, button, event_type)
        self.keyboard.show_touch_handles(show = self._can_show_handles(),
                                         auto_hide = False)

    def update(self):
        active = self.key.active
        BCClick.update(self)

        if active and not self.key.active:
            # hide the touch handles
            self.keyboard.show_touch_handles(self._can_show_handles())

    def _can_show_handles(self):
        return self.is_active() and \
               config.mousetweaks and config.mousetweaks.is_active() and \
               not config.xid_mode


class BCHoverClick(ButtonController):

    id = "hoverclick"

    def release(self, view, button, event_type):
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

    def release(self, view, button, event_type):
        view.set_visible(False)

    def update(self):
        self.set_sensitive(not config.xid_mode) # insensitive in XEmbed mode


class BCShowClick(ButtonController):

    id = "showclick"

    def release(self, view, button, event_type):
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
                    layout.set_item_visible(item, show_click)
                elif item.group == 'noclick':
                    layout.set_item_visible(item, not show_click)

    def can_dwell(self):
        return not config.mousetweaks or not config.mousetweaks.is_active()


class BCMove(ButtonController):

    id = "move"

    def press(self, view, button, event_type):
        view.start_move_window()

    def long_press(self, view, button):
        if not config.xid_mode:
            self.keyboard.show_touch_handles(True)

    def release(self, view, button, event_type):
        view.stop_move_window()

    def update(self):
        self.set_visible(not config.has_window_decoration() and \
                         not config.xid_mode)


class BCLayer(ButtonController):
    """ layer switch button, switches to layer <layer_index> when released """

    layer_index = None

    def _get_id(self):
        return "layer" + str(self.layer_index)
    id = property(_get_id)

    def release(self, view, button, event_type):
        keyboard = self.keyboard

        active_before = keyboard.active_layer_index == self.layer_index
        locked_before = active_before and keyboard._layer_locked

        active, locked = keyboard.step_sticky_key_state(
                                       self.key,
                                       active_before, locked_before,
                                       button, event_type)

        keyboard.active_layer_index = self.layer_index \
                                      if active else 0

        keyboard._layer_locked       = locked \
                                      if self.layer_index else False

        if active_before != active:
            keyboard.update_visible_layers()
            keyboard.redraw()

    def update(self):
        # don't show active state for layer 0, it'd be visible all the time
        active = self.key.get_layer_index() != 0 and \
                 self.key.get_layer_index() == self.keyboard.active_layer_index
        self.set_active(active)
        self.set_locked(active and self.keyboard._layer_locked)


class BCPreferences(ButtonController):

    id = "settings"

    def release(self, view, button, event_type):
        run_script("sokSettings")

    def update(self):
        self.set_visible(not config.xid_mode and \
                         not config.running_under_gdm and \
                         not config.lockdown.disable_preferences)


class BCQuit(ButtonController):

    id = "quit"

    def release(self, view, button, event_type):
        view.emit_quit_onboard()

    def update(self):
        self.set_visible(not config.xid_mode and \
                         not config.lockdown.disable_quit)

