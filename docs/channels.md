# Channels

Channels let you reach HomeClaw from your favorite platform — Telegram, Discord, Slack, a web browser, email, and more. All channels talk to the same Core and share the same memory, tools, and user identity.

---

## Available channels

| Channel | How to start | What you get |
|---------|-------------|-------------|
| **WebChat** | `python -m channels.run webchat` | Browser chat at http://localhost:8014 |
| **Telegram** | `python -m channels.run telegram` | Telegram bot for personal or group use |
| **Discord** | `python -m channels.run discord` | Discord bot for servers |
| **Slack** | `python -m channels.run slack` | Slack app for workspaces |
| **Email** | Start email channel (see config) | Send/receive via email |
| **CLI** | `python -m main start` | Built-in terminal chat |
| **Matrix** | `python -m channels.run matrix` | Matrix/Element chat |
| **WeChat** | `python -m channels.run wechat` | WeChat integration |
| **WhatsApp** | `python -m channels.run whatsapp` | WhatsApp integration |
| **Webhook** | `python -m channels.run webhook` | Relay for custom bots |

---

## Quick start: WebChat (browser)

The fastest channel to try — no bot tokens or accounts needed.

1. Make sure Core is running: `python -m main start`
2. In another terminal:

```bash
python -m channels.run webchat
```

3. Open **http://localhost:8014** in your browser
4. Start chatting

---

## Set up Telegram

### Step 1: Create a Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts to create a bot
3. BotFather gives you a **bot token** — save it

### Step 2: Configure HomeClaw

Add the bot token to `channels/.env`:

```
CORE_URL=http://127.0.0.1:9000
TELEGRAM_BOT_TOKEN=your-bot-token-here
```

### Step 3: Add your Telegram identity to user.yml

Find your Telegram chat ID (send a message to your bot, then check `https://api.telegram.org/bot<TOKEN>/getUpdates`) and add it to `config/user.yml`:

```yaml
users:
  - name: Alice
    id: alice
    im:
      - telegram_123456789
```

### Step 4: Start the channel

```bash
python -m channels.run telegram
```

Now send a message to your Telegram bot — HomeClaw replies.

---

## Set up Discord

### Step 1: Create a Discord bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a **New Application** → go to **Bot** → click **Add Bot**
3. Copy the **bot token**
4. Under **OAuth2 → URL Generator**, select **bot** scope and **Send Messages** permission
5. Use the generated URL to invite the bot to your server

### Step 2: Configure HomeClaw

Add to `channels/.env`:

```
CORE_URL=http://127.0.0.1:9000
DISCORD_BOT_TOKEN=your-discord-bot-token
```

### Step 3: Add your Discord identity to user.yml

```yaml
users:
  - name: Alice
    id: alice
    im:
      - discord_987654321
```

### Step 4: Start the channel

```bash
python -m channels.run discord
```

Mention the bot or DM it in Discord to chat with HomeClaw.

---

## Running multiple channels

You can run as many channels as you want alongside the Companion App. Each runs as a separate process:

```bash
# Terminal 1: Core
python -m main start

# Terminal 2: WebChat
python -m channels.run webchat

# Terminal 3: Telegram
python -m channels.run telegram
```

All channels share the same Core. A user chatting from Telegram and the Companion App is recognized as the same person (if their identities are in the same `user.yml` entry) — but conversations on different channels are kept in separate sessions.

---

## Channels vs Companion App

| | Companion App | Channels |
|---|---|---|
| **What it is** | A client app on your device | Server-side bridge processes |
| **How it reaches Core** | Directly via HTTP | Channel process forwards messages |
| **Extra features** | Manage Core, install skills, Canvas | Platform-specific features (groups, threads) |
| **Setup** | Just set Core URL | Run a process + set bot tokens |
| **Best for** | Personal use, full control | Group access, familiar platforms |

**You can use both.** Many people use the Companion App for personal/admin tasks and Telegram or Discord for family or group access.

See [Companion App vs Channels](companion-vs-channels.md) for a deep technical comparison.

---

## User permissions

Every user who talks to HomeClaw — from any channel — must be listed in `config/user.yml`. The `im`, `email`, and `phone` fields map platform identities to HomeClaw users:

```yaml
users:
  - name: Alice
    id: alice
    im:
      - companion_alice          # Companion App
      - telegram_123456789       # Telegram
      - discord_987654321        # Discord
    email:
      - alice@example.com        # Email channel
```

If someone sends a message and their identity isn't in `user.yml`, Core rejects it.

---

## Custom bots (Inbound API)

Any bot or script can talk to HomeClaw by POSTing to Core's `/inbound` endpoint:

```bash
curl -X POST http://127.0.0.1:9000/inbound \
  -H "Content-Type: application/json" \
  -d '{"user_id": "my_bot_user", "text": "Hello HomeClaw"}'
```

The response contains the AI's reply. Add `my_bot_user` to `config/user.yml` first.

See [HowToWriteAChannel.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAChannel.md) in the repo for building a full channel.

---

## Tips

- **Channel not connecting?** Check that `CORE_URL` in `channels/.env` is correct and Core is running.
- **"Permission denied" errors?** The user's platform identity must be in `config/user.yml`.
- **Start channels from the Portal:** The [Portal](portal.md) can start WebChat, Telegram, and Discord channels with a click.
- **Channels are independent processes.** If a channel crashes, Core and other channels keep running. Just restart the crashed channel.
