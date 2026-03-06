# Review: System plugins, tools, and stability hardening

This document summarizes the review applied to keep logic correct, stable, robust, and crash-free after the system-plugin/tools and revert changes.

## Scope of review

- **System plugins**: homeclaw-browser in `system_plugins/homeclaw-browser`; discovery and startup in `core/plugins_startup.py`.
- **Config**: `base/base.py` (CoreMetadata, `_normalize_system_plugins_env`), `config/skills_and_plugins.yml`.
- **Tools**: `markdown_to_pdf` in `tools/builtin.py` (VMPrint/pandoc/weasyprint).
- **Install scripts**: `install.sh`, `install.ps1` (VMPrint step, vmprint-main rename).

## Hardening applied

### 1. `core/plugins_startup.py`

- **Discovery**
  - `os.listdir(base)` wrapped in `try/except OSError` so permission or I/O errors return `[]` instead of crashing.
- **Allowlist**
  - `system_plugins` from metadata is validated as a list; non-list is treated as `[]`.
  - Filter uses `c.get("id", "") in allowlist` to avoid KeyError on malformed entries.
- **Host and port**
  - `host` defaulted and stripped; missing/invalid yields `"127.0.0.1"`.
  - `port` parsed with try/except; invalid or out-of-range (1–65535) falls back to `9000`.
- **Plugin env**
  - `plugin_env_config` must be a dict; otherwise use `{}`.
  - Per-plugin env: only iterate when `plugin_env` is a dict; env vars set with `str(k)` and `str(v)` (or `""` for None) so subprocess env is always string-valued.
- **Start/register loops**
  - Use `item.get("cwd")`, `item.get("start_argv")`, `item.get("id", "?")` so missing keys never raise.
  - Skip start when `not cwd or not start_argv`; skip register when `not cwd`.
  - `core._system_plugin_processes`: only append when `getattr(..., None)` is actually a list.
- **Numeric config**
  - `system_plugins_ready_timeout` and `system_plugins_start_delay` parsed with try/except; on TypeError/ValueError use safe defaults (90.0 and 2.0).

### 2. `base/base.py` — `_normalize_system_plugins_env`

- Documented as “Never raises.”
- Inner loop over `vars_dict.items()` wrapped in try/except; any failure for a single var sets that var to `""` and continues.
- Ensures plugin env values are always strings (True→"true", False→"false", None→"", else `str(v)`).

### 3. `tools/builtin.py` — `markdown_to_pdf` executor

- `_get_tools_config()` may be None: use `_get_tools_config() or {}`.
- `markdown_to_pdf` config may be missing or not a dict: `isinstance(tools_cfg, dict)` and `isinstance(md2pdf_cfg, dict)` checks; treat non-dict as `{}` so `md2pdf_cfg.get("vmprint_dir")` never runs on a non-dict.

### 4. Logic and config (unchanged, verified)

- **System plugins** live in `system_plugins/`; discovery only from that directory (no `system_plugin_dirs`).
- **Config**: `system_plugins_auto_start`, `system_plugins` (allowlist), `system_plugins_env`, `system_plugins_start_delay` in `config/skills_and_plugins.yml`; all loaded and validated in `base/base.py`.
- **VMPrint**: install scripts (4b) clone to `tools/vmprint`, rename `vmprint-main` → `vmprint` if present; `markdown_to_pdf` uses `tools.markdown_to_pdf.vmprint_dir` with fallback to pandoc/weasyprint.
- **homeclaw-browser**: remains a system plugin under `system_plugins/homeclaw-browser`; no install-script step (first-time setup is manual per README).

## Result

- Discovery and startup tolerate missing or invalid config, bad metadata types, and unlistable or missing directories.
- Subprocess env is always string-valued; process list append is guarded.
- `markdown_to_pdf` never assumes config is a dict.
- Normalization of `system_plugins_env` never raises; malformed values become `""`.

All changes preserve existing behavior for valid config and add defensive handling so invalid or unexpected values do not crash Core.
