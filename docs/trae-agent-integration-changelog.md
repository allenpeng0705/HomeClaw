# Trae Agent integration – change summary

This doc summarizes all code/config changes for replacing Trae IDE (trae-cn) with **Trae Agent** (trae-cli) and adding optional install support.

---

## 1. Config and metadata

| File | Change |
|------|--------|
| **base/base.py** | Replaced `cursor_bridge_trae_cli_path` with `cursor_bridge_trae_agent_path` and `cursor_bridge_trae_agent_config`. Updated allowlist and `from_yaml` to use the new keys. |
| **core/core.py** | When starting the Cursor Bridge, sets `TRAE_AGENT_PATH` and `TRAE_AGENT_CONFIG` from the new config keys (and no longer sets `TRAE_CLI_PATH`). Fallback for path: `shutil.which("trae-cli")`. |
| **config/skills_and_plugins.yml** | Comments and examples updated: `cursor_bridge_trae_agent_path`, `cursor_bridge_trae_agent_config`; Trae Bridge section describes Trae Agent (trae-cli) and Windows paths. |
| **config/friend_presets.yml** | Trae preset comment and system_prompt updated for Trae Agent (run_agent returns output; open_project sets cwd only). |

---

## 2. Bridge (Cursor Bridge server)

| File | Change |
|------|--------|
| **external_plugins/cursor_bridge/server.py** | **Executable:** `_trae_executable()` → `_trae_agent_executable()` (uses `TRAE_AGENT_PATH`, else `trae-cli`). Added `_trae_agent_config_file()` for `--config-file`. **open_project:** `_open_in_trae()` no longer launches an IDE; only sets active cwd and returns a short message. **run_agent:** `_run_trae_task()` now runs `trae-cli run "<task>" --working-dir <cwd> --console-type simple` and optionally `--config-file`; captures stdout/stderr and returns it. Windows: added .cmd/.ps1 handling for the trae-cli subprocess (same pattern as Cursor/Claude). Interactive: trae backend uses `_trae_agent_executable()` for PTY. State and routing already supported `trae`; no structural change. |

---

## 3. Plugin and API

| File | Change |
|------|--------|
| **plugins/TraeBridge/plugin.yaml** | Descriptions updated for Trae Agent: open_project = set project folder (no IDE); run_agent = run trae-cli and return output; references to trae_config.yaml and repo README. |
| **core/routes/misc_api.py** | Already accepted `backend=trae` and `bridge_plugin=trae-bridge` for status and interactive session; no code change needed. |
| **core/llm_loop.py** | `_trae_bridge_capability_and_params()` and preset `trae` routing to `trae-bridge`; already present. |

---

## 4. Client (Companion app)

| File | Change |
|------|--------|
| **clients/HomeClawApp/lib/screens/chat_screen.dart** | Treats friend `trae` as dev bridge; backend `trae`, plugin `trae-bridge`. |
| **clients/HomeClawApp/lib/core_service.dart** | `getCursorBridgeActiveCwd` and interactive APIs accept `backend=trae` / `trae-bridge`. |

---

## 5. Install scripts

| File | Change |
|------|--------|
| **install.sh** | Optional step when `HOMECLAW_INSTALL_TRAE_AGENT=1`: clone trae-agent to `tools/trae-agent`, install uv if missing (`pip install uv`), run `uv sync --all-extras`, copy `trae_config.yaml.example` → `trae_config.yaml` if missing. After install/update, applies **patches/trae-agent-anthropic-client-minimax.patch** so Minimax (and other Anthropic-compatible backends) get standard tool format. End message: how to install Trae Agent and set `cursor_bridge_trae_agent_path` / `cursor_bridge_trae_agent_config` in config. |
| **install.ps1** | Same optional step; Windows paths; applies the same patch after install/update; same end message. |
| **install.bat** | New flag `trae`: sets `HOMECLAW_INSTALL_TRAE_AGENT=1`; echo and comments updated for Trae Agent and “install.bat trae”. |

---

## 6. Docs

| File | Change |
|------|--------|
| **docs/cursor-claude-code-bridge.md** | Section 4 “Trae Bridge” rewritten for Trae Agent: setup (clone, uv sync, trae_config.yaml), env vars (`TRAE_AGENT_PATH`, `TRAE_AGENT_CONFIG`), Windows note (path to trae-cli.exe, bash tool / Git Bash/WSL). |
| **docs/trae-agent-integration-investigation.md** | Existing investigation doc; no change. |
| **docs/trae-agent-integration-changelog.md** | This file. |

---

## 7. requirements.txt and `uv`

**No change to requirements.txt.**

- **uv** is used only by the **install scripts** when the user runs with `HOMECLAW_INSTALL_TRAE_AGENT=1` (or `install.bat trae`). The scripts run `uv` to clone trae-agent and execute `uv sync` in that repo; they already install uv on the fly (`pip install uv`) when it’s missing.
- HomeClaw Core and the Cursor Bridge **do not import or run `uv`**. They only run the **trae-cli** binary (from `TRAE_AGENT_PATH` or PATH) as a subprocess.
- Adding `uv` to requirements.txt would install it for every user even if they never use Trae Agent. It is an optional install-time tool for the Trae Agent flow, not a runtime dependency of the application.

So: **do not add `uv` to requirements.txt.**
