import gtk
import gobject

from Onboard.IconPalette import IconPalette

### Logging ###
import logging
__logger__ = logging.getLogger("KbdWindow")
__logger__.setLevel(logging.WARNING)
###############

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

class KbdWindow(gtk.Window):
    """Very messy class holds the keyboard widget.  The mess is the docked window support which is disable because of numerous metacity bugs."""
    def __init__(self):
        gtk.Window.__init__(self)
        self.keyboard = None
        self.connect("destroy", gtk.main_quit)
        self.connect("configure-event", self.cb_configure_event)
        self.set_accept_focus(False)
        self.grab_remove()
        self.set_keep_above(True)
        self.hidden = True

        config.geometry_notify_add(self.resize)
        self.set_default_size(config.keyboard_width, config.keyboard_height)
        config.position_notify_add(self.move)
        self.move(config.x_position, config.y_position)

        self.connect("window-state-event", self.cb_state_change)

        self.icp = IconPalette()
        self.icp.connect("activated", self.do_show)


    def do_show(self, widget=None):
        if config.icp_in_use: self.icp.do_hide()
        self.icp.forbidShowing = True
        self.move(config.x_position, config.y_position) # to be sure that the window manager places it correctly
        self.show_all()
        self.hidden = False

    def do_hide(self):
        self.hide_all()
        self.hidden = True
        self.icp.forbidShowing = False
        if config.icp_in_use: self.icp.do_show()

    def set_keyboard(self, keyboard):
        if self.keyboard:
            self.remove(self.keyboard)
        self.keyboard = keyboard
        self.add(self.keyboard)
        self.keyboard.show()
        self.queue_draw()

    def do_set_layout(self, client, cxion_id, entry, user_data):
        return

    def cb_configure_event(self, event, user_data):
        """
        Callback that is called when onboard receives a configure-event
        because of a change of its position or size.
        The callback stores the new values to the correspondent gconf
        keys.
        """
        x_pos, y_pos = self.get_position()
        width, height = self.get_size()

        # store new value only if it is different to avoid infinite loop
        if x_pos != config.x_position: config.x_position = x_pos
        if y_pos != config.y_position: config.y_position = y_pos
        if width != config.keyboard_width: config.keyboard_width = width
        if height != config.keyboard_height: onfig.keyboard_height = height


    def do_set_gravity(self, edgeGravity):
        self.edgeGravity = edgeGravity
        width, height = self.get_size()

        '''
        This will place the window on the edge corresponding to the edge gravity
        '''

        geom = self.get_screen().get_monitor_geometry(0)
        eg = self.edgeGravity

        x = 0
        y = 0
        if eg == gtk.gdk.GRAVITY_SOUTH:
            y = geom.height - height
            y += 29 #to account for panel.


        self.move(x, y)

        gobject.idle_add(self.do_set_strut)

    def do_set_strut(self):
        propvals = [0,0,0,0,0,0,0,0,0,0,0,0]
        """propvals = [0,#left
                0, #right
                0, #top
                300,#bottom
                0,#left_start_y
                0,#left_end_y
                0,#right_start_y
                0,#right_end_y
                0,#top_start_x
                0,#top_end_x
                0,#bottom_start_x
                3000]#bottom_end_x"""

        screen = self.get_screen()
        biggestHeight = 0
        for n in range(screen.get_n_monitors()):
            tempHeight = screen.get_monitor_geometry(n).height
            if biggestHeight < tempHeight:
                biggestHeight = tempHeight




        geom = self.get_screen().get_monitor_geometry(0)
        eg = self.edgeGravity
        x, y = self.window.get_origin()

        width,height = self.get_size()

        if eg == gtk.gdk.GRAVITY_NORTH:
            propvals[2] = height + y
            propvals[9] = width
        elif eg == gtk.gdk.GRAVITY_SOUTH and y != 0:
            #propvals[2] = y
            #propvals[9] = geom.width - 1
            propvals[3] = biggestHeight - y
            propvals[11] = width - 1

        # tell window manager to not overlap buttons with maximized window
            self.window.property_change("_NET_WM_STRUT_PARTIAL",
                                        "CARDINAL",
                                        32,
                                        gtk.gdk.PROP_MODE_REPLACE,
                                        propvals)
        self.queue_resize_no_redraw()


    def cb_state_change(self, widget, event):
        # Used to catch the KbdWindow being inconified with the minimized
        # button in the decoration
        # print "cb_kbdwin_state_change has been called"
        if event.changed_mask & gtk.gdk.WINDOW_STATE_ICONIFIED:
            if event.new_window_state & gtk.gdk.WINDOW_STATE_ICONIFIED:
                self.do_hide()
                self.deiconify()

