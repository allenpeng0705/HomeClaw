# Tinode channel (full channel)

Full channel using **Tinode gRPC**. Connects to a Tinode server, receives chat messages, builds a `PromptRequest`, and sends to Core via **POST /process** (async: Core POSTs reply to this channel’s `/get_response`). Core connection from **channels/.env** only.

## Setup

1. **Install**: `pip install -r requirements.txt` (includes `tinode_grpc`, `pydub`, etc.).
2. **Configure**: Tinode server and credentials (see channel `.env` or config). Core: set `core_host` and `core_port` (or `CORE_URL`) in **channels/.env**.
3. **Allow users**: In `config/user.yml`, add the Tinode user id (as your channel maps it) under `im` for allowed users.

## Run

```bash
python -m channels.run tinode
# or
python -m channels.tinode.channel
```

Start **Core first**. Default: channel listens on `0.0.0.0:8007` (see `config.yml`). Optional: set `TINODE_ALLOW_SAME_USER=1` in env to process messages from the same account (e.g. mobile + channel).

## Images and files

This channel uses the **same semantics as the Companion app**: images are sent as data URLs in the `PromptRequest`; other files are saved to the channel docs folder and sent as `files` (paths). Core stores **images** in the user’s **images** folder when the model doesn’t support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.
