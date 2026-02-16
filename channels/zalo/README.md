# Zalo channel

HTTP webhook that a **Zalo OA (Official Account) bridge** or adapter calls. The bridge runs on your machine, receives Zalo messages (e.g. via Zalo OA webhook), POSTs to this channel, and sends our response back via the Zalo API. Core connection from **channels/.env** only.

## How it works

1. Run this channel: `python -m channels.run zalo` (listens on port 8015 by default).
2. Run your Zalo OA bridge so that:
   - On each incoming Zalo message: POST to `http://127.0.0.1:8015/message` with `{ "user_id": "zalo_<user_id>", "text": "<message>", "user_name": "..." }`.
   - Sends the response `{ "text": "..." }` back via the Zalo OA API.
3. Add `zalo_<id>` to `config/user.yml` under `im` for allowed users.

## Run

```bash
python -m channels.run zalo
```

Set `ZALO_CHANNEL_HOST`, `ZALO_CHANNEL_PORT` in `channels/.env` if needed. The bridge must be able to reach this server (localhost is fine if the bridge runs on the same machine).

## Zalo OA setup

Set up a Zalo Official Account and configure your webhook to call your bridge; the bridge then forwards to this channel and uses the reply with the [Zalo OA API](https://developers.zalo.me/docs/api/official-account-api/) to send messages back to the user.
