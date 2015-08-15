#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright © 2013 marmuta <marmvta@gmail.com>
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

import sys
import subprocess

from gi.repository import Gtk


class KeyboardDialog(Gtk.Dialog):
    """ Form with embedded keyboard. """

    def __init__(self):
        super(KeyboardDialog, self).__init__()

        self._value = ""

        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        self.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)

        self.set_default_response(Gtk.ResponseType.OK)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        entry_box = Gtk.Box()
        self._entry = Gtk.Entry()
        self._entry.set_activates_default(True)
        entry_box.pack_start(self._entry, True, True, 1)

        button = Gtk.Button("Enter")
        button.connect("clicked", self._on_done_clicked)
        entry_box.pack_start(button, False, False, 1)
        box.pack_start(entry_box, False, False, 1)

        socket = Gtk.Socket()
        socket.set_size_request(800, 200)
        box.pack_end(socket, True, True, 1)

        self.get_content_area().add(box)

        xid = self._start_onboard()
        socket.add_id(xid)

        self.show_all()

        self.connect("response", self._on_response)

    def get_value(self):
        return self._value

    def _on_response(self, widget, response):
        if response == Gtk.ResponseType.OK:
            self._value = self._entry.get_text()
        self._onboard.terminate()

    def _on_done_clicked(self, widget):
        self._value = self._entry.get_text()
        self.response(Gtk.ResponseType.OK)

    def _start_onboard(self):
        """ Start Onboard and return the xid of the keyboard plug. """

        self._onboard = None
        xid = 0
        args = ["onboard", "--xid",
                "-l", "Compact"]
        try:
            self._onboard = subprocess.Popen(args,
                                             stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE,
                                             close_fds=True)
            line = self._onboard.stdout.readline()
            xid = int(line)
        except OSError as e:
            print("Failed to execute '{}', {}".format(" ".join(args), e),
                  file=sys.stderr)

        return xid


dialog = KeyboardDialog()
if dialog.run() == Gtk.ResponseType.OK:
    print("KeyboardDialog returned", repr(dialog.get_value()))


