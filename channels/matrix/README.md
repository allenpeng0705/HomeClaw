# Matrix channel (full channel)

Full channel using **simplematrixbotlib** and **nio**. Logs in to a Matrix homeserver, receives room/DM messages, builds a `PromptRequest`, and sends to Core via **POST /process** (async: Core POSTs reply to this channel’s `/get_response`). Core connection from **channels/.env** only.

## Setup

1. **Install**: `pip install -r requirements.txt` (includes `simplematrixbotlib`, `nio`).
2. **Configure**: Create **channels/matrix/.env** with:
   - `home_server` — e.g. `https://matrix.org`
   - `username` — e.g. `@yourbot:matrix.org`
   - `password` — account password
3. **Core**: Set `core_host` and `core_port` (or `CORE_URL`) in **channels/.env**.
4. **Allow users**: In `config/user.yml`, add the Matrix user id (e.g. `matrix_@user:matrix.org` or as your channel maps it) under `im` for allowed users.

## Run

```bash
python -m channels.run matrix
# or
python -m channels.matrix.channel
```

Start **Core first**. Default: channel listens on `0.0.0.0:8005` (see `config.yml`). Invite the bot to a room or send a DM; messages are forwarded to Core and replies are sent back.

## Images and files

This channel uses the **same semantics as the Companion app**: media from Matrix (images, files) is downloaded to the channel docs folder or as data URLs and sent to Core in the `PromptRequest` as `images` and `files`. Core stores **images** in the user’s **images** folder when the model doesn’t support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.
