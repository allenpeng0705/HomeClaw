# Image / vision handling (Companion, mix mode, local-only)

## Overview

When the Companion app (or any channel) sends images, Core decides whether to include them in the LLM message based on **main_llm_supported_media** and **mode** (local / cloud / mix). This document describes how we keep the feature stable and robust.

---

## 1. How Core receives images

- **POST /inbound**: body can include `images` (list of file paths or data URLs) and/or `files` (data URLs with `data:image/...` are moved to `images` in `inbound_handlers`).
- **WebSocket /ws**: client sends JSON with `images` and/or `files`; Core builds `InboundRequest` with `images` and passes it to `process_text_message`.

**Client (Companion app)** should send either:

- `payload.images = [path_or_data_url, ...]`, or  
- `payload.files = [data:image/...;base64,..., ...]`

so that Core sees `request.images` in `process_text_message`. If the client omits `images` or sends a wrong shape, Core will not see any image and will not trigger vision logic.

---

## 2. Vision by mode

### 2.1 Cloud mode

- **main_llm** is a cloud model (e.g. `cloud_models/DeepSeek-Chat`).
- **main_llm_supported_media()** defaults to `[image, audio, video]` for cloud unless the model entry overrides `supported_media`.
- Images are included in the user message when `"image" in supported_media`; no extra logic.

### 2.2 Mix mode (local + cloud)

- **main_llm_local** and **main_llm_cloud** are both set; hybrid router chooses route per request.
- **Vision override**: If the request has **images** and the **local** model does **not** support image but the **cloud** model does, Core:
  1. In **process_text_message**: includes images in the message (adds `"image"` to `supported_media` when cloud supports image).
  2. In **answer_from_memory**: before running the heuristic/semantic/slm router, forces **route = "cloud"** for this request so the cloud model is used and can understand the image.
- So under mix mode, image understanding is available as long as the cloud model supports vision, even if the default route is local.

### 2.3 Local-only mode

- **main_llm** is a local model (no mix).
- If the local model **supports** image (e.g. has `mmproj` and `supported_media: [image]`): images are included and the local vision model is used.
- If the local model **does not** support image:
  - Core **saves** the image(s) to the user’s **images folder**: `homeclaw_root/{user_id}/images/` (e.g. `{ts}_{i}.jpg`).
  - Core returns a **polite message** without calling the LLM: *"I've saved your image(s) to your images folder. The current model doesn't support image understanding. You can switch to a vision-capable model (e.g. in mix mode or a local vision model) to ask about the image."*

---

## 3. Per-user images folder

- **Sandbox layout**: For each user, `ensure_user_sandbox_folders` creates `homeclaw_root/{user_id}/images/` (and other subdirs). See `base/workspace.py` (`images_subdir`, default `"images"`).
- **When used**: When Core does **not** include images in the LLM message (local-only, no vision), it writes each image to `homeclaw_root/{user_id}/images/` so the user can later use a vision model or refer to the file.

---

## 4. Helpers

- **Util().main_llm_supported_media()**: Returns supported media for the **effective** main LLM (default route in mix).
- **Util().main_llm_supported_media_for_ref(model_ref)**: Returns supported media for a given ref (e.g. `main_llm_local` or `main_llm_cloud`). Used in mix mode to decide vision override and whether to include images in the message.

---

## 5. Flickering / no response (client side)

If the Companion app shows **flickering** or **Core doesn’t respond** when sending an image:

1. **Payload**: Ensure the app sends `images` (or `files` with `data:image/...`) in the same JSON as `text` and `user_id`. If the client splits or retries in a way that drops `images`, Core will not see them.
2. **Timeout**: Large base64 images can make the request slow; ensure the client and any proxy use a sufficient read timeout (e.g. `inbound_request_timeout_seconds` in config).
3. **UI**: If the app re-renders or clears the input when attaching an image, it can look like “flickering”; that’s a client-side UX issue.

Server-side: with the above logic (mix → cloud for vision, local-only → save + polite message, per-user images folder), Core should always either understand the image or respond with a clear message and saved files.
