class Pane:
    "The pane holds the keys and is drawn by the keyboard widget."

    xScale = 1
    yScale = 1

    def __init__(self,keyboard,ident,keys,columns,viewPortSizeX,viewPortSizeY,rgba,fontSize):
        self.ident = ident
        self.viewPortSizeX = viewPortSizeX
        self.viewPortSizeY = viewPortSizeY
        self.fontSize = fontSize
        self.xScale = 1
        self.yScale = 1
        self.rgba = rgba
        self.keyboard = keyboard
        self.columns = columns
        self.key_groups = {'_default': keys}
        return

    def paint(self, context):
        for group in self.key_groups.values():
            for key in group.values():
                key.paint(self.xScale, self.yScale, context)
                key.paintFont(self.xScale, self.yScale, context)

    def on_size_changed(self, width, height, *args, **kargs):
        self.xScale = width/self.viewPortSizeX
        self.yScale = height/self.viewPortSizeY

    def configure_labels(self, mods, *args, **kargs):
        """
        Cycles through each group of keys in this pane and set each key's
        label font size to the maximum possible for that group.
        """
        for group in self.key_groups.values():
            max_size = 0
            for key in group.values():
                key.configure_label(mods, self.xScale, self.yScale)
                best_size = key.get_best_font_size(self.xScale, self.yScale,
                    *args, **kargs)
                if not max_size or best_size < max_size:
                    max_size = best_size
            for key in group.values():
                key.font_size = max_size
