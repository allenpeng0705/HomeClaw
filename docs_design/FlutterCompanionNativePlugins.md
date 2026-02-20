# Flutter companion: one codebase + native plugins for all platforms

The **HomeClaw Companion** app is built with **Flutter** so we have **one codebase** for Mac, Windows, Android, and iOS. Native-only features (voice input, screen recording, system.run, notifications, etc.) are implemented via **Flutter plugins** (platform channels): Dart calls into platform-specific code (Swift/Kotlin for Apple/Android, Swift/C++ for macOS/Windows) where Flutter doesn’t provide an API or where we need full control (e.g. TCC, permissions).

This doc describes that strategy and how it maps to OpenClaw-style features.

---

## Why Flutter + plugins

- **One codebase:** Shared UI, navigation, Core API client, settings, chat, and node/canvas UX. Same app on Mac, Windows, Android, iOS.
- **Native where needed:** Screen recording, microphone/speech, system.run, notifications, accessibility, etc. differ per OS. Flutter **platform channels** (method channels) let Dart call into:
  - **iOS:** Swift/Objective-C
  - **Android:** Kotlin/Java
  - **macOS:** Swift (same as iOS pattern)
  - **Windows:** C++ or C# (Win32 / Windows Runtime)

So we don’t need separate native Mac and Windows apps unless we choose to; we add **plugins** that implement the same Dart API with platform-specific code.

---

## Plugin layout (conceptual)

Each “feature” that needs native support can be a **Flutter plugin** (or a set of methods in a single “homeclaw_native” plugin):

| Feature / capability   | Dart API (plugin)     | macOS (Swift)     | Windows (C++/C#)   | Linux (C/C++)      | Android (Kotlin)   | iOS (Swift)        |
|------------------------|------------------------|-------------------|--------------------|--------------------|--------------------|
| **Voice input**        | e.g. `startListening()` / `stopListening()` → stream audio or text | AVFoundation, Speech | WinRT Speech / MediaCapture | PulseAudio/pipewire + speech-to-text | Android SpeechRecognizer, AudioRecord | AVFoundation, SFSpeechRecognizer |
| **Screen recording**   | e.g. `startScreenRecord(duration)` → file or data URL | ReplayKit / ScreenCapture (TCC) | Windows Graphics Capture API | PipeWire / X11 capture | MediaProjection     | ReplayKit          |
| **Camera snap/clip**   | e.g. `cameraSnap()` / `cameraClip(duration)` | AVFoundation      | Windows.Media.Capture | V4L2 / gstreamer   | CameraX / Camera2  | AVFoundation       |
| **System run**         | e.g. `systemRun(command, args)` → stdout/stderr/exit | Process + TCC/exec approvals | CreateProcess / shell       | Process / shell     | ProcessBuilder (or restricted) | Not typical on iOS  |
| **Notifications**      | e.g. `showNotification(title, body)` | UserNotifications / NSUserNotification | WinRT ToastNotification     | DBus notify         | NotificationManager | UNUserNotificationCenter |
| **Node registration**  | App registers as a “node” with Core/plugin | WebSocket client + local node id | Same                      | Same                | Same                | Same                |
| **Canvas (optional)**  | WebView or native view for agent-driven UI | WKWebView / native | WebView2 / native  | WebKitGTK           | WebView             | WKWebView          |

- **Core connection, chat, nodes list, canvas UX:** All in Dart (HTTP/WebSocket to Core; WebView or Flutter UI for canvas).
- **Anything that needs a platform API** (mic, screen, camera, process execution, notifications): implement in the plugin’s native side and expose a single Dart API so the rest of the app stays platform-agnostic.

---

## How Flutter plugins work (short)

1. **Dart:** Define a `MethodChannel` (e.g. `homeclaw_native/system_run`) and call `channel.invokeMethod('systemRun', {'command': 'ls', 'args': ['-la']})`. Handle the result (e.g. stdout, stderr, exit code) or errors (permission denied, timeout).
2. **Platform side:** Register a handler that receives the method name and arguments, runs the native code (e.g. run a process, start screen capture), and returns a result map (or throws).
3. **Permissions:** Request and handle permissions in the **native** code (e.g. macOS TCC prompts, Android runtime permissions, iOS capability usage descriptions). The Dart side only calls the plugin; the plugin triggers prompts and returns success/failure.

So yes: **we can write Flutter plugins to solve the native support problem** — one Dart API, multiple native implementations.

---

## What goes in the app (Dart) vs plugin (native)

- **Dart (shared):**
  - Core URL, API key, HTTP/WebSocket client, chat UI, settings.
  - Node list and “connect as node” flow (connection state, node id).
  - Canvas UI (e.g. WebView or Flutter widgets driven by Core/plugin).
  - Calling plugin APIs for voice, screen record, camera, system.run, notifications.
  - Orchestration: e.g. “user asked for screen record” → call plugin → upload or send result to Core.
- **Plugin (per platform):**
  - Voice: start/stop capture and/or speech recognition; return audio bytes or transcript.
  - Screen record: start/stop, return file path or data URL.
  - Camera: snap/clip, return file or data URL.
  - System run: run command with optional approval/allowlist; return stdout/stderr/exit.
  - Notifications: show local notification with title/body.
  - Any other capability that requires a platform API not exposed by Flutter.

---

## iOS and Android: same idea

On **iOS** and **Android**, Flutter plugins work the same way:

- **Android:** Plugin has an `android/` subproject; Dart talks to Kotlin/Java via `MethodChannel`; Kotlin/Java uses Android APIs (SpeechRecognizer, MediaProjection, CameraX, NotificationManager, etc.).
- **iOS:** Plugin has an `ios/` subproject; Dart talks to Swift/Obj-C via `MethodChannel`; Swift uses AVFoundation, ReplayKit, SFSpeechRecognizer, UNUserNotificationCenter, etc.

So **one Flutter codebase + one set of plugin APIs** can support **all four platforms** (Mac, Windows, Android, iOS), with each platform implementing only what it supports (e.g. no `system.run` on iOS, or a no-op that returns “not supported”).

---

## Summary

- **One code, all platforms:** Flutter app in `clients/homeclaw_companion/` with shared UI and logic.
- **Native features via plugins:** Voice, screen record, camera, system.run, notifications, etc. implemented as Flutter plugins (method channels) with native code per platform.
- **Mac/Windows:** Use the same plugin pattern (Swift for macOS, C++/C# for Windows) so we don’t need separate native Mac/Windows apps.
- **iOS/Android:** Same Dart code and same plugin API; Android and iOS implement their side in Kotlin and Swift.

This is why we can use **one codebase** and still support **voice input, screen recording, and other high-level features** on each platform by writing **plugins** for the parts that require native support.
