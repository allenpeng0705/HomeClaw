# Multimodal (images + text) via channels to Core

When you use a **vision-capable local model** (e.g. LLaVA with `mmproj` in `config/core.yml`), you can send **images + text** from a channel to Core. Core builds an OpenAI-style multimodal message (text + `image_url` parts) and calls the vision model.

---

## 1. How to send images

### POST /inbound

Request body (JSON):

- **text** (required): User message text.
- **images** (optional): List of image payloads. Each item can be:
  - **Data URL**: `"data:image/jpeg;base64,<base64-string>"` or `"data:image/png;base64,..."`.
  - **Raw base64**: Just the base64 string; Core wraps it as `data:image/jpeg;base64,<string>`.
  - **File path**: Path on the Core server (e.g. from an upload dir); Core reads the file and base64-encodes it. Only use when the client and Core share the same filesystem or upload path.

Example (data URL):

```json
{
  "user_id": "telegram_123",
  "text": "What's in this image?",
  "images": ["data:image/jpeg;base64,/9j/4AAQSkZJRg..."]
}
```

Example (multiple images):

```json
{
  "user_id": "user1",
  "text": "Compare these two screenshots.",
  "images": [
    "data:image/png;base64,iVBORw0KGgo...",
    "data:image/png;base64,iVBORw0KGgo..."
  ]
}
```

When **auth_enabled** is true, include `X-API-Key` or `Authorization: Bearer <key>` in the request headers.

### WebSocket /ws

Send a JSON message with the same shape:

- **user_id**, **text** (required).
- **images** (optional): Same as above (list of data URLs, raw base64, or paths).

Example frame:

```json
{
  "user_id": "ws_user",
  "text": "Describe this image.",
  "images": ["data:image/jpeg;base64,/9j/4AAQ..."]
}
```

When **auth_enabled** is true, send `X-API-Key` or `Authorization: Bearer <key>` in the WebSocket handshake headers.

---

## 2. Full channels (/process, /local_chat)

Channels that use **PromptRequest** (e.g. full channel implementations) already have:

- **contentType**: `TEXT`, `TEXTWITHIMAGE`, or `IMAGE`.
- **images**: List of **file paths** (paths on the server where the channel wrote uploaded images).

Core converts those paths to data URLs when building the multimodal user message. So full channels only need to set `contentType` and `images` (paths) on the request; no change to the Core API.

---

## 3. Flow inside Core

1. **Inbound** (/inbound or /ws): Request has **text** and optional **images** (data URLs, base64, or paths). Core builds a **PromptRequest** with `contentType=TEXTWITHIMAGE` when images are present.
2. **process_text_message**: If `request.images` is non-empty, the current user message is built as **multimodal content**: `[{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:..."}}, ...]`. Otherwise it is plain text.
3. **answer_from_memory** → **openai_chat_completion**: Messages are sent to the LLM as-is. Vision models (llama-server with `--mmproj`) accept the OpenAI-compatible format with `image_url` parts.
4. **Chat history**: Only the **text** part of the user message is stored in history (so past turns remain text-only; the current turn can be text + images).

---

## 4. Other channels (Tinode, Matrix, WeChat, WhatsApp, Email)

These channels already use **PromptRequest** with **images=[]** and **contentType=TEXT**. They do **not** yet pass images to Core. Core already accepts **request.images** (list of paths or data URLs) and **contentType=TEXTWITHIMAGE**; no Core change is needed. To support multimodal, each channel only needs to **populate** `request.images` and set `contentType` when the platform sends an image.

| Channel | Current behavior | What to do to support images |
|--------|------------------|------------------------------|
| **Tinode** | Builds `PromptRequest` with `images=[]`. In the message loop, `data_type == 'image'` is handled with a TODO and does not call Core. | When `data_type == 'image'`, get image from `content_dict['ent'][0]['data']['val']` (base64). Build `data:image/<subtype>;base64,<val>` and set `request.images = [data_url]`, `contentType = ContentType.TEXTWITHIMAGE`, then call Core (e.g. `transferTocore` or equivalent) instead of `pass`. Use a short `text` (e.g. "User sent an image" or caption if available). |
| **Matrix** | Builds `PromptRequest` from `message.source['content']['body']` (text only); `images=[]`. | For `m.image` events, get image URL from content (e.g. `content.url` or `content.info.url`), download to a temp file (or fetch and base64). Set `request.images = [path]` or `[data_url]`, `contentType = ContentType.TEXTWITHIMAGE`, `text` = body or "Image". |
| **WeChat** (wcferry) | Builds `PromptRequest` from `msg.content` (text); `images=[]`. | When `WxMsg` indicates image type (e.g. `msg.type` or message kind), use wcferry API to get image path or bytes. Set `request.images = [path]` or `[data_url]`, `contentType = ContentType.TEXTWITHIMAGE`, `text` = caption or "Image". |
| **WhatsApp** (neonize) | `handle_message` only reads `message.Message.conversation` or `extendedTextMessage.text`; builds `PromptRequest` with `images=[]`. | Add a branch for image messages (e.g. `message.Message.imageMessage`). Download or get image bytes, save to temp path or base64. Set `request.images = [path_or_data_url]`, `contentType = ContentType.TEXTWITHIMAGE`, `text` = caption or "Image", then `syncTransferTocore(request)`. |
| **Email** | Builds `PromptRequest` from subject/body only; `images=[]`. `fetch_email_content` returns body text and does not extract attachments. | In `fetch_email_content` (or when building the request), iterate `msg.get_payload()` for parts with `Content-Disposition: attachment` or image `Content-Type`. Decode and write to temp files (or base64). Set `request.images = [path, ...]`, `contentType = ContentType.TEXTWITHIMAGE` when any image attachment, and keep body as `text`. |

**Summary**

- **Core**: Already supports `PromptRequest.images` (paths or data URLs) and builds multimodal user content in `process_text_message`. No Core change.
- **Channels**: Each channel needs a small, platform-specific change: when the platform delivers an image, obtain a **path** (file on disk) or **data URL** (base64), set `request.images = [path_or_data_url, ...]` and `request.contentType = ContentType.TEXTWITHIMAGE`, then send the same `PromptRequest` to Core as today.

---

## 5. Requirements

- **Vision model**: In `config/core.yml`, the main (or chosen) local model must have **mmproj** set so llama-server is started with `--mmproj` (see config comments for vision models).
- **Capabilities**: For tool use (e.g. **image** tool), the model should have a capability that indicates vision (e.g. `Chat` or a dedicated vision capability) so it can be selected for image tasks.
- **Channels**: For Tinode, Matrix, WeChat, WhatsApp, and Email to send images to Core, each channel must be extended to detect image messages, obtain a path or data URL, and set `request.images` and `contentType=TEXTWITHIMAGE` before calling Core (see §4).
