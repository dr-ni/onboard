# Onboard 1.4.2

![onb](https://github.com/dr-ni/onboard/blob/main/onboard.png)

## Description

Onboard is an onscreen keyboard useful for everybody that cannot use a
hardware keyboard; for example TabletPC users or mobility impaired users.
It has been designed with simplicity in mind and can be used right away
without the need of any configuration, as it can read the keyboard layout
from the X server.

Features are:
- Support of custom layouts through the use of xml and svg files.
- Support of custom themes for the appearance through the use of xml files.
- Support of macros to automatically type custom defined texts.
- Support of <modifier>+<mouseclick> combination.
- Toggling mouse buttons to perform right clicks with the left mouse button.
- Control of the hover click feature provided by the system.
- Minimizing the keyboard to the panel, a trayicon, or a floating icon.
- Docking

The parent project sadly seems not to be maintained anymore
(https://launchpad.net/onboard). Old PPA downloads for
Ubuntu-releases can still be found at 
https://launchpad.net/~onboard/+archive/ubuntu/stable

## Building from Source:
Find below short instructions on how to build Onboard straight from this
github repository. If you have improvements to share, get errors or run
into other problems, please let us know. Build instructions for
new distributions are always welcome too.

## Ubuntu:
        sudo apt install git build-essential fakeroot
        sudo apt install dh-python python3-distutils-extra devscripts pkg-config libhunspell-dev
        sudo apt install libgtk-3-dev libxtst-dev libxkbfile-dev libdconf-dev libcanberra-dev
        mkdir onboard_build
        cd onboard_build
        git clone https://github.com/dr-ni/onboard.git

        # build
        cd onboard
        fakeroot debian/rules clean
        fakeroot debian/rules build
        export DEB_HOST_ARCH=$(sed -i 's/oldString/new String/g'); fakeroot debian/rules binary

        # install packages
        cd ..
        sudo dpkg -i onboard_1.4.2*.deb 
        sudo dpkg -i onboard-common_1.4.2_all.deb 
        sudo dpkg -i onboard-data_1.4.2_all.deb
        sudo dpkg -i gnome-shell-extension-onboard_1.4.2_all.deb

## Arch Linux:
        pacman -S base-devel git python-distutils-extra dconf gtk3 \
        libcanberra hunspell python-gobject gsettings-desktop-schemas \
        iso-codes python-cairo librsvg python-dbus dbus-glib

        git clone https://github.com/dr-ni/onboard
        cd onboard
        python3 setup.py build
        sudo tools/install_gsettings_schema

        # At this point you should be able to start Onboard
        # from the project directory with
        ./onboard

        # If everything works as expected, install with
        sudo python3 setup.py install

        # And if necessary, uninstall with
        sudo python3 setup.py install --record files.txt
        sudo xargs -a files.txt --delimiter='\n' rm -v
        sudo rm -rf /usr/local/share/onboard

## Mageia:
        urpmi git gcc-c++ lib64zlib-devel python3-distutils-extra \
        libgtk+3.0-devel libxtst-devel libxkbfile-devel libdconf-devel \
        libhunspell-devel libcanberra-devel libpython3-devel intltool

        # more or less optional, but recommended for full functionality
        urpmi mousetweaks lib64atspi-gir2.0 at-spi2-core-qt \
        python3-dbus qtatspi-plugin

        git clone https://github.com/dr-ni/onboard
        cd onboard
        python3 setup.py build
        sudo tools/install_gsettings_schema

        # At this point you should be able to start Onboard
        # from the project directory with
        ./onboard

        # If everything works as expected, install with
        sudo python3 setup.py install

        # And if necessary, uninstall with
        sudo python3 setup.py install --record files.txt
        sudo xargs -a files.txt --delimiter='\n' rm -v
        sudo rm -rf /usr/local/share/onboard
        
## Mousetweaks (optional):
https://github.com/dr-ni/mousetweaks

The mousetweaks package provides mouse accessibility enhancements for the
GNOME desktop. It offers a way to perform clicks without using any physical
mouse buttons (Hover Click).
The package is also available in various package managers. However it is often
not working anymore with onboard. In this case a manual installation from the
source package should help.

## Homepage:
https://github.com/dr-ni/onboard

## Reporting Bugs:
https://github.com/dr-ni/onboard/issues

## License:
This program is released under the terms of the GNU General Public License. Please see the file COPYING for details.
