# Core.py refactor — Phase 1: Extract pure helpers

**Status:** Done  
**Branch:** refactor/core-multi-module (or as created)

## Goal

Extract pure helper code from `core/core.py` into dedicated modules so Core never crashes if a dependency fails and to reduce core.py size. No behavior change; backward compatible.

## Changes

### 1. New files

- **core/log_helpers.py**
  - `_component_log(component, message)` — logs when not silent (uses `Util().is_silent()`).
  - `_truncate_for_log(s, max_len=2000)` — truncates string for logging.
  - `_strip_leading_route_label(s)` — strips leading `[Local]` / `[Cloud]` etc.
  - `_SuppressConfigCoreAccessFilter` — logging filter to hide GET /api/config/core 200 from uvicorn access log.
  - Deps: `logging`, `re`, `loguru`, `base.util.Util`. No dependency on `core.core`.

- **core/tool_helpers_fallback.py**
  - Fallback implementations when `core.services.tool_helpers` is missing or broken:
    - `tool_result_looks_like_error`, `tool_result_usable_as_final_response`
    - `infer_remind_me_fallback`, `remind_me_needs_clarification`, `remind_me_clarification_question`
    - `infer_route_to_plugin_fallback`, `parse_raw_tool_calls_from_content`
  - Logic matches the previous inline block in core.py (and aligns with core.services.tool_helpers).
  - Deps: `json`, `re`, `uuid`, `loguru`, `typing`. No dependency on `core.core`.

### 2. core/core.py

- **Tool helpers:** Still prefer `core.services.tool_helpers`; on any exception, import the same symbols from `core.tool_helpers_fallback` (with same `_`-prefixed aliases). Removed ~240 lines of inline fallback.
- **Log helpers:** Removed `_SuppressConfigCoreAccessFilter`, `_component_log`, `_truncate_for_log`, `_strip_leading_route_label`. Added:
  - `from core.log_helpers import _component_log, _truncate_for_log, _strip_leading_route_label, _SuppressConfigCoreAccessFilter`
- **Kept:** `logging.basicConfig(level=logging.CRITICAL)` and `_pinggy_state` in core.py.
- All call sites in core.py unchanged: they still use `_component_log`, `_truncate_for_log`, `_strip_leading_route_label`, `_SuppressConfigCoreAccessFilter` and the tool helper aliases (`_tool_result_looks_like_error`, etc.).

## Logic and stability

- **Correctness:** Behavior is unchanged; only the definition location moved. Tool helper fallback logic is identical to the previous inline block.
- **Robustness:** Helpers are defensive (try/except, type checks). No new code paths that could crash Core.
- **Completeness:** All previous usages in core.py now resolve via imports; no remaining inline definitions of these helpers.

## Tests

- **Environment:** Use the project conda env, e.g. `conda activate pytorch`, then run pytest from repo root.
- **Phase 1 tests:** `tests/test_core_refactor_phase1.py` — tests `core.log_helpers` and `core.tool_helpers_fallback` (no Core/chromadb).
  - Full run: `conda activate pytorch && python -m pytest tests/test_core_refactor_phase1.py -v`
  - If the environment aborts when loading `torch` (via `base.util`), run only the tool_helpers_fallback tests:  
    `python -m pytest tests/test_core_refactor_phase1.py -v -k "tool_helpers_fallback or parse_raw or tool_result or infer_route or infer_remind or remind_me"`
- **Existing route tests:** `tests/test_core_routes.py` — imports `core.routes` (which loads `base.util` → torch). Run when torch loads successfully: `python -m pytest tests/test_core_routes.py -v`.

## Summary

| Item | Before | After |
|------|--------|--------|
| core.py | ~6308 lines (incl. ~280 helper lines) | ~6068 lines |
| core/log_helpers.py | — | ~60 lines |
| core/tool_helpers_fallback.py | — | ~230 lines |
| Tool helpers in core.py | Inline fallback block | Import from service or fallback module |
| Log helpers in core.py | Inline | Import from core.log_helpers |

Phase 1 is complete. Proceed to Phase 2 (route registration) when ready.
