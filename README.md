# Onboard 1.4.2

![onb](https://github.com/dr-ni/onboard/blob/main/onboard.png)

## Description

Onboard is an onscreen keyboard useful for everybody that cannot use a
hardware keyboard; for example Tablet-PC users or mobility impaired users.
It has been designed with simplicity in mind and can be used right away
without the need of any configuration, as it can read the keyboard layout
from the X server. Onboard is currently not working with wayland - a correct
x11/xorg setup is required.

The parent project at https://launchpad.net/onboard sadly seems not to be
maintained anymore. Old PPA downloads for Ubuntu-releases can still be
found at https://launchpad.net/~onboard/+archive/ubuntu/stable .

## Building from Source
Find below short instructions on how to build Onboard straight from this
github repository. If you have improvements to share, get errors or run
into other problems, please let us know. Build instructions for
new distributions are always welcome too.

### !!! First uninstall ALL onboard and mousetweaks packages !!!

## Ubuntu:
        sudo apt install git build-essential python3-packaging
        sudo apt install dh-python python3-distutils-extra devscripts pkg-config
        sudo apt install libgtk-3-dev libxtst-dev libxkbfile-dev libdconf-dev libcanberra-dev
        sudo apt install libhunspell-dev libudev-dev

        
        # Build
        git clone https://github.com/dr-ni/onboard
        cd onboard
        python3 setup.py clean
        python3 setup.py build
        
        # Install
        sudo tools/install_gsettings_schema
        sudo python3 setup.py install
        
        # Uninstall with python
        sudo python3 setup.py install --record files.txt
        sudo xargs -a files.txt --delimiter='\n' rm -v
        sudo rm -rf /usr/local/share/onboard

## Arch Linux:
        pacman -S base-devel git python-packaging python-distutils-extra dconf gtk3 \
        libcanberra hunspell python-gobject gsettings-desktop-schemas \
        iso-codes python-cairo librsvg python-dbus dbus-glib

        git clone https://github.com/dr-ni/onboard
        cd onboard
        python3 setup.py clean
        python3 setup.py build
        sudo tools/install_gsettings_schema
        # If everything worked without errors, install with
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
        python3 setup.py clean
        python3 setup.py build
        sudo tools/install_gsettings_schema
        # If everything worked without errors, install with
        sudo python3 setup.py install

        # And if necessary, uninstall with
        sudo python3 setup.py install --record files.txt
        sudo xargs -a files.txt --delimiter='\n' rm -v
        sudo rm -rf /usr/local/share/onboard
        
## Mousetweaks (optional package)

The mousetweaks package provides mouse accessibility enhancements for the
GNOME desktop. It offers a way to perform clicks without using any physical
mouse buttons (Hover Click).
The package is also available in various package managers. However, it is often
not working anymore with onboard. In this case a manual installation from https://github.com/dr-ni/mousetweaks should help.

## Homepage
https://github.com/dr-ni/onboard

## Reporting Bugs
https://github.com/dr-ni/onboard/issues

## License
This program is released under the terms of the GNU General Public License. Please see the file COPYING for details.
