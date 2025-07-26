#!/bin/bash
# Get the absolute path of the script's directory
SCRIPT_PATH="$(
    cd -- "$(dirname "$0")" >/dev/null 2>&1
    pwd -P
)"
set -e
python3 setup.py build_i18n

echo "Updating all .po files in po/ using po/onboard.pot..."

for f in po/*.po; do
    echo "Checking $f"
    msgmerge --update --quiet --backup=none "$f" po/onboard.pot && echo "✔️  $f updated"
done

echo "All .po files updated."
