"""
Cursor Bridge: HTTP server for HomeClaw to run commands, open projects, or chat with Cursor's agent on the dev machine.

Main features:
- open_project: open a folder/project in Cursor IDE (so you can then chat with the agent there).
- run_agent: run Cursor CLI agent with a task in non-interactive mode and return the output (run and see results).
- run_command: run a shell command (e.g. npm test) and return output.

Run: python -m external_plugins.cursor_bridge.server
     Optional: CURSOR_BRIDGE_PORT=3104 (default 3104), CURSOR_BRIDGE_CWD=/path/to/project
"""
import logging
import json
import os
import subprocess
import threading
from typing import Any, Dict, Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

app = FastAPI(title="Cursor Bridge", description="HomeClaw → open project, run agent, run commands on dev machine")

# Optional: default cwd for run_command / run_agent when not provided.
DEFAULT_CWD = os.environ.get("CURSOR_BRIDGE_CWD") or os.getcwd()
BRIDGE_PORT = int(os.environ.get("CURSOR_BRIDGE_PORT", "3104"))
# Optional: persist the last active project cwd across bridge restarts.
STATE_FILE = (os.environ.get("CURSOR_BRIDGE_STATE_FILE") or "").strip()
if not STATE_FILE:
    # Default to a per-user location on Windows/mac/Linux.
    STATE_FILE = os.path.join(os.path.expanduser("~"), ".homeclaw", "cursor_bridge_state.json")

_ACTIVE_CWD_LOCK = threading.Lock()
_ACTIVE_CWD: Optional[str] = None  # set by open_project/open_file; used as default cwd for run_agent/run_command

def _load_state() -> None:
    """Load persisted active cwd (best-effort)."""
    try:
        if not STATE_FILE or not os.path.isfile(STATE_FILE):
            return
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
        cwd = (obj.get("active_cwd") or "").strip() if isinstance(obj, dict) else ""
        if cwd and os.path.isdir(cwd):
            with _ACTIVE_CWD_LOCK:
                global _ACTIVE_CWD
                _ACTIVE_CWD = cwd
            logger.info("Loaded cursor bridge state: active_cwd=%s", cwd)
    except Exception as e:
        logger.warning("Failed to load cursor bridge state: %s", e)


def _save_state() -> None:
    """Persist active cwd (best-effort)."""
    try:
        if not STATE_FILE:
            return
        base = os.path.dirname(STATE_FILE)
        if base and not os.path.isdir(base):
            os.makedirs(base, exist_ok=True)
        cwd = _get_active_cwd() or ""
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"active_cwd": cwd}, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.warning("Failed to save cursor bridge state: %s", e)


# Load persisted state at import time (so it works when started by Core).
_load_state()


def _set_active_cwd(path: str) -> None:
    """Set active cwd if path is an existing directory."""
    p = (path or "").strip()
    if not p:
        return
    try:
        if os.path.isdir(p):
            with _ACTIVE_CWD_LOCK:
                global _ACTIVE_CWD
                _ACTIVE_CWD = p
            _save_state()
    except Exception:
        return


def _get_active_cwd() -> Optional[str]:
    try:
        with _ACTIVE_CWD_LOCK:
            return _ACTIVE_CWD
    except Exception:
        return None


def _resolve_path(p: str) -> str:
    """Resolve a path relative to DEFAULT_CWD when needed."""
    s = (p or "").strip()
    if not s:
        return s
    abs_p = os.path.abspath(s) if not os.path.isabs(s) else s
    if os.path.exists(abs_p):
        return abs_p
    return os.path.normpath(os.path.join(DEFAULT_CWD, s))


def _status_payload() -> Dict[str, Any]:
    """Return bridge status for UI/debugging."""
    return {
        "default_cwd": DEFAULT_CWD,
        "active_cwd": _get_active_cwd(),
        "state_file": STATE_FILE,
    }


def _run_command(command: str, cwd: Optional[str] = None, timeout_sec: int = 60) -> tuple:
    """Run a shell command; return (success, output_or_error)."""
    if not (command or str(command).strip()):
        return False, "Error: command is empty."
    cmd = str(command).strip()
    work_dir = (cwd or "").strip() or DEFAULT_CWD
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=work_dir if os.path.isdir(work_dir) else DEFAULT_CWD,
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout_sec, 300)),
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, err or out or f"Command exited with code {proc.returncode}"
        if out:
            return True, out
        if err:
            # Some CLIs write to stderr even on success; surface it.
            return True, err
        return True, "(no output)"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout_sec}s."
    except Exception as e:
        return False, f"Error: {e!s}"


def _cursor_cli_executable() -> str:
    """Return the path to the Cursor CLI used to open projects/files. Use CURSOR_CLI_PATH if set, else 'cursor'."""
    path = (os.environ.get("CURSOR_CLI_PATH") or "").strip()
    if path and os.path.isfile(path):
        return path
    if path:
        return path
    return "cursor"


def _open_in_cursor(path: str) -> tuple:
    """Open a path (folder or file) in Cursor IDE. Returns (success, message). Uses CURSOR_CLI_PATH or 'cursor' CLI."""
    if not (path or str(path).strip()):
        return False, "Error: path is empty."
    p = _resolve_path(path)
    if not os.path.exists(p):
        return False, f"Path does not exist: {path}"
    try:
        import platform
        cursor_cmd = _cursor_cli_executable()
        is_windows = platform.system() == "Windows"
        cwd = os.path.dirname(p) if os.path.isfile(p) else p
        if is_windows and cursor_cmd.lower().endswith(".cmd"):
            subprocess.Popen(
                ["cmd", "/c", cursor_cmd, p],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif is_windows and cursor_cmd.lower().endswith(".ps1"):
            subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", cursor_cmd, p],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif platform.system() == "Darwin":
            subprocess.Popen(
                ["open", "-a", "Cursor", p],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                [cursor_cmd, p],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True, f"Opened in Cursor: {p}"
    except FileNotFoundError:
        return False, (
            "Cursor CLI 'cursor' not found (open project in Cursor IDE failed). "
            "In Cursor: Command Palette → 'Shell Command: Install cursor'. "
            "If the bridge is started by Core, set cursor_bridge_cursor_cli_path in config to the full path of cursor.cmd, or set CURSOR_CLI_PATH in the environment where Core runs."
        )
    except Exception as e:
        return False, f"Could not open in Cursor: {e!s}. Install Cursor shell command (Command Palette: 'Install cursor') and ensure 'cursor' is in PATH or set CURSOR_CLI_PATH."


def _agent_executable() -> str:
    """Return the path to the Cursor CLI agent. Use CURSOR_AGENT_PATH if set (so bridge works when started by Core without agent in PATH), else 'agent'."""
    path = (os.environ.get("CURSOR_AGENT_PATH") or "").strip()
    if path and os.path.isfile(path):
        return path
    if path:
        # Path configured but file missing; use it anyway so subprocess gives a clear error
        return path
    return "agent"


def _run_agent_task(task: str, cwd: Optional[str] = None, timeout_sec: int = 120) -> tuple:
    """Run Cursor CLI agent in non-interactive mode: agent -p \"task\". Returns (success, output_or_error). On Windows, .cmd/.ps1 are run via cmd or powershell."""
    if not (task or str(task).strip()):
        return False, "Error: task is empty."
    work_dir = (cwd or "").strip()
    if not work_dir:
        work_dir = _get_active_cwd() or DEFAULT_CWD
    if not os.path.isdir(work_dir):
        work_dir = DEFAULT_CWD
    agent_cmd = _agent_executable()
    task_str = task.strip()
    # On Windows, agent may be agent.cmd or agent.ps1; subprocess needs cmd/powershell to run them.
    # On macOS/Linux, run the executable directly (agent should be a binary or a script with shebang + exec bit).
    try:
        import platform
        is_windows = platform.system() == "Windows"
    except Exception:
        is_windows = False
    # --trust so agent runs non-interactively (avoids "Workspace Trust Required" prompt and exit 1)
    # --output-format json so the bridge can reliably extract the result text.
    if is_windows and agent_cmd.lower().endswith(".cmd"):
        run_argv = ["cmd", "/c", agent_cmd, "--trust", "-p", "--output-format", "json", task_str]
    elif is_windows and agent_cmd.lower().endswith(".ps1"):
        run_argv = ["powershell", "-ExecutionPolicy", "Bypass", "-File", agent_cmd, "--trust", "-p", "--output-format", "json", task_str]
    else:
        run_argv = [agent_cmd, "--trust", "-p", "--output-format", "json", task_str]
    _log_argv = run_argv.copy()
    if len(_log_argv) > 2 and len(task_str) > 80:
        _log_argv[-1] = task_str[:80] + "..."
    logger.info("agent run: argv=%s cwd=%s", _log_argv, work_dir)
    try:
        def _run(argv: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                argv,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=max(30, min(timeout_sec, 1800)),
            )

        proc = _run(run_argv)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        # If this agent version doesn't support --output-format, retry without it (keep --trust/-p).
        if proc.returncode != 0 and err and (
            "output-format" in err.lower() or "unknown option" in err.lower() or "unrecognized" in err.lower()
        ):
            fallback_argv = [a for a in run_argv if a not in ("--output-format", "json")]
            logger.info("agent retry without --output-format (flag unsupported)")
            proc = _run(fallback_argv)
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            logger.warning(
                "agent exited non-zero: returncode=%s stdout_len=%s stderr_len=%s stdout_preview=%s stderr_preview=%s",
                proc.returncode,
                len(out),
                len(err),
                (out[:500] if out else "(empty)"),
                (err[:500] if err else "(empty)"),
            )
            parts = [f"Agent exited with code {proc.returncode}."]
            if err:
                parts.append(f"stderr: {err}")
            if out:
                parts.append(f"stdout: {out}")
            msg = "\n".join(parts) if (err or out) else parts[0]
            if "Authentication required" in msg or "agent login" in msg.lower() or "CURSOR_API_KEY" in msg:
                msg += " To fix: run 'agent login' in a terminal, or set CURSOR_API_KEY in the environment where the bridge runs. If Core auto-starts the bridge, set cursor_bridge_cursor_api_key in config/skills_and_plugins.yml (or CURSOR_API_KEY before starting Core)."
            elif not (err or out):
                msg += (
                    " No output from agent. Run in a terminal to see the real error: agent -p \"<your task>\". "
                    "If you see 'Authentication required', run 'agent login' or set CURSOR_API_KEY (or cursor_bridge_cursor_api_key in config)."
                )
            return False, msg
        # Parse JSON output when available (Cursor CLI: --output-format json).
        if out:
            try:
                last_line = out.strip().splitlines()[-1]
                obj = json.loads(last_line)
                if isinstance(obj, dict):
                    result_text = (obj.get("result") or obj.get("text") or "").strip()
                    if result_text:
                        return True, result_text
            except Exception:
                pass
            return True, out
        if err:
            # Some CLIs write to stderr even on success; surface it.
            return True, err
        return True, (
            "(no output)\n"
            "The Cursor CLI agent exited successfully but produced no output. "
            "Try running the same task inside Cursor IDE chat, or run it in a terminal to see interactive output: "
            "agent --trust -p \"<your task>\"."
        )
    except FileNotFoundError:
        return False, (
            "Cursor CLI 'agent' not found. "
            "If you use cursor_bridge_auto_start: set cursor_bridge_agent_path in config to the full path (PowerShell: (Get-Command agent).Source). "
            "Otherwise start the bridge from a terminal where 'agent --version' works, or install: Windows: irm 'https://cursor.com/install?win32=true' | iex — macOS/Linux: curl https://cursor.com/install -fsS | bash. See https://cursor.com/docs/cli"
        )
    except subprocess.TimeoutExpired:
        return False, f"Agent timed out after {timeout_sec}s. For long tasks, use Cursor in the IDE or Cloud Agent."
    except Exception as e:
        return False, f"Error: {e!s}"


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def _run_impl(body: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch by capability_id; return PluginResult. Never raises."""
    request_id = body.get("request_id", "")
    plugin_id = body.get("plugin_id", "cursor-bridge")
    user_input = (body.get("user_input") or "").strip()
    cap_id = (body.get("capability_id") or "ask_cursor").strip().lower().replace(" ", "_").replace("-", "_")
    params = body.get("capability_parameters") or {}
    if not isinstance(params, dict):
        params = {}

    success = True
    text = ""
    error = None

    if cap_id in ("get_status", "status"):
        # Return bridge status (active project cwd, default cwd, etc.)
        success = True
        text = json.dumps(_status_payload(), ensure_ascii=False)

    elif cap_id == "run_command":
        command = (params.get("command") or "").strip()
        cwd = (params.get("cwd") or "").strip() or None
        if not command:
            success = False
            error = "run_command requires 'command' in capability_parameters."
        else:
            if not cwd:
                cwd = _get_active_cwd() or None
            success, text = _run_command(command, cwd=cwd)

    elif cap_id == "open_file":
        path = (params.get("path") or "").strip()
        if not path:
            success = False
            error = "open_file requires 'path' in capability_parameters."
        else:
            try:
                abs_path = _resolve_path(path)
                success, text = _open_in_cursor(abs_path)
                if success:
                    _set_active_cwd(os.path.dirname(abs_path))
            except Exception as e:
                success = False
                text = f"Could not open {path}: {e!s}. You can run 'cursor {path}' in terminal if Cursor CLI is installed."

    elif cap_id == "open_project":
        # Open a folder or project in Cursor IDE so the user can chat with the agent there.
        path = (params.get("path") or params.get("folder") or "").strip()
        if not path:
            success = False
            error = "open_project requires 'path' or 'folder' in capability_parameters."
        else:
            resolved = _resolve_path(path)
            success, text = _open_in_cursor(resolved)
            if success and os.path.isdir(resolved):
                _set_active_cwd(resolved)

    elif cap_id == "run_agent":
        # Run Cursor CLI agent with a task (non-interactive); return output so user sees results in the channel.
        task = (params.get("task") or params.get("prompt") or user_input or "").strip()
        cwd = (params.get("cwd") or "").strip() or None
        timeout = 600  # default 10 min; allow up to 1800 (30 min) to match plugin HTTP timeout
        try:
            t = int(params.get("timeout_sec", timeout))
            if 30 <= t <= 1800:
                timeout = t
        except (TypeError, ValueError):
            pass
        if not task:
            success = False
            error = "run_agent requires 'task' or 'prompt' in capability_parameters, or user_input."
        else:
            if not cwd:
                cwd = _get_active_cwd() or None
            success, text = _run_agent_task(task, cwd=cwd, timeout_sec=timeout)

    else:
        # ask_cursor or unknown: treat user_input or params.task as a natural-language task; run as a single command if it looks like one.
        task = (params.get("task") or user_input or "").strip()
        if not task:
            success = False
            error = "No task or user_input provided."
        else:
            # Heuristic: if task is a single line and looks like a command (no leading "please" etc.), run it.
            first = task.split("\n")[0].strip().lower()
            if first.startswith(("npm ", "pnpm ", "yarn ", "pip ", "python ", "node ", "npx ", "cargo ", "go ")):
                success, text = _run_command(task.split("\n")[0].strip())
            else:
                # Otherwise return instructions so the user can run it in Cursor manually, or we could run `cursor --help` etc.
                text = f"Task: {task[:500]}. Run this in Cursor (terminal or command palette). To run shell commands from HomeClaw, use capability run_command with a concrete command (e.g. npm test)."

    # When success is False, ensure error is set so PluginResult is consistent (Core shows result.error or result.text).
    if not success and text and error is None:
        error = text
    return {
        "request_id": request_id,
        "plugin_id": plugin_id,
        "success": success,
        "text": text,
        "error": error,
        "metadata": {},
    }


@app.post("/run")
async def run(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept PluginRequest (JSON) from HomeClaw. Dispatch by capability_id; return PluginResult (JSON).
    Never raises: any unexpected error returns success=False with error message.
    """
    try:
        if not isinstance(body, dict):
            body = {}
        return _run_impl(body)
    except Exception as e:
        _b = body if isinstance(body, dict) else {}
        return {
            "request_id": _b.get("request_id", ""),
            "plugin_id": _b.get("plugin_id", "cursor-bridge"),
            "success": False,
            "text": "",
            "error": f"Cursor Bridge error: {e!s}",
            "metadata": {},
        }


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=BRIDGE_PORT)
