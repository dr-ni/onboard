#!/usr/bin/python
# -*- coding: utf-8 -*-

import os

from xml.dom import minidom
from copy import deepcopy

from KeyGtk import * 
import KeyCommon

INSTALL_DIR = '/usr/share/onboard'

modifiers = {"shift":1,"caps":2, "control":4, "mod1":8, "mod2":16, "mod3":32, "mod4":64, "mod5":128}


modDic = {"LWIN" : ("Win",64),"RTSH" : ("⇧".decode('utf-8'), 1), "LFSH" : ("⇧".decode('utf-8'), 1), "RALT" : ("Alt Gr", 128), "LALT" : ("Alt", 8), "RCTL" : ("Ctrl", 4), "LCTL" : ("Ctrl", 4), "CAPS" : ("CAPS", 2), "NMLK" : ("Nm\nLk",16)}

otherDic = {"RWIN" : "Win","MENU" : "Menu" ,"BKSP" : "⇦".decode("utf-8"),"RTRN" : "Return", "TAB" : "Tab", "INS":"Ins", "HOME":"Hm", "PGUP": "Pg\nUp","DELE":"Del","END":"End","PGDN":"Pg\nDn", "UP":  "↑".decode("utf-8"), "DOWN":"↓".decode("utf-8"), "LEFT" : "←".decode("utf-8"), "RGHT" : "→".decode("utf-8"), "KP0" : "0", "KP1" : "1", "KP2" : "2", "KP3" : "3", "KP4" : "4", "KP5" : "5", "KP6" : "6", "KP7" : "7", "KP8" : "8", "KP9" : "9", "KPDL":"Del", "KPEN": "Ent" }

funcKeys = (("ESC",65307),("F1",65470),("F2",65471),("F3",65472),("F4", 65473),("F5", 65474),("F6",65475),("F7",65476),("F8",65477),("F9",65478),("F10",65479),("F11", 65480),("F12", 65481),
			("Prnt", 65377), ("Scroll", 65300),("Pause", 65299))
			
			
keysyms = {"space" : 65408, "insert" : 0xff9e, "home" : 0xff50, "page_up" : 0xff55, "page_down" : 0xff56, "end" :0xff57, "delete" : 0xff9f, "return" : 65293, "backspace" : 65288}

def run_script(script,sok):
		a =__import__(script)
		a.run(sok)

def get_install_dir():
        # ../../utils.py
        thisFilePath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # when run uninstalled
        if os.path.isfile(os.path.join(thisFilePath,"data","onboard.svg")):
            return thisFilePath
        # when installed
        elif os.path.isdir(INSTALL_DIR):
            return INSTALL_DIR

def create_layout_XML(name,vk,sok):
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
		paneDocs.append(paneDoc)
	
	_create_pane_xml(sok.keyboard.basePane, doc, baseDoc, vk, name)
	
	for i in range(len(paneDocs)):
		_create_pane_xml(sok.keyboard.panes[i], doc, paneDocs[i], vk, name)
			
	
	#messy
	docFile = open(os.path.join(os.path.expanduser("~"), ".sok", "layouts", "%s.sok" % name), 'w')
	docFile.write(doc.toxml())
	docFile.close()
	
	docFile = open(os.path.join(os.path.expanduser("~"), ".sok", "layouts", "%s-%s.svg" % (name,sok.keyboard.basePane.ident)), 'w')
	docFile.write(baseDoc.toxml())
	docFile.close()
	
	for i in range(len(paneDocs)):
		docFile = open(os.path.join(os.path.expanduser("~"), ".sok", "layouts", "%s-%s.svg" % (name, sok.keyboard.panes[i].ident)), 'w')
		docFile.write(paneDocs[i].toxml())
		docFile.close()
			
													
	
def _create_pane_xml(pane, doc, svgDoc, vk, name):
    """
    @type   pane: Onboard.Pane.Pane
    @param  pane: Pane object that we are creating xml for.

    @type   doc: xml.dom.minidom.Document
    @param  doc: DOM of .sok layout file.

    @type   svgDoc: xml.dom.minidom.Document.
    @param  svgDoc: DOM of this panes SVG file.

    @type   vk:     Virtkey.Virtkey

    @type   name:   str
    @param  name:   Name of layout to be created.

    """

    config_element  = _make_pane_config_xml(doc, pane.ident, 
                        "%s-%s.svg" % (name,pane.ident),pane.rgba,pane.fontSize)

    doc.documentElement.appendChild(config_element)

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
        
            config_element.appendChild(_make_key_xml(doc, keyKey, keyVal))
            
        elif keyVal.__class__ == LineKey:
            print "funky keys not yet implemented"
        
		

def _make_pane_config_xml(doc,ident,filename,rgba,font):		
	
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
		


def _make_key_xml(doc, ident, key):

    key_element = doc.createElement("key")

    if ident in otherDic:
        key_element.setAttribute("label", otherDic[ident]);

    if key.action_type != KeyCommon.KEYCODE_ACTION:
        if key.labels:
            if key.labels[0]:
                key_element.setAttribute("label",key.labels[0])
            if key.labels[1]:
                key_element.setAttribute("cap_label",key.labels[1])
            if key.labels[2]:
                key_element.setAttribute("shift_label",key.labels[2])
            if key.labels[3]:
                key_element.setAttribute("altgr_label",key.labels[3])
            if key.labels[4]:
                key_element.setAttribute("altgrNshift_label",key.labels[4])
	
    key_element.setAttribute("id",ident)
		
    if key.action_type == KeyCommon.CHAR_ACTION:
        key_element.setAttribute("char", key.action)
    elif key.action_type == KeyCommon.KEYSYM_ACTION:
        key_element.setAttribute("keysym", str(key.action))
    elif key.action_type == KeyCommon.KEYCODE_ACTION:
        key_element.setAttribute("keycode", str(key.action))
    elif key.action_type == KeyCommon.MODIFIER_ACTION:
        for k,val in modifiers.items():
            if key.action == val:
                key_element.setAttribute("modifier", k)
    elif key.action_type == KeyCommon.MACRO_ACTION:
        key_element.setAttribute("macro", str(key.action))
    elif key.action_type == KeyCommon.SCRIPT_ACTION:
        key_element.setAttribute("script", key.action)

    if key.fontOffsetX:
        key_element.setAttribute("font_offset_x", key.fontOffsetX)

    if key.fontOffsetY:
        key_element.setAttribute("font_offset_y", key.fontOffsetY)

    if key.sticky:
        key_element.setAttribute("sticky", "true")
    else:
        key_element.setAttribute("sticky", "false")	


    return key_element


def matmult(m, v):
    """ Matrix-vector multiplication """
    nrows = len(m)
    w = [None] * nrows
    for row in range(nrows):
        w[row] = reduce(lambda x,y: x+y, map(lambda x,y: x*y, m[row], v))
    return w
			
if __name__=='__main__':
	
	from sys import argv
	
	
	if argv[0]:
		from virtkey import virtkey
		from sok import Sok
		s = Sok()
		vk = virtkey()
		create_layout_XML(argv[0],vk,s)
	else:
		print "Type name for personalised layout"
	s.clean
	
