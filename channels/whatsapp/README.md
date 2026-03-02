# WhatsApp channel (full channel)

Full channel using the **Neonize/WhatsApp Multi-Device** stack. Receives messages from WhatsApp, builds a `PromptRequest`, and sends to Core via **POST /process** (async: Core POSTs reply to this channel’s `/get_response`). Core connection from **channels/.env** only.

## Setup

1. **Install**: `pip install -r requirements.txt` (includes `neonize`).
2. **Configure**: Core connection: set `core_host` and `core_port` (or `CORE_URL`) in **channels/.env**. Optional: `channels/whatsapp/.env` for channel-specific options.
3. **Allow users**: In `config/user.yml`, add `whatsapp_<user_id>` (or the identity your channel uses) under `im` for allowed users.
4. **First run**: The channel will pair with WhatsApp (e.g. QR or link); session is stored (e.g. `db.sqlite3` in the channel folder).

## Run

```bash
python -m channels.run whatsapp
# or
python -m channels.whatsapp.channel
```

Start **Core first**. Default: channel listens on `0.0.0.0:8006` (see `config.yml`).

## Images and files

This channel uses the **same semantics as the Companion app**: media (image, video, audio, document) is downloaded via `_download_media_to_path_or_data_url` and sent to Core in the request as `images`, `videos`, `audios`, or `files` (paths or data URLs). Core stores **images** in the user’s **images** folder when the model doesn’t support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.
