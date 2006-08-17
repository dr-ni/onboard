#!/usr/bin/python
import os
def run(sok):
	
	
	pid = os.fork()
	if not pid:
		os.execvp("python", ("python", "settings-dialog.py"))#I suppose your wondering why I did this...
	


