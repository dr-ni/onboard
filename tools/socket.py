#!/usr/bin/python

import string
import optparse

import pygtk
pygtk.require('2.0')
import gtk,sys

parser = optparse.OptionParser(usage=
            "Usage: %prog [options] [model1 model2 ...]")
parser.add_option("-v", "--verbose",
            action="store_true", dest="verbose", default=False,
            help="Print a few status messages")
parser.add_option("-x", type="int", dest="x", help="Window x position")
parser.add_option("-y", type="int", dest="y", help="Window y position")
parser.add_option("-s", "--size", dest="size", default="800x200",
        help="Window size, widthxheight")
parser.add_option("-t", "--title", dest="title",
        help="Window title")
options, args = parser.parse_args()

verbose = options.verbose
size = [int(val) for val in options.size.split("x")]

window = gtk.Window()
window.resize(*size)
if options.title:
    window.set_title(options.title)
window.show()
if not options.x is None and \
   not options.y is None:
    window.move(options.x, options.y)

socket = gtk.Socket()
socket.show()
window.add(socket)

if verbose:
    print "Socket ID=", socket.get_id()
window.connect("destroy", lambda w: gtk.main_quit())

def plugged_event(widget):
    if verbose:
        print "I (", widget, ") have just had a plug inserted!"

socket.connect("plug-added", plugged_event)

if args:
    socket.add_id(long(args[0]))

gtk.main()
