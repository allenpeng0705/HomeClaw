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
| **core.yml**    | Yes      | **Package the full repo `config/core.yml`** — all comments and all fields. See [Packaged config (core.yml)](#packaged-config-coreyml) below. |
| user.yml        | Yes      | Default `user.yml` template; on first run copy to Application Support. |
| Companion app   | Yes      | Existing Flutter macOS (or Windows) build. |
| **Node.js**     | Yes      | Embedded so **system_plugins/homeclaw-browser** (WebChat, Control UI, Playwright) works without user installing Node. Launcher sets PATH to bundled `node/bin`; Core starts the plugin with `node server.js`. |
| **homeclaw-browser** | Yes | **system_plugins/homeclaw-browser** is packaged; `npm install` runs at build time so `node_modules` is in the bundle. Playwright browser binaries are not bundled by default (optional first-run install). |
| Model files     | **No**   | User copies GGUF etc. into e.g. `~/HomeClaw/models`; guide in UI or doc. |
| Plugins/channels| Optional | Ship default set; heavy optional deps can be “install on demand” later. |

---

## Packaged config (core.yml)

**Package the current `config/core.yml` from the repo as-is** — with every comment and every field. Do not strip comments or omit optional keys.

- **Source file:** `config/core.yml` (repository root).
- **What to ship:** This entire file. Users (or advanced users) may need to re-configure any number of things (LLM, memory, plugins, auth, ports, etc.); having the full commented reference in one place avoids guesswork and keeps behavior consistent with development.
- **First-run:** Copy this packaged `core.yml` into the app's config directory (e.g. Application Support). Then overwrite only the minimal keys required for the bundle (e.g. `model_path`, `workspace_dir`) so paths point at the user's HomeClaw folder; leave all other keys and comments unchanged.
- **Reference copy:** Optionally keep an untouched copy in the bundle (e.g. `Resources/core/config/core.yml.reference`) so users can diff or restore the original. The active config used at runtime is the one in Application Support (or equivalent).

---

## First-run experience (models and config)

1. **First launch:** Create `~/HomeClaw/` (or App Support) and subdirs: `models`, `config`, `workspace` (or use Application Support for config/DB).
2. **Config:** Copy the packaged full `core.yml` (see above) into that config dir; then set only the minimal path keys (e.g. `model_path: ~/HomeClaw/models`, `workspace_dir`) so the rest of the file (comments and all fields) stays intact.
3. **Models:** Show a short guide: “To use local LLMs, put your model files (e.g. `.gguf`) in: **~/HomeClaw/models**.” Optional: “Open folder” button, “I’ve added models” to continue. Cloud-only users can skip.
4. **Core start:** Launcher (or Companion) starts Core with that config; Companion connects to `http://127.0.0.1:9000`.

---

## Packaging script

A **shell script** builds either a **single launcher app** (macOS) or a folder-only package:

```bash
./scripts/package_homeclaw.sh [--no-companion] [--no-launcher] [--no-node] [--output DIR] [--no-archive]
```

**Default on macOS:** Produces a **single launcher app** that matches the design above:

1. **Embedded Python** — Downloads [python-build-standalone](https://github.com/astral-sh/python-build-standalone) (no user Python install).
2. **Dependencies** — `pip install -r requirements.txt` into that Python in the bundle.
3. **Core + full config** — `main.py`, Core code, and **full `config/core.yml`** (all comments and fields) and `user.yml` inside the app.
4. **Companion app** — Flutter macOS build, inside the bundle.
5. **HomeClaw.app** — Double-click starts Core (embedded Python) then opens Companion. Models are not included; users put GGUF etc. in `~/HomeClaw/models` (see `PACKAGE_README.txt`).

**Options:**

- **--no-launcher:** Only produce the folder (Core + config + Companion). No embedded Python, no .app launcher; user runs `pip install -r requirements.txt` and `python -m main start` themselves.
- **--no-node:** Do not bundle Node.js or run `npm install` for homeclaw-browser. The plugin will need Node on PATH at run time (and you must run `npm install` in system_plugins/homeclaw-browser yourself if building a folder).
- **--no-companion:** Skip Flutter build (launcher or folder will not include Companion).
- **--output DIR:** Use `DIR` instead of `dist/HomeClaw-package-YYYYMMDD`.
- **--no-archive:** Do not create the `.tar.gz` tarball.

**Excluded from the package:** `__pycache__`, `database`, `logs`, `models`, `*.gguf`, `.git`, `venv`, `node_modules`, `site`, `docs`, `tests`. See `PACKAGE_README.txt` in the package for models path and usage.

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
