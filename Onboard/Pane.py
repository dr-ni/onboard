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
                	key.paint(self.xScale, self.yScale, context)

                
                for key in self.keys.values():
                	key.paintFont(self.xScale, self.yScale, context)

		return

