# How to write a new channel

This document describes **two ways** to add a new way for users to talk to HomeClaw: **(1) full channel** (like WeChat, Matrix, Tinode) and **(2) webhook/inbound based** (no new channel code in HomeClaw; your bot just POSTs to the Core or to the Webhook relay).

See **Channel.md** for user-facing channel usage and **Design.md** §3.2 for architecture.

---

## 1. Which method to use

| Method | When to use | Effort |
|--------|-------------|--------|
| **Full channel** | You need a **dedicated process** that owns the IM/protocol connection (e.g. WhatsApp Web client, Matrix client, IMAP polling). The channel receives messages from the platform, builds a **PromptRequest**, and either gets the reply **asynchronously** (Core POSTs to your `/get_response`) or **synchronously** (POST /local_chat). | Implement a **BaseChannel** subclass; register with Core; run as a separate process (e.g. `python -m channels.run <name>`). |
| **Webhook / inbound** | Your bot (Telegram, Discord, n8n, custom script) can **send one HTTP request per message**. You don’t need to add new code to HomeClaw: just POST to **Core `/inbound`** or to the **Webhook `/message`** with `{ "user_id", "text" }` and add **user_id** to `config/user.yml`. | No HomeClaw channel code. Write your bot to POST to Core or Webhook; add user_id to user.yml. Optionally add a small script under `channels/<name>/` that uses /inbound (e.g. `channels/telegram/`) so users can run `python -m channels.run telegram`. |

**Summary:** Use **full channel** when you must run a long-lived process that holds the connection to the IM (e.g. WhatsApp Web, Matrix, email IMAP). Use **webhook/inbound** when the platform can call you (webhook) or you can poll and then call Core (e.g. Telegram getUpdates → POST /inbound).

---

## 2. Method 1: Full channel (WeChat, Matrix, Tinode style)

A **full channel** is a **separate process** that:

1. Implements **BaseChannel** (registers with Core, exposes **POST /get_response** so Core can push replies).
2. Receives messages from the external system (IM, email, etc.), builds a **PromptRequest**, and sends it to the Core via **POST /process** (async: Core will later POST to your `/get_response`) or **POST /local_chat** (sync: reply in the same HTTP response).
3. Delivers the reply back to the user (send email, send IM message, etc.).

### 2.1 When to use

- The protocol requires a **long-lived connection** or **polling by a dedicated process** (e.g. WhatsApp Web session, Matrix client, IMAP polling for email).
- You want **async delivery**: Core processes the request and later POSTs the reply to your channel’s `/get_response` endpoint.

### 2.2 Steps

1. **Create a folder** under `channels/<YourChannel>/` (e.g. `channels/myim/`).

2. **Implement a subclass of BaseChannel** in `channels/<YourChannel>/channel.py`:
   - **Metadata**: Build a `ChannelMetadata` with `name`, `host`, `port`, and `endpoints` (e.g. `[{"path": "/get_response", "method": "POST"}]`).
   - **Register**: In `initialize()`, call `self.register_channel(...)` so the Core knows your host/port and can POST replies to you.
   - **Receive from platform**: Your code (polling, webhook, or client events) receives a user message; build a **PromptRequest** (see `base/base.py`: `request_id`, `channel_name`, `channelType`, `user_name`, `app_id`, `user_id`, `contentType`, `text`, `action`, `host`, `port`, `images`/`videos`/`audios`, `timestamp`, etc.).
   - **Send to Core**:
     - **Async**: Call `await self.transferTocore(request)`. Core returns 200 and will later POST an **AsyncResponse** to your `POST /get_response`. Implement **handle_async_response(response)** to deliver the reply to the user (e.g. send IM message).
     - **Sync**: Call `await self.localChatWithcore(request)` and get the reply text in the return value; then deliver it to the user.
   - **Shutdown**: On exit, call `self.deregister_channel(...)` (BaseChannel does this in `stop()`).

3. **Expose POST /get_response**: BaseChannel already adds `@self.app.post("/get_response")` that receives **AsyncResponse** and calls `handle_async_response`. Override **handle_async_response** in your subclass to send the reply to the user (e.g. SMTP for email, Matrix send message, etc.).

4. **Config**: Put `config.yml` (host, port) and optionally `.env` (credentials, Core URL) in your channel folder. Core URL can come from **channels/.env** (`core_host`, `core_port` or `CORE_URL`). BaseChannel’s `core_url()` uses `Util().get_channels_core_url()` which reads from `channels/.env`.

5. **Run**: Implement **main()** that creates your channel, sets up the FastAPI app, and runs `await channel.run()`. Then add your channel name to **channels/run.py** `CHANNELS` so users can run `python -m channels.run <name>`.

### 2.3 Key types and code locations

- **BaseChannel**: `base/BaseChannel.py` — `ChannelMetadata`, `register_channel`, `deregister_channel`, `transferTocore`, `localChatWithcore`, `POST /get_response`, `handle_async_response`, `run()`.
- **PromptRequest**: `base/base.py` — full schema (request_id, channel_name, channelType, user_name, app_id, user_id, contentType, text, action, host, port, images, videos, audios, timestamp).
- **AsyncResponse**: `base/base.py` — request_id, host, port, from_channel, request_metadata, response_data (Core sends this to your `/get_response`).
- **Example full channels**: `channels/matrix/`, `channels/tinode/`, `channels/wechat/`, `channels/whatsapp/`, `core/emailChannel/` or `channels/emailChannel/`.

### 2.4 Permission

Same as all channels: **config/user.yml**. Add the user identity (e.g. email, Matrix user id, phone number) under the appropriate field and set **permissions** (e.g. `IM`, `EMAIL`). The Core checks this before processing.

---

## 3. Method 2: Webhook / inbound (no new HomeClaw channel code)

With this method you **do not** implement a BaseChannel. Any bot (Telegram, Discord, Slack, n8n, your own script) can talk to HomeClaw by sending one HTTP request per message.

### 3.1 When to use

- The platform supports **webhooks** (Discord, Slack, etc. POST to your URL) or **polling** (Telegram getUpdates) and you can call an HTTP endpoint from your bot.
- You want minimal code: no BaseChannel, no registration, no `/get_response`. Just **POST** and get **{ "text": "..." }** back.

### 3.2 Two ways to send messages

| Target | Endpoint | Use when |
|-------|----------|----------|
| **Core directly** | `POST http://<core_host>:<core_port>/inbound` | Your bot can reach the Core (e.g. same machine, or Core exposed via Tailscale/SSH). |
| **Webhook relay** | `POST http://<webhook_host>:8005/message` | Core is not reachable (e.g. Core on home LAN; Webhook runs on a VPS or relay). The Webhook forwards to Core `/inbound`. |

Both accept the **same JSON body** and return **{ "text": "<reply>" }**.

### 3.3 Request and response

**Request (JSON)**

```json
{
  "user_id": "telegram_123456789",
  "text": "Hello, what's the weather?",
  "channel_name": "telegram",
  "user_name": "Alice"
}
```

- **user_id** (required): Identity you use for permission; must be allowed in **config/user.yml** (e.g. under **im** with **IM** permission). Examples: `telegram_<chat_id>`, `discord_<user_id>`.
- **text** (required): The user message.
- **channel_name** (optional): e.g. `"telegram"`.
- **user_name** (optional): Display name.

**Response**

```json
{ "text": "Here is the weather..." }
```

If Core is unreachable or returns an error, you may get `{"error": "...", "text": ""}`.

### 3.4 What you need to do

1. **Implement your bot** (outside or inside the repo):
   - Receive the user message (e.g. Telegram getUpdates, Discord webhook, Slack event).
   - POST to **Core `/inbound`** or **Webhook `/message`** with `{ "user_id", "text", "channel_name", "user_name" }`.
   - Send the returned `text` back to the user (e.g. Telegram sendMessage, Discord reply).

2. **Config**:
   - **config/user.yml**: Add **user_id** (e.g. `telegram_123456789`) under **im** for a user with **IM** permission (or leave permissions empty to allow all).
   - **Core or Webhook URL**: Your bot must know the Core URL (e.g. `http://127.0.0.1:9000`) or Webhook URL (e.g. `http://relay:8005`). For in-repo bots, use **channels/.env** (`core_host`, `core_port` or `CORE_URL`).

3. **Auth (optional)**: When Core is exposed on the internet, set **auth_enabled: true** and **auth_api_key** in `config/core.yml`; send **X-API-Key** or **Authorization: Bearer** with each request. See **docs/RemoteAccess.md**.

### 3.5 Example: Telegram bot (inbound)

The repo includes a minimal Telegram channel that uses **POST /inbound**:

- **Code**: `channels/telegram/channel.py` — long-poll **getUpdates**, for each message POST to **Core /inbound** with `user_id = telegram_<chat_id>`, then **sendMessage** with the reply.
- **Config**: `channels/telegram/.env` — `TELEGRAM_BOT_TOKEN`, and Core URL from **channels/.env**.
- **Run**: `python -m channels.run telegram`.

No BaseChannel; just a small script that bridges Telegram ↔ Core /inbound. Same pattern for **channels/discord/** and **channels/slack/**.

### 3.6 Example: Webhook relay

When the Core is only on your home LAN, run the **Webhook** on a host that can reach both the internet and the Core:

- **Run**: `python -m channels.run webhook` (listens on port 8005 by default).
- **Code**: `channels/webhook/channel.py` — FastAPI app; **POST /message** accepts the same JSON as `/inbound` and forwards to **Core /inbound**; returns the same `{ "text": "..." }`.
- Point your bot at `http://<webhook_host>:8005/message` instead of the Core. Set **channels/.env** so the Webhook can reach the Core (`core_host`, `core_port`).

---

## 4. Summary

| Method | Add code to HomeClaw? | Core API | Run |
|--------|----------------------|----------|-----|
| **Full channel** | Yes: BaseChannel subclass under `channels/<name>/` | POST /process (async) or POST /local_chat (sync); Core POSTs to your /get_response for async | `python -m channels.run <name>` (after adding to run.py) |
| **Webhook / inbound** | No (or optional small script under channels/ that calls /inbound) | POST /inbound or POST Webhook /message | Your bot; optionally `python -m channels.run telegram` etc. |

Both use **config/user.yml** for permission (user_id allowlist). For full channel, see **base/BaseChannel.py** and **channels/matrix/** or **channels/whatsapp/**. For inbound, see **channels/telegram/channel.py** and **channels/webhook/channel.py**.

---

## 5. References

- **Channel.md** — User guide: configuration, channels list, troubleshooting.
- **Design.md** §3.2 — Channels architecture, full vs minimal, Core endpoints.
- **docs/RemoteAccess.md** — Auth for /inbound and /ws when exposing Core.
- **channels/README.md** — List of channels and how to run them.
