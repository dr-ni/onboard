#!/usr/bin/python
import os
import sys
import subprocess

def run():
    pid = os.fork() 
    if pid == 0:
        subprocess.call(("python", "-cfrom Onboard.settings import Settings\ns = Settings(False)"))
        os._exit(os.EX_OK)



    
