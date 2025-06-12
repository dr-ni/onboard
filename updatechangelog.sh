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
BASE=$(echo "$LAST_VERSION" | sed 's/-[0-9]\+$//')
REV=$(echo "$LAST_VERSION" | sed 's/^.*-\([0-9]\+\)$/\1/')

echo "Current version: $LAST_VERSION"
echo "Base: $BASE, Revision: $REV"


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
        NEW_VERSION="${NEW_BASE}-1"
        ;;
    [mM])
        MINOR=$((MINOR + 1))
        PATCH=0
        NEW_BASE="${MAJOR}.${MINOR}.${PATCH}"
        NEW_VERSION="${NEW_BASE}-1"
        ;;
    [pP])
        PATCH=$((PATCH + 1))
        NEW_BASE="${MAJOR}.${MINOR}.${PATCH}"
        NEW_VERSION="${NEW_BASE}-1"
        ;;
    *)
        # Default: increment revision only
        NEW_REV=$((REV + 1))
        NEW_BASE="${BASE}"
        NEW_VERSION="${BASE}-${NEW_REV}"
        ;;
esac

echo "Proposed new version: $NEW_VERSION"
read -p "Is this OK? [Y/n] " confirm
if [[ "$confirm" =~ ^[Nn]$ ]]; then
    echo "Aborted by user."
    exit 1
fi
# Continue with NEW_VERSION
echo "Proceeding with version: $NEW_VERSION"
echo
echo "📦 Please select the debian/changelog target distribution for this release:"
echo "  [u] unstable           (for patch/revision releases)"
echo "  [n] next               (for minor updates)"
echo "  [e] experimental       (for major changes or breakage)"
echo "  [c] rc                 (release candidate)"
echo "  [r] release            (final, production-ready release)"
echo "  [x] UNRELEASED         (default – for in-development state)"
read -p "Choice [x]: " dist_choice

case "$dist_choice" in
    [uU]) DIST="unstable" ;;
    [nN]) DIST="next" ;;
    [eE]) DIST="experimental" ;;
    [cC]) DIST="rc" ;;
    [rR]) DIST="release" ;;
    ""|[xX]) DIST="UNRELEASED" ;;
    *)
        echo "❌ Invalid choice. Aborting."
        exit 1
        ;;
esac

echo "✅ Selected distribution target: $DIST"


# e.g. gbp dch --new-version="$NEW_VERSION" ...

gbp dch --auto --debian-branch=main --new-version="$NEW_VERSION"  --distribution="$DIST"
read -p "📝 Press e to open the changelog in editor... " confirm


if [ "${BASE}" != "$NEW_BASE" ]; then
  echo "Update README.md and setup.py for version ${NEW_BASE}"
  sed -i "1s/^# Onboard [0-9]\+\.[0-9]\+\.[0-9]\+/# Onboard ${NEW_BASE}/" README.md
  sed -i "s/version = '[0-9]\+\.[0-9]\+\.[0-9]\+'/version = '${NEW_BASE}'/" setup.py
fi




if [[ "$confirm" =~ ^[eE]$ ]]; then
  $EDITOR "$CHANGELOG"
fi

if [ "${BASE}" != "$NEW_BASE" ]; then
  # 7. Confirm before commit
  echo
  read -p "Press [Enter] to add & commit the changelog, README.md & setup.py or Ctrl+C to cancel..."
  # 8. Commit
  echo "📤 Committing changelog..."
  git add "$CHANGELOG"
  git add "README.md"
  git add "setup.py"
  git commit -m "Update changelog, README.md & setup.py version: $NEW_VERSION"
else
  # 7. Confirm before commit
  echo
  read -p "Press [Enter] to add & commit the changelog or Ctrl+C to cancel..."
  # 8. Commit
  echo "📤 Committing changelog..."
  git add "$CHANGELOG"
  git commit -m "Update changelog revision: $NEW_VERSION"
fi
read -p "Press [Enter] to push or Ctrl+C to cancel..."

git push

echo "✅ Done: changelog updated and pushed."