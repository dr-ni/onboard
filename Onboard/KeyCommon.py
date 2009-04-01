# -*- coding: UTF-8 -*-

from math import sqrt

### Logging ###
import logging
_logger = logging.getLogger("KeyCommon")
###############

BASE_PANE_TAB_HEIGHT = 40

(CHAR_ACTION, KEYSYM_ACTION, KEYCODE_ACTION, MODIFIER_ACTION, MACRO_ACTION,
SCRIPT_ACTION, KEYPRESS_NAME_ACTION) = range(1,8)

# KeyCommon hosts the abstract classes for the various types of Keys.
# UI-specific keys should be defined in KeyGtk or KeyKDE files.
# NOTE: I really don't like the way pointWithinKey() is handled.
# I won't change it now, but we should strive for maximum
# efficency of inheritance (move the poinWithinKey() to
# the Key class and only tweak it for the other classes.


class KeyCommon:
    ''' a library-independent key class. Specific 
        rendering options are stored elsewhere. '''

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

    beingScanned = False
    """True when onboard is in scanning mode and key is highlighted"""

    font_size = 1
    """ Size to draw the label text in Pango units"""

    label = ""
    """ Label that is currently displayed by this key """

###################

    def __init__(self):
        pass

    def setProperties(self, action_type, action, labels, sticky, fontOffsetX,
            fontOffsetY):
        self.action_type = action_type
        self.action = action
        self.labels = labels
        self.sticky = sticky
        self.fontOffsetX = fontOffsetX
        self.fontOffsetY = fontOffsetY
    
    def on_size_changed(self, xScale, yScale):
        raise NotImplementedException()

    def configure_label(self, mods, xScale, yScale):
        if mods[1]:
            if mods[128] and self.labels[4]:
                self.label = self.labels[4]
            elif self.labels[2]:
                self.label = self.labels[2]
            elif self.labels[1]:
                self.label = self.labels[1]
            else:
                self.label = self.labels[0]
        
        elif mods[128] and self.labels[4]:
            self.label = self.labels[3]
        
        elif mods[2]:
            if self.labels[1]:
                self.label = self.labels[1]
            else:
                self.label = self.labels[0]
        else:
            self.label = self.labels[0]

    def paintFont(self, xScale, yScale, x, y, context = None):
        ''' Key.paintFont() paints a font. All context-related
            actions are UI-dependent. Thus, they are moved 
            to overriddable classes.'''

        self.moveObject((x + self.fontOffsetX) * xScale,
                        (y + self.fontOffsetY) * yScale, 
                        context)

class TabKeyCommon(KeyCommon):

    pane = None
    """Pane that this key is on."""

    ''' class for those tabs up the right hand side '''
    def __init__(self, keyboard, width, pane):
        KeyCommon.__init__(self)
        
        self.pane = pane
        self.width = width
        self.keyboard = keyboard
        self.modifier = None # what for?
        self.sticky = True

    def pointWithinKey(self, widget, mouseX, mouseY):
        ''' does exactly what the name says - checks for the 
            mouse within a key. returns bool. '''
        if (mouseX > self.keyboard.kbwidth 
            and mouseY > self.height*self.index + BASE_PANE_TAB_HEIGHT 
            and mouseY < self.height*(self.index + 1)+ BASE_PANE_TAB_HEIGHT):
            return True
        else:
            return False

    def paint(self, context):
        ''' paints the TabKey object '''
        self.height = (self.keyboard.height / len(self.keyboard.panes)) - (BASE_PANE_TAB_HEIGHT / len(self.keyboard.panes))
        self.index = self.keyboard.panes.index(self.pane)
    
    
class BaseTabKeyCommon(KeyCommon):

    pane = None
    """Pane that this key is on."""

    ''' class for the tab that brings you to the base pane '''
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
        '''Don't draw anything for this key'''
        pass

class LineKeyCommon(KeyCommon):
    ''' class for keyboard buttons made of lines '''
    def __init__(self, pane, coordList, fontCoord, rgba):
        KeyCommon.__init__(self, pane)
        self.coordList = coordList
        self.fontCoord = fontCoord
        self.rgba = rgba
        
    def pointCrossesEdge(self, x, y, xp1, yp1, sMouseX, sMouseY):
        ''' Checks whether a point, when scanning from top left crosses edge'''
        return ((((y <= sMouseY) and ( sMouseY < yp1)) or  
            ((yp1 <= sMouseY) and (sMouseY < y))) and 
            (sMouseX < (xp1 - x) * (sMouseY - y) / (yp1 - y) + x))
        
    
    def point_within_key(self, location, scale):
        '''Checks whether point is within shape.
           Currently does not bother trying to work out
           curved paths accurately. '''

        _logger.warn("LineKeyGtk should be using the implementation in KeyGtk")

        x = self.coordList[0]
        y = self.coordList[1]
        c = 2
        coordLen = len(self.coordList)
        within = False
        
        sMouseX = location[0]/scale[0]
        sMouseY = location[1]/scale[1]
        
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
        
    def paint(self, xScale, yScale, context = None):
        ''' This class is quite hard to abstract, so all of its
            processing lies now in the UI-dependent class. '''
               
    def paintFont(self, xScale, yScale, context = None):
        KeyCommon.paintFont(self, xScale, yScale, self.coordList[0], self.coordList[1], context)
            
    
    
class RectKeyCommon(KeyCommon):
    ''' An abstract class for rectangular keyboard buttons '''
    def __init__(self, x, y, width, height, rgba):
        KeyCommon.__init__(self)
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.rgba = rgba      
      
    def point_within_key(self, location, scale):
        return (location[0] / scale[0] > self.x 
                and location[0] / scale[0] < (self.x + self.width)
                and location[1] / scale[1] > self.y 
                and location[1] / scale[1] < (self.y + self.height))
    
    def paint(self, xScale, yScale, context = None):
        pass
