# Feishu (飞书 / Lark) channel

Receives **Feishu Open Platform** event callbacks (request URL mode). On `im.message.receive_v1`: forwards to Core `/inbound` and sends the reply via the Feishu API. Core connection from **channels/.env** only.

Inspired by the other agent Feishu plugin: [clawdbot-feishu](https://github.com/m1heng/clawdbot-feishu).

## You don't need a Feishu "server"

Run the Feishu channel on **your own machine** (same as Core). Expose it to the internet with a **tunnel** (ngrok, cloudflared, etc.) so Feishu can send events to it. No separate server or VPS required.

**Example (ngrok):** In one terminal run `python -m channels.run feishu` (listens on 8016). In another run `ngrok http 8016`. Copy the HTTPS URL ngrok shows (e.g. `https://abc123.ngrok.io`) and in Feishu set the callback URL to `https://abc123.ngrok.io/feishu/events`.

**Example (Cloudflare Tunnel):** If you already use `cloudflared` for Core, run a second tunnel for the Feishu channel: `cloudflared tunnel --url http://127.0.0.1:8016` (or add 8016 to your existing setup). Use the resulting URL + `/feishu/events` in Feishu.

## Setup

1. **Feishu Open Platform**: Create an app at [open.feishu.cn](https://open.feishu.cn) (or [open.larksuite.com](https://open.larksuite.com) for Lark).
2. **Permissions**: Enable at least:
   - `im:message` — send and receive messages
   - `im:message.p2p_msg:readonly` — read DMs to the bot
   - `im:message.group_at_msg:readonly` — receive @mentions in groups
   - `im:message:send_as_bot` — send messages as the bot
3. **Events**: In **Events & Callbacks** (事件与回调), under **订阅方式**, select **「将事件发送至 开发者服务器」**. Add event `im.message.receive_v1`. Set **请求地址** (Request URL) to your tunnel URL + `/feishu/events` (e.g. `https://abc123.ngrok.io/feishu/events`). You can also use the root URL (e.g. `https://abc123.ngrok.io/`) for verification only—the channel returns the challenge on both `/` and `/feishu/events`.
4. **channels/.env** (or **channels/feishu/.env**): Set `FEISHU_APP_ID`, `FEISHU_APP_SECRET`. To use a different port than 8016, set `FEISHU_CHANNEL_PORT=端口号` (e.g. `FEISHU_CHANNEL_PORT=9016`). Optional: `FEISHU_CHANNEL_HOST` (default `0.0.0.0`), `FEISHU_BASE_URL`, `FEISHU_EVENT_PATH`.
5. **config/user.yml**: Add `feishu_<user_id>` under `im` for allowed users.

## Run

```bash
python -m channels.run feishu
```

Listens on `0.0.0.0:10046`. Start a tunnel (ngrok, cloudflared, etc.) to that port and use the tunnel’s HTTPS URL + `/feishu/events` in Feishu.

## "Timeout" when saving Request URL

If Feishu says **timeout** when you save the event callback URL:

1. **Channel and tunnel must be running** before you click Save. Start `python -m channels.run feishu`, then start your tunnel (e.g. `ngrok http 8016`), then save in Feishu.
2. **Use the HTTPS URL** Feishu can reach: the tunnel’s public URL (e.g. `https://abc123.ngrok.io`), not `http://127.0.0.1:8016`. Add path `/feishu/events` (e.g. `https://abc123.ngrok.io/feishu/events`).
3. **Check the channel console**: When you click Save, you should see `[Feishu] URL verification received, returning challenge...`. If you see that but Feishu still times out, the response is not reaching Feishu (slow tunnel, firewall, or Feishu blocking). If you never see it, the request is not reaching your app (wrong URL, tunnel not running, or tunnel pointing to wrong port).
4. **Free tunnel cold start**: With free ngrok, the first request after idle can be slow; try saving again once the tunnel is warm.

## Images and files

Feishu uses the **same request as the Companion app**: **POST /inbound** with `text`, `images`, `videos`, `audios`, and `files`. The event payload may include `message.images`, `message.files`, etc. (e.g. by `file_key`); to send binary content to Core, the channel must download via Feishu’s message-resource API and pass **data URLs** or paths. Core stores **images** in the user’s **images** folder when the model doesn’t support vision; **files** are processed by file-understanding (documents can be added to Knowledge base). See **docs_design/ChannelImageAndFileInbound.md**.

**Outbound images:** When Core returns images in the reply, the channel uploads each (up to 5) via Feishu `/im/v1/images` (image_type=message), then sends them with `msg_type=image` in the same thread (reply or new message to chat).

## Connection mode

This channel uses **webhook (Request URL)** only. It does not use `HTTP_PROXY`/`HTTPS_PROXY` (connects directly to Core and to Feishu API). Feishu’s **长连接** (long connection) mode would require a different implementation (WebSocket client); for now, webhook + a tunnel is the supported way.
