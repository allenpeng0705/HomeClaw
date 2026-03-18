"""
Cursor Bridge: HTTP server for HomeClaw to run commands, open projects, or chat with Cursor's agent on the dev machine.

Main features:
- open_project: open a folder/project in Cursor IDE (so you can then chat with the agent there).
- run_agent: run Cursor CLI agent with a task in non-interactive mode and return the output (run and see results).
- run_command: run a shell command (e.g. npm test) and return output.

Run: python -m external_plugins.cursor_bridge.server
     Optional: CURSOR_BRIDGE_PORT=3104 (default 3104), CURSOR_BRIDGE_CWD=/path/to/project
"""
import os
import subprocess
from typing import Any, Dict, Optional

from fastapi import FastAPI

app = FastAPI(title="Cursor Bridge", description="HomeClaw → open project, run agent, run commands on dev machine")

# Optional: default cwd for run_command / run_agent when not provided.
DEFAULT_CWD = os.environ.get("CURSOR_BRIDGE_CWD") or os.getcwd()
BRIDGE_PORT = int(os.environ.get("CURSOR_BRIDGE_PORT", "3104"))


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
        return True, out or "(no output)"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout_sec}s."
    except Exception as e:
        return False, f"Error: {e!s}"


def _open_in_cursor(path: str) -> tuple:
    """Open a path (folder or file) in Cursor IDE. Returns (success, message). Uses 'cursor' CLI if in PATH."""
    if not (path or str(path).strip()):
        return False, "Error: path is empty."
    p = os.path.abspath(path) if not os.path.isabs(path) else path
    if not os.path.exists(p):
        p = os.path.normpath(os.path.join(DEFAULT_CWD, path))
    if not os.path.exists(p):
        return False, f"Path does not exist: {path}"
    try:
        import platform
        if platform.system() == "Windows":
            # Cursor installs 'cursor' / code.cmd; try cursor first, else startfile with Cursor if associated.
            try:
                subprocess.Popen(
                    ["cursor", p],
                    cwd=os.path.dirname(p) if os.path.isfile(p) else p,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                )
            except FileNotFoundError:
                os.startfile(p)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(
                ["open", "-a", "Cursor", p],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["cursor", p],
                cwd=os.path.dirname(p) if os.path.isfile(p) else p,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True, f"Opened in Cursor: {p}"
    except Exception as e:
        return False, f"Could not open in Cursor: {e!s}. Install Cursor shell command (Command Palette: 'Install cursor') and ensure 'cursor' is in PATH."


def _run_agent_task(task: str, cwd: Optional[str] = None, timeout_sec: int = 120) -> tuple:
    """Run Cursor CLI agent in non-interactive mode: agent -p \"task\". Returns (success, output_or_error)."""
    if not (task or str(task).strip()):
        return False, "Error: task is empty."
    work_dir = (cwd or "").strip() or DEFAULT_CWD
    if not os.path.isdir(work_dir):
        work_dir = DEFAULT_CWD
    try:
        proc = subprocess.run(
            ["agent", "-p", task.strip()],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=max(30, min(timeout_sec, 600)),
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, err or out or f"Agent exited with code {proc.returncode}"
        return True, out or "(no output)"
    except FileNotFoundError:
        return False, "Cursor CLI 'agent' not found. Install it: curl https://cursor.com/install -fsS | bash (macOS/Linux) or see https://cursor.com/docs/cli"
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

    if cap_id == "run_command":
        command = (params.get("command") or "").strip()
        cwd = (params.get("cwd") or "").strip() or None
        if not command:
            success = False
            error = "run_command requires 'command' in capability_parameters."
        else:
            success, text = _run_command(command, cwd=cwd)

    elif cap_id == "open_file":
        path = (params.get("path") or "").strip()
        if not path:
            success = False
            error = "open_file requires 'path' in capability_parameters."
        else:
            abs_path = os.path.abspath(path) if not os.path.isabs(path) else path
            if not os.path.exists(abs_path):
                abs_path = os.path.normpath(os.path.join(DEFAULT_CWD, path))
            try:
                import platform
                if platform.system() == "Windows":
                    os.startfile(abs_path)  # type: ignore[attr-defined]
                elif platform.system() == "Darwin":
                    subprocess.run(["open", abs_path], check=False, capture_output=True, timeout=5)
                else:
                    subprocess.run(["xdg-open", abs_path], check=False, capture_output=True, timeout=5)
                text = f"Opened: {abs_path}"
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
            success, text = _open_in_cursor(path)

    elif cap_id == "run_agent":
        # Run Cursor CLI agent with a task (non-interactive); return output so user sees results in the channel.
        task = (params.get("task") or params.get("prompt") or user_input or "").strip()
        cwd = (params.get("cwd") or "").strip() or None
        timeout = 120
        try:
            t = int(params.get("timeout_sec", timeout))
            if 30 <= t <= 600:
                timeout = t
        except (TypeError, ValueError):
            pass
        if not task:
            success = False
            error = "run_agent requires 'task' or 'prompt' in capability_parameters, or user_input."
        else:
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
    uvicorn.run(app, host="0.0.0.0", port=BRIDGE_PORT)
