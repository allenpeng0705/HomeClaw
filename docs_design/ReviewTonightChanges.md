# Review: Tonight’s Changes (Logic, Stability, Robustness)

This document summarizes the changes made in this session and the review applied for logic, stability, and robustness. It covers: **channels (file and media support)**, **plugin LLM and concurrency**, **session-related behavior**, **file-understanding** (Core integration and design), and **system_plugins/homeclaw-browser** (Control UI, browser, canvas, nodes).

---

## 1. Channels: File and Media Support

### 1.1 Core and base

- **InboundRequest** (`base/base.py`): Added optional `videos`, `audios`, `files` (and existing `images`). All optional lists; Core uses `getattr(..., None) or []` when reading.
- **Core `/inbound` and `/ws`** (`core/core.py`): Read `request.videos`, `request.audios`, `request.files`; set `pr.videos`, `pr.audios`, `pr.files`; choose `content_type_for_perm` from VIDEO / AUDIO / TEXTWITHIMAGE / TEXT (files-only → TEXT). File-understanding block resolves data-URL `request.files` to temp paths before `process_files`.
- **WebSocket `/ws`**: Builds `InboundRequest` with `images`, `videos`, `audios`, `files` from client JSON. Validation: require `user_id` and either `text` or at least one of images/videos/audios/files (`has_media`).

**Logic:** Media-only messages are allowed; permission uses content type; file-understanding only for `files` (data URLs resolved to temp paths).

**Stability:** Safe list access (`list(...) if getattr(...) else []`); no crash on missing keys.

---

### 1.2 Channels using `/inbound`

- **Telegram, Discord, Slack:** Attachments downloaded (or data URL); classified by content type into images/videos/audios/files; sent in payload. Defensive try/except around downloads; limited attachment count (e.g. Teams 15, Discord 10).
- **Webhook, Signal, Google Chat, Feishu, Dingtalk:** Optional `images`, `videos`, `audios`, `files` in payload/event; forwarded when present. Text default `"(no text)"` when only media.
- **Teams:** Bot Framework `activity.attachments`; `_content_type_media_kind()`; `_download_teams_attachment_to_data_url()` (async httpx); cap 15 attachments; message with only attachments allowed.
- **iMessage, Zalo, BlueBubbles:** Pydantic body with optional `text`, `images`, `videos`, `audios`, `files`; payload includes media when present; `text` default `"(no text)"`.

**Logic:** All channels that can send media now send it in the same shape (images/videos/audios/files); Core treats them uniformly.

**Stability:** Optional fields; safe `.get()` or `or []`; no crash on missing body keys.

---

### 1.3 Email channel

- **Attachment extraction** (`channels/emailChannel/channel.py`): `_extract_attachments_from_message()` walks MIME parts; `Content-Disposition` attachment/inline with filename; decode payload → temp file; classify by `_media_kind(content_type)`; return (images, videos, audios, files). Exceptions in write logged; continue.
- **fetch_email_content:** Returns (msg_id, from_addr, subject, body, images, videos, audios, files). **Guards:** If `data` empty or `data[0]` too short, return empty tuple. Try/except around `message_from_bytes` and around `_extract_attachments_from_message`; on failure return empty strings/lists or skip.
- **monitor_inbox:** Unpacks 8 values; **skip when `not msg_id and not from_addr`** (invalid fetch). Builds PromptRequest with images/videos/audios/files; sets `contentType` from media; passes `files=` to Core.

**Logic:** Only parts with filename and attachment/inline are treated as attachments; content type drives classification; failed decode or extraction does not crash the loop.

**Stability:** Guards on fetch result; try/except around decode and attachment extraction; skip bad emails.

---

### 1.4 WebChat

- **index.html:** File input; `mediaKind(type)`; on send, read files via FileReader as data URLs; classify into images/videos/audios/files; payload includes them; text default `"(no text)"` when only files.

**Logic:** Same media shape as other channels; WebSocket message matches Core’s InboundRequest.

---

## 2. Plugin LLM and Concurrency

### 2.1 Same REST API for built-in and external plugins

- **POST /api/plugins/llm/generate** (`core/core.py`): Body `PluginLLMGenerateRequest` (`messages`, optional `llm_name`). Validates `messages` is non-empty list; calls `self.openai_chat_completion(messages, llm_name=llm_name)`; returns `{ "text": "..." }` or error. Auth: `Depends(_verify_inbound_auth)` (same as `/inbound`).
- **PluginLLMGenerateRequest** (`base/base.py`): `messages: List[Dict[str, Any]]` (supports multimodal content); `llm_name: Optional[str] = None`.
- **Util.plugin_llm_generate()** (`base/util.py`): POSTs to `get_core_url() + "/api/plugins/llm/generate"`; adds X-API-Key when auth_enabled; **try/except around `resp.json()`** so malformed JSON doesn’t crash; returns text or None.

**Logic:** One API for all plugin LLM calls; built-in use helper, external use HTTP; auth and contract aligned.

**Stability:** Validation on `messages`; getattr for body fields; exception handling in handler and in helper; JSON parse guarded.

---

### 2.2 LLM concurrency (llm_max_concurrent_local, llm_max_concurrent_cloud)

- **Config:** `core.yml` and `CoreMetadata`: `llm_max_concurrent_local` (default 1), `llm_max_concurrent_cloud` (default 4); clamped 1–32 in `from_yaml`.
- **Util** (`base/util.py`): `_get_llm_semaphore()` lazy-creates `asyncio.Semaphore(n)`. **Thread-safe creation:** class-level `Util._llm_semaphore_creation_lock` (threading.Lock); double-check inside lock so only one semaphore is created.
- **openai_chat_completion:** Acquires semaphore then calls `_openai_chat_completion_impl`. **openai_chat_completion_message:** Acquires same semaphore then calls `_openai_chat_completion_message_impl`. REST handler uses Core’s `openai_chat_completion`, so it shares the semaphore.

**Logic:** All LLM use (channel, post_process, tool loop, plugin API) goes through the same semaphore; default 1 serializes; config allows 2–10 for cloud.

**Stability:** Lazy init with lock avoids race on semaphore creation; n clamped so semaphore is valid.

---

### 2.3 Post-process and docs

- **tools/builtin.py:** Post-process uses only `post_process_prompt` (system) and plugin output (user); comment notes Core applies markdown outbound when sending to channel.
- **PluginLLMAndQueueDesign.md:** Describes post_process, same API for built-in/external, concurrency, local vs cloud recommendation (1 vs 2–10).
- **PluginsGuide.md:** Built-in plugins use `Util().plugin_llm_generate()` for LLM; link to design doc.

---

## 3. Robustness Fixes Applied in Review

1. **PluginLLMGenerateRequest.messages:** Type changed from `List[Dict[str, str]]` to `List[Dict[str, Any]]` so multimodal (e.g. content as list) is accepted.
2. **Util._get_llm_semaphore:** Creation guarded by class-level `threading.Lock` and double-check so only one semaphore is created under concurrency.
3. **Email fetch_email_content:** Guard when `data` empty or `data[0]` too short; try/except around `message_from_bytes` and around `_extract_attachments_from_message`; return empty tuple or empty lists on failure.
4. **Email monitor_inbox:** Skip processing when `not msg_id and not from_addr` after fetch (invalid email).
5. **Util.plugin_llm_generate:** try/except around `resp.json()` so malformed response body doesn’t raise; fallback to `{}`.

---

## 4. Summary Checklist

| Area              | Logic | Stability | Robustness |
|-------------------|-------|-----------|------------|
| InboundRequest + Core /inbound, /ws | ✓ Media and files; content_type; file-understanding | ✓ getattr; safe lists | ✓ Validation; data-URL resolve |
| Channels (Telegram, Discord, Slack, Teams, etc.) | ✓ Same payload shape; text default | ✓ Optional fields; try/except download | ✓ Attachment limits; skip bad data |
| Email attachments | ✓ MIME walk; temp files; skip bad fetch | ✓ Guards; try/except decode/extract | ✓ Skip invalid email; no crash on bad part |
| Plugin LLM API    | ✓ One API; semaphore shared | ✓ Auth; validation; exception handling | ✓ Any for messages; JSON parse safe |
| llm_max_concurrent_local / _cloud | ✓ Two semaphores (local vs cloud); resolve then acquire | ✓ Locked lazy init; n clamped | ✓ Local 1, cloud 4 defaults |
| **Session**        | ✓ dm_scope; per-session key; cron delivery | ✓ session_cfg.get() with defaults; api_enabled | ✓ No crash on missing config |
| **File-understanding** | ✓ request.files; data-URL → temp; process_files; add_to_kb | ✓ try/except; _safe_list; empty result fallback | ✓ Never crash on bad file or missing lib |
| **system_plugins/homeclaw-browser** | ✓ WebChat, browser, canvas, nodes; session per user | ✓ Errors as success: false; Core handles non-2xx | ✓ Plugin never throws to Core |
| **main_llm_language (list)** | ✓ First = primary; full list = allowed languages | ✓ Normalize str/list/None → non-empty list; call sites use Util() | ✓ Backward compat; to_yaml writes list |
| **route_to_plugin + browser** | ✓ Fallback message when result None; URL infer from user_input | ✓ try/except on fallback send; params plain object in run-handler | ✓ FileReader.onerror in control-ui |

All changes have been reviewed for correct behavior, safe access patterns, and defensive handling of bad or missing data.

---

## 5. Session-Related Behavior

**Design:** Session config and APIs support **dm_scope** (main / per-peer / per-channel-peer / per-account-channel-peer), session listing for plugin UIs, and **per-session response delivery** (e.g. cron `delivery_target='session'`).

### 5.1 Config and APIs

- **Config** (`config/core.yml` → `session`): `dm_scope`, `prune_keep_n`, `prune_after_turn`, `daily_reset_hour`, `idle_minutes`, `api_enabled`, `sessions_list_limit`. Core reads via `getattr(Util().get_core_metadata(), "session", None) or {}` with safe `.get()` for each key.
- **get_session_id** (`core/core.py`): Uses `_resolve_session_key(app_id, user_name, user_id, channel_name, account_id)` when `dm_scope` is one of main / per-peer / per-channel-peer / per-account-channel-peer; otherwise falls back to chatDB session lookup. Returns a stable session identifier for chat history and for response routing.
- **_persist_last_channel:** Persists both **default** key (latest channel) and **per-session** key `app_id:user_id:session_id` so cron can deliver to a specific session via `send_response_to_channel_by_key(session_key)`.
- **GET /api/sessions:** Lists sessions (app_id, user_name, user_id, session_id, created_at) for plugin UIs. Requires `session.api_enabled` (default true); uses `sessions_list_limit` (capped 1–500).
- **GET /ui:** Launcher page shows sessions table when session API is enabled; data from `get_sessions()`.

**Logic:** Session key drives where responses go (default vs per-session); dm_scope drives how session_id is derived (one DM vs per peer/channel/account). Cron can target a session by key.

**Stability:** All session config access uses `.get()` with defaults; `session_cfg.get("api_enabled", True)`; no crash on missing or invalid config.

---

## 6. File-Understanding

**Design:** [FileUnderstandingDesign.md](FileUnderstandingDesign.md). Core runs file-understanding on **request.files** (paths or data URLs); also exposed as tool **file_understand(path)**.

### 6.1 Core integration (process_text_message)

- **request.files:** Read via `getattr(request, "files", None) or []`; non-list normalized to `[]`.
- **Data-URL resolution:** Each entry that starts with `data:` is decoded (base64), written to a temp file (suffix from content-type: .pdf, .jpg, .m4a, .mp4, .bin), and the temp path is used for `process_files`. Decode failure is logged; that entry is skipped or left as-is so processing continues.
- **process_files:** Called with resolved paths, `supported_media`, `base_dir`, `max_chars`. Result: `images`, `audios`, `videos`, `document_texts`, `document_paths`, `errors`. All steps (config load, path resolve, process_files, result merge, add_to_kb) are inside try/except; on any exception we log and continue without file-derived content. **Defensive:** `_safe_list()` for every result attribute; empty result fallback object if `process_files` returns None so we never crash on extend/iterate.
- **Documents:** Short notice with paths is injected; model uses **document_read** / **knowledge_base_add**. When user sent file(s) only and doc size ≤ `file_understanding.add_to_kb_max_chars`, we add to user KB directly. add_to_kb is wrapped in try/except and timeout; failures are logged.

**Logic:** Files from channels (including /inbound data URLs) are resolved to paths → classified → merged into message or document notice; tool flow and add-to-KB match the design doc.

**Stability:** No step in file-understanding can crash Core; config and int parsing guarded; result attributes accessed via _safe_list; errors logged and processing continues.

---

## 7. system_plugins/homeclaw-browser

**Design:** [homeclaw-browser/README.md](../system_plugins/homeclaw-browser/README.md), [BrowserCanvasNodesPluginDesign.md](BrowserCanvasNodesPluginDesign.md). Single Node.js **system plugin** providing Control UI (WebChat + WebSocket proxy), browser automation (Playwright), canvas, and nodes.

### 7.1 What it provides

- **Control UI:** GET `/`, WebSocket `/ws` (proxy to Core `/ws`). WebChat and chat proxy; CORE_URL and CORE_API_KEY (if auth) configured when starting the server.
- **Browser:** Capabilities `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill`, `browser_scroll`, `browser_close_session`, and browser settings (color scheme, geolocation, timezone, locale, device, offline, headers, credentials). One Playwright context per user/session so multi-turn flows use the same page.
- **Canvas:** GET `/canvas`, capability `canvas_update`; agent pushes UI (title, blocks) to the canvas viewer by session.
- **Nodes:** GET `/nodes`, capabilities `node_list`, `node_command`; devices connect via `/nodes-ws`; plugin forwards commands and returns results. Unsupported or failed commands return `success: false`, `error: "<message>"`; plugin does not throw to Core.

### 7.2 Integration with Core

- **Registration:** `node register.js` POSTs to Core `/api/plugins/register` with capabilities and `ui` (webchat, control, dashboard, tui, custom). Core GET `/ui` shows WebChat, Canvas, Nodes links.
- **Auto-start:** When `system_plugins_auto_start: true` in core.yml, Core starts plugins in `system_plugins/` (optional allowlist `system_plugins: [homeclaw-browser]`) and runs `node register.js` after Core is ready.
- **Browser vs Core tools:** Set `tools.browser_enabled: false` in core.yml to use this plugin for all browser actions via `route_to_plugin(plugin_id="homeclaw-browser", ...)`.

**Logic:** One plugin serves WebChat, browser, canvas, and nodes; session scoping is per user/session for browser and canvas; Core treats plugin as external HTTP plugin.

**Stability:** Plugin returns errors as `success: false` in body or non-2xx; Core handles both without crashing and passes messages to the agent/user. README states errors are caught and returned; plugin never throws to Core.

### 7.3 main_llm_language as list (stability review)

- **CoreMetadata** (`base/base.py`): `main_llm_language` is `List[str]`. `_normalize_main_llm_language(raw)` accepts `str`, `List[str]`, or `None`; returns non-empty list (default `["en"]`). `from_yaml` uses it; `to_yaml` writes the list as-is.
- **Util** (`base/util.py`): `main_llm_language()` returns primary (first element) for prompt file loading; handles not-list or empty as `"en"`. `main_llm_languages()` returns full list; `_normalize_language_list(language)` used in `set_mainllm` so stored value is always a list.
- **Call sites** (`core/core.py`, `core/tam.py`, `core/orchestrator.py`): All use `Util().main_llm_language()` instead of `getattr(meta, "main_llm_language", "en")`, so they get a string (primary language) and remain correct.
- **Config** (`config/core.yml`): `main_llm_language: [en]` with comments on how to set (list) and meaning (first = primary; full list = allowed response languages).

**Stability:** Old YAML with `main_llm_language: en` is normalized to `["en"]`; no crash on None or empty list; prompt loading and routing unchanged.

### 7.4 Browser “open URL” and route_to_plugin robustness

- **Issue:** User asks to “open https://www.baidu.com in browser”; response was “Handled by routing (TAM or plugin).” with nothing else. Causes: (1) LLM sometimes calls `route_to_plugin(plugin_id="homeclaw-browser")` without `capability_id` or `parameters`, so plugin received empty capability and returned “Unknown capability”; (2) when plugin (inline) returned `None`, Core returned `ROUTING_RESPONSE_ALREADY_SENT` without sending any message to the user.
- **Fixes:**
  1. **tools/builtin.py** (`_route_to_plugin_executor`): When `result_text is None`, send fallback message “The action was completed.” to the channel, then return `ROUTING_RESPONSE_ALREADY_SENT`. User always gets some feedback.
  2. **system_plugins/homeclaw-browser/run-handler.js**: When `capability_id` is empty, infer “open URL” from `user_input`: extract first URL with a simple regex; if found, treat as `browser_navigate` with that URL. So “open https://www.baidu.com” works even when the LLM does not pass `capability_id` or `parameters`. Improved “Unknown capability” error message when capability is missing to suggest passing `capability_id` (e.g. browser_navigate) or including a URL in the message.

**Logic:** Plugin can still be called with explicit `capability_id` and `parameters`; when omitted, browser plugin infers navigate from user text. Core never returns “Handled by routing” without having sent at least one message to the channel.

**Robustness (additional):**
- **tools/builtin.py:** When sending the fallback message (“The action was completed.”), wrap `send_response_to_request_channel` in try/except; on failure log and still return `ROUTING_RESPONSE_ALREADY_SENT` so the tool does not surface a raw exception.
- **run-handler.js:** `params` is normalized so it is always a plain object: if `body.capability_parameters` is missing, null, or not a non-array object, use `{}`. Avoids spread/access errors when a client sends invalid capability_parameters.

### 7.5 Control UI WebChat file picker (same as channels/webchat)

- **control-ui/index.html:** File input added (`type="file"`, `multiple`, `accept="image/*,video/*,audio/*,*/*"`). Send logic matches channels/webchat: payload has `user_id`, `text` (or `"(no text)"` when only files), and optionally `images`, `videos`, `audios`, `files` as data URLs. `mediaKind(type)` classifies by MIME. User can send text only, files only, or both.
- **Robustness:** `FileReader.onerror` is set so that if a file fails to read (e.g. permission, too large), the handler still increments `done` and calls `onAllRead()` when all files are processed; the payload is sent with whatever was read successfully, so the UI does not hang. `filesEl && filesEl.files` guarded before use.
