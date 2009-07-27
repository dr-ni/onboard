#!/bin/sh
#
#
# Copyright © 2009 Francesco Fumanti <francesco.fumanti@gmx.net>
#
# This script is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#
#
#
# This file is part of Onboard.
#
# This script replaces the .pot-files in the source tree by regenerating
# them from the indicated source files.
#
# onboard.pot.in has to list all the files with the strings for onboard.pot.
# onboard-settings.pot.in has to list all the files with the strings for onboard-settings.pot.
#
# This script should be launched from the po source folder.
#
#
# Update po/onboard/onboard.pot
#
/usr/bin/xgettext -f onboard/onboard.pot.in -p onboard -o onboard.pot 
#
# Update po/onboard-settings/onboard-settings.pot
#
/usr/bin/xgettext -f onboard-settings/onboard-settings.pot.in -p onboard-settings -o onboard-settings.pot 

