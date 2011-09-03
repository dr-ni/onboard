### Logging ###
import logging
_logger = logging.getLogger("Keyboard")
###############

import string

from gi.repository import GObject, Gtk

from gettext import gettext as _

from Onboard.KeyGtk import *
from Onboard import KeyCommon

import osk

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

class Keyboard:
    "Cairo based keyboard widget"

    scanningActive = None # Key currently being scanned.
    altLocked = False
    scanning_x = None
    scanning_y = None
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
        Reset pane index if it is out of range. e.g. due to
        loading a layout with fewer panes.
        """
        index = self.active_layer_index
        if index < 0 or index >= len(self.get_layers()):
            self.active_layer_index = 0

##################

    def __init__(self, vk):
        self.vk = vk

        #List of keys which have been latched.
        #ie. pressed until next non sticky button is pressed.
        self.stuck = []

        self.next_mouse_click_button = 0
        self.move_start_position = None

        self.canvas_rect = Rect()

    def destruct(self):
        self.clean()

    def initial_update(self):
        """ called when the layout has been loaded """
        self.assure_valid_active_layer()
        self.update_ui()

    def get_layers(self):
        if self.layout:
            return self.layout.get_layer_ids()
        return []

    def iter_keys(self, group_name=None):
        """ iterate through all keys or all keys of a group """
        return self.layout.iter_keys(group_name)

    def utf8_to_unicode(self,utf8Char):
        return ord(utf8Char.decode('utf-8'))

    def scan_tick(self): #at intervals scans across keys in the row and then down columns.
        if self.scanningActive:
            self.scanningActive.beingScanned = False

        pane = self.active_layer

        if not self.scanning_y == None:
            self.scanning_y = (self.scanning_y + 1) % len(pane.columns[self.scanning_x])
        else:
            self.scanning_x = (self.scanning_x + 1) % len(pane.columns)

        if self.scanning_y == None:
            y = 0
        else:
            y = self.scanning_y

        self.scanningActive = pane.columns[self.scanning_x][y]

        self.scanningActive.beingScanned = True
        self.queue_draw()

        return True

    def get_key_at_location(self, location):
        # First try all keys of the active layer
        for item in reversed(list(self.layout.iter_layer_keys(self.active_layer))):
            if item.is_point_within(location):
                return item

        # Then check all non-layer keys (layout switcher, hide, etc.)
        for item in reversed(list(self.layout.iter_layer_keys(None))):
            if item.is_point_within(location):
                return item

    def cb_dialog_response(self, dialog, response, snippet_id, \
                           label_entry, text_entry):
        if response == Gtk.ResponseType.OK:
            label = label_entry.get_text().decode("utf-8")
            text = text_entry.get_text().decode("utf-8")
            config.set_snippet(snippet_id, (label, text))
        dialog.destroy()

    def cb_macroEntry_activate(self,widget,macroNo,dialog):
        self.set_new_macro(macroNo, gtk.RESPONSE_OK, widget, dialog)

    def set_new_macro(self,macroNo,response,macroEntry,dialog):
        if response == gtk.RESPONSE_OK:
            config.set_snippet(macroNo, macroEntry.get_text())

        dialog.destroy()

    def _on_mods_changed(self):
        raise NotImplementedException()


    def press_key(self, key, button=1):
        if not key.on:
            if self.mods[8]:
                self.altLocked = True
                self.vk.lock_mod(8)

            if key.sticky == True:
                # special case:
                # CAPS lock skips latched state and goes directly
                # into the locked position.
                if key.id == "CAPS":
                    key.stuckOn = True
                else:
                    self.stuck.append(key)
            else:
                self.active_key = key #Since only one non-sticky key can be pressed at once.

            key.on = True

            # press key
            self.send_press_key(key, button)
        else:
            if key in self.stuck:
                key.stuckOn = True
                self.stuck.remove(key)
            else:
                key.stuckOn = False
                self.send_release_key(key)

        self.update_buttons()

        # Do we need to draw the whole keyboard?
        if key.sticky:
            self.redraw()
        else:
            self.redraw(key)  # no, just one key


    def send_press_key(self, key, button=1):

        if key.action_type == KeyCommon.CHAR_ACTION:
            self.vk.press_unicode(self.utf8_to_unicode(key.action))

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
            snippet_id = string.atoi(key.action)
            mlabel, mString = config.snippets.get(snippet_id, (None, None))
            if mString:
                self.press_key_string(mString)

            elif not config.xid_mode:  # block dialog in xembed mode
                dialog = Gtk.Dialog(_("New snippet"),
                                    self.get_toplevel(), 0,
                                    (Gtk.STOCK_CANCEL,
                                     Gtk.ResponseType.CANCEL,
                                     _("_Save snippet"),
                                     Gtk.ResponseType.OK))

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

        elif key.action_type == KeyCommon.KEYCODE_ACTION:
            self.vk.press_keycode(key.action)

        elif key.action_type == KeyCommon.SCRIPT_ACTION:
            if not config.xid_mode:  # block settings dialog in xembed mode
                if key.action:
                    run_script(key.action)

        elif key.action_type == KeyCommon.BUTTON_ACTION:
            # Layer switching key?
            if key.is_layer_button():
                layer_index = key.get_layer_index()
                if key.on:
                    self.active_layer_index = layer_index
                else:
                    self.active_layer_index = 0

            elif key.id == "move":
                rootwin = Gdk.get_default_root_window()
                dunno, x, y, mods = rootwin.get_pointer()
                window = self.get_window().get_parent()
                wx, wy = window.get_position()
                self.move_start_position = (wx-x, wy-y)

            else:
                # all other buttons act on release only
                pass


    def release_key(self, key):
        # release the directly pressed key
        self.send_release_key(key)

        # click buttons keep the modifier keys unchanged until
        # the click happens -> allow clicks with modifiers
        if not (key.action_type == KeyCommon.BUTTON_ACTION and \
            key.id in ["middleclick", "secondaryclick"]):

            # release latched modifiers
            self.release_stuck_keys()

        self.update_ui()

    def release_stuck_keys(self, except_keys = None):
        """ release stuck (modifier) keys """
        if len(self.stuck) > 0:
            for key in self.stuck[:]:
                if not except_keys or not key in except_keys:
                    self.send_release_key(key)
                    self.stuck.remove(key)

            # modifiers may change many key labels -> redraw everything
            self.redraw()

    def send_release_key(self,key):
        if key.action_type == KeyCommon.CHAR_ACTION:
            self.vk.release_unicode(self.utf8_to_unicode(key.action))
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
            # Handle button activation on mouse release. This way remapped
            # pointer buttons don't cause press/release message pairs with
            # different buttons.
            self.button_released(key)
        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            mod = key.action

            if not mod == 8:
                self.vk.unlock_mod(mod)

            self.mods[mod] -= 1

        if self.altLocked:
            self.altLocked = False
            self.vk.unlock_mod(8)

        self.release_key_state(key)

    def release_key_state(self,key):
        if key.action_type in [KeyCommon.MODIFIER_ACTION]:
            self.active_layer_index = 0

        # Makes sure we draw key pressed before unpressing it.
        GObject.idle_add(self.release_key_idle, key)

    def release_key_idle(self, key):
        key.on = False
        self.redraw(key)
        return False


    def press_key_string(self, keystr):
        """
        Send key presses for all characters in a unicode string
        and keep track of the changes in input_line.
        """
        capitalize = False

        keystr = keystr.replace(u"\\n", u"\n")

        for ch in keystr:
            if ch == u"\b":   # backspace?
                keysym = get_keysym_from_name("backspace")
                self.vk.press_keysym  (keysym)
                self.vk.release_keysym(keysym)
            elif ch == u"\n":
                # press_unicode("\n") fails in gedit.
                # -> explicitely send the key symbol instead
                keysym = get_keysym_from_name("return")
                self.vk.press_keysym  (keysym)
                self.vk.release_keysym(keysym)
            else:             # any other printable keys
                self.vk.press_unicode(ord(ch))
                self.vk.release_unicode(ord(ch))

        return capitalize

    def button_released(self, key):
        key_id = key.get_id()

        if key_id == "showclick":
            config.show_click_buttons = not config.show_click_buttons
            #config.enable_decoration = not config.enable_decoration

        elif key_id == "middleclick":
            if self.get_next_button_to_click() == 2:
                self.set_next_mouse_click(None)
            else:
               self.set_next_mouse_click(2)

        elif key_id == "secondaryclick":
            if self.get_next_button_to_click() == 3:
                self.set_next_mouse_click(None)
            else:
               self.set_next_mouse_click(3)

        elif key.id == "move":
            self.move_start_position = None

        elif key.id == "quit":
            self._emit_quit_onboard()

    def update_ui(self):
        self.update_buttons()
        self.update_layout()

    def update_layout(self):
        layout = self.layout

        # show/hide layers
        layers = layout.get_layer_ids()
        if layers:
            layout.set_visible_layers([layers[0], self.active_layer])

        # show/hide click buttons
        groups = layout.get_key_groups()
        for key in groups["click"]:
            key.visible = config.show_click_buttons

        # show/hide move button
        #keys = self.find_keys_from_ids(["move"])
        #for key in keys:
        #    key.visible = not config.enable_decoration

        # recalculate items rectangles
        layout.fit_inside_canvas(self.canvas_rect)

        # recalculate font sizes
        self.update_font_sizes()

    def update_buttons(self):
        """ update the state of all button "keys" """
        for key in self.iter_keys():
            if key.action_type == KeyCommon.BUTTON_ACTION:
                key_id = key.get_id()

                checked = None

                # click buttons
                if key_id == "showclick":
                    checked = config.show_click_buttons
                elif key_id == "middleclick":
                    checked = (self.get_next_button_to_click() == 2)
                elif key_id == "secondaryclick":
                    checked = (self.get_next_button_to_click() == 3)

                # layer buttons
                if key.is_layer_button():
                    layer_index = key.get_layer_index()
                    checked = (layer_index == self.active_layer_index)

                # redraw on changes
                if not checked is None and \
                   key.checked != checked:
                    key.checked = checked
                    self.redraw(key)


    def on_outside_click(self):
        # release latched modifier keys
        if self.next_mouse_click_button:
            self.release_stuck_keys()

        self.next_mouse_click_button = None
        self.update_ui()


    def set_next_mouse_click(self, button):
        """
        Converts the next mouse left-click to the click
        specified in @button. Possible values are 2 and 3.
        """
        try:
            if not button is None:
                osk.Util().convert_primary_click(button)
                self.next_mouse_click_button = button
        except osk.Util().error as error:
            _logger.warning(error)

    def get_next_button_to_click(self):
        """
        Returns the button given to set_next_mouse_click.
        returns None if there is currently no special button
        scheduled to be clicked.
        """
        return self.next_mouse_click_button


    def clean(self):
        for key in self.iter_keys():
            if key.on: self.send_release_key(key)

        # Somehow keyboard objects don't get released
        # when switching layouts, there are still
        # excess references/memory leaks somewhere.
        # Therefore virtkey references have to be released
        # explicitely or Xlib runs out of client connections
        # after a couple dozen layout switches.
        self.vk = None

    def find_keys_from_ids(self, key_ids):
        keys = []
        for key in self.iter_keys():
            if key.id in key_ids:
                keys.append(key)
        return keys



