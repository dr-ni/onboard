""" Classes for recursive layout definition """

from Onboard.utils import Rect

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################


class KeyContext(object):
    """
    Transforms logical coordinates into canvas coordinates and vice versa.
    """
    def __init__(self):
        # logical rectangle as defined by the keyboard layout
        self.log_rect = Rect(0.0, 0.0, 1.0, 1.0)  # includes border

        # canvas rectangle in drawing units
        self.canvas_rect = Rect(0.0, 0.0, 1.0, 1.0)

    def __repr__(self):
        return" log={} canvas={}".format(self.log_rect.to_list(),
                                         self.canvas_rect.to_list())

    def log_to_canvas(self, coord):
        return (self.log_to_canvas_x(coord[0]), \
                self.log_to_canvas_y(coord[1]))

    def log_to_canvas_rect(self, rect):
        if rect.is_empty():
            return Rect()
        return Rect(self.log_to_canvas_x(rect.x),
                    self.log_to_canvas_y(rect.y),
                    self.scale_log_to_canvas_x(rect.w),
                    self.scale_log_to_canvas_y(rect.h))

    def log_to_canvas_x(self, x):
        return self.canvas_rect.x + (x - self.log_rect.x) * self.canvas_rect.w / self.log_rect.w

    def log_to_canvas_y(self, y):
        return self.canvas_rect.y + (y - self.log_rect.y) * self.canvas_rect.h / self.log_rect.h


    def scale_log_to_canvas(self, coord):
        return (self.scale_log_to_canvas_x(coord[0]), \
                self.scale_log_to_canvas_y(coord[1]))

    def scale_log_to_canvas_x(self, x):
        return x * self.canvas_rect.w / self.log_rect.w

    def scale_log_to_canvas_y(self, y):
        return y * self.canvas_rect.h / self.log_rect.h


    def canvas_to_log(self, coord):
        return (self.canvas_to_log_x(coord[0]), \
                self.canvas_to_log_y(coord[1]))

    def canvas_to_log_rect(self, rect):
        return Rect(self.canvas_to_log_x(rect.x),
                    self.canvas_to_log_y(rect.y),
                    self.scale_canvas_to_log_x(rect.w),
                    self.scale_canvas_to_log_y(rect.h))

    def canvas_to_log_x(self, x):
        return x * self.log_rect.w / self.canvas_rect.w + self.log_rect.x

    def canvas_to_log_y(self, y):
        return y * self.log_rect.h / self.canvas_rect.h + self.log_rect.y


    def scale_canvas_to_log_x(self, x):
        return x * self.log_rect.w / self.canvas_rect.w

    def scale_canvas_to_log_y(self, y):
        return y * self.log_rect.h / self.canvas_rect.h


class LayoutItem(object):
    """ Abstract base class for layoutable items """

    # parent item in the layout tree
    parent = None

    # id string of the item
    id = None

    # name of the layer the item is to be shown on, None for all layers
    layer = None

    # filename of the svg file where the key geometry is defined
    filename = None

    # child items
    items = ()

    # key context for transformation between logical and canvas coordinates
    context = None

    # State of visibility. Also determines if drawing space will be
    # assigned to this item and its children.
    visible = True

    # border around the item
    border = 0.0


    def __init__(self):
        self.context = KeyContext()

    def dumps(self):
        """
        Recursively dumps the layout (sub-) tree starting from self.
        Returns a multi-line string.
        """
        global _level
        if not "_level" in globals():
            _level = -1
        _level += 1
        s = "   "*_level + "{} id={} layer={} filename={}\n".format(
                                  object.__repr__(self),
                                  repr(self.id),
                                  repr(self.layer),
                                  repr(self.filename),
                                  repr(self.visible),
                                  ) + \
               "".join(item.dumps() for item in self.items)
        _level -= 1
        return s

    def get_rect(self):
        """ Get bounding box in logical coordinates """
        return self.get_border_rect().deflate(self.border)

    def get_border_rect(self):
        """ Get bounding rect including border in logical coordinates """
        return self.context.log_rect

    def get_canvas_rect(self):
        """ Get bounding box in canvas coordinates """
        return self.context.log_to_canvas_rect(self.get_rect())

    def get_canvas_border_rect(self):
        """ Get bounding rect including border in canvas coordinates """
        return self.context.canvas_rect

    def fit_inside_canvas(self, canvas_border_rect):
        """
        Scale panel to fit inside the given canvas_rect.
        """
        self.context.canvas_rect = canvas_border_rect
        self.update_log_rect()

    def update_log_rect(self):
        pass

    def is_point_within(self, canvas_point):
        """ Returns true if the point lies inside of the items borders. """
        return self.get_canvas_border_rect().point_inside(canvas_point)

    def is_visible(self):
        """ Returns visibility status """
        return self.visible

    def set_visible_layers(self, layers):
        """
        Show all items of layer "layer", hide all items of the other layers.
        """
        if not self.layer is None:
            self.visible = self.layer in layers

        for item in self.items:
            item.set_visible_layers(layers)

    def get_layer_ids(self, _layer_ids=None):
        """
        Searches the tree for layer ids and returns them in order of appearance
        """
        if _layer_ids is None:
            _layer_ids = []

        if not self.layer is None and \
           not self.layer in _layer_ids:
            _layer_ids.append(self.layer)

        for item in self.items:
            item.get_layer_ids(_layer_ids)

        return _layer_ids

    def get_key_groups(self):
        """
        Traverses the tree and returns all keys sorted by group.
        """
        key_groups = {}
        for key in self.iter_keys():
            keys = key_groups.get(key.group, [])
            keys.append(key)
            key_groups[key.group] = keys
        return key_groups

    def bring_group_to_front(self, group_name):
        return
        group_names = [_name for _name, _keys in self.key_groups]
        if group_name in group_names:
            index = group_names.index(group_name)
            group = self.key_groups[index]
            self.key_groups.remove(group)
            self.key_groups.append(group)

    def get_filename(self):
        """ Recursively finds the closeset definition of the svg filename """
        if self.filename:
            return self.filename
        if self.parent:
            return self.parent.get_filename()
        return None

    def is_key(self):
        """ Returns true if self is a key. """
        return self.__class__.__name__ == "RectKey"

    def iter_visible_items(self):
        """
        Iterates through all visible layout items of the layout tree.
        Invisible items hide all of their children as well.
        """
        if self.visible:
            yield self

            for item in self.items:
                for visible_item in item.iter_visible_items():
                    yield visible_item

    def iter_keys(self, group_name = None):
        """
        Iterates through all keys of the layout tree.
        """
        if self.is_key():
            if group_name is None or key.group == group_name:
                yield self

        for item in self.items:
            for key in item.iter_keys(group_name):
                yield key

    def iter_layer_keys(self, layer = None, _found_layer = None):
        """
        Iterates through all keys of the given layer.
        The first layer definition found in the path to each key wins.
        layer=None iterates through all keys that don't have a layer
        specified anywhere in their path.
        """
        if self.layer == layer:
            _found_layer = layer

        if self.layer and self.layer != _found_layer:
            return

        if self.is_key():
            if _found_layer == layer:
                yield self

        for item in self.items:
            for key in item.iter_layer_keys(layer, _found_layer):
                yield key



class LayoutBox(LayoutItem):
    """
    Container for one or more non-overlapping layout items.
    Items can be layed out either horiuontally or vertically.
    """

    # Spread out child items horizontally or vertically.
    horizontal = True

    # distance between items
    spacing = 1

    def update_log_rect(self):
        self.context.log_rect = self._calc_bounds()

    def _calc_bounds(self):
        """ Get bounding box including border in logical coordinates """
        bounds_rect = Rect()
        for item in self.items:
            if item.is_visible():
                rect = item.get_border_rect()
                if bounds_rect.is_empty():
                    bounds_rect = rect
                else:
                    bounds_rect = bounds_rect.union(rect)
        return bounds_rect

    def fit_inside_canvas(self, canvas_border_rect):
        """ Scale items to fit inside the given canvas_rect """

        LayoutItem.fit_inside_canvas(self, canvas_border_rect)

        # sort items in order of increasing position
        axis = 0 if self.horizontal else 1
        items = sorted(self.items, 
                       key=lambda item: item.get_border_rect()[axis])

        # get canvas rectangle without borders
        canvas_rect = self.get_canvas_rect()

        # determine what portion of the canvas each item covers
        spans = []
        position = 0.0
        for i, item in enumerate(items):
            if item.is_visible():
                rect = item.get_border_rect()
                length = rect[axis+2]
                if position and not rect.is_empty():
                    position += self.spacing
            else:
                length = 0
            spans.append([position, length])
            position += length

        # stretch all items to fill the available space
        scale = canvas_rect[axis+2] / position

        # assign the new canvas rect (drawing destination)
        for i, item in enumerate(items):
            rect = Rect(*canvas_rect)
            rect[axis]   = canvas_rect[axis] + spans[i][0] * scale
            rect[axis+2] = spans[i][1] * scale
            item.fit_inside_canvas(rect)


class LayoutPanel(LayoutItem):
    """
    Group of keys layed out at fixed positions relative to each other.
    """

    def fit_inside_canvas(self, canvas_border_rect):
        """
        Scale panel to fit inside the given canvas_rect.
        """
        LayoutItem.fit_inside_canvas(self, canvas_border_rect)

        # Setup the childrens transformations, taking care of the border.
        if self.get_border_rect().is_empty():
            for item in self.items:
                item.context.canvas_rect = Rect()
        else:
            context = KeyContext()
            context.log_rect = self.get_border_rect()
            context.canvas_rect = self.get_canvas_rect()

            for item in self.items:
                if True or item.layer is None:
                    rect = context.log_to_canvas_rect(item.context.log_rect)
                    item.fit_inside_canvas(rect)
                else:
                    rect = context.log_to_canvas_rect(self.context.log_rect)
                    item.fit_inside_canvas(rect)

    def update_log_rect(self):
        self.context.log_rect = self._calc_bounds()

    def _calc_bounds(self):
        """ Calculate the bounding rectangle over all items of this panel """
        bounds = None
        for item in self.items:
            if item.is_visible():
                rect = item.get_border_rect()
                if not rect.is_empty():
                    if bounds is None:
                        bounds = rect
                    else:
                        bounds = bounds.union(rect)

        if bounds is None:
            return Rect()
        return bounds

