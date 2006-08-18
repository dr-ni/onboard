#!/usr/bin/python

from xml.dom import minidom
import gtk
import sys
from Keyboard import Keyboard
from Key import * 
from Pane import Pane
import re
import string

from KbdWindow import KbdWindow
import virtkey
import gconf
import gettext


import os.path

from utils import *


class Sok:
	def __init__(self):
	    
	    # This is done so multiple keys with the same modifier don't interfere with each other.
	    self.mods = {1:0,2:0, 4:0,8:0, 16:0,32:0,64:0,128:0}
	    
	    self.SOK_INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
	    sys.path.append("%s/scripts" % self.SOK_INSTALL_DIR)
	    self.vk = virtkey.virtkey()
	    	    
	    self.gconfClient = gconf.client_get_default()
	    
	    filename = self.gconfClient.get_string("/apps/sok/layout_filename")
	    
	    self.window = KbdWindow(self)
	    
	    if not filename or not os.path.exists(filename):
		self.load_default_layout()

	    else:
		self.load_layout(filename)
		
	    self.window.set_keyboard(self.keyboard)
	    
	    self.gconfClient.add_dir("/apps/sok",gconf.CLIENT_PRELOAD_NONE)
	    
	    self.macros = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)
	    	
	    self.window.show_all()

	    self.gconfClient.notify_add("/apps/sok/sizeX",self.window.do_set_size)
    	    self.gconfClient.notify_add("/apps/sok/layout_filename",self.do_set_layout)
            self.gconfClient.notify_add("/apps/sok/macros",self.do_change_macros)
	    self.gconfClient.notify_add("/apps/sok/scanning_interval", self.do_change_scanningInterval)
	    self.gconfClient.notify_add("/apps/sok/scanning", self.do_change_scanning)
	     	    
	    self.SOK_INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
	    os.chdir(self.SOK_INSTALL_DIR)
	    
	    
	    scanning = self.gconfClient.get_bool("/apps/sok/scanning")
	    if scanning:
	    	self.scanning = scanning
	    	self.keyboard.reset_scan()
	    else:
	    	self.scanning = False
	    
	    scanningInterval = self.gconfClient.get_int("/apps/sok/scanning_interval")
	    if scanningInterval:
	    	self.scanningInterval = scanningInterval
	    else:
	    	self.scanningInterval = 750
	    
	    
	    sys.path.append(os.path.join(self.SOK_INSTALL_DIR,'scripts'))
	    
	    
	def unstick(self):
		for key in self.keyboard.basePane.keys.values():
			if key.on :
				self.keyboard.release_key(key)
			
		
	def clean(self): #Called when sok is gotten rid off.
	    self.unstick()
	    self.window.hide()
	    
	    	
	def do_change_scanning(self, cxion_id, entry, user_data,thing):
		self.scanning = self.gconfClient.get_bool("/apps/sok/scanning")
		self.keyboard.reset_scan()
	
	def do_change_scanningInterval(self, cxion_id, entry, user_data,thing):
		self.scanningInterval = self.gconfClient.get_int("/apps/sok/scanningInterval")
	
	def do_change_macros(self):
		    self.macros = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)

	def do_set_layout(self,client, cxion_id, entry, user_data):
		self.unstick()
		filename = self.gconfClient.get_string("/apps/sok/layout_filename")
		if os.path.exists(filename):
			self.load_layout(filename)
			self.window.set_keyboard(self.keyboard)
		else:
			self.load_default_layout()

		self.window.set_keyboard(self.keyboard)
	
	def hexstring_to_float(self,hexString):	
		return float(string.atoi(hexString,16))

	
	def get_sections_keys(self,section,keys,pane,xOffset,yOffset):
		"gets keys for a specified sections from the XServer."
		rows = self.vk.layout_get_keys(section)
		
		for row in rows:
			for key in row:
				shape = key['shape']
				name = key['name'].strip(chr(0)) #since odd characters after names shorter than 4.
				
				if name in modDic:
					nkey = RectKey(pane,float(shape[0] + xOffset),float(shape[1] + yOffset), float(shape[2]), float(shape[3]),(0.95,0.9,0.85,1))
					props = modDic[name]
					
					actions = ("","","",props[1],"")
					labels =(props[0],"","","","")
					sticky = True
				
				else:
					
					
					actions = ("",key['keysym'],"","","","")
					
					if name in otherDic:
						
						nkey = RectKey(pane,float(shape[0] + xOffset),float(shape[1] + yOffset), float(shape[2]), float(shape[3]),(0.85,0.8,0.65,1))
						labels= (otherDic[name],"","","","")
					else:
						nkey = RectKey(pane,float(shape[0]+ xOffset),float(shape[1] + yOffset), float(shape[2]), float(shape[3]),(0.9,0.85,0.7,1))
						labDic = key['labels']
						labels = (labDic[0],labDic[2],labDic[1],labDic[3],labDic[4])
						
					sticky = False
					
					
				nkey.set_properties(actions, labels, sticky,0,0)
					
				keys[name] =  nkey
	
	def load_default_layout(self):
		panes = []
		
		sizeA = self.vk.layout_get_section_size("Alpha")
		sizeK = self.vk.layout_get_section_size("Keypad") 
		sizeE = self.vk.layout_get_section_size("Editing")
		sizeF = (294, 94)
		#Tidy this up
		
		
		listX = [sizeA[0],sizeE[0] + sizeK[0] + 20 + 125 ,sizeF[0]]
		listY = [sizeA[1]+ 5,sizeE[1] + 6, sizeK[1]+6,64 ,sizeF[1]] #alpha,editing,keypad,macros,functions
		listX.sort()
		listY.sort()
		sizeX = listX[len(listX)-1]
		sizeY = listY[len(listY)-1]
		
		keys = {}
		pane = Pane(self,"Alpha", keys,None, float(sizeX), float(sizeY), [0,0,0,0.3],5)
		panes.append(pane)
		self.get_sections_keys("Alpha", keys,pane,0,0)
			
				
		keys = {}
		pane = Pane(self,"Editing",keys,None, float(sizeX), float(sizeY), [0.3,0.3,0.7,0.3],5)
		panes.append(pane)	
		self.get_sections_keys("Editing", keys, pane, 0, 2)
		self.get_sections_keys("Keypad", keys, pane, sizeE[0] + 20 , 2)
		
		
		
		for r in range(3):
			for c in range(3):
				n = c + r*3
				mkey = RectKey(pane,sizeE[0] +sizeK[0] +45 + c*30, 7 + r*28, 25, 24,(0.5,0.5,0.8,1))
				mkey.set_properties(("", "", "", "",("%d" %n) ),("Macro\n%d" % (n),"","","",""), False,0,0)
				keys["m%d" % (n)] = mkey
		
		
		
		
		keys = {}
		pane = Pane(self,"Functions",keys,None, float(sizeX), float(sizeY), [0.6,0.3,0.7,0.3],5)
		panes.append(pane)
		y = 0
		for n in range(len(funcKeys)):
			if n  >=8:
				y = 27
				m = n -8
			else :
				m = n
			
			fkey = RectKey(pane,5 + m*30, 5 + y, 25, 24,(0.5,0.5,0.8,1))
			fkey.set_properties(("", funcKeys[n][1], "", ""),(funcKeys[n][0],"","","",""), False,0,0)
			keys[funcKeys[n][0]] = fkey
		
		settingsKey = RectKey(pane,5, 61, 60.0, 30.0,(0.95,0.5,0.5,1))
		settingsKey.set_properties(("","","","","","sokSettings"), ("Settings","","","",""), False,0,0)
		keys["settings"] = settingsKey
		
		switchingKey = RectKey(pane,70 ,61,60.0,30.0,(0.95,0.5,0.5,1))
		switchingKey.set_properties(("","","","","","switchButtons"), ("Switch\nButtons","","","",""), False,0,0)
		keys["switchButtons"] = switchingKey
		
		
		basePane = panes[0]
		otherPanes = panes[1:]

		self.keyboard = Keyboard(self,basePane,otherPanes)
		for pane in panes:
			pane.set_DrawingArea(self.keyboard)		
				
	
	
	def load_keys(self,doc,keys):
		
			for key in doc.getElementsByTagName("key"):  
				try:
					if key.attributes["id"].value in keys:
						actions = ["","","","","",""]
						if key.hasAttribute("char"):
							actions[0] = key.attributes["char"].value
						elif key.hasAttribute("keysym"):
							value = key.attributes["keysym"].value
							if value[1] == "x":#Deals for when keysym is a hex value.
								actions[1] = string.atoi(value,16)
							else:
								actions[1] = string.atoi(value,10)
						elif key.hasAttribute("press"):
							actions[2] = key.attributes["press"].value
						elif key.hasAttribute("modifier"):
							actions[3] = modifiers[key.attributes["modifier"].value]
						elif key.hasAttribute("macro"):
							actions[4] = key.attributes["macro"].value
						elif key.hasAttribute("script"):
							actions[5] = key.attributes["script"].value

						labels = ["","","","",""]
						if key.hasAttribute("label"):
							labels[0] = key.attributes["label"].value
						if key.hasAttribute("cap_label"):
							labels[1] = key.attributes["cap_label"].value
						if key.hasAttribute("shift_label"):
							labels[2] = key.attributes["shift_label"].value
						if key.hasAttribute("altgr_label"):
							labels[3] = key.attributes["altgr_label"].value
						if key.hasAttribute("altgrNshift_label"):
							labels[4] = key.attributes["altgrNshift_label"].value	
					
						if key.hasAttribute("font_offset_x"):
							offsetX = float(key.attributes["font_offset_x"].value)
						else:
							offsetX = 0
						
						if key.hasAttribute("font_offset_y"):
							offsetY = float(key.attributes["font_offset_y"].value)
						else:
							offsetY = 0
						
						
						stickyString = key.attributes["sticky"].value
						if stickyString == "true":
							sticky = True
						else:
							sticky= False
						
						keys[key.attributes["id"].value].set_properties(actions,
											labels,
											sticky, offsetX, offsetY)
				except KeyError, (strerror):
					print "key missing id"

	def load_layout(self,kblang):
		
		

		kbfolder = os.path.dirname(kblang)

		f = open(kblang)
		langdoc = minidom.parse(f).documentElement
		f.close()

		
	        
	        

		panes = []
		
		


		for paneXML in langdoc.getElementsByTagName("pane"):
			
			try:
				path= "%s/%s" % (kbfolder,paneXML.attributes["filename"].value)
				
				
				f = open(path)
				try:			
		        		svgdoc = minidom.parse(f).documentElement
		        		f.close()
			
					keys = {}

					try:
	                                        viewPortSizeX = float(svgdoc.attributes['width'].value)
	                                        viewPortSizeY = float(svgdoc.attributes['height'].value)
	                                except ValueError:
						print "Units for canvas height and width must be px.  In the svg file this corresponds with having no units after the height and width"

					#find background of pane
					paneBackground = [0.0,0.0,0.0,0.0]
			
					if paneXML.hasAttribute("backgroundRed"):
						paneBackground[0] = paneXML.attributes["backgroundRed"].value
					if paneXML.hasAttribute("backgroundGreen"):
						paneBackground[1] = paneXML.attributes["backgroundGreen"].value
					if paneXML.hasAttribute("backgroundBlue"):
						paneBackground[2] = paneXML.attributes["backgroundBlue"].value
					if paneXML.hasAttribute("backgroundAlpha"):
						paneBackground[3] = paneXML.attributes["backgroundAlpha"].value

					
					
					#scanning
					columns = []
					
					
					if paneXML.hasAttribute("font"):
						fontSize = string.atoi(paneXML.attributes["font"].value)
					else:
						fontSize = 25
					
					pane = Pane(self,paneXML.attributes["id"].value,keys,columns, viewPortSizeX, viewPortSizeY, paneBackground, fontSize)

					
					
			

					for rect in svgdoc.getElementsByTagName("rect"): 
						id = rect.attributes["id"].value
						
						styleString = rect.attributes["style"].value
						result = re.search("(fill:#\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?;)", styleString).groups()[0]
				
						rgba = [self.hexstring_to_float(result[6:8])/255,
						self.hexstring_to_float(result[8:10])/255,
						self.hexstring_to_float(result[10:12])/255,
						1]#not bothered for now 

						keys[id] = RectKey(pane,float(rect.attributes['x'].value),
										float(rect.attributes['y'].value),
										float(rect.attributes['width'].value),
										float(rect.attributes['height'].value),rgba)
					
					for path in svgdoc.getElementsByTagName("path"):
						id = path.attributes["id"].value
						styleString = rect.attributes["style"].value
						result = re.search("(fill:#\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?;)", styleString).groups()[0]
				
						rgba = (self.hexstring_to_float(result[6:8])/255,
						self.hexstring_to_float(result[8:10])/255,
						self.hexstring_to_float(result[10:12])/255,
						1)#not bothered for now

						dList = path.attributes["d"].value.split(" ")
						dList = dList[1:-2] #trim unwanted M, Z
						coordList = []
						for d in dList:
							l = d.split(",")
							for p in l:
								if len(p) == 1:
									coordList.append(p)
								else:
									coordList.append(float(p))

						keys[id] = LineKey(pane,coordList,rgba)
					
											
						
					self.load_keys(langdoc,keys)
				#	self.load_keys(paneXML,keys)
					
					try:
						
						for columnXML in paneXML.getElementsByTagName("column"):
							column = []
							columns.append(column)
							for scanKey in columnXML.getElementsByTagName("scankey"):
								column.append(keys[scanKey.attributes["id"].value])
					except KeyError, (strerror):
						print "require %s key, appears in scanning only" % (strerror)
					

					panes.append(pane)
				except KeyError, (strerror):
					print "require %s" % (strerror)
					
				f.close()
			except KeyError:
				print "require filename in pane"
		
		
		
		basePane = panes[0]
		otherPanes = panes[1:]

		self.keyboard = Keyboard(self,basePane,otherPanes)
		for pane in panes:
			pane.set_DrawingArea(self.keyboard)

		

			



	
if __name__=='__main__':
	s = Sok()
	gtk.main()
	s.clean()
