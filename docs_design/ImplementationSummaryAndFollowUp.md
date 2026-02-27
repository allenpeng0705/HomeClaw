# Implementation Summary: WhatsApp Web, Flutter, CLI

Short summary of what was implemented and how to run it. **Follow-up / blockers** for when you’re back are at the end.

---

## 1. WhatsApp Web channel + bridge

### Channel (Python)

- **Where:** `channels/whatsappweb/`
- **Run:** From repo root: `python -m channels.run whatsappweb`
- **Config:** Core URL in `channels/.env` (`core_host`, `core_port`, or `CORE_URL`). Channel listens on port **8010** by default (`WHATSAPPWEB_PORT`).
- **API:** `POST /webhook` with body `{ "user_id": "...", "text": "..." }` → forwards to Core `/inbound` with `channel_name=whatsappweb`, returns `{ "text": "..." }`.

### Bridge (Node.js + Baileys)

- **Where:** `channels/whatsappweb/bridge/`
- **Setup:** `cd channels/whatsappweb/bridge && npm install`
- **Run:** `CHANNEL_URL=http://127.0.0.1:8010 node index.js`
- **First run:** Scan QR in terminal with WhatsApp (Linked devices). Session is saved in `auth/` (add `auth/` to `.gitignore` if not already).
- **Flow:** WhatsApp message → bridge → POST to channel `/webhook` → channel → Core → reply back to bridge → bridge sends reply to WhatsApp.

**Docs:** `channels/whatsappweb/README.md`, `channels/whatsappweb/bridge/README.md`, `channels/whatsappweb/ARCHITECTURE.md`, `CONFIG.md`.

---

## 2. Flutter companion app

- **Where:** `clients/HomeClawApp/`
- **What:** Chat UI + Settings (Core URL, API key). Sends message via `POST /inbound`, shows reply.
- **Platforms:** Mac, Windows, Android, iOS (Flutter). Linux can be added later.

### Run (after one-time setup)

1. **Generate platform projects** (required once; needs Flutter SDK):
   ```bash
   cd clients/HomeClawApp
   flutter create .
   flutter pub get
   ```
2. **Run by platform:**
   - macOS: `flutter run -d macos`
   - Windows: `flutter run -d windows`
   - Android: `flutter run -d android`
   - iOS: `flutter run -d ios`
3. In the app: open **Settings**, set **Core URL** (e.g. `http://127.0.0.1:9000`), save. Then use the chat screen.

**Docs:** `clients/HomeClawApp/README.md` (includes Android cleartext HTTP note and iOS/macOS signing hints).

---

## 3. CLI tool

- **Where:** `clients/cli/`
- **Setup:** `pip install -r requirements.txt` (httpx)
- **Run:**
  ```bash
  python homeclaw_cli.py chat "Hello"
  HOMECLAW_CORE_URL=http://127.0.0.1:9000 python homeclaw_cli.py chat "Your message"
  python homeclaw_cli.py chat --api-key YOUR_KEY "Hello"
  ```

**Docs:** `clients/cli/README.md`.

---

## 4. Master plan

- **Where:** `docs_design/ImplementationPlanWhatsAppWebFlutterCLI.md`
- **Content:** Step-by-step plan and implementation order for whatsappweb, bridge, Flutter, and CLI.

---

## 5. Connectivity (remote access)

- **Doc:** `docs_design/HomeClawCompanionConnectivity.md`
- **Content:** How clients connect to Core (local URL, Tailscale, Cloudflare Tunnel, SSH). No SDK in app; only Core URL + optional API key.

---

# Follow-up / blockers (when you’re back)

Items that may need your attention or testing:

1. **Flutter: platform folders**  
   The Flutter app has `lib/` and `pubspec.yaml` only. You must run **`flutter create .`** inside `clients/HomeClawApp/` once to generate `android/`, `ios/`, `macos/`, `windows/`. Without this, `flutter run` will fail.

2. **Flutter: Android HTTP**  
   If you use a non-HTTPS Core URL (e.g. `http://192.168.x.x:9000`) on Android, you may need to allow cleartext (see `clients/HomeClawApp/README.md`). We didn’t add `network_security_config` or manifest changes so your project isn’t modified by default; add them if you need HTTP on Android.

3. **Flutter: iOS / macOS signing**  
   For real devices or release builds, configure signing in Xcode. macOS may need “Outgoing Connections” (or similar) in entitlements if the system blocks the app. We didn’t change entitlements; add if needed.

4. **Baileys bridge: API version**  
   The bridge uses `@whiskeysockets/baileys` (e.g. ^6.7.9). If Baileys changes exports or event names (e.g. `makeWASocket`, `messages.upsert`), update `channels/whatsappweb/bridge/index.js`. If you see “Cannot find module” or “ev.on is not a function”, check the [Baileys repo](https://github.com/WhiskeySockets/Baileys) and adjust the code.

5. **WhatsApp Web: user_id allowlist**  
   Core may require `user_id` to be in `config/user.yml` (IM permission). The bridge sends JID as `user_id` (e.g. `1234567890@s.whatsapp.net`). If Core rejects requests, add that id (or a mapping) to your user config.

6. **CLI: install as global command**  
   The CLI is run as `python homeclaw_cli.py chat "..."`. If you want a single command (e.g. `homeclaw chat "..."`), add a symlink or PATH entry as in `clients/cli/README.md`, or add a `pyproject.toml` and install with `pip install -e .` and an entry point.

7. **Optional: WebSocket /ws in Flutter and CLI**  
   Current implementation uses only `POST /inbound` (sync). For streaming or lower latency, you could add WebSocket `/ws` support in the Flutter app and/or a `cli ws` subcommand; not done in this pass.

If you hit any other issue (e.g. Core auth, channel port conflict, or Baileys QR not showing), check the READMEs in the relevant folder first; then fix or document and we can iterate.
