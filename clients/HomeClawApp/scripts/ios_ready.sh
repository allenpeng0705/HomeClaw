#!/usr/bin/env bash
# Run from clients/HomeClawApp. Ensures iOS build can succeed:
# - flutter pub get (creates ios/Flutter/Generated.xcconfig so FLUTTER_ROOT is set)
# - pod install (syncs Podfile.lock with Pods)
set -e
cd "$(dirname "$0")/.."
echo "Running flutter pub get..."
flutter pub get
echo "Running pod install in ios/..."
cd ios && pod install && cd ..
echo "Done. You can now: flutter run -d ios  (or open ios/Runner.xcworkspace in Xcode)"
