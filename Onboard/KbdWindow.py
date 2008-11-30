import gtk
import gobject

class KbdWindow(gtk.Window):
    """Very messy class holds the keyboard widget.  The mess is the docked window support which is disable because of numerous metacity bugs."""
    def __init__(self,sok):#
        gtk.Window.__init__(self)
        self.keyboard = None
        #self.add(self.keyboard)
        self.sok = sok
        self.connect("destroy", gtk.main_quit)
        self.connect("configure-event", self.cb_save_position_and_size)
        self.set_accept_focus(False)
        self.grab_remove()
        self.set_keep_above(True)

        #self.set_default_size(self.get_screen().get_monitor_geometry(0).width,300)
        x = self.sok.gconfClient.get_int("/apps/onboard/width")
        y = self.sok.gconfClient.get_int("/apps/onboard/height")
        
        if x and y:
            self.set_default_size(x,y)
        else:
            self.set_default_size(800,300)

        #self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DOCK)
    
    
    def set_keyboard(self, keyboard):
        if self.keyboard:
            self.remove(self.keyboard)
        self.keyboard = keyboard
        self.add(self.keyboard)
        self.keyboard.show()
        self.queue_draw()

    def do_set_layout(self, client, cxion_id, entry, user_data):
        return

    def do_set_size(self, client, cxion_id, entry, user_data): 
    
        self.set_default_size(self.sok.gconfClient.get_int("/apps/onboard/width"),
                    self.sok.gconfClient.get_int("/apps/onboard/height"))


    def cb_save_position_and_size(self, event, user_data):
        """
        Callback that is called when onboard receives a configure-event
        because of a change of its position or size.
        The callback stores the new values to the correspondent gconf
        keys.
        """
        currentPosition = self.get_position()
        currentSize = self.get_size()
        self.sok.gconfClient.set_int("/apps/onboard/horizontal_position", currentPosition[0])
        self.sok.gconfClient.set_int("/apps/onboard/vertical_position", currentPosition[1])
        self.sok.gconfClient.set_int("/apps/onboard/width", currentSize[0])
        self.sok.gconfClient.set_int("/apps/onboard/height", currentSize[1])



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
