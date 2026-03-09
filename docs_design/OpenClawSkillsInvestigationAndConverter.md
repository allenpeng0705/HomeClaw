# OpenClaw Skills: Investigation, Reuse, and Converter Design

This document summarizes how **OpenClaw** uses skills, how **HomeClaw** can reuse them, and a design for a **converter** to download and convert OpenClaw skills for HomeClaw. It also clarifies script languages (Python, Node.js/TypeScript) and skill types (instruction-only vs script-based).

---

## 1. How OpenClaw Uses Skills

### 1.1 Two formats in the ecosystem

OpenClaw’s ecosystem uses **two** main ways to define skills:

| Format | Role | Where |
|--------|------|--------|
| **SKILL.md** | Primary skill definition: YAML frontmatter + Markdown body. Name, description, instructions for the LLM. | [openclaw/skills](https://github.com/openclaw/skills) repo; workspace `~/.openclaw/workspace/skills/` or bundled. |
| **skill.yaml** | Manifest for ClawHub/publishing: identity, permissions, config, **entry point** (how to run). | Used when publishing to ClawHub; defines entry point type and path. |

- **SKILL.md** is what the agent sees: name, description, and instructions (and optional metadata like `metadata.clawdbot` with emoji, `requires`, `os`).
- **skill.yaml** is the publish/install manifest: `name`, `version`, `author`, `description`, `permissions`, `config`, and **`entryPoint`** (`type`, `path`, optional `prompt`).

So: **SKILL.md** = “what the skill is and how to use it”; **skill.yaml** = “how to run it and what it needs.”

### 1.2 Entry point types (OpenClaw)

From [OpenClaw Creating Skills](https://docs.openclaw.ai/tools/creating-skills) and [Skill Manifest Reference](https://openclawai.me/blog/skill-manifest-reference):

| entryPoint.type | Meaning | HomeClaw equivalent |
|-----------------|--------|----------------------|
| **natural** | No script; LLM follows natural-language instructions (optionally with `prompt` in manifest). | **Instruction-only skill**: SKILL.md only, no `scripts/`. Model follows body + tools. |
| **typescript** | TypeScript/JavaScript module; path points to `.ts` or `.js`. OpenClaw runs in **Node.js**; complex skills use `@openclaw/sdk`. | **Script skill**: put compiled `.js` (or `.mjs`/`.cjs`) in `scripts/`; HomeClaw runs via `run_skill` with **node** (already supported). |
| **shell** | Shell script; path points to `.sh` (or similar). | **Script skill**: put `.sh` in `scripts/`; HomeClaw runs via `run_skill` with bash/WSL on Windows. |

So OpenClaw **does** use **Node.js** (TypeScript/JavaScript) for skill scripts when `entryPoint.type === 'typescript'`. Python appears in some skills (e.g. ontology scripts) as helper/scripts; the primary “full control” path in OpenClaw docs is TypeScript + `@openclaw/sdk`.

### 1.3 OpenClaw skill layout (GitHub / workspace)

Typical layout:

- **SKILL.md** — required; frontmatter + body.
- **scripts/** — optional; automation scripts (`.py`, `.ts`/`.js`, `.sh`).
- **references/** — optional; docs/examples for the model.
- **skill.yaml** — optional in repo; used for ClawHub publish (name, version, entryPoint, permissions, config).

Skills are loaded from (in order): workspace `/skills`, then `~/.openclaw/skills`, then bundled. The [openclaw/skills](https://github.com/openclaw/skills) repo archives skills from clawhub.com; structure is skill folders, each with SKILL.md and often scripts.

---

## 2. How HomeClaw Uses Skills

### 2.1 Loader and format

- **Loader:** `base/skills.py` scans `skills_dir` (default `skills/`) for subdirs containing **SKILL.md**.
- **Format:** SKILL.md = YAML frontmatter (`---` … `---`) + Markdown body. Required: `name`, `description`. Optional: `keywords`, `trigger`, `metadata`, etc.
- **Injection:** When `use_skills: true`, Core injects “Available skills” (name, description, optional body for selected skills) into the system prompt. Optional vector search (`skills_use_vector_search`) by description/body.

So HomeClaw is **SKILL.md-centric**; it does not read `skill.yaml`. Compatibility with OpenClaw is therefore: **same SKILL.md format** + **same idea of scripts in `scripts/`**.

### 2.2 run_skill and script languages

`run_skill` in `tools/builtin.py` runs a script from the skill’s **scripts/** folder. Supported extensions:

| Extension | Runtime | Notes |
|-----------|---------|--------|
| **.py, .pyw** | Python (Core’s `sys.executable` or in-process if in `run_skill_py_in_process_skills`) | Default: subprocess. Optional in-process for listed skills. |
| **.js, .mjs, .cjs** | **Node.js** (`node` from PATH) | Subprocess; `cwd` = skill folder; env includes `HOMECLAW_OUTPUT_DIR`, `HOMECLAW_USER_LOCATION`, keyed overrides from user config. |
| **.sh, .bash** | bash (or WSL on Windows if no bash) | Subprocess. |

So HomeClaw **already supports Node.js** for skill scripts (`.js`, `.mjs`, `.cjs`). No change needed to run OpenClaw skills that ship a JS entry point.

### 2.3 Instruction-only vs script-based

- **Instruction-only:** Skill folder has **SKILL.md** but **no** `scripts/` (or empty). Model uses **run_skill(skill_name=…)** with **no** `script`; Core returns a short confirmation and instructs the model to continue in the same turn using tools (e.g. document_read, save_result_page, file_write). No script is executed.
- **Script-based:** Skill folder has **scripts/** with at least one file. Model calls **run_skill(skill_name=…, script=…, args=[…])**. Core runs the script (Python / Node / shell) and returns stdout (and stderr) to the model.

So we can reuse:
- **Instruction-only OpenClaw skills** by copying the folder and keeping SKILL.md (and references/ if useful); no converter for “script” needed.
- **Script-based OpenClaw skills** by copying the folder and ensuring the runnable is one of `.py`, `.js`/`.mjs`/`.cjs`, or `.sh` in `scripts/`.

---

## 3. Reusing OpenClaw Skills in HomeClaw

### 3.1 What already matches

- **SKILL.md:** Same idea (frontmatter + body). OpenClaw’s frontmatter may include extra keys (`metadata`, `compatibility`, etc.); HomeClaw’s loader keeps name, description, body, and can preserve other keys. No conversion *required* for SKILL.md.
- **scripts/:** Same idea. If an OpenClaw skill has `scripts/` with `.py`, `.js`/`.mjs`/`.cjs`, or `.sh`, HomeClaw can run them via `run_skill` as-is, provided:
  - The script is **invocable** as a single file (e.g. `node scripts/main.js args…`).
  - It does not depend on OpenClaw-only APIs (e.g. `@openclaw/sdk`, Gateway-specific env) unless we add adapters or document limitations.

### 3.2 Differences to handle

| Aspect | OpenClaw | HomeClaw | Reuse strategy |
|--------|----------|----------|-----------------|
| Manifest | skill.yaml (entryPoint, permissions, config) | No skill.yaml; config in core.yml / user.yml / skill config.yml | Converter can map skill.yaml → SKILL.md frontmatter or to a short “Config” section in body; config/API keys via HomeClaw’s keyed skill config or env. |
| Entry point | typescript → .ts/.js path; shell → .sh; natural → no script | run_skill(script=filename) with file in scripts/ | Ensure the **file** that OpenClaw would run is present in `scripts/` with a supported extension. For TypeScript: `.ts` runs via **tsx** or **ts-node** when in PATH; otherwise use compiled `.js` (or `.mjs`/`.cjs`). |
| Tool names | May reference OpenClaw tool names (e.g. web_fetch, browser_*) | HomeClaw names (fetch_url, browser_navigate, …) | Converter or doc can map names; or add a “Tool names” section in converted SKILL.md (see skills/README.md). |
| SDK / runtime | TypeScript skills may use `@openclaw/sdk` (browser, notify, etc.) | No OpenClaw SDK | Skills that rely on SDK need a **Python or Node** reimplementation using HomeClaw tools/plugins (e.g. route_to_plugin for browser), or we document “partial support / instruction-only” and do not run the script. |

### 3.3 Summary: reuse without a converter

- **Instruction-only:** Copy the OpenClaw skill folder into `skills/`; keep SKILL.md (and references/). Optionally adjust tool names in the body to HomeClaw’s (fetch_url, browser_*, etc.).
- **Script-based (Python or shell):** Copy folder; ensure script is under `scripts/`. Add script name to `tools.run_skill_allowlist` if you use an allowlist.
- **Script-based (TypeScript/JS):** Copy folder; put `.js`/`.mjs`/`.cjs` in `scripts/` (Node) or `.ts` in `scripts/` (requires **tsx** or **ts-node** on PATH). If the skill depends on `@openclaw/sdk`, treat as “needs port” or instruction-only.

---

## 4. Converter: Download and Convert OpenClaw Skills

### 4.1 Goals

- **Download** OpenClaw skills from a source (e.g. GitHub `openclaw/skills` subtree, or a ClawHub API if available).
- **Normalize** to HomeClaw layout: one folder per skill under `skills/` with **SKILL.md** and optional **scripts/**.
- **Map** skill.yaml → SKILL.md (frontmatter + optional “Config” section) and ensure the runnable script (if any) is in `scripts/` with a supported extension.

**external_skills folder** — HomeClaw supports a second skills folder, **external_skills_dir** (default: `external_skills`). It is loaded and used the same way as `skills/`. Put converted OpenClaw skills in `external_skills/`; when a skill is stable and often used, move it to `skills/`. Set `external_skills_dir: ""` to disable. See `config/core.yml` and `config/skills_and_plugins.yml`.

### 4.2 Source options

| Source | Pros | Cons |
|--------|------|------|
| **GitHub openclaw/skills** | Single repo; many skills; clone or sparse checkout | Repo is “all versions archived”; structure may vary; need to pick a skill path (e.g. `skills/<author>/<skill-name>/`). |
| **ClawHub** | Official registry; install flow | May require API or CLI; format may be package (tarball) with skill.yaml. |
| **Direct URL / tarball** | Flexible | One-off; no single index. |

Recommendation: start with **GitHub** (clone or download per skill folder); optionally add ClawHub later if they expose an API or tarball URL.

### 4.3 Conversion steps (per skill)

1. **Input:** A folder (from GitHub or unpacked tarball) containing at least SKILL.md, optionally skill.yaml, scripts/, references/.
2. **Output:** A folder under HomeClaw `skills/` with:
   - **SKILL.md** — From source SKILL.md; if skill.yaml exists, merge: description, name, version (e.g. into frontmatter or body); add a short “Config / Permissions” section from skill.yaml if useful.
   - **scripts/** — Copy over files that are runnable:
     - `.py`, `.sh`, `.bash` → copy as-is.
     - `.ts` → run via **tsx** or **ts-node** when in PATH; otherwise compile to `.js` and put in scripts/. Converter copies `.ts` as-is; no compile step required.
     - `.js`, `.mjs`, `.cjs` → copy as-is.
   - **references/** — Copy as-is (optional).
3. **Tool name hints:** Optionally append (or inject in body) a short “HomeClaw tool names” block using the mapping from skills/README.md (e.g. web_fetch → fetch_url, browser → browser_navigate, etc.).
4. **Allowlist:** Converter can output a suggested `run_skill_allowlist` snippet (list of script filenames) for core.yml.

### 4.4 Script language matrix

| OpenClaw entryPoint / file | HomeClaw run_skill | Converter action |
|----------------------------|--------------------|-------------------|
| natural (no script) | No script; instruction-only | SKILL.md only; no scripts/ or leave empty. |
| shell, path: `scripts/run.sh` | run_skill(…, script=`run.sh`) | Copy `scripts/run.sh` into `scripts/`. |
| typescript, path: `dist/index.js` or `src/index.ts` | run_skill(…, script=`index.js` or `index.ts`) | Copy `dist/index.js` to `scripts/index.js`, or copy `.ts` to `scripts/`; HomeClaw runs `.ts` if tsx/ts-node is in PATH. |
| Python (in scripts/) | run_skill(…, script=`main.py`) | Copy `scripts/main.py` into `scripts/`. |

### 4.5 Implementation outline

- **Converter script:** `scripts/convert_openclaw_skill.py` — converts a **local** OpenClaw skill folder to HomeClaw layout.
  - Usage: `python scripts/convert_openclaw_skill.py /path/to/openclaw-skill-folder [--output skills/my-skill-1.0.0] [--dry-run]`
  - Copies SKILL.md; merges skill.yaml name/description/version into frontmatter if present; copies `scripts/` (only .py, .js, .mjs, .cjs, .sh); copies `references/`; prints suggested `run_skill_allowlist`.
- **Download from GitHub:** Clone or fetch a subtree of `openclaw/skills`, then run the converter on each skill folder:
  - `git clone --depth 1 --filter=blob:none https://github.com/openclaw/skills.git /tmp/openclaw-skills`
  - Then for each skill: `python scripts/convert_openclaw_skill.py /tmp/openclaw-skills/skills/<author>/<skill-name> --output skills/<skill-id>`
- **Convert (per skill):**
    - Read SKILL.md; if skill.yaml exists, read it and merge name/description/version into frontmatter or body.
    - Create `skills/<skill-id>/` (skill-id from folder name or skill.yaml name+version).
    - Copy SKILL.md (with optional edits); copy scripts/ (filter by extension); copy references/.
    - Optionally write a small `CONVERTED_FROM` or `openclaw_skill.yaml` for traceability.
  - **Report:** List converted skills and suggested allowlist entries.
- **Config:** Optional `config/openclaw_skills_sources.yml` or CLI args: list of GitHub paths or tarball URLs to pull.

### 4.6 Node.js and TypeScript

- **Node.js:** HomeClaw already runs `.js`/`.mjs`/`.cjs` in `run_skill` via `node`. No Core change needed.
- **TypeScript:** OpenClaw’s primary “full control” skill implementation is TypeScript. HomeClaw **run_skill** supports `.ts` when **tsx** or **ts-node** is in PATH (no compile step needed). Converter copies `.ts` files into `scripts/`; if the user has `npm install -g tsx` (or ts-node), TypeScript skills run as-is. Otherwise they can still compile to `.js` and use that.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| How does OpenClaw use skills? | SKILL.md (frontmatter + body) for instructions; optional skill.yaml for manifest (entryPoint: natural / typescript / shell). Scripts in scripts/; TypeScript/JS runs in Node.js. |
| Can we reuse them in HomeClaw? | Yes. Same SKILL.md format; same scripts/ idea. Instruction-only: copy folder. Script-based: copy folder; use .py, .js/.mjs/.cjs, .ts (requires tsx/ts-node in PATH), or .sh in scripts/. |
| Converter? | Download from GitHub (or ClawHub); normalize to skills/<id>/ with SKILL.md + scripts/; map skill.yaml into SKILL.md; copy runnable scripts; optionally add tool-name hints and allowlist snippet. |
| Instruction-only vs script? | Instruction-only = no scripts/; model follows SKILL.md and uses tools. Script-based = scripts/ present; model calls run_skill(skill_name, script, args). Both supported in HomeClaw. |
| Python vs Node.js? | HomeClaw supports both: .py via Python, .js/.mjs/.cjs via Node. OpenClaw uses Node.js (TypeScript) as the primary “full control” skill runtime; many skills also have or can have Python/shell. |
| Does OpenClaw use Node.js for skills? | Yes. Entry point type `typescript` and the “TypeScript Skills” path in OpenClaw docs run in Node.js; complex skills use `@openclaw/sdk`. |

---

## 6. OpenClaw source reference (clawdbot)

When aligning how HomeClaw runs skills and uses SKILL.md, refer to the **OpenClaw source** in the sibling repo **`../clawdbot`**. Key modules:

### 6.1 Loading skills and SKILL.md

- **`src/agents/skills/workspace.ts`** — `loadSkillEntries()` scans workspace/managed/bundled/extra dirs for folders with **SKILL.md**; parses frontmatter; `buildWorkspaceSkillsPrompt()` / `resolveSkillsPromptForRun()` build the prompt (name, description, **location** = path to SKILL.md).
- **`src/agents/skills/frontmatter.ts`** — Parses YAML frontmatter; metadata (emoji, requires.bins/env), invocation policy, optional command-dispatch (tool name, arg mode).
- **`src/agents/skills/types.ts`** — `SkillEntry`, `SkillCommandSpec` (name, skillName, description, optional dispatch to tool).

### 6.2 How the agent uses skills (Read-then-follow)

- **`src/agents/system-prompt.ts`** — Skills section: *"If exactly one skill clearly applies: read its SKILL.md at &lt;location&gt; with **Read**, then follow it."* The model does **not** call a generic run_skill(script, args); it uses **Read** to load SKILL.md, then follows the body (which may describe shell/scripts). Script execution is via the model running shell/exec from the doc.

### 6.3 User-invokable commands (/command)

- **`buildWorkspaceSkillCommandSpecs()`** (workspace.ts) — One `SkillCommandSpec` per skill; optional frontmatter `command-dispatch: tool` + `command-tool: <toolName>` so `/command args` invokes that tool with raw args.
- **`src/auto-reply/skill-commands.ts`** — `resolveSkillCommandInvocation()` parses e.g. `/weather London` or `/skill weather London` and returns the command + args for the runner.

### 6.4 OpenClaw vs HomeClaw (running skills)

| Aspect | OpenClaw (clawdbot) | HomeClaw |
|--------|---------------------|----------|
| Discovery | Prompt lists name, description, **location** (path to SKILL.md). | Prompt lists name, description, folder, optional body. |
| Use | Model **reads** SKILL.md at location with Read, then follows body (may run shell from doc). | Model calls **run_skill**(skill_name, script, args); script/args from SKILL.md. |
| Scripts | Described in SKILL.md; model runs via shell/exec. | **run_skill** tool; Core runs script in scripts/ (Python/Node/shell). |

**Takeaways:** (1) SKILL.md format is aligned. (2) Including **path to SKILL.md** in the prompt would let the model `file_read` it (OpenClaw-style). (3) HomeClaw keeps **run_skill(script, args)** for script execution. (4) OpenClaw `skills/skill-creator/SKILL.md` is a good reference for progressive disclosure and layout.

---

## 7. References

- HomeClaw: `base/skills.py`, `tools/builtin.py` (`_run_skill_executor`), `skills/README.md`, `docs_design/SkillsGuide.md`.
- OpenClaw: [Creating Skills](https://docs.openclaw.ai/tools/creating-skills), [Building Custom Skills](https://openclawai.me/blog/building-skills), [Skill Manifest Reference](https://openclawai.me/blog/skill-manifest-reference).
- Repo: [openclaw/skills](https://github.com/openclaw/skills) (archived skills from ClawHub).
- HOW_TO_USE.md § “Reusing skills from OpenClaw”; docs/promote-homeclaw.md § “Skills: Reuse OpenClaw Skillsets”.
