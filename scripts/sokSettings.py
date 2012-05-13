#!/usr/bin/python
from gi.repository import GLib

def run():
    GLib.spawn_async(argv=["python",
                           "-cfrom Onboard.settings import Settings\ns = Settings(False)"],
                     flags=GLib.SpawnFlags.SEARCH_PATH)

