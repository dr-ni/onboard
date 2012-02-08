# -*- coding: utf-8 -*-
"""
File containing Config singleton.
"""

from __future__ import division, print_function, unicode_literals

import os
import sys
from shutil import copytree
from optparse import OptionParser
from gettext import gettext as _

from gi.repository import GLib, Gtk

from Onboard.utils        import show_confirmation_dialog, Version
from Onboard.WindowUtils  import Handle
from Onboard.ConfigUtils  import ConfigObject
from Onboard.MouseControl import Mousetweaks, ClickMapper
from Onboard.Exceptions   import SchemaError

### Logging ###
import logging
_logger = logging.getLogger("Config")
###############

# gsettings objects
SCHEMA_ONBOARD          = "apps.onboard"
SCHEMA_KEYBOARD         = "apps.onboard.keyboard"
SCHEMA_WINDOW           = "apps.onboard.window"
SCHEMA_WINDOW_LANDSCAPE = "apps.onboard.window.landscape"
SCHEMA_WINDOW_PORTRAIT  = "apps.onboard.window.portrait"
SCHEMA_ICP              = "apps.onboard.icon-palette"
SCHEMA_ICP_LANDSCAPE    = "apps.onboard.icon-palette.landscape"
SCHEMA_ICP_PORTRAIT     = "apps.onboard.icon-palette.portrait"
SCHEMA_AUTO_SHOW        = "apps.onboard.auto-show"
SCHEMA_UNIVERSAL_ACCESS = "apps.onboard.universal-access"
SCHEMA_THEME            = "apps.onboard.theme-settings"
SCHEMA_LOCKDOWN         = "apps.onboard.lockdown"
SCHEMA_SCANNER          = "apps.onboard.scanner"
SCHEMA_GSS              = "org.gnome.desktop.screensaver"
SCHEMA_GDI              = "org.gnome.desktop.interface"

MODELESS_GKSU_KEY = "/apps/gksu/disable-grab"  # old gconf key, unused

# hard coded defaults
DEFAULT_X                  = 100   # Make sure these match the schema defaults,
DEFAULT_Y                  = 50    # else dconf data migration won't happen.
DEFAULT_HEIGHT             = 200
DEFAULT_WIDTH              = 600

DEFAULT_ICP_X              = 100   # Make sure these match the schema defaults,
DEFAULT_ICP_Y              = 50    # else dconf data migration won't happen.
DEFAULT_ICP_HEIGHT         = 64
DEFAULT_ICP_WIDTH          = 64

DEFAULT_LAYOUT             = "Compact"
DEFAULT_THEME              = "Classic Onboard"
DEFAULT_COLOR_SCHEME       = "Classic Onboard"

START_ONBOARD_XEMBED_COMMAND = "onboard --xid"

GTK_KBD_MIXIN_MOD          = "Onboard.KeyboardGTK"
GTK_KBD_MIXIN_CLS          = "KeyboardGTK"

INSTALL_DIR                = "/usr/share/onboard"
LOCAL_INSTALL_DIR          = "/usr/local/share/onboard"
USER_DIR                   = ".onboard"

SYSTEM_DEFAULTS_FILENAME   = "onboard-defaults.conf"

DEFAULT_RESIZE_HANDLES     = list(Handle.RESIZERS)

SCHEMA_VERSION_0_97         = Version(1, 0)   # Onboard 0.97
SCHEMA_VERSION              = SCHEMA_VERSION_0_97


# enum for simplified number of resize_handles
class NumResizeHandles:
    NONE = 0
    SOME = 1
    ALL  = 2


class Config(ConfigObject):
    """
    Singleton Class to encapsulate the gsettings stuff and check values.
    """

    # String representation of the module containing the Keyboard mixin
    # used to draw keyboard
    _kbd_render_mixin_mod = GTK_KBD_MIXIN_MOD

    # String representation of the keyboard mixin used to draw keyboard.
    _kbd_render_mixin_cls = GTK_KBD_MIXIN_CLS

    # extension of layout files
    LAYOUT_FILE_EXTENSION = ".onboard"

    # A copy of snippets so that when the list changes in gsettings we can
    # tell which items have changed.
    _last_snippets = None

    # Margin to leave around labels
    LABEL_MARGIN = (1, 1)

    # Horizontal label alignment
    DEFAULT_LABEL_X_ALIGN = 0.5

    # Vertical label alignment
    DEFAULT_LABEL_Y_ALIGN = 0.5

    # layout group for independently sized superkey labels
    SUPERKEY_SIZE_GROUP = "super"

    # width of frame around onboard when window decoration is disabled
    UNDECORATED_FRAME_WIDTH = 5.0

    # radius of the rounded window corners
    CORNER_RADIUS = 10

    # y displacement of the key face of dish keys
    DISH_KEY_Y_OFFSET = 1.0

    # raised border size of dish keys
    DISH_KEY_BORDER = (2.5, 2.5)

    # index of currently active pane, not stored in gsettings
    active_layer_index = 0

    # protext window move/resize
    drag_protection = True

    def __new__(cls, *args, **kwargs):
        """
        Singleton magic.
        """
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls, args, kwargs)
            cls.self.init()
        return cls.self

    def __init__(self):
        """
        This constructor is still called multiple times.
        Do nothing here and use the singleton constructor "init()" instead.
        Don't call base class constructors.
        """
        pass

    def init(self):
        """
        Singleton constructor, should only run once.
        """
        # parse command line
        parser = OptionParser()
        parser.add_option("-l", "--layout", dest="layout",
                help="Specify layout file ({}) or name" \
                     .format(self.LAYOUT_FILE_EXTENSION))
        parser.add_option("-t", "--theme", dest="theme",
                help="Specify theme file (.theme) or name")
        parser.add_option("-x", type="int", dest="x", help="x coord of window")
        parser.add_option("-y", type="int", dest="y", help="y coord of window")
        parser.add_option("-s", "--size", dest="size",
                help="size widthxheight")
        parser.add_option("-e", "--xid", action="store_true", dest="xid_mode",
                help="XEmbed mode for gnome-screensaver")
        parser.add_option("-a", "--keep-aspect", action="store_true",
                dest="keep_aspect_ratio",
                help="Keep aspect ratio when resizing the window")
        parser.add_option("-d", "--debug", type="str", dest="debug",
            help="DEBUG={notset|debug|info|warning|error|critical}")
        options = parser.parse_args()[0]
        self.options = options

        # setup logging
        log_params = {
            "format" : '%(asctime)s:%(levelname)s:%(name)s: %(message)s'
        }
        if options.debug:
             log_params["level"] = getattr(logging, options.debug.upper())
        if False: # log to file
            log_params["level"] = "DEBUG"
            log_params["filename"] = "/tmp/onboard.log"
            log_params["filemode"] = "w"

        logging.basicConfig(**log_params)

        # call base class constructor once logging is available
        try:
            ConfigObject.__init__(self)
        except SchemaError as e:
            _logger.error(str(e))
            sys.exit()

        # init paths
        self.install_dir = self._get_install_dir()
        self.user_dir = self._get_user_dir()

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

        # Make sure there is a 'Default' entry when tracking the system theme.
        # 'Default' is the theme used when encountering an so far unknown 
        # gtk-theme. 'Default' is added on first start and therefore a
        # corresponding system default is respected.
        theme_assocs = self.system_theme_associations
        if not "Default" in theme_assocs:
            theme_assocs["Default"] = self.theme
            self.system_theme_associations = theme_assocs

        # remember command line theme for system theme tracking
        if options.theme:
            self.remember_theme(self.theme)

        # load theme
        global Theme
        from Onboard.Appearance import Theme
        self.apply_theme()

        # give gtk theme a chance to take over
        self.update_theme_from_system_theme()

        # misc initializations
        self.xid_mode = options.xid_mode
        self._last_snippets = dict(self.snippets)  # store a copy

        # remember state of mousetweaks click-type window
        if self.mousetweaks:
            self.mousetweaks.old_click_type_window_visible = \
                          self.mousetweaks.click_type_window_visible

            if self.mousetweaks.is_active() and \
                self.universal_access.hide_click_type_window:
                self.mousetweaks.click_type_window_visible = False

        # remember if we are running under GDM
        self.running_under_gdm = 'RUNNING_UNDER_GDM' in os.environ

        # tell config objects that their properties are valid now
        self.on_properties_initialized()

        _logger.debug("Leaving _init")

    def cleanup(self):
        # stop dangling main windows from responding when restarting
        # due to changes to window type hint or decoration.
        self.disconnect_notifications()
        self.clickmapper.cleanup()
        if self.mousetweaks:
            self.mousetweaks.cleanup()

    def final_cleanup(self):
        if self.mousetweaks:
            if self.xid_mode:
                self.mousetweaks.click_type_window_visible = \
                        self.mousetweaks.old_click_type_window_visible
            else:
                if self.universal_access.enable_click_type_window_on_exit:
                    self.mousetweaks.click_type_window_visible = True
                else:
                    self.mousetweaks.click_type_window_visible = \
                        self.mousetweaks.old_click_type_window_visible

    def _init_keys(self):
        """ Create key descriptions """

        self.schema = SCHEMA_ONBOARD
        self.sysdef_section = "main"

        self.add_key("schema-version", "") # is assigned SCHEMA_VERSION on first start
        self.add_key("use-system-defaults", False)
        self.layout_key = \
        self.add_key("layout", DEFAULT_LAYOUT)
        self.theme_key  = \
        self.add_key("theme",  DEFAULT_THEME)
        self.add_key("system-theme-tracking-enabled", True)
        self.add_key("system-theme-associations", {})
        self.add_key("snippets", {})
        self.add_key("show-status-icon", True)
        self.add_key("start-minimized", False)
        self.add_key("xembed-onboard", False, "onboard_xembed_enabled")
        self.add_key("show-tooltips", True)
        self.add_key("key-label-font", "")      # default font for all themes
        self.add_key("key-label-overrides", {}) # default labels for all themes
        self.add_key("current-settings-page", 0)

        self.keyboard         = ConfigKeyboard()
        self.window           = ConfigWindow()
        self.icp              = ConfigICP(self)
        self.auto_show        = ConfigAutoShow()
        self.universal_access = ConfigUniversalAccess(self)
        self.theme_settings   = ConfigTheme(self)
        self.lockdown         = ConfigLockdown(self)
        self.gss              = ConfigGSS(self)
        self.gdi              = ConfigGDI(self)
        self.scanner          = ConfigScanner(self)

        self.children = [self.keyboard,
                         self.window,
                         self.icp,
                         self.auto_show,
                         self.universal_access,
                         self.theme_settings,
                         self.lockdown,
                         self.gss,
                         self.gdi,
                         self.scanner]

        try:
            self.mousetweaks = Mousetweaks()
            self.children.append(self.mousetweaks)
        except (SchemaError, ImportError) as e:
            _logger.warning(str(e))
            self.mousetweaks = None

        self.clickmapper = ClickMapper()

    def init_from_gsettings(self):
        """ 
        Overloaded to migrate old dconf data to a new gsettings schema
        """
        ConfigObject.init_from_gsettings(self)

        import osk
        util = osk.Util()

        def migrate_dconf_value(dconf_key, config_object, gskey):
            try:
                value = util.read_dconf_key(dconf_key)
            except (ValueError, TypeError) as e:
                value = None
                _logger.warning("migrate_dconf_value: {}".format(e))

            if not value is None:
                setattr(config_object, gskey.prop, value)
                _logger.debug("migrate_dconf_value: {key} -> {path} {gskey}, value={value}" \
                              .format(key=dconf_key, 
                                      path=co.schema, 
                                      gskey=gskey.key, value=value))

        def migrate_dconf_key(dconf_key, config_object, key):
            gskey = config_object.find_key(key)
            if gskey.is_default():
                migrate_dconf_value(dconf_key, config_object, gskey)

        # --- onboard 0.96 -> 0.97 ---------------------------------------------
        format = Version.from_string(self.schema_version)
        if format < SCHEMA_VERSION_0_97:

            # window rect moves from apps.onboard to 
            # apps.onboard.window.landscape/portrait
            co = self.window.landscape
            if co.gskeys["x"].is_default() and \
               co.gskeys["y"].is_default() and \
               co.gskeys["width"].is_default() and \
               co.gskeys["height"].is_default():

                co.settings.delay()
                migrate_dconf_value("/apps/onboard/x", co, co.gskeys["x"])
                migrate_dconf_value("/apps/onboard/y", co, co.gskeys["y"])
                migrate_dconf_value("/apps/onboard/width", co, co.gskeys["width"])
                migrate_dconf_value("/apps/onboard/height", co, co.gskeys["height"])
                co.settings.apply()
            
            # icon-palette rect moves from apps.onboard.icon-palette to 
            # apps.onboard.icon-palette.landscape/portrait
            co = self.icp.landscape
            if co.gskeys["x"].is_default() and \
               co.gskeys["y"].is_default() and \
               co.gskeys["width"].is_default() and \
               co.gskeys["height"].is_default():

                co.settings.delay()
                migrate_dconf_value("/apps/onboard/icon-palette/x", co, co.gskeys["x"])
                migrate_dconf_value("/apps/onboard/icon-palette/y", co, co.gskeys["y"])
                migrate_dconf_value("/apps/onboard/icon-palette/width", co, co.gskeys["width"])
                migrate_dconf_value("/apps/onboard/icon-palette/height", co, co.gskeys["height"])
                co.settings.apply()

            # move keys from root to window
            co = self.window
            migrate_dconf_key("/apps/onboard/window-decoration", co, "window-decoration")
            migrate_dconf_key("/apps/onboard/force-to-top", co, "force-to-top")
            migrate_dconf_key("/apps/onboard/transparent-background", co, "transparent-background")
            migrate_dconf_key("/apps/onboard/transparency", co, "transparency")
            migrate_dconf_key("/apps/onboard/background-transparency", co, "background-transparency")
            migrate_dconf_key("/apps/onboard/enable-inactive-transparency", co, "enable-inactive-transparency")
            migrate_dconf_key("/apps/onboard/inactive-transparency", co, "inactive-transparency")
            migrate_dconf_key("/apps/onboard/inactive-transparency-delay", co, "inactive-transparency-delay")

            # accessibility keys move from root to universal-access
            co = self.universal_access
            migrate_dconf_key("/apps/onboard/hide-click-type-window", co, "hide-click-type-window")
            migrate_dconf_key("/apps/onboard/enable-click-type-window-on-exit", co, "enable-click-type-window-on-exit")

            # move keys from root to keyboard
            co = self.keyboard
            migrate_dconf_key("/apps/onboard/show-click-buttons", co, "show-click-buttons")

            self.schema_version = SCHEMA_VERSION.to_string()

    ##### handle special keys only valid in system defaults #####
    def _read_sysdef_section(self, parser):
        super(self.__class__, self)._read_sysdef_section(parser)

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

    def _convert_sysdef_key(self, gskey, sysdef, value):
        # key exclusive to system defaults?
        if sysdef in ["superkey-label", \
                      "superkey-label-independent-size"]:
            return value
        else:
            return super(self.__class__, self). \
                         _convert_sysdef_key(gskey, sysdef, value)


    ##### property helpers #####
    def _gsettings_get_key_label_overrides(self, gskey):
        return self.get_unpacked_string_list(gskey, "a{s[ss]}")

    def _gsettings_set_key_label_overrides(self, gskey, value):
        self.set_packed_string_list(gskey, value)

    def _gsettings_get_snippets(self, gskey):
        return self.get_unpacked_string_list(gskey, "a{i[ss]}")

    def _gsettings_set_snippets(self, gskey, value):
        self.set_packed_string_list(gskey, value)

    # Property layout_filename, linked to gsettings key "layout".
    # layout_filename may only get/set a valid filename,
    # whereas layout also allows to get/set only the basename of a layout.
    def layout_filename_notify_add(self, callback):
        self.layout_notify_add(callback)

    def get_layout_filename(self):
        return self._get_user_sys_filename_gs(
             gskey                = self.layout_key,
             user_filename_func   = lambda x: \
                 os.path.join(self.user_dir,    "layouts", x) + \
                 self.LAYOUT_FILE_EXTENSION,
             system_filename_func = lambda x: \
                 os.path.join(self.install_dir, "layouts", x) + \
                 self.LAYOUT_FILE_EXTENSION,
             final_fallback       = os.path.join(self.install_dir,
                                                "layouts", DEFAULT_LAYOUT +
                                                self.LAYOUT_FILE_EXTENSION))
    def set_layout_filename(self, filename):
        if filename and os.path.exists(filename):
            self.layout = filename
        else:
            _logger.warning(_("layout '{filename}' does not exist") \
                            .format(filename=filename))

    layout_filename = property(get_layout_filename, set_layout_filename)


    # Property theme_filename, linked to gsettings key "theme".
    # theme_filename may only get/set a valid filename,
    # whereas theme also allows to get/set only the basename of a theme.
    def theme_filename_notify_add(self, callback):
        self.theme_notify_add(callback)

    def get_theme_filename(self):
        return self._get_user_sys_filename_gs(
             gskey                = self.theme_key,
             user_filename_func   = Theme.build_user_filename,
             system_filename_func = Theme.build_system_filename,
             final_fallback       = os.path.join(self.install_dir,
                                                "themes", DEFAULT_THEME +
                                                "." + Theme.extension()))
    def set_theme_filename(self, filename, save = True):
        if filename and os.path.exists(filename):
            self.set_theme(filename, save)

            # remember currently active gtk theme
            if self.system_theme_tracking_enabled:
                self.remember_theme(filename)
        else:
            _logger.warning(_("theme '{filename}' does not exist") \
                            .format(filename=filename))

    theme_filename = property(get_theme_filename, set_theme_filename)

    def remember_theme(self, theme_filename):
        if self.gdi:   # be defensive
            gtk_theme = self.get_gtk_theme()
            theme_assocs = self.system_theme_associations
            theme_assocs[gtk_theme] = theme_filename
            self.system_theme_associations = theme_assocs

    def _gsettings_get_system_theme_associations(self, gskey):
        return self.get_unpacked_string_list(gskey, "a{ss}")

    def _gsettings_set_system_theme_associations(self, gskey, value):
        self.set_packed_string_list(gskey, value)

    def apply_theme(self):
        theme_filename = self.theme_filename
        _logger.info(_("Loading theme from '{}'").format(theme_filename))

        theme = Theme.load(theme_filename)
        if not theme:
            _logger.error(_("Unable to read theme '{}'").format(theme_filename))
        else:
            # Save to gsettings
            # Make sure gsettings is in sync with onboard (LP: 877601)
            self.theme = theme_filename
            theme.apply()

            # Fix theme not saved to gesettings when switching 
            # system contrast themes. 
            # Possible gsettings bug in Precise (wasn't in Oneiric).
            self.settings.apply()

    def update_theme_from_system_theme(self):
        """ Switches themes for system theme tracking """
        if self.system_theme_tracking_enabled:
            gtk_theme = self.get_gtk_theme()
            theme_assocs = self.system_theme_associations

            new_theme = theme_assocs.get(gtk_theme, None)
            if not new_theme:
                new_theme = theme_assocs.get("Default", None)
                if not new_theme:
                    new_theme = DEFAULT_THEME

            self.theme = new_theme
            self.apply_theme()

    def get_gtk_theme(self):
        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings:   # be defensive, don't know if this can fail
            gtk_theme = gtk_settings.get_property('gtk-theme-name')
            return gtk_theme
        return None

    def get_image_filename(self, image_filename):
        """
        Returns an absolute path for a label image.
        This function isn't linked to any gsettings key.'
        """
        return self._get_user_sys_filename(
             filename             = image_filename,
             description          = "image",
             user_filename_func   = lambda x: \
                 os.path.join(self.user_dir,    "layouts", "images", x),
             system_filename_func = lambda x: \
                 os.path.join(self.install_dir, "layouts", "images", x))

    def allow_system_click_type_window(self, allow):
        """ called from hover click button """
        if not self.mousetweaks:
            return

        # This assumes that mousetweaks.click_type_window_visible never
        # changes between activation and deactivation of mousetweaks.
        if allow:
            self.mousetweaks.click_type_window_visible = \
                self.mousetweaks.old_click_type_window_visible
        else:
            # hide the mousetweaks window when onboard's settings say so
            if self.universal_access.hide_click_type_window:

                self.mousetweaks.old_click_type_window_visible = \
                            self.mousetweaks.click_type_window_visible

                self.mousetweaks.click_type_window_visible = False

    def enable_hover_click(self, enable):
        if enable:
            self.allow_system_click_type_window(False)
            self.mousetweaks.set_active(True)
        else:
            self.mousetweaks.set_active(False)
            self.allow_system_click_type_window(True)

    def is_visible_on_start(self):
        return not self.xid_mode and \
               not self.start_minimized and \
               not self.auto_show.enabled

    def is_auto_show_enabled(self):
        return not self.xid_mode and \
               self.auto_show.enabled

    def get_frame_width(self):
        """ width of the frame around the keyboard """
        if self.xid_mode:
            return 1.0
        elif self.has_window_decoration():
            return 0.0
        elif self.window.transparent_background:
            return 1.0
        else:
            return self.UNDECORATED_FRAME_WIDTH

    def check_gnome_accessibility(self, parent = None):
        if not self.xid_mode and \
           not self.gdi.toolkit_accessibility:
            question = _("Enabling auto-show requires Gnome Accessibility.\n\n"
                         "Onboard can turn on accessiblity now, however it is "
                         "recommende to log out and back in "
                         "for it to reach its full potential.\n\n"
                         "Enable accessibility now?")
            reply = show_confirmation_dialog(question, parent)
            if not reply == True:
                return False

            self.gdi.toolkit_accessibility = True

        return True

    def get_drag_threshold(self):
        threshold = self.universal_access.gskeys["drag_threshold"].value
        if threshold == -1:
            # get the systems DND threshold
            threshold = Gtk.Settings.get_default(). \
                                    get_property("gtk-dnd-drag-threshold")
        return threshold

    def is_icon_palette_in_use(self):
        """
        Show icon palette when there is no other means to unhide onboard.
        Unhiding by unity launcher isn't available in force-to-top mode.
        """
        return self.icp.in_use or self.is_icon_palette_last_unhide_option()

    def is_icon_palette_last_unhide_option(self):
        """
        Is the icon palette the last remaining way to unhide onboard?
        Unhiding by unity launcher isn't available in force-to-top mode.
        """
        return self.window.force_to_top and not self.show_status_icon

    def has_window_decoration(self):
        """ Force-to-top mode doesn't support window decoration """
        return self.window.window_decoration and not self.window.force_to_top

    def get_sticky_state(self):
        return not self.xid_mode and \
               (self.window.window_state_sticky or self.window.force_to_top)
               
    def is_inactive_transparency_enabled(self):
        return self.window.enable_inactive_transparency and \
               not self.scanner.enabled
    
    ####### resize handles #######
    def resize_handles_notify_add(self, callback):
        self.window.resize_handles_notify_add(callback)
        self.icp.resize_handles_notify_add(callback)

    def get_num_resize_handles(self):
        """ Translate array of handles to simplified NumResizeHandles enum """
        handles = self.window.resize_handles
        if len(handles) == 0:
            return NumResizeHandles.NONE
        if len(handles) == 8:
            return NumResizeHandles.ALL
        return NumResizeHandles.SOME

    def set_num_resize_handles(self, num):
        if num == NumResizeHandles.ALL:
            window_handles = list(Handle.RESIZERS) 
            icp_handles    = list(Handle.RESIZERS)
        elif num == NumResizeHandles.NONE:
            window_handles = []
            icp_handles    = []
        else:
            window_handles = list(Handle.CORNERS)
            icp_handles    = [Handle.SOUTH_EAST]

        self.window.resize_handles = window_handles
        self.icp.resize_handles = icp_handles

    @staticmethod
    def _string_to_handles(string):
        """ String of handle ids to array of Handle enums """
        ids = string.split()
        handles = []
        for id in ids:
            handle = Handle.RIDS.get(id)
            if not handle is None:
                handles.append(handle)
        return handles

    @staticmethod
    def _handles_to_string(handles):
        """ Array of handle enums to string of handle ids """
        ids = []
        for handle in handles:
            ids.append(Handle.IDS[handle])
        return " ".join(ids)

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
        snippets = dict(self.snippets) # copy to enable callbacks
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
        snippets = dict(self.snippets) # copy to enable callbacks
        del snippets[index]
        self.snippets = snippets


    ###### gnome-screensaver, xembedding #####
    def enable_gss_embedding(self, enable):
        if enable:
            self.onboard_xembed_enabled = True
            self.gss.embedded_keyboard_enabled = True
            self.set_xembed_command_string_to_onboard()
        else:
            self.onboard_xembed_enabled = False
            self.gss.embedded_keyboard_enabled = False

    def is_onboard_in_xembed_command_string(self):
        """
        Checks whether the gsettings key for the embeded application command
        contains the entry defined by onboard.
        Returns True if it is set to onboard and False otherwise.
        """
        if self.gss.embedded_keyboard_command.startswith(START_ONBOARD_XEMBED_COMMAND):
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
        result = None

        # when run from source
        src_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src_data_path = os.path.join(src_path, "data")
        if os.path.isfile(os.path.join(src_data_path, "onboard.gschema.xml")):
            # Add the data directory to the icon search path
            icon_theme = Gtk.IconTheme.get_default()
            src_icon_path = os.path.join(src_path, "icons")
            icon_theme.append_search_path(src_icon_path)
            result = src_path
        # when installed to /usr/local
        elif os.path.isdir(LOCAL_INSTALL_DIR):
            result = LOCAL_INSTALL_DIR
        # when installed to /usr
        elif os.path.isdir(INSTALL_DIR):
            result = INSTALL_DIR
    
        assert(result)  # warn early when the installation dir wasn't found
        return result

    def _get_user_dir(self):
        return os.path.join(os.path.expanduser("~"), USER_DIR)


class ConfigKeyboard(ConfigObject):
    """Window configuration """

    def _init_keys(self):
        self.schema = SCHEMA_KEYBOARD
        self.sysdef_section = "keyboard"

        self.add_key("show-click-buttons", False)
        self.add_key("sticky-key-release-delay", 0.0)
        self.add_key("sticky-key-behavior", {"all" : "cycle"})

    def _gsettings_get_sticky_key_behavior(self, gskey):
        _list = gskey.settings.get_strv(gskey.key)

        # Omitted key group/id means "all" keys
        for i, x in enumerate(_list):
            if not ":" in x:
                _list[i] = "all:" + x

        return self.unpack_string_list(_list, 'a{ss}')
 
    def _gsettings_set_sticky_key_behavior(self, gskey, value):
        return self.set_packed_string_list(gskey, value)

    #    gskey.settings.set_strv(gskey.key, _list)
     #   self._dict_to_gsettings_list(gskey, value)

#    def _gsettings_get_sticky_key_behavior(self, gskey):
#        return gskey.settings.get_value(gskey.key).unpack()

#    def _gsettings_set_sticky_key_behavior(self, gskey, value):
#        gskey.settings.set_value(gskey.key, GLib.Variant('a{ss}', value))

class ConfigWindow(ConfigObject):
    """Window configuration """

    def _init_keys(self):
        self.schema = SCHEMA_WINDOW
        self.sysdef_section = "window"

        self.add_key("window-state-sticky", True)
        self.add_key("window-decoration", False)
        self.add_key("force-to-top", False)
        self.add_key("keep-aspect-ratio", False)
        self.add_key("transparent-background", False)
        self.add_key("transparency", 0.0)
        self.add_key("background-transparency", 10.0)
        self.add_key("enable-inactive-transparency", False)
        self.add_key("inactive-transparency", 50.0)
        self.add_key("inactive-transparency-delay", 1.0)
        self.add_key("resize-handles", DEFAULT_RESIZE_HANDLES)

        self.landscape = ConfigWindow.Landscape(self)
        self.portrait = ConfigWindow.Portrait(self)

        self.children = [self.landscape, self.portrait]

    ##### property helpers #####
    def _convert_sysdef_key(self, gskey, sysdef, value):
        if sysdef == "resize-handles":
            return Config._string_to_handles(value)
        else:
            return ConfigObject._convert_sysdef_key(self, gskey, sysdef, value)

    def _gsettings_get_resize_handles(self, gskey):
        value = self.settings.get_string(gskey.key)
        return Config._string_to_handles(value)

    def _gsettings_set_resize_handles(self, gskey, handles):
        value = Config._handles_to_string(handles)
        self.settings.set_string(gskey.key, value)

    def position_notify_add(self, callback):
        self.landscape.x_notify_add(callback)
        self.landscape.y_notify_add(callback)
        self.portrait.x_notify_add(callback)
        self.portrait.y_notify_add(callback)

    def size_notify_add(self, callback):
        self.landscape.width_notify_add(callback)
        self.landscape.height_notify_add(callback)
        self.portrait.width_notify_add(callback)
        self.portrait.height_notify_add(callback)

    class Landscape(ConfigObject):
        def _init_keys(self):
            self.schema = SCHEMA_WINDOW_LANDSCAPE
            self.sysdef_section = "window.landscape"

            self.add_key("x", DEFAULT_X)
            self.add_key("y", DEFAULT_Y)
            self.add_key("width", DEFAULT_WIDTH)
            self.add_key("height", DEFAULT_HEIGHT)

    class Portrait(ConfigObject):
        def _init_keys(self):
            self.schema = SCHEMA_WINDOW_PORTRAIT
            self.sysdef_section = "window.portrait"

            self.add_key("x", DEFAULT_X)
            self.add_key("y", DEFAULT_Y)
            self.add_key("width", DEFAULT_WIDTH)
            self.add_key("height", DEFAULT_HEIGHT)


class ConfigICP(ConfigObject):
    """ Icon palette configuration """
 
    def _init_keys(self):
        self.schema = SCHEMA_ICP
        self.sysdef_section = "icon-palette"

        self.add_key("in-use", False)
        self.add_key("resize-handles", DEFAULT_RESIZE_HANDLES)

        self.landscape = ConfigICP.Landscape(self)
        self.portrait = ConfigICP.Portrait(self)

        self.children = [self.landscape, self.portrait]

    ##### property helpers #####
    def _convert_sysdef_key(self, gskey, sysdef, value):
        if sysdef == "resize-handles":
            return Config._string_to_handles(value)
        else:
            return ConfigObject._convert_sysdef_key(self, gskey, sysdef, value)

    def _gsettings_get_resize_handles(self, gskey):
        value = self.settings.get_string(gskey.key)
        return Config._string_to_handles(value)

    def _gsettings_set_resize_handles(self, gskey, handles):
        value = Config._handles_to_string(handles)
        self.settings.set_string(gskey.key, value)

    def position_notify_add(self, callback):
        self.landscape.x_notify_add(callback)
        self.landscape.y_notify_add(callback)
        self.portrait.x_notify_add(callback)
        self.portrait.y_notify_add(callback)

    def size_notify_add(self, callback):
        self.landscape.width_notify_add(callback)
        self.landscape.height_notify_add(callback)
        self.portrait.width_notify_add(callback)
        self.portrait.height_notify_add(callback)

    class Landscape(ConfigObject):
        def _init_keys(self):
            self.schema = SCHEMA_ICP_LANDSCAPE
            self.sysdef_section = "icon-palette.landscape"

            self.add_key("x", DEFAULT_ICP_X)
            self.add_key("y", DEFAULT_ICP_Y)
            self.add_key("width", DEFAULT_ICP_WIDTH)
            self.add_key("height", DEFAULT_ICP_HEIGHT)

    class Portrait(ConfigObject):
        def _init_keys(self):
            self.schema = SCHEMA_ICP_PORTRAIT
            self.sysdef_section = "icon-palette.portrait"

            self.add_key("x", DEFAULT_ICP_X)
            self.add_key("y", DEFAULT_ICP_Y)
            self.add_key("width", DEFAULT_ICP_WIDTH)
            self.add_key("height", DEFAULT_ICP_HEIGHT)


class ConfigAutoShow(ConfigObject):
    """ auto_show configuration """

    def _init_keys(self):
        self.schema = SCHEMA_AUTO_SHOW
        self.sysdef_section = "auto-show"

        self.add_key("enabled", False)
        self.add_key("unoccluded-margin", 40.0)


class ConfigUniversalAccess(ConfigObject):
    """ universal_access configuration """

    def _init_keys(self):
        self.schema = SCHEMA_UNIVERSAL_ACCESS
        self.sysdef_section = "universal-access"

        self.add_key("drag-threshold", -1)
        self.add_key("hide-click-type-window", True)
        self.add_key("enable-click-type-window-on-exit", True)

    def _post_notify_hide_click_type_window(self):
        """ called when changed in gsettings (preferences window) """
        mousetweaks = self.parent.mousetweaks

        if not mousetweaks:
            return
        if mousetweaks.is_active():
            if self.hide_click_type_window:
                mousetweaks.click_type_window_visible = False
            else:
                mousetweaks.click_type_window_visible = \
                            mousetweaks.old_click_type_window_visible


class ConfigTheme(ConfigObject):
    """ Theme configuration """

    def _init_keys(self):
        self.schema = SCHEMA_THEME
        self.sysdef_section = "theme-settings"

        self.add_key("color-scheme", DEFAULT_COLOR_SCHEME,
                     prop="color_scheme_filename")
        self.add_key("key-style", "flat")
        self.add_key("roundrect-radius", 0.0)
        self.add_key("key-size", 100.0)
        self.add_key("key-fill-gradient", 0.0)
        self.add_key("key-stroke-gradient", 0.0)
        self.add_key("key-gradient-direction", 0.0)
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

    def _can_set_color_scheme_filename(self, filename):
        if not os.path.exists(filename):
            _logger.warning(_("color scheme '{filename}' does not exist") \
                            .format(filename=filename))
            return False
        return True

    def _gsettings_get_key_label_overrides(self, gskey):
        return self.get_unpacked_string_list(gskey, "a{s[ss]}")

    def _gsettings_set_key_label_overrides(self, gskey, value):
        self.set_packed_string_list(gskey, value)

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


class ConfigLockdown(ConfigObject):
    """ Lockdown/Kiosk mode configuration """

    def _init_keys(self):
        self.schema = SCHEMA_LOCKDOWN
        self.sysdef_section = "lockdown"

        self.add_key("disable-click-buttons", False)
        self.add_key("disable-hover-click", False)
        self.add_key("disable-preferences", False)
        self.add_key("disable-quit", False)
        self.add_key("disable-touch-handles", False)

    def lockdown_notify_add(self, callback):
        self.disable_click_buttons_notify_add(callback)
        self.disable_hover_click_notify_add(callback)
        self.disable_preferences_notify_add(callback)
        self.disable_quit_notify_add(callback)


class ConfigGSS(ConfigObject):
    """ gnome-screen-saver configuration keys"""

    def _init_keys(self):
        self.schema = SCHEMA_GSS
        self.sysdef_section = "gnome-screen-saver"

        self.add_key("embedded-keyboard-enabled", True)
        self.add_key("embedded-keyboard-command", "")


class ConfigGDI(ConfigObject):
    """ Key to enable Gnome Accessibility"""

    def _init_keys(self):
        self.schema = SCHEMA_GDI
        self.sysdef_section = "gnome-desktop-interface"

        self.add_key("toolkit-accessibility", False)
        self.add_key("gtk-theme", "", writable=False)  # read_only for safety


class ConfigScanner(ConfigObject):
    """ Scanner configuration """

    DEFAULT_INTERVAL          = 1.20
    DEFAULT_INTERVAL_FAST     = 0.05
    DEFAULT_MODE              = 0 # AutoScan
    DEFAULT_CYCLES            = 2
    DEFAULT_BACKTRACK         = 5
    DEFAULT_ALTERNATE         = False
    DEFAULT_USER_SCAN         = False
    DEFAULT_DEVICE_NAME       = "Default"
    DEFAULT_DEVICE_KEY_MAP    = {}
    DEFAULT_DEVICE_BUTTON_MAP = { 1: 0, 3: 5 } # Button 1: Step, Button 3: Activate
    DEFAULT_FEEDBACK_FLASH    = True

    def _init_keys(self):
        self.schema = SCHEMA_SCANNER
        self.sysdef_section = "scanner"

        self.add_key("enabled", False)
        self.add_key("mode", self.DEFAULT_MODE)
        self.add_key("interval", self.DEFAULT_INTERVAL)
        self.add_key("interval-fast", self.DEFAULT_INTERVAL_FAST)
        self.add_key("cycles", self.DEFAULT_CYCLES)
        self.add_key("backtrack", self.DEFAULT_BACKTRACK)
        self.add_key("alternate", self.DEFAULT_ALTERNATE)
        self.add_key("user-scan", self.DEFAULT_USER_SCAN)
        self.add_key("device-name", self.DEFAULT_DEVICE_NAME)
        self.add_key("device-detach", False)
        self.add_key("device-key-map", self.DEFAULT_DEVICE_KEY_MAP)
        self.add_key("device-button-map", self.DEFAULT_DEVICE_BUTTON_MAP)
        self.add_key("feedback-flash", self.DEFAULT_FEEDBACK_FLASH)

    def _gsettings_get_mode(self, gskey):
        return gskey.settings.get_enum(gskey.key)

    def _gsettings_set_mode(self, gskey, value):
        gskey.settings.set_enum(gskey.key, value)

    def _gsettings_get_device_key_map(self, gskey):
        return gskey.settings.get_value(gskey.key).unpack()

    def _gsettings_set_device_key_map(self, gskey, value):
        gskey.settings.set_value(gskey.key, GLib.Variant('a{ii}', value))

    def _gsettings_get_device_button_map(self, gskey):
        return gskey.settings.get_value(gskey.key).unpack()

    def _gsettings_set_device_button_map(self, gskey, value):
        gskey.settings.set_value(gskey.key, GLib.Variant('a{ii}', value))

