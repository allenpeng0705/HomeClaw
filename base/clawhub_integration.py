from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def clawhub_available() -> bool:
    """True when `clawhub` is on PATH."""
    try:
        return shutil.which("clawhub") is not None
    except Exception:
        return False


def _run_cmd(
    argv: List[str],
    *,
    cwd: Optional[Path] = None,
    timeout_s: int = 60,
) -> ClawHubResult:
    """Run a command and capture output. Never raises."""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_s)),
        )
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return ClawHubResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            returncode=int(proc.returncode),
            duration_ms=dt_ms,
            error=None if proc.returncode == 0 else f"Command failed ({proc.returncode})",
        )
    except FileNotFoundError:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return ClawHubResult(ok=False, returncode=127, duration_ms=dt_ms, error="clawhub not found on PATH")
    except subprocess.TimeoutExpired as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        out = (getattr(e, "stdout", None) or "") if isinstance(getattr(e, "stdout", None), str) else ""
        err = (getattr(e, "stderr", None) or "") if isinstance(getattr(e, "stderr", None), str) else ""
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
    q = (query or "").strip()
    if not q:
        return ([], ClawHubResult(ok=False, error="query is empty"))
    lim = max(1, min(200, int(limit) if limit is not None else 20))

    # Try JSON mode first (many CLIs support this).
    r = _run_cmd(["clawhub", "search", q, "--limit", str(lim), "--json"], timeout_s=timeout_s)
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
    r2 = _run_cmd(["clawhub", "search", q, "--limit", str(lim)], timeout_s=timeout_s)
    if not r2.ok:
        return ([], r2)
    lines = [ln.rstrip("\n") for ln in (r2.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return ([], r2)

    # Heuristic parsing: try to extract first token as id, rest as description.
    results: List[Dict[str, Any]] = []
    for ln in lines:
        if ln.strip().lower().startswith(("id ", "name ", "search", "results", "---")):
            continue
        # Common formats:
        # - "summarize  Text summarization skill ..."
        # - "owner/skill-name  Description ..."
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
    argv = ["clawhub", "install", spec]
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
        from scripts.convert_openclaw_skill import convert_skill  # type: ignore
    except Exception as e:
        return {"ok": False, "error": f"Converter import failed: {e}"}

    sid = (skill_id or "").strip()
    if not sid:
        return {"ok": False, "error": "skill_id is empty"}

    try:
        src = find_openclaw_installed_skill_dir(sid, extra_search_dirs=openclaw_search_dirs)
    except Exception:
        src = None
    if not src or not src.is_dir():
        return {"ok": False, "error": f"Installed OpenClaw skill not found for '{sid}'. Try running `clawhub install {sid}` first."}

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

