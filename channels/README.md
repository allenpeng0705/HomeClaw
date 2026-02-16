# Channels

All channels live here. Each channel is a **separate process**; run the Core first, then run one or more channels.

## Channel types

- **Full channel** (BaseChannel): Registers with Core, sends full `PromptRequest`, gets reply via callback or `/local_chat`. E.g. `whatsapp`, `matrix`, `wechat`, `tinode`, `emailChannel` (in core).
- **Inbound-style** (minimal): No BaseChannel; the process receives messages from the platform (Telegram, Discord, Slack) and POSTs to Core **/inbound**; replies are sent back. E.g. `telegram`, `discord`, `slack`.
- **Webhook**: HTTP relay; any client can POST to `/message` and get a reply (forwards to Core `/inbound`). Run `webhook` when Core is not directly reachable.

## Run a channel

From repo root:

```bash
python -m channels.run <channel_name>
```

Examples:

```bash
python -m channels.run webhook
python -m channels.run telegram
python -m channels.run discord
python -m channels.run slack
python -m channels.run whatsapp
python -m channels.run matrix
python -m channels.run wechat
python -m channels.run tinode
python -m channels.run google_chat
python -m channels.run signal
python -m channels.run imessage
python -m channels.run teams
python -m channels.run webchat
python -m channels.run zalo
python -m channels.run feishu
python -m channels.run dingtalk
python -m channels.run bluebubbles
```

Or run the channel module directly:

```bash
python -m channels.telegram.channel
python -m channels.webhook.channel
```

## Run multiple channels

Run each channel in its own terminal (or as a separate process):

1. Start Core: `python main.py` (and choose to run core) or start core however you normally do.
2. In another terminal: `python -m channels.run telegram`
3. In another: `python -m channels.run discord`
4. etc.

Same as before: every channel is a separate process; the runner just gives one command (`channels.run <name>`) to start any of them.

## List of channels (channels)

| Channel      | Type     | Status   | Notes |
|-------------|----------|----------|--------|
| email       | full     | in core  | emailChannel in core/ |
| matrix      | full     | ✅       | channels/matrix/ |
| tinode      | full     | ✅       | channels/tinode/ |
| wechat      | full     | ✅       | channels/wechat/ |
| whatsapp    | full     | ✅       | channels/whatsapp/ |
| webhook     | relay    | ✅       | channels/webhook/ |
| telegram    | inbound  | ✅       | channels/telegram/ |
| discord     | inbound  | ✅       | channels/discord/ |
| slack       | inbound  | ✅       | channels/slack/ |
| google_chat | HTTP     | ✅       | channels/google_chat/ — Google Chat API events |
| signal      | webhook  | ✅       | channels/signal/ — bridge POSTs to /message |
| imessage    | webhook  | ✅       | channels/imessage/ — bridge POSTs to /message |
| teams       | HTTP     | ✅       | channels/teams/ — Bot Framework /api/messages |
| webchat     | client   | ✅       | channels/webchat/ — browser UI over WebSocket /ws |
| zalo        | webhook  | ✅       | channels/zalo/ — bridge POSTs to /message |
| feishu      | HTTP     | ✅       | channels/feishu/ — Feishu/Lark event callback |
| dingtalk    | Stream   | ✅       | channels/dingtalk/ — DingTalk Stream (WebSocket) |
| bluebubbles | webhook  | ✅       | channels/bluebubbles/ — bridge POSTs to /message |
| CLI         | in main  | ✅       | main.py interactive |

## Config

- **channels/.env**: **Single source for Core connection.** All channels use this file only for connecting to the Core (no hardcoded URL, no config from other places). Set `core_host` and `core_port`, or `CORE_URL`. Copy from `channels/.env.example`. Optional: put bot tokens (TELEGRAM_BOT_TOKEN, DISCORD_BOT_TOKEN, etc.) here or in each channel’s `.env`.
- **config/user.yml**: Allowlist: add `telegram_<id>`, `discord_<id>`, `slack_<id>`, etc. under `im` for a user with `IM` permission.
- Per-channel: copy `.env.example` to `.env` in the channel folder only for bot tokens if you don’t put them in `channels/.env`.
