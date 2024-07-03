# Onboard 1.4.2

![onb](https://github.com/dr-ni/onboard/blob/main/onboard.png)

## Description

Onboard is an onscreen keyboard useful for everybody that cannot use a
hardware keyboard; for example Tablet-PC users or mobility impaired users.
It has been designed with simplicity in mind and can be used right away
without the need of any configuration, as it can read the keyboard layout
from the X server. Onboard is currently not working with wayland - a correct
X11/Xorg setup is required.

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
        # Uninstall
        sudo apt purge onboard onboard-common onboard-data
        sudo apt purge mousetweaks

        # Install dependencies
        sudo apt install git build-essential python3-packaging python3-dev
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

        # Fix settings
        onboard-settings
        # select Keyboard → Advanced → Input Options
        # change Input event source from Xinput to GTK
        # change Key-stroke-generator to AT-SPI

        # Change keyboard language layout
        # setxkbmap -layout de
        # or [us|in|ru|...]
        
        # Uninstall
        sudo python3 setup.py install --record files.txt
        sudo xargs -a files.txt --delimiter='\n' rm -v
        sudo rm -rf /usr/local/share/onboard
        sudo rm -rf /usr/local/lib/python3.*/dist-packages/onboard-1.4.*.egg-info/
        sudo rm files.txt

## Arch Linux:
        # Uninstall
        sudo pacman -S mousetweaks
        sudo pacman -S onboard
        
        # Install dependencies
        pacman -S base-devel git python-packaging python-distutils-extra dconf gtk3 \
        libcanberra hunspell python-gobject gsettings-desktop-schemas \
        iso-codes python-cairo librsvg python-dbus dbus-glib

        # Build
        git clone https://github.com/dr-ni/onboard
        cd onboard
        python3 setup.py clean
        python3 setup.py build
        
        # Install
        sudo tools/install_gsettings_schema
        sudo python3 setup.py install
        
        # Fix settings
        onboard-settings
        # select Keyboard → Advanced → Input Options
        # change Input event source from Xinput to GTK
        
        # Uninstall
        sudo python3 setup.py install --record files.txt
        sudo xargs -a files.txt --delimiter='\n' rm -v
        sudo rm -rf /usr/local/share/onboard
        sudo rm -rf /usr/local/lib/python3.*/dist-packages/onboard-1.4.*.egg-info/
        sudo rm files.txt

## Mageia:
        # Install dependencies
        urpmi git gcc-c++ lib64zlib-devel python3-distutils-extra
        urpmi libgtk+3.0-devel libxtst-devel libxkbfile-devel libdconf-devel
        urpmi libhunspell-devel libcanberra-devel libpython3-devel intltool
        # more or less optional, but recommended for full functionality
        urpmi lib64atspi-gir2.0 at-spi2-core-qt python3-dbus qtatspi-plugin

        # Build
        git clone https://github.com/dr-ni/onboard
        cd onboard
        python3 setup.py clean
        python3 setup.py build
        
        # Install
        sudo tools/install_gsettings_schema
        sudo python3 setup.py install

        # Fix settings
        onboard-settings
        # select Keyboard → Advanced → Input Options
        # change Input event source from Xinput to GTK
        
        # Uninstall
        sudo python3 setup.py install --record files.txt
        sudo xargs -a files.txt --delimiter='\n' rm -v
        sudo rm -rf /usr/local/share/onboard
        sudo rm -rf /usr/local/lib/python3.*/dist-packages/onboard-1.4.*.egg-info/
        sudo rm files.txt
        
## Manuals

        # Terminal
        man onboard
        
        # Interactive
        yelp "help:onboard"
        xdg-open "help:onboard"

        # Onboard
        # Right click on icon in systray -> Help
        
## DBUS interface

Interface description: [DBUS.md](https://github.com/dr-ni/onboard/blob/main/DBUS.md)

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
