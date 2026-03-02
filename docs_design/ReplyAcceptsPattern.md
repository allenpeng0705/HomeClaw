# Reply-accepts pattern: what channels and Companion can receive

Channels and the Companion app can tell Core **what types of reply content they can receive**. Core uses this to decide whether to send inline media (images, files) or to send **links** instead. Default is **text-only**.

**Companion and direct clients:** The Companion app (and any client that sends `reply_accepts` including `image` and/or `file`) receives **full reply content**—text, images, files—directly from Core. This does **not** depend on Core having a public URL. The public URL is only used when the client is **text-only**, to optionally provide view links instead of inline media.

---

## 1. Goal

- **Single contract:** Every client (channel or Companion) declares `reply_accepts` (or equivalent). Core respects it when building the response.
- **Graceful degradation:** If a client does not accept images, Core sends only text; when Core has a **public URL** configured, it may also send **view links** (e.g. “Image: [open link]”) so the user can open media. If Core has no public URL, it never generates links—text-only clients get only the reply text.
- **Extensible:** Same pattern can cover `text`, `image`, `video`, `audio`, `file` (and later e.g. `card`).

---

## 2. Capability declaration

### 2.1 Shape

A client declares which reply content types it can handle. Proposed field name: **`reply_accepts`**.

- **Type:** Optional list of strings, e.g. `["text", "image", "file"]`.
- **Default when omitted or empty:** `["text"]` (text-only).
- **Allowed values (proposed):**
  - `text` — always implied; plain text reply.
  - `image` — client can display or send inline images (data URLs, paths, or platform-specific upload).
  - `file` — client can display or send file links / attachments.
  - (Future: `video`, `audio`, `card`.)

So:

- **Text-only:** `reply_accepts` omitted, or `[]`, or `["text"]` → Core sends only text; for any images/files it would have sent, Core adds **links** only when a public URL is configured (see §4); otherwise it sends only text.
- **Text + image:** `reply_accepts: ["text", "image"]` → Core sends `text` and `images` (and optionally `image`) as today. **No public URL needed**; client gets inline data (paths or data URLs).
- **Text + image + file:** `reply_accepts: ["text", "image", "file"]` → Core sends text, images, and file paths/attachments as agreed. **No public URL needed**; client gets full content.

### 2.2 Where to send it

- **POST /inbound (InboundRequest):** Add optional field `reply_accepts: Optional[List[str]] = None`. Used by webhook-style channels (Slack, Telegram, Feishu, etc.) and by Companion when it POSTs to /inbound. If omitted, Core treats as text-only.
- **Plugin channels (PromptRequest):** Add optional field `reply_accepts: Optional[List[str]] = None`. Used by WhatsApp, Matrix, Tinode, etc. If omitted, Core treats as text-only.
- **Channel registration (optional):** When a plugin channel registers with Core, it could send a default `reply_accepts` (e.g. `["text", "image"]`) so every request from that channel doesn’t need to. Per-request `reply_accepts` in PromptRequest would override the registered default.
- **WebSocket / Companion:** The client can send `reply_accepts` in the same payload as the message (e.g. in the JSON body that carries `user_id`, `text`, `images`, etc.). Core uses it for the reply to that request.

For a first version, **per-request** is enough: InboundRequest and PromptRequest both get `reply_accepts`. Registration can be added later if needed.

---

## 3. Core behavior when building the reply

Core builds the reply (for sync /inbound response, async AsyncResponse, or WebSocket push) from:

- Response text (and optionally format).
- Any images (paths or data URLs) produced by the pipeline (e.g. image generation, tool output).
- Any files (paths or URLs) produced by the pipeline.

**Logic:**

1. **Resolve capabilities:** From the request (InboundRequest or PromptRequest) read `reply_accepts`. If missing or empty, use `["text"]`.
2. **Text:** Always include the reply text.
3. **Images:**
   - If `"image"` is in `reply_accepts`: include `images` (and optionally `image`) in the response as today (data URLs or paths, depending on the code path). Channels that support inline images use this.
   - If `"image"` is **not** in `reply_accepts` but the pipeline produced images: do **not** put raw images in the response. Instead, if Core has a public URL, for each image generate a **view link** (see §4) and either:
     - add an **`image_links`** field to the response (list of URLs), and/or
     - append to the reply text a short line per image, e.g. `Image: [view](url)` or `Image: <url>`, so the user can open it. Core can use the same link generation as `get_file_view_link` (e.g. `/files/out?token=...&path=...` with signed token). If Core has no public URL, do not add image_links or append link lines; return only the reply text.
4. **Files (optional, same idea):** If `"file"` is in `reply_accepts`, include file paths or upload URLs as the current design does. If not, Core can add **file_links** or append “File: [link]” to the text using the same file-serving mechanism.

So: **text-only** → no `images` in response; instead `image_links` and/or text with links. **Text+image** → `images` (and optionally `image`) as today; no need for links unless we want both.

---

## 4. Link generation for unsupported media (only when Core has a public URL)

When the client does **not** accept `image` (or `file`), Core does not send inline image data (or file content).

- **If Core does *not* have a public URL configured** (e.g. `core_public_url` unset): **Never generate links.** For text-only clients, Core returns **only the reply text**; any images or files the pipeline produced are not included and are not replaced by links.
- **If Core *does* have a public URL:** Reuse Core’s existing file-serving and token logic:
  - **Scope:** User id (or “companion” / default) for the sandbox.
  - **Path:** Relative path under that scope (e.g. `images/xyz.png`, `output/report.pdf`).
  - **Token:** `create_file_access_token(scope, path)` from `core.result_viewer` (or equivalent).
  - **URL:** `{core_public_url}/files/out?token={token}&path={path}` (same pattern as `get_file_view_link`).

If the image is only in memory (e.g. generated and not yet written to the user’s sandbox), Core should write it to the user’s `images` (or similar) folder first, then generate the link—only when a public URL is configured. That way “text-only” clients still get a single, stable URL per image.

**Response shape when falling back to links (public URL set):**

- **`image_links`:** `Optional[List[str]]` — list of view URLs for images that were not included in `images`.
- **`file_links` (optional):** Same for files.
- **Text:** Optionally append lines like “Image: {url}” or “Image: [view](url)” so channels that only show text still show something clickable. 
---

## 5. Default when omitted

- **Omitted or empty `reply_accepts`:** Treated as **text-only** (`["text"]`). Core sends only text. For any images or files it would have sent: Core adds **links** only if a public URL is configured (§4); otherwise Core returns **only the reply text**. Channels and Companion that want inline images or files must send `reply_accepts: ["text", "image"]` or `["text", "image", "file"]` explicitly.

---

## 6. Where to implement in Core

- **Request models:** Add `reply_accepts: Optional[List[str]] = None` to `InboundRequest` and `PromptRequest` in `base/base.py`.
- **Registration (optional):** In `RegisterChannelRequest` or the handler that stores channel info, add an optional `reply_accepts`; when building AsyncResponse for that channel, use it if the request does not override.
- **Response building (sync /inbound):** In the handler that builds the JSON response (e.g. in `route_registration.py` or `inbound_handlers.py`), after getting `content` with `text` and `images`:
  - Read `reply_accepts` from the request (default `["text"]` if omitted).
  - If `"image"` not in `reply_accepts` and `content.get("images")`:
    - If Core has a public URL: for each image path, generate a view link (scope = user_id, path = relative path under sandbox; token via `create_file_access_token`; URL = core_public_url + `/files/out?token=...&path=...`). Set `content["image_links"] = list_of_urls`; optionally append to `content["text"]` a line per link; remove or do not set `content["images"]` for that response.
    - If Core does not have a public URL: do not set `image_links` or `images`; return only the reply text.
  - If `"image"` in `reply_accepts`, keep current behavior (include `images`).
- **Response building (async plugin):** In `core/core.py` where `resp_data = {"text": ..., "images": img_paths}` is built, apply the same rule: if the request’s `reply_accepts` does not include `"image"`, do not set `resp_data["images"]`. If Core has a public URL, set `resp_data["image_links"]` and optionally append link lines to text; otherwise return only text.
- **WebSocket push:** Same logic when building the push payload (text + images vs text + image_links).

---

## 7. Channel and Companion usage

- **Channels that support inline images** (Slack, Telegram, Discord, Teams, etc.): Send `reply_accepts: ["text", "image"]`. They receive `images` and optionally `image` as today.
- **Channels that are text-only:** Send `reply_accepts: ["text"]` (or omit). They receive only `text`; if Core has a public URL, they may also receive `image_links` (and optionally link lines in the text); if not, they get only the reply text.
- **Companion / WebChat:** Send `reply_accepts: ["text", "image", "file"]` when the UI supports media—they receive **full content** (text, images, files) from Core **even when Core has no public URL**. Send `["text"]` when it doesn’t (then Core returns only text, or text + links if public URL is set).

This gives a single, clear pattern: **channels and Companion declare what they can receive; Core sends either inline media or links accordingly.**

---

## References

- **Inbound/outbound contract:** `docs_design/ChannelImageAndFileInbound.md`
- **Channel review:** `channels/CHANNEL_REVIEW.md`
- **File view links:** `core.result_viewer` (`create_file_access_token`, `get_file_view_link`); `core/core.py` file serving at `/files/out`
- **Request models:** `base.base.InboundRequest`, `base.base.PromptRequest`
