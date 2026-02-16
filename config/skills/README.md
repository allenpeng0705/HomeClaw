# Skills (SKILL.md format)

**Full guide:** See **docs/SkillsGuide.md** for a complete user and developer guide: introduction, how to use skills, how to implement them, how to test them, and config reference.

**Tools vs skills:** In HomeClaw, **tools** are the **static base**—callable actions (exec, browser, cron, sessions_*, memory, file, web, etc.). **Skills** are the **application layer**: many (ClawHub has thousands), each a task-oriented instruction package (SKILL.md) that tells the agent *how* to use different tools to finish different tasks. So: tools = capabilities; skills = know-how for specific tasks.

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
3. Set **use_skills: true** and **skills_dir: config/skills** in `config/core.yml`.
4. Restart or send a new message; the model will see "Available skills" in its context.

You can copy skill folders from [ClawHub](https://clawhub.biz/) or other skill registries into this directory to reuse them. HomeClaw has equivalent tools for exec, browser, cron, sessions_*, memory, file, web; most community skills that don't rely on canvas/nodes/gateway are usable. See **Design.md §3.6**.

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
