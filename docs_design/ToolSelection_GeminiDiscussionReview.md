# Tool/Skill Selection: Review of Gemini Discussion

This document reviews the ideas from the user's discussion with Gemini about fixing wrong tool/skill selection in HomeClaw, and compares them with our current implementation.

---

## Gemini's Five Ideas (Summary)

1. **Router–Specialist (Intent Router + Targeted Toolset)**  
   Use a small/fast model to categorize high-level intent (e.g. Home_Automation, Information_Retrieval). Then give the main model only 3–5 tools for that category. Fewer tools → better selection.

2. **Pydantic / Structured Output Enforcement**  
   Use enums for parameters (e.g. `room_name` as enum, not free string). Use JSON Mode / Function Calling for cloud; for local models use Outlines or Guidance to force valid schema output.

3. **Few-Shot Semantic Library (RAG for Tools)**  
   Store tool descriptions in a vector DB. At query time, retrieve the top 3–5 most relevant tools by semantic similarity and inject only those into the prompt. Keeps the context clean.

4. **Negative Constraints and "Not-Found" Tool**  
   Add an explicit tool like `no_relevant_tool_found` and instruct the model: "If none of the tools fit, you MUST call this." Add negative examples: "When user says X, do NOT use Tool A; use Tool B because [reason]."

5. **Multi-Step Validation (Self-Correction)**  
   After the model selects a tool, run a verification step (secondary prompt or logic): "Does user intent match this tool?" If no, ask the model to re-select before executing.

---

## Comparison with Our Current Implementation

| Gemini idea | What we have today | Gap / opportunity |
|-------------|--------------------|--------------------|
| **1. Router–Specialist / Targeted toolset** | **Tool profiles** (`tools.profile`: minimal, messaging, coding, full) and **skills_filter**. We narrow the tool/skill set by **config**, not by a separate router model. Same goal (fewer tools), different mechanism. | Gemini's **Intent Router**: a small/fast model (or rules) categorizes the query (e.g. Home_Automation, Information_Retrieval), then we give the main model only tools for that category. We could add this: router outputs category → we filter tools by profile/allowlist for that category. |
| **2. Structured output / enums** | We use OpenAI-style function/tool calling with JSON Schema in `ToolDefinition`. Parameters are typically free-form strings. We do **not** use enums in tool schemas or constrained generation (Outlines/Guidance) for local models. | **Gap:** We could add **enums** in tool parameter schemas where the set is fixed (e.g. provider, room_name). For local models, we could explore **constrained decoding** (e.g. grammar/GBNF) so only valid tool calls are produced — we already have some Qwen/GBNF support. |
| **3. RAG for tools** | We have **skills_use_vector_search** (RAG for skills): embed skill descriptions, retrieve by query, inject top-N skills. We **do not** have RAG for **tools**. Tools are either all or filtered by profile. | **Opportunity:** Add **tools_use_vector_search** (or similar): embed tool name+description, retrieve top-K tools by query similarity, inject only those. This would give "3–5 relevant tools per query" without an intent router. Reuse existing vector store / embedder. |
| **4. Negative constraints / no_relevant_tool** | We have **routing rules** in the system prompt (e.g. "Do NOT use tavily_crawl or exec for search; use web_search only") and **force-include** instructions. We do **not** have an explicit `no_relevant_tool_found` (or similar) tool. We have **tool_selection_examples** (few-shot) but not necessarily "Goldilocks" negative examples. | **Opportunity:** (a) Add a tool like **no_tool_needed** or **no_relevant_tool_found** and instruct the model to call it when no tool fits. (b) Expand **selection_examples** (or prompt) with explicit negative examples: "When user says X, do NOT use A; use B because …". |
| **5. Multi-step validation** | We **do not** run a verification step before executing a tool. We execute the selected tool and, in some cases, handle errors or mix-mode fallback after the fact. | **Opportunity:** For high-stakes or ambiguous cases, add an optional **verification** step: before execution, ask a small/secondary model or the same model: "User asked: …; selected tool: X. Does this match? Yes/No." If No, re-prompt for a new tool choice. This adds latency and cost; use only when needed (e.g. exec, destructive tools) or behind a config flag. |

---

## Summary Table (Gemini vs HomeClaw)

| Strategy | Our status | Possible next step |
|----------|------------|--------------------|
| Targeted toolset | ✅ Tool profiles + skills_filter (config-based) | Optional: intent router (model or rules) → category → profile |
| RAG for tools | ❌ Not implemented | Reuse **existing skills RAG** infra; add tools_use_vector_search, **default false**. Both skills and tools RAG off by default (low confidence in retrieval). |
| Structured output / enums | ⚠️ Schema only; no enums/constraints | Enums in schema; optional constrained decoding for local |
| Negative examples + no_tool | ⚠️ Some routing rules; no "no tool" tool | no_relevant_tool_found tool + more negative few-shots |
| Verification before execution | ❌ | Optional verification step for selected tool (config or per-tool) |

---

## Recommended Order of Implementation (if we extend)

1. **RAG for tools** — Reuse **existing skills RAG** (same vector store, embedder): embed tool name+description, retrieve by query, inject top-K. Add config e.g. `tools_use_vector_search`, **default false**. Both skills and tools RAG off by default; turn on only when confident in retrieval.
2. **Negative examples + no_tool** — Add `no_tool_needed` (or similar) and 2–3 clear negative examples in selection_examples or system prompt. Low effort, can reduce wrong tool choice.
3. **Enums in tool schemas** — Where we have a fixed set (e.g. search provider, file type), add enum in JSON Schema so the model sees allowed values.
4. **Optional verification** — Add a config flag (e.g. for exec or "sensitive" tools) to run a quick verification LLM call before execution. Use sparingly to avoid latency.
5. **Intent router (optional)** — If we still see wrong selection after 1–2, consider a lightweight intent classifier (small model or rules) that outputs a category and we map category → tool profile or tool subset.

---

## Relation to Our Design Doc

Our **ToolSkillSelection_DesignAndDiscussion.md** chose the **OpenClaw-style** approach: no config-driven intent table; **narrow the set** (profiles + skills_filter) and **strong descriptions**. Gemini's ideas are compatible:

- **Targeted toolset** → we do it via profiles/skills_filter; Gemini adds "intent router" as one way to choose the set.
- **RAG for tools** → same idea as "narrow the set," but **query-dependent** (top-K by similarity) instead of fixed profile. Could be an optional layer on top of profiles.
- **Negative constraints / no_tool / verification** → improvements to **how** we prompt and validate, not a change to the "no big intent config" principle.

So we can adopt Gemini's suggestions incrementally (RAG for tools, no_tool, negative examples, enums, optional verification) without reverting to a large config-driven intent → tool table.

---

## How About Skills?

The same ideas apply to **skill** selection. The model chooses when to call **run_skill(skill_name=..., ...)** from the list of skills we inject. Here is the comparison for skills specifically.

### RAG for skills: off in practice

We have **skills_use_vector_search** (RAG for skills) in code, but in practice it is **not turned on** because the correct skills are often **not** selected: retrieval by semantic similarity to the query frequently returns the wrong skills or misses the right one. So we rely on **all skills** (or **skills_filter**) and let the model choose from the full (or filtered) list, rather than a RAG-retrieved subset.

Possible reasons RAG for skills underperforms:

- **Short or cross-lingual queries** — e.g. Chinese "总结PDF做幻灯片" vs English skill descriptions; embedding similarity is weak.
- **Threshold and K** — similarity threshold too high → no skills; too low → noisy set. Top-K too small → right skill dropped; too large → long list again.
- **What is embedded** — if we only embed name + description, we can miss "when to use" nuance that lives in the body.
- **Similar descriptions** — e.g. html-slides vs ppt-generation both "generate slides"; retrieval may not distinguish intent.

So for skills, **targeted set by config (skills_filter)** is currently more reliable than **query-dependent RAG**. The doc below still describes RAG as an option; treat it as "available but not recommended until retrieval quality is improved."

### What we have for skills today

| Mechanism | Purpose |
|-----------|---------|
| **skills_use_vector_search** | RAG for skills (in code). **Off in practice** — correct skills often not selected; see above. |
| **skills_filter** | OpenClaw-style: when set, only these skill folder names are in the prompt. **Preferred** when you want a smaller set. |
| **skills_include_body_for** | For listed skills, include SKILL.md body so the model has full "When to use" / workflow. |
| **skills_force_include_rules** | When query matches a pattern, ensure certain skills are in the list and optionally add an instruction or auto_invoke. |
| **Friend preset** | Per-friend "skills" list can further restrict which skills are in the prompt. |
| **Strong descriptions** | SKILL.md frontmatter (name, description) + body; model picks from that. |

So for skills we rely on: **targeted set** (skills_filter + friend preset) and, when not using RAG, **all skills** in the prompt. We do **not** have: an explicit "no skill fits" option, negative few-shots for skills, or verification before run_skill.

### Gemini-style ideas applied to skills

| Idea | For skills today | Gap / opportunity |
|------|------------------|--------------------|
| **1. Targeted set** | ✅ RAG + skills_filter + friend preset. We already narrow the skill list. | Optional: intent router that outputs a "skill category" and we filter skills by category (same as for tools). |
| **2. Structured output** | run_skill has `skill_name` (string), `script`, `args`. The model can hallucinate a skill name not in the list. | We could constrain **skill_name** to the set of injected skill folders (enum in schema or post-validate and reject). Reduces "wrong skill" or non-existent skill. |
| **3. RAG for skills** | ⚠️ **skills_use_vector_search** exists but is **off** — retrieval often selects wrong skills. We use all skills or **skills_filter** instead. | To make RAG useful: better embeddings / include body in index, cross-lingual support, threshold tuning, or hybrid "RAG then intersect with skills_filter." Until then, prefer skills_filter. |
| **4. Negative constraints / "no skill"** | We have force-include rules and instructions. We do **not** tell the model "if no skill fits, say so" or "do NOT use skill A for intent X; use B." | (a) In the run_skill / skills block, add: "If the user's request does not match any of the skills above, do NOT call run_skill; reply in natural language." (b) Add negative few-shots: "When user says X, do NOT use skill A; use skill B because …". (c) Optionally a **no_skill_needed** tool or a clear instruction that "no tool call" is valid when no skill fits. |
| **5. Verification** | We do not verify "does user intent match this skill?" before executing run_skill. | Optional: before running run_skill, a quick check (prompt or logic): "User asked: …; selected skill: X. Does this match? Yes/No." Re-prompt if No. Useful when skills are many or similar (e.g. html-slides vs ppt-generation). |

### Suggested next steps for skills

1. **Constrain skill_name** — When building the run_skill tool schema, set `skill_name` to an enum of the injected skill folder names (or validate after parsing and reject invalid names). Prevents calling non-existent or wrong skills.
2. **Negative examples for skills** — In the system prompt or selection_examples, add 1–2 lines: "When user asks for [slides from a PDF], use skill html-slides, not ppt-generation." / "When user asks for [general search], do not use a skill; use web_search."
3. **Explicit "no skill fits" instruction** — In the skills block or tool instructions: "If none of the listed skills apply to the user's request, do not call run_skill; answer using other tools or in natural language."
4. **Optional verification for run_skill** — Config flag or only when many skills: before executing run_skill, ask the model (or a small checker): "Does the user intent match skill X?" and re-select if not.

Skills today benefit from **skills_filter** (and friend preset) for a targeted set; **RAG is off** because it often picks the wrong skills. The main improvements are **constraining skill_name**, **negative examples**, and an explicit **"no skill fits"** instruction, with optional **verification** for difficult cases. If we want query-dependent skill narrowing in the future, we need to improve retrieval (embeddings, what we index, threshold, or hybrid with filter) before turning RAG for skills back on.

---

## What We Can Do Next (Prioritized)

Concrete next steps, ordered by impact vs effort. Pick one or two to implement first.

### Quick wins (low effort, clear benefit)

1. **Constrain `skill_name` in run_skill**  
   When building the run_skill tool schema for the LLM, set `skill_name` to an **enum** of the currently injected skill folder names (from `skills_list`). Prevents the model from calling a non-existent or typo'd skill. Implement in the place that builds the run_skill tool definition (e.g. tools/builtin.py or wherever the schema is built).

2. **"No skill fits" + "No tool fits" instructions**  
   In the system prompt (skills block and/or tools section), add one line: *"If the user's request does not match any of the skills [or tools] above, do NOT call run_skill [or any tool]; reply in natural language or with the most relevant tool only."* Optionally add a **no_tool_needed** tool that the model can call when nothing fits (and we treat it as "no tool call, just reply").

3. **Negative few-shot examples**  
   Add 2–3 negative examples to `config/prompts/tools/selection_examples.yml` (or the system prompt): e.g. *"When user says 'search the web' / '上网搜', do NOT use exec or tavily_crawl; use web_search."* / *"When user asks for slides from a PDF, use skill html-slides (or ppt-generation for PPT), not a generic summarizer."* Helps both tools and skills.

4. **Tighten tool and skill descriptions**  
   Review `tools/builtin.py` and key SKILL.md files: make descriptions unambiguous (when to use / when NOT to use). Especially for web_search vs tavily_crawl vs exec, folder_list, and high-use skills (html-slides, ppt-generation). No code change beyond text.

### Medium effort (higher impact)

5. **RAG for tools**  
   Reuse the skills RAG pattern: embed tool name+description, store in vector DB (or reuse existing collection with a namespace). At request time, retrieve top-K tools by query similarity and inject only those. Fallback: if RAG returns too few or fails, use profile or all tools. Gives query-dependent tool set without an intent router. **Note:** If retrieval for tools is as weak as for skills (cross-lingual, short query), consider making it optional and A/B testing.

6. **Enums in tool schemas**  
   Where a tool has a fixed set of options (e.g. search provider, file type), add `enum` in the JSON Schema for that parameter so the model sees allowed values and is less likely to hallucinate.

7. **Hybrid RAG for skills (if we want RAG again)**  
   Before turning `skills_use_vector_search` back on: (a) include body (or "when to use" section) in the embedded text; (b) try cross-lingual embeddings or query expansion; (c) use **skills_filter** as a pre-filter so RAG retrieves only from that list (smaller index, less noise). Then re-enable and tune threshold/K.

### Optional (when needed)

8. **Optional verification step**  
   Config flag (e.g. `tools.verify_before_execute`) or only for sensitive tools (exec, file_write): before executing the selected tool, one short LLM call: *"User asked: …; selected tool: X. Does this match? Yes/No."* If No, re-prompt for a new selection. Adds latency; use sparingly.

9. **Intent router (Gemini's suggestion)**  
   Gemini's "Router–Specialist" idea: use a small/fast model (or rules) to categorize high-level intent (e.g. Information_Retrieval, System_Control), then pass only the 3–5 tools for that category to the main model. In our terms: lightweight classifier or rule-based mapping query → category, then category → tool profile or tool allowlist. Consider only if wrong selection persists after 1–5.

---

**Suggested order:** Start with **1 (constrain skill_name)** and **2 (no skill/tool fits instruction)** and **3 (negative examples)** — all low effort. Then try **5 (RAG for tools)** if you want query-dependent tools, or **6 (enums)** for clearer parameters. Leave 7–9 for when you hit specific pain points.

---

## Replan: Intent Router as a Core Step

Because the **Intent router** (Gemini's Router–Specialist idea) may be important, we replan with it as a central piece: query-dependent narrowing of the tool (and optionally skill) set *before* the main model sees the list.

### Why the Intent router matters

- Today we narrow by **config** (fixed profile or skills_filter). The model still sees the same set for every request in that session.
- An **Intent router** narrows **per query**: "user said X → category → only tools/skills for that category." So the main model gets 3–10 relevant tools instead of 30–70, which directly targets wrong tool/skill selection.
- We implement the router with the **LLM** (one short classification call). We avoid phrase tables and keyword lists for intent logic — we cannot list everything.

### Phased plan

**Phase 1 — Quick wins (do first)**  
Same as above: constrain `skill_name`, "no tool/skill fits" instruction, negative few-shot examples, tighten descriptions. Low effort, no new pipeline.

**Phase 2 — Intent router (Gemini), LLM-based**

1. **Define categories**  
   Examples: `search_web`, `list_files`, `read_document`, `create_slides`, `schedule_remind`, `open_url`, `general_chat`, `coding`. Each category has a clear meaning and a dedicated tool set.

2. **Define mapping: category → tools (and optionally skills)**  
   - Reuse existing **tool profiles** where possible: e.g. `search_web` → profile `minimal` (only web_search, folder_list, run_skill, …) or a small **allowlist** (e.g. web_search, fetch_url).
   - Or add **category → tool allowlist** in config/code (e.g. `intent_router.categories.search_web.tools: [web_search, fetch_url]`). Same idea for skills: `search_web` → no skills or a small list.

3. **Router: query → category (LLM only)**  
   We **do not** use phrase tables, keyword lists, or regexes for intent routing — we cannot list every phrasing, language, or edge case. Use the **LLM** to map query → category.

   One short LLM call *before* the main turn: send the user message and a fixed prompt, e.g. "Classify this user message into exactly one category: search_web, list_files, read_document, create_slides, schedule_remind, open_url, general_chat, coding. Reply with only the category name." Parse the reply → category, then filter tools/skills by that category and run the main turn with the reduced set. Handles paraphrases and mixed language without maintaining any phrase list.

4. **Integration in LLM loop**  
   - Before building the tool list: call `intent_router.route(query)` → get `category` from one short LLM classification call.
   - If category is not `general_chat`: filter tools by that category's profile or allowlist (reuse `filter_tools_by_profile` or a new allowlist filter). Optionally filter skills by category.
   - Pass the reduced tool (and skill) list to the main model. Log category for debugging.

5. **Config**  
   - e.g. `intent_router.enabled: true`, category list, and category → tool profile or allowlist (and optional skill list). No phrase tables. Fallback when disabled: current behavior (config profile or full).

**Phase 3 — After router is in place**

- **Constrain skill_name** to the skills actually in the prompt (router may have reduced them).
- **Negative examples** and "no tool fits" still help the main model choose within the reduced set.
- **Optional:** RAG or embedding-based fallback for category if the router LLM fails or times out.
- **Optional:** RAG for tools as an alternative or complement to router (query → top-K tools); can be compared to router-based narrowing.

### What we need to implement (Phase 2)

| Piece | Where | Description |
|-------|--------|-------------|
| Categories + tool/skill set per category | Config or code | Category id → tool profile or tool allowlist (and optional skill list). No phrases. |
| Router (LLM) | e.g. `base/intent_router.py` | One short LLM call: "Classify into one of [categories]. Reply with only the category." Parse reply → category. Use same model as main or a smaller/faster one. |
| Use router in loop | `core/llm_loop.py` | Before building `all_tools`: if router enabled, `category = route(query)` (LLM); then filter tools (and optionally skills) by category. |

**Principle:** We do **not** use tables, phrase lists, or regexes for intent logic when the LLM can do it — we cannot list every phrasing, language, or edge case. Use the LLM for query → category; we only maintain the **category → tool/skill set** mapping.
