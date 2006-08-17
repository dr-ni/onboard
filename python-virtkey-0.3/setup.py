#!/usr/bin/python

from distutils.core import setup, Extension
setup(name="virtkey",
      ext_modules=[Extension("virtkey", 
		["python-virtkey.c","ucs2keysym.c"],
		libraries=["X11","Xtst"]
		)],
	version="0.01"
      )
