# -*- coding: utf-8
"""
File containing ConfigObject.
"""

from __future__ import division, print_function, unicode_literals

### Logging ###
import logging
_logger = logging.getLogger("ConfigUtils")
###############

import os
import sys
from ast import literal_eval
from gettext import gettext as _
try:
    import configparser
except ImportError:
    # python2 fallback
    import ConfigParser as configparser

from gi.repository import Gio

from Onboard.Exceptions import SchemaError
from Onboard.utils import pack_name_value_list, unpack_name_value_list

_CAN_SET_HOOK       = "_can_set_"       # return true if value is valid
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
    def __init__(self, parent = None, schema = ""):
        self.parent = parent       # parent ConfigObject
        self.children = []         # child config objects; not necessarily
                                   #   reflecting the gsettings hierarchy
        self.schema = schema       # schema-path to the gsettings object
        self.gskeys = {}           # key-value objects {property name, GSKey()}
        self.sysdef_section = None # system defaults section name
        self.system_defaults = {}  # system defaults {property name, value}

        # add keys in here
        self._init_keys()

        # check if the gsettings schema is installed
        if not self.schema in Gio.Settings.list_schemas():
            raise SchemaError(_("gsettings schema for '{}' is not installed").
                                                             format(self.schema))

        # create gsettings object and its python properties
        self.settings = Gio.Settings.new(self.schema)
        for gskey in list(self.gskeys.values()):
            gskey.settings = self.settings
            self._setup_property(gskey)

        # check hook function names
        self.check_hooks()

    def _init_keys(self):
        """ overload this and use add_key() to add key-value tuples """
        pass

    def add_key(self, key, default, prop = None, sysdef = None, 
                      writable = True):
        """ Convenience function to create and add a new GSKey. """
        gskey = GSKey(None, key, default, prop, sysdef, writable)
        self.gskeys[gskey.prop] = gskey
        return gskey

    def find_key(self, key):
        """ Search for key (gsettings name) """
        for gskey in self.gskeys.values():
            if gskey.key == key:
                return gskey
        return None

    def get_root(self):
        """ Return the root config object """
        co = self
        while co:
            if co.parent is None:
                return co
            co = co.parent

    def check_hooks(self):
        """
        Simple runtime plausibility check for all overloaded hook functions.
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
                        # no need for translation
                        raise NameError(
                            "'{}' looks like a ConfigObject hook function, but "
                            "'{}' is not a known property of '{}'"
                            .format(member, prop, str(self)))

    def disconnect_notifications(self):
        """ Recursively remove all callbacks from all notification lists. """
        for gskey in list(self.gskeys.values()):
            prop = gskey.prop
            setattr(type(self), _NOTIFY_CALLBACKS.format(prop), [])

        for child in self.children:
            child.disconnect_notifications()

    def _setup_property(self, gskey):
        """ Setup python property and notification callback """
        prop = gskey.prop

        # list of callbacks
        setattr(type(self), _NOTIFY_CALLBACKS.format(prop), [])

        # method to add callback
        def _notify_add(self, callback, _prop=prop):
            """ method to add a callback to this property """
            getattr(self, _NOTIFY_CALLBACKS.format(prop)).append(callback)
        setattr(type(self), prop+'_notify_add', _notify_add)

        # method to remove a callback
        def _notify_remove(self, callback, _prop=prop):
            """ method to remove a callback from this property """
            try:
                getattr(self, _NOTIFY_CALLBACKS.format(prop)).remove(callback)
            except ValueError:
                pass
        setattr(type(self), prop+'_notify_remove', _notify_remove)

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

                if _gskey.value != value:
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
                        #if value != _gskey.gsettings_get():
                        if value != _gskey.value:
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
        for gskey in list(self.gskeys.values()):
            if hasattr(options, gskey.prop):  # command line option there?
                value = getattr(options, gskey.prop)
                if not value is None:
                    gskey.value = value

    def init_from_gsettings(self):
        """ init propertiy values from gsettings """

        for prop, gskey in list(self.gskeys.items()):
            gskey.value = gskey.default
            if hasattr(self, _GSETTINGS_GET_HOOK + prop):
                gskey.value = getattr(self, _GSETTINGS_GET_HOOK + prop)(gskey)
            else:
                gskey.value = gskey.gsettings_get()

        for child in self.children:
            child.init_from_gsettings()

    def init_from_system_defaults(self):
        """ fill property values with system defaults """

        for prop, value in list(self.system_defaults.items()):
            setattr(self, prop, value)  # write to gsettings

        for child in self.children:
            child.init_from_system_defaults()

    def on_properties_initialized(self):
        for child in self.children:
            child.on_properties_initialized()

    @staticmethod
    def _get_user_sys_filename_gs(gskey, final_fallback, \
                            user_filename_func = None,
                            system_filename_func = None):
        """ Convenience function, takes filename from gskey. """
        return ConfigObject._get_user_sys_filename(gskey.value, gskey.key,
                                                   final_fallback,
                                                   user_filename_func,
                                                   system_filename_func)

    @staticmethod
    def _get_user_sys_filename(filename, description, \
                               final_fallback = None,
                               user_filename_func = None,
                               system_filename_func = None):
        """
        Checks a filenames validity and if necessary expands it to a
        fully qualified path pointing to either the user or system directory.
        User directory has precedence over the system one.
        """

        filepath = filename
        if filename and not os.path.exists(filename):
            # assume filename is just a basename instead of a full file path
            _logger.debug(_("{description} '{filename}' not found yet, "
                           "retrying in default paths") \
                           .format(description=description, filename=filename))

            if user_filename_func:
                filepath = user_filename_func(filename)
                if not os.path.exists(filepath):
                    filepath = ""

            if  not filepath and system_filename_func:
                filepath = system_filename_func(filename)
                if not os.path.exists(filepath):
                    filepath = ""

            if not filepath:
                _logger.info(_("unable to locate '{filename}', "
                               "loading default {description} instead") \
                            .format(description=description, filename=filename))
        if not filepath and not final_fallback is None:
            filepath = final_fallback

        if not os.path.exists(filepath):
            _logger.error(_("failed to find {description} '{filename}'") \
                           .format(description=description, filename=filename))
            filepath = ""
        else:
            _logger.debug(_("{description} '{filepath}' found.") \
                          .format(description=description, filepath=filepath))

        return filepath

    @staticmethod
    def get_unpacked_string_list(gskey, type_spec):
        """ Store dictionary in a gsettings list key """
        _list = gskey.settings.get_strv(gskey.key)
        return ConfigObject.unpack_string_list(_list, type_spec)

    @staticmethod
    def set_packed_string_list(gskey, value):
        """ Store dictionary in a gsettings list key """
        _list = ConfigObject.pack_string_list(value)
        gskey.settings.set_strv(gskey.key, _list)

    @staticmethod
    def pack_string_list(value):
        """ very crude hard coded behavior, fixme as needed """
        if type(value) == dict:
            _dict = value
            if value:
                # has collection interface?
                key, _val = _dict.items()[0]
                if not hasattr(_val, "__iter__"):
                    _dict = dict([key, [value]] for key, value in _dict.items())
            return ConfigObject._dict_to_list(_dict)

        assert(False) # unsupported python type

    @staticmethod
    def unpack_string_list(_list, type_spec):
        """ very crude hard coded behavior, fixme as needed """
        if type_spec == "a{ss}":
            _dict = ConfigObject._list_to_dict(_list, str, num_values = 1)
            return dict([key, value[0]] for key, value in _dict.items())  

        if type_spec == "a{s[ss]}":
            return ConfigObject._list_to_dict(_list, str, num_values = 2)

        if type_spec == "a{i[ss]}":
            return ConfigObject._list_to_dict(_list, int, num_values = 2)

        assert(False) # unsupported type_spec

    @staticmethod
    def _dict_to_list(_dict):
        """ Store dictionary in a gsettings list key """
        return pack_name_value_list(_dict)

    @staticmethod
    def _list_to_dict(_list, key_type = str, num_values = 2):
        """ Get dictionary from a gsettings list key """
        if sys.version_info.major == 2:
            _list = [x.decode("utf-8") for x in _list]  # translate to unicode

        return unpack_name_value_list(_list, key_type=key_type,
                                             num_values = num_values)

    def load_system_defaults(self, paths):
        """
        System default settings can be optionally provided for distribution
        specific customization or branding.
        They are stored in simple ini-style files, residing in a small choice
        of directories. The last setting found in the list of paths wins.
        """
        _logger.info(_("Looking for system defaults in {paths}") \
                        .format(paths=paths))

        filename = None
        parser = configparser.SafeConfigParser()
        try:
            filename = parser.read(paths)
        except configparser.ParsingError as ex:
            _logger.error(_("Failed to read system defaults. " + str(ex)))

        if not filename:
            _logger.info(_("No system defaults found."))
        else:
            _logger.info(_("Loading system defaults from {filename}") \
                            .format(filename=filename))
            self._read_sysdef_section(parser)


    def _read_sysdef_section(self, parser):
        """
        Read this instances (and its childrens) system defaults section.
        """

        for child in self.children:
            child._read_sysdef_section(parser)

        self.system_defaults = {}
        if self.sysdef_section and \
           parser.has_section(self.sysdef_section):
            items = parser.items(self.sysdef_section)

            if sys.version_info.major == 2:
                items = [(key, val.decode("UTF-8")) for key, val in items]

            # convert ini file strings to property values
            sysdef_gskeys = dict((k.sysdef, k) for k in list(self.gskeys.values()))
            for sysdef, value in items:
                _logger.info(_("Found system default '{}={}'") \
                              .format(sysdef, value))

                gskey = sysdef_gskeys.get(sysdef, None)
                value = self._convert_sysdef_key(gskey, sysdef, value)

                if not value is None:
                    prop = gskey.prop if gskey else sysdef.replace("-", "_")
                    self.system_defaults[prop] = value


    def _convert_sysdef_key(self, gskey, sysdef, value):
        """
        Convert a system default string to a property value.
        Sysdef strings -> values of type of gskey's default value.
        """

        if gskey is None:
            _logger.warning(_("System defaults: Unknown key '{}' "
                              "in section '{}'") \
                              .format(sysdef, self.sysdef_section))
        else:
            _type = type(gskey.default)
            str_type = str if sys.version_info.major >= 3 \
                       else unicode
            if _type == str_type and value[0] != '"':
                value = '"' + value + '"'
            try:
                value = literal_eval(value)
            except (ValueError, SyntaxError) as ex:
                _logger.warning(_("System defaults: Invalid value"
                                  " for key '{}' in section '{}'"
                                  "\n  {}").format(sysdef,
                                                    self.sysdef_section, ex))
                return None  # skip key
        return value


class GSKey:
    """
    Class for a key-value tuple for ConfigObject.
    It associates python properties with gsettings keys,
    system default keys and command line options.
    """
    def __init__(self, settings, key, default, prop, sysdef, writable):
        if prop is None:
            prop = key.replace("-","_")
        if sysdef is None:
            sysdef = key
        self.settings  = settings # gsettings object
        self.key       = key      # gsettings key name
        self.sysdef    = sysdef   # system default name
        self.prop      = prop     # python property name
        self.default   = default  # hard coded default, determines type
        self.value     = default  # current property value
        self.writable = writable  # If False, never write the key to gsettings
                                  #    even on accident.

    def is_default(self):
        return self.value == self.default

    def gsettings_get(self):
        """ Get value from gsettings. """
        value = self.default
        try:
            # Bug in Gio, gir1.2-glib-2.0, Oneiric
            # Onboard is accumultating open file handles
            # at "/home/<user>/.config/dconf/<user>' when
            # reading from gsettings before writing.
            # Check with:
            # lsof -w -p $( pgrep gio-test ) -Fn |sort|uniq -c|sort -n|tail
            #value = self.settings[self.key]

            _type = type(self.default)
            if _type == str:
                value = self.settings.get_string(self.key)
            elif _type == int:
                value = self.settings.get_int(self.key)
            elif _type == float:
                value = self.settings.get_double(self.key)
            else:
                value = self.settings[self.key]

        except KeyError as ex:
            _logger.error(_("Failed to get gsettings value. ") + str(ex))

        return value

    def gsettings_set(self, value):
        """ Send value to gsettings. """
        if self.writable:
            self.settings[self.key] = value

    def gsettings_apply(self):
        """ Send current value to gsettings. """
        if self.writable:
            self.settings[self.key] = self.value

