# Skills (SKILL.md format)

**Full guide:** See **docs/SkillsGuide.md** for a complete user and developer guide: introduction, how to use skills, how to implement them, how to test them, and config reference.

**Tools vs skills:** In HomeClaw, **tools** are the **static base**—callable actions (exec, browser, cron, sessions_*, memory, file, web, **route_to_plugin**, run_skill, etc.). **Skills** are the **application layer**: each skill is a task-oriented instruction package (SKILL.md) that tells the agent *how* to use tools (and plugins) to finish tasks. So: tools = capabilities; skills = know-how.

**Can skills use plugins?** Yes. Skills don’t call tools or plugins directly — the **agent** does. The agent has the **route_to_plugin** tool (plugin_id, capability_id, parameters). When a skill says “use the browser to navigate to X,” the agent can call **route_to_plugin**(plugin_id="homeclaw-browser", capability_id="browser_navigate", parameters={url: X}). So when browser (or canvas, nodes) are provided by the **homeclaw-browser** plugin (with tools.browser_enabled: false), skills that refer to browser/canvas/nodes still work: the agent uses route_to_plugin with the right capability_id. See **docs_design/ToolsSkillsPlugins.md** (§2.2 “Can skills use plugins?”).

When **use_skills: true** in `config/core.yml`, HomeClaw scans this directory for **skill folders**: each subfolder that contains a **SKILL.md** file is loaded and injected into the system prompt as "Available skills".

## Format (SKILL.md / AgentSkills compatible)

Each skill is a **folder** with at least:

- **SKILL.md** — Required. YAML frontmatter + markdown body:
  ```yaml
  ---
  name: my-skill
  description: What this skill does in one line.
  ---
  Optional: longer instructions or usage notes in markdown.
  ```

Optional frontmatter: `homepage`, `user-invocable`, `disable-model-invocation`, `metadata`.

## Adding skills

1. Create a subfolder under `config/skills/`, e.g. `config/skills/weather-help/`.
2. Add **SKILL.md** with `name`, `description`, and optional body.
3. (Optional) Add **scripts/** with runnable scripts; the agent can call **run_skill**(skill_name, script, args).
4. Set **use_skills: true** and **skills_dir: config/skills** in `config/core.yml`.
5. Restart or send a new message; the model will see "Available skills" in its context.

## Bundled skills

- **desktop-ui** — macOS-only desktop UI automation (peekaboo). Use **run_skill**(skill_name="desktop-ui", script="run.py", args=[...]). On Windows/Linux, run.py returns a clear "not available on this platform" message; Core does not crash.
- **ip-cameras** — RTSP/ONVIF IP cameras (camsnap + ffmpeg). Use **run_skill**(skill_name="ip-cameras", script="run.py", args=[...]). If camsnap or ffmpeg is missing, run.py returns a clear error; Core does not crash.

You can add skill folders from other registries or create your own. HomeClaw has equivalent tools for exec, browser, cron, sessions_*, memory, file, web; most skills that use those tools are usable. See **Design.md §3.6**.

## Skill compatibility

Skills written for other agents may reference **tools** (e.g. `browser` with click/type/snapshot, `web_fetch`, `sessions_spawn`, `cron`, `memory_search`). HomeClaw’s loader injects **name + description** into the prompt so the model knows the skill exists. The **body** of SKILL.md is not injected by default (to save tokens); if you enable `include_body` in the loader, the model will see instructions that may refer to tools we don’t have.

**Rough mapping for HomeClaw:**

| Other / reference | HomeClaw |
|----------|------------|
| `web_fetch` | `fetch_url` (fetch URL, HTML→text) |
| `browser` (read page) | `browser_navigate` or `fetch_url` |
| `browser` (click, type, post) | **Yes**: `browser_snapshot` → `browser_click`, `browser_type` (shared session per request; requires Playwright) |
| `sessions_spawn` | **Yes**: **sessions_spawn** (sub-agent one-off run; optional llm_name or capability) |
| `cron` | **Yes**: **cron_schedule** (cron expression + message), **cron_list** (list jobs). TAM also accepts cron in TIME intents. |
| `memory_search` / files | RAG + `file_read`, `folder_list` |


**cron** — Supported. Use **cron_schedule** with a 5-field cron expression (e.g. `0 9 * * *` for daily at 9:00) and a message; **cron_list** to list scheduled jobs. TAM (time/reminder flow) also accepts type "cron" with cron_expr in the intent JSON. Time-related scheduling is first-class.

With sessions_spawn, cron, browser, and other tools in place, skills like **social-media-agent** can be used for full automation (post tweets via browser, cron schedules, spawn sessions) as well as strategy and content ideas.
