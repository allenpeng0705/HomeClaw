# Microsoft Teams channel

HTTP endpoint that receives **Bot Framework** activities (e.g. from Teams). On message: forwards to Core `/inbound`, then sends the reply via the Bot Framework Connector API. Core connection from **channels/.env** only.

## Setup

1. **Azure Bot / Teams**: Create a bot in [Azure Bot Service](https://portal.azure.com) or Teams developer portal; get **Microsoft App ID** and **App Password**.
2. **Configure messaging endpoint**: Set your bot's endpoint to `https://your-host:8013/api/messages` (or use ngrok for local dev).
3. **channels/.env**: Set `TEAMS_APP_ID` and `TEAMS_APP_PASSWORD` (or `MICROSOFT_APP_ID`, `MICROSOFT_APP_PASSWORD`) so the channel can send replies via the Connector API.
4. **config/user.yml**: Add `teams_<user_id>` under `im` for allowed users (use the `from.id` from the activity).

## Run

```bash
python -m channels.run teams
```

Default: listen on `0.0.0.0:8013`. Set `TEAMS_CHANNEL_HOST`, `TEAMS_CHANNEL_PORT` in `channels/.env` if needed.
