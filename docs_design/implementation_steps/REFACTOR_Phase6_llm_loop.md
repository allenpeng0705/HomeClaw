# Core.py refactor — Phase 6: Extract answer_from_memory (llm_loop)

**Status:** Done  
**Branch:** refactor/core-multi-module (or as created)

## Goal

Move the entire `Core.answer_from_memory` implementation from `core/core.py` into `core/llm_loop.py` as a single async function `answer_from_memory(core, ...)`. Core keeps a thin wrapper that delegates. All callers (orchestrator, process_text_message, inbound handlers, etc.) still call `core.answer_from_memory(...)` and see unchanged behavior.

## Changes

### 1. New file: core/llm_loop.py

- **answer_from_memory(core, query, messages, app_id=None, user_name=None, user_id=None, agent_id=None, session_id=None, run_id=None, metadata=None, filters=None, limit=10, response_format=None, tools=None, tool_choice=None, logprobs=None, top_logprobs=None, parallel_tool_calls=None, deployment_id=None, extra_headers=None, functions=None, function_call=None, host=None, port=None, request=None) -> Optional[str]**

  Single async function containing the full LLM/tool loop logic:
  - Pending plugin retry (missing params)
  - Hybrid router (mix mode: heuristic, semantic, classifier/perplexity)
  - Workspace bootstrap, companion identity (who), system context (date/time, location)
  - Agent/daily memory (retrieval-first or legacy inject)
  - Skills (vector search, force-include, triggers)
  - RAG memory, knowledge base, profile, prompt manager
  - Plugins list (vector search, force-include), routing block
  - Optional compaction (memory flush, trim messages)
  - File/sandbox rules injection
  - Tool loop: LLM call, tool execution, mix fallback, route_to_plugin/remind_me/document fallbacks
  - Chat DB add, session pruning, final response

  All `self` references in the original method were replaced with `core` (first parameter). No import of `core.core`. Uses:
  - `core.log_helpers`: `_component_log`, `_truncate_for_log`, `_strip_leading_route_label`
  - `core.services.tool_helpers` or `core.tool_helpers_fallback`: `_parse_raw_tool_calls_from_content`, `_infer_remind_me_fallback`, `_remind_me_clarification_question`, `_remind_me_needs_clarification`, `_infer_route_to_plugin_fallback`, `_tool_result_usable_as_final_response`, `_tool_result_looks_like_error`
  - `base.*`, `memory.*`, `tools.builtin` (close_browser_session), etc.
  - `Path(__file__).resolve().parent.parent` in llm_loop yields project root (same as in core.py).

### 2. core/core.py

- **Import:** `from core.llm_loop import answer_from_memory as _answer_from_memory_fn`
- **Method:** `Core.answer_from_memory(self, ...)` replaced with a thin wrapper that returns `await _answer_from_memory_fn(self, query, messages, app_id=..., request=..., )`. Signature unchanged.

## Logic and stability

- **Logic:** The body was moved verbatim; only `self` → `core` and indentation (method body → function body) were changed. No behavior change.
- **Stability:** Same error handling (try/except, fallbacks). No new dependencies on core.core; llm_loop receives `core` as argument and calls `core.*` only.
- **Platforms:** No OS-specific code; works on macOS, Windows, Linux.

## Testing

- **Syntax:** `python3 -c "import ast; ast.parse(open('core/llm_loop.py').read())"` passes.
- **Unit:** `tests/test_core_refactor_phases2_4.py::test_llm_loop_module` checks that `core.llm_loop.answer_from_memory` exists and is an async function.  
  Note: Importing `core.llm_loop` pulls in base.util and other heavy deps; in environments where torch/OMP aborts, run with a filter or after fixing the env.
- **Manual:** Run Core, send one message (sync and stream), trigger a tool (e.g. remind_me, route_to_plugin), and confirm response and DB persist as before.

## Summary

Phase 6 extracts the large `answer_from_memory` implementation (~1580 lines) into `core/llm_loop.py`, reducing core.py size and isolating the LLM/tool loop. Core remains the single entry point; `core.answer_from_memory(...)` delegates to `llm_loop.answer_from_memory(core, ...)`.
