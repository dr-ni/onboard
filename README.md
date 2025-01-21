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
        
## Build and Install Debian Packages

To build Debian packages from the source, two scripts are available:
- `build_debs.sh`: Creates the `.deb` packages and related metadata.
- `install_debs_with_local_repo.sh`: Sets up a local repository and installs the packages on a target system.

---

### Notes
- Both scripts automatically use `sudo` to install dependencies or packages.
- Ensure you have `sudo` privileges and be ready to enter your password when prompted during execution.

---

### Build Debian Packages

The `build_debs.sh` script automates building `.deb` packages and associated metadata in the **parent directory**.

#### Steps:

1. **For Current Releases**:
   - Ensure you are in the Onboard source directory and execute the following commands:
     ```bash
     chmod +x build_debs.sh
     ./build_debs.sh
     ```

2. **For Older Releases**:
   - If the `build_debs.sh` script is missing, copy it into the source directory and run:
     ```bash
     cp /path/to/build_debs.sh /path/to/onboard_sources/
     cd /path/to/onboard_sources/
     chmod +x build_debs.sh
     ./build_debs.sh
     ```

The Debian packages will be saved in the directory: `/path/to/onboard_sources/build/debs` 

---

### Install the Debian Packages

The `install_debs_with_local_repo.sh` script simplifies installing the generated `.deb` packages using a local repository.

#### Steps:
1. **Prepare Files**:
   - Copy the following to a directory on the target system:
     - All `.deb` files.
     - The `Packages.gz` file.
     - The `install_debs_with_local_repo.sh` script.

2. **Run the Script**:
   - Navigate to the directory and execute:
     ```bash
     chmod +x install_debs_with_local_repo.sh
     ./install_debs_with_local_repo.sh
     ```
        
## D-Bus interface

The Onboard D-Bus interface allows communication between Onboard and other processes running concurrently on the Linux desktop.

Here the Interface description:
[DBUS.md](https://github.com/dr-ni/onboard/blob/main/DBUS.md)

## Mousetweaks

This optional package provides mouse accessibility enhancements for the GNOME desktop.
It offers a way to perform clicks without using any physical mouse buttons (Hover Click).
The package is also available in various package managers. However, it is often
not working anymore with onboard. In this case a manual installation from https://github.com/dr-ni/mousetweaks should help.

## Homepage
https://github.com/dr-ni/onboard

## Reporting Bugs
https://github.com/dr-ni/onboard/issues

## License
This program is released under the terms of the GNU General Public License. Please see the file COPYING for details.
