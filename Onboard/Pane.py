class Pane:
    "The pane holds the keys and is drawn by the keyboard widget."

    xScale = 1
    yScale = 1

    def __init__(self,keyboard,ident,keys,columns,viewPortSizeX,viewPortSizeY,rgba,fontSize):
        self.ident = ident
        self.keys = keys
        self.viewPortSizeX = viewPortSizeX
        self.viewPortSizeY = viewPortSizeY
        self.fontSize = fontSize
        self.xScale = 1
        self.yScale = 1
        self.rgba = rgba
        self.keyboard = keyboard
        self.columns = columns
        return

    def paint(self, context):
        for key in self.keys.values():
                    key.paint(self.xScale, self.yScale, context)

        for key in self.keys.values():
            key.paintFont(self.xScale, self.yScale, context)

    def on_size_changed(self, width, height, *args, **kargs):
        self.xScale = width/self.viewPortSizeX
        self.yScale = height/self.viewPortSizeY

    def configure_labels(self, mods, *args, **kargs):
        for key in self.keys.values():
            key.configure_label(mods, self.xScale, self.yScale, 
                    *args, **kargs)
