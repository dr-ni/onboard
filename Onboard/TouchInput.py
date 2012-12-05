# -*- coding: utf-8 -*-
""" Touch input """

from __future__ import division, print_function, unicode_literals

import time

from gi.repository         import Gdk

from Onboard.utils         import Timer

### Logging ###
import logging
_logger = logging.getLogger("TouchInput")
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

BUTTON123_MASK = Gdk.ModifierType.BUTTON1_MASK | \
                 Gdk.ModifierType.BUTTON2_MASK | \
                 Gdk.ModifierType.BUTTON3_MASK

DRAG_GESTURE_THRESHOLD2 = 40**2

(
    NO_GESTURE,
    TAP_GESTURE,
    DRAG_GESTURE,
    FLICK_GESTURE,
) = range(4)

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
    updated    = None
    primary    = False   # primary sequence for drag operations
    delivered  = False

    def init_from_button_event(self, event):
        self.id         = POINTER_SEQUENCE
        self.point      = (event.x, event.y)
        self.root_point = (event.x_root, event.y_root)
        self.time       = event.get_time()
        self.button     = event.button
        self.updated    = time.time()

    def init_from_motion_event(self, event):
        self.id         = POINTER_SEQUENCE
        self.point      = (event.x, event.y)
        self.root_point = (event.x_root, event.y_root)
        self.time       = event.get_time()
        self.state      = event.state
        self.updated    = time.time()

    def init_from_touch_event(self, event, id):
        self.id         = id
        self.point      = (event.x, event.y)
        self.root_point = (event.x_root, event.y_root)
        self.time       = event.time  # has no get_time() method, update has no time too
        self.button     = 1
        self.state      = Gdk.ModifierType.BUTTON1_MASK
        self.updated    = time.time()

    def is_touch(self):
        return self.id != POINTER_SEQUENCE

    def __repr__(self):
        return "{}({})".format(type(self).__name__,
                               repr(self.id))
class TouchInput:
    """
    Unified handling of multi-touch sequences and conventional pointer input.
    """
    (
        TOUCH_INPUT_NONE,
        TOUCH_INPUT_SINGLE,
        TOUCH_INPUT_MULTI,
    ) = range(3)

    GESTURE_DETECTION_SPAN = 100 # [ms] until two finger tap&drag is detected
    GESTURE_DELAY_PAUSE = 3000   # [ms] Suspend delayed sequence begin for this
                                 # amount of time after the last key press.
    delay_sequence_begin = True  # No delivery, i.e. no key-presses after
                                 # gesture detection, but delays press-down.

    def __init__(self):
        self._input_sequences = {}
        self._touch_events_enabled = self.is_touch_enabled()
        self._multi_touch_enabled  = config.keyboard.touch_input == \
                                     self.TOUCH_INPUT_MULTI
        self._gestures_enabled     = self._touch_events_enabled
        self._last_event_was_touch = False
        self._last_sequence_time = 0

        self._gesture = NO_GESTURE
        self._gesture_begin_point = (0, 0)
        self._gesture_begin_time = 0
        self._gesture_detected = False
        self._gesture_cancelled = False
        self._num_tap_sequences = 0
        self._gesture_timer = Timer()

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
        if self._touch_events_enabled:
            event_mask |= Gdk.EventMask.TOUCH_MASK

        self.add_events(event_mask)

    def is_touch_enabled(self):
        return config.keyboard.touch_input != self.TOUCH_INPUT_NONE

    def has_input_sequences(self):
        """ Are any clicks/touches still ongoing? """
        return bool(self._input_sequences)

    def last_event_was_touch(self):
        """ Was there just a touch event? """
        return self._last_event_was_touch

    def _on_button_press_event(self, widget, event):
        if self._touch_events_enabled:
            source_device = event.get_source_device()
            source = source_device.get_source()
            if source == Gdk.InputSource.TOUCHSCREEN:
                return

        if event.type == Gdk.EventType.BUTTON_PRESS:
            sequence = InputSequence()
            sequence.init_from_button_event(event)
            sequence.primary = True
            self._last_event_was_touch = False

            self._input_sequence_begin(sequence)

    def _on_motion_event(self, widget, event):
        if self._touch_events_enabled:
            source_device = event.get_source_device()
            source = source_device.get_source()
            if source == Gdk.InputSource.TOUCHSCREEN:
                return

        sequence = self._input_sequences.get(POINTER_SEQUENCE)
        if sequence is None:
            sequence = InputSequence()
            sequence.primary = True
        sequence.init_from_motion_event(event)

        self._last_event_was_touch = False
        self._input_sequence_update(sequence)

    def _on_button_release_event(self, widget, event):
        sequence = self._input_sequences.get(POINTER_SEQUENCE)
        if not sequence is None:
            sequence.point      = (event.x, event.y)
            sequence.root_point = (event.x_root, event.y_root)
            sequence.time       = event.get_time()

            self._input_sequence_end(sequence)

    def _on_touch_event(self, widget, event):
        source_device = event.get_source_device()
        source = source_device.get_source()
        if source != Gdk.InputSource.TOUCHSCREEN:
            return

        touch = event.touch
        id = str(touch.sequence)
        self._last_event_was_touch = True

        event_type = event.type
        if event_type == Gdk.EventType.TOUCH_BEGIN:
            sequence = InputSequence()
            sequence.init_from_touch_event(touch, id)
            if len(self._input_sequences) == 0:
                sequence.primary = True

            self._input_sequence_begin(sequence)

        elif event_type == Gdk.EventType.TOUCH_UPDATE:
            sequence = self._input_sequences.get(id)
            if not sequence is None:
                sequence.point      = (touch.x, touch.y)
                sequence.root_point = (touch.x_root, touch.y_root)
                sequence.time       = event.get_time()
                sequence.updated    = time.time()

                self._input_sequence_update(sequence)

        else:
            if event_type == Gdk.EventType.TOUCH_END:
                pass

            elif event_type == Gdk.EventType.TOUCH_CANCEL:
                pass

            sequence = self._input_sequences.get(id)
            if not sequence is None:
                sequence.time       = event.get_time()
                self._input_sequence_end(sequence)

    def _input_sequence_begin(self, sequence):
        """ Button press/touch begin """
        self._gesture_sequence_begin(sequence)
        first_sequence = len(self._input_sequences) == 0

        if first_sequence or \
           self._multi_touch_enabled:
            self._input_sequences[sequence.id] = sequence

            if not self._gesture_detected:
                if first_sequence and \
                   self._multi_touch_enabled and \
                   self.delay_sequence_begin and \
                   sequence.time - self._last_sequence_time > \
                                   self.GESTURE_DELAY_PAUSE:
                    # Delay the first tap; we may have to stop it
                    # from reaching the keyboard.
                    self._gesture_timer.start(self.GESTURE_DETECTION_SPAN / 1000.0,
                                              self.on_delayed_sequence_begin,
                                              sequence)

                else:
                    # Tell the keyboard right away.
                    self.deliver_input_sequence_begin(sequence)

        self._last_sequence_time = sequence.time

    def on_delayed_sequence_begin(self, sequence):
        if not self._gesture_detected: # work around race condition
            self.deliver_input_sequence_begin(sequence)
            self._gesture_cancelled = True
        return False

    def deliver_input_sequence_begin(self, sequence):
        self.on_input_sequence_begin(sequence)
        sequence.delivered = True

    def _input_sequence_update(self, sequence):
        """ Pointer motion/touch update """
        self._gesture_sequence_update(sequence)
        if not sequence.state & BUTTON123_MASK or \
           not self.in_gesture_detection_delay(sequence):
            self._gesture_timer.finish()  # don't run begin out of order
            self.on_input_sequence_update(sequence)

    def _input_sequence_end(self, sequence):
        """ Button release/touch end """
        self._gesture_sequence_end(sequence)
        self._gesture_timer.finish()  # run delayed sequence before end
        if sequence.id in self._input_sequences:
            del self._input_sequences[sequence.id]

            if sequence.delivered:
                self._gesture_timer.finish()  # run delayed sequence before end
                self.on_input_sequence_end(sequence)

        if self._input_sequences:
            self._discard_stuck_input_sequences()

        self._last_sequence_time = sequence.time

    def _discard_stuck_input_sequences(self):
        """
        Input sequence handling requires guaranteed balancing of
        begin, update and end events. There is no indication yet this
        isn't always the case, but still, at this time it seems like a
        good idea to prepare for the worst.
        -> Clear out aged input sequences, so Onboard can start from a
        fresh slate and not become terminally unresponsive.
        """
        expired_time = time.time() - 30
        for id, sequence in list(self._input_sequences.items()):
            if sequence.updated < expired_time:
                _logger.warning("discarding expired input sequence " + str(id))
                del self._input_sequences[id]

    def in_gesture_detection_delay(self, sequence):
        span = sequence.time - self._gesture_begin_time
        return span < self.GESTURE_DETECTION_SPAN

    def _gesture_sequence_begin(self, sequence):
        if self._num_tap_sequences == 0:
            self._gesture = NO_GESTURE
            self._gesture_detected = False
            self._gesture_cancelled = False
            self._gesture_begin_point = sequence.point
            self._gesture_begin_time = sequence.time # event time
        else:
            if self.in_gesture_detection_delay(sequence) and \
               not self._gesture_cancelled:
                self._gesture_timer.stop()  # cancel delayed sequence begin
                self._gesture_detected = True
        self._num_tap_sequences += 1

    def _gesture_sequence_update(self, sequence):
        if self._gesture_detected and \
           sequence.state & BUTTON123_MASK and \
           self._gesture == NO_GESTURE:
            point = sequence.point
            dx = self._gesture_begin_point[0] - point[0]
            dy = self._gesture_begin_point[1] - point[1]
            d2 = dx * dx + dy * dy

            # drag gesture?
            if d2 >= DRAG_GESTURE_THRESHOLD2:
                num_touches = len(self._input_sequences)
                self._gesture = DRAG_GESTURE
                self.on_drag_gesture_begin(num_touches)
        return True

    def _gesture_sequence_end(self, sequence):
        if len(self._input_sequences) == 1: # last sequence of the gesture?
            if self._gesture_detected:
                gesture = self._gesture

                if gesture == NO_GESTURE:
                    # tap gesture?
                    elapsed = sequence.time - self._gesture_begin_time
                    if elapsed <= 300:
                        self.on_tap_gesture(self._num_tap_sequences)

                elif gesture == DRAG_GESTURE:
                    self.on_drag_gesture_end(0)

            self._num_tap_sequences = 0

    def on_tap_gesture(self, num_touches):
        return False

    def on_drag_gesture_begin(self, num_touches):
        return False

    def on_drag_gesture_end(self, num_touches):
        return False

