# Skills (SKILL.md format)

**Full guide:** See **docs/SkillsGuide.md** for a complete user and developer guide: introduction, how to use skills, how to implement them, how to test them, and config reference.

**Tools vs skills:** In HomeClaw, **tools** are the **static base**—callable actions (exec, browser, cron, sessions_*, memory, file, web, **route_to_plugin**, run_skill, etc.). **Skills** are the **application layer**: each skill is a task-oriented instruction package (SKILL.md) that tells the agent *how* to use tools (and plugins) to finish tasks. So: tools = capabilities; skills = know-how.

**Can skills use plugins?** Yes. Skills don’t call tools or plugins directly — the **agent** does. The agent has the **route_to_plugin** tool (plugin_id, capability_id, parameters). When a skill says “use the browser to navigate to X,” the agent can call **route_to_plugin**(plugin_id="homeclaw-browser", capability_id="browser_navigate", parameters={url: X}). So when browser (or canvas, nodes) are provided by the **homeclaw-browser** plugin (with tools.browser_enabled: false), skills that refer to browser/canvas/nodes still work: the agent uses route_to_plugin with the right capability_id. See **docs_design/ToolsSkillsPlugins.md** (§2.2 “Can skills use plugins?”).

When **use_skills: true** in `config/core.yml`, HomeClaw scans this directory for **skill folders**: each subfolder that contains a **SKILL.md** file is loaded and injected into the system prompt as "Available skills". When **skills_use_vector_search** is true, the text we **embed for RAG** is: **name** + **description** + **keywords** + **trigger** (instruction snippet + pattern terms from `trigger:` in SKILL.md). So adding **keywords** and/or **trigger** improves skill selection for user queries. See **docs_design/SkillsRAGContent.md** for details.

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

Optional frontmatter: `homepage`, `user-invocable`, `disable-model-invocation`, `metadata`, **`trigger`**.

### Trigger (force-include and auto_invoke from the skill)

To avoid repeating rules in `config/core.yml` for every skill, you can declare **`trigger`** in the skill’s frontmatter. When the user query matches `trigger.patterns`, Core force-includes this skill, appends `instruction` to the system prompt, and (if the model doesn’t call the tool) runs **auto_invoke** so the skill runs anyway.

```yaml
trigger:
  patterns: ["weather|forecast|天气"]   # regex list; query matched case-insensitively
  instruction: "The user asked about weather. Call run_skill with the location from the message."
  auto_invoke:
    script: get_weather.py
    args: ["{{query}}"]
```

- **patterns**: list of regex strings (or a single `pattern:` string). If any matches the user query, the trigger fires.
- **instruction**: optional; added to the system prompt when the trigger fires so the model is told to use this skill.
- **auto_invoke**: optional. When the model returns no tool call, Core runs `run_skill(skill_name=<folder>, script=..., args=...)` with `{{query}}` replaced by the user message. Use only when the intent is narrow (weather, search, image) and args can be derived from the message.

You do **not** need to add a matching entry to `skills_force_include_rules` in core.yml when the skill has a `trigger`. Use core.yml rules only to override or for skills without a SKILL.md trigger.

## Adding skills

1. Create a subfolder under `config/skills/`, e.g. `config/skills/weather-help/`.
2. Add **SKILL.md** with `name`, `description`, and optional body.
3. (Optional) Add **USAGE.md** in the same folder: user-facing "how to ask" examples. When the skill is loaded with body (see **skills_include_body_for** in core.yml), USAGE.md is appended to the skill body so the model can answer "how do I use this?".
4. (Optional) Add **scripts/** with runnable scripts; the agent can call **run_skill**(skill_name, script, args).
5. Set **use_skills: true** and **skills_dir: config/skills** in `config/core.yml`. To include full skill body (and USAGE.md) for specific skills so the model can answer "how do I use this?", set **skills_include_body_for: [folder-name]** (e.g. `[maton-api-gateway-1.0.0]`).
6. Restart or send a new message; the model will see "Available skills" in its context.

## When to add a force-include rule (config/core.yml)

You **do not** need a `skills_force_include_rules` entry for every skill. Most skills are discovered by RAG (vector search) and the model calls **run_skill** when appropriate.

Add a rule only when:

- **RAG under-ranks the skill** — e.g. "weather in Beijing" might not retrieve the weather skill in the top N, so we force-include it when the query matches a pattern.
- **The model often refuses** — some models reply "I can't fetch weather" instead of calling the tool; a **force-include** with a strong instruction (and optionally **auto_invoke**) ensures the skill runs.

Use **auto_invoke** only when:

1. User intent is **clear and narrow** (weather, web search, generate image).
2. The **only** correct response is to run that skill (not to say "I can't").
3. Arguments can be derived from the user message (e.g. `{{query}}` or a single extracted value). Do **not** use auto_invoke for skills that need the model to choose among options (e.g. which file to summarize, which style).

So we have rules (with or without auto_invoke) for **image generation**, **weather**, and **Baidu search**; other skills (summarize, LinkedIn writer, etc.) rely on RAG + model tool use and do not need special rules unless you observe repeated failures.

## Include all skills (OpenClaw-style)

If **many** skills are never selected by RAG, you can inject **all** skills so the model always sees every one. In **`config/core.yml`** set:

```yaml
skills_use_vector_search: false
```

When `skills_use_vector_search` is false, Core loads every skill from `skills_dir` and adds them to the system prompt (name + description only, no body). No RAG, no cap. The model can then call **run_skill** for any skill by folder name. Trade-off: with many skills (e.g. 50+), the prompt is longer; if your context window is large enough, this avoids "skill not selected" entirely.

## Bundled skills

- **desktop-ui** — macOS-only desktop UI automation (peekaboo). Use **run_skill**(skill_name="desktop-ui", script="run.py", args=[...]). On Windows/Linux, run.py returns a clear "not available on this platform" message; Core does not crash.
- **ip-cameras** — RTSP/ONVIF IP cameras (camsnap + ffmpeg). Use **run_skill**(skill_name="ip-cameras", script="run.py", args=[...]). If camsnap or ffmpeg is missing, run.py returns a clear error; Core does not crash.
- **Social (official APIs, free):** **x-api-1.0.0** (X/Twitter — post tweet, read timeline via X API v2), **meta-social-1.0.0** (Facebook Page + Instagram via Meta Graph API). Use **run_skill** with script `request.py`; set `X_ACCESS_TOKEN` or `META_ACCESS_TOKEN` (or in skill config.yml).
- **Social (optional, paid):** **hootsuite-1.0.0** — post/schedule to X, Facebook, LinkedIn, Instagram via Hootsuite. Requires Hootsuite subscription and **HOOTSUITE_ACCESS_TOKEN**. Use **run_skill** with script `request.py`: `list` (profiles), `post <profile_id> <text> [scheduledSendTime]`.

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
