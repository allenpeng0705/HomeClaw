# Claw-Code dogfood checklist

Use this to verify Core, WebChat (`/clawcode`), Companion, and CLI work together on a trusted network.

## Prerequisites

1. **Core** runs with `clawcode.enabled: true` in `config/core.yml`.
2. **WebChat** channel runs (default port **8014**); `channels/.env` has `CORE_URL` pointing at Core (**9000**) and an API key if `auth_enabled` is on.
3. **Companion** is logged in with the same **Core user id** as the Claw-Code session `owner_user_id` and the same **API key** (Settings) when Core requires auth.
4. Optional: set **`clawcode_web_ui_url`** in Companion to your WebChat Claw-Code page (e.g. `https://host:8014/clawcode`) so “Open in browser” works from the phone.
5. **Push (approval notifications):** In `config/core.yml`, set **`push_notifications.enabled: true`** and configure FCM (Android) and/or APNs (Apple) per project docs. The Companion must register its device token with Core (opens after login). If push is misconfigured, approvals still work via the Claw-Code screen and API; Core logs *push reached 0 devices* when no token was reached.

## Config extras (optional)

- **`clawcode.mcp_preset_note`**: Free-form text listing MCP `server_id` keys (from `tools.mcp.servers`) and how agents should use them. Appended to the system prompt for Claw-Code turns.
- **`clawcode.mcp_tool_allowlist`**: When non-empty, only `server_id/tool_name` pairs in the list are callable via `mcp_call` during Claw-Code turns; `mcp_list_tools` is filtered accordingly.
- **P5 channel binding:** `PUT /api/clawcode/channel-bindings` with `owner_user_id` = your Core user id (`user.yml` **id** or **name**) and `clawcode_session_id` = UUID. Then Telegram/Discord (and other channels) can omit `clawcode_session_id` on `/inbound` once that IM account maps to the same user in `user.yml` — Core merges the binding after permission check. In-channel `/clawcode bind <uuid>` still binds under the channel’s `user_id` (e.g. `telegram_123`).

## Flow

1. **Create a session** (CLI): `python3 -m main clawcode session new --cwd /path/to/repo` — note `clawcode_session_id` and that `owner_user_id` matches your inbound user.
2. **Optional metadata** (CLI): `python3 -m main clawcode session set-meta --git-remote-hint "origin main"` — calls **`PATCH /api/clawcode/sessions/{id}`** (same auth as other Claw-Code APIs).
3. **Web UI**: Open `/clawcode`, set Core URL, API key, and **user id** = owner. Toggle **Assistant Markdown** if you want rendered replies (requires CDN scripts). Select the session and send a message; confirm replies and optional tool events appear.
4. **Companion**: Open **Claw-Code**; confirm sessions and pending approvals list load; open Web UI if configured. If you opened the app via an approval **push** while logged out, complete **Login** — the pending approval flow should still open **Claw-Code** after friends load.
5. **Approval path**: Trigger a tool that requires approval; confirm **push** (if configured) opens **Claw-Code** with a hint for the pending approval; resolve approve/reject and confirm the agent continues.
6. **Session file**: Under `database/clawcode_sessions/<id>.json`, after a completed turn, check **`last_run_id`**, **`status`**, and **`last_usage`**. If the LLM returns OpenAI-style **`usage`**, totals are summed over tool rounds. If not, Core may still write **`last_usage`** with **`estimated": true`** (character heuristic from the final user + assistant text).

## Troubleshooting

- **403 on inbound** with `clawcode_session_id`: `user_id` on the request must match the session `owner_user_id`.
- **404 on `/api/clawcode/*`**: `clawcode.enabled` is false or Core not restarted.
- **No accurate `last_usage`**: Some local stacks omit `usage` in chat completion responses — check for **`estimated": true`** or use workflow trace (`python3 -m main clawcode attach`) / provider metrics.
- **No push**: See Core logs for *push reached 0 devices*; verify credentials paths, token registration, and that the device platform matches FCM vs APNs routing.

## Reverse proxy

If Core or WebChat sit behind **nginx/Caddy**, see **`docs/clawcode-ui-security.md`** for TLS examples, long timeouts, and WebSocket/SSE notes.
