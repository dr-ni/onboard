# -*- coding: UTF-8 -*-

import pango
# from math import sqrt
from KeyCommon import *

# BASE_PANE_TAB_HEIGHT = 40

class Key(KeyCommon):
    def __init__(self, pane):
        KeyCommon.__init__(self, pane)
    def moveObject(self, x, y, context = None):
        context.move_to(x, y)

    def createLayout(self, label):
        self.layout = self.pane.keyboard.create_pango_layout(label)

    def paintFont(self, xScale, yScale, x, y, context = None):
        KeyCommon.paintFont(self, xScale, yScale, x, y, context)

        if hasattr(self, "layout"):
            context.set_source_rgb(0, 0, 0)
            self.layout.set_font_description(pango.FontDescription("Sans Serif %d" %( self.fontScale * self.pane.fontSize)))
            context.update_layout(self.layout)            
            context.show_layout(self.layout)


class TabKey(TabKeyCommon, Key):
    def __init__(self, keyboard, width, pane):
        TabKeyCommon.__init__(self, keyboard, width, pane)
        Key.__init__(self, pane)

    def paint(self, context = None):
        TabKeyCommon.paint(self, context)
        context.rectangle(self.keyboard.kbwidth, 
                          self.height * self.index + BASE_PANE_TAB_HEIGHT, self.width, self.height)

        if self.pane == self.keyboard.activePane and self.stuckOn:
            context.set_source_rgba(1, 0, 0,1)
        else:       
            context.set_source_rgba(float(self.pane.rgba[0]), float(self.pane.rgba[1]),float(self.pane.rgba[2]),float(self.pane.rgba[3]))
        
        context.fill()

    
class BaseTabKey(BaseTabKeyCommon, Key):
    def __init__(self, keyboard, width):
        BaseTabKeyCommon.__init__(self, keyboard, width)
        Key.__init__(self, None)

    ''' this class has no UI-specific code at all. Why? '''
    def paint(self,context):
        #We don't paint anything here because we want it to look like the base pane.
        pass
class LineKey(LineKeyCommon, Key):
    def __init__(self, pane, coordList, fontCoord, rgba):
        LineKeyCommon.__init__(self, pane, coordList, fontCoord, rgba)
        Key.__init__(self, pane)

    def pointWithinKey(self, widget, mouseX, mouseY):
        """Cairo specific, hopefully fast way of doing this"""
        context = widget.window.cairo_create()
        self.draw_path(self.pane.xScale, self.pane.yScale, context)

        return context.in_fill(mouseX, mouseY)

    def paint(self, xScale, yScale, context):
        self.draw_path(xScale, yScale, context)

        if (self.stuckOn):
            context.set_source_rgba(1.0, 0.0, 0.0,1.0)
        elif (self.on):
            context.set_source_rgba(0.5, 0.5, 0.5,1.0)
        elif (self.beingScanned):   
            context.set_source_rgba(0.45,0.45,0.7,1.0)
        else:
            context.set_source_rgba(self.rgba[0], self.rgba[1],self.rgba[2],self.rgba[3])

        context.fill_preserve()
        context.set_source_rgb(0, 0, 0)
        context.stroke()

    def draw_path(self, xScale, yScale, context):
        ''' currently this method contains all the LineKey 
            painting code. '''
        LineKeyCommon.paint(self, xScale, yScale, context = None)
        c = 2
        context.move_to(self.coordList[0]*xScale, self.coordList[1]*yScale)
        while not c == len(self.coordList):
            xp1 = self.coordList[c+1]*xScale
            yp1 = self.coordList[c+2]*yScale
            try:
                if self.coordList[c] == "L":
                    c +=3
                    context.line_to(xp1,yp1)
                else:   
                    xp2 = self.coordList[c+3]*xScale
                    yp2 = self.coordList[c+4]*yScale
                    xp3 = self.coordList[c+5]*xScale
                    yp3 = self.coordList[c+6]*yScale
                    context.curve_to(xp1,yp1,xp2,yp2,xp3,yp3)
                    c += 7

            except TypeError, (strerror):
                print x
                print y
                print xp1
                print yp1
                print strerror

                

    def paintFont(self, xScale, yScale, context = None):
        Key.paintFont(self, xScale, yScale, 
            self.fontCoord[0], self.fontCoord[1], context)


    
class RectKey(RectKeyCommon, Key):
    def __init__(self, pane, x, y, width, height, rgba):
        RectKeyCommon.__init__(self, pane, x, y, width, height, rgba)

    def paint(self, xScale, yScale, context = None):
        
        context.rectangle(self.x*xScale,self.y*yScale,self.width*xScale, self.height*yScale)
        
        if (self.stuckOn):
            context.set_source_rgba(1, 0, 0,1)
        elif (self.on):
            context.set_source_rgba(0.5, 0.5, 0.5,1)
        elif (self.beingScanned):   
            context.set_source_rgba(0.45,0.45,0.7,1)
        else:
            context.set_source_rgba(self.rgba[0], self.rgba[1],self.rgba[2],self.rgba[3])
        
        context.fill_preserve()
        context.set_source_rgb(0, 0, 0)
        context.stroke()

    def paintFont(self, xScale, yScale, context = None):
        Key.paintFont(self, xScale, yScale, self.x, self.y, context)

        
