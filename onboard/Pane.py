class Pane:
	
	def __init__(self,sok,ident,keys,columns,viewPortSizeX,viewPortSizeY,rgba,fontSize):
		self.ident = ident
		self.keys = keys
		self.viewPortSizeX = viewPortSizeX
		self.viewPortSizeY = viewPortSizeY
		self.fontSize = fontSize
		self.xScale = 1
		self.xScale = 1
		self.rgba = rgba
		self.sok = sok
		self.columns = columns
		return

	#def set_keys(self,keys):
	#	self.keys = keys

	def paint(self,context,fontContext,width,height):
		
		self.xScale = width/self.viewPortSizeX
            	self.yScale = height/self.viewPortSizeY
		
		for key in self.keys.values():
                #key = self.keys[k]
                	key.paint(context,self.xScale,self.yScale)

                
                for key in self.keys.values():
                #key = self.keys[k]
                	key.paintFont(fontContext,self.xScale, self.yScale)


		return

	def set_DrawingArea(self, da):
		self.da = da
