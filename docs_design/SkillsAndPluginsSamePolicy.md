# Skills and Plugins: Same Policy (Include All)

## How we handle skills and plugins (summary)

- **Default: load all, no vector store.** By default we load all skills and all plugins and inject them into every request. We do **not** use the vector store unless you explicitly turn it on. If the flag or any related setting is **missing** from config, we use this default: load all, do not create or use the skills/plugins vector store.
- **Same policy:** Skills and plugins use the same idea: default = include all; optional vector search = only top‑N in the prompt. Force-include / trigger rules still add specific items when the query matches.
- **Skills:** Loaded from `skills_dir` + optional `skills_extra_dirs`; disabled via `skills_disabled`. Injected as an "Available skills" block; the model calls `run_skill(skill_name=..., ...)`.
- **Plugins:** Loaded from `plugins/` + optional `plugins_extra_dirs` + API registration. Injected as a routing block (id + description per plugin); the model calls `route_to_plugin(plugin_id=..., ...)`.
- **Vector store and the flag:** The skills (or plugins) vector store is **only created when the corresponding flag is true**. If `skills_use_vector_search` is missing or false (default), Core never creates `skills_vector_store`. If `plugins_use_vector_search` is missing or false (default), Core never creates `plugins_vector_store`. So the flag controls both **creation** and **use**; we do not keep a vector store when the flag is off or absent.

## Policy

HomeClaw uses the **same approach** for skills and for plugins so that "not found" is easy to avoid and behavior is predictable.

- **Default (flag missing or false):** Load **all** eligible skills and **all** registered plugins; inject them into every request. No vector store is created or used. This is the default when `skills_use_vector_search` / `plugins_use_vector_search` (or related settings) are omitted from config.
- **Optional (flag explicitly true):** Turn on vector search (`skills_use_vector_search: true` or `plugins_use_vector_search: true`) to create the store, sync on startup, and put only the top‑N most relevant in the prompt; trigger/force-include rules still add specific items when the query matches.

This matches OpenClaw’s behavior: all eligible skills are in the prompt at once (see [OpenClawSkillsHowAdded.md](OpenClawSkillsHowAdded.md)).

## Skills

- **Loaded from:** `skills_dir` (e.g. `skills`) plus optional **`skills_extra_dirs`** (list of paths, relative to project root). Each subfolder with a `SKILL.md` is one skill. Merged with first-wins by folder name. Any folder in **`skills_disabled`** is not loaded (case-insensitive).
- **When `skills_use_vector_search: false` (default):** All skills from main + extra dirs (minus disabled) are injected into the system prompt as the "Available skills" block. The **LLM selects** which skill to use—you do **not** need to add a config rule for each skill. Put **trigger.patterns** and **trigger.instruction** in each skill's SKILL.md so when the query matches, the model gets the nudge from the skill itself. **skills_force_include_rules** in core.yml is optional; leave **empty** to rely on LLM selection + per-skill trigger.
- **When `skills_use_vector_search: true`:** Skills are retrieved by embedding similarity; only the top `skills_max_in_prompt` are in the prompt. Trigger-matched skills are still prepended so they are not missed.
- **Disabling:** Set `skills_disabled: [folder1, folder2]` in `core.yml` so those skill folders are never loaded (e.g. `skills_disabled: [x-api-1.0.0]`).

## Plugins

- **Loaded from:**  
  - **Built-in:** `plugins/` (Python plugins and manifest-based external http/subprocess/mcp).  
  - **External dir(s):** Optional `plugins_extra_dirs` in config (see below).  
  - **API:** Plugins can also register via `POST /api/plugins/register` (stored in `config/external_plugins.json`).
- **After registration:** Every loaded/registered plugin (inline + external) appears in `get_plugin_list_for_prompt()`, which returns a list of `{ id, description }`.
- **Injection:** When building the system prompt, Core builds a **routing block** that includes an "Available plugins:" section: one line per plugin, `plugin_id: description`. That block is appended to the system message (`system_parts`). So the LLM sees every registered plugin and can call `route_to_plugin(plugin_id=..., capability_id=..., parameters=...)`.
- **When `plugins_use_vector_search: false` (default):** All plugins from `get_plugin_list_for_prompt()` are in the routing block. The **LLM selects** which plugin to use—you do **not** need to add a config rule for each plugin. **plugins_force_include_rules** in core.yml is optional; leave **empty** to rely on LLM selection.
- **When `plugins_use_vector_search: true`:** Plugins are retrieved by embedding similarity; only the top `plugins_max_in_prompt` are in the block. `plugins_force_include_rules` can add specific plugins when the query matches (optional).

## External plugin directory

To support **dynamically added** plugins without editing core code or calling the API:

- **Config:** `plugins_extra_dirs` (list of paths). Paths are relative to the project root or absolute. Example: `plugins_extra_dirs: [config/external_plugins]`.
- **Behavior:** On `load_plugins()`, Core scans each extra dir. For each **subfolder** that contains a `plugin.yaml` (or `plugin.yml` / `plugin.json`) with `type: http` (or `subprocess` / `mcp`), the plugin is registered as an external plugin (same as those under `plugins/` with type http/subprocess/mcp). Python (inline) plugins in extra dirs are **not** loaded (they must live under `plugins/` or register via API).
- **Use case:** Drop a folder (e.g. `config/external_plugins/my-http-plugin/` with `plugin.yaml` and `type: http`) and restart Core (or rely on hot-reload if enabled); the plugin is discovered and its id/description appear in the routing block.

## Summary

| Item        | Default (include all) | When vector search on |
|------------|------------------------|------------------------|
| Skills     | All from `skills_dir` (+ extra dirs, − disabled) in prompt; trigger adds instruction | RAG top‑N + trigger‑matched |
| Plugins    | All from registry in routing block | RAG top‑N + force-include rules |
| Injection  | Skills block + routing block (with plugin list) appended to system message | Same, but lists are filtered by RAG |

| Flag | Vector store | Sync on startup | At request time |
|------|--------------|-----------------|------------------|
| `skills_use_vector_search: false` (default) | **Not created** | No | All skills loaded from disk and injected |
| `skills_use_vector_search: true` | Created (`skills_vector_collection`) | Yes (if `skills_refresh_on_startup`) | RAG retrieval + trigger/force-include |
| `plugins_use_vector_search: false` (default) | **Not created** | No | All plugins in routing block |
| `plugins_use_vector_search: true` | Created (`plugins_vector_collection`) | Yes (if `plugins_refresh_on_startup`) | RAG retrieval + force-include rules |

After a plugin is registered (from `plugins/`, from `plugins_extra_dirs`, or via API), its **id** and **description** are included in the routing block string for the next request, so the model can choose it.
