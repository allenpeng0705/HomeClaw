# Distribution Strategy: Lightweight Core + Companion-Only Distribution

## Summary

- **HomeClawApp (Companion)** — Distribute via **GitHub releases**, **direct download**, **App Store**, **Google Play**. Small, easy to ship.
- **HomeClaw system (Core)** — Too large to ship as a single download. Distribute as **code + requirements** only: user installs **Python** and (optionally) **Ollama** or **llama.cpp**; we provide a **small installer or pip** and a **single settings UI** (Companion “Manage Core” or a web UI).
- **LLM backend** — Prefer **Ollama** (user installs once; no model bundling). Optional **llama.cpp** with models in a **fixed folder** (e.g. `~/HomeClaw/models`).
- **Settings** — One UI: **Companion’s “Manage Core”** (already exists) for core.yml/user.yml; optionally a **web settings page** served by Core for headless/CLI-only setups.

---

## 1. What We Distribute Where

| Artifact | How to distribute | Size / Notes |
|----------|-------------------|--------------|
| **HomeClawApp** (Companion) | GitHub releases, App Store, Google Play, direct download | DMG / ZIP / store packages; small, user-friendly |
| **HomeClaw Core** | No single “fat” package. Distribute **code + config only** via: pip, minimal zip, or installer script | Small (no embedded Python/Node/models) |
| **llama.cpp** | Not bundled. User installs **Ollama** (recommended) or **llama.cpp** themselves | N/A |
| **Models** | Not distributed. User puts GGUF (etc.) in a **specified folder** (e.g. `~/HomeClaw/models`) | User-managed |

---

## 2. LLM: Ollama vs llama.cpp

### Option A: Ollama (recommended for distribution)

- User installs Ollama once: `brew install ollama` (Mac), or [ollama.com](https://ollama.com) (Mac/Windows/Linux).
- User runs `ollama pull <model>`; models live in Ollama’s own directory.
- HomeClaw Core talks to Ollama’s API (OpenAI-compatible); no model_path in Core for Ollama models.
- **Pros:** No bundling, no “where to put models” in our docs; one install for user.
- **Cons:** User must install and run Ollama.

**Config:** In `config/llm.yml`, define a provider with `path: ollama/<model>` (or your existing Ollama entry). No `model_path` needed for Ollama.

### Option B: llama.cpp

- User installs **llama.cpp** (or llama-server) themselves — we do **not** ship it.
- User puts **models** (e.g. `.gguf`) in a **single specified folder**, e.g.:
  - **Mac/Linux:** `~/HomeClaw/models`
  - **Windows:** `%USERPROFILE%\HomeClaw\models`
- In Core config, `model_path` (or equivalent) points at that folder; llama-server is started (by user or by Core, if we support it) with `-m` from that path.
- **Pros:** Full control, no Ollama dependency.
- **Cons:** User must install llama.cpp and manage models in the specified folder.

**Unified convention:** We document one **canonical models directory** for all platforms, e.g.:

- `~/HomeClaw/models` (Mac/Linux)
- `%USERPROFILE%\HomeClaw\models` (Windows)

Core’s default `model_path` (or the value we set in installers) should resolve to this.

---

## 3. One UI for Settings / Configuration

Requirements:

- Choose LLM backend (Ollama vs llama.cpp).
- If llama.cpp: set **model path** (default: `~/HomeClaw/models` or Windows equivalent).
- Edit other Core settings (host, port, auth, memory, plugins, etc.).

**Option 1: Companion “Manage Core” (existing)**  
- HomeClawApp already has **Manage Core** (core.yml & user.yml) via Core’s `/api/config` API.
- Add or highlight in that UI:
  - **LLM backend:** Ollama vs llama.cpp (or “local server”).
  - **Model path** (for llama.cpp): single field, default `~/HomeClaw/models` / `%USERPROFILE%\HomeClaw\models`.
- This is the **single primary UI** for most users (they use Companion anyway).

**Option 2: Web settings (optional)**  
- Core serves a **/settings** (or /admin) page: same fields (backend, model path, core.yml whitelist).
- For headless/CLI-only or “Core on a server, no Companion” setups.
- Can be a simple HTML/JS form that calls `/api/config/core` (and users if needed).

**Recommendation:** Use **Companion “Manage Core”** as the one main UI; add a **web settings** page in Core only if you need it for server/headless use.

---

## 4. How to Distribute Core on Mac, Linux, Windows

Core distribution = **no big bundle**. User gets:

- Python 3.11+ (and optionally Node for homeclaw-browser).
- Ollama **or** llama.cpp (if using local LLM).
- HomeClaw **code + config templates** and a **clear models directory**.

### 4.1 Mac

| Method | What user does | What we provide |
|--------|----------------|-----------------|
| **Homebrew formula** | `brew tap … && brew install homeclaw` | Formula installs Core code + venv + `homeclaw` CLI; docs say “install Ollama: brew install ollama” and “models in ~/HomeClaw/models if using llama.cpp”. |
| **Install script** | Run `curl \| sh` or download script, then run | Script: clone or download code zip, create venv, `pip install -r requirements.txt`, create `~/HomeClaw` and `~/HomeClaw/models`, copy default config. |
| **pip** (future) | `pip install homeclaw-core` | Package contains only code; config and models dir are created on first run or via `homeclaw init`. |

Default **model_path** in config: `~/HomeClaw/models`.

### 4.2 Linux

| Method | What user does | What we provide |
|--------|----------------|-----------------|
| **Install script** | Same as Mac: download script, run | Same script (or Linux-specific) that sets up venv, code, `~/HomeClaw` and `~/HomeClaw/models`. |
| **pip** (future) | `pip install homeclaw-core` | Same as Mac. |
| **Docker** (optional) | `docker run …` or docker-compose | Image has Python + Core code; no embedded Node/Ollama/models. User mounts config and `~/HomeClaw/models`; can run Ollama on host or in another container. |

Default **model_path**: `~/HomeClaw/models`.

### 4.3 Windows

| Method | What user does | What we provide |
|--------|----------------|-----------------|
| **Install script (PowerShell)** | Run `.ps1` (e.g. from GitHub) | Script: download code zip, create venv, pip install, create `%USERPROFILE%\HomeClaw` and `%USERPROFILE%\HomeClaw\models`, copy default config. |
| **pip** (future) | `pip install homeclaw-core` | Same as Mac/Linux; first run creates `%USERPROFILE%\HomeClaw` and `%USERPROFILE%\HomeClaw\models`. |
| **Optional: small NSIS/installer** | Run installer | Only installs code + launcher; prompts for Python path if not found; creates HomeClaw folder and models dir. |

Default **model_path**: `%USERPROFILE%\HomeClaw\models` (or document one canonical path).

---

## 5. Installer / First-Run Behavior (recommended)

For **script or pip** installs, provide a single entrypoint and clear layout:

1. **Create canonical directories**
   - Mac/Linux: `~/HomeClaw`, `~/HomeClaw/models`, `~/HomeClaw/config` (or use repo `config/` with defaults).
   - Windows: `%USERPROFILE%\HomeClaw`, `…\models`, `…\config`.

2. **Config**
   - Copy default `core.yml` / `llm.yml` into that config dir (or repo `config/`) with:
     - `model_path` = `~/HomeClaw/models` (or Windows equivalent).
     - LLM provider = Ollama by default (with one example model), or “local” (llama.cpp) with a note to put models in `model_path`.

3. **LLM**
   - **Ollama:** Document “Install Ollama; run `ollama serve` and `ollama pull <model>`; select that model in Manage Core.”
   - **llama.cpp:** Document “Install llama-server; put .gguf in ~/HomeClaw/models; set model_path in Manage Core (or leave default).”

4. **Settings**
   - Point user to **Companion → Manage Core** (or web /settings) to choose Ollama vs llama.cpp and set model path.

---

## 6. What to Build Next (concrete)

1. **Document**
   - One **“Install HomeClaw Core”** page: Mac (Homebrew + script), Linux (script + optional Docker), Windows (PowerShell + optional pip).
   - One **“Models and LLM”** section: Ollama (install, pull model, select in UI) vs llama.cpp (install, put GGUF in `~/HomeClaw/models`, set model_path).

2. **Companion “Manage Core”**
   - Add or expose in UI:
     - **LLM backend:** Ollama | llama.cpp (or “local server”).
     - **Model path** (for llama.cpp): one field, default `~/HomeClaw/models` / `%USERPROFILE%\HomeClaw\models`.

3. **Default config**
   - In default `core.yml` (or installer-provided): `model_path` = platform-specific `~/HomeClaw/models` or `%USERPROFILE%\HomeClaw\models`.

4. **Lightweight install**
   - **Mac/Linux:** One script (e.g. `install.sh`) that: clone or download code, venv, pip install, create `~/HomeClaw` and `~/HomeClaw/models`, write default config.
   - **Windows:** One PowerShell script that does the same under `%USERPROFILE%\HomeClaw`.

5. **Optional**
   - **Web settings** page in Core (e.g. `/settings`) if you want config without Companion.
   - **Docker** image (Core only, no Python/Node in image if you use host mounts for venv, or image with venv only; models and config mounted).

---

## 7. Summary Table

| Topic | Decision |
|-------|----------|
| **Companion** | Distribute via GitHub, download, App Store, Google Play only. |
| **Core** | Do not distribute a big package. Distribute code + config; user installs Python, optionally Node, and Ollama or llama.cpp. |
| **LLM** | Prefer **Ollama**; support **llama.cpp** with models in a **single specified folder**. |
| **Models** | User puts them in **~/HomeClaw/models** (Mac/Linux) or **%USERPROFILE%\HomeClaw\models** (Windows). |
| **Settings UI** | **One UI:** Companion “Manage Core” (add LLM backend + model path); optional web /settings in Core. |
| **Mac** | Homebrew formula or install script; docs: Ollama + models path. |
| **Linux** | Install script (and optional Docker); same docs. |
| **Windows** | PowerShell install script (and optional pip); same docs. |

This keeps Core distribution small and avoids shipping binaries/models while giving a single, clear place for models and one UI for configuration.
