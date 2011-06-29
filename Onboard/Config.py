"""
File containing Config singleton.
"""

import os
import sys
from optparse import OptionParser
import ConfigParser as configparser
from gettext import gettext as _

from gi.repository import Gio, Gtk

from Onboard.utils import pack_name_value_list, unpack_name_value_list

### Logging ###
import logging
_logger = logging.getLogger("Config")
###############

# gsettings base objects
BASE_KEY        = "apps.onboard"
THEME_BASE_KEY  = "apps.onboard.theme"
ICP_BASE_KEY    = "apps.onboard.icon-palette"
GSS_BASE_KEY    = "org.gnome.desktop.screensaver"


START_ONBOARD_XEMBED_COMMAND = "onboard --xid"

MODELESS_GKSU_KEY = "/apps/gksu/disable-grab"

DEFAULT_LAYOUT             = "Classic Onboard.onboard"
DEFAULT_THEME              = "Classic Onboard.theme"
DEFAULT_COLORS             = "Classic Onboard.colors"

KEYBOARD_DEFAULT_HEIGHT    = 800
KEYBOARD_DEFAULT_WIDTH     = 300

SCANNING_DEFAULT_INTERVAL  = 750

ICP_DEFAULT_HEIGHT         = 80
ICP_DEFAULT_WIDTH          = 80
ICP_DEFAULT_X_POSITION     = 40
ICP_DEFAULT_Y_POSITION     = 300

GTK_KBD_MIXIN_MOD          = "Onboard.KeyboardGTK"
GTK_KBD_MIXIN_CLS          = "KeyboardGTK"

INSTALL_DIR                = "/usr/share/onboard"
USER_DIR                   = ".onboard"

class Config (object):
    """
    Singleton Class to encapsulate the gsettings stuff and check values.
    """

    _kbd_render_mixin_mod = GTK_KBD_MIXIN_MOD
    """
    String representation of the module containing the Keyboard mixin
    used to draw keyboard
    """

    _kbd_render_mixin_cls = GTK_KBD_MIXIN_CLS
    """
    String representation of the keyboard mixin used to draw keyboard.
    """

    _option_height = None
    """ Height when set on cmd line """

    _option_width = None
    """ Width when set on cmd line """

    _last_snippets = None
    """
    A copy of snippets so that when the list changes in gsettings we can 
    tell which items have changed.
    """

    SIDEBARWIDTH = 60
    """ Width of sidebar buttons """

    DEFAULT_LABEL_OFFSET = (2.0, 0.0)
    """ Offset of label from key edge when not specified in layout"""

    LABEL_MARGIN = (4,4)
    """ Margin to leave around labels """

    SUPERKEY_SIZE_GROUP = "super"
    """ layout group for independently sized superkey labels """

    def __new__(cls, *args, **kwargs):
        """
        Singleton magic.
        """
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls)
            cls.self._init()
        return cls.self

    def _init(self):
        """
        Singleton constructor, should only run once.
        """
        _logger.debug("Entered in _init")

        # parse command line
        parser = OptionParser()
        parser.add_option("-l", "--layout", dest="layout_filename",
                help="Specify layout file (.onboard) or name")
        parser.add_option("-t", "--theme", dest="theme_filename",
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

        # create gsettings objects
        self._init_gsettings()

        # Load system defaults (if there are any, not required).
        # Used for adaption to distribution defaults, aka branding.
        self.system_defaults = self._load_system_defaults()

        # migrate old user dir .sok to .onboard
        old_user_dir = os.path.join(os.path.expanduser("~"), ".sok")
        user_dir = self.user_dir
        if not os.path.exists(user_dir) and os.path.exists(old_user_dir):
            _logger.info(_("Migrating user directory '{}' to '{}'.") \
                          .format(old_user_dir, user_dir))
            import shutil
            try:
                shutil.copytree(old_user_dir, user_dir)
            except OSError as e: # python >2.5
                _logger.error(_("Failed to migrate user directory. ") + str(e))

        self._last_snippets = dict(self.snippets)  # store a copy

        if (options.size):
            size = options.size.split("x")
            self._option_width  = int(size[0])
            self._option_height = int(size[1])

        x = self._get_initial_int(options.x, self.X_POSITION_KEY)
        if self.x != x:   # avoid unnecessary disk writes
            self.x = x

        y = self._get_initial_int(options.y, self.Y_POSITION_KEY)
        if self.y != y:   # avoid unnecessary disk writes
            self.y = y


        # Find layout
        self.LAYOUT_FILENAME_KEY.value = self.get_initial_filename(
             option               = options.layout_filename,
             gskey                = self.LAYOUT_FILENAME_KEY,
             user_filename_func   = lambda x: \
                 os.path.join(self.user_dir,    "layouts", x) + ".onboard",
             system_filename_func = lambda x: \
                 os.path.join(self.install_dir, "layouts", x) + ".onboard",
             final_fallback       = os.path.join(self.install_dir, 
                                                 "layouts", DEFAULT_LAYOUT))
        # Find theme
        from Onboard.Appearance import Theme
        theme_filename            = self.get_initial_filename(
             option               = options.theme_filename,
             gskey                = self.THEME_FILENAME_KEY,
             user_filename_func   = Theme.build_user_filename,
             system_filename_func = Theme.build_system_filename,
             final_fallback       = os.path.join(self.install_dir, 
                                                 "themes", DEFAULT_THEME))
        self.THEME_FILENAME_KEY.value = theme_filename

        # theme defaults in case theme loading fails
        self._color_scheme_filename  = ""
        self._key_style              = "flat"
        self._roundrect_radius       = 0
        self._key_fill_gradient      = 0
        self._key_stroke_gradient    = 0
        self._key_gradient_direction = 0
        self._key_label_font         = ""
        self._key_label_overrides    = {}

        # load theme
        _logger.info("Loading theme from " + theme_filename)
        theme = Theme.load(theme_filename)
        if not theme:
            _logger.error("Unable to read theme '%s'" % theme_filename)
        else:
            self._color_scheme_filename  = theme.get_color_scheme_filename()
            self._key_style              = theme.key_style
            self._roundrect_radius       = theme.roundrect_radius
            self._key_fill_gradient      = theme.key_fill_gradient
            self._key_stroke_gradient    = theme.key_stroke_gradient
            self._key_gradient_direction = theme.key_gradient_direction
            if theme.key_label_font:
                self._key_label_font = theme.key_label_font
            self._key_label_overrides.update(theme.key_label_overrides)

            if options.theme_filename:
                theme.apply()  # apply to gsettings; make sure everything is in sync
                self.theme_filename = theme_filename # store in gsettings

        self.xid_mode = options.xid_mode

        _logger.debug("Leaving _init")

    def _init_gsettings(self):

        def new(gskeys, settings, key, default, prop = None):
            class GSKey: pass
            if not prop:
                prop = key.replace("-","_") # python property name
            gskey = GSKey()
            gskey.settings = settings
            gskey.key = key
            gskey.value = default
            gskeys[prop] = gskey
            return gskey

        # create gsettings objects
        settings       = Gio.Settings.new(BASE_KEY)
        settings_theme = Gio.Settings.new(THEME_BASE_KEY)
        settings_icp   = Gio.Settings.new(ICP_BASE_KEY)
        settings_gss   = Gio.Settings.new(GSS_BASE_KEY)

        gskeys = {}   # {python property : GSKey}

        # gsettings keys for onboard
        self.X_POSITION_KEY             = new(gskeys, settings, "x", 0)
        self.Y_POSITION_KEY             = new(gskeys, settings, "y", 0)
        self.KEYBOARD_WIDTH_KEY         = new(gskeys, settings, "width", KEYBOARD_DEFAULT_WIDTH)
        self.KEYBOARD_HEIGHT_KEY        = new(gskeys, settings, "height", KEYBOARD_DEFAULT_HEIGHT)
        self.LAYOUT_FILENAME_KEY        = new(gskeys, settings, "layout-filename", DEFAULT_LAYOUT)
        self.THEME_FILENAME_KEY         = new(gskeys, settings, "theme-filename", DEFAULT_THEME)
        self.SCANNING_KEY               = new(gskeys, settings, "enable-scanning", False)
        self.SCANNING_INTERVAL_KEY      = new(gskeys, settings, "scanning-interval", SCANNING_DEFAULT_INTERVAL)
        self.SNIPPETS_KEY               = new(gskeys, settings, "snippets", {})
        self.SHOW_STATUS_ICON_KEY       = new(gskeys, settings, "show-status-icon", False)
        self.START_MINIMIZED_KEY        = new(gskeys, settings, "start-minimized", False)
        self.CURRENT_SETTINGS_PAGE_KEY  = new(gskeys, settings, "current-settings-page", 0)
        self.ONBOARD_XEMBED_KEY         = new(gskeys, settings, "xembed-onboard", False, "onboard_xembed_enabled")

        # gsettings keys for theme
        self.COLOR_SCHEME_FILENAME_KEY  = new(gskeys, settings_theme, "color-scheme-filename", DEFAULT_THEME)
        self.KEY_STYLE_KEY              = new(gskeys, settings_theme, "key-style", "flat")
        self.ROUNDRECT_RADIUS_KEY       = new(gskeys, settings_theme, "roundrect-radius", 0)
        self.KEY_FILL_GRADIENT_KEY      = new(gskeys, settings_theme, "key-fill-gradient", 0)
        self.KEY_STROKE_GRADIENT_KEY    = new(gskeys, settings_theme, "key-stroke-gradient", 0)
        self.KEY_GRADIENT_DIRECTION_KEY = new(gskeys, settings_theme, "key-gradient-direction", 0)
        self.KEY_LABEL_FONT_KEY         = new(gskeys, settings_theme, "key-label-font", "")
        self.KEY_LABEL_OVERRIDES_KEY    = new(gskeys, settings_theme, "key-label-overrides", {})

        # gsettings keys for icon palette
        self.ICP_IN_USE_KEY             = new(gskeys, settings_icp, "in-use", False, "icp_in_use")
        self.ICP_X_POSITION_KEY         = new(gskeys, settings_icp, "x", 40, "icp_x")
        self.ICP_Y_POSITION_KEY         = new(gskeys, settings_icp, "y", 300, "icp_y")
        self.ICP_WIDTH_KEY              = new(gskeys, settings_icp, "width", 80, "icp_width")
        self.ICP_HEIGHT_KEY             = new(gskeys, settings_icp, "height", 80, "icp_height")

        # gsettings keys for gnome screensaver
        # Used for XEmbedding onboard into gnome-screensavers unlock screen.
        self.GSS_XEMBED_ENABLE_KEY      = new(gskeys, settings_gss, "embedded-keyboard-enabled", None, "gss_embedded_keyboard_enabled")
        self.GSS_XEMBED_COMMAND_KEY     = new(gskeys, settings_gss, "embedded-keyboard-command", None, "gss_embedded_keyboard_command")

        self._setup_properties(gskeys)

        self.gskeys = gskeys

    def _setup_properties(self, gskeys):
        """ 
        Setup python properties and notification callbacks
        for all gsettings keys.
        """
        for prop, gskey in gskeys.items():
            # init value from gsettings
            if hasattr(type(self), "_gsettings_get_"+prop):
                # get gsettings value by custom method
                gskey.value = \
                        getattr(type(self),"_gsettings_get_"+prop)(self, gskey)
            else:
                gskey.value = gskey.settings[gskey.key]

            # callback list for notification listeners
            setattr(self, '_'+prop+"_notify_callbacks", [])

            # method to add a callback to this property
            setattr(type(self), prop+'_notify_add', 
                    lambda self, callback, _prop=prop: \
                            getattr(self, '_'+_prop+'_notify_callbacks') \
                                .append(callback))

            # call back function for change notification
            def notify_changed_cb(settings, key, _gskey=gskey, _prop=prop):
                # Get-gsettings hook, for reading values from gsettings 
                # in non-standard ways.
                if hasattr(self, "_gsettings_get_"+_prop):
                    value = getattr(self,"_gsettings_get_"+_prop)(_gskey)
                else:
                    value = _gskey.settings[_gskey.key]

                # Can-set hook, for value validation.
                if not hasattr(self, "_can_set_"+_prop) or \
                       getattr(self, "_can_set_"+_prop)(value):
                    _gskey.value = value
                    #print "notify: ",key, _gskey.key, _prop, value
                    for callback in getattr(self, '_'+_prop+'_notify_callbacks'):
                        callback(value)

                # Post-notification hook for anything that properties
                # needs to do after all listeners have been notified.
                if hasattr(self, "_post_notify_"+_prop):
                    getattr(self, "_post_notify_"+_prop)()

            setattr(self, '_'+prop+'_changed_cb', notify_changed_cb)

            # connect callback function to gsettings
            gskey.settings.connect("changed::"+gskey.key, 
                                    getattr(self, '_'+prop+'_changed_cb'))

    def __getattr__(self, prop):
        if hasattr(self, "gskeys"):
            gskey = self.gskeys.get(prop, None)
            if gskey:
                return gskey.value
        raise AttributeError("'{}' object has no attribute '{}'" \
                             .format(type(self).__name__, prop))

    def __setattr__(self, prop, value):
        if hasattr(self, "gskeys"):
            gskey = self.gskeys.get(prop, None)
            if gskey:
                if not hasattr(self, "_can_set_"+prop) or \
                       getattr(self, "_can_set_"+prop)(value):
                    gskey.value = value
                    if hasattr(self, "_gsettings_set_"+prop):
                        getattr(self,"_gsettings_set_"+prop)(gskey, value)
                    else:
                        if value != gskey.settings[gskey.key]:
                            #print "setattr: ", gskey.key, prop, value
                            gskey.settings[gskey.key] = value

                        # reset system default flag
                        sdk = self._build_system_default_key(gskey.key)
                        if sdk in gskey.settings.keys() and \
                           gskey.settings[sdk]:
                            gskey.settings[sdk] = False

                return
        object.__setattr__(self, prop, value)

    ##### onboard base property helpers #####
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

    def _can_set_layout_filename(self, filename):
        if not os.path.exists(filename):
            _logger.warning(_("layout '%s' does not exist") % filename)
            return False
        return True

    def _can_set_theme_filename(self, filename):
        if not os.path.exists(filename):
            _logger.warning(_("theme '%s' does not exist") % filename)
            return False
        return True

    def _can_set_color_scheme_filename(self, filename):
        if not os.path.exists(filename):
            _logger.warning(_("color scheme '%s' does not exist") % filename)
            return False
        return True

    def _gsettings_get_snippets(self, gskey):
        return self._gsettings_list_to_dict(gskey, int)

    def _gsettings_set_snippets(self, gskey, value):
        self._dict_to_gsettings_list(gskey, value)


    ##### Icon palette property helpers #####
    def _can_set_icp_x(self, value):
        return value >= 0

    def _can_set_icp_y(self, value):
        return value >= 0

    def _can_set_icp_width(self, value):
        return value > 0

    def _can_set_icp_height(self, value):
        return value > 0

    def icp_size_notify_add(self, callback):
        self.icp_width_notify_add(callback)
        self.icp_height_notify_add(callback)

    def icp_position_notify_add(self, callback):
        self.icp_x_notify_add(callback)
        self.icp_y_notify_add(callback)


    ##### theme property helpers #####
    def _gsettings_get_key_label_overrides(self, gskey):
        return self._gsettings_list_to_dict(gskey)

    def _gsettings_set_key_label_overrides(self, gskey, value):
        self._dict_to_gsettings_list(gskey, value)

    def theme_attributes_notify_add(self, callback):
        self.key_style_notify_add(callback)
        self.roundrect_radius_notify_add(callback)
        self.key_fill_gradient_notify_add(callback)
        self.key_stroke_gradient_notify_add(callback)
        self.key_gradient_direction_notify_add(callback)
        self.key_label_font_notify_add(callback)
        self.key_label_overrides_notify_add(callback)
        self.key_style_notify_add(callback)
        self.key_style_notify_add(callback)


    ###### gnome-screensaver, xembedding #####
    def is_onboard_in_xembed_command_string(self):
        """
        Checks whether the gsettings key for the embeded application command
        contains the entry defined by onboard.
        Returns True if it is set to onboard and False otherwise.
        """
        if self.gss_embedded_keyboard_command == START_ONBOARD_XEMBED_COMMAND:
            return True
        else:
            return False

    def set_xembed_command_string_to_onboard(self):
        """
        Write command to start the embedded onboard into the corresponding
        gsettings key.
        """
        self.gss_embedded_keyboard_command = START_ONBOARD_XEMBED_COMMAND


    ####### Snippets #######

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


    # modeless gksu - diabled until gksu moved to gsettings
    def modeless_gksu_notify_add(self, callback):
        pass
    modeless_gksu = property(lambda self: False)

    def _load_system_defaults(self):
        """ 
        System default settings are optionally provided for distribution 
        specific customization.
        They are stored in simple ini-style files, residing in a small choice 
        of directories. The last setting found in the list of paths wins.
        """
        sd = {}
        defaults_filename = "onboard-defaults.conf"
        paths = [os.path.join(self.install_dir, defaults_filename),
                 os.path.join("/etc/onboard", defaults_filename)]
        _logger.info(_("Looking for system defaults in %s") % str(paths))

        filename = None
        cp = configparser.SafeConfigParser()
        try:
            filename = cp.read(paths)
        except configparser.ParsingError, e:
            _logger.error(_("Failed to read system defaults. " + str(e)))

        if not filename:
            _logger.info(_("No system defaults found."))
        else:
            _logger.info(_("Loading system defaults from %s.") % filename)

            section = "system_defaults"
            sd = dict(cp.items(section))

            if cp.has_option(section, "superkey_label_independent_size"):
                sd["superkey_label_independent_size"] = \
                      cp.getboolean(section, "superkey_label_independent_size")

            # window position
            if "x" in sd:
                sd["x"] = cp.getint(section, "x")
            if "y" in sd:
                sd["y"] = cp.getint(section, "y")

            # window size
            if "width" in sd:
                sd["width"] = cp.getint(section, "width")
            if "height" in sd:
                sd["height"] = cp.getint(section, "height")
            #if "size" in sd:
            #    size = sd["size"].split("x")
            #    sd["width"] = int(size[0])
            #    sd["height"] = int(size[1])

            # Convert the simplified superkey_label setting to the
            # more general key_label_overrides setting.
            if "superkey_label" in sd and \
               not "key_label_overrides" in sd:
                overrides = {}
                group = self.SUPERKEY_SIZE_GROUP \
                    if sd.get("superkey_label_independent_size") \
                    else ""
                for key_id in ["LWIN", "RWIN"]:
                    overrides[key_id] = (sd["superkey_label"], group)
                sd["key_label_overrides"] = overrides

        return sd

    def _get_initial_int(self, option, gskey):
        return self._get_initial_value(option, gskey)

    def get_initial_filename(self, option, gskey, final_fallback,
                                   user_filename_func = None,
                                   system_filename_func = None):

        filename = self._get_initial_value(option, gskey)
        description = gskey.key

        if filename and not os.path.exists(filename):
            # assume theme_filename is just a basename
            _logger.info(_("Can't find file '%s'. Retrying as %s basename.") %
                         (filename, description))

            basename = filename

            if user_filename_func:
                filename = user_filename_func(basename)
                if not os.path.exists(filename):
                    filename = ""

            if  not filename and system_filename_func:
                filename = system_filename_func(basename)
                if not os.path.exists(filename):
                    filename = ""

            if not filename:
                _logger.info(_("Can't load basename '%s'"
                               " loading default %s instead") %
                             (basename, description))

        if not filename:
            filename = final_fallback

        if not os.path.exists(filename):
            _logger.error(_("Unable to find %s '%s'") % (description, filename))
            filename = ""

        return filename

    def _get_initial_value(self, option, gskey):
        """ Type independent value getter.
            Tries to retrieve the value in the following order from
            - command line option (option)
            - system defaults (gskey.key)
            - gsettings (gskey.settings, gskey.key)
            - hard coded default (gskey.default)
        """
        value = None

        if option:
            # command line option has precedence
            value = option
        else:
            system_default = self.system_defaults.get(gskey.key, None)
            use_system_default = None
            sdk = self._build_system_default_key(gskey.key)
            if gskey.settings and sdk in gskey.settings.keys():
                use_system_default = gskey.settings[sdk]

            if not system_default is None and use_system_default:
                # There is no gsettings or the key has never been set.
                value = system_default
            elif gskey.settings:
                value = gskey.settings[gskey.key]

        if value is None:
            value = gskey.default

        return value

    def _build_system_default_key(self, key):
        """ builds the gsettings key that determines if the 
            system default should be used
        """
        return key + "-system-default"

    def _dict_to_gsettings_list(self, gskey, _dict):
        """ Store dictionary in a gsettings list key """
        _list = pack_name_value_list(_dict)
        gskey.settings.set_strv(gskey.key, _list)

    def _gsettings_list_to_dict(self, gskey, key_type = str):
        """ Get dictionary from a gsettings list key """
        _list = gskey.settings.get_strv(gskey.key)
        return unpack_name_value_list(_list, key_type=key_type)

    def _get_kbd_render_mixin(self):
        __import__(self._kbd_render_mixin_mod)
        return getattr(sys.modules[self._kbd_render_mixin_mod],
                self._kbd_render_mixin_cls)
    kbd_render_mixin = property(_get_kbd_render_mixin)

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



