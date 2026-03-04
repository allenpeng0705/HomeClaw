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

### 1.1 Multi-user and multi-device

Push **supports multiple users**. Core stores push tokens **per user_id**; each user receives push only for their own messages, reminders, and user-to-user messages.

- **One user per login (per app instance):** The Companion app can only be **logged in as one user at a time**. When the app registers its push token with Core, it sends the **current logged-in user_id**. That token is then associated with that user. If the user logs out and another user logs in on the same device, the app should **re-register** the token with the new user_id so that push goes to the correct user; Core may optionally remove or reassign the token for the previous user on that device (e.g. if using `device_id` to deduplicate).
- **One user, multiple devices:** A single user may be logged in on **multiple devices** (e.g. phone and tablet). Each device registers its own token with the **same user_id**. Core sends push to **all tokens** for that user so that every device receives the notification.

---

## 2. Core side

### 2.1 Push token storage

- **API**: `POST /api/companion/push-token` (or similar) with body: `{ "user_id": "...", "token": "...", "platform": "android"|"ios" }`. Optionally `device_id` for replacing an old token.
- **Storage**: Simple JSON file under `database/` (e.g. `push_tokens.json`) or a DB table. Structure: `user_id -> [ { "token": "...", "platform": "...", "updated_at": "..." } ]`. Remove tokens that fail (invalid/expired) when FCM returns an error.

### 2.2 Sending push when delivering

- **deliver_to_user(user_id, text, ..., from_friend="HomeClaw")** is used by Core for reminders, cron, inbound fallback, and any proactive delivery. When no WebSocket session is open, **base.push_send.send_push_to_user** is called with the same `from_friend`; it routes each token by `platform`:
  - **APNs** for `platform` in (ios, macos, tvos, ipados, watchos): send via APNs HTTP/2 API (JWT auth with .p8 key).
  - **FCM** for android and others: send via Firebase Admin SDK (service account JSON).

### 2.3 When push is sent

- **Reminders** and **cron** (time-sensitive): push is always sent so the user gets notified when the app is in background.
- **User-to-user messages** (`source=user_message`): push is sent so the recipient gets a notification when user1 sends to user2 and user2’s app is in background or killed. Title is “Message from &lt;sender name&gt;”, body is the message text.

**How to verify push for user messages:** Log in as user2 on a device, put the app in background (or kill it). From another device/session, have user1 send a message to user2. user2 should receive a system notification; tapping it should open the app and the chat with user1. Ensure FCM/APNs is configured (see 2.4) and that the Companion has registered the push token with Core for user2 (e.g. by opening any chat as user2 once).

### 2.4 Push payload format (multi-user, per-friend)

Core adds **user_id**, **source**, **from_friend**, and for user_message **from_user_id** to every push so the Companion can show which user the notification is for and which friend it is from (e.g. open the correct chat thread).

- **APNs (iOS/macOS):** Custom keys at root level (outside `aps`):
  - `user_id`, `source`, `from_friend`: as above.
  - **`link`** (string): deep link for tap-to-open, e.g. `homeclaw://chat?from_friend=HomeClaw`. When the user taps the notification, the app opens this URL and navigates to that chat (iOS/macOS AppDelegate opens the URL; Dart handles `homeclaw://chat` via app_links).
- **FCM (Android):** `data` map (all values strings):
  - `user_id`, `source`, `from_friend`, `text`: as above.
  - **`link`** (string): same deep link format so the app can use it if desired (Android already uses FCM tap callback; the link is available for consistency).

**Companion behaviour:** When the app receives a push (foreground handler or when the user taps the notification), read `user_id`, `source`, and **from_friend** from the payload. Use `from_friend` to route to the correct friend chat (e.g. show “From Sabrina: …” or add the notification to Sabrina’s thread). One device can receive push for many users; the payload identifies which user and which friend each notification is for.

### 2.5 Config (core.yml)

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
1. Create a [Firebase project](https://console.firebase.google.com/) and add an **Android** app. Use package name **`com.homeclaw.homeclawApp`** (must match `android/app/build.gradle.kts` `applicationId`).
2. Download **google-services.json** from the Firebase Console (Project settings → Your apps → Android app → Download config) and place it in **`clients/HomeClawApp/android/app/google-services.json`**. (Do not commit this file if it contains secrets; add to `.gitignore` if needed.)
3. The repo already applies the **Google Services** plugin: `android/settings.gradle.kts` declares it, and `android/app/build.gradle.kts` applies it. No extra Gradle edits needed once the JSON is in place.
4. Run `flutter pub get` and build: `cd clients/HomeClawApp && flutter pub get && flutter build apk` (or run on a device).
5. **Core (server)** must be able to send FCM: install `pip install firebase-admin` and set **config/core.yml** `push_notifications.fcm.credentials_path` to the path to your **Firebase service account JSON** (Project settings → Service accounts → Generate new private key), or set env **`GOOGLE_APPLICATION_CREDENTIALS`** to that file path. See §2.4 above.

### 3.2 Flutter dependencies

- **firebase_core** – initialize Firebase.
- **firebase_messaging** – get FCM token, handle foreground/background messages.

### 3.3 App behaviour

1. **iOS / macOS**: Request notification permission; get **APNs device token** via native `HomeclawNative().getApnsToken()` (no Firebase). Send to Core with `platform: "ios"` or `"macos"`. AppDelegate must call `HomeclawNativePlugin.receiveApnsToken(deviceToken)` when the system delivers the token.
2. **Android**: Firebase is initialized only on Android. Get **FCM token** via `FirebaseMessaging.instance.getToken()`; send to Core with `platform: "android"`.
3. **Send token to Core**: `POST /api/companion/push-token` with `user_id`, `token`, `platform` (“ios” or “android”). Same auth (API key) as other Core requests.
4. **Background/terminated / tap to open chat**: When the user taps the notification:
   - **Android**: FCM `onMessageOpenedApp` / `getInitialMessage` provides the payload; the app navigates to the chat for `from_friend`.
   - **iOS/macOS**: Each push includes a **deep link** (`link`: `homeclaw://chat?from_friend=...`). AppDelegate implements `UNUserNotificationCenterDelegate` and opens that URL when the user taps; the app handles `homeclaw://chat` via **app_links** (`getInitialLink` for cold start, `uriLinkStream` when already running) and navigates to that chat. No Firebase on Apple; works in China.

### 3.4 Optional: conditional compilation

If you want the app to build **without** Firebase (e.g. for desktop-only builds), use conditional imports or a stub so that `getToken()` is only called when Firebase is configured; otherwise skip token registration.

---

## 4. Security and privacy

- **Tokens** are sensitive (they allow sending messages to that device). Store them only on Core (or your backend), protect the service account key, and use **HTTPS** + API key for the push-token endpoint. For a broader picture of encryption and security (Companion–Core and user-to-user), see [CompanionEncryptionAndSecurity.md](CompanionEncryptionAndSecurity.md).
- **user_id** should match the **logged-in user** when the Companion registers the token. One user can have **multiple tokens** (multiple devices); each device registers with the same user_id. Only one user is logged in per app instance at a time.

---

## 5. Summary

| Platform   | Token source        | Core sends via |
|-----------|---------------------|----------------|
| **iOS**   | APNs device token    | **APNs** (HTTP/2, .p8 key) |
| **Android** | FCM token         | **FCM** (Firebase Admin SDK). In China, Google/FCM is often blocked; the app does not rely on FCM for core features and will not crash — push for reminders when app is killed/background simply won't arrive; users still get messages and reminders when they open the app (inbox, chat history sync). |

| Component  | Responsibility |
|------------|----------------|
| **Companion** | iOS: get APNs token, send to Core with platform "ios". Android: get FCM token, send with platform "android". Register token with **current logged-in user_id**; re-register when user changes (logout/login). |
| **Core**   | Store tokens **per user_id** (multi-user); when deliver_to_user runs (no WebSocket), send push to all tokens for that user. One user can have many tokens (multi-device). |

**Multi-user:** Push is scoped by user_id; each user gets only their notifications. **One login at a time:** The app has a single active user per session; token is tied to that user until re-registration. **Multi-device:** One user can have multiple devices; each device registers its token under the same user_id.

With this, reminders (and other proactive messages) can reach the user even when the Companion app has been killed by the system.

---

## 6. Android FCM verification checklist

After setting up the app in the Firebase Console and adding **google-services.json**:

| Step | What to check |
|------|----------------|
| **Companion** | `android/app/google-services.json` present; package name in Firebase matches `com.homeclaw.homeclawApp`. |
| **Companion** | Gradle: `android/settings.gradle.kts` has `com.google.gms.google-services` plugin; `android/app/build.gradle.kts` applies it. Build succeeds. |
| **Companion** | App has Core **base URL** and **API key** set (Settings). Token registration uses same auth as `/inbound`. |
| **Companion** | On Android, after login or opening a chat, `registerPushTokenWithCore(userId)` runs; no errors in logs. |
| **Core** | `config/core.yml` → `push_notifications.enabled: true` and `push_notifications.fcm.credentials_path` set to your **service account JSON** path (or `GOOGLE_APPLICATION_CREDENTIALS` env). |
| **Core** | `pip install firebase-admin` (in `requirements.txt`). Core starts without FCM errors. |
| **Core** | When a reminder fires and there is no WebSocket for that user, Core calls `send_push_to_user`; Android tokens get FCM. Check Core logs for "deliver_to_user: sent … push(es)". |
| **E2E** | Create a reminder in Core for the logged-in user; kill or background the Companion app; reminder time passes → device receives the notification. |
