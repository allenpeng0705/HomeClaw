# Tool/Skill Selection: Plan Summary and Step-by-Step

One-page summary of the plan and how to implement it. For context see **ToolSelection_GeminiDiscussionReview.md** and **ToolSkillSelection_DesignAndDiscussion.md**.

---

## Principle

**Do not use tables, phrase lists, or regexes for intent logic when the LLM can do it** — we cannot list every phrasing, language, or edge case. Use the LLM (e.g. one short classification call for intent routing); maintain only **category → tool/skill set** mapping in config.

---

## RAG for skills and tools: off by default

- **RAG for skills** (`skills_use_vector_search`): already exists; **off by default** in config and code. Kept off because retrieval often selects wrong skills (cross-lingual, short query, similar descriptions).
- **RAG for tools**: when implemented, **reuse the existing skills RAG infrastructure** (same vector store pattern, embedder, sync/refresh). Add e.g. `tools_use_vector_search` (or `tools.use_vector_search` under `tools:`), **default false**. Same reason: we are not fully confident in RAG for skills and tools, so both stay **off by default** until retrieval quality is proven. Users can turn them on explicitly if they want to try.

---

## Plan Summary

| Phase | What | Why |
|-------|------|-----|
| **Phase 1** | Quick wins: constrain `skill_name`, "no tool/skill fits" instruction, negative few-shots, tighten descriptions | Low effort; improves selection without new pipeline. |
| **Phase 2** | Intent router (LLM): one short LLM call maps query → category; filter tools (and optionally skills) by category before main turn | Per-query narrowing; main model sees 3–10 tools instead of 30–70. No phrase tables. |
| **Phase 3** | After router: keep skill_name enum, negative examples, optional verification / RAG fallback | Refinements once router is in place. |

---

## Step-by-Step Implementation

### Phase 1 — Quick wins

| Step | Action | Where | Notes |
|------|--------|--------|-------|
| 1.1 | **Constrain `skill_name` in run_skill** | Where run_skill tool schema is built (e.g. `tools/builtin.py`) | When building the tool definition for the LLM, set `skill_name` parameter to an **enum** of the currently injected skill folder names (from `skills_list`). If skills_list is not available at tool-registration time, the schema may need to be built per-request in the LLM loop where skills_list is known. |
| 1.2 | **"No tool/skill fits" instruction** | System prompt in `core/llm_loop.py` (where tools/skills block is built) | Add one line: "If the user's request does not match any of the skills or tools above, do NOT call run_skill or any tool; reply in natural language." Optionally add a `no_tool_needed` tool and treat it as "no tool call, just reply." |
| 1.3 | **Negative few-shot examples** | `config/prompts/tools/selection_examples.yml` or system prompt | Add 2–3 examples: e.g. "When user says 'search the web' / '上网搜', do NOT use exec or tavily_crawl; use web_search." "When user asks for slides from a PDF, use skill html-slides (or ppt-generation for PPT)." |
| 1.4 | **Tighten descriptions** | `tools/builtin.py`, key SKILL.md files | Clarify when to use and when NOT to use (web_search vs tavily_crawl vs exec; folder_list; html-slides, ppt-generation). Text only. |

---

### Phase 2 — Intent router (LLM-based)

| Step | Action | Where | Notes |
|------|--------|--------|-------|
| 2.1 | **Define categories** | Config (e.g. under `intent_router` in skills_and_plugins.yml) or code | Fixed list, e.g.: `search_web`, `list_files`, `read_document`, `create_slides`, `schedule_remind`, `open_url`, `general_chat`, `coding`. |
| 2.2 | **Define category → tools (and optionally skills)** | Config or code | For each category: either a **tool profile** (reuse existing minimal/messaging/coding) or a **tool allowlist** (e.g. search_web → [web_search, fetch_url]). Optionally skill allowlist per category. No phrases — only category id and tool/skill set. |
| 2.3 | **Implement router module** | New file e.g. `base/intent_router.py` | Function `route(query: str, ..., config) -> str` (category id). Inside: one short LLM completion with prompt like "Classify this user message into exactly one category: [list]. Reply with only the category name." Parse reply (strip, lowercase, map to known category); on parse failure or timeout return `general_chat`. Use same model as main or a smaller/faster one (config). |
| 2.4 | **Call router in LLM loop** | `core/llm_loop.py` | Before building `all_tools`: if `intent_router.enabled`, call `category = intent_router.route(query, ...)`. Then filter tools by that category's profile or allowlist (reuse `filter_tools_by_profile` or implement allowlist filter). Optionally filter `skills_list` by category's skill list. Log category. |
| 2.5 | **Config** | `config/skills_and_plugins.yml` (or core) | Add `intent_router.enabled: true/false`, list of categories, and per-category tool profile or tool allowlist (and optional skill list). Fallback when disabled: current behavior (tool profile from config or full tools). |

---

### Phase 3 — After router (implemented)

| Step | Action | Where | Notes |
|------|--------|--------|-------|
| 3.1 | **Constrain skill_name to router output** | `core/llm_loop.py`, `base/intent_router.py` | Router is called once early. Per-category `skills: [folder1, ...]` in `category_tools` filters skills; `skill_name` enum is built from the (router-filtered) skills list. |
| 3.2 | **Optional: router fallback** | `base/intent_router.py` | On parse failure or exception, `route()` returns `general_chat`; llm_loop uses config profile for tools. Documented in module docstring. |
| 3.3 | **Optional: verification step** | `core/llm_loop.py`, `base/intent_router.py` | `intent_router.verify_tool_selection` + `verify_tools` (default exec, file_write). Before executing, one LLM call; if No, skip and return "Verification: tool selection did not match user intent; execution skipped." |
| 3.4 | **Optional: RAG for tools** | `base/tools_rag.py`, `core/llm_loop.py`, `core/initialization.py`, `core/core.py` | `tools.tools_use_vector_search` **default false**. Reuses same vector store/embedder pattern as skills: sync tool name+description to collection `homeclaw_tools`, retrieve by query; optional `tools_max_retrieved`, `tools_similarity_threshold`, `tools_refresh_on_startup`. Off by default like skills RAG. |

---

## Implementation order (recommended)

1. **Phase 1:** Do 1.1–1.4 (quick wins). No new pipeline; immediate benefit.
2. **Phase 2:** Do 2.1 → 2.2 (config/categories) → 2.3 (router module) → 2.4 (integration in loop) → 2.5 (config keys). Test with `intent_router.enabled: true` and a few categories.
3. **Phase 3:** Do 3.1 when router filters skills; add 3.2 (fallback); consider 3.3–3.4 as needed.

---

## Files to touch (checklist)

| File / area | Phase 1 | Phase 2 |
|-------------|---------|---------|
| `tools/builtin.py` | run_skill schema: skill_name enum (may need per-request build in llm_loop) | — |
| `core/llm_loop.py` | Add "no tool/skill fits" line; load selection_examples | Call intent_router.route(); filter tools/skills by category |
| `config/prompts/tools/selection_examples.yml` | Add negative examples | — |
| SKILL.md / tool descriptions | Tighten text | — |
| **New:** `base/intent_router.py` | — | route(query) → category via one LLM call; read config |
| `config/skills_and_plugins.yml` | — | intent_router.enabled, categories, category → tools/skills |
| `base/tool_profiles.py` | — | Reuse for category → profile; or add category → allowlist in config |

---

## Summary

- **Principle:** No phrase/table logic for intent; use LLM. Only maintain category → tool/skill set.
- **Phase 1:** Constrain skill_name, add "no tool fits" instruction, negative examples, better descriptions.
- **Phase 2:** LLM-based intent router (one classification call) → category → filter tools/skills → main turn with reduced set.
- **Phase 3:** Align skill_name enum with router; optional fallback, verification, RAG for tools.
