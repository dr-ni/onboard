#!/usr/bin/python

from distutils.core import setup, Extension
setup(name="virtkey",
      ext_modules=[Extension("virtkey", 
		["python-virtkey.c","ucs2keysym.c"],include_dirs=['/usr/include/gtk-2.0', '/usr/include/glib-2.0', '/usr/lib/glib-2.0/include', '/usr/include/pango-1.0', '/usr/lib/gtk-2.0/include', '/usr/include/cairo'],
		libraries=["X11","Xtst","glib-2.0","gdk-x11-2.0"]
		)],
	version="0.01"
      )
