"""
Cursor Bridge: HTTP server for HomeClaw to run commands, open projects, or chat with Cursor's agent on the dev machine.

Main features:
- open_project: open a folder/project in Cursor IDE (so you can then chat with the agent there).
- run_agent: run Cursor CLI agent with a task in non-interactive mode and return the output (run and see results).
- run_agent_interactive: start Cursor/Claude agent in a PTY so the user can interact via Companion/WebChat.
- run_command: run a shell command (e.g. npm test) and return output.
- run_command_interactive: start a shell command in a PTY for interactive use.

Run: python -m external_plugins.cursor_bridge.server
     Optional: CURSOR_BRIDGE_PORT=3104 (default 3104), CURSOR_BRIDGE_CWD=/path/to/project
"""
import asyncio
import logging
import json
import os
import platform
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Cursor Bridge", description="HomeClaw → open project, run agent, run commands on dev machine")

IS_WINDOWS = platform.system() == "Windows"
IS_DARWIN = platform.system() == "Darwin"

# Optional shared-secret for remote/LAN exposure. If set, requests must include X-HomeClaw-Bridge-Key.
BRIDGE_API_KEY = (os.environ.get("CURSOR_BRIDGE_API_KEY") or "").strip()

# Optional: default cwd for run_command / run_agent when not provided.
DEFAULT_CWD = os.environ.get("CURSOR_BRIDGE_CWD") or os.getcwd()
BRIDGE_PORT = int(os.environ.get("CURSOR_BRIDGE_PORT", "3104"))
# Optional: persist the last active project cwd across bridge restarts.
STATE_FILE = (os.environ.get("CURSOR_BRIDGE_STATE_FILE") or "").strip()
if not STATE_FILE:
    # Default to a per-user location on Windows/mac/Linux.
    STATE_FILE = os.path.join(os.path.expanduser("~"), ".homeclaw", "cursor_bridge_state.json")

_ACTIVE_CWD_LOCK = threading.Lock()
# Track active project per backend so Cursor and ClaudeCode don't step on each other.
# Keys: "cursor" | "claude"
_ACTIVE_CWD_BY_BACKEND: Dict[str, Optional[str]] = {"cursor": None, "claude": None}

def _load_state() -> None:
    """Load persisted active cwd (best-effort)."""
    try:
        if not STATE_FILE or not os.path.isfile(STATE_FILE):
            return
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return
        # Backward compat: old state used {"active_cwd": "..."} (Cursor only).
        legacy = (obj.get("active_cwd") or "").strip()
        cursor_cwd = (obj.get("cursor_active_cwd") or legacy or "").strip()
        claude_cwd = (obj.get("claude_active_cwd") or "").strip()
        with _ACTIVE_CWD_LOCK:
            if cursor_cwd and os.path.isdir(cursor_cwd):
                _ACTIVE_CWD_BY_BACKEND["cursor"] = cursor_cwd
            if claude_cwd and os.path.isdir(claude_cwd):
                _ACTIVE_CWD_BY_BACKEND["claude"] = claude_cwd
        if _ACTIVE_CWD_BY_BACKEND.get("cursor") or _ACTIVE_CWD_BY_BACKEND.get("claude"):
            logger.info(
                "Loaded cursor bridge state: cursor_active_cwd=%s claude_active_cwd=%s",
                _ACTIVE_CWD_BY_BACKEND.get("cursor"),
                _ACTIVE_CWD_BY_BACKEND.get("claude"),
            )
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
        cursor_cwd = _get_active_cwd("cursor") or ""
        claude_cwd = _get_active_cwd("claude") or ""
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"cursor_active_cwd": cursor_cwd, "claude_active_cwd": claude_cwd},
                f,
                ensure_ascii=False,
            )
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.warning("Failed to save cursor bridge state: %s", e)


# Load persisted state at import time (so it works when started by Core).
_load_state()


def _set_active_cwd(path: str, backend: str = "cursor") -> None:
    """Set active cwd for a backend if path is an existing directory."""
    p = (path or "").strip()
    if not p:
        return
    b = (backend or "cursor").strip().lower()
    if b not in ("cursor", "claude"):
        b = "cursor"
    try:
        if os.path.isdir(p):
            with _ACTIVE_CWD_LOCK:
                _ACTIVE_CWD_BY_BACKEND[b] = p
            _save_state()
    except Exception:
        return


def _get_active_cwd(backend: str = "cursor") -> Optional[str]:
    try:
        b = (backend or "cursor").strip().lower()
        if b not in ("cursor", "claude"):
            b = "cursor"
        with _ACTIVE_CWD_LOCK:
            return _ACTIVE_CWD_BY_BACKEND.get(b)
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


# --- Bridge interactive sessions (PTY/ConPTY on bridge machine) ---


@dataclass
class _BridgeChunk:
    seq: int
    text: str
    timestamp: float


@dataclass
class _BridgeSession:
    session_id: str
    command: str
    cwd: Optional[str]
    created_at: float
    status: str = "running"
    exit_code: Optional[int] = None
    _buffer: List[_BridgeChunk] = field(default_factory=list)
    _next_seq: int = 1
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append_output(self, text: str) -> None:
        now = time.time()
        with self._lock:
            if not text:
                return
            self._buffer.append(_BridgeChunk(seq=self._next_seq, text=text, timestamp=now))
            self._next_seq += 1
            # Cap buffer size
            if len(self._buffer) > 500:
                self._buffer = self._buffer[-300:]

    def read_from(self, from_seq: int = 1) -> Tuple[List[_BridgeChunk], int]:
        with self._lock:
            chunks = [c for c in self._buffer if c.seq >= from_seq]
            last_seq = self._next_seq - 1
        return chunks, last_seq


class _BridgeInteractiveManager:
    """Manages PTY/ConPTY sessions on the bridge machine for run_agent_interactive / run_command_interactive."""

    def __init__(self, max_sessions: int = 5):
        self._sessions: Dict[str, _BridgeSession] = {}
        self._unix_master_fds: Dict[str, int] = {}
        self._win_procs: Dict[str, Any] = {}
        self._max_sessions = max(1, max_sessions)
        self._lock = threading.Lock()

    def _make_session_id(self) -> str:
        return f"bridge_{uuid.uuid4().hex[:12]}"

    def start_session(self, command: str, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
        """Start a PTY session; returns (session_id, initial_output). Blocks until first output or process start."""
        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError("Too many bridge interactive sessions")
            session_id = self._make_session_id()
            sess = _BridgeSession(
                session_id=session_id,
                command=command,
                cwd=(cwd or "").strip() or None,
                created_at=time.time(),
            )
            self._sessions[session_id] = sess
        cwd = (cwd or "").strip() or DEFAULT_CWD
        if not os.path.isdir(cwd):
            cwd = DEFAULT_CWD
        env = env or {}
        env_merged = {**os.environ, **env}
        if IS_WINDOWS:
            self._start_win_conpty(sess, cwd, env_merged)
        else:
            self._start_unix_pty(sess, cwd, env_merged)
        chunks, _ = sess.read_from(1)
        initial = "".join(c.text for c in chunks)
        return session_id, initial

    def _start_unix_pty(self, sess: _BridgeSession, cwd: str, env: Dict[str, str]) -> None:
        import pty as pty_mod

        def _run():
            try:
                argv = ["/bin/sh", "-c", sess.command]
                pid, master_fd = pty_mod.fork()
                if pid == 0:
                    try:
                        os.chdir(cwd)
                    except Exception:
                        pass
                    os.execvpe(argv[0], argv, env)
                else:
                    try:
                        self._unix_master_fds[sess.session_id] = master_fd
                    except Exception:
                        pass
                    try:
                        while True:
                            try:
                                data = os.read(master_fd, 4096)
                            except OSError:
                                break
                            if not data:
                                break
                            sess.append_output(data.decode("utf-8", errors="replace"))
                    finally:
                        try:
                            os.close(master_fd)
                        except OSError:
                            pass
                        try:
                            self._unix_master_fds.pop(sess.session_id, None)
                        except Exception:
                            pass
                        sess.status = "exited"
            except Exception as e:
                sess.append_output(f"Error starting PTY: {e!s}\n")
                sess.status = "error"
                sess.exit_code = 1

        threading.Thread(target=_run, daemon=True).start()

    def _start_win_conpty(self, sess: _BridgeSession, cwd: str, env: Dict[str, str]) -> None:
        try:
            from pywinpty import PtyProcess  # type: ignore
        except ImportError:
            sess.append_output(
                "Interactive sessions on Windows require the optional 'pywinpty' dependency. "
                "Install with: pip install pywinpty\n"
            )
            sess.status = "error"
            sess.exit_code = 1
            return

        def _run():
            try:
                proc = PtyProcess.spawn(sess.command, cwd=cwd, env=env)
                self._win_procs[sess.session_id] = proc
                try:
                    while True:
                        try:
                            data = proc.read(4096)
                        except Exception:
                            break
                        if not data:
                            break
                        text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
                        sess.append_output(text)
                finally:
                    try:
                        proc.close()
                    except Exception:
                        pass
                    self._win_procs.pop(sess.session_id, None)
                    sess.status = "exited"
            except Exception as e:
                sess.append_output(f"Failed to start ConPTY: {e!s}\n")
                sess.status = "error"
                sess.exit_code = 1

        threading.Thread(target=_run, daemon=True).start()

    def write(self, session_id: str, data: str) -> None:
        if not data:
            return
        if IS_WINDOWS:
            proc = self._win_procs.get(session_id)
            if proc is not None:
                try:
                    proc.write(data)
                except Exception:
                    pass
        else:
            fd = self._unix_master_fds.get(session_id)
            if fd is not None:
                try:
                    os.write(fd, data.encode("utf-8"))
                except OSError:
                    pass

    def read(self, session_id: str, from_seq: int = 1) -> Tuple[List[_BridgeChunk], str, Optional[int], str]:
        with self._lock:
            sess = self._sessions.get(session_id)
        if not sess:
            raise KeyError("Unknown session_id")
        chunks, _ = sess.read_from(from_seq)
        return chunks, sess.status, sess.exit_code, sess.command

    def stop(self, session_id: str) -> None:
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess:
                sess.status = "killed"
        if IS_WINDOWS:
            proc = self._win_procs.pop(session_id, None)
            if proc is not None:
                try:
                    proc.close()
                except Exception:
                    pass
        else:
            fd = self._unix_master_fds.pop(session_id, None)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass


_BRIDGE_INTERACTIVE = _BridgeInteractiveManager()


def _agent_interactive_command(backend: str) -> Tuple[str, Optional[str]]:
    """Return (command_string, cwd) to run the agent interactively (no -p, no task)."""
    if (backend or "").strip().lower() == "claude":
        exe = _claude_executable()
        cwd = _get_active_cwd("claude") or DEFAULT_CWD
        if IS_WINDOWS and exe.lower().endswith(".cmd"):
            cmd = f'cmd /c "{exe}"'
        elif IS_WINDOWS and exe.lower().endswith(".ps1"):
            cmd = f'powershell -ExecutionPolicy Bypass -File "{exe}"'
        else:
            cmd = exe
        return cmd, cwd
    # Cursor agent
    exe = _agent_executable()
    cwd = _get_active_cwd("cursor") or DEFAULT_CWD
    if IS_WINDOWS and exe.lower().endswith(".cmd"):
        cmd = f'cmd /c "{exe}" --trust'
    elif IS_WINDOWS and exe.lower().endswith(".ps1"):
        cmd = f'powershell -ExecutionPolicy Bypass -File "{exe}" --trust'
    else:
        cmd = f"{exe} --trust"
    return cmd, cwd


def _status_payload() -> Dict[str, Any]:
    """Return bridge status for UI/debugging."""
    return {
        "default_cwd": DEFAULT_CWD,
        "cursor_active_cwd": _get_active_cwd("cursor"),
        "claude_active_cwd": _get_active_cwd("claude"),
        "state_file": STATE_FILE,
        "auth_enabled": bool(BRIDGE_API_KEY),
    }


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    # Only protect the plugin endpoint; allow /health unauthenticated for readiness checks.
    if BRIDGE_API_KEY and request.url.path not in ("/health",):
        got = (request.headers.get("X-HomeClaw-Bridge-Key") or "").strip()
        if not got or got != BRIDGE_API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


async def _run_command(command: str, cwd: Optional[str] = None, timeout_sec: int = 60) -> tuple:
    """Run a shell command; return (success, output_or_error)."""
    if not (command or str(command).strip()):
        return False, "Error: command is empty."
    cmd = str(command).strip()
    work_dir = (cwd or "").strip() or DEFAULT_CWD
    try:
        eff_cwd = work_dir if os.path.isdir(work_dir) else DEFAULT_CWD
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=eff_cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=max(1, min(int(timeout_sec or 60), 300)),
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return False, f"Command timed out after {timeout_sec}s."
        out = (stdout_b.decode("utf-8", errors="replace") if stdout_b else "").strip()
        err = (stderr_b.decode("utf-8", errors="replace") if stderr_b else "").strip()
        rc = proc.returncode if proc.returncode is not None else 1
        if rc != 0:
            return False, err or out or f"Command exited with code {rc}"
        if out:
            return True, out
        if err:
            # Some CLIs write to stderr even on success; surface it.
            return True, err
        return True, "(no output)"
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
        cursor_cmd = _cursor_cli_executable()
        cwd = os.path.dirname(p) if os.path.isfile(p) else p
        if IS_WINDOWS and cursor_cmd.lower().endswith(".cmd"):
            subprocess.Popen(
                ["cmd", "/c", cursor_cmd, p],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif IS_WINDOWS and cursor_cmd.lower().endswith(".ps1"):
            subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", cursor_cmd, p],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif IS_DARWIN:
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


def _claude_executable() -> str:
    """Return the path to Claude Code CLI. Use CLAUDE_PATH if set, else 'claude' (resolved via PATH)."""
    path = (os.environ.get("CLAUDE_PATH") or "").strip()
    if path and os.path.isfile(path):
        return path
    if path:
        return path
    return shutil.which("claude") or "claude"


def _claude_env_from_config() -> Dict[str, str]:
    """Read Claude config from ~/.claude/settings.json and return env vars to inject. Injects the full \"env\" object (all keys, values stringified) so ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, API_TIMEOUT_MS, ANTHROPIC_MODEL, etc. are passed to the CLI. Also supports top-level anthropic_api_key/api_url for backward compat."""
    out: Dict[str, str] = {}
    base = os.path.expanduser("~")
    if not base:
        return out

    def _str_value(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        return str(v)

    def _merge_from(data: Optional[Dict[str, Any]]) -> None:
        if not isinstance(data, dict):
            return
        # Top-level keys for backward compat (only if not already set from env block)
        for key in ("anthropic_api_key", "api_key", "ANTHROPIC_API_KEY"):
            v = data.get(key)
            if isinstance(v, str) and v.strip() and "ANTHROPIC_API_KEY" not in out:
                out["ANTHROPIC_API_KEY"] = v.strip()
                break
        for key in ("anthropic_api_url", "api_url", "ANTHROPIC_API_URL"):
            v = data.get(key)
            if isinstance(v, str) and v.strip() and "ANTHROPIC_API_URL" not in out:
                out["ANTHROPIC_API_URL"] = v.strip()
                break
        # Full env block: inject every key so ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, API_TIMEOUT_MS, ANTHROPIC_MODEL, etc. are all passed
        env_block = data.get("env")
        if isinstance(env_block, dict):
            for ek, ev in env_block.items():
                if not isinstance(ek, str) or not ek.strip():
                    continue
                out[ek.strip()] = _str_value(ev)

    try:
        settings_path = os.path.join(base, ".claude", "settings.json")
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                _merge_from(json.load(f))
        legacy_path = os.path.join(base, ".claude.json")
        if os.path.isfile(legacy_path):
            with open(legacy_path, "r", encoding="utf-8") as f:
                _merge_from(json.load(f))
    except Exception as e:
        logger.debug("Could not load Claude settings from ~/.claude/settings.json: %s", e)
    return out


def _claude_subprocess_env() -> Dict[str, str]:
    """Environment for Claude CLI subprocess: inherit current env, then fill from ~/.claude/settings.json if ANTHROPIC_API_KEY etc. are not set."""
    env = dict(os.environ)
    from_file = _claude_env_from_config()
    for key, value in from_file.items():
        if value and (not env.get(key) or not str(env.get(key)).strip()):
            env[key] = value
    return env


async def _run_claude_task(task: str, cwd: Optional[str] = None, timeout_sec: int = 120) -> tuple:
    """Run Claude Code CLI headlessly. Always uses --dangerously-skip-permissions for non-interactive runs."""
    if not (task or str(task).strip()):
        return False, "Error: task is empty."
    work_dir = (cwd or "").strip()
    if not work_dir:
        work_dir = _get_active_cwd("claude") or DEFAULT_CWD
    if not os.path.isdir(work_dir):
        work_dir = DEFAULT_CWD
    claude_cmd = _claude_executable()
    task_str = task.strip()
    # Headless + skip permissions + JSON output (fallback if unsupported).
    if IS_WINDOWS and claude_cmd.lower().endswith(".cmd"):
        run_argv = ["cmd", "/c", claude_cmd, "--dangerously-skip-permissions", "-p", "--output-format", "json", task_str]
    elif IS_WINDOWS and claude_cmd.lower().endswith(".ps1"):
        run_argv = ["powershell", "-ExecutionPolicy", "Bypass", "-File", claude_cmd, "--dangerously-skip-permissions", "-p", "--output-format", "json", task_str]
    else:
        run_argv = [claude_cmd, "--dangerously-skip-permissions", "-p", "--output-format", "json", task_str]
    _log_argv = run_argv.copy()
    if len(_log_argv) > 2 and len(task_str) > 80:
        _log_argv[-1] = task_str[:80] + "..."
    logger.info("claude run: argv=%s cwd=%s", _log_argv, work_dir)

    claude_env = _claude_subprocess_env()

    async def _run_exec(argv: list[str]) -> tuple[int, str, str]:
        p = await asyncio.create_subprocess_exec(
            *argv,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=claude_env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                p.communicate(),
                timeout=max(30, min(int(timeout_sec or 120), 1800)),
            )
        except asyncio.TimeoutError:
            try:
                p.kill()
            except Exception:
                pass
            raise
        out_s = (stdout_b.decode("utf-8", errors="replace") if stdout_b else "").strip()
        err_s = (stderr_b.decode("utf-8", errors="replace") if stderr_b else "").strip()
        rc = p.returncode if p.returncode is not None else 1
        return rc, out_s, err_s

    try:
        rc, out, err = await _run_exec(run_argv)
        if rc != 0 and err and (
            "output-format" in err.lower() or "unknown option" in err.lower() or "unrecognized" in err.lower()
        ):
            fallback_argv = [a for a in run_argv if a not in ("--output-format", "json")]
            logger.info("claude retry without --output-format (flag unsupported)")
            rc, out, err = await _run_exec(fallback_argv)
        if rc != 0:
            parts = [f"Claude exited with code {rc}."]
            if err:
                parts.append(f"stderr: {err}")
            if out:
                parts.append(f"stdout: {out}")
            msg = "\n".join(parts) if (err or out) else parts[0]
            if "anthropic_api_key" in msg.lower() or "api key" in msg.lower() or "login" in msg.lower():
                msg += " To fix: set ANTHROPIC_API_KEY in the environment where the bridge runs, or add anthropic_api_key to ~/.claude/settings.json (or C:\\Users\\<you>\\.claude\\settings.json on Windows), or run 'claude' once interactively to log in."
            return False, msg
        if out:
            try:
                last_line = out.strip().splitlines()[-1]
                obj = json.loads(last_line)
                if isinstance(obj, dict):
                    result_text = (obj.get("result") or obj.get("text") or obj.get("output") or "").strip()
                    if result_text:
                        return True, result_text
            except Exception:
                pass
            return True, out
        if err:
            return True, err
        return True, "(no output)"
    except FileNotFoundError:
        return False, (
            "Claude Code CLI 'claude' not found. Install it (see https://code.claude.com/docs/en/overview), "
            "or set CLAUDE_PATH to the full path of the claude executable/script."
        )
    except asyncio.TimeoutError:
        return False, f"Claude timed out after {timeout_sec}s."
    except Exception as e:
        return False, f"Error: {e!s}"

async def _run_agent_task(task: str, cwd: Optional[str] = None, timeout_sec: int = 120) -> tuple:
    """Run Cursor CLI agent in non-interactive mode: agent -p \"task\". Returns (success, output_or_error). On Windows, .cmd/.ps1 are run via cmd or powershell."""
    if not (task or str(task).strip()):
        return False, "Error: task is empty."
    work_dir = (cwd or "").strip()
    if not work_dir:
        work_dir = _get_active_cwd("cursor") or DEFAULT_CWD
    if not os.path.isdir(work_dir):
        work_dir = DEFAULT_CWD
    agent_cmd = _agent_executable()
    task_str = task.strip()
    # --trust so agent runs non-interactively (avoids "Workspace Trust Required" prompt and exit 1)
    # --output-format json so the bridge can reliably extract the result text.
    if IS_WINDOWS and agent_cmd.lower().endswith(".cmd"):
        run_argv = ["cmd", "/c", agent_cmd, "--trust", "-p", "--output-format", "json", task_str]
    elif IS_WINDOWS and agent_cmd.lower().endswith(".ps1"):
        run_argv = ["powershell", "-ExecutionPolicy", "Bypass", "-File", agent_cmd, "--trust", "-p", "--output-format", "json", task_str]
    else:
        run_argv = [agent_cmd, "--trust", "-p", "--output-format", "json", task_str]
    _log_argv = run_argv.copy()
    if len(_log_argv) > 2 and len(task_str) > 80:
        _log_argv[-1] = task_str[:80] + "..."
    logger.info("agent run: argv=%s cwd=%s", _log_argv, work_dir)
    async def _run_exec(argv: list[str]) -> tuple[int, str, str]:
        p = await asyncio.create_subprocess_exec(
            *argv,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                p.communicate(),
                timeout=max(30, min(int(timeout_sec or 120), 1800)),
            )
        except asyncio.TimeoutError:
            try:
                p.kill()
            except Exception:
                pass
            raise
        out_s = (stdout_b.decode("utf-8", errors="replace") if stdout_b else "").strip()
        err_s = (stderr_b.decode("utf-8", errors="replace") if stderr_b else "").strip()
        rc = p.returncode if p.returncode is not None else 1
        return rc, out_s, err_s

    try:
        rc, out, err = await _run_exec(run_argv)
        # If this agent version doesn't support --output-format, retry without it (keep --trust/-p).
        if rc != 0 and err and (
            "output-format" in err.lower() or "unknown option" in err.lower() or "unrecognized" in err.lower()
        ):
            fallback_argv = [a for a in run_argv if a not in ("--output-format", "json")]
            logger.info("agent retry without --output-format (flag unsupported)")
            rc, out, err = await _run_exec(fallback_argv)
        if rc != 0:
            logger.warning(
                "agent exited non-zero: returncode=%s stdout_len=%s stderr_len=%s stdout_preview=%s stderr_preview=%s",
                rc,
                len(out),
                len(err),
                (out[:500] if out else "(empty)"),
                (err[:500] if err else "(empty)"),
            )
            parts = [f"Agent exited with code {rc}."]
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
    except asyncio.TimeoutError:
        return False, f"Agent timed out after {timeout_sec}s. For long tasks, use Cursor in the IDE or Cloud Agent."
    except Exception as e:
        return False, f"Error: {e!s}"


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


async def _run_impl(body: Dict[str, Any]) -> Dict[str, Any]:
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
        backend = (params.get("backend") or "").strip().lower()
        payload = _status_payload()
        if backend in ("cursor", "claude"):
            payload["active_cwd"] = payload.get(f"{backend}_active_cwd")
        else:
            # Backward compat: active_cwd means cursor active cwd.
            payload["active_cwd"] = payload.get("cursor_active_cwd")
        text = json.dumps(payload, ensure_ascii=False)

    elif cap_id in ("set_cwd", "set_project", "set_project_cwd"):
        path = (params.get("path") or params.get("cwd") or "").strip()
        if not path:
            success = False
            error = "set_cwd requires 'path' in capability_parameters."
        else:
            resolved = _resolve_path(path)
            if not os.path.isdir(resolved):
                success = False
                error = f"Path is not a directory: {resolved}"
            else:
                _set_active_cwd(resolved, backend="claude")
                text = f"Active project set: {resolved}"

    elif cap_id == "run_command":
        command = (params.get("command") or "").strip()
        cwd = (params.get("cwd") or "").strip() or None
        if not command:
            success = False
            error = "run_command requires 'command' in capability_parameters."
        else:
            backend = (params.get("backend") or "").strip().lower()
            if backend not in ("cursor", "claude"):
                pid_lower = (plugin_id or "").strip().lower()
                backend = "claude" if "claude" in pid_lower else "cursor"
            if not cwd:
                cwd = _get_active_cwd(backend) or None
            success, text = await _run_command(command, cwd=cwd)

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
                    _set_active_cwd(os.path.dirname(abs_path), backend="cursor")
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
                _set_active_cwd(resolved, backend="cursor")

    elif cap_id == "run_agent":
        # Run Cursor CLI agent (cursor-bridge) or Claude Code CLI (claude-code-bridge) with a task; return output.
        task = (params.get("task") or params.get("prompt") or user_input or "").strip()
        cwd = (params.get("cwd") or "").strip() or None
        backend = (params.get("backend") or "").strip().lower()
        if not backend:
            # Infer from plugin_id when caller uses separate plugin ids.
            pid_lower = (plugin_id or "").strip().lower()
            backend = "claude" if "claude" in pid_lower else "cursor"
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
                cwd = _get_active_cwd(backend) or None
            if backend == "claude":
                success, text = await _run_claude_task(task, cwd=cwd, timeout_sec=timeout)
            else:
                success, text = await _run_agent_task(task, cwd=cwd, timeout_sec=timeout)

    elif cap_id == "run_agent_interactive":
        # Start Cursor or Claude agent in a PTY on the bridge; return session_id + initial_output for Core/Companion to use.
        backend = (params.get("backend") or "").strip().lower()
        if not backend:
            pid_lower = (plugin_id or "").strip().lower()
            backend = "claude" if "claude" in pid_lower else "cursor"
        cwd_override = (params.get("cwd") or "").strip() or None
        try:
            cmd, cwd = _agent_interactive_command(backend)
            if cwd_override and os.path.isdir(cwd_override):
                cwd = cwd_override
            session_env = _claude_subprocess_env() if backend == "claude" else None
            session_id, initial = await asyncio.to_thread(_BRIDGE_INTERACTIVE.start_session, cmd, cwd, session_env)
            text = json.dumps({"session_id": session_id, "initial_output": initial, "status": "running"}, ensure_ascii=False)
        except Exception as e:
            success = False
            error = str(e)
            text = ""

    elif cap_id == "run_command_interactive":
        # Start a shell command in a PTY on the bridge; return session_id + initial_output.
        command = (params.get("command") or "").strip()
        if not command:
            success = False
            error = "run_command_interactive requires 'command' in capability_parameters."
        else:
            cwd = (params.get("cwd") or "").strip() or None
            if not cwd:
                backend = (params.get("backend") or "").strip().lower()
                if not backend:
                    pid_lower = (plugin_id or "").strip().lower()
                    backend = "claude" if "claude" in pid_lower else "cursor"
                cwd = _get_active_cwd(backend) or DEFAULT_CWD
            if not os.path.isdir(cwd):
                cwd = DEFAULT_CWD
            try:
                session_id, initial = await asyncio.to_thread(_BRIDGE_INTERACTIVE.start_session, command, cwd)
                text = json.dumps({"session_id": session_id, "initial_output": initial, "status": "running"}, ensure_ascii=False)
            except Exception as e:
                success = False
                error = str(e)
                text = ""

    elif cap_id == "interactive_read":
        session_id = (params.get("session_id") or "").strip()
        if not session_id:
            success = False
            error = "interactive_read requires 'session_id' in capability_parameters."
        else:
            try:
                from_seq = int(params.get("from_seq") or 1)
            except (TypeError, ValueError):
                from_seq = 1
            try:
                chunks, status, exit_code, command = _BRIDGE_INTERACTIVE.read(session_id, from_seq=from_seq)
                text = json.dumps({
                    "session_id": session_id,
                    "status": status,
                    "exit_code": exit_code,
                    "command": command,
                    "chunks": [{"seq": c.seq, "text": c.text, "timestamp": c.timestamp} for c in chunks],
                }, ensure_ascii=False)
            except KeyError:
                success = False
                error = "Unknown session_id."
                text = ""
            except Exception as e:
                success = False
                error = str(e)
                text = ""

    elif cap_id == "interactive_write":
        session_id = (params.get("session_id") or "").strip()
        data = (params.get("data") or "").replace("\r\n", "\n")
        if not session_id:
            success = False
            error = "interactive_write requires 'session_id' in capability_parameters."
        else:
            try:
                _BRIDGE_INTERACTIVE.write(session_id, data)
                text = "ok"
            except KeyError:
                success = False
                error = "Unknown session_id."
                text = ""
            except Exception as e:
                success = False
                error = str(e)
                text = ""

    elif cap_id == "interactive_stop":
        session_id = (params.get("session_id") or "").strip()
        if not session_id:
            success = False
            error = "interactive_stop requires 'session_id' in capability_parameters."
        else:
            try:
                _BRIDGE_INTERACTIVE.stop(session_id)
                text = "stopped"
            except Exception as e:
                success = False
                error = str(e)
                text = ""

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
                success, text = await _run_command(task.split("\n")[0].strip())
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
        return await _run_impl(body)
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
