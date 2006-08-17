import gconf



def run(sok):
	gconfClient = gconf.client_get_default()
	print "switch"
	b = gconfClient.get_bool("/desktop/gnome/peripherals/mouse/left_handed")
	gconfClient.set_bool("/desktop/gnome/peripherals/mouse/left_handed", not b)
