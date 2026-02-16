# Webhook Channel

Any bot (Telegram, Discord, Slack, n8n, etc.) can talk to HomeClaw Core with **no custom channel code** by sending HTTP POSTs.

## Option A: POST directly to Core (simplest)

If the Core is reachable (e.g. same machine or Tailscale), POST to the Core:

```http
POST http://<core_host>:<core_port>/inbound
Content-Type: application/json

{
  "user_id": "telegram_12345",
  "text": "Hello, what's the weather?",
  "channel_name": "telegram",
  "user_name": "Alice"
}
```

Response:

```json
{ "text": "Here is the weather..." }
```

- Add `user_id` to `config/user.yml` under a user with `IM` (or desired) permission so the request is allowed.
- `channel_name` is a label (e.g. `telegram`, `discord`); optional, default `webhook`.

## Option B: POST to this webhook (when Core is not public)

Run this webhook process where it can be reached (e.g. same host as Core, or a relay). It forwards to Core `/inbound`.

```bash
# From project root; uses channels/.env for core_host, core_port
python -m channels.webhook.channel
# or: uvicorn channels.webhook.channel:app --host 0.0.0.0 --port 8005
```

Then any bot POSTs to this server:

```http
POST http://<webhook_host>:8005/message
Content-Type: application/json

{
  "user_id": "discord_98765",
  "text": "Hello"
}
```

Same response shape: `{ "text": "..." }`.

## Minimal bot examples

**Telegram (python-telegram-bot):**

```python
from telegram import Update
from telegram.ext import ContextTypes
import httpx

CORE_URL = "http://127.0.0.1:9000"  # or your Core / webhook URL

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = f"telegram_{update.effective_user.id}"
    text = update.message.text
    r = httpx.post(f"{CORE_URL}/inbound", json={"user_id": user_id, "text": text, "channel_name": "telegram"}, timeout=60)
    data = r.json()
    await update.message.reply_text(data.get("text", ""))
```

**Discord (discord.py):**

```python
import discord
import httpx

CORE_URL = "http://127.0.0.1:9000"

async def on_message(message):
    if message.author.bot:
        return
    user_id = f"discord_{message.author.id}"
    r = httpx.post(f"{CORE_URL}/inbound", json={"user_id": user_id, "text": message.content, "channel_name": "discord"}, timeout=60)
    data = r.json()
    await message.channel.send(data.get("text", ""))
```

Add `telegram_12345` / `discord_98765` etc. to `config/user.yml` under `im:` for the user(s) that should be allowed.

## WebSocket (for our own client)

The Core also exposes **WebSocket `ws://<core_host>:<core_port>/ws`**. Use it for a **dedicated client** (e.g. WebChat) that keeps one connection open. Send JSON `{"user_id": "...", "text": "..."}` and receive `{"text": "..."}`. Same permission as `/inbound`. Bots (Telegram, Discord) should use HTTP `/inbound` or this webhook; WebSocket is for our own UI or app.
