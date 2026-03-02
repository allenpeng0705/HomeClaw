# BlueBubbles channel

[BlueBubbles](https://bluebubbles.app/) exposes iMessage as an API. This channel runs a **webhook server** that your BlueBubbles bridge calls: bridge POSTs incoming messages here; we forward to Core `/inbound` and return the reply text. The bridge sends that reply back via the BlueBubbles API.

## Setup

1. Run BlueBubbles server and your bridge (webhook or poller) that receives iMessage events.
2. Configure the bridge to POST to this channel’s `/message` endpoint (e.g. `http://host:8017/message`) with body: `{ "user_id": "bluebubbles_<chat_id>", "text": "user message" }`. Optional: `user_name`.
3. Bridge reads the response `{ "text": "..." }` and sends it back via BlueBubbles API.
4. **channels/.env**: Core connection only (core_host, core_port or CORE_URL). Optional: `BLUEBUBBLES_CHANNEL_PORT` (default 8017), `BLUEBUBBLES_CHANNEL_HOST`.
5. **config/user.yml**: Add `bluebubbles_<id>` under `im` for allowed users if you use allowlists.

## Images and files

The bridge can send the same payload as Companion: in addition to `user_id`, `text`, `user_name`, include optional `images`, `videos`, `audios`, or `files` (data URLs or paths). The channel forwards them to Core `/inbound`. Core stores **images** in the user's **images** folder when the model doesn't support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.

## Run

```bash
python -m channels.run bluebubbles
```

Default: listen on `0.0.0.0:8017`. Point your BlueBubbles bridge at `http://<host>:8017/message`.
