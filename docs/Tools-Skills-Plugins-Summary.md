# Tools, Skills, and Plugins — When and How We Use Them

This document summarizes how HomeClaw selects and uses **tools**, **skills**, and **plugins**, and whether the LLM can use **multiple tools or skills** in one task.

---

## 1. Tools

### What they are

- **Tools** are functions the LLM can call (OpenAI-compatible tool/function calling).
- Defined as `ToolDefinition` (name, description, parameters, `execute_async`).
- Registered at startup in `ToolRegistry` via `register_builtin_tools()` and optionally `register_routing_tools()`.
- Examples: `time`, `file_read`, `folder_list`, `document_read`, `web_search`, `remind_me`, `cron_schedule`, **`run_skill`**, **`route_to_plugin`**, `route_to_tam`, etc.

### When tools are used

- When **`use_tools`** is true in Core config (default: true), the registry’s tools are passed to the LLM as `tools=openai_tools` with **`tool_choice="auto"`**, so the **LLM decides** whether and which tools to call each turn.

### How we select which tools the LLM sees

1. **Base list**  
   `all_tools = registry.get_openai_tools()` — every registered tool the registry exposes.

2. **Friend preset (tools)**  
   If the current friend has a **preset** (e.g. `reminder`, `note`, `finder`) and that preset defines **`tools_preset`** (in `config/friend_presets.yml` or preset config), the list is **filtered** to only tool names in that preset:
   - **reminder**: `remind_me`, `record_date`, `recorded_events_list`, `cron_*`, `route_to_tam`.
   - **note**: `document_read`, `file_read`, `file_write`, `folder_list`, `file_find`, `save_result_page`, `get_file_view_link`.
   - **finder**: `file_find`, `folder_list`, `document_read`, `file_read`, `file_write`, `save_result_page`, `get_file_view_link`, **`run_skill`**, `web_search`.

   So **which tools are available depends on the friend’s preset** when one is set.

3. **Unified vs non‑unified**  
   - **Unified** (`orchestrator_unified_with_tools` true, default): `route_to_tam` and `route_to_plugin` **are** included.
   - **Non‑unified**: they are **removed** from the list, so the LLM only sees “normal” built-in tools.

4. **No extra query-based filtering**  
   We do **not** filter tools by user message (e.g. we don’t hide `run_skill` for “你好”). The LLM sees the (possibly preset-filtered) tool list and decides what to call.

---

## 2. Skills

### What they are

- **Skills** are capability modules: a folder with **SKILL.md** (name, description, keywords, trigger, body) and optionally a **scripts/** directory (e.g. `.py`, `.sh`, `.js`).
- The LLM uses skills only indirectly: by calling the **`run_skill`** tool with `skill_name` (and optionally `script`, `args`).

### When skills are used

- When **skills are enabled** (e.g. `use_skills` and skills dirs configured), we build an **“Available skills”** block and inject it into the **system prompt**.
- The **LLM** then decides when to call **`run_skill`** based on user intent and the skill descriptions/keywords in that block.
- **Special-case logic (our “if/else”)** only:
  - **Force-include rules** (`skills_force_include_rules` in config): when the user query matches a rule’s pattern, we **add** those skills to the list and can add **auto_invoke** (run a tool even if the model didn’t call it).
  - **Skill-driven triggers** (in each SKILL.md `trigger.patterns`): when the query matches, we add that skill and optionally an **auto_invoke** for `run_skill`.
  - Used for things like **reminder/scheduling** or “always run this skill when user says X”.

### How we select which skills appear in the prompt

1. **Skills directory list**  
   From `get_all_skills_dirs(...)` (main skills dir, external_skills_dir, skills_extra_dirs).

2. **Which skills are loaded**
   - **Vector search off** (`skills_use_vector_search` false): load **all** skills from those dirs (`load_skills_from_dirs`), minus disabled.
   - **Vector search on**: **RAG** over the skills index with the **current user query**; top hits (up to `skills_max_retrieved`) are loaded; if none, **fallback** to all from disk. Optionally **capped** by `skills_max_in_prompt`.

3. **Force-include (config)**  
   If the query matches a **skills_force_include_rules** pattern, the rule’s `folders` are added to the list and optional **instruction** / **auto_invoke** is applied.

4. **Skill-driven triggers**  
   For each skill with **trigger.patterns** in SKILL.md, if the **query** matches a pattern, that skill is added (if not already) and optional **instruction** / **auto_invoke** for `run_skill` is added.

5. **Friend preset (skills)**  
   If the friend’s preset has a **`skills`** list, we **filter** the current skills list to only those names. So a preset can restrict which skills the model sees.

6. **Build prompt block**  
   The final list is passed to **`build_skills_system_block(skills_list, ...)`**, which produces the “Available skills” section (names, descriptions, keywords, optionally body). **No** query-based filtering that removes skills; the LLM sees all skills in this list and decides when to call `run_skill`.

### Summary for skills

- **Selection**: Combination of (a) all-from-dirs or RAG-by-query, (b) force-include rules, (c) skill trigger patterns, (d) friend preset filter.
- **Use**: **LLM-driven** via `run_skill`; we only force-include/auto-invoke for **special cases** (e.g. reminder/scheduling).

---

## 3. Plugins

### What they are

- **Plugins** are external modules (e.g. homeclaw-browser, PPT) registered with the Core **plugin manager**.
- The LLM uses them only via the **`route_to_plugin`** tool (`plugin_id`, `capability_id`, `parameters`).

### When plugins are used

- When **unified** mode is on, **`route_to_plugin`** is in the tool list and the system prompt includes an **“Available plugins”** list (id + description).
- The **LLM** decides when to call **`route_to_plugin`** based on user intent and that list.

### How we select which plugins appear in the prompt

1. **Base list**
   - **Vector search off**: **All** plugins from `plugin_manager.get_plugin_list_for_prompt()`.
   - **Vector search on**: **RAG** by query; if no hits, **fallback** to all; then cap by `plugins_max_in_prompt`.

2. **Force-include**
   - **plugins_force_include_rules**: if the query matches a rule pattern, those plugin IDs are added.
   - **skills_force_include_rules** can also specify **plugins: [id, ...]**; those IDs are added to the plugin list.

3. **Friend preset (plugins)**  
   If the preset has a **`plugins`** list, we **filter** the plugin list to only those IDs.

4. **Routing block**  
   The final list is rendered in the **“Routing (choose one)”** block so the model sees “Available plugins” and when to use **`route_to_plugin`** (e.g. browser, PPT, node camera).

### Summary for plugins

- **Selection**: All or RAG + force-include (config + skills rules) + friend preset filter.
- **Use**: **LLM-driven** via **`route_to_plugin`**.

---

## 4. Multi-tool and multi-skill usage in one task

### Multiple tools in one LLM response

- The LLM can return **multiple `tool_calls`** in a **single** assistant message.
- The code does **`for tc in tool_calls:`** and executes **each** tool in turn, appending each result as a separate `role: tool` message.
- So in **one turn** the model can call several tools (e.g. `folder_list` then `document_read` then `save_result_page`).

### Multiple rounds (multi-turn tool loop)

- **`max_tool_rounds = 10`**: we keep calling the LLM with the conversation + tool results until the model returns **no** `tool_calls` (only content) or we hit 10 rounds.
- So for **one user task**, the LLM can:
  - Use **multiple tools in one reply** (e.g. two tools in one turn).
  - Use **multiple rounds** (e.g. call `file_find` → get result → call `document_read` → get result → call `run_skill` or `save_result_page`).

### Multiple skills in one task

- **Yes.** The model can:
  - Call **`run_skill`** multiple times in one turn (if it returns multiple tool_calls).
  - Call **`run_skill`** in one round and other tools in the next (or vice versa).
  - Combine **`run_skill`** with **`document_read`**, **`file_write`**, **`save_result_page`**, etc., across rounds.
- Instruction-only skills (no `scripts/`) are documented as “call `run_skill(skill_name)` then **continue in the same turn**” (e.g. document_read → generate → save_result_page); the multi-round loop supports that.

### Tools vs skills vs plugins in one task

- The same conversation can mix:
  - **Tools**: e.g. `time`, `folder_list`, `document_read`, `remind_me`, `run_skill`, `route_to_plugin`.
  - **Skills**: via **`run_skill`** (one or more skills, one or more times).
  - **Plugins**: via **`route_to_plugin`** (e.g. browser then run_skill for slides).
- So the LLM **can** use **multiple skills and/or tools (and optionally plugins)** for a single user request, within the 10-round limit and tool list it sees.

---

## 5. Quick reference

| Layer        | What the LLM sees                    | Who selects? | Multi-use in one task? |
|-------------|--------------------------------------|--------------|-------------------------|
| **Tools**   | OpenAI-style tool list               | Registry + friend preset + unified flag | Yes: multiple tool_calls per turn + up to 10 rounds |
| **Skills**  | “Available skills” block in system   | Dirs + RAG/load + force-include + skill triggers + friend preset | Yes: via multiple `run_skill` calls / rounds |
| **Plugins** | “Available plugins” in routing block | Plugin manager + RAG/load + force-include + friend preset | Yes: via multiple `route_to_plugin` calls / rounds |

- **Selection**: We **build** the tool list and the skill/plugin **prompt sections**; the **LLM** then **chooses** what to call.
- **Special cases**: Force-include and **auto_invoke** (and skill trigger patterns) are the only “if/else” that **force** a skill/tool to run when the model didn’t call it; used mainly for reminder/scheduling and similar.
