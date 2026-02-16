# Tools, Skills, and Plugins: What They Are and How the LLM Decides

This doc clarifies the **three extension layers** (Tools, Skills, Plugins), how each is presented to the LLM when **orchestrator_unified_with_tools: true**, how the LLM chooses between **route_to_tam**, **route_to_plugin**, and **tools/skills**, and how they could be refined (including whether plugins can use tools).

---

## 1. Summary table

| Layer | What it is | How the LLM sees it | How the LLM invokes it | Who runs it |
|-------|------------|----------------------|-------------------------|-------------|
| **Tools** | Native, callable capabilities (file, exec, memory, time, browser, etc.) and **routing** (route_to_tam, route_to_plugin). | **Tool registry** → OpenAI-compatible tool schemas (name, description, parameters) sent with every chat completion. Plus **TOOLS.md** (workspace) as human-readable “what you can do” in the system prompt. | LLM returns a **tool_call** (name + arguments). Core executes via the tool registry and appends the result; loop continues or ends. | Core (tool executor in Core process). |
| **Skills** | Application-style capabilities: each skill is a **folder** with **SKILL.md** (name + description) and optional **scripts/** (e.g. run.sh, main.py). | **Skills block** in system prompt: “## Available skills” + list of “**name**: description”. No separate tool schema beyond **run_skill** (one tool for all skills). | LLM calls **run_skill(skill_name, script, args)** when the task fits a skill’s description. | Core runs the **script** (sandboxed, allowlist in config). |
| **Plugins** | Independent **feature bundles**: one plugin = one focus (e.g. Weather, News, Quotes). Each has **config.yml** (id, description) and a **Python** `run()` method. | **Routing block** in system prompt: “## Routing” + “If it clearly matches one of these plugins, call route_to_plugin(plugin_id)” + “Available plugins: **plugin_id**: description”. Plus **route_to_plugin** tool schema. | LLM calls **route_to_plugin(plugin_id)** when the user intent clearly matches a plugin’s description. | Core calls **plugin.run()**; plugin uses Core interface (LLM, channel, chat) and its own logic (HTTP, config). |

So:

- **Tools** = low-level, native capabilities + routing; LLM chooses by **tool name + parameters** (schemas in the API).
- **Skills** = catalog of “applications” (scripts); LLM chooses by **skill name + script** via the single **run_skill** tool and the **skills block** in the prompt.
- **Plugins** = dedicated features selected by **plugin_id**; LLM chooses by **route_to_plugin(plugin_id)** using the **routing block** (plugin list) in the prompt.

---

## 2. What each layer is and what it’s for

### 2.1 Tools

- **Target:** Native capabilities of the “local” environment (Core process): files, exec, memory (RAG), time, reminders, cron, browser, web search, sessions, channel send, **and** routing (TAM, plugins).
- **What they can do:** Anything the executor implements: read/write files, run allowlisted commands, call LLM, search memory, schedule reminders, open URLs, run scripts via **run_skill**, **route_to_tam**, **route_to_plugin**, etc.
- **Injection:**
  - **Tool registry** → every registered tool becomes an OpenAI-style tool (name, description, parameters) sent to the LLM in the chat completion request.
  - **TOOLS.md** (workspace) → optional human-readable “Tools / capabilities” block in the system prompt (identity, agents, then tools). Helps the model answer “what can you do?” and when to use which tool; actual execution is still via tool_calls.
- **Refinement:** Tools are the **atomic** layer. They don’t “call” skills or plugins directly; the LLM calls **route_to_plugin** or **run_skill**, and Core runs the plugin or skill script. So tools are the interface the LLM uses to trigger plugins and skills.

### 2.2 Skills

- **Target:** Application-level capabilities that are **described** in the prompt. A skill is an “app” whose implementation is **the LLM using tools** (and optionally **run_skill(script)** to run a script). So skills are **tool-driven apps**: they can only do what the **tool set** allows (browser, file_read, cron, memory_search, etc.).
- **What they can do:** Whatever the **tools** can do. The LLM reads SKILL.md (name, description, and often a body that says “use browser, web_fetch, cron, …”) and **calls those tools** to accomplish the workflow. So the skill has **no separate runtime**—the “runtime” is the LLM + tool loop. Optionally the skill has a `scripts/` folder; then the LLM can also call **run_skill(skill_name, script, …)** to run a script; that script runs in a subprocess and **does not** call Core tools (it’s standalone).
- **Injection:**
  - **Skills block** in system prompt: loaded from **skills_dir** (e.g. config/skills/), each subfolder with **SKILL.md** → “## Available skills” + “- **name**: description” (and optionally body). So the LLM sees a **list of skills and descriptions** in the prompt and uses that to decide when to follow a skill workflow (by calling the right tools) or when to call **run_skill**.
  - **run_skill** is a **single tool** in the registry. The LLM uses it to run a script from a skill’s `scripts/` folder when the task fits that script.
- **Refinement:** Skills = **tool-bound apps** (LLM + tools). Plugins = **code-bound apps** (plugin.run() in Python, no tool layer). So: **Skills can only do what tools allow; plugins can do anything the developer codes.**

#### How skills register what they can do and how Core selects them

1. **Register (declare) what the skill can do**  
   Put a skill **folder** under **skills_dir** (e.g. `config/skills/`). The folder name is the **skill_id** used by **run_skill** (e.g. `social-media-agent-1.0.0`, `example`). Inside the folder, add **SKILL.md** with:
   - **YAML frontmatter** between `---` and `---`: at least **name** and **description**.
   - Optional **body**: instructions for the LLM (e.g. “use browser, web_fetch, cron…”).
   - Example:
     ```yaml
     ---
     name: social-media-agent
     description: Autonomous social media management for X/Twitter using only HomeClaw native tools...
     ---
     # Body: usage notes, which tools to use, etc.
     ```
   There is **no** separate “skill registry” in code. Registration = having a folder with **SKILL.md** under **skills_dir**. Optional: add a **scripts/** subfolder with allowlisted scripts (e.g. `run.sh`, `main.py`) that **run_skill** can execute.

2. **How Core knows about skills**  
   When building the system prompt (in **answer_from_memory**), if **use_skills** is true in config, Core:
   - Resolves **skills_dir** from config (e.g. `config/skills`).
   - Calls **load_skills(skills_dir)** → scans for subdirs that contain **SKILL.md**, parses each file (frontmatter + body), returns a list of dicts: `name`, `description`, `body` (optional), `path` (folder path).
   - Calls **build_skills_system_block(skills_list)** → builds a string `"## Available skills\n\n- **name**: description\n..."` (and optionally body). When the folder name differs from the frontmatter `name`, the block shows `(run_skill skill_name: \`folder\`)` so the LLM knows what to pass to **run_skill**. That string is appended to **system_parts**, so the LLM sees it in the system message.

3. **How the LLM selects skills**  
   - **For “follow this workflow” (no script):** The LLM reads the **Available skills** block (name + description, and body if included). When the user request matches a skill’s description, the LLM **uses tools** as described in the skill (e.g. browser, cron, file_read). No **run_skill** call; the skill is just guidance.
   - **For “run a script”:** When a skill has a **scripts/** folder and the task fits, the LLM calls **run_skill(skill_name, script, args)**. **skill_name** must be the **folder name** under skills_dir (e.g. `social-media-agent-1.0.0`, `example`), not only the frontmatter `name`. The **run_skill** tool schema (and, if present, the folder name in the skills block) tells the LLM which `skill_name` to use.

4. **When skills run**  
   - **Workflow-style:** The skill “runs” when the LLM **uses tools** in that turn (or over several turns) according to the skill’s description/body. There is no single “run skill” call; it’s just the normal tool loop.
   - **Script-style:** The skill’s script runs when the LLM calls **run_skill(skill_name, script, …)** and Core executes the script (subprocess, sandboxed under the skill folder, allowlist from config). So “when” = **when the LLM chooses the run_skill tool** with that skill_name and script.

**Summary:** Skills register by **folder + SKILL.md** under skills_dir. Core discovers them at **request time** (load_skills → skills block in the prompt). The LLM selects by **matching the user request to the skill’s name/description** and either follows the workflow (using tools) or calls **run_skill(folder_name, script)**. Skills run when the LLM uses tools for the workflow or when it calls run_skill for a script.

### 2.3 Plugins

- **Target:** One plugin = one focused feature (Weather, News, Quotes, Mail, etc.). Each plugin is **independent** and has its own **config.yml** (id, description) and Python **run()** method. The LLM selects by **description** (shown in the routing block) and calls **route_to_plugin(plugin_id)**.
- **What they can do:** Whatever `plugin.run()` does: call HTTP APIs, use **Util().openai_chat_completion()**, use **coreInst.get_latest_chats()**, **coreInst.send_response_to_latest_channel()**, etc. Today plugins **do not** call the Core **tool registry** (no `get_tool_registry().execute_async(...)` in plugin code). So plugins use Core’s **programmatic** API (LLM, channel, chat), not the tool layer.
- **Injection:**
  - **Routing block** in system prompt (when unified and plugins exist): “## Routing (choose one)” + “For time-related prefer remind_me / record_date / cron_schedule; use route_to_tam if too complex; if it clearly matches a plugin, call route_to_plugin(plugin_id); otherwise respond or use other tools” + “Available plugins: **plugin_id**: description (first 120 chars)”.
  - **route_to_plugin(plugin_id)** is a tool in the registry; the LLM gets the plugin list only from the **prompt**, not from a separate API. So the **description** in config.yml is what the LLM uses to decide.
- **Refinement:** Plugins are “feature bundles” with a single entry point (**run()**). They can be extended to **use tools** (e.g. Core could pass a tool-executor interface to the plugin, or the plugin could call the same registry with a ToolContext). See §5.

**Plugin Standard (any language, MCP):** A language-agnostic plugin standard is defined in **docs/PluginStandard.md**. Plugins can be **inline** (Python in-process), **subprocess** (any language: stdin/stdout JSON), **http** (POST request/response), or **mcp** (MCP server). Declare via **plugin.yaml** (id, name, description, type, config). Core discovers, registers, and runs them; plugins may use or expose MCP. Existing Python plugins work as inline without a manifest.

### 2.4 Tools vs Plugins: common targets + sequences vs dedicated external services

**One major difference:**

| | **Tools** | **Plugins** |
|--|-----------|--------------|
| **Purpose** | **Common target things** that people do on a computer: handle local files, search the web and respond, create files/folders, run commands, etc. | **Dedicated for one thing**, often integrating a **web service or MCP from another company**. |
| **Scope** | General-purpose, composable, local/universal. The LLM can **chain many tool calls** into a **sequence of tasks** (e.g. read several files → summarize → generate one PPT). | Single-purpose: one plugin = one focused capability (e.g. Weather, News, Slack, a company's MCP). |
| **Integration** | Built into Core; no external product required (except optional APIs like Tavily/Brave for web search). | Typically leverage **external web APIs** or **MCP (Model Context Protocol)** from other companies. |
| **Example** | "Read these 3 reports and create a PPT that summarizes them" → LLM uses `document_read`, then `file_write` or a script to produce a PPT (sequence of tools). | "What's the weather in Paris?" → LLM calls **route_to_plugin(weather)**; plugin calls a Weather API and returns the answer. |

So: **tools** = the building blocks for **common targets** and **multi-step workflows** (read → transform → create). **Plugins** = **one dedicated capability** that usually depends on an **external service or MCP**.

### 2.5 Popular things on a computer and how HomeClaw covers them

| What people do | Layer | How HomeClaw does it |
|----------------|--------|-------------------------|
| Handle local files (read, edit, create, list, find) | **Tools** | `file_read`, `file_write`, `file_edit`, `apply_patch`, `folder_list`, `file_find`, `document_read` (PDF/PPT/Word/MD/HTML/XML/JSON). |
| Search the web and respond | **Tools** | `web_search` (Tavily/Brave), `fetch_url`, optional `browser_*` for interactive pages. |
| Create a new file or folder | **Tools** | `file_write` (creates parent dirs), `folder_list` to explore; optional `folder_create` later. |
| Do a **sequence of tasks** (e.g. read several files → generate one PPT to summarize) | **Tools** (or **Skills**) or **Plugins** | LLM uses tools in sequence (`document_read`, then `file_write` / `run_skill`) or **route_to_plugin** to a document-export plugin. For **native .pptx/.xlsx**, a plugin (e.g. python-pptx/openpyxl) is recommended; see §2.6. |
| Reminders and scheduling | **Tools** | `remind_me`, `record_date`, `cron_schedule`, `cron_list`, `cron_remove`; or **route_to_tam** for complex time intent. |
| Recall past context (memory) | **Tools** | `memory_search`, `memory_get` (RAG). |
| Use a **dedicated external service** (weather, news, chat in Slack, etc.) | **Plugins** | **route_to_plugin(plugin_id)**; plugin calls that company's API or MCP. |
| Run a script or app (CLI/UI) | **Tools** | `exec` (allowlisted), `run_skill` (script under a skill), `process_*` for background jobs. |
| Call a generic REST API (book hotel, create post, etc.) | **Tools** | `http_request`, `webhook_trigger`. |
| Send message to another session or channel | **Tools** | `sessions_send`, `channel_send`, `sessions_spawn`. |

So most **popular computer tasks** are either **tool sequences** (files + web + create + run) or **one dedicated plugin** (external service/MCP). HomeClaw leverages both: strong tools for common targets and sequences, plugins for dedicated integrations.

### 2.6 Good plugin candidates: document export (PPT, Excel)

When the user asks to **"generate a PPT"** or **"generate an Excel"** (or PDF in a specific layout), built-in tools can only go so far:

- **Tools today:** `save_result_page` → HTML/markdown report (and link if base_url set); `file_write` → text/CSV (Excel can open CSV). No native .pptx or .xlsx.
- **Native .pptx / .xlsx** require libraries (e.g. python-pptx, openpyxl) and a bit of logic (slides, cells, formatting).

**Recommendation:** Implement these as **plugins**. For example:

- A **"Document export"** (or **"PPT/Excel export"**) plugin with description like: "Generate PowerPoint (.pptx) or Excel (.xlsx) documents from user content, summaries, or tabular data."
- The plugin’s `run()` uses python-pptx / openpyxl to build the file, writes it to a known directory (e.g. under `database/` or a configured export path), and sends the user a message with the file path or a download link (if you add file-serving for exports).
- The orchestrator routes "generate a PPT for me" / "export to Excel" to this plugin via **route_to_plugin(plugin_id)**.

That keeps Core generic (HTML report + CSV via tools) and puts format-specific export logic in a plugin that can depend on the right libraries and evolve independently.

### 2.7 OpenClaw extensions vs HomeClaw plugins

OpenClaw’s codebase can be inspected at **`../clawdbot`** (relative to this repo). The following is based on that codebase.

**What OpenClaw extensions are**

- **Format:** Each extension is a **plugin package** with:
  - **Manifest:** `openclaw.plugin.json` with `id`, `configSchema`, and optionally `channels`, `providers`, `skills`, `name`, `description`, `version`.
  - **Entry:** Default export is an object with `register(api: OpenClawPluginApi)`. The plugin calls e.g. `api.registerChannel({ plugin: whatsappPlugin })`, `api.runtime`, or other API methods.
- **Discovery:** Plugins are discovered from:
  - Bundled plugins directory
  - State directory **extensions** (e.g. `~/.openclaw/extensions`)
  - Workspace **`.openclaw/extensions`**
  - Package `openclaw.extensions` in package.json (entry file paths)
- **Purpose:** One extension can provide **channels** (WhatsApp, Telegram, Slack, Discord, Zalo, Twitch, voice-call, BlueBubbles, Nostr, etc.), **providers** (e.g. TTS), or **skills**. So extensions are how OpenClaw adds both **how users reach the assistant** (channels) and, where supported, **provider/skill** capabilities — all inside the **single Gateway process**.

**Side-by-side comparison**

| Aspect | **Extensions (OpenClaw)** | **Plugins (HomeClaw)** |
|--------|----------------------------|-------------------------|
| **What they extend** | **Gateway**: channels, providers, skills. Loaded into one process. | **Core agent behavior**: one plugin = one capability (Weather, News, Quotes, PPT/Excel, etc.). Do **not** implement channels. |
| **Where code runs** | Inside the Gateway; `register(api)` runs at load; channel code in same process. | Inside Core when orchestrator routes via **route_to_plugin(plugin_id)**; Core calls **plugin.run()**. |
| **Purpose** | Add **how users reach the assistant** (channels) or **providers/skills**. | Add **what the assistant does** for a request (answer, fetch, generate). |
| **Registration** | Path- and manifest-driven: install under `~/.openclaw/extensions` or workspace; manifest declares `channels`/`providers`/`skills`; gateway loads at startup. | **Directory + config**: plugin folder under `plugins/` with `config.yml` (id, description); PluginManager loads at startup. |
| **Selection** | Config: user enables channels/plugins; gateway uses enabled set. No LLM in the loop for “which extension.” | **LLM-routed**: plugin list (id + description) in system prompt; model calls **route_to_plugin(plugin_id)** when intent matches. |
| **Independence** | Package per extension (TypeScript/JS, own deps); can ship as npm or copy into extensions dir. | One folder per plugin (Python, own deps); lives under `plugins/`; no formal package format yet. |
| **3rd-party implementation** | Documented manifest + `register(api)`; SDK types; install via `openclaw plugins install <path>`. | Subclass `BasePlugin`, implement `run()`, add `config.yml`; drop into `plugins/` — simple but no formal SDK or install CLI. |
| **Complex tasks / MCP** | Extensions can use gateway runtime and APIs; MCP/tools depend on what the gateway exposes to plugins. | Plugins **cannot** call Core tool registry or MCP today; they use Core’s programmatic API (LLM, channel, chat). Target: allow plugins to use MCPs/tools for complex tasks. |
| **Memory / profile** | Depends on gateway APIs exposed to extensions (session, context). | Plugins get **coreInst** (chat, send_response, add_user_input_to_memory); **no** direct memory search or profile API today. Target: plugins use memory + profile for personalized service. |
| **Stability / contract** | Manifest schema, plugin SDK, allowlist/audit for security; version in manifest. | config.yml + BasePlugin; no version/contract doc yet; hot-reload optional. |

**Summary:** OpenClaw **extensions** = loadable channel/provider/skill packages in the gateway (path + manifest, `register(api)`). HomeClaw **plugins** = loadable agent-capability modules in the core (LLM-selected via **route_to_plugin**, **plugin.run()**). Channels in HomeClaw are separate (processes or /inbound bots), not plugins.

---

### 2.8 HomeClaw plugin target (goals)

The intended direction for HomeClaw plugins is:

- **Independent:** Each plugin is a self-contained unit (own code, config, optional deps) that can be developed and versioned separately.
- **Easy for 3rd parties to implement:** Clear contract (e.g. BasePlugin, config.yml schema, how to register), minimal boilerplate, and ideally a small SDK or install path so 3rd parties can ship plugins without forking Core.
- **Registered and selected by Core:** Plugins are discovered (e.g. from a plugins directory or registry) and **selected by Core**: the LLM sees the plugin list and chooses **route_to_plugin(plugin_id)** when the user intent matches; Core then runs the chosen plugin.
- **Use MCPs and tools for complex tasks:** Plugins should be able to call **MCPs** (Model Context Protocol) and/or **Core tools** (allowlisted) so they can perform complex, multi-step tasks (e.g. query external data, file operations, scheduled actions) without reimplementing everything in plugin code.
- **Extensible and stable:** A stable plugin API/contract and backward-compatible evolution so that plugin authors and Core can upgrade independently; clear lifecycle (load, run, timeout, errors).
- **Memory and profile for personalization:** Plugins should be able to use **memory** (e.g. RAG search, recent context) and **user profile** (preferences, identity) to provide personalized responses and behavior.

**Current state vs target**

| Goal | Current state | Target |
|------|----------------|--------|
| Independent | Plugin = folder under `plugins/` with config.yml + Python; no formal package format. | Clear “plugin package” (folder or archive), optional version/schema; installable without forking Core. |
| 3rd-party friendly | Implement BasePlugin + config.yml; copy into plugins dir. No SDK or install CLI. | Documented contract, minimal SDK (or stable CoreInterface slice), optional `plugins install` or registry. |
| Registered & selected by Core | ✅ PluginManager loads from plugins dir; LLM selects via route_to_plugin(plugin_id). | Keep; optionally broaden discovery (e.g. workspace plugins, allowlist). |
| Use MCPs / tools | ❌ Plugins do not call tool registry or MCP. | Expose safe plugin API: invoke allowlisted tools and/or MCP clients so plugins can complete complex tasks. |
| Extensible & stable | BasePlugin + coreInst; no formal API version or stability doc. | Document plugin API surface; version it; avoid breaking plugin code on Core upgrades. |
| Memory & profile | coreInst has chat methods and add_user_input_to_memory; **no** memory_search or profile access for plugins. | Expose memory (e.g. search/recall) and profile (read, optional update) to plugins so they can personalize. |

This target keeps plugins as **agent-capability** modules (not channels), selected by the LLM and run by Core, while making them **independent**, **easy to implement by 3rd parties**, **powerful** (MCP + tools), and **personalized** (memory + profile).

---

## 3. How the LLM decides: route_to_tam vs route_to_plugin vs tools/skills

With **orchestrator_unified_with_tools: true**, the **main LLM** sees one system prompt and one set of tools. The **order** of system prompt blocks is:

1. **Workspace** (if use_workspace_bootstrap): Identity → Agents → **Tools / capabilities** (TOOLS.md).
2. **Skills** (if use_skills): **Available skills** (name + description per skill).
3. **Memory** (if use_memory): RAG context + response template.
4. **Routing** (if unified and plugins exist): **Routing (choose one)** + time preferences (remind_me, record_date, cron_schedule, route_to_tam) + plugin list + “otherwise respond or use other tools.”
5. **Recorded events** (optional): short summary from TAM so the model knows upcoming events.

So the LLM decides purely from:

- **Text in the prompt:** Routing block tells it to prefer **remind_me / record_date / cron_schedule** for time, **route_to_tam** only if “too complex,” **route_to_plugin(plugin_id)** when it “clearly matches” a listed plugin, and “otherwise respond or use other tools.”
- **Tool schemas:** Every tool (including **route_to_tam**, **route_to_plugin**, **run_skill**, file_read, etc.) has a name and description in the API. The model picks a tool by name and fills parameters.

There is **no** separate “orchestrator” LLM; the same model does:

- **Time/scheduling** → prefer **remind_me** / **record_date** / **cron_schedule**; use **route_to_tam** only when the request is time-related but too complex for those tools.
- **Plugin-shaped request** → if the user intent clearly matches one of the “Available plugins” (by description), call **route_to_plugin(plugin_id)**.
- **Everything else** → respond in natural language or use other tools (file_read, memory_search, **run_skill**, etc.).

So: **Tools** = what the model can call (including routing); **TOOLS.md** + **Routing block** + **Skills block** = how we tell the model *when* to use which tool (including route_to_tam, route_to_plugin, run_skill).

### 3.1 Do plugins, tools, and skills conflict when selecting?

**No execution conflict.** For a single user message, only **one path** is taken. The system does not run a plugin and a skill and a generic tool at the same time for the same intent:

- **Unified mode (default):** The main LLM sees all tools (including `route_to_plugin`, `route_to_tam`, `run_skill`) and the routing block. It chooses **one or more tool calls** in sequence (e.g. first `route_to_plugin(weather)`, then the plugin runs and returns; or first `memory_search`, then `file_read`, etc.). So per “routing” decision the model picks one kind of action: time tools, route_to_tam, route_to_plugin, run_skill, or other tools. There is no race between plugin and tool—whichever the LLM calls runs.
- **Non-unified mode:** A separate orchestrator runs first and decides TIME → TAM, or OTHER + plugin match → that plugin. If it handles the request, the main LLM with tools is never invoked for that message. So again only one path.

**Possible mis-selection.** Because the LLM sees plugins, skills, and tools in the **same** prompt, it can sometimes choose the “wrong” option if descriptions overlap or are vague (e.g. use `web_search` instead of the Weather plugin for “what’s the weather”). That’s a **selection quality** issue, not a structural conflict. To reduce it:

- Use **clear, distinct descriptions** for each plugin and skill (e.g. “Current weather for a location; use when the user asks about weather, temperature, or forecast” for Weather).
- Keep the routing block and TOOLS.md aligned (e.g. “If it clearly matches one of these plugins, call route_to_plugin”).
- Optionally use **vector retrieval** for plugins/skills (`plugins_use_vector_search` / `skills_use_vector_search`) so only the most relevant few are injected, reducing noise and improving selection.

---

## 3.1 Skills vs Plugins: the one distinction that matters

Both feel like “an app to finish one task.” The important difference is **how the app is implemented** and **what limits it**:

| | **Skill** | **Plugin** |
|--|-----------|------------|
| **Implementation** | The **LLM** does the task by **calling tools** (and optionally **run_skill(script)**). The skill is described in SKILL.md; the LLM reads that and uses **browser**, **file_read**, **cron**, **memory_search**, etc. to accomplish it. So the “app” = LLM + tool calls. | **plugin.run()** in Python. The plugin is code: HTTP, **Util().openai_chat_completion()**, **coreInst.send_response_to_latest_channel()**, config, etc. The “app” = whatever the developer writes in **run()**. |
| **Can use tools?** | **Yes.** The skill’s *workflow* is the LLM using tools. So the skill can do everything that the **tool set** allows (browser, file, cron, memory, run_skill, …). | **No.** Plugin code does **not** call the tool registry (no file_read, remind_me, etc. from inside the plugin). It uses Core’s programmatic API (LLM, channel) and its own logic. |
| **Limitation** | A skill can **only** do what **tools** allow. If there’s no tool for it, the skill can’t do it (unless you add a script via run_skill; that script runs in a subprocess and still doesn’t call Core tools). So: **skills = tool-bound.** | A plugin can do **anything** you implement in Python: any API, any logic, any use of Core’s LLM/channel. It’s **not** limited by the tool catalog. So: **plugins = unlimited (by tools).** |

So in one sentence:

- **Skills** = apps implemented by **the LLM using tools** (and optionally running a script). They are **limited to what tools allow**.
- **Plugins** = apps implemented by **Python run()**. They can do **whatever you code**; they don’t use the tool layer, so they’re **not limited by tools**.

That’s why “skills can use tools, plugin cannot” is the right mental model: the skill’s behavior *is* the LLM calling tools; the plugin’s behavior is standalone code.

---

## 4. Differences at a glance

| Aspect | Tools | Skills | Plugins |
|-------|--------|--------|---------|
| **Granularity** | Single operations (read file, run command, route to TAM, route to plugin). | One “skill” = one folder (name + description + scripts); invoked via **run_skill(skill_name, script)**. | One plugin = one id + description + **run()**; invoked via **route_to_plugin(plugin_id)**. |
| **Implementation** | Executor function (e.g. in tools/builtin.py); registered in tool registry. | Scripts in `<skill>/scripts/`; run by Core when **run_skill** is called. | Python class with **run()**; loaded by PluginManager; Core calls **plugin.run()**. |
| **Config** | Tool params in schema; some global options in core.yml (e.g. tools.file_read_max_chars, tools.run_skill_allowlist). | skills_dir in core.yml; each skill = folder with SKILL.md (+ scripts/). | plugins/ folder; each plugin has config.yml (id, description, etc.). |
| **How LLM selects** | By tool name + parameters (from tool schemas). Routing block + TOOLS.md guide *when* to use route_to_tam / route_to_plugin / other tools. | By skill name + script (from **run_skill** tool + “Available skills” block). | By plugin_id (from **route_to_plugin** tool + “Available plugins” list in Routing block). |
| **Can use Core LLM?** | Yes (executors can call Util().openai_chat_completion or similar). | Scripts run in a process; they don’t call Core LLM unless they hit an API. | Yes (plugins use Util().openai_chat_completion, coreInst.get_latest_chats, etc.). |
| **Can use Core tools?** | N/A (they *are* the tools). | No (scripts are separate processes; no tool registry in script). | **Not today.** Plugin code doesn’t call the tool registry. Possible extension: see §5. |

---

## 5. Can plugins use tools? Can they call each other?

- **Plugins calling tools:** Today **no**. Plugins have access to **Core interface** (e.g. coreInst, Util()) and use **openai_chat_completion**, **send_response_to_latest_channel**, **get_latest_chats**. They do **not** call `get_tool_registry().execute_async(...)`. So a plugin cannot today “use file_read” or “use remind_me” as tools.  
  **Refinement:** Expose a safe way for plugins to invoke tools (e.g. Core passes a `context: ToolContext` and a `execute_tool(name, args)` helper that runs allowlisted tools only). Then a Weather plugin could, for example, call a “fetch_url” or “cache” tool if we add it and allowlist it for plugins.

- **Plugins calling other plugins:** Not by design. The LLM selects **one** plugin per user turn via **route_to_plugin(plugin_id)**. A plugin’s **run()** could in principle call another plugin’s **run()** (e.g. get plugin from PluginManager and await plugin.run()), but that’s not the intended flow; the intended flow is “one user message → one route_to_plugin or other tools.” So we don’t recommend plugin‑to‑plugin calls unless we explicitly design for it (e.g. “compose” plugins).

- **Skills calling tools:** Skills are **scripts** run via **run_skill**. The script runs in a subprocess/sandbox; it doesn’t have access to the Core process or the tool registry. So skills don’t “call” Core tools. If we wanted that, we’d need something like a “skill API” or a small daemon that the script can call to ask Core to run a tool (out of scope for now).

- **Tools “calling” skills/plugins:** The LLM does that: it calls **run_skill** or **route_to_plugin**; Core runs the script or **plugin.run()**. So from the tool layer’s point of view, “calling” a skill or plugin = the model choosing that tool and Core executing it.

---

## 5.1 Scaling: many skills and plugins (context size and discoverability)

**You’re right:** with many skills or many plugins, we currently **inject all of them** into the system prompt (skills block + plugin list in the routing block). That causes two problems:

1. **Context size:** The prompt can grow large and exceed the model’s context window (or leave little room for chat history and memory).
2. **Discoverability:** A long list in the prompt is harder for the LLM to use reliably; it may miss or mis-select the right skill/plugin.

Plugins have the same issue: each plugin’s description (from config.yml) is appended to the routing block, so many plugins → long “Available plugins” list.

**Ways to address it:**

| Approach | Description | Pros / cons |
|----------|-------------|-------------|
| **Config limits (short term)** | Cap how many skills/plugins we inject (e.g. `skills_max_in_prompt: 10`, `plugins_max_in_prompt: 10`). Take the first N (or a stable order). | Simple; immediately reduces prompt size. Con: LLM never sees the rest; order matters. |
| **Retrieval / selection (medium term)** | Before building the prompt, **select** a subset of skills/plugins relevant to the **current query** (e.g. embed query + each description, return top-k; or a small classifier/LLM call). Inject only that subset. | Prompt stays small; LLM sees only relevant items. Con: needs embedding or extra LLM call; latency/cost. |
| **Discovery tools (medium term)** | Don’t inject the full list. Instead add **tools** like `list_skills(query?)` / `search_skills(query)` and `list_plugins(query?)` / `search_plugins(query)` that return matching skills/plugins (and their descriptions). System prompt says: “When you need a skill or plugin, call list_skills/list_plugins or search_skills/search_plugins.” | No catalog in the prompt; LLM fetches on demand. Con: extra tool round-trip; need to implement and optionally index by embedding. |
| **Categories / hierarchy** | Group skills (and plugins) by category. Inject only category names + one-line summary (e.g. “Time: remind_me, record_date, cron. Social: social-media-agent. …”). Optionally a tool `get_skills_in_category(category)` to expand. | Shorter initial prompt; LLM picks category then detail. Con: requires defining categories and maintaining them. |

**Implemented (short term):** **Config limits** in `core.yml`: `skills_max_in_prompt` and `plugins_max_in_prompt` (0 = no limit). When set to a positive number, only the first N skills (and first N plugins) are injected into the system prompt. That caps prompt size when you have many skills/plugins; order is the scan/load order (skills: sorted by folder name; plugins: load order). **Medium term:** Add **retrieval** (top-k by relevance to the query) or **discovery tools** (list_skills, search_plugins, etc.) so the LLM doesn’t depend on a single long list in the prompt.

---

## 6. Recommended refinements

1. **Keep orchestrator_unified_with_tools: true.** One main LLM with tools (including route_to_tam, route_to_plugin) is simpler and avoids a separate orchestrator LLM.
2. **Clarify TOOLS.md vs tool registry:** TOOLS.md = human-readable “what you can do” and when to use what (including “use Weather plugin when …”); tool registry = actual callable tools. Keep TOOLS.md in sync with the routing block and tool list (e.g. mention “route_to_plugin(plugin_id) when the request clearly matches a plugin”).
3. **Routing block wording:** Already says “prefer remind_me / record_date / cron_schedule; use route_to_tam only if too complex” and “if it clearly matches one of these plugins, call route_to_plugin(plugin_id).” Optionally add one line: “For script-based workflows (see Available skills), use run_skill(skill_name, script, …).”
4. **Plugin descriptions:** Short, clear descriptions in config.yml (and the first ~120 chars in the prompt) drive plugin selection. Keep them focused (e.g. “Current weather for a configured city” not “Does various things”).
5. **Plugins using tools (optional):** If we want plugins to reuse Core tools (e.g. file_read, fetch_url), add a small API: e.g. `core.execute_tool(name, args)` or pass a restricted ToolContext to the plugin so it can call only allowlisted tools. Then document which tools are plugin-callable and the security model.

---

## 7. Summary

- **Tools** = native + routing; registered in the tool registry; LLM chooses by tool name/params; guided by TOOLS.md and the Routing block.
- **Skills** = catalog of script-based “applications”; listed in the Skills block; LLM invokes via **run_skill**; no direct use of Core tools inside the script.
- **Plugins** = one-feature Python bundles; listed in the Routing block (plugin_id + description); LLM invokes via **route_to_plugin(plugin_id)**; plugins use Core’s programmatic API (LLM, channel) but **not** the tool registry today.

The LLM decides between **route_to_tam**, **route_to_plugin**, and other tools/skills using the **Routing block** and **tool schemas**; we keep **orchestrator_unified_with_tools: true** and treat this single model as the only router.

---

## 8. Persistent registration and vector retrieval (skills first, then plugins)

This section describes the **target design**: persistent registration, extraction of useful text, storage in a **dedicated** vector DB (separate from RAG memory), and retrieval by user query at inject time. We implement **skills** first (structure is more stable); **plugins** follow the same logic.

### 8.1 Goals

1. **Persistent registration** for both skills and plugins: store metadata (index = folder/id, refined text for prompt) so we don’t depend only on scanning the filesystem every request.
2. **Extract useful information** from SKILL.md (and plugin config.yml): produce a **refined text** that we embed and inject (name + description, optionally a short summary of the body).
3. **Store refined text in a vector database** with the index (folder name for skills, plugin_id for plugins). **Separate collections** for skills vs plugins (embeddings stored separately from each other and from main RAG memory).
4. **At inject time:** Use the **user’s input (query)** to search the vector DB, retrieve the **most similar** skills (or plugins), up to a **configurable count** and above a **configurable similarity threshold**. Only those are injected into the system prompt.
5. **Sync with filesystem:** When we use a retrieved skill, we go to its folder and load SKILL.md as today. If the folder is **missing** (removed), we **remove** that entry from the vector DB and skip it. So the vector DB stays in sync: missing folders → delete from vector store. We do **not** need a separate relational table; the vector store (with id + metadata) is enough. Optionally run a full resync on startup (scan all folders, upsert new/changed, delete ids that no longer exist).

### 8.2 Data model (skills)

- **Index:** Skill folder name under `skills_dir` (e.g. `social-media-agent-1.0.0`, `example`). Used as **vector document id**.
- **Refined text:** Text we embed and use for similarity search. Suggested: `name + "\n" + description` (and optionally first N characters of body). This is what we store in vector metadata and/or re-read from disk when building the prompt block.
- **Vector store:** One **dedicated collection** (e.g. `homeclaw_skills`). Same Chroma (or same backend) as memory, **different collection name**. Each document: `id = folder`, `embedding = embed(refined_text)`, `metadata = { folder, name, description }` (and optionally `refined_text` if we want to avoid re-reading for the block).
- **Sync:** On startup (or on demand): scan `skills_dir`; for each folder with SKILL.md, parse → refined text → embed → upsert. Then list all ids in the collection; if an id is not in the current folder list, **delete** that id (folder was removed).

### 8.3 Data model (plugins)

- **Index:** Plugin id (from config.yml). Used as vector document id.
- **Refined text:** Description (and optionally name) from config.yml.
- **Vector store:** One **dedicated collection** (e.g. `homeclaw_plugins`). Separate from skills and from memory.
- **Sync:** After PluginManager loads plugins, upsert each plugin (id, embedding, metadata). If a plugin is removed from config/plugins, we don’t have a “folder” to check; we can resync from the current plugin list and delete ids that are no longer in the list.

### 8.4 Config (skills first)

- **skills_use_vector_search:** bool = false. When true, we **retrieve** skills by vector search on the user query instead of injecting all (or the first N).
- **skills_vector_collection:** str = `"homeclaw_skills"`. Chroma collection name for skills (separate from memory).
- **skills_max_retrieved:** int = 10. Max number of skills to retrieve and inject per request.
- **skills_similarity_threshold:** float = 0.0. Minimum similarity score (e.g. 0.5). Results below are dropped. Chroma returns distance; we use `similarity = 1 - distance` for cosine and filter `similarity >= threshold`.
- **skills_refresh_on_startup:** bool = true. On Core startup, run sync (see §8.5).  
- **skills_test_dir:** str = "" (optional). If set (e.g. `config/skills_test`), this dir is **fully synced** every time (all skills embedded and upserted with id `test__&lt;folder&gt;`). Use for testing skills.  
- **skills_incremental_sync:** bool = false. When true, **skills_dir** is synced **incrementally**: only folders not already in the vector store are embedded and inserted. When false, all folders in skills_dir are re-embedded and upserted (current behavior).

### 8.5 Sync behavior: full vs incremental, and test folder

**Current (default) behavior:** On startup we scan **all** folders in `skills_dir` and **re-embed and upsert every skill** every time. We do **not** only process “new” ones.

**Reasonable refinement:**

- **Production `skills_dir`:** Use **incremental sync** when `skills_incremental_sync` is true: only process folders that are **not** already in the vector store (`get(folder)` is None). New skills get embedded and inserted; existing ones are skipped. This avoids re-embedding many skills on every startup.
- **Test folder `skills_test_dir` (optional):** A separate directory (e.g. `config/skills_test`) used for **testing skills**. This folder is **fully synced every time**: all folders in it are scanned, embedded, and upserted (overwrite by id). So changes to SKILL.md in the test folder are reflected on every startup. Test skills use ids prefixed with `test__` (e.g. `test__my-skill`) so they don’t clash with production ids and we know to load from the test path when we see that id at retrieve time. **Cleanup:** After syncing the test dir, any vector-store id that starts with `test__` and whose folder is **no longer** in the test dir (e.g. skill moved to production or removed) is **deleted** from the store. So when you remove a skill from the test folder, the next sync removes its `test__xxx` entry from the database.

So: **test folder = full sync every time** (for quick iteration on skills); **production skills_dir = incremental (only new)** when enabled.

### 8.6 Flow (skills)

1. **Startup (if skills_use_vector_search and skills_refresh_on_startup):**  
   - If **skills_test_dir** is set: scan it, parse, embed, upsert all with id = `"test__" + folder_name`.  
   - Then sync **skills_dir**: if **skills_incremental_sync** is true, only process folders where `get(folder)` is None (new); else process all and upsert.

2. **At answer_from_memory (when use_skills and skills_use_vector_search):**  
   - Embed the **user query** (same embedder as memory).  
   - Search `skills_vector_collection` with `query_embedding`, `limit = skills_max_retrieved`.  
   - For each result: `similarity = 1 - distance`; if `similarity < skills_similarity_threshold`, skip.  
   - For each remaining result (id): if id starts with `"test__"`, **load from disk** `skills_test_dir / (id without prefix) / SKILL.md`; else **load** `skills_dir / id / SKILL.md`. If the folder or file is **missing**, delete that id from the vector collection and skip.  
   - Build the skills block from the loaded skill dicts (same `build_skills_system_block` as today) and append to the system prompt.

3. **Fallback:** If `skills_use_vector_search` is false, keep current behavior: `load_skills` → cap by `skills_max_in_prompt` → build block.

### 8.6 Plugins (same logic, later)

- Config: `plugins_use_vector_search`, `plugins_vector_collection`, `plugins_max_retrieved`, `plugins_similarity_threshold`, `plugins_refresh_on_startup`.  
- Sync: after plugin load, upsert each plugin (id, embed(description), metadata).  
- At inject time: search plugins collection by query, retrieve top-k above threshold, then only list those plugins in the routing block. If a plugin id is no longer in PluginManager (e.g. plugin removed), delete from vector collection when we detect it.

### 8.7 Implementation order

1. **Skills:** Add config, create skills vector store (same Chroma client, different collection), implement sync and retrieve path in Core; keep fallback when `skills_use_vector_search` is false.  
2. **Plugins:** Same pattern: config, plugins vector store, sync after plugin load, retrieve by query when building the routing block.
