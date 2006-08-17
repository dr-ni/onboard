#!/usr/bin/python
import os
def run():
	
	
	pid = os.fork()
	if not pid:
		os.execvp("python", ("python", "run-settings.py"))#I suppose your wondering why I did this...
	


