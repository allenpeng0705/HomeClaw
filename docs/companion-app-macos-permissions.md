# Companion app: macOS permissions

This page describes what permissions the **HomeClaw Companion** app may need on **macOS**, and how to set them up. We only request what the app actually uses.

---

## Current app (chat only)

The companion app today:

- Connects to HomeClaw Core over HTTP (POST /inbound).
- Stores Core URL and API key in app storage.

**Permissions needed:**

- **Network (outgoing):** The app must be allowed to make HTTP requests to Core. Flutter macOS builds typically get this by default. If the app is sandboxed, enable **Outgoing Connections (Client)** in the entitlements (see below).
- **No system permission prompts** for the current feature set: we do not use Accessibility, Screen Recording, Microphone, Notifications, or Automation.

So for **chat-only use**, you usually do not need to turn on any permissions in System Settings; only ensure the app can reach Core (and, for release/sandbox, the network entitlement).

---

## If you add more features later

If you later add features such as voice input, notifications, or screen capture, you may need **TCC (Transparency, Consent, and Control)** permissions. macOS will prompt when the app first uses each capability:

| Permission | When you'd need it |
|------------|---------------------|
| **Notifications** | Local or push notifications (e.g. “Core replied”). |
| **Accessibility** | Accessibility-based automation. |
| **Screen Recording** | Screen capture or recording. |
| **Microphone** | Voice input (push-to-talk, etc.). |
| **Speech Recognition** | Dictation or voice commands in the app. |
| **Automation / AppleEvents** | Controlling other apps (e.g. browser, scripts) from the app. |

**Best practices:**

1. **Signing:** Use a real **Apple Development** (or Developer ID) certificate. Ad-hoc signing changes every build and macOS may drop previously granted permissions.
2. **Bundle ID:** Keep a **consistent bundle identifier** (e.g. `ai.homeclaw.companion`). Changing it makes macOS treat the app as new and revoke prior grants.
3. **Fixed path:** Run the app from a **fixed location**. Moving or renaming the app can invalidate permission entries.
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

1. Open **macos/Runner/Release.entitlements** (release) or **macos/Runner/DebugProfile.entitlements** (debug).
2. Ensure **Outgoing Connections (Client)** is enabled:
   ```xml
   <key>com.apple.security.network.client</key>
   <true/>
   ```
   Flutter’s default macOS template often includes this already.

If you ship without App Sandbox, the app can use the network without this entitlement; sandboxing is recommended for distribution.

---

## Summary

- **Today (chat only):** No extra permissions to turn on in System Settings; only ensure network works (and entitlements for sandbox if you use it).
- **Later (voice, notifications, screen, etc.):** Add capabilities as needed; use proper signing, a stable bundle ID, and a fixed path, and use the TCC reset steps above if needed.
