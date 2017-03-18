#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright © 2017 marmuta <marmvta@gmail.com>
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

# Glade in Zesty doesn't necessarily assign ids to object tags anymore.
# On Xenial and below they are still required, however.
# onboard-settings won't start without them.
# This script adds numbered ids wherever they are missing.

import sys
import re
import optparse
from xml.dom import minidom

parser = optparse.OptionParser(
    usage="Usage: %prog [options] <glade .ui files>")
parser.add_option(
    "-i", "--in-place", action="store_true", dest="in_place",
    help="replace the input file")
options, args = parser.parse_args()

if len(args) < 1:
    parser.print_usage()
    sys.exit(1)

for fn in args:
    ids = set()

    def get_base_id(cls):
        if cls.startswith("Gtk"):
            return cls[3:].lower()
        return None

    def get_free_id(base_id):
        i = 1
        while True:
            id = base_id + str(i)
            if id not in ids:
                return id
            i += 1

    def new_id(cls):
        id = get_free_id(get_base_id(cls))
        ids.add(id)
        return id

    with minidom.parse(fn).documentElement as dom:
        objects = dom.getElementsByTagName("object")

        for o in objects:
            attr = o.attributes.get("id")
            if attr:
                ids.add(attr.value)

    lines = []
    iline = 1
    with open(fn) as f:
        for line in f:
            line = line.rstrip()

            m = re.search('<\s*object\s+(.*)>', line)
            if m:
                attrs = m.groups()[0]

                m = re.search('class\s*=\s*["\'](\w*)["\']', attrs)
                cls = m.groups()[0] if m else None

                m = re.search('id\s*=\s*["\']([^"\']+)["\']', attrs)
                id_ = m.groups()[0] if m else None

                if id_ is None:
                    id_ = new_id(cls)
                    if line.endswith("/>"):
                        line = line[:-2].rstrip()
                        line += ' id="' + id_ + '"/>'
                    elif line.endswith(">"):
                        line = line[:-1].rstrip()
                        line += ' id="' + id_ + '">'
                    else:
                        print("Error parsing line {}: {}"
                              .format(iline, repr(line)), file=sys.stderr)
                        sys.exit(1)

            lines.append(line)
            iline += 1

    if options.in_place:
        with open(fn, "w") as f:
            for line in lines:
                print(line, file=f)
    else:
        for line in lines:
            print(line)



