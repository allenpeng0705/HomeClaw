# HomeClaw Companion – feature implementation status


---

## Done

| Feature | Implementation |
|--------|-----------------|
| **Chat** | POST /inbound, Core URL + API key in settings. |
| **Notifications** | homeclaw_native `showNotification` (Android, iOS, macOS, Windows Toast, Linux notify-send). |
| **Voice input** | homeclaw_voice (speech_to_text on Android/iOS/macOS/Windows/Web; Vosk on Linux). |
| **QR pairing** | CLI `pair`, app “Scan QR to connect” (mobile_scanner). |

---

## Implemented in this pass

| Feature | Implementation |
|--------|-----------------|
| **Camera (photo)** | image_picker: take photo, get file path, attach to chat or send to Core. |
| **Camera (short video)** | image_picker: record short video (max duration), get path, attach/send. |
| **Screen recording** | homeclaw_native `startScreenRecord` remains stub; app shows “Record screen” and calls plugin (returns null until native impl). Optional: desktop_screen_recorder for desktop later. |
| **System run** | Allowlist in app settings (SharedPreferences); run command via Dart `Process.run` on desktop (macOS, Windows, Linux) when command matches allowlist. Not on iOS; Android optional/restricted. |
| **TTS (talk mode)** | flutter_tts: optional “Speak” after reply or button to speak last reply. |
| **Canvas** | New screen/tab with WebView (webview_flutter); load URL from settings or Core (e.g. agent-driven UI). |
| **Deep link** | app_links: handle `homeclaw://agent?message=...` → open app and send message to Core. |

---

## Implemented (this pass)

| Feature | Implementation |
|--------|-----------------|
| **Node registration** | Settings: Nodes URL + Node ID; "Connect as node" connects WebSocket to plugin `/nodes-ws`, registers with capabilities (screen, camera, notify). NodeService handles camera_snap, camera_clip, screen_record, notify. |
| **Tray / menu bar** | homeclaw_native `getTraySupported` returns true on macOS/Windows/Linux; `setTrayIcon` stub (no-op) on desktop. |
| **Exec allowlist (pattern)** | CoreService `isExecAllowed(fullCommand)`: each entry is exact executable name or regex pattern. Settings hint updated. |
| **Send photo/video to Core** | CoreService `uploadFiles(paths)` → POST /api/upload; `sendMessage(text, images, videos)`. Chat: pending attachments (photo/video/screen), upload on Send, then /inbound with paths. |

## Screen recording (native)

| Platform | Implementation |
|----------|----------------|
| **Linux** | `startScreenRecord`: spawns `ffmpeg -f x11grab -t <duration> -i $DISPLAY -c:v libx264`; returns temp file path. Requires `ffmpeg` in PATH. |
| **macOS 12.3+** | `startScreenRecord`: ScreenCaptureKit (SCStream) + AVAssetWriter; records display to `.mov` in temp dir; returns path. App must have Screen Recording permission. Plugin and app deployment target set to 12.3. |
| **Windows / iOS / Android** | Stub: returns null. Can be added later (Graphics Capture, RPScreenRecorder, MediaProjection). |

## Not yet implemented

| Feature | Notes |
|--------|--------|
| **Screen recording (other platforms)** | Android: MediaProjection + Service. iOS: RPScreenRecorder + AVAssetWriter. Windows: Graphics Capture API. |

---

## App structure after this pass

- **ChatScreen:** Chat, voice (mic), camera (photo/video attach), “Record screen” (calls plugin), “Speak” (TTS), Settings.
- **SettingsScreen:** Core URL, API key, Scan QR, **Exec allowlist** (for system run), **Canvas URL** (for WebView).
- **CanvasScreen:** Full-screen WebView loading Canvas URL (or from Core).
- **Main:** Handle deep link `homeclaw://agent` (app_links) and open chat with pre-filled message.
- **System run:** Triggered from chat (e.g. “Run: ls -la”) or a small “Run command” dialog; allowlist checked before Process.run on desktop.

---

## Dependencies added

- image_picker
- flutter_tts
- webview_flutter
- app_links
- path_provider, path (for saving files / paths)

Screen recording on desktop can later use `desktop_screen_recorder` or native implementation in homeclaw_native.
