# WhatsApp Web Channel (HomeClaw)

This channel connects **HomeClaw Core** to **WhatsApp** using the **WhatsApp Web** protocol. It is named **whatsappweb** to distinguish it from the existing **whatsapp** channel (which uses the Neonize/WhatsApp Multi-Device stack). WhatsApp Web typically uses a library such as [Baileys](https://github.com/WhiskeySockets/Baileys) (Node.js) to maintain a browser-like session and send/receive messages.

**Location:** `channels/whatsappweb/`  
**Run:** `python -m channels.run whatsappweb` (from repo root). Core URL is taken from `channels/.env` (`core_host`, `core_port`, or `CORE_URL`).

---

## Purpose

- Receive messages from WhatsApp (via a WhatsApp Web bridge) and forward them to **Core** (`POST /inbound` or `/process`).
- Send replies from Core back to WhatsApp (via the same bridge).
- Support optional **QR login** / session storage so the bridge can reconnect without re-pairing.

---

## Architecture (summary)

1. **Bridge (external or future):** A WhatsApp Web client (e.g. Baileys in Node.js) keeps a session with WhatsApp servers, receives messages, and POSTs them to this channel’s **ingestion endpoint** (e.g. `/webhook` or `/message`). The channel forwards to Core. Core’s response (sync from `/inbound` or async via `/get_response`) is returned to the bridge, which then sends the reply over WhatsApp.
2. **This channel:** Provides the HTTP endpoint and Core connectivity; does not implement the WhatsApp Web protocol itself. Optionally, a small Node (or Python) **bridge** can live in this folder or in a sibling repo that POSTs to this channel.
3. **Core:** Unchanged. Uses `channel_name=whatsappweb` for session/routing and outbound delivery.

See **ARCHITECTURE.md** in this folder for detailed flow and **CONFIG.md** for config keys.

---

## Enabling and running

- Add **whatsappweb** to the list of channels you run (e.g. `python -m channels.run whatsappweb`).
- Ensure **Core** is running and reachable. Set `core_host`, `core_port`, or `CORE_URL` in `channels/.env`.
- Ensure `user_id` values you send (e.g. WhatsApp JID or phone) are allowed in `config/user.yml` if you use permission checks.
- A **Baileys bridge** is included in **`bridge/`**: run `cd bridge && npm install && node index.js`. Set `CHANNEL_URL` (default `http://127.0.0.1:8010`). See **bridge/README.md**.

---

## Auth and session (when using a bridge)

- Session (credentials) for WhatsApp Web are **not** stored in HomeClaw by default. The **bridge** (e.g. Baileys) owns auth: QR login, pairing, and credential storage (e.g. a folder or DB). This channel only receives already-decoded messages from the bridge and forwards to Core.
- If you run a bridge in this repo later, use a dedicated directory (e.g. `channels/whatsappweb/auth/` or a path from config) for credentials and keep it out of version control.

---

## Main entry points

| Item | Description |
|------|-------------|
| `channel.py` | FastAPI app, BaseChannel (or minimal HTTP), registration with Core, `main()`. |
| **Ingestion** | POST endpoint (e.g. `/webhook` or `/message`) that accepts a minimal payload (`user_id`, `text`, optional `images`/`files`) and forwards to Core `/inbound`. |
| **Response** | Sync: response body from `/inbound` is returned to the bridge. Async: Core POSTs to this channel’s `/get_response`; the channel then forwards to the bridge (bridge must be able to receive callbacks or poll). |

---

## Config and environment

- **Core URL:** `channels/.env`: `core_host`, `core_port`, or `CORE_URL`.
- **Channel host/port:** Passed when starting the channel (e.g. env `WHATSAPPWEB_HOST`, `WHATSAPPWEB_PORT` or in a small config file). Defaults can be set in `channel.py`.
- **Optional:** `channels/whatsappweb/.env` for channel-specific options (e.g. auth dir for a future bridge).

See **CONFIG.md** for a full list.

---

## Troubleshooting

- **Core unreachable:** Check `channels/.env` and that Core is running on `core_host:core_port`.
- **401/403 from Core:** If Core has `auth_enabled: true`, the channel (or bridge) must send the required API key when calling Core.
- **No reply in WhatsApp:** Ensure the bridge is sending the reply from this channel back to WhatsApp; check channel logs and bridge logs.

---

## Related files

- **Channel code:** `channel.py`
- **Architecture:** `ARCHITECTURE.md`
- **Config:** `CONFIG.md`
- **Channels runner:** `channels/run.py` (includes `whatsappweb` in `CHANNELS`)
