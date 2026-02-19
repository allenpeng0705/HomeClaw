# homeclaw_native

Flutter plugin for HomeClaw companion: native features (notifications, screen record, camera, system run, tray). For **voice input** use the [homeclaw_voice](https://github.com/your-org/HomeClaw/tree/main/clients/homeclaw_companion/packages/homeclaw_voice) package.

## Usage

Add to your app’s `pubspec.yaml`:

```yaml
dependencies:
  homeclaw_native:
    path: packages/homeclaw_native  # or pub.dev when published
```

```dart
import 'package:homeclaw_native/homeclaw_native.dart';

final native = HomeclawNative();

// Platform version (always implemented)
final version = await native.getPlatformVersion();

// Optional features – return null/false or throw if not implemented
await native.showNotification(title: 'Title', body: 'Body');
final path = await native.startScreenRecord(durationSec: 10, includeAudio: false);
final photoPath = await native.cameraSnap(facing: 'back');
final clipPath = await native.cameraClip(durationSec: 5);
final result = await native.systemRun(command: 'ls', args: ['-la'], timeoutSec: 5);
final hasTray = await native.getTraySupported();
```

## API

| Method | Returns | Notes |
|--------|--------|--------|
| `getPlatformVersion()` | `String?` | All platforms. |
| `showNotification(title, body)` | `void` | Android, iOS, macOS, Windows (Toast), Linux (notify-send). |
| `startScreenRecord(...)` | `String?` | **Linux:** ffmpeg x11grab (requires `ffmpeg` in PATH). **macOS 12.3+:** ScreenCaptureKit + AVAssetWriter. **Windows/iOS/Android:** stub (returns null). |
| `cameraSnap({facing})` | `String?` | Stub. |
| `cameraClip(...)` | `String?` | Stub. |
| `systemRun(...)` | `Map<String, dynamic>?` | Stub. |
| `getTraySupported()` | `bool` | Stub. |

Methods not implemented on a platform return `notImplemented()` on the native side; the Dart API catches `PlatformException` and returns `null` or `false`.

## Implementation status

- **Notifications:** Android (NotificationCompat), iOS/macOS (UserNotifications), Windows (PowerShell Toast on Windows 10+), Linux (notify-send).
- **Voice:** Use the [homeclaw_voice](packages/homeclaw_voice) package (wraps speech_to_text; supports Android, iOS, macOS, Windows beta, Web).
- **Implemented:** `startScreenRecord` on Linux (ffmpeg) and macOS 12.3+ (ScreenCaptureKit).
- **Stub (returns null or notImplemented):** `cameraSnap`, `cameraClip`, `systemRun`; `getTraySupported`/`setTrayIcon` on desktop return true/no-op.

## Method channel

Channel name: `homeclaw_native`.  
Method names: `getPlatformVersion`, `showNotification`, `startScreenRecord`, etc.

## Platforms

Android, iOS, macOS, Windows, Linux. Each platform implements the methods it supports; others return not implemented.