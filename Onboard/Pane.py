### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class PaneContext:
    def __init__(self):
        # the available window size
        self.canvas_size = 1,1

        # the size of this pane as defined in the keyboard layout
        self.log_size = 1,1
        self.log_offset = 0,0  # start of the bounding box around visible keys

    def log_to_canvas_x(self, x):
        return (x - self.log_offset[0]) * self.canvas_size[0] / self.log_size[0]

    def log_to_canvas_y(self, y):
        return (y - self.log_offset[1]) * self.canvas_size[1] / self.log_size[1]

    def scale_log_to_canvas_x(self, x):
        return x * self.canvas_size[0] / self.log_size[0]

    def scale_log_to_canvas_y(self, y):
        return y * self.canvas_size[1] / self.log_size[1]

    def canvas_to_log(self, coord):
        return (self.canvas_to_log_x(coord[0]), self.canvas_to_log_y(coord[1]))

    def canvas_to_log_x(self, x):
        return x * self.log_size[0] / self.canvas_size[0] + self.log_offset[0]

    def canvas_to_log_y(self, y):
        return y * self.log_size[1] / self.canvas_size[1] + self.log_offset[1]

    def scale_canvas_to_log_x(self, x):
        return x * self.log_size[0] / self.canvas_size[0]

    def scale_canvas_to_log_y(self, y):
        return y * self.log_size[1] / self.canvas_size[1]


class Pane:
    "The pane holds the keys and is drawn by the keyboard widget."

    def __init__(self, name, key_groups, columns, size, rgba):

        self.name = name
        """ The name for this pane, needed when saving keyboard layout """

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

        self.wordlist_color_template = None
        """ Template key with colors for the dynamic wordlist """

        self.pane_context = PaneContext()
        """
        Handles conversion between between logical coordinates of the layout
        and drawing coordinates
        """

        self.update_bounding_box()

    def paint(self, context):
        for group in self.key_groups.values():
            for key in group:
                if key.is_visible():
                    key.paint(self.pane_context, context)
                    key.paint_font(self.pane_context, context)

    def on_size_changed(self, width, height, *args, **kargs):
        self.pane_context.canvas_size = width, height

    def configure_labels(self, mods, *args, **kargs):
        """
        Cycles through each group of keys in this pane and set each key's
        label font size to the maximum possible for that group.
        """
        for key,group in self.key_groups.items():
            if key != "word":  # word list uses fixed size font
                max_size = 0
                for key in group:
                    key.configure_label(mods, self.pane_context)
                    best_size = key.get_best_font_size(self.pane_context, *args, **kargs)
                    if not max_size or best_size < max_size:
                        max_size = best_size
                for key in group:
                    key.font_size = max_size

    def get_key_at_location(self, location, *args, **kargs):
        for group in self.key_groups.values():
            for key in group:
                if key.is_active():
                    if key.point_within_key(location, self.pane_context, *args, **kargs):
                        return key

    def update_wordlist(self, builder, choices=[]):

        # dynamic wordlist?
        if self.key_groups.has_key("wordlist"):

            # only support a single wordlist per pane
            wordlist = self.key_groups["wordlist"][0] # background of wordlist
            if not self.wordlist_color_template:
                self.wordlist_color_template = wordlist
                if self.key_groups.has_key("word"):
                    self.wordlist_color_template = self.key_groups["word"][0]

            self.key_groups["word"] = builder.create_wordlist_keys(
                                         choices,
                                         self.pane_context,
                                         wordlist.location,
                                         wordlist.geometry,
                                         self.wordlist_color_template.rgba,
                                         self.wordlist_color_template.label_rgba,
                                         )

        # static word0..n keys?
        elif self.key_groups.has_key("word"):
            keys = self.key_groups["word"]
            raise NotImplementedError()

    def show_word_completion_ui(self, visible):
        for group, keys in self.key_groups.items():
            if group in ("wordlist", "word", "wcbutton"):
                for key in keys:
                    key.visible = visible
        self.update_bounding_box()

    def update_bounding_box(self):
        l = None
        for keys in self.key_groups.values():
            for key in keys:
                if key.is_visible():
                    bounds = key.get_bounds()
                    if bounds:
                        if l is None:
                            l,t = bounds[0]
                            r,b = bounds[1]
                        else:
                            l = min(l,bounds[0][0])
                            t = min(t,bounds[0][1])
                            r = max(r,bounds[1][0])
                            b = max(b,bounds[1][1])
        if not l is None:
            l -= config.LAYOUT_MARGIN[0]
            t -= config.LAYOUT_MARGIN[1]
            r += config.LAYOUT_MARGIN[0]
            b += config.LAYOUT_MARGIN[1]
            self.pane_context.log_offset = l,t
            self.pane_context.log_size   = r-l, b-t



