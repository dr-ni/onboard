class Pane:
    "The pane holds the keys and is drawn by the keyboard widget."

    scale = (0, 0)
    """
    The amount to multiply to convert from layout co-ordinates to drawing
    co-ordinates.
    """

    def __init__(self, name, key_groups, columns, size, rgba):

        self.name = name
        """ The name for this pane, needed when saving keyboard layout """

        self.size = size
        """ The size of this pane as defined in the keyboard layout """

        self.rgba = rgba
        """
        Four tuple with values between 0 and 1 containing the pane's
        background colour
        """

        self.columns = columns
        """ A two dimensional array of Keys.  Used for scanning """

        self.key_groups = key_groups
        """
        Dictionary with group name as the key and an array of keys for each
        value.  Each group of keys is drawn with the same label font size.
        """

    def paint(self, context):
        for group in self.key_groups.values():
            for key in group:
                key.paint(self.scale, context)
                key.paint_font(self.scale, context)

    def on_size_changed(self, width, height, *args, **kargs):
        self.scale = (width / self.size[0], height / self.size[1])

    def configure_labels(self, mods, *args, **kargs):
        """
        Cycles through each group of keys in this pane and set each key's
        label font size to the maximum possible for that group.
        """
        for group in self.key_groups.values():
            max_size = 0
            for key in group:
                key.configure_label(mods, self.scale)
                best_size = key.get_best_font_size(self.scale, *args, **kargs)
                if not max_size or best_size < max_size:
                    max_size = best_size
            for key in group:
                key.font_size = max_size

    def get_key_at_location(self, location, *args, **kargs):
        for group in self.key_groups.values():
            for key in group:
                if key.point_within_key(location, self.scale, *args, **kargs):
                    return key
