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

**When Core has auth enabled** (`auth_enabled: true` in Core config): set **CORE_API_KEY** in `channels/.env` to the same value as Core's `auth_api_key`, so all channels that POST to Core can authenticate. See the CORE_API_KEY bullet below.

- **channels/.env**: **Single source for Core connection.** All channels use this file only for connecting to the Core (no hardcoded URL, no config from other places). Set `core_host` and `core_port`, or `CORE_URL`. Copy from `channels/.env.example`. Optional: put bot tokens (TELEGRAM_BOT_TOKEN, DISCORD_BOT_TOKEN, etc.) here or in each channel’s `.env`.
- **CORE_API_KEY** (in **channels/.env**): You may need to set this when Core has **auth_enabled** (Core config: `auth_enabled: true` and `auth_api_key: "..."`). Set `CORE_API_KEY` in `channels/.env` to the same value as Core's `auth_api_key`. All channels that POST to Core (/inbound) use it: telegram, discord, slack, signal, imessage, bluebubbles, zalo, dingtalk, google_chat, teams, feishu, webhook, whatsappweb; WebChat proxy also uses it. If Core auth is disabled, leave `CORE_API_KEY` unset or empty.
- **config/user.yml**: Allowlist: add `telegram_<id>`, `discord_<id>`, `slack_<id>`, etc. under `im` for a user with `IM` permission.
- Per-channel: copy `.env.example` to `.env` in the channel folder only for bot tokens if you don’t put them in `channels/.env`.

## How channel maps to user

When you use a channel (Slack, Feishu, DingTalk, Telegram, etc.) to talk to Core, Core maps the request to a **user** in **config/user.yml** so it knows who you are for sandbox, chat history, memory, and permissions.

1. **Channel sends an identity**  
   Each channel builds a **`user_id`** string that identifies the person (or chat) on that platform, and POSTs it to Core with **`channel_name`**:
   - **Slack**: `user_id` = `slack_<Slack user ID>` (e.g. `slack_U0AHT91TSRL`)
   - **Feishu**: `user_id` = `feishu_<sender_id>` or `feishu_unknown`
   - **DingTalk**: `user_id` = `dingtalk_<sender_id>` (e.g. `dingtalk_$:LWCP_v1:$...`)
   - **Telegram**: `user_id` = `telegram_<chat_id>`
   - **Discord**: `user_id` = `discord_<author.id>`
   - **Matrix**: `user_id` = Matrix ID (e.g. `@user:domain`)
   - **WebChat**: often `user_id` = `webchat_user` (or from env)
   - Other channels use the same idea: a prefix for the channel + the platform's user/chat identifier.

2. **Core matches `user_id` to a user in user.yml**  
   For **IM** (instant messaging) channels, Core calls **`check_permission(user_name, user_id, ChannelType.IM, ...)`**. It looks up **config/user.yml** and finds the **first user** whose **`im:`** list contains that **`user_id`** (exact or case-insensitive). That user is the "matched" user.

3. **Core sets the system user**  
   Once matched, Core sets **`request.system_user_id`** = that user's **`id`** (or **`name`**) from user.yml (e.g. `AllenPeng`). Everything that is per-user (sandbox folder, chat history, memory, knowledge base, file tools) uses this **system_user_id**.

4. **What you need to do**  
   In **config/user.yml**, under the user who should be allowed to use that channel account, add the **exact `user_id`** the channel sends to the **`im:`** list.  
   - When someone sends a message, the channel often logs the `user_id` it's using (e.g. Feishu: "user_id=feishu_ou_xxx (add to config/user.yml under im)").  
   - Add that string to that user's `im:` list. Then Core will map that channel identity to that user and use their sandbox and data.

**Summary:**  
**Channel identity** (`user_id` + `channel_name`) → matched against **user.im** in **user.yml** → **system_user_id** (user.id/name) → used for sandbox, chat, memory, and permissions.

## Channel implementation review

For a **per-channel summary** of image/file support, logic, and crash safety, see **[CHANNEL_REVIEW.md](CHANNEL_REVIEW.md)**. The design doc for the image/file contract is **docs_design/ChannelImageAndFileInbound.md**.
