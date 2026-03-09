from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Only one clawhub login at a time so OAuth state is not overwritten (avoids "Missing state").
_clawhub_login_lock = threading.Lock()
# Background login: process handle and last URL (so "already in progress" can return the URL).
_clawhub_login_proc: Optional[subprocess.Popen] = None
_clawhub_login_url: Optional[str] = None

try:
    from loguru import logger  # type: ignore
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClawHubResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


def _get_clawhub_executable() -> Optional[str]:
    """
    Resolve path to clawhub executable (Windows, macOS, Linux).
    Checks PATH first, then common npm global install locations so Core finds clawhub even when
    started from an environment where npm global bin is not on PATH. Returns None if not found.
    Never raises.
    """
    try:
        exe = shutil.which("clawhub")
        if exe:
            return exe
        # Windows: npm global installs often go to %APPDATA%\\npm or %LOCALAPPDATA%\\npm
        if os.name == "nt":
            for base in (
                os.environ.get("APPDATA", ""),
                os.environ.get("LOCALAPPDATA", ""),
            ):
                if not base:
                    continue
                for name in ("clawhub.cmd", "clawhub.ps1", "clawhub"):
                    p = Path(base) / "npm" / name
                    if p.is_file():
                        return str(p)
        # Unix: common npm global bin paths
        try:
            home = Path.home()
            for candidate in (
                home / ".npm-global" / "bin" / "clawhub",
                home / ".nvm" / "current" / "bin" / "clawhub",
                home / ".local" / "share" / "npm" / "bin" / "clawhub",
            ):
                if candidate.is_file() or (candidate.parent / "clawhub").is_file():
                    return str(candidate) if candidate.is_file() else str(candidate.parent / "clawhub")
        except Exception:
            pass
        # Ask npm for global prefix and look for bin/clawhub (capture bytes, decode ourselves to avoid gbk in reader thread)
        try:
            proc = subprocess.run(
                ["npm", "config", "get", "prefix"],
                capture_output=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout:
                out = (proc.stdout or b"").decode("utf-8", errors="replace")
                prefix = Path(out.strip().strip('"'))
                if prefix.is_dir():
                    # Windows: prefix is often .../npm, so clawhub.cmd next to it
                    for name in ("clawhub.cmd", "clawhub.ps1", "clawhub"):
                        p = prefix / name
                        if p.is_file():
                            return str(p)
                    # Unix: prefix/bin/clawhub
                    bin_clawhub = prefix / "bin" / "clawhub"
                    if bin_clawhub.is_file():
                        return str(bin_clawhub)
        except Exception:
            pass
    except Exception:
        pass
    return None


def clawhub_available() -> bool:
    """True when `clawhub` is found on PATH or in common npm global locations."""
    return _get_clawhub_executable() is not None


def _clawhub_argv(*args: str) -> List[str]:
    """Build argv for running clawhub: [resolved_exe, ...args]. Returns [] if clawhub not found."""
    exe = _get_clawhub_executable()
    if not exe:
        return []
    return [exe] + list(args)


def clawhub_whoami(*, timeout_s: int = 10) -> Tuple[bool, str]:
    """
    Run `clawhub whoami` to check if the user is logged in.
    Returns (logged_in, message). Never raises.
    """
    if not clawhub_available():
        return (False, "clawhub not found on PATH")
    argv = _clawhub_argv("whoami")
    if not argv:
        return (False, "clawhub not found on PATH")
    r = _run_cmd(argv, timeout_s=timeout_s)
    if not r.ok:
        return (False, (r.stderr or r.stdout or r.error or "Not logged in").strip() or "Not logged in")
    out = (r.stdout or "").strip()
    return (True, out or "Logged in")


def clawhub_ensure_logged_in(token: Optional[str] = None) -> Tuple[bool, str]:
    """
    Ensure ClawHub CLI is logged in. If whoami fails and token is provided, run login --no-browser --token and retry.
    Use when config has clawhub_token (e.g. from core.yml). Returns (logged_in, message). Never raises.
    """
    try:
        logged_in, msg = clawhub_whoami(timeout_s=10)
        if logged_in:
            return (True, msg)
        t = (token or "").strip()
        if not t:
            return (False, msg)
        clawhub_login_with_token(t)
        return clawhub_whoami(timeout_s=10)
    except Exception:
        return (False, "Not logged in")


# Pattern to find a URL in clawhub login output (e.g. "Open https://... to authenticate")
_URL_RE = re.compile(r"https?://[^\s\)\]\"']+")


def _extract_login_url(combined: str) -> Optional[str]:
    """Extract OAuth URL from clawhub login stdout+stderr. Returns first likely URL or None. Never raises."""
    combined = (combined or "").strip()
    if not combined:
        return None
    for m in _URL_RE.finditer(combined):
        candidate = m.group(0).rstrip(".,;:")
        if any(x in candidate.lower() for x in ("github", "openclaw", "clawhub", "convex", "auth")):
            return candidate
    first = _URL_RE.search(combined)
    return first.group(0).rstrip(".,;:") if first else None


def _login_env() -> Dict[str, str]:
    """Build environment for clawhub login so the CLI can store OAuth state (e.g. under HOME). Never raises."""
    try:
        env = dict(os.environ)
        if "HOME" not in env or not (env.get("HOME") or "").strip():
            if os.name == "nt":
                env["HOME"] = (env.get("USERPROFILE") or "").strip() or env.get("APPDATA", "")
            else:
                try:
                    env["HOME"] = str(Path.home())
                except Exception:
                    pass
        return env
    except Exception:
        return dict(os.environ)


def _reap_clawhub_login_proc(proc: subprocess.Popen) -> None:
    """Background: wait for process, then clear global. Daemon thread. Never raises."""
    global _clawhub_login_proc
    try:
        proc.wait(timeout=300)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        with _clawhub_login_lock:
            if _clawhub_login_proc is proc:
                _clawhub_login_proc = None
    except Exception:
        pass


def clawhub_login_with_token(token: str) -> Dict[str, Any]:
    """
    Log in to ClawHub using a token (no browser). Run `clawhub login --no-browser --token <token>`.
    Use when the browser flow fails with "Missing state". Get a token from clawhub.ai (sign in with GitHub).
    Returns dict with: ok (bool), message (str), stdout (str), stderr (str). Never raises.
    """
    t = (token or "").strip()
    if not t:
        return {"ok": False, "message": "Token is empty", "stdout": "", "stderr": ""}
    if not clawhub_available():
        return {"ok": False, "message": "clawhub not found on PATH", "stdout": "", "stderr": ""}
    argv = _clawhub_argv("login", "--no-browser", "--token", t)
    if not argv:
        return {"ok": False, "message": "clawhub not found on PATH", "stdout": "", "stderr": ""}
    r = _run_cmd(argv, timeout_s=30, env=_login_env())
    if r.ok:
        out = (r.stdout or "").strip() or "Logged in with token."
        return {"ok": True, "message": out, "stdout": r.stdout or "", "stderr": r.stderr or ""}
    err = (r.stderr or r.stdout or r.error or "Token login failed").strip()
    return {"ok": False, "message": err[:500], "stdout": r.stdout or "", "stderr": r.stderr or ""}


def clawhub_login_start(*, wait_for_url_s: int = 15) -> Dict[str, Any]:
    """
    Start `clawhub login` in the background and return as soon as we have the URL (or after
    wait_for_url_s). The HTTP request can return quickly so proxies (e.g. Cloudflare) do not
    return 524. The user completes OAuth on the Core machine; tap "Refresh status" to verify.
    If already logged in (whoami succeeds), returns immediately without opening the browser.
    Returns dict with: ok (bool), url (str or None), message (str), stdout (str), stderr (str).
    Never raises.
    """
    global _clawhub_login_proc, _clawhub_login_url
    if not clawhub_available():
        return {"ok": False, "url": None, "message": "clawhub not found on PATH", "stdout": "", "stderr": ""}
    argv = _clawhub_argv("login")
    if not argv:
        return {"ok": False, "url": None, "message": "clawhub not found on PATH", "stdout": "", "stderr": ""}
    # If already logged in, do not open the browser; just report success.
    logged_in, whoami_msg = clawhub_whoami(timeout_s=10)
    if logged_in:
        return {
            "ok": True,
            "url": None,
            "message": f"Already logged in. {whoami_msg} No need to open the browser. Tap Refresh status to confirm.",
            "stdout": "",
            "stderr": "",
        }
    with _clawhub_login_lock:
        if _clawhub_login_proc is not None and _clawhub_login_proc.poll() is None:
            url = _clawhub_login_url or ""
            return {
                "ok": True,
                "url": url or None,
                "message": "Login already in progress. Complete it in the browser on the machine running Core, then tap Refresh status.",
                "stdout": "",
                "stderr": "",
            }
        try:
            proc = subprocess.Popen(
                argv,
                env=_login_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            return {"ok": False, "url": None, "message": str(e), "stdout": "", "stderr": ""}
        _clawhub_login_proc = proc
    output_lines: List[bytes] = []
    output_lock = threading.Lock()

    def read_stream(stream: Any) -> None:
        if stream is None:
            return
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                with output_lock:
                    output_lines.append(chunk)
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    t_out = threading.Thread(target=read_stream, args=(proc.stdout,), daemon=True)
    t_err = threading.Thread(target=read_stream, args=(proc.stderr,), daemon=True)
    t_out.start()
    t_err.start()
    url = None
    deadline = time.perf_counter() + max(1, min(60, wait_for_url_s))
    while time.perf_counter() < deadline and url is None:
        time.sleep(0.4)
        with output_lock:
            combined = ""
            for chunk in output_lines:
                combined += _decode_output(chunk)
        url = _extract_login_url(combined)
        if proc.poll() is not None:
            break
    with output_lock:
        combined = ""
        for chunk in output_lines:
            combined += _decode_output(chunk)
    if url is None:
        url = _extract_login_url(combined)
    if url:
        with _clawhub_login_lock:
            _clawhub_login_url = url
        t = threading.Thread(target=_reap_clawhub_login_proc, args=(proc,), daemon=True)
        t.start()
        return {
            "ok": True,
            "url": url,
            "message": "Complete login on the machine running Core. If a browser opened there, use it. Otherwise open the URL below on that machine only. Then tap Refresh status to confirm.",
            "stdout": combined[:2000],
            "stderr": "",
        }
    if proc.poll() is not None:
        out_str = combined
        raw_msg = (out_str or "Login failed").strip()
        if "missing state" in raw_msg.lower():
            raw_msg = "OAuth state was lost. Complete login only in the browser on the machine running Core; do not open the URL on another device."
        return {"ok": False, "url": None, "message": raw_msg[:500], "stdout": out_str[:2000], "stderr": ""}
    with _clawhub_login_lock:
        _clawhub_login_url = _extract_login_url(combined) or ""
    t = threading.Thread(target=_reap_clawhub_login_proc, args=(proc,), daemon=True)
    t.start()
    return {
        "ok": True,
        "url": _extract_login_url(combined),
        "message": "Login started. Complete it in the browser on the machine running Core, then tap Refresh status.",
        "stdout": combined[:2000],
        "stderr": "",
    }


def clawhub_login(*, timeout_s: int = 180) -> Dict[str, Any]:
    """
    Run `clawhub login` and block until the process exits or timeout. Prefer clawhub_login_start()
    from the API so the HTTP request returns quickly and proxies do not time out (524).
    Returns dict with: ok (bool), url (str or None), message (str), stdout (str), stderr (str).
    Never raises.
    """
    if not clawhub_available():
        return {"ok": False, "url": None, "message": "clawhub not found on PATH", "stdout": "", "stderr": ""}
    argv = _clawhub_argv("login")
    if not argv:
        return {"ok": False, "url": None, "message": "clawhub not found on PATH", "stdout": "", "stderr": ""}
    with _clawhub_login_lock:
        r = _run_cmd(argv, timeout_s=timeout_s, env=_login_env())
    combined = f"{r.stdout or ''}\n{r.stderr or ''}"
    url = _extract_login_url(combined)
    if url:
        return {
            "ok": True,
            "url": url,
            "message": "Complete login on the machine running Core. If a browser opened there, use it. Otherwise open the URL below on that machine only (the OAuth callback must reach that machine). Do not open the URL on this device unless this device is running Core.",
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
        }
    if r.ok:
        return {"ok": True, "url": None, "message": "Login may have completed. Check with whoami.", "stdout": r.stdout or "", "stderr": r.stderr or ""}
    raw_msg = (r.stderr or r.stdout or r.error or "Login failed").strip() or "Run 'clawhub login' in a terminal on the machine running Core."
    if "missing state" in raw_msg.lower():
        raw_msg = (
            "OAuth state was lost or mismatched. This usually means: (1) the login URL was opened on a different device (e.g. phone) — you must complete login only in the browser on the machine running Core; or (2) login was started twice — wait for one attempt to finish or time out, then try again once. Start a fresh login and complete it only on the Core machine."
        )
    return {
        "ok": False,
        "url": None,
        "message": raw_msg,
        "stdout": r.stdout or "",
        "stderr": r.stderr or "",
    }


def _decode_output(raw: Any) -> str:
    """Decode subprocess output as UTF-8; avoid system encoding (e.g. gbk) in reader threads. Never raises."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bytes):
        if len(raw) == 0:
            return ""
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            try:
                return raw.decode("latin-1", errors="replace")
            except Exception:
                return ""
    return ""


def _first_error_line(stderr: str, max_len: int = 500) -> str:
    """Extract first meaningful error line from stderr (skip Node/experimental warnings). Never raises."""
    if not (stderr or "").strip():
        return ""
    for line in (stderr or "").splitlines():
        ln = (line or "").strip()
        if not ln or len(ln) < 5:
            continue
        low = ln.lower()
        if "experimental" in low or "deprecat" in low or "warning" in low or "warn:" in low:
            continue
        return ln[:max_len]
    return (stderr or "").strip()[:max_len]


def _run_cmd(
    argv: List[str],
    *,
    cwd: Optional[Path] = None,
    timeout_s: int = 60,
    env: Optional[Dict[str, str]] = None,
) -> ClawHubResult:
    """Run a command and capture output. Never raises.
    Captures stdout/stderr as bytes and decodes as UTF-8 in this process so the subprocess
    reader threads never use system encoding (avoids gbk UnicodeDecodeError on Windows).
    If env is provided, the subprocess uses it; otherwise it inherits the current environment."""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            timeout=max(1, int(timeout_s)),
            env=env,
        )
        dt_ms = int((time.perf_counter() - t0) * 1000)
        out_str = _decode_output(proc.stdout)
        err_str = _decode_output(proc.stderr)
        if proc.returncode == 0:
            err_msg = None
        else:
            snippet = _first_error_line(err_str)
            err_msg = f"Command failed ({proc.returncode})" + (f": {snippet}" if snippet else "")
        return ClawHubResult(
            ok=proc.returncode == 0,
            stdout=out_str,
            stderr=err_str,
            returncode=int(proc.returncode),
            duration_ms=dt_ms,
            error=err_msg,
        )
    except FileNotFoundError:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return ClawHubResult(ok=False, returncode=127, duration_ms=dt_ms, error="clawhub not found on PATH")
    except subprocess.TimeoutExpired as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        out = _decode_output(getattr(e, "stdout", None))
        err = _decode_output(getattr(e, "stderr", None))
        return ClawHubResult(ok=False, stdout=out, stderr=err, returncode=124, duration_ms=dt_ms, error="Command timed out")
    except Exception as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return ClawHubResult(ok=False, returncode=1, duration_ms=dt_ms, error=str(e))


def clawhub_search(query: str, *, limit: int = 20, timeout_s: int = 30) -> Tuple[List[Dict[str, Any]], ClawHubResult]:
    """
    Search skills via `clawhub search`.
    Returns (results, raw_result). Never raises.

    Parsing strategy:
    - Prefer JSON if `clawhub search --json` is supported.
    - Fallback: parse table-ish text into minimal {id,name,description} rows.
    """
    try:
        q = (query or "").strip()
        if not q:
            return ([], ClawHubResult(ok=False, error="query is empty"))
        try:
            lim = max(1, min(200, int(limit) if limit is not None else 20))
        except (TypeError, ValueError):
            lim = 20

        # Try JSON mode first (many CLIs support this).
        argv = _clawhub_argv("search", q, "--limit", str(lim), "--json")
        if not argv:
            return ([], ClawHubResult(ok=False, error="clawhub not found on PATH"))
        r = _run_cmd(argv, timeout_s=timeout_s)
        if r.ok:
            try:
                data = json.loads(r.stdout or "[]")
                if isinstance(data, dict) and "results" in data:
                    data = data.get("results")
                if isinstance(data, list):
                    out = []
                    for row in data:
                        if not isinstance(row, dict):
                            continue
                        sid = (row.get("id") or row.get("name") or row.get("slug") or "").strip()
                        if not sid:
                            continue
                        out.append({
                            "id": sid,
                            "name": (row.get("name") or sid).strip(),
                            "description": (row.get("description") or row.get("summary") or "").strip(),
                            "downloads": row.get("downloads"),
                            "stars": row.get("stars") or row.get("rating"),
                            "tags": row.get("tags") if isinstance(row.get("tags"), list) else None,
                        })
                    return (out, r)
            except Exception:
                # Fall through to text parsing.
                pass

        # Fallback: plain text output
        argv2 = _clawhub_argv("search", q, "--limit", str(lim))
        r2 = _run_cmd(argv2, timeout_s=timeout_s) if argv2 else ClawHubResult(ok=False, error="clawhub not found on PATH")
        if not r2.ok:
            return ([], r2)
        lines = [ln.rstrip("\n") for ln in (r2.stdout or "").splitlines() if ln.strip()]
        if not lines:
            return ([], r2)

        # Heuristic parsing: try to extract first token as id, rest as description.
        results = []
        for ln in lines:
            if ln.strip().lower().startswith(("id ", "name ", "search", "results", "---")):
                continue
            m = re.match(r"^\s*([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)\s+(.*)$", ln)
            if not m:
                continue
            sid = (m.group(1) or "").strip()
            desc = (m.group(2) or "").strip()
            if not sid:
                continue
            results.append({"id": sid, "name": sid, "description": desc})
            if len(results) >= lim:
                break
        return (results, r2)
    except Exception as e:
        return ([], ClawHubResult(ok=False, error=str(e)))


def _candidate_openclaw_skills_dirs(extra_dirs: Optional[List[Path]] = None) -> List[Path]:
    """Likely OpenClaw install dirs: optional extra_dirs first (e.g. project downloads/skills), then cwd/skills, then ~/.openclaw/skills."""
    out: List[Path] = []
    if extra_dirs:
        for p in extra_dirs:
            if p is None:
                continue
            out.append(p)
    try:
        out.append(Path.cwd() / "skills")
    except Exception:
        pass
    try:
        out.append(Path.home() / ".openclaw" / "skills")
    except Exception:
        pass
    # De-dup while preserving order
    seen = set()
    uniq: List[Path] = []
    for p in out:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if str(rp) in seen:
            continue
        seen.add(str(rp))
        uniq.append(p)
    return uniq


def find_openclaw_installed_skill_dir(skill_id: str, extra_search_dirs: Optional[List[Path]] = None) -> Optional[Path]:
    """
    Best-effort locate of an installed OpenClaw skill folder.
    When extra_search_dirs is set (e.g. [downloads/skills, downloads]), those are searched first.
    Never raises; returns None if not found.
    """
    sid = (skill_id or "").strip()
    if not sid:
        return None
    candidates = _candidate_openclaw_skills_dirs(extra_dirs=extra_search_dirs)
    # Prefer exact name match; else newest folder containing sid.
    newest: Tuple[float, Optional[Path]] = (0.0, None)
    for base in candidates:
        try:
            if not base.is_dir():
                continue
            exact = base / sid
            if exact.is_dir():
                return exact
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                name = child.name or ""
                if sid.lower() == name.lower():
                    return child
                if sid.lower() in name.lower():
                    try:
                        mtime = child.stat().st_mtime
                    except Exception:
                        mtime = 0.0
                    if mtime >= newest[0]:
                        newest = (mtime, child)
        except Exception:
            continue
    return newest[1]


def clawhub_install(
    skill_spec: str,
    *,
    timeout_s: int = 180,
    dry_run: bool = False,
    with_deps: bool = False,
    cwd: Optional[Path] = None,
) -> ClawHubResult:
    """
    Install a skill via `clawhub install <spec>`.
    When cwd is set (e.g. project_root/downloads), clawhub uses that as working dir so the skill is downloaded there
    (typically into cwd/skills/<skill_id>). Otherwise uses process cwd / ~/.openclaw/skills.
    """
    spec = (skill_spec or "").strip()
    if not spec:
        return ClawHubResult(ok=False, error="skill_spec is empty")
    argv = _clawhub_argv("install", spec)
    if not argv:
        return ClawHubResult(ok=False, error="clawhub not found on PATH")
    if dry_run:
        argv.append("--dry-run")
    if with_deps:
        argv.append("--with-deps")
    return _run_cmd(argv, cwd=cwd, timeout_s=timeout_s)


def convert_installed_openclaw_skill_to_homeclaw(
    *,
    skill_id: str,
    homeclaw_root: Path,
    external_skills_dir: str,
    openclaw_search_dirs: Optional[List[Path]] = None,
    timeout_s: int = 180,
) -> Dict[str, Any]:
    """
    Convert an already-installed OpenClaw skill into HomeClaw external_skills dir using scripts/convert_openclaw_skill.py.
    When openclaw_search_dirs is set (e.g. [downloads/skills, downloads]), those are searched first for the skill folder.
    Returns { ok: bool, ... }. Never raises.
    """
    try:
        # Ensure project root (parent of base/) is on sys.path so "scripts" can be imported when Core is run from another cwd
        _project_root = str(Path(__file__).resolve().parent.parent)
        if _project_root not in sys.path:
            sys.path.insert(0, _project_root)
        from scripts.convert_openclaw_skill import convert_skill  # type: ignore
    except Exception as e:
        return {"ok": False, "error": f"Converter import failed: {e}. Run Core from the project root or ensure scripts/ is on PYTHONPATH."}

    sid = (skill_id or "").strip()
    if not sid:
        return {"ok": False, "error": "skill_id is empty"}

    try:
        src = find_openclaw_installed_skill_dir(sid, extra_search_dirs=openclaw_search_dirs)
    except Exception:
        src = None
    if not src or not src.is_dir():
        candidates = _candidate_openclaw_skills_dirs(extra_dirs=openclaw_search_dirs)
        searched = ", ".join(str(p) for p in candidates[:5])
        return {
            "ok": False,
            "error": f"Installed OpenClaw skill not found for '{sid}'. Searched: {searched}. If clawhub install succeeded, the skill may be under a different name (e.g. skill-1.0.0); check the install cwd (e.g. downloads/skills/).",
        }

    # external_skills_dir can be relative to root or absolute; empty means disabled.
    ext = (external_skills_dir or "").strip()
    if not ext:
        return {"ok": False, "error": "external_skills_dir is empty/disabled in config; enable it to install converted skills."}
    try:
        out_base = Path(ext)
        if not out_base.is_absolute():
            out_base = (homeclaw_root / out_base).resolve()
        else:
            out_base = out_base.resolve()
    except Exception:
        out_base = (homeclaw_root / "external_skills").resolve()

    out_dir = out_base / sid
    try:
        report = convert_skill(src, out_dir, dry_run=False, merge_skill_yaml=True)
        if isinstance(report, dict) and report.get("error"):
            return {"ok": False, "error": report.get("error"), "source": str(src), "output": str(out_dir)}
        return {"ok": True, "source": str(src), "output": str(out_dir), "report": report}
    except Exception as e:
        return {"ok": False, "error": str(e), "source": str(src), "output": str(out_dir)}


def clawhub_install_and_convert(
    *,
    skill_spec: str,
    skill_id_hint: Optional[str],
    homeclaw_root: Path,
    external_skills_dir: str,
    clawhub_download_dir: Optional[str] = None,
    dry_run: bool = False,
    with_deps: bool = False,
) -> Dict[str, Any]:
    """
    One-shot: run `clawhub install` with cwd=clawhub_download_dir (staging), then locate installed folder,
    then convert into HomeClaw external_skills_dir. When clawhub_download_dir is set (e.g. "downloads"),
    install runs with cwd=homeclaw_root/clawhub_download_dir so OpenClaw downloads go there; we then search
    that dir (and its skills/ subdir) first when locating the skill for conversion.
    Returns { ok: bool, install: {..}, convert: {..} }. Never raises.
    """
    spec = (skill_spec or "").strip()
    if not spec:
        return {"ok": False, "error": "skill_spec is empty"}
    sid = (skill_id_hint or "").strip() or spec.split("@", 1)[0].split(":", 1)[0].strip()

    download_path: Optional[Path] = None
    if (clawhub_download_dir or "").strip():
        try:
            d = Path((clawhub_download_dir or "").strip())
            download_path = (homeclaw_root / d).resolve() if not d.is_absolute() else d.resolve()
            # Ensure cwd exists so subprocess.run(cwd=...) does not fail
            if download_path and not download_path.is_dir():
                download_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            download_path = None

    install_res = clawhub_install(
        spec, dry_run=dry_run, with_deps=with_deps, cwd=download_path, timeout_s=180
    )
    install_info = {
        "ok": install_res.ok,
        "returncode": install_res.returncode,
        "duration_ms": install_res.duration_ms,
        "stdout": (install_res.stdout or "")[-8000:],
        "stderr": (install_res.stderr or "")[-8000:],
        "error": install_res.error,
    }
    if dry_run:
        return {"ok": install_res.ok, "install": install_info, "convert": None}
    if not install_res.ok:
        # If stderr suggests login/auth or permission, append a hint
        err_lower = (install_res.stderr or "").lower()
        if any(x in err_lower for x in ("login", "not logged in", "unauthorized", "401", "authenticate", "clawhub login")):
            install_info["hint"] = "ClawHub may require login. On the machine running Core, run: clawhub login"
        elif any(x in err_lower for x in ("eacces", "permission denied", "eperm", "read-only")):
            install_info["hint"] = "Permission denied. Run Core from a writable directory or set homeclaw_root in config to a writable path."
        return {"ok": False, "install": install_info, "convert": None}

    openclaw_search_dirs: Optional[List[Path]] = None
    if download_path and download_path.is_dir():
        openclaw_search_dirs = [download_path / "skills", download_path]

    convert_res = convert_installed_openclaw_skill_to_homeclaw(
        skill_id=sid,
        homeclaw_root=homeclaw_root,
        external_skills_dir=external_skills_dir,
        openclaw_search_dirs=openclaw_search_dirs,
    )
    return {"ok": bool(convert_res.get("ok")), "install": install_info, "convert": convert_res}

