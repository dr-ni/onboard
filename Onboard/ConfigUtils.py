"""
File containing ConfigObject.
"""

import os
import ConfigParser as configparser
from ast import literal_eval
from gettext import gettext as _

from gi.repository import Gio

from Onboard.utils import pack_name_value_list, unpack_name_value_list

### Logging ###
import logging
_logger = logging.getLogger("ConfigUtils")
###############

_CAN_SET_HOOK       = "_can_set_"       # return tru if value is valid
_GSETTINGS_GET_HOOK = "_gsettings_get_" # retrieve from gsettings
_GSETTINGS_SET_HOOK = "_gsettings_set_" # store into gsettings
_POST_NOTIFY_HOOK   = "_post_notify_"   # runs after all listeners notified
_NOTIFY_CALLBACKS   = "_{}_notify_callbacks" # name of list of callbacka

class ConfigObject(object):
    """
    Class for a configuration object with multiple key-value tuples.
    It aims to unify the handling of python properties, gsettings keys,
    system default keys and command line options.

    Python properties and notification functions are created
    automagically for all keys added in _init_keys().
    """
    def __init__(self, parent = None, gspath = ""):
        self.parent = parent       # parent ConfigObject
        self.children = []         # child config objects; not necessarily
                                   #   reflecting the gsettings hierarchy
        self.gspath = gspath       # path to the gsettings object
        self.gskeys = {}           # key-value objects {property name, GSKey()}
        self.sysdef_section = None # system defaults section name
        self.system_defaults = {}  # system defaults {property name, value}

        # add keys in here
        self._init_keys()

        self.settings = Gio.Settings.new(self.gspath)
        for gskey in self.gskeys.values():
            gskey.settings = self.settings
            self._setup_property(gskey)

        # check hook function names
        self.check_hooks()

    def _init_keys(self):
        """ overload this and use add_key() to add key-value tuples """
        pass

    def add_key(self, key, default, prop = None, sysdef = None):
        """ Convenience function to create and add a new GSKey. """
        gskey = GSKey(None, key, default, prop, sysdef)
        self.gskeys[gskey.prop] = gskey
        return gskey

    def check_hooks(self):
        """
        Simple runtime plausibility check on all overloaded hook functions.
        Does the property part of the function name reference an existing
        config property?
        """
        prefixes = [_CAN_SET_HOOK,
                    _GSETTINGS_GET_HOOK,
                    _GSETTINGS_SET_HOOK,
                    _POST_NOTIFY_HOOK]

        for member in dir(self):
            for prefix in prefixes:
                if member.startswith(prefix):
                    prop = member[len(prefix):]
                    if not prop in self.gskeys:
                        raise NameError(
                            "'{}' looks like a ConfigObject hook function, but "
                            "'{}' is not a known property of '{}'"
                            .format(member, prop, str(self)))

    def _setup_property(self, gskey):
        """ Setup python property and notification callback """
        prop = gskey.prop

        # list of callbacks
        setattr(type(self), _NOTIFY_CALLBACKS.format(prop), [])

        # method to add callbak
        def _notify_add(self, callback, _prop=prop):
            """ method to add a callback to this property """
            getattr(self, _NOTIFY_CALLBACKS.format(prop)).append(callback)
        setattr(type(self), prop+'_notify_add', _notify_add)

        # gsettings callback
        def _notify_changed_cb(self, settings, key, _gskey=gskey, _prop=prop):
            """ call back function for change notification """
            # get-gsettings hook, for reading values from gsettings
            # in non-standard ways, i.e. convert data types.
            if hasattr(self, _GSETTINGS_GET_HOOK +_prop):
                value = getattr(self, _GSETTINGS_GET_HOOK +_prop)(_gskey)
            else:
                value = _gskey.gsettings_get()

            # Can-set hook, for value validation.
            if not hasattr(self, _CAN_SET_HOOK + _prop) or \
                   getattr(self, _CAN_SET_HOOK + _prop)(value):
                _gskey.value = value
                for callback in getattr(self, _NOTIFY_CALLBACKS.format(prop)):
                    callback(value)

            # Post-notification hook for anything that properties
            # need to do after all listeners have been notified.
            if hasattr(self, _POST_NOTIFY_HOOK + _prop):
                getattr(self, _POST_NOTIFY_HOOK + _prop)()

        setattr(type(self), '_'+prop+'_changed_cb', _notify_changed_cb)

        # connect callback function to gsettings
        if gskey.settings:
            gskey.settings.connect("changed::"+gskey.key,
                                    getattr(self, '_'+prop+'_changed_cb'))

        # getter function
        def get_value(self, _gskey = gskey, _prop = prop):
            """ property getter """
            return _gskey.value

        # setter function
        def set_value(self, value, save = True, _gskey = gskey, _prop = prop):
            """ property setter """
            # can-set hook, for value validation
            if not hasattr(self, _CAN_SET_HOOK +_prop) or \
                   getattr(self, _CAN_SET_HOOK +_prop)(value):

                if save:
                    # save to gsettings
                    if hasattr(self, _GSETTINGS_SET_HOOK + _prop):
                        # gsettings-set hook, custom value setter
                        getattr(self, _GSETTINGS_SET_HOOK +_prop)(_gskey, value)
                    else:
                        if value != _gskey.gsettings_get():
                            _gskey.gsettings_set(value)

                _gskey.value = value

        # create propery
        if not hasattr(self, 'get_'+prop):   # allow overloading
            setattr(type(self), 'get_'+prop, get_value)
        if not hasattr(self, 'set_'+prop):   # allow overloading
            setattr(type(self), 'set_'+prop, set_value)
        setattr(type(self), prop,
                            property(getattr(type(self), 'get_'+prop),
                                     getattr(type(self), 'set_'+prop)))

    def init_properties(self, options):
        """ initialize the values of all properties """

        # start from hard coded defaults, then try gsettings
        self.init_from_gsettings()

        # let system defaults override gsettings
        if self.use_system_defaults:
            self.init_from_system_defaults()
            self.use_system_defaults = False    # write to gsettings

        # let command line options override everything
        for gskey in self.gskeys.values():
            if hasattr(options, gskey.key):  # command line option there?
                value = getattr(options, gskey.key)
                if not value is None:
                    gskey.value = value

    def init_from_gsettings(self):
        """ init propertiy values from gsettings """

        for prop, gskey in self.gskeys.items():
            gskey.value = gskey.default
            if hasattr(self, _GSETTINGS_GET_HOOK + prop):
                gskey.value = getattr(self, _GSETTINGS_GET_HOOK + prop)(gskey)
            else:
                gskey.value = gskey.gsettings_get()

        for child in self.children:
            child.init_from_gsettings()

    def init_from_system_defaults(self):
        """ fill property values with system defaults """

        for prop, value in self.system_defaults.items():
            setattr(self, prop, value)  # write to gsettings

        for child in self.children:
            child.init_from_system_defaults()

    @staticmethod
    def _get_user_sys_filename(gskey, final_fallback, \
                            user_filename_func = None,
                            system_filename_func = None):
        """
        Checks a filenames validity and if necessary expands it to
        a full filename pointing to either the user or system directory.
        User directory has precedence over the system one.
        """
        filename    = gskey.value
        description = gskey.key

        if filename and not os.path.exists(filename):
            # assume theme is just a basename
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

    @staticmethod
    def _dict_to_gsettings_list(gskey, _dict):
        """ Store dictionary in a gsettings list key """
        _list = pack_name_value_list(_dict)
        gskey.settings.set_strv(gskey.key, _list)

    @staticmethod
    def _gsettings_list_to_dict(gskey, key_type = str):
        """ Get dictionary from a gsettings list key """
        _list = gskey.settings.get_strv(gskey.key)

        _list = [x.decode("utf-8") for x in _list]  # translate to unicode

        return unpack_name_value_list(_list, key_type=key_type)


    def load_system_defaults(self, paths):
        """
        System default settings can be optionally provided for distribution
        specific customization or branding.
        They are stored in simple ini-style files, residing in a small choice
        of directories. The last setting found in the list of paths wins.
        """
        _logger.info(_("Looking for system defaults in %s") % str(paths))

        filename = None
        parser = configparser.SafeConfigParser()
        try:
            filename = parser.read(paths)
        except configparser.ParsingError as ex:
            _logger.error(_("Failed to read system defaults. " + str(ex)))

        if not filename:
            _logger.info(_("No system defaults found."))
        else:
            _logger.info(_("Loading system defaults from %s.") % filename)
            self.read_sysdef_section(parser)


    def read_sysdef_section(self, parser):
        """
        Read this instances (and its childrens) system defaults section.
        """

        for child in self.children:
            child.read_sysdef_section(parser)

        self.system_defaults = {}
        if self.sysdef_section and \
           parser.has_section(self.sysdef_section):
            items = parser.items(self.sysdef_section)
            items = [(key, val.decode("UTF-8")) for key, val in items]

            # convert ini file strings to property values
            sysdef_gskeys = dict((k.sysdef, k) for k in self.gskeys.values())
            for sysdef, value in items:
                _logger.debug(_(u"Found system default '{}={}'") \
                              .format(sysdef, value))

                gskey = sysdef_gskeys.get(sysdef, None)
                value = self.convert_sysdef_key(gskey, sysdef, value)

                if not value is None:
                    prop = gskey.prop if gskey else sysdef.replace("-", "_")
                    self.system_defaults[prop] = value


    def convert_sysdef_key(self, gskey, sysdef, value):
        """ Convert a system default string into a property value. """

        if gskey is None:
            _logger.warning(_(u"System defaults: Unknown key '{}' "
                              u"in section '{}'") \
                              .format(sysdef, self.sysdef_section))
        else:
            _type = type(gskey.default)
            if _type == str and value[0] != u'"':
                value = u'"' + value + '"'
            try:
                value = literal_eval(value)
            except (ValueError, SyntaxError) as ex:
                _logger.warning(_(u"System defaults: Invalid value"
                                  u" for key '{}' in section '{}'"
                                  u"\n  {}").format(sysdef,
                                                    self.sysdef_section, ex))
                return None  # skip key
        return value


class GSKey:
    """
    Class for a key-value tuple for ConfigObject.
    It associates python properties with gsettings keys,
    system default keys and command line options.
    """
    def __init__(self, settings, key, default, prop, sysdef):
        if prop is None:
            prop = key.replace("-","_")
        if sysdef is None:
            sysdef = key
        self.settings = settings # gsettings object
        self.key      = key      # gsettings key name
        self.sysdef   = sysdef   # system default name
        self.prop     = prop     # python property name
        self.default  = default  # hard coded default, determines type
        self.value    = default  # current property value

    def gsettings_get(self):
        """ Get value from gsettings. """
        try:
            return self.settings[self.key]
        except KeyError as ex:
            _logger.error(_("Failed to get gsettings value. ") + str(ex))
            return self.default

    def gsettings_set(self, value):
        """ Send value to gsettings. """
        self.settings[self.key] = value

    def gsettings_apply(self):
        """ Send current value to gsettings. """
        self.settings[self.key] = self.value

