# macOS permissions for HomeClaw Companion app

This doc describes what permissions the **HomeClaw Companion** Flutter app may need on macOS, and how to set them up. It is inspired by [OpenClaw’s macOS permissions guide](https://open-claw.bot/docs/platforms/mac/permissions); we only request what the app actually uses.

---

## Current app (chat only)

The companion app today only:

- Connects to HomeClaw Core over HTTP (POST /inbound).
- Stores Core URL and API key in app storage (shared_preferences).

**Permissions needed for this:**

- **Network (outgoing):** The app must be allowed to make HTTP requests to Core. Flutter macOS builds typically get this by default. If the app is sandboxed, enable **Outgoing Connections (Client)** in the macOS entitlements (see below).
- **No TCC prompts** for the current feature set: we do not use Accessibility, Screen Recording, Microphone, Notifications, or Automation.

So for **chat-only use**, you usually do not need to “turn on” any permissions in System Settings; only ensure the app can reach Core (and, for release/sandbox, the network entitlement).

---

## If you add more features later (OpenClaw-style)

If you later add features similar to OpenClaw’s Mac app, you may need these **TCC (Transparency, Consent, and Control)** permissions. macOS will prompt the user when the app first uses each capability:

| Permission | Typical use in OpenClaw | When you’d need it in HomeClaw |
|------------|--------------------------|----------------------------------|
| **Notifications** | Show system notifications (e.g. “Core replied”) | If you add local/push notifications. |
| **Accessibility** | Control UI or automate actions | If you add accessibility-based automation. |
| **Screen Recording** | Capture screen for “see my screen” / recording | If you add screen capture or recording. |
| **Microphone** | Voice input (push-to-talk, etc.) | If you add voice input to the app. |
| **Speech Recognition** | Dictation / voice commands | If you add speech-to-text in the app. |
| **Automation / AppleEvents** | Control other apps (e.g. browser, scripts) | If you add “run script” or control other apps from the app. |

**How to handle them (like OpenClaw):**

1. **Signing:** Use a real **Apple Development** (or Developer ID) certificate. Ad-hoc signing changes every build and macOS may drop previously granted permissions.
2. **Bundle ID:** Keep a **consistent bundle identifier** (e.g. `ai.homeclaw.companion`). Changing it makes macOS treat the app as a new app and revoke prior grants.
3. **Fixed path:** Run the app from a **fixed location** (e.g. `build/macos/Build/Products/Release/HomeClawApp.app` or a copied path). Moving or renaming the app can invalidate TCC entries.
4. **Reset if prompts stop:** If macOS stops showing permission prompts or access seems lost, reset TCC for your bundle ID (replace `ai.homeclaw.companion` with your actual bundle ID):
   ```bash
   sudo tccutil reset Accessibility ai.homeclaw.companion
   sudo tccutil reset ScreenCapture ai.homeclaw.companion
   sudo tccutil reset AppleEvents ai.homeclaw.companion
   ```
   Then relaunch the app from the same path and grant permissions when prompted. You can also remove the app from **System Settings → Privacy & Security** and try again.

---

## Flutter macOS entitlements (network)

After you run `flutter create .` in `clients/HomeClawApp/`, you get a `macos/` folder. To allow outgoing network when the app is sandboxed:

1. Open **macos/Runner/Release.entitlements** (for release) or **macos/Runner/DebugProfile.entitlements** (for debug).
2. Ensure **Outgoing Connections (Client)** is enabled, for example:
   ```xml
   <key>com.apple.security.network.client</key>
   <true/>
   ```
   Flutter’s default macOS template often includes this already.

If you ship without App Sandbox, the app can use the network without this entitlement, but sandboxing is recommended for distribution.

---

## Location on all platforms (Companion app)

The Companion app requests **location (when in use)** on **Android**, **iOS**, **macOS**, **Windows**, and **Linux** so it can send position to Core (e.g. for weather, reminders).

- **Android:** `ACCESS_FINE_LOCATION` / `ACCESS_COARSE_LOCATION` in `AndroidManifest.xml`.
- **iOS:** `NSLocationWhenInUseUsageDescription` in `ios/Runner/Info.plist`.
- **macOS:** `NSLocationWhenInUseUsageDescription` in `macos/Runner/Info.plist`.
- **Windows:** No manifest change needed (Win32 app). The user allows location in **Settings → Privacy & security → Location**; the app uses the system location API when permitted.
- **Linux:** The app uses **geolocator_linux** (optional dependency). The user may need to allow location in the desktop environment (e.g. GNOME location settings) if prompted.

If location is denied or unavailable, the app still works; it simply does not send location with messages.

---

## Summary

- **Today (chat only):** No extra permissions to “turn on” in System Settings; only ensure network works (and entitlements for sandbox if you use it).
- **Later (voice, notifications, screen, etc.):** Add capabilities as needed; use proper signing, stable bundle ID, and fixed path, and refer to OpenClaw’s approach and TCC reset steps above.
