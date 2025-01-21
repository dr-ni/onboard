#!/bin/sh

# Description:
# This script sets up a temporary local APT repository for the Onboard packages
# located in the "onboard" subdirectory of the script's location.
# It configures the local repository, updates the package index, and installs the
# necessary Onboard packages (onboard, onboard-data, gnome-shell-extension-onboard).
# After installation, the temporary repository configuration is removed.

# Note: This script must be executed as root.

# Get the absolute path of the script's directory
SCRIPT_PATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

# Check if the script is run as root
if [ "$(id -u)" = "0" ]; then
    # Configure a local APT repository
    echo "deb [trusted=yes] file:$SCRIPT_PATH/ ./" > /etc/apt/sources.list.d/onboardlocalrepo.list

    # Update package index for the temporary local repository
    apt-get update -o Dir::Etc::sourcelist="/etc/apt/sources.list.d/onboardlocalrepo.list"

    # Install the Onboard packages
    apt-get -y install onboard onboard-data gnome-shell-extension-onboard

    # Remove the temporary local repository configuration
    rm /etc/apt/sources.list.d/onboardlocalrepo.list
else
    while ! sudo -n true 2>/dev/null; do
        echo "This script requires sudo privileges."
        if ! sudo -v; then
            echo "Please provide your password to continue."
        fi
    done
    sudo "$0"
fi