#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright © 2014-2015 marmuta <marmvta@gmail.com>
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

import optparse
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

parser = optparse.OptionParser(
    usage="Usage: %prog [options] [model1 model2 ...]")
parser.add_option(
    "-v", "--verbose",
    action="store_true", dest="verbose", default=False,
    help="Print a few status messages")
parser.add_option("-x", type="int", dest="x", help="Window x position")
parser.add_option("-y", type="int", dest="y", help="Window y position")
parser.add_option(
    "-s", "--size", dest="size", default="800x200",
    help="Window size, widthxheight")
parser.add_option(
    "-t", "--title", dest="title",
    help="Window title")
options, args = parser.parse_args()

verbose = options.verbose
size = [int(val) for val in options.size.split("x")]

window = Gtk.Window()
window.resize(*size)
if options.title:
    window.set_title(options.title)
window.show()
if options.x is not None and \
   options.y is not None:
    window.move(options.x, options.y)

socket = Gtk.Socket()
socket.show()
window.add(socket)

if verbose:
    print("Socket ID=", socket.get_id())
window.connect("destroy", lambda w: Gtk.main_quit())


def plugged_event(widget):
    if verbose:
        print("I (", widget, ") have just had a plug inserted!")


socket.connect("plug-added", plugged_event)

if args:
    socket.add_id(int(args[0]))

Gtk.main()
