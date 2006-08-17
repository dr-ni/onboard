import pango
from math import sqrt

class TabKey:
   
   def __init__(self,keyboard,width,pane):
	
	
        self.width = width

	
        self.keyboard = keyboard

	self.on = False
	self.stuckOn = False
	

	
	self.pane = pane

	self.modifier = None	

	self.sticky = True
	self.actions = [False,False,False,False,False,False]

   def point_within_key(self,mouseX,mouseY):
	if (mouseX > self.keyboard.kbwidth 
		and mouseY > self.height*self.index 
		and mouseY < self.height*(self.index + 1)):
			return True
	return False

   
   def paint(self,context):
	self.height = self.keyboard.height/len(self.keyboard.panes)
	self.index = self.keyboard.panes.index(self.pane)
	
        
	context.rectangle(self.keyboard.kbwidth,self.height*self.index,self.width, self.height)
	
	if self.pane == self.keyboard.activePane:
        	if (self.stuckOn):
	    		context.set_source_rgba(1, 0, 0,1)
        	else:
			context.set_source_rgba(0,0,0,0)
	else:
		context.set_source_rgba(float(self.pane.rgba[0]), float(self.pane.rgba[1]),float(self.pane.rgba[2]),float(self.pane.rgba[3]))
	context.fill()
       

class LineKey:
	"class for keyboard buttons made of lines"
	def __init__(self, pane, coordList, rgba):
		self.pane = pane
		self.coordList = coordList
		self.rgba = rgba


		self.labels = ["","","","",""]
	
	        self.pane = pane
	        
	        self.beingScanned = False
    	
    	    	self.actions = ["","","","","",""]
		self.sticky = False
       	 	self.stuckOn = False
		self.on = False
		
		
	def set_properties(self, actions, labels, sticky):
		self.actions = actions
		if sticky == "true":
			self.sticky = True
		else:
			self.sticky= False
		self.labels = labels

    	
	def point_crosses_edge(self,x,y,xp1,yp1,sMouseX,sMouseY):
		if ((((y<=sMouseY) and (sMouseY<yp1)) or  
			((yp1<=sMouseY) and (sMouseY<y))) and 
			(sMouseX < (xp1 - x) * (sMouseY - y) / (yp1 - y) + x)):
							return True
							
		else:
			return False
		
	
	def point_within_key(self,mouseX,mouseY):
		x = self.coordList[0]
		y = self.coordList[1]
		c = 2
		coordLen = len(self.coordList)
		within = False
		
		sMouseX = mouseX/self.pane.xScale
		sMouseY = mouseY/self.pane.yScale
		
		while not c == coordLen:

			xp1 = self.coordList[c+1]
			yp1 = self.coordList[c+2]
			try:
				if self.coordList[c] == "L":
					within = (self.point_crosses_edge(x,y,xp1,yp1,sMouseX,sMouseY) ^ within) # a xor		
					c +=3
					x = xp1
					y = yp1
						
				else:	
					xp2 = self.coordList[c+3]
					yp2 = self.coordList[c+4]
					xp3 = self.coordList[c+5]
					yp3 = self.coordList[c+6]
					within = (self.point_crosses_edge(x,y,xp3,yp3,sMouseX,sMouseY) ^ within) # a xor		i
					x = xp3
					y = yp3
					c += 7

				

			except ZeroDivisionError, (strerror):
				print strerror
				print "x: %f, y: %f, yp1: %f" % (x,y,yp1)
		return within
    	def paint(self,context):
		c = 2
		context.move_to(self.coordList[0], self.coordList[1])
		while not c == len(self.coordList):
			xp1 = self.coordList[c+1]
			yp1 = self.coordList[c+2]
			try:
				if self.coordList[c] == "L":
					c +=3
					context.line_to(xp1,yp1)
				else:	
					xp2 = self.coordList[c+3]
					yp2 = self.coordList[c+4]
					xp3 = self.coordList[c+5]
					yp3 = self.coordList[c+6]
					context.curve_to(xp1,yp1,xp2,yp2,xp3,yp3)
					c += 7
					
			except TypeError, (strerror):
				print x
				print y
				print xp1
				print yp1
				print strerror
				
        		if (self.stuckOn):
	    			context.set_source_rgba(1, 0, 0,1)
			elif (self.on):
            			context.set_source_rgba(0.5, 0.5, 0.5,1)
            		elif (self.beingScanned):	
            			context.set_source_rgba(0.45,0.45,0.7,1)
        		else:
            			context.set_source_rgba(self.rgba[0], self.rgba[1],self.rgba[2],self.rgba[3])
	
        		context.fill_preserve()
		        context.set_source_rgb(0, 0, 0)
		        
			

			
    	def paintFont(self,fontContext, xScale, yScale):
		return
	
	
class RectKey:
    "Class for rectangular keyboard buttons"
    def __init__(self,pane,x,y,width,height,rgba):
        
	self.x = x
        self.y = y
        self.width = width
        self.height = height

	self.rgba = rgba

	self.beingScanned = False
	
	self.actions = [False,False,False,False,False,False]

	self.labels = ["","","","",""]
	
        self.pane = pane
    	
	self.sticky = False
        self.stuckOn = False
	self.on = False
        
    def set_properties(self, actions,labels,sticky):
	self.actions = actions
	self.sticky = sticky
	
	self.labels = labels
	

    def point_within_key(self,mouseX,mouseY):
        if(mouseX/self.pane.xScale>self.x and mouseX/self.pane.xScale<(self.x+self.width)):
            if(mouseY/self.pane.yScale>self.y and mouseY/self.pane.yScale<(self.y+self.height)):
                return True
        else:
            return False
         
    
    def paint(self,context,xScale,yScale):
       
	#context.rectangle(self.x,self.y,self.width, self.height) 
	context.rectangle(self.x*xScale,self.y*yScale,self.width*xScale, self.height*yScale)
	
        if (self.stuckOn):
	    context.set_source_rgba(1, 0, 0,1)
	elif (self.on):
            context.set_source_rgba(0.5, 0.5, 0.5,1)
        elif (self.beingScanned):	
            			context.set_source_rgba(0.45,0.45,0.7,1)
        else:
            context.set_source_rgba(self.rgba[0], self.rgba[1],self.rgba[2],self.rgba[3])
	
        context.fill_preserve()
        context.set_source_rgb(0, 0, 0)

      	context.stroke()
        
        
    def paintFont(self,fontContext, xScale, yScale):
        
        if xScale<yScale:
            fontScale = xScale
        else: 
            fontScale = yScale # oddly python doesn't do scope in if statements.
        
#        fontContext.move_to((self.x + self.width/2)*xScale - 8*fontScale,(self.y + self.height/2)*yScale - 17*fontScale)
       # fontContext.move_to((self.x)*xScale + 3*xScale,(self.y)*yScale + 0.1*yScale)
        
        fontContext.move_to(self.x*xScale + 4, self.y*yScale - 0.03*self.pane.fontSize*sqrt(fontScale))

	if self.pane.sok.mods[1]:
        	if self.pane.sok.mods[128] and self.labels[4]:
        		self.layout = self.pane.da.create_pango_layout(self.labels[4])
        	elif self.labels[2]:
			self.layout = self.pane.da.create_pango_layout(self.labels[2])
		elif self.labels[1]:
			self.layout = self.pane.da.create_pango_layout(self.labels[1])
		else:
			self.layout = self.pane.da.create_pango_layout(self.labels[0])
	
	elif self.pane.sok.mods[128] and self.labels[4]:
		self.layout = self.pane.da.create_pango_layout(self.labels[3])
	
	elif self.pane.sok.mods[2]:
		if self.labels[1]:
			self.layout = self.pane.da.create_pango_layout(self.labels[1])
		else:
			self.layout = self.pane.da.create_pango_layout(self.labels[0])		
	else:
		self.layout = self.pane.da.create_pango_layout(self.labels[0])
	


        self.layout.set_font_description(pango.FontDescription("Sans Serif %d" %(fontScale*self.pane.fontSize)))
        fontContext.update_layout(self.layout)
        fontContext.show_layout(self.layout)
        
