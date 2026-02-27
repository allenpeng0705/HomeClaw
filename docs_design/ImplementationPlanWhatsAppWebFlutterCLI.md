# Implementation Plan: WhatsApp Web, Flutter App, and CLI

This document is the master plan and step-by-step log for implementing (1) the **whatsappweb** channel with an optional Baileys bridge, (2) the **Flutter** companion app for Mac, Windows, Android, and iOS, and (3) a **CLI** tool that talks to HomeClaw Core. Any blockers or follow-up items are documented at the end.

---

## Goals

| Component | Goal |
|-----------|------|
| **WhatsApp Web** | Channel receives messages from a bridge (Baileys), forwards to Core, returns reply to bridge so it can send back to WhatsApp. Optional: include a runnable Node.js bridge in the repo. |
| **Flutter app** | Cross-platform client: Mac, Windows, Android, iOS. Connect to Core (URL + optional API key), send message, show reply. Document build/run per platform. |
| **CLI** | Command-line tool: send message to Core, print reply; optional status/sessions. |

All connect to **HomeClaw Core** (POST /inbound or WebSocket /ws). Core URL is configurable; remote access via Tailscale/Cloudflare is deployment-only.

---

## Step 1: WhatsApp Web channel (Python)

- **Status:** Done (existing).
- **Location:** `channels/whatsappweb/`
- **What it does:** FastAPI app with `POST /webhook`. Body: `user_id`, `text`, optional `images`/`files`. Forwards to Core `POST /inbound` with `channel_name=whatsappweb`, returns Core’s `{ "text": "..." }`.
- **Run:** `python -m channels.run whatsappweb` (port 8010 by default). Core URL from `channels/.env`.
- **Docs:** README.md, ARCHITECTURE.md, CONFIG.md in `channels/whatsappweb/`.

---

## Step 2: WhatsApp Web bridge (Node.js + Baileys) [optional]

- **Purpose:** A small Node app that keeps a WhatsApp Web session (Baileys), receives messages from WhatsApp, POSTs them to the whatsappweb channel’s `/webhook`, and sends the response back to WhatsApp.
- **Location:** `channels/whatsappweb/bridge/`
- **Steps:**
  1. Add `bridge/package.json` with Baileys and axios/node-fetch.
  2. Add `bridge/index.js` (or `src/index.js`): init Baileys, QR or session auth, on message received → POST to `CHANNEL_URL/webhook` (e.g. `http://127.0.0.1:8010/webhook`), take `response.text` and send via Baileys to the chat.
  3. Document: `CHANNEL_URL` env (channel base URL), auth dir for session storage, first-run QR login.
- **Blocker/note:** If Baileys API or session handling is complex, document “manual steps” (run bridge, scan QR, restart) in bridge/README.md for you to finish when back.

---

## Step 3: Flutter app (Mac, Windows, Android, iOS)

- **Location:** `clients/flutter/`
- **Steps:**
  1. Create Flutter project: `flutter create .` in `clients/flutter/` (or create parent and move).
  2. Add dependencies: `http` and/or `web_socket_channel` in `pubspec.yaml`.
  3. Implement **Core service:** base URL + optional API key; `POST /inbound` with `user_id`, `text`; parse `{ "text": "..." }`. Optionally support WebSocket `/ws` for streaming later.
  4. **Settings screen:** Store Core URL and API key (e.g. shared_preferences or flutter_secure_storage). Default URL e.g. `http://127.0.0.1:9000`.
  5. **Chat screen:** Text field + send button; on send, call Core, show reply in a list or text area.
  6. **Platforms:** Ensure macOS/Windows are enabled in the project. Document: `flutter run -d macos`, `flutter run -d windows`, `flutter run -d android`, `flutter run -d ios` (and any signing/entitlements needed).
- **Docs:** Update `clients/flutter/README.md` with: how to open project, set Core URL, build/run for each platform, and any known issues (e.g. macOS network entitlements, Android cleartext if needed).

---

## Step 4: CLI tool

- **Location:** `clients/cli/`
- **Implementation:** Python 3 script (or small Go binary). Read Core URL from env `HOMECLAW_CORE_URL` (default `http://127.0.0.1:9000`) and optional `HOMECLAW_API_KEY`. Subcommand: `chat "message"` → POST /inbound, print reply text.
- **Steps:**
  1. Add `clients/cli/homeclaw_cli.py` (or `main.py`) with argparse: `chat <text>`, `--url`, `--api-key`.
  2. Use `httpx` or `requests`: POST JSON `{"user_id": "cli", "text": "<text>"}` to `<url>/inbound`, headers for API key if set. Print `response.json().get("text", "")` or error.
  3. Add `requirements.txt` (e.g. httpx) and README with usage.
- **Optional later:** `status`, `sessions` subcommands calling Core APIs.

---

## Step 5: Documentation and blocker list

- **Summary doc:** Short summary of what was implemented and how to run each piece (for you when you return).
- **Blocker / follow-up doc:** Any incomplete items (e.g. “Baileys QR flow needs testing”, “Flutter iOS signing”, “CLI install as global command”) so you can handle them when back.

---

## Implementation order

1. ✅ Plan (this doc)  
2. ✅ WhatsApp Web bridge (Node.js) in `channels/whatsappweb/bridge/` — implemented (Baileys; see bridge/README.md)  
3. ✅ Flutter app: `clients/HomeClawApp/` — Core client, settings, chat UI, README (run `flutter create .` once to generate platform folders)  
4. ✅ CLI: `clients/cli/homeclaw_cli.py` + requirements.txt + README  
5. ✅ Summary + blocker doc: `docs_design/ImplementationSummaryAndFollowUp.md`  
