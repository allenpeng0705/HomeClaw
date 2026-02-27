# Core.py refactor — Phase 2: Extract route registration

**Status:** Done  
**Branch:** refactor/core-multi-module (or as created)

## Goal

Move all FastAPI route registration (add_api_route, add_websocket_route, exception handler, and inline POST handlers for /process, /local_chat, /inbound) from `Core.__init__` into a dedicated module. Core calls a single function so __init__ stays shorter and route wiring is in one place.

## Changes

### 1. New file: core/route_registration.py

- **register_all_routes(core)**  
  Single function that:
  - Takes the Core instance (`core`) and uses `core.app` to register routes.
  - Registers the **RequestValidationError** exception handler.
  - Registers all **add_api_route** and **add_websocket_route** calls (lifecycle, inbound, config, files, memory, knowledge_base, plugins, misc, companion push/auth, UI, WebSocket).
  - Defines and registers the three inline POST handlers:
    - **POST /process** — permission check, set user/friend_id, persist last channel, put request on queue; uses `core` for all callbacks.
    - **POST /local_chat** — permission check, persist last channel, optional orchestrator, then `core.process_text_message`; uses `core` for all callbacks.
    - **POST /inbound** — async/stream/sync handling, `core._handle_inbound_request`, `core._outbound_text_and_format`, image data URLs, WS/push fallback when disconnected; uses `core` for all callbacks.
  - **Pinggy:** Uses `core._pinggy_state_getter` (a callable returning the shared state dict). If not set or not callable, uses a default no-op getter.
  - Logs at the end: `"core initialized and all the endpoints are registered!"`.

- **Imports:** FastAPI (Depends, Request, RequestValidationError, responses), base.base (PromptRequest, InboundRequest, User, AsyncResponse, ChannelType, ContentType), base.tools (ROUTING_RESPONSE_ALREADY_SENT), base.util (Util), and all `core.routes` submodules. No import of `core.core` to avoid circular imports.

### 2. core/core.py

- **Import:** `from core.route_registration import register_all_routes`
- **Before route registration:** Set `self._pinggy_state_getter = lambda: _pinggy_state` so the shared pinggy state is available to `register_all_routes`.
- **Replacement:** The whole block that registered the exception handler, all add_api_route/add_websocket_route calls, and the three `@self.app.post` handlers (and the final logger.debug) is replaced by:
  - `self._pinggy_state_getter = lambda: _pinggy_state`
  - `register_all_routes(self)`
- **Unchanged:** All Core methods used by the handlers (e.g. `check_permission`, `_persist_last_channel`, `process_text_message`, `_handle_inbound_request`, `_outbound_text_and_format`, etc.) remain in core.py; no behavior change.

## Logic and stability

- **Correctness:** Handler logic is unchanged; only the definition location and the variable used for the Core instance (`self` → `core`) changed. All call sites in the handlers use `core.*` consistently.
- **Robustness:** Same try/except and defensive patterns as before. No new code paths that could crash Core.
- **Completeness:** Every route and handler previously in __init__ is now registered inside `register_all_routes(self)`; no routes are left in core.py.

## Tests

- **Existing:** `tests/test_core_routes.py` still validates that route handler factories exist and return callables; it does not require routes to be registered in core.py. Run with project env (e.g. `conda activate pytorch && python -m pytest tests/test_core_routes.py -v`). If the environment aborts when loading torch (e.g. via base.util), use the same workaround as in Phase 1.
- **Manual:** Start Core, hit `/process`, `/local_chat`, `/inbound`, and key API routes to confirm behavior unchanged.

## Summary

| Item | Before | After |
|------|--------|--------|
| Route registration in core.py | ~290 lines (exception handler + routes + 3 inline handlers) | 2 lines (set _pinggy_state_getter + register_all_routes(self)) |
| core/route_registration.py | — | ~470 lines (register_all_routes + all handlers) |
| Core.__init__ | Long inline route block | Short delegation to register_all_routes |

Phase 2 is complete. Proceed to Phase 3 (initialization) when ready.
