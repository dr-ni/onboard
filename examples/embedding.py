#!/usr/bin/python3

# Copyright © 2013, marmuta
#
# This file is part of Onboard.
#
# Onboard is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Onboard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


import subprocess

from gi.repository import Gtk


class KeyboardEntry(Gtk.Window):
    """ Form with embedded keyboard. """

    def __init__(self):
        super(KeyboardEntry, self).__init__()

        self._value = ""

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        entry_box = Gtk.Box()
        self._entry = Gtk.Entry()
        entry_box.pack_start(self._entry, True, True, 1)

        button = Gtk.Button("Done")
        button.connect("clicked", self._on_done_clicked)
        entry_box.pack_start(button, False, False, 1)
        box.pack_start(entry_box, False, False, 1)

        socket = Gtk.Socket()
        box.pack_end(socket, True, True, 1)

        self.resize(800, 220)
        self.add(box)
        self.connect("destroy", self._quit)

        xid = self._start_onboard()
        socket.add_id(xid)

    def get_value(self):
        return self._value

    def _quit(self, widget=None):
         Gtk.main_quit()
         self._onboard.terminate()

    def _on_done_clicked(self, widget):
        """docstring for _on_done_clicked"""
        self._value = self._entry.get_text()
        self._quit()

    def _start_onboard(self):
        """ Start Onboard and return the xid of the keyboard plug. """

        self._onboard = None
        xid = 0
        try:
            self._onboard = subprocess.Popen(["onboard", "--xid",
                                              "-l", "Compact"],
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       close_fds=True)
            line = self._onboard.stdout.readline()
            xid = int(line)
        except OSError as e:
            _logger.error(_format("Failed to execute '{}', {}", \
                            " ".join(args), e))

        return xid


entry = KeyboardEntry()
entry.show_all()

Gtk.main()

print("KeyboardEntry returned", repr(entry.get_value()))


