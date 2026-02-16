# Slack channel (inbound API)

Minimal Slack bot using **Socket Mode** (no public URL). Forwards DMs/channel messages to Core **POST /inbound** and posts the reply.

## Setup

1. **Create app**: [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch.
2. **Enable Socket Mode**: Settings → Socket Mode → Enable → Create app-level token (scopes: `connections:write`). Save as `SLACK_APP_TOKEN` (xapp-...).
3. **Bot token**: OAuth & Permissions → add scope `chat:write`, install to workspace. Copy Bot User OAuth Token as `SLACK_BOT_TOKEN` (xoxb-...).
4. **Event Subscriptions**: Enable Events → Subscribe to bot events → add `message.im`, `message.channels` (or as needed). Save.
5. **Install**: `pip install -r requirements.txt`
6. **Configure**: Core connection: set `core_host` and `core_port` (or `CORE_URL`) in **channels/.env** only. Tokens: copy `.env.example` to `.env` here and set `SLACK_APP_TOKEN` and `SLACK_BOT_TOKEN`, or set them in `channels/.env`.
7. **Allow users**: In `config/user.yml`, add `slack_<user_id>` (e.g. `slack_U01234ABCD`) to a user with `IM` permission.

## Run

```bash
python -m channels.slack.channel
# or
python -m channels.run slack
```

Start Core first. Message the bot in Slack (DM or in a channel where the app is added).
