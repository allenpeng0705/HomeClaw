# HomeClaw Flutter app: feature parity with OpenClaw

This doc maps **OpenClaw’s app features** (macOS menu bar, iOS/Android nodes, CLI) to the **HomeClaw Flutter companion** and defines how we support them using **one codebase + Flutter plugins** for platform-specific code.

---

## OpenClaw features to mirror

| OpenClaw feature | Description | HomeClaw Flutter approach |
|------------------|-------------|---------------------------|
| **Chat / agent** | Send message, get reply (HTTP or WebSocket). | ✅ Done: POST /inbound, Core URL + API key in settings. Optional: add WebSocket /ws for streaming. |
| **Voice input** | Push-to-talk or voice wake; speech-to-text. | **Plugin:** `startVoiceListening()` / `stopVoiceListening()` → stream audio or transcript. Native: AVFoundation (Apple), WinRT (Windows), SpeechRecognizer (Android), etc. |
| **Voice output (TTS)** | Talk mode, ElevenLabs-style. | **Plugin or HTTP:** `speak(text)` → play TTS. Native TTS per platform, or call Core/plugin HTTP for cloud TTS. |
| **Screen recording** | Record screen (with optional audio). | **Plugin:** `startScreenRecord(duration, {includeAudio})` → file or data URL. ReplayKit (Apple), MediaProjection (Android), Windows Graphics Capture, PipeWire (Linux). |
| **Camera** | Snap photo, short video clip. | **Plugin:** `cameraSnap()`, `cameraClip(duration)` → file or data URL. AVFoundation, CameraX, WinRT, V4L2. |
| **Canvas** | Agent-driven UI (HTML/JS or native). | **Dart + WebView:** Load URL or HTML from Core/plugin; or Flutter widgets driven by Core. No plugin required if we use Flutter’s WebView. |
| **System run** | Run shell command with approvals. | **Plugin (desktop only):** `systemRun(command, args, {timeout})` → stdout, stderr, exitCode. Exec approvals in app settings (allowlist). Not on iOS. |
| **Notifications** | Show local notification (e.g. “Core replied”). | **Plugin:** `showNotification(title, body)`. UserNotifications (Apple), WinRT (Windows), NotificationManager (Android), DBus (Linux). |
| **Node registration** | App connects as a “node” so Core can invoke device actions. | **Dart:** WebSocket or HTTP to Core (or homeclaw-browser plugin) with node id; advertise capabilities; handle `node.invoke`-style commands (camera, screen, etc.) by calling the plugins above. |
| **Status / menu bar** | Menu bar icon, status, quick actions. | **Plugin (desktop):** tray icon, menu (macOS/Windows/Linux). Optional; can start with a normal window. |
| **Deep links** | `homeclaw://agent?message=...` to send from outside. | **Dart:** Register `homeclaw://` URL scheme; parse and send message to Core. Already have `homeclaw://connect` for QR; add `homeclaw://agent`. |
| **QR pairing** | Scan QR to set Core URL + token. | ✅ Done: CLI `pair`, app “Scan QR to connect”. |
| **Exec approvals** | Allowlist for `system.run`. | **Dart:** Store allowlist in app (e.g. SharedPreferences or file); plugin calls back to Dart “can run this command?” or plugin reads allowlist from a file the app writes. |

---

## Plugin strategy: one “homeclaw_native” plugin

Use a **single** Flutter plugin package (**homeclaw_native**) that exposes all native capabilities via one **MethodChannel**. Per platform we implement only the methods that make sense (e.g. no `systemRun` on iOS; return “not supported” or throw).

**Suggested Dart API (method names and args):**

| Method | Arguments | Returns | Platforms |
|--------|-----------|--------|-----------|
| `startVoiceListening` | `{String? locale}` | `Stream<Uint8List>` or `Stream<String>` (transcript) | All (plugin returns stream via EventChannel) |
| `stopVoiceListening` | — | `void` | All |
| `startScreenRecord` | `{int durationSec, bool includeAudio}` | `String` (file path or data URL) | macOS, Windows, Linux, Android, iOS |
| `cameraSnap` | `{String? facing}` | `String` (path or data URL) | All |
| `cameraClip` | `{int durationSec, bool includeAudio}` | `String` | All |
| `systemRun` | `{String command, List<String> args, int? timeoutSec}` | `{stdout, stderr, exitCode}` | macOS, Windows, Linux, Android (restricted) |
| `showNotification` | `{String title, String body}` | `void` | All |
| `getTraySupported` | — | `bool` | Desktop only |
| `setTrayIcon` / `setTrayMenu` | (optional) | — | Desktop |

**Permissions:** Requested in native code (TCC on macOS, runtime permissions on Android/iOS, etc.). Plugin returns a clear error if permission is denied.

---

## How the app uses the plugin

1. **Chat:** Already uses Core (POST /inbound). Optional: switch to WebSocket /ws and show typing/streaming.
2. **Voice:** User taps “Voice”; app calls `startVoiceListening`; plugin streams audio or transcript; app sends transcript (or audio URL if Core accepts it) to Core and displays reply.
3. **Screen record:** User asks in chat or taps “Record screen”; app calls `startScreenRecord(durationSec: 10)`; plugin returns path/URL; app uploads to Core or sends in next message (if Core supports file upload).
4. **Camera:** Same as screen record: `cameraSnap()` / `cameraClip()` → send to Core.
5. **Canvas:** App has a “Canvas” tab or overlay with a WebView; Core (or homeclaw-browser plugin) sends URL or HTML; app loads it. No plugin required if we use `webview_flutter` or similar.
6. **Node mode:** App registers with Core (or plugin) as a node with id and capability list (voice, screen, camera, systemRun). When Core sends “invoke camera.snap,” app calls plugin `cameraSnap()` and returns result. Protocol can be HTTP callback or WebSocket depending on what Core supports.
7. **Notifications:** When Core sends “notify” or when a background task has a result, app calls `showNotification(title, body)`.
8. **Deep link:** App registers `homeclaw://agent`; when opened with `?message=...`, app sends that message to Core and shows reply (or opens chat with that message).

---

## Phased implementation

| Phase | What | Delivers |
|-------|------|----------|
| **0 (done)** | Chat, settings, Scan QR, Core URL + API key. | Usable app on all platforms. |
| **1** | **homeclaw_native** plugin package; stub implementations (return “not implemented” where needed). App depends on plugin; calls no new methods yet. | Clean plugin structure; no regressions. |
| **2** | **Notifications** in plugin (all platforms). App calls `showNotification` when Core reply arrives (optional) or for “Core connected.” | Notifications work. |
| **3** | **Voice input** in plugin (mic → stream or transcript). App “Voice” button sends transcript to Core. | Push-to-talk style voice. |
| **4** | **Camera** in plugin (snap + clip). App “Camera” or node command. | Photo/video from device. |
| **5** | **Screen recording** in plugin. App “Record screen” or node command. | Screen capture. |
| **6** | **System run** in plugin (desktop + Android with allowlist). Exec approvals UI in app. | Run shell commands from Core. |
| **7** | **Canvas** in app (WebView + URL/HTML from Core or plugin). **Node registration** (app as node) if Core/plugin protocol is defined. | Canvas UI; app as node. |
| **8** | **Tray / menu bar** (desktop plugin). **Deep link** `homeclaw://agent`. **Voice wake** (optional). | Desktop polish; deep link. |

---

## Where the plugin lives

- **Option A:** Inside the app repo: `clients/homeclaw_companion/packages/homeclaw_native` (path dependency in `pubspec.yaml`: `homeclaw_native: path: packages/homeclaw_native`).
- **Option B:** Top-level: `clients/packages/homeclaw_native` so other clients could use it later.

Use **Option A** for simplicity; the app is the only consumer for now.

---

## Summary

- **Feature parity with OpenClaw** = chat, voice, screen record, camera, canvas, system.run, notifications, node registration, (optional) tray and deep links.
- **Implementation:** One Flutter app + one **homeclaw_native** plugin. Plugin exposes a single Dart API; each platform implements what it can; app orchestrates and talks to Core.
- **Phases:** Stub plugin → notifications → voice → camera → screen record → system run → canvas/node → tray/deep link. This keeps the app working at each step and adds OpenClaw-like features incrementally.
