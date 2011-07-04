"""
File containing Config singleton.
"""

import os
import sys
from shutil import copytree
from optparse import OptionParser
from gettext import gettext as _

from gi.repository import Gtk

from Onboard.ConfigUtils import ConfigObject

### Logging ###
import logging
_logger = logging.getLogger("Config")
###############

# gsettings objects
ONBOARD_BASE = "apps.onboard"
THEME_BASE   = "apps.onboard.theme"
ICP_BASE     = "apps.onboard.icon-palette"
GSS_BASE     = "org.gnome.desktop.screensaver"
MODELESS_GKSU_KEY = "/apps/gksu/disable-grab"  # old gconf key, unused

# hard coded defaults
DEFAULT_X                  = 0
DEFAULT_Y                  = 0
DEFAULT_HEIGHT             = 800
DEFAULT_WIDTH              = 300

DEFAULT_LAYOUT             = "Classic Onboard"
DEFAULT_THEME              = "Classic Onboard"
DEFAULT_COLOR_SCHEME       = "Classic Onboard"

DEFAULT_SCANNING_INTERVAL  = 750

DEFAULT_ICP_X              = 40
DEFAULT_ICP_Y              = 300
DEFAULT_ICP_HEIGHT         = 80
DEFAULT_ICP_WIDTH          = 80

START_ONBOARD_XEMBED_COMMAND = "onboard --xid"

GTK_KBD_MIXIN_MOD          = "Onboard.KeyboardGTK"
GTK_KBD_MIXIN_CLS          = "KeyboardGTK"

INSTALL_DIR                = "/usr/share/onboard"
USER_DIR                   = ".onboard"

SYSTEM_DEFAULTS_FILENAME   = "onboard-defaults.conf"



class Config(ConfigObject):
    """
    Singleton Class to encapsulate the gsettings stuff and check values.
    """

    # String representation of the module containing the Keyboard mixin
    # used to draw keyboard
    _kbd_render_mixin_mod = GTK_KBD_MIXIN_MOD

    # String representation of the keyboard mixin used to draw keyboard.
    _kbd_render_mixin_cls = GTK_KBD_MIXIN_CLS

    # A copy of snippets so that when the list changes in gsettings we can
    # tell which items have changed.
    _last_snippets = None

    # Width of sidebar buttons
    SIDEBARWIDTH = 60

    # Offset of label from key edge when not specified in layout
    DEFAULT_LABEL_OFFSET = (2.0, 0.0)

    # Margin to leave around labels
    LABEL_MARGIN = (4, 4)

    # layout group for independently sized superkey labels
    SUPERKEY_SIZE_GROUP = "super"

    def __new__(cls, *args, **kwargs):
        """
        Singleton magic.
        """
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls, args, kwargs)
            super(Config, cls.self).__init__()  # call base class constructor
            cls.self.init()
        return cls.self

    def __init__(self):
        """
        This constructor is still called multiple times.
        Do nothing here, don't call base classes constructor.
        """
        pass

    def init(self):
        """
        Singleton constructor, should only run once.
        """
        _logger.debug("Entered in _init")

        # parse command line
        parser = OptionParser()
        parser.add_option("-l", "--layout", dest="layout",
                help="Specify layout file (.onboard) or name")
        parser.add_option("-t", "--theme", dest="theme",
                help="Specify theme file (.theme) or name")
        parser.add_option("-x", type="int", dest="x", help="x coord of window")
        parser.add_option("-y", type="int", dest="y", help="y coord of window")
        parser.add_option("-s", "--size", dest="size",
                help="size widthxheight")
        parser.add_option("-e", "--xid", action="store_true", dest="xid_mode",
                help="XEmbed mode for gnome-screensaver")
        parser.add_option("-d", "--debug", type="str", dest="debug",
            help="DEBUG={notset|debug|info|warning|error|critical}")
        options = parser.parse_args()[0]

        if options.debug:
            logging.basicConfig(level=getattr(logging, options.debug.upper()))
        else:
            logging.basicConfig()

        # migrate old user dir ".sok" to ".onboard"
        old_user_dir = os.path.join(os.path.expanduser("~"), ".sok")
        user_dir = self.user_dir
        if not os.path.exists(user_dir) and os.path.exists(old_user_dir):
            _logger.info(_("Migrating user directory '{}' to '{}'.") \
                          .format(old_user_dir, user_dir))
            try:
                copytree(old_user_dir, user_dir)
            except OSError as ex: # python >2.5
                _logger.error(_("Failed to migrate user directory. ") + str(ex))

        # Load system defaults (if there are any, not required).
        # Used for distribution specific settings, aka branding.
        paths = [os.path.join(self.install_dir, SYSTEM_DEFAULTS_FILENAME),
                 os.path.join("/etc/onboard", SYSTEM_DEFAULTS_FILENAME)]
        self.load_system_defaults(paths)

        # initialize all property values
        self.init_properties(options)

        # Special case for keyboard size
        if (options.size):
            size = options.size.split("x")
            self.width  = int(size[0])
            self.height = int(size[1])

        # load theme
        global Theme
        from Onboard.Appearance import Theme
        theme_filename = self.theme_filename
        _logger.info(_("Loading theme from '{}'").format(theme_filename))

        theme = Theme.load(theme_filename)
        if not theme:
            _logger.error(_("Unable to read theme '{}'").format(theme_filename))
        else:
            # save to gsettings only if theme came from the command line
            save = bool(options.theme)
            self.set_theme_filename(theme_filename, save)
            theme.apply(save)

        # misc initializations
        self.xid_mode = options.xid_mode
        self._last_snippets = dict(self.snippets)  # store a copy

        _logger.debug("Leaving _init")

    def _init_keys(self):
        """ Create key descriptions """

        self.gspath = ONBOARD_BASE
        self.sysdef_section = "main"

        self.add_key("use-system-defaults", False)
        self.add_key("x", DEFAULT_X)
        self.add_key("y", DEFAULT_Y)
        self.add_key("width", DEFAULT_WIDTH)
        self.add_key("height", DEFAULT_HEIGHT)
        self.layout_key = \
        self.add_key("layout", DEFAULT_LAYOUT, prop="layout_filename")
        self.theme_key  = \
        self.add_key("theme",  DEFAULT_THEME,  prop="theme_filename")
        self.add_key("enable-scanning", False)
        self.add_key("scanning-interval", DEFAULT_SCANNING_INTERVAL)
        self.add_key("snippets", {})
        self.add_key("show-status-icon", False)
        self.add_key("start-minimized", False)
        self.add_key("xembed-onboard", False, "onboard_xembed_enabled")
        self.add_key("key-label-font", "")      # default font for all themes
        self.add_key("key-label-overrides", {}) # default labels for all themes
        self.add_key("current-settings-page", 0)

        self.theme = ConfigTheme(self)
        self.icp = ConfigICP(self)
        self.gss = ConfigGSS(self)

        self.children = [self.theme, self.icp, self.gss]
 
    ##### handle special keys only valid in system defaults #####
    def read_sysdef_section(self, parser):
        super(self.__class__, self).read_sysdef_section(parser)

        # Convert the simplified superkey_label setting into
        # the more general key_label_overrides setting.
        sds = self.system_defaults
        if "superkey_label" in sds:
            overrides = sds.get( "key_label_overrides", {})
            group = self.SUPERKEY_SIZE_GROUP \
                if sds.get("superkey_label_independent_size") else ""
            for key_id in ["LWIN", "RWIN"]:
                overrides[key_id] = (sds["superkey_label"], group)
            sds["key_label_overrides"] = overrides

    def convert_sysdef_key(self, gskey, sysdef, value):
        # key exclusive to system defaults?
        if sysdef in ["superkey-label", \
                      "superkey-label-independent-size"]:
            return value
        else:
            return super(self.__class__, self). \
                         convert_sysdef_key(gskey, sysdef, value)


    ##### property helpers #####
    def position_notify_add(self, callback):
        self.x_notify_add(callback)
        self.y_notify_add(callback)

    def geometry_notify_add(self, callback):
        self.width_notify_add(callback)
        self.height_notify_add(callback)

    def _can_set_x(self, value):
        return self.width + value > 1

    def _can_set_y(self, value):
        return self.height + value > 1

    def _can_set_width(self, value):
        return value > 0

    def _can_set_height(self, value):
        return value > 0

    def _can_set_layout(self, filename):
        if not os.path.exists(filename):
            _logger.warning(_("layout '%s' does not exist") % filename)
            return False
        return True

    def get_layout_filename(self):
        return self._get_user_sys_filename(
             gskey                = self.layout_key,
             user_filename_func   = lambda x: \
                 os.path.join(self.user_dir,    "layouts", x) + ".onboard",
             system_filename_func = lambda x: \
                 os.path.join(self.install_dir, "layouts", x) + ".onboard",
             final_fallback       = os.path.join(self.install_dir,
                                                 "layouts", DEFAULT_LAYOUT))
    def get_theme_filename(self):
        return self._get_user_sys_filename(
             gskey                = self.theme_key,
             user_filename_func   = Theme.build_user_filename,
             system_filename_func = Theme.build_system_filename,
             final_fallback       = os.path.join(self.install_dir,
                                                 "themes", DEFAULT_THEME))
    def _can_set_theme(self, filename):
        if not os.path.exists(filename):
            _logger.warning(_("theme '%s' does not exist") % filename)
            return False
        return True

    def _can_set_color_scheme(self, filename):
        if not os.path.exists(filename):
            _logger.warning(_("color scheme '%s' does not exist") % filename)
            return False
        return True

    def _gsettings_get_key_label_overrides(self, gskey):
        return self._gsettings_list_to_dict(gskey)

    def _gsettings_set_key_label_overrides(self, gskey, value):
        self._dict_to_gsettings_list(gskey, value)

    def _gsettings_get_snippets(self, gskey):
        return self._gsettings_list_to_dict(gskey, int)

    def _gsettings_set_snippets(self, gskey, value):
        self._dict_to_gsettings_list(gskey, value)


    ####### Snippets editing #######
    def set_snippet(self, index, value):
        """
        Set a snippet in the snippet list.  Enlarge the list if not big
        enough.

        @type  index: int
        @param index: index of the snippet to set.
        @type  value: str
        @param value: Contents of the new snippet.
        """
        if value == None:
            raise TypeError("Snippet text must be str")

        label, text = value
        snippets = self.snippets
        _logger.info("Setting snippet %d to '%s', '%s'" % (index, label, text))
        snippets[index] = (label, text)
        self.snippets = snippets

    def del_snippet(self, index):
        """ 
        Delete a snippet.

        @type  index: int
        @param index: index of the snippet to delete.
        """
        _logger.info("Deleting snippet %d" % index)
        snippets = self.snippets
        del snippets[index]
        self.snippets = snippets

    # Add another callback system for snippets: called once per modified snippet.
    # The automatically provided callback list, the one connected to
    # gsettings changed signals, is still "_snippets_callbacks" (snippet*s*).
    _snippet_callbacks = []
    def snippet_notify_add(self, callback):
        """
        Register callback to be run for each snippet that changes

        Callbacks are called with the snippet index as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._snippet_callbacks.append(callback)

    def _post_notify_snippets(self):
        """
        Hook into snippets notification and run single snippet callbacks.
        """
        if self._last_snippets is None:
            return

        snippets = self.snippets

        # If the snippets in the two lists don't have the same value or one
        # list has more items than the other do callbacks for each item that
        # differs
        diff = set(snippets.keys()).symmetric_difference( \
                   self._last_snippets.keys())
        for index in diff:
            for callback in self._snippet_callbacks:
                callback(index)

        self._last_snippets = dict(self.snippets) # store a copy


    ###### gnome-screensaver, xembedding #####
    def is_onboard_in_xembed_command_string(self):
        """
        Checks whether the gsettings key for the embeded application command
        contains the entry defined by onboard.
        Returns True if it is set to onboard and False otherwise.
        """
        if self.gss.embedded_keyboard_command == START_ONBOARD_XEMBED_COMMAND:
            return True
        else:
            return False

    def set_xembed_command_string_to_onboard(self):
        """
        Write command to start the embedded onboard into the corresponding
        gsettings key.
        """
        self.gss.embedded_keyboard_command = START_ONBOARD_XEMBED_COMMAND

    def _get_kbd_render_mixin(self):
        __import__(self._kbd_render_mixin_mod)
        return getattr(sys.modules[self._kbd_render_mixin_mod],
                self._kbd_render_mixin_cls)
    kbd_render_mixin = property(_get_kbd_render_mixin)


    # modeless gksu - disabled until gksu moves to gsettings
    def modeless_gksu_notify_add(self, callback):
        pass
    modeless_gksu = property(lambda self: False)


    def _get_install_dir(self):
        # ../Config.py
        path = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))

        # when run uninstalled
        local_data_path = os.path.join(path, "data")
        if os.path.isfile(os.path.join(local_data_path, "onboard.svg")):
            # Add the data directory to the icon search path
            icon_theme = Gtk.IconTheme.get_default()
            icon_theme.append_search_path(local_data_path)
            return path
        # when installed
        elif os.path.isdir(INSTALL_DIR):
            return INSTALL_DIR
    install_dir = property(_get_install_dir)

    def _get_user_dir(self):
        return os.path.join(os.path.expanduser("~"), USER_DIR)
    user_dir = property(_get_user_dir)


class ConfigICP(ConfigObject):
    """ Icon palette configuration """

    def _init_keys(self):
        self.gspath = ICP_BASE
        self.sysdef_section = "icon-palette"

        self.add_key("in-use", False)
        self.add_key("x", DEFAULT_ICP_X)
        self.add_key("y", DEFAULT_ICP_Y)
        self.add_key("width", DEFAULT_ICP_WIDTH)
        self.add_key("height", DEFAULT_ICP_HEIGHT)

    ##### property helpers #####
    def position_notify_add(self, callback):
        self.x_notify_add(callback)
        self.y_notify_add(callback)

    def size_notify_add(self, callback):
        self.width_notify_add(callback)
        self.height_notify_add(callback)

    def _can_set_x(self, value):
        return value >= 0

    def _can_set_y(self, value):
        return value >= 0

    def _can_set_width(self, value):
        return value > 0

    def _can_set_height(self, value):
        return value > 0


class ConfigTheme(ConfigObject):
    """ Theme configuration """

    def _init_keys(self):
        self.gspath = THEME_BASE
        self.sysdef_section = "theme"

        self.add_key("color-scheme", DEFAULT_COLOR_SCHEME,
                     prop="color_scheme_filename")
        self.add_key("key-style", "flat")
        self.add_key("roundrect-radius", 0)
        self.add_key("key-fill-gradient", 0)
        self.add_key("key-stroke-gradient", 0)
        self.add_key("key-gradient-direction", 0)
        self.key_label_font_key = \
        self.add_key("key-label-font", "")      # font for current theme
        self.key_label_overrides_key = \
        self.add_key("key-label-overrides", {}) # labels for current theme

    ##### property helpers #####
    def theme_attributes_notify_add(self, callback):
        self.key_style_notify_add(callback)
        self.roundrect_radius_notify_add(callback)
        self.key_fill_gradient_notify_add(callback)
        self.key_stroke_gradient_notify_add(callback)
        self.key_gradient_direction_notify_add(callback)
        self.key_label_font_notify_add(callback)
        self.key_label_overrides_notify_add(callback)
        self.key_style_notify_add(callback)

    def _gsettings_get_key_label_overrides(self, gskey):
        return self._gsettings_list_to_dict(gskey)

    def _gsettings_set_key_label_overrides(self, gskey, value):
        self._dict_to_gsettings_list(gskey, value)

    def get_key_label_overrides(self):
        gskey = self.key_label_overrides_key

        # merge with default value from onboard base config
        value = dict(self.parent.key_label_overrides)
        value.update(gskey.value)

        return value

    def get_key_label_font(self):
        gskey = self.key_label_font_key

        value = gskey.value
        if not value:
            # get default value from onboard base config instead
            value = self.parent.key_label_font

        return value


class ConfigGSS(ConfigObject):
    """ gnome-screen-saver configuration keys"""

    def _init_keys(self):
        self.gspath = GSS_BASE
        self.sysdef_section = "gnome-screen-saver"

        self.add_key("embedded-keyboard-enabled", True)
        self.add_key("embedded-keyboard-command", "")

