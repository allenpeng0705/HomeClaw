# Outbound Markdown and unknown-request notification

This doc describes two optional features: **(1) outbound Markdown conversion** so channels that don’t display Markdown well can show readable text, and **(2) notifying the owner when an unknown user tries to access** so they can add that identity to `config/user.yml` (no separate “pairing” flow).

---

## 1. Outbound Markdown (Core applies by default)

**Purpose:** When the assistant’s reply is **Markdown** (e.g. `**bold**`, `*italic*`, code blocks, lists) and the **channel cannot render Markdown** well, the user may see raw Markdown. Outbound Markdown conversion turns the reply into something the channel can display nicely.

**When we convert:** **Only when the result looks like Markdown** (e.g. contains `**`, `*`, `` ` ``, `#`, links, etc.). If the reply is plain text, Core sends the **original text** unchanged. So Markdown replies get converted; plain replies pass through as-is.

**Who does it:** **Core** converts (when applicable) **before** sending to channels. Channels receive the text and send it as-is; they do **not** need to call any Markdown helper.

**Config:** In `config/core.yml` — **`outbound_markdown_format`**: `whatsapp` (default) | `plain` | `none`

- **whatsapp** — when the reply is Markdown, convert to `*bold*` `_italic_` `~strikethrough~` (works for most IMs: WhatsApp, Telegram, Signal, etc.).
- **plain** — when the reply is Markdown, strip to **plaintext**. Use this if your channel **does not support** the whatsapp-style markers (e.g. some SMS or minimal clients); you still get readable text without raw `**` or `*`.
- **none** — no conversion; always send the raw assistant reply.

**Implementation:**

- **Core** uses a helper when building every outbound `response_data["text"]`. The helper checks `outbound_markdown_format`; if `none`, returns original text. If the text **does not look like Markdown** (no bold/italic/code/headers/links), returns original text. Otherwise converts via **base/markdown_outbound.py** (`looks_like_markdown` + `markdown_to_channel`); on any failure returns the **original text** so Core never crashes.
- **base/markdown_outbound.py** (never raises): `looks_like_markdown(text)`, `markdown_to_plain(text)`, `markdown_to_whatsapp(text)`, `markdown_to_channel(text, format)`.
- Channels just send the text they receive.

**Summary:** Conversion runs **only when the result is Markdown**; otherwise the original text is sent. Config in `core.yml`: `whatsapp` (default for most IMs) or `plain` for channels that don’t support whatsapp format (plaintext output).

---

### 1.1 Three outbound formats (Core decides per response)

Core classifies each outbound response and sends a **`format`** field alongside **`text`** so clients can display correctly:

| **format** | **Meaning** | **Use** |
|------------|-------------|--------|
| **plain** | Ordinary text; no Markdown. | Show as plain text. |
| **markdown** | Content is Markdown; clients that support it (Companion app, web chat, Control UI) should **render** it in the chat view. | Display as rendered Markdown (headings, lists, code, links). |
| **link** | Short message with a file, folder, or report link (e.g. *"Report is ready. Open: &lt;url&gt;"* or `/files/out`). | Show the text and make the URL clickable. |

**File/folder vs image:**

- **File or folder:** Responses that contain a file or folder reference (e.g. report link, `/files/out?...`) are classified as **link** when the message is short and contains an http(s) URL. The client shows the text and makes the link clickable.
- **Image (exception):** When the response includes an **image**, Core sends it **directly** to the channel/Companion in the payload (`images` / `image` as data URLs or paths), not as a link. The client displays the image inline.

**Stability:** All outbound helpers (`classify_outbound_format`, `_outbound_text_and_format`, `_safe_classify_format`) are written to **never raise**; on any exception they return a safe default (e.g. `"plain"` or `(text, "plain")`) so Core never crashes.

**Where `format` appears:** WebSocket `/ws` and POST `/inbound` responses include `"format": "plain"|"markdown"|"link"`. The same field is set in `response_data` when Core pushes to the channel queue (channels can ignore it or use it).

**Behavior:**

- For **WebSocket** and **POST /inbound** (Companion, web chat, Control UI): when Core classifies as **markdown** or **link**, it sends **raw** `text` (no conversion); when **plain**, it applies `outbound_markdown_format` so the payload is consistent. So markdown-capable clients receive raw Markdown when `format === "markdown"` and should render it; when `format === "plain"` they should show as plain text (e.g. `Text` widget, not MarkdownBody) so that converted markers like `*bold*` are not re-interpreted.
- For **channel queue** (e.g. Telegram, WhatsApp, Discord): Core sends **converted** text (per `outbound_markdown_format`) and always sets **`format`: `"plain"`** so the payload is self-consistent (channel-ready text; no markdown/link hint). Channels send the text as-is.

**Classification** (in **base/markdown_outbound.py**): `classify_outbound_format(text)` — short message (≤600 chars) with an http(s) URL and no Markdown → **link** (file/folder/report links); text that looks like Markdown → **markdown**; else **plain**. Never raises. Core uses `_safe_classify_format(text)` so format is always set safely.

**Why it might not work well (and what was fixed):**

- **Format vs content mismatch:** Previously, the channel queue sent **converted** text (e.g. `*bold*` for WhatsApp) but still set `format` to `"markdown"` or `"link"` from the original reply. Any client that used `format` to choose rendering would try to render that text as Markdown and get wrong display. **Fix:** Channel queue now always sends `format: "plain"` when the text is channel-ready (converted), so the payload is consistent.
- **Rich clients ignoring `format`:** Companion and web chat get responses from POST /inbound or WebSocket with raw text and `format` (plain | markdown | link). If the client **always** renders the reply as Markdown (e.g. `MarkdownBody`), then when `format === "plain"` the converted text (e.g. `*bold*`) may be re-interpreted (e.g. as italic). **Recommendation:** When `format === "plain"`, render with a plain text widget; when `format === "markdown"` or `"link"`, use Markdown so links and structure render correctly.
- **Link classification:** "link" is only used when the message is ≤600 chars and contains an http(s) URL and does **not** look like Markdown. Longer messages or messages with bold/italic/code are classified as "markdown"; they still get raw text and URLs are tappable if the client uses a Markdown renderer.

---

## 2. Unknown-request notification (no separate pairing)

**What we already have:** **user.yml** is the allowlist. Each user has `im`, `email`, `phone` (channel identities). If the request’s `user_id` is not in any user’s list for that channel type, Core **denies** (401). So “pairing” in the sense of “who can access” is already done via user.yml.

**Permission rule unchanged (empty list = allow all):** The unknown-request notification **does not change** permission logic. The rule remains: **if a user’s list (`im`, `email`, or `phone`) is empty for that channel type, that user is treated as a match — i.e. allow all senders for that channel.** So empty list = allow all. We encourage users to set permission lists correctly (non-empty when you want to restrict access). Only when **no** user matches (every user has a non-empty list and the request’s `user_id` is not in any of them) do we deny — and optionally notify.

**What we may add:** An optional **notification** when an **unknown** user is **denied**:

1. **Detect:** Core receives a request; `check_permission` returns no match (deny). Notification runs **only** in this case; it never affects when we allow or deny.
2. **Notify:** Optionally send a message to the **last-used channel** (the channel that last sent a message to Core — typically the owner’s). The message says something like: *“Unknown request from \<channel_name\>: user_id=\<user_id\>. Add this identity to config/user.yml (under im, email, or phone) to allow access.”*
3. **Owner decides:** The owner sees this on their client and can **add** that identity to user.yml (im, email, or phone) and reload. No separate pairing flow.

**Config:** Optional `notify_unknown_request: true` in `config/core.yml`. When `true` and permission is **denied**, Core pushes that message to the response queue for the last-used channel. The owner gets the notification there.

**Important:** We only update “last channel” when the request is **allowed**. So when an unknown user is denied, we do **not** overwrite last channel; the notification goes to the owner’s last-used channel.

**Summary:** Permission rule is unchanged: empty list = allow all. Optional: when a request is denied (no user matched), notify the owner via last-used channel so they can add that identity to user.yml. We encourage setting permission lists correctly.

---

## 3. Long-running tasks (PPT, slides, document summarize)

**Issue:** When the user asks for a PPT, HTML slides, or a long document summary, the model may reply with “I am working with you and need some time” but **not call the tool** (e.g. `route_to_plugin` for ppt-generation). The client then receives only that short message and never gets the file or link, so it feels like “nothing happened.”

**How sync /inbound works:** POST /inbound and WebSocket /ws return **one** response when the full pipeline (LLM + tools) finishes. There is no streaming of intermediate “working…” messages. So the user sees either (1) the final reply (with link or result), or (2) a timeout/error if the request takes too long.

**What was fixed:**

- **Fallback when the model doesn’t call the tool:** If the user clearly asked for PPT/slides/presentation (e.g. “generate a PPT about X”, “做个PPT”) and the model returns a short “working on it” style message **without** calling `route_to_plugin`, Core now infers `route_to_plugin(plugin_id=ppt-generation, capability_id=create_from_source, parameters={source: user query})` and runs the plugin. The user gets the file + link in the same response.
- **Tool description:** The `route_to_plugin` tool description now states that the model **must** call the tool (not just say “I need some time”) so the user gets the result.

**Recommendations:**

- **Client timeout:** PPT generation or document summarization can take 1–3 minutes. The Companion app uses a 600s (10 min) timeout for POST /inbound; other clients (e.g. nginx, Cloudflare) should set `read_timeout` ≥ `inbound_request_timeout_seconds` (or ≥ 300 if you want a cap). See `config/core.yml` and `inbound_request_timeout_seconds`.
- **User messaging:** If your client shows a loading state, keep it until the HTTP response arrives (or timeout). Optionally show a short hint like “PPT and long summaries can take 1–2 minutes” so the user knows to wait.

---

## 4. Progress during long work (stream=true)

**Purpose:** When a task takes a long time (PPT, document read, save_result_page), the user sees only a loading state and doesn’t know what’s happening. **Progress feedback** lets the client show messages like “Generating your presentation…” so the user knows the system is working.

**What "stream" means:** With **`stream: true`**, the client does **not** get a single JSON response. It gets a **stream of events** (SSE): each event is a line `data: {...}\n\n`. The client reads events until it receives one with `event: "done"`, which has the same payload as the non-stream response (text, format, images). So "stream" = **response format** (SSE) + optional **progress** events before "done".

**How it works:**

- **POST /inbound** accepts an optional **`stream`: `true`** in the request body (same payload as usual: `user_id`, `text`, etc.).
- When **`stream: true`**, Core returns **Server-Sent Events (SSE)** (`Content-Type: text/event-stream`) instead of a single JSON response.
- **Progress events:** Core sends an initial "Processing your request…" right away. During the pipeline, when a long-running tool is about to run (`route_to_plugin`, `run_skill`, `document_read`, `save_result_page`), Core pushes a progress event on the stream, e.g.  
  `data: {"event": "progress", "message": "Generating your presentation…", "tool": "route_to_plugin"}\n\n`  
  Message text is short and user-facing (e.g. “Generating your presentation…”, “Reading the document…”, “Running ppt-generation…”).
- **Final event:** When the pipeline finishes, Core sends one last SSE event:  
  `data: {"event": "done", "ok": true, "text": "...", "format": "plain"|"markdown"|"link", "status": 200, "images": [...]}\n\n`  
  Same shape as the non-stream JSON response (text, format, images as data URLs when present). On error, `ok: false` and `error` is set.

**Effect on short tasks (always use stream):** If the client **always** sends `stream: true`, a short task (e.g. quick Q&A, no tools) still works the same: the client receives (1) one progress event, e.g. "Processing your request…", then (2) soon after the "done" event with the reply. The user may briefly see "Processing your request…" and then the answer. There is no extra delay or different result — only the response is delivered as SSE instead of one JSON. The client must use the SSE code path (EventSource or parse `data:` lines) and treat "done" as the final reply; that same path works for both short and long tasks.

**How the client decides:** The client does **not** need to guess which requests will be long. Two simple options:

- **Always use stream:** Send `stream: true` for every POST /inbound if you want progress. For short tasks you will just get the `done` event quickly (with few or no progress events). Same final result shape.
- **User preference:** Add a setting like "Show progress during long tasks" and send `stream: true` when it is on. Again, no per-request guessing.

**Client usage:**

1. POST `/inbound` with body `{ "user_id": "...", "text": "...", "stream": true }`.
2. Read the response as an **EventSource** (or fetch with `Accept: text/event-stream` and parse `data:` lines).
3. For each event: if `event === "progress"`, show `message` in the UI (e.g. under the loading spinner). If `event === "done"`, use `text`, `format`, and `images` as the final reply and close the stream.

**Client parsing and display:**

- **Parse:** The response body is SSE: each event is one or more lines ending with a blank line. Each event line starting with `data: ` (space after colon) carries one JSON object. So: read the stream (e.g. chunk by chunk or line by line); buffer until you have a full event (e.g. up to `\n\n`); for each line that starts with `data: `, take the rest of the line, parse as JSON → you get an object with at least `event` and either `message` (progress) or `text` / `format` / `images` (done).
- **Decide what to show:** Inspect the parsed object’s `event` field:
  - **`event === "progress"`** → Optional: show `message` to the user (e.g. under the loading spinner or as the loading label). You can choose to show every progress message, or only the latest, or hide progress and keep a generic “Working…” (e.g. from a user preference “Show progress during long tasks”).
  - **`event === "done"`** → This is the final reply. Use `text`, `format`, and `images` exactly like the non-stream JSON response: show the reply in the chat, render markdown/link if needed, display images. If `ok === false`, show `error` (or `text`) as the error message. Then close the stream and stop reading.
- **Whether to display progress:** Up to the client. Options: (1) always show progress messages; (2) show progress only when a “show progress” preference is on; (3) never show progress text, only a generic spinner until “done”. Parsing is the same in all cases; you only change what you render for `event === "progress"`.

**Example (Companion or WebChat):** Use `stream: true` when sending a message (or when a "show progress" preference is on); subscribe to the SSE stream and update the loading label with each `progress.message` until `done`. No protocol change for the final result — same `text`/`format`/`images` as non-stream.

**Effect on channels:** The **`stream`** parameter applies only to **POST /inbound** (and its HTTP response). Channels that use **POST /process** (e.g. Telegram/Discord bridges) do **not** call /inbound; they push a request to Core's queue and receive the reply when Core POSTs to their **/get_response** endpoint. So **stream has no effect** on those channels — they always get one final response (no progress events over the channel today). If a channel bridge instead called **POST /inbound** (e.g. a relay that receives Telegram messages, calls Core /inbound, then sends the result to Telegram), then that bridge could use `stream: true` to get progress and optionally show it in the channel (e.g. send "Processing your request…" then the final reply).

**Companion app: switcher, parsing, and display design**

- **Who uses stream:** In practice only the **Companion app** (and any client that explicitly opts in) will set `stream: true`. Other channels use POST /process and get one result via callback, so they do not need streaming. So it is correct to add streaming support only where the client waits on the HTTP response (e.g. Companion).
- **Switcher:** Add a **setting** in the Companion app (e.g. "Show progress during long tasks") to turn streaming on or off. When **on**: send `stream: true`, parse SSE, and show progress messages. When **off**: send `stream: false` (or omit), use the single-JSON response path — no parsing of SSE, same behavior as today. This keeps other clients unchanged and lets users who prefer a simple loading bar disable progress text.
- **Parsing and display:** When the setting is on, the Companion should (1) send `stream: true` in the POST /inbound body, (2) read the response as a stream (e.g. chunked), (3) parse SSE: buffer until a full event (e.g. up to `\n\n`), for each line starting with `data: ` parse the rest as JSON, (4) if `event === "progress"` call a callback or set state with `message`, (5) if `event === "done"` use `text` / `format` / `images` as the final reply and close. So yes — add parsing and displaying of streaming messages when the switcher is on.
- **How to display progress (design):** Before the final result, show progress under the same loading state so the user sees one place for "working". Options: (A) **Under the loading bar** — show a short line of text below the existing linear/indeterminate progress indicator (e.g. "Processing your request…", then "Generating your presentation…"). (B) **Replace the generic "Loading…"** — use the latest progress `message` as the loading label instead of a fixed string. (C) **Temporary chat bubble** — show progress as a temporary assistant message that is replaced by the final reply when "done" (can feel noisy). Recommendation: (A) or (B); keep progress in the same visual area as the spinner/bar so it’s clear it’s still loading, not a final message.
