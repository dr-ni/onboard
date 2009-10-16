### Logging ###
import logging
_logger = logging.getLogger("KeyboardSVG")
###############

from gettext import gettext as _
from xml.dom import minidom
import os
import re
import string
import sys
import pango

from Onboard             import Exceptions
from Onboard             import KeyCommon
from Onboard.KeyGtk      import LineKey, RectKey
from Onboard.Keyboard    import Keyboard
from Onboard.KeyboardGTK import KeyboardGTK
from Onboard.Pane        import Pane
from Onboard.utils       import hexstring_to_float, modifiers, matmult

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class KeyboardSVG(config.kbd_render_mixin, Keyboard):
    """
    Keyboard loaded from an SVG file.
    """

    def __init__(self, filename):
        config.kbd_render_mixin.__init__(self)
        Keyboard.__init__(self)
        self.load_layout(filename)
        self.initial_update()
        
        # setup timer for auto saving modified dictionaries
        config.kbd_render_mixin.add_timer(self, 5, Keyboard._cb_auto_save_timer)

    def load_pane_svg(self, pane_xml, pane_svg):
        keys = {}

        try:
            pane_size = (
                float(pane_svg.attributes['width'].value.replace("px", "")),
                float(pane_svg.attributes['height'].value.replace("px", "")))
            
        except ValueError:
            raise Exceptions.SVGSyntaxError(_("Units for canvas height and"
                " width must currently be px (pixels)."))

        #find background of pane
        pane_background = [0.0,0.0,0.0,0.0]

        if pane_xml.hasAttribute("backgroundRed"):
            pane_background[0] = pane_xml.attributes["backgroundRed"].value
        if pane_xml.hasAttribute("backgroundGreen"):
            pane_background[1] = pane_xml.attributes["backgroundGreen"].value
        if pane_xml.hasAttribute("backgroundBlue"):
            pane_background[2] = pane_xml.attributes["backgroundBlue"].value
        if pane_xml.hasAttribute("backgroundAlpha"):
            pane_background[3] = pane_xml.attributes["backgroundAlpha"].value

        #find label color of pane
        pane_label_rgba = [0.0,0.0,0.0,1.0]

        if pane_xml.hasAttribute("labelRed"):
            pane_label_rgba[0] = float(pane_xml.attributes["labelRed"].value)
        if pane_xml.hasAttribute("labelGreen"):
            pane_label_rgba[1] = float(pane_xml.attributes["labelGreen"].value)
        if pane_xml.hasAttribute("labelBlue"):
            pane_label_rgba[2] = float(pane_xml.attributes["labelBlue"].value)
        if pane_xml.hasAttribute("labelAlpha"):
            pane_label_rgba[3] = float(pane_xml.attributes["labelAlpha"].value)

        #scanning
        columns = []
        
        self.load_keys_geometry(pane_svg, keys)
        key_groups = self.load_keys(pane_xml, keys, pane_label_rgba)

        try:
            for column_xml in pane_xml.getElementsByTagName("column"):
                column = []
                columns.append(column)
                for scanKey in column_xml.getElementsByTagName("scankey"):
                    column.append(keys[scanKey.attributes["id"].value])
        except KeyError, (exception):
            raise Exceptions.LayoutFileError(
                _("%s appears in scanning definition only") % (str(exception)))
        
        return Pane(pane_xml.attributes["id"].value, key_groups,
            columns, pane_size, pane_background)


    def load_layout(self, layout_data_file):
        kbfolder = os.path.dirname(layout_data_file)
        panes = []

        f = open(layout_data_file)
        try:
            langdoc = minidom.parse(f).documentElement
            try:    
                for pane_config in langdoc.getElementsByTagName("pane"):
                    pane_svg_filename = os.path.join(kbfolder,
                        pane_config.attributes["filename"].value)
                    try:
                        with open(pane_svg_filename) as svg_file:
                            pane_svg = minidom.parse(svg_file).documentElement
                        try:
                            panes.append(
                                self.load_pane_svg(pane_config, pane_svg))
                        finally:
                            pane_svg.unlink()

                    except Exception, (exception):
                        raise Exceptions.LayoutFileError(_("Error loading ")
                            + pane_svg_filename, chained_exception = exception)
            finally:
                langdoc.unlink()
        finally:
            f.close()
        
        
        basePane = panes[0]
        otherPanes = panes[1:]

        self.set_basePane(basePane)

        for pane in otherPanes:
            self.add_pane(pane)

    def load_keys_geometry(self, svgdoc, keys):
        for rect in svgdoc.getElementsByTagName("rect"): 
            id = rect.attributes["id"].value
            
            styleString = rect.attributes["style"].value
            result = re.search("(fill:#\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?\d?\D?;)", 
                styleString).groups()[0]
    
            rgba = [hexstring_to_float(result[6:8])/255,
            hexstring_to_float(result[8:10])/255,
            hexstring_to_float(result[10:12])/255,
            1]#not bothered for now 

            keys[id] = RectKey(id,
                (float(rect.attributes['x'].value),
                 float(rect.attributes['y'].value)),
                (float(rect.attributes['width'].value),
                 float(rect.attributes['height'].value)),
                rgba)
        
            # TODO fix LineKeys
            """
            for path in svgdoc.getElementsByTagName("path"):
                id = path.attributes["id"].value
                keys[id] = self.parse_path(path, pane)
            """                     

    def load_keys(self, doc, keys, label_rgba):
        groups = {}
        for key_xml in doc.getElementsByTagName("key"):  
            name = key_xml.attributes["id"].value
            if name in keys:
                key = keys[name]
                if key_xml.hasAttribute("char"):
                    key.action = key_xml.attributes["char"].value
                    key.action_type = KeyCommon.CHAR_ACTION
                elif key_xml.hasAttribute("keysym"):
                    value = key_xml.attributes["keysym"].value
                    key.action_type = KeyCommon.KEYSYM_ACTION
                    if value[1] == "x":#Deals for when keysym is hex
                        key.action = string.atoi(value,16)
                    else:
                        key.action = string.atoi(value,10)
                elif key_xml.hasAttribute("keypress_name"):
                    key.action = key_xml.attributes["keypress_name"].value
                    key.action_type = KeyCommon.KEYPRESS_NAME_ACTION
                elif key_xml.hasAttribute("modifier"):
                    try:
                        key.action = modifiers[
                                    key_xml.attributes["modifier"].value]
                    except KeyError, (strerror):
                        raise Exception("Unrecognised modifier %s in" \
                            "definition of %s" (strerror, name))
                    key.action_type = KeyCommon.MODIFIER_ACTION
                        
                elif key_xml.hasAttribute("macro"):
                    key.action = key_xml.attributes["macro"].value
                    key.action_type = KeyCommon.MACRO_ACTION
                elif key_xml.hasAttribute("script"):
                    key.action = key_xml.attributes["script"].value
                    key.action_type = KeyCommon.SCRIPT_ACTION
                elif key_xml.hasAttribute("keycode"):
                    key.action = string.atoi(
                        key_xml.attributes["keycode"].value)
                    key.action_type = KeyCommon.KEYCODE_ACTION
                elif key_xml.hasAttribute("button"):
                    key.action = name[:]
                    key.action_type = KeyCommon.BUTTON_ACTION
                elif key_xml.hasAttribute("word"):
                    key.action = key_xml.attributes["word"].value
                    key.action_type = KeyCommon.WORD_ACTION
                elif key_xml.hasAttribute("draw_only") and \
                     key_xml.attributes["draw_only"].value.lower() == "true":
                    key.action = None
                    key.action_type = None
                else:
                    raise Exceptions.LayoutFileError(name
                        + " key does not have an action defined")

                labels = ["","","","",""]
                #if label specified search for modified labels.
                if key_xml.hasAttribute("label"):
                    labels[0] = key_xml.attributes["label"].value
                    if key_xml.hasAttribute("cap_label"):
                        labels[1] = key_xml.attributes["cap_label"].value
                    if key_xml.hasAttribute("shift_label"):
                        labels[2] = key_xml.attributes["shift_label"].value
                    if key_xml.hasAttribute("altgr_label"):
                        labels[3] = key_xml.attributes["altgr_label"].value
                    if key_xml.hasAttribute("altgrNshift_label"):
                        labels[4] = \
                            key_xml.attributes["altgrNshift_label"].value   
                # If key is a macro (snippet) generate label from number.
                elif key.action_type == KeyCommon.MACRO_ACTION:
                    labels[0] = "%s\n%s" % (_("Snippet"), key.action)
                # Get labels from keyboard.
                else:
                    if key.action_type == KeyCommon.KEYCODE_ACTION:
                        labDic = self.vk.labels_from_keycode(key.action)
                        labels = (labDic[0],labDic[2],labDic[1],
                                                    labDic[3],labDic[4])

                # Translate labels - Gettext behaves oddly when translating
                # empty strings
                key.labels = [ lab and _(lab) or None for lab in labels ]

                # assign label color - default label color is pane default
                key.label_rgba = label_rgba 

                if key_xml.hasAttribute("font_offset_x"):
                    offset_x = \
                        float(key_xml.attributes["font_offset_x"].value)
                else:
                    offset_x = config.DEFAULT_LABEL_OFFSET[0]
                
                if key_xml.hasAttribute("font_offset_y"):
                    offset_x = \
                        float(key_xml.attributes["font_offset_y"].value)
                else:
                    offset_y = config.DEFAULT_LABEL_OFFSET[1]
                key.label_offset = (offset_x, offset_y)
                
                if key_xml.hasAttribute("sticky"):
                    sticky = key_xml.attributes["sticky"].value.lower()
                    if sticky == "true":
                        key.sticky = True
                    elif sticky == "false":
                        key.sticky = False
                    else:
                        raise Exception( "'sticky' attribute had an" 
                            "invalid value: %s when parsing key %s" 
                            % (sticky, name))
                else:
                    key.sticky = False

                if key_xml.hasAttribute("group"):
                    group = key_xml.attributes["group"].value
                else:
                    group = "_default"
                if not groups.has_key(group): groups[group] = []
                groups[group].append(key)

        return groups            

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


    def create_wordlist_keys(self, choices, 
                             wordlist_location, wordlist_geometry,
                             word_rgba, word_label_rgba, scale):
        """ 
        Dynamically create a variable number of buttons for word completion.       
        """
        if not self.window:
            return []

        keys = []
        button_gap = config.WORDLIST_BUTTON_GAP[0]
        x,y = 0.0, 0.0
        w,h = wordlist_geometry

        # font size is based on the height of the template key
        font_size = int(wordlist_geometry[1] * pango.SCALE * scale[1] *.4)
        context = self.window.cairo_create()
        layout = context.create_layout()
        #context = self.create_pango_context() # no, results in wrong scaling
        font_description = pango.FontDescription()
        font_description.set_family("Normal")
        font_description.set_size(font_size)
        layout.set_font_description(font_description)
        
        # center label vertically
        layout.set_text("Tg") # for maximum y-extent 
        label_width, label_height = layout.get_size()
        log_height = label_height / pango.SCALE / scale[1]
        yoffset = (wordlist_geometry[1] - log_height) / 2
        
        button_infos = []
        for i,choice in enumerate(choices):
   
            # text extent in Pango units -> button size in logical units 
            layout.set_text(choice)
            label_width, label_height = layout.get_size()
            label_width = label_width / pango.SCALE / scale[0]
            w = label_width + config.WORDLIST_LABEL_MARGIN[0] * 2
            
            # reached the end of the available space?
            if x + w > wordlist_geometry[0]:
                break
            
            button_infos.append([label_width, w, choice])
            x += w + button_gap  # move to begin of next button

        # stretch the buttons to the available space
        if len(button_infos):
            gap_total = (len(button_infos)-1) * button_gap
            stretch_fact = (wordlist_geometry[0] - gap_total) / float(x - gap_total - button_gap)
            #stretch_fact = 1.0  # no stretching, left aligned

            # create buttons
            x,y = 0.0, 0.0
            w,h = wordlist_geometry
            for i,(label_width, w, match) in enumerate(button_infos):
                
                w = w * stretch_fact
                xoffset = (w - label_width) / 2 # center label horizontally
                
                key = RectKey("word" + str(i),
                        (wordlist_location[0] + x, wordlist_location[1] + y),
                        (w, h),
                        word_rgba)
                key.labels = (match[:],)*5            
                key.label_offset = (xoffset, yoffset)
                key.label_rgba = word_label_rgba
                key.font_size = font_size
                key.action_type = KeyCommon.WORD_ACTION
                key.action = i            
                keys.append(key)
                
                x += w + button_gap  # move to begin of next button
            
        return keys

