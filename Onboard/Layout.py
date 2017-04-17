# -*- coding: utf-8 -*-

# Copyright © 2012 Gerd Kohlberger <lowfi@chello.at>
# Copyright © 2011-2014, 2016 marmuta <marmvta@gmail.com>
#
# This file is part of Onboard.
#
# Onboard is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Onboard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

""" Classes for recursive layout definition """

import time
from math import exp

from Onboard.utils import Rect, TreeItem
from Onboard.Timer import Timer, idle_call

from Onboard.Config import Config
config = Config()


class KeyContext(object):
    """
    Transforms logical coordinates to canvas coordinates and vice versa.
    """
    def __init__(self):
        # Logical rectangle as defined by the keyboard layout.
        # Never changed after loading.
        self.initial_log_rect = Rect(0.0, 0.0, 1.0, 1.0)  # includes border

        # Logical rectangle as defined by the keyboard layout.
        # May be changed after loading e.g. for word suggestion keys.
        self.log_rect = Rect(0.0, 0.0, 1.0, 1.0)  # includes border

        # Canvas rectangle in drawing units.
        self.canvas_rect = Rect(0.0, 0.0, 1.0, 1.0)

    def __repr__(self):
        return "log={} canvas={}".format(list(self.log_rect),
                                         list(self.canvas_rect))

    def log_to_canvas(self, coord):
        return (self.log_to_canvas_x(coord[0]),
                self.log_to_canvas_y(coord[1]))

    def log_to_canvas_rect(self, rect):
        if rect.is_empty():
            return Rect()
        return Rect(self.log_to_canvas_x(rect.x),
                    self.log_to_canvas_y(rect.y),
                    self.scale_log_to_canvas_x(rect.w),
                    self.scale_log_to_canvas_y(rect.h))

    def log_to_canvas_x(self, x):
        canvas_rect = self.canvas_rect
        log_rect = self.log_rect
        return canvas_rect.x + (x - log_rect.x) * canvas_rect.w / log_rect.w

    def log_to_canvas_y(self, y):
        canvas_rect = self.canvas_rect
        log_rect = self.log_rect
        return canvas_rect.y + (y - log_rect.y) * canvas_rect.h / log_rect.h

    def scale_log_to_canvas(self, coord):
        return (self.scale_log_to_canvas_x(coord[0]),
                self.scale_log_to_canvas_y(coord[1]))

    def scale_log_to_canvas_l(self, coord):
        return list(self.scale_log_to_canvas(coord))

    def scale_log_to_canvas_x(self, x):
        return x * self.canvas_rect.w / self.log_rect.w

    def scale_log_to_canvas_y(self, y):
        return y * self.canvas_rect.h / self.log_rect.h

    def canvas_to_log(self, coord):
        return (self.canvas_to_log_x(coord[0]),
                self.canvas_to_log_y(coord[1]))

    def canvas_to_log_rect(self, rect):
        return Rect(self.canvas_to_log_x(rect.x),
                    self.canvas_to_log_y(rect.y),
                    self.scale_canvas_to_log_x(rect.w),
                    self.scale_canvas_to_log_y(rect.h))

    def canvas_to_log_x(self, x):
        canvas_rect = self.canvas_rect
        log_rect = self.log_rect
        return (x - canvas_rect.x) * log_rect.w / canvas_rect.w + log_rect.x

    def canvas_to_log_y(self, y):
        canvas_rect = self.canvas_rect
        log_rect = self.log_rect
        return (y - canvas_rect.y) * log_rect.h / canvas_rect.h + log_rect.y

    def scale_canvas_to_log(self, coord):
        return (self.scale_canvas_to_log_x(coord[0]),
                self.scale_canvas_to_log_y(coord[1]))

    def scale_canvas_to_log_l(self, coord):
        return list(self.scale_canvas_to_log(coord))

    def scale_canvas_to_log_x(self, x):
        return x * self.log_rect.w / self.canvas_rect.w

    def scale_canvas_to_log_y(self, y):
        return y * self.log_rect.h / self.canvas_rect.h

    def log_to_canvas_path(self, path):
        result = path.copy()
        log_to_canvas_x = self.log_to_canvas_x
        log_to_canvas_y = self.log_to_canvas_y
        for op, coords in result.segments:
            for i in range(0, len(coords), 2):
                coords[i]   = log_to_canvas_x(coords[i])
                coords[i + 1] = log_to_canvas_y(coords[i + 1])
        return result

    # ##### Speed-optimized overloads #####

    def log_to_canvas(self, coord):   # noqa: flake8
        canvas_rect = self.canvas_rect
        log_rect = self.log_rect
        return (canvas_rect.x + (coord[0] - log_rect.x) *
                canvas_rect.w / log_rect.w,
                canvas_rect.y + (coord[1] - log_rect.y) *
                canvas_rect.h / log_rect.h)

    def log_to_canvas_rect(self, rect):   # noqa: flake8
        """ ~50% faster than the above. """
        w = rect.w
        h = rect.h
        if w <= 0 or h <= 0:
            return Rect()

        canvas_rect = self.canvas_rect
        log_rect = self.log_rect
        scale_w = canvas_rect.w / log_rect.w
        scale_h = canvas_rect.h / log_rect.h

        return Rect(canvas_rect.x + (rect.x - log_rect.x) * scale_w,
                    canvas_rect.y + (rect.y - log_rect.y) * scale_h,
                    w * scale_w,
                    h * scale_h)

    def scale_log_to_canvas(self, coord):   # noqa: flake8
        canvas_rect = self.canvas_rect
        log_rect = self.log_rect
        return (coord[0] * canvas_rect.w / log_rect.w,
                coord[1] * canvas_rect.h / log_rect.h)


class LayoutRoot:
    """
    Decorator class wrapping the root item.
    Implements extensive caching to avoid most of the expensive
    (for python) traversal of the layout tree.
    """
    def __init__(self, item):
        self.__dict__['_item'] = item    # item to decorate
        self.invalidate_caches()
        self.init_chamfer_sizes()
        self._font_sizes_valid = False
        self._item.root_decorator = self  # point back here from the tree root

    def __getattr__(self, name):
        return getattr(self._item, name)

    def __setattr__(self, name, value):
        self._item.__setattr__(name, value)

    def invalidate_caches(self):
        self.invalidate_traversal_caches()
        self.invalidate_geometry_caches()

    def invalidate_traversal_caches(self):
        # speed up iterating the tree
        self._cached_items = {}
        self._cached_keys = {}
        self._cached_visible_items = {}
        self._cached_layer_items = {}
        self._cached_layer_keys = {}
        self._cached_key_groups = {}

        # cache available layers
        self._cached_layer_ids = None

    def invalidate_geometry_caches(self):
        # speed up hit testing
        self._cached_hit_rects = {}
        self._last_hit_args = None
        self._last_hit_key = None

    def invalidate_font_sizes(self):
        """
        Update font_sizes at the next possible chance.
        """
        self._font_sizes_valid = False

    def get_font_sizes_valid(self):
        return self._font_sizes_valid

    def set_font_sizes_valid(self, valid):
        self._font_sizes_valid = valid

    def fit_inside_canvas(self, canvas_border_rect):
        self._item.fit_inside_canvas(canvas_border_rect)

        # rects likely changed
        # -> invalidate geometry related caches
        self.invalidate_geometry_caches()

    def do_fit_inside_canvas(self, canvas_border_rect):
        self._item.do_fit_inside_canvas(canvas_border_rect)

        # rects likely changed
        # -> invalidate geometry related caches
        self.invalidate_geometry_caches()

    def set_visible_layers(self, layer_ids):
        """
        Show all items of layer "layer", hide all items of the other layers.
        """
        self.invalidate_caches()
        self._item.set_visible_layers(layer_ids)

    def set_item_visible(self, item, visible):
        if item.visible != visible:
            item.set_visible(visible)
            self.invalidate_caches()

    def iter_items(self):
        items = self._cached_items
        if not items:
            items = tuple(self._item.iter_items())
            self._cached_items = items
        return items

    def iter_keys(self, group_name=None):
        items = self._cached_keys.get(group_name)
        if not items:
            items = tuple(self._item.iter_keys(group_name))
            self._cached_keys[group_name] = items
        return items

    def iter_visible_items(self):
        items = self._cached_visible_items
        if not items:
            items = tuple(self._item.iter_visible_items())
            self._cached_visible_items = items
        return items

    def iter_layer_keys(self, layer_id):
        """
        Returns cached visible keys per layer, re-creates cache if necessary.
        Use iter_layer_keys if performance doesn't matter.
        """
        items = self._cached_layer_keys.get(layer_id)
        if not items:
            items = tuple(self._item.iter_layer_keys(layer_id))
            self._cached_layer_keys[layer_id] = items
        return items

    def iter_layer_items(self, layer_id=None, only_visible=True):
        args = (layer_id, only_visible)
        items = self._cached_layer_items.get(args)
        if not items:
            items = tuple(self._item.iter_layer_items(*args))
            self._cached_layer_items[args] = items
        return items

    def get_layer_ids(self, parent_layer_id=None):
        layer_ids = self._cached_layer_ids
        if not layer_ids:
            layer_ids = self._item.get_layer_ids()
            self._cached_layer_ids = layer_ids

        if parent_layer_id:
            prefix = parent_layer_id + "."
            return [id for id in layer_ids if id.startswith(prefix)]

        return layer_ids

    def get_key_groups(self):
        """
        Return all keys sorted by group.
        """
        key_groups = self._cached_key_groups
        if not key_groups:
            key_groups = self._item.get_key_groups()
            self._cached_key_groups = key_groups
        return key_groups

    def get_key_at(self, point, active_layer_ids):
        """
        Find the topmost key at point.
        """
        active_layer_ids = tuple(active_layer_ids)

        # After motion-notify-event the query-tooltip event calls this
        # a second time with the same point. Don't search again in that case.
        args = (point, active_layer_ids)
        if self._last_hit_args == args:
            return self._last_hit_key

        key = None
        x, y = point
        hit_rects = self._get_hit_rects(active_layer_ids)
        for x0, y0, x1, y1, k in hit_rects:
            # Inlined test, not using Rect.is_point_within for speed.
            if x >= x0 and x < x1 and \
               y >= y0 and y < y1:
                if k.geometry is None or \
                   k.get_hit_path().is_point_within(point):
                    key = k
                    break

        self._last_hit_args = args
        self._last_hit_key = key

        return key

    def _get_hit_rects(self, active_layer_ids):
        try:
            hit_rects = self._cached_hit_rects[active_layer_ids]
        except KeyError:
            # All visible and sensitive key items sorted by z-order.
            # Keys of the active layer have priority over non-layer keys
            # (layer switcher, hide, etc.).
            iter_layer_keys = self.iter_layer_keys
            items = []
            for layer_id in reversed(active_layer_ids):
                items.extend(list(reversed(list(iter_layer_keys(layer_id)))))
            items.extend(list(reversed(list(iter_layer_keys(None)))))

            hit_rects = []
            for item in items:
                r = item.get_hit_rect()
                if r is not None:  # not clipped away?
                    hit_rects.append(r.to_extents() + (item,))

            self._cached_hit_rects[active_layer_ids] = hit_rects

        return hit_rects

    def init_chamfer_sizes(self):
        chamfer_sizes = self._calc_chamfer_sizes()
        for key in self.iter_global_keys():
            if key.chamfer_size is None:
                layer_id = key.get_layer()
                chamfer_size = chamfer_sizes.get(layer_id)
                if chamfer_size is not None:
                    key.chamfer_size = chamfer_size

    def _calc_chamfer_sizes(self):
        chamfer_sizes = {}
        for layer_id in [None] + self.get_layer_ids():
            # find the most frequent key width or height of the layer
            hist = {}
            for key in self.iter_layer_keys(layer_id):
                r = key.get_border_rect()
                s = min(r.w, r.h)
                hist[s] = hist.get(s, 0) + 1
            most_frequent_size = \
                max(list(zip(list(hist.values()), list(hist.keys()))))[1] \
                if hist else None
            chamfer_size = most_frequent_size * 0.5 \
                if most_frequent_size is not None else None
            chamfer_sizes[layer_id] = chamfer_size
        return chamfer_sizes


class LayoutItem(TreeItem):
    """ Abstract base class for layoutable items """

    # group string of the item, label size group for keys
    group = None

    # take this item out of the size group when updating the layout.
    # Instead chose the best label size for this item alone.
    ignore_group = None

    # name of the layer the item is to be shown on, None for all layers
    layer_id = None

    # filename of the svg file where the key geometry is defined
    filename = None

    # key context for transformation between logical and canvas coordinates
    context = None

    # State of visibility. Also determines if drawing space will be
    # assigned to this item and its children.
    visible = True

    # sensitivity, aka. greying; False to stop interaction with the item
    sensitive = True

    # Border around the item. The border "shrinks" the item and
    # is invisible but still sensitive to clicks.
    border = 0.0

    # Expand item in LayoutBoxes
    # "True"  expands the item into the space of invisible siblings.
    # "False" keeps it at the size of the even distribution of all siblings.
    #         Usually this will lock the key to the aspect ratio of its
    #         svg geometry.
    expand = True

    # sublayout sub-trees
    sublayouts = None

    # parent item of sublayout roots
    sublayout_parent = None

    # override switching back to layer 0 on key press
    # True:  do switch to layer 0 on press
    # False: dont't
    # None:  maybe, hard-coded default-behavior for compatibility with <0.99
    unlatch_layer = None

    # False if the key should be ignored by the scanner
    scannable = True

    # Determines scanning order
    scan_priority = None

    # parsing helpers, only valid while loading a layout
    templates = None
    keysym_rules = None

    # root decorator
    root_decorator = None

    # Clip children?
    clip_rect = None

    # Function to continue event processing on cancelling a gesture
    sequence_begin_retry_func = None

    def __init__(self):
        self.context = KeyContext()

    def __repr__(self):
        return "{}({})".format(type(self).__name__, repr(self.id))

    def dumps(self):
        """
        Recursively dumps the layout (sub-) tree starting from self.
        Returns a multi-line string.
        """
        global _level
        if "_level" not in globals():
            _level = -1
        _level += 1
        s = "   " * _level + "{} id={} layer_id={} fn={} vis={} {}\n" \
            .format(object.__repr__(self),
                    repr(self.id),
                    repr(self.layer_id),
                    repr(self.filename),
                    repr(self.visible),
                    repr(self.context.log_rect),
                    ) + \
            "".join(item.dumps() for item in self.items)
        _level -= 1
        return s

    def set_id(self, id):
        self.id = id

    def get_rect(self):
        """ Get bounding box in logical coordinates """
        return self.get_border_rect().deflate(self.border)

    def get_border_rect(self):
        """ Get bounding rect including border in logical coordinates """
        return self.context.log_rect

    def set_border_rect(self, border_rect):
        """ Set bounding rect including border in logical coordinates """
        self.context.log_rect = border_rect

    def get_initial_border_rect(self):
        """
        Get initial bounding rect including border in logical coordinates
        """
        return self.context.initial_log_rect

    def set_initial_border_rect(self, border_rect):
        """
        Set initial bounding rect including border in logical coordinates.
        """
        self.context.initial_log_rect = border_rect

    def get_canvas_rect(self):
        """ Get bounding box in canvas coordinates """
        return self.context.log_to_canvas_rect(self.get_rect())

    def get_canvas_border_rect(self):
        """ Get bounding rect including border in canvas coordinates """
        return self.context.canvas_rect

    def get_log_aspect_ratio(self):
        """
        Return the aspect ratio of the visible logical extents
        of the layout tree.
        """
        size = self.get_log_extents()
        return size[0] / float(size[1])

    def get_log_extents(self):
        """
        Get the logical extents of the layout tree.
        Extents ignore invisible, "collapsed" items,
        ie. an invisible click column is not included.
        """
        return self.get_border_rect().get_size()

    def get_canvas_extents(self):
        """
        Get the canvas extents of the layout tree.
        """
        size = self.get_log_extents()
        return self.context.scale_log_to_canvas(size)

    def get_extra_render_size(self):
        """ Account for stroke width and antialiasing of keys and bars"""
        root = self.get_layout_root()
        return root.context.scale_log_to_canvas((2.0, 2.0))

    def fit_inside_canvas(self, canvas_border_rect):
        """
        Scale item and its children to fit inside the given canvas_rect.
        """
        # recursively update item's bounding boxes
        self.update_log_rects()

        # recursively fit inside canvas
        self.do_fit_inside_canvas(canvas_border_rect)

    def do_fit_inside_canvas(self, canvas_border_rect):
        """
        Scale item and its children to fit inside the given canvas_rect.
        """
        self.context.canvas_rect = canvas_border_rect

    def update_log_rects(self):
        """
        Recursively update the log_rects of this sub-tree.
        """
        for item in self.iter_depth_first():
            item.update_log_rect()

    def update_log_rect(self):
        """
        Update the log_rect of this item.
        Override this for layout items that have to calculate their
        logical rectangle.
        """
        pass

    def get_hit_rect(self):
        """ Returns true if the point lies within the items borders. """
        rect = self.get_canvas_border_rect().inflate(1)

        # attempt to clip at the parents clip_rect
        parent = self.get_parent()
        if parent and parent.clip_rect is not None:
            rect = parent.clip(rect)
            if rect.is_empty():
                return None

        return rect

    def set_clip_rect(self, canvas_rect):
        """ Set clipping rectangle in canvas coordinates. """
        self.clip_rect = canvas_rect

    def clip(self, canvas_rect):
        """ Clip rect at the current clipping rect """
        return self.clip_rect.intersection(canvas_rect)

    def is_point_within(self, canvas_point):
        """ Returns true if the point lies within the items borders. """
        rect = self.get_hit_rect()
        if rect is None:
            return False
        return rect.is_point_within(canvas_point)

    def set_visible(self, visible):
        if self.visible != visible:
            self.visible = visible
            self.on_visibility_changed(visible)

    def is_visible(self):
        """ Returns visibility status """
        return self.visible

    def on_visibility_changed(self, visible):
        for item in self.items:
            item.on_visibility_changed(visible)

    def is_path_visible(self):
        """ Are all items in the path to the root visible? """
        item = self
        while item:
            if not item.visible:
                return False
            item = item.parent
        return True

    def has_visible_key(self):
        """
        Checks if there is any visible key in the
        subtree starting at self.
        """
        for item in self.iter_visible_items():
            if item.is_key():
                return True
        return False

    def is_path_scannable(self):
        """ Are all items in the path to the root scannable? """
        item = self
        while item:
            if not item.scannable:
                return False
            item = item.parent
        return True

    def get_path_scan_priority(self):
        """ Return the closeset scan_priority in the path to the root. """
        item = self
        while item:
            if item.scan_priority is not None:
                return item.scan_priority
            item = item.parent
        return 0

    def get_layout_root(self):
        """ Return the root layout item """
        item = self
        while item:
            if item.parent is None:
                return item
            item = item.parent

    def get_root_decorator(self):
        """ Return the root decorator if available """
        return self.get_layout_root().root_decorator

    def get_layer(self):
        """
        Return the first layer_id on the path from the tree root to self
        """
        layer_id = None
        item = self
        while item:
            if item.layer_id is not None:
                layer_id = item.layer_id
            item = item.parent
        return layer_id

    @staticmethod
    def layer_to_parent_id(layer_id):
        """
        Doctests:
        >>> repr(LayoutItem.layer_to_parent_id(None))
        'None'
        >>> repr(LayoutItem.layer_to_parent_id("abc"))
        'None'
        >>> LayoutItem.layer_to_parent_id("abc.cde")
        'abc'
        >>> LayoutItem.layer_to_parent_id("abc.cde.fgh")
        'abc.cde'
        """
        if layer_id is None:
            return None

        pos = layer_id.rfind(".")
        if pos >= 0:
            return layer_id[:pos]
        return None

    def set_visible_layers(self, layer_ids):
        """
        Show all items of layers <layer_ids>, hide all items of
        the other layers.
        """
        if self.layer_id is not None:
            if not self.is_key():
                self.set_visible(self.layer_id in layer_ids)

        for item in self.items:
            item.set_visible_layers(layer_ids)

    def get_layer_ids(self, _layer_ids=None):
        """
        Search the tree for layer ids and return them in order of appearance
        """
        if _layer_ids is None:
            _layer_ids = []

        if self.layer_id is not None and \
           self.layer_id not in _layer_ids:
            _layer_ids.append(self.layer_id)

        for item in self.items:
            item.get_layer_ids(_layer_ids)

        return _layer_ids

    def get_key_groups(self):
        """
        Traverse the tree and return all keys sorted by group.
        """
        key_groups = {}
        for key in self.iter_keys():
            keys = key_groups.get(key.group, [])
            keys.append(key)
            key_groups[key.group] = keys
        return key_groups

    def lower_to_bottom(self):
        """ lower self to the bottom of its siblings """
        if self.parent:
            self.parent.items.remove(self)
            self.parent.items.insert(0, self)

    def raise_to_top(self):
        """ raise self to the top of its siblings """
        if self.parent:
            self.parent.items.remove(self)
            self.parent.items.append(self)

    def get_filename(self):
        """
        Recursively searches for the closest definition of the svg filename.
        """
        if self.filename:
            return self.filename
        if self.parent:
            return self.parent.get_filename()
        return None

    def can_unlatch_layer(self):
        """
        Recursively searches for the closest definition of the
        unlatch_layer attribute.
        """
        if self.unlatch_layer is not None:
            return self.unlatch_layer
        if self.parent:
            return self.parent.can_unlatch_layer()
        return None

    def is_key(self):
        """ Returns true if self is a key. """
        return False

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

    def iter_keys(self, group_name=None):

        """
        Iterates through all keys of the layout tree.
        """
        if self.is_key():
            if group_name is None or self.group == group_name:
                yield self

        for item in self.items:
            for key in item.iter_keys(group_name):
                yield key

    def iter_global_items(self):
        """
        Iterates through all items of the tree including sublayouts.
        """
        yield self

        for item in self.items:
            for child in item.iter_global_items():
                yield child

        if self.sublayouts:
            for item in self.sublayouts:
                for child in item.iter_global_items():
                    yield child

    def iter_global_keys(self, group_name=None):
        """
        Iterates through all keys of the layout tree including sublayouts.
        """
        if self.is_key():
            if group_name is None or self.group == group_name:
                yield self

        for item in self.items:
            for key in item.iter_global_keys(group_name):
                yield key

        if self.sublayouts:
            for item in self.sublayouts:
                for key in item.iter_global_keys(group_name):
                    yield key

    def iter_layer_keys(self, layer_id=None):
        """
        Iterates through all keys of the given layer.
        """
        for item in self.iter_layer_items(layer_id):
            if item.is_key():
                yield item

    def iter_layer_items(self, layer_id=None, only_visible=True,
                         _found_layer_id=None):
        """
        Iterate through all items of the given layer.
        The first layer definition found in the path to each key wins.
        layer=None iterates through all keys that don't have a layer
        specified anywhere in their path.
        """
        if only_visible and not self.visible:
            return

        if self.layer_id == layer_id:
            _found_layer_id = layer_id

        if self.layer_id and \
           self.layer_id != _found_layer_id and \
           (not layer_id or
            not (self.layer_id.startswith(layer_id + ".") or
                 layer_id.startswith(self.layer_id + "."))):
            return

        if _found_layer_id == layer_id:
            yield self

        for item in self.items:
            for item in item.iter_layer_items(layer_id, only_visible,
                                              _found_layer_id):
                yield item

    def find_instance_in_path(self, classinfo):
        """
        Find an item of a certain type in the path from self to the root.
        """
        item = self
        while item:
            if isinstance(item, classinfo):
                return item
            item = item.parent
        return None

    def update_templates(self, templates):
        if templates:
            if self.templates is None:
                self.templates = templates
            else:
                self.templates.update(templates)

    def update_keysym_rules(self, keysym_rules):
        if keysym_rules:
            if self.keysym_rules is None:
                self.keysym_rules = keysym_rules
            else:
                self.keysym_rules.update(keysym_rules)

    def append_sublayout(self, sublayout):
        if sublayout:
            if self.sublayouts is None:
                self.sublayouts = []
            self.sublayouts.append(sublayout)

    def find_sublayout(self, id):
        """
        Look for a sublayout item upwards from self to the root.
        """
        for item in self.iter_to_root():
            sublayouts = item.sublayouts
            if sublayouts:
                for sublayout in sublayouts:
                    if sublayout.id == id:
                        return sublayout
        return None

    def iter_to_global_root(self):
        """
        Iterate through sublayouts all the way to the global layout root.
        LayoutLoader needs this to access key templates from inside of
        sublayouts.
        """
        item = self
        while item:
            yield item
            item = item.parent or item.sublayout_parent

    def on_press(self, view, button, event_type):
        pass

    def on_release(self, view, button, event_type):
        pass

    def dispatch_input_sequence_begin(self, sequence):
        if self.visible and self.sensitive:
            point = sequence.point
            rect = self.get_canvas_border_rect()
            if rect.is_point_within(point):

                # allow self to handle it first
                if self.on_input_sequence_begin(sequence):
                    return True

                # then ask the children
                for item in self.items:
                    if item.dispatch_input_sequence_begin(sequence):
                        return True

    def dispatch_input_sequence_update(self, sequence):
        if sequence.active_item is not None:
            sequence.active_item.on_input_sequence_update(sequence)
        else:
            if self.visible and self.sensitive:
                point = sequence.point
                rect = self.get_canvas_border_rect()
                if rect.is_point_within(point):

                    if self.on_input_sequence_update(sequence):
                        return True

                    for item in self.items:
                        if item.dispatch_input_sequence_update(sequence):
                            return True

    def dispatch_input_sequence_end(self, sequence):
        if sequence.active_item is not None:
            sequence.active_item.on_input_sequence_end(sequence)
        else:
            if self.visible and self.sensitive:
                point = sequence.point
                rect = self.get_canvas_border_rect()
                if rect.is_point_within(point):

                    # allow self to handle it first
                    if self.on_input_sequence_end(sequence):
                        return True

                    # then ask the children
                    for item in self.items:
                        if item.dispatch_input_sequence_end(sequence):
                            return True

    def on_input_sequence_begin(self, sequence):
        return False

    def on_input_sequence_update(self, sequence):
        return False

    def on_input_sequence_end(self, sequence):
        return False

    def draw_tree(self, context):
        """
        Traverses top to bottom all visible layout items of the
        layout tree. Invisible paths are cut short.
        """
        if self.visible:
            if context.draw_rect.intersects(self.get_canvas_border_rect()):
                if self.clip_rect is not None:
                    cr = context.cr
                    cr.save()
                    cr.rectangle(*self.clip_rect.int())  # int clip is faster
                    cr.clip()

                self.draw_item(context)

                for item in self.items:
                    item.draw_tree(context)

                if self.clip_rect is not None:
                    context.cr.restore()

    def draw_item(self, context):
        if self.layer_id:
            context.draw_layer_background(self)


class LayoutBox(LayoutItem):
    """
    Container for distributing items along a single horizontal or
    vertical axis. Items touch, but don't overlap.
    """

    # Spread out child items horizontally or vertically.
    horizontal = True

    # distance between items
    spacing = 1

    # Don't extend bounding box into invisibles
    compact = False

    def __init__(self, horizontal=True):
        super(LayoutBox, self).__init__()
        if self.horizontal != horizontal:
            self.horizontal = horizontal

    def update_log_rect(self):
        self.context.log_rect = self._calc_bounds()

    def _calc_bounds(self):
        """
        Calculate the bounding rectangle over all items of this panel.
        Include invisible items to stretch the visible ones into their
        space too.
        """
        compact = self.compact
        bounds = None
        for item in self.items:
            if not compact or item.visible:
                rect = item.get_border_rect()
                if not rect.is_empty():
                    if bounds is None:
                        bounds = rect
                    else:
                        bounds = bounds.union(rect)

        if bounds is None:
            return Rect()
        return bounds

    def do_fit_inside_canvas(self, canvas_border_rect):
        """ Scale items to fit inside the given canvas_rect """

        LayoutItem.do_fit_inside_canvas(self, canvas_border_rect)

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
                length += rect[axis + 2]

        # Find the stretch factor, that fills the available canvas space with
        # evenly distributed, all visible items.
        fully_visible_scale = canvas_rect[axis + 2] / length \
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
            length = item.get_border_rect()[axis + 2]
            if length and item.has_visible_key():
                length *= fully_visible_scale
                if item.expand:
                    length_expandables += length
                    num_expandables += 1
                else:
                    length_nonexpandables += length
                    num_nonexpandables += 1

        # Calculate a second stretch factor for expandable and actually
        # visible items. This takes care of the part of the canvas_rect
        # that isn't covered by the first factor yet.
        # All calculation is done in preliminary canvas coordinates.
        length_target = canvas_rect[axis + 2] - length_nonexpandables - \
            canvas_spacing * (num_nonexpandables + num_expandables - 1)
        expandable_scale = length_target / length_expandables \
            if length_expandables else 1.0

        # Calculate the final canvas rectangles and traverse
        # the tree recursively.
        position = 0.0
        for i, item in enumerate(items):
            rect = item.get_border_rect()
            if item.has_visible_key():
                length  = rect[axis + 2]
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
            r[axis + 2] = canvas_length
            item.do_fit_inside_canvas(r)

            position += canvas_length + spacing

    def get_log_extents(self):
        """
        Get the logical extents of the layout tree.
        Extents ignore invisible, "collapsed" items,
        ie. an invisible click column is not included.
        """
        rect = None
        for item in self.items:
            r = item.get_border_rect()
            if rect is None:
                rect = r.copy()
            else:
                if self.horizontal:
                    rect.w += r.w
                else:
                    rect.h += r.h

        return rect.get_size()


class DrawingItem(LayoutItem):
    """
    Base class of drawable Items.
    """

    # extended id for key specific theme tweaks
    # e.g. theme_id=DELE.numpad (with id=DELE)
    theme_id = None

    # extended id for layout specific tweaks
    # e.g. "hide.wordlist", for hide button in wordlist mode
    svg_id = None

    # color scheme
    color_scheme = None

    def __init__(self):
        LayoutItem.__init__(self)
        self.colors = {}

    def get_svg_id(self):
        return ""

    def set_id(self, id, theme_id=None, svg_id=None):
        self.theme_id, self.id = self.parse_id(id)
        if theme_id:
            self.theme_id = theme_id
        self.svg_id = self.id if not svg_id else svg_id

    @staticmethod
    def parse_id(value):
        """
        The theme id has the form <id>.<arbitrary identifier>, where
        the identifier should be a description of the location of
        the key relative to its surroundings, e.g. 'DELE.next-to-backspace'.
        Don't use layout names or layer ids for the theme id, they lose
        their meaning when layouts are copied or renamed by users.
        """
        theme_id = value
        id = value.split(".")[0]
        return theme_id, id

    @staticmethod
    def split_theme_id(theme_id):
        """
        Simple split in prefix (id) before the dot and suffix after the dot.
        """
        components = theme_id.split(".")
        if len(components) == 1:
            return components[0], ""
        return components[0], components[1]

    @staticmethod
    def build_theme_id(prefix, postfix):
        if postfix:
            return prefix + "." + postfix
        return prefix

    def get_similar_theme_id(self, prefix=None):
        if prefix is None:
            prefix = self.id
        theme_id = prefix
        comps = self.theme_id.split(".")[1:]
        if comps:
            theme_id += "." + comps[0]
        return theme_id

    def get_fill_color(self):
        return self.get_color("fill")

    def get_stroke_color(self):
        return self.get_color("stroke")

    def get_label_color(self):
        return self.get_color("label")

    def get_secondary_label_color(self):
        return self.get_color("secondary-label")

    def get_dwell_progress_color(self):
        return self.get_color("dwell-progress")

    def get_color(self, element, state=None):
        color_key = (element)
        try:
            return self.colors[color_key]
        except KeyError:
            return self.cache_color(element, color_key, state)

    def cache_color(self, element, color_key, state=None):
        if self.color_scheme:
            rgba = self.color_scheme.get_key_rgba(self, element, state)
        elif element == "label":
            rgba = [0.0, 0.0, 0.0, 1.0]
        else:
            rgba = [1.0, 1.0, 1.0, 1.0]
        self.colors[color_key] = rgba
        return rgba

    def get_state(self):
        state = {}
        return state


class RectangleItem(DrawingItem):
    """
    Item that draws a simple filled rectangle.
    """

    def draw_item(self, context):
        cr = context.cr
        cr.save()
        cr.set_source_rgba(*self.get_fill_color())
        cr.rectangle(*self.get_canvas_rect())
        cr.fill()
        cr.restore()


class LayoutPanel(DrawingItem):
    """
    Group of keys layed out at fixed positions relative to each other.
    """

    # Don't extend bounding box into invisibles
    compact = False

    def do_fit_inside_canvas(self, canvas_border_rect):
        """
        Scale panel to fit inside the given canvas_rect.
        """
        LayoutItem.do_fit_inside_canvas(self, canvas_border_rect)

        # Setup children's transformations, take care of the border.
        if self.get_border_rect().is_empty():
            # Clear all item's transformations if there are no visible items.
            for item in self.items:
                item.context.canvas_rect = Rect()
        else:
            context = KeyContext()
            context.log_rect = self.get_border_rect()
            context.canvas_rect = self.get_canvas_rect()  # exclude border

            for item in self.items:
                rect = context.log_to_canvas_rect(item.context.log_rect)
                item.do_fit_inside_canvas(rect)

    def update_log_rect(self):
        self.context.log_rect = self._calc_bounds()

    def _calc_bounds(self):
        """ Calculate the bounding rectangle over all items of this panel """
        # If there is no visible item return an empty rect
        if all(not item.is_visible() for item in self.items):
            return Rect()

        compact = self.compact
        bounds = None
        for item in self.items:
            if not compact or item.visible:
                rect = item.get_border_rect()
                if not rect.is_empty():
                    if bounds is None:
                        bounds = rect
                    else:
                        bounds = bounds.union(rect)

        if bounds is None:
            return Rect()
        return bounds


class ScrolledLayoutPanel(LayoutPanel):
    """
    LayoutPanel with inertial scrolling.

    get_border_rect(): size of the  panel
    _scroll_rect: extends of the area to be scrolled, logical coordinates
    """
    def __init__(self):
        super(ScrolledLayoutPanel, self).__init__()

        self._scroll_rect = Rect()  # area to be scrolled, logical coordinates
        self._scroll_offset = [0, 0]          # logical coordinate

        self._drag_begin_point = None
        self._drag_begin_scroll_offset = [0, 0]
        self._drag_active = False
        self._drag_cancelled = False
        self._step_timer = Timer()
        self._cancel_timer = Timer()

        self._lock_x_axis         = False
        self._lock_y_axis         = False

        self.scrolled_context = KeyContext()

        self.stop_scrolling()

    def update_log_rect(self):
        # do not calculate bounds from content
        pass

    def set_scroll_rect(self, rect):
        """
        Set size of the virtual area to be scrolled over.
        Logical coordinates.
        """
        self._scroll_rect = rect.copy()
        self.set_damage(self.get_visible_scrolled_rect())

    def set_scroll_offset(self, offset_x, offset_y):
        """
        Set scrolled position. Logical coordinates.
        """
        self.stop_scrolling()

        r = self.get_visible_scrolled_rect()
        offset_x = max(r.w - self._scroll_rect.w, offset_x)
        offset_y = max(r.h - self._scroll_rect.h, offset_y)

        self._scroll_offset = [offset_x, offset_y]
        self._update_contents()

    def get_scroll_offset(self):
        return self._scroll_offset

    def stop_scrolling(self):
        self._last_step_time = None
        self._target_offset = [None, None]
        self._acceleration = [0, 0]
        self._velocity = [0, 0]
        self._dampening = [0, 0]
        self._step_timer.stop()

    def lock_x_axis(self, lock):
        """ Set to False to constraint movement in x. """
        self._lock_x_axis = lock

    def lock_y_axis(self, lock):
        """ Set to True to constraint movement in y. """
        self._lock_y_axis = lock

    def set_damage(self, scrolled_log_rect):
        self.on_damage(scrolled_log_rect)

    def on_damage(self, scrolled_log_rect):
        pass

    def on_input_sequence_begin(self, sequence):
        if sequence.primary:
            sequence.active_item = self
            self._drag_initiate(sequence)
        return False

    def on_input_sequence_update(self, sequence):
        if self.is_drag_initiated() and \
           not self.is_drag_cancelled():

            self._drag_update(sequence)

            if self.is_drag_active():
                sequence.cancel_key_action = True
                sequence.active_item = self

        return False

    def on_input_sequence_end(self, sequence):
        if self.is_drag_active():
            self._drag_end()
            sequence.active_item = None
        elif self.is_drag_initiated() and not self.is_drag_cancelled():
            self._drag_cancel(sequence)

        return False

    def _drag_initiate(self, sequence):
        point = sequence.point
        self._drag_active = False
        self._drag_cancelled = False
        self._drag_begin_point = point[:]
        self._drag_begin_scroll_offset = self._scroll_offset[:]
        self._drag_begin_time = time.time()
        self._dampening = [20, 20]

        log_point = self.scrolled_context.canvas_to_log(sequence.point)
        if self.is_background_at(log_point):
            self._drag_activate()
        else:
            self._cancel_timer.start(0.35, self._drag_cancel, sequence)

    def _drag_activate(self):
        self._drag_active = True
        self._cancel_timer.stop()
        self._start_animation()

    def _drag_cancel(self, sequence):
        self._drag_cancelled = True
        self._drag_end()

        sequence.active_item = None
        if self.sequence_begin_retry_func is not None:
            self.sequence_begin_retry_func(sequence)

        return False

    def _drag_update(self, sequence):
        point = sequence.point
        dx = point[0] - self._drag_begin_point[0]
        dy = point[1] - self._drag_begin_point[1]

        # initiate scrolling?
        if not self.is_drag_active():
            dt = time.time() - self._drag_begin_time
            d_thresh = 12.0
            v_thresh = 100.0

            d = abs(dx)
            vx = d / dt
            if d > d_thresh and vx > v_thresh:
                if self._lock_x_axis:
                    self._drag_cancel(sequence)
                else:
                    self._drag_activate()
            else:
                d = abs(dy)
                vy = d / dt
                if d > d_thresh and vy > v_thresh:
                    if self._lock_y_axis:
                        self._drag_cancel(sequence)
                    else:
                        self._drag_activate()

        if self.is_drag_active():
            context = self.context
            self._target_offset = \
                [self._drag_begin_scroll_offset[0] +
                    context.scale_canvas_to_log_x(dx),
                    self._drag_begin_scroll_offset[1] +
                    context.scale_canvas_to_log_y(dy)]

    def _drag_end(self):
        self._drag_active = False
        self._drag_begin_point = None
        self._drag_begin_scroll_offset = None
        self._target_offset = [None, None]
        self._dampening = [3, 3]
        self._cancel_timer.stop()

    def is_drag_initiated(self):
        """ Sequence begin received, but not yet actually dragging. """
        return self._drag_begin_point is not None

    def is_drag_active(self):
        """ Are we actually dragging? """
        return self._drag_active

    def is_drag_cancelled(self):
        """ Has gesture been cancelled before it could become active? """
        return self._drag_cancelled

    def _start_animation(self):
        self._step_timer.start(1.0 / 60.0, self._step_scroll_position)

    def _stop_animation(self):
        self._step_timer.stop()
        self._last_step_time = None

    def _step_scroll_position(self):
        force = [0.0, 0.0]
        context = self.context

        t = time.time()
        if self._last_step_time is not None:
            dt = min(t - self._last_step_time, 0.1)  # stay in stable range
            mass = 0.002
            limit_dampening = 15
            limit_force_scale = 0.25

            canvas_rect = self.get_canvas_rect()
            scroll_rect = context.log_to_canvas_rect(self._scroll_rect)
            scroll_offset = context.scale_log_to_canvas_l(self._scroll_offset)
            target_offset = [
                None if self._target_offset[0] is None
                else context.scale_log_to_canvas_x(self._target_offset[0]),
                None if self._target_offset[1] is None
                else context.scale_log_to_canvas_y(self._target_offset[1])]

            tleft = canvas_rect.left() - scroll_rect.left()
            dleft = scroll_offset[0] - tleft

            tright = canvas_rect.right() - scroll_rect.right()
            dright = scroll_offset[0] - tright

            ttop = canvas_rect.top() - scroll_rect.top()
            dtop = scroll_offset[1] - ttop

            tbottom = canvas_rect.bottom() - scroll_rect.bottom()
            dbottom = scroll_offset[1] - tbottom

            # left limit
            if dleft > 0:
                force[0] -= dleft * limit_force_scale
                self._dampening[0] = limit_dampening
                if not self.is_drag_active() and \
                   target_offset[0] is None:
                    target_offset[0] = tleft   # snap to edge

            # right limit
            elif dright < 0:
                force[0] -= dright * limit_force_scale
                self._dampening[0] = limit_dampening
                if not self.is_drag_active() and \
                   target_offset[0] is None:
                    target_offset[0] = tright

            # top limit
            if dtop > 0:
                force[1] -= dtop * limit_force_scale
                self._dampening[1] = limit_dampening
                if not self.is_drag_active() and \
                   target_offset[1] is None:
                    target_offset[1] = ttop

            # bottom limit
            elif dbottom < 0:
                force[1] -= dbottom * limit_force_scale
                self._dampening[1] = limit_dampening
                if not self.is_drag_active() and \
                   target_offset[1] is None:
                    target_offset[1] = tbottom

            if target_offset[0] is not None:
                force[0] += target_offset[0] - scroll_offset[0]
            if target_offset[1] is not None:
                force[1] += target_offset[1] - scroll_offset[0]

            self._acceleration[0] = force[0] / mass
            self._acceleration[1] = force[1] / mass
            self._velocity[0] += self._acceleration[0] * dt
            self._velocity[1] += self._acceleration[1] * dt
            self._velocity[0] *= exp(dt * -self._dampening[0])
            self._velocity[1] *= exp(dt * -self._dampening[1])

            if not self._lock_x_axis:
                scroll_offset[0] += self._velocity[0] * dt
                if 0 and self.is_drag_active() and \
                   not target_offset[0] is None:
                    scroll_offset[0] = target_offset[0]

            if not self._lock_y_axis:
                scroll_offset[1] += self._velocity[1] * dt
                if 0 and self.is_drag_active() and \
                   not target_offset[1] is None:
                    scroll_offset[1] = target_offset[1]

            self._scroll_offset = context.scale_canvas_to_log_l(scroll_offset)

            self._target_offset[0] = None if target_offset[0] is None \
                else context.scale_canvas_to_log_x(target_offset[0])
            self._target_offset[1] = None if target_offset[1] is None \
                else context.scale_canvas_to_log_y(target_offset[1])

            idle_call(self._update_contents_on_scroll)

        self._last_step_time = t

        # stop updates when movement has died down
        if not self.is_drag_initiated():
            eps = 0.5
            velocity2 = (self._velocity[0] * self._velocity[0] +
                         self._velocity[1] * self._velocity[1])
            if force[0] < eps and \
               force[1] < eps and \
               velocity2 < eps * eps:
                self._stop_animation()

        return True

    def _update_contents_on_scroll(self):
        # time.sleep(0.1)
        self._update_contents()
        self.on_scroll_offset_changed()

    def _update_contents(self):
        self.do_fit_inside_canvas(self.get_canvas_border_rect())
        self.set_damage(self.get_visible_scrolled_rect())

    def on_scroll_offset_changed(self):
        pass

    def get_visible_scrolled_rect(self):
        """
        Portion of the virtual scroll rect visible in the Panel,
        in logical coordinates.
        """
        rect = self.get_rect()
        rect.x -= self._scroll_offset[0]
        rect.y -= self._scroll_offset[1]
        return rect

    def do_fit_inside_canvas(self, canvas_border_rect):
        """
        Translate children.
        """
        LayoutItem.do_fit_inside_canvas(self, canvas_border_rect)

        # Setup children's transformations, take care of the border.
        if self.get_border_rect().is_empty():
            # Clear all item's transformations if there are no visible items.
            for item in self.items:
                item.context.canvas_rect = Rect()
        else:
            context = KeyContext()
            context.log_rect = self.get_border_rect()
            context.canvas_rect = self.get_canvas_rect()  # exclude border
            context.canvas_rect.x += \
                self.context.scale_log_to_canvas_x(self._scroll_offset[0])
            context.canvas_rect.y += \
                self.context.scale_log_to_canvas_y(self._scroll_offset[1])
            self.scrolled_context = context

            for item in self.items:
                rect = context.log_to_canvas_rect(item.context.log_rect)
                item.do_fit_inside_canvas(rect)

    def draw_item(self, context):
        cr = context.cr
        cr.save()
        cr.set_source_rgba(*self.get_fill_color())
        cr.rectangle(*self.get_canvas_rect())
        cr.fill()
        cr.restore()



