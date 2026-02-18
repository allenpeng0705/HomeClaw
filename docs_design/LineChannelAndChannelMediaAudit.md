# Line channel, channel media audit, and WhatsApp evaluation

This doc covers: **(1)** adding a **Line** channel for HomeClaw (using LINE Messaging API and webhook, inspired by OpenClaw’s Line extension); **(2)** an **audit of all channels** for file / image / audio / video support and alignment with Core’s multimodal and file-understanding; **(3)** an **evaluation of WhatsApp**: HomeClaw’s own plugin (neonize) vs OpenClaw’s approach (Baileys + gateway), and whether to use a “webhook” (Cloud API) style for WhatsApp.

---

## 1. Line channel for HomeClaw

**Goal:** Support LINE as a channel so users in Japan, Taiwan, Thailand, etc. can talk to Core via LINE.

**OpenClaw reference:** OpenClaw has a Line extension in `clawdbot/extensions/line/` and LINE Messaging API logic in `clawdbot/src/line/`. The extension uses a **webhook**: LINE sends events to a URL; the server validates the signature, parses events (message, follow, postback), downloads media via LINE’s Get content API, and forwards to the agent. Outbound: push/reply text, Flex messages, templates, quick replies, media URLs. So the pattern is: **LINE Messaging API + webhook** (no long-polling; LINE calls us).

**HomeClaw approach:**

- **Same idea:** Implement a **Line channel** that:
  1. Exposes a **webhook endpoint** (e.g. `POST /line/webhook`) that LINE can call.
  2. Verifies **X-Line-Signature** with the channel secret (HMAC).
  3. Parses **WebhookRequestBody** (message, follow, unfollow, join, leave, postback).
  4. For **message** events: extracts text; for image/video/audio, downloads content via LINE’s Get content API (or saves to a temp file / channel docs folder) and sends paths (or data URLs) to Core in a `PromptRequest` with the right `contentType` and `images`/`videos`/`audios` (or `files`).
  5. Registers with Core and puts requests on the Core request queue; receives replies from the response queue and sends them back via LINE Messaging API (push message / reply token).
- **Config:** Channel needs `channel_access_token` and `channel_secret` (from LINE Developers Console). Optional: webhook path, media max size. Store in channel `.env` or a small config file under the channel.
- **Permission:** Use the same model as other channels: `user_id` = LINE user ID (e.g. `line:Uxxxxxxxx`) in `config/user.yml` under `im`; empty list = allow all.
- **Media:** LINE supports image, video, audio, file. We can treat image/video/audio like other channels (paths or data URLs in `images`/`videos`/`audios`); “file” can go to `request.files` and Core runs file-understanding. So we **do not** need to treat everything as a single “file” type; we can map LINE message types to our ContentType and lists.

**Implementation outline:**

- New folder: `channels/line/` with e.g. `channel.py`, `webhook.py`, `send.py`, `download.py`.
- `channel.py`: FastAPI app, register with Core, start a server that listens on a port; mount webhook route that accepts POST with raw body for signature verification.
- `webhook.py`: Parse LINE webhook body, verify signature, dispatch to handlers (message → build PromptRequest and sync/post to Core; follow/postback as needed).
- `download.py`: Given a LINE message ID and access token, call LINE Get content API, stream to a file under `channels/line/docs/` (or temp), return path; respect max size.
- `send.py`: Given a reply text (and optional media), call LINE push message or reply message API.
- **Reply flow:** Core puts `AsyncResponse` on the response queue; the Line channel’s consumer gets it and calls LINE reply (if we have reply token) or push (using stored user/group ID from request_metadata).

**Differences from OpenClaw:** OpenClaw is TypeScript and integrates with their gateway and pairing. HomeClaw is Python and uses `user.yml` for permission and Core request/response queues. The **protocol** (LINE webhook → parse → PromptRequest → Core → AsyncResponse → LINE API) is the same; only the surrounding stack differs.

---

## 2. Channel media audit (file / image / audio / video)

Core supports **multimodal** and **files**: `PromptRequest` has `images`, `videos`, `audios`, and optional `files`. Core uses `process_text_message` to build the LLM message from these and from file-understanding on `files`. **Request queue:** Core now processes all processable content types (TEXT, TEXTWITHIMAGE, IMAGE, AUDIO, VIDEO) in the request queue, not only TEXT.

**Per-channel summary:**

| Channel       | Image | Video | Audio | Files | Notes |
|---------------|-------|-------|-------|-------|--------|
| **WhatsApp**  | Yes   | No    | No    | No    | Image: download to base64 data URL, TEXTWITHIMAGE. videos=[], audios=[]. No generic file or video/audio yet. |
| **Matrix**    | Yes   | No    | No    | No    | Image: download from mxc to file, add to images. videos=[], audios=[]. |
| **WeChat**    | Yes   | No    | No    | No    | Image: extra path or base64. videos=[], audios=[]. |
| **Tinode**    | Yes   | No    | No    | No    | Image: inline/data URL, TEXTWITHIMAGE. videos=[], audios=[]. |
| **Email**     | No    | No    | No    | No    | Text only in the current flow. |
| **Webhook**   | —    | —     | —     | —     | Depends on what the client sends in the payload (can include images/files if implemented). |
| **Line (new)**| Plan | Plan  | Plan  | Plan  | Map LINE image/video/audio to images/videos/audios; file → files. |

**Unified approach suggestion:**

- **Image:** All IM channels that support photos should send them as `images` (path or data URL) and set `contentType=TEXTWITHIMAGE` (or IMAGE if no text). Core already uses `request.images` in the message.
- **Video / audio:** Channels that support video or audio should fill `videos` and `audios` (paths or data URLs) and set `contentType=VIDEO` or `AUDIO` (or TEXT with caption). Core uses them in the message when the main model’s `supported_media` includes them.
- **Files (generic):** When the channel receives a “file” (e.g. document, or unknown type), save to the **channel’s doc folder** (e.g. `channels/<name>/docs/`), add the path to `request.files`. Core runs **file-understanding** on `request.files` (detect type, merge into images/audios/videos or document notice). So channels **do not** need to classify file type; they can send everything as `files` and let Core classify, or they can map known image/video/audio to the right list and put the rest in `files`.
- **Treating all as files:** Alternatively, a channel could put every attachment (image, video, audio, document) as a path in `request.files` and leave `images`/`videos`/`audios` empty. Core’s file-understanding would then classify each file and merge into the right lists and document notices. That is **simpler for the channel** (one code path: save file → add path to `files`) and is a valid choice; the only downside is that file-understanding runs on every attachment (slight overhead). So **either** “channel maps types to images/videos/audios/files” **or** “channel sends all as files” is fine; we encourage documenting which strategy each channel uses.

**Core fix applied:** The request queue now processes requests whose `contentType` is TEXT, TEXTWITHIMAGE, IMAGE, AUDIO, or VIDEO (not only TEXT), so messages that contain only an image or only audio are now processed.

---

## 3. WhatsApp: HomeClaw plugin (neonize) vs OpenClaw (Baileys / “webhook”)

**HomeClaw today:** The WhatsApp channel uses **neonize** (a Go library for WhatsApp Web protocol), used from Python. It runs an **unofficial** WhatsApp client (QR login, same idea as “WhatsApp Web”). Messages are received via the library’s events and sent to Core; replies are sent back via the same client. So it is **not** the official WhatsApp Business API (Cloud API).

**OpenClaw:** Uses **Baileys** (Node.js, `@whiskeysockets/baileys`) — also an **unofficial** WhatsApp Web client. Their “web” channel is the Baileys-based inbox monitor that receives messages and forwards them to the gateway/agent; outbound goes through the same Baileys session. So OpenClaw’s WhatsApp is **not** “webhook” in the sense of “WhatsApp Cloud API calls our URL.” It is “we run a WhatsApp Web client and process messages in our gateway.”

**Comparison:**

| Aspect | HomeClaw (neonize) | OpenClaw (Baileys) |
|--------|--------------------|--------------------|
| Stack | Python + neonize (Go) | Node.js + Baileys |
| Protocol | Unofficial (WhatsApp Web) | Unofficial (WhatsApp Web) |
| Login | QR / pairing | QR / pairing |
| Hosting | We run the client | They run the client |
| Official API | No | No |

**“Webhook” in the sense of WhatsApp Cloud API:** The **official** WhatsApp Cloud API (Meta) is webhook-based: you register a URL; Meta sends events (messages, status, etc.) to that URL. No QR, no long-lived client; you need a Business account and approval. That would be a **different** channel (e.g. “WhatsApp Cloud” or “WhatsApp Business API”) and would **not** replace the current “WhatsApp (neonize)” channel without a separate implementation.

**Recommendation:**

- **Keep the current HomeClaw WhatsApp channel (neonize)** for the existing use case: personal/small-team usage with QR login and no Business API. It is consistent with “we run one bot client per channel.”
- **Do not** switch to OpenClaw’s Baileys purely to get “webhook”: both are unofficial clients; the difference is language/runtime, not webhook vs non-webhook. If we wanted to align with OpenClaw’s stack we’d need a Node bridge or a full port, which is a large change without a clear benefit for the current goal.
- **If** you later need **official** support, compliance, or no QR (e.g. for business numbers), add a **second** channel implementation that uses the **WhatsApp Cloud API** (webhook): register a webhook URL, receive events, send replies via the Cloud API. That would be “WhatsApp Cloud” or “WhatsApp Business” and could coexist with the current neonize-based “WhatsApp” channel.

**Summary:** HomeClaw’s neonize-based WhatsApp and OpenClaw’s Baileys-based WhatsApp are both unofficial Web clients. Neither is the Cloud API webhook. We should keep our plugin unless we explicitly want to add a separate Cloud API (webhook) channel for business/official use.
