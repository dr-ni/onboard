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


class AtspiStateTracker(EventSource):
    """
    Keeps track of the currently active accessible by listening
    to AT-SPI focus events.
    """

    _atspi_listeners_registered = False
    _focused_accessible = None

    def __init__(self):
        EventSource.__init__(self, ["text-entry-activated"])
        self._last_accessible = None
        self._last_accessible_active = None
        self._state = {}

    def cleanup(self):
        EventSource.cleanup(self)
        self._register_atspi_listeners(False)

    def connect(self, event_name, callback):
        EventSource.connect(self, event_name, callback)
        self._register_atspi_listeners(True)

    def disconnect(self, event_name, callback):
        EventSource.disconnect(self, event_name, callback)
        if not self.has_listeners():
            self._register_atspi_listeners(False)

    def _register_atspi_listeners(self, register = True):
        if not "Atspi" in globals():
            return

        if register:
            if not self._atspi_listeners_registered:
                Atspi.EventListener.register_no_data(self._on_atspi_global_focus,
                                                     "focus")
                Atspi.EventListener.register_no_data(self._on_atspi_object_focus,
                                                     "object:state-changed:focused")
                self._atspi_listeners_registered = True

        else:
            if self._atspi_listeners_registered:
                Atspi.EventListener.deregister_no_data(self._on_atspi_global_focus,
                                                     "focus")
                Atspi.EventListener.deregister_no_data(self._on_atspi_object_focus,
                                                     "object:state-changed:focused")
                self._atspi_listeners_registered = False

    def _on_atspi_global_focus(self, event):
        self._on_atspi_focus(event, True)

    def _on_atspi_object_focus(self, event):
        self._on_atspi_focus(event)

    def _on_atspi_focus(self, event, focus_received = False):
        accessible = event.source
        focused = bool(focus_received) or bool(event.detail1) # received focus?
        self._state = {}

        self._log_accessible(accessible, focused)

        if accessible:
#           try:
            self._state = self._read_accessible_state(accessible)
#           except: # private exception gi._glib.GError when gedit became unresponsive
#               _logger.info("AtspiAutoHide: Invalid accessible,"
#                            " failed to read state")

            editable = self._is_accessible_editable(self._state)
            visible =  focused and editable

            active = visible
            if focused:
                self._focused_accessible = accessible
            elif not focused and self._focused_accessible == accessible:
                self._focused_accessible = None
            else:
                active = False

            if not self._last_accessible is self._focused_accessible or \
               self._last_accessible_active != active:
                self._last_accessible = self._focused_accessible
                self._last_accessible_active = active

                self._accessible_activated(accessible, active)

    def _accessible_activated(self, accessible, active):
        # notify listeners
        self.emit("text-entry-activated", accessible, active)

    def get_state(self):
        """ All available state of the focused accessible """
        if self._focused_accessible:
            return self._state
        return {}
 
    def get_role(self):
        """ Role of the focused accessible """
        if self._focused_accessible:
            return self._state.get("role")
        return None
 
    def get_state_set(self):
        """ State set of the focused accessible """
        if self._focused_accessible:
            return self._state.get("state")
        return None
 
    def get_extents(self):
        """ Screen rect of the focused accessible """

        if self._focused_accessible:
            return self._state.get("extents", Rect())
        return Rect()

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
        Read attributes and id the accessible.
        Find out as much as we can about its purpose.
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


