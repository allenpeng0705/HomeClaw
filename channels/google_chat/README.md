# Google Chat channel

Runs an HTTP server that receives **Google Chat API** interaction events. On MESSAGE, forwards to Core `/inbound` and returns the reply. Core connection from **channels/.env** only.

## Setup

1. **Google Cloud**: Enable [Google Chat API](https://console.cloud.google.com/apis/api/chat.googleapis.com), create/configure a Chat app.
2. **Connection settings**: Set the app's **HTTP endpoint URL** to your server (e.g. `https://your-host:8010/` or use ngrok for local dev).
3. **Allow users**: In `config/user.yml`, add `google_chat_<user_id>` under `im` for a user with `IM` permission. The channel uses `user.name` from the event (e.g. `users/123` → `google_chat_123`).

## Run

```bash
python -m channels.run google_chat
# or
python -m channels.google_chat.channel
```

Default: listen on `0.0.0.0:8010`. Set `GOOGLE_CHAT_HOST`, `GOOGLE_CHAT_PORT` in `channels/.env` if needed.

## Images and files

This channel uses the **same request as the Companion app**: **POST /inbound** with `text`, `images`, `videos`, `audios`, and `files`. When the event includes attachments, the channel forwards `images` and `files` to Core. Core stores **images** in the user's **images** folder when the model doesn't support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). **Reply images:** When Core returns `images`, the channel adds them to the response as **cardsV2** image widgets. Google Chat requires **HTTPS** URLs for card images; set **GOOGLE_CHAT_IMAGE_BASE_URL** (e.g. `https://yourserver.com/files`) in env so file paths are turned into URLs, or ensure Core returns `https://` image URLs. See **docs_design/ChannelImageAndFileInbound.md** and **channels/CHANNEL_REVIEW.md**.

## Local dev

Expose your local server (e.g. ngrok) and put that URL in the Chat app configuration so Google can POST events to your machine.
