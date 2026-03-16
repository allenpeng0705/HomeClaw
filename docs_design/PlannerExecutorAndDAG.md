# Planner–Executor and DAG for HomeClaw

This doc specifies the **Planner–Executor** and **DAG / state machine** approach for tool flows. The Planner–Executor is the **default for all intents**: one planning call, then a robust executor. DAG is for fixed known flows that can skip the planner.

---

## 1. Goals

- **Planner–Executor (all intents)**: For every request that needs tools, run a **planning** phase (cloud/large model) once → JSON plan (steps + tool + args). Then a small/local model or dumb executor runs steps with only the current step’s tool in context. Re-plan on error. **Default path for all intents**; make it strong and robust so we cut token load and wrong-tool choices everywhere.
- **DAG / state machine**: Explicit chains for known flows (e.g. `document_read → run_skill → save_result_page`). When a flow is defined for a category, we can run the DAG instead of the planner for that request. Complements the planner; does not replace it for “all intents.”

---

## 2. Planner–Executor (default for all intents)

### 2.1 When to use it

- **Default: all intents.** Whenever the request is not “greeting-only” and tools are enabled, use Planner–Executor. No per-category allowlist for planning; the planner sees the intent category and full tool list and produces a plan for any task.
- **Opt-out only**: Config can **skip** planning for specific categories (e.g. pure chat with no tools), e.g. `skip_planner_for_categories: [general_chat]` when the router says “no tools needed” or for very short greetings. If the request needs tools, we still use the planner regardless of category.
- **Fallback to ReAct**: If planning fails (planner unavailable, invalid JSON, validation error, or empty plan), **fall back to the current ReAct loop** so the user always gets a response. Planner–Executor must be robust: validate plans, enforce limits, and never block the user.

### 2.2 Which tools/skills the planner sees (category coverage)

- **Guaranteeing the category has all needed tools/skills:** The planner is given the **same** tool and skill set as the ReAct loop: intent router category (or multi-category union) → `category_tools` + skills filter, plus `tools_always_included`. So the plan only references tools/skills the executor is allowed to run. We do **not** give the planner the full tool list and then restrict at execution time; that would require re-plan or fallback when the plan uses a forbidden tool.
- **Coverage:** Rely on (1) **multi-category** so the router can return e.g. `search_web, list_files` when the user needs both, (2) **tools_always_included** so narrow categories still get e.g. `save_result_page`, `folder_list`, and (3) **fallback to ReAct** when planning fails or the request is too open-ended. See `docs_design/IntentRouter_CategoriesCoverage.md` for full coverage, fallbacks, and how to handle **new tools** and **new skills** (new tools need `TOOL_PROFILES` and/or `category_tools`; new skills are auto-available for categories without an explicit `skills` list, otherwise add the skill folder to the category’s `skills` in config).

### 2.3 Planning phase

- **Model**: Prefer cloud or larger local model (“architect”). Use existing `_resolve_llm` or a dedicated `planner_llm` config.
- **Input**: User message (+ optional short context: last turn or intent category). **Tool definitions**: the **category-filtered** tool list and skill list (same as ReAct for this turn), sent **once** to the planner.
- **Output**: A single structured JSON **plan** (see schema below). No execution in this call.

### 2.4 Plan JSON schema (example)

```json
{
  "goal": "Summarize the user's PDF and produce HTML slides",
  "steps": [
    {
      "id": "1",
      "tool": "document_read",
      "arguments": { "path": "documents/norm-v4.pdf" },
      "optional": false
    },
    {
      "id": "2",
      "tool": "run_skill",
      "arguments": { "skill_name": "html-slides-1.0.0" },
      "optional": false
    },
    {
      "id": "3",
      "tool": "save_result_page",
      "arguments": {
        "title": "Summary slides",
        "content": "<from_step_2_or_model>",
        "format": "html"
      },
      "optional": false,
      "note": "Use content from step 2 result; generate full HTML if only instruction was returned"
    }
  ],
  "requires_final_summary": true
}
```

- **goal**: Short description (for logging and re-plan prompts).
- **steps**: Ordered list. Each step has:
  - **id**: String (e.g. "1", "2") for referencing in re-plan or errors.
  - **tool**: Tool name (must match a registered tool).
  - **arguments**: Object; may include placeholders like `"<from_step_1>"` or “generate from previous result” to be resolved by executor or a small LLM.
- **optional**: If true, failure of this step does not force re-plan (e.g. skip and continue).
- **requires_final_summary**: If true, after all steps run, send results to LLM once for a short user-facing summary.

Placeholders in `arguments` can be resolved by:
- **Dumb executor**: Replace `<from_step_N>` with the raw text result of step N.
- **Light LLM**: One small call per step that needs “generate content from step N” (e.g. step 3: “Given step 2 output, fill save_result_page content”).

### 2.5 Execution phase

- **Loop**: For each step in `steps`:
  1. Resolve arguments (replace placeholders with prior step results).
  2. Execute the tool (same as current tool execution path).
  3. Append tool result to an execution log (step_id, tool, args, result).
  4. On **error** (or configurable “unexpected” result): optionally **re-plan** (call planner again with: goal + execution log + last error; get new plan from current step or from start).
  5. If step is **optional** and fails, log and continue; otherwise on failure either re-plan or break and return error to user.
- **Context for “fill-in” LLM (if used)**: Only the current step’s tool definition + prior step results. No full tool list. Reduces tokens and wrong-tool choices.

### 2.5a How step results are handled (no LLM between steps)

After each step finishes, we get a **result** (string output from the tool). Here is how we use it:

1. **Store**  
   The result is saved in `step_results[step_id]`. Used for later steps, re-plan, and final summary.

2. **Placeholder replacement (no LLM)**  
   Before running the **next** step, we resolve placeholders in that step's `arguments`. Any `<from_step_1>` or `<from_step_2>` is **replaced by the raw text** of that step's result. This is simple string substitution; **no LLM is called** with the previous step's result.  
   Example: step 3 has `"content": "<from_step_2>"` → we set `content` to the exact string from step 2, then call the tool.

3. **When we do use an LLM**  
   - **Before** execution: the **planner** (user message + tool list).  
   - **On failure**: **re-plan** (goal + execution log including step results + error).  
   - **After all steps**: **final-summary** (goal + execution log → short reply).  
   So step results are fed into re-plan and final-summary, but **not** into a per-step LLM during execution.

4. **Do we need an LLM with the previous step's result?**  
   **Currently: no.** For flows like document_read → run_skill → save_result_page with `content: "<from_step_2>"`, the executor substitutes the raw result.  
   **Optional future:** A "fill-in" LLM could generate a **derived** value (e.g. title or summary) from a long step result for one step. Not implemented today.

**Summary:** Step results are used only for (a) placeholder substitution in later steps, (b) re-plan on failure, and (c) final-summary. No LLM is involved between steps.

### 2.6 Re-plan conditions

- Tool returned an error (e.g. file not found, timeout).
- Tool returned a sentinel (e.g. “content too short”; could be configured).
- Max steps or max re-plans exceeded.
- Optional: “Unexpected” result (e.g. empty content when content was required).

Re-plan input: original goal + `steps` so far + last tool name + last error/result. Planner returns a new plan (can be “retry step N”, “skip to step N”, or a new step list).

### 2.7 Robustness (make it strong)

- **Plan validation**: Before execution, validate the plan: every `tool` is a registered tool name; `arguments` keys match the tool’s schema; step ids unique; step count ≤ `max_steps_per_plan`. If invalid, either ask planner once more with “invalid plan” feedback or **fall back to ReAct**.
- **Planning failure**: If the planner call fails (timeout, parse error, empty/malformed JSON), **fall back to ReAct** immediately. User must never be stuck.
- **Executor limits**: Enforce timeouts per step (reuse `tool_timeout_seconds`); optional retry once per step before re-plan; cap total steps per request so a bad plan cannot loop forever.
- **Re-plan limits**: Cap `max_replans` (e.g. 2). After that, either continue with remaining steps (if any), or return partial results + error message, or fall back to ReAct for the remainder.
- **Optional steps**: If a step is marked `optional` and it fails, log and continue; do not re-plan unless required for correctness.
- **Final summary**: Prefer always generating a short user-facing reply from the execution log (with or without tools in that call) so the user gets a clear outcome even when some steps failed.

### 2.8 Final summary (optional)

If `requires_final_summary` is true: one LLM call with execution log (and optionally last user message) to produce a short natural-language reply (e.g. “I’ve created the slides and here’s the link.”). No tools in this call.

### 2.9 Config (example)

```yaml
# config/skills_and_plugins.yml or core.yml
planner_executor:
  enabled: true
  # Default: use planner for ALL intents. Only skip for these categories (e.g. when no tools needed).
  skip_planner_for_categories: [general_chat]
  planner_llm: null   # null = use main_llm or cloud fallback; prefer cloud/large for quality
  max_steps_per_plan: 12
  max_replans: 2
  re_plan_on_error: true
  requires_final_summary: true
  # Fallback: if planning fails (timeout, invalid plan), use current ReAct loop
  fallback_to_react_on_plan_failure: true
```

### 2.10 How it works (step by step)

From user message to final response, the planner–executor path runs as follows. If anything fails, the system **falls back to the normal ReAct loop** so the user always gets a reply.

1. **Config and intent**
   - Read `planner_executor.enabled` and `skip_planner_for_categories`.
   - Intent router has already run → we have one or more categories (e.g. `create_slides`, `read_document`).
   - If planner is **disabled**, or the category is in the skip list, **do not use planner** → continue with the normal ReAct tool loop.

2. **Planning (one LLM call)**
   - Build a prompt: user message, intent category, and the **category-filtered** list of tools and skills (same set ReAct would see).
   - Call the planner LLM (e.g. `planner_llm` or main model). Ask for a single JSON object: `goal`, `steps` (each with `id`, `tool`, `arguments`, `optional`), and optional `requires_final_summary`.
   - Parse the response (extract JSON, handle markdown wrapping). **Validate**: every step’s `tool` is in the allowed list, step count ≤ `max_steps_per_plan`, step ids unique.
   - If **parsing or validation fails** → no plan → **fall back to ReAct** (user is not blocked).

3. **Execution (no LLM for tool choice)**
   - For each step in the plan, in order:
     - **Resolve placeholders** in `arguments`: replace `<from_step_N>` with the text result of step N (from the current run or from a previous run after re-plan).
     - **Run the tool**: call the same tool registry as ReAct (`execute_async(tool_name, args, context)`).
     - Store the result under the step’s `id` for later steps and for re-plan/summary.
   - If a step **fails** (tool error or exception):
     - If the step is **optional** → log and **continue** to the next step.
     - Otherwise → go to **re-plan** (step 4) or, if re-plan is not possible or exhausted, **fall back to ReAct** with the error.

4. **Re-plan (on step failure, optional)**
   - If `re_plan_on_error` is true and re-plan count &lt; `max_replans`: build a **re-plan prompt** with the original goal, execution log (steps that ran and their results), and the failed step + error.
   - Call the planner again (same LLM). Get a **new** plan (e.g. retry with different args, skip a step, or a shorter sequence).
   - Parse and validate the new plan. If valid, **resume execution** from step 3 with the new plan, passing current `step_results` so placeholders like `<from_step_1>` still work.
   - If re-plan fails or we’ve already done `max_replans` re-plans → **fall back to ReAct**.

5. **Final summary (optional)**
   - After **all** steps succeed: if the plan has `requires_final_summary` and config allows it, make **one more LLM call** (no tools) with the goal, a short execution log, and the user’s request. The model returns a short natural-language reply (e.g. “I’ve created the slides; here’s the link.”).
   - If that call fails or returns nothing → use the **last step’s result** (e.g. the link) as the reply.

6. **Respond to the user**
   - If the executor **succeeded** (with or without final summary): that reply is the **final response**; the ReAct tool loop is **skipped** for this turn.
   - If the executor **failed** or we never got a valid plan: the **ReAct loop** runs as usual (LLM + tools in a loop until the model replies or max rounds).

**In short:** Plan once (1–2) → Execute steps in order (3) → Re-plan on failure if allowed (4) → Optionally summarize (5) → Return result or fall back to ReAct (6). No step is allowed to block the user; every failure path leads to ReAct or a clear error message.

---

## 3. DAG / state machine (known flows)

### 3.1 Purpose

For **fully predictable** flows, avoid the planner and the per-step LLM: define a fixed chain of tools and (optionally) argument templates. Executor runs the chain; only “fill-in” (e.g. path, title) might need one small LLM or user input.

### 3.2 Flow definition (example)

Define in config or a small DSL/YAML:

```yaml
# Example: create_html_slides flow (HTML slides only; differs from ppt-generation)
flows:
  create_html_slides:
    trigger: category  # or intent_router category
    category: create_html_slides
    steps:
      - tool: document_read
        args_from:
          path: [user_message_path, "documents/"]   # from user or default
      - tool: run_skill
        args:
          skill_name: html-slides-1.0.0
      - tool: save_result_page
        args_from:
          title: [llm_from_step_2, "Summary slides"]
          content: [result_of_step_2]
          format: "html"
```

- **trigger**: `category` (when intent router returns this category) or `pattern` (user message match).
- **steps**: Ordered list. Each step: **tool**, **args** (fixed) or **args_from** (from user, from prior step result, or “llm_from_step_N” for one tiny LLM call to fill a field).

### 3.3 Execution

- When the flow triggers, run steps in order. No “what next?” LLM call.
- **args_from** resolution: `user_message_path` = extract path from user message (existing logic); `result_of_step_N` = raw result of step N; `llm_from_step_N` = one short LLM call with step N result to generate a field (e.g. title).
- On error: optional fallback to ReAct loop or re-plan (as in planner–executor).

### 3.3a One generic executor — no new code per flow

**You do not need to add new code for each DAG.** A single generic executor runs any flow defined in config. Adding a new flow = add a new entry under `planner_executor.flows` in YAML (category, steps with tool, args, args_from). Supported args_from source types (fixed set): **user_message_path**, **user_message_path_pdf**, **user_message_folder**, **user_message_text**, **result_of_step_N**, **llm_from_step_N**, **llm_markdown_from_step_N**. Optional per-step: **run_only_if_previous_step_longer_than: N** (skip step when previous result length &lt; N). Optional per-flow: **when_step_skipped_return_summary_of_previous: true** (when a step is skipped, LLM-summarize the previous result and return it; e.g. search_web: short result → summarize and reply, long result → save_result_page and return link). New code is only needed when you introduce a new source type (e.g. current_date, env:VAR).

### 3.4 Relation to planner

- **Planner is default for all intents.** DAG is an optimization for known flows.
- **Option A (recommended)**: DAG first for category. If a flow is defined for the intent category, run the DAG (no planner call); else **run planner** (for any intent). If planner fails, fall back to ReAct.
- **Option B**: Always run planner. For categories that have a DAG, executor can optionally “lock” the plan to the DAG steps for extra robustness (same steps, less variance).
- So: **Planner–Executor = default path for every intent**; DAG = optional shortcut when we have a fixed flow for that category.

---

## 4. Implementation order (step-by-step, flag-controlled)

Implement incrementally; each phase is gated by `planner_executor.enabled` in config. When `enabled: false` (default), behavior is unchanged (ReAct only).

| Phase | What | Flag / behavior |
|-------|------|------------------|
| **1** | Config + branch point | Add `planner_executor` config (in `skills_and_plugins.yml` and `planner_executor_config` in metadata). In `llm_loop`, after intent router: if `enabled` and category not in `skip_planner_for_categories` → set `_use_planner_executor`; when tools are used, log and **continue to ReAct**. No behavior change. **Done.** |
| **2** | Planning only | In the branch: call a **planner** (build prompt with user message, category, category-filtered tools/skills; one LLM call; parse JSON plan). Validate plan (tool names, step count ≤ max). Log plan; still **execute via ReAct** (so we can test planning without changing execution). **Done** (`base/planner_executor.py` + call in `llm_loop`). |
| **3** | Executor loop | When plan is valid: run **executor** (loop steps, resolve placeholders, execute each tool via existing tool path, collect results). On success: use last result as response and skip ReAct. On step error: fall back to ReAct. **Done** (`run_executor` in `base/planner_executor.py`). |
| **4** | Re-plan + fallback | On step error: call planner again with goal + execution log + error; get new plan; resume executor (or from start). Enforce `max_replans`. On plan failure (timeout, invalid JSON, validation): **fall back to ReAct** so user always gets a response. **Done** (`call_replan`, `run_executor` re-plan loop in `base/planner_executor.py`; llm_loop passes `completion_fn`, `config`, `tool_names`). |
| **5** | Final summary (optional) | If plan has `requires_final_summary`: one LLM call with execution log → short user-facing reply. **Done** (`call_final_summary`, `build_final_summary_messages` in `base/planner_executor.py`; run_executor calls it on success when plan + config request it). |
| **DAG** | Fixed flows | When a flow exists for the category, run DAG instead of planner (no planner call). **Done** (`flows` under `planner_executor` in config; `get_flow_for_categories`, `run_dag`, `_resolve_flow_step_args` in `base/planner_executor.py`; llm_loop runs DAG first, then planner, then ReAct). |

**Config (Phase 1 in place):** `planner_executor.enabled: false` in `config/skills_and_plugins.yml`. Set `enabled: true` when Phase 2 (or later) is ready to run. Other keys: `skip_planner_for_categories`, `planner_llm`, `max_steps_per_plan`, `max_replans`, `fallback_to_react_on_plan_failure`.

---

## 5. Files to touch (high level)

- **Config**: `skills_and_plugins.yml` or `core.yml` for `planner_executor` (e.g. `enabled`, `skip_planner_for_categories`, `fallback_to_react_on_plan_failure`) and `flows`.
- **Core loop**: `core/llm_loop.py` — after intent router: if flow defined for category → run DAG; else if planner enabled and category not in skip list → call planner, validate plan, run executor (with ReAct fallback on failure); else current ReAct.
- **Planner**: New module or function to build planner prompt, call LLM, parse JSON plan (with validation).
- **Executor**: New module or functions: run step, resolve placeholders, append to log, decide re-plan.
- **DAG**: Load flow definitions; implement args_from (user path, result_of_step_N, optional llm_from_step_N).

---

## 6. Summary

- **Planner–Executor is for all intents**: Default path whenever tools are needed. One planning call (cloud/large) → JSON plan; robust executor runs steps with minimal context; re-plan on error; fallback to ReAct on plan failure. Strong and robust so it can be the main path everywhere.
- **DAG**: Optional fixed chains for known flows; when a flow exists for the category, run it (no planner); else use planner. Complements the planner; does not replace “planner for all.”
- This doc is the spec for implementing the “silver bullet” when you’re ready; no code changes until you adopt it.
