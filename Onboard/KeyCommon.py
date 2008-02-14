# -*- coding: UTF-8 -*-

from math import sqrt

BASE_PANE_TAB_HEIGHT = 40

CHAR_ACTION, KEYSYM_ACTION, KEYCODE_ACTION, MODIFIER_ACTION, MACRO_ACTION, SCRIPT_ACTION = range(1,7)

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

    pane = None
    """Pane that this key is on."""

    on = False
    """True when key is being pressed."""

    stuckOn = False
    """When key is sticky and pressed twice."""

    sticky = False
    """Keys that stay stuck when pressed like modifiers."""

    beingScanned = False
    """True when onboard is in scanning mode and key is highlighted"""

    def __init__(self,pane):
        self.pane = pane
        
    def setProperties(self, action_type, action, labels, sticky, 
                                                    fontOffsetX, fontOffsetY):

        self.fontOffsetX = fontOffsetX # Mostly for odd shaped keys.
        self.fontOffsetY = fontOffsetY
        self.action = action
        self.action_type = action_type
        self.sticky = sticky
        self.labels = labels
    
    def paintFont(self, xScale, yScale, x, y, context = None):
        ''' Key.paintFont() paints a font. All context-related
            actions are UI-dependent. Thus, they are moved 
            to overriddable classes.'''

        if hasattr(self,"labels"):
            if xScale < yScale:
                self.fontScale = xScale
            else: 
                self.fontScale = yScale # oddly python doesn't do scope in if statements.
            if self.pane.keyboard.mods[1]:
                if self.pane.keyboard.mods[128] and self.labels[4]:
                    label = self.labels[4]
                elif self.labels[2]:
                    label = self.labels[2]
                elif self.labels[1]:
                    label = self.labels[1]
                else:
                    label = self.labels[0]
            
            elif self.pane.keyboard.mods[128] and self.labels[4]:
                label = self.labels[3]
            
            elif self.pane.keyboard.mods[2]:
                if self.labels[1]:
                    label = self.labels[1]
                else:
                    label = self.labels[0]
            else:
                label = self.labels[0]

            #TODO This is a hack we should make sure that the text is always scaled down so it fits within the key.
            if len(label) > 4:
                self.fontScale -= 1.1
            elif len(label) > 1:
                self.fontScale -= 1.1

            if self.fontScale < 0.5:
                self.fontScale = 0.5

            self.moveObject((x + self.fontOffsetX) * xScale + 4, (y +self.fontOffsetY) * yScale - 0.03*self.pane.fontSize*sqrt(self.fontScale), context)

            self.createLayout(label)

class TabKeyCommon(KeyCommon):
    ''' class for those tabs up the right hand side '''
    def __init__(self, keyboard, width, pane):
        KeyCommon.__init__(self, pane)

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

   
    def paint(self, context = None):
        ''' paints the TabKey object '''
        #mhb TODO: make it UI independent
        self.height = (self.keyboard.height / len(self.keyboard.panes)) - (BASE_PANE_TAB_HEIGHT / len(self.keyboard.panes))
        self.index = self.keyboard.panes.index(self.pane)
    
    
class BaseTabKeyCommon(KeyCommon):
    ''' class for the tab that brings you to the base pane '''
    def __init__(self, keyboard, width):
        KeyCommon.__init__(self, None)
       
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
        
    
    def pointWithinKey(self, widget, mouseX, mouseY):
        '''Checks whether point is within shape.
           Currently does not bother trying to work out
           curved paths accurately. '''
        x = self.coordList[0]
        y = self.coordList[1]
        c = 2
        coordLen = len(self.coordList)
        within = False
        
        sMouseX = mouseX/self.pane.xScale
        sMouseY = mouseY/self.pane.yScale
        
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
    def __init__(self, pane, x, y, width, height, rgba):
        KeyCommon.__init__(self,pane)
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.rgba = rgba      
      
    def pointWithinKey(self, widget, mouseX, mouseY):
        if(mouseX / self.pane.xScale > self.x and mouseX / self.pane.xScale < (self.x + self.width)
           and mouseY / self.pane.yScale > self.y and mouseY / self.pane.yScale < (self.y + self.height)):
           return True
        else:
           return False
         
    
    def paint(self, xScale, yScale, context = None):
        pass
