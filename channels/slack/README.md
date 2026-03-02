# Slack channel (inbound API)

Minimal Slack bot using **Socket Mode** (no public URL). Forwards DMs/channel messages to Core **POST /inbound** and posts the reply.

## Setup

1. **Create app**: [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch.
2. **Enable Socket Mode**: Settings → Socket Mode → Enable → Create app-level token (scopes: `connections:write`). Save as `SLACK_APP_TOKEN` (xapp-...).
3. **Bot token**: OAuth & Permissions → add scope `chat:write`, install to workspace. Copy Bot User OAuth Token as `SLACK_BOT_TOKEN` (xoxb-...).
4. **Event Subscriptions**: Enable Events → Subscribe to bot events → add `message.im`, `message.channels` (or as needed). Save.
5. **Install**: `pip install -r requirements.txt`
6. **Configure**: Core connection: set `core_host` and `core_port` (or `CORE_URL`) in **channels/.env** only. Tokens: copy `.env.example` to `.env` here and set `SLACK_APP_TOKEN` and `SLACK_BOT_TOKEN`, or set them in `channels/.env`.
7. **Allow users**: In `config/user.yml`, add `slack_<user_id>` to a user's `im` list. The `user_id` is **Slack's user ID** (e.g. `U01234ABCD`) for the person who messages the bot.
   - **Where to get it**: In Slack, right‑click the user's name (in a message or member list) → **Copy member ID**. Or: Workspace menu → Settings & administration → Manage members → open the user → the URL or profile may show the ID.
   - Example: to allow Slack user `U01234ABCD` as the HomeClaw user `AllenPeng`, add to that user's `im` list: `slack_U01234ABCD` (e.g. `im: ['matrix:@...', 'slack_U01234ABCD']`).

## Run

```bash
python -m channels.slack.channel
# or
python -m channels.run slack
```

Start **Core first** (`python -m main start`). Wait until Core is ready, then run the Slack channel.

**How the channel connects to Core**  
The Slack channel uses **HTTP** (same as a browser): `GET /ready` to check Core is up, then `POST /inbound` with JSON for each message. Core is a web server; there is no separate socket. The channel does not use HTTP_PROXY for Core (so `127.0.0.1` is always hit directly). On startup you’ll see: `Slack channel Core URL: http://127.0.0.1:10056` — verify it matches the port you use in the browser.

**If you see 502** — (1) Ensure Core is running and listening on the port in `core_port` (if using extra_port, Core must have been started with `extra_port` set in core.yml). (2) If something else is on that port, stop it or use another port. (3) If the browser works but the channel gets 502, the channel may have been using a proxy; it now skips proxy for Core. Check (Windows): `netstat -ano | findstr :<port>`.

## Images and files

The Slack channel uses the **same request as the Companion app**: **POST /inbound** with `text`, `images`, `videos`, `audios`, and `files`. When a user attaches files in Slack, the channel downloads them (via Slack file URLs + bot token) to **data URLs** and sends them in the payload. Core stores **images** in the user’s **images** folder when the model doesn’t support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.

## How Slack (phone), Slack bot, and Core communicate

```
┌─────────────────┐         ┌──────────────────────────────────┐         ┌─────────────┐
│  Slack on phone │         │  Slack bot (this channel process) │         │    Core     │
│  (or desktop)   │         │  running on your computer        │         │  (same box) │
└────────┬────────┘         └───────────────┬──────────────────┘         └──────┬──────┘
         │                                  │                                   │
         │  1. You send "你好"               │                                   │
         │  ──────────────────────────────► │                                   │
         │     (Slack servers push event    │                                   │
         │      over WebSocket to bot)      │                                   │
         │                                  │  2. Bot acks to Slack immediately │
         │  ◄────────────────────────────── │     (so Slack doesn't retry)      │
         │                                  │                                   │
         │                                  │  3. Bot POST /inbound (HTTP)      │
         │                                  │     user_id=slack_U0AHT..., text  │
         │                                  │  ───────────────────────────────► │
         │                                  │                                   │  4. Core: auth,
         │                                  │                                   │     user allowlist,
         │                                  │                                   │     LLM/tools...
         │                                  │  5. Core returns 200 + {text: "…"} │
         │                                  │  ◄─────────────────────────────── │
         │                                  │                                   │
         │  6. Bot posts reply to Slack    │                                   │
         │  ◄────────────────────────────── │  chat_postMessage(...)            │
         │     (you see the reply in Slack) │                                   │
```

- **Slack ↔ Bot**: **Socket Mode** (WebSocket). Slack pushes events (e.g. new message) to your bot; the bot does not need a public URL. Your bot acks each event right away, then does the work.
- **Bot ↔ Core**: **HTTP**. One `POST http://127.0.0.1:9000/inbound` per message. The bot waits for Core's response (sync; up to 120s). Core checks auth (API key), user allowlist (`slack_<user_id>` in `user.yml`), then runs the pipeline and returns `{ "text": "…" }`.
- **Bot → Slack**: **Slack Web API** (HTTP). After Core replies, the bot calls `chat_postMessage` to post the reply in the same channel/thread.

All three must be running / reachable: Slack's servers, your Slack channel process, and Core (e.g. `python -m main start`).

### Troubleshooting: "Empty response" / "Core didn't receive the request"

If the Slack bot gets a response **immediately** and Core never logs the request, **something other than Core is answering on port 9000** (or the port in `channels/.env`). Core would take several seconds to run the LLM; an instant empty reply means a different process or proxy is handling the connection.

1. **Stop everything** (Slack channel, Core, any other app using the same port).
2. **Start only Core** from the project root: `python -m main start`.
3. **Check what is on the port** (Windows): `netstat -ano | findstr :9000` — you should see one process (your Python/Core). If you see another PID, that app is using 9000; exit it or change `core_port` in `channels/.env` and Core's port in `config/core.yml` to a different port.
4. **Verify Core answers**: open `http://127.0.0.1:9000/ready` in a browser or run `curl http://127.0.0.1:9000/ready`. You should see JSON. If you get nothing or a non-JSON page, Core is not the one responding.
5. **Start the Slack channel**. It logs whether Core is reachable at startup. If you still get empty response, the new log line will show GET /ready result on the same URL so you can see what is actually on that port.
