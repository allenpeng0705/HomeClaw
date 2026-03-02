# Channel implementation review

This document summarizes each channel’s behavior for **image/file support**, **logic correctness**, **feature coverage**, and **crash safety**. It complements the design doc `docs_design/ChannelImageAndFileInbound.md`.

**Four-step flow (images):**

1. **Receive** — Channel gets image/file from the platform (user upload).
2. **Forward to Core** — Channel sends `POST /inbound` with `text`, `images`, `videos`, `audios`, `files` (data URLs or paths).
3. **Receive from Core** — Core responds with `{"text": "...", "images": ["data:image/...;base64,..."]}` when the reply includes generated images.
4. **Send to user** — Channel decodes data URLs and sends images back on the platform.

---

## Summary table

| Channel       | Inbound (1→2)     | Outbound (3→4)    | Proxy bypass | Crash-safe notes                    |
|---------------|-------------------|-------------------|--------------|-------------------------------------|
| Slack         | ✅                | ✅                | ✅           | Full try/except; image upload in try |
| Telegram      | ✅                | ✅                | ✅           | Try/except; `r.json() if r.content else {}` |
| Discord       | ✅                | ✅                | ✅           | Try/except; `r.content` guard; reply fallback to channel.send |
| Webhook       | ✅                | ✅ (pass-through) | ✅           | Returns full `r.json()`; caller sends |
| iMessage      | ✅                | ✅ (pass-through) | ✅           | `r.json() if r.content`; out has images |
| Signal        | ✅                | ✅ (pass-through) | ✅           | Same as iMessage                    |
| Zalo          | ✅                | ✅ (pass-through) | ✅           | Same as iMessage                    |
| BlueBubbles   | ✅                | ✅ (pass-through) | ✅           | Same as iMessage                    |
| WhatsApp Web  | ✅                | ✅ (pass-through) | ✅           | Returns full Core response          |
| Feishu        | Payload only*     | ✅                | ✅           | Outbound: upload image → image_key, reply/send with msg_type=image |
| DingTalk      | Payload only*     | ✅                | ✅           | Outbound: upload → media_id, send via sessionWebhook when present |
| Teams         | ✅                | ✅                | ✅           | Reply: text + attachments (data URL or path→data URL) |
| Google Chat   | ✅                | ✅ (HTTPS URLs)   | ✅           | Reply: text + cardsV2 image widgets; GOOGLE_CHAT_IMAGE_BASE_URL for paths |
| WhatsApp      | ✅ (plugin)       | ✅                | ✅           | process_message_queue sends text + images via send_image |
| Matrix        | ✅ (plugin)       | ✅                | ✅           | process_message_queue: images list + data URL; send_image_message |
| Tinode        | ✅ (plugin)       | ✅                | ✅           | process_message_queue: text + images (path/data URL → Tinode JSON) |
| Line          | ✅                | ✅ (HTTPS URLs)   | ✅           | Plugin; text+images in one reply; LINE_IMAGE_BASE_URL for paths |
| Webchat       | ✅ (upload/paths) | ✅ (display)      | ✅           | Client; WS to Core; index.html shows data.images |

**Legend**

- **Payload only** (Inbound): The request body to Core already supports `images`, `videos`, `audios`, `files` (same shape as other channels). The channel does **not** yet implement the extra step to get binary data from the platform (e.g. Feishu `file_key` → call “get message resource” API → data URL). So the *payload shape* is in place; *population* of image/file data is not implemented yet.
- **Text only** (Outbound): The channel currently sends **only the reply text** to the user. The platform (Feishu, DingTalk) *does* support sending images in replies (e.g. Feishu `image_key`, DingTalk `media_id`), but this channel’s code does not yet implement upload + send of images. So outbound is “text only” until that is added.

**Feishu and DingTalk outbound (3→4) implemented:** Feishu: Core returns `images`; channel uploads each via `/im/v1/images` (image_type=message), gets `image_key`, then replies/sends with `msg_type=image`. DingTalk: Core returns `images`; channel gets access token (old gettoken), uploads via `media/upload` to get `media_id`, then sends image via `sessionWebhook` (when present in callback). If `sessionWebhook` is not in the stream callback, only text is sent; images are skipped.

**Image vs file in outbound (3→4):** Supporting **image** in outbound does **not** mean the channel supports **file**. Currently: **Outbound image** — Core returns `images` (or `image_links` for text-only clients). Channels that support it send those as images to the user. **Outbound file** — Core does **not** add a `files` or `file_links` list to the response. Tool-generated files (e.g. PDF, doc) are delivered as **links in the reply text** (e.g. from `get_file_view_link`); the channel sends the text and the user sees a clickable URL. No channel reads `files`/`file_links` from Core and attaches file bytes to the reply. So **file** outbound (3→4) is **not** implemented; only **text + image** outbound is.

\* Inbound “Payload only” = payload shape in place; platform may require extra download step (e.g. Feishu `file_key` → get resource).

---

## Per-channel review

### Slack (`channels/slack/channel.py`)

- **Inbound:** Message events include `event.files`; files are downloaded via `url_private` + bot token and converted to data URLs; `images`, `videos`, `audios`, `files` are sent in the same payload as Companion.
- **Outbound:** `post_to_core_sync` returns `{"text", "images"}`. Process handler reads `reply_images = result.get("images") or []`, decodes each with `Util.data_url_to_bytes(data_url)`, skips when `raw` is None, uploads via `web_client.files_upload` in the same thread. Text is sent with `chat_postMessage`; then images (up to 5).
- **Logic:** Empty or non-JSON Core response is handled (empty body branch sets reply; JSON branch uses try/except ValueError). Connection errors and generic exceptions are caught; return value is always `{"text": str, "images": list}`.
- **Crash safety:** Outer try/except in `post_to_core_sync`; process handler wraps `chat_postMessage` and the image upload loop in a single try/except — one failed upload logs and does not crash. `Util.data_url_to_bytes` returns None on invalid input, so no decode crash.
- **Proxy:** `trust_env=False` on `httpx.Client` so channel talks directly to Core (no HTTP_PROXY).

---

### Telegram (`channels/telegram/channel.py`)

- **Inbound:** Photo/document/audio/video from Bot API; file IDs are resolved via `getFile` + download to data URLs; payload includes `images`, `videos`, `audios`, `files`. Placeholder text when only media: e.g. "Image", "Video".
- **Outbound:** `handle_message` reads `reply_images = data.get("images") or []`. For each of the first 5 data URLs, decodes with `Util.data_url_to_bytes`; if raw is truthy, sends with `send_photo` (first image can have caption = reply text). Remaining text is sent with `send_message`.
- **Logic:** Correct ordering: images first (with optional caption on first), then text. Caption length capped at 1024 in `send_photo`.
- **Crash safety:** `handle_message` has try/except for Core call; on exception sets `reply` and `reply_images = []`. Uses `data = r.json() if r.content else {}` so empty or non-JSON Core response does not raise.
- **Proxy:** `trust_env=False` on all `AsyncClient` usages (Core and Telegram API).

---

### Discord (`channels/discord/channel.py`)

- **Inbound:** Attachments are iterated; each is downloaded via `download_attachment_to_data_url` and classified as image/video/audio/file; payload includes `images`, `videos`, `audios`, `files`. Placeholder text when only media.
- **Outbound:** `post_to_core` returns `{"text", "images"}`. In `on_message`, `reply_images = result.get("images") or []`; each data URL is decoded with `Util.data_url_to_bytes` and appended as `discord.File(BytesIO(raw), ...)` (up to 5). Reply: `message.reply(content=..., files=...)` or text only; on `discord.HTTPException` falls back to `message.channel.send(...)`.
- **Logic:** Text truncated to 2000 chars for Discord; empty content passed as None when only files.
- **Crash safety:** `post_to_core` uses `data = r.json() if r.content else {}` and always returns a dict with "text" and "images". If both `message.reply` and `message.channel.send` fail (e.g. permissions), the handler could raise; optional hardening: outer try/except in `on_message` to log and avoid killing the bot.
- **Proxy:** `trust_env=False` on all `AsyncClient` usages (Core and Discord attachment download).

---

### Webhook (`channels/webhook/channel.py`)

- **Inbound:** `WebhookMessage` accepts `images`, `videos`, `audios`, `files`. Body is forwarded with `model_dump(exclude_none=True)` to Core `/inbound`.
- **Outbound:** Handler returns `r.json()` on success — so Core’s full response (including `images`) is returned to the caller. The relay/bot calling the webhook must send text and images to the user.
- **Logic:** Straight pass-through; no image decoding in the channel.
- **Crash safety:** Non-200 from Core returns JSONResponse with status and error; ConnectError returns 503; other exceptions return 500. No `r.json()` on failure path (returns error payload), so no crash from invalid JSON. If Core returns 200 with malformed body, `r.json()` could raise; consider try/except and 500 with error message for extra safety.
- **Feature:** Contract supports full inbound and outbound; outbound is pass-through.

---

### iMessage (`channels/imessage/channel.py`)

- **Inbound:** `IMessageBody` has `images`, `videos`, `audios`, `files`; all passed through to Core.
- **Outbound:** Response is `{"text": reply or "(no reply)"}` and, when present, `out["images"] = data["images"]`. Bridge must send those images via BlueBubbles/iMessage API.
- **Logic:** `data = r.json() if r.content else {}` avoids JSON decode on empty response.
- **Crash safety:** ConnectError and Exception caught; always return a dict with at least "text". Images key only added when Core returns them.
- **Feature:** Full contract; bridge implements actual send.

---

### Signal (`channels/signal/channel.py`)

- **Inbound:** `SignalMessage` has `images`, `videos`, `audios`, `files`; forwarded to Core.
- **Outbound:** Same pattern as iMessage: `out["images"] = data["images"]` when present; bridge sends to user.
- **Logic/Crash safety:** Same as iMessage; `r.json() if r.content else {}`.

---

### Zalo (`channels/zalo/channel.py`)

- **Inbound:** `ZaloMessage` has `images`, `videos`, `audios`, `files`; forwarded to Core.
- **Outbound:** Same as iMessage/Signal; response includes `images` when Core returns them.
- **Logic/Crash safety:** Same; `r.json() if r.content else {}`.

---

### BlueBubbles (`channels/bluebubbles/channel.py`)

- **Inbound:** `BlueBubblesMessage` has `images`, `videos`, `audios`, `files`; forwarded to Core.
- **Outbound:** Same pass-through of `data["images"]` to the bridge.
- **Logic/Crash safety:** Same as iMessage/Signal/Zalo.

---

### WhatsApp Web (`channels/whatsappweb/channel.py`)

- **Inbound:** Accepts payload with `images`, `videos`, `audios`, `files`; forwards to Core.
- **Outbound:** Returns full `r.json()` from Core, so `images` are in the response; bridge sends to WhatsApp.
- **Crash safety:** Depends on error handling in the route (exceptions and non-200 handling); caller gets full response on success.

---

### Feishu (`channels/feishu/channel.py`)

- **Inbound:** Payload shape in place: `message.images`, `message.videos`, etc. are added to Core payload when present. Feishu often sends resource refs (e.g. `file_key`); converting those to data URLs would require calling Feishu’s “get message resource” API (not yet implemented).
- **Outbound:** Text plus images. `reply_accepts: ["text", "image"]`. Text sent via `reply_to_feishu_message` / `send_feishu_message`. For each of Core's `images` (up to 5): decode with `Util.data_url_to_bytes`, upload via `upload_feishu_image` (POST `/im/v1/images`, image_type=message), then `reply_to_feishu_message_with_image` or `send_feishu_image_message` with `msg_type=image` and `image_key`.
- **Logic:** URL verification at POST `/` and POST `/feishu/events`; challenge returned as `{"challenge": str}`. Deduplication by `message_id` (OrderedDict, FIFO eviction at 5000 entries). Encrypted payloads are skipped (TODO decrypt with `FEISHU_ENCRYPT_KEY`).
- **Crash safety:** `request.json()` wrapped in try/except; 400 on parse failure. Core call in try/except; reply default `"(no reply)"`. `data = r.json() if r.content else {}` (invalid JSON caught by outer except; reply/reply_images set). `reply_images` forced to list via `isinstance(_img, list)` so iteration is safe. Image loop: each upload/send in sequence; helpers return None/False on exception, so one failure does not crash; next image still attempted.
- **Proxy:** `trust_env=False` for Feishu and Core clients.

---

### DingTalk (`channels/dingtalk/channel.py`)

- **Inbound:** Payload includes `images`, `videos`, `audios`, `files` when provided by the stream SDK or callback data. Stream mode may not expose attachment URLs for all message types; when present, they are forwarded.
- **Outbound:** Text plus images. `reply_accepts: ["text", "image"]`. Text via `reply_text(reply, incoming_message)`. For images: access token from old gettoken (appkey/appsecret = client_id/client_secret); each Core `images` (up to 5) decoded with `Util.data_url_to_bytes`, uploaded via `upload_dingtalk_media` (oapi `media/upload`, type=image); then sent via `send_dingtalk_image_via_webhook(session_webhook, media_id)`. **Requires `sessionWebhook` in callback data**; if absent, only text is sent.
- **Logic:** Message parsed with `ChatbotMessage.from_dict`; on parse failure returns BAD_REQUEST. Core errors and exceptions set reply string and return OK so the stream does not break.
- **Crash safety:** try/except around parse and around Core POST; reply always set before `reply_text`. `r.json() if r.content else {}` (invalid JSON caught by except; reply_images = []). `reply_images` forced to list via `isinstance(_img, list)`. Image loop does not raise; token/upload/send helpers return None/False on exception; failures are logged.
- **Proxy:** `trust_env=False` for Core and DingTalk API (gettoken, media upload, webhook POST).

---

### Logic and stability review (Feishu & DingTalk outbound image)

- **Core response:** Both channels use `data = r.json() if r.content else {}`. If the body is non-empty but invalid JSON, `r.json()` raises and is caught by the existing try/except; `reply` and `reply_images` are set in the except block so the handler always returns 200 and does not crash.
- **reply_images type:** `data.get("images")` may be non-list (e.g. null, string). Both channels now set `reply_images = _img if isinstance(_img, list) else []` so the image loop never iterates over a string or None.
- **Data URL decode:** `Util.data_url_to_bytes(data_url)` returns `None` on invalid or non–data-URL input; both channels skip the item with `continue` when `raw`/`raw_bytes` is falsy. No decode crash.
- **Feishu:** `upload_feishu_image`, `reply_to_feishu_message_with_image`, and `send_feishu_image_message` catch all exceptions and return None/False; no exception propagates from the image loop. Text is sent before images; image send failure only logs.
- **DingTalk:** `get_dingtalk_access_token`, `upload_dingtalk_media`, and `send_dingtalk_image_via_webhook` catch exceptions and return None/False. Token is fetched only when `session_webhook` is present. Image loop does not raise; `reply_text` is always called so the stream flow is unchanged.
- **Conclusion:** Logic is correct (text first, then up to 5 images; reply vs send by message_id/chat_id for Feishu, sessionWebhook for DingTalk). No uncaught exceptions in the new paths; channels remain stable.

---

### Teams (`channels/teams/channel.py`)

- **Inbound:** Bot Framework message activities; attachments (image/video/audio/file) are downloaded via `contentUrl` to data URLs and sent to Core `/inbound`.
- **Outbound:** `send_reply(activity, reply_text, image_content_urls)` sends text plus up to 5 image attachments. Each item from Core `response_data["images"]` or `["image"]` can be a **data URL** (used as-is) or a **file path** (read and converted to data URL). Bot Framework Connector accepts `contentUrl` as data URL or HTTPS URL. Attachments are added to the reply activity and POSTed to the Connector.

---

### Google Chat (`channels/google_chat/channel.py`)

- **Inbound:** MESSAGE events; text and optional `message.images/videos/audios/files` are sent to Core `/inbound`.
- **Outbound:** Response includes `text` and, when Core returns images, **cardsV2** with image widgets. **Google Chat card imageUrl must be HTTPS.** Each item from `response_data["images"]` or `["image"]`: if already an `https://` URL it is used; if a file path and **GOOGLE_CHAT_IMAGE_BASE_URL** is set, URL is `GOOGLE_CHAT_IMAGE_BASE_URL` + basename(path). Data URLs are not supported in cards and are skipped. Up to 5 images in one card.

---

### WhatsApp (`channels/whatsapp/channel.py`) — plugin channel

- **Inbound:** Image/video/audio/document messages are downloaded (neonize `download_media`) and sent to Core as data URLs or paths in `PromptRequest`; `syncTransferTocore` posts to Core `/process`.
- **Outbound:** `process_message_queue` reads `response_data["text"]` and `response_data["images"]` (or `response_data["image"]`). Text is sent via `client.send_message(chat, text)`. For each image (path or data URL), bytes are resolved (path → read file; data URL → `Util.data_url_to_bytes`), written to a temp file if needed, and sent via `client.send_image(chat, path)` when available (neonize). Up to 5 images; temp files are removed after send.
- **Proxy:** `BaseChannel` uses `trust_env=False` for Core; shutdown uses `httpx.get(..., trust_env=False)`.

---

### Matrix (`channels/matrix/channel.py`) — plugin channel

- **Inbound:** `m.image` / `m.video` / `m.audio` / `m.file` are downloaded from Matrix media API to temp files and passed as paths in `PromptRequest`; `transferTocore` posts to Core `/process`.
- **Outbound:** `process_message_queue` handles `response_data["text"]`, `response_data["images"]` (list), and `response_data["image"]` (single). Each image can be a file path or a data URL; data URLs are decoded with `Util.data_url_to_bytes`, written to a temp file, and sent via `bot.api.send_image_message(room_id, image_filepath=path)`. Video is sent via `send_video_message`. Temp files from data URLs are unlinked after send. Up to 5 images.
- **Proxy:** `BaseChannel` and media download use `trust_env=False`; shutdown uses `httpx.get(..., trust_env=False)`.

---

### Tinode (`channels/tinode/channel.py`) — plugin channel

- **Inbound:** Text and image/audio/video/file messages are forwarded to Core via `PromptRequest` (images as data URLs; audio/video/files as paths). `syncTransferTocore` posts to Core `/process`.
- **Outbound:** `process_message_queue` pops `chat` (topic) by `msg_id`, sends `response_data["text"]` via `publish(chat, text)`, then sends each item in `response_data["images"]` or `response_data["image"]`. Each image (path or data URL) is converted to bytes, then to Tinode JSON format `{"ent": [{"data": {"mime": "...", "val": "<base64>"}}]}`, and sent via `publish(chat, content)`. Up to 5 images.
- **Proxy:** `BaseChannel` uses `trust_env=False`; shutdown uses `httpx.get(..., trust_env=False)`.

---

### Line (`channels/line/channel.py`)

- **Inbound:** Webhook receives message/image/video/audio/file; media is downloaded via LINE Get content API to `channels/line/docs/` and paths are sent to Core in `PromptRequest`; `syncTransferTocore` posts to Core `/process`.
- **Outbound:** `process_message_queue` builds a single `messages` array (LINE reply token is one-time use): text message first, then up to 5 image messages. **LINE requires HTTPS URLs** for images. For each item in `response_data["images"]` or `response_data["image"]`: if the item is already an `https://` URL it is used; if it is a file path and **LINE_IMAGE_BASE_URL** is set (in env), the URL is `LINE_IMAGE_BASE_URL` + basename(path) (you must serve those files at that base). Data URLs are not supported by LINE and are skipped. `send_line_messages` sends text + images in one reply or push call.
- **Proxy:** `BaseChannel` and `line/send.py` / `line/download.py` use `trust_env=False`.

---

### Webchat (`channels/webchat/`)

- **Inbound:** Browser client sends messages over **WebSocket to Core** (`/ws`). Images are uploaded via **POST /api/upload** (channel proxies to Core); Core returns paths, and the client sends them in the WS payload as `images`. So inbound images are supported (upload → paths → Core).
- **Outbound:** Core pushes responses over the same WebSocket (event `push` or inline). The channel server only proxies upload and KB sync; it does not process message queues. The **frontend** (`index.html`) displays `data.text` and, when `data.images` is present, renders each URL (data URL or path) as an `<img>` in the log. So outbound images are supported when Core includes `images` in the WS payload.
- **Proxy:** Proxies to Core use `trust_env=False`.

---

## Cross-cutting points

- **Proxy bypass:** All channels use `trust_env=False` on httpx clients (or `httpx.get(..., trust_env=False)` for one-off calls) so that Core and platform APIs are reached directly, not via `HTTP_PROXY`/`HTTPS_PROXY`. Plugin channels (WhatsApp, Matrix, Tinode) use `BaseChannel.transferTocore` / `syncTransferTocore`, which use `trust_env=False`; registration and deregistration also use it.
- **Core contract:** All channels that POST to Core use the same payload shape: `user_id`, `text`, `channel_name`, `user_name`, and optionally `images`, `videos`, `audios`, `files` (data URLs or paths). Core responds with `{"text": "...", "images": ["data:image/...;base64,..."]}` when the reply includes generated images.
- **Decoding:** Channels that send Core’s images to the user use `base.util.Util.data_url_to_bytes(data_url)`; it returns `None` on invalid or non-data-URL input, so callers should check before upload.
- **Limits:** Slack and Discord send at most 5 response images; Telegram caps at 5 and caps caption length. These avoid platform limits and oversized payloads.
- **Optional robustness:** (1) Prefer `data = r.json() if r.content else {}` when parsing Core response (Telegram, Discord, and webhook-style channels already do this where applicable). (2) In Discord, an outer try/except in `on_message` can catch send failures so one bad reply does not kill the bot. (3) In Slack, wrapping each `files_upload` in its own try/except would isolate one failing image (current single try/except for the whole block is already safe).

---

## Reply-accepts implementation review (logic + crash safety)

All changes use **reply_accepts** per `docs_design/ReplyAcceptsPattern.md`: clients declare what they accept (default text-only); Core sends inline images only when `"image"` is in **reply_accepts**, otherwise text or **image_links** (when Core has a public URL).

### Core

- **`base/base.py`:** `InboundRequest` and `PromptRequest` have `reply_accepts: Optional[List[str]] = None`. No required-field change; existing callers omit it and get `None`. **Crash:** None (optional field, default `None`).
- **`core/result_viewer.py` — `build_image_view_links(image_paths, scope)`:** Returns `[]` when `image_paths` is empty, when `get_result_link_base_url()` is empty, when `homeclaw_root` is missing, or when a path is outside sandbox. All branches use try/except or early return. **Crash:** None (docstring: "Never raises").
- **`core/route_registration.py` — sync POST /inbound:** `reply_accepts = getattr(request, "reply_accepts", None)`; if `None` or not a list, use `["text"]`. When client does not accept image, `scope = (getattr(request, "user_id", None) or "").strip() or "companion"`; `build_image_view_links` returns a list; link lines appended with `str(content.get("text") or "")` and try/except. **Crash:** None.
- **`core/core.py` — async plugin response:** Same pattern: `getattr(request, "reply_accepts", None)` defaulting to `["text"]`; `scope` from `user_id` or `system_user_id` or `"companion"`; `build_image_view_links`; text append with `str(resp_data.get("text") or "")` and try/except. **Crash:** None.
- **`core/inbound_handlers.py` — run_async_inbound:** `reply_accepts` from request; when not accepting image, `build_image_view_links` and entry update inside try/except; `str(entry.get("text") or "")` for append. Outer try/except stores a failure entry on any exception. **Crash:** None. **PromptRequest** in `handle_inbound_request_impl` gets `reply_accepts=getattr(request, "reply_accepts", None)` — safe.

### Channels (payload + response handling)

- **Slack:** Payload includes literal `"reply_accepts": ["text", "image"]`. Response: `data.get("text", "")`, `data.get("images") or []`; return always `{"text": ..., "images": ...}`. **Crash:** None.
- **Feishu:** Payload includes `"reply_accepts": ["text"]`. `data = r.json() if r.content else {}`; `reply = data.get("text", "")`. **Crash:** None.
- **DingTalk:** Same as Feishu; `data = r.json() if r.content else {}`. **Crash:** None.
- **Telegram:** `reply_accepts: ["text", "image"]`. `data = r.json() if r.content else {}`; `reply_images = data.get("images") or []`; `Util.data_url_to_bytes` used only when sending; loop skips when `raw` is None. **Crash:** None.
- **Discord:** Same pattern; `data.get("images") or []`; return always includes `"images"`. **Crash:** None.
- **Teams:** `reply_accepts: ["text", "image"]`. `reply_images = data.get("images") or ([data["image"]] if data.get("image") else [])` — `data["image"]` only when `data.get("image")` is truthy, so key exists. **Crash:** None.
- **Google Chat:** Same reply_images pattern as Teams; iteration over `(reply_images or [])[:5]` with `isinstance(item, str)` check. **Crash:** None.
- **Signal:** `reply_accepts: ["text", "image"]`. `SignalMessage.user_id` is required (str); `data.get("images")` used only to set `out["images"]` when truthy. **Crash:** None.
- **iMessage:** Same as Signal; `IMessageBody.user_id` required. **Crash:** None.
- **Zalo, BlueBubbles:** Same pattern; payload + `data.get(...)` and optional `out["images"]`. **Crash:** None.
- **WhatsApp Web:** `payload.setdefault("reply_accepts", ["text", "image"])`; forwards body then setdefault; response is `r.json()`. **Crash:** None.
- **Webhook:** Forwards `body.model_dump(exclude_none=True)`; no default **reply_accepts** (caller may send it). Core defaults to text-only when omitted. **Crash:** None.
- **WhatsApp, Matrix, Tinode, Line (plugin):** Each builds `PromptRequest(..., reply_accepts=["text", "image"])`. Optional field; Pydantic accepts it. **Crash:** None.

### Summary

- **Logic:** Default `["text"]` when **reply_accepts** missing or not a list; `"image" in reply_accepts` controls inline vs links vs text-only; scope from `user_id` or `"companion"`; image_links only when Core has public URL.
- **Crash safety:** All new code uses getattr with defaults, `.get()` for dicts, try/except around link building and text append, and `str(... or "")` before string concatenation. No unguarded KeyError, AttributeError, or TypeError.

---

## References

- **Design:** `docs_design/ChannelImageAndFileInbound.md` (inbound/outbound contract, storage, per-channel status).
- **Reply-accepts pattern:** `docs_design/ReplyAcceptsPattern.md` — channels and Companion declare what they can receive (text, image, file); default text-only; Core can send links instead of inline media when not accepted.
- **Data URL helper:** `base.util.Util.data_url_to_bytes`.
- **Core inbound API:** `POST /inbound`; request/response shape in `base/base.py` and `core/route_registration.py`.
