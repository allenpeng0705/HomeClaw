# WhatsApp Web Channel — Architecture and data flow (HomeClaw)

This document describes how the **whatsappweb** channel fits into HomeClaw: ingestion from a WhatsApp Web bridge, forwarding to Core, and sending replies back.

---

## High-level flow

```
WhatsApp (phone) ←→ Bridge (e.g. Baileys) ←→ channels/whatsappweb ←→ HomeClaw Core
```

- **Bridge:** External process (e.g. Node.js with Baileys) that maintains the WhatsApp Web session, receives messages from WhatsApp, and POSTs them to this channel. It also sends back to WhatsApp the replies it receives from the channel.
- **whatsappweb channel:** HTTP server that receives payloads from the bridge, forwards to Core (`/inbound` or `/process`), and returns or forwards Core’s response to the bridge.
- **Core:** Handles session, LLM, tools, plugins; returns text (and optional media) for the channel to deliver.

---

## Inbound (WhatsApp → Core)

1. User sends a message in WhatsApp.
2. **Bridge** receives it (e.g. via Baileys events), normalizes to a simple payload (e.g. `user_id`, `text`, optional `images`/`files`).
3. Bridge **POSTs** to this channel’s ingestion endpoint (e.g. `POST /webhook` or `POST /message`).
4. **Channel** maps the payload to Core’s **InboundRequest** (or PromptRequest) and POSTs to Core’s **`/inbound`** (or `/process`) with `channel_name=whatsappweb`.
5. Core processes the request (session, LLM, tools) and returns a response (sync JSON or async callback).
6. **Channel** returns the response to the bridge (sync: HTTP response body; async: channel receives Core’s POST to `/get_response` and notifies the bridge).
7. **Bridge** sends the reply to WhatsApp (e.g. via Baileys send message).

---

## Outbound (Core → WhatsApp)

- **Sync:** Core’s `/inbound` returns JSON with `text` (and optionally `images`/`files`). The channel returns this to the bridge in the HTTP response; the bridge sends it to WhatsApp.
- **Async:** Core POSTs to the channel’s **`/get_response`** with `AsyncResponse`. The channel looks up the original request (e.g. by `request_id` / `request_metadata`) and forwards the response data to the bridge. The bridge must then send that to the correct WhatsApp chat (using stored chat/JID from the original request).

---

## Session and identity

- **user_id:** Should uniquely identify the WhatsApp user or chat (e.g. JID like `1234567890@s.whatsapp.net` or a stable id used by the bridge). Core uses this for session scope (`session.dm_scope`), permissions (`config/user.yml`), and reply routing.
- **channel_name:** Always `whatsappweb` so Core and tools (e.g. `channel_send`) can target this channel.

---

## Optional: running the bridge inside HomeClaw

- The WhatsApp Web **protocol** (Baileys) is typically implemented in **Node.js**. A possible layout:
  - **Bridge:** `channels/whatsappweb/bridge/` (Node.js, Baileys), or a separate repo/process. It reads config (channel URL, auth dir), connects to WhatsApp, and forwards messages to `http://<channel_host>:<port>/webhook`.
  - **Channel:** This Python FastAPI app; no Baileys dependency. Just HTTP ingestion and Core forwarding.
- Credentials (QR login, session) are stored by the bridge (e.g. in `channels/whatsappweb/auth/` or a path from env); keep that path out of version control.

---

## Security

- Treat incoming payloads from the bridge as **trusted** only if the bridge runs in a controlled environment. If the ingestion endpoint is ever exposed (e.g. for a remote bridge), add auth (e.g. shared secret, API key).
- Core’s `auth_enabled` applies to `/inbound`; the channel must send the configured API key when calling Core if auth is enabled.
