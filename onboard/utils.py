#!/usr/bin/python
import os
from xml.dom import minidom
from copy import deepcopy
from xml.dom.ext import PrettyPrint
from Key import * 

def run_script(script,sok):
		a =__import__(script)
		
		a.run(sok)


modifiers = {"shift":1,"caps":2, "control":4, "mod1":8, "mod2":16, "mod3":32, "mod4":64, "mod5":128}


modDic = {"RTSH" : ("⇧".decode('utf-8'), 1), "LFSH" : ("⇧".decode('utf-8'), 1), "RALT" : ("Alt Gr", 128), "LALT" : ("Alt", 8), "RCTL" : ("Ctrl", 4), "LCTL" : ("Ctrl", 4), "CAPS" : ("CAPS", 2), "NMLK" : ("Nm\nLk",16)}

otherDic = {"LWIN" : "Win", "RWIN" : "Win","MENU" : "Menu" ,"BKSP" : "⇦".decode("utf-8"),"RTRN" : "Return", "TAB" : "Tab", "INS":"Ins", "HOME":"Hm", "PGUP": "Pg\nUp","DELE":"Del","END":"End","PGDN":"Pg\nDn", "UP":  "↑".decode("utf-8"), "DOWN":"↓".decode("utf-8"), "LEFT" : "←".decode("utf-8"), "RGHT" : "→".decode("utf-8"), "KP0" : "0", "KP1" : "1", "KP2" : "2", "KP3" : "3", "KP4" : "4", "KP5" : "5", "KP6" : "6", "KP7" : "7", "KP8" : "8", "KP9" : "9", "KPDL":"Del", "KPEN": "Ent" }

funcKeys = (("ESC",65307),("F1",65470),("F2",65471),("F3",65472),("F4", 65473),("F5", 65474),("F6",65475),("F7",65476),("F8",65477),("F9",65478),("F10",65479),("F11", 65480),("F12", 65481),
			("Prnt", 65377), ("Scroll", 65300),("Pause", 65299))
			
			
keysyms = {"space" : 65408, "insert" : 0xff9e, "home" : 0xff50, "page_up" : 0xff55, "page_down" : 0xff56, "end" :0xff57, "delete" : 0xff9f, "return" : 65293, "backspace" : 65288}



def create_default_layout_XML(name,vk,sok):
	"Reads layout stored within onBoard and outputs it to XML"
	doc = minidom.Document()
	
	
	keyboard_element = doc.createElement("keyboard")
	keyboard_element.setAttribute("id", name)
	doc.appendChild(keyboard_element)
	
	
	f = open(os.path.join(sok.SOK_INSTALL_DIR,"layouts","template.svg"))
	baseDoc = minidom.parse(f)
	f.close()
	
	paneDocs = []
	for pane in sok.keyboard.panes:
		paneDoc = deepcopy(baseDoc)
		paneDocs.append((pane,paneDoc))#tuple
	
	pane = sok.keyboard.basePane
	
	read_layout_from_sok(doc, baseDoc, pane, vk,name)
	
	for paneDoc in paneDocs:
		read_layout_from_sok(doc, paneDoc[1], paneDoc[0], vk,name)
			
	
	#messy
	docFile = open(os.path.join(os.path.expanduser("~"), ".sok", "layouts", "%s.sok" % name), 'w')
	PrettyPrint(doc,docFile)
	docFile.close()
	
	docFile = open(os.path.join(os.path.expanduser("~"), ".sok", "layouts", "%s-%s.svg" % (name,sok.keyboard.basePane.ident)), 'w')
	PrettyPrint(baseDoc,docFile)
	docFile.close()
	
	for pane in paneDocs:
		docFile = open(os.path.join(os.path.expanduser("~"), ".sok", "layouts", "%s-%s.svg" % (name,pane[0].ident)), 'w')
		PrettyPrint(pane[1],docFile)
		docFile.close()
			
													
	
def read_layout_from_sok(doc,svgDoc, pane, vk, name):
	basePane_element  = make_xml_pane(doc,pane.ident,"%s-%s.svg" % (name,pane.ident),pane.rgba,pane.fontSize)
	doc.documentElement.appendChild(basePane_element)
	
	svgDoc.documentElement.setAttribute("width", str(pane.viewPortSizeX))
	svgDoc.documentElement.setAttribute("height", str(pane.viewPortSizeY))
	
	for keyKey,keyVal in pane.keys.items():
		if keyVal.__class__ == RectKey:
			svgDoc.documentElement.appendChild(make_xml_rect(doc,
											keyKey,
											keyVal.x,
											keyVal.y,
											keyVal.width,
											keyVal.height,
											keyVal.rgba))
		
			
			labels = ['','','','','']		
			for n in range(len(keyVal.labels)):
				try:
					labels[n] = keyVal.labels[n].decode('utf-8')
					
				except UnicodeDecodeError:
					labels[n] = '?' #to deal with xorg 7.1 which seems to report some wonky values...

			basePane_element.appendChild(make_xml_key(doc,
											keyKey, 
											labels, 
											keyVal.actions,
											keyVal.sticky,
											keyVal.fontOffsetX,
											keyVal.fontOffsetY))
			
		elif keyVal.__class__ == LineKey:
			print "funky keys not yet implemented"
			
		

def make_xml_pane(doc,ident,filename,rgba,font):		
	
	pane_element = doc.createElement("pane")
	
	pane_element.setAttribute("id", ident)
	pane_element.setAttribute("filename", filename)
	pane_element.setAttribute("backgroundRed", str(rgba[0]))
	pane_element.setAttribute("backgroundGreen", str(rgba[1]))
	pane_element.setAttribute("backgroundBlue", str(rgba[2]))
	pane_element.setAttribute("backgroundAlpha", str(rgba[3]))
	pane_element.setAttribute("font", str(font))
	
	
	return pane_element
	
def make_xml_rect(doc,ident,x,y,width,height,rgba):
	rect_element = doc.createElement("rect")
		
	rect_element.setAttribute("id",ident)
	rect_element.setAttribute("x",str(x))
	rect_element.setAttribute("y",str(y))
	rect_element.setAttribute("width",str(width))
	rect_element.setAttribute("height",str(height))

	rect_element.setAttribute("style","fill:#%s%s%s;stroke:#000000;" % (dec_to_hex_colour(rgba[0]),
															dec_to_hex_colour(rgba[1]),dec_to_hex_colour(rgba[2])))
	
	return rect_element

def dec_to_hex_colour(dec):
	
	hexString = hex(int(255*dec))[2:]	
	if len(hexString) == 1:
		hexString = "0" + hexString
		
	
	return hexString
		


def make_xml_key(doc,ident, labels, actions,sticky, fontOffsetX, fontOffsetY):
	key_element = doc.createElement("key")
	
	if labels[0]:
		key_element.setAttribute("label",labels[0])
	if labels[1]:
		key_element.setAttribute("cap_label",labels[1])
	if labels[2]:
		key_element.setAttribute("shift_label",labels[2])
	if labels[3]:
		key_element.setAttribute("altgr_label",labels[3])
	if labels[4]:
		key_element.setAttribute("altgrNshift_label",labels[4])
	
	
	key_element.setAttribute("id",ident)
		
	
	if actions[0]:
		key_element.setAttribute("char", actions[0])
	elif actions[1]:
		key_element.setAttribute("keysym", str(actions[1]))
	elif actions[2]:
		key_element.setAttribute("press", actions[2])
	elif actions[3]:
		for key,val in modifiers.items():
			if actions[3] == val:
				key_element.setAttribute("modifier", key)
		
	elif actions[4]:
		key_element.setAttribute("macro", actions[4])
	elif actions[5]:
		key_element.setAttribute("script", actions[5])
	
	if fontOffsetX:
		key_element.setAttribute("font_offset_x", fontOffsetX)
	
	if fontOffsetY:
		key_element.setAttribute("font_offset_y", fontOffsetY)
	
	
	if sticky:
		key_element.setAttribute("sticky", "true")
	else:
		key_element.setAttribute("sticky", "false")	
	
	
	return key_element


			
if __name__=='__main__':
	
	from sys import argv
	
	
	if argv[0]:
		from virtkey import virtkey
		from sok import Sok
		s = Sok()
		vk = virtkey()
		create_default_layout_XML(argv[0],vk,s)
	else:
		print "Type name for personalised layout"
	s.clean
	
