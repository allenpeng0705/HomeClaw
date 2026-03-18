# Preset Friends vs Intent Router, DAG, and Plan-Executor

This document describes how **preset AI friends** (Reminder, Note, Finder, Cursor, etc.) interact with **intent_router**, **categories**, **DAG**, and **Plan-Executor**, and whether the preset implementation needs to be upgraded.

---

## 1. Current behavior (no change in flow order)

### 1.1 Request flow

1. **Intent router** runs first (when enabled) and classifies the user message into one or more **categories** (e.g. `schedule_remind`, `general_chat`, `send_email`).
2. **Category → tools:** `category_tools` (or profile) for that category defines which tools are allowed → `_tool_defs_filtered`.
3. **OpenAI tool list:** `all_tools` is built from `_tool_defs_filtered` (category-filtered tool defs converted to OpenAI format).
4. **Friend preset:** If the current friend has a **preset** with `tools_preset`, `all_tools` is **further filtered** to only tool names in that preset’s list. So the LLM sees the **intersection** of (category-allowed tools) and (preset-allowed tools).
5. **Planner / DAG:** `openai_tools` (and thus `_pe_tool_names`) is set from this **final** `all_tools` (after preset filter). So the Plan-Executor and DAG only see and use **preset-filtered** tool names when the friend has a preset.

So: **preset always wins as a further restriction.** Category filtering happens first; preset filtering is applied on top. DAG and Plan-Executor already use the same preset-filtered list.

### 1.2 Skills and plugins

- **Skills:** Filtered by intent_router category (Phase 3.1), then by friend preset’s `skills` list if present.
- **Plugins:** Same idea: category doesn’t filter plugins today; preset’s `plugins` list restricts which plugins are in the routing block.

So preset friends already get the correct restricted context (tools, skills, plugins, memory_sources, system_prompt, etc.) and **DAG/Planner use the same restricted tool set**.

---

## 2. Do we need to upgrade?

### 2.1 Current design is consistent

- **Reminder** + “remind me in 5 min” → category `schedule_remind` → category tools include remind_me, cron_* → preset “reminder” allows the same → LLM and DAG see only reminder tools. Correct.
- **Reminder** + “send an email” → category `send_email` → category would allow run_skill, etc., but **preset** restricts to reminder tools only → run_skill is not in the list → DAG for send_email would not have run_skill; we fall back to ReAct and the Reminder assistant (with only reminder tools) cannot send email. That is **intended**: preset friends are specialized.
- **Cursor** friend → pure bridge: no LLM; message is sent directly to Cursor Bridge (run_agent), which runs the Cursor CLI agent with the message as the task.

So the **current implementation does not need a mandatory upgrade** for correctness: preset filtering is applied after category filtering, and Planner/DAG already use the preset-filtered tools.

### 2.2 Optional upgrades (improve clarity or performance)

| Option | What | Pros | Cons |
|--------|------|------|------|
| **A. Skip intent_router when friend has preset** | If `friend.preset` is set and preset has `tools_preset`, do not call the intent router; use **only** preset tools/skills/plugins (and no category-based DAG for that request). | One fewer LLM call for preset friends; preset behavior is independent of router; no edge cases where category adds tools the preset doesn’t want. | Preset friends never use category-specific DAG flows (e.g. if we later added a “reminder DAG” we’d skip it). For Reminder/Note/Cursor we don’t rely on DAG today, so acceptable. |
| **B. Preset category_allowlist** | In preset config, optional `category_allowlist: [schedule_remind]`. If intent_router returns a category not in the list, immediately return a fixed message (“I’m the Reminder assistant; I only handle reminders.”) without calling the main LLM. | Saves tokens and latency when user asks the wrong friend something off-topic. | New config surface; need to maintain allowlist per preset. |
| **C. Document only** | No code change; document in `FriendConfigFrameworkImplementation.md` and/or `Tools-Skills-Plugins-Summary.md` that (1) tools = category ∩ preset, (2) DAG/Planner use preset-filtered tools. | No risk; clarifies behavior for future changes. | No behavioral or performance improvement. |

**Recommendation:**

- **Short term:** Do **C** (document the interaction). No code change; behavior is already correct.
- **Later, if desired:** Add **A** (skip intent_router when friend has a preset with `tools_preset`) to make preset friends fully independent of the router and save one LLM call per request for those friends. Option **B** can be added on top if you want a cheap “wrong friend” reply.

---

## 3. Implementation sketch for Option A (skip intent_router for preset)

If we adopt Option A later:

- After resolving `_current_friend` and `preset_name`, if `preset_name` is non-empty and `get_friend_preset_config(preset_name)` has a `tools_preset` (or non-empty `tools` list), set a flag e.g. `_preset_strict_tools = True`.
- When `_preset_strict_tools` is True:
  - Do **not** call `intent_router_route(...)` (or treat as “no category”).
  - Do **not** apply category_tools; build `_tool_defs_filtered` from the full registry, then apply **only** the preset tool filter (so the LLM sees exactly the preset’s tools).
  - Skip DAG/Planner for category (no `_intent_router_categories`), so the request is handled by ReAct with preset tools only.

No change to preset YAML schema is required for A; only the order of operations in `llm_loop.py` (conditional skip of intent_router when preset is strict).

---

## 4. Cursor friend: pure bridge (no LLM)

For the **Cursor** preset friend, the LLM is **not involved**. Core forwards the user message directly to the Cursor Bridge and returns the plugin result.

- **When:** Friend preset is `cursor` and the request has a non-empty message.
- **How:** Core picks capability and parameters by pattern (no LLM): **open_project** ("open X project", "open &lt;path&gt;", "open X in cursor"), **open_file** ("open file &lt;path&gt;"), **run_command** ("run npm/pip/...", "execute &lt;command&gt;"), **run_agent** (everything else). Then `route_to_plugin(plugin_id="cursor-bridge", capability_id=..., parameters=...)` and return the plugin result. No intent router, no skills/tools injection, no LLM call.
- **Bridge behavior:** open_project/open_file open in Cursor IDE; run_command runs a shell command; run_agent runs Cursor CLI agent with the message as the task (`agent -p "&lt;message&gt;"`).
- **Fallback:** If the bridge call raises, Core logs and continues (the request would then go through the normal flow; in practice the Cursor preset is only used with the bridge).

---

## 5. Summary

| Question | Answer |
|----------|--------|
| Are preset tools and intent_router/DAG/Planner already aligned? | Yes. Tools = category ∩ preset; DAG and Plan-Executor use the same preset-filtered list. |
| Is an upgrade **required**? | No. Current behavior is correct and consistent. |
| Cursor: LLM involved? | No. Message is routed by pattern to open_project / open_file / run_command / run_agent, then bridged to Cursor Bridge. |
| Suggested next step | Document the interaction (Option C). Optionally later: skip intent_router for preset friends (Option A) to save one LLM call and keep preset behavior independent of router. |
