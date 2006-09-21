#!/usr/bin/python

import gtk
import Key
import gobject
import gconf
import string
from Key import *
sidebarWidth = 60
try:
	from utils import run_script 
	from utils import keysyms
except DeprecationWarning:
	pass


class Keyboard(gtk.DrawingArea):
    "Cairo based keyboard widget"
    def __init__(self,sok,basePane,panes):
        gtk.DrawingArea.__init__(self)

        self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK | gtk.gdk.LEAVE_NOTIFY_MASK) 
        self.connect("expose_event", self.expose)
        self.connect("button_press_event", self.mouse_button_press)
        self.connect("button_release_event", self.mouse_button_release)
        self.connect("leave-notify-event", self.cb_leave_notify)
	
	
	self.sok = sok
	
	self.locked = []
	
	self.activePane = None # When set to a pane, the pane overlays the basePane.
        
	self.active = None #Currently active key
        
        self.scanningActive = None # Key currently being scanned.
        
	self.stuck = [] #List of keys which have been latched.  ie. pressed until next non sticky button is pressed.
	
	self.tabKeys = []
	
	self.basePane = basePane #Pane which is always visible
	
	self.panes = panes # All panes except the basePane

	if self.panes:
		for n in range(len(self.panes)):
            		self.tabKeys.append(TabKey(self,sidebarWidth,self.panes[n]))
        
        self.queue_draw()
        
            
    def cb_leave_notify(self, widget, grabbed):
    	gtk.gdk.pointer_ungrab() # horrible.  Grabs pointer when key is pressed, released when cursor leaves keyboard
	if self.active:
		self.release_key(self.active)
		self.queue_draw()
	return True
	
    
    def utf8_to_unicode(self,utf8Char):
        
        return ord(utf8Char.decode('utf-8'))
  	
        
    def scan_tick(self): #at intervals scans across keys in the row and then down columns.
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
			

		elif key.actions[4]:#macros
		 	try:
				mString = self.sok.macros[string.atoi(key.actions[4])]
				for c in mString:
					char = self.utf8_to_unicode(c)
					self.sok.vk.press_unicode(char)
					self.sok.vk.release_unicode(char)
			except IndexError:
				dialog = gtk.Dialog("No snippet", self.sok.window, 0, ("_Save snippet", gtk.RESPONSE_OK, 
										"_Cancel", gtk.RESPONSE_CANCEL))
				dialog.vbox.add(gtk.Label("No snippet for this button,\nType new snippet"))
				
				macroEntry = gtk.Entry()				
			
				dialog.connect("response", self.cb_dialog_response,string.atoi(key.actions[4]),macroEntry)
				
				macroEntry.connect("activate", self.cb_dialog_response,gtk.RESPONSE_OK,string.atoi(key.actions[4]),macroEntry)
				dialog.vbox.pack_end(macroEntry)

				dialog.show_all()


		elif key.actions[5]:
			run_script(key.actions[5],self.sok)	
			
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
		
		
    def cb_dialog_response(self, widget, response, macroNo,macroEntry):
    	if response == gtk.RESPONSE_OK:	
		
		if macroNo > (len(self.sok.macros) - 1):
			
			for n in range(len(self.sok.macros) - (macroNo - 1)):
							
				self.sok.macros.append("")

		self.sok.macros[macroNo] = macroEntry.get_text()
		self.sok.gconfClient.set_list("/apps/sok/macros",gconf.VALUE_STRING, self.sok.macros)

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
	    context.set_line_width(1.1)
	    
	    size = self.get_allocation()
	    
            self.kbwidth = size.width - sidebarWidth # to allow for sidebar
	    self.height = size.height
	    
	    context.set_source_rgba(float(self.basePane.rgba[0]),
					float(self.basePane.rgba[1]),
					float(self.basePane.rgba[2]),
					float(self.basePane.rgba[3]))#get from .sok
	    context.paint()
	    
	    
	    self.basePane.paint(context,self.kbwidth,self.height)
	    
	    if (self.activePane):
		
		context.rectangle(0, 0, self.kbwidth, self.height)
		context.set_source_rgba(float(self.activePane.rgba[0]),
					float(self.activePane.rgba[1]),
					float(self.activePane.rgba[2]),
					float(self.activePane.rgba[3]))#get from .sok
	        context.fill()
		self.activePane.paint(context,self.kbwidth,self.height)
		
	    	
	    	
            for key in self.tabKeys:
	            key.paint(context)
        
            return True


	

        


    

