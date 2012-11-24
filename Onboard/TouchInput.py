# -*- coding: utf-8 -*-
""" Touch input """

from __future__ import division, print_function, unicode_literals

from gi.repository         import Gdk

### Logging ###
import logging
_logger = logging.getLogger("TouchInput")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################


# sequence id of core pointer events
POINTER_SEQUENCE = 0

class InputSequence:
    """ 
    State of a single click- or touch sequence.
    On a multi-touch capable touch screen, any number of 
    InputSequences may be in flight simultaneously.
    """
    id         = None
    point      = None
    root_point = None
    time       = None
    button     = None
    event_type = None
    state      = None
    active_key = None
    cancel     = False

    def init_from_button_event(self, event):
        self.id         = POINTER_SEQUENCE
        self.point      = (event.x, event.y)
        self.root_point = (event.x_root, event.y_root)
        self.time       = event.time
        self.button     = event.button

    def init_from_motion_event(self, event):
        self.id         = POINTER_SEQUENCE
        self.point      = (event.x, event.y)
        self.root_point = (event.x_root, event.y_root)
        self.time       = event.time
        self.state      = event.state

    def init_from_touch_event(self, event, id):
        self.id         = id
        self.point      = (event.x, event.y)
        self.root_point = (event.x_root, event.y_root)
        self.time       = event.time
        self.button     = 1
        self.state      = Gdk.ModifierType.BUTTON1_MASK

    def __repr__(self):
        return "{}({})".format(type(self).__name__, 
                               repr(self.id))

class TouchInput:
    """
    Unified handling of multi-touch sequences and conventional pointer input.
    """

    def __init__(self):
        self._input_sequences = {}
        self._multi_touch_enabled = config.keyboard.multi_touch_enabled

        self.connect("button-press-event",   self._on_button_press_event)
        self.connect("button_release_event", self._on_button_release_event)
        self.connect("motion-notify-event",  self._on_motion_event)
        self.connect("touch-event",          self._on_touch_event)

        # set up event handling
        event_mask = Gdk.EventMask.BUTTON_PRESS_MASK | \
                     Gdk.EventMask.BUTTON_RELEASE_MASK | \
                     Gdk.EventMask.POINTER_MOTION_MASK | \
                     Gdk.EventMask.LEAVE_NOTIFY_MASK | \
                     Gdk.EventMask.ENTER_NOTIFY_MASK
        if self._multi_touch_enabled:
            event_mask |= Gdk.EventMask.TOUCH_MASK

        self.add_events(event_mask)

    def _on_button_press_event(self, widget, event):
        if self._multi_touch_enabled:
            source_device = event.get_source_device()
            source = source_device.get_source()
            #print("_on_button_press_event",source)
            if source == Gdk.InputSource.TOUCHSCREEN:
                return

        if event.type == Gdk.EventType.BUTTON_PRESS:
            sequence = InputSequence()
            sequence.init_from_button_event(event)

            self._input_sequence_begin(sequence)

    def _on_motion_event(self, widget, event):
        if self._multi_touch_enabled:
            source_device = event.get_source_device()
            source = source_device.get_source()
            #print("_on_motion_event",source)
            if source == Gdk.InputSource.TOUCHSCREEN:
                return

        sequence = self._input_sequences.get(POINTER_SEQUENCE)
        if sequence is None:
            sequence = InputSequence()

        sequence.init_from_motion_event(event)

        self._input_sequence_update(sequence)

    def _on_button_release_event(self, widget, event):
        sequence = self._input_sequences.get(POINTER_SEQUENCE)
        if not sequence is None:
            sequence.point      = (event.x, event.y)
            sequence.root_point = (event.x_root, event.y_root)
            sequence.time       = event.time

            self._input_sequence_end(sequence)

    def _on_touch_event(self, widget, event):
        source_device = event.get_source_device()
        source = source_device.get_source()
        #print("_on_touch_event",source)
        if source != Gdk.InputSource.TOUCHSCREEN:
            return

        touch = event.touch
        id = str(touch.sequence)

        event_type = event.type
        if event_type == Gdk.EventType.TOUCH_BEGIN:
            sequence = InputSequence()
            sequence.init_from_touch_event(touch, id)

            self._input_sequence_begin(sequence)

        elif event_type == Gdk.EventType.TOUCH_UPDATE:
            sequence = self._input_sequences.get(id)
            sequence.point = (touch.x, touch.y)
            sequence.root_point = (touch.x_root, touch.y_root)

            self._input_sequence_update(sequence)

        else:
            if event_type == Gdk.EventType.TOUCH_END:
                pass

            elif event_type == Gdk.EventType.TOUCH_CANCEL:
                pass

            sequence = self._input_sequences.get(id)
            self._input_sequence_end(sequence)

        #print(event_type, self._input_sequences)

    def _input_sequence_begin(self, sequence):
        """ Button press/touch begin """
        self._input_sequences[sequence.id] = sequence
        #print("_input_sequence_begin", self._input_sequences)
        return self.on_input_sequence_begin(sequence)

    def _input_sequence_update(self, sequence):
        """ Pointer motion/touch update """
        return self.on_input_sequence_update(sequence)

    def _input_sequence_end(self, sequence):
        """ Button release/touch end """
        if sequence.id in self._input_sequences: # ought to be always the case
            del self._input_sequences[sequence.id]
        #print("_input_sequence_end", self._input_sequences)
        return self.on_input_sequence_end(sequence)

    def has_input_sequences(self):
        """ Are any touches still ongoing? """
        return bool(self._input_sequences)

