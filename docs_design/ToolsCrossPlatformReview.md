# Tools cross-platform review (Windows, Linux, Mac)

This document reviews built-in tools in `tools/builtin.py` for cross-platform behavior. All file/folder tools and exec/skill tools are designed to work on **Windows**, **Linux**, and **Mac**.

## Summary

| Area | Status | Notes |
|------|--------|--------|
| File / folder path handling | ✅ Cross-platform | pathlib.Path, normalized slashes |
| folder_list, file_find, file_read, file_write, file_edit | ✅ | Use _resolve_file_path + Path; returned paths use `/` |
| document_read, get_file_view_link, save_result_page | ✅ | Same path pipeline |
| exec | ✅ | Platform-specific allowlist (dir/type vs ls/cat) |
| run_skill (.py, .sh, .bat) | ✅ | .sh on Windows uses bash or WSL when available |
| apply_patch, markdown_to_pdf | ✅ | Path-based; no shell-specific logic |

---

## File and folder tools

### Path resolution (`_resolve_file_path`)

- **pathlib.Path** is used for all path construction and joining. `Path` uses the correct separator per OS when resolving.
- **Input normalization:** User paths are normalized with `path_arg.replace("\\", "/")` for comparison and prefix checks, so both `documents/file.pdf` and `documents\file.pdf` are accepted.
- **Windows absolute paths:** Rejected when `homeclaw_root` is set (sandbox mode): `path_arg[1] == ":"` detects drive letters so we do not allow `C:\...` inside the sandbox.
- **Leading slash:** A leading `/` without a drive letter (e.g. `/documents/file`) is treated as sandbox-relative and the leading slash is stripped so resolution works on all platforms.
- **Share path:** `share` and `share/...` are handled with normalized lowercase and `lstrip("/\\")` so both `/` and `\` work.

### Relative path normalization (`_normalize_relative_path`)

- Strips leading `./`, `.\\`, `/`, and `\` so that the same logical path is produced on Windows and Unix.
- Used before joining with the absolute base from `sandbox_paths.json`. Joining is done with `Path(base) / rest`, which is correct on all platforms.

### Sandbox validation (`_path_under`)

- Uses `full.resolve().relative_to(base.resolve())`; no string or separator logic. Works on Windows, Linux, and Mac.

### Returned paths to the LLM/client

- In **folder_list** and **file_find**, relative paths are built with `str(p.relative_to(base_for_rel)).replace("\\", "/")`, so the API and LLM always see **forward slashes** (e.g. `documents/file.pdf`), which work in `document_read(path=...)` on every platform.
- **get_file_view_link** uses `path_for_link = str(full.relative_to(effective_base)).replace("\\", "/")` for the same reason.

### File I/O

- **read_text / write_text:** All file content I/O uses `Path.read_text(encoding="utf-8", errors="replace")` and `Path.write_text(..., encoding="utf-8")`. No `open()` with hardcoded paths; when `open()` is used, the argument is a `Path` (Python 3 accepts it on all platforms).
- **iterdir(), rglob():** Used on `Path` objects; behavior is cross-platform.

### Bare filename detection (`_is_bare_filename`)

- Rejects paths containing `/` or `\`, and rejects Windows-style absolutes with `len(p) > 1 and p[1] == ":"`.

---

## Exec tool

- **Allowlist:** `_default_exec_allowlist()` returns different commands per OS:
  - **Windows:** `date`, `whoami`, `echo`, `cd`, `dir`, `type`, `where`, `powershell`
  - **Mac/Linux:** `date`, `whoami`, `echo`, `pwd`, `ls`, `cat`, `which`
- **Execution:** Uses `asyncio.create_subprocess_exec(executable, *args, ...)` (no `shell=True`), so behavior is the same across platforms for the same allowlist entry.
- Config can override via `tools.exec_allowlist` in core config.

---

## run_skill

- **.py scripts:** Run with the same Python interpreter; cross-platform.
- **.sh / .bash on Windows:** If `platform.system() == "Windows"`, the code looks for `bash` (e.g. Git Bash) or `wsl` and runs the script with that. If neither is found, it returns a clear error asking the user to install Git for Windows or WSL, or to use a `.py`/`.bat` script.
- **.sh / .bash on Mac/Linux:** Run with `str(script_path)` and `*args_list` via `create_subprocess_exec`; the system uses the default shell where needed.
- **.bat / .cmd:** Not explicitly special-cased; they would run via `create_subprocess_exec` (on Windows the OS would run them; on non-Windows they would fail unless a compatibility layer exists). Prefer `.py` or `.sh` + bash/WSL for cross-platform skills.

---

## Other tools

- **apply_patch:** Uses `_resolve_file_path` and Path for reading/writing patched files; cross-platform.
- **markdown_to_pdf:** Uses configurable paths (e.g. VMPrint, pandoc) and `Path`; temp files and output paths are Path-based. No OS-specific branching.
- **process_list, process_poll, process_kill:** Rely on `psutil` (or equivalent); `psutil` is cross-platform.
- **Browser/Playwright:** Depends on Playwright installation and browser binaries; not specific to path handling in builtin tools.
- **platform_info:** Uses `platform.system()`, `platform.machine()`, `platform.platform()` for reporting only.

---

## Recommendations

1. **Keep using pathlib.Path** for all new file/folder logic; avoid `os.path` and raw string concatenation for paths.
2. **Keep normalizing returned paths** with `.replace("\\", "/")` when returning paths to the LLM or API so clients see a single, portable format.
3. **Exec:** Document in user-facing docs that the default allowlist is platform-specific (e.g. `dir`/`type` on Windows, `ls`/`cat` on Unix) and that custom allowlists should list commands valid for the OS where Core runs.
4. **run_skill:** Document that `.sh` skills on Windows require Git Bash or WSL unless the user configures another runner.

---

## Reference

- Path resolution and sandbox: `_resolve_file_path`, `_path_under`, `_normalize_relative_path`, `_resolve_relative_to_absolute_via_sandbox_json` in `tools/builtin.py`.
- File/folder tools: `_folder_list_executor`, `_file_find_executor`, `_file_read_executor`, `_document_read_executor`, `_file_write_executor`, `_file_edit_executor`, `_get_file_view_link_executor`, `apply_patch` (and related).
- Exec and run_skill: `_default_exec_allowlist`, `_exec_executor`, run_skill branch for `.sh` on Windows (around line 2827 in builtin.py).
- Design: `docs_design/FileSandboxDesign.md` for sandbox layout and semantics.
