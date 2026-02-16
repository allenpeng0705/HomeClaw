# Channels

Channels are how you reach your HomeClaw assistant: WebChat, Telegram, Discord, email, CLI, and more. All use the same Core and the same permission list.

---

## Supported channels

| Channel    | Type     | Run command                          |
|-----------|----------|--------------------------------------|
| **CLI**   | In-process | `python -m main start`               |
| **WebChat** | WebSocket | `python -m channels.run webchat`   |
| **Telegram** | Inbound  | `python -m channels.run telegram`  |
| **Discord**  | Inbound  | `python -m channels.run discord`   |
| **Slack**    | Inbound  | `python -m channels.run slack`     |
| **Email**    | Full     | Start email channel (see repo)     |
| **Matrix, Tinode, WeChat, WhatsApp** | Full | `python -m channels.run <name>` |
| **Webhook**  | Relay    | `python -m channels.run webhook`   |

---

## Allow who can talk

Edit **`config/user.yml`**. Each user has `name`, `email`, `im` (e.g. `telegram_<chat_id>`, `discord_<user_id>`), and optional `permissions`. Only listed users can send messages to Core. See [Multi-user support](../docs_design/MultiUserSupport.md) in the repo for details.

---

## Inbound API (any bot)

Any bot can POST to Core **`/inbound`** with:

```json
{ "user_id": "telegram_123456789", "text": "Hello" }
```

Response: `{ "text": "..." }`. Add `user_id` to `config/user.yml`. If Core is not reachable from the internet, use the **Webhook** channel as a relay. See [Channel.md](../Channel.md) and [HowToWriteAChannel.md](../docs_design/HowToWriteAChannel.md) in the repo.
