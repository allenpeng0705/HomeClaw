# Core refactoring: modular Core

## Current state

- **core/core.py** is reduced in size; route handlers were moved into **core/routes/**.
- A single **Core** class (singleton, implements `CoreInterface`) holds:
  - FastAPI app and all route registrations
  - Plugin manager, orchestrator, chat DB, memory, vector stores, knowledge base
  - WebSocket session state, inbound async results, pending plugin calls
  - Dozens of route handlers (inbound, config, plugins, memory, KB, sessions, files, UI, /ws) all defined **inside** `initialize()`
- **core/** already has: `coreInterface.py`, `orchestrator.py`, `result_viewer.py`, `emailChannel/`, `utils/`. Most “business” logic still lives in `core.py`.

**Problems:** Hard to navigate, test, or extend; risky to change; one file does too much.

---

## Goal

- **Keep Core as the single entrypoint** (no change to how main.py or channels use it).
- **Split logic into small, focused modules** that “work as Core” together: Core stays the facade and wires them.
- **Improve**: readability, testability, extensibility (e.g. new routes or features in new modules without touching the giant file).

---

## Proposed module layout

High level: **Core** stays the singleton and owns `self.app` and shared state, but **route handlers and domain logic** move into submodules. Core’s `initialize()` imports and registers routes from these modules instead of defining them inline.

### 1. Route / API modules (FastAPI routers or plain functions)

| Module | Responsibility |
|--------|----------------|
| **auth.py** | `verify_inbound_auth`, `ws_auth_ok`. |
| **lifecycle.py** | `/register_channel`, `/deregister_channel`, `/ready`, `/pinggy`, `/shutdown`. |
| **inbound.py** | GET `/inbound/result` (POST `/inbound` stays in core.py). |
| **config_api.py** | GET/PATCH `/api/config/core`, GET/POST/PATCH/DELETE `/api/config/users`. |
| **files.py** | GET `/files/out`, GET `/api/sandbox/list`, POST `/api/upload`. |
| **memory_routes.py** | POST `/memory/summarize`, GET/POST `/memory/reset`. |
| **knowledge_base_routes.py** | `/knowledge_base/reset`, `folder_sync_config`, `sync_folder`. |
| **plugins_api.py** | `/api/plugins/*`, GET `/api/plugin-ui`. |
| **misc_api.py** | `/api/skills/clear-vector-store`, `/api/testing/clear-all`, GET `/api/sessions`, GET `/api/reports/usage`. |
| **ui_routes.py** | GET `/ui` (launcher). |
| **websocket_routes.py** | WebSocket `/ws`. |

Each module receives **Core instance** (or a narrow interface) so it can call `self.check_permission`, `self.get_latest_chats`, etc., and register routes; auth via Depends(auth.verify_inbound_auth) where required. No need to change Core’s public API.

### 2. Domain / service helpers (no routes)

| Module | Responsibility | Notes |
|--------|----------------|--------|
| **core/services/inbound_handler.py** | Build PromptRequest from InboundRequest, run orchestrator, format response (sync/stream/async) | Extract from current `/inbound` and helpers |
| **core/services/outbound_format.py** | `_format_outbound_text`, `_outbound_text_and_format`, `_safe_classify_format`; markdown_to_channel usage | Already has base.markdown_outbound |
| **core/services/location.py** | `_latest_location_path`, `_normalize_location_to_address`, `_set_latest_location`, `_get_latest_location*` | Pure logic, easy to test |
| **core/services/tool_helpers.py** | `_tool_result_looks_like_error`, `_tool_result_usable_as_final_response`, `_parse_raw_tool_calls_from_content`, `_infer_route_to_plugin_fallback` | Used by orchestrator/inbound |

These stay stateless or take Core (or a small interface) as argument; Core continues to own all state.

### 3. What stays in core.py

- Imports and singleton **Core** class definition.
- **__init__**: create `self.app`, assign plugin_manager, orchestrator, chat DB, memory, vector_store, knowledge_base, queues, WebSocket maps, etc.
- **initialize()**: 
  - Vector stores, memory, KB, Cognee/chroma setup.
  - **Register routers**: e.g. `from core.routes import inbound, config_api, ...` then `self.app.include_router(inbound.router, ...)` (or attach route functions that close over `self`).
  - No long handler bodies; keep only “wire Core + router” code.
- High-level methods that are part of **CoreInterface** or used everywhere: `check_permission`, `get_latest_chats`, `add_chat_history`, `get_session_id`, `deliver_to_user`, etc. Those can stay in core.py initially; later they can move to a **CoreSessionService** or stay as-is.
- **Lifecycle**: `start_email_channel`, `stop`, `exit_gracefully`, `main()`.

So core.py becomes a **thin shell**: init state, call `initialize_*()` in submodules, register routes from submodules, expose CoreInterface and lifecycle. Target: bring core.py down to roughly 1,500–2,500 lines (everything else moved into routes/* and services/*).

---

## How to register routes (two options)

**Option A – Routers with dependency injection**

- Each module defines a **FastAPI APIRouter** and a function `def register(core: Core)` that adds the router to `core.app` and passes `core` (or a Depends() that returns core) so handlers can call `core.check_permission`, etc.
- In Core.initialize():  
  `inbound.register(self)` → `self.app.include_router(inbound.router, prefix="")`.

**Option B – Handler factories that close over Core (implemented)**

- Each module defines `get_*_handler(core)` that returns an async handler (closure over `core`).
- In Core.initialize():  
  `self.app.add_api_route("/path", module.get_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])`.
- This is what was implemented: minimal change, same behavior, no APIRouter.

---

## Phased plan

### Phase 1 – Extract auth and one route module (low risk)

1. Add **core/routes/auth.py**: move `_verify_inbound_auth` and `_ws_auth_ok` into a module that takes `Util()` (or core) for metadata; export Depends for use elsewhere.
2. Add **core/routes/lifecycle.py**: move `/register_channel`, `/deregister_channel`, `/ready`, `/pinggy`, `/shutdown` into functions that take `core`; register them in `Core.initialize()`.
3. Run tests and manual smoke (start Core, hit /ready, register channel). No change to external behavior.

### Phase 2 – Extract inbound and config API

1. **core/routes/inbound.py**: move POST `/inbound` and GET `/inbound/result` (and stream/async helpers) into this module; use auth from core/routes/auth.py.
2. **core/routes/config_api.py**: move all `/api/config/*` handlers.
3. **core/services/inbound_handler.py** (optional): extract “build request → run orchestrator → build response” so inbound route is thin.  
4. Test thoroughly (Companion, webchat, channels).

### Phase 3 – Extract remaining API and WebSocket

1. **core/routes/plugins_api.py**, **memory_api.py**, **knowledge_base_api.py**, **sessions_api.py**, **files_api.py**, **testing_api.py**, **ui.py**.
2. **core/websocket.py**: move `/ws` handler and push/session logic.
3. **core/services/**: move location, outbound_format, tool_helpers as needed.

### Phase 4 – Optional enhancements

- Introduce a **CoreSessionService** (or similar) that owns session/chat/location logic and is used by Core and routes.
- Add **unit tests** for services (inbound_handler, location, tool_helpers) with a small Core mock.
- Add **integration tests** that start Core and hit key routes.

---

## Extensibility after refactor

- **New route groups**: add `core/routes/xyz_api.py`, register in `Core.initialize()`; core.py stays small.
- **New features**: add `core/services/feature.py` and call from the right route module.
- **Testing**: mock only the Core interface or a small set of services when testing a single route module or service.
- **Multiple backends**: e.g. swap inbound handler or session service without touching the rest of Core.

---

## Summary

- **Yes, refactoring is worthwhile:** Core is too large; splitting into small modules will improve maintainability and extensibility without changing how the rest of the app uses Core.
- **Stable approach:** Keep Core as the single entrypoint and state owner; move route handlers and domain logic into **core/routes/*.py** and **core/services/*.py**, and register them from `Core.initialize()`.
- **Start small:** Phase 1 (auth + lifecycle) proves the pattern with minimal risk; then move inbound and config (Phase 2), then the rest (Phase 3). This keeps the codebase stable and avoids big-bang rewrites.
