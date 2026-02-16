# Telegram channel (inbound API)

Minimal Telegram channel that uses Core **POST /inbound**. No full BaseChannel; this process polls Telegram and forwards messages to the Core.

## Setup

1. **Create a bot**: [@BotFather](https://t.me/BotFather) → `/newbot` → get token.
2. **Install deps** (in a venv if you like): `pip install -r requirements.txt`
3. **Configure**: Core connection: set `core_host` and `core_port` (or `CORE_URL`) in **channels/.env** only. Bot token: copy `.env.example` to `.env` in this folder and set `TELEGRAM_BOT_TOKEN`, or set `TELEGRAM_BOT_TOKEN` in `channels/.env`.
4. **Allow users**: In `config/user.yml`, add `telegram_<chat_id>` to a user with `IM` permission. Get your chat_id from the first message to the bot (check logs or Telegram API).

## Run

1. Start HomeClaw Core as usual.
2. Run this channel:
   ```bash
   python -m channels.telegram.channel
   ```
   Or from repo root: `python -m channels.run telegram`
3. Message your bot on Telegram; replies come from the Core.

## user_id

Use `telegram_<chat_id>` in `config/user.yml` (e.g. `telegram_123456789`).
