#!/usr/bin/env python3
import os
import sys
import subprocess
import re

# Define the default configuration
DEFAULT_OVERRIDE = """[org.onboard]
layout='Compact'
theme='Nightshade'
key-label-font='{font}'
key-label-overrides=['RWIN::super-group', 'LWIN::super-group']
xembed-onboard=true

[org.onboard.window]
docking-enabled=true
force-to-top=true
"""

# List of preferred fallback fonts
FALLBACK_FONTS = ["Ubuntu", "Noto Sans", "Sans", "Arial", "DejaVu Sans", "Liberation Sans"]

def run_command(command):
    """Helper function to execute shell commands and return output."""
    try:
        output = subprocess.check_output(command, universal_newlines=True).strip()
        return output if output else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def get_desktop_environment():
    """Detects the current desktop environment."""
    return os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

def get_default_font():
    """Detects the default system font based on the desktop environment."""
    desktop_env = get_desktop_environment()

    if "xfce" in desktop_env:
        print("Detected XFCE environment. Using xfconf-query...")
        font = run_command(["xfconf-query", "-c", "xsettings", "-p", "/Gtk/FontName"])
    elif any(env in desktop_env for env in ["gnome", "cinnamon", "mate", "unity"]):
        print("Detected GNOME-based environment. Using gsettings...")
        font = run_command(["gsettings", "get", "org.gnome.desktop.interface", "font-name"])
        if font:
            font = font.strip("'")  # Remove single quotes added by gsettings
    else:
        print("Unknown environment. Falling back to available system fonts.")
        font = None
    if font:
        # Remove surrounding single quotes (gsettings output is quoted)
        font = font.strip("'")

        # Extract only the font family (removes numeric font size at the end)
        font = re.sub(r"\s+\d+$", "", font)  # Removes last number if present

    return font if font else None

def find_available_font():
    """Find the best available font using `fc-list`."""
    try:
        # Get the list of installed fonts
        output = subprocess.check_output(["fc-list"], universal_newlines=True)
        available_fonts = set()

        # Extract font family names from `fc-list` output
        for line in output.splitlines():
            parts = line.split(":")
            if len(parts) > 1:
                font_name = parts[1].strip().split(",")[0]  # Get the first font name
                available_fonts.add(font_name)

        # Try to find a preferred font
        for font in FALLBACK_FONTS:
            if font in available_fonts:
                print("Using preferred available font: {}".format(font))
                return font

        # Use the first detected font if no preferred fonts are found
        if available_fonts:
            first_font = next(iter(available_fonts))
            print("Using first detected system font: {}".format(first_font))
            return first_font

    except subprocess.CalledProcessError:
        print("Error: `fc-list` command failed.")
    except FileNotFoundError:
        print("Error: `fc-list` not found. Is fontconfig installed?")

    return "Sans"  # Hardcoded fallback if font detection fails

def generate_gschema_override(schema_file):
    """ Generate the .gschema.override file dynamically. """
    
    selected_font = get_default_font()
    if not selected_font:
        selected_font = find_available_font()

    print("Detected font: {}".format(selected_font))
    
    override_content = DEFAULT_OVERRIDE.format(font=selected_font)

    # Write the override file
    with open(schema_file, "w") as f:
        f.write(override_content)

    print("Generated GSettings override file: {}".format(schema_file))

if __name__ == "__main__":
    # Read schema directory from command-line argument
    if len(sys.argv) != 2:
        print("Usage: {} <schema-file>".format(sys.argv[0]))
        sys.exit(1)

    schema_file = sys.argv[1]
    generate_gschema_override(schema_file)
