# OpenClaw Investigation: media, media-understanding, markdown, pairing, ACP

This document summarizes what the following OpenClaw (clawdbot) modules are and how they work. Source: **`../clawdbot/src`**.

---

## 1. Media (`src/media/`)

**What it is:** A **temporary media storage and serving** layer. It downloads or accepts media (images, audio, etc.), saves them under a config directory with a short TTL, and exposes them via HTTP so other parts of the system (e.g. vision/audio pipelines, channels) can load them by URL.

**How it works:**

- **Store (`store.ts`):**
  - `saveMediaSource(source)` — `source` can be a **URL** (HTTP/HTTPS) or a **local file path**. For URLs it downloads with SSRF guards, redirect limits, and size limits (default 5MB). For local paths it copies within a sandbox. Saves to `configDir/media/` with a sanitized filename (optional pattern `{original}---{uuid}.{ext}`). Returns `{ path, id, size }`.
  - `getMediaDir()`, `ensureMediaDir()`, `cleanOldMedia(ttlMs)` — directory under config; cleanup by TTL (default 2 minutes).
- **Server (`server.ts`):**
  - `attachMediaRoutes(app, ttlMs)` — Express route **GET `/media/:id`**. Serves file by `id` from the media dir, enforces size and TTL, sets MIME via `detectMime`, sends body, then best-effort deletes file after response. Returns 400/404/410/413 for invalid path, not found, expired, or too large.
- **Host (`host.ts`):**
  - `ensureMediaHosted(source, opts)` — Saves the source via `saveMediaSource`, optionally starts a small HTTP server if `startServer` and port is free, and returns a **Tailscale (or local) URL** like `https://{tailnetHostname}/media/{id}` so remote clients (e.g. WhatsApp, Telegram) can fetch the media.
- **Parse (`parse.ts`):**
  - Parses **MEDIA tokens** from command/stdout text (e.g. `MEDIA: \`url\`` or `MEDIA: file path`). Normalizes `file://` to a path, validates URLs vs local paths, optional bare filenames. Used to turn model/cli output into a list of loadable media sources.
- **Fetch (`fetch.ts`):** HTTP fetch for URLs with Content-Length/range checks, max bytes, and optional SSRF policy.
- **MIME (`mime.ts`):** Detect MIME from buffer and/or path; extension from MIME.
- **Input-files (`input-files.ts`):** Extracts text and/or images from **files** (including **PDF** via pdfjs-dist and @napi-rs/canvas), with limits (max bytes, max chars, allowed MIMEs, PDF max pages/pixels). Used to feed file content into the agent.
- **Audio (`audio.ts`), image-ops (`image-ops.ts`), png-encode (`png-encode.ts`):** Utilities for audio tags, image operations, and PNG encoding.

**Summary:** Media = **fetch/copy → temp file under config dir → serve by ID with TTL → optional Tailscale URL for remote access**. Used so channels and understanding pipelines get a stable URL to pass to APIs.

---

## 2. Media-understanding (`src/media-understanding/`)

**What it is:** **Multimodal understanding** for attachments: **images** (describe), **audio** (transcribe), **video** (describe). It runs before or alongside the main LLM so that image/audio/video content is turned into text that the agent can use.

**How it works:**

- **Types (`types.ts`):**
  - `MediaUnderstandingKind`: `"audio.transcription"` | `"video.description"` | `"image.description"`.
  - `MediaAttachment`: `path?`, `url?`, `mime?`, `index`, `alreadyTranscribed?`.
  - `MediaUnderstandingOutput`: `kind`, `attachmentIndex`, `text`, `provider`, `model?`.
  - Provider interface: `transcribeAudio`, `describeVideo`, `describeImage` with request/result types (buffer, fileName, mime, apiKey, model, timeoutMs, etc.).
- **Runner (`runner.ts`):**
  - `runCapability(capability, attachments, ctx, config)` — For each capability (image, audio, video), selects attachments, resolves model (from config/catalog), and runs the appropriate provider (CLI or API). Uses **concurrency** and **caching** (e.g. `MediaAttachmentCache`) to avoid re-running. Returns `{ outputs, decision }` with per-attachment outcomes (success/skipped/failed).
  - Handles **CLI-based** models (e.g. local whisper) and **API-based** providers (OpenAI, Google, Deepgram, etc.). Resolves binary path, timeout, env.
- **Apply (`apply.ts`):**
  - `applyMediaUnderstanding(ctx, config)` — Normalizes attachments from message context, runs image/audio/video understanding in order, then **injects** the resulting text into the context (e.g. as formatted blocks or file content) so the main agent sees “user said X and sent image described as Y, audio transcribed as Z”.
  - Can also extract **text/file** content (PDF, CSV, etc.) via `extractFileContentFromSource` and inject that. Scope and limits come from config.
- **Scope (`scope.ts`):**
  - `resolveMediaUnderstandingScope({ scope, sessionKey, channel, chatType })` — Returns `"allow"` or `"deny"` based on config rules (match by channel, chatType, keyPrefix). Used to turn media understanding on/off per channel or session.
- **Providers (`providers/`):**
  - **OpenAI:** image (vision), audio (Whisper).
  - **Google:** video (Gemini), audio.
  - **Anthropic, Groq, Minimax, Zai:** image (and some audio/video).
  - **Deepgram:** audio transcription (including live).
  - Each provider implements the `MediaUnderstandingProvider` interface (e.g. `describeImage`, `transcribeAudio`, `describeVideo`).

**Summary:** Media-understanding = **attachments → choose provider/model → run transcription/description → inject text into message context** so the agent can “see” and “hear” the user’s media.

---

## 3. Markdown (`src/markdown/`)

**What it is:** **Markdown parsing and channel-specific rendering.** It turns Markdown into an intermediate representation (IR) and then renders it with channel-specific markers (e.g. WhatsApp uses `*bold*`, `_italic_`, `` `code` ``).

**How it works:**

- **IR (`ir.ts`):**
  - Uses **markdown-it** to parse Markdown and build an IR: `MarkdownIR = { text, styles[], links[] }`. Styles are spans with `start`, `end`, and `style`: `bold`, `italic`, `strikethrough`, `code`, `code_block`, `spoiler`, `blockquote`. Links have `start`, `end`, `href`. Handles lists, tables, and nested structures so that the “plain” text plus style/link spans can be re-rendered in different syntaxes.
- **Render (`render.ts`):**
  - `renderMarkdownWithMarkers(ir, options)` — Takes the IR and a **style map** (e.g. `bold → { open: '*', close: '*' }`). Sorts and merges style spans, then walks the text and inserts open/close markers. Optional `buildLink(link, text)` for channel-specific link formatting. Produces a single string with the channel’s markers.
- **WhatsApp (`whatsapp.ts`):**
  - `markdownToWhatsApp(text)` — Converts **standard Markdown** to **WhatsApp** syntax: protect fenced and inline code, then convert `**bold**`/`__bold__` → `*bold*`, `~~strikethrough~~` → `~strikethrough~`. So the bot can output Markdown and the channel adapter gets WhatsApp-compatible formatting.
- **Fences (`fences.ts`):** Parsing of fenced code blocks (used by media parse and others).
- **Code-spans (`code-spans.ts`):** Inline code span parsing.
- **Tables (`tables.ts`):** Table handling in the IR.
- **Frontmatter (`frontmatter.ts`):** YAML frontmatter parsing for documents.

**Summary:** Markdown = **parse Markdown → IR (text + style/link spans) → render with configurable markers** so the same content can be sent as WhatsApp/Telegram/Discord/etc. formatting.

---

## 4. Pairing (`src/pairing/`)

**What it is:** **Channel pairing and approval flow.** When a user contacts the bot on a channel (e.g. Telegram, WhatsApp) that is not yet allowed, the bot shows a **pairing code**. The owner approves via CLI (`openclaw pairing approve <channel> <code>`). The store persists pending requests and an allow-list per channel.

**How it works:**

- **Pairing-store (`pairing-store.ts`):**
  - **PairingRequest:** `id`, `code` (8-char from alphabet A–Z/2–9), `createdAt`, `lastSeenAt`, `meta?`. Stored per channel in `{credentialsDir}/{safeChannelKey}-pairing.json`. TTL for pending (e.g. 1 hour), max pending per channel (e.g. 3). Uses **proper-lockfile** for concurrent safety.
  - **Allow-list:** `allowFrom: string[]` in `{channel}-allowFrom.json`. Functions: add pending request, get/cancel by code, approve (move identity from pending to allowFrom), list allowed, check if a user is allowed.
- **Pairing-messages (`pairing-messages.ts`):**
  - `buildPairingReply({ channel, idLine, code })` — Builds the reply shown to the user: “OpenClaw: access not configured”, the user id line, the pairing code, and the CLI command for the owner to approve: `openclaw pairing approve <channel> <code>`.
- **Pairing-labels (`pairing-labels.ts`):**
  - `resolvePairingIdLabel(channel)` — Returns the channel’s human-readable id label (e.g. “userId”) from the channel’s pairing adapter, used in messages.

**Summary:** Pairing = **unknown user gets a code → owner runs CLI to approve → identity stored in allowFrom** so only approved users can use the bot on that channel.

---

## 5. ACP (`src/acp/`)

**What it is:** **Agent Client Protocol (ACP) gateway bridge.** OpenClaw can run as an **ACP agent** that speaks the Agent Client Protocol (stdin/stdout ND-JSON stream). The ACP server process connects to the **OpenClaw Gateway** (WebSocket) and translates between ACP requests (e.g. `Initialize`, `Prompt`, `ListSessions`) and gateway RPC/events. So an ACP client (e.g. Cursor, another IDE) can talk to OpenClaw’s backend through this process.

**How it works:**

- **Types (`types.ts`):**
  - `AcpSession`: `sessionId`, `sessionKey`, `cwd`, `createdAt`, `abortController`, `activeRunId`. Tracks a session and its active run for cancel.
  - `AcpServerOptions`: `gatewayUrl`, `gatewayToken`, `gatewayPassword`, `defaultSessionKey`, `defaultSessionLabel`, `requireExistingSession`, `resetSession`, `prefixCwd`, `verbose`.
- **Server (`server.ts`):**
  - `serveAcpGateway(opts)` — Loads config, builds gateway connection and auth (token/password). Creates a **GatewayClient** (WebSocket to gateway) and an **AgentSideConnection** from the **ACP SDK** over stdin/stdout (ND-JSON stream). Instantiates **AcpGatewayAgent** (translator) that implements the ACP `Agent` interface; gateway events are forwarded to the agent. So: **stdin/stdout (ACP) ↔ AcpGatewayAgent ↔ GatewayClient ↔ Gateway**.
- **Translator (`translator.ts`):**
  - **AcpGatewayAgent** implements ACP methods: `initialize`, `newSession`, `loadSession`, `listSessions`, `prompt`, `cancel`, etc. For `prompt`, it maps ACP prompt + attachments to gateway chat format, sends to the gateway, and streams back agent/tool events into ACP session notifications (e.g. `agent_message_chunk`, `tool_call`). Session keys and IDs are mapped via **session-mapper**; attachments are extracted and formatted via **event-mapper**.
- **Session (`session.ts`):**
  - **AcpSessionStore** (in-memory by default): create/get session by id, get by runId, set/clear/cancel active run (abort controller). Used by the translator to track sessions and cancel runs.
- **Session-mapper (`session-mapper.ts`):** Maps between ACP session ids/keys and gateway session keys; handles `resetSession` and meta (cwd, label).
- **Event-mapper (`event-mapper.ts`):** Maps gateway chat/agent events to ACP structures (e.g. extract text from prompt, attachments, tool calls).
- **Client (`client.ts`):**
  - `createAcpClient(opts)` — Spawns the **openclaw acp** process (server) with optional args, wraps stdin/stdout in a **ClientSideConnection** (ACP SDK), and returns a handle. Used when an app (e.g. Cursor) wants to connect to OpenClaw as an ACP agent; the app runs the client which starts the server subprocess and talks ACP over its stdio.
- **Commands (`commands.js`):** Exposes available commands to the ACP client.
- **Meta (`meta.js`):** Helpers to read config/meta (e.g. bool, number, string) for session options.

**Summary:** ACP = **stdio (ND-JSON) ↔ ACP SDK ↔ AcpGatewayAgent ↔ GatewayClient ↔ OpenClaw Gateway**. Enables IDE/ACP clients to use OpenClaw’s sessions and models without implementing the gateway protocol.

---

## Quick reference

| Module               | Purpose                                                                 | Key entry points / concepts                                      |
|----------------------|-------------------------------------------------------------------------|-------------------------------------------------------------------|
| **media**            | Temp media storage and HTTP serving; URLs for channels/APIs           | `saveMediaSource`, `GET /media/:id`, `ensureMediaHosted`, parse MEDIA tokens |
| **media-understanding** | Turn images/audio/video into text for the agent                    | `applyMediaUnderstanding`, `runCapability`, providers (OpenAI, Deepgram, …)  |
| **markdown**         | Parse Markdown to IR; render with channel-specific markers            | `MarkdownIR`, `renderMarkdownWithMarkers`, `markdownToWhatsApp`   |
| **pairing**          | Pairing codes and allow-list for channel access                       | Pairing store (pending + allowFrom), `buildPairingReply`, approve via CLI   |
| **acp**              | ACP protocol bridge to OpenClaw Gateway                                | `serveAcpGateway`, `AcpGatewayAgent`, GatewayClient, ClientSideConnection   |

---

## When to use them / HomeClaw implications

### Media and media-understanding

**When OpenClaw uses them**

- **Media:** When a channel sends or receives files (images, audio, documents): save to temp dir, serve via GET `/media/:id`, or produce a shareable URL (e.g. Tailscale) so the other side (channel or API) can load the file.
- **Media-understanding:** OpenClaw runs it **once per inbound message, before the main LLM**, in the reply pipeline. In `auto-reply/reply/get-reply.ts`, right after `finalizeInboundContext(ctx)` and before session/command handling, it calls:
  - `applyMediaUnderstanding({ ctx: finalized, cfg, agentDir, activeModel })`
  So **when the user sends a message that has attachments** (image, audio, video), OpenClaw:
  1. Resolves scope (allow/deny by channel/session from config).
  2. For each capability (image → describe, audio → transcribe, video → describe), picks a provider/model (OpenAI, Google, Deepgram, etc.), runs it, and gets text.
  3. Injects that text into the message context (e.g. “User sent an image. Description: …” or “Audio transcript: …”).
  4. The main chat model then sees **text only** (plus optional image URLs if the model is vision-capable).
  So “when to use” is: **whenever the incoming request has image/audio/video attachments and media-understanding is enabled in config.** No extra “decision” at runtime beyond: attachments present + scope allow → run understanding.

**How HomeClaw could use them**

- **Multimodal models (e.g. OpenAI, Gemini):** If the model supports **images**, you can send image URLs or base64 in the chat API; no separate “understanding” step is required for the model to “see” the image. You still need **media** to store/serve files so the channel can hand you a URL or path, and so you can pass a URL (or buffer) to the API.
- **Audio / video:** Most chat APIs don’t accept raw audio/video. So you **convert to text first** (transcription/description) and then either:
  - Inject that text as user context (“User sent audio. Transcript: …”), or
  - Use it as the sole user message when there’s no other text.
  That’s exactly what **media-understanding** does: run transcription/description, then inject text. So for HomeClaw:
  - **Images:** Optional. Use media to hold files/URLs; either (a) send images to a vision-capable model directly, or (b) run image description and inject text (useful if the main model is text-only).
  - **Audio / video:** Use media-understanding-style pipeline (or a single provider) to get text, then inject into context or use as user message.
- **When to run:** Same as OpenClaw: **before** the main LLM call, if the current request has attachments and config allows (e.g. enabled + scope allow). So: in your “process message” path, after you have the final message + attachments, if there are image/audio/video attachments → run understanding → merge results into the text/context you send to the model.

**Summary:** You need **media** (storage + optional HTTP serving) whenever channels send or receive binary files. You need **media-understanding** (or equivalent) when you have audio/video (to get text), or when you want image description as text for a text-only model. With a multimodal model, images can go straight to the model; audio/video still need a “understand → text” step.

**HomeClaw implementation status (media and media-understanding)**

We have **not** implemented separate **named** "media" and "media-understanding" modules that are "called at proper time" like OpenClaw. What we have:

| Concept | Implemented? | When / where it runs |
|--------|---------------|----------------------|
| **Media (storage + serving)** | **No** | We do not have temp media storage or GET `/media/:id`. Channels send paths or data URLs in `request.images` / `request.audios` / `request.videos`; we use them directly when building the message. |
| **Media in the message** | **Yes** | In `process_text_message`: we read `request.images`, `request.audios`, `request.videos`, check `Util().main_llm_supported_media()`, and add image/audio/video **content parts** (image_url, input_audio, input_video) to the user message when the model supports them. So "media" is handled at the **right time** (when building the message), but it is **implicit** in the pipeline, not a separate callable "media" step. |
| **Media-understanding (multimodal)** | **Yes, when model supports it** | When the main model supports image/audio/video, we send those parts in the same chat completion; the model "understands" at chat time. So understanding is **called at the proper time** (when we call the LLM with the message we built). No separate "applyMediaUnderstanding" step. |
| **Media-understanding (text-only model)** | **No** | When the model does **not** support a media type, we **omit** that media and add a short note (e.g. "Image(s) omitted - model does not support images."). We do **not** run a separate "understand → inject text" step (e.g. describe image → inject "User sent an image. Description: …"). So text-only models never "see" the content of images/audio/video. |
| **Media-understanding (tool)** | **Yes, for image only** | The **image** tool calls `core.analyze_image(prompt, image_base64, mime_type)` when the LLM wants to analyze an image (e.g. from a path or URL). So explicit "media-understanding" for **image** is **called at the proper time** (when the model invokes the image tool). We do not have an "audio" or "video" tool that transcribes/describes and returns text. |

---

### Markdown

**When OpenClaw uses it**

Markdown is used **on the way out**: when the **bot’s reply** is sent to a channel that does not support full Markdown. The agent/model outputs Markdown; the channel adapter converts it to the channel’s format before sending.

- **WhatsApp:** `markdownToWhatsApp(text)` in `web/auto-reply/deliver-reply.ts` and `web/outbound.ts`. Converts `**bold**` → `*bold*`, `~~strikethrough~~` → `~strikethrough~`, leaves code blocks and inline code as-is (WhatsApp uses ``` for monospace).
- **Telegram:** `markdownToIR` + `renderMarkdownWithMarkers` in `telegram/format.ts` to produce Telegram’s Markdown or HTML for captions and messages.

So: **Markdown is used when sending the assistant’s reply to a channel that has its own formatting rules** (WhatsApp, Telegram, etc.). The same Markdown reply is converted per channel.

**When HomeClaw would use it**

Use it when **you send the model’s reply to a channel that expects a different syntax** (e.g. WhatsApp, Telegram). If your channel adapter sends plain text only, you don’t need it. If you add WhatsApp/Telegram (or similar) and want bold/italic/code to show correctly, add a Markdown → channel-format step (e.g. a small `markdownToWhatsApp`-style function) in the adapter that delivers the reply.

---

### Pairing — what it is for, and should HomeClaw consider it?

**What pairing is for (OpenClaw docs + code)**

OpenClaw uses “pairing” in **two separate** ways:

1. **DM pairing (who can talk to the bot in DMs)**  
   - When a channel’s **DM policy** is `pairing`, **unknown senders** (not on the allowlist) do **not** get their messages processed. Instead they receive a **short pairing code** (8 chars, 1-hour TTL, max 3 pending per channel). The **owner** approves by running:
   - `openclaw pairing list <channel>`
   - `openclaw pairing approve <channel> <code>`
   - Approved identities are stored in `~/.openclaw/credentials/<channel>-allowFrom.json` (and merged with config allowlists). So pairing is the **default access control for DMs**: “only people I’ve explicitly approved can DM my bot.”
   - Alternatives in OpenClaw: `allowlist` (block unknown, no code), `open` (allow everyone; requires explicit `"*"` in allowlist), `disabled` (no DMs).

2. **Node/device pairing (which devices can join the gateway)**  
   - Separate flow for **devices** (e.g. iOS/Android app, headless nodes) that connect to the Gateway. They create a “device” pairing request; the owner approves with `openclaw devices list` / `openclaw devices approve <id>`. State lives under `~/.openclaw/devices/`. This is **not** about chat users; it’s about which machines/apps can attach to the gateway.

**So “pairing mode” (in the sense you asked about) = DM pairing:**  
“Unknown user sends a DM → bot replies with a code and ignores content until owner runs CLI to approve.”

**Should HomeClaw consider it?**

- **Consider DM pairing if:** You have (or plan) **multiple channels** (e.g. Telegram, WhatsApp) where **unknown users** can DM the bot, and you want **“only approved users can talk to the bot”** without maintaining a static config list by hand. Then a pairing flow (code + approve via CLI or a small admin UI) is useful.
- **You may skip it if:**  
  - HomeClaw is **single-user** or only used by you (e.g. one Telegram account), or  
  - You’re fine with a **fixed allowlist** in config (e.g. `user.yml` or channel config) and don’t need on-the-fly approval of new users.

So: **Pairing is for secure, owner-approved DM access.** Adopt it if you want OpenClaw-style “unknown user gets a code → I approve once → they can DM”; otherwise an allowlist or single-user setup is enough.
