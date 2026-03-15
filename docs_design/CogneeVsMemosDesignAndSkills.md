# Cognee vs MemOS: Design Differences and Using MemOS Skills in HomeClaw

This doc summarizes how **Cognee** and **MemOS** differ in data model and scoping, then focuses on **MemOS’s task/skill features** and how HomeClaw can use them beyond “store the same thing as Cognee.”

---

## 1. Storage and Scoping: Cognee vs MemOS

### 1.1 Cognee (user-based, dataset-centric)

| Aspect | Design |
|--------|--------|
| **Scope** | **One dataset per (user_id, agent_id)**. Dataset name: `memory_{user}_{agent}` (e.g. `memory_AllenPeng_HomeClaw`). |
| **Unit of storage** | **Dataset**. Each dataset holds raw text → after `cognify`, graph nodes/edges + vector embeddings. |
| **Identity** | No explicit “owner” field on nodes; scope is **implicit** via which dataset you add to or search. |
| **Multi-user/agent** | Different (user, agent) pairs → different datasets; no built-in “public” or cross-user visibility. |
| **Structure** | **Graph**: entities, relations, triplets. Search is graph completion + semantic over the graph. No notion of “tasks” or “skills.” |

So with Cognee we **store everything user-based**: each user+agent gets one dataset; all that user’s memories for that agent live in that dataset. There is no session, no task boundary, no skill entity—just graph + vector per dataset.

### 1.2 MemOS (owner + session, task + skill model)

| Aspect | Design |
|--------|--------|
| **Scope** | **Owner** (e.g. `agent:main` or `agent:{agentId}`). We map HomeClaw `(user_id, agent_id)` → single `agentId` string → owner `agent:{agentId}`. **Session** (`sessionKey`) groups messages into one conversation. |
| **Unit of storage** | **Chunks** (per turn, with `owner`), **tasks** (segments of a session with `owner`), **skills** (separate table + files, with `owner` and **visibility**: private/public). |
| **Identity** | **Explicit**: chunks, tasks, and skills have `owner`. Search uses `ownerFilter = ["agent:{agentId}", "public"]` so the agent sees only its own + public. |
| **Multi-agent** | **Memory isolation** by owner; **public memory** and **skill visibility** (private/public); tools like `memory_write_public`, `skill_publish`, `skill_search(scope=...)`. |
| **Structure** | **Chunks** (FTS + vector) → **Tasks** (boundaries by topic + idle timeout; status: active/completed/skipped; LLM summary: Goal, Key Steps, Result, Key Details) → **Skills** (SKILL.md, scripts, evals; generated/upgraded from tasks; versioned; quality score). |

So MemOS is **owner- and session-based**, with a **richer model**: not only “chunk” storage but **tasks** (conversation segments with summaries) and **skills** (reusable procedures with files and versions). Skills are first-class and can be created/upgraded automatically from completed tasks.

---

## 2. Summary Table

| Dimension | Cognee | MemOS |
|-----------|--------|--------|
| **Primary scope** | (user_id, agent_id) → one dataset | owner (e.g. agent:main), sessionKey |
| **What is stored** | Raw text → graph + vector per dataset | Chunks (owner) + tasks (owner) + skills (owner + visibility) |
| **Sessions** | No | Yes (sessionKey groups turns) |
| **Tasks** | No | Yes (boundaries, status, LLM summary) |
| **Skills** | No | Yes (DB + files, generated/upgraded from tasks) |
| **Multi-agent / public** | No | Yes (owner isolation, public memory, skill visibility) |
| **Search** | Graph + semantic over graph | FTS + vector over chunks; separate skill_search (FTS + vector + LLM relevance) |

So: **Cognee = user-scoped graph memory; MemOS = owner/session-scoped chunk + task + skill memory** with multi-agent and skill evolution.

---

## 3. MemOS Skills and Task Summaries (Details)

### 3.1 Task pipeline (already running in standalone)

- **Task boundary detection**: Per-turn LLM “SAME/NEW” topic + 2-hour idle timeout → segments a session into tasks. Status: `active` | `completed` | `skipped`.
- **Task summarization**: When a task completes, LLM writes **Goal, Key Steps, Result, Key Details** (and preserves code, commands, URLs, file paths, errors). Stored in `tasks.summary` and related chunks.
- **Quality filtering**: Tasks that are too short or trivial are marked `skipped` and excluded from search/skill pipeline.

So with the current MemOS standalone server, **task boundaries and task summaries are already produced**; they are stored in MemOS’s DB and used internally. HomeClaw today only uses **chunk search** (and merged search with Cognee); it does **not** yet expose “list my tasks” or “get task summary” to the agent.

### 3.2 Skill evolution (already wired in standalone)

- **After a task completes**, `SkillEvolver.onTaskCompleted` runs:
  1. **Rule filter**: Skip if task too small or low quality.
  2. **Find related skill**: FTS + vector over existing skills → LLM picks at most one skill that is **highly** related to the task (same domain).
  3. **If related skill found**: LLM evaluates whether to **upgrade** it (refine/extend/fix) from this task; if yes, `SkillUpgrader` produces a new version (changelog, version number). Chunks are linked to that skill.
  4. **If no related skill**: LLM evaluates whether the task is worth a **new skill**; if yes, `SkillGenerator` produces SKILL.md + scripts + references + evals. New skill is stored (DB + files under `skill.dirPath`), chunks linked to it. **Quality score** (0–10); below 6 → `draft`.
  5. **Auto-install**: If configured, generated/upgraded skills are copied to **workspaceDir/skills/<skill.name>** (SkillInstaller). In our standalone, `workspaceDir` is `stateDir/workspace` by default (e.g. `vendor/memos/data/workspace`).

So MemOS **does** memorize and generate skills: they live in SQLite (`skills`, `skill_versions`, `skill_embeddings`, FTS) and on disk (`dirPath` → SKILL.md, scripts). The standalone server already runs this pipeline; what’s missing is **exposing** tasks and skills to HomeClaw (APIs + tools).

### 3.3 Where skills live in MemOS

- **DB**: `skills` (id, name, description, version, status, owner, visibility, dirPath, qualityScore, …), `skill_versions`, `skill_embeddings`, FTS table `skills_fts`.
- **Disk**: Each skill has `dirPath` (e.g. under stateDir); contains SKILL.md and any generated scripts. **Installed** skills are copied to `workspaceDir/skills/<skill.name>` when `SkillInstaller.install()` runs (e.g. on auto-install after generation).

To use MemOS skills **in HomeClaw** we can:
- **Option A**: Expose MemOS skill/task APIs from the standalone server and add HomeClaw tools that call them (search skills, get task summary, get skill content).
- **Option B**: Point MemOS `workspaceDir` at HomeClaw’s `external_skills_dir` (or a subdir) so that MemOS “install” writes directly into the tree HomeClaw already scans for skills (e.g. `external_skills`). Then MemOS-generated skills appear as normal HomeClaw skills without extra sync.
- **Option C**: Keep MemOS workspace under `vendor/memos/data/workspace` and add a **sync** (API or tool) that copies selected skills from MemOS workspace into `external_skills_dir` so HomeClaw picks them up.

We can combine A + B or A + C depending on whether we want “one place” for MemOS state (B) or “clear separation + explicit sync” (C).

---

## 4. Using MemOS in HomeClaw Beyond “Same as Cognee”

Today, with **composite** memory we already do:

- **Add**: Same user message is sent to both Cognee and MemOS (Cognee → graph; MemOS → chunks + task boundaries + task summaries + skill evolution).
- **Search**: Merged chunk/graph results; MemOS hits can carry `task_id` but we don’t expose task/skill APIs yet.

To **get benefit from MemOS that Cognee does not provide**, we should:

1. **Expose task and skill APIs from the MemOS standalone server**  
   - List tasks (e.g. `GET /memory/tasks?agentId=...`).  
   - Get task summary (e.g. `GET /memory/task/:id/summary`).  
   - Skill search (e.g. `POST /memory/skill_search` with query, scope, agentId).  
   - Get skill by id (e.g. `GET /memory/skill/:id` or content by name).  
   So the agent (via HomeClaw) can **query tasks and skills**, not only raw chunk search.

2. **Add HomeClaw tools that call these APIs**  
   - e.g. `memos_task_summary(task_id)` — when a search hit has `task_id`, the agent can fetch the full structured summary (Goal, Key Steps, Result, Key Details).  
   - e.g. `memos_skill_search(query, scope)` — find skills by semantic + FTS + LLM relevance before using them.  
   - e.g. `memos_skill_get(skill_id)` or `memos_skill_content(name)` — get SKILL.md (and optionally scripts) to run or show.  
   So the agent can **use** MemOS’s memorized and generated skills, not just the same blob of text we also put in Cognee.

3. **Make MemOS-generated skills visible to HomeClaw’s skill system**  
   - Either set MemOS `workspaceDir` to HomeClaw’s `external_skills_dir` (or `external_skills_dir/memos`) so auto-install writes there (**Option B**).  
   - Or add a sync endpoint/tool that copies from MemOS workspace to `external_skills_dir` (**Option C**).  
   Then the existing HomeClaw skill loader (skills_dir / external_skills_dir) will see MemOS-generated skills as normal skills (SKILL.md in a folder).

4. **Optional: public memory and skill visibility**  
   - If we add `memory_write_public` and skill publish/unpublish to the standalone API, we can add corresponding HomeClaw tools so the agent can use multi-agent features when needed.

---

## 5. Recommended Next Steps

1. **Implement task/skill HTTP API in MemOS standalone**  
   - `GET /memory/tasks`, `GET /memory/task/:id/summary`, `POST /memory/skill_search`, `GET /memory/skill/:id` (and optionally skill by name).  
   - All should respect `agentId` → owner and (for skills) scope (self/public/mix).

2. **Add HomeClaw tools**  
   - `memos_task_summary`, `memos_skill_search`, `memos_skill_get` (and optionally “sync MemOS skills to external_skills” if using Option C).

3. **Configure workspaceDir for skills**  
   - Either in `memos-standalone.json`: set `workspaceDir` to `$HOMECLAW_ROOT/external_skills/memos` (or similar) so generated skills land where HomeClaw loads them; or add sync and keep workspace under vendor/memos/data.

4. **Document for users**  
   - “With composite memory, Cognee gives you user-based graph memory; MemOS gives you tasks and skills. Use these tools to read task summaries and to find/use MemOS-generated skills.”

This way we **don’t just save the same thing with Cognee**—we **use Cognee for user-based graph memory** and **use MemOS for tasks, summaries, and memorized/generated skills** inside HomeClaw.
