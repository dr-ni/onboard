#!/usr/bin/python
import gtk
import gtk.glade
import gconf
import gobject

from virtkey import virtkey

from Onboard.OnboardGtk import OnboardGtk

import shutil

import utils
from utils import get_install_dir

from xml.parsers.expat import ExpatError
from xml.dom import minidom

import os
import os.path
import gettext

from gettext import gettext as _
#setup gettext
app="onboard-settings"
gettext.textdomain(app)
gettext.bindtextdomain(app)
gtk.glade.textdomain(app)
gtk.glade.bindtextdomain(app)

class Settings:
    def __init__(self,mainwin):

            
        self.SOK_INSTALL_DIR = get_install_dir()       
        if not self.SOK_INSTALL_DIR:
            print "Onboard not installed properly"
            return
        
        self.gladeXML = gtk.glade.XML(os.path.join(self.SOK_INSTALL_DIR,"data", "settings.glade")) 
        self.window = self.gladeXML.get_widget("settingsWindow")

        self.gladeXML.signal_autoconnect({"on_layoutView_released" : self.do_change_layout, 
                "on_addButton_clicked": self.add_sok,
                "on_removeButton_clicked": self.cb_removeButton_clicked,
                "on_macroAddButton_clicked": self.add_macro,
                "on_closeButton_clicked":self.cb_closeButton_clicked,
                "on_intervalSpin_value_changed" : self.cb_intervalSpin_value_changed,
                "on_scanningCheck_toggled" : self.cb_scanningCheck_toggled,
                "on_closeButton_clicked":gtk.main_quit,
                "on_personaliseButton_clicked": self.cb_on_personaliseButton_clicked,
                "on_layoutFolderButton_clicked" : self.cb_layoutFolderButton_clicked,
                "on_icon_toggled" : self.cb_icon_toggled
                })
        
        self.layoutView = self.gladeXML.get_widget("layoutView")
        self.macroNumberBox = self.gladeXML.get_widget("macroNumberBox")
        self.macroTextBox = self.gladeXML.get_widget("macroTextBox")
        self.macroDeleteBox = self.gladeXML.get_widget("macroDeleteBox")
        
        self.gconfClient = gconf.client_get_default()
        

        self.layoutView.append_column(gtk.TreeViewColumn(None, gtk.CellRendererText(), markup = 0))
                

        self.user_layout_root = "%s/.sok/layouts/" % os.path.expanduser("~")
        if not os.path.exists(self.user_layout_root):
            os.makedirs(self.user_layout_root)
        
        
        self.update_layoutList()
        
        self.on_macros_changed()#Populate the macro list

        self.gladeXML.get_widget("icon_toggle").set_active(self.gconfClient.get_bool("/apps/sok/trayicon"))
                    
        
        scanEnabled = self.gconfClient.get_bool("/apps/sok/scanning")
        if scanEnabled:
            self.gladeXML.get_widget("scanningCheck").set_active(True)
        
        scanInterval = self.gconfClient.get_int("/apps/sok/scanning_interval")
        if scanInterval:
            self.gladeXML.get_widget("intervalSpin").set_value(float(scanInterval)/1000)
        
        self.window.show()
            
        self.window.set_keep_above(not mainwin)
        
        self.window.connect("destroy", gtk.main_quit)

        
        gtk.main()

    
    def on_macros_changed(self,client=None, cxion_id=None, entry=None, user_data=None):
        tempMacroList = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)
        self.macroNumbers = []
        
        for child in self.macroNumberBox.get_children():
            if child.__class__ is gtk.Entry:
                self.macroNumberBox.remove(child)
        
        for child in self.macroTextBox.get_children():
            if child.__class__ is gtk.Entry:
                self.macroTextBox.remove(child)
        
        for child in self.macroDeleteBox.get_children():
            if child.__class__ is gtk.Button:
                self.macroDeleteBox.remove(child)
        
        for n in range(len(tempMacroList)):
            macroStr = tempMacroList[n]
            if macroStr:
                self.macroNumbers.append(n)
                
                numberEntry = gtk.Entry()
                numberEntry.set_text(str(n))
                numberEntry.connect("activate",self.cb_macro_numberEntry_activate,n)
                numberEntry.set_size_request(5, 30)
                self.macroNumberBox.pack_start(numberEntry,False,False,5)
                numberEntry.show()

                textEntry = gtk.Entry()
                textEntry.set_text(macroStr)
                textEntry.connect("activate",self.cb_macro_textEntry_activate,n)
                textEntry.set_size_request(-1, 30)
                self.macroTextBox.pack_start(textEntry,False,False,5)
                textEntry.show()
                
                deleteButton = gtk.Button(stock=gtk.STOCK_DELETE)
                deleteButton.connect("clicked",self.cb_macro_deleteButton_clicked,n)
                self.macroDeleteBox.pack_start(deleteButton,False,False,5)
                deleteButton.show()
                

    def cb_macro_numberEntry_activate(self,widget,currentNumber):
        
        newNo = int(widget.get_text())
        
        if not newNo in self.macroNumbers:
            li = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)
            
            if newNo > (len(li) - 1):
                for n in range(len(li) - (newNo - 1)):      
                    li.append("")
            text = li[currentNumber]

            li[currentNumber] = ""
            li[newNo] = text
            
            self.gconfClient.set_list("/apps/sok/macros",gconf.VALUE_STRING,li)
            
            self.on_macros_changed()
        else:
            dialog = gtk.MessageDialog(self.window,type=gtk.MESSAGE_WARNING,buttons=gtk.BUTTONS_OK,message_format=_("Snippet already assigned to this number"))
            dialog.run()
            widget.set_text(str(currentNumber))
            dialog.destroy()
            
            

    def cb_macro_textEntry_activate(self,widget,currentNumber):
        li = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)       
        
        li[currentNumber] = widget.get_text()
        
        self.gconfClient.set_list("/apps/sok/macros",gconf.VALUE_STRING,li)
        
        self.on_macros_changed()
        
        
        

    def cb_macro_deleteButton_clicked(self,widget,currentNumber):
        li = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)       
        
        li[currentNumber] = ""
        
        self.gconfClient.set_list("/apps/sok/macros",gconf.VALUE_STRING,li)
        
        self.on_macros_changed()

    def cb_icon_toggled(self,widget):
        self.gconfClient.set_bool("/apps/sok/trayicon",widget.get_active())

    def open_user_layout_dir(self):
        if os.path.exists('/usr/bin/nautilus'):
            os.system(("nautilus --no-desktop %s" %self.user_layout_root))
        elif os.path.exists('/usr/bin/thunar'):
            os.system(("thunar %s" %self.user_layout_root))
        else:
            print _("No file manager to open layout folder")
            
    def cb_layoutFolderButton_clicked(self,widget):
        self.open_user_layout_dir()

    def cb_on_personaliseButton_clicked(self, widget):
        dialog = MacroDialog(self.window, 
                            _("Enter name for personalised layout")) #recycling
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            text = dialog.macroEntry.get_text()
            s = OnboardGtk(False)
            utils.create_layout_XML(text, virtkey(), s)
            s.clean()
            self.update_layoutList()
            self.open_user_layout_dir()

        dialog.destroy()
        
    def cb_scanningCheck_toggled(self,widget):
        self.gconfClient.set_bool("/apps/sok/scanning",widget.get_active())
    
    def cb_intervalSpin_value_changed(self,widget):
        self.gconfClient.set_int("/apps/sok/scanning_interval", int(widget.get_value()*1000))
    
    def cb_closeButton_clicked(self, widget):
        self.window.destroy()

    def update_layoutList(self):    
        self.layoutList = gtk.ListStore(str,str)
        self.layoutView.set_model(self.layoutList)
        
        #it = self.layoutList.append(("Default", ""))
        #self.layoutView.get_selection().select_iter(it)
        self.get_soks(os.path.join(self.SOK_INSTALL_DIR,"layouts"))
        self.get_soks(self.user_layout_root)
        
    
    def cb_selected_layout_changed(self):
        self.get_soks(self.user_layout_root)

    def cb_macroList_drag_drop(self, widget, event,thing1,thing2,thing3):
        gobject.idle_add(self.macroList_changed)#To make sure gtk has finished changing the value of macroList before updating gconf.
        

    def add_macro(self, event):

        dialog = MacroDialog(self.window,_("Enter text for snippet"))

        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            text = dialog.macroEntry.get_text()
            
            l = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)
            
            if self.macroNumbers:
                if len(l) <= (self.macroNumbers[-1] +1):
                    l.append(text)
                else:
                    l[self.macroNumbers[-1] + 1] = text
            else:
                l.append(text)
            self.gconfClient.set_list("/apps/sok/macros",gconf.VALUE_STRING, l)
            
        dialog.destroy()
        
        self.on_macros_changed()        
        

    
    
    def add_sok(self, event):#todo filtering
        chooser = gtk.FileChooserDialog(title=None,action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                      buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        filterer = gtk.FileFilter()
        filterer.add_pattern("*.sok")
        chooser.add_filter(filterer)
        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            filename = chooser.get_filename()
                

            f = open(filename)
            sokdoc = minidom.parse(f).documentElement
            for p in sokdoc.getElementsByTagName("pane"):
                fn = p.attributes['filename'].value
                
                shutil.copyfile("%s/%s" % (os.path.dirname(filename), fn), "%s%s" % (self.user_layout_root, fn)) 
            

            shutil.copyfile(filename,"%s%s" % (self.user_layout_root, os.path.basename(filename)))

            self.update_layoutList()
        chooser.destroy()
        

    def cb_removeButton_clicked(self, event):
        filename = self.layoutList.get_value(self.layoutView.get_selection().get_selected()[1],1)

        f = open(filename)
        sokdoc = minidom.parse(f).documentElement
        f.close()
        
        os.remove(filename)

        for p in sokdoc.getElementsByTagName("pane"):
            os.remove("%s/%s" % (os.path.dirname(filename), p.attributes['filename'].value))#todo get sok to deal with not having a layout.
        self.gconfClient.set_string("/apps/sok/layout_filename", '')
        self.update_layoutList()
        


    def get_soks(self, path):
        
        files = os.listdir(path)
            
        soks = []
        for f in files:
            if f[-4:] == ".sok":
                filename = "%s/%s" % (path,f)
                file_object = open(filename)
                try:
                    sokdoc = minidom.parse(file_object).documentElement

                    if os.access(filename,os.W_OK):
                        it = self.layoutList.append(("<i>%s</i>" 
                            % sokdoc.attributes["id"].value, filename))
                    else:
                        it = self.layoutList.append((
                            sokdoc.attributes["id"].value, filename))
                
                    if filename == self.gconfClient.get_string("/apps/sok/layout_filename"):
                        self.layoutView.get_selection().select_iter(it)
                except ExpatError,(strerror):
                    print "XML in %s %s" % (filename, strerror)
                except KeyError,(strerror):
                    print "key %s required in %s" % (strerror,filename)
                
                file_object.close()
                

            



    def find_soks(self, path):
        #files = os.listdir("%s/.sok/layouts" % os.path.expanduser("~"))
        files = os.listdir(path)
        soks = []
        for f in files:
            if f[-4:] == ".sok":
                soks.append(f)
        return soks



    def do_change_layout(self,widget,event):
        
        
        filename = self.layoutList.get_value(widget.get_selection().get_selected()[1],1)
        
        
        
        self.gconfClient.set_string("/apps/sok/layout_filename", filename)
    
    

    
class MacroDialog(gtk.MessageDialog):
    def __init__(self,parent,message):
        gtk.MessageDialog.__init__(self,parent,gtk.MESSAGE_QUESTION)
        self.add_buttons(gtk.STOCK_OK,gtk.RESPONSE_OK,
                    gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.macroEntry = gtk.Entry()
        self.macroEntry.connect("activate", self.cb_macroEntry_activated)
        self.vbox.pack_end(self.macroEntry)
        self.set_markup(message)

    def cb_macroEntry_activated(self, event):
        self.response(gtk.RESPONSE_OK)

            
    
if __name__=='__main__':
    
    s = Settings(True)
#    gtk.main()
