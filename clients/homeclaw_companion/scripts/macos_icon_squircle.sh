#!/usr/bin/env bash
# Apply Apple-style squircle icon to the macOS app using iconsur.
# Run from clients/homeclaw_companion. Requires: brew install iconsur (or npm i -g iconsur)
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPANION_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$COMPANION_DIR"

CONFIG="${COMPANION_DIR}/macos/Runner/Configs/AppInfo.xcconfig"
if [[ -f "$CONFIG" ]]; then
  PRODUCT_NAME=$(grep PRODUCT_NAME "$CONFIG" | head -1 | sed 's/.*= *//' | tr -d ' ')
else
  PRODUCT_NAME="homeclaw_companion"
fi

BUILD_TYPE="${1:-Release}"
APP_PATH="${COMPANION_DIR}/build/macos/Build/Products/${BUILD_TYPE}/${PRODUCT_NAME}.app"
ICON_PATH="${COMPANION_DIR}/assets/icon/app_icon.png"

if ! command -v iconsur &>/dev/null; then
  echo "Install iconsur first: brew install iconsur   (or: npm i -g iconsur)"
  exit 1
fi

if [[ ! -f "$ICON_PATH" ]]; then
  echo "Icon not found: $ICON_PATH"
  exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "App not found at $APP_PATH"
  echo "Build first: flutter build macos   (or: flutter run -d macos, then use: $0 Debug)"
  exit 1
fi

iconsur set "$APP_PATH" -l -i "$ICON_PATH"
echo "Icon applied. Updating system icon cache (may ask for password)..."
sudo iconsur cache
echo "Done. Open the app from build folder or re-run it to see the new icon."
