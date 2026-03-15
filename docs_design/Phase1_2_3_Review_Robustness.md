# Phase 1, 2, 3 — robustness review

Review to ensure logic is correct, stable, robust, and **never crashes**. All identified issues have been fixed.

---

## 1. Intent router (`base/intent_router.py`)

| Area | Change |
|------|--------|
| **route()** | Return `"general_chat"` if `config` is missing or not a dict. Build `categories` inside try/except; on exception use `DEFAULT_CATEGORIES`. Normalize categories with `c is not None` check. |
| **include_turns / max_chars** | Parse with try/except; on `TypeError`/`ValueError` use 0 and 300. |
| **_format_recent_context** | Only process items that are dicts (`isinstance(m, dict)`). Wrap loop in try/except; on exception return "" so prompt still builds. |
| **_format_categories_for_prompt** | If `config` is not a dict, treat as `{}`. Wrap in try/except; on exception return comma‑joined categories. |
| **get_tools_filter_for_category** | Full try/except; return None on any exception. Require `config` to be dict and `category` to be str. Use `str(k)` for keys; guard `cat_key` empty. |
| **get_skills_filter_for_category** | Wrapped in try/except; return None on exception. Use `s is not None` in list comp. |
| **verify_tool_selection** | If `completion_fn` is None, return True (allow execution). Use safe `query_safe`/`args_safe`; check `callable(completion_fn)` before calling. |

---

## 2. Phase 1.1 — run_skill enum (`core/llm_loop.py`)

| Issue | Fix |
|-------|-----|
| Mutating a local `props` when `params.get("properties")` was missing never updated the tool dict. | Always set `params["properties"] = props` and `fn["parameters"] = params` after patching so the tool dict is updated. |
| Non-dict `t`, `fn`, or `params` could cause AttributeError. | Check `isinstance(t, dict)`, `isinstance(fn, dict)`, and build safe `params`/`props` (default to `{}`). |
| Any exception in the block could crash the loop. | Whole Phase 1.1 block wrapped in try/except; on exception log and skip patch. |

---

## 3. Phase 1.2 — “no tool fits” instruction

| Issue | Fix |
|-------|-----|
| `get_core_metadata()` or getattr could raise. | Wrapped in try/except; on exception skip appending the block (no crash). |

---

## 4. Phase 3.1 — category skills filter

| Issue | Fix |
|-------|-----|
| `s.get(...)` on non-dict skill item could raise. | Iterate with `isinstance(s, dict)`; non-dicts kept in list (no filter). |
| `get_skills_filter_for_category` or list comp could raise. | Full try/except; on exception log and leave `skills_list` unchanged. |
| None or non-string in `_cat_skills`. | Use `s is not None and str(s).strip()` in set comprehension. |

---

## 5. Phase 2/3 — tool filter by category

| Issue | Fix |
|-------|-----|
| `get_tools_filter_for_category` or `get_tools_for_llm` or list comp could raise. | Whole block in try/except; on exception fall back to `get_tools_for_llm(_tool_defs, tools_cfg_for_desc)`. |
| `_cat_filter` not a dict. | Check `isinstance(_cat_filter, dict)` before using `.get()`. |
| None in `_cat_filter["tools"]`. | Use `n is not None and str(n).strip()` in set comp. |

---

## 6. Intent router config in LLM loop

| Issue | Fix |
|-------|-----|
| `get_core_metadata()` could return non-dict `intent_router_config`. | After getattr, enforce `_intent_router_config = {}` when `not isinstance(_intent_router_config, dict)`. |
| Phase 3.3 verification reading config. | Build `_verify_cfg` / `_verify_tools` in try/except; use `_ir_cfg` only if dict; ensure `_verify_tools` is list/tuple. |

---

## 7. Tools RAG (`base/tools_rag.py`)

| Issue | Fix |
|-------|-----|
| `vector_store.search` could return None; `for r in results` would crash. | Iterate over `(results or [])`. |
| Result item without `.score` or non-numeric score. | Each result handled in try/except; `float(dist)` in try; on `TypeError`/`ValueError` continue. |
| Access to `r.payload` when payload is not dict. | Use `(getattr(r, "payload") or {}).get("name")` after isinstance check. |

---

## 8. General principles applied

- **Router and filters:** On any exception, fall back to safe behavior (e.g. `"general_chat"`, full tools, or skip optional step).
- **Type guards:** Check `isinstance(..., dict)` (or list) before using `.get()` or iterating.
- **None and empty:** Use `(x or [])`, `(x or {})`, `x is not None and str(x).strip()` where needed.
- **Numeric config:** Parse int/float in try/except; use sensible defaults on error.
- **Mutation:** When patching nested structures, ensure the mutated object is written back so the parent dict is updated.
- **Logging:** Use `logger.debug(...)` for fallbacks so failures are visible without crashing.

All touched paths are intended to be crash-safe and to degrade gracefully under bad config or unexpected data.

---

## 9. Multi-category and tools_always_included (review)

| Area | Safeguard |
|------|------------|
| **_intent_router_categories parsing** | Built from `(_intent_router_category or "").split(",")` with `if (c or "").strip()` so empty list or empty strings are not kept. |
| **Skills: single vs multi-category** | Only use `_intent_router_categories[0]` when `len(_intent_router_categories) == 1` and `_intent_router_categories[0]` is truthy; else set `_cat_skills = None` so we don’t index empty list or pass None to get_skills_filter_for_category. |
| **Tools: single vs multi-category** | Same pattern: use `[0]` only when `len == 1` and first element truthy; else `_cat_filter = None` so we fall through to `get_tools_for_llm(_tool_defs, tools_cfg_for_desc)`. |
| **_tool_defs_filtered never None** | After the tool-filter try/except and tools_always_included block, if `_tool_defs_filtered is None` we set it to `_tool_defs if isinstance(_tool_defs, list) else []` so later `len(_tool_defs_filtered)` and iteration never crash. |
| **Log line** | Only run `len(_tool_defs_filtered) < len(_tool_defs)` when both are lists to avoid TypeError. |
| **tools_always_included** | Entire block in try/except; use `isinstance(_intent_router_config, dict)` before `.get()`; require `isinstance(_always, list)` and `_tool_defs_filtered is not None`; use `getattr(t, "name", None)`; build new list with `list(_tool_defs_filtered) + [...]` so we don’t mutate a shared reference. |
| **intent_router.get_tools_filter_for_categories** | Already wrapped in try/except; returns None on exception; iterates with `if not cat or not isinstance(cat, str)`; `get_tool_names_for_profile` returns list (never raises). |
| **intent_router.get_skills_filter_for_categories** | Same: try/except, None on exception; safe iteration. |
| **tool_profiles.get_tool_names_for_profile** | Returns `[]` for None/empty profile, non-str profile, or "full"; uses `isinstance(m, dict)`; iterates safely over `m.items()`. |
