# LINE Channel

LINE Messaging API channel for HomeClaw. Receives message, image, video, audio, and file events via webhook; forwards to Core; sends replies via LINE reply or push API.

## Setup

1. Create a LINE channel at [LINE Developers Console](https://developers.line.biz/).
2. In **channels/line/**, create a `.env` file:

   ```
   LINE_CHANNEL_ACCESS_TOKEN=<your channel access token>
   LINE_CHANNEL_SECRET=<your channel secret>
   ```

3. Set the webhook URL in LINE Developers Console to:
   `https://<your-host>:<port>/line/webhook`
   (e.g. `https://example.com:8010/line/webhook` if the channel runs on port 8010.)

4. Add LINE user IDs to **config/user.yml** under `im`, e.g.:
   - `line:user:<userId>` for DMs
   - `line:group:<groupId>` for groups  
   Empty list = allow all.

## Run

From repo root:

```bash
python -m channels.run line
```

Or from **channels/line/**:

```bash
python channel.py
```

The channel listens on the host/port in **channels/line/config.yml** (default port 8010).

## Media

- **Image / video / audio / file:** Downloaded via LINE Get content API and saved under **channels/line/docs/**. Paths are sent to Core; Core runs file-understanding and uses them in the message.
- **Reply:** Core sends text back; the channel uses LINE reply (if we have a reply token) or push API.
