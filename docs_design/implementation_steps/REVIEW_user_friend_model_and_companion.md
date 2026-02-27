# Review: User/Friend model, Core stability, cross-platform, Companion, prompts

This document summarizes the review of all changes and docs for: (1) logic correctness, (2) stability and robustness (never crash Core), (3) cross-platform (Mac, Windows, Linux), (4) Companion app connection/communication with Core, (5) prompts for user/friend model and folder structure.

**Scope:** Steps 1–15 (user.yml friends/identity, request context, memory paths, profile, sandbox, friend identity, chat/sessions/TAM/push, channels→HomeClaw, Companion login/me/friends, scoped endpoints, file tools/path resolution, docs).

---

## 1. Logic correctness (100%)

### 1.1 User and friend identity

- **user.yml:** `id`, `name`, optional `username`/`password`, `friends` list (HomeClaw first). Parsing and default `[HomeClaw]` are correct. Validation (no duplicate email/im/phone) unchanged.
- **Request context:** `system_user_id` from permission check; `friend_id` from request or default "HomeClaw". Channels always get `friend_id = "HomeClaw"`. Inbound accepts `friend_id` in body; default "HomeClaw". All storage (chat, sessions, memory, TAM one-shot, last channel, file paths) keys by (user_id, friend_id) where applicable. ✓

### 1.2 Data scoping

- **Chat/sessions:** DB and API filter by (user_id, friend_id). Reset and list endpoints use the same scope. ✓
- **Memory (RAG):** Namespace/key by (system_user_id, friend_id) where implemented. ✓
- **AGENT_MEMORY / daily:** Paths `memories/{user_id}/{friend_id}/...`. Clear and load use the same paths. ✓
- **TAM one-shot:** Stored and delivered with user_id and friend_id; push includes `from_friend`. ✓
- **Last channel:** Keyed by system_user_id so delivery goes to the right user. ✓
- **File sandbox:** `homeclaw_root/{user_id}/`; relative paths like `{friend_id}/output/`, `{friend_id}/knowledge/` under that root. Path traversal rejected (full under base). ✓

### 1.3 Companion–Core

- **POST /inbound:** Body may include `user_id`, `app_id`, `friend_id`. Core uses them for permission, session, and storage. Missing `friend_id` → "HomeClaw". ✓
- **Companion sendMessage:** Now accepts optional `friendId` and sends it as `friend_id` when provided. Chat screen can pass it when per-friend chat is implemented; until then all traffic is (user_id, HomeClaw). ✓
- **WebSocket:** Register sends `user_id`; Core maps session→user for push. Push payload includes `from_friend`. ✓
- **Auth:** Step 12 login returns token; `/api/me` and `/api/me/friends` require Bearer token. Companion can use API key (getConfigUsers) or later token (me/friends) for different flows. ✓

---

## 2. Stability and robustness (never crash Core)

### 2.1 Core routes and dependencies

- **companion_auth:** JSON and user lookup in try/except; token cleanup and user resolution guarded; 401/500 with safe messages. ✓
- **memory_routes:** `_memory_reset_user_friend` uses `_safe_str_strip` for query/body; all clear steps in try/except. ✓
- **misc_api (sessions):** get_core_metadata and session_cfg in try/except; limit parsing with fallback 100; get_sessions in try/except → []. ✓
- **core.py:** Assignments to request.user_name, system_user_id, friend_id in try/except; _persist_last_channel in try/except. ✓
- **ChatHistory.reset:** Normalization and deletes in try/except; never raises. ✓

### 2.2 Path and file handling

- **workspace:** `_sanitize_friend_id` and `_sanitize_identity_filename` replace invalid path chars; all path builders use Path and resolve(); try/except where needed. ✓
- **builtin _resolve_file_path:** Path traversal check (full.relative_to(base)); ValueError → None. Normalize backslash to slash for comparison. ✓
- **TAM / memory:** Per-row and per-call try/except; skip bad rows or return safe defaults. ✓

### 2.3 Base and tools

- **User.from_yaml / _parse_friends:** Invalid entries skipped; default friends [HomeClaw]. ✓
- **Tool context:** getattr(..., None) for system_user_id, friend_id; str().strip() with fallbacks. ✓

---

## 3. Cross-platform (Mac, Windows, Linux)

### 3.1 Paths

- **pathlib.Path:** Used for all Core and workspace path construction and resolve(). Path separators are OS-specific; joining with `/` is supported on Windows in Python 3. ✓
- **Normalization:** In file tools, `path_arg.replace("\\", "/")` before logic so "share" and subpaths work the same on Windows. ✓
- **Sanitization:** `_sanitize_friend_id` and identity filename strip `/\:*?"<>|` (Windows-invalid); safe on all platforms. ✓

### 3.2 Case and encoding

- **Share path:** Comparison uses `.strip().lower()` so "Share" and "share" behave the same across case-sensitive filesystems. ✓
- **No assumption** of case-sensitive or case-insensitive FS; path resolution is consistent. ✓

### 3.3 Companion (Flutter)

- **Path package:** Uses `path` and `path_provider`; platform-agnostic. ✓
- **HTTP/WebSocket:** Same on all platforms. ✓
- **Push:** iOS/macOS (APNs) vs Android (FCM) vs Windows/Linux (no-op) handled in code. ✓

---

## 4. Companion app – connection and communication

### 4.1 Connection

- **Base URL:** Configurable; trailing slash stripped. ✓
- **Auth:** X-API-Key and Authorization: Bearer (API key). Step 12 token auth is for /api/me and /api/me/friends; /inbound and config endpoints use API key. ✓
- **Timeouts:** sendMessage 600s; checkConnection 5s; config/upload timeouts set. ✓
- **Remote Core:** async: true to avoid proxy timeouts; polling GET /inbound/result; WebSocket for push. ✓

### 4.2 Messaging

- **POST /inbound:** Sends user_id, text, channel_name, optional app_id, **friend_id** (when provided), location, media. Core sets system_user_id from user allowlist and friend_id from body or "HomeClaw". ✓
- **WebSocket:** Connect to /ws; register with user_id; receive push and inbound_result. Push includes from_friend (for future per-friend routing). ✓
- **Streaming:** stream: true with SSE when local Core and onProgress set. ✓

### 4.3 Data flow

- **Current UI:** Friend list screen uses getConfigUsers() (full user list, API key). One chat per user; no friend_id sent → Core uses HomeClaw. ✓
- **Optional flow:** Login (username/password) → token → /api/me, /api/me/friends → show friends → sendMessage(userId, friendId: selectedFriend). Core already supports friend_id in body. ✓
- **Push:** Core sends from_friend in push payload; Companion forwards it in pushMessageStream so UI can later route notifications by friend. ✓

### 4.4 Changes made in this review

- **core_service.dart:** sendMessage now has optional `friendId` and sends `friend_id` in the body when non-empty. Chat screen does not pass it yet (default remains HomeClaw); when per-friend chat is added, pass the selected friend's id.
- **core_service.dart:** Push messages from Core now include `from_friend` in the map added to pushMessageStream (when Core sends it), so UI can route reminders/notifications to the correct friend chat. ✓

---

## 5. Prompts (user/friend model and folder structure)

### 5.1 Tool descriptions (builtin.py)

- **file_read, document_read, file_understand, file_write:** Describe user sandbox (downloads/, documents/, output/, work/, share/, knowledgebase/) and per-friend paths ({FriendName}/output/, {FriendName}/knowledge/). Share = global share. ✓
- **Path parameter:** "Relative path under user sandbox"; "Use 'share/...' for global share"; friend paths documented. ✓

### 5.2 TAM and other config prompts

- **config/prompts/tam/scheduling.en.yml:** Time parsing only; no path or user/friend semantics. ✓
- **Orchestrator / process_text_message:** System prompt and tool context inject user_name, system_user_id, friend_id via ToolContext; friend identity file loaded for the current friend and injected. ✓

### 5.3 Folder semantics

- **FolderSemanticsAndInference.md:** Describes user root, friend output/knowledge, share, default path. ✓
- **Tool behavior:** Empty path → user root; "share" → global share; "{friend}/output/" etc. resolved under user sandbox. Descriptions match. ✓

---

## 6. Summary table

| Area | Status | Notes |
|------|--------|--------|
| **Logic** | ✓ | user/friend scoping, defaults, storage, and APIs consistent. |
| **Robustness** | ✓ | try/except, safe parsing, path traversal rejected; Core does not crash on bad input. |
| **Cross-platform** | ✓ | pathlib, backslash normalization, sanitization; Companion platform checks. |
| **Companion–Core** | ✓ | /inbound, /ws, auth, push; friend_id in body supported; sendMessage accepts friendId. |
| **Prompts** | ✓ | Tool descriptions and folder semantics align with user/friend model and paths. |

---

## 7. Optional follow-ups (not bugs)

- **Companion:** Add login screen and use /api/me, /api/me/friends with token; show friends and pass friendId in sendMessage for per-friend chats.
- **Companion:** Use from_friend in push payload to route notifications to the correct friend chat when multiple chats are open.
- **KB reset:** Scoped by (user_id, friend_id) deferred; current route is full reset.
- **WebSocket register:** Core could persist friend_id per session if Companion sends it on register for push routing.

All reviewed logic is correct, stable, and cross-platform; Companion communication is correct and extended with friend_id support.
