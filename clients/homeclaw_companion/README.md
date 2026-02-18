# HomeClaw Companion (Flutter)

Companion app for **HomeClaw Core**: chat from Mac, Windows, Android, and iOS. Connects to Core via HTTP (POST /inbound).

## Prerequisites

- **Flutter SDK** 3.0+ ([flutter.dev](https://flutter.dev)).
- **HomeClaw Core** running (e.g. `http://127.0.0.1:9000`).

## First-time setup: generate platform folders

This project contains the Dart code and `pubspec.yaml`. You must generate the platform-specific projects (Android, iOS, macOS, Windows) once:

```bash
cd clients/homeclaw_companion
flutter create .
```

Answer **Yes** if asked to overwrite files (it will add android/, ios/, macos/, windows/). Then:

```bash
flutter pub get
```

## Run by platform

- **macOS:** `flutter run -d macos`
- **Windows:** `flutter run -d windows`
- **Android:** `flutter run -d android` (device or emulator)
- **iOS:** `flutter run -d ios` (device or simulator; requires Xcode on Mac)

To list devices: `flutter devices`.

## App usage

1. **First launch:** Open **Settings** (gear icon), set **Core URL** (e.g. `http://127.0.0.1:9000`). If Core has `auth_enabled: true`, set **API Key**. Tap **Save**.
2. **Chat:** Type a message and send; the reply from Core appears below.

## Remote Core (e.g. Tailscale, Cloudflare)

Use the same app: in Settings set **Core URL** to your exposed URL (e.g. `https://your-machine.tailnet-name.ts.net` or your Cloudflare tunnel URL). No code change needed.

## Android: HTTP (non-HTTPS) Core

If Core is HTTP (e.g. local `http://192.168.x.x:9000`), Android 9+ blocks cleartext by default. Either:

- Use an HTTPS URL (e.g. via tunnel), or
- Add cleartext: create or edit `android/app/src/main/res/xml/network_security_config.xml` with cleartext allowed, and in `AndroidManifest.xml` set `android:networkSecurityConfig="@xml/network_security_config"` and `android:usesCleartextTraffic="true"` on the `<application>` tag.

(See [Flutter network security](https://docs.flutter.dev/development/data-and-backend/network-security) for details.)

## iOS / macOS: network and signing

- **Simulator:** Usually works with default settings.
- **Real device / release:** Configure signing in Xcode (macOS: enable "Outgoing Connections" in entitlements if needed). For iOS, add any required capabilities (e.g. network).

## Troubleshooting

- **Connection refused:** Ensure Core is running and the URL in Settings is correct (no trailing slash).
- **401 / 403:** Enable and set the API key in Settings to match Core’s `auth_api_key`.
- **Platform build fails:** Run `flutter doctor` and fix any reported issues. Ensure you ran `flutter create .` and `flutter pub get`.
