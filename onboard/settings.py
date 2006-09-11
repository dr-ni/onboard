#!/usr/bin/python
import gtk
import gtk.glade
import gconf
import gobject

from virtkey import virtkey

from sok import Sok

import shutil

from utils import *

from xml.parsers.expat import ExpatError
import os
import os.path

class Settings:
	def __init__(self,mainwin):

			
		self.SOK_INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
			
		gladeXML = gtk.glade.XML(os.path.join(self.SOK_INSTALL_DIR,"settings.glade")) 
		self.window = gladeXML.get_widget("settingsWindow")

		gladeXML.signal_autoconnect({"on_layoutView_released" : self.do_change_layout, 
				"on_addButton_clicked": self.add_sok,
				"on_removeButton_clicked": self.cb_removeButton_clicked,
				"on_macroAddButton_clicked": self.add_macro,
				"on_macroView_drag_drop": self.cb_macroList_drag_drop,
				"on_macroRemoveButton_clicked": self.remove_macro,
				"on_closeButton_clicked":self.cb_closeButton_clicked,
				"on_intervalSpin_value_changed" : self.cb_intervalSpin_value_changed,
				"on_scanningCheck_toggled" : self.cb_scanningCheck_toggled,
				"on_closeButton_clicked":gtk.main_quit,
				"on_personaliseButton_clicked": self.cb_on_personaliseButton_clicked,
				"on_layoutFolderButton_clicked" : self.cb_layoutFolderButton_clicked,
				"on_icon_toggled" : self.cb_icon_toggled
				})
		
		self.layoutView = gladeXML.get_widget("layoutView")
		self.macroView = gladeXML.get_widget("macroView")

		
		self.gconfClient = gconf.client_get_default()
		

		self.layoutView.append_column(gtk.TreeViewColumn(None, gtk.CellRendererText(), markup = 0))
				
		self.macroView.append_column(gtk.TreeViewColumn(None, gtk.CellRendererText(), markup = 0))

		self.macroList = gtk.ListStore(str,int) # Complains with just the str.
		self.macroView.set_model(self.macroList)


		self.user_layout_root = "%s/.sok/layouts/" % os.path.expanduser("~")
		if not os.path.exists(self.user_layout_root):
			os.makedirs(self.user_layout_root)
		
		
		self.update_layoutList()
		
		

		tempMacroList = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)
		for m in tempMacroList:
			self.macroList.append((m,0)) 

		
		scanEnabled = self.gconfClient.get_bool("/apps/sok/scanning")
		if scanEnabled:
			gladeXML.get_widget("scanningCheck").set_active(True)
		
		scanInterval = self.gconfClient.get_int("/apps/sok/scanning_interval")
		if scanInterval:
			gladeXML.get_widget("intervalSpin").set_value(float(scanInterval)/1000)
		
		self.window.show()
			
		self.window.set_keep_above(not mainwin)
		
		self.window.connect("destroy", gtk.main_quit)

		
		gtk.main()

	
	def cb_icon_toggled(self,widget):
		self.gconfClient.set_bool("/apps/sok/trayicon",widget.get_active())

	def cb_layoutFolderButton_clicked(self,widget):
		os.system(("nautilus --no-desktop %s" %self.user_layout_root))
	
	def cb_on_personaliseButton_clicked(self, widget):
		dialog = MacroDialog() #recycling
		dialog.vbox.pack_start(gtk.Label("Enter name for personalised layout"))
		dialog.show_all()
		response = dialog.run()
		if response == gtk.RESPONSE_OK:
			text = dialog.macroEntry.get_text()
			s = Sok()
			create_default_layout_XML(text, virtkey(), s)
			s.clean()
			self.update_layoutList()
			os.system(("nautilus --no-desktop %s" %self.user_layout_root))
			
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
		
		it = self.layoutList.append(("Default", ""))
		self.layoutView.get_selection().select_iter(it)
		self.get_soks(os.path.join(self.SOK_INSTALL_DIR,"layouts"))
		self.get_soks(self.user_layout_root)
		
	
	def cb_selected_layout_changed(self):
		self.get_soks(self.user_layout_root)

	def cb_macroList_drag_drop(self, widget, event,thing1,thing2,thing3):
		gobject.idle_add(self.macroList_changed)#To make sure gtk has finished changing the value of macroList before updating gconf.
		

	def macroList_changed(self):
		tempMacroList = []
		it = self.macroList.get_iter_first()
		
		while it:
			tempMacroList.append(self.macroList.get_value(it,0))
			it = self.macroList.iter_next(it)
		
		self.gconfClient.set_list("/apps/sok/macros",gconf.VALUE_STRING, tempMacroList)





	def add_macro(self, event):

		dialog = MacroDialog()

		dialog.show_all()
		response = dialog.run()
		if response == gtk.RESPONSE_OK:
			text = dialog.macroEntry.get_text()
			self.macroList.append((text,0))
			l = self.gconfClient.get_list("/apps/sok/macros",gconf.VALUE_STRING)
			l.append(text)
			self.gconfClient.set_list("/apps/sok/macros",gconf.VALUE_STRING, l)
			
		dialog.destroy()
		
	def remove_macro(self, event):
		self.macroList.remove(self.macroView.get_selection().get_selected()[1])
		self.macroList_changed()
	
		

	
	
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
				theActualFile = open(filename)
				try:
					sokdoc = minidom.parse(theActualFile).documentElement
					if os.access(filename,os.W_OK):
						it = self.layoutList.append(("<i>%s</i>" % sokdoc.attributes["id"].value,filename))#arg is a tuple. Looks wrong.  Silly python.
					else:
						it = self.layoutList.append((sokdoc.attributes["id"].value,filename))
				
					if filename == self.gconfClient.get_string("/apps/sok/layout_filename"):
						self.layoutView.get_selection().select_iter(it)
				except ExpatError,(strerror):
					print "XML in %s %s" % (filename, strerror)
				except KeyError,(strerror):
					print "key %s required in %s" % (strerror,filename)
				
				theActualFile.close()
				

			



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
	
	
		
		
	
class MacroDialog(gtk.Dialog):
	def __init__(self):
		gtk.Dialog.__init__(self)
		self.add_buttons(gtk.STOCK_OK,gtk.RESPONSE_OK,
					gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
		self.macroEntry = gtk.Entry()
		self.macroEntry.connect("activate", self.cb_macroEntry_activated)
		self.vbox.pack_end(self.macroEntry)

	def cb_macroEntry_activated(self, event):
		self.response(gtk.RESPONSE_OK)

			
	
if __name__=='__main__':
    
    s = Settings(True)
#    gtk.main()


