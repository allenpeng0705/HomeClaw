# Tool Selection & Execution: Discussion (Gemini + HomeClaw)

This doc summarizes the Gemini discussion and maps it to HomeClaw’s current behavior, then lists options to consider before implementing.

---

## 1. What HomeClaw Already Does

| Gemini idea | HomeClaw today |
|-------------|----------------|
| **Two-stage: category then tools** | **Intent router**: one LLM call (or embedding-based) → category (e.g. `create_slides`, `read_document`). Then tools/skills are filtered by that category’s `profile` or `tools`/`skills` in `skills_and_plugins.yml` → only 11–20 tools in prompt, not 72. |
| **Avoid “all tools every turn”** | We reduce tools by **category** (deterministic filter), not by RAG. So we’re already doing “classifier + inject only that category.” |
| **Constrain tool names (no hallucination)** | **Qwen 3.5 / Qwen3 xLAM**: GBNF grammar forces valid tool names (and structure) when tools are present. Other backends use OpenAI-style `tool_choice` + schema. |
| **Predictable sequences (e.g. A → B)** | **Partial**: after instruction-only `run_skill` we restrict to `save_result_page`, `file_write`, `document_read`, `file_read`, `web_search` so the model doesn’t loop on `run_skill`. Not a full DAG; more like “allowed set for next turn.” |

So: **category-based filtering** and **grammar for tool names** are already in place. The remaining pain is (a) still sending full tool *definitions* (names + descriptions + params) every turn, and (b) the model sometimes choosing poor follow-ups (e.g. repeated `web_search` instead of `save_result_page`).

---

## 2. What We Tried and Why It’s Off

- **Tool RAG** (`tools_use_vector_search`): Off by default. Same as skills RAG: semantic search often picks the wrong tools (e.g. “cold” → weather instead of smart plug). Config comment: “RAG for tools often selects wrong tools.”
- **Skills RAG** (`skills_use_vector_search`): Off by default; same stability concern.

So we rely on **intent router + category → allowlist** rather than RAG for tool/skill selection.

---

## 3. Gemini’s Suggestions vs Our Context

### 3.1 Planner–Executor (plan once, execute steps)

- **Idea**: One “planner” call (cloud or large model) produces a JSON plan (steps + tool + args). A small/local model or a pure executor loop runs each step; only on error do we re-plan.
- **Pros**: Full tool definitions sent once (to planner). Execution turns can send only the current step’s tool (or name + args), so much smaller context and fewer “what next?” decisions for the local model.
- **Cons**: Plan can be wrong or brittle (e.g. wrong path, wrong tool). Dynamic flows (“if document_read fails, try file_understand”) need re-plan or conditional logic. We’d need a clear JSON schema and a way to pass tool results into the next step.
- **Fit for HomeClaw**: The design is **Planner–Executor for all intents** (default path whenever tools are needed). One planning call → JSON plan; robust executor runs steps; fallback to ReAct on plan failure. See `PlannerExecutorAndDAG.md` for the full spec (validation, re-plan, DAG for known flows).

### 3.2 Skeleton selection (names + one line, then full schema for chosen tool)

- **Idea**: Turn 1: send only tool **names** + one-sentence summary → LLM picks `tool_x`. Turn 2: send full schema for `tool_x` only → LLM fills args, we execute.
- **Pros**: Big token saving on the “selection” turn; small model sees a short list.
- **Cons**: Two LLM calls per tool decision; latency and cost. For “document_read then run_skill then save_result_page” we’d have 2×3 = 6 calls instead of 3. Needs careful UX (e.g. don’t show “thinking” twice per tool).

### 3.3 Prompt caching (KV cache)

- **Idea**: System prompt + tool definitions are static; only conversation and tool results change. Cache the static part so the model doesn’t re-process it every turn.
- **HomeClaw**: We don’t currently control prompt caching in the agent loop. llama.cpp (and many servers) can cache on their side; we’d need to (1) keep system + tool block in a fixed format and (2) ensure the inference backend actually caches (e.g. via `cache_prompt` or similar if the API supports it). **Low code impact, high gain** if the server supports it—worth checking our HTTP client and server config.

### 3.4 Tool dependency DAG

- **Idea**: Define “after Tool A, only Tool B/C are valid” so we don’t need the LLM to “decide” every step.
- **HomeClaw**: We have a **soft** version: after instruction-only `run_skill`, we restrict to a fixed set. A full DAG would mean a schema (e.g. in skill YAML or a separate file) like `document_read → [run_skill, file_understand]`, `run_skill(html-slides) → [save_result_page, file_write]`. Execution would be a state machine. **Medium complexity**, good for reducing redundant tool choices and loops.

---

## 4. What Would Help the “Wrong Tool” Problem (e.g. web_search after run_skill)

The logs show the model calling `web_search` repeatedly after instruction-only `run_skill` (and sometimes never calling `save_result_page`). We already:

- Added instruction text: “Do NOT call web_search for this task—use only the document content above” and “You MUST call save_result_page or file_write… before replying.”
- Restrict allowed tools after run_skill to `save_result_page`, `file_write`, `document_read`, `file_read`, `web_search`.

So we **allowed** `web_search` in the restricted set for skills that need it; but for html-slides we *don’t* need it, and the model still prefers it. Options:

1. **Per-skill “allowed_after_run”**: In the skill’s config or instruction, list tools allowed after run (e.g. html-slides: only `save_result_page`, `file_write`). Then we restrict to that list instead of the global list. So for html-slides we’d **remove** `web_search` from the allowed set after run_skill.
2. **Stronger instruction only**: Keep current allowed set but make the instruction even more explicit (“For this skill do not use web_search. Use only document content and then save_result_page.”). Cheapest; may still be ignored by small models.
3. **Planner–Executor for this path**: For “create_slides” intent, planner outputs steps: `[document_read, run_skill(html-slides), save_result_page]`. Executor runs them in order; no “choose next tool” for those steps. Re-plan only on error.

---

## 5. Recommended Order to Explore (before coding)

1. **Prompt caching**  
   Check whether the local/cloud inference path sends a stable “system + tools” block and whether the server supports caching. If yes, enable it (config or API). No change to tool selection logic.

2. **Per-skill “allowed_after_run”**  
   Define for instruction-only skills (e.g. html-slides, ppt-generation) a small allowlist for the turn after run_skill. For html-slides: `[save_result_page, file_write]` (and optionally `document_read`, `file_read` if we want wrong-order recovery). Remove `web_search` for that skill so the model can’t wander. Small code change in `llm_loop` + config/skill metadata.

3. **Planner–Executor as the default for all intents**  
   Design a JSON schema for “plan” (goal, steps with tool + args). Use planner whenever tools are needed; config can **skip** planning for specific categories (e.g. `skip_planner_for_categories: [general_chat]`). One planning call (cloud/large) → plan; robust executor runs steps (validate plan, re-plan on error, fallback to ReAct on plan failure). See `PlannerExecutorAndDAG.md`. Bigger change but addresses “heavy prompt every turn” and “model picks wrong tool” for all intents.

4. **DAG / state machine for known flows**  
   Later: define explicit tool chains for high-value flows (e.g. document_read → run_skill → save_result_page) so we don’t rely on the LLM for every step. Complements planner or replaces it for fixed workflows.

---

## 6. Summary

- We **already** do two-stage (intent → category → filter tools) and grammar-constrained tool names; RAG for tools/skills is off on purpose.
- To reduce load and improve behavior we can, in order: **(1)** enable prompt caching if the stack supports it, **(2)** add per-skill `allowed_after_run` so we don’t offer `web_search` after html-slides, **(3)** add an optional planner–executor mode for selected intents, **(4)** consider DAG/state machine for fixed workflows.

If you want to implement one of these next, the smallest high-impact step is **(2) per-skill allowed_after_run** (and optionally tightening the instruction text further). The planner–executor is the largest but addresses both token weight and wrong-tool issues for multi-step tasks.
