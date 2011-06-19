"""
File containing Config singleton.
"""

### Logging ###
import logging
_logger = logging.getLogger("Config")
###############

import gconf
import gtk
import os
import sys

from optparse import OptionParser
import ConfigParser as configparser

from gettext import gettext as _
from Onboard.utils import pack_name_value_list, unpack_name_value_list

KEYBOARD_WIDTH_GCONF_KEY    = "/apps/onboard/width"
KEYBOARD_HEIGHT_GCONF_KEY   = "/apps/onboard/height"
LAYOUT_FILENAME_GCONF_KEY   = "/apps/onboard/layout_filename"
X_POSITION_GCONF_KEY        = "/apps/onboard/horizontal_position"
Y_POSITION_GCONF_KEY        = "/apps/onboard/vertical_position"
SCANNING_GCONF_KEY          = "/apps/onboard/enable_scanning"
SCANNING_INTERVAL_GCONF_KEY = "/apps/onboard/scanning_interval"
SNIPPETS_GCONF_KEY          = "/apps/onboard/snippets"
SNIPPETS2_GCONF_KEY         = "/apps/onboard/snippets2"
SHOW_STATUS_ICON_GCONF_KEY  = "/apps/onboard/use_status_icon"
START_MINIMIZED_GCONF_KEY   = "/apps/onboard/start_minimized"

THEME_FILENAME_GCONF_KEY    = "/apps/onboard/theme_filename"
COLOR_SCHEME_FILENAME_GCONF_KEY = "/apps/onboard/theme/color_scheme_filename"
KEY_STYLE_GCONF_KEY         = "/apps/onboard/theme/key_style"
ROUNDRECT_RADIUS_GCONF_KEY  = "/apps/onboard/theme/roundrect_radius"
KEY_FILL_GRADIENT_GCONF_KEY = "/apps/onboard/theme/key_fill_gradient"
KEY_STROKE_GRADIENT_GCONF_KEY = "/apps/onboard/theme/key_stroke_gradient"
KEY_GRADIENT_DIRECTION_GCONF_KEY = "/apps/onboard/theme/key_gradient_direction"
KEY_LABEL_FONT_GCONF_KEY        = "/apps/onboard/theme/label_font"
KEY_LABEL_OVERRIDES_GCONF_KEY = "/apps/onboard/theme/key_label_overrides"

CURRENT_SETTINGS_PAGE_GCONF_KEY = "/apps/onboard/current_settings_page"

DEFAULT_LAYOUT              = "Classic Onboard.onboard"
DEFAULT_THEME               = "Classic Onboard.theme"
DEFAULT_COLORS              = "Classic Onboard.colors"

KEYBOARD_DEFAULT_HEIGHT   = 800
KEYBOARD_DEFAULT_WIDTH    = 300

SCANNING_DEFAULT_INTERVAL = 750

GTK_KBD_MIXIN_MOD = "Onboard.KeyboardGTK"
GTK_KBD_MIXIN_CLS = "KeyboardGTK"

INSTALL_DIR = "/usr/share/onboard"
USER_DIR = ".onboard"

ICP_IN_USE_GCONF_KEY     = "/apps/onboard/icon_palette/in_use"
ICP_WIDTH_GCONF_KEY      = "/apps/onboard/icon_palette/width"
ICP_HEIGHT_GCONF_KEY     = "/apps/onboard/icon_palette/height"
ICP_X_POSITION_GCONF_KEY = "/apps/onboard/icon_palette/horizontal_position"
ICP_Y_POSITION_GCONF_KEY = "/apps/onboard/icon_palette/vertical_position"

ICP_DEFAULT_HEIGHT   = 80
ICP_DEFAULT_WIDTH    = 80
ICP_DEFAULT_X_POSITION = 40
ICP_DEFAULT_Y_POSITION = 300

MODELESS_GKSU_GCONF_KEY = "/apps/gksu/disable-grab"

ONBOARD_XEMBED_GCONF_KEY      = "/apps/onboard/xembed_onboard"
START_ONBOARD_XEMBED_COMMAND  = "onboard --xid"
GSS_XEMBED_ENABLE_GCONF_KEY   = "/apps/gnome-screensaver/embedded_keyboard_enabled"
GSS_XEMBED_COMMAND_GCONF_KEY  = "/apps/gnome-screensaver/embedded_keyboard_command"


class Config (object):
    """
    Singleton Class to encapsulate the gconf stuff and check values.
    """

    _gconf_client = gconf.client_get_default()

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
    A copy of snippets so that when the list changes in gconf we can tell which
    items have changed.
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

        self._gconf_client.add_dir("/apps/onboard", gconf.CLIENT_PRELOAD_NONE)
        self._gconf_client.add_dir("/apps/gksu", gconf.CLIENT_PRELOAD_NONE)
        self._gconf_client.add_dir("/apps/gnome-screensaver", \
                                                gconf.CLIENT_PRELOAD_NONE)

        # Load system defaults (if there are any, not required).
        # Used for adaption to distribution defaults, aka branding.
        self.system_defaults = self.load_system_defaults()

        self._gconf_client.notify_add(KEYBOARD_WIDTH_GCONF_KEY,
                self._geometry_notify_cb)
        self._gconf_client.notify_add(KEYBOARD_HEIGHT_GCONF_KEY,
                self._geometry_notify_cb)

        self._gconf_client.notify_add(ICP_IN_USE_GCONF_KEY,
                self._icp_in_use_change_notify_cb)
        self._gconf_client.notify_add(ICP_WIDTH_GCONF_KEY,
                self._icp_size_change_notify_cb)
        self._gconf_client.notify_add(ICP_HEIGHT_GCONF_KEY,
                self._icp_size_change_notify_cb)
        self._gconf_client.notify_add(ICP_X_POSITION_GCONF_KEY,
                self._icp_position_change_notify_cb)
        self._gconf_client.notify_add(ICP_Y_POSITION_GCONF_KEY,
                self._icp_position_change_notify_cb)
        self._gconf_client.notify_add(START_MINIMIZED_GCONF_KEY,
                self._start_minimized_notify_cb)

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

        # convert old snippets (text) to the new snippets2 (label, text) format
        snippets = self.snippets
        # No user changes in snippets2 and yes, user changes in old snippets
        if not self._gconf_client.get_without_default(SNIPPETS2_GCONF_KEY) and \
               self._gconf_client.get_without_default(SNIPPETS_GCONF_KEY):
            old_snippets = self._gconf_client.get_list(SNIPPETS_GCONF_KEY, \
                                                       gconf.VALUE_STRING)
            snippets = {}
            for i, s in enumerate(old_snippets):
                snippets[i] = ("", s)
            if snippets:
                self.snippets = snippets   # update gconf

        self._last_snippets = self.snippets
        self._gconf_client.notify_add(SNIPPETS2_GCONF_KEY,
                self._snippets_notify_cb)

        if (options.size):
            size = options.size.split("x")
            self._option_width  = int(size[0])
            self._option_height = int(size[1])

        x = self.get_initial_int(options.x, "x", X_POSITION_GCONF_KEY, 0)
        if self.x_position != x:   # avoid unnecessary disk writes
            self.x_position = x

        y = self.get_initial_int(options.y, "y", Y_POSITION_GCONF_KEY, 0)
        if self.y_position != y:   # avoid unnecessary disk writes
            self.y_position = y


        # Find layout
        self._layout_filename = self.get_initial_filename(
             option               = options.layout_filename,
             system_default_key   = "layout",
             gconf_key            = LAYOUT_FILENAME_GCONF_KEY,
             user_filename_func   = lambda x: \
                 os.path.join(self.user_dir,    "layouts", x) + ".onboard",
             system_filename_func = lambda x: \
                 os.path.join(self.install_dir, "layouts", x) + ".onboard",
             final_fallback       = os.path.join(self.install_dir, 
                                                 "layouts", DEFAULT_LAYOUT))
        # Find theme
        from Onboard.Appearance import Theme
        self._theme_filename = self.get_initial_filename(
             option               = options.theme_filename,
             system_default_key   = "theme",
             gconf_key            = THEME_FILENAME_GCONF_KEY,
             user_filename_func   = Theme.build_user_filename,
             system_filename_func = Theme.build_system_filename,
             final_fallback       = os.path.join(self.install_dir, 
                                                 "themes", DEFAULT_THEME))
        theme_filename = self._theme_filename

        # theme defaults in case everything fails
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
                theme.apply()  # apply to gconf; make sure everything is in sync
                self.theme_filename = theme_filename # store in gconf

        self._gconf_client.notify_add(LAYOUT_FILENAME_GCONF_KEY,
                self._layout_filename_notify_cb)
        self._gconf_client.notify_add(X_POSITION_GCONF_KEY,
                self._position_notify_cb)
        self._gconf_client.notify_add(Y_POSITION_GCONF_KEY,
                self._position_notify_cb)
        self._gconf_client.notify_add(SCANNING_GCONF_KEY,
                self._scanning_notify_cb)
        self._gconf_client.notify_add(SCANNING_INTERVAL_GCONF_KEY,
                self._scanning_interval_notify_cb)
        self._gconf_client.notify_add(SHOW_STATUS_ICON_GCONF_KEY,
                self._show_status_icon_notify_cb)
        self._gconf_client.notify_add(MODELESS_GKSU_GCONF_KEY,
                self._modeless_gksu_notify_cb)
        self._gconf_client.notify_add(ONBOARD_XEMBED_GCONF_KEY,
                self._onboard_xembed_notify_cb)

        self._gconf_client.notify_add(THEME_FILENAME_GCONF_KEY,
                self._theme_filename_notify_cb)
        self._gconf_client.notify_add(COLOR_SCHEME_FILENAME_GCONF_KEY,
                self._color_scheme_filename_notify_cb)
        self._gconf_client.notify_add(KEY_STYLE_GCONF_KEY,
                self._theme_attributes_notify_cb)
        self._gconf_client.notify_add(ROUNDRECT_RADIUS_GCONF_KEY,
                self._theme_attributes_notify_cb)
        self._gconf_client.notify_add(KEY_FILL_GRADIENT_GCONF_KEY,
                self._theme_attributes_notify_cb)
        self._gconf_client.notify_add(KEY_STROKE_GRADIENT_GCONF_KEY,
                self._theme_attributes_notify_cb)
        self._gconf_client.notify_add(KEY_GRADIENT_DIRECTION_GCONF_KEY,
                self._theme_attributes_notify_cb)
        self._gconf_client.notify_add(KEY_LABEL_FONT_GCONF_KEY,
                self._theme_attributes_notify_cb)
        self._gconf_client.notify_add(KEY_LABEL_OVERRIDES_GCONF_KEY,
                self._key_label_overrides_notify_cb)

        self.xid_mode = options.xid_mode

        _logger.debug("Leaving _init")

    def load_system_defaults(self):
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

    def get_initial_filename(self, option, system_default_key,
                                   gconf_key, final_fallback,
                                   user_filename_func = None,
                                   system_filename_func = None):

        filename = ""
        description = system_default_key

        if option:
            # command line option has precedence
            filename = option
        else:
            system_default = self.system_defaults.get(system_default_key, None)
            gconf_value = None
            if self._gconf_client:
                gconf_value = self._gconf_client.get_without_default(gconf_key)
            if not system_default is None and gconf_value is None:
                # There is no gconfd or the key has never been set.
                filename = system_default
            elif self._gconf_client:
                filename = self._gconf_client.get_string(gconf_key)

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

    def get_initial_int(self, option, system_default_key,
                        gconf_key, final_fallback=None):
        value = None

        if option:
            value = option
        else:
            system_default = self.system_defaults.get(system_default_key, None)
            gconf_value = None
            if self._gconf_client:
                gconf_value = self._gconf_client.get_without_default(gconf_key)
            if not system_default is None and gconf_value is None:
                # There is no gconfd or the key has never been set.
                value = system_default
            elif self._gconf_client:
                value = self._gconf_client.get_int(gconf_key)

        if value is None:
            value = final_fallback
        return value

    def dict_to_gconf_list(self, gconf_key, _dict):
        """ Store dictionary in a gconf list key """
        _list = pack_name_value_list(_dict)

        # python-gconf 2.28.1-ubuntu3 fails with unicode strings for set_list
        _list = [x.encode("utf-8") for x in _list]  # translate to non-unicode

        self._gconf_client.set_list(gconf_key, gconf.VALUE_STRING, _list)

    def gconf_list_to_dict(self, gconf_key, key_type = str):
        """ Get dictionary from a gconf list key """
        _list = self._gconf_client.get_list(gconf_key, gconf.VALUE_STRING)

        _list = [x.decode("utf-8") for x in _list]  # translate to unicode

        return unpack_name_value_list(_list, key_type=key_type)

    ######## Layout #########
    _layout_filename_notify_callbacks   = []
    def layout_filename_notify_add(self, callback):
        """
        Register callback to be run when layout filename changes.

        Callbacks are called with the layout filename as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._layout_filename_notify_callbacks.append(callback)

    def _layout_filename_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve layout change notifications from gconf and check the file is
        valid before calling callbacks.
        """
        filename = self._gconf_client.get_string(LAYOUT_FILENAME_GCONF_KEY)
        self.do_set_layout_filename(filename)

        for callback in self._layout_filename_notify_callbacks:
            callback(filename)

    def do_set_layout_filename(self, filename):
        if not os.path.exists(filename):
            _logger.warning("layout '%s' does not exist" % filename)
        else:
            self._layout_filename = filename

    def _get_layout_filename(self):
        """
        Layout filename getter.
        """
        return self._layout_filename
    def _set_layout_filename(self, value):
        """
        Layout filename setter, TODO check valid.

        @type  value: str
        @param value: Absolute path to the layout description file.
        """
         # don't wait for gconf notify event, settings need it immediately
        self.do_set_layout_filename(value)
        self._gconf_client.set_string(LAYOUT_FILENAME_GCONF_KEY, value)
    layout_filename = property(_get_layout_filename, _set_layout_filename)

    ######## Theme #########
    _theme_filename_notify_callbacks   = []
    def theme_filename_notify_add(self, callback):
        """
        Register callback to be run when theme filename changes.

        Callbacks are called with the theme filename as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._theme_filename_notify_callbacks.append(callback)

    def _theme_filename_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve theme change notifications from gconf and check the file is
        valid before calling callbacks.
        """
        filename = self._gconf_client.get_string(THEME_FILENAME_GCONF_KEY)
        self.do_set_theme_filename(filename)

        for callback in self._theme_filename_notify_callbacks:
            callback(filename)

    def do_set_theme_filename(self, filename):
        if not os.path.exists(filename):
            _logger.warning("theme '%s' does not exist" % filename)
        else:
            self._theme_filename = filename

    def _get_theme_filename(self):
        """
        Theme filename getter.
        """
        return self._theme_filename
    def _set_theme_filename(self, value):
        """
        Theme filename setter, TODO check valid.

        @type  value: str
        @param value: Absolute path to the theme description file.
        """
         # don't wait for gconf notify event, settings need it immediately
        self.do_set_theme_filename(value)
        self._gconf_client.set_string(THEME_FILENAME_GCONF_KEY, value)
    theme_filename = property(_get_theme_filename, _set_theme_filename)


    ######## color_scheme #########
    _color_scheme_filename_notify_callbacks   = []
    def color_scheme_filename_notify_add(self, callback):
        """
        Register callback to be run when color_scheme filename changes.

        Callbacks are called with the color_scheme filename as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._color_scheme_filename_notify_callbacks.append(callback)

    def _color_scheme_filename_notify_cb(self, client, cxion_id,
                                         entry, user_data):
        """
        Recieve color_scheme change notifications from gconf and check the file
        is valid before calling callbacks.
        """
        filename = \
               self._gconf_client.get_string(COLOR_SCHEME_FILENAME_GCONF_KEY)
        self.do_set_color_scheme_filename(filename)

        for callback in self._color_scheme_filename_notify_callbacks:
            callback(filename)

    def do_set_color_scheme_filename(self, filename):
        if not os.path.exists(filename):
            _logger.warning("color_scheme '%s' does not exist" % filename)
        else:
            self._color_scheme_filename = filename

    def _get_color_scheme_filename(self):
        """
        color_scheme filename getter.
        """
        return self._color_scheme_filename
    def _set_color_scheme_filename(self, value):
        """
        color_scheme filename setter, TODO check valid.

        @type  value: str
        @param value: Absolute path to the color_scheme description file.
        """
         # don't wait for gconf notify event, settings need it immediately
        self.do_set_color_scheme_filename(value)
        self._gconf_client.set_string(COLOR_SCHEME_FILENAME_GCONF_KEY, value)
    color_scheme_filename = property(_get_color_scheme_filename,
                                     _set_color_scheme_filename)

    # notification for most of the themes attributes
    _theme_attributes_callbacks = []
    def theme_attributes_notify_add(self, callback):
        self._theme_attributes_callbacks.append(callback)
    def _theme_attributes_notify_cb(self, client, cxion_id, entry,
            user_data):
        self.read_theme_vars()
        for callback in self._theme_attributes_callbacks:
            callback(None)

    def read_theme_vars(self):
        self._key_style = \
                self._gconf_client.get_string(KEY_STYLE_GCONF_KEY)
        self._roundrect_radius = \
                self._gconf_client.get_int(ROUNDRECT_RADIUS_GCONF_KEY)
        self._key_fill_gradient = self. \
                _gconf_client.get_int(KEY_FILL_GRADIENT_GCONF_KEY)
        self._key_stroke_gradient = self. \
                _gconf_client.get_int(KEY_STROKE_GRADIENT_GCONF_KEY)
        self._key_gradient_direction = self. \
                _gconf_client.get_int(KEY_GRADIENT_DIRECTION_GCONF_KEY)
        self._key_label_font = \
                self._gconf_client.get_string(KEY_LABEL_FONT_GCONF_KEY)
        self._key_label_overrides = \
                self.gconf_list_to_dict(KEY_LABEL_OVERRIDES_GCONF_KEY)

    ####### key_style #######
    def _get_key_style(self):
        return self._key_style
    def _set_key_style(self, value):
        self._key_style = value
        self._gconf_client.set_string(KEY_STYLE_GCONF_KEY, value)
    key_style = property(_get_key_style,
                         _set_key_style)

    ####### roundrect_radius #######
    def _get_roundrect_radius(self):
        return self._roundrect_radius
    def _set_roundrect_radius(self, value):
        self._roundrect_radius = value
        self._gconf_client.set_int(ROUNDRECT_RADIUS_GCONF_KEY, value)
    roundrect_radius = property(_get_roundrect_radius,
                                _set_roundrect_radius)

    ####### key_fill_gradient #######
    def _get_key_fill_gradient(self):
        return self._key_fill_gradient
    def _set_key_fill_gradient(self, value):
        self._key_fill_gradient = value
        self._gconf_client.set_int(KEY_FILL_GRADIENT_GCONF_KEY, value)
    key_fill_gradient = property(_get_key_fill_gradient,
                                      _set_key_fill_gradient)

    ####### key_stroke_gradient #######
    def _get_key_stroke_gradient(self):
        return self._key_stroke_gradient
    def _set_key_stroke_gradient(self, value):
        self._key_stroke_gradient = value
        self._gconf_client.set_int(KEY_STROKE_GRADIENT_GCONF_KEY, value)
    key_stroke_gradient = property(_get_key_stroke_gradient,
                                   _set_key_stroke_gradient)

    ####### key_gradient_direction #######
    def _get_key_gradient_direction(self):
        return self._key_gradient_direction
    def _set_key_gradient_direction(self, value):
        self._key_gradient_direction = value
        self._gconf_client.set_int(KEY_GRADIENT_DIRECTION_GCONF_KEY, value)
    key_gradient_direction = property(_get_key_gradient_direction,
                                      _set_key_gradient_direction)

    ####### key_label_font #######
    def _get_key_label_font(self):
        if self._key_label_font:
            return self._key_label_font
        return self.system_defaults.get("key_label_font", "")

    def _set_key_label_font(self, value):
        self._key_label_font = value
        self._gconf_client.set_string(KEY_LABEL_FONT_GCONF_KEY, value)
    key_label_font = property(_get_key_label_font,
                              _set_key_label_font)

    ####### key_label_overrides #######
    _key_label_overrides_callbacks = []
    def key_label_overrides_notify_add(self, callback):
        self._key_label_overrides_callbacks.append(callback)
    def _key_label_overrides_notify_cb(self, client, cxion_id, entry,
            user_data):
        self._key_label_overrides = \
                self.gconf_list_to_dict(KEY_LABEL_OVERRIDES_GCONF_KEY)

        for callback in self._key_label_overrides_callbacks:
            callback(self._key_label_overrides)
    def _get_key_label_overrides(self):          # returns dict of tuples
        if self._key_label_overrides:
            return self._key_label_overrides
        return self.system_defaults.get("key_label_overrides", {})
    def _set_key_label_overrides(self, value):   # expects dict of tuples
        self._key_label_overrides = value
        self.dict_to_gconf_list(KEY_LABEL_OVERRIDES_GCONF_KEY, value)
    key_label_overrides = property(_get_key_label_overrides,
                                  _set_key_label_overrides)

    ####### Geometry ########
    _geometry_notify_callbacks = []
    def _get_keyboard_height(self):
        """
        Keyboard height getter, check height is greater than 1.
        """

        height = self.get_initial_int(self._option_height, "height",
                                           KEYBOARD_HEIGHT_GCONF_KEY)
        if height and height > 1:
            return height
        else:
            return KEYBOARD_DEFAULT_HEIGHT

    def _set_keyboard_height(self, value):
        """
        Keyboard height setter, check height is greater than 1.
        """
        if value > 1 and \
           value != self._gconf_client.get_int(KEYBOARD_HEIGHT_GCONF_KEY):
            self._gconf_client.set_int(KEYBOARD_HEIGHT_GCONF_KEY, value)
    keyboard_height = property(_get_keyboard_height, _set_keyboard_height)

    def _get_keyboard_width(self):
        """
        Keyboard width getter, check width is greater than 1.
        """
        width = self.get_initial_int(self._option_width, "width",
                                           KEYBOARD_WIDTH_GCONF_KEY)

        if width and width > 1:
            return width
        else:
            return KEYBOARD_DEFAULT_WIDTH

    def _set_keyboard_width(self, value):
        """
        Keyboard width setter, check width is greater than 1.
        """
        if value > 1 and \
                value != self._gconf_client.get_int(KEYBOARD_WIDTH_GCONF_KEY):
            self._gconf_client.set_int(KEYBOARD_WIDTH_GCONF_KEY, value)
    keyboard_width  = property(_get_keyboard_width, _set_keyboard_width)

    def geometry_notify_add(self, callback):
        """
        Register callback to be run when the keyboard geometry changes.

        Callbacks are called with the new geomtery as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._geometry_notify_callbacks.append(callback)

    def _geometry_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve geometry change notifications from gconf and run callbacks.
        """
        for callback in self._geometry_notify_callbacks:
            callback(self.keyboard_width, self.keyboard_height)

    ####### Position ########
    _position_notify_callbacks = []
    def _get_x_position(self):
        """
        Keyboard x position getter.
        """
        return self._gconf_client.get_int(X_POSITION_GCONF_KEY)
    def _set_x_position(self, value):
        """
        Keyboard x position setter.
        """
        if value + self.keyboard_width > 1 and \
                value != self._gconf_client.get_int(X_POSITION_GCONF_KEY):
            _logger.info("New keyboard x position: %d" % value)
            self._gconf_client.set_int(X_POSITION_GCONF_KEY, value)
    x_position = property(_get_x_position, _set_x_position)

    def _get_y_position(self):
        """
        Keyboard y position getter.
        """
        return self._gconf_client.get_int(Y_POSITION_GCONF_KEY)
    def _set_y_position(self, value):
        """
        Keyboard y position setter.
        """
        if value + self.keyboard_height > 1 and \
           value != self._gconf_client.get_int(Y_POSITION_GCONF_KEY):
            self._gconf_client.set_int(Y_POSITION_GCONF_KEY, value)
    y_position = property(_get_y_position, _set_y_position)

    def position_notify_add(self, callback):
        """
        Register callback to be run when the keyboard position changes.

        Callbacks are called with the new position as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._position_notify_callbacks.append(callback)

    def _position_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve position change notifications from gconf and run callbacks.
        """
        for callback in self._position_notify_callbacks:
            callback(self.x_position, self.y_position)

    ####### Scanning ########
    _scanning_callbacks = []
    def _get_scanning(self):
        """
        Scanning mode active getter.
        """
        return self._gconf_client.get_bool(SCANNING_GCONF_KEY)
    def _set_scanning(self, value):
        """
        Scanning mode active setter.
        """
        return self._gconf_client.set_bool(SCANNING_GCONF_KEY, value)
    scanning = property(_get_scanning, _set_scanning)

    def scanning_notify_add(self, callback):
        """
        Register callback to be run when the scanning mode changes.

        Callbacks are called with the new value as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._scanning_callbacks.append(callback)

    def _scanning_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve scanning mode change notifications from gconf and run callbacks.
        """
        for callback in self._scanning_callbacks:
            callback(self.scanning)

    ## Scanning interval ####
    _scanning_interval_callbacks = []
    def _get_scanning_interval(self):
        """
        Scanning interval time getter.
        """
        interval = self._gconf_client.get_int(SCANNING_INTERVAL_GCONF_KEY)
        if interval and interval > 0:
            return interval
        else:
            return SCANNING_DEFAULT_INTERVAL
    def _set_scanning_interval(self, value):
        """
        Scanning interval time getter.
        """
        return self._gconf_client.set_int(SCANNING_INTERVAL_GCONF_KEY, value)
    scanning_interval = property(_get_scanning_interval, _set_scanning_interval)

    def scanning_interval_notify_add(self, callback):
        """
        Register callback to be run when the scanning interval time changes.

        Callbacks are called with the new time as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._scanning_interval_callbacks.append(callback)

    def _scanning_interval_notify_cb(self, client, cxion_id, entry,
            user_data):
        """
        Recieve scanning interval change notifications from gconf and run
        callbacks.
        """
        for callback in self._scanning_interval_callbacks:
            callback(self.scanning_interval)

    ####### Snippets #######
    _snippet_callbacks = []
    _snippets_callbacks = []
    def _get_snippets(self):
        """
        List of snippets getter.
        """
        return self.gconf_list_to_dict(SNIPPETS2_GCONF_KEY, int)
    def _set_snippets(self, value): #{"0":("label", "text"), "1":...}
        """
        List of snippets setter.
        """
        self.dict_to_gconf_list(SNIPPETS2_GCONF_KEY, value)
    snippets = property(_get_snippets, _set_snippets)

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

    def snippet_notify_add(self, callback):
        """
        Register callback to be run for each snippet that changes

        Callbacks are called with the snippet index as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._snippet_callbacks.append(callback)

    def snippets_notify_add(self, callback):
        """
        Register callback to be run when the snippets list changes.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._snippets_callbacks.append(callback)

    def _snippets_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve snippets list notifications from gconf and run callbacks.
        """
        snippets = self.snippets

        for callback in self._snippets_callbacks:
            callback(snippets)


        # If the snippets in the two lists don't have the same value or one
        # list has more items than the other do callbacks for each item that
        # differs
        diff = set(snippets.keys()).symmetric_difference( \
                   self._last_snippets.keys())
        for index in diff:
            for callback in self._snippet_callbacks:
                callback(index)

        self._last_snippets = self.snippets


    ####### Status icon #######
    _show_status_icon_callbacks = []
    def _get_show_status_icon(self):
        """
        Status icon visible getter.
        """
        return self._gconf_client.get_bool(SHOW_STATUS_ICON_GCONF_KEY)
    def _set_show_status_icon(self, value):
        """
        Status icon visible setter.
        """
        return self._gconf_client.set_bool(SHOW_STATUS_ICON_GCONF_KEY, value)
    show_status_icon = property(_get_show_status_icon, _set_show_status_icon)

    def show_status_icon_notify_add(self, callback):
        """
        Register callback to be run when the status icon visibility changes.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._show_status_icon_callbacks.append(callback)

    def _show_status_icon_notify_cb(self, client, cxion_id, entry,
            user_data):
        """
        Recieve status icon visibility notifications from gconf and run callbacks.
        """
        for callback in self._show_status_icon_callbacks:
            callback(self.show_status_icon)

    #### Start minimized ####
    _start_minimized_callbacks = []
    def _get_start_minimized(self):
        """
        Start minimized getter.
        """
        return self._gconf_client.get_bool(START_MINIMIZED_GCONF_KEY)
    def _set_start_minimized(self, value):
        """
        Start minimized setter.
        """
        return self._gconf_client.set_bool(START_MINIMIZED_GCONF_KEY, value)
    start_minimized = property(_get_start_minimized, _set_start_minimized)

    def start_minimized_notify_add(self, callback):
        """
        Register callback to be run when the start minimized option changes.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._start_minimized_callbacks.append(callback)

    def _start_minimized_notify_cb(self, client, cxion_id, entry,
            user_data):
        """
        Recieve status icon visibility notifications from gconf and run callbacks.
        """
        for callback in self._start_minimized_callbacks:
            callback(self.start_minimized)

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
            icon_theme = gtk.icon_theme_get_default()
            icon_theme.append_search_path(local_data_path)
            return path
        # when installed
        elif os.path.isdir(INSTALL_DIR):
            return INSTALL_DIR
    install_dir = property(_get_install_dir)

    def _get_user_dir(self):
        return os.path.join(os.path.expanduser("~"), USER_DIR)
    user_dir = property(_get_user_dir)

    ####### IconPalette aka icp ########

    # iconPalette activation option
    def _icp_get_in_use(self):
        """
        iconPalette visible getter.
        """
        return self._gconf_client.get_bool(ICP_IN_USE_GCONF_KEY)

    def _icp_set_in_use(self, value):
        """
        iconPalette visible setter.
        """
        return self._gconf_client.set_bool(ICP_IN_USE_GCONF_KEY, value)

    icp_in_use = property(_icp_get_in_use, _icp_set_in_use)

    # callback for when the iconPalette gets activated/deactivated
    _icp_in_use_change_callbacks = []

    def icp_in_use_change_notify_add(self, callback):
        """
        Register callback to be run when the setting about using
        the IconPalette changes.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._icp_in_use_change_callbacks.append(callback)

    def _icp_in_use_change_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve iconPalette visibility notifications from gconf and run callbacks.
        """
        for callback in self._icp_in_use_change_callbacks:
            callback(self.icp_in_use)


    # iconPalette size
    def _icp_get_width(self):
        """
        iconPalette width getter.
        """
        width = self._gconf_client.get_int(ICP_WIDTH_GCONF_KEY)
        if width:
            return width
        else:
            return ICP_DEFAULT_WIDTH

    def _icp_set_width(self, value):
        """
        iconPalette width setter.
        """
        if value > 0 and \
           value != self._gconf_client.get_int(ICP_WIDTH_GCONF_KEY):
            self._gconf_client.set_int(ICP_WIDTH_GCONF_KEY, int(value))

    icp_width  = property(_icp_get_width, _icp_set_width)

    def _icp_get_height(self):
        """
        iconPalette height getter.
        """
        height = self._gconf_client.get_int(ICP_HEIGHT_GCONF_KEY)
        if height:
            return height
        else:
            return ICP_DEFAULT_HEIGHT

    def _icp_set_height(self, value):
        """
        iconPalette height setter.
        """
        if value > 0 and \
           value != self._gconf_client.get_int(ICP_HEIGHT_GCONF_KEY):
            self._gconf_client.set_int(ICP_HEIGHT_GCONF_KEY, int(value))

    icp_height = property(_icp_get_height, _icp_set_height)

    _icp_size_change_notify_callbacks = []

    def icp_size_change_notify_add(self, callback):
        """
        Register callback to be run when the size of the iconPalette
        changes.

        Callbacks are called with the new size as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._icp_size_change_notify_callbacks.append(callback)

    def _icp_size_change_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve size change notifications from gconf and run callbacks.
        """
        for callback in self._icp_size_change_notify_callbacks:
            callback(self.icp_width, self.icp_height)


    # iconPalette position
    def _icp_get_x_position(self):
        """
        iconPalette x position getter.
        """
        x_pos = self._gconf_client.get_int(ICP_X_POSITION_GCONF_KEY)
        if x_pos:
            return x_pos
        else:
            return ICP_DEFAULT_X_POSITION

    def _icp_set_x_position(self, value):
        """
        iconPalette x position setter.
        """
        if value > 0 and \
           value != self._gconf_client.get_int(ICP_X_POSITION_GCONF_KEY):
            self._gconf_client.set_int(ICP_X_POSITION_GCONF_KEY, int(value))

    icp_x_position = property(_icp_get_x_position, _icp_set_x_position)

    def _icp_get_y_position(self):
        """
        iconPalette y position getter.
        """
        y_pos = self._gconf_client.get_int(ICP_Y_POSITION_GCONF_KEY)
        if y_pos:
            return y_pos
        else:
            return ICP_DEFAULT_Y_POSITION

    def _icp_set_y_position(self, value):
        """
        iconPalette y position setter.
        """
        if value > 0 and \
           value != self._gconf_client.get_int(ICP_Y_POSITION_GCONF_KEY):
            self._gconf_client.set_int(ICP_Y_POSITION_GCONF_KEY, int(value))

    icp_y_position = property(_icp_get_y_position, _icp_set_y_position)

    _icp_position_change_notify_callbacks = []

    def icp_position_change_notify_add(self, callback):
        """
        Register callback to be run when the position of the
        iconPalette changes.

        Callbacks are called with the new position as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._icp_position_change_notify_callbacks.append(callback)

    def _icp_position_change_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve position change notifications from gconf and run callbacks.
        """
        for callback in self._icp_position_change_notify_callbacks:
            callback(self.icp_x_position, self.icp_y_position)


    ####### Modeless gksu password dialogs ########

    # get and set/unset the option
    def _get_modeless_gksu(self):
        """
        Modeless gksu status getter.
        """
        return self._gconf_client.get_bool(MODELESS_GKSU_GCONF_KEY)

    def _set_modeless_gksu(self, value):
        """
        Modeless gksu status setter.
        """
        return self._gconf_client.set_bool(MODELESS_GKSU_GCONF_KEY, value)

    modeless_gksu = property(_get_modeless_gksu, _set_modeless_gksu)

    # list of callbacks that get executed when the modeless gksu status changes
    _modeless_gksu_notify_callbacks = []

    def modeless_gksu_notify_add(self, callback):
        """
        Register callback to be run when the setting about the
        modality of gksu dialog changes.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._modeless_gksu_notify_callbacks.append(callback)

    def _modeless_gksu_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Recieve gksu modality notifications from gconf and run callbacks.
        """
        for callback in self._modeless_gksu_notify_callbacks:
            callback(self.modeless_gksu)


    ####### XEmbedding onboard into gnome-screensaver to unlock screen ########

    # methods concerning the xembed enabled gconf key of onboard
    def _get_onboard_xembed_enabled(self):
        """
        Get status of the onboard xembed enabled checkbox.
        """
        return self._gconf_client.get_bool(ONBOARD_XEMBED_GCONF_KEY)

    def _set_onboard_xembed_enabled(self, value):
        """
        Set status of the onboard xembed enabled checkbox.
        """
        return self._gconf_client.set_bool(ONBOARD_XEMBED_GCONF_KEY, value)

    onboard_xembed_enabled = property(_get_onboard_xembed_enabled, \
                                      _set_onboard_xembed_enabled)

    _onboard_xembed_notify_callbacks = []

    def onboard_xembed_notify_add(self, callback):
        """
        Register callback to be run when there are changes in
        the xembed_onboard gconf key.

        Callbacks are called with the new list as a parameter.

        @type  callback: function
        @param callback: callback to call on change
        """
        self._onboard_xembed_notify_callbacks.append(callback)

    def _onboard_xembed_notify_cb(self, client, cxion_id, entry, user_data):
        """
        Execute callbacks on gconf notifications.
        """
        for callback in self._onboard_xembed_notify_callbacks:
            callback(self.onboard_xembed_enabled)

    # methods concerning the xembed enabled gconf key of the gnome-screensaver
    def _get_gss_xembed_enabled(self):
        """
        Get status of xembed enabled gconf key of the gnome-screensaver.
        """
        return self._gconf_client.get_bool(GSS_XEMBED_ENABLE_GCONF_KEY)

    def _gss_set_xembed_enabled(self, value):
        """
        Set status of xembed enabled gconf key of the gnome-screensaver.
        """
        return self._gconf_client.set_bool(GSS_XEMBED_ENABLE_GCONF_KEY, value)

    gss_xembed_enabled = property(_get_gss_xembed_enabled, \
                                    _gss_set_xembed_enabled)

    # methods concerning the xembed command gconf key of the gnome-screensaver
    def is_onboard_in_xembed_command_string(self):
        """
        Checks whether the gconf key for the embeded application command
        contains the entry defined by onboard.
        Returns True if it is set to onboard and False otherwise.
        """
        if self._gconf_client.get_string(GSS_XEMBED_COMMAND_GCONF_KEY) == \
                                                 START_ONBOARD_XEMBED_COMMAND:
            return True
        else:
            return False

    def set_xembed_command_string_to_onboard(self):
        """
        Write command to start the embedded onboard into the corresponding
        gconf key.
        """
        self._gconf_client.set_string(GSS_XEMBED_COMMAND_GCONF_KEY, \
                                                 START_ONBOARD_XEMBED_COMMAND)


    ####### current_settings_page #######
    def _get_current_settings_page(self):
        return self._gconf_client.get_int(CURRENT_SETTINGS_PAGE_GCONF_KEY)
    def _set_current_settings_page(self, value):
        self._gconf_client.set_int(CURRENT_SETTINGS_PAGE_GCONF_KEY, value)
    current_settings_page = property(_get_current_settings_page,
                                     _set_current_settings_page)


