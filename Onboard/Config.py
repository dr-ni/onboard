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

from gettext import gettext as _

KEYBOARD_WIDTH_GCONF_KEY    = "/apps/onboard/width"
KEYBOARD_HEIGHT_GCONF_KEY   = "/apps/onboard/height"
LAYOUT_FILENAME_GCONF_KEY   = "/apps/onboard/layout_filename"
X_POSITION_GCONF_KEY        = "/apps/onboard/horizontal_position"
Y_POSITION_GCONF_KEY        = "/apps/onboard/vertical_position"
SCANNING_GCONF_KEY          = "/apps/onboard/enable_scanning"
SCANNING_INTERVAL_GCONF_KEY = "/apps/onboard/scanning_interval"
SNIPPETS_GCONF_KEY          = "/apps/onboard/snippets"
SHOW_STATUS_ICON_GCONF_KEY  = "/apps/onboard/use_status_icon"
START_MINIMIZED_GCONF_KEY   = "/apps/onboard/start_minimized"

KEYBOARD_DEFAULT_HEIGHT   = 800
KEYBOARD_DEFAULT_WIDTH    = 300

SCANNING_DEFAULT_INTERVAL = 750

GTK_KBD_MIXIN_MOD = "Onboard.KeyboardGTK"
GTK_KBD_MIXIN_CLS = "KeyboardGTK"

INSTALL_DIR = "/usr/share/onboard"

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

    _set_height = None
    """ Height when set on cmd line """

    _set_width = None
    """ Width when set on cmd line """

    _old_snippets = None
    """
    A copy of snippets so that when the list changes in gconf we can tell which
    items have changed.
    """

    SIDEBARWIDTH = 60
    """ Width of sidebar buttons """

    DEFAULT_LABEL_OFFSET = (2.0, 0.0)
    """ Offset of label from key edge when not specified in layout"""

    LABEL_MARGIN = (4,0)
    """ Margin to leave around labels """

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
        parser.add_option("-l", "--layout", dest="filename",
                help="Specify layout .onboard file")
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
        self._gconf_client.notify_add(SNIPPETS_GCONF_KEY,
                self._snippets_notify_cb)

        self._old_snippets = self.snippets

        if (options.size):
            size = options.size.split("x")
            self._set_width  = int(size[0])
            self._set_height = int(size[1])

        if (options.x):
            self.x_position = int(options.x)
        if (options.y):
            self.y_position = int(options.y)

        # Find layout
        if options.filename:
            filename = options.filename
        else:
            filename = self._gconf_client.get_string(LAYOUT_FILENAME_GCONF_KEY)

        if filename and not os.path.exists(filename):
            _logger.warning("Can't load %s loading default layout instead" %
                filename)
            filename = ''

        if not filename:
            filename = os.path.join(self.install_dir,
                    "layouts", "Default.onboard")

        if not os.path.exists(filename):
            raise Exception("Unable to find layout %s" % filename)
        self.__filename = filename

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

        self.xid_mode = options.xid_mode

        _logger.debug("Leaving _init")

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
        if not os.path.exists(filename):
            _logger.warning("layout %s does not exist" % filename)
        else:
            self.__filename = filename

        for callback in self._layout_filename_notify_callbacks:
            callback(filename)

    def _get_layout_filename(self):
        """
        Layout filename getter.
        """
        return self.__filename
    def _set_layout_filename(self, value):
        """
        Layout filename setter, TODO check valid.

        @type  value: str
        @param value: Absolute path to the layout description file.
        """
        self._gconf_client.set_string(LAYOUT_FILENAME_GCONF_KEY, value)
    layout_filename = property(_get_layout_filename, _set_layout_filename)

    ####### Geometry ########
    _geometry_notify_callbacks = []
    def _get_keyboard_height(self):
        """
        Keyboard height getter, check height is greater than 1.
        """
        if self._set_height:
            height = self._set_height
        else:
            height = self._gconf_client.get_int(KEYBOARD_HEIGHT_GCONF_KEY)

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
        if self._set_width:
            width = self._set_width
        else:
            width = self._gconf_client.get_int(KEYBOARD_WIDTH_GCONF_KEY)

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
        return self._gconf_client.get_list(SNIPPETS_GCONF_KEY,
                gconf.VALUE_STRING)
    def _set_snippets(self, value):
        """
        List of snippets setter.
        """
        self._gconf_client.set_list(SNIPPETS_GCONF_KEY, gconf.VALUE_STRING,
                value)
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

        snippets = self.snippets
        for n in range(1 + index - len(snippets)):
            snippets.append("")
        _logger.info("Setting snippet %d to %s" % (index, value))
        snippets[index] = value
        self.snippets = snippets

    def del_snippet(self, index):
        _logger.info("Deleting snippet %d" % index)
        snippets = self.snippets
        snippets[index] = ""
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

        length_of_shortest = min(len(snippets), len(self._old_snippets))
        length_of_longest = max(len(snippets), len(self._old_snippets))
        for index in range(length_of_shortest):
            if snippets[index] != self._old_snippets[index]:
                for callback in self._snippet_callbacks:
                    callback(index)

        for index in range(length_of_shortest, length_of_longest):
            for callback in self._snippet_callbacks:
                callback(index)

        self._old_snippets = self.snippets


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
