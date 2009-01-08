import cluttergtk # must be the first to be imported
import cairo
import clutter
import cluttercairo
import gtk

### Config Singleton ###
from Onboard.Config import Config
config = Config()
########################

EXTRA_PANE_WIDTH  = config.SIDEBARWIDTH    * 4
EXTRA_PANE_HEIGHT = config.keyboard_height / 3

class KeyboardClutter(cluttergtk.Embed):
    def __init__(self):
        cluttergtk.Embed.__init__(self)
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK 
                      | gtk.gdk.BUTTON_RELEASE_MASK 
                      | gtk.gdk.LEAVE_NOTIFY_MASK)

        self.connect("expose_event",         self.expose)
        self.connect("button_press_event",   self.mouse_button_press)
        self.connect("button_release_event", self.mouse_button_release)
        self.connect("leave-notify-event",   self.cb_leave_notify)

        self._base_tex = cluttercairo.CairoTexture(
                width=config.keyboard_width - config.SIDEBARWIDTH * 4,
                height=config.keyboard_height)
        #self._base_tex.set_position(x=(stage.get_width() - 200) / 2,
        #                       y=(stage.get_height() - 200) / 2)

        stage = self.get_stage()
        stage.set_perspective(60, 1.0, 0.1, 100.0)
        stage.set_color(clutter.Color(red=0xbb, green=0xbb, blue=0xbb,
            alpha=0xff))
        stage.add(self._base_tex)
        self._base_tex.show()
        
        # cluttercairo.Texture is also a clutter.Texture, so we can save
        # memory when dealing with multiple copies by simply cloning it
        # and manipulating the clones
        """
        clone_tex = clutter.CloneTexture(self._base_tex)
        clone_tex.set_position((stage.get_width() - 200) / 2,
                               (stage.get_height() - 200) / 2)
        clone_tex.set_rotation(clutter.Y_AXIS, -45.0, center_x, 0, center_z)
        stage.add(clone_tex)
        clone_tex.show()
        """

        center_x = self._base_tex.get_width() / 2
        center_z = self._base_tex.get_height() / 2

        self._other_tex = cluttercairo.CairoTexture(
            width=config.keyboard_width - config.SIDEBARWIDTH * 4,
            height=config.keyboard_height)
        self._other_tex.set_position(stage.get_width() + 400,
                40)
        self._other_tex.set_rotation(clutter.Y_AXIS, -10.0, center_x, 0, 
                center_z)
        stage.add(self._other_tex)
        self._other_tex.set_scale(0.15, 0.15)
        self._other_tex.show()

        self._another_tex = cluttercairo.CairoTexture(
            width=config.keyboard_width - config.SIDEBARWIDTH * 4,
            height=config.keyboard_height)
        self._another_tex.set_position(stage.get_width() + 400,
                2 * stage.get_height() / 3)
        self._another_tex.set_rotation(clutter.Y_AXIS, -10.0, center_x, 0, 
                center_z)
        stage.add(self._another_tex)
        self._another_tex.set_scale(0.15, 0.15)
        self._another_tex.show()

        stage.show()

    def cb_leave_notify(self, widget, grabbed):
        """ 
        horrible.  Grabs pointer when key is pressed, released when cursor 
        leaves keyboard
        """

        gtk.gdk.pointer_ungrab() 
        if self.active:
                    
            if self.scanningActive:
                self.active = None      
                self.scanningActive = None
            else:       
                self.release_key(self.active)
            self.queue_draw()
        return True

    def mouse_button_release(self,widget,event):
        if self.active:
            #self.active.on = False
            self.release_key(self.active)
            if len(self.stuck) > 0:
                for stick in self.stuck:
                    self.release_key(stick)
                self.stuck = []
            self.active = None

        self.queue_draw()
        return True

    def mouse_button_press(self,widget,event):
        gtk.gdk.pointer_grab(self.window, True)
        if event.type == gtk.gdk.BUTTON_PRESS:
            self.active = None#is this doing anything
            
            if config.scanning and self.basePane.columns:
                
                if self.scanningTimeId:
                    if not self.scanningNoY == None:
                        self.press_key(self.scanningActive)
                        gobject.source_remove(self.scanningTimeId)
                        self.reset_scan()
                    else:
                        self.scanningNoY = -1
                        gobject.source_remove(self.scanningTimeId)
                        self.scanningTimeId = gobject.timeout_add(
                                config.scanning_interval, self.scan_tick)
                else:   
                    self.scanningTimeId = gobject.timeout_add(
                        config.scanning_interval, self.scan_tick)
                    self.scanningNoX = -1
            else:
                if self.activePane:
                    for key in self.activePane.keys.values():
                        self.is_key_pressed(key, widget, event)
                else:   
                    for key in self.basePane.keys.values():
                        self.is_key_pressed(key, widget, event)

                #for key in self.tabKeys:
                #    self.is_key_pressed(key, widget, event)
                
                actor = self.get_stage().get_actor_at_pos(int(event.x),
                        int(event.y))
                if actor.__class__ == cluttercairo.CairoTexture:
                    center_x = self._base_tex.get_width() / 2
                    center_z = self._base_tex.get_height() / 2
                    actor.set_rotation(clutter.Y_AXIS, 15.0, 
                            center_x, 0, center_z)


        return True 

    @staticmethod
    def clear_context(context):
        # Clear our surface
        context.save()
        context.set_operator (cairo.OPERATOR_CLEAR)
        context.paint()
        context.restore()

    def draw_pane(self, context, pane, width, height):
        self.kbwidth = width
        self.height  = height

        context.set_line_width(1.1)

        self.clear_context(context)

        context.set_source_rgba(float(pane.rgba[0]),
                    float(pane.rgba[1]),
                    float(pane.rgba[2]),
                    float(pane.rgba[3]))#get from .sok
        context.paint()

        pane.paint(context, width, height)

        del(context) # we need to destroy the context so that the
                     # texture gets properly updated with the result
                     # of our operations; you can either move all the
                     # drawing operations into their own function and
                     # let the context go out of scope or you can
                     # explicitly destroy it

    def expose(self, widget, event):
        context = self._base_tex.cairo_create()
        size = self.get_allocation()
        self.draw_pane(context, self.basePane, 
            size.width - config.SIDEBARWIDTH * 4,
            size.height
        )

        context = self._other_tex.cairo_create()
        self.draw_pane(context, self.panes[0],
            size.width - config.SIDEBARWIDTH * 4,
            size.height)

        context = self._another_tex.cairo_create()
        self.draw_pane(context, self.panes[1],
            size.width - config.SIDEBARWIDTH * 4,
            size.height)

        return True
