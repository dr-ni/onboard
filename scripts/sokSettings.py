#!/usr/bin/python
import os
import sys

def run():
    # double fork to prevent zombies
    pid = os.fork() 
    if pid > 0:
        # grand parent
        return

    # first child
    pid = os.fork() 
    if pid > 0:
        # parent
        sys.exit(0)

    # second child
    os.execvp("python", ("python", "-cfrom Onboard.settings import Settings\ns = Settings(False)"))



    
