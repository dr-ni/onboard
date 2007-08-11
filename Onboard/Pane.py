class Pane:
	"The pane holds the keys and is drawn by the keyboard widget."
	def __init__(self,keyboard,ident,keys,columns,viewPortSizeX,viewPortSizeY,rgba,fontSize):
		self.ident = ident
		self.keys = keys
		self.viewPortSizeX = viewPortSizeX
		self.viewPortSizeY = viewPortSizeY
		self.fontSize = fontSize
		self.xScale = 1
		self.xScale = 1
		self.rgba = rgba
		self.keyboard = keyboard
		self.columns = columns
		return


	def paint(self,context,width,height):
		
		self.xScale = width/self.viewPortSizeX
            	self.yScale = height/self.viewPortSizeY
		
		for key in self.keys.values():
                	key.paint(context,self.xScale,self.yScale)

                
                for key in self.keys.values():
                	key.paintFont(context,self.xScale, self.yScale)

		return

	def set_DrawingArea(self, da):
		self.da = da
