# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import sys
import gc
from contextlib import contextmanager

from gi.repository import GObject, Gtk, Gdk

from Onboard.KeyGtk       import *
from Onboard              import KeyCommon
from Onboard.KeyCommon    import StickyBehavior
from Onboard.MouseControl import MouseController
from Onboard.Scanner      import Scanner
from Onboard.utils        import Timer, Modifiers
from Onboard.WordPrediction import WordPrediction

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


class Keyboard(WordPrediction):
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

    @contextmanager
    def suppress_modifiers(self):
        """ Turn modifiers off temporarily. May be nested. """
        self._push_and_clear_modifiers()
        yield None
        self._pop_and_restore_modifiers()

    def _push_and_clear_modifiers(self):
        self._suppress_modifiers_stack.append(self._mods.copy())
        for mod, nkeys in self._mods.items():   
            if nkeys:
                self._mods[mod] = 0
                self.vk.unlock_mod(mod)

    def _pop_and_restore_modifiers(self):
        self._mods = self._suppress_modifiers_stack.pop()
        for mod, nkeys in self._mods.items():   
            if nkeys:
                self.vk.lock_mod(mod)

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
        WordPrediction.__init__(self, self.atspi_state_tracker)

        self._pressed_key = None
        self._last_typing_time = 0
        self._suppress_modifiers_stack = []

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

    def on_layout_loaded(self):
        """ called when the layout has been loaded """
        self.reset()

        self._connect_button_controllers()
        self.assure_valid_active_layer()
        WordPrediction.on_layout_loaded(self)
        self.update_ui()

        # Update Onboard to show the initial modifiers
        keymap = Gdk.Keymap.get_default()
        if keymap:
            mod_mask = keymap.get_modifier_state()
            self.set_modifiers(mod_mask)

    def _connect_button_controllers(self):
        """ connect button controllers to button keys """
        self.button_controllers = {}

        # connect button controllers to button keys
        types = { type.id : type for type in \
                   [BCMiddleClick, BCSingleClick, BCSecondaryClick, 
                    BCDoubleClick, BCDragClick, BCHoverClick,
                    BCHide, BCShowClick, BCMove, BCPreferences, BCQuit,
                    BCStealthMode, BCAutoLearn, BCAutoPunctuation, BCInputline,
                    BCExpandCorrections, BCLanguage,
                   ]
                }
        for key in self.layout.iter_keys():
            if key.is_layer_button():
                bc = BCLayer(self, key)
                bc.layer_index = key.get_layer_index()
                self.button_controllers[key] = bc
            else:
                type = types.get(key.id)
                if type:
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
        self.update_context_ui()

    def get_pressed_key(self):
        return self._pressed_key

    def set_currently_typing(self):
        """ Remember it was us who just typed text. """
        self._last_typing_time = time.time()

    def is_typing(self):
        """ Is Onboard currently or was it just recently sending any text? """
        key = self.get_pressed_key()
        return key and self._is_text_insertion_key(key) or \
               time.time() - self._last_typing_time <= 0.3

    def _is_text_insertion_key(self, key):
        """ Does key actually insert any characters (not navigation key) """
        return not key.is_modifier() and \
               not key.type in [KeyCommon.KEYSYM_TYPE, # Fx
                                KeyCommon.KEYPRESS_NAME_TYPE, # cursor
                               ]

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

            can_send_key = (not key.sticky or not key.active) and \
                            not key.action == KeyCommon.DELAYED_STROKE_ACTION and \
                            not key.type == KeyCommon.WORD_TYPE

            # Get drawing behing us now so it can't delay processing key_up()
            # and cause unwanted key repeats on slow systems.
            self.redraw([key])
            self.process_updates()

            if can_send_key:
                if not key.is_modifier() and not key.is_button():
                    # punctuation duties before keypress is sent
                    WordPrediction.on_before_key_down(self, key)

                # press key
                self.send_key_down(key, button, event_type)

            # Modifier keys may change multiple keys 
            # -> redraw all dependent keys
            # no danger of key repeats plus more work to do
            # -> redraw asynchronously
            if can_send_key and key.is_modifier():
                self.redraw(self.update_labels())

    def key_up(self, key, button = 1, event_type = EventType.CLICK):
        """ Release one of Onboard's key representations. """
        #duration = time.time() - self._press_time
        #print("key press duration {}ms".format(int(duration * 1000)))

        update = False

        if key.sensitive:

            # Was the key nothing but pressed before?
            extend_pressed_state = key.is_pressed_only()

            if key.sticky:
                if self.step_sticky_key(key, button, event_type):
                    self.send_key_up(key)
                    if key.is_modifier():
                        self.redraw(self.update_labels())
            else:
                update = self.release_non_sticky_key(key, button, event_type)

            # Skip updates for the common letter press to improve
            # responsiveness on slow systems.
            if update or \
               key.type == KeyCommon.BUTTON_TYPE:
                self.update_context_ui()

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

            # Make note that it was us who just sent text
            # (vs. at-spi update due to scrolling, physical typing, ...).
            if self._is_text_insertion_key(key):
                self.set_currently_typing()

        self._pressed_key = None
        gc.enable()

    def send_key_down(self, key, button, event_type):
        key_type = key.type
        modifier = key.modifier

        if key.action != KeyCommon.DELAYED_STROKE_ACTION:
            self.send_key_press(key, button, event_type)
        if key.action == KeyCommon.DOUBLE_STROKE_ACTION:
            self.send_key_release(key, button, event_type)

        if modifier:
            # Increment this before lock_mod() to skip 
            # updating keys a second time in set_modifiers().
            self.mods[modifier] += 1

            # Alt is special because is activates the window managers move mode.
            if modifier != 8: # not Alt?
                self.vk.lock_mod(modifier)

    def send_key_up(self,key, button = 1, event_type = EventType.CLICK):
        key_type = key.type
        modifier = key.modifier

        if key.action == KeyCommon.DOUBLE_STROKE_ACTION or \
           key.action == KeyCommon.DELAYED_STROKE_ACTION:
            self.send_key_press(key, button, event_type)
        self.send_key_release(key)

        if modifier:
            # Decrement this before unlock_mod() to skip
            # updating keys a second time in set_modifiers().
            self.mods[modifier] -= 1

            # Alt is special because it activates the window managers move mode.
            if modifier != 8: # not Alt?
                self.vk.unlock_mod(modifier)

        if self.alt_locked:
            self.alt_locked = False
            self.vk.unlock_mod(8)

    def send_key_press(self, key, button, event_type):
        """ Actually generate a fake key press """
        key_type = key.type

        if key_type == KeyCommon.CHAR_TYPE:
            if sys.version_info.major == 2:
                char = self.utf8_to_unicode(key.code)
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
                char = self.utf8_to_unicode(key.code)
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
        Send key presses for all characters in a unicode string.
        """
        keystr = keystr.replace("\\n", "\n") # for new lines in snippets

        if self.vk:   # may be None in the last call before exiting
            for ch in keystr:
                if ch == "\n":
                    # press_unicode("\n") fails in gedit.
                    # -> explicitely send the key symbol instead
                    self.press_keysym("return")
                else:             # any other printable keys
                    self.vk.press_unicode(ord(ch))
                    self.vk.release_unicode(ord(ch))

    def release_non_sticky_key(self, key, button, event_type):
        needs_layout_update = False

        # release key
        self.send_key_up(key, button, event_type)

        # Insert words on button release to avoid having the wordlist
        # change between button press and release. This also allows for
        # long presses to trigger a different action, e.g. menu.
        WordPrediction.send_key_up(self, key, button, event_type)

        # Don't release latched modifiers for click buttons yet,
        # Keep them unchanged until the actual click happens
        # -> allow clicks with modifiers
        if not key.is_layer_button() and \
           not (key.type == KeyCommon.BUTTON_TYPE and \
                key.id in ["middleclick", "secondaryclick"]) and \
           not key in self.get_text_displays():
            # release latched modifiers
            self.release_latched_sticky_keys()

            # undo temporary suppression of the text display
            WordPrediction.show_input_line_on_key_release(self, key)

        # Send punctuation after the key press and after sticky keys have
        # been released, since this may trigger latching right shift.
        #self.send_punctuation_suffix()

        # switch to layer 0 on (almost) any key release
        if not key.is_layer_button() and \
           not key.id in ["move", "showclick"] and \
           not self._editing_snippet:
            if self.active_layer_index != 0 and not self.layer_locked:
                self.active_layer_index = 0
                self.update_visible_layers()
                needs_layout_update = True
                self.redraw()

        # punctuation assistance and collapse corrections
        WordPrediction.on_after_key_release(self, key)

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
            self.redraw(self.update_labels())

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
                _logger.warning("Invalid sticky behavior '{}' for key '{}'" \
                              .format(value, key.id))
        return behavior

    def on_snippets_dialog_closed(self):
        self._editing_snippet = False

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
                    self.redraw([key])

            # modifiers may change many key labels -> redraw everything
            self.redraw(self.update_labels())

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
            self.redraw(self.update_labels())

    def update_ui(self):
        """
        Force update of everything.
        Relatively expensive, don't call this while typing.
        """
        self.update_visible_layers()
        self.update_labels()
        self.update_context_ui()
        self.invalidate_font_sizes()
        self.invalidate_keys()
        self.invalidate_shadows()

    def update_context_ui(self):
        """ Update text-context dependent ui """
        # update buttons
        for controller in list(self.button_controllers.values()):
            controller.update()

        keys = WordPrediction.update_wp_ui(self)

        self.update_layout()

        self.redraw(keys)

    def update_layout(self):
        layout = self.layout
        if not layout:
            return

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

        # Give toolkit-dependent keyboardGTK a chance to
        # update the aspect ratio of the main window
        self.on_layout_updated()

    def update_visible_layers(self):
        """ show/hide layers """
        layout = self.layout
        if layout:
            layers = layout.get_layer_ids()
            if layers:
                layout.set_visible_layers([layers[0], self.active_layer])

    def on_outside_click(self):
        """
        Called by outside click polling.
        Keep this as Francesco likes to have modifiers
        reset when clicking outside of onboard.
        """
        self.release_latched_sticky_keys()
        self.update_ui()

    def on_cancel_outside_click(self):
        """ Called when outside click polling times out. """
        pass

    def get_mouse_controller(self):
        if config.mousetweaks and \
           config.mousetweaks.is_active():
            return config.mousetweaks
        return config.clickmapper

    def cleanup(self):
        WordPrediction.cleanup(self)

        # reset still latched and locked modifier keys on exit
        self.release_latched_sticky_keys()

        # NumLock is special, keep its state on exit
        if not config.keyboard.sticky_key_release_delay:
            for key in self._locked_sticky_keys[:]:
                if key.modifier == Modifiers.NUMLK:
                    self._locked_sticky_keys.remove(key)

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

    def find_items_from_ids(self, ids):
        if self.layout is None:
            return []
        return list(self.layout.find_ids(ids))

    def find_items_from_classes(self, item_classes):
        if self.layout is None:
            return []
        return list(self.layout.find_classes(item_classes))

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
            layout = self.keyboard.layout
            layout.set_item_visible(visible)
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
            rects = self.keyboard.get_click_type_button_screen_rects()
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
                    layout.set_item_visible(item, show_click)
                elif item.group == 'noclick':
                    layout.set_item_visible(item, not show_click)

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
            keyboard.update_visible_layers()
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


class BCExpandCorrections(ButtonController):

    id = "expand-corrections"

    def release(self, button, event_type):
        wordlist = self.key.get_parent()
        wordlist.expand_corrections(not wordlist.are_corrections_expanded())


class BCAutoLearn(ButtonController):

    id = "learnmode"

    def release(self, button, event_type):
        config.wp.auto_learn = not config.wp.auto_learn

        # don't learn when turning auto_learn off
        if not config.wp.auto_learn:
            self.keyboard.discard_changes()

        # turning on auto_learn disables stealth_mode
        if config.wp.auto_learn and config.wp.stealth_mode:
            config.wp.stealth_mode = False

    def update(self):
        self.set_active(config.wp.auto_learn)


class BCAutoPunctuation(ButtonController):

    id = "punctuation"

    def release(self, button, event_type):
        config.wp.auto_punctuation = not config.wp.auto_punctuation
        self.keyboard.punctuator.reset()

    def update(self):
        self.set_active(config.wp.auto_punctuation)


class BCStealthMode(ButtonController):

    id = "stealthmode"

    def release(self, button, event_type):
        config.wp.stealth_mode = not config.wp.stealth_mode

        # don't learn, forget words when stealth mode is enabled
        if config.wp.stealth_mode:
            self.keyboard.discard_changes()

    def update(self):
        self.set_active(config.wp.stealth_mode)


class BCInputline(ButtonController):

    id = "inputline"

    def release(self, button, event_type):
        # hide the input line display when it is clicked
        self.keyboard.hide_input_line()

class BCLanguage(ButtonController):

    id = "language"

    def __init__(self, keyboard, key):
        ButtonController.__init__(self, keyboard, key)


    def release(self, button, event_type):
        self.keyboard.show_language_menu(self.key, button)


