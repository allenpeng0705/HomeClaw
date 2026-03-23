# Companion App

The **HomeClaw Companion** is a Flutter app for **Mac, Windows, iPhone, and Android**. It is the primary way to use HomeClaw — chat with your AI, manage your server, and install skills, all from one app.

---

## Why the Companion App

- **One app, all platforms** — Same Flutter codebase for desktop and mobile.
- **Direct connection** — The app talks to your HomeClaw Core over HTTP. No bot tokens, no third-party platform needed.
- **Full control** — Chat, manage config, install skills, switch models — without editing files or using SSH.

---

## What you can do

### Chat

Send text messages, attach images and files. The assistant replies using your configured LLM (cloud or local). Voice input and text-to-speech are supported.

### Friends

Each user has a **friends list** — different assistants with different personalities or capabilities. The default friend is "HomeClaw" (your main assistant). You can add **preset friends** for specific tasks:

| Friend | Preset | What it does |
|--------|--------|-------------|
| HomeClaw | *(default)* | General assistant with full tools |
| Reminder | `reminder` | Scheduling and reminders |
| Note | `note` | Note-taking |
| Cursor | `cursor` | Cursor Bridge — open projects, run agents on your dev machine |

**Dedicated model per friend (math, science, …):** In `config/friend_presets.yml`, add a preset with optional **`llm_ref`** (e.g. `local_models/your_id` or `cloud_models/Your-Cloud-Id`). In `user.yml`, add a friend with **`preset: math`** (or your preset name). That Companion friend then uses that model for the whole chat (overrides mix-mode route for that session). Use **`tools_preset: tutor`** for a light tool set (`time`, `sessions_spawn`, `models_list`, `web_search`). See comments in **`friend_presets.yml`** for commented **`math`** / **`science`** examples and [LLM catalog how-to](llm-catalog-howto.md).

Friends are configured in `config/user.yml` under each user's `friends:` list. The Companion App shows them so you can switch between assistants. See [Friends & Family](friends-and-family.md) for how to add friends and set up a family AI network.

### Manage Core

Edit **core.yml** and **user.yml** from the app — LLM settings, memory, tools, auth, users. No need to SSH or edit config files by hand.

### Skills (ClawHub)

Browse and install skills from **ClawHub** directly in the app. Skills are workflows the LLM can execute (e.g. summarize, research, translate).

### Canvas

An agent-driven UI viewer. The LLM can push live content (titles, text blocks, buttons) to a "second screen" in the app. Useful for status displays, choices, and simple forms. Requires the **homeclaw-browser** plugin.

---

## Get the Companion App

### Build from source (recommended)

The source is in `clients/HomeClawApp/` in the repo.

**Prerequisites:** [Flutter SDK](https://flutter.dev/docs/get-started/install) installed.

```bash
cd clients/HomeClawApp
flutter pub get
flutter run          # run on connected device or desktop
```

**Platform-specific:**

| Platform | Command | Notes |
|----------|---------|-------|
| **macOS** | `flutter run -d macos` | See [macOS permissions](#macos-permissions) below |
| **Windows** | `flutter run -d windows` | |
| **iPhone** | `flutter run -d ios` | Requires Xcode and a signing profile |
| **Android** | `flutter run -d android` | Requires Android Studio / SDK |

See `clients/HomeClawApp/README.md` for full build and release instructions.

### Install from TestFlight / App Store

If a TestFlight or store build is available, install it directly on your device.

---

## Connect to Core

The Companion App needs two things: your **Core URL** and (optionally) an **API key**.

### Same machine (localhost)

If the app and Core run on the same computer:

1. Start Core: `python -m main start`
2. In the app, go to **Settings** → set **Core URL** to `http://127.0.0.1:9000`
3. Start chatting.

### Same network (home Wi-Fi or Tailscale)

If Core runs on a different machine on your local network:

1. Find Core's IP (e.g. `192.168.1.100` or a Tailscale IP like `100.x.x.x`).
2. In the app, set **Core URL** to `http://192.168.1.100:9000`.

### Remote access (phone on cellular, laptop away from home)

Expose Core with a tunnel so the app can reach it from anywhere:

- **Scan to connect:** Core can show a QR code at `/pinggy` — scan it from the app's Settings to auto-fill the URL and API key.
- **Pinggy (built-in, fastest):** Set `pinggy.token` in `core.yml` and Core starts a tunnel automatically. Scan the QR code to connect. [Details →](remote-access.md#pinggy-built-in)
- **Cloudflare Tunnel:** Run `cloudflared tunnel --url http://127.0.0.1:9000`, then use the public URL in the app. [Details →](remote-access.md#cloudflare-tunnel)
- **ngrok:** Run `ngrok http 9000` for a quick public URL. [Details →](remote-access.md#ngrok)
- **Tailscale:** Install Tailscale on both machines. Use the Tailscale IP as Core URL. [Details →](remote-access.md#tailscale)

**Important:** When Core is reachable from the internet, enable auth in `config/core.yml`:

```yaml
auth_enabled: true
auth_api_key: "your-long-random-key"
```

Enter the same API key in the app's Settings.

---

## Companion App vs Channels

The Companion App and channels (Telegram, Discord, WebChat, email) are two ways to reach the same Core. You can use both at the same time — they share memory, config, and user identity.

| | Companion App | Channels |
|---|---|---|
| **What it is** | A client app on your device | Server-side bridge processes |
| **How it reaches Core** | Directly via HTTP/WebSocket | Channel process forwards messages |
| **Extra features** | Manage Core, install skills, Canvas | Platform-specific (e.g. Telegram groups) |
| **Setup** | Just set Core URL | Run a channel process + set bot tokens |

**When to use the Companion App:** Personal use, managing config, when you want one app for everything.

**When to use channels:** When you want to reach HomeClaw from Telegram, Discord, email, or a browser (WebChat). See [Channels](channels.md).

---

## Canvas setup

Canvas lets the LLM push live UI to a "second screen" in the app.

1. Ensure the **homeclaw-browser** plugin is running (Core can auto-start it).
2. In the app's **Settings**, set **Canvas URL** to `http://<host>:3020/canvas` (the plugin's port, not Core's).
3. Open Canvas from the app menu.
4. In Chat, ask the agent to "update the canvas" or "show something on the canvas."

If Core and the Canvas plugin run on different ports, both must be reachable from the app. For remote access, you may need two tunnels (one for Core, one for the plugin) or a reverse proxy. See [Remote access](remote-access.md) for details.

---

## macOS permissions

For chat-only use, the app typically needs no special permissions — just outgoing network access (enabled by default in Flutter macOS builds).

If you add features like voice input, notifications, or screen capture later, macOS will prompt for each capability. Tips:

- Use a real Apple Development certificate (ad-hoc signing resets permissions each build).
- Keep a consistent bundle ID (e.g. `ai.homeclaw.companion`).
- Run the app from a fixed location.
- If permission prompts stop appearing, reset with: `sudo tccutil reset Accessibility ai.homeclaw.companion`

For Flutter sandbox builds, ensure `com.apple.security.network.client` is `true` in `macos/Runner/Release.entitlements`. See [full macOS permissions reference](companion-app-macos-permissions.md).

---

## Tips

- **User must exist in Core:** Your user ID must be in `config/user.yml` (or added via Portal). The default companion user ID is `companion`.
- **Friends not updating?** Core stores users in TinyDB (`database/users.json`) after first migration from `user.yml`. To apply `user.yml` changes: stop Core, delete `database/users.json`, restart Core. Or manage friends from the Portal.
- **WebView on desktop:** Canvas uses an embedded WebView which may have a fixed frame on desktop. Use the "Open in browser" button for a resizable view.
