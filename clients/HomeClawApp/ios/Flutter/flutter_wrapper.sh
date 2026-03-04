#!/bin/sh
# Find FLUTTER_ROOT and run xcode_backend.sh. Used by Xcode Run Script / Thin Binary phases.
# Xcode often has minimal PATH, so we try: Generated.xcconfig, FLUTTER_ROOT env, login PATH, common paths.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# SRCROOT = ios directory (parent of Flutter); Xcode sets it when running the script
SRCROOT="${SRCROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
GENERATED="${SRCROOT}/Flutter/Generated.xcconfig"

# 1. From Generated.xcconfig (created by "flutter pub get")
if [ -f "$GENERATED" ]; then
  FLUTTER_ROOT="$(grep -E "^FLUTTER_ROOT=" "$GENERATED" | head -1 | sed 's/^FLUTTER_ROOT=//')"
fi

# 2. From environment (Xcode: Edit Scheme → Run → Arguments → Environment Variables)
if [ -n "$FLUTTER_ROOT" ] && [ ! -f "$FLUTTER_ROOT/packages/flutter_tools/bin/xcode_backend.sh" ]; then
  FLUTTER_ROOT=""
fi

# 3. Login shell PATH (so Terminal's flutter is found when Xcode builds)
if [ -z "$FLUTTER_ROOT" ]; then
  FLUTTER_BIN="$(bash -l -c 'which flutter 2>/dev/null' 2>/dev/null)"
  if [ -n "$FLUTTER_BIN" ]; then
    FLUTTER_ROOT="$(cd "$(dirname "$FLUTTER_BIN")/.." && pwd)"
  fi
fi

# 4. Common install locations
if [ -z "$FLUTTER_ROOT" ] && [ -n "$HOME" ]; then
  for candidate in "$HOME/flutter" "$HOME/development/flutter" "$HOME/Development/flutter"; do
    if [ -d "$candidate" ] && [ -f "$candidate/bin/flutter" ]; then
      FLUTTER_ROOT="$candidate"
      break
    fi
  done
fi

BACKEND="$FLUTTER_ROOT/packages/flutter_tools/bin/xcode_backend.sh"
if [ -z "$FLUTTER_ROOT" ] || [ ! -f "$BACKEND" ]; then
  echo "error: Could not find Flutter SDK." >&2
  echo "  Run in Terminal: cd clients/HomeClawApp && flutter pub get && cd ios && pod install" >&2
  echo "  Or set FLUTTER_ROOT in Xcode: Edit Scheme → Run → Arguments → Environment Variables." >&2
  exit 1
fi

exec /bin/sh "$BACKEND" "$@"
