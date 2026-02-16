# DingTalk (钉钉) channel

Uses **DingTalk Stream mode** (WebSocket, no public IP required). Receives messages via the [dingtalk-stream](https://github.com/open-dingtalk/dingtalk-stream-sdk-python) SDK, forwards to Core `/inbound`, and replies with `reply_text`. Core connection from **channels/.env** only.

Inspired by the other agent DingTalk plugin: [other-agent-channel-dingtalk](https://github.com/soimy/other-agent-channel-dingtalk).

## Setup

1. **DingTalk Developer Console**: Create an **internal** app at [open.dingtalk.com](https://open.dingtalk.com). Add **Robot** capability and set message receiving to **Stream mode**. Publish the app.
2. **Credentials**: From the app page, get **Client ID** (AppKey) and **Client Secret** (AppSecret).
3. **channels/.env**: Set `DINGTALK_CLIENT_ID` and `DINGTALK_CLIENT_SECRET`.
4. **config/user.yml**: Add `dingtalk_<sender_id>` under `im` for allowed users if you use allowlists.

## Run

```bash
python -m channels.run dingtalk
```

The process opens a WebSocket connection to DingTalk and stays running. No HTTP callback URL or public IP is required for Stream mode.

## Connection mode

This channel uses **Stream mode** only (WebSocket long connection). For webhook/card modes or advanced options (e.g. `robotCode`, `corpId`, `agentId`), see the [other agent DingTalk plugin](https://github.com/soimy/other-agent-channel-dingtalk) and DingTalk docs.
