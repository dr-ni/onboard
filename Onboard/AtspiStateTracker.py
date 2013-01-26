# -*- coding: utf-8 -*-
""" GTK specific keyboard class """

from __future__ import division, print_function, unicode_literals

from Onboard.utils        import Rect, EventSource, Process

### Logging ###
import logging
_logger = logging.getLogger("KeyboardGTK")
###############

try:
    from gi.repository import Atspi
except ImportError as e:
    _logger.info(_("Atspi unavailable, auto-hide won't be available"))


class AsyncEvent:
    """
    Decouple AT-SPI events from D-Bus callbacks to to reduce the risk for deadlocks.
    """
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self._kwargs = kwargs

    def __repr__(self):
        return type(self).__name__ + "(" + \
           ", ".join(str(key) + "=" + repr(val) \
                     for key, val in self._kwargs.items()) \
           + ")"


class AtspiStateTracker(EventSource):
    """
    Keeps track of the currently active accessible by listening
    to AT-SPI focus events.
    """

    _focus_event_names      = ["text-entry-activated"]
    _text_event_names       = ["text-changed", "text-caret-moved"]
    _key_stroke_event_names = ["key-pressed"]
    _event_names = ["focus-changed"] + \
                   _focus_event_names + \
                   _text_event_names + \
                   _key_stroke_event_names

    _focus_listeners_registered = False
    _keystroke_listeners_registered = False
    _text_listeners_registered = False

    # synchronously accessible members
    _focused_accessible = None   # any currently focused accessible
    _active_accessible = None    # editable focused accessible

    # asynchronously accessible members
    _state = None                # cache of various accessible properties

    def __new__(cls, *args, **kwargs):
        """
        Singleton magic.
        """
        if not hasattr(cls, "self"):
            cls.self = object.__new__(cls, *args, **kwargs)
            cls.self.construct()
        return cls.self

    def __init__(self):
        """
        Called multiple times, don't use this.
        """
        pass

    def construct(self):
        """
        Singleton constructor, runs only once.
        """
        EventSource.__init__(self, self._event_names)

        self._last_accessible = None
        self._last_accessible_active = None
        self._state = {}
        self._frozen = False

    def cleanup(self):
        EventSource.cleanup(self)
        self._register_atspi_listeners(False)

    def connect(self, event_name, callback):
        EventSource.connect(self, event_name, callback)
        self._update_listeners()

    def disconnect(self, event_name, callback):
        EventSource.disconnect(self, event_name, callback)
        self._update_listeners()

    def _update_listeners(self):
        register = self.has_listeners(self._focus_event_names)
        self._register_atspi_focus_listeners(register)

        register = self.has_listeners(self._text_event_names)
        self._register_atspi_text_listeners(register)

        register = self.has_listeners(self._key_stroke_event_names)
        self._register_atspi_keystroke_listeners(register)

    def _register_atspi_listeners(self, register):
        self._register_atspi_focus_listeners(register)
        self._register_atspi_text_listeners(register)
        self._register_atspi_keystroke_listeners(register)

    def _register_atspi_focus_listeners(self, register):
        if not "Atspi" in globals():
            return

        if self._focus_listeners_registered != register:

            if register:
                self.atspi_connect("_listener_focus",
                                   "focus",
                                   self._on_atspi_global_focus)
                self.atspi_connect("_listener_object_focus",
                                   "object:state-changed:focused",
                                   self._on_atspi_object_focus)

                # private asynchronous event
                EventSource.connect(self, "focus-changed",
                                      self._on_focus_changed)
            else:
                self.atspi_disconnect("_listener_focus",
                                      "focus")
                self.atspi_disconnect("_listener_object_focus",
                                      "object:state-changed:focused")

                EventSource.disconnect(self, "focus-changed",
                                      self._on_focus_changed)

            self._focus_listeners_registered = register

    def _register_atspi_text_listeners(self, register):
        if self._text_listeners_registered != register:
            if register:
                self.atspi_connect("_listener_text_changed",
                                   "object:text-changed",
                                   self._on_atspi_text_changed)
                self.atspi_connect("_listener_text_caret_moved",
                                   "object:text-caret-moved",
                                   self._on_atspi_text_caret_moved)
            else:
                self.atspi_disconnect("_listener_text_changed",
                                      "object:text-changed")
                self.atspi_disconnect("_listener_text_caret_moved",
                                      "object:text-caret-moved")

        self._text_listeners_registered = register

    def _register_atspi_keystroke_listeners(self, register):
        if self._keystroke_listeners_registered != register:
            modifier_masks = range(16)

            if register:
                self._keystroke_listener = \
                        Atspi.DeviceListener.new(self._on_atspi_keystroke, None)

                for modifier_mask in modifier_masks:
                    Atspi.register_keystroke_listener( \
                                        self._keystroke_listener,
                                        None,        # key set, None=all
                                        modifier_mask,
                                        Atspi.KeyEventType.PRESSED,
                                        Atspi.KeyListenerSyncType.SYNCHRONOUS)
            else:
                # Apparently any single deregister call will turn off
                # all the other registered modifier_masks too. Since
                # deregistering takes extremely long (~2.5s for 16 calls)
                # seize the opportunity and just pick a single arbitrary
                # mask (Quantal).
                modifier_masks = [2]

                for modifier_mask in modifier_masks:
                    Atspi.deregister_keystroke_listener(
                                        self._keystroke_listener,
                                        None, # key set, None=all
                                        modifier_mask,
                                        Atspi.KeyEventType.PRESSED)

                self._keystroke_listener = None

        self._keystroke_listeners_registered = register

    def atspi_connect(self, attribute, event, callback):
        """
        Start listening to an AT-SPI event.
        Creates a new event listener for each event, since this seems
        to be the only way to allow reliable deregistering of events.
        """
        if hasattr(self, attribute):
            listener = getattr(self, attribute)
        else:
            listener = None

        if listener is None:
            listener = Atspi.EventListener.new(callback, None)
            setattr(self, attribute, listener)
        listener.register(event)

    def atspi_disconnect(self, attribute, event):
        """
        Stop listening to AT-SPI event.
        """
        listener = getattr(self, attribute)
        listener.deregister(event)

    def freeze(self):
        """
        Freeze AT-SPI message processing, e.g. while displaying
        a dialog or popoup menu.
        """
        self._register_atspi_listeners(False)
        self._frozen = True

    def thaw(self):
        """
        Resume AT-SPI message processing.
        """
        self._update_listeners()
        self._frozen = False

    def emit_async(self, event_name, *args, **kwargs):
        if not self._frozen:
            EventSource.emit_async(self, event_name, *args, **kwargs)

    ########## synchronous handlers ##########

    def _on_atspi_global_focus(self, event, user_data):
        self._on_atspi_focus(event, True)

    def _on_atspi_object_focus(self, event, user_data):
        self._on_atspi_focus(event)

    def _on_atspi_focus(self, event, focus_received = False):
        focused = bool(focus_received) or bool(event.detail1) # received focus?
        accessible = event.source

        # Don't access the accessible while frozen. This leads to deadlocks
        # while displaying Onboard's own dialogs/popup menu's.
        if not self._frozen:
            self._log_accessible(accessible, focused)

            if accessible:
                # Read the bare minimum from the accessible to keep
                # the risk for lockups down. Do everything else in
                # the asynchronous handler.
                state = {}
                try:
                    state["role"] = accessible.get_role()
                    state["state-set"] = accessible.get_state_set()
                except: # private exception gi._glib.GError when
                        # gedit became unresponsive.
                    _logger.warning("_on_atspi_focus(): "
                                    "Invalid accessible, failed to read state")

                editable = self._is_accessible_editable(state)
                active =  focused and editable

                if focused:
                    self._focused_accessible = accessible
                elif not focused and self._focused_accessible == accessible:
                    self._focused_accessible = None
                else:
                    active = False

                if self._focused_accessible and active:
                    self._active_accessible = self._focused_accessible
                else:
                    self._active_accessible = None

                if not self._last_accessible is self._focused_accessible or \
                   self._last_accessible_active != active:
                    self._last_accessible = self._focused_accessible
                    self._last_accessible_active = active

                    ae = AsyncEvent(accessible = event.source,
                                    active     = active)
                    self.emit_async("focus-changed", ae)

    def _on_atspi_text_changed(self, event, user_data):
        if event.source is self._active_accessible:
            #print("_on_atspi_text_changed", event.detail1, event.detail2, event.source, event.type, event.type.endswith("delete"))
            insert = event.type.endswith("insert")
            delete = event.type.endswith("delete")
            if insert or delete:
                ae = AsyncEvent(pos    = event.detail1,
                                length = event.detail2,
                                insert = insert)
                self.emit_async("text-changed", ae)
            else:
                _logger.error("_on_atspi_text_changed: unknown event type '{}'" \
                              .format(event.type))
        return False

    def _on_atspi_text_caret_moved(self, event, user_data):
        if event.source is self._active_accessible:
            #print("_on_atspi_text_caret_moved", event.detail1, event.detail2, event.source, event.type, event.source.get_name(), event.source.get_role())
            ae = AsyncEvent(caret = event.detail1)
            self.emit_async("text-caret-moved", ae)
        return False

    def _on_atspi_keystroke(self, event, user_data):
        #print("_on_atspi_keystroke",event, event.modifiers, event.hw_code, event.id, event.is_text, event.type, event.event_string)
        #keysym = event.id # What is this? Not XK_ keysyms at least.
        if event.type == Atspi.EventType.KEY_PRESSED_EVENT:
            ae = AsyncEvent(hw_code   = event.hw_code,
                            modifiers = event.modifiers)
            self.emit_async("key-pressed", ae)

        return False # don't consume event

    ########## asynchronous handlers ##########

    def _on_focus_changed(self, event):
        accessible = event.accessible
        active = event.active
        self._state = {}

        if accessible and active:
            try:
                self._state = self._read_accessible_state(accessible)
            except: # Private exception gi._glib.GError when
                    # gedit became unresponsive.
                _logger.warning("_on_focus_changed(): "
                                "Invalid accessible, failed to read state")

            self.emit("text-entry-activated", accessible)
        else:
            self.emit("text-entry-activated", None)

    def get_state(self):
        """ All available state of the focused accessible """
        return self._state

    def get_role(self):
        """ Role of the focused accessible """
        return self._state.get("role")

    def get_state_set(self):
        """ State set of the focused accessible """
        return self._state.get("state")

    def get_extents(self):
        """ Screen rect of the focused accessible """
        return self._state.get("extents", Rect())

    def _is_accessible_editable(self, acc_state):
        """ Is this an accessible onboard should be shown for? """
        role  = acc_state.get("role")
        state = acc_state.get("state-set")
        if not state is None:

            if role in [Atspi.Role.TEXT,
                        Atspi.Role.TERMINAL,
                        Atspi.Role.DATE_EDITOR,
                        Atspi.Role.PASSWORD_TEXT,
                        Atspi.Role.EDITBAR,
                        Atspi.Role.ENTRY,
                        Atspi.Role.DOCUMENT_TEXT,
                        Atspi.Role.DOCUMENT_FRAME,
                        Atspi.Role.DOCUMENT_EMAIL,
                        Atspi.Role.SPIN_BUTTON,
                        Atspi.Role.COMBO_BOX,
                        Atspi.Role.DATE_EDITOR,
                        Atspi.Role.PARAGRAPH,      # LibreOffice Writer
                        Atspi.Role.HEADER,
                        Atspi.Role.FOOTER,
                       ]:
                if role in [Atspi.Role.TERMINAL] or \
                   (not state is None and state.contains(Atspi.StateType.EDITABLE)):
                    return True
        return False

    def _read_accessible_state(self, accessible):
        """
        Read attributes and find out as much as we
        can about the accessibles purpose.
        """
        state = {}

        interfaces = accessible.get_interfaces()
        state["id"] = accessible.get_id()
        state["role"] = accessible.get_role()
        state["state-set"] = accessible.get_state_set()
        state["name"] = accessible.get_name()
        state["attributes"] = accessible.get_attributes()
        state["interfaces"] = interfaces

        ext = accessible.get_extents(Atspi.CoordType.SCREEN)
        state["extents"] = Rect(ext.x, ext.y, ext.width, ext.height)

        pid = accessible.get_process_id()
        state["process-id"] = pid
        if pid != -1:
            state["process-name"] = Process.get_process_name(pid)

        app = accessible.get_application()
        if app:
            state["app-name"] = app.get_name()
            state["app-description"] = app.get_description()

        return state

    def _log_accessible(self, accessible, focused):
        if _logger.isEnabledFor(logging.DEBUG):
            msg = "AT-SPI focus event: focused={}, ".format(focused)
            if not accessible:
                msg += "accessible={}".format(accessible)
            else:
                try:
                    role = accessible.get_role()
                except: # private exception gi._glib.GError when gedit became unresponsive
                    role = None

                try:
                    role_name = accessible.get_role_name()
                except: # private exception gi._glib.GError when gedit became unresponsive
                    role_name = None

                try:
                    state_set = accessible.get_state_set()
                    states = state_set.states
                    editable = state_set.contains(Atspi.StateType.EDITABLE) \
                               if state_set else None
                except: # private exception gi._glib.GError when gedit became unresponsive
                    states = None
                    editable = None

                try:
                    ext = accessible.get_extents(Atspi.CoordType.SCREEN)
                    extents   = Rect(ext.x, ext.y, ext.width, ext.height)
                except: # private exception gi._glib.GError when gedit became unresponsive
                    extents = None

                msg += "name={name}, role={role}({role_name}), " \
                       "editable={editable}, states={states}, " \
                       "extents={extents}]" \
                        .format(name=accessible.get_name(),
                                role = role,
                                role_name = role_name,
                                editable = editable,
                                states = states,
                                extents = extents \
                               )
            _logger.debug(msg)


class AtspiStateType:
    states = ['ACTIVE',
              'ANIMATED',
              'ARMED',
              'BUSY',
              'CHECKED',
              'COLLAPSED',
              'DEFUNCT',
              'EDITABLE',
              'ENABLED',
              'EXPANDABLE',
              'EXPANDED',
              'FOCUSABLE',
              'FOCUSED',
              'HAS_TOOLTIP',
              'HORIZONTAL',
              'ICONIFIED',
              'INDETERMINATE',
              'INVALID',
              'INVALID_ENTRY',
              'IS_DEFAULT',
              'LAST_DEFINED',
              'MANAGES_DESCENDANTS',
              'MODAL',
              'MULTISELECTABLE',
              'MULTI_LINE',
              'OPAQUE',
              'PRESSED',
              'REQUIRED',
              'RESIZABLE',
              'SELECTABLE',
              'SELECTABLE_TEXT',
              'SELECTED',
              'SENSITIVE',
              'SHOWING',
              'SINGLE_LINE',
              'STALE',
              'SUPPORTS_AUTOCOMPLETION',
              'TRANSIENT',
              'TRUNCATED',
              'VERTICAL',
              'VISIBLE',
              'VISITED',
             ]

    @staticmethod
    def to_strings(state_set):
        result = []
        for s in AtspiStateType.states:
            if state_set.contains(getattr(Atspi.StateType, s)):
                result.append(s)
        return result


