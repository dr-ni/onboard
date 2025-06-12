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
  echo "⚠️  Warning: No new commits since last changelog update."
  echo "This is usually fine for a patch or higher-level update."

  while true; do
    read -p "Do you still want to proceed with the changelog update? [y/N] " response
    case "$response" in
      [yY]) 
        echo "Proceeding despite no new commits."
        break
        ;;
      [nN]|"") 
        echo "Skipping changelog update."
        exit 0
        ;;
      *) 
        echo "Please answer yes [y] or no [n]."
        ;;
    esac
  done
fi

# --- Get the current version from changelog ---
LAST_VERSION=$(dpkg-parsechangelog -S Version)

# Extract upstream part (without the -revision)
UPSTREAM="${LAST_VERSION%-*}"
REV="${LAST_VERSION##*-}"

# Detect if it's an RC version like 1.4.4~rc2
if [[ "$UPSTREAM" =~ ^([0-9.]+)~rc([0-9]+)$ ]]; then
    BASE="${BASH_REMATCH[1]}"
    RC="${BASH_REMATCH[2]}"
else
    BASE="$UPSTREAM"
    RC=""
fi

echo "Current version: $LAST_VERSION"
echo "Base: $BASE, Revision: $REV"
if [[ -n "$RC" ]]; then
    echo "RC: $RC"
fi

# --- Ask user what to increment ---
echo "Which part of the version would you like to increment?"
echo "  [b] base (major)"
echo "  [m] minor"
echo "  [p] patch"
echo "  [r] revision (default)"
read -p "Choice [r]: " choice

# Split BASE into major.minor.patch
IFS='.' read -r MAJOR MINOR PATCH <<< "$BASE"

case "$choice" in
    [bB])
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        NEW_BASE="${MAJOR}.${MINOR}.${PATCH}"
        NEW_REV=1
        ;;
    [mM])
        MINOR=$((MINOR + 1))
        PATCH=0
        NEW_BASE="${MAJOR}.${MINOR}.${PATCH}"
        NEW_REV=1
        ;;
    [pP])
        PATCH=$((PATCH + 1))
        NEW_BASE="${MAJOR}.${MINOR}.${PATCH}"
        NEW_REV=1
        ;;
    *)
        NEW_REV=$((REV + 1))
        NEW_BASE="${BASE}"
        ;;
esac

NEW_VERSION="${NEW_BASE}-${NEW_REV}"

NEXT_RC=1
if [[ -n "$RC" ]]; then
    NEXT_RC=$((RC + 1))
fi

echo
echo "🍞 Please select the debian/changelog target distribution for this release:"
echo "  [u] unstable           – for patch/revision releases"
echo "                          → setup.py: ${NEW_BASE}.dev${NEW_REV}"
echo "  [n] next               – for minor updates"
echo "                          → setup.py: ${NEW_BASE}.dev${NEW_REV}"
echo "  [e] experimental       – for major changes or breakage"
echo "                          → setup.py: ${NEW_BASE}.dev${NEW_REV}"
echo "  [c] rc                 – release candidate"
echo "                          → setup.py: ${NEW_BASE}rc${NEXT_RC}[.dev${NEW_REV}]"
echo "  [r] release            – final, production-ready release"
echo "                          → setup.py: ${NEW_BASE}"
echo "  [x] UNRELEASED         – in-development state for revision releases (default)"
echo "                          → setup.py: ${NEW_BASE}.post${NEW_REV}"

read -p "Choice [x]: " dist_choice

case "$dist_choice" in
    [uU])
        DIST="unstable"
        SETUP_SUFFIX=".dev${NEW_REV}"
        ;;
    [nN])
        DIST="next"
        SETUP_SUFFIX=".dev${NEW_REV}"
        ;;
    [eE])
        DIST="experimental"
        SETUP_SUFFIX=".dev${NEW_REV}"
        ;;
    [cC])
        DIST="rc"
        RC_NUMBER=$NEXT_RC
        echo
        read -p "🔧 Add development suffix ('rc${RC_NUMBER}.dev${NEW_REV}')? [y/N]: " ADD_DEV
        if [[ "$ADD_DEV" =~ ^[yY]$ ]]; then
            SETUP_SUFFIX="rc${RC_NUMBER}.dev${NEW_REV}"
        else
            SETUP_SUFFIX="rc${RC_NUMBER}"
        fi
        NEW_VERSION="${NEW_BASE}~rc${RC_NUMBER}-${NEW_REV}"
        ;;
    [rR])
        DIST="release"
        SETUP_SUFFIX=""
        ;;
    ""|[xX])
        DIST="UNRELEASED"
        SETUP_SUFFIX=".post${NEW_REV}"
        ;;
    *)
        echo "❌ Invalid choice. Aborting."
        exit 1
        ;;
esac

echo
echo "✅ Selected changelog distribution: $DIST"
echo "✅ Corresponding setup.py suffix:   $SETUP_SUFFIX"
echo "Proposed new version: $NEW_VERSION"
read -p "Is this OK? [Y/n] " confirm
if [[ "$confirm" =~ ^[Nn]$ ]]; then
    echo "Aborted by user."
    exit 1
fi

echo "Proceeding with version: $NEW_VERSION"

yes | gbp dch --auto --debian-branch=main --new-version="$NEW_VERSION" --distribution="$DIST"
echo
echo "Edit changelog?"
read -p "📝 Press e to open the changelog in editor... " confirm
if [[ "$confirm" =~ ^[eE]$ ]]; then
  $EDITOR "$CHANGELOG"
fi

echo "Update README.md version ${NEW_VERSION}"
sed -i "1s/^# Onboard [0-9]\+\.[0-9]\+\.[0-9]\+.*$/# Onboard ${NEW_VERSION}/" README.md
echo "Update setup.py version: ${NEW_BASE}${SETUP_SUFFIX}"
sed -i "s/^version = '[0-9a-zA-Z_.-]\+'/version = '${NEW_BASE}${SETUP_SUFFIX}'/" setup.py

echo
read -p "Press [Enter] to add & commit the changelog, README.md & setup.py or Ctrl+C to cancel..."
echo "📤 Committing changelog, README.md & setup.py..."
git add "$CHANGELOG" README.md setup.py

if [ "${BASE}" != "$NEW_BASE" ]; then
  git commit -m "Update version: $NEW_VERSION"
else
  git commit -m "Update changelog revision: $NEW_VERSION"
fi

read -p "Press [Enter] to push or Ctrl+C to cancel..."
git push

echo "✅ Done: changelog updated and pushed."
