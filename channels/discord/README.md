# Discord channel (inbound API)

Minimal Discord bot that forwards DMs/channel messages to Core **POST /inbound** and replies with the Core response.

## Setup

1. **Create a bot**: [Discord Developer Portal](https://discord.com/developers/applications) → New Application → Bot → Reset Token.
2. **Enable intents**: Bot → Privileged Gateway Intents → enable "Message Content Intent".
3. **Invite bot**: OAuth2 → URL Generator → scopes: `bot`; permissions: Send Messages, Read Message History, View Channels.
4. **Install**: `pip install -r requirements.txt`
5. **Configure**: Core connection: set `core_host` and `core_port` (or `CORE_URL`) in **channels/.env** only. Bot token: copy `.env.example` to `.env` here and set `DISCORD_BOT_TOKEN`, or set it in `channels/.env`.
6. **Allow users**: In `config/user.yml`, add `discord_<user_id>` (e.g. `discord_123456789012345678`) to a user with `IM` permission. To get user ID: enable Developer Mode in Discord → right-click user → Copy User ID.

## Run

```bash
python -m channels.discord.channel
# or
python -m channels.run discord
```

Then start Core and send a message to the bot (DM or in a channel where it can read).
