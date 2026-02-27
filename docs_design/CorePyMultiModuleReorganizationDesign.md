# Core.py multi-module reorganization — design and steps

**Goal:** Reorganize `core/core.py` (~6300 lines) into multiple modules for maintainability, without changing behavior or breaking the single entry point (`Core` class, `main()`). This document is for **review and discussion** before any code changes.

---

## 1. Current state analysis

### 1.1 File structure (summary)

| Section | Approx. lines | Description |
|--------|----------------|-------------|
| **Imports** | 1–89 | Standard lib, FastAPI, base/memory/tools, routes; optional `core.services.tool_helpers` with inline fallback |
| **Tool helpers fallback** | 103–340 | ~240 lines: inline definitions when `tool_helpers` import fails (`_tool_result_looks_like_error`, `_tool_result_usable_as_final_response`, `_infer_remind_me_fallback`, etc.) |
| **_SuppressConfigCoreAccessFilter** | 340–366 | Logging filter for uvicorn access log |
| **Module helpers** | 357–383 | `_component_log`, `_truncate_for_log`, `_strip_leading_route_label` |
| **class Core(CoreInterface)** | 384–~6224 | **~5840 lines** — main class |
| **main()** | 6225–6260 | Entry point: event loop, `with Core() as core`, `core.run()` |
| **Windows Ctrl handler** | 6269–6304 | `_win_console_ctrl_handler`, `_core_instance_for_ctrl_c` |

### 1.2 Core class — method groups (by responsibility)

| Group | Methods (examples) | Approx. lines | Notes |
|-------|--------------------|----------------|-------|
| **Construction & route registration** | `__new__`, `__init__` (incl. all `app.add_api_route` / `@app.post` blocks) | ~760 | Route registration is a large inline block (~250 lines) inside `__init__` |
| **Plugin discovery & startup** | `find_plugin_prompt`, `is_proper_plugin`, `find_plugin_for_text`, `load_plugins`, `initialize_plugins`, `start_hot_reload`, `_pending_plugin_call_*`, `_discover_system_plugins`, `_wait_for_core_ready`, `_run_system_plugins_startup` | ~350 | System plugins (e.g. homeclaw-browser) start/register |
| **Embedding / vector / KB init** | `get_embedding`, `initialize_vector_store`, `_create_skills_vector_store`, `_create_plugins_vector_store`, `_create_agent_memory_vector_store`, `_create_knowledge_base`, `_create_knowledge_base_cognee`, `initialize` | ~450 | Cognee config, Chroma, KB |
| **Inbound** | `_handle_inbound_request`, `_run_async_inbound`, `_handle_inbound_request_impl`, `_inbound_sse_generator` | ~265 | POST /inbound, async, SSE |
| **Last channel & location** | `_persist_last_channel`, `_latest_location_path`, `_normalize_location_to_address`, `_set_latest_location`, `_get_latest_location`, `_get_latest_location_entry` | ~125 | Per-user last channel and location cache |
| **System context / prompt** | `get_system_context_for_plugins`, `save_latest_prompt_request_to_file`, `read_latest_prompt_request_from_file` | ~30 | |
| **Orchestrator & queues** | `orchestrator_handler`, `process_request_queue` | ~100 | |
| **Outbound** | `_format_outbound_text`, `_safe_classify_format`, `_outbound_text_and_format`, `send_response_to_latest_channel`, `send_response_to_channel_by_key`, `deliver_to_user`, `send_response_to_request_channel`, `send_response_for_plugin` | ~195 | Response delivery to channels/Companion |
| **Background loops** | `process_memory_queue`, `_process_kb_folder_sync_scheduler`, `process_memory_summarization_scheduler`, `process_response_queue` | ~160 | Memory queue, KB sync, summarization, response queue |
| **Session / chat IDs** | `get_run_id`, `get_latest_chat_info`, `get_latest_chats`, `get_latest_chats_by_role`, `_resolve_session_key`, `get_session_id` | ~120 | Session key resolution, chat history access |
| **Media** | `_resize_image_data_url_if_needed`, `_image_item_to_data_url`, `_audio_item_to_base64_and_format`, `_video_item_to_base64_and_format` | ~140 | Data URL / base64 handling for images/audio/video |
| **process_text_message** | Single method | ~315 | Builds context, calls `answer_from_memory` |
| **Prompt / permission** | `prompt_template`, `check_permission` | ~60 | |
| **Channels & run()** | `start_email_channel`, `_start_pinggy_and_open_browser`, `run()` | ~210 | run() contains server startup, init order, system_plugins, pinggy, sandbox setup |
| **Stop / shutdown** | `stop`, `register_channel`, `deregister_channel`, `shutdown_channel`, `shutdown_all_channels`, Chroma start/stop | ~95 | |
| **LLM (thin)** | `openai_chat_completion`, `extract_json_str`, `extract_tuple_str`, `openai_completion` | ~95 | Delegation to LLM service |
| **answer_from_memory** | Single method | **~1605** | **Largest single block:** hybrid router, tools, plugins, mix mode, tool loop, final response |
| **Chat/session API** | `add_chat_history`, `get_sessions`, `send_message_to_session`, `get_session_transcript`, `get_session_transcript_jsonl`, `prune_session_transcript`, `summarize_session_transcript`, `add_chat_history_by_role`, `add_user_input_to_memory`, `sync_user_kb_folder` | ~330 | Chat DB and session tools |
| **Misc** | `_memory_summarization_state_path`, etc. | ~50 | |

### 1.3 External usage

- **main.py:** `from core import core` then `core.main()` (and `core.main` for thread start). So `core` is the module `core/core.py`; the package `core/__init__.py` is empty, so `core` resolves to the `core` submodule (core.py).
- **Core instantiation:** Only in `core/core.py` itself: `with Core() as core: loop.run_until_complete(core.run())`.
- **CoreInterface:** Defines abstract methods; Core implements them. Other code may depend on the interface type.

**Constraint:** After refactor, `from core import core` and `core.main`, `core.Core` must keep working. Prefer keeping `core.Core` and `core.main()` in `core/core.py` (or re-exported from `core/__init__.py`).

---

## 2. Design principles

1. **Single entry point:** `Core` class and `main()` remain the only public entry; no new entry points.
2. **Backward compatibility:** No change to `core.Core`, `core.main`, or to `CoreInterface` contract. All existing callers (main.py, routes that receive `core`) stay valid.
3. **No behavior change:** Purely structural refactor; same logic, same tests, same process layout.
4. **Incremental steps:** Split in ordered steps so each step is reviewable and keeps the repo runnable.
5. **Minimal coupling:** Extracted code receives `core` (or a narrow interface) as argument where it needs to call back; avoid circular imports.
6. **Preserve Core as facade:** Core keeps attributes (e.g. `self.chatDB`, `self.mem_instance`, `self.request_queue`) and delegates to helpers/services; extracted modules do not hold Core state.

---

## 3. Proposed module layout

### 3.1 New modules (under `core/`)

| Module | Responsibility | Incoming deps | Outgoing (uses) |
|--------|----------------|---------------|------------------|
| **core/tool_helpers_fallback.py** | Inline fallback implementations when `core.services.tool_helpers` fails to import. | None | None |
| **core/log_helpers.py** | `_component_log`, `_truncate_for_log`, `_strip_leading_route_label`; optionally `_SuppressConfigCoreAccessFilter`. | None | None |
| **core/route_registration.py** | Register all FastAPI routes (add_api_route, add_websocket_route, inline @app.post handlers). One function e.g. `register_all_routes(app, core)` or `register_all_routes(core)` that receives Core instance. | Core (for handler factories that need `self`) | core.routes.*, lifecycle, etc. |
| **core/initialization.py** | `initialize()` body and helpers: `_create_skills_vector_store`, `_create_plugins_vector_store`, `_create_agent_memory_vector_store`, `_create_knowledge_base`, `_create_knowledge_base_cognee`. Functions take `core` (or necessary refs) and perform init; Core.initialize() calls them. | Core (refs to set on self) | Util, Chroma, Cognee, etc. |
| **core/plugins_startup.py** | `_discover_system_plugins`, `_wait_for_core_ready`, `_run_system_plugins_startup`. Async helpers; Core calls them from run() (e.g. asyncio.create_task). | Core (for env/config) | httpx, asyncio |
| **core/inbound_handlers.py** | `_handle_inbound_request`, `_run_async_inbound`, `_handle_inbound_request_impl`, `_inbound_sse_generator`. Async functions that take `(core, request, ...)` and use core’s queues, permission, process_text_message, etc. | Core | base, Util, last_channel, etc. |
| **core/outbound.py** | `_format_outbound_text`, `_safe_classify_format`, _outbound_text_and_format`, `send_response_to_latest_channel`, `send_response_to_channel_by_key`, `deliver_to_user`, `send_response_to_request_channel`, `send_response_for_plugin`. Can be functions taking `core` or a small `OutboundService(core)`. | Core | last_channel, response_queue, ws_sessions, push |
| **core/session_channel.py** | Last-channel and location: `_persist_last_channel`, `_latest_location_path`, `_normalize_location_to_address`, `_set_latest_location`, `_get_latest_location`, `_get_latest_location_entry`. Session/chat IDs: `_resolve_session_key`, `get_session_id`, `get_run_id`, `get_latest_chat_info`, `get_latest_chats`, `get_latest_chats_by_role`. All need Core (chatDB, request_metadata, last_channel store). Could be a single module with functions `(core, ...)` or a small helper class holding `core` ref. | Core | chatDB, last_channel, Util |
| **core/llm_loop.py** | The entire `answer_from_memory` implementation (~1600 lines). Receives `(core, query, messages, ...)` and uses core’s LLM, tools, memory, chatDB, plugin_manager, etc. Core.answer_from_memory() becomes a thin wrapper that calls `llm_loop.answer_from_memory(core, ...)`. | Core | tool_helpers, orchestrator, hybrid_router, tools, plugins |
| **core/media_utils.py** | `_resize_image_data_url_if_needed`, `_image_item_to_data_url`, `_audio_item_to_base64_and_format`, `_video_item_to_base64_and_format`. Pure or almost-pure helpers (only need core for config if at all). | Optional core ref for config | base64, PIL, etc. |
| **core/entry.py** (optional) | `main()`, `_win_console_ctrl_handler`, `_core_instance_for_ctrl_c`. Keeps process entry and Windows-specific handler out of core.py. | Core | asyncio, signal, ctypes (Windows) |

### 3.2 What stays in core/core.py

- **Imports** (consolidated; import from new modules where needed).
- **class Core(CoreInterface):**
  - `__new__`, `__init__`: Create app, queues, config, lifespan; **call** `route_registration.register_all_routes(self)` (or equivalent); no inline route blocks.
  - **Thin method bodies** that delegate:
    - `initialize()` → call `initialization.initialize(core)` (or initialization.run(core)).
    - `_handle_inbound_request`, `_run_async_inbound`, `_handle_inbound_request_impl`, `_inbound_sse_generator` → delegate to `inbound_handlers.*` with `self`.
    - `_persist_last_channel`, `get_session_id`, `get_run_id`, `get_latest_chats`, etc. → delegate to `session_channel.*` with `self`.
    - `answer_from_memory` → delegate to `llm_loop.answer_from_memory(self, ...)`.
    - Outbound methods → delegate to `outbound.*` with `self`.
    - Media helpers → delegate to `media_utils.*` (or keep if very short).
  - **Methods that stay in full** (or nearly): `process_text_message` (or move to a small `core/process_text_message.py` later), `check_permission`, `prompt_template`, `run()`, `stop()`, plugin discovery if we keep them as one-liners calling plugins_startup, `openai_chat_completion`, `extract_json_str`, `extract_tuple_str`, `openai_completion`, `add_chat_history`, `get_sessions`, `send_message_to_session`, `get_session_transcript`, `prune_session_transcript`, `summarize_session_transcript`, `add_chat_history_by_role`, `add_user_input_to_memory`, `sync_user_kb_folder`, `_memory_summarization_state_path`, and any other small API that is just a few lines.
- Re-exports or imports so that `Core` and `main` are still available from `core.core` (or from `core/__init__.py`).

### 3.3 Dependency direction (no cycles)

```
main.py
  → core.main (core/entry.py or core/core.py)

core/core.py (Core class)
  → core.log_helpers
  → core.tool_helpers_fallback (or core.services.tool_helpers)
  → core.route_registration
  → core.initialization
  → core.plugins_startup
  → core.inbound_handlers
  → core.outbound
  → core.session_channel
  → core.llm_loop
  → core.media_utils (optional)
  → core.entry (for main() if moved)

core/route_registration.py
  → core.routes.*, lifecycle, auth, etc.

core/llm_loop.py
  → core.log_helpers, tool_helpers, base, tools, orchestrator, hybrid_router, memory, etc.
  ← receives core (Core instance)
```

All new modules depend on `core` only as a passed-in instance (or not at all for pure helpers). No new module should be imported by `core/core.py` in a way that creates a cycle (e.g. routes already import nothing from core.py except the Core type passed into handler factories).

---

## 4. Step-by-step migration plan (for discussion)

Phases are ordered so that each step is independently reviewable and the app still runs after each step.

### Phase 0: Preparation (no file split)

- **0.1** Add unit tests or integration tests that cover Core startup, one inbound request, and one `answer_from_memory` path (if not already present), so we can regress later steps.
- **0.2** Confirm `core.services.tool_helpers` is the single source of truth and the inline fallback in core.py is only a fallback. Document that `tool_helpers_fallback` will replace the inline block in core.py.

### Phase 1: Extract pure helpers (low risk)

- **1.1** Create **core/log_helpers.py** with `_component_log`, `_truncate_for_log`, `_strip_leading_route_label`, and move `_SuppressConfigCoreAccessFilter` here. In core.py, remove these and add `from core.log_helpers import ...`. Run tests and manual smoke.
- **1.2** Create **core/tool_helpers_fallback.py** with all inline fallback functions (the block that runs when `tool_helpers` import fails). In core.py, try import from `core.services.tool_helpers`; on failure, import from `core.tool_helpers_fallback`. Remove the ~240 lines of inline fallback from core.py. Run tests.

### Phase 2: Extract route registration (medium risk)

- **2.1** Create **core/route_registration.py** with a single function `register_all_routes(core: Core)` (or `register_all_routes(app, core)` if we pass app explicitly). Move every `self.app.add_api_route`, `self.app.add_websocket_route`, and the inline `@self.app.post("/process")`, `@self.app.post("/local_chat")`, `@self.app.post("/inbound")` bodies into this function (receiving `core` so handlers can call `core.*`). In Core.__init__, after creating `self.app`, call `register_all_routes(self)`. Ensure no closure over `self` is broken (handlers use `core` instead of `self`). Run full server and test /process, /inbound, /ws, config, etc.

### Phase 3: Extract initialization (medium risk)

- **3.1** Create **core/initialization.py** with:
  - `run_initialize(core: Core)` that performs the current `initialize()` logic (vector stores, embedder, Cognee, etc.) and sets attributes on `core`.
  - Optionally split: `_create_skills_vector_store(core)`, `_create_plugins_vector_store(core)`, etc., and call them from `run_initialize(core)`.
- In Core, `initialize()` becomes `initialization.run_initialize(self)`. Run tests and startup.

### Phase 4: Extract inbound handlers (medium risk)

- **4.1** Create **core/inbound_handlers.py** with:
  - `async def handle_inbound_request(core, request, progress_queue=None) -> Tuple[bool, str, int, Optional[List[str]]]`
  - `async def run_async_inbound(core, request_id, request)`
  - `async def handle_inbound_request_impl(core, request, progress_queue=None) -> ...`
  - `async def inbound_sse_generator(core, progress_queue, task)` (or as generator that takes core)
- Core keeps `_handle_inbound_request`, `_run_async_inbound`, etc., as one-liners that call these with `self`. Route handlers still receive `core` and call `core._handle_inbound_request`; no change to route registration. Run /inbound sync, async, and stream.

### Phase 5: Extract outbound and session/channel (medium risk)

- **5.1** Create **core/outbound.py** with all outbound-related functions taking `core` as first argument. Core methods become thin wrappers.
- **5.2** Create **core/session_channel.py** with last-channel, location, and session-id/run-id/get_latest_chats logic; all take `core`. Core methods delegate. Test deliver_to_user, send_response_to_latest_channel, get_sessions, get_session_id.

### Phase 6: Extract answer_from_memory (high impact, careful testing)

- **6.1** Create **core/llm_loop.py** with a single function:
  - `async def answer_from_memory(core, query, messages, app_id=None, user_name=None, user_id=None, ...) -> Optional[str]`
  - Move the entire current body of `Core.answer_from_memory` into this function; replace `self` with `core` throughout.
- In Core, `async def answer_from_memory(self, ...): return await llm_loop.answer_from_memory(self, ...)`. Run full conversation flow, tools, mix mode, and plugins.

### Phase 7: Extract plugins startup and media (lower risk)

- **7.1** Create **core/plugins_startup.py** with `_discover_system_plugins`, `_wait_for_core_ready`, `_run_system_plugins_startup`; take `core` (or only what’s needed). Core.run() calls these as today.
- **7.2** Create **core/media_utils.py** with image/audio/video helpers. Core delegates. Test file upload and image-in-response.

### Phase 8: Optional — entry point and cleanup

- **8.1** Move `main()` and `_win_console_ctrl_handler` (and related globals) to **core/entry.py**. In core.py do `from core.entry import main`. Ensure `core.main` and `core.Core` still work for main.py (either from core/__init__.py or from core.core).
- **8.2** Final pass: reduce core.py to minimal Core class (attributes, thin delegators), imports, and any remaining small methods that are not worth moving. Run full regression.

---

## 5. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| **Circular imports** | New modules never import `core.core`; they receive `Core` instance as argument. core.py imports the new modules. Type hints can use `TYPE_CHECKING` and string annotations for `Core` if needed. |
| **Closure over `self` in route handlers** | Route registration will pass `core` into handler factories; handlers use `core` (the same instance as `self`). All current `self.*` in handlers become `core.*`. |
| **Large single move (answer_from_memory)** | Phase 6 is one big move; do it in a single PR with broad testing (one request, tool call, mix mode, plugin). Consider a feature flag to switch old vs new path during rollout (optional). |
| **Regression** | After each phase, run existing tests and manual smoke (start Core, send one message, check response). Phase 0 adds tests if missing. |

---

## 6. Open points for discussion

1. **Route registration:** Prefer one function `register_all_routes(core)` in one module, or split by domain (e.g. `register_lifecycle_routes`, `register_api_routes`) in the same module?
2. **Naming:** `llm_loop` vs `answer_from_memory` vs `conversation_engine` for the big LLM/tool loop module?
3. **session_channel:** One module for both “last channel + location” and “session_id / get_latest_chats”, or split into `core/last_channel.py` and `core/session_resolution.py`?
4. **CoreInterface:** Should it stay as-is, or should we add a narrow “CoreFacade” type (e.g. only the methods that llm_loop needs) to reduce coupling?
5. **Backward compat:** Keep `from core.core import Core, main` working, or officially switch to `from core import Core, main` (and implement `core/__init__.py` to re-export)?

---

## 7. Estimated line count after refactor (approximate)

| File | Before | After (target) |
|------|--------|----------------|
| core/core.py | ~6308 | ~1200–1800 (Core class + thin wrappers + run/stop, imports) |
| core/log_helpers.py | 0 | ~35 |
| core/tool_helpers_fallback.py | 0 | ~240 |
| core/route_registration.py | 0 | ~350 |
| core/initialization.py | 0 | ~450 |
| core/plugins_startup.py | 0 | ~130 |
| core/inbound_handlers.py | 0 | ~270 |
| core/outbound.py | 0 | ~200 |
| core/session_channel.py | 0 | ~250 |
| core/llm_loop.py | 0 | ~1620 |
| core/media_utils.py | 0 | ~145 |
| core/entry.py | 0 | ~90 |

Total lines remain roughly the same; core.py drops to a fraction of current size.

---

**Next:** Review this design; adjust module boundaries and phase order as needed; then implement Phase 0 and Phase 1 as first concrete steps.
