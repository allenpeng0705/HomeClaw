# Multimodal (image, audio, video) via channels to Core

When the main model supports image, audio, or video (see `config/core.yml` **supported_media** and **docs_design/MediaSupportAndProviders.md**), channels can send media to Core. Core builds an OpenAI-style multimodal message (text + image_url / input_audio / input_video parts) and calls the LLM. **The channel is responsible for receiving media, saving it somewhere (or keeping a data URL), and sending paths or data URLs to Core.**

---

## 1. Channel responsibility: how to support multi-modal

Each channel that can receive image, audio, or video from the platform must:

1. **Receive** the media from the platform (e.g. image message, voice message, video attachment).
2. **Obtain a path or data URL** for Core to use:
   - **Option A (recommended for full channels):** Save the file to disk (e.g. temp dir or upload dir) and pass the **file path** in `PromptRequest.images` / `.audios` / `.videos`. Core will read the file and encode it when building the message. Use a path that Core can read (same machine or shared filesystem).
   - **Option B:** Keep or build a **data URL** (e.g. `data:image/jpeg;base64,...`) and pass it in the same list. Core accepts data URLs directly; no separate file is required.
3. **Compose the input to Core:**
   - Set **text**: User message text or a short caption (e.g. "User sent an image", "Voice message", or the platform caption).
   - Set **images** / **audios** / **videos**: List of **paths** or **data URLs** (one item per file). Empty list `[]` when there is no media of that type.
   - Set **contentType**: `ContentType.TEXT` (text only), `ContentType.TEXTWITHIMAGE` (text + image(s)), `ContentType.IMAGE` (image only), `ContentType.AUDIO` (audio), `ContentType.VIDEO` (video). Use the type that matches what you are sending so Core and permissions behave correctly.
4. **Send** the same **PromptRequest** to Core as today (`transferTocore` or `localChatWithcore`). Core will only add media parts that the main model supports (**supported_media** in config); unsupported types are omitted and a short note is added so the model does not crash.

**What kind of file each channel should handle**

| Modality | Typical file types | PromptRequest field | Core expects |
|----------|--------------------|----------------------|--------------|
| **Image** | JPEG, PNG, GIF, WebP | `images: List[str]` | Each item: file path (Core reads and base64-encodes) or data URL `data:image/<type>;base64,...` |
| **Audio** | WAV, MP3, OGG, WebM | `audios: List[str]` | Each item: file path or data URL `data:audio/<type>;base64,...` |
| **Video** | MP4, WebM | `videos: List[str]` | Each item: file path or data URL `data:video/<type>;base64,...` |
| **Files** (any type) | Image, audio, video, PDF, Word, Excel, txt, etc. | `files: List[str]` | Each item: **file path** (Core runs file-understanding: detects type, handles media like above, extracts text from documents and injects into message). Paths must be under **tools.file_read_base** or absolute. See **FileUnderstandingDesign.md**. |

Channels do not need to support all three media types. You can send **files** (paths) and Core will classify and handle each; or send **images** / **audios** / **videos** explicitly when you already know the type. Support only the modalities your platform can send (e.g. WhatsApp: image + audio; email: image + attachment). Core accepts any subset of `images`, `audios`, `videos`; it will omit unsupported types based on **main_llm_supported_media()**.

**Summary:** The channel is responsible for **receiving and saving** (or encoding) the media and **composing** the request to Core with **text**, **images** / **audios** / **videos** (paths or data URLs), and **contentType**. Core is responsible for checking model support and building the LLM message; it does not fetch or store media for channels.

---

## 1b. Files and file-understanding (image, audio, video, documents)

We support **files** in the channel: the channel can send a list of **file paths** in **PromptRequest.files**. Core runs a **file-understanding** module that (1) detects the type of each file (image, audio, video, or document), (2) handles each correctly: media → same flow as before (content parts); documents → extract text and inject into the user message. The module is **stable and robust**: every step is wrapped in try/except; failures are logged and Core continues. See **docs_design/FileUnderstandingDesign.md**.

**Channel: supporting "file"** — Receive any file from the platform, **save** it to disk in **your channel’s own doc folder** (e.g. `channels/<channel_name>/docs/`) so each channel manages its own downloaded files, then set **request.files = [path1, path2, ...]** (paths must be readable by Core, e.g. under **tools.file_read_base** or absolute). Core runs file-understanding and merges results into the message. You can still set **request.images** / **audios** / **videos** explicitly if you already know the type. See **FileUnderstandingDesign.md** §6 for per-channel doc folder and §7 for user-based knowledge base.

**Legacy / document_read:** **document_read** (and **file_read**) remain available as **tools** the model can call. With **request.files**, document content is extracted and injected automatically; the model sees it in the same turn.

---

## 1c. document_read tool (optional)

With **request.files** (see §1b), document content is extracted and injected automatically. **document_read** (and **file_read**) remain available as **tools** the model can call when the user refers to a path.

**What works today**

- **document_read** (and **file_read**) are **tools** the model can call. They read a file from a **path** under **tools.file_read_base** (see `config/core.yml`). So if the channel (or the user) has saved a PDF/Word/Excel file to a path under that base (e.g. an uploads directory), the **model** can read it when the user asks — e.g. user says "Summarize the report I sent" and the channel saved it as `uploads/report.pdf`; the channel can set `text` to something like "User attached report.pdf (saved at uploads/report.pdf). Please read and summarize it." The model can then call **document_read(path="uploads/report.pdf")** to get the content. Supported formats (when Unstructured or pypdf is installed): PDF, PPT, Word (.docx/.doc), Excel (.xlsx/.xls), HTML, MD, XML, JSON, CSV, etc. See **document_read** in TOOLS.md / tool registry.
- **Knowledge base**: The knowledge base is **user-based** (per user_id), not per-channel. The user can **add** document content to their knowledge base (e.g. via **knowledge_base_add** or the KB flow); that is separate from "channel sends a document in this message." If file-understanding adds extracted documents to the KB (optional), it uses the same user-based KB so the same user’s content from any channel is queryable together.

**How a channel can support document attachments today**

1. **Receive** the document from the platform (e.g. email attachment, Matrix file, WhatsApp document).
2. **Save** the file to a path under **tools.file_read_base** (or a subdir like `uploads/`) so Core and the tool layer can read it. Use a unique name (e.g. timestamp + original filename) to avoid clashes.
3. **Compose** the request to Core: set **text** to the user’s message plus a clear reference to the file, e.g. `"User attached report.pdf. Path: uploads/20250116_report.pdf. Please read and summarize."` Set **images** / **audios** / **videos** as usual (or empty). Do **not** put the document path in `images` — those are for image media only.
4. **Send** the PromptRequest to Core. The model will see the text and can call **document_read(path="uploads/20250116_report.pdf")** to get the content (within `file_read_base` and tool safety limits).

**Possible future**

- Add **documents: List[str]** to **PromptRequest** (and optionally to **InboundRequest**), where each item is a **file path** (or a way to get the file). In **process_text_message**, for each path in `request.documents`, Core would **extract text** (using the same logic as **document_read**: Unstructured, pypdf, or plain text) and **append** it to the user message (e.g. "User attached: report.pdf\n\n[extracted text]"). Then the model would see the document content in the same turn without a tool call. This would require a new field, extraction logic in Core, and size/type limits.

**Summary:** PDF/Word/Excel are **not** first-class message attachments today. Channels can save documents under **file_read_base** and reference the path in **text** so the model can use **document_read** to read them.

---

## 2. How to send images (POST /inbound and WebSocket)

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

## 3. Full channels (/process, /local_chat)

Channels that use **PromptRequest** (e.g. full channel implementations) have:

- **contentType**: `TEXT`, `TEXTWITHIMAGE`, `IMAGE`, `AUDIO`, `VIDEO` (set to match what you send).
- **images**: List of **file paths** or data URLs (paths on the server where the channel saved uploaded images).
- **audios**: List of **file paths** or data URLs (paths where the channel saved audio files).
- **videos**: List of **file paths** or data URLs (paths where the channel saved video files).

Core reads paths (or uses data URLs as-is) and builds the multimodal user message. So full channels: **receive media → save to a path (or keep data URL) → set `contentType`, `images` / `audios` / `videos`, and `text` on the request → send to Core.**

---

## 4. Flow inside Core

1. **Inbound** (/inbound or /ws): Request has **text** and optional **images** (data URLs, base64, or paths). Core builds a **PromptRequest** with `contentType=TEXTWITHIMAGE` when images are present. (Inbound/ws today accept **images** only; **audios** / **videos** can be added to the payload if needed.)
2. **process_text_message**: Core reads `request.images`, `request.audios`, `request.videos` and `Util().main_llm_supported_media()`. For each supported type, it builds content parts (image_url, input_audio, input_video) from paths or data URLs; unsupported types are omitted and a short note is added.
3. **answer_from_memory** → **openai_chat_completion**: Messages are sent to the LLM as-is. Vision/multimodal models accept the OpenAI-compatible format with image_url / input_audio / input_video parts.
4. **Chat history**: Only the **text** part of the user message is stored in history (past turns remain text-only; the current turn can include media).

---

## 5. Other channels (Tinode, Matrix, WeChat, WhatsApp, Email)

These channels already use **PromptRequest** with **images=[]**, **audios=[]**, **videos=[]** and **contentType=TEXT**. Core accepts **request.images**, **request.audios**, **request.videos** (lists of paths or data URLs) and builds multimodal content when the main model supports it. To support multi-modal, each channel must **handle the file types the platform can send**, **save media somewhere** (or build a data URL), and **compose** the request: set `request.images` / `request.audios` / `request.videos` and `request.contentType`, then send to Core.

| Channel | Current behavior | What to do to support multi-modal |
|--------|------------------|-----------------------------------|
| **Tinode** | Builds `PromptRequest` with `images=[]`, `audios=[]`, `videos=[]`. `data_type == 'image'` is often a TODO. | **Image:** When `data_type == 'image'`, get image (e.g. base64 from content), save to temp file or build data URL. Set `request.images = [path_or_data_url]`, `contentType = ContentType.TEXTWITHIMAGE`, `text` = caption or "User sent an image", then call Core. **Audio/Video:** When the platform sends audio/video, download or get bytes, save to path (or data URL), set `request.audios` / `request.videos` and `contentType`, then call Core. |
| **Matrix** | Builds `PromptRequest` from message body (text); `images=[]`. | **Image:** For `m.image`, get URL from content, download to temp file (or base64). Set `request.images = [path_or_data_url]`, `contentType = ContentType.TEXTWITHIMAGE`, `text` = body or "Image". **Audio/Video:** For `m.audio`, `m.video`, download to path or data URL, set `request.audios` / `request.videos` and `contentType`, then send to Core. |
| **WeChat** (wcferry) | Builds `PromptRequest` from `msg.content` (text); `images=[]`. | **Image:** When message is image type, use wcferry API to get path or bytes. Set `request.images = [path_or_data_url]`, `contentType = ContentType.TEXTWITHIMAGE`, `text` = caption or "Image". **Audio/Video:** When platform sends voice/video, get path or bytes, set `request.audios` / `request.videos` and `contentType`, then send to Core. |
| **WhatsApp** (neonize) | Builds `PromptRequest` from text; `images=[]`. | **Image:** For `imageMessage`, download or get bytes, save to path or data URL. Set `request.images`, `contentType = ContentType.TEXTWITHIMAGE`, `text` = caption or "Image", then `syncTransferTocore(request)`. **Audio/Video:** For `audioMessage` / `videoMessage`, use platform API to download, save to path (or data URL), set `request.audios` / `request.videos` and `contentType`, then send to Core. |
| **Email** | Builds `PromptRequest` from subject/body; no attachments. | **Image:** Iterate `msg.get_payload()` for image parts; decode and write to temp files (or base64). Set `request.images = [path, ...]`, `contentType = ContentType.TEXTWITHIMAGE` when any image, keep body as `text`. **Audio/Video:** Same pattern for audio/video attachments; set `request.audios` / `request.videos` and `contentType` when present, then send to Core. |

**Summary**

- **Core**: Supports `PromptRequest.images`, `audios`, `videos` (paths or data URLs) and builds multimodal user content in `process_text_message`; omits unsupported types per **supported_media** so the model does not crash.
- **Channels**: Each channel is **responsible** for receiving media from the platform, saving it somewhere (or building a data URL), and composing the request with **text**, **images** / **audios** / **videos**, and **contentType** before sending to Core. Support only the modalities your platform can send.

---

## 6. Requirements

- **Model support**: In `config/core.yml`, set **supported_media** on the main model entry (e.g. `[image]`, `[image, audio, video]`). Local vision models need **mmproj** for image; see **MediaSupportAndProviders.md** and config comments.
- **Channels**: Each channel that supports multi-modal must **receive** media from the platform, **save** it to a path (or build a data URL), and **compose** the PromptRequest with **text**, **images** / **audios** / **videos**, and **contentType** before sending to Core (see §1 and §5).
