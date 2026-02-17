# Media support (image / audio / video) and how providers work

This doc explains how **LiteLLM**, **OpenAI**, and **Google Gemini** support image, audio, and video. We do **not** assume “one API does everything” — modalities and APIs differ by provider and model.

---

## 1. Summary

| Provider / layer | Image | Audio | Video | Same API for all? |
|------------------|-------|-------|-------|-------------------|
| **LiteLLM** | Yes: `image_url` in message content | Yes: `input_audio` in message content | Varies (see below) | One `/chat/completions`; content parts vary by modality |
| **OpenAI** | Chat Completions + `image_url` (e.g. gpt-4o) | Chat Completions + `input_audio` (**gpt-4o-audio-preview** only) | Separate **Videos API** (e.g. Sora) | **No** — image vs audio = different models; video = different API |
| **Gemini** | `generateContent` + inlineData (image) | `generateContent` + inlineData (audio) | `generateContent` + inlineData (video) | **Yes** — one API, one model can accept image/audio/video |

So:

- **Image**: Same Chat Completions (or Gemini `generateContent`) with image in message content; no separate “image API” for analysis.
- **Audio**: Same Chat Completions **but** for OpenAI you must use **gpt-4o-audio-preview** (not gpt-4o). Gemini can accept audio in the same `generateContent` call.
- **Video**: For **analysis**, Gemini supports video in `generateContent`. OpenAI has a separate **Videos API** (e.g. Sora) for generation; video-as-input in Chat Completions is model-specific. LiteLLM “video” support often refers to **video generation** (e.g. Veo, Sora), not necessarily video input in chat.

Therefore **supported_media** in `core.yml` should reflect **the specific model** you use (e.g. gpt-4o = image only; gpt-4o-audio = audio; Gemini 1.5 Pro = image, audio, video).

---

## 2. LiteLLM

- **Role**: Proxy that speaks OpenAI-compatible `/chat/completions` and maps to many providers (OpenAI, Gemini, Anthropic, etc.).
- **Image**: You send `content: [ {"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}} ]`. LiteLLM forwards this and, if a provider doesn’t accept URLs, converts to base64. So **one chat completion call** with image in content.
- **Audio**: You send `content: [ {"type": "text", "text": "..."}, {"type": "input_audio", "input_audio": {"data": "<base64>", "format": "wav"}} ]`. Same `/chat/completions` endpoint. LiteLLM passes this through; **which models accept it** depends on the provider (e.g. OpenAI only for **gpt-4o-audio-preview**).
- **Video**: LiteLLM has **video generation** (e.g. Veo, Sora) via dedicated endpoints, not “video as user input in chat” in the same way as image/audio. For **video input** in chat, support is provider- and model-specific (e.g. Gemini can accept video in `generateContent`).
- **Capability checks**: LiteLLM exposes:
  - `litellm.supports_vision(model="openai/gpt-4o")` → image input
  - `litellm.supports_audio_input(model="openai/gpt-4o-audio-preview")` → audio input  
  So **per-model** capabilities exist; we don’t call these today and rely on **supported_media** in config instead.

**Takeaway**: One API (chat completions), but **which modalities work depends on the model**. Our `supported_media` in `core.yml` should match the **model** (e.g. gpt-4o → `[image]`, gpt-4o-audio → `[audio]`, Gemini 1.5 Pro → `[image, audio, video]`).

---

## 3. OpenAI

- **Image**: **Chat Completions API** with user message `content` containing `{"type": "image_url", "image_url": {"url": "data:image/..."}}`. Models like **gpt-4o**, **gpt-4o-mini** support this. No separate “vision API” — same `/v1/chat/completions` call.
- **Audio**: **Chat Completions API** with user message `content` containing `{"type": "input_audio", "input_audio": {"data": "<base64>", "format": "wav"}}`. Only the **gpt-4o-audio-preview** (or “gpt-audio”) model supports this. Standard **gpt-4o** does **not** accept `input_audio`; audio is a **different model**, not an extra endpoint.
- **Video**: **Videos API** (e.g. Sora) is a **separate** API for video **generation**. Sending “video as user input” in Chat Completions is not the same as the Images/Vision flow; support is limited and model-specific.

So for OpenAI:

- If **main_llm** is **gpt-4o** (or gpt-4o-mini): set **supported_media: [image]** (and text). Do **not** set `[audio]` or `[video]` for gpt-4o.
- If **main_llm** is **gpt-4o-audio-preview**: set **supported_media: [audio]** (and text). This model does **not** support image input.
- To support both image and audio in one “logical” main model with OpenAI you’d need either two model entries (and routing) or a single model that supports both (e.g. a future unified model); today OpenAI splits them.

---

## 4. Google Gemini

- **One API**: **generateContent** (REST / SDK). Same call can include text + image + audio + video.
- **Content parts**: Text, **inlineData** (base64 + mimeType for image/audio/video), or **fileData** (reference to Files API upload). So image, audio, and video **input** are all supported in the **same** request format.
- **Video**: Gemini docs describe “video understanding” — you can send video (e.g. as inlineData or file reference) and get text analysis. “Video generation” (e.g. Veo) is a different product/API.

So for Gemini (e.g. gemini-1.5-pro, gemini-1.5-flash): **supported_media: [image, audio, video]** is typically correct for a single model. You still set it explicitly in `core.yml` if you want to restrict (e.g. [image] only) or document behavior.

---

## 5. How HomeClaw uses this

- **supported_media** in `config/core.yml` is set **per model entry** (under `local_models` or `cloud_models`). It lists what that **specific model** can handle: `image`, `audio`, `video`.
- **main_llm** points to one of those entries (e.g. `cloud_models/OpenAI-GPT4o`). The **supported_media** for main_llm is the one on **that** entry.
- **Defaults**:
  - **Cloud (LiteLLM)**: We default to `[image, audio, video]` if the entry has no `supported_media`. That is **optimistic** and wrong for OpenAI (gpt-4o is image-only; gpt-4o-audio is audio-only). So for OpenAI models you **should** set `supported_media` explicitly (e.g. gpt-4o → `[image]`, gpt-4o-audio → `[audio]`).
  - **Local**: Default `[]` (text-only) or `[image]` if `mmproj` is set.
- **Core behavior**: When building the user message, Core calls `Util().main_llm_supported_media()` and only adds image/audio/video parts for types in that list; others are omitted and a short note is added so the model doesn’t receive unsupported content and doesn’t crash.

So we **do not** assume “cloud = one API that does image + audio + video.” We **do** assume one **call shape** (chat completions with content parts); the **model** decides what it accepts, and that is reflected in **supported_media** per model in `core.yml`. For OpenAI, that means different entries for image vs audio (different models); for Gemini, one entry often supports all three.

---

## 6. Parameters HomeClaw sends (cloud and local)

We use **one** request shape for both **local** (llama-server) and **cloud** (LiteLLM): `POST /v1/chat/completions` with a JSON body that includes `messages`. Each user message can have `content` as a string (text only) or as a **list of content parts** (multimodal).

- **Image**: When the main model supports image and the request has `images`, we build `content` as a list: first part `{"type": "text", "text": "..."}`, then for each image `{"type": "image_url", "image_url": {"url": "<data URL>"}}`. We convert each image item (file path, data URL, or raw base64) to a data URL via `_image_item_to_data_url` (path → read file, base64, then `data:image/jpeg;base64,...`). So we **do** add the proper parameters for image for both local and cloud; no separate "image path" field — the image is in the message content.
- **Audio**: When the main model supports audio and the request has `audios`, we add content parts `{"type": "input_audio", "input_audio": {"data": "<base64>", "format": "wav"}}` (or detected format). We convert each audio item (file path or data URL) to base64 and a format (e.g. wav, mp3) and put them in the same user message `content` list. Same API, same request for local and cloud; local llama-server may not support `input_audio` (depends on server), so set `supported_media` only when the model actually accepts it.
- **Video**: When the main model supports video and the request has `videos`, we add content parts in the format the provider expects (e.g. base64 + format). Video input in chat is less standardized; we add parts when supported_media includes `"video"` and the format is documented.

So: we **do** add the proper parameters — image path (or URL/base64) is converted and sent inside the message `content` as `image_url`; audio/video are sent as content parts when supported. Local and cloud both receive the same `messages`.

---

## 7. References

- LiteLLM: [Vision](https://docs.litellm.ai/docs/completion/vision), [Audio](https://docs.litellm.ai/docs/completion/audio), [Image URL handling](https://docs.litellm.ai/docs/proxy/image_handling).
- OpenAI: [Images and vision](https://platform.openai.com/docs/guides/images), [Audio and speech (Chat Completions)](https://platform.openai.com/docs/guides/audio?api-mode=chat), [GPT-4o](https://platform.openai.com/docs/models/gpt-4o), [GPT-4o Audio](https://platform.openai.com/docs/models/gpt-4o-audio-preview).
- Google: [Gemini text generation](https://ai.google.dev/gemini-api/docs/text-generation), [Audio](https://ai.google.dev/gemini-api/docs/audio), [Video understanding](https://ai.google.dev/gemini-api/docs/video-understanding).
