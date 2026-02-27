# HomeClaw clients

This folder holds **clients** that connect to **HomeClaw Core**: companion apps (mobile, desktop) and command-line tools. All of them talk to Core over HTTP and/or WebSocket; they do not depend on a specific tunnel (Tailscale, Cloudflare, etc.) — that is a deployment choice for exposing Core.

---

## What lives here

| Client | Description | Status |
|--------|-------------|--------|
| **Flutter** | Cross-platform companion app (iOS, Android, macOS, Windows, Linux). Chat with Core, settings for URL + API key, Scan QR to connect. | Implemented in `HomeClawApp/`. Run `flutter run -d macos|windows|linux|android|ios`. |
| **CLI** | Command-line tool to send messages to Core and print reply. | Implemented in `cli/`. Run `python homeclaw_cli.py chat "message"`. |

---

## How clients connect to Core

- **Base URL:** Core’s HTTP server (from `config/core.yml`: `host`, `port`; default `http://127.0.0.1:9000`).
- **Endpoints used by clients:**
  - **POST /inbound** — Send a user message and get a sync response. Payload: `user_id`, `text`, optional `channel_name`, `images`, `files`, etc. When `auth_enabled: true`, send `X-API-Key` or `Authorization: Bearer <key>`.
  - **WebSocket /ws** — Interactive chat: send messages, receive streamed or final replies. Same auth as `/inbound` when enabled.
  - **GET /api/sessions** — List sessions (if enabled in Core).
  - **POST /api/plugins/llm/generate** — Direct LLM call (e.g. for plugins); auth when enabled.

So: every client only needs a **Core URL** (e.g. `http://127.0.0.1:9000`) and optionally an **API key**. No Tailscale or Cloudflare SDK inside the app — use Tailscale/Cloudflare (or any tunnel) only to expose Core and then point the client at the resulting URL.

---

## Remote access (Tailscale, Cloudflare Tunnel, etc.)

- **Local:** Core URL = `http://127.0.0.1:9000` (or your `host:port` from `core.yml`).
- **Remote:** Expose Core with Tailscale Serve/Funnel, Cloudflare Tunnel, ngrok, or SSH port-forward. Then set Core URL in the client to that base URL (e.g. `https://your-machine.tailnet-name.ts.net` or `https://your-tunnel.trycloudflare.com`). If Core has `auth_enabled: true`, configure the same API key in the client.

See **docs_design/HomeClawCompanionConnectivity.md** for a short comparison of options. For **how iOS, Android, and desktop connect when Core runs remotely** (Tailscale, QR pairing, SSH), see **docs_design/RemoteConnectionIOSAndroidDesktop.md**.

---

## Flutter app

- **Location:** `clients/HomeClawApp/`
- **Targets:** macOS, Windows, Android, iOS (Linux can be added later).
- **Features:** Settings (Core URL, API key); chat screen (send message, show reply via POST /inbound).
- **Run:** See `HomeClawApp/README.md`. One-time: `flutter create .` then `flutter pub get`; then `flutter run -d macos` (or windows/android/ios).

---

## CLI

- **Location:** `clients/cli/`
- **Purpose:** Send a message to Core, print reply. Core URL via `HOMECLAW_CORE_URL` or `--url`; API key via `HOMECLAW_API_KEY` or `--api-key`.
- **Run:** `pip install -r requirements.txt` then `python homeclaw_cli.py chat "Your message"`. See `cli/README.md`.

---

## Summary

- **channels/** — Inbound channels (e.g. WhatsApp Web, Telegram) that receive messages from the outside and forward to Core.
- **clients/** — Outbound-facing clients (Flutter app, CLI) that the user runs to talk to Core. All connect to the same Core URL; tunnel choice is up to deployment.
