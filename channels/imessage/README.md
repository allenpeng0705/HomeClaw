# iMessage channel

HTTP webhook that an **iMessage bridge** calls (e.g. BlueBubbles with a small adapter, or a local script). The bridge runs on your machine, receives iMessage, POSTs to this channel, and sends our response back via iMessage. Core connection from **channels/.env** only.

## How it works

1. Run this channel: `python -m channels.run imessage` (listens on port 8012 by default).
2. Run your iMessage bridge so that:
   - On each incoming iMessage: POST to `http://127.0.0.1:8012/message` with `{ "user_id": "imessage_<chat_id>", "text": "<message>", "user_name": "..." }`.
   - Sends the response `{ "text": "..." }` back via iMessage.
3. Add `imessage_<id>` to `config/user.yml` under `im` for allowed users.

## Images and files

The bridge can send the same payload as Companion: in addition to `user_id`, `text`, `user_name`, include optional `images`, `videos`, `audios`, or `files` (data URLs or paths). The channel forwards them to Core `/inbound`. Core stores **images** in the user's **images** folder when the model doesn't support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.

## Run

```bash
python -m channels.run imessage
```

Set `IMESSAGE_CHANNEL_HOST`, `IMESSAGE_CHANNEL_PORT` in `channels/.env` if needed. For BlueBubbles, use an adapter that forwards messages to this webhook.
