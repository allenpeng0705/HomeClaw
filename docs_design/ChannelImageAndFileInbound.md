# Channel image and file support

All channels (Slack, DingTalk, Feishu, WhatsApp, WhatsApp Web, Google Chat, Signal, Discord, Matrix, Teams, Telegram, Tinode, Zalo, and others) can send **images and files** to Core using the **same request format as the Companion app**: **POST /inbound** (or, for full channels, `PromptRequest` with the same `images` / `files` semantics) with data URLs or paths.

---

## 1. Same request as Companion

Core accepts **POST /inbound** with JSON body (`InboundRequest` in `base/base.py`):

- **text** (required) — e.g. user message or `"See attached."` when sending only media
- **images** — list of **data URLs** (`data:image/...;base64,...`) or **file paths** Core can read
- **videos** — list of data URLs or paths
- **audios** — list of data URLs or paths
- **files** — list of data URLs or paths; Core runs **file-understanding** (images in `files` are treated as images; other types as documents/audio/video)

Channels that receive attachments from the platform should:

1. Download each attachment (Slack file URL, Feishu file_key, DingTalk stream payload, etc.).
2. Convert to **data URL** (e.g. `data:image/jpeg;base64,...`) or save to a path under the user sandbox and pass the path.
3. Send the same payload: `user_id`, `text`, `channel_name`, `user_name`, and optionally `images`, `videos`, `audios`, `files`.

No separate API: the channel just adds these fields to the same `/inbound` call.

---

## 2. Per-channel status

| Channel   | Images / files to Core |
|----------|-------------------------|
| **Slack** | **Supported.** Message `event.files` downloaded via `url_private` + bot token to data URLs; images/videos/audios/files sent in same payload as Companion. |
| **DingTalk** | Payload shape in place (`images`, `videos`, `audios`, `files`). Stream SDK may not expose attachment URLs in all message types; when provided, channel forwards them. |
| **Feishu** | Payload shape is in place (`message.images`, `message.videos`, etc.). Feishu events may reference resources by `file_key`; the channel would need to call Feishu’s “get message resource” API, download the file, and convert to data URL (or save under user sandbox and pass path) to fully support attachments. |
| **WhatsApp** | **Supported.** Media downloaded to path or data URL; images/videos/audios/files sent in PromptRequest to Core (full channel). |
| **WhatsApp Web** | **Supported.** Webhook payload accepts `images`, `videos`, `audios`, `files` (data URLs or paths); forwarded as-is to Core `/inbound`. Bridge must provide them. |
| **Google Chat** | Payload accepts `images`, `files` from event `msg`; forwards to Core when present. |
| **Signal** | Webhook body accepts `images`, `files`; forwarded to Core `/inbound`. Bridge must send data URLs or paths. |
| **Discord** | **Supported.** Attachments downloaded to data URLs; images/videos/audios/files sent to Core. |
| **Matrix** | **Supported.** Full channel: media downloaded to channel docs or as data URLs; PromptRequest with `images`, `files`. |
| **Teams** | **Supported.** Bot Framework attachments downloaded to data URLs; images/videos/audios/files sent to Core. |
| **Telegram** | **Supported.** File IDs resolved via Bot API to data URLs; images/videos/audios/files sent to Core. |
| **Tinode** | **Supported.** Full channel: images as data URLs, files saved to docs; PromptRequest with `images`, `files`. |
| **Zalo** | Webhook body accepts `images`, `files`; forwarded to Core. Bridge must send data URLs or paths. |
| **BlueBubbles / iMessage / webhook** | Same contract: payload can include `images`, `videos`, `audios`, `files`; bridge or client provides data URLs or paths. |

---

## 3. Where Core stores images and files

Core uses the same logic for **all** inbound sources (Companion, Slack, DingTalk, Feishu, WhatsApp, WhatsApp Web, Google Chat, Signal, Discord, Matrix, Teams, Telegram, Tinode, Zalo, webhook, etc.):

- **Images**
  - When the main LLM **does not support vision** (local-only, no image): Core saves inbound images to the **user’s images folder**:  
    `{homeclaw_root}/{user_id}/images/`  
    (see `config/core.yml` → `homeclaw_root`; `user_id` is the inbound `user_id`, e.g. `slack_U0AHT...`, `feishu_ou_...`).
  - When the model **supports vision**: images are sent in the prompt (as data URLs or resolved paths); they are not necessarily written to disk by Core unless the above “no vision” path is taken.

- **Files (non-image documents, or any type in `files`)**
  - Core runs **file-understanding** on `files` (and image data URLs in `files` are moved into `images`). Data URLs are decoded to **temporary files** for processing.
  - **Documents**: Extracted text is injected into the user message; if the user sends file(s) only (no or negligible text) and the doc is not too big, Core can **add the content to the user’s Knowledge base** (config `file_understanding.add_to_kb_max_chars`). The **physical file** is not automatically saved to a folder; the LLM can use tools (e.g. write to `documents` or `downloads`) if the user asks to save it.
  - **User sandbox folders** (under `{homeclaw_root}/{user_id}/`): `images`, `downloads`, `documents`, `knowledgebase`, `work`, `output`, `share`. So:
    - **Images** → stored in **`{user_id}/images`** when the model doesn’t support vision.
    - **Files** → processed for content; content can go to **Knowledge base**; saving the file to **`downloads`** or **`documents`** is done by the LLM/tools (e.g. user says “save this to my downloads”) or could be added as an optional Core behavior later.

Summary:

- **Images** → user’s **images** folder when applicable (no-vision path).
- **Files** → **Knowledge** (vector KB) for extracted text when configured; **downloads** / **documents** via tools or future Core option.

---

## 4. Four-step image flow (receive → Core → receive from Core → send to user)

For **images** (step 1: files can be added later), the intended flow is:

1. **Channel receives image/file from user** — User sends photo/attachment on the platform (Slack, Telegram, etc.). Channel already supports this on many channels (Slack, Discord, Telegram, WhatsApp, etc.); some need platform-specific download (e.g. Feishu `file_key` → get resource).
2. **Channel forwards to Core** — Same payload as Companion: `POST /inbound` with `text`, `images` (data URLs or paths). Already in place for all channels that accept attachments.
3. **Channel receives image from Core** — Core returns `200` with body `{"text": "...", "images": ["data:image/...;base64,..."], "image": "..."}` when the reply includes generated images (e.g. image-generation skill). Channels must read `data.get("images")` from the response.
4. **Channel forwards image to user** — Channel sends the image(s) back on the platform (e.g. Slack: `files_upload` in thread; Telegram: `sendPhoto`; Discord: `File` in reply).

**Implemented (step 1 – images only):**

- **Slack**: Reads `images` from Core response; decodes data URLs with `Util.data_url_to_bytes`; uploads each via `files_upload` to the same thread.
- **Telegram**: Reads `images`; sends each with `send_photo` (bytes from data URL); text as caption on first image or separate message.
- **Discord**: Reads `images`; sends as `discord.File(BytesIO(bytes), ...)` in the reply (with optional text).
- **Webhook**: Already returns full `r.json()` so `images` are in the response; caller/bridge can send them.
- **iMessage, Signal, Zalo, BlueBubbles**: Response body includes `"images": data["images"]` when Core returns images; the bridge must send them to the user (e.g. via BlueBubbles/Signal/Zalo API).
- **WhatsApp Web**: Returns full Core response (includes `images`); bridge sends to WhatsApp.

**Helper:** `base.util.Util.data_url_to_bytes(data_url)` decodes a `data:...;base64,...` string to bytes for upload to Slack, Telegram, Discord, etc.

**Not yet implemented (outbound response images):** Feishu, DingTalk, Teams, Google Chat — would require each platform’s “upload image” / “send message with image” API (e.g. Feishu: upload image → `image_key` → send message with `msg_type=image`). Same 4-step contract applies when implemented.

---

## 5. References

- **InboundRequest**: `base/base.py`
- **Inbound handling (images, files, file_understanding)**: `core/inbound_handlers.py`, `core/core.py` (e.g. `images_dir = Path(root) / str(user_id) / "images"`, file_understanding, add_to_kb)
- **User sandbox folders**: `base/workspace.py` (`ensure_user_sandbox_folders`: `images`, `downloads`, `documents`, `knowledgebase`, …)
- **File-understanding**: `docs_design/FileUnderstandingDesign.md`
- **How to write a channel**: `docs_design/HowToWriteAChannel.md` (§2.2: images, files, data URLs, paths)
- **Data URL to bytes**: `base.util.Util.data_url_to_bytes` (for channels sending Core response images to the user)
