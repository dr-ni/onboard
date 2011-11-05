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

    # group string of the item, size group for keys
    group = None

    # name of the layer the item is to be shown on, None for all layers
    layer_id = None

    # filename of the svg file where the key geometry is defined
    filename = None

    # child items
    items = ()

    # key context for transformation between logical and canvas coordinates
    context = None

    # State of visibility. Also determines if drawing space will be
    # assigned to this item and its children.
    visible = True

    # sensitivity, aka. greying; True to stop interaction witht the item
    sensitive = True

    # Border around the item. The border is invisible but still
    # sensitive to clicks.
    border = 0.0

    # Expand item in LayoutBoxes
    # "True" expands the item into the space of invisible siblings.
    # "False" keeps it at the size of the even distribution of all siblings.
    #         Usually this will lock the key to the aspect ratio of its
    #         svg geometry.
    expand = True

    # columns of rows of key ids for scanning
    scan_columns = None

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
        s = "   "*_level + "{} id={} layer_id={} filename={}\n".format(
                                  object.__repr__(self),
                                  repr(self.id),
                                  repr(self.layer_id),
                                  repr(self.filename),
                                  repr(self.visible),
                                  ) + \
               "".join(item.dumps() for item in self.items)
        _level -= 1
        return s

    def set_items(self, items):
        self.items = items
        for item in items:
            item.parent = self

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

    def fit_inside_canvas(self, canvas_border_rect, keep_aspect = False,
                                x_align = 0.5, y_align = 0.0):
        """
        Scale item and its children to fit inside the given canvas_rect.
        """
        # update items bounding boxes
        for item in self.iter_depth_first():
            item.update_log_rect()

        # keep aspect ratio and align the result
        if keep_aspect:
            log_rect = self.context.log_rect
            canvas_border_rect = log_rect.align_inside_rect(canvas_border_rect,
                                                          x_align, y_align)

        # recursively fit inside canvas
        self._fit_inside_canvas(canvas_border_rect)

    def _fit_inside_canvas(self, canvas_border_rect):
        """
        Scale item and its children to fit inside the given canvas_rect.
        """
        self.context.canvas_rect = canvas_border_rect

    def update_log_rect(self):
        """
        Override this for layout items that have to calculate their
        logical rectangle.
        """
        pass

    def is_point_within(self, canvas_point):
        """ Returns true if the point lies within the items borders. """
        rect = self.get_canvas_border_rect().inflate(1)
        return rect.point_inside(canvas_point)

    def is_visible(self):
        """ Returns visibility status """
        return self.visible

    def has_visible_key(self):
        """
        Checks if there is any visible key in the
        subtree starting at self.
        """
        for item in self.iter_visible_items():
            if item.is_key():
                return True
        return False

    def get_layout_root(self):
        """ Returns the root layout item """
        item = self
        while item:
            if item.parent is None:
                return item
            item = item.parent

    def get_layer(self):
        """ Returns the first layer on the path from the tree root to self """
        layer_id = None
        item = self
        while item:
            if not item.layer_id is None:
                layer_id = item.layer_id
            item = item.parent
        return layer_id

    def set_visible_layers(self, layer_ids):
        """
        Show all items of layer "layer", hide all items of the other layers.
        """
        if not self.layer_id is None:
            self.visible = self.layer_id in layer_ids

        for item in self.items:
            item.set_visible_layers(layer_ids)

    def get_layer_ids(self, _layer_ids=None):
        """
        Searches the tree for layer ids and returns them in order of appearance
        """
        if _layer_ids is None:
            _layer_ids = []

        if not self.layer_id is None and \
           not self.layer_id in _layer_ids:
            _layer_ids.append(self.layer_id)

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
        return False

    def iter_items(self):
        """
        Iterates through all layout items of the layout tree.
        """
        yield self

        for item in self.items:
            for child in item.iter_depth_first():
                yield child

    def iter_depth_first(self):
        """
        Iterates depth first through all layout items of the layout tree.
        """
        for item in self.items:
            for child in item.iter_depth_first():
                yield child

        yield self

    def iter_visible_items(self):
        """
        Traverses top to bottom all visible layout items of the
        layout tree. Invisible paths are cut short.
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

    def iter_layer_keys(self, layer_id = None):
        """
        Iterates through all keys of the given layer.
        """
        for item in self.iter_layer_items(layer_id):
            if item.is_key():
                yield item

    def iter_layer_items(self, layer_id = None, only_visible = True,
                              _found_layer_id = None):
        """
        Iterates through all items of the given layer.
        The first layer definition found in the path to each key wins.
        layer=None iterates through all keys that don't have a layer
        specified anywhere in their path.
        """
        if only_visible and not self.visible:
            return

        if self.layer_id == layer_id:
            _found_layer_id = layer_id

        if self.layer_id and self.layer_id != _found_layer_id:
            return

        if _found_layer_id == layer_id:
            yield self

        for item in self.items:
            for item in item.iter_layer_items(layer_id, only_visible,
                                              _found_layer_id):
                yield item



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
        """
        Calculate the bounding rectangle over all items of this panel.
        Include invisible items to stretch the visible ones into their
        space too.
        """
        # If there is no visible item return an empty rect
        # if all(not item.is_visible() for item in self.items):
        #     return Rect()

        bounds = None
        for item in self.items:
            rect = item.get_border_rect()
            if not rect.is_empty():
                if bounds is None:
                    bounds = rect
                else:
                    bounds = bounds.union(rect)

        if bounds is None:
            return Rect()
        return bounds

    def _fit_inside_canvas(self, canvas_border_rect):
        """ Scale items to fit inside the given canvas_rect """

        LayoutItem._fit_inside_canvas(self, canvas_border_rect)

        axis = 0 if self.horizontal else 1
        items = self.items

        # get canvas rectangle without borders
        canvas_rect = self.get_canvas_rect()

        # Find the combined length of all items, including
        # invisible ones (logical coordinates).
        length = 0.0
        for i, item in enumerate(items):
            rect = item.get_border_rect()
            if not rect.is_empty():
                if i:
                    length += self.spacing
                length += rect[axis+2]

        # Find the stretch factor, that fills the available canvas space with
        # evenly distributed, all visible items.
        fully_visible_scale = canvas_rect[axis+2] / length \
                              if length else 1.0
        canvas_spacing = fully_visible_scale * self.spacing

        # Transform items into preliminary canvas space, drop invisibles
        # and find the total lengths of expandable and non-expandable
        # items (preliminary canvas coordinates).
        length_expandables = 0.0
        num_expandables = 0
        length_nonexpandables = 0.0
        num_nonexpandables = 0
        for i, item in enumerate(items):
            length = item.get_border_rect()[axis+2]
            if length and item.has_visible_key():
                length *= fully_visible_scale
                if item.expand:
                    length_expandables += length
                    num_expandables += 1
                else:
                    length_nonexpandables += length
                    num_nonexpandables += 1

        # Calculate a second stretch factor for expandable and actually
        # visible items. This takes care of the part of the canvas_rect,
        # that isn't covered by the first factor yet.
        # All calculation is done in preliminary canvas coordinates.
        length_target = canvas_rect[axis+2] - length_nonexpandables - \
                   canvas_spacing * (num_nonexpandables + num_expandables - 1)
        expandable_scale = length_target / length_expandables \
                           if length_expandables else 1.0

        # Calculate the final canvas rectangles and traverse
        # the tree recursively.
        position = 0.0
        for i, item in enumerate(items):
            rect = item.get_border_rect()
            if item.has_visible_key():
                length  = rect[axis+2]
                spacing = canvas_spacing
            else:
                length  = 0.0
                spacing = 0.0

            scale = fully_visible_scale
            if item.expand:
                scale *= expandable_scale
            canvas_length = length * scale

            # set the final canvas rect
            r = Rect(*canvas_rect)
            r[axis]   = canvas_rect[axis] + position
            r[axis+2] = canvas_length
            item._fit_inside_canvas(r)

            position += canvas_length + spacing


class LayoutPanel(LayoutItem):
    """
    Group of keys layed out at fixed positions relative to each other.
    """

    def _fit_inside_canvas(self, canvas_border_rect):
        """
        Scale panel to fit inside the given canvas_rect.
        """
        LayoutItem._fit_inside_canvas(self, canvas_border_rect)
        # Setup the childrens transformations, take care of the border.
        if self.get_border_rect().is_empty():
            # clear all items transformations if there are no visible items
            for item in self.items:
                item.context.canvas_rect = Rect()
        else:
            context = KeyContext()
            context.log_rect = self.get_border_rect()
            context.canvas_rect = self.get_canvas_rect()

            for item in self.items:
                rect = context.log_to_canvas_rect(item.context.log_rect)
                item._fit_inside_canvas(rect)

    def update_log_rect(self):
        self.context.log_rect = self._calc_bounds()

    def _calc_bounds(self):
        """ Calculate the bounding rectangle over all items of this panel """
        # If there is no visible item return an empty rect
        if all(not item.is_visible() for item in self.items):
            return Rect()

        bounds = None
        for item in self.items:
            rect = item.get_border_rect()
            if not rect.is_empty():
                if bounds is None:
                    bounds = rect
                else:
                    bounds = bounds.union(rect)

        if bounds is None:
            return Rect()
        return bounds

