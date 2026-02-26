# Core refactoring – phase summary and reference

This document is the **authoritative phase-by-phase log** of the Core route refactor. It is intended for reviewers and learners: use the **Review checklist** at the end to verify logic, stability, and documentation.

**Design goals:** Logic 100% correct and unchanged from pre-refactor behavior; stable and robust (no new crashes); works on all platforms (Windows, macOS, Linux). The refactor only moves route handlers into `core/routes/*` and registers them from `Core.initialize()`; it does not change request/response behavior or add new failure modes.

**Pre-refactor core.py:** To compare or recover the original single-file Core, use git history (e.g. `git show <commit-before-refactor>:core/core.py`).

---

## Phase 1: Auth + lifecycle routes ✅

**Goal:** Extract auth helpers and lifecycle route handlers into `core/routes/` without changing behavior.

### Added files

| File | Purpose |
|------|--------|
| **core/routes/__init__.py** | Package init; exports `auth`, `lifecycle`. |
| **core/routes/auth.py** | `verify_inbound_auth(request)` for Depends (HTTP); `ws_auth_ok(websocket)` for WebSocket. Uses `Util().get_core_metadata()` only. Never raises except `HTTPException(401)`. |
| **core/routes/lifecycle.py** | Handler factories: `get_register_channel_handler(core)`, `get_deregister_channel_handler(core)`, `get_ready_handler(core)`, `get_pinggy_handler(core, get_pinggy_state)`, `get_shutdown_handler(core)`. Each returns an async handler closed over `core`. Pinggy uses a getter for the global `_pinggy_state` to avoid circular imports. |

### Changes in core.py

1. **Import:** `from core.routes import auth, lifecycle`
2. **Lifecycle routes:** Replaced inline `@self.app.post("/register_channel")` … `@self.app.get("/shutdown")` with:
   - `self.app.add_api_route("/register_channel", lifecycle.get_register_channel_handler(self), methods=["POST"])`
   - Same for `/deregister_channel`, `/ready`, `/pinggy` (with `lambda: _pinggy_state` and `response_class=HTMLResponse`), `/shutdown`.
3. **Auth:** Removed inline `_verify_inbound_auth` and `_ws_auth_ok`. All `Depends(_verify_inbound_auth)` → `Depends(auth.verify_inbound_auth)`. The single `_ws_auth_ok(websocket)` call → `auth.ws_auth_ok(websocket)`.

### Behavior and stability

- **Auth:** Logic unchanged; safe Bearer parsing in auth.py (no IndexError). On any non-HTTPException error, auth.py raises `HTTPException(401)` so Core does not crash.
- **Lifecycle:** Same behavior: register/deregister call `core.register_channel` / `core.deregister_channel`; ready returns 200/503 from `core._core_http_ready`; pinggy uses `core_public_url` then `_pinggy_state`; shutdown calls `core.stop()`. Request body for register/deregister remains `RegisterChannelRequest` (FastAPI infers from handler type hint).
- **No new dependencies**; no change to Core singleton or `initialize()` order relative to other routes.

### Verification

- Lint: no new issues on `core/core.py`, `core/routes/auth.py`, `core/routes/lifecycle.py`.
- Grep: no remaining `_verify_inbound_auth` or `_ws_auth_ok` in `core/core.py`.
- Manual: run Core, hit `GET /ready`, `POST /register_channel` (with body), `GET /pinggy`, `GET /shutdown` (if desired); confirm /inbound and /ws still enforce auth when `auth_enabled` is true.

---

## Phase 2: Inbound + config API ✅

**Goal:** Extract GET /inbound/result and the full config API (core.yml + user.yml) into route modules; keep POST /inbound in core.py (stream/async logic unchanged).

### Added files

| File | Purpose |
|------|--------|
| **core/routes/inbound.py** | `get_inbound_result_handler(core)` – async handler for GET /inbound/result. Uses `core._inbound_async_results` and TTL; returns 202 pending, 200 done, or 404 gone. |
| **core/routes/config_api.py** | Constants: `CONFIG_CORE_WHITELIST`, `CONFIG_CORE_BOOL_KEYS`. Helpers: `_deep_merge`, `_merge_models_list`, `_redact_config`. Handler factories: `get_api_config_core_get_handler(core)`, `get_api_config_core_patch_handler(core)`, `get_api_config_users_get_handler(core)`, `get_api_config_users_post_handler(core)`, `get_api_config_users_patch_handler(core)`, `get_api_config_users_delete_handler(core)`. All use `Util()` and `User`; POST creates user and calls `ensure_user_sandbox_folders` + `build_and_save_sandbox_paths_json`. |

### Changes in core.py

1. **Import:** `from core.routes import auth, lifecycle, inbound, config_api`
2. **Route registration (after lifecycle):**  
   `add_api_route("/inbound/result", inbound.get_inbound_result_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])`  
   Plus six config routes: GET/PATCH `/api/config/core`, GET/POST `/api/config/users`, PATCH/DELETE `/api/config/users/{user_name}` – each with `dependencies=[Depends(auth.verify_inbound_auth)]`.
3. **Removed:** Inline `inbound_result` handler (GET /inbound/result) and the entire config API block: `_CONFIG_CORE_WHITELIST`, `_CONFIG_CORE_BOOL_KEYS`, `_deep_merge`, `_merge_models_list`, `_redact_config`, and the six `@self.app.get/patch/post/delete` config handlers.

### Behavior and stability

- **GET /inbound/result:** Same logic: TTL cleanup, 400 on missing request_id, 404 on unknown/expired, 202 pending, 200 with text/format/images/error. Reads/mutates `core._inbound_async_results` (same dict reference).
- **Config API:** Same whitelist, deep-merge, model-list merge, redaction; core.yml and user.yml read/write via Util(); user POST creates sandbox folders and updates sandbox_paths.json. No Core instance methods used except via Util() and base types.
- **POST /inbound** remains in core.py; no change to stream/async behavior.

### Verification

- Lint: no issues on `core/core.py`, `core/routes/inbound.py`, `core/routes/config_api.py`.
- Recommended: run Core, POST /inbound with async: true, poll GET /inbound/result; GET/PATCH /api/config/core and GET/POST/PATCH/DELETE /api/config/users (with auth when enabled).

---

## Phase 3: Remaining APIs + WebSocket ✅

**Goal:** Extract files, memory, knowledge_base, plugins, misc (skills/testing/sessions/reports), UI launcher, and WebSocket /ws into route modules.

### Added files

| File | Purpose |
|------|--------|
| **core/routes/files.py** | `get_files_out_handler`, `get_api_sandbox_list_handler`, `get_api_upload_handler`. Includes `_escape_for_html` for directory listing. |
| **core/routes/memory_routes.py** | `get_memory_summarize_handler`, `get_memory_reset_handler` (GET+POST). Reset uses core.mem_instance, chatDB, orchestratorInst.tam, workspace/daily/profile clear. |
| **core/routes/knowledge_base_routes.py** | `get_knowledge_base_reset_handler`, `get_knowledge_base_folder_sync_config_handler`, `get_knowledge_base_sync_folder_handler` (GET+POST). Helper `_sync_folder_user_id(request)`. |
| **core/routes/plugins_api.py** | Register, unregister, unregister-all, health/{id}, llm/generate, memory/add, memory/search, plugin-ui. All use core.plugin_manager or core.openai_chat_completion / core.mem_instance. |
| **core/routes/misc_api.py** | Skills clear-vector-store, testing clear-all, sessions list, reports/usage (JSON or CSV). |
| **core/routes/ui_routes.py** | `get_ui_launcher_handler` for GET /ui (sessions table, plugin UIs, testing buttons). |
| **core/routes/websocket_routes.py** | `get_websocket_handler(core)` for /ws: auth via auth.ws_auth_ok, core._ws_sessions/_ws_user_by_session, core._handle_inbound_request, core._outbound_text_and_format. |

### Changes in core.py

1. **Imports:** Added `plugins_api`, `misc_api`, `ui_routes`, `websocket_routes` to the core.routes import.
2. **Registration:** All of the above routes registered via `add_api_route` (with dependencies where needed) and `add_websocket_route("/ws", websocket_routes.get_websocket_handler(self))`.
3. **Removed:** Inline handlers for files_out, _escape_for_html, api_sandbox_list, api_upload; memory_summarize, memory_reset; knowledge_base_reset, folder_sync_config, _sync_folder_user_id, sync_folder; all plugin API handlers; skills clear, testing clear-all, sessions, reports/usage; ui_launcher; websocket_chat; and the "add more endpoints" comment.

### Behavior and stability

- **Files:** Same token verification, path resolution, directory HTML listing, file response. Sandbox list and upload use Util() and Path/datetime/uuid.
- **Memory:** Summarize calls core.run_memory_summarization(); reset uses core.mem_instance, chatDB, meta, workspace/daily/profile/TAM clear (unchanged).
- **Knowledge base:** Reset/folder_sync_config/sync_folder use core.knowledge_base and core.sync_user_kb_folder; _sync_folder_user_id logic unchanged.
- **Plugins:** All plugin_manager and LLM/memory calls go through core; request/response shapes unchanged.
- **Misc:** Skills/testing/sessions/reports unchanged; reports usage still imports hybrid_router.metrics.
- **UI:** Same HTML launcher; core.get_sessions and plugin_manager.plugin_by_id.
- **WebSocket:** Same auth, session tracking, InboundRequest build, _handle_inbound_request, _outbound_text_and_format, image data URLs; finally block clears _ws_sessions and _ws_user_by_session.

### Verification

- Lint: no issues on core.py and all new route modules.
- Recommended: run Core and hit /files/out (with token), /api/sandbox/list, /api/upload; /memory/summarize, /memory/reset; /knowledge_base/reset, /knowledge_base/folder_sync_config, /knowledge_base/sync_folder; plugin register/unregister/health/llm/memory, /api/plugin-ui; /api/skills/clear-vector-store, /api/testing/clear-all, /api/sessions, /api/reports/usage; GET /ui; connect to /ws and send messages.

---

## Phase 4: Services + tests + full doc ✅

**Goal:** Complete the reference documentation; leave service extraction as optional follow-up; add a minimal test to ensure route modules and handler factories load correctly.

### Done

1. **Full reference (below):** Complete map of all route modules and what remains in core.py.
2. **CoreRefactoringModularCore.md:** Updated to reflect the implemented layout (handler factories + `add_api_route` / `add_websocket_route`).
3. **Services:** Inbound handler logic (`_handle_inbound_request`, `_handle_inbound_request_impl`, `_run_async_inbound`), outbound format (`_outbound_text_and_format`), location helpers, and tool_helpers **remain as Core methods** in core.py for stability. Optional future phase: extract these into `core/services/` when adding more tests or features.
4. **Tests:** `tests/test_core_routes.py` – smoke tests for the route layer (see **Tests for Core routes** below).

### Verification

- All route behavior is unchanged; no new runtime dependencies.
- Recommended: run Core, run a quick smoke (e.g. GET /ready, GET /ui, POST /inbound with auth if enabled).

---

## Full reference (after all phases)

### Route modules (core/routes/)

| Module | Handlers / factories | Auth |
|--------|----------------------|------|
| **auth.py** | `verify_inbound_auth`, `ws_auth_ok` | — |
| **lifecycle.py** | `get_register_channel_handler`, `get_deregister_channel_handler`, `get_ready_handler`, `get_pinggy_handler`, `get_shutdown_handler` | — |
| **inbound.py** | `get_inbound_result_handler` | Depends(auth) on route |
| **config_api.py** | `get_api_config_core_get_handler`, `get_api_config_core_patch_handler`, `get_api_config_users_*` (get/post/patch/delete) | Depends(auth) |
| **files.py** | `get_files_out_handler`, `get_api_sandbox_list_handler`, `get_api_upload_handler` | files_out: token; sandbox/upload: Depends(auth) |
| **memory_routes.py** | `get_memory_summarize_handler`, `get_memory_reset_handler` | reset: Depends(auth) |
| **knowledge_base_routes.py** | `get_knowledge_base_reset_handler`, `get_knowledge_base_folder_sync_config_handler`, `get_knowledge_base_sync_folder_handler` | Depends(auth) |
| **plugins_api.py** | register, unregister, unregister-all, health/{id}, llm/generate, memory/add, memory/search, plugin-ui list | All except plugin-ui: Depends(auth) |
| **misc_api.py** | skills clear-vector-store, testing clear-all, sessions list, reports/usage | Depends(auth) |
| **ui_routes.py** | `get_ui_launcher_handler` | — |
| **websocket_routes.py** | `get_websocket_handler` | auth.ws_auth_ok inside handler |

### Still in core.py (not extracted)

- **POST /inbound** (stream + async + sync) and **POST /process**, **POST /local_chat** (channel flow).
- **Core state and init:** `self.app`, plugin_manager, orchestrator, chatDB, memory, knowledge_base, `_ws_sessions`, `_ws_user_by_session`, `_inbound_async_results`, etc.
- **Core methods used by routes and flow:** `_handle_inbound_request`, `_handle_inbound_request_impl`, `_run_async_inbound`, `_outbound_text_and_format`, `run_memory_summarization`, `sync_user_kb_folder`, `get_sessions`, `openai_chat_completion`, `check_permission`, and all other CoreInterface / internal methods.
- **Lifecycle:** `start_email_channel`, `stop`, `main()`, `initialize()` (which registers all routes from the modules above).

### How to add a new route group

1. Add `core/routes/your_module.py` with one or more `get_*_handler(core)` functions returning async handlers.
2. In `core/routes/__init__.py`, import and export your module.
3. In `Core.initialize()`, after existing `add_api_route` / `add_websocket_route` calls, add:
   - `self.app.add_api_route("/path", your_module.get_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])` (or as needed).
4. Use `core` inside the handler for any Core state or methods.

### Pre-refactor comparison

- The pre-refactor single-file `core.py` can be recovered from git history for diff or comparison.

See **CoreRefactoringModularCore.md** for the overall design and phased plan.

---

## Tests for Core routes

Smoke tests live in **tests/test_core_routes.py**. They do not start Core or call real HTTP endpoints; they only check that route modules and handler factories load and behave as expected.

### What the tests do

| Test | What it checks |
|------|----------------|
| `test_route_modules_import` | All 11 route submodules (`auth`, `lifecycle`, `inbound`, `config_api`, `files`, `memory_routes`, `knowledge_base_routes`, `plugins_api`, `misc_api`, `ui_routes`, `websocket_routes`) can be imported without errors (no circular imports or missing dependencies). |
| `test_auth_helpers_exist_and_are_callable` | `auth.verify_inbound_auth` and `auth.ws_auth_ok` exist and are callable. |
| `test_handler_factory_exists_and_returns_callable` | For each handler factory (e.g. `get_ready_handler`, `get_inbound_result_handler`, …), the function exists on its module, is callable, and when called with a **mock Core** (and extra args where needed, e.g. `get_pinggy_state` for pinggy) **returns a callable** (the actual route handler). Uses a single parametrized test over the list of 35+ factories. |
| `test_all_factories_count` | Sanity check that the number of factories in the test list is at least 35, so new routes are not forgotten when adding tests. |

The mock Core only sets a few attributes (`_inbound_async_results`, `_ws_sessions`, `_ws_user_by_session`, `plugin_manager`, `get_sessions`) so that handler factories that touch these in the closure do not raise when the returned handler is not invoked. The tests **do not** call the returned handlers (no request/response simulation).

### How to run the tests

**Prerequisites:** From the project root, Core and its dependencies must be importable (e.g. `pip install -r requirements.txt` or your usual env). Install pytest:

```bash
pip install pytest
```

**Run from project root** (the directory that contains `core/`, `tests/`, `config/`, etc.). Use **pytest**; do not run `python -m tests.test_core_routes` or `python -m tests/test_core_routes.py` (that will fail with ModuleNotFoundError):

```bash
# Run all Core route smoke tests
python -m pytest tests/test_core_routes.py -v

# Run with short description for each test
python -m pytest tests/test_core_routes.py -v -s

# Run a single test by name
python -m pytest tests/test_core_routes.py -v -k "test_route_modules_import"

# Run only factory tests (parametrized)
python -m pytest tests/test_core_routes.py -v -k "test_handler_factory"
```

**Using python3:**

```bash
python3 -m pytest tests/test_core_routes.py -v
```

**Exit codes:** 0 = all tests passed; non‑zero = one or more tests failed (e.g. missing factory or import error). Pytest prints which test failed and the assertion message.

### How they work

1. **Imports:** The test file imports from `core.routes` (and thus `core.routes.auth`, `core.routes.lifecycle`, etc.). If any module has a circular import or a missing dependency, the import step fails and the test run fails immediately.
2. **Factory list:** The test file defines a list `ROUTE_FACTORIES` of `(module_name, factory_name, extra_args)`. For almost all handlers, `extra_args` is `()`. For `get_pinggy_handler`, `extra_args` is `(lambda: {},)` because the factory expects `(core, get_pinggy_state)`.
3. **Parametrized test:** `test_handler_factory_exists_and_returns_callable` is parametrized over this list. For each row, it gets the module by name from `core.routes`, gets the factory by name, asserts it is callable, then calls `factory(mock_core, *extra_args)` and asserts the result is callable. This guarantees that `Core.initialize()` can call the same factories with `self` and get valid handlers to pass to `add_api_route` / `add_websocket_route`.
4. **No async required:** These tests are synchronous; they do not run the returned async handlers. So `pytest-asyncio` is not required for this file (unlike tests that call async endpoints).

Adding a new route module or a new handler factory requires adding a row to `ROUTE_FACTORIES` in `tests/test_core_routes.py` and, if needed, bumping the minimum count in `test_all_factories_count`.

---

## Review checklist (for reviewers and learners)

Use this to verify logic, stability, and documentation.

### Logic and parity with backup

- [ ] **Route coverage:** Every route that was in pre-refactor core.py (except those still in core.py) is registered in `Core.initialize()` via `add_api_route` / `add_websocket_route`. Use git history to compare `@self.app.(get|post|patch|delete|websocket)` if needed.
- [ ] **Auth:** Routes that had `Depends(_verify_inbound_auth)` in the backup now have `dependencies=[Depends(auth.verify_inbound_auth)]`. WebSocket uses `auth.ws_auth_ok(websocket)` inside the handler.
- [ ] **GET /inbound/result:** Uses `core._inbound_async_results` (same dict as POST /inbound and _run_async_inbound). TTL cleanup mutates that dict when present; default `{}` only avoids AttributeError.
- [ ] **Config API:** Whitelist and bool keys match backup; deep_merge, merge_models_list, redact_config logic unchanged; user POST calls `ensure_user_sandbox_folders` and `build_and_save_sandbox_paths_json`.
- [ ] **Files / memory / KB / plugins / misc / UI / WebSocket:** Handler bodies match backup behavior (same status codes, response shapes, and Core method calls).

### Stability and robustness

- [ ] **No new crashes:** Auth raises only `HTTPException(401)`; route handlers catch exceptions and return JSONResponse with appropriate status/detail; no unguarded attribute access on `core` for required attributes (optional use `getattr(..., None)` or default).
- [ ] **Cross-platform:** No platform-specific code was added; same behavior on Windows, macOS, Linux. Existing use of `Path`, `os`, and ASGI is unchanged.
- [ ] **Imports:** No circular imports; `core.routes` imports from `base.*`, `fastapi`, etc.; Core imports `core.routes` in `initialize()` after app exists.

### Documentation

- [ ] **CoreRefactorPhaseSummary.md:** Phases 1–4 and Full reference match the actual modules and route list. “How to add a new route group” is accurate.
- [ ] **CoreRefactoringModularCore.md:** “Current state” and “Route / API modules” table reflect the implemented layout (handler factories, module names).
- [ ] **Pre-refactor reference:** Use git history to recover or diff the pre-refactor `core.py` if needed.
