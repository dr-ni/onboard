#!/bin/sh
# Description:
# This script sets up a temporary local APT repository for the Onboard packages.
# The script searches for the required deb packages in one of the following locations:
#   - The directory provided as the first parameter ($1)
#   - The current working directory
#   - The directory where the script is located
#   - A ".build/debs" subdirectory (relative to either the script's location or the current working directory)
# After locating the packages, it configures the local repository, updates the package index,
# and installs the necessary Onboard packages (onboard, onboard-data, and if GNOME Shell is present,
# gnome-shell-extension-onboard). Once installation is complete, the temporary repository configuration is removed.
#
# Author: Lukas Gottschall
#
# Note: This script must be executed as root.

# Get the absolute path of the script's directory
SCRIPT_PATH="$(
    cd -- "$(dirname "$0")" >/dev/null 2>&1
    pwd -P
)"

# Function to provide a list of directories to check
check_directories() {
    echo "$DEB_DIR"
    echo "$SCRIPT_PATH"
    echo "$(pwd)"
    echo "$SCRIPT_PATH/build/debs"
    echo "$(pwd)/build/debs"
}

# Check if the script is run as root
if [ "$(id -u)" = "0" ]; then
    # Set the default directory
    DEB_DIR="${1:-$SCRIPT_PATH}"

    # Search for the file
    DEB_FOUND=false
    for dir in $(check_directories); do
        if find "$dir" -maxdepth 1 -name "onboard-common_*_all.deb" | grep -q .; then
            DEB_DIR="$dir"
            DEB_FOUND=true
            break
        fi
    done

    # Check if the file was found
    if [ "$DEB_FOUND" = false ]; then
        echo "Error: Unable to find onboard debs. Please run $0 /path/to/onboard/debs"
        exit 1
    fi

    echo "Onboard debs found in: $DEB_DIR"

    # Configure a local APT repository
    echo "deb [trusted=yes] file:$DEB_DIR/ ./" >/etc/apt/sources.list.d/onboardlocalrepo.list

    # Update package index for the temporary local repository
    apt-get update -o Dir::Etc::sourcelist="/etc/apt/sources.list.d/onboardlocalrepo.list"

    # Install the Onboard packages
    if which gnome-shell >/dev/null 2>&1; then
    	echo "GNOME Shell is installed."
        apt-get -y install onboard onboard-data gnome-shell-extension-onboard
    else
	echo "GNOME Shell is not installed."
        apt-get -y install onboard onboard-data
    fi

    # Remove the temporary local repository configuration
    rm /etc/apt/sources.list.d/onboardlocalrepo.list
else
    while ! sudo -n true 2>/dev/null; do
        echo "This script requires sudo privileges."
        if ! sudo -v; then
            echo "Please provide your password to continue."
        fi
    done
    sudo "$0" "$@"
fi
