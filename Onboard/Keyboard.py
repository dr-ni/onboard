import gobject
import gtk
import string
import virtkey
import time

from Onboard.KeyGtk import *
from Onboard import KeyCommon
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
_logger = logging.getLogger("WordPredictor")
###############

class Keyboard:
    "Cairo based keyboard widget"

    # When set to a pane, the pane overlays the basePane.
    activePane = None
    active = None #Currently active key
    scanningActive = None # Key currently being scanned.
    altLocked = False
    scanning_x = None
    scanning_y = None

    last_auto_save_time = 0

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

    def __init__(self):
        self.vk = virtkey.virtkey()

        #List of keys which have been latched.
        #ie. pressed until next non sticky button is pressed.
        self.stuck = []
        self.tabKeys = []
        self.panes = [] # All panes except the basePane
        self.tabKeys.append(BaseTabKey(self, config.SIDEBARWIDTH))

        self.input_line = InputLine()
        self.punctuator = Punctuator()
        self.predictor  = None
        self.auto_learn = config.auto_learn
        self.auto_punctuation = config.auto_punctuation
        self.stealth_mode = config.stealth_mode

        self.word_prefix = ""
        self.word_choices = []

        # setup timer for auto saving modified dictionaries
        self.auto_save_interval = config.auto_save_interval  # in seconds
        self.add_timer(5, self._cb_auto_save_timer)

        # weighting - 0=100% frequency, 100=100% time
        self.frequency_time_ratio = config.frequency_time_ratio

    def destruct(self):
        self.clean()
        if self.predictor:
            self.predictor.save_dictionaries()

    def initial_update(self):
        """ called when the layout has been loaded """
        self.enable_word_prediction(config.word_prediction)
        self.update_ui()

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

    def get_key_at_location(self, location, *args, **kargs):
        pane = self.activePane or self.basePane
        return self.get_tabkey_at_location(location, *args, **kargs) or \
               pane.get_key_at_location(location, *args, **kargs)

    def get_tabkey_at_location(self, location, *args, **kargs):
        for tabkey in self.tabKeys:
             if(tabkey.pointWithinKey(self, *location)):
                  return tabkey
        return None

    def cb_dialog_response(self, widget, response, macroNo,macroEntry):
        self.set_new_macro(macroNo, response, macroEntry, widget)

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
                self.stuck.append(key)

            else:
                self.active_key = key #Since only one non-sticky key can be pressed at once.

            key.on = True

            # punctuation duties before keypress is sent
            self.send_punctuation_prefix(key)

            # press key
            self.send_press_key(key, button)

            # update input_line with pressed key
            if self.track_input(key):
                self.commit_input_line()

        else:
            if key in self.stuck:
                key.stuckOn = True
                self.stuck.remove(key)
            else:
                key.stuckOn = False
                self.send_release_key(key)

        #print self.input_line.valid,self.input_line.cursor,"'"+self.input_line.line+"'"
        self.update_buttons()
        self.queue_draw()


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
            try:
                mString = unicode(config.snippets[string.atoi(key.action)])
# If mstring exists do the below, otherwise the code in finally should always
# be done.
                if mString:
                    press_key_string(mString)
                    return

            except IndexError:
                pass

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
            self.vk.press_keycode(key.action)

        elif key.action_type == KeyCommon.SCRIPT_ACTION:
            run_script(key.action)

        elif key.action_type == KeyCommon.WORD_ACTION:
            s  = self.get_match_remainder(key.action) # unicode
            if self.auto_punctuation and button != 3:
                self.punctuator.set_end_of_word()
            self.press_key_string(s)

        elif key.action_type == KeyCommon.BUTTON_ACTION:
            self.button_pressed(key)

        else:
            for k in self.tabKeys: # don't like this.
                if k.pane == self.activePane:
                    k.on = False
                    k.stuckOn = False

            self.activePane = key.pane


    def release_key(self, key):
        # release the directly pressed key
        self.send_release_key(key)

        # add punctuation suffix
        cap_keys = None
        if self.auto_punctuation:
            suffix = self.punctuator.build_suffix() # unicode
            if self.press_key_string(suffix):
                # stuck keys off
                for key in self.find_keys_from_names(("LFSH",)):
                    if key.on or key.stuckOn:
                        key.on = False
                        key.stuckOn = False
                        if key in self.stuck:
                            self.stuck.remove(key)
                # capitalization on
                cap_keys = self.find_keys_from_names(("RTSH",))
                for key in cap_keys:
                    key.on = True
                    key.stuckOn = False
                    if key not in self.stuck:
                        self.stuck.append(key)
                self.vk.lock_mod(1)
                self.mods[1] = 1   # shift

        self.find_word_choices()
        self.update_ui()

        self.release_stuck_keys(cap_keys)

    def release_stuck_keys(self, except_keys = None):
        """ release stuck (modifier) keys """
        if len(self.stuck) > 0:
            for stick in self.stuck:
                if not except_keys or not stick in except_keys:
                    self.send_release_key(stick)
                    self.stuck.remove(stick)

    def send_release_key(self,key):
        if key.action_type == KeyCommon.CHAR_ACTION:
            self.vk.release_unicode(self.utf8_to_unicode(key.action))
        elif key.action_type == KeyCommon.KEYSYM_ACTION:
            self.vk.release_keysym(key.action)
        elif key.action_type == KeyCommon.KEYPRESS_NAME_ACTION:
            self.vk.release_keysym(get_keysym_from_name(key.action))
        elif key.action_type == KeyCommon.KEYCODE_ACTION:
            self.vk.release_keycode(key.action);
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
        if not key.action_type in (KeyCommon.CHAR_ACTION,
                               KeyCommon.KEYSYM_ACTION,
                               KeyCommon.KEYPRESS_NAME_ACTION,
                               KeyCommon.KEYCODE_ACTION,
                               KeyCommon.MACRO_ACTION,
                               KeyCommon.SCRIPT_ACTION,
                               KeyCommon.WORD_ACTION):
            self.activePane = None

        gobject.idle_add(self.release_key_idle,key) #Makes sure we draw key pressed before unpressing it.

    def release_key_idle(self,key):
        key.on = False
        self.queue_draw()
        return False


    def press_key_string(self, keystr):
        """
        Send key presses for all characters in a unicode string
        and keep track of the changes in input_line.
        """
        capitalize = False

        for ch in keystr:
            if ch == u"\b":   # backspace?
                keysym = get_keysym_from_name("backspace")
                self.vk.press_keysym  (keysym)
                self.vk.release_keysym(keysym)
                if not self.stealth_mode:
                    self.input_line.delete_left()

            elif ch == u"\x0e":  # set to upper case at sentence begin?
                capitalize = True

            else:             # any other printable keys
                self.vk.press_unicode(ord(ch))
                self.vk.release_unicode(ord(ch))
                if not self.stealth_mode:
                    self.input_line.insert(ch)

        return capitalize


    def track_input(self, key):
        """
        word prediction:
        Sync input_line with single key presses.
        WORD_ACTION and MACRO_ACTION do this in press_key_string.
        """
        end_editing = False

        if self.stealth_mode:
            return  True

        name = key.get_name().upper()
        char = key.get_label().decode("utf-8")
        #print  name," '"+char +"'",key.action_type
        if len(char) > 1:
            char = u""

        if key.action_type == KeyCommon.WORD_ACTION:
            pass # don't reset input on word insertion

        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            pass  # simply pressing a modifier shouldn't stop the word

        elif key.action_type == KeyCommon.BUTTON_ACTION:
            pass

        elif key.action_type == KeyCommon.KEYSYM_ACTION:
            if   name == 'ESC':
                self.input_line.reset()
            end_editing = True

        elif key.action_type == KeyCommon.KEYPRESS_NAME_ACTION:
            if   name == 'DELE':
                self.input_line.delete_right()
            elif name == 'LEFT':
                self.input_line.move_cursor(-1)
            elif name == 'RGHT':
                self.input_line.move_cursor(1)
            else:
                end_editing = True

        elif key.action_type == KeyCommon.KEYCODE_ACTION:
            if   name == 'RTRN':
                char = u"\n"
            elif name == 'SPCE':
                char = u" "
            elif name == 'TAB':
                char = u"\t"

            if name == 'BKSP':
                self.input_line.delete_left()
            elif self.input_line.is_printable(char):
                if self.mods[4]:  # ctrl+key press?
                    end_editing = True
                else:
                    self.input_line.insert(char)
            else:
                end_editing = True
        else:
            end_editing = True

        if not self.input_line.is_valid(): # cursor moved outside known range?
            end_editing = True

        #print end_editing,"'%s' " % self.input_line.line, self.input_line.cursor
        return end_editing

    def button_pressed(self, key):
        name = key.get_name()
        if   name == "stealthmode":
            self.set_stealth_mode(not self.stealth_mode)
        elif name == "learnmode":
            self.set_auto_learn(not self.get_auto_learn())
        elif name == "punctuation":
            self.set_auto_punctuation(not self.auto_punctuation)
        elif name == "inputline":
            self.commit_input_line()

    def update_ui(self):
        self.update_buttons()
        self.update_inputline()
        self.update_wordlists()
        self.queue_draw()

    def update_buttons(self):
        """ update the state of all keys of the button group """
        for key, pane in self.iter_keys():
            if key.action_type == KeyCommon.BUTTON_ACTION:
                name = key.get_name()
                if   name == "stealthmode":
                    key.checked = self.stealth_mode
                if   name == "learnmode":
                    key.checked = self.get_auto_learn()
                elif name == "punctuation":
                    key.checked = self.auto_punctuation

    def update_inputline(self):
        if self.predictor:
            for key, pane in self.iter_keys("inputline"):
                s = self.input_line.line
                if s:
                    pane.bring_group_to_front("inputline")
                    key.visible = True
                else:
                    s = u""
                    key.visible = False
                key.set_content(s, self.input_line.get_word_infos(), self.input_line.cursor)
                # print [(x.start, x.end) for x in word_infos]

    def update_wordlists(self):
        for pane in [self.basePane,] + self.panes:
            pane.update_wordlist(self, self.word_choices)

    def find_word_choices(self):
        """ word prediction: find choices, only once per key press """
        self.word_choices = []
        if self.predictor:
            #self.word_prefix  = self.input_line.get_word_before_cursor()
            context = self.input_line.get_context()
            self.word_choices = self.predictor.predict(context,
                                                     self.frequency_time_ratio)
            print "input_line='%s'" % self.input_line.line
#            
#            # update word information before the cursor
#            info = self.predictor.get_word_information(self.word_prefix)
#            wi = self.input_line.get_word_info_at_cursor()
#            if wi:
#                wi.set_info(bool(info), len(self.word_choices) > 0,
#                            bool(self.input_line.is_junk(self.word_prefix)))

#            # update remaining word information as needed
#            # needed when inserting punctuation, multiple words, snippets
#            #print [x.empty for x in self.input_line.get_word_infos()]
#            for wi in self.input_line.iter_outdated_word_infos():
#                _logger.info("updating remaining word info: " + wi.word)
#                choices = self.predictor.predict(wi.word)
#                info = self.predictor.get_word_information(wi.word)
#                wi.set_info(bool(info), len(choices) > 0,
#                            bool(self.input_line.is_junk(wi.word)))

    def get_match_remainder(self, index):
        """ returns the rest of matches[index] that hasn't been typed yet """
        text = self.input_line.get_context()
        word_prefix = self.predictor.get_last_context_token(text)
        print self.word_choices[index], word_prefix
        return self.word_choices[index][len(word_prefix):]

    def commit_input_line(self):
        """ word prediction: try to learn all words and clear the input line """
        changed = self.input_line.is_empty()

        if self.predictor and self.get_auto_learn():
            self.predictor.learn_text(self.input_line.line, True)

        self.punctuator.reset()
        self.input_line.reset()
        self.word_choices = []
        self.word_prefix = ""
        return changed

    def apply_prediction_profile(self):
        if self.predictor:
            # todo: settings
            auto_learn_dict = "%s/.sok/dictionaries/user.dict" \
                                  % os.path.expanduser("~")
            system_dicts = ["dictionaries/en.dict"]
            system_dicts = [os.path.join(config.install_dir, "dictionaries/en.dict")]
            user_dicts   = [auto_learn_dict]
            self.predictor.load_dictionaries(system_dicts,
                                             user_dicts,
                                             auto_learn_dict)

    def send_punctuation_prefix(self, key):
        if self.auto_punctuation:
            if key.action_type == KeyCommon.KEYCODE_ACTION:
                char = key.get_label().decode("utf-8")
                prefix = self.punctuator.build_prefix(char) # unicode
                self.press_key_string(prefix)

    def cb_word_prediction(self, enable):
        """ callback for gconf notifications """
        self.enable_word_prediction(enable)
        self.update_ui()

    def enable_word_prediction(self, enable):
        if enable:
            # only load dictionaries if there is a
            # dynamic or static wordlist in the layout
            if self.find_keys_from_names(("wordlist", "word0")):
                self.predictor  = WordPredictor()
                self.apply_prediction_profile()
            self.last_auto_save_time = time.time()
        else:
            if self.predictor:
                self.predictor.save_dictionaries()
            self.predictor = None

        for pane in [self.basePane,] + self.panes:
            pane.show_word_prediction_ui(enable)


    def cb_set_auto_learn(self, enable):
        """ callback for gconf notifications """
        self.set_auto_learn(enable)
        self.update_ui()

    def set_auto_learn(self, enable):
        self.auto_learn = enable         # don't rely on gconf being available
        if config.auto_learn != enable:  # don't recursively call gconf
            config.auto_learn = enable

        if not self.auto_learn:
            self.input_line.reset()      # don't learn when turning auto_learn off

        if self.auto_learn and self.stealth_mode:
            self.set_stealth_mode(False) # auto_learn on disables stealth_mode

    def get_auto_learn(self):
        return self.auto_learn and not self.stealth_mode

    def cb_set_auto_punctuation(self, enable):
        """ callback for gconf notifications """
        self.set_auto_punctuation(enable)
        self.update_ui()

    def set_auto_punctuation(self, enable):
        self.auto_punctuation = enable   # don't rely on gconf being available
        self.punctuator.reset()
        if config.auto_punctuation != enable:  # don't recursively call gconf
            config.auto_punctuation = enable

    def cb_set_auto_save_interval(self, seconds):
        """ callback for gconf notifications """
        self.auto_save_interval = seconds
        _logger.info("setting auto_save_interval to %d" % seconds)

    def _cb_auto_save_timer(self):
        if self.predictor and self.auto_save_interval:   # 0=no auto save
            t = time.time()
            if t - self.last_auto_save_time > self.auto_save_interval:
                self.last_auto_save_time = t
                self.predictor.save_dictionaries()
        return True # run again

    def cb_set_frequency_time_ratio(self, ratio):
        """ callback for gconf notifications """
        _logger.info("setting frequency_time_ratio to %d" % ratio)
        self.frequency_time_ratio = ratio
        self.update_ui()

    def cb_set_stealth_mode(self, enable):
        """ callback for gconf notifications """
        self.set_stealth_mode(enable)
        self.update_ui()

    def set_stealth_mode(self, enable):
        self.stealth_mode = enable         # don't rely on gconf being available
        if config.stealth_mode != enable:  # don't recursively call gconf
            config.stealth_mode = enable

        if self.stealth_mode:
            self.input_line.reset()        # don't learn, forget words

    def clean(self):
        for key, pane in self.iter_keys():
            if key.on: self.send_release_key(key)

    def find_keys_from_names(self, names):
        keys = []
        for key, pane in self.iter_keys():
            if key.name in names:
                keys.append(key)
        return keys

    def iter_keys(self, group=None):
        """ iterate through all keys or all keys of a group """
        for pane in [self.basePane,] + self.panes:
            if group:
                if group in pane.key_groups.keys():
                    for key in pane.key_groups[group]:
                        yield key,pane
            else:
                for group in pane.key_groups.values():
                    for key in group:
                        yield key,pane


