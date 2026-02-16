# Signal channel

HTTP webhook that a **Signal bridge** calls (e.g. signal-cli with a small script). The bridge runs on your machine, receives Signal messages, POSTs to this channel, and sends our response back via Signal. Core connection from **channels/.env** only.

## How it works

1. You run this channel: `python -m channels.run signal` (listens on port 8011 by default).
2. You run a Signal bridge (e.g. signal-cli) that:
   - On each incoming Signal message: POST to `http://127.0.0.1:8011/message` with `{ "user_id": "signal_<number_or_id>", "text": "<message>", "user_name": "..." }`.
   - Takes the response `{ "text": "..." }` and sends it back via Signal.
3. Add `signal_<id>` to `config/user.yml` under `im` for allowed users.

## Run

```bash
python -m channels.run signal
```

Set `SIGNAL_CHANNEL_HOST`, `SIGNAL_CHANNEL_PORT` in `channels/.env` if needed. The bridge must be able to reach this server (localhost is fine if the bridge runs on the same machine).
