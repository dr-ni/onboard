# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

import sys

from gi.repository import GObject, Gtk, Gdk

from Onboard.utils import Timer
from Onboard.KeyGtk import *
from Onboard import KeyCommon
from Onboard.MouseControl import MouseController
from Onboard.Scanner import Scanner
from Onboard.WordPredictor import *

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

    def __init__(self, vk):
        self.scanner = None
        self.vk = vk
        self.unpress_timer = UnpressTimer(self)
        self._latched_sticky_keys = []
        self._locked_sticky_keys = []

    def destruct(self):
        self.cleanup()

    def initial_update(self):
        """ called when the layout has been loaded """

        #List of keys which have been latched.
        #ie. pressed until next non sticky button is pressed.
        self._latched_sticky_keys = []
        self._locked_sticky_keys = []
        self._editing_snippet = False
        self._last_canvas_extents = None

        self.canvas_rect = Rect()
        self.button_controllers = {}

        self.input_line = InputLine()
        self.atspi_text_context = AtspiTextContext(self, 
                                                   self.atspi_state_tracker)
        self.text_context = None

        self._hide_input_line = False
        self.punctuator = Punctuator()
        self.predictor  = None

        self.word_choices = []
        self.word_infos = []

        self.enable_word_prediction(config.wp.enabled)

        # connect button controllers to button keys
        types = [BCMiddleClick, BCSingleClick, BCSecondaryClick, BCDoubleClick, BCDragClick,
                 BCHoverClick,
                 BCHide, BCShowClick, BCMove, BCPreferences, BCQuit,
                 BCStealthMode, BCAutoLearn, BCAutoPunctuation, BCInputline,
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

        self.assure_valid_active_layer()
        self.update_ui()

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
        self.press_key(key)
        self.release_key(key)

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

    def get_key_at_location(self, location):
        if not self.layout:   # don't fail on exit
            return None

        # First try all keys of the active layer
        for item in reversed(list(self.layout.iter_layer_keys(self.active_layer))):
            if item.visible and item.is_point_within(location):
                return item

        # Then check all non-layer keys (layer switcher, hide, etc.)
        for item in reversed(list(self.layout.iter_layer_keys(None))):
            if item.visible and item.is_point_within(location):
                return item

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

    def cb_macroEntry_activate(self,widget,macroNo,dialog):
        self.set_new_macro(macroNo, gtk.RESPONSE_OK, widget, dialog)

    def set_new_macro(self,macroNo,response,macroEntry,dialog):
        if response == gtk.RESPONSE_OK:
            config.set_snippet(macroNo, macroEntry.get_text())

        dialog.destroy()

    def _on_mods_changed(self):
        raise NotImplementedError()

    def press_key(self, key, button = 1, event_type = EventType.CLICK):
        if not key.sensitive:
            return

        # unpress the previous key
        self.unpress_timer.reset()

        key.pressed = True

        if not key.active:
            if self.mods[8]:
                self.alt_locked = True
                self.vk.lock_mod(8)

        if not key.sticky or not key.active:
            # punctuation duties before keypress is sent
            self.send_punctuation_prefix(key)

            # press key
            self.send_press_key(key, button, event_type)

            # Word prediction: if there is no AT-SPI, track the
            # key presses we sent ourselves.
            if self.input_line.track_sent_key(key, self.mods):
                self.commit_input_line()

            # Modifier keys may change multiple keys -> redraw everything
            if key.action_type == KeyCommon.MODIFIER_ACTION:
                self.redraw()

        self.redraw([key])

    def release_key(self, key, button = 1, event_type = EventType.CLICK):
        if not key.sensitive:
            return

        # Was the key nothing but pressed before?
        extend_pressed_state = key.is_pressed_only()

        if key.sticky:
            self.cycle_sticky_key(key, button, event_type)
        else:
            self.send_release_key(key, button, event_type)

            # Don't release latched modifiers for click buttons right now.
            # Keep modifier keys unchanged until the actual click happens
            # -> allow clicks with modifiers
            if not key.is_layer_button() and \
               not (key.action_type == KeyCommon.BUTTON_ACTION and \
                    key.id in ["middleclick", "secondaryclick"]) and \
               not key.id in ["inputline"]:
                # release latched modifiers
                self.release_latched_sticky_keys()

                # undo temporary suppression of the input line
                self._hide_input_line = False


            # Send punctuation after the key press and after sticky keys have
            # been released, since this may trigger latching right shift.
            self.send_punctuation_suffix()

            # switch to layer 0
            if not key.is_layer_button() and \
               not key.id in ["move", "showclick"] and \
               not self._editing_snippet:
                if self.active_layer_index != 0 and not self.layer_locked:
                    self.active_layer_index = 0
                    self.redraw()

            self.find_word_choices()

        self.update_controllers()
        self.update_layout()

        # Is the key still nothing but pressed?
        extend_pressed_state = extend_pressed_state and key.is_pressed_only()

        # Draw key unpressed to remove the visual feedback.
        if extend_pressed_state and \
           not config.scanner.enabled:
            # Keep key pressed for a little longer for clear user feedback.
            self.unpress_timer.start(key)
        else:
            # Unpress now to avoid flickering of the
            # pressed color after key release.
            key.pressed = False
            self.redraw([key])

    def cycle_sticky_key(self, key, button, event_type):
        """ One cycle step when pressing a sticky (latchabe/lockable) key """

        active, locked = self.cycle_sticky_key_state(key,
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
                self.send_release_key(key)
                if key.action_type == KeyCommon.MODIFIER_ACTION:

                    self.redraw()   # redraw the whole keyboard

    def cycle_sticky_key_state(self, key, active, locked, button, event_type):
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
        return behavior in ["cycle", "dblclick", "latch"]

    def _can_lock(self, key, event_type):
        """
        Can sticky key enter locked state?
        Locked keys stay active until they are pressed again.
        """
        behavior = self._get_sticky_key_behavior(key)
        return behavior in ["cycle", "lock"] or \
               behavior in ["dblclick"] and event_type == EventType.DOUBLE_CLICK

    def _can_lock_on_double_click(self, key, event_type):
        """
        Can sticky key enter locked state on double click?
        Locked keys stay active until they are pressed again.
        """
        behavior = self._get_sticky_key_behavior(key)
        return behavior in ["dblclick"] and \
               event_type == EventType.DOUBLE_CLICK

    def _get_sticky_key_behavior(self, key):
        """ Return the sticky key behavior for the given key """
        behaviors     = ["cycle", "dblclick", "latch", "lock"]

        _dict = config.keyboard.sticky_key_behavior

        # try the individual key id
        behavior = _dict.get(key.id)

        # Special case: CAPS key always defaults to lock-only behavior
        # unless it was expicitely included in sticky_key_behaviors.
        if behavior is None and \
           key.id == "CAPS":
            behavior = "lock"

        # try the key group
        if behavior is None:
            if key.is_modifier():
                behavior = _dict.get("modifiers")
            if key.is_layer_button():
                behavior = _dict.get("layers")

        # try the 'all' group
        if behavior is None:
            behavior = _dict.get("all")

        # else fall back to hard coded default
        if not behavior in behaviors:
            behavior = "cycle"

        return behavior

    def send_press_key(self, key, button, event_type):

        if key.action_type == KeyCommon.CHAR_ACTION:
            char = key.action
            if sys.version_info.major == 2:
                char = self.utf8_to_unicode(char)
            self.vk.press_unicode(char)

        elif key.action_type == KeyCommon.KEYSYM_ACTION:
            self.vk.press_keysym(key.action)
        elif key.action_type == KeyCommon.KEYPRESS_NAME_ACTION:
            self.vk.press_keysym(get_keysym_from_name(key.action))
        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            mod = key.action

            if not mod == 8: #Hack since alt puts metacity into move mode and prevents clicks reaching widget.
                self.vk.lock_mod(mod)
            self.mods[mod] += 1
        elif key.action_type == KeyCommon.MACRO_ACTION:
            snippet_id = int(key.action)
            mlabel, mString = config.snippets.get(snippet_id, (None, None))
            if mString:
                self.press_key_string(mString)

            # Block dialog in xembed mode.
            # Don't allow to open multiple dialogs in force-to-top mode.
            elif not config.xid_mode and \
                not self._editing_snippet:

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
                self._editing_snippet = True

        elif key.action_type == KeyCommon.KEYCODE_ACTION:
            self.vk.press_keycode(key.action)

        elif key.action_type == KeyCommon.SCRIPT_ACTION:
            if not config.xid_mode:  # block settings dialog in xembed mode
                if key.action:
                    run_script(key.action)

        elif key.action_type == KeyCommon.WORD_ACTION:
            s  = self.get_match_remainder(key.action) # unicode
            if config.wp.auto_punctuation and \
               button != 3: # right click suppresses punctuation
                self.punctuator.set_end_of_word()
            self.press_key_string(s)

        elif key.action_type == KeyCommon.BUTTON_ACTION:
            controller = self.button_controllers.get(key)
            if controller:
                controller.press(button, event_type)

    def has_latched_sticky_keys(self, except_keys = None):
        """ any sticky keys latched? """
        return len(self._latched_sticky_keys) > 0

    def release_latched_sticky_keys(self, except_keys = None):
        """ release latched sticky (modifier) keys """
        if len(self._latched_sticky_keys) > 0:
            for key in self._latched_sticky_keys[:]:
                if not except_keys or not key in except_keys:
                    self.send_release_key(key)
                    self._latched_sticky_keys.remove(key)
                    key.active = False

            # modifiers may change many key labels -> redraw everything
            self.redraw()

    def release_locked_sticky_keys(self):
        """ release locked sticky (modifier) keys """
        if len(self._locked_sticky_keys) > 0:
            for key in self._locked_sticky_keys[:]:
                self.send_release_key(key)
                self._locked_sticky_keys.remove(key)
                key.active = False
                key.locked = False
                key.pressed = False

            # modifiers may change many key labels -> redraw everything
            self.redraw()

    def send_release_key(self,key, button = 1, event_type = EventType.CLICK):
        if key.action_type == KeyCommon.CHAR_ACTION:
            char = key.action
            if sys.version_info.major == 2:
                char = self.utf8_to_unicode(char)
            self.vk.release_unicode(char)
        elif key.action_type == KeyCommon.KEYSYM_ACTION:
            self.vk.release_keysym(key.action)
        elif key.action_type == KeyCommon.KEYPRESS_NAME_ACTION:
            self.vk.release_keysym(get_keysym_from_name(key.action))
        elif key.action_type == KeyCommon.KEYCODE_ACTION:
            self.vk.release_keycode(key.action);
        elif key.action_type == KeyCommon.MACRO_ACTION:
            pass
        elif key.action_type == KeyCommon.SCRIPT_ACTION:
            pass
        elif key.action_type == KeyCommon.BUTTON_ACTION:
            controller = self.button_controllers.get(key)
            if controller:
                controller.release(button, event_type)
        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            mod = key.action

            if not mod == 8:
                self.vk.unlock_mod(mod)

            self.mods[mod] -= 1

        if self.alt_locked:
            self.alt_locked = False
            self.vk.unlock_mod(8)

    def press_key_string(self, keystr):
        """
        Send key presses for all characters in a unicode string
        and keep track of the changes in text_context.
        """
        capitalize = False

        keystr = keystr.replace("\\n", "\n")

        if self.vk:   # may be None in the last call before exiting
            for ch in keystr:
                if ch == "\b":   # backspace?
                    keysym = get_keysym_from_name("backspace")
                    self.vk.press_keysym  (keysym)
                    self.vk.release_keysym(keysym)

                    if not config.wp.stealth_mode:
                        self.input_line.delete_left()

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

                    if not config.wp.stealth_mode:
                        self.input_line.insert(ch)

        return capitalize

    def update_ui(self):
        """ Force update of everything """
        self.update_controllers()
        self.update_layout()
        self.update_font_sizes()

    def update_controllers(self):
        # update buttons
        for controller in list(self.button_controllers.values()):
            controller.update()

        self.update_inputline()
        self.update_wordlists()

        self.update_layout()

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
        self.commit_input_line()
        self.update_ui()

    def on_cancel_outside_click(self):
        """ Called when outside click polling times out. """
        pass

    def get_mouse_controller(self):
        if config.mousetweaks and \
           config.mousetweaks.is_active():
            return config.mousetweaks
        return config.clickmapper

    def update_inputline(self):
        """ Refresh the GUI displaying the current line's content """
        if self.predictor:
            for key in self.find_keys_from_ids(["inputline"]):
                if self._hide_input_line:
                    key.visible = False
                else:
                    line = self.text_context.get_line()
                    if line:
                        key.raise_to_top()
                        key.visible = True
                    else:
                        line = u""
                        key.visible = False

                    key.set_content(line, self.word_infos,
                                    self.text_context.get_line_cursor_pos())
                self.redraw([key])
                # print [(x.start, x.end) for x in word_infos]

    def update_wordlists(self):
        if self.predictor:
            for item in self.find_keys_from_ids(["wordlist"]):
                word_keys = self.create_wordlist_keys(self.word_choices,
                                                item.get_rect(), item.context)
                fixed_keys = item.find_ids(["wordlistbg"])
                item.set_items(fixed_keys + word_keys)
                self.redraw([item])

    def find_word_choices(self):
        """ word prediction: find choices, only once per key press """
        self.word_choices = []
        if self.predictor:
            context = self.text_context.get_context()
            self.word_choices = self.predictor.predict(context)
            #print "line='%s'" % self.text_context.get_line()

            # update word information for the input line display
            self.word_infos = self.predictor.get_word_infos( \
                                               self.text_context.get_line())

    def on_text_context_changed(self):
        """ The text of the target widget changed or the cursor moved """
        self.find_word_choices()
        self.update_controllers()

    def get_match_remainder(self, index):
        """ returns the rest of matches[index] that hasn't been typed yet """
        if not self.predictor:
            return ""
        text = self.text_context.get_context()
        word_prefix = self.predictor.get_last_context_token(text)
        #print self.word_choices[index], word_prefix
        return self.word_choices[index][len(word_prefix):]

    def commit_input_line(self):
        """ word prediction: try to learn all words and clear the input line """
        if self.text_context is self.input_line:
            if self.predictor and config.wp.can_auto_learn():
                self.predictor.learn_text(self.text_context.get_line(), True)

        self.reset_text_context()
        self.punctuator.reset()
        self.word_choices = []

    def hide_input_line(self, hide = True):
        """
        Temporarily hide the input line to access keys below it.
        """
        self._hide_input_line = hide
        self.update_inputline()

    def enable_word_prediction(self, enable):
        if enable:
            # only load dictionaries if there is a
            # dynamic or static wordlist in the layout
            if self.find_keys_from_ids(("wordlist", "word0")):
                self.predictor = WordPredictor()
                self.apply_prediction_profile()
        else:
            if self.predictor:
                self.predictor.save_dictionaries()
            self.predictor = None

        # show/hide word-prediction buttons
        for item in self.layout.iter_items():
            if item.group in ("inputline", "wordlist", "word", "wpbutton"):
                item.visible = enable

        # Init text context tracking.
        # Keep track in and write to both contexts in parallel,
        # but read only from the active one.
        if self.text_context:
            self.text_context.cleanup() # deregister AT-SPI listeners 
        if enable:
            if True:
                self.text_context = self.atspi_text_context
            else:
                self.text_context = self.input_line
            self.text_context.enable(True) # register AT-SPI listerners
        else:
            self.text_context = None

    def reset_text_context(self):
        """
        Reset all contexts and cancel whatever has accumulated for learning.
        """
        self.atspi_text_context.reset()
        self.input_line.reset()

    def apply_prediction_profile(self):
        if self.predictor:
            # todo: settings
            system_models = ["lm:system:en"]
            user_models = ["lm:user:en"]
            auto_learn_model = user_models
            self.predictor.set_models(system_models,
                                      user_models,
                                      auto_learn_model)

    def send_punctuation_prefix(self, key):
        if config.wp.auto_punctuation:
            if key.action_type == KeyCommon.KEYCODE_ACTION:
                char = key.get_label()
                prefix = self.punctuator.build_prefix(char) # unicode
                self.press_key_string(prefix)

    def send_punctuation_suffix(self):
        """
        Type the last part of the punctuation and possibly enable
        handle capitalization for the next key press
        """
        if config.wp.auto_punctuation:
            suffix = self.punctuator.build_suffix() # unicode
            if suffix and self.press_key_string(suffix):

                # unlatch left shift
                for key in self.find_keys_from_ids(["LFSH"]):
                    if key.active:
                        key.active = False
                        key.locked = False
                        if key in self._latched_sticky_keys:
                            self._latched_sticky_keys.remove(key)
                        if key in self._locked_sticky_keys:
                            self._locked_sticky_keys.remove(key)

                # latch right shift for capitalization
                for key in self.find_keys_from_ids(["RTSH"]):
                    key.active = True
                    key.locked = False
                    if not key in self._latched_sticky_keys:
                        self._latched_sticky_keys.append(key)
                self.vk.lock_mod(1)
                self.mods[1] = 1   # shift
                self.redraw()   # redraw the whole keyboard

    def cleanup(self):
        # reset still latched and locked modifier keys on exit
        self.release_latched_sticky_keys()
        self.release_locked_sticky_keys()
        self.unpress_timer.stop()

        for key in self.iter_keys():
            if key.pressed and key.action_type in \
                [KeyCommon.CHAR_ACTION,
                 KeyCommon.KEYSYM_ACTION,
                 KeyCommon.KEYPRESS_NAME_ACTION,
                 KeyCommon.KEYCODE_ACTION]:

                # Release still pressed enter key when onboard gets killed
                # on enter key press.
                _logger.debug("Releasing still pressed key '{}'" \
                              .format(key.id))
                self.send_release_key(key)

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
        self.set_visible(not config.has_window_decoration())
        self.set_sensitive(not config.xid_mode)

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

        active, locked = keyboard.cycle_sticky_key_state(
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
        self.set_sensitive(not config.xid_mode and \
                           not config.running_under_gdm and \
                           not config.lockdown.disable_preferences)


class BCQuit(ButtonController):

    id = "quit"

    def release(self, button, event_type):
        self.keyboard.emit_quit_onboard()

    def update(self):
        self.set_sensitive(not config.xid_mode and \
                           not config.lockdown.disable_quit)


class BCAutoLearn(ButtonController):

    id = "learnmode"

    def release(self, button, event_type):
        config.wp.auto_learn = not config.wp.auto_learn

        # don't learn when turning auto_learn off
        if not config.wp.auto_learn:
            self.keyboard.reset_text_context()

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
            self.keyboard.reset_text_context()

    def update(self):
        self.set_active(config.wp.stealth_mode)


class BCInputline(ButtonController):

    id = "inputline"

    def release(self, button, event_type):
        self.keyboard.hide_input_line()


