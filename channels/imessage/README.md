# iMessage channel

HTTP webhook that an **iMessage bridge** calls (e.g. BlueBubbles with a small adapter, or a local script). The bridge runs on your machine, receives iMessage, POSTs to this channel, and sends our response back via iMessage. Core connection from **channels/.env** only.

## How it works

1. Run this channel: `python -m channels.run imessage` (listens on port 8012 by default).
2. Run your iMessage bridge so that:
   - On each incoming iMessage: POST to `http://127.0.0.1:8012/message` with `{ "user_id": "imessage_<chat_id>", "text": "<message>", "user_name": "..." }`.
   - Sends the response `{ "text": "..." }` back via iMessage.
3. Add `imessage_<id>` to `config/user.yml` under `im` for allowed users.

## Run

```bash
python -m channels.run imessage
```

Set `IMESSAGE_CHANNEL_HOST`, `IMESSAGE_CHANNEL_PORT` in `channels/.env` if needed. For BlueBubbles, use an adapter that forwards messages to this webhook.
