#!/bin/bash
set -e

ENV_FILE=".env.debian.maintainer"
EDITOR="${EDITOR:-nano}"  # Use default editor or fallback to nano
CHANGELOG="debian/changelog"


# Default values for initial .env file
DEFAULT_NAME="Uwe Niethammer"
DEFAULT_EMAIL="uwe@dr-niethammer.de"

# --- Check if gbp (git-buildpackage) is installed ---
if ! command -v gbp &> /dev/null; then
  sudo apt install git-buildpackage
fi

# --- Check if gbp (git-buildpackage) is installed ---
if ! command -v gbp &> /dev/null; then
  echo "❌ Error: git-buildpackage (gbp) is not installed."
  echo "You can install it using: sudo apt install git-buildpackage"
  exit 1
fi

# --- Create .env file if missing ---
if [ ! -f "$ENV_FILE" ]; then
  echo "⚠️  $ENV_FILE not found — creating it..."
  cat > "$ENV_FILE" <<EOF
# Maintainer environment for Debian packaging
DEBFULLNAME="$DEFAULT_NAME"
DEBEMAIL="$DEFAULT_EMAIL"
EOF
  echo "✅  Created $ENV_FILE with default maintainer info."
fi

# --- Load the .env file ---
source "$ENV_FILE"

# --- Export to environment so gbp/dch can see them ---
export DEBFULLNAME
export DEBEMAIL

# --- Validate variables ---
if [ -z "$DEBFULLNAME" ] || [ -z "$DEBEMAIL" ]; then
  echo "❌ Error: DEBFULLNAME or DEBEMAIL not set in $ENV_FILE"
  exit 1
fi

# --- Confirm identity ---
echo "🔧 Using maintainer identity: $DEBFULLNAME <$DEBEMAIL>"


# Get last commit that modified debian/changelog
LAST_CHANGELOG_COMMIT=$(git log -n1 --pretty=format:%H -- debian/changelog)

# Count new commits since then (in entire repo)
NEW_COMMITS=$(git rev-list --count "${LAST_CHANGELOG_COMMIT}..HEAD")

if [ "$NEW_COMMITS" -eq 0 ]; then
  echo "✅ No new commits since last changelog update — skipping changelog."
  exit 0
fi

# --- Run gbp dch with all passed arguments ---
LAST_VERSION=$(dpkg-parsechangelog -S Version)
BASE=$(echo "$LAST_VERSION" | sed 's/-[0-9]\+$//')
REV=$(echo "$LAST_VERSION" | sed 's/^.*-\([0-9]\+\)$/\1/')
NEW_REV=$((REV + 1))
NEW_VERSION="${BASE}-${NEW_REV}"

echo "New version: $NEW_VERSION"
gbp dch --auto --debian-branch=main --new-version="$NEW_VERSION"

# 6. Open changelog in editor
echo "📝 Opening changelog in editor..."
$EDITOR "$CHANGELOG"

# 7. Confirm before commit & push
echo
read -p "Press [Enter] to commit and push the changelog, or Ctrl+C to cancel..."

# 8. Commit and push
echo "📤 Committing changelog..."
git add "$CHANGELOG"
git commit -m "Update changelog for version $NEW_VERSION"
git push

echo "✅ Done: changelog updated and pushed."