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

class Keyboard:
    "Cairo based keyboard widget"

    # When set to a pane, the pane overlays the basePane.
    active = None #Currently active key
    scanningActive = None # Key currently being scanned.
    altLocked = False
    scanning_x = None
    scanning_y = None

### Properties ###

    _mods = {1:0,2:0, 4:0,8:0, 16:0,32:0,64:0,128:0}
    def _get_mod(self, key):
        return self._mods[key]
    def _set_mod(self, key, value):
        self._mods[key] = value
        self._on_mods_changed()
    mods = dictproperty(_get_mod, _set_mod)
    """ The number of pressed keys per modifier """

    def _get_activePane(self):
        panes = [self.basePane] + self.panes
        index = config.active_pane_index
        if index < 0 or index >= len(panes):
            index = 0
        return panes[index]
    def _set_activePane(self, pane):
        index = 0
        for i, pn in enumerate([self.basePane] + self.panes):
            if pn is pane:
                index = i
                break
        config.active_pane_index = index
    activePane = property(_get_activePane, _set_activePane)
    """ currently active pane objext """

    def assure_valid_activePane(self):
        """
        Reset pane index if it is out of range. e.g. due to 
        loading a layout with fewer panes.
        """
        panes = [self.basePane] + self.panes
        index = config.active_pane_index
        if index < 0 or index >= len(panes):
            config.active_pane_index = 0

##################

    def __init__(self, vk):
        self.vk = vk

        #List of keys which have been latched.
        #ie. pressed until next non sticky button is pressed.
        self.stuck = []
        self.tabKeys = []
        self.panes = [] # All panes except the basePane
        self.tabKeys.append(BaseTabKey(self, config.SIDEBARWIDTH))
        self.queue_draw()

    def initial_update(self):
        """ called when the layout has been loaded """
        self.assure_valid_activePane()

    def set_basePane(self, basePane):
        self.basePane = basePane #Pane which is always visible

    def add_pane(self, pane):
        self.panes.append(pane)
        self.tabKeys.append(TabKey(self, config.SIDEBARWIDTH, pane))

    def utf8_to_unicode(self,utf8Char):
        return ord(utf8Char.decode('utf-8'))

    def scan_tick(self): #at intervals scans across keys in the row and then down columns.
        if self.scanningActive:
            self.scanningActive.beingScanned = False

        if self.activePane:
            pane = self.activePane
        else:
            pane = self.basePane

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

    def is_key_pressed(self,key, widget, event):
        if(key.pointWithinKey(widget, event.x, event.y)):
            self.press_key(key)

    def _on_mods_changed(self):
        raise NotImplementedException()

    def press_key(self, key):
        if not self.vk:
            return

        if not key.on:
            if self.mods[8]:
                self.altLocked = True
                self.vk.lock_mod(8)

            if key.sticky == True:
                    self.stuck.append(key)

            else:
                self.active = key #Since only one non-sticky key can be pressed at once.

            key.on = True

            self.locked = []
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
                    for c in mString:
                        self.vk.press_unicode(ord(c))
                        self.vk.release_unicode(ord(c))
                    return

                if not config.xid_mode:  # block dialog in xembed mode

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
            else:
                for k in self.tabKeys: # don't like this.
                    if k.pane == self.activePane:
                        k.on = False
                        k.stuckOn = False

                self.activePane = key.pane
        else:
            if key in self.stuck:
                key.stuckOn = True
                self.stuck.remove(key)
            else:
                key.stuckOn = False
                self.release_key(key)

        self.queue_draw()

    def cb_dialog_response(self, dialog, response, snippet_id, \
                           label_entry, text_entry):
        if response == Gtk.ResponseType.OK:
            config.set_snippet(snippet_id, \
                               (label_entry.get_text(), text_entry.get_text()))
        dialog.destroy()

    def release_key(self,key):
        if not self.vk:
            return

        if key.action_type == KeyCommon.CHAR_ACTION:
            self.vk.release_unicode(self.utf8_to_unicode(key.action))
        elif key.action_type == KeyCommon.KEYSYM_ACTION:
            self.vk.release_keysym(key.action)
        elif key.action_type == KeyCommon.KEYPRESS_NAME_ACTION:
            self.vk.release_keysym(get_keysym_from_name(key.action))
        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            mod = key.action

            if not mod == 8:
                self.vk.unlock_mod(mod)

            self.mods[mod] -= 1

        elif key.action_type == KeyCommon.KEYCODE_ACTION:
            self.vk.release_keycode(key.action);

        elif key.action_type == KeyCommon.MACRO_ACTION:
            pass
        elif key.action_type == KeyCommon.SCRIPT_ACTION:
            if key.name == "middleClick":
                self.set_next_mouse_click(2)
            elif key.name == "secondaryClick":
                self.set_next_mouse_click(3)
        else:
            self.activePane = None

        if self.altLocked:
            self.altLocked = False
            self.vk.unlock_mod(8)

        # Makes sure we draw key pressed before unpressing it.
        GObject.idle_add(self.release_key_idle, key)

    def release_key_idle(self, key):
        key.on = False
        self.queue_draw()
        return False

    def set_next_mouse_click(self, button):
        """
        Converts the next mouse left-click to the click
        specified in @button. Possible values are 2 and 3.
        """
        try:
            osk.Util().convert_primary_click(button)
        except osk.error as error:
            _logger.warning(error)

    def clean(self):
        for pane in [self.basePane,] + self.panes:
            for group in pane.key_groups.values():
                for key in group:
                    if key.on: self.release_key(key)

        # Somehow keyboard objects don't get released
        # when switching layouts, there are still
        # excess references/memory leaks somewhere.
        # Therefore virtkey references have to be released
        # explicitely or Xlib runs out of client connections
        # after a couple dozen layout switches.
        self.vk = None

