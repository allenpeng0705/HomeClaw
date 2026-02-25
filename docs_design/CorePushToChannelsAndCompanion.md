# Core push to channels and Companion

Core can **push messages proactively** to channels and the Companion app (cron, reminders, record_date follow-ups, async inbound result). Channels and Companion tell Core how to reach them; Core then delivers when needed.

---

## 1. Scenarios

1. **Cron** – Recurring task (e.g. "remind me every day at 9am") runs at the scheduled time; Core pushes the message to the user (Companion + channel).
2. **One-shot reminders** – "Remind me in 5 minutes" or "remind me tomorrow at 9am"; when the time comes, Core pushes to the user.
3. **Recorded dates** – User says "my birthday is March 15"; Core records it and can schedule a reminder (day before / on day); when it fires, Core pushes.
4. **Async inbound** – Client sends POST /inbound with `async: true` (and optional `push_ws_session_id`); Core returns 202 and processes in background; when done, Core pushes the result to the client’s WebSocket so the client doesn’t need to poll.
5. **Connection-close workaround** – Proxies (e.g. Cloudflare) may close long-lived HTTP responses; using async + push or stream + heartbeat avoids that.

---

## 2. How Core knows where to push

### Companion (and any client that holds a WebSocket)

1. Client opens **WebSocket** to Core: `wss://core-host/ws` (with auth: query `?api_key=...` or headers).
2. Core sends **`{"event": "connected", "session_id": "<uuid>"}`**.
3. Client sends **`{"event": "register", "user_id": "<user_id>"}`** so Core can map this connection to a user.
4. Core stores **session_id → WebSocket** and **session_id → user_id**.
5. When Core needs to push to that user (cron, reminder, async result), it looks up WebSockets registered for that user_id and sends **`{"event": "push", "source": "reminder"|"cron"|"push", "text": "...", "images": [...]}`** or **`{"event": "inbound_result", "request_id": "...", "text": "...", ...}`** for async inbound.

So: **Core does not initiate a connection to the Companion.** The Companion (or channel bridge) opens the WebSocket; Core uses that existing connection to push.

### Channels (HTTP callback)

- Today, channels are usually **request–response**: user sends message → channel forwards to Core → Core replies in the same HTTP response. For **proactive** push (cron/reminder), Core uses **last-channel** data: it has stored the last channel’s host/port and POSTs the message to that channel’s `/get_response` (or equivalent). So the “channel” that last talked to Core gets the push.
- For **per-session** delivery (e.g. multiple users), cron/remind_me can pass **channel_key** (e.g. `app_id:user_id:session_id`); Core looks up that key in the last-channel store and sends there.
- **Alternative (future):** A channel bridge could open a WebSocket to Core and register `user_id` (like the Companion); then Core pushes over that WebSocket. Same protocol as Companion.

---

## 3. Core API

### `deliver_to_user(user_id, text, images=None, channel_key=None, source="push")`

- **WebSocket:** For every session_id where `user_id` is registered, send a **push** event (text, images, source).
- **Channel:** If `channel_key` is set, call **`send_response_to_channel_by_key(channel_key, text)`**. Otherwise call **`send_response_to_latest_channel(text)`**.

Used by TAM (cron, one-shot reminder, record_date) and any code that needs to push to a user.

### WebSocket events (server → client)

| Event             | When                    | Payload |
|-------------------|-------------------------|--------|
| `connected`       | Right after accept      | `session_id` |
| `registered`      | After client sent `register` | `user_id` |
| `push`            | Proactive message (cron, reminder) | `source`, `text`, `images`? |
| `inbound_result`  | Async /inbound finished | `request_id`, `ok`, `text`, `images`? |

### WebSocket events (client → server)

| Event      | Purpose |
|------------|--------|
| `register` | Tell Core this connection is for `user_id` (so push goes to this socket). |
| (none)     | Normal chat: `user_id`, `text`, optional media → Core processes and replies. |

---

## 4. TAM integration

- **remind_me** and **cron_schedule** tools get **user_id** (and **channel_key** for per-session) from the request context and pass them into TAM.
- **One-shot reminders** are stored with **user_id** and **channel_key** (DB columns on `homeclaw_tam_one_shot_reminders`). When a reminder fires, TAM calls **`deliver_to_user(user_id, message, channel_key=channel_key, source="reminder")`**.
- **Cron jobs** store **user_id** and **channel_key** in **params**. When a cron task runs, it calls **`send_reminder_to_channel(message, params)`**, which uses **`deliver_to_user(user_id, message, channel_key=channel_key, source="cron")`** when Core has that method.
- **record_date** → scheduled reminders use **system_user_id** as **user_id** when calling **schedule_one_shot**.

---

## 5. Companion app

- For **remote Core**, the app opens a WebSocket to Core, receives **session_id**, sends **`register`** with the current **user_id** (from the message being sent), and uses **push_ws_session_id** for async /inbound so Core can push the reply.
- The app exposes **`pushMessageStream`**: when Core sends **`event: "push"`**, the app adds the payload to this stream; the UI can subscribe and show proactive messages (cron, reminders) in chat or as notifications.

---

## 6. Summary

| Scenario           | Who initiates      | How Core delivers |
|--------------------|--------------------|-------------------|
| Cron / reminder    | Core (scheduler)   | `deliver_to_user` → WebSocket(s) for user_id + channel by channel_key |
| Async /inbound     | Client (POST 202)  | Push **inbound_result** on WebSocket for **push_ws_session_id** |
| Connection timeout | Client (async or stream) | Short POST + poll, or stream + heartbeat, or push over WebSocket |

Channels and Companion “tell” Core how to send to them by **holding a WebSocket and registering user_id**, or (channels) by being the **last channel** (and optional **channel_key**). Core then pushes directly for all the scenarios above.
