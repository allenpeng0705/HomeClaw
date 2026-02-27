# Core.py refactor — Phase 4: Extract inbound handlers

**Status:** Done  
**Branch:** refactor/core-multi-module (or as created)

## Goal

Move the inbound request handling logic (POST /inbound and WebSocket /ws shared flow) from `core/core.py` into `core/inbound_handlers.py`. Core keeps thin wrappers that delegate to the module; route registration and callers are unchanged.

## Changes

### 1. New file: core/inbound_handlers.py

- **handle_inbound_request(core, request, progress_queue=None)**  
  Crash-safe wrapper: calls `handle_inbound_request_impl(core, ...)` and on exception returns `(False, error_msg, 500, None)`.

- **run_async_inbound(core, request_id, request)**  
  Background task for async /inbound: calls `handle_inbound_request(core, request)`, builds response (out_text, out_fmt, data_urls), stores in `core._inbound_async_results[request_id]`, and if `request.push_ws_session_id` is set pushes the result to that WebSocket.

- **handle_inbound_request_impl(core, request, progress_queue=None)**  
  Full implementation: normalizes images/videos/audios/files (including data URLs in files → images), builds `PromptRequest`, checks permission via `core.check_permission`, stores location via `core._normalize_location_to_address` / `core._set_latest_location`, sets `core.latestPromptRequest`, calls `core._persist_last_channel`, optionally `core.orchestrator_handler`, then `core.process_text_message`, and returns `(ok, text, status, image_paths)`.

- **inbound_sse_generator(core, progress_queue, task)**  
  Async generator: yields SSE progress events from the queue, heartbeat every 40s, then when the task completes yields a final `done` event with result (using `core._outbound_text_and_format` for text and building data URLs for images). Never raises; on error yields `done` with `ok=False`.

- **Imports:** asyncio, base64, copy, json, os, time, datetime, base.base (ChannelType, ContentType, InboundRequest, PromptRequest), base.tools (ROUTING_RESPONSE_ALREADY_SENT), loguru. No import of core.core.

### 2. core/core.py

- **Import:**  
  `from core.inbound_handlers import handle_inbound_request as _handle_inbound_request_fn, run_async_inbound as _run_async_inbound_fn, handle_inbound_request_impl as _handle_inbound_request_impl_fn, inbound_sse_generator as _inbound_sse_generator_fn`
- **Core._handle_inbound_request:**  
  `return await _handle_inbound_request_fn(self, request, progress_queue=progress_queue)`
- **Core._run_async_inbound:**  
  `await _run_async_inbound_fn(self, request_id, request)`
- **Core._handle_inbound_request_impl:**  
  `return await _handle_inbound_request_impl_fn(self, request, progress_queue=progress_queue)`
- **Core._inbound_sse_generator:**  
  `async for chunk in _inbound_sse_generator_fn(self, progress_queue, task): yield chunk`
- **Removed:** The previous ~270 lines of inline implementation of these four methods.

## Logic and stability

- **Correctness:** Behavior unchanged; only the definition location and the use of `core` instead of `self` in the extracted functions. Permission, location, last channel, orchestrator, process_text_message, and response image paths are unchanged.
- **Robustness:** Same try/except and defensive handling; no new code paths that could crash Core.
- **Completeness:** All logic that was in the four methods is now in inbound_handlers; Core only delegates.

## Tests

- POST /inbound (sync, async, stream=true) and WebSocket /ws should behave as before. Manual or automated tests that hit these endpoints should still pass.
- Existing route tests (e.g. test_core_routes) are unchanged; they only check that handler factories exist.

## Summary

| Item | Before | After |
|------|--------|--------|
| Inbound handler logic in core.py | ~270 lines (4 methods) | 4 thin wrappers (~15 lines) |
| core/inbound_handlers.py | — | ~300 lines (4 functions) |

Phase 4 is complete. Proceed to Phase 5 (outbound and session/channel) when ready.
