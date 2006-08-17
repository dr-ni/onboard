#!/usr/bin/python

import sys
from Pane import Pane
import gtk
import Key
import gobject
keysyms = {"space" : 0xff80, "insert" : 0xff9e, "home" : 0xff50, "page_up" : 0xff55, "page_down" : 0xff56, "end" :0xff57, "delete" : 0xff9f}


import os
import string
from Key import *
sidebarWidth = 60
from utils import run_script 


class Keyboard(gtk.DrawingArea):
    "Cairo based keyboard widget"
    def __init__(self,sok,basePane,panes):
        gtk.DrawingArea.__init__(self)

        self.add_events(gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK | gtk.gdk.LEAVE_NOTIFY_MASK) 
        self.connect("expose_event", self.expose)
        self.connect("motion_notify_event", self.mouse_motion)
        self.connect("button_press_event", self.mouse_button_press)
        self.connect("button_release_event", self.mouse_button_release)
        self.connect("leave-notify-event", self.cb_leave_notify)
	
	
	self.sok = sok
	
	self.locked = []
	
	self.activePane = None
        
	self.active = None
        self.scanningActive = None
        
	self.stuck = []
	
	self.tabKeys = [] 
	
	self.basePane = basePane 
	
	self.panes = panes 

	if self.panes:
		for n in range(len(self.panes)):
            		self.tabKeys.append(TabKey(self,sidebarWidth,self.panes[n]))
        
        self.queue_draw()
        
            
    def cb_leave_notify(self, widget, grabbed):
    	gtk.gdk.pointer_ungrab()
		
	return True
	
    
    def utf8_to_unicode(self,utf8Char):
        return ord(utf8Char.decode('utf-8'))
  	

    
    def mouse_motion(self,widget,event):
        return #do nothing for now
	#for k in self.keys.keys():
        #    key = self.keys[k]
        #    if(key.point_within_key(event.x,event.y)):
        #        key.active = True
        #    else:
        #        key.active = False

        #self.queue_draw()
        
    def scan_tick(self):
    	if self.scanningActive:
    		self.scanningActive.beingScanned = False
    	
    	if self.activePane:
    		pane = self.activePane
    	else:
    		pane = self.basePane
    	
    	if not self.sok.scanningNoY == None:
    		self.sok.scanningNoY = (self.sok.scanningNoY + 1) % len(pane.columns[self.sok.scanningNoX])
    	else:
    		self.sok.scanningNoX = (self.sok.scanningNoX + 1) % len(pane.columns)
    	
    	if self.sok.scanningNoY == None:
    		y = 0
    	else:
    		y = self.sok.scanningNoY
    	
    	self.scanningActive = pane.columns[self.sok.scanningNoX][y]
    	
    	self.scanningActive.beingScanned = True
 	self.queue_draw()
    	return True
        
    
    def reset_scan(self):#Between scans and when value of scanning changes.
		
		if self.scanningActive:
			self.scanningActive.beingScanned = False
		
		self.sok.scanningTimeId = None
	    
	    	self.sok.scanningNoX = None
	    	self.sok.scanningNoY = None
	    	self.queue_draw()
        
    def mouse_button_press(self,widget,event):
    	gtk.gdk.pointer_grab(self.window, True)
    	if event.type == gtk.gdk.BUTTON_PRESS:
		self.active = None#is this doing anything
	        
	        if self.sok.scanning:
	        	
	        	if self.sok.scanningTimeId:
	        		if not self.sok.scanningNoY == None:
	        			self.press_key(self.scanningActive)
	        			#self.release_key(self.scanningActive)
	        			#self.mouse_button_release(None,None) #Yuk, sort this out.  Shouldn't call the callback.
	        			gobject.source_remove(self.sok.scanningTimeId)
	        			self.reset_scan()
	        			
	        			
	        			
	        			
	        		else:
	        			self.sok.scanningNoY = -1
	        			gobject.source_remove(self.sok.scanningTimeId)
	        			self.sok.scanningTimeId = gobject.timeout_add(self.sok.scanningInterval,self.scan_tick)
	        	else:	
	        		self.sok.scanningTimeId = gobject.timeout_add(self.sok.scanningInterval,self.scan_tick)
	        		self.sok.scanningNoX = -1
	        else:
					
			if self.activePane:
				for key in self.activePane.keys.values():
					self.is_key_pressed(key,event)
			else:	
				for key in self.basePane.keys.values():
					self.is_key_pressed(key,event)
			


			for key in self.tabKeys:
				self.is_key_pressed(key,event)
	return True 

     
    def is_key_pressed(self,key,event):
		if(key.point_within_key(event.x,event.y)):
			self.press_key(key)
    
    def mouse_button_release(self,widget,event):
	
	if self.active:
		self.active.on = False
		self.release_key(self.active)
		if len(self.stuck) > 0:
			for stick in self.stuck:
				self.release_key(stick)
			self.stuck = []

	self.queue_draw()
	return True

    def press_key(self,key):
    	if not key.on:
		if key.sticky == True:
				self.stuck.append(key)
				
		else:
			self.active = key #Since only one non-sticky key can be pressed at once.
		
		key.on = True
		
		self.locked = []
		for m in self.sok.mods.keys():
			if self.sok.mods[m]:
				self.sok.vk.lock_mod(m)
				self.locked.append(m)
		
	    	if key.actions[0]:
			
			self.sok.vk.press_unicode(self.utf8_to_unicode(key.actions[0]))
		
		elif key.actions[2]:
			self.sok.vk.press_keysym(keysyms[key.actions[2]])
		
		elif key.actions[1]:
			self.sok.vk.press_keysym(key.actions[1])
		
		elif key.actions[3]:
			
			mod = key.actions[3]
			self.sok.mods[mod] += 1
			
			#if self.sok.mods[mod] == 1: #if the modifier is currently unpressed globaly.
			#	self.sok.vk.lock_mod(mod)

		elif key.actions[4]:
		 	try:
				mString = self.sok.macros[string.atoi(key.actions[4])]
				for c in mString:
					char = self.utf8_to_unicode(c)
					self.sok.vk.press_unicode(char)
					self.sok.vk.release_unicode(char)
			except IndexError:
				dialog = gtk.Dialog("Macro not chosen", self.sok.window, 0, ("Open settings", gtk.RESPONSE_OK, 
										"Cancel", gtk.RESPONSE_CANCEL))
				dialog.vbox.add(gtk.Label("No macro for this button,\nClick open settings to create one"))
				dialog.connect("response", self.cb_dialog_response)
				dialog.show_all()


		elif key.actions[5]:
			run_script(key.actions[5])	
			
		else:
			for k in self.tabKeys: # don't like this.
				if k.pane == self.activePane:
					k.on = False
					k.stuckOn = False
			
			self.activePane = key.pane
		
					

	else:
		if key in self.stuck:
			key.stuckOn = True
			self.stuck.remove(key)
		else:
			key.stuckOn = False
			self.release_key(key)

	self.queue_draw()
		
		
    def cb_dialog_response(self, widget, response):
    	if response == gtk.RESPONSE_OK:
		run_script("sokSettings")

	widget.destroy()

    
    def release_key(self,key):
    	key.on = False

    	if key.actions[0]:
    		self.sok.vk.release_unicode(self.utf8_to_unicode(key.actions[0]))
	elif key.actions[2]:
		self.sok.vk.release_keysym(keysyms[key.actions[2]])
	elif key.actions[1]:
		self.sok.vk.release_keysym(key.actions[1])
	elif key.actions[3]:
		mod = key.actions[3]
		self.sok.mods[mod] -= 1
		
		#if not self.sok.mods[mod]: #if the modifier is currently pressed globaly.
		#	self.sok.vk.unlock_mod(mod)
	elif key.actions[4] or key.actions[5]:
		pass
			
			
	else:
		self.activePane = None
	
	for m in self.locked:
			self.sok.vk.unlock_mod(m)

    def expose(self, widget, event):
	    
	    context = widget.window.cairo_create()
	    context.set_line_width(1.2)
            #fontContext = widget.window.cairo_create()
	    fontContext = context

	    size = self.get_allocation()
            
	

            #set a clip region for the expose event
            context.rectangle(event.area.x, event.area.y,
                                                  event.area.width, event.area.height)
            context.clip()

	    fontContext.rectangle(event.area.x, event.area.y,
                                                  event.area.width, event.area.height)
            fontContext.clip()

            self.kbwidth = size.width - sidebarWidth # to allow for sidebar
	    self.height = size.height
            
	    #context.scale((self.kbwidth)/self.basePane.viewPortSizeX, self.height/self.basePane.viewPortSizeY)
	    
	    context.set_source_rgba(float(self.basePane.rgba[0]),
					float(self.basePane.rgba[1]),
					float(self.basePane.rgba[2]),
					float(self.basePane.rgba[3]))#get from .sok

	    context.paint()#paint bg

	    self.basePane.paint(context,fontContext,self.kbwidth,self.height) 
	    

	    #Initialising this here for the tab drawing later.
	    paneFontContext = widget.window.cairo_create()
	    paneFontContext.rectangle(event.area.x, event.area.y,
                                                  event.area.width, event.area.height)
            paneFontContext.clip()



	    if (self.activePane):
		paneContext = widget.window.cairo_create()
		paneContext.set_line_width(1.2)
		paneContext.rectangle(event.area.x, event.area.y,
                                                  event.area.width, event.area.height)
            	paneContext.clip()
		#paneContext.scale((self.kbwidth)/self.basePane.viewPortSizeX, self.height/self.basePane.viewPortSizeY)
		
		paneContext.set_source_rgba(float(self.activePane.rgba[0]),
					float(self.activePane.rgba[1]),
					float(self.activePane.rgba[2]),
					float(self.activePane.rgba[3]))
		paneContext.paint()
		self.activePane.paint(paneContext,paneFontContext,self.kbwidth,self.height)
	    	
            #Using fontcontext because don't want tabs to scale.
            for key in self.tabKeys:
		key.paint(paneFontContext)
    
            return False


	
	

        


    

