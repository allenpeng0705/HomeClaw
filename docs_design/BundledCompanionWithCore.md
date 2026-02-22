# Bundling HomeClaw Core with the Companion App

**Goal:** Package the full system so that running the Companion app can start HomeClaw (Core) automatically. Model files are **not** packaged; users are guided to place them in a specified folder.

## Feasibility: Yes

It is possible to ship a single distributable (e.g. macOS app or installer) that:

1. **Includes:** Python runtime + Core code + config templates + Companion app (or a launcher).
2. **Excludes:** Model files (GGUF, etc.) — too large; user puts them in a documented folder.
3. **On first run:** Create default config (e.g. in Application Support), point `model_path` / `workspace_dir` to that location, and show a short setup guide (e.g. “Put your model files in **~/HomeClaw/models**” or “Choose a folder for models”).
4. **When user runs the app:** Start Core in the background (if not already running), then open the Companion UI (or the Flutter app). Companion connects to `http://127.0.0.1:9000` by default.

---

## Approaches

### A. Launcher app (recommended for “one double‑click”)

- **What you ship:** One app (e.g. “HomeClaw.app”) that:
  1. On launch, starts Core in the background (bundled Python + `python -m main start` or a small wrapper), then opens the Companion window (Flutter build or embedded).
  2. Uses a **bundled Python** (e.g. [python.org embeddable](https://www.python.org/downloads/windows/) on Windows, or a relocatable Python framework on macOS) so the user does not need to install Python.
- **Where things live:**
  - **macOS:** e.g. `HomeClaw.app/Contents/Resources/python/` (Python + venv or bundled deps), `HomeClaw.app/Contents/Resources/core/` (Core code), `~/Library/Application Support/HomeClaw/` (config, workspace, DB). Models: `~/HomeClaw/models` or a path the user chooses in first-run.
  - **Windows:** Similar: app dir + `%APPDATA%\HomeClaw` for config; models in e.g. `%USERPROFILE%\HomeClaw\models`.
- **Models:** Not in the package. First-run screen or doc: “Place your GGUF (and other) model files in **this folder**,” with a button to open that folder and optionally a “I’ve added models” / “Skip for now.”

### B. Companion app “Start Core” + optional bundled Core

- **What you ship:** The existing Companion app, plus an **optional** installer or separate download that installs Core + Python into a fixed location (e.g. `/Applications/HomeClaw Core/` or `~/HomeClaw/`).
- **Flow:** User runs Companion. If Core is not reachable, Companion shows “Start HomeClaw” (or “Install & start” on first use). If Core is bundled: Companion runs the bundled `main.py` (via bundled Python). If not bundled: prompt to install Core or enter Core URL.
- **Models:** Same as A: a documented folder (e.g. `~/HomeClaw/models`), no models in the package.

---

## What to package (no models)

| Component        | Package? | Notes |
|-----------------|----------|--------|
| Python runtime  | Yes      | Embedded/relocatable so user doesn’t install Python. |
| Core code       | Yes      | `main.py`, `core/`, `base/`, `llm/`, `config/` (templates), `system_plugins/`, etc. |
| `requirements.txt` deps | Yes | Install into a venv or bundle wheels next to the embedded Python. |
| Config templates| Yes      | Default `core.yml` / `user.yml`; on first run copy to Application Support and set `model_path`, `workspace_dir`. |
| Companion app   | Yes      | Existing Flutter macOS (or Windows) build. |
| Model files     | **No**   | User copies GGUF etc. into e.g. `~/HomeClaw/models`; guide in UI or doc. |
| Plugins/channels| Optional | Ship default set; heavy optional deps can be “install on demand” later. |

---

## First-run experience (models and config)

1. **First launch:** Create `~/HomeClaw/` (or App Support) and subdirs: `models`, `config`, `workspace` (or use Application Support for config/DB).
2. **Config:** Copy default `core.yml` into that config dir; set e.g. `model_path: ~/HomeClaw/models` and `workspace_dir` to the chosen app-support path.
3. **Models:** Show a short guide: “To use local LLMs, put your model files (e.g. `.gguf`) in: **~/HomeClaw/models**.” Optional: “Open folder” button, “I’ve added models” to continue. Cloud-only users can skip.
4. **Core start:** Launcher (or Companion) starts Core with that config; Companion connects to `http://127.0.0.1:9000`.

---

## Implementation sketch (macOS launcher)

1. **Bundle layout (example):**
   - `HomeClaw.app/Contents/MacOS/launcher` — small binary or script that starts Core then opens Companion.
   - `HomeClaw.app/Contents/Resources/python/` — embedded Python + venv with Core deps.
   - `HomeClaw.app/Contents/Resources/core/` — Core repo (main.py, core/, base/, llm/, config templates, etc.).
   - `HomeClaw.app/Contents/Resources/companion/` — Flutter-built `homeclaw_companion.app` or the Companion binary.

2. **Launcher logic:**
   - If Core not already running (e.g. GET http://127.0.0.1:9000/ready): run `Resources/python/bin/python -m main start` (or equivalent) in background with `PYTHONPATH=Resources/core` and config from `~/Library/Application Support/HomeClaw/config/`.
   - Open Companion (e.g. `open Resources/companion/homeclaw_companion.app` or run the binary).

3. **Config and model path:** Launcher or first-run script writes default config under Application Support and sets `model_path` to `~/HomeClaw/models`; first-run UI or doc tells user to put model files there.

---

## Summary

- **Yes,** you can package the system with the Companion app and have “run Companion → HomeClaw runs automatically.”
- **Do not** package model files; use a fixed, documented folder (e.g. `~/HomeClaw/models`) and guide the user to put files there.
- **Recommended approach:** A small launcher that starts Core (bundled Python + Core) then opens the Companion app, with a one-time setup that creates config and points to the models folder.
