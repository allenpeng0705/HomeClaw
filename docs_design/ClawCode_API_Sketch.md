# Claw-Code API sketch (P0)

Companion to `docs_design/ClawCode_Design.md`. JSON shapes are stable targets for implementation; adjust with version notes if needed.

## Feature gate

- Config: `clawcode.enabled: true` in merged `core.yml` (see `config/core.yml.reference`).
- When **disabled**, `POST/GET /api/clawcode/*` return **404** (not advertised).
- Inbound: `clawcode_session_id` is **ignored** unless `clawcode.enabled` is true (normal chat path).

## Auth

Same as `/inbound`: when `auth_enabled` + `auth_api_key` are set, require `X-API-Key` or `Authorization: Bearer <key>`.

## `POST /api/clawcode/sessions`

Creates a coding session bound to one **`cwd`** and an **`owner_user_id`** (must match `user_id` on later `POST /inbound` turns for that session).

**Request body (JSON):**

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `owner_user_id` | string | yes | Same identifier as inbound `user_id` (e.g. Companion id, CLI user). |
| `cwd` | string | yes | Absolute working directory; validated against `clawcode.allowed_roots` when set. |

**Response 201:** full session record (stored under `database/clawcode_sessions/<id>.json`), including:

| Field | Notes |
|-------|--------|
| `mode` | `plan` or `agent`; default from `clawcode.default_session_mode` in merged config, else **`agent`**. |
| `main_llm_ref`, `tool_llm_ref` | Empty strings until patched; when set to a **valid** ref in `llm.yml`, Core uses them for that session’s main model and tool-selection model (invalid refs are ignored). |
| `git_remote_hint` | Operator note; empty until patched. |
| `task_plan` | JSON array of `{ id, title, status }` (`pending` \| `running` \| `done` \| `blocked`); injected into system prompt for agent continuity (milestones A–B). |
| `checkpoint`, `resume_hint`, `last_run_error` | Optional operator strings; `last_run_error` cleared when a turn completes successfully via `record_clawcode_turn_finished`. |

```json
{
  "clawcode_session_id": "<uuid>",
  "owner_user_id": "...",
  "cwd": "...",
  "status": "idle",
  "mode": "agent",
  "git_remote_hint": "",
  "last_run_id": "",
  "main_llm_ref": "",
  "tool_llm_ref": "",
  "created_at": 1710000000.0,
  "updated_at": 1710000000.0
}
```

**Errors:** `400` validation, `403` cwd not allowed, `404` feature disabled.

## `GET /api/clawcode/sessions`

Lists sessions for one owner.

**Query:** `owner_user_id` (required for MVP).

**Response 200:**

```json
{
  "sessions": [ { ... same fields as create ... } ]
}
```

## `GET /api/clawcode/sessions/{id}`

**Query:** `owner_user_id` (required).

**Response 200:** session record plus `worktree_hint` and `usage_hint` when Claw-Code is enabled.

**Errors:** `403` wrong owner, `404` session not found or feature disabled.

## `PATCH /api/clawcode/sessions/{id}`

**Query:** `owner_user_id` (required; must match the session’s `owner_user_id`).

**Body (JSON):** include at least one of:

| Field | Type | Notes |
|-------|------|--------|
| `git_remote_hint` | string | Operator note (e.g. default remote/branch). |
| `main_llm_ref` | string | Main chat model ref; must resolve in merged `llm.yml` and be **available** or Core ignores it. |
| `tool_llm_ref` | string | Tool-calling / selection model ref; same validation as `main_llm_ref`. |
| `mode` | string | `plan` (read-biased tool policy) or `agent` (normal `tool_policy` for Claw-Code turns). |
| `task_plan` | array | See create response; max ~50 steps normalized server-side. |
| `checkpoint` | string | Short operator checkpoint text. |
| `resume_hint` | string | What to do next after failure or interruption. |
| `last_run_error` | string | Operator-visible error; Web UI may PATCH on failed inbound. |

`cwd`, `owner_user_id`, and `clawcode_session_id` are **not** patchable via this endpoint (use **rebind** for `cwd`).

## `GET /api/clawcode/mcp/servers`

Returns sanitized entries from merged `tools.mcp.servers` (id, transport, command preview, args preview, whether URL is set). **Milestone C.**

## `POST /api/clawcode/mcp/health`

Body optional: `{ "server_ids": ["id1", …] }` — if omitted, probes each configured server. Runs `list_tools` per server (may spawn subprocesses). Returns `{ "results": [ { "server_id", "ok", "tool_count" or "error" } ] }`.

## `POST /api/clawcode/sessions/{id}/rebind`

**Query:** `owner_user_id` (required).

**Body (JSON):** `{ "cwd": "<absolute path>" }` — same validation as create (`directory exists`, `clawcode.allowed_roots`).

**Response 200:** updated session (same shape as GET). **Errors:** `400`/`403`/`404` analogous to create/patch.

## Path preflight (Claw-Code tool turns)

For session-bound turns, tools that take an **absolute** `path` must resolve **under** the session `cwd` (after normalization). Violations fail the tool call before execution (workflow trace may record the rejection).

**Response 200:** updated session (same enrichment as GET detail: `worktree_hint`, `usage_hint`). Workflow trace may emit `clawcode_session_patched` when tracing is on.

**Errors:** `400` if no allowed fields are present, `403` wrong owner, `404` not found / feature off.

## `POST /inbound` (extensions)

Optional fields on existing `InboundRequest`:

| Field | Type | Notes |
|-------|------|--------|
| `clawcode_session_id` | string | When `clawcode.enabled`, must reference an existing session; `user_id` must match session `owner_user_id`. |
| `tool_profile` | string | Optional; if omitted and session is present, Core may set `default_tool_profile` from `clawcode` config (default `coding`). Use **`coding`** or **`clawcode`** (same tool set). |

**Flow:** Core copies `clawcode_session_id` into `PromptRequest.request_metadata`, validates session, injects **Claw-Code session** block (mode, secrets reminder) + optional **`config/clawcode.yml`** `system_prompt_addendum`, emits workflow trace `clawcode_turn_started` when trace is enabled.

**Git via `exec`:** If `clawcode.git_write_allowed` is **explicitly `false`**, mutating git commands (`git commit`, `git push`, etc.) are blocked in `exec` for Claw-Code turns. If the key is **omitted**, behavior stays backward-compatible (**writes allowed**).

## Workflow trace `event_type` (additive)

- `clawcode_session_started` — session created (details: `clawcode_session_id`, `owner_user_id`, `cwd`).
- `clawcode_session_patched` — operator metadata updated (details: `clawcode_session_id`, `owner_user_id`, `keys`).
- `clawcode_turn_started` — inbound turn bound to a session (details: `clawcode_session_id`, `user_id`).

## CLI (`python3 -m main clawcode …`)

Config file: **`~/.config/homeclaw/clawcode.json`** (`core_base_url`, `api_key`, `owner_user_id`, optional `default_clawcode_session_id`).

| Command | Action |
|---------|--------|
| `clawcode login [--url URL] [--key KEY] [--owner ID]` | Save URL (defaults from project `core.yml` host/port if `--url` omitted), API key, owner id. |
| `clawcode session new [--cwd DIR] [--owner ID]` | `POST /api/clawcode/sessions`; stores returned id as default session. |
| `clawcode session list [--owner ID]` | `GET /api/clawcode/sessions?owner_user_id=…` |
| `clawcode session set-meta [-s ID] [--git-remote-hint …] [--main-llm-ref …] [--tool-llm-ref …] [--mode plan or agent]` | `PATCH /api/clawcode/sessions/{id}` (at least one flag required). |
| `clawcode session rebind [-s ID] --cwd DIR` | `POST /api/clawcode/sessions/{id}/rebind` with new cwd. |
| `clawcode run [-s SESSION] [--stream] MESSAGE...` | `POST /inbound` with `clawcode_session_id` (default session from config if `-s` omitted). |
| `clawcode attach` | `GET /dev/workflow-trace/stream` (SSE lines; needs `workflow_trace_sse_enabled` on Core). |

Override API key with env **`HOMECLAW_API_KEY`** when set.

## Channel bindings (P5)

- **`GET/PUT/DELETE /api/clawcode/channel-bindings`** maps **owner_user_id** (Core user id) → **clawcode_session_id**. Core merges this on **POST /inbound** (and **`/process`** where supported) when `clawcode_session_id` is omitted, after resolving the effective user id from channel permissions.
- Channel adapters can merge the same mapping via **`channels/clawcode_binding.py`** using channel-local `user_id` (see Telegram/Discord/WebChat patterns).

### Channel parity (who merges Claw-Code bindings / commands)

| Channel | Mechanism |
|---------|-----------|
| Telegram, Discord, Slack | `merge_clawcode_binding_into_inbound_payload` + `try_clawcode_command_reply` |
| Matrix, Line, WhatsApp | `merge_clawcode_binding_into_prompt_request` + `try_clawcode_command_reply` |
| DingTalk, Feishu, Google Chat, Teams, WhatsApp Web, Webhook, Zalo, BlueBubbles, iMessage, Signal | `apply_clawcode_inbound_flow` |
| **WeChat (wcferry)** | same as Matrix-style: `try_clawcode_command_reply` + `merge_clawcode_binding_into_prompt_request` on `PromptRequest` |
| **WebChat** | Proxies `/api/clawcode/*` and `/clawcode` UI; client sends `clawcode_session_id` in JSON when needed (no duplicate merge in `channel.py`). |

## OpenAPI

Machine-readable fragment: **`docs/openapi/clawcode.yaml`** (merge into a parent spec or use as reference).

## MCP / desktop integrations

See **`docs/clawcode-mcp-integration.md`** (`clawcode.mcp_preset_note`, `clawcode.mcp_tool_allowlist`, optional future stdio bridge).

## Future / follow-ups

- Optional **SQLite** migration for session rows (today: one JSON file per session under `database/clawcode_sessions/`).
- First-party **stdio MCP** bridge for IDE-style local servers (see MCP doc).
