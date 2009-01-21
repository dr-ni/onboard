#Unfinished
from Onboard.Keyboard import Keyboard

class KeyboardVirtkey(Keyboard):
    def __init__(self):
        Keyboard.__init__(self)
        self.load_default_layout()

    def load_default_layout(self):
        self.keyboard = Keyboard(self)
        panes = []
        
        sizeA = self.vk.layout_get_section_size("Alpha")
        sizeK = self.vk.layout_get_section_size("Keypad") 
        sizeE = self.vk.layout_get_section_size("Editing")
        sizeF = (294, 94)
        #Tidy this up
        
        
        listX = [sizeA[0],sizeE[0] + sizeK[0] + 20 + 125 ,sizeF[0]]
        listY = [sizeA[1]+ 1,sizeE[1] + 3, sizeK[1]+3,64 ,sizeF[1]] #alpha,editing,keypad,macros,functions
        listX.sort()
        listY.sort()
        sizeX = listX[len(listX)-1]
        sizeY = listY[len(listY)-1]
            
    
    
        keys = {}
        pane = Pane(self.keyboard,"Alpha", keys,None, float(sizeX), float(sizeY), [0,0,0,0.3],DEFAULT_FONTSIZE)
        panes.append(pane)
        self.get_sections_keys("Alpha", keys,pane,0,0)
            
                
        keys = {}
        pane = Pane(self.keyboard,"Editing",keys,None, float(sizeX), float(sizeY), [0.3,0.3,0.7,0.3],DEFAULT_FONTSIZE)
        panes.append(pane)  
        self.get_sections_keys("Editing", keys, pane, 0, 2)
        self.get_sections_keys("Keypad", keys, pane, sizeE[0] + 20 , 2)
        
        for r in range(3):
            for c in range(3):
                n = c + r*3
                mkey = RectKey(pane,sizeE[0] +sizeK[0] +45 + c*38, 7 + r*28, 33, 24,(0.5,0.5,0.8,1))
                mkey.setProperties(KeyCommon.MACRO_ACTION, str(n), 
                                (_("Snippet\n%d") % (n),"","","",""), False,0,0)
                keys["m%d" % (n)] = mkey
        
        keys = {}
        pane = Pane(self.keyboard,"Functions",keys,None, float(sizeX), float(sizeY), [0.6,0.3,0.7,0.3],DEFAULT_FONTSIZE)
        panes.append(pane)
        y = 0
        for n in range(len(utils.funcKeys)):
            if n  >=8:
                y = 27
                m = n -8
            else :
                m = n
            
            fkey = RectKey(pane,5 + m*30, 5 + y, 25, 24,(0.5,0.5,0.8,1))
            fkey.setProperties(KeyCommon.KEYSYM_ACTION, utils.funcKeys[n][1], 
                                (utils.funcKeys[n][0],"","","",""), False,0,0)
            keys[utils.funcKeys[n][0]] = fkey
        
        settingsKey = RectKey(pane,5, 61, 60.0, 30.0,(0.95,0.5,0.5,1))
        settingsKey.setProperties(KeyCommon.SCRIPT_ACTION, "sokSettings", 
                                    (_("Settings"),"","","",""), False, 0, 0)
        keys["settings"] = settingsKey
        
        switchingKey = RectKey(pane,70 ,61,60.0,30.0,(0.95,0.5,0.5,1))
        switchingKey.setProperties(KeyCommon.SCRIPT_ACTION, "switchButtons", 
                                (_("Switch\nButtons"),"","","",""), False, 0, 0)
        keys["switchButtons"] = switchingKey
        
        
        basePane = panes[0]
        otherPanes = panes[1:]

        self.keyboard.set_basePane(basePane)

        for pane in otherPanes:
            self.keyboard.add_pane(pane)

    def get_sections_keys(self, section, keys, pane, xOffset, yOffset):
        "gets keys for a specified sections from the XServer."
        
        rows = self.vk.layout_get_keys(section)
        
        for row in rows:
            for key in row:
                shape = key['shape']
                name = key['name'].strip(chr(0)) #since odd characters after names shorter than 4.
                
                if name in utils.modDic:
                    nkey = RectKey(pane,float(shape[0] + xOffset),float(shape[1] + yOffset), float(shape[2]), float(shape[3]),(0.95,0.9,0.85,1))
                    props = utils.modDic[name]
                    
                    action = props[1]
                    action_type = KeyCommon.MODIFIER_ACTION

                    labels = (props[0],"","","","")
                    sticky = True
                
                else:            
                    action = key['keycode']
                    action_type = KeyCommon.KEYCODE_ACTION
                    
                    if name in utils.otherDic:
                        
                        nkey = RectKey(pane,float(shape[0] + xOffset),float(shape[1] + yOffset), float(shape[2]), float(shape[3]),(0.85,0.8,0.65,1))
                        labels = (utils.otherDic[name],"","","","")
                    else:
                        nkey = RectKey(pane,float(shape[0]+ xOffset),float(shape[1] + yOffset), float(shape[2]), float(shape[3]),(0.9,0.85,0.7,1))
                        labDic = key['labels']
                        labels = (labDic[0],labDic[2],labDic[1],labDic[3],labDic[4])
                        
                    sticky = False
                    
                    
                nkey.setProperties(action_type, action, labels, sticky, 0, 0)
                    
                keys[name] =  nkey
    
