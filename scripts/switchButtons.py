import gconf

def run():
	gconfClient = gconf.client_get_default()
	b = gconfClient.get_bool("/desktop/gnome/peripherals/mouse/left_handed")
	gconfClient.set_bool("/desktop/gnome/peripherals/mouse/left_handed", not b)
