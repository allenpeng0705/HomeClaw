# Skills: User and Developer Guide

This guide explains what skills are, how to **use** them (as a user or operator), how to **implement** them (as a skill developer), and how to **test** them. It is written so both end users and skill developers can follow it easily.

---

## 1. Introduction

### 1.1 What are skills?

**Skills** are task-oriented instruction packages that tell the assistant *how* to accomplish specific goals using the **tools** it already has (browser, file read, cron, memory search, etc.). Think of them as “apps” that are implemented by the **LLM following instructions** and calling tools—not by separate code.

- **Tools** = what the assistant *can* do (e.g. read a file, run a cron job, open a URL).
- **Skills** = *how* to combine those tools for a task (e.g. “use browser + cron + memory to run a social media workflow”).

So: **tools = capabilities; skills = know-how for specific tasks.**

### 1.2 Why use skills?

- **Reuse:** One skill (e.g. “social media agent”) can be dropped into any HomeClaw instance that has the right tools.
- **Clarity:** The assistant sees “Available skills” in its context and can choose the right one for the user’s request.
- **No new code:** A skill is a **folder** with a **SKILL.md** file (and optionally scripts). You don’t need to write Python plugins.

### 1.3 Skills vs plugins vs tools

| | **Tools** | **Skills** | **Plugins** |
|--|-----------|------------|-------------|
| **What** | Single operations (file_read, cron_schedule, browser_*, etc.). | Task workflows: the LLM uses tools according to a skill’s instructions. | Standalone features (e.g. Weather, News) implemented in Python. |
| **Implementation** | Built-in functions in the tool registry. | SKILL.md (name, description, body) + optional scripts. | Plugin class with `run()`; config.yml. |
| **Limitation** | N/A. | Can only do what **tools** allow. | Can do anything you code (HTTP, LLM, etc.). |

Skills are **tool-bound**: they describe workflows using existing tools. Plugins are **code-bound**: they run their own logic. See **docs/ToolsSkillsPlugins.md** for more detail.

---

## 2. How to use skills (users and operators)

### 2.1 Enable skills

1. Open **config/core.yml**.
2. Set **use_skills: true**.
3. Set **skills_dir** to the folder that contains your skill folders (default: **skills**).

Example:

```yaml
use_skills: true
skills_dir: skills
```

4. Restart Core (or send a new message). The assistant will see an “Available skills” block in its system prompt and can use those skills when they match the user’s request.

### 2.2 Add or remove skills

- **Add a skill:** Put a new **folder** under **skills_dir** (e.g. `skills/my-skill/`) with a **SKILL.md** file inside (see §3). No code change needed.
- **Remove a skill:** Delete or move that folder out of **skills_dir**. If you use vector search (§2.4), stale entries are cleaned up when you load that skill (lazy delete) or when you run a full sync.

### 2.3 Limit how many skills are in the prompt (no vector search)

If you have many skills and **do not** use vector search, you can cap how many are injected so the prompt does not grow too large:

```yaml
skills_max_in_prompt: 10   # 0 = no limit; only the first N skills (by folder order) are injected.
```

### 2.4 Optional: retrieve skills by similarity (vector search)

When you have **many** skills, you can inject only the ones **most relevant** to the user’s query instead of listing all of them.

1. Set **skills_use_vector_search: true** in **config/core.yml**.
2. On startup, Core will sync skill **descriptions** (and optional body snippet) into a **separate vector store** (collection `homeclaw_skills` by default). No RAG memory is used for this.
3. For each user message, Core embeds the **query**, searches the skills collection, and injects only the **top‑k** skills above a **similarity threshold** into the prompt.

Relevant options:

```yaml
skills_use_vector_search: true
skills_vector_collection: homeclaw_skills
skills_max_retrieved: 10
skills_similarity_threshold: 0.5
skills_refresh_on_startup: true
```

- **skills_max_retrieved:** Max number of skills to inject per request (e.g. 10).
- **skills_similarity_threshold:** Minimum similarity (0–1). Skills below this are not injected.
- **skills_refresh_on_startup:** If true, skills_dir (and optional test dir) are synced to the vector store on every Core startup.

### 2.5 Optional: test folder and incremental sync

- **skills_test_dir:** Optional path (e.g. `skills_test`). Skills in this folder are **fully synced every time** (all re-embedded and upserted with id `test__<folder>`). Use this to **test** new or updated skills; see §4.
- **skills_incremental_sync:** When **true**, only **new** skills in **skills_dir** (not already in the vector store) are embedded and inserted. Existing skills are **not** re-processed. Use this in production to avoid re-embedding many skills on every restart. To **update** an existing skill’s embedding after you changed SKILL.md, set this to **false** once, restart, then set it back to **true** if you want.

Example:

```yaml
skills_test_dir: skills_test
skills_incremental_sync: false
```

---

## 3. How to implement a skill (developers)

### 3.1 Folder structure

A **skill** is a **folder** under **skills_dir** (e.g. `skills/`). The **folder name** is the **skill id** used by the system and by the **run_skill** tool (e.g. `example`, `social-media-agent-1.0.0`).

Required:

- **SKILL.md** — One file per skill. It must contain at least a **name** and **description** in YAML frontmatter.

Optional:

- **scripts/** — Subfolder with scripts (e.g. `run.sh`, `main.py`) that the LLM can run via the **run_skill** tool. Scripts are sandboxed and can be allowlisted in config (see **tools.run_skill_allowlist** in core.yml).
- Other files (e.g. README, references) — For humans; the loader only requires SKILL.md.

Example layout:

```
skills/
  example/
    SKILL.md
  my-weather-skill/
    SKILL.md
    scripts/
      run.sh
      main.py
```

### 3.2 SKILL.md format

**SKILL.md** has two parts:

1. **YAML frontmatter** (between the first `---` and the second `---`): at least **name** and **description**.
2. **Body** (after the second `---`): optional Markdown. It can describe how to use tools, step-by-step workflows, or when to call **run_skill**.

**Minimal example:**

```markdown
---
name: example
description: Example skill to show SKILL.md format. Does nothing by itself; the model can refer to it when use_skills is enabled.
---
This is the optional body. You can add usage notes or instructions here.
```

**Larger example (workflow + tools):**

```markdown
---
name: social-media-agent
description: Autonomous social media management for X/Twitter using only HomeClaw native tools. Use when a user wants to automate X posting, generate content, track engagement, or build an audience.
---

# Social Media Agent

Manage an X/Twitter account using HomeClaw's built-in tools.

## Core Tools

- `browser_*` — Post tweets, engage with posts
- `fetch_url` — Scrape profiles, trending topics
- `cron_schedule` — Schedule regular posting
- `memory_search` — Track what was posted

## Posting a Tweet

1. Navigate to x.com/compose/post with browser_navigate
2. Use browser_snapshot to find the text input
3. Use browser_type to enter the tweet text
4. Use browser_click on the Post button
```

- **name:** Display name for the skill (can differ from the folder name).
- **description:** Short summary. This is what the LLM uses to decide when the skill is relevant. When vector search is on, this (and optionally the start of the body) is embedded for similarity search.
- **Body:** Instructions for the LLM (which tools to use, in what order). The body is optional and may not be injected by default (to save tokens); check **include_body** in the loader if you need it in the prompt.

### 3.3 Skill id: folder name vs frontmatter name

- The **folder name** (e.g. `social-media-agent-1.0.0`) is the **skill_id** used by **run_skill(skill_name, script, ...)**. The LLM must pass this folder name when calling **run_skill**.
- The **frontmatter `name`** (e.g. `social-media-agent`) is for display. If it differs from the folder name, the system prompt will show something like: **social-media-agent** (run_skill skill_name: `social-media-agent-1.0.0`) so the LLM knows which value to use.

So: **folder name = id for run_skill; frontmatter name = human-readable name.**

### 3.4 Optional: scripts and run_skill

If your skill needs to run a **script** (e.g. a shell script or Python script):

1. Create a **scripts/** folder inside the skill folder.
2. Put your script there (e.g. `run.sh`, `main.py`).
3. In **config/core.yml**, under **tools**, set **run_skill_allowlist** to the script names you allow (e.g. `["run.sh", "main.py"]`). Only those filenames can be executed.
4. The LLM can then call **run_skill(skill_name=<folder>, script=run.sh, args=[...])**. Core runs the script in a subprocess, sandboxed under that skill folder.

The **skill_name** argument must be the **folder name** under skills_dir (e.g. `social-media-agent-1.0.0`), not only the frontmatter `name`.

### 3.5 Tool names in HomeClaw

When you write instructions in the body, use the **tool names** that HomeClaw actually has. Common ones:

| You might see in other docs | HomeClaw tool |
|-----------------------------|------------------|
| web_fetch | fetch_url |
| browser (navigate, click, type) | browser_navigate, browser_snapshot, browser_click, browser_type |
| cron | cron_schedule, cron_list, cron_remove |
| sessions_spawn | sessions_spawn |
| memory_search / files | memory_search, memory_get, file_read, folder_list |

See **config/workspace/TOOLS.md** and **skills/README.md** for the full list and compatibility notes.

### 3.6 Summary for implementers

1. Create a **folder** under **skills_dir** (e.g. `skills/my-skill/`).
2. Add **SKILL.md** with **name** and **description** in the frontmatter, and optional body with tool workflows.
3. Optionally add **scripts/** and list allowed script names in **tools.run_skill_allowlist**.
4. No code change is required; the next sync or request will pick up the skill.

---

## 4. How to test skills

### 4.1 Use the test folder (recommended for new or changed skills)

1. **Create a test directory** (e.g. `skills_test/`) and set it in config:
   ```yaml
   skills_test_dir: skills_test
   ```
2. **Put the skill there** with the **same structure** as in production (e.g. `skills_test/my-skill/SKILL.md`). You do **not** need to rename the folder to `test_xxx`; the system automatically stores test skills with id **test__&lt;folder_name&gt;** (e.g. `test__my-skill`).
3. Set **skills_use_vector_search: true** and **skills_refresh_on_startup: true**. On each startup, the **test folder is fully synced**: all skills in it are re-embedded and upserted, so any change to SKILL.md is reflected immediately.
4. **Test** by chatting with the assistant; it will retrieve test skills (ids starting with `test__`) when they match the query and load their content from **skills_test_dir**.
5. When the skill is ready, **move** the folder from **skills_test_dir** to **skills_dir** (e.g. `skills/my-skill/`). On the next startup:
   - The **test__my-skill** entry is **removed** from the vector store (cleanup: test ids whose folder is no longer in the test dir are deleted).
   - The skill in **skills_dir** is either added (if incremental) or upserted (if full sync). With **skills_incremental_sync: true**, it will be added as a new skill; with **false**, all skills in skills_dir are re-synced.

### 4.2 Updating an existing skill (no test folder)

If you only changed an existing skill in **skills_dir** (e.g. edited SKILL.md):

1. Set **skills_incremental_sync: false** in **config/core.yml**.
2. Restart Core once. A **full sync** runs: all skills in skills_dir are re-embedded and upserted, so your updated skill gets a new embedding.
3. Optionally set **skills_incremental_sync: true** again and restart if you want incremental sync for future restarts.

### 4.3 Workflow summary

| Goal | What to do |
|------|------------|
| **Implement a new skill** | Develop it in **skills_test_dir** (full sync every time). When ready, move folder to **skills_dir**. With incremental sync, it will be added as new on next startup. |
| **Update an existing skill** | Option A: Put the updated version in **skills_test_dir**, test, then move to **skills_dir** and run once with **skills_incremental_sync: false**. Option B: Edit in **skills_dir**, set **skills_incremental_sync: false**, restart once, then set back to **true** if desired. |
| **Remove a skill** | Remove its folder from **skills_dir** (and from **skills_test_dir** if it was there). Test ids not in the test folder are deleted on next sync; production ids are lazily deleted when the system tries to load that skill and the folder is missing. |

---

## 5. Config reference (skills)

All skills-related options in **config/core.yml**:

| Option | Default | Meaning |
|--------|--------|---------|
| **use_skills** | true | If true, skills are loaded and injected into the system prompt. |
| **skills_dir** | skills | Directory scanned for skill folders (each with SKILL.md). |
| **skills_max_in_prompt** | 0 | When not using vector search: max number of skills to inject (0 = no limit). |
| **skills_use_vector_search** | false | When true, skills are retrieved by similarity to the user query instead of listing all (or first N). |
| **skills_vector_collection** | homeclaw_skills | Chroma collection name for skill embeddings (separate from memory). |
| **skills_max_retrieved** | 10 | Max skills to retrieve and inject per request when vector search is on. |
| **skills_similarity_threshold** | 0.0 | Min similarity (0–1); skills below this are not injected. |
| **skills_refresh_on_startup** | true | If true, sync skills_dir (and optional skills_test_dir) to the vector store on startup when vector search is on. |
| **skills_test_dir** | "" | Optional. If set (e.g. skills_test), this dir is fully synced every time; ids are stored as test__&lt;folder&gt;. |
| **skills_incremental_sync** | false | When true, only skills **not** already in the vector store are embedded and inserted for **skills_dir**; existing skills are skipped. |

**Tools config** (for run_skill):

- **tools.run_skill_allowlist:** List of script names allowed to run (e.g. `["run.sh", "main.py", "generate_image.py"]`). Empty list `[]` or unset = allow any script under a skill's `scripts/` folder; non-empty = only those names.
- **tools.run_skill_timeout:** Timeout in seconds for running a skill script (default 60).

---

## 6. Examples in this repo

- **skills/example/** — Minimal skill: SKILL.md with name, description, and a short body. No scripts.
- **skills/social-media-agent-1.0.0/** — Richer example: frontmatter + long body describing tools and workflows (browser, cron, memory, etc.). Good reference for writing workflow-style skills.

See also **skills/README.md** for tool compatibility (e.g. web_fetch → fetch_url, cron, sessions_spawn) and **docs/ToolsSkillsPlugins.md** for how skills relate to tools and plugins.

---

## 7. Quick reference

- **Add a skill:** New folder under **skills_dir** with **SKILL.md** (name + description).
- **Use skills:** **use_skills: true**, **skills_dir** set; optionally **skills_use_vector_search: true** and related options.
- **Test a skill:** Put it in **skills_test_dir**, set **skills_test_dir** in config; test; then move to **skills_dir**.
- **Update a skill:** Full sync once (**skills_incremental_sync: false**, restart), or use test dir then move.
- **run_skill:** LLM calls **run_skill(skill_name=&lt;folder&gt;, script=&lt;file&gt;, args=[...])**; **skill_name** must be the **folder name** under skills_dir (or under skills_test_dir for test skills, with id test__&lt;folder&gt;).
