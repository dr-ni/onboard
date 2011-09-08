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

    color_scheme = None
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
        self.auto_release_keys = []

        self.next_mouse_click_button = 0
        self.move_start_position = None

        self.canvas_rect = Rect()

        self.button_controllers = {}

    def destruct(self):
        self.clean()

    def initial_update(self):
        """ called when the layout has been loaded """

        # connect button controllers to button keys
        types = [BCHide, BCShowClick, BCMiddleClick, BCSecondaryClick,
                 BCMove, BCQuit]
        for key in self.layout.iter_keys():
            if key.is_layer_button():
                bc = BCLayer(self, key)
                bc.layer_index = key.get_layer_index()
                self.button_controllers[key.id] = bc
            else:
                for type in types:
                    if type.id == key.id:
                        self.button_controllers[key.id] = type(self, key)

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
        key.pressed = True

        if not key.latched:
            if self.mods[8]:
                self.altLocked = True
                self.vk.lock_mod(8)

        if not key.sticky or not key.latched:
            self.send_press_key(key, button)

            # Modifier keys may change multiple keys -> redraw everything
            if key.action_type == KeyCommon.MODIFIER_ACTION:
                self.redraw()

        self.redraw(key)

    def release_key(self, key):
        if key.sticky:
            if not key.latched:
                key.latched = True

                # special case caps-lock key:
                # CAPS skips latched state and goes directly
                # into the locked position.
                if key.id in ["CAPS"]:
                    key.locked = True
                else:
                    self.auto_release_keys.append(key)

            elif not key.locked:
                self.auto_release_keys.remove(key)
                key.locked = True
            else:
                self.send_release_key(key)
                key.latched = False
                key.locked = False
                if key.action_type == KeyCommon.MODIFIER_ACTION:
                    self.redraw()   # redraw the whole keyboard
        else:
            self.send_release_key(key)

            # Don't release latched modifiers for click buttons right now.
            # Keep modifier keys unchanged until the actual click happens
            # -> allow clicks with modifiers
            if not (key.action_type == KeyCommon.BUTTON_ACTION and \
                key.id in ["middleclick", "secondaryclick"]):

                # release latched modifiers
                self.release_stuck_keys()

            # switch to layer 0
            if not key.is_layer_button():
                if self.active_layer_index != 0 and not self.layer_locked:
                   self.active_layer_index = 0
                   self.redraw()

        self.update_ui()

        self.unpress_key(key)

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
            controller = self.button_controllers.get(key.id)
            if controller:
                controller.press()


    def release_stuck_keys(self, except_keys = None):
        """ release stuck (modifier) keys """
        if len(self.auto_release_keys) > 0:
            for key in self.auto_release_keys[:]:
                if not except_keys or not key in except_keys:
                    self.send_release_key(key)
                    self.auto_release_keys.remove(key)
                    key.latched = False

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
            controller = self.button_controllers.get(key.id)
            if controller:
                controller.release()
        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            mod = key.action

            if not mod == 8:
                self.vk.unlock_mod(mod)

            self.mods[mod] -= 1

        if self.altLocked:
            self.altLocked = False
            self.vk.unlock_mod(8)

#        if key.action_type in [KeyCommon.MODIFIER_ACTION]:
#            self.active_layer_index = 0

    def unpress_key(self, key):
        # Makes sure we draw key pressed before unpressing it.
        GObject.idle_add(self.unpress_key_idle, key)

    def unpress_key_idle(self, key):
        key.pressed = False
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

    def update_ui(self):
        # update buttons
        for controller in self.button_controllers.values():
            controller.update()

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
            if key.latched:
                self.send_release_key(key)

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



class ButtonController(object):
    """
    MVC inspired Controller that handles events and the resulting 
    state changes of buttons.
    """
    def __init__(self, keyboard, key):
        self.keyboard = keyboard
        self.key = key

    def press(self):
        """ button pressed """
        pass

    def release(self):
        """ button released """
        pass

    def update(self):
        """ asynchronous ui update """
        pass

    def set_latched(self, latched = None):
        if not latched is None and self.key.latched != latched:
            self.key.latched = latched
            self.keyboard.redraw(self.key)

    def set_locked(self, locked = None):
        if not locked is None and self.key.locked != locked:
            self.key.locked = locked
            self.keyboard.redraw(self.key)


class BCHide(ButtonController):

    id = "hide"

    def release(self):
        window = self.keyboard.get_parent()
        window.toggle_visible()

class BCShowClick(ButtonController):

    id = "showclick"

    def release(self):
        config.show_click_buttons = not config.show_click_buttons
        #config.enable_decoration = not config.enable_decoration

    def update(self):
        self.set_latched(config.show_click_buttons)


class BCMiddleClick(ButtonController):

    id = "middleclick"

    def release(self):
        if self.keyboard.get_next_button_to_click() == 2:
            self.keyboard.set_next_mouse_click(None)
        else:
           self.keyboard.set_next_mouse_click(2)

    def update(self):
        self.set_latched(self.keyboard.get_next_button_to_click() == 2)


class BCSecondaryClick(ButtonController):

    id = "secondaryclick"

    def release(self):
        if self.keyboard.get_next_button_to_click() == 3:
            self.keyboard.set_next_mouse_click(None)
        else:
           self.keyboard.set_next_mouse_click(3)

    def update(self):
        self.set_latched(self.keyboard.get_next_button_to_click() == 3)


class BCMove(ButtonController):

    id = "move"

    def press(self):
        rootwin = Gdk.get_default_root_window()
        dunno, x, y, mods = rootwin.get_pointer()
        window = self.keyboard.get_window().get_parent()
        wx, wy = window.get_position()
        self.keyboard.move_start_position = (wx-x, wy-y)

    def release(self):
        self.keyboard.move_start_position = None


class BCQuit(ButtonController):

    id = "quit"

    def release(self):
        self.keyboard.emit_quit_onboard()


class BCLayer(ButtonController):

    layer_index = None

    def _get_id(self):
        return "layer" + str(self.layer_index)
    id = property(_get_id)

    def release(self):
        layer_index = self.key.get_layer_index()
        if self.keyboard.active_layer_index != layer_index:
            self.keyboard.active_layer_index = layer_index
            self.keyboard.layer_locked = False
            self.keyboard.redraw()
        elif self.layer_index != 0:
            if not self.keyboard.layer_locked:
                self.keyboard.layer_locked = True
            else:
                self.keyboard.active_layer_index = 0
                self.keyboard.layer_locked = False
                self.keyboard.redraw()

    def update(self):
        latched = self.key.get_layer_index() == self.keyboard.active_layer_index
        self.set_latched(latched)
        self.set_locked(latched and self.keyboard.layer_locked)


