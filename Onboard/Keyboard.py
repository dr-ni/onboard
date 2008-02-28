#!/usr/bin/python

import gtk
import gobject
import gconf
import string

from KeyGtk import *
import KeyCommon

sidebarWidth = 60
try:
	from Onboard.utils import run_script, keysyms
except DeprecationWarning:
	pass


class Keyboard(gtk.DrawingArea):
    "Cairo based keyboard widget"
    def __init__(self,sok):
        gtk.DrawingArea.__init__(self)

        # This is done so multiple keys with the same modifier don't interfere with each other
        self.mods = {1:0,2:0, 4:0,8:0, 16:0,32:0,64:0,128:0}

        self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK | gtk.gdk.LEAVE_NOTIFY_MASK) 
        self.connect("expose_event", self.expose)
        self.connect("button_press_event", self.mouse_button_press)
        self.connect("button_release_event", self.mouse_button_release)
        self.connect("leave-notify-event", self.cb_leave_notify)
	
        self.sok = sok

        self.activePane = None 
        # When set to a pane, the pane overlays the basePane.
            
        self.active = None #Currently active key

        self.scanning = False;
        self.scanningInterval = 1;
        
        self.scanningActive = None # Key currently being scanned.
        
        self.stuck = [] 
        #List of keys which have been latched.  
        #ie. pressed until next non sticky button is pressed.

        self.altLocked = False 

        self.tabKeys = []

        self.panes = [] # All panes except the basePane

        self.tabKeys.append(BaseTabKey(self,sidebarWidth))

        self.queue_draw()
        
       
    def set_basePane(self, basePane):
	self.basePane = basePane #Pane which is always visible

    def add_pane(self, pane):
        self.panes.append(pane)
        self.tabKeys.append(TabKey(self,sidebarWidth,pane))
 
    def cb_leave_notify(self, widget, grabbed):
    	gtk.gdk.pointer_ungrab() # horrible.  Grabs pointer when key is pressed, released when cursor leaves keyboard
	if self.active:
				
		if self.scanningActive:
			self.active = None		
			self.scanningActive = None
		else:		
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
    	
    	if not self.scanningNoY == None:
    		self.scanningNoY = (self.scanningNoY + 1) % len(pane.columns[self.scanningNoX])
    	else:
    		self.scanningNoX = (self.scanningNoX + 1) % len(pane.columns)
    	
    	if self.scanningNoY == None:
    		y = 0
    	else:
    		y = self.scanningNoY
    	
    	self.scanningActive = pane.columns[self.scanningNoX][y]
    	
    	self.scanningActive.beingScanned = True
 	self.queue_draw()
    	
    	return True
        
    
    def reset_scan(self):#Between scans and when value of scanning changes.
		
		if self.scanningActive:
			self.scanningActive.beingScanned = False
		
		self.scanningTimeId = None
	    	
	    	self.scanningNoX = None
	    	self.scanningNoY = None
	    	self.queue_draw()
        
    def mouse_button_press(self,widget,event):
    	gtk.gdk.pointer_grab(self.window, True)
    	if event.type == gtk.gdk.BUTTON_PRESS:
            self.active = None#is this doing anything
	        
            if self.scanning and self.basePane.columns:
	        	
	        	if self.scanningTimeId:
	        		if not self.scanningNoY == None:
	        			self.press_key(self.scanningActive)
	        			gobject.source_remove(self.scanningTimeId)
	        			self.reset_scan()
	        		else:
	        			self.scanningNoY = -1
	        			gobject.source_remove(self.scanningTimeId)
	        			self.scanningTimeId = gobject.timeout_add(
                                        self.scanningInterval, self.scan_tick)
	        	else:	
	        		self.scanningTimeId = gobject.timeout_add(
                                        self.scanningInterval,self.scan_tick)
	        		self.scanningNoX = -1
            else:
                if self.activePane:
                    for key in self.activePane.keys.values():
                        self.is_key_pressed(key, widget, event)
                else:	
                    for key in self.basePane.keys.values():
                        self.is_key_pressed(key, widget, event)

                for key in self.tabKeys:
                    self.is_key_pressed(key, widget, event)
	return True 

     
    def is_key_pressed(self,key, widget, event):
		if(key.pointWithinKey(widget, event.x, event.y)):
			self.press_key(key)
    
    def mouse_button_release(self,widget,event):
        if self.active:
            #self.active.on = False
            self.release_key(self.active)
            if len(self.stuck) > 0:
                for stick in self.stuck:
                    self.release_key(stick)
                self.stuck = []
            self.active = None

        self.queue_draw()
        return True

    def press_key(self, key):
        if not key.on:
            if self.mods[8]:
                self.altLocked = True
                self.sok.vk.lock_mod(8)	

            if key.sticky == True:
                    self.stuck.append(key)
                    
            else:
                self.active = key #Since only one non-sticky key can be pressed at once.
            
            key.on = True
            
            self.locked = []
            if key.action_type == KeyCommon.CHAR_ACTION:
                self.sok.vk.press_unicode(self.utf8_to_unicode(key.action))
            
            elif key.action_type == KeyCommon.KEYSYM_ACTION:
                self.sok.vk.press_keysym(key.action)
            
            elif key.action_type == KeyCommon.MODIFIER_ACTION:
                mod = key.action
                
                if not mod == 8: #Hack since alt puts metacity into move mode and prevents clicks reaching widget.
                    self.sok.vk.lock_mod(mod)
                self.mods[mod] += 1
                    

            elif key.action_type == KeyCommon.MACRO_ACTION:
                try:
                    mString = self.sok.macros[string.atoi(key.action)]
                    if mString:#If mstring exists do the below, otherwise the code in finally should always be done.
                        for c in mString:
                            char = self.utf8_to_unicode(c)
                            self.sok.vk.press_unicode(char)
                            self.sok.vk.release_unicode(char)
                        return
                            
                except IndexError:
                    pass

                dialog = gtk.Dialog("No snippet", self.sok.window, 0, ("_Save snippet", gtk.RESPONSE_OK, 
                                        "_Cancel", gtk.RESPONSE_CANCEL))
                dialog.vbox.add(gtk.Label("No snippet for this button,\nType new snippet"))
                
                macroEntry = gtk.Entry()				
            
                dialog.connect("response", self.cb_dialog_response,string.atoi(key.action), macroEntry)
                
                macroEntry.connect("activate", self.cb_macroEntry_activate,string.atoi(key.action), dialog)
                dialog.vbox.pack_end(macroEntry)

                dialog.show_all()

            elif key.action_type == KeyCommon.KEYCODE_ACTION:
                self.sok.vk.press_keycode(key.action);
                
            elif key.action_type == KeyCommon.SCRIPT_ACTION:
                run_script(key.action, self.sok)	
                
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
	self.set_new_macro(macroNo, response, macroEntry, widget)

    def cb_macroEntry_activate(self,widget,macroNo,dialog):
	self.set_new_macro(macroNo, gtk.RESPONSE_OK, widget, dialog)
	
    	

    def set_new_macro(self,macroNo,response,macroEntry,dialog):
	if response == gtk.RESPONSE_OK:	
		
		if macroNo > (len(self.sok.macros) - 1):#makes sure array long enough for this next bit
			for n in range((macroNo + 1) - len(self.sok.macros)):			
				self.sok.macros.append("")
		
		self.sok.macros[macroNo] = macroEntry.get_text()
		self.sok.gconfClient.set_list("/apps/sok/macros",gconf.VALUE_STRING, self.sok.macros)

	dialog.destroy()
	
    def release_key(self,key):
        if key.action_type == KeyCommon.CHAR_ACTION:
    		self.sok.vk.release_unicode(self.utf8_to_unicode(key.action))
        elif key.action_type == KeyCommon.KEYSYM_ACTION:
            self.sok.vk.release_keysym(key.action)
        elif key.action_type == KeyCommon.MODIFIER_ACTION:
            mod = key.action
            
            if not mod == 8:		
                self.sok.vk.unlock_mod(mod)
            
            self.mods[mod] -= 1
            
        elif key.action_type == KeyCommon.KEYCODE_ACTION:
            self.sok.vk.release_keycode(key.action);
            
        elif (key.action_type == KeyCommon.MACRO_ACTION or 
              key.action_type == KeyCommon.SCRIPT_ACTION):
            pass
                
                
        else:
            self.activePane = None
        
        
        if self.altLocked:
            self.altLocked = False
            self.sok.vk.unlock_mod(8)
        
        gobject.idle_add(self.release_key_idle,key) #Makes sure we draw key pressed before unpressing it. 


    def release_key_idle(self,key):
    	key.on = False
        self.queue_draw()
        return False

      	
    
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
