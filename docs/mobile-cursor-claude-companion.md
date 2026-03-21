# Mobile Companion ↔ Cursor CLI & Claude Code — Investigation & Best Practices

How the **Companion app** (phone) uses **Cursor** and **Claude Code** through **HomeClaw Core** and the **Cursor Bridge**, and how to get the best experience on mobile.

---

## 1. End-to-end path (what actually runs where)

| Layer | Runs on | Role |
|--------|---------|------|
| **Companion app** | Phone | UI, auth, `POST /inbound` (often **`async: true`** → 202 + poll), optional flash toggles |
| **Core** | Your server (LAN/VPS) | Routes **Cursor** / **ClaudeCode** / **Trae** friends to pattern routing (`llm_loop.py`) → `route_to_plugin` → HTTP to bridge |
| **Cursor Bridge** | **Dev machine** (where Cursor / Claude CLI live) | `run_agent`, `get_status`, session store in `~/.homeclaw/cursor_bridge_state.json` |
| **CLIs** | Same machine as bridge | `agent … -p` (Cursor), `claude … -p` (Claude Code) |

**Critical for mobile users:** All **paths** in messages like “open project `/Users/me/repo`” refer to the **bridge machine’s filesystem**, not the phone. The phone does not mount the repo unless you use some sync path the bridge understands.

---

## 2. What the Companion app already does well (codebase)

From `clients/HomeClawApp/lib/core_service.dart` and `chat_screen.dart`:

1. **Async mode for bridge friends**  
   For `friendId` **`cursor`**, **`claudecode`**, or **`trae`**, the app sends **`async: true`** (and also when Core URL is “remote”). That avoids holding a single HTTP connection for many minutes — important on **cellular** and behind **reverse proxies** (502 if idle timeout kills the connection).

2. **Permission / auto-run toggles**  
   - **Cursor:** `cursor_agent_yolo` → bridge passes **`--yolo`** (same as `--force`) for that message.  
   - **Claude Code:** `claude_skip_permissions` → **`--dangerously-skip-permissions`**.

3. **Friend-specific plugin IDs**  
   Cursor → `cursor-bridge`, ClaudeCode → `claude-code-bridge` (see `chat_screen.dart`).

4. **Bridge status**  
   `getCursorBridgeStatus()` / `getCursorBridgeActiveCwd()` call **`GET /api/cursor-bridge/status`**. The API returns **`active_cwd`** plus **`cursor_stored_session_active`**, **`claude_stored_session_active`**, and optional session counts. The chat app bar shows a small **“session linked”** chip for Cursor / Claude Code when the stored session flag is true for that friend.

5. **Live preview while polling (Cursor)**  
   With **`async: true`**, the app sends **`bridge_agent_stream_preview: true`**. Core streams Cursor Bridge **`stream-json`** (NDJSON) into the pending inbound entry; **`GET /inbound/result`** may include **`text_preview`** so the loading line updates during long **`run_agent`** tasks. Claude Code / Trae still resolve to a single final result (no CLI stream on the phone for those yet).

6. **Session continuation (server-side)**  
   When enabled in config, the bridge persists **`session_id` per project** and uses **`--resume`** / **`--continue`** for Cursor and Claude (see `docs/cursor-claude-code-bridge.md`). Companion does not need extra fields for that — it’s automatic per **active cwd** on the bridge.

---

## 3. Official CLI capabilities relevant to mobile UX

### Cursor Agent CLI

- **Docs:** [Headless](https://cursor.com/docs/cli/headless), [Parameters](https://cursor.com/docs/cli/reference/parameters), [Output format](https://cursor.com/docs/cli/reference/output-format).
- **Print mode:** `-p` / `--print` with **`--trust`** for non-interactive workspace trust.
- **Sessions:** `--continue`, `--resume <chatId>`; JSON success includes **`session_id`** (already used by the bridge).
- **Output:** `text` | `json` | `stream-json`; the bridge uses **`json`** for the non-streaming **`POST /run`** path, and **`stream-json` + `--stream-partial-output`** when Core requests **`metadata.stream_agent`** (NDJSON to Core → **`text_preview`** on poll).
- **Long tasks:** Async poll still drives completion; **`text_preview`** can update the UI while the agent runs (Cursor only, when CLI supports stream mode).

### Claude Code CLI

- **Docs:** [Headless / programmatic](https://code.claude.com/docs/en/headless).
- **Sessions:** `--continue`, `--resume <id>` with `-p`; bridge mirrors Cursor-style persistence in state file.
- **Permissions:** `--dangerously-skip-permissions` when Companion flash is on (or explicit param).

---

## 4. Gaps & how to use the stack better from a phone

### A. Mental model & prompts

- **Always think “my dev machine”:** e.g. “Open project `D:\work\MyApp` in Cursor” is a path on the **PC running the bridge**.
- **Short follow-ups:** With session continuation enabled, you can send “now add tests” without repeating the whole spec — the CLI thread is tied to **project cwd** on the bridge.
- **New thread:** Say **“clear cursor session”** / **“new claude session”** (pattern-routed) or use **`clear_*_session`** from tools if exposed.

### B. Network & security

- **Reachability:** Phone must reach **Core**; Core must reach **bridge** `base_url` (often `http://127.0.0.1:3104` only works if Core and bridge are the **same host**). For phone → home PC, typical patterns: **Tailscale**, VPN, or SSH tunnel; adjust plugin `base_url` / firewall.
- **`CURSOR_BRIDGE_API_KEY`:** If the bridge is exposed beyond localhost, set the shared secret and ensure Core sends **`X-HomeClaw-Bridge-Key`** (see bridge README).
- **Flash toggles on mobile:** Full auto-run is powerful; treat the phone like a **remote control for a trusted dev box**.

### C. Companion app enhancements (not all implemented)

| Idea | Benefit |
|------|--------|
| **Show “active project” + optional session hint** | Implemented: status flags drive a **session linked** chip; full JSON still available via **`getCursorBridgeStatus()`**. |
| **Markdown / code blocks** | Chat uses **`flutter_markdown`**; **plain text** is a **settings toggle** for copy-friendly rendering on dev-bridge friends — not “no Markdown”. |
| **Progress text** | **Cursor `run_agent`:** bridge **`stream-json`** → Core **`text_preview`** on **`/inbound/result`** poll. Claude/Trae: final result only until a similar stream exists. |
| **Cancel** | Hard without process groups / bridge API to kill a running `agent`/`claude` child — product expectation should be “long run may take minutes”. |
| **Attachments** | Photos on the phone are not automatically paths on the bridge; today’s flow is **text-first**. Improving this needs a defined story (e.g. upload to Core, path visible to bridge, or paste image description from an LLM on Core first). |

### D. Reliability

- **Proxy timeouts:** Async + poll is the right pattern; ensure any **reverse proxy** in front of Core allows long enough timeouts for **`/inbound/result`** polling (see `docs/cursor-claude-code-bridge.md` Trae note — same idea).
- **Plugin HTTP timeout:** `plugins/*/plugin.yaml` **`timeout_sec`** (e.g. 1800) should stay **≥** worst-case CLI run.

---

## 5. Quick checklist for “mobile + Cursor/Claude”

1. Bridge running on dev PC; **`agent` / `claude`** on PATH or configured paths in `skills_and_plugins.yml`.
2. Core can **HTTP POST** the bridge URL (not only localhost if Core is elsewhere).
3. Companion **`friendId`** = **`cursor`** or **`claudecode`** for the right preset.
4. **`cursor_bridge_cursor_continue_session`** / **`cursor_bridge_claude_continue_session`** as desired (default on for sticky threads).
5. Optional: **Tailscale** (or similar) + **`CURSOR_BRIDGE_API_KEY`** if crossing untrusted networks.

---

## 6. Related docs

- `docs/cursor-claude-code-bridge.md` — capabilities, session continuation, config keys.
- `external_plugins/cursor_bridge/README.md` — env vars, auto-start, Claude/Cursor flags.
- `docs_design/CompanionAppFAQ.md` — Companion limitations (Markdown, location, combine user).

This document is **investigation + product guidance**; implement API/UI changes in Core and `clients/HomeClawApp` as you prioritize them.
