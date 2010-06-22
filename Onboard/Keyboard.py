### Logging ###
import logging
_logger = logging.getLogger("Keyboard")
###############

import gobject
import gtk
import string

from Onboard.KeyGtk import *
from Onboard import KeyCommon

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
    activePane = None
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
                try:
                    mString = unicode(config.snippets[string.atoi(key.action)])
# If mstring exists do the below, otherwise the code in finally should always
# be done.
                    if mString:
                        for c in mString:
                            self.vk.press_unicode(ord(c))
                            self.vk.release_unicode(ord(c))
                        return

                except IndexError:
                    pass

                if not config.xid_mode:  # block dialog in xembed mode

                    dialog = gtk.Dialog("No snippet", self.parent, 0,
                            ("_Save snippet", gtk.RESPONSE_OK,
                             "_Cancel", gtk.RESPONSE_CANCEL))
                    dialog.vbox.add(gtk.Label(
                        "No snippet for this button,\nType new snippet"))

                    macroEntry = gtk.Entry()

                    dialog.connect("response", self.cb_dialog_response,string.atoi(key.action), macroEntry)

                    macroEntry.connect("activate", self.cb_macroEntry_activate,string.atoi(key.action), dialog)
                    dialog.vbox.pack_end(macroEntry)

                    dialog.show_all()

            elif key.action_type == KeyCommon.KEYCODE_ACTION:
                self.vk.press_keycode(key.action);

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


    def cb_dialog_response(self, widget, response, macroNo,macroEntry):
        self.set_new_macro(macroNo, response, macroEntry, widget)

    def cb_macroEntry_activate(self,widget,macroNo,dialog):
        self.set_new_macro(macroNo, gtk.RESPONSE_OK, widget, dialog)

    def set_new_macro(self,macroNo,response,macroEntry,dialog):
        if response == gtk.RESPONSE_OK:
            config.set_snippet(macroNo, macroEntry.get_text())

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
                self.map_pointer_button(2) # map middle button to primary
            elif key.name == "secondaryClick":
                self.map_pointer_button(3) # map secondary button to primary


        else:
            self.activePane = None


        if self.altLocked:
            self.altLocked = False
            self.vk.unlock_mod(8)

        gobject.idle_add(self.release_key_idle,key) #Makes sure we draw key pressed before unpressing it.

    def release_key_idle(self,key):
        key.on = False
        self.queue_draw()
        return False

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

