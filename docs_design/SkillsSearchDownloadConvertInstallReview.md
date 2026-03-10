# Skills Search, Download, Convert, and Install — Workflow Review

This document reviews HomeClaw’s end-to-end workflow for **searching** (ClawHub), **downloading** (`clawhub install`), **converting** (OpenClaw → HomeClaw), and **loading** skills, and records refinements applied for correctness and consistency.

---

## 1. Flow Overview

| Step | What happens | Where |
|------|----------------|-------|
| **Search** | User searches ClawHub registry by query. | Companion (Core API), Portal (direct), CLI (`python -m main skills search`) |
| **Download** | `clawhub install <spec>` runs with `cwd=clawhub_download_dir` (e.g. `downloads/`). OpenClaw skill is written under that dir (often `downloads/skills/<id>` or nested). | `base/clawhub_integration.py` → `clawhub_install()` |
| **Locate** | After install, we locate the installed folder (exact or partial match by `skill_id`). | `find_openclaw_installed_skill_dir()` |
| **Convert** | OpenClaw skill folder → HomeClaw layout (SKILL.md, scripts/, references/) under `external_skills_dir`. | `convert_installed_openclaw_skill_to_homeclaw()` → `scripts/convert_openclaw_skill.py` |
| **Load** | Core loads skills from `skills_dir`, then `external_skills_dir`, then `skills_extra_dirs` (first match per folder name wins). | `base/skills.py` → `get_all_skills_dirs()`, `load_skills_from_dirs()`; prompt in `core/llm_loop.py` |
| **Remove** | User can remove only skills under `external_skills_dir` (built-in `skills/` protected). | `base/skills.py` → `remove_skill_folder()`; API/Portal/CLI |

---

## 2. Entry Points and Consistency

- **Companion app** → Core HTTP: `GET /api/skills/list`, `GET /api/skills/search?query=`, `POST /api/skills/install`, `POST /api/skills/remove`. Core runs `clawhub` and uses `Util().root_path()`, `external_skills_dir`, `clawhub_download_dir` from config.
- **Portal** → Same logic but inside Portal process: uses `portal_config.ROOT_DIR` (project root) and reads `core.yml` for `external_skills_dir` / `clawhub_download_dir`. Search/install must use the same auth (e.g. `clawhub_token`) as Core when available.
- **CLI** → `python -m main skills search|install|remove`. Uses `Util().get_core_metadata()` and `Util().root_path()`; `skill_id_hint=None` for install so `sid` is derived from spec (e.g. `summarize@1.0.0` → `summarize`).

All three must resolve the same project root and config so that install-from-Portal and install-from-Companion (via Core) write to the same `external_skills/` that Core loads.

---

## 3. Config Keys (core.yml)

| Key | Purpose | Default |
|-----|---------|--------|
| `use_skills` | Whether to load and inject skills into the prompt. | — |
| `skills_dir` | Built-in skills directory (relative to root or absolute). | `skills` |
| `external_skills_dir` | Converted/external skills (ClawHub install target). Empty = disabled. | `external_skills` |
| `clawhub_download_dir` | Staging dir for `clawhub install` (raw OpenClaw output). | `downloads` |
| `clawhub_token` | Optional; used by Core/Portal for `clawhub_ensure_logged_in` so search/install work without browser. | — |
| `skills_extra_dirs` | Additional skill dirs (list). | `[]` |

Paths relative to project root are resolved via `get_skills_dir(..., root)` in `base/skills.py` using the same `root` everywhere (Core: `Util().root_path()`).

---

## 4. Correctness Checks (Done)

- **Root for sync-vector-store**  
  Sync endpoint must use the same root as the rest of Core (e.g. `homeclaw_root`). Using `Path(__file__).resolve().parent...` can differ when Core is run from another cwd or with `homeclaw_root` set. **Refinement:** Use `Path(Util().root_path())` in the sync-vector-store handler.

- **Portal ClawHub auth**  
  Portal’s skills search (and install) should use `clawhub_ensure_logged_in(token)` when `clawhub_token` is set in core config, so Portal behaves like Core API. **Refinement:** In Portal `skills_search` and `skills_install`, load token from config and call `clawhub_ensure_logged_in(token)` before calling `clawhub_search` / `clawhub_install_and_convert`.

- **Locating installed skill after download**  
  Some ClawHub layouts use an extra scope dir, e.g. `downloads/skills/<scope>/<skill-id>`. We only iterated direct children of `download_path/skills` and `download_path`, so we could miss nested skills. **Refinement:** In `find_openclaw_installed_skill_dir`, when searching inside `extra_search_dirs`, also look one level deeper (for each direct child that is a directory, look for `sid` among its subdirs).

---

## 5. Flow Summary (After Refinements)

1. **Search**  
   Companion → Core `/api/skills/search` or Portal `/api/portal/skills/search`: ensure logged in (token if set), then `clawhub search` (JSON or text parsing). Same for both.

2. **Install (API / Portal / CLI)**  
   - Ensure logged in (token if set for API and Portal).  
   - Create `clawhub_download_dir` if missing.  
   - Run `clawhub install <spec>` with `cwd=homeclaw_root/clawhub_download_dir`.  
   - Locate installed folder: `find_openclaw_installed_skill_dir(sid, extra_search_dirs=[download_path/skills, download_path])`, with one-level recursion in those dirs.  
   - Convert: `convert_skill(src, external_skills_dir/sid)`.  
   - Return install + convert result; new skill is in `external_skills/` and will be loaded on next request (or after vector sync if enabled).

3. **Load**  
   `get_all_skills_dirs()` → `load_skills_from_dirs()` / vector search. Order: `skills_dir` → `external_skills_dir` → `skills_extra_dirs`. First matching folder name wins.

4. **Remove**  
   Only from `external_skills_dir`; `remove_skill_folder` checks path is under `ext_base`.

---

## 6. Model “Suggest to search” Hint

When skills are enabled, the system prompt includes a short hint so the model can suggest adding more skills when none fit:

- **Companion app** (Settings → Skills), **Portal** (Skills), or **scripts/convert_openclaw_skill.py** to convert an OpenClaw skill folder.  
- New skills go to `external_skills` and are loaded on the next session.

See `core/llm_loop.py` (skills block and empty-skills hint).

---

## 7. Files Touched in This Review

| Area | File | Change |
|------|------|--------|
| Sync root | `core/routes/misc_api.py` | Use `Util().root_path()` for sync-vector-store. |
| Portal auth | `portal/app.py` | `clawhub_ensure_logged_in(token)` before search and install. |
| Locate skill | `base/clawhub_integration.py` | One-level recursion in `find_openclaw_installed_skill_dir` for extra_search_dirs. |

No change to the converter script or to the install/convert contract; only consistency and robustness improvements.
