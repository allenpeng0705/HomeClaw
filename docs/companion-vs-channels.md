# Companion app vs Channels

HomeClaw lets you talk to the same Core from many places: the **Companion app** (Flutter), **WebChat**, **Telegram**, **Discord**, **email**, and other **channels**. This page explains the difference between the **Companion app** and **channels**, and how Core handles each.

---

## Short answer

| | **Companion app** | **Channels** |
|---|-------------------|--------------|
| **What it is** | A **client app** (Flutter) you run on your phone or desktop. | **Server-side processes** that bridge an external platform (Telegram, Discord, WebChat server, etc.) to Core. |
| **How it reaches Core** | **Directly**: the app calls Core’s HTTP/WebSocket API (e.g. **POST /inbound**) from the device. | **Indirectly**: a channel process runs on your side, receives messages from the platform (e.g. Telegram servers), then forwards them to Core (e.g. **POST /inbound** or **POST /process**). |
| **Who runs what** | You run the app on your device; Core runs on your server/PC. | You run a **channel process** (e.g. `python -m channels.run telegram`) that talks to both the platform and Core. |
| **Identity** | The app sends a **user_id** (e.g. `companion` or your name) and **channel_name: "companion"**. That user must be in **config/user.yml**. | The channel sends a **user_id** from the platform (e.g. `telegram_123`, `matrix:@user:domain`) and **channel_name** (e.g. `telegram`, `discord`). Those identities must be listed in **config/user.yml** under the right user’s `im` / `email` / `phone`. |
| **Management** | The app can call **config API** (e.g. GET/PATCH core.yml, users) and **Manage Core** from the UI. | Channel processes typically only forward chat; they do not manage config. |

So: the **Companion app** is a **direct client** to Core. **Channels** are **bridge processes** between an external platform and Core.

---

## How Core treats them

Core does **not** treat the Companion app as a special “non-channel.” From Core’s point of view:

1. **Same entrypoint for chat**  
   Both the Companion app and channel processes send messages to Core via **POST /inbound** (or, for some channels, **POST /process**). The payload includes **user_id**, **channel_name**, **text**, and optional media.

2. **Same permission model**  
   Core checks **config/user.yml**: the **user_id** (and, for channels, the platform identity in `im` / `email` / `phone`) must be allowed. So you add:
   - For **Companion**: a user with that **user_id** in **user.yml** (e.g. `id: companion`, or your name with `im: ['companion']` if you use that as identity).
   - For **Telegram**: a user whose **im** list includes the Telegram identity (e.g. `telegram_123456789`).

3. **Same session and memory**  
   Sessions and memory are keyed by **user_id** and **channel_name** (and optionally app_id, account_id). So:
   - Companion with `user_id: alice` and `channel_name: companion` → one session/memory for “alice on companion.”
   - Telegram with `user_id: telegram_123` and `channel_name: telegram` → one session/memory for that user on Telegram.  
   Core does not mix them unless you use the same **user_id** and design for it.

4. **Same processing**  
   Core runs the same pipeline: permission → orchestrator → tools/plugins/skills → LLM → reply. The reply is then:
   - **Companion**: returned in the HTTP response to the app; the app displays it.
   - **Channels**: returned to the channel process (in the HTTP response or via a response queue); the channel sends it back to the platform (e.g. Telegram, Discord).

So the **only** difference in “how we handle them” is **who sends the request and who receives the reply**:

- **Companion**: Your app sends the request and gets the reply in the same HTTP (or WebSocket) call.
- **Channels**: The **channel process** sends the request to Core and gets the reply, then the channel process delivers the reply to the user on the platform (Telegram, email, etc.).

---

## When to use which

- **Companion app**  
  Use when you want one app (phone, desktop) to chat with Core and optionally manage config (core.yml, user.yml). No bot or platform account needed; you only need Core URL and optional API key. Good for personal use and remote access (e.g. with Tailscale or Cloudflare Tunnel).

- **Channels**  
  Use when you want to talk to Core from **Telegram**, **Discord**, **email**, **WebChat** (browser), etc. You run the corresponding channel process (and set bot tokens, etc.); the channel bridges that platform to Core. Good for multi-user or platform-specific access (e.g. family on Telegram, team on Discord).

You can use **both**: same Core, same memory and config; some users use the Companion app, others use Telegram or WebChat. Each user identity is in **user.yml** and gets the same Core behavior.
