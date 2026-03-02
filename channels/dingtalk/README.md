# DingTalk (钉钉) channel

Uses **DingTalk Stream mode** (WebSocket, no public IP required). Receives messages via the [dingtalk-stream](https://github.com/open-dingtalk/dingtalk-stream-sdk-python) SDK, forwards to Core `/inbound`, and replies with `reply_text`. Core URL from **channels/.env**; DingTalk credentials from **channels/dingtalk/.env** (or channels/.env).

Inspired by the other agent DingTalk plugin: [other-agent-channel-dingtalk](https://github.com/soimy/other-agent-channel-dingtalk).

## Setup

1. **DingTalk Developer Console**: Create an **internal** app at [open.dingtalk.com](https://open.dingtalk.com). Add **Robot** capability and set message receiving to **Stream mode**. Publish the app.
2. **Credentials**: From the app page, get **Client ID** (AppKey) and **Client Secret** (AppSecret).
3. **channels/dingtalk/.env**: Set `DINGTALK_CLIENT_ID` and `DINGTALK_CLIENT_SECRET` (or set them in channels/.env).
4. **config/user.yml**: Add the DingTalk id under `im` for the user who may message the bot. When someone sends a message, the channel prints: `[DingTalk] sender_id=... → add to config/user.yml im: dingtalk_...` — add that **exact** value (e.g. `dingtalk_$:LWCP_v1:$PYr83ZBtc0VPbbkOaB1BNw==`) to the user's `im:` list. Matching is case-insensitive.

**No Core log when you send from DingTalk?** Then the request is not reaching Core. (1) Ensure Core is running and **channels/.env** has `core_host` and `core_port` (or `CORE_URL`) pointing to Core (e.g. `core_port=9000`). (2) The channel uses direct connection to Core (no HTTP proxy). (3) In the **DingTalk channel** console you should see `DingTalk → Core: user_id=... status=200` (or 403, etc.) when a message is sent — if you see `status=200` but still "Request failed", Core did receive it (check Core's log file, e.g. `logs/core_debug.log`, for "POST /inbound received" or "IM permission denied").

## Run

```bash
python -m channels.run dingtalk
```

The process opens a WebSocket connection to DingTalk and stays running. No HTTP callback URL or public IP is required for Stream mode.

## Images and files

DingTalk uses the **same request as the Companion app**: **POST /inbound** with `text`, `images`, `videos`, `audios`, and `files`. The payload already includes these fields when the Stream SDK provides attachment data. Core stores **images** in the user’s **images** folder when the model doesn’t support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.

**Outbound images:** When Core returns images, the channel uploads each (up to 5) via DingTalk `media/upload` to get `media_id`, then sends them via the callback's **sessionWebhook** with `msgtype: image`. If the stream callback does not include `sessionWebhook`, only the text reply is sent (no images).

## Connection mode

This channel uses **Stream mode** only (WebSocket long connection). For webhook/card modes or advanced options (e.g. `robotCode`, `corpId`, `agentId`), see the [other agent DingTalk plugin](https://github.com/soimy/other-agent-channel-dingtalk) and DingTalk docs.
