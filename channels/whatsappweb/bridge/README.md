# WhatsApp Web bridge (Baileys)

This Node.js app connects to WhatsApp via [Baileys](https://github.com/WhiskeySockets/Baileys), receives messages, forwards them to the HomeClaw **whatsappweb** channel, and sends the reply back to WhatsApp.

## Prerequisites

- **Node.js** 18+ and npm.
- **WhatsApp** account and phone to scan QR code (first run).
- **whatsappweb channel** running: `python -m channels.run whatsappweb` (default port 8010).
- **HomeClaw Core** running and reachable from the channel (set `channels/.env`: `core_host`, `core_port` or `CORE_URL`).

## Setup

```bash
cd channels/whatsappweb/bridge
npm install
```

## Environment

| Variable      | Description                                      | Default                |
|---------------|--------------------------------------------------|------------------------|
| `CHANNEL_URL` | Base URL of the whatsappweb channel              | `http://127.0.0.1:8010` |
| `AUTH_DIR`    | Directory for Baileys session (creds)           | `./auth`               |

## Run

1. Start the **whatsappweb channel** (from repo root):  
   `python -m channels.run whatsappweb`
2. Start the bridge:
   ```bash
   CHANNEL_URL=http://127.0.0.1:8010 node index.js
   ```
3. **First run:** Scan the QR code in the terminal with WhatsApp on your phone (Linked devices).
4. Session is saved in `AUTH_DIR`; next runs reconnect without QR.

## Flow

1. User sends a message in WhatsApp.
2. Bridge receives it (Baileys), extracts text and chat JID.
3. Bridge POSTs `{ "user_id": "<jid>", "text": "..." }` to `CHANNEL_URL/webhook`.
4. Channel forwards to Core `/inbound`; Core returns `{ "text": "..." }`.
5. Bridge sends that text back to the WhatsApp chat.

## Troubleshooting

- **"Channel POST failed"** — Ensure the whatsappweb channel is running and `CHANNEL_URL` is correct. Check channel logs.
- **"Core unreachable"** — Channel uses `channels/.env` for Core; ensure Core is running and env is set.
- **QR keeps appearing** — Delete `AUTH_DIR` and scan again; ensure no other process is using the same auth dir.
- **Baileys API errors** — If `makeWASocket` or event names changed in a newer Baileys version, update `index.js` (see [Baileys docs](https://github.com/WhiskeySockets/Baileys)).

## Security

- Keep `auth/` out of version control (add `auth/` to `.gitignore`). It contains session credentials.
