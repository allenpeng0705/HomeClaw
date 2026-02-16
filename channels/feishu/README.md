# Feishu (飞书 / Lark) channel

Receives **Feishu Open Platform** event callbacks (request URL mode). On `im.message.receive_v1`: forwards to Core `/inbound` and sends the reply via the Feishu API. Core connection from **channels/.env** only.

Inspired by the other agent Feishu plugin: [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu).

## Setup

1. **Feishu Open Platform**: Create an app at [open.feishu.cn](https://open.feishu.cn) (or [open.larksuite.com](https://open.larksuite.com) for Lark).
2. **Permissions**: Enable at least:
   - `im:message` — send and receive messages
   - `im:message.p2p_msg:readonly` — read DMs to the bot
   - `im:message.group_at_msg:readonly` — receive @mentions in groups
   - `im:message:send_as_bot` — send messages as the bot
3. **Events**: In **Events & Callbacks**, choose **Request URL** (webhook). Add event `im.message.receive_v1`. Set the callback URL to your server (e.g. `https://your-host:8016/feishu/events`; use ngrok for local dev).
4. **channels/.env**: Set `FEISHU_APP_ID`, `FEISHU_APP_SECRET` (from the app credentials page). Optional: `FEISHU_BASE_URL` (default `https://open.feishu.cn`; use `https://open.larksuite.com` for Lark), `FEISHU_EVENT_PATH` (default `/feishu/events`), `FEISHU_CHANNEL_PORT` (8016).
5. **config/user.yml**: Add `feishu_<user_id>` (e.g. `feishu_ou_xxx`) under `im` for allowed users.

## Run

```bash
python -m channels.run feishu
```

Default: listen on `0.0.0.0:8016`. The callback URL you configure in Feishu must be publicly reachable (e.g. ngrok for local: `ngrok http 8016`, then `https://xxx.ngrok.io/feishu/events`).

## Connection mode

This channel uses **webhook (Request URL)** only. For **WebSocket (long connection)** mode like the other agent plugin, you would need to implement the Feishu WebSocket client; for a minimal setup, webhook + a public URL (or tunnel) is sufficient.
