### Logging ###
import logging
logger = logging.getLogger("OnboardGtk")
#logger.setLevel(logging.DEBUG)
###############

import os
import re
import string
import sys
from xml.dom import minidom

from Onboard.Keyboard    import Keyboard
from Onboard.KeyboardGTK import KeyboardGTK
from Onboard.KeyGtk      import LineKey, RectKey
from Onboard.Pane        import Pane
from Onboard.utils       import hexstring_to_float, modifiers, matmult
from Onboard             import KeyCommon

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class KeyboardSVG(Keyboard, config.kbd_render_mixin):
    """
    Keyboard loaded from an SVG file.
    """

    def __init__(self, filename):
        config.kbd_render_mixin.__init__(self)
        Keyboard.__init__(self)
        self.load_layout(filename)
        
    def load_layout(self, kblang):
        kbfolder = os.path.dirname(kblang)

        f = open(kblang)
        langdoc = minidom.parse(f).documentElement
        f.close()
            
        panes = []
        for paneXML in langdoc.getElementsByTagName("pane"):
            path= "%s/%s" % (kbfolder,paneXML.attributes["filename"].value)
            
            f = open(path)
            try:            
                svgdoc = minidom.parse(f).documentElement
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
                    fontSize = DEFAULT_FONTSIZE
                
                pane = Pane(self,paneXML.attributes["id"].value,keys,columns, viewPortSizeX, viewPortSizeY, paneBackground, fontSize)

                for rect in svgdoc.getElementsByTagName("rect"): 
                    id = rect.attributes["id"].value
                    
                    styleString = rect.attributes["style"].value
                    result = re.search("(fill:#\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?;)", styleString).groups()[0]
            
                    rgba = [hexstring_to_float(result[6:8])/255,
                    hexstring_to_float(result[8:10])/255,
                    hexstring_to_float(result[10:12])/255,
                    1]#not bothered for now 

                    keys[id] = RectKey(pane,
                        float(rect.attributes['x'].value),
                        float(rect.attributes['y'].value),
                        float(rect.attributes['width'].value),
                        float(rect.attributes['height'].value),rgba)
                
                for path in svgdoc.getElementsByTagName("path"):
                    id = path.attributes["id"].value
                    keys[id] = self.parse_path(path, pane)
                                        
                
                svgdoc.unlink()
                
                self.load_keys(langdoc,keys)
                
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
                print _("require %s") % (strerror)
                
            f.close()
        
        langdoc.unlink()
        
        
        basePane = panes[0]
        otherPanes = panes[1:]

        self.set_basePane(basePane)

        for pane in otherPanes:
            self.add_pane(pane)

    def load_keys(self,doc,keys):
        for key in doc.getElementsByTagName("key"):  
            try:
                if key.attributes["id"].value in keys:
                    action = None
                    action_type = None

                    if key.hasAttribute("char"):
                        action = key.attributes["char"].value
                        action_type = KeyCommon.CHAR_ACTION
                    elif key.hasAttribute("keysym"):
                        value = key.attributes["keysym"].value
                        action_type = KeyCommon.KEYSYM_ACTION
                        if value[1] == "x":#Deals for when keysym is hex
                            action = string.atoi(value,16)
                        else:
                            action = string.atoi(value,10)
                    elif key.hasAttribute("keypress_name"):
                        action = key.attributes["keypress_name"].value
                        action_type = KeyCommon.KEYPRESS_NAME_ACTION
                    elif key.hasAttribute("press"):
                        action = key.attributes["char"].value
                        action_type = KeyCommon.CHAR_ACTION
                    elif key.hasAttribute("modifier"):
                        try:
                            action = modifiers[
                                        key.attributes["modifier"].value]
                            action_type = KeyCommon.MODIFIER_ACTION
                        except KeyError, (strerror):
                            print "Can't find modifier " + str(strerror)
                            
                    elif key.hasAttribute("macro"):
                        action = key.attributes["macro"].value
                        action_type = KeyCommon.MACRO_ACTION
                    elif key.hasAttribute("script"):
                        action = key.attributes["script"].value
                        action_type = KeyCommon.SCRIPT_ACTION
                    elif key.hasAttribute("keycode"):
                        action = string.atoi(
                                            key.attributes["keycode"].value)
                        action_type = KeyCommon.KEYCODE_ACTION

                    labels = ["","","","",""]
                    #if label specified search for modified labels.
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
                    #Get labels from keyboard.
                    else:
                        if action_type == KeyCommon.KEYCODE_ACTION:
                            labDic = self.vk.labels_from_keycode(action)
                            labels = (labDic[0],labDic[2],labDic[1],
                                                        labDic[3],labDic[4])

                
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
                    
                    keys[key.attributes["id"].value].setProperties(
                                        action_type, action, labels,
                                        sticky, offsetX, offsetY)
            except KeyError, (strerror):
                print "key missing id: " + str(strerror)

    def parse_path(self, path, pane):
        id = path.attributes["id"].value
        styleString = path.attributes["style"].value
        result = re.search("(fill:#\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?;)", styleString).groups()[0]

        rgba = (hexstring_to_float(result[6:8])/255,
        hexstring_to_float(result[8:10])/255,
        hexstring_to_float(result[10:12])/255,
        1)#not bothered for now

        dList = path.attributes["d"].value.split(" ")
        dList = dList[1:-2] #trim unwanted M, Z
        coordList = []

        transformMatrix = None
        if path.hasAttribute("transform"):
            transform = path.attributes["transform"].value
            if transform.startswith("matrix"):
                #Convert strings to floats
                transformCoords = map(float,transform[7:-1].split(","))

                transformMatrix = (
                    (transformCoords[0],transformCoords[2],transformCoords[4]),
                    (transformCoords[1],transformCoords[3],transformCoords[5]),
                    (0, 0, 1))
            elif transform.startswith("translate"):
                transformCoords = map(float,transform[10:-1].split(","))

                transformMatrix = (
                    (1.0,0.0,transformCoords[0]),
                    (0.0,1.0,transformCoords[1]),
                    (0.0,0.0,1.0)
                )
            else:
                print "Warning: Unhandled transform " + transform

        xTotal = 0.0
        yTotal = 0.0
        numCoords = 0
        for d in dList:
            l = d.split(",")
            if len(l) == 1:
                #A letter
                coordList.append(l)
            else:
                #A coord
                numCoords = numCoords +1

                l = map(float,l)

                if transformMatrix:
                    l = matmult(transformMatrix, l+[1])[:-1]

                xTotal = xTotal + l[0]
                yTotal = yTotal + l[1]

                coordList.append(l[0])
                coordList.append(l[1])

        #Point at which we want the label drawn
        fontCoord = (xTotal/numCoords, yTotal/numCoords)

        return LineKey(pane, coordList, fontCoord, rgba)


