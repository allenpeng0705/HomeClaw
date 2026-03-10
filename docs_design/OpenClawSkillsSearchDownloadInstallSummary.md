# How OpenClaw Uses Skills: Search, Download, Install (Summary)

This document summarizes how **OpenClaw** (latest code in `../openclaw`) discovers, searches, downloads, and installs skills, based on the OpenClaw codebase and docs.

---

## 1. Where skills come from (loading, not “search” in the gateway)

OpenClaw **loads** skills from several **directories** at runtime. There is **no built-in “search the internet for skills”** inside the gateway. Discovery is **directory-based**:

| Source | Path | Precedence (name conflict) |
|--------|------|----------------------------|
| **Bundled** | Shipped with install (npm package or OpenClaw.app) | Lowest |
| **Extra dirs** | `skills.load.extraDirs` in `~/.openclaw/openclaw.json` | Low |
| **Managed** | `~/.openclaw/skills` | Medium |
| **AgentSkills personal** | `~/.agents/skills` | Medium-high |
| **AgentSkills project** | `<workspace>/.agents/skills` | High |
| **Workspace** | `<workspace>/skills` | **Highest** |

- **Precedence:** For the same skill name, workspace wins, then managed, then bundled.
- **Implementation:** `src/agents/skills/workspace.ts` — `loadSkillEntries()` scans these dirs, uses `loadSkillsFromDir` (from `@mariozechner/pi-coding-agent`), merges by name with the order above.
- **Plugins** can add skill dirs via `openclaw.plugin.json`; they are merged into `extraDirs` and follow the same loading rules.

---

## 2. Search and install: ClawHub + CLI (outside the gateway)

**Search** and **download/install** are **not** implemented inside the OpenClaw gateway. They are done by:

- **ClawHub** — public skill registry at [clawhub.ai](https://clawhub.ai) (docs also mention clawhub.com).
- **ClawHub CLI** — npm package `clawhub`, used from the **command line** (or by the agent via the **clawhub skill** and tools).

### ClawHub (registry + site)

- **What it is:** Public registry for OpenClaw skills; versioned bundles + metadata; discovery (search, tags, usage).
- **Flow:** Publish → ClawHub stores bundle and version → Registry indexes for search → Users **browse, download, install** (via CLI or site).
- **Search:** Vector/embedding search (not just keywords).
- **Downloads:** Zip per version; CLI uses this to install into a skills directory.

### ClawHub CLI (`clawhub`)

- **Install CLI:** `npm i -g clawhub` (or pnpm).
- **Auth (for publish):** `clawhub login` (browser or `--token`), `clawhub logout`, `clawhub whoami`.
- **Search:**  
  `clawhub search "query"`  
  Optional: `--limit <n>`.
- **Install:**  
  `clawhub install <slug>`  
  Optional: `--version <version>`, `--force` (overwrite).  
  By default installs into `./skills` under current directory (or OpenClaw workspace if set). Uses `--workdir` / `--dir` or env `CLAWHUB_WORKDIR` to override.
- **Update:**  
  `clawhub update <slug>` or `clawhub update --all`  
  Optional: `--version`, `--force`, `--no-input`.
- **List (installed):**  
  `clawhub list`  
  Reads `.clawhub/lock.json` under workdir.
- **Publish:**  
  `clawhub publish <path>`  
  With `--slug`, `--name`, `--version`, `--changelog`, `--tags`.
- **Sync (scan + publish):**  
  `clawhub sync`  
  With `--root`, `--all`, `--dry-run`, `--bump`, `--changelog`, `--tags`, `--concurrency`.

So: **search** = `clawhub search "..."`. **Download/install** = `clawhub install <slug>` (CLI downloads from registry and writes into a skills directory). The **gateway** does not call the registry API itself; it only **loads** whatever is already on disk in the directories above.

---

## 3. “Automatic” search and install (via the agent + clawhub skill)

The README says: *“With ClawHub enabled, the agent can search for skills automatically and pull in new ones as needed.”*

This is implemented by:

- **ClawHub skill** — `skills/clawhub/SKILL.md` in OpenClaw. It teaches the agent to use the **clawhub CLI** (search, install, update, publish).
- **Agent has the clawhub skill** → model sees its description and instructions → user says e.g. “find a skill for X” or “install the calendar skill” → agent can call **tools** (e.g. `exec` or a run-skill/script tool) to run:
  - `clawhub search "calendar"`
  - `clawhub install some-skill-slug`
- **Install target:** By default the CLI installs into `./skills` (or the OpenClaw workspace). That directory is exactly **workspace skills** (`<workspace>/skills`), which the gateway already loads. So after `clawhub install`, the next session (or skills refresh) **picks up** the new skill from disk.

So “automatic” = **agent-driven**: the agent uses the clawhub skill + CLI (search → install) and the gateway then loads the new skill from the workspace (or managed) skills dir. There is no separate “gateway calls ClawHub API to search/install” path; it’s CLI + disk.

---

## 4. In-gateway “skill install” (dependency install, not registry download)

The gateway does have a **skills.install** RPC (`src/gateway/server-methods/skills.ts`): it runs **dependency installers** for a skill that is **already on disk** (e.g. install a binary or Node package required by that skill). It does **not** download the skill from ClawHub.

- **skills.install** calls `installSkill()` in `src/agents/skills-install.ts`.
- **installSkill**:
  - Finds the skill entry by name in the workspace (and other loaded sources).
  - Reads `metadata.openclaw.install` from the skill’s SKILL.md (installer specs: brew, node, go, uv, **download**).
  - Runs the **chosen installer** (e.g. `brew install formula`, `npm i -g pkg`, or **download** from a URL + extract into the skill’s tools dir).
- **Download installer** (`src/agents/skills-install-download.ts`):  
  Uses a **URL from the skill’s install spec** (e.g. a fixed release URL), with SSRF guards. This is for **dependencies** (binaries, runtimes), not for “download skill from ClawHub”. ClawHub install is done by the **clawhub** CLI, which writes the skill folder under `skills/`.

So:

- **Search:** ClawHub (site or `clawhub search`).
- **Download skill from registry:** `clawhub install <slug>` (CLI).
- **Install skill’s dependencies (binaries, etc.):** Gateway `skills.install` (or macOS Skills UI) using `metadata.openclaw.install` specs.

---

## 5. Skill format and gating

- **Format:** AgentSkills-compatible; each skill is a folder with **SKILL.md** (YAML frontmatter + body). Frontmatter: `name`, `description`, optional `metadata` (single-line JSON).
- **Gating:** At load time, skills are filtered by `metadata.openclaw` (e.g. `requires.bins`, `requires.env`, `requires.config`, `os`). Only **eligible** skills are included in the snapshot and in the prompt.
- **Config:** `~/.openclaw/openclaw.json` under `skills.entries.<name>` can enable/disable, set env, apiKey, config. Session snapshot is taken at session start; optional watcher can refresh when SKILL.md files change.

---

## 6. Short comparison with HomeClaw

| Aspect | OpenClaw | HomeClaw |
|--------|----------|----------|
| **Skill locations** | Bundled, `~/.openclaw/skills`, `<workspace>/skills`, extraDirs, plugin dirs | `skills/` (and optional extra dirs from config) |
| **Search** | Via ClawHub (site or `clawhub search`) | No built-in registry search |
| **Download/install from registry** | `clawhub install <slug>` (CLI) into workspace/managed dir | N/A (no ClawHub in HomeClaw) |
| **“Automatic” install** | Agent uses **clawhub skill** + exec to run `clawhub search` / `clawhub install`; gateway loads from disk | N/A |
| **Dependency install** | Gateway `skills.install` runs install specs (brew/node/go/uv/download) for a skill already on disk | run_skill can run scripts; no generic “install deps” RPC like OpenClaw |

---

## 7. When the user asks for something but the skill is not installed

OpenClaw does **not** have a dedicated “skill not found” handler that intercepts the request or injects a special reply. Behavior is driven by **what’s in the prompt** and **model behavior**.

### What the model sees

- Only **eligible** (installed + gated) skills are included in the **&lt;available_skills&gt;** block in the system prompt. So if “calendar” is not installed, the model never sees a “calendar” skill in that list.
- The **Skills (mandatory)** section says:
  - “If exactly one skill clearly applies: read its SKILL.md at &lt;location&gt;, then follow it.”
  - “If **none clearly apply**: do not read any SKILL.md.”
- The **Documentation** section includes: **“Find new skills: https://clawhub.com”** (`src/agents/system-prompt.ts` → `buildDocsSection`).

### What happens in practice

1. **User asks for something that needs an uninstalled skill**  
   No skill in &lt;available_skills&gt; “clearly applies” (the right one isn’t there). The model is told not to read any SKILL.md in that case.

2. **No automatic install or special tool**  
   The gateway does not detect “user wanted X but skill missing” and does not auto-call ClawHub or inject a “install this skill” tool. There is no dedicated “skill not found” flow.

3. **Model can still respond**  
   - It can say it doesn’t have that capability and point the user to **clawhub.com** or to run **`npx clawhub search "…"`** (because “Find new skills: https://clawhub.com” is in the docs section).
   - If the **clawhub** skill is installed and eligible, the model **sees** that skill in &lt;available_skills&gt; and can use **exec** (or equivalent) to run `clawhub search "…"` and `clawhub install <slug>`, then tell the user a new skill was installed and they may need a new session.

4. **CLI-only hint**  
   When an admin runs `openclaw skills list` or `openclaw skills check`, the CLI appends: **“Tip: use \`npx clawhub\` to search, install, and sync skills.”** (`src/cli/skills-cli.format.ts` → `appendClawHubHint`). That does not affect the in-chat reply when a skill is missing.

### Summary

| Scenario | What OpenClaw does |
|---------|---------------------|
| User asks for something that needs an **uninstalled** skill | No special handler. Model only sees installed skills; “none clearly apply”; it can naturally say it doesn’t have that and point to clawhub.com or `clawhub search` (from docs line). |
| **Clawhub skill** is installed | Model can use exec to run `clawhub search` / `clawhub install` and then inform the user. |
| User asks for something that needs a skill that **is installed but missing deps** (e.g. binary) | Skill appears in list but may be “missing” (not eligible). Control UI / macOS app can show install options; gateway `skills.install` RPC can run the skill’s install spec (brew/node/download). |

So “when the user asks but the skill wasn’t installed” is handled by: (1) model only seeing installed skills, (2) docs line about ClawHub, and (3) optional clawhub skill so the model can run search/install via exec. There is no separate “suggest install” or “skill not found” pipeline in the gateway.

---

## 8. References in OpenClaw

- **Docs:** `docs/tools/clawhub.md`, `docs/tools/skills.md`, `docs/cli/skills.md`
- **Skill loading:** `src/agents/skills/workspace.ts` (`loadSkillEntries`, precedence, limits)
- **Skill install (deps):** `src/agents/skills-install.ts`, `src/agents/skills-install-download.ts`
- **Gateway skills RPC:** `src/gateway/server-methods/skills.ts` (`skills.status`, `skills.bins`, `skills.install`, `skills.update`)
- **ClawHub skill:** `skills/clawhub/SKILL.md`
- **System prompt (docs + skills section):** `src/agents/system-prompt.ts` (`buildDocsSection`, `buildSkillsSection`)
- **CLI ClawHub hint:** `src/cli/skills-cli.format.ts` (`appendClawHubHint`)
