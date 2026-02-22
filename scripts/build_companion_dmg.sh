#!/usr/bin/env bash
# Build the HomeClaw Companion app for macOS and create a single DMG file.
# Usage: ./scripts/build_companion_dmg.sh [--output /path/to/Companion.dmg]
# Default output: clients/homeclaw_companion/homeclaw_companion.dmg

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPANION_DIR="$REPO_ROOT/clients/homeclaw_companion"
OUTPUT_DMG=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --output)
      OUTPUT_DMG="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--output /path/to/Companion.dmg]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$OUTPUT_DMG" ]]; then
  OUTPUT_DMG="$COMPANION_DIR/homeclaw_companion.dmg"
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script builds a macOS DMG; run it on macOS." >&2
  exit 1
fi

echo "Building Companion app (macOS release)..."
cd "$COMPANION_DIR"
flutter pub get
flutter build macos --release

APP_PATH="$COMPANION_DIR/build/macos/Build/Products/Release/homeclaw_companion.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Build did not produce $APP_PATH" >&2
  exit 1
fi

echo "Creating DMG..."
DMG_DIR=$(mktemp -d)
cp -R "$APP_PATH" "$DMG_DIR/"
ln -s /Applications "$DMG_DIR/Applications"

# Create DMG (may need full disk access for hdiutil on some systems)
hdiutil create -volname "HomeClaw Companion" -srcfolder "$DMG_DIR" -ov -format UDZO "$OUTPUT_DMG"
rm -rf "$DMG_DIR"

echo "Done. DMG: $OUTPUT_DMG"
ls -la "$OUTPUT_DMG"
