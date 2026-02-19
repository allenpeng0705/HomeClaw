#!/usr/bin/env bash
# Bake Apple-style squircle (rounded corners) into macOS app icon assets.
# Run from clients/homeclaw_companion. Run after: dart run flutter_launcher_icons
# Requires: ImageMagick (brew install imagemagick)
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPANION_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$COMPANION_DIR"

ICON_SRC="${COMPANION_DIR}/assets/icon/app_icon.png"
APPSET="${COMPANION_DIR}/macos/Runner/Assets.xcassets/AppIcon.appiconset"

if [[ ! -f "$ICON_SRC" ]]; then
  echo "Source icon not found: $ICON_SRC"
  exit 1
fi
if [[ ! -d "$APPSET" ]]; then
  echo "AppIcon.appiconset not found. Run: dart run flutter_launcher_icons"
  exit 1
fi

# Prefer magick (ImageMagick 7), fallback to convert (ImageMagick 6)
CONVERT=""
if command -v magick &>/dev/null; then
  CONVERT="magick"
elif command -v convert &>/dev/null; then
  CONVERT="convert"
fi
if [[ -z "$CONVERT" ]]; then
  echo "ImageMagick not found. Install: brew install imagemagick"
  echo "Alternatively use iconsur after building: ./scripts/macos_icon_squircle.sh"
  exit 1
fi

# Apple-style corner radius ~22% of size (approximates squircle)
radius_pct=22
sizes=(16 32 64 128 256 512 1024)
TMP_RESIZED="/tmp/mac_icon_resized_$$.png"
TMP_MASK="/tmp/mac_icon_mask_$$.png"
for size in "${sizes[@]}"; do
  r=$(( size * radius_pct / 100 ))
  [[ $r -lt 2 ]] && r=2
  out="${APPSET}/app_icon_${size}.png"
  if [[ "$CONVERT" == "magick" ]]; then
    "$CONVERT" "$ICON_SRC" -resize "${size}x${size}" "$TMP_RESIZED"
    "$CONVERT" -size "${size}x${size}" xc:none -fill white -draw "roundrectangle 0,0,$size,$size,$r,$r" "$TMP_MASK"
    "$CONVERT" "$TMP_RESIZED" "$TMP_MASK" -alpha off -compose copy-opacity -composite "$out"
  else
    "$CONVERT" "$ICON_SRC" -resize "${size}x${size}" "$TMP_RESIZED"
    "$CONVERT" -size "${size}x${size}" xc:none -fill white -draw "roundrectangle 0,0,$size,$size,$r,$r" "$TMP_MASK"
    "$CONVERT" "$TMP_RESIZED" "$TMP_MASK" -alpha off -compose copy-opacity -composite "$out"
  fi
  echo "  $out"
done
rm -f "$TMP_RESIZED" "$TMP_MASK"

echo "Done. macOS app icon assets now have Apple-style rounded corners."
echo "Rebuild the app (e.g. flutter run -d macos) to see the icon."
