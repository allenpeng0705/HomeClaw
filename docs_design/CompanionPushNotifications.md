# Push notifications from HomeClaw to Companion (iOS/Android)

When the Companion app is **killed or in the background**, the system may not keep the WebSocket open. Reminders and other proactive messages then cannot be delivered over WebSocket. **Remote push notifications** allow HomeClaw Core to send a notification to the device even when the app is not running.

- **iOS / macOS**: **APNs only** (Apple Push Notification service). No Firebase on Apple devices (FCM is blocked in China). Companion gets the APNs device token via native code (`homeclaw_native.getApnsToken()`); Core sends directly to APNs (HTTP/2 with .p8 key).
- **Android (and Windows/Linux if FCM is added later)**: **FCM** (Firebase Cloud Messaging). Companion uses Firebase to get the FCM token; Core sends via Firebase Admin SDK.

---

## 1. Overview

- **Companion app**: On **iOS**: requests notification permission, gets **APNs device token** (`FirebaseMessaging.instance.getAPNSToken()`), sends to Core with `platform: "ios"`. On **Android**: gets **FCM token** (`getToken()`), sends to Core with `platform: "android"`.
- **HomeClaw Core**: Stores **user_id → list of {token, platform}**. When **deliver_to_user** is called (reminder, cron, etc.):
  1. Try WebSocket first (existing behaviour).
  2. If no WebSocket session for that user, send **remote push** per token: **APNs** for `platform` in (ios, macos, tvos, ipados, watchos); **FCM** for android and others.

---

## 2. Core side

### 2.1 Push token storage

- **API**: `POST /api/companion/push-token` (or similar) with body: `{ "user_id": "...", "token": "...", "platform": "android"|"ios" }`. Optionally `device_id` for replacing an old token.
- **Storage**: Simple JSON file under `database/` (e.g. `push_tokens.json`) or a DB table. Structure: `user_id -> [ { "token": "...", "platform": "...", "updated_at": "..." } ]`. Remove tokens that fail (invalid/expired) when FCM returns an error.

### 2.2 Sending push when delivering

- **deliver_to_user(user_id, text, ..., from_friend="HomeClaw")** is used by Core for reminders, cron, inbound fallback, and any proactive delivery. When no WebSocket session is open, **base.push_send.send_push_to_user** is called with the same `from_friend`; it routes each token by `platform`:
  - **APNs** for `platform` in (ios, macos, tvos, ipados, watchos): send via APNs HTTP/2 API (JWT auth with .p8 key).
  - **FCM** for android and others: send via Firebase Admin SDK (service account JSON).

### 2.3 Push payload format (multi-user, per-friend)

Core adds **user_id**, **source**, and **from_friend** to every push so the Companion can show which user the notification is for and which friend it is from (e.g. open the correct chat thread).

- **APNs (iOS/macOS):** Custom keys at root level (outside `aps`):
  - `user_id` (string): target user (e.g. `"alice"`, `"companion"`).
  - `source` (string): e.g. `"reminder"`, `"push"`, `"inbound"`.
  - `from_friend` (string): which friend the message is from — `"HomeClaw"` (system) or a friend name (e.g. `"Sabrina"`). Used to route the notification to the correct friend chat.
  - Standard: `aps.alert.title`, `aps.alert.body`, `aps.sound`.
- **FCM (Android):** `data` map (all values strings):
  - `user_id`: target user.
  - `source`: e.g. `"reminder"`, `"push"`, `"inbound"`.
  - `from_friend`: which friend the message is from (`"HomeClaw"` or friend name).
  - `text`: body text (same as notification body).

**Companion behaviour:** When the app receives a push (foreground handler or when the user taps the notification), read `user_id`, `source`, and **from_friend** from the payload. Use `from_friend` to route to the correct friend chat (e.g. show “From Sabrina: …” or add the notification to Sabrina’s thread). One device can receive push for many users; the payload identifies which user and which friend each notification is for.

### 2.4 Config (core.yml)

Add to **config/core.yml** (optional):

```yaml
# Push notifications: APNs for iOS/Apple, FCM for Android.
push_notifications:
  enabled: true
  # APNs (iOS/macOS/tvOS): Core sends directly to Apple.
  ios:  # or apns:
    key_path: "path/to/AuthKey_XXXXX.p8"   # relative to project root
    key_id: "XXXXXXXXXX"
    team_id: "XXXXXXXXXX"
    bundle_id: "com.example.homeclawCompanion"
    sandbox: true   # true for development, false for production
  # FCM (Android and other non-Apple): Core sends via Firebase.
  fcm:
    credentials_path: "path/to/serviceAccountKey.json"
# Legacy: credentials_path at top level also used for FCM if fcm.credentials_path not set.
# Or set env GOOGLE_APPLICATION_CREDENTIALS for FCM.
```

- **APNs**: Requires `pip install pyjwt cryptography "httpx[http2]"`. Core uses **JWT auth with an APNs Key (.p8)** only — the legacy Apple Push Services certificate (.p12) is not supported (APNs HTTP/2 API accepts JWT only). If you created a .p12 push certificate, create an **APNs Key** instead: [Apple Developer → Keys](https://developer.apple.com/account/resources/authkeys/list) → + → enable **Apple Push Notifications** → Download the .p8 file once (you cannot download it again). Use that file as `key_path`, and set `key_id` (from the key name in Developer), `team_id` (10-char Team ID), and `bundle_id` (e.g. `com.homeclaw.homeclawApp`) in `config/core.yml` under `push_notifications.ios`. Use `sandbox: true` for development/Simulator/TestFlight, `sandbox: false` for App Store.
- **FCM**: Requires `pip install firebase-admin` and a Firebase service account JSON key.

---

## 3. Companion app side

### 3.1 Setup (one-time)

**iOS / macOS (APNs only, no Firebase):**
- No Firebase or GoogleService-Info.plist needed for push (avoids FCM, works in China).
- **Push Notifications** is enabled via entitlements: `aps-environment` is set in `ios/Runner/Runner.entitlements` and `macos/Runner/DebugProfile.entitlements` / `Release.entitlements` (use `development` for sandbox, switch to `production` for App Store).
- In Xcode you can also enable **Background Modes → Remote notifications** for iOS so the app can receive push when backgrounded.
- The app’s **AppDelegate** must call `HomeclawNativePlugin.receiveApnsToken(deviceToken)` in `didRegisterForRemoteNotificationsWithDeviceToken` (already done in `ios/Runner/AppDelegate.swift` and `macos/Runner/AppDelegate.swift`).

**Android (FCM):**
1. Create a [Firebase project](https://console.firebase.google.com/) and add an **Android** app (package name).
2. Download **google-services.json** and place it in `clients/homeclaw_companion/android/app/google-services.json`.
3. Run `flutter pub get` in `clients/homeclaw_companion`.

### 3.2 Flutter dependencies

- **firebase_core** – initialize Firebase.
- **firebase_messaging** – get FCM token, handle foreground/background messages.

### 3.3 App behaviour

1. **iOS / macOS**: Request notification permission; get **APNs device token** via native `HomeclawNative().getApnsToken()` (no Firebase). Send to Core with `platform: "ios"` or `"macos"`. AppDelegate must call `HomeclawNativePlugin.receiveApnsToken(deviceToken)` when the system delivers the token.
2. **Android**: Firebase is initialized only on Android. Get **FCM token** via `FirebaseMessaging.instance.getToken()`; send to Core with `platform: "android"`.
3. **Send token to Core**: `POST /api/companion/push-token` with `user_id`, `token`, `platform` (“ios” or “android”). Same auth (API key) as other Core requests.
4. **Background/terminated**: When the user taps the notification, the OS opens the app. Reminder text is shown in the notification.

### 3.4 Optional: conditional compilation

If you want the app to build **without** Firebase (e.g. for desktop-only builds), use conditional imports or a stub so that `getToken()` is only called when Firebase is configured; otherwise skip token registration.

---

## 4. Security and privacy

- **Tokens** are sensitive (they allow sending messages to that device). Store them only on Core (or your backend), protect the service account key, and use HTTPS + API key for the push-token endpoint.
- **user_id** should match the same identity used for reminders (e.g. “System” or the chat user). One user can have multiple tokens (multiple devices).

---

## 5. Summary

| Platform   | Token source        | Core sends via |
|-----------|---------------------|----------------|
| **iOS**   | APNs device token    | **APNs** (HTTP/2, .p8 key) |
| **Android** | FCM token         | **FCM** (Firebase Admin SDK) |

| Component  | Responsibility |
|------------|----------------|
| **Companion** | iOS: get APNs token, send to Core with platform "ios". Android: get FCM token, send with platform "android". |
| **Core**   | Store tokens per user_id; when deliver_to_user runs (no WebSocket), route by platform: APNs for Apple, FCM for others. |

With this, reminders (and other proactive messages) can reach the user even when the Companion app has been killed by the system.
