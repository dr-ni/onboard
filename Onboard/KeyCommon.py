# -*- coding: UTF-8 -*-

from math import sqrt

### Logging ###
import logging
_logger = logging.getLogger("KeyCommon")
###############

BASE_PANE_TAB_HEIGHT = 40

(CHAR_ACTION, KEYSYM_ACTION, KEYCODE_ACTION, MODIFIER_ACTION, MACRO_ACTION,
    SCRIPT_ACTION, KEYPRESS_NAME_ACTION, WORD_ACTION, BUTTON_ACTION) = range(1,10)

# KeyCommon hosts the abstract classes for the various types of Keys.
# UI-specific keys should be defined in KeyGtk or KeyKDE files.
# NOTE: I really don't like the way pointWithinKey() is handled.
# I won't change it now, but we should strive for maximum
# efficency of inheritance (move the poinWithinKey() to
# the Key class and only tweak it for the other classes.


class KeyCommon(object):
    """ a library-independent key class. Specific
        rendering options are stored elsewhere. """

    action_type = None
    """Type of action to do when key is pressed."""

    action = None
    """Data used in action."""

    on = False
    """True when key is being pressed."""

    stuckOn = False
    """When key is sticky and pressed twice."""

    sticky = False
    """Keys that stay stuck when pressed like modifiers."""

    checked = False
    """True when key stays pressed down permanently vs. the transient 'on' """

    beingScanned = False
    """True when Onboard is in scanning mode and key is highlighted"""

    font_size = 1
    """ Size to draw the label text in Pango units"""

    label_index = 0
    """ Index in labels that is currently displayed by this key """

    labels = None
    """ Labels which are displayed by this key """

    label_offset = None
    """ The amount to offset the label in each direction """

    visible = True
    """ State of visibility """

###################

    def __init__(self):
        pass

    def on_size_changed(self, pane_context):
        raise NotImplementedError()

    def configure_label(self, mods, pane_context):
        if mods[1]:
            if mods[128] and self.labels[4]:
                self.label_index = 4
            elif self.labels[2]:
                self.label_index = 2
            elif self.labels[1]:
                self.label_index = 1
            else:
                self.label_index = 0

        elif mods[128] and self.labels[3]:
            self.label_index = 3

        elif mods[2]:
            if self.labels[1]:
                self.label_index = 1
            else:
                self.label_index = 0
        else:
            self.label_index = 0

    def paint_font(self, pane_context, location, context = None):
        raise NotImplementedError()

    def get_label(self):
        return self.labels[self.label_index]

    def is_active(self):
        return not self.action_type is None

    def get_name(self):
        return ""

    def is_visible(self):
        return self.visible

    def get_bounds(self):
        """ return ((left, top), (right, bottom)) of the bounding rectangle """
        return None


class TabKeyCommon(KeyCommon):

    pane = None
    """Pane that this key is on."""

    """ class for those tabs up the right hand side """
    def __init__(self, keyboard, width, pane):
        KeyCommon.__init__(self)

        self.pane = pane
        self.width = width
        self.keyboard = keyboard
        self.modifier = None # what for?
        self.sticky = True

    def pointWithinKey(self, widget, mouseX, mouseY):
        """ does exactly what the name says - checks for the
            mouse within a key. returns bool. """
        if (mouseX > self.keyboard.kbwidth
            and mouseY > self.height*self.index + BASE_PANE_TAB_HEIGHT
            and mouseY < self.height*(self.index + 1)+ BASE_PANE_TAB_HEIGHT):
            return True
        else:
            return False

    def paint(self, context):
        """ paints the TabKey object """
        self.height = (self.keyboard.height / len(self.keyboard.panes)) - (BASE_PANE_TAB_HEIGHT / len(self.keyboard.panes))
        self.index = self.keyboard.panes.index(self.pane)

    def get_label(self):
        return ""

class BaseTabKeyCommon(KeyCommon):

    pane = None
    """Pane that this key is on."""

    """ class for the tab that brings you to the base pane """
    def __init__(self, keyboard, width):
        KeyCommon.__init__(self)

        self.width = width
        self.keyboard = keyboard
        self.modifier = None # what for?
        self.sticky = False

    def pointWithinKey(self, widget, mouseX, mouseY):
        if (mouseX > self.keyboard.kbwidth
            and mouseY < BASE_PANE_TAB_HEIGHT):
            return True
        else:
            return False


    def paint(self,context=None):
        """Don't draw anything for this key"""
        pass

    def get_label(self):
        return ""


class BaseKeyCommon(KeyCommon):
    """ base class for keyboard keys """

    name = None
    """ Unique identifier for the key """

    rgba = None
    """ Colour of the key """

    rgba_checked = None
    """ Colour of the key in checked state """

    def __init__(self, name, rgba):
        KeyCommon.__init__(self)
        self.name = name
        self.set_rgba(rgba)

    def set_rgba(self, rgba, rgba_checked=None):
        self.rgba = rgba
        if rgba_checked:
            self.rgba_checked = rgba_checked
        else:
            if sum(rgba[:3])/3.0 > 0.5:
                self.rgba_checked = [0.5, 0.5, 0.5,1]  # same as for self.on
            else:
                self.rgba_checked = [min(x + 0.2, 1.0) for x in rgba]
            self.rgba_checked[3] = rgba[3]

    def get_fill_color(self):
        if (self.stuckOn):
            color = (1, 0, 0, 1)
        elif (self.on):
            color = (0.5, 0.5, 0.5,1)
        elif (self.checked):
            color = self.rgba_checked
        elif (self.beingScanned):
            color = (0.45,0.45,0.7,1)
        else:
            color = self.rgba
        return color


class LineKeyCommon(BaseKeyCommon):
    """ class for keyboard buttons made of lines """

    def __init__(self, name, pane, coordList, fontCoord, rgba):
        BaseKeyCommon.__init__(self, name, rgba)
        self.coordList = coordList
        self.fontCoord = fontCoord
        # pane? (m)

    def pointCrossesEdge(self, x, y, xp1, yp1, sMouseX, sMouseY):
        """ Checks whether a point, when scanning from top left crosses edge"""
        return ((((y <= sMouseY) and ( sMouseY < yp1)) or
            ((yp1 <= sMouseY) and (sMouseY < y))) and
            (sMouseX < (xp1 - x) * (sMouseY - y) / (yp1 - y) + x))


    def point_within_key(self, location, pane_context):
        """Checks whether point is within shape.
           Currently does not bother trying to work out
           curved paths accurately. """

        _logger.warning("LineKeyGtk should be using the implementation in KeyGtk")

        x = self.coordList[0]
        y = self.coordList[1]
        c = 2
        coordLen = len(self.coordList)
        within = False

        sMouseX,sMouseY = pane_context.canvas_to_log(location)

        while not c == coordLen:

            xp1 = self.coordList[c+1]
            yp1 = self.coordList[c+2]
            try:
                if self.coordList[c] == "L":
                    within = (self.pointCrossesEdge(x,y,xp1,yp1,sMouseX,sMouseY) ^ within) # a xor
                    c +=3
                    x = xp1
                    y = yp1

                else:
                    xp2 = self.coordList[c+3]
                    yp2 = self.coordList[c+4]
                    xp3 = self.coordList[c+5]
                    yp3 = self.coordList[c+6]
                    within = (self.pointCrossesEdge(x,y,xp3,yp3,sMouseX,sMouseY) ^ within) # a xor
                    x = xp3
                    y = yp3
                    c += 7

            except ZeroDivisionError, (strerror):
                print strerror
                print "x: %f, y: %f, yp1: %f" % (x,y,yp1)
        return within

    def paint(self, pane_context, context = None):
        """
        This class is quite hard to abstract, so all of its
        processing lies now in the UI-dependent class.
        """

    def paint_font(self, pane_context):
        KeyCommon.paint_font(self, pane_context,
            (self.coordList[0], self.coordList[1]))

    def get_bounds(self):  # sample implementation, probably not working as is
        """ return ((left, top), (right, bottom)) of the bounding rectangle """
        if self.coordList:
            l,t = self.coordList[0]
            r,b = self.coordList[0]
            for x,y in self.coordList:
                l = min(l,x)
                t = min(t,y)
                r = max(r,x)
                b = max(b,y)
            return (l,t),(r,b)
        return None


class RectKeyCommon(BaseKeyCommon):
    """ An abstract class for rectangular keyboard buttons """

    location = None
    """ Coordinates of the key on the keyboard """

    geometry = None
    """ Width and height of the key """

    rgba = None
    """ Fill colour of the key """

    hover_rgba   = None
    """ Mouse over colour of the key """

    pressed_rgba   = None
    """ Pushed down colour of the key """

    latched_rgba = None
    """ On colour of modifier key """

    locked_rgba  = None
    """ Locked colour of modifier key """

    scanned_rgba  = None
    """ Colour for key being scanned"""

    stroke_rgba = None
    """ Outline colour of the key in flat mode """

    label_rgba = (0.0,0.0,0.0,1.0)
    """ Four tuple with values between 0 and 1 containing label color"""

    def __init__(self, name, location, geometry, rgba):
        BaseKeyCommon.__init__(self, name, rgba)
        self.location = location
        self.geometry = geometry

    def get_name(self):
        return self.name

    def point_within_key(self, point_location, pane_context):
        point = pane_context.canvas_to_log(point_location)
        return   point[0] >  self.location[0] \
            and (point[0] < (self.location[0] + self.geometry[0])) \
            and  point[1] >  self.location[1] \
            and (point[1] < (self.location[1] + self.geometry[1]))

    def paint(self, pane_context, context = None):
        pass

    def get_bounds(self):
        """ return ((left, top), (right, bottom)) of the bounding rectangle """
        return self.location, (self.location[0]+self.geometry[0],
                               self.location[1]+self.geometry[1])


class InputLineKeyCommon(RectKeyCommon):
    """ An abstract class for InputLine keyboard buttons """

    line = u""
    word_infos = None
    cursor = 0

    def __init__(self, name, location, geometry, rgba):
        RectKeyCommon.__init__(self, name, location, geometry, rgba)

    def get_label(self):
        return u""

    def get_fill_color(self):
        if (self.stuckOn):
            fill = self.locked_rgba
        elif (self.on):
            fill = self.latched_rgba
        elif (self.beingScanned):
            fill = self.scanned_rgba
        else:
            fill = self.rgba
        return fill


