# HomeClaw — Channels Guide

Channels are how users (or bots) reach your HomeClaw Core. This document has two parts: **Part I for users** (how to use and configure channels), **Part II for developers** (design, comparison with other agent, and improvements).

**Other languages / 其他语言 / 他の言語 / 다른 언어:** [简体中文](Channel_zh.md) | [日本語](Channel_jp.md) | [한국어](Channel_kr.md)

---

# Part I — For Users

## 1. What are channels?

A **channel** is a way to talk to your home Core:

- **From your phone or elsewhere**: Use Email, Matrix, WeChat, WhatsApp, or a bot (e.g. Telegram) that forwards messages to the Core.
- **From the same machine**: Use the CLI in the terminal, or (in the future) a WebChat in the browser.

All channels use the same Core and the same permission list: you allow who can talk to the assistant in `config/user.yml`.

---

## 2. Common configuration

### 2.1 Allowing who can talk (required for IM and bots)

Edit **`config/user.yml`**. Each user has:

- **name**: Display name.
- **email**, **im**, **phone**: Identifiers that the Core matches to the incoming message (e.g. your email address, or `telegram_123456789`).
- **permissions**: Which channel types this user can use: `EMAIL`, `IM`, `PHONE`, or leave empty to allow all.

**Example: allow one person by email and one by Telegram**

```yaml
users:
  - name: me
    email: ["me@example.com"]
    im: ["telegram_123456789"]
    permissions: [EMAIL, IM]
  - name: HomeClaw
    email: []
    im: []
    permissions: []
```

- For **inbound-style bots** (Telegram, Discord, etc.), use **im** with an id like `telegram_<chat_id>` or `discord_<user_id>`, and include `IM` in **permissions** (or leave permissions empty to allow all).
- For **email** channel, put the allowed addresses in **email** and add `EMAIL` (or leave permissions empty).

### 2.2 Where the Core is (for channel processes)

Channel processes need to know the Core’s address. Set **`channels/.env`**:

```env
core_host=127.0.0.1
core_port=9000
mode=dev
```

Use your machine’s IP or hostname if channels run on another machine.

---

## 3. Channels you can use

**All supported channels**

| Channel | Type | Run |
|---------|------|-----|
| **CLI** | In-process (local_chat) | `python main.py` |
| **Email** | Full (BaseChannel) | Start separately; see §3.2. Email code: `core/emailChannel/` or `channels/emailChannel/`. |
| **Matrix, Tinode, WeChat, WhatsApp** | Full (BaseChannel) | `python -m channels.run matrix` (or tinode, wechat, whatsapp) |
| **Telegram, Discord, Slack** | Inbound (POST /inbound) | `python -m channels.run telegram` (or discord, slack) |
| **Google Chat, Signal, iMessage, Teams, Zalo, Feishu, DingTalk, BlueBubbles** | Inbound / HTTP / webhook | `python -m channels.run google_chat` (or signal, imessage, teams, zalo, feishu, dingtalk, bluebubbles) |
| **WebChat** | WebSocket /ws | `python -m channels.run webchat` |
| **Webhook** | Relay (forwards to Core /inbound) | `python -m channels.run webhook` |

**Auth (when exposing Core on the internet):** Set **auth_enabled: true** and **auth_api_key** in `config/core.yml`; then **POST /inbound** and **WebSocket /ws** require **X-API-Key** or **Authorization: Bearer**. See **docs/RemoteAccess.md**.

---

### 3.1 CLI (terminal)

**Use**: Chat with the assistant from the same machine where the Core runs.

**How to run**

```bash
python main.py
```

Then type your message and press Enter. The Core runs in a background thread; replies are printed in the same terminal.

**Config**: None beyond Core and LLM config. Prefixes:

- `+` or `+` then text: store in memory.
- `?` or `？` then text: retrieve from memory.
- `quit`: exit. `llm`: list/set LLM.

**No need to add yourself in user.yml for local CLI** (the local sender is treated as allowed).

---

### 3.2 Email

**Use**: Send an email to your assistant; reply comes back by email. Good for “access from anywhere” without installing an IM app.

**Config**

1. **`config/email_account.yml`**: IMAP and SMTP server, port, and credentials for the account the Core will use (e.g. `assistant@mydomain.com`).
2. **`config/user.yml`**: Add your email in **email** and **permissions** (e.g. `EMAIL`) for the user you want to allow.
3. **`channels/emailChannel/config.yml`**: host/port for the email channel process (optional; defaults exist).

**Run**

Start the Core, then start the email channel (see your deployment or main docs). The channel polls IMAP and sends replies via SMTP.

---

### 3.3 Matrix, Tinode, WeChat, WhatsApp (full in-tree channels)

**Use**: Use your usual IM (Matrix, Tinode, WeChat, WhatsApp) to talk to the assistant. Each of these runs as a **separate process** that logs in (or connects) to the IM and forwards messages to the Core.

**Config (concept)**

- **Channel config**: In each channel folder (e.g. `channels/matrix/`, `channels/whatsapp/`) there is a `config.yml` and often a `.env` for credentials (bot token, API keys, etc.).
- **`config/user.yml`**: Add the identities that are allowed to talk (e.g. your Matrix user id, or phone number for WhatsApp) under **im** (or the right field) and set **permissions** (e.g. `IM`).
- **`channels/.env`**: Must have **core_host** and **core_port** so the channel can reach the Core.

**Run**

Start the Core first, then start the channel process for the IM you use (see each channel’s README or config). The channel registers with the Core and receives replies via HTTP callback.

**How WhatsApp (and similar) works: one account = one friend**

Your question: “My WhatsApp channel needs one account and login — one friend on my WhatsApp. When I log into WhatsApp on my phone, I send a message to that friend, and the home computer receives it. How does other agent do that?”

**Same idea in other agent and HomeClaw:**

1. **One WhatsApp account = “the friend”**  
   That account is **not** your personal phone number logged in on the computer. It is a **second identity** the computer uses:
   - **Dedicated number (recommended)**: A second phone number or WhatsApp Business used only for the assistant. You add that number as a contact on your phone; when you message it, the home computer receives the message.
   - **Personal number (multi-device)**: Your own number, with the home computer linked as a second device (WhatsApp Web style). Then the computer is “your WhatsApp on the computer”; you can message that session (e.g. self-chat).

2. **Where does that account “live”?**  
   On the **home computer**. other agent: the **Gateway** (one process on the home machine) runs a **WhatsApp Web client** (Baileys) for that account. HomeClaw: the **WhatsApp channel process** (e.g. `channels/whatsapp/channel.py`, using neonize) runs on the home machine and holds the WhatsApp Web session for that account. So the “friend” is that account, and its **session runs on the home computer**.

3. **How does the message get from your phone to the home computer?**  
   **Your phone never talks to the home computer directly.** Flow:
   - You (on your phone, Account A) send a message to the friend (Account B).
   - WhatsApp’s servers deliver that message to **all linked devices** of Account B.
   - One of those “devices” is the **WhatsApp Web session on the home computer** (the channel process). The home computer keeps an **outbound** connection to WhatsApp (like a browser with WhatsApp Web), so it receives the message and can send replies.
   - So: **Phone → WhatsApp servers → Home computer (outbound to WhatsApp)**. No need to expose the home computer to the internet for WhatsApp; no webhook or tunnel is required for this leg.

4. **What you have to do (other agent example)**  
   - **Configure** who is allowed to talk (e.g. `allowFrom: ["+15551234567"]` or pairing).
   - **Link** the account once: `other-agent channels login --channel whatsapp` → scan QR; session is stored (e.g. `~/.other-agent/credentials/whatsapp/`).
   - **Start** the gateway: `other-agent gateway`. The Gateway runs the WhatsApp Web client for that account on the home computer.
   - On your phone: add that number as a contact and send a message. The home computer receives it and the assistant replies.

HomeClaw is the same pattern: run the WhatsApp channel on the home computer, log in once (QR), add your phone number in `config/user.yml` under **im**, then message that “friend” from your phone. The channel process (on home) receives via WhatsApp’s servers and forwards to the Core.

---

### 3.4 New: Inbound API (any bot, no new channel code)

**Use**: Connect **any** bot (Telegram, Discord, Slack, n8n, your own script) to the Core by sending one HTTP request per message. You don’t add new channel code to HomeClaw; you only run your bot and point it at the Core (or at the Webhook relay).

**Config**

1. **`config/user.yml`**: Add the **user_id** your bot will send (e.g. `telegram_123456789`, `discord_98765`) under **im** for a user that has **IM** (or allow all with empty permissions).
2. **Core reachable**: Your bot must be able to POST to `http://<core_host>:<core_port>/inbound`. If the Core is only on your home LAN, use the Webhook (next) or expose Core via Tailscale/SSH.
3. **Auth (optional)**: When exposing Core on the internet, set **auth_enabled: true** and **auth_api_key** in `config/core.yml`; send **X-API-Key** or **Authorization: Bearer** with each request. See docs/RemoteAccess.md.

**Request**

```http
POST http://<core_host>:<core_port>/inbound
Content-Type: application/json

{
  "user_id": "telegram_123456789",
  "text": "Hello, what's the weather?",
  "channel_name": "telegram",
  "user_name": "Alice"
}
```

**Response**

```json
{ "text": "Here is the weather..." }
```

**Example: Telegram**

A full minimal example is in **`channels/telegram/`**:

1. Create a bot with [@BotFather](https://t.me/BotFather), get the token.
2. In `channels/telegram/`: copy `.env.example` to `.env`, set `TELEGRAM_BOT_TOKEN` and `CORE_URL` (e.g. `http://127.0.0.1:9000`).
3. In `config/user.yml`: add `telegram_<your_chat_id>` under **im** for a user with **IM** permission (get chat_id by sending a message to the bot and checking logs or Telegram API).
4. Start the Core (and LLM), then run:
   ```bash
   pip install -r channels/telegram/requirements.txt
   python -m channels.run telegram
   ```
5. Message your bot on Telegram; it will POST to Core `/inbound` and reply with the Core’s text.

---

### 3.5 New: Webhook channel (relay when Core is not reachable)

**Use**: When the Core runs only on your home LAN and your bot runs elsewhere (or on the internet), run the **Webhook** process on a host that can reach both the bot and the Core. The bot POSTs to the Webhook; the Webhook forwards to the Core and returns the reply. **Constraint**: The Webhook host must be reachable by the app that sends the request **and** must have access to the home computer (Core). See §4.1 for the full connectivity picture.

**Config**

- **`channels/.env`**: Set **core_host** and **core_port** so the Webhook can reach the Core.
- **`config/user.yml`**: Same as for the Inbound API; the Webhook just forwards, so **user_id** is still checked by the Core.

**Run**

```bash
python -m channels.webhook.channel
```

By default it listens on port **8005**. Point your bot at:

```http
POST http://<webhook_host>:8005/message
Content-Type: application/json

{ "user_id": "telegram_123456789", "text": "Hello" }
```

Response shape is the same: `{ "text": "..." }`.

---

### 3.6 New: WebSocket (for our own client)

**Use**: Build a **dedicated client** (e.g. a WebChat in the browser or a small app) that keeps one connection open to the Core. Same permission as the Inbound API; useful for a future WebChat or streaming.

**Endpoint**

```
ws://<core_host>:<core_port>/ws
```

**Protocol**

- Send JSON: `{ "user_id": "...", "text": "..." }`.
- Receive JSON: `{ "text": "...", "error": "..." }`.

**Config**: Same **user_id** allowlist in `config/user.yml` (e.g. under **im** with **IM** permission). When **auth_enabled: true**, send **X-API-Key** or **Authorization: Bearer** in the WebSocket handshake headers. To use from another device, make the Core reachable (e.g. Tailscale or SSH tunnel) and connect to `ws://<reachable_host>:<port>/ws`.

---

### 3.7 Troubleshooting: "Connection error when sending to http://127.0.0.1:8005/get_response"

This error means the **Core** is trying to POST the reply to the **Matrix (or other full) channel** at `http://127.0.0.1:8005/get_response`, but nothing is listening on that address.

**Cause:** Full channels (Matrix, Tinode, WeChat, WhatsApp) run as **separate processes**. The channel must be **running** and listening on the port it registered with the Core (e.g. 8005 for Matrix). If you only started the Core and not the channel, or the channel crashed, the Core cannot deliver the response.

**Fix:**

1. **Start the channel process** in a separate terminal (from repo root):
   ```bash
   python -m channels.run matrix
   ```
   For Matrix, the channel listens on port **8005** by default (`channels/matrix/config.yml`). Leave this process running.

2. **Order:** Start **Core first**, then start the **Matrix channel**. The channel registers with the Core (host, port); when a reply is ready, the Core POSTs to `http://<channel_host>:<port>/get_response`. If the channel is not running, the connection fails.

3. **If Core and channel run on different machines:** In the channel’s `config.yml`, set **host** to an IP or hostname that the Core can reach (e.g. the channel machine’s LAN IP), not `0.0.0.0`. Core converts `0.0.0.0` to `127.0.0.1`, so with `0.0.0.0` the Core will always try to reach the channel on the **same machine** (127.0.0.1).

---

## 4. Access from anywhere (summary)

| Goal | Option |
|------|--------|
| Use from phone with email | **Email** channel: send email to the Core’s account; reply by email. |
| Use from phone with IM | **Matrix / Tinode / WeChat / WhatsApp**: run the matching channel; Core must be reachable from where the channel runs. Or run a **Telegram (or other) bot** that POSTs to **Core /inbound** or **Webhook /message**; put Webhook on a relay if Core is only at home. |
| Use from browser on same LAN | (Future WebChat.) Today: use **WebSocket /ws** with a small client; Core host = machine IP, port = Core port. |
| Use from browser from anywhere | Expose Core (or Webhook) via **Tailscale** or **SSH tunnel**, then use WebSocket or a simple Web UI. |

### 4.1 Important: connectivity is always required

The Webhook (or Core) does **not** remove the need for network access. You always need **both** of these to work:

1. **The app that sends the request** (your phone, a bot server, a browser) must be able to reach **the Webhook or the Core** (whichever URL you use). If the Core/Webhook is only on your home LAN, the app cannot reach it unless you expose it (e.g. Tailscale, SSH tunnel, or public IP).
2. **If the Webhook runs on a different machine than the Core** (e.g. Webhook on a VPS, Core on home): the Webhook must have **access to the home computer** (the Core). So you must expose the Core to the Webhook (e.g. reverse SSH tunnel from home to the VPS, or Tailscale on both home and VPS).

So:

- **Webhook on the home computer**: Then the only link to set up is **app → home** (e.g. Tailscale on phone and home, or tunnel). The Webhook just gives one URL; it doesn’t make the home computer reachable by itself.
- **Webhook on a relay (e.g. VPS)**: Then you need **app → VPS** (usually easy) **and** **VPS → home Core** (home must expose Core to the VPS, e.g. reverse tunnel or Tailscale).

Same as other agent: they use Tailscale or SSH so that “the app” (browser, CLI) can reach the Gateway. We don’t avoid that; we just give one HTTP/WS contract (Core or Webhook) and you choose where to run things and how to connect them.

---

# Part II — For Developers

## 1. Current channel design

### 1.1 Two patterns

| Pattern | Description | Used by |
|--------|-------------|--------|
| **Full channel** | A process that implements **BaseChannel**: it registers with the Core (name, host, port), sends **PromptRequest** (full schema) via HTTP, and either (a) receives the reply asynchronously when the Core POSTs to its **/get_response** endpoint, or (b) uses **POST /local_chat** and gets the reply in the same HTTP response. | Email, Matrix, Tinode, WeChat, WhatsApp, CLI (CLI uses local_chat in-process). |
| **Minimal (inbound / WebSocket)** | No BaseChannel process. The client (external bot or our own app) sends a **minimal payload** to the Core and gets a **sync** reply. | Any bot via **POST /inbound**; our own client via **WebSocket /ws**; optional **Webhook** relay that forwards to /inbound. |

Both patterns use the same permission model: **config/user.yml** (user identities and channel types). The Core turns minimal payloads into an internal **PromptRequest** and runs the same pipeline (permission → RAG + LLM or plugin → reply).

### 1.2 Contracts

- **Full channel → Core**:
  - **POST /process**: Body = **PromptRequest** (request_id, channel_name, request_metadata, channelType, user_name, app_id, user_id, contentType, text, action, host, port, images, videos, audios, timestamp). Core returns 200 and later POSTs **AsyncResponse** to the channel’s **host:port/get_response**.
  - **POST /local_chat**: Same body; Core returns the reply **text in the response body** (sync).
- **Minimal → Core**:
  - **POST /inbound**: Body = **InboundRequest** (user_id, text, channel_name?, user_name?, app_id?, action?). Response = **{ "text": "..." }**. Implemented by building a PromptRequest internally and reusing the same handler as local_chat.
  - **WebSocket /ws**: Send JSON **{ user_id, text, ... }**; receive **{ text, error }**. Same logic as /inbound, shared via **Core._handle_inbound_request()**.

### 1.3 Webhook channel

- **Role**: HTTP relay. Listens on a port (default 8005); **POST /message** accepts the same JSON as **POST /inbound** and forwards to **Core /inbound**; returns the same **{ "text": "..." }**.
- **When to use**: Core is not directly reachable from the internet or from the bot (e.g. Core on home LAN; Webhook on a VPS or Tailscale host). One Webhook can serve many bots.
- **Code**: `channels/webhook/channel.py` (FastAPI app); config in `channels/webhook/config.yml`; Core URL from **channels/.env**.

---

## 2. Connecting to the home computer: HomeClaw vs other agent

### 2.1 How other agent does it

- **Single Gateway**: All channels run inside (or connect to) one process on one port. No separate “channel processes” to deploy.
- **Channels**: WhatsApp (Baileys), Telegram (grammY), Slack, Discord, etc., are implemented in the repo or as extensions; each channel uses the platform’s API (bot token or WhatsApp Web session). The Gateway owns the connection and the credentials.
- **Remote access**: Gateway binds to loopback by default. Users reach it via **Tailscale Serve/Funnel** or **SSH tunnel**; then they use **WebChat** or the Control UI in the browser. So “connect to home computer” = connect to the Gateway (or its tunnel) and use WebChat or the app.
- **No separate “relay” for messages**: Messages don’t go through a separate proxy server; they go to the Gateway. Discovery/reachability is solved by Tailscale or SSH, not by a custom “message relay.”

### 2.2 How HomeClaw does it

- **Core + channel processes**: The Core is the brain; channels are separate processes (or external bots) that send requests to the Core. So “connect to home computer” can mean:
  - **Direct**: The client (user’s phone via IM, or a bot) talks to a **channel process** that runs on the home machine (e.g. email, WeChat, WhatsApp). That channel talks to the Core on localhost or LAN.
  - **Inbound / Webhook**: The client (or a bot) talks to the **Core** (or to the **Webhook**) over HTTP/WS. If the Core is only on the home LAN, we can run the **Webhook** on a host that is reachable from the internet (or from Tailscale) and that can reach the Core; then “connect to home” = connect to the Webhook URL, which forwards to the Core.
- **WebSocket**: We expose **/ws** on the Core so our own client (e.g. future WebChat) can hold one connection. To use it from elsewhere, the Core (or a reverse proxy in front of it) must be reachable (e.g. Tailscale or SSH tunnel), similar to other agent.

### 2.3 Where the code lives: separate vs inside the core

- **HomeClaw**: Channels are **independent modules** and run **separately** from the Core. Full channels (Email, Matrix, WeChat, WhatsApp, etc.) are separate processes. The Webhook channel and WebSocket (/ws) support the same “minimal API” style (POST /inbound or /message) — but to use that with Telegram, Discord, etc., you still need to **write some bot code** (e.g. long‑poll Telegram, handle webhooks from Discord). That bot code is **separate from the Core**: it lives in **channels/** (e.g. `channels/telegram/channel.py`, `channels/discord/channel.py`) or in your own script; it is not part of the Core process. The Webhook relay itself is also a separate process (`channels/webhook/`). So: Core = one process; every channel or bot that talks to it is either another process (full channel, Webhook) or an external script (Telegram/Discord bot) that POSTs to Core or Webhook.
- **other agent**: Channel code runs **inside the core (Gateway)** or as extensions loaded by the Gateway. WhatsApp, Telegram, Slack, Discord, etc. are implemented in the Gateway (or its extensions); the Gateway process runs the WhatsApp client, Telegram client, and so on. There is no separate “Telegram bot process” that POSTs to the Gateway — the Gateway *is* the Telegram (and WhatsApp, etc.) client. So: one process (Gateway) = core + all channel code in one place (or in extensions).

So you are correct: HomeClaw’s channels (and the bot code for /inbound/Webhook/WebSocket) are **separate from the Core**; other agent’s channel code is **in the core or in extensions**.

### 2.4 What we do differently / better (for our goals)

| Aspect | other agent | HomeClaw |
|--------|----------|------------|
| **Adding a new bot** | New channel (or extension) in codebase; configure bot token in Gateway config. | **Minimal API**: Any bot can POST to **/inbound** (or Webhook **/message**) with `{ user_id, text }`. Channels (Telegram, Discord, Slack, etc.) live in **channels/**; add **user_id** to user.yml. Example: `channels/telegram/`. |
| **Deployment of channels** | One Gateway process; all channels in one place. | Core + one or more channel processes (or no extra process if using only /inbound bots). **Webhook** gives a single relay endpoint for many bots when Core isn’t public. |
| **Connect to home** | Tailscale/SSH to Gateway; then WebChat/Control UI. | **Multiple paths**: (1) IM channels (email, WeChat, etc.) that run on the home machine; (2) bots that POST to Core **/inbound** (if Core reachable); (3) bots that POST to **Webhook** (Webhook can sit on a relay); (4) **WebSocket /ws** for our own client (reach Core via Tailscale/SSH). We support “any bot with one HTTP contract” without implementing each IM in our repo. |
| **Local LLM + RAG** | Cloud-first; optional local; no vector RAG in core. | **Local-first** LLM (llama.cpp) + **RAG** (SQLite + Chroma). Channels are agnostic to this; same Core for all. |

So: we **learn from other agent** (one clear contract, WebSocket for our client, Tailscale/SSH for remote), but we **support what we want**: minimal API for bots, optional Webhook relay, local LLM and RAG, and no requirement to implement every IM inside the repo.

---

## 3. What we can do (current)

- **Full channels**: Email, Matrix, Tinode, WeChat, WhatsApp, CLI; each implements BaseChannel, registers with Core, uses /process (async) or /local_chat (sync).
- **Minimal API**: **POST /inbound** and **WebSocket /ws** with **InboundRequest**-style payload; shared handler **Core._handle_inbound_request()**; permission via user.yml.
- **Webhook**: One HTTP relay (**channels/webhook**) that forwards **POST /message** to Core **/inbound**; config via channels/.env.
- **Examples**: **channels/telegram/**, **channels/discord/**, **channels/slack/** — minimal bots using /inbound; run with `python -m channels.run <name>`.
- **Docs**: Design.md (architecture), Improvement.md (ideas, HTTP vs WS), Comparison.md (vs other agent), this Channel.md (users + developers).

---

## 4. What we have and what we can improve

**Already available**

- **Onboarding**: `python main.py onboard` — wizard to set workspace, LLM, channels, skills; updates core.yml.
- **Doctor**: `python main.py doctor` — checks config and LLM connectivity; suggests fixes.
- **Remote access and auth**: **docs/RemoteAccess.md** — auth_enabled/auth_api_key for /inbound and /ws; Tailscale or SSH to expose Core.

**Possible improvements (keep our goals)**

- **Single entry point**: One command or script to start **Core + one or more channels** (e.g. Core + webhook) so deployment is “run this and you have core + channel(s).”
- **Pairing (optional)**: For IM/bots, an optional **pairing** step (e.g. first contact gets a code, user approves in config or CLI) so the assistant isn’t open to anyone who finds the number/id.
- **WebChat**: A minimal **Web UI** that talks to the Core (e.g. over **WebSocket /ws**) so users can chat from the browser without configuring another IM. We have **channels/webchat/**; fits “connect to home” via Tailscale/SSH + browser.

We **don’t** need to copy other agent’s single binary or full tool set; we keep **local LLM + RAG** and **minimal bot API**, and improve **ops** and **documentation** so “channel to home computer” is clear and easy.

---

## 5. References

- **Design**: `Design.md` (Core, channels, /inbound, /ws, webhook).
- **How to write a new channel**: **docs/HowToWriteAChannel.md** (full channel vs webhook/inbound; two methods for developers).
- **Improvement ideas**: `Improvement.md` (other agent summary, comparison, channel vs gateway, HTTP vs WS, example).
- **Comparison with other agent**: `Comparison.md`.
- **Remote access and auth**: **docs/RemoteAccess.md**.
- **Channel usage**: `channels/README.md`, `channels/webhook/README.md`, `channels/telegram/README.md`.
