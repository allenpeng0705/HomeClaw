# Core.py refactor — Phase 5: Extract outbound and session/channel

**Status:** Done  
**Branch:** refactor/core-multi-module (or as created)

## Goal

Move outbound response formatting/delivery and session/channel (last-channel, location, session-id/run-id/get_latest_chats) from `core/core.py` into `core/outbound.py` and `core/session_channel.py`. Core keeps thin wrappers that delegate; all callers (route handlers, inbound_handlers, plugins) still call `core.*` and see unchanged behavior.

## Changes

### 1. New file: core/session_channel.py

- **_persist_last_channel(core, request)**  
  Persist last channel to DB and file; also save per-session key for cron. Calls `get_session_id(core, ...)` from the same module.

- **_latest_location_path(core)**  
  Returns Path to `latest_locations.json` under database dir. Never raises.

- **_normalize_location_to_address(core, location_input)**  
  Converts lat/lng to address via base.geocode; returns (display_location, lat_lng_str).

- **_set_latest_location(core, system_user_id, location_str, lat_lng_str=None)**  
  Writes latest location for user to JSON file.

- **_get_latest_location(core, system_user_id)**  
  Returns latest location string or None.

- **_get_latest_location_entry(core, system_user_id)**  
  Returns full entry dict or None.

- **_resolve_session_key(core, app_id, user_id, channel_name, account_id)**  
  Derives session key from config dm_scope and identity_links.

- **get_session_id(core, app_id, user_name, user_id, channel_name, account_id, friend_id, validity_period)**  
  Resolves or returns session ID (dm_scope-based or from chatDB/cache).

- **get_run_id(core, agent_id, user_name, user_id, validity_period)**  
  Returns run_id from core.run_ids or chatDB.get_runs, else user_id.

- **get_latest_chat_info(core, app_id, user_name, user_id)**  
  Returns (app_id, user_name, user_id) of latest session or (None, None, None).

- **get_latest_chats(core, app_id, user_name, user_id, num_rounds, timestamp)**  
  Returns list of ChatMessage; optional timestamp filter (30 min window).

- **get_latest_chats_by_role(core, sender_name, responder_name, num_rounds, timestamp)**  
  Returns histories by role with optional timestamp filter.

All take `core` as first argument and use `core.chatDB`, `core.session_ids`, `core.run_ids` where needed. No import of core.core.

### 2. New file: core/outbound.py

- **format_outbound_text(core, text)**  
  Applies outbound_markdown_format (whatsapp/plain/none); uses looks_like_markdown and markdown_to_channel.

- **safe_classify_format(core, text)**  
  Returns classify_outbound_format(text) or "plain" on exception.

- **outbound_text_and_format(core, text)**  
  Returns (text_to_send, format) for clients; format is plain|markdown|link.

- **send_response_to_channel_by_key(core, key, response)**  
  Builds resp_data with outbound_text_and_format; uses latestPromptRequest or last_channel_store.get_last_channel(key); puts AsyncResponse on core.response_queue. Handles "homeclaw" app_id (print).

- **send_response_to_latest_channel(core, response)**  
  Calls send_response_to_channel_by_key(core, last_channel_store._DEFAULT_KEY, response).

- **deliver_to_user(core, user_id, text, images, channel_key, source, from_friend)**  
  Pushes to WebSocket sessions for user_id, then push_send (APNs/FCM), then send_response_to_channel_by_key or send_response_to_latest_channel. Same payload and error handling as before.

- **send_response_to_request_channel(core, response, request, image_path, video_path, audio_path)**  
  Builds AsyncResponse with optional media paths and puts on core.response_queue.

- **send_response_for_plugin(core, response, request)**  
  If request is not None, send_response_to_request_channel; else send_response_to_latest_channel.

All take `core` as first argument. No import of core.core.

### 3. core/core.py

- **Imports:**  
  From core.session_channel: _persist_last_channel_fn, _latest_location_path_fn, _normalize_location_to_address_fn, _set_latest_location_fn, _get_latest_location_fn, _get_latest_location_entry_fn, get_run_id as _get_run_id_fn, get_latest_chat_info as _get_latest_chat_info_fn, get_latest_chats as _get_latest_chats_fn, get_latest_chats_by_role as _get_latest_chats_by_role_fn, _resolve_session_key as _resolve_session_key_fn, get_session_id as _get_session_id_fn.  
  From core.outbound: format_outbound_text as _format_outbound_text_fn, safe_classify_format as _safe_classify_format_fn, outbound_text_and_format as _outbound_text_and_format_fn, send_response_to_latest_channel as _send_response_to_latest_channel_fn, send_response_to_channel_by_key as _send_response_to_channel_by_key_fn, deliver_to_user as _deliver_to_user_fn, send_response_to_request_channel as _send_response_to_request_channel_fn, send_response_for_plugin as _send_response_for_plugin_fn.

- **Core methods**  
  Each of the above is replaced with a thin wrapper that calls the corresponding _*_fn(self, ...). Class constant _LATEST_LOCATION_SHARED_KEY = "companion" is kept in Core.

- **Removed:** ~250 lines of inline implementation for session_channel helpers and ~200 lines for outbound helpers (exact counts in diff).

## Logic and stability

- **Correctness:** Behavior unchanged. All logic copied verbatim; `self` replaced with `core` in the new modules. Route handlers, inbound_handlers, cron, plugins still call core._persist_last_channel, core.send_response_to_latest_channel, core.deliver_to_user, core.get_session_id, etc., and receive the same results.
- **Robustness:** Same defensive checks and try/except; no new code paths that could crash Core.
- **Completeness:** All last-channel, location, session/run-id, and outbound formatting/delivery logic is in the two new modules; Core only delegates.

## Tests

- **Unit:** tests/test_core_refactor_phases2_4.py includes test_session_channel_module, test_outbound_module, test_outbound_format_helpers_no_core. Run: `pytest tests/test_core_refactor_phases2_4.py -v`. Note: session_channel and outbound import base.util (via session_channel’s Util() and outbound’s Util()); in environments where torch aborts on load, the full suite may need to be run in a different env where torch loads successfully.
- **Manual:** deliver_to_user, send_response_to_latest_channel, get_session_id, get_latest_chats should behave as before (Companion push, cron, reminders, session resolution).

## Summary

| Item | Before | After |
|------|--------|--------|
| Session/channel + location logic in core.py | ~220 lines | Thin wrappers (~50 lines) |
| Outbound formatting + delivery in core.py | ~200 lines | Thin wrappers (~35 lines) |
| core/session_channel.py | — | ~270 lines |
| core/outbound.py | — | ~200 lines |

Phase 5 is complete. Proceed to Phase 6 (answer_from_memory → llm_loop) when ready.
