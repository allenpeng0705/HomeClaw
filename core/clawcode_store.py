"""Claw-Code session persistence (JSON files). See docs_design/ClawCode_API_Sketch.md."""

from __future__ import annotations

import json
import os
import shlex
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from base.util import Util


def _clawcode_config() -> Dict[str, Any]:
    meta = Util().get_core_metadata()
    raw = getattr(meta, "clawcode", None)
    return raw if isinstance(raw, dict) else {}


def clawcode_feature_enabled() -> bool:
    return bool(_clawcode_config().get("enabled"))


def clawcode_direct_openai_settings(request: Any) -> Optional[Dict[str, str]]:
    """
    Optional OpenAI-compatible chat endpoint used only for Claw-Code turns (inbound has clawcode_session_id).
    Bypasses cloud_llm_host / LiteLLM proxy for those completions.

    core.yml under clawcode.direct_openai:
      base_url: https://api.example.com/v1   # /chat/completions appended if missing
      model: <provider model id>
      api_key: "..."                         # optional; prefer api_key_env for secrets
      api_key_env: MINIMAX_API_KEY           # read key from environment

    Returns dict with keys url, api_key, model; or None if not configured / missing key / not a Claw-Code turn.
    """
    if request is None or not clawcode_feature_enabled():
        return None
    md = getattr(request, "request_metadata", None) or {}
    if not isinstance(md, dict) or not str(md.get("clawcode_session_id") or "").strip():
        return None
    root = _clawcode_config().get("direct_openai")
    if not isinstance(root, dict):
        return None
    base = str(root.get("base_url") or root.get("url") or "").strip().rstrip("/")
    if not base:
        return None
    model = str(root.get("model") or "").strip()
    if not model:
        return None
    key = ""
    ak = root.get("api_key")
    if isinstance(ak, str):
        key = ak.strip()
    if not key:
        envn = str(root.get("api_key_env") or root.get("api_key_name") or "").strip()
        if envn:
            key = (os.environ.get(envn) or "").strip()
    if not key:
        return None
    blo = base.lower()
    if not blo.startswith(("http://", "https://")):
        base = "https://" + base.lstrip("/")
    if "/chat/completions" in base:
        url = base
    else:
        url = base + "/chat/completions"
    return {"url": url, "api_key": key, "model": model}


def default_clawcode_tool_profile() -> str:
    return str((_clawcode_config().get("default_tool_profile") or "coding")).strip() or "coding"


def default_clawcode_session_mode() -> str:
    """New sessions: plan (read-biased tool policy) or agent (default)."""
    m = str(_clawcode_config().get("default_session_mode") or "agent").strip().lower()
    return m if m in ("plan", "agent") else "agent"


def clawcode_git_writes_allowed() -> bool:
    """
    When False (explicit in core.yml), Claw-Code turns block git mutating commands via exec.
    When key is omitted, allow (backward compatible).
    """
    cfg = _clawcode_config()
    if "git_write_allowed" not in cfg:
        return True
    return bool(cfg.get("git_write_allowed"))


def session_mode_value(rec: Optional[Dict[str, Any]]) -> str:
    if not isinstance(rec, dict):
        return "agent"
    m = str(rec.get("mode") or "agent").strip().lower()
    return m if m in ("plan", "agent") else "agent"


def _looks_like_git_write_command(command: str) -> bool:
    c = (command or "").strip().lower()
    if not c or "git" not in c:
        return False
    import re

    if not re.search(r"(?:^|[;&|])\s*git\s+", c):
        return False
    # Mutating / history-changing git operations
    return bool(
        re.search(
            r"\bgit\s+(commit|push|pull|merge|rebase|cherry-pick|stash|reset|clean|rm|mv|branch\s+-[dD]|switch\s+-[dD]|checkout\s+-b)\b",
            c,
        )
    )


def clawcode_exec_git_block_message(command: str, context: Any) -> Optional[str]:
    """If exec should be blocked for Claw-Code git policy, return user-facing error; else None."""
    if clawcode_git_writes_allowed():
        return None
    req = getattr(context, "request", None)
    md = getattr(req, "request_metadata", None) if req is not None else None
    if not isinstance(md, dict) or not str(md.get("clawcode_session_id") or "").strip():
        return None
    if not clawcode_feature_enabled():
        return None
    if not _looks_like_git_write_command(command):
        return None
    return (
        "Error: git write/network git commands are disabled for Claw-Code on this Core "
        "(clawcode.git_write_allowed: false). Ask the operator to enable git_write_allowed or run git outside the agent."
    )


def _validated_llm_ref(ref: str) -> Optional[str]:
    r = (ref or "").strip()
    if not r:
        return None
    try:
        ent, _ = Util()._get_model_entry(r)
        if ent and Util().model_entry_available(ent):
            return r
    except Exception:
        pass
    return None


def apply_clawcode_main_llm_override(effective_llm_name: Optional[str], request: Any) -> Optional[str]:
    """After routing selects a main model, session main_llm_ref overrides when valid."""
    if request is None:
        return effective_llm_name
    md = getattr(request, "request_metadata", None) or {}
    if not isinstance(md, dict):
        return effective_llm_name
    csid = str(md.get("clawcode_session_id") or "").strip()
    if not csid or not clawcode_feature_enabled():
        return effective_llm_name
    s = get_session(csid)
    if not isinstance(s, dict):
        return effective_llm_name
    ref = str(s.get("main_llm_ref") or "").strip()
    chosen = _validated_llm_ref(ref)
    return chosen if chosen else effective_llm_name


def clawcode_tool_llm_ref_for_session(request: Any) -> Optional[str]:
    """Optional per-session tool-calling model (validated against llm.yml)."""
    if request is None:
        return None
    md = getattr(request, "request_metadata", None) or {}
    if not isinstance(md, dict):
        return None
    csid = str(md.get("clawcode_session_id") or "").strip()
    if not csid or not clawcode_feature_enabled():
        return None
    s = get_session(csid)
    if not isinstance(s, dict):
        return None
    ref = str(s.get("tool_llm_ref") or "").strip()
    return _validated_llm_ref(ref)


_PATH_PREFLIGHT_TOOLS = frozenset(
    {"file_read", "file_write", "file_edit", "document_read", "file_understand", "folder_list", "file_find"}
)


def clawcode_tool_preflight(tool_name: str, arguments: Dict[str, Any], context: Any) -> Optional[str]:
    """
    Claw-Code-only guards before approval gate / execution.
    Absolute paths must stay under the session cwd (and allowed_roots).
    """
    if not clawcode_feature_enabled():
        return None
    req = getattr(context, "request", None)
    md = getattr(req, "request_metadata", None) if req is not None else None
    if not isinstance(md, dict):
        return None
    csid = str(md.get("clawcode_session_id") or "").strip()
    if not csid:
        return None
    sess = get_session(csid)
    if not sess:
        return None
    root = str(sess.get("cwd") or "").strip()
    if not root or not os.path.isdir(root):
        return None
    name = (tool_name or "").strip()
    args = arguments if isinstance(arguments, dict) else {}
    if name in _PATH_PREFLIGHT_TOOLS:
        p = args.get("path") or args.get("image") or ""
        ps = str(p).strip() if p is not None else ""
        if ps and os.path.isabs(ps):
            try:
                norm_root = os.path.realpath(_normalize_cwd(root))
                norm_path = os.path.realpath(_normalize_cwd(ps))
                common = os.path.commonpath([norm_path, norm_root])
                if common != norm_root:
                    return (
                        f"Error: absolute path escapes Claw-Code session cwd — path must be under `{norm_root}`."
                    )
            except (ValueError, OSError):
                return "Error: invalid path for Claw-Code session."
    return None


def rebind_session_cwd(session_id: str, owner_user_id: str, new_cwd: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    """Change session cwd (same validation as create)."""
    sid = (session_id or "").strip()
    oid = (owner_user_id or "").strip()
    if not sid or not oid:
        return None, "session_id and owner_user_id are required", 400
    if not clawcode_feature_enabled():
        return None, "Claw-Code API disabled (set clawcode.enabled: true in core.yml)", 404
    rec = get_session(sid)
    if not rec:
        return None, "session not found", 404
    if str(rec.get("owner_user_id") or "").strip() != oid:
        return None, "forbidden", 403
    norm_cwd = _normalize_cwd(new_cwd)
    if not norm_cwd or not os.path.isdir(norm_cwd):
        return None, "cwd must be an existing directory", 400
    if not cwd_allowed(norm_cwd):
        return None, "cwd is not under clawcode.allowed_roots", 403
    out = touch_session(sid, cwd=norm_cwd)
    return out, None, 200


def validate_clawcode_turn(
    clawcode_session_id: str,
    inbound_user_id: str,
    system_user_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[int]]:
    """
    Same rules as POST /inbound when clawcode_session_id is set.
    Session owner may match inbound channel user_id (e.g. telegram_123) or Core system_user_id
    (user.yml id/name) so P5 channel bindings keyed by Core user id work for IM channels.
    Returns (error_message, http_status) if invalid; (None, None) if valid or id empty.
    """
    csid = (clawcode_session_id or "").strip()
    if not csid:
        return None, None
    if not clawcode_feature_enabled():
        return (
            "Claw-Code is disabled (omit clawcode_session_id or set clawcode.enabled in core.yml)",
            403,
        )
    sess = get_session(csid)
    if not sess:
        return "Unknown clawcode_session_id", 404
    owner = str(sess.get("owner_user_id") or "").strip()
    uid_in = (inbound_user_id or "").strip()
    sys_u = (system_user_id or "").strip()
    if owner == uid_in:
        return None, None
    if sys_u and owner == sys_u:
        return None, None
    return "Claw-Code session access denied (user_id must match session owner)", 403


def prepare_prompt_request_clawcode(request: Any) -> Optional[str]:
    """
    For POST /process: merge channel binding (P5), validate clawcode_session_id, set default tool_profile.
    Returns user-facing error text or None if OK.
    """
    md = dict(getattr(request, "request_metadata", None) or {})
    csid = str(md.get("clawcode_session_id") or "").strip()
    uid = (getattr(request, "user_id", None) or "").strip()
    sys_uid = (getattr(request, "system_user_id", None) or "").strip()
    if not csid and clawcode_feature_enabled():
        from core import clawcode_channel_bindings as _ccb

        for key in (sys_uid, uid):
            if not key:
                continue
            bound = _ccb.get_binding(key)
            if bound:
                csid = bound
                md["clawcode_session_id"] = csid
                break
    if not csid:
        return None
    md["clawcode_session_id"] = csid
    try:
        request.request_metadata = md
    except Exception:
        pass
    err, _st = validate_clawcode_turn(csid, uid, system_user_id=sys_uid or None)
    if err:
        return err
    tp = getattr(request, "tool_profile", None)
    if not tp or not str(tp).strip():
        try:
            request.tool_profile = default_clawcode_tool_profile()
        except Exception:
            pass
    try:
        from base.workflow_trace import emit_event

        emit_event(
            event_type="clawcode_turn_started",
            component="clawcode",
            summary="process queue turn with clawcode session",
            details={"clawcode_session_id": csid, "user_id": uid},
        )
    except Exception:
        pass
    return None


def sessions_base_dir() -> Path:
    root = Util().root_path()
    return Path(root) / "database" / "clawcode_sessions"


def _normalize_cwd(cwd: str) -> str:
    return os.path.normpath(os.path.abspath((cwd or "").strip()))


def cwd_allowed(cwd: str) -> bool:
    cfg = _clawcode_config()
    roots = cfg.get("allowed_roots")
    if not isinstance(roots, list) or not roots:
        return True
    norm = _normalize_cwd(cwd)
    for r in roots:
        if not isinstance(r, str) or not r.strip():
            continue
        base = _normalize_cwd(r)
        try:
            common = os.path.commonpath([norm, base])
            if common == base or norm == base:
                return True
        except (ValueError, OSError):
            continue
    return False


def _session_path(session_id: str) -> Path:
    sid = (session_id or "").strip()
    if not sid or "/" in sid or "\\" in sid or sid.startswith("."):
        raise ValueError("invalid session id")
    return sessions_base_dir() / f"{sid}.json"


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    path = _session_path(session_id)
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def create_session(*, owner_user_id: str, cwd: str) -> Dict[str, Any]:
    owner = (owner_user_id or "").strip()
    if not owner:
        raise ValueError("owner_user_id is required")
    norm_cwd = _normalize_cwd(cwd)
    if not norm_cwd or not os.path.isdir(norm_cwd):
        raise ValueError("cwd must be an existing directory")
    if not cwd_allowed(norm_cwd):
        raise PermissionError("cwd is not under clawcode.allowed_roots")
    sessions_base_dir().mkdir(parents=True, exist_ok=True)
    sid = str(uuid.uuid4())
    now = time.time()
    rec: Dict[str, Any] = {
        "clawcode_session_id": sid,
        "owner_user_id": owner,
        "cwd": norm_cwd,
        "status": "idle",
        "mode": default_clawcode_session_mode(),
        "created_at": now,
        "updated_at": now,
        "git_remote_hint": "",
        "last_run_id": "",
        "main_llm_ref": "",
        "tool_llm_ref": "",
        "task_plan": [],
        "checkpoint": "",
        "resume_hint": "",
        "last_run_error": "",
    }
    path = _session_path(sid)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    return rec


def list_sessions_for_owner(owner_user_id: str) -> List[Dict[str, Any]]:
    owner = (owner_user_id or "").strip().lower()
    if not owner:
        return []
    base = sessions_base_dir()
    if not base.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            if str(data.get("owner_user_id") or "").strip().lower() == owner:
                out.append(data)
        except Exception:
            continue
    out.sort(key=lambda x: float(x.get("updated_at") or x.get("created_at") or 0), reverse=True)
    return out


def touch_session(session_id: str, **updates: Any) -> Optional[Dict[str, Any]]:
    rec = get_session(session_id)
    if not rec:
        return None
    rec.update({k: v for k, v in updates.items() if v is not None})
    rec["updated_at"] = time.time()
    path = _session_path(session_id)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    return rec


_PATCHABLE_SESSION_KEYS = frozenset(
    {
        "git_remote_hint",
        "main_llm_ref",
        "tool_llm_ref",
        "mode",
        "task_plan",
        "checkpoint",
        "resume_hint",
        "last_run_error",
    }
)


def _normalize_task_plan(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(raw[:50]):
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or f"step-{i + 1}").strip()[:64]
        title = str(item.get("title") or "").strip()[:500]
        st = str(item.get("status") or "pending").strip().lower()
        if st not in ("pending", "running", "done", "blocked"):
            st = "pending"
        out.append({"id": tid or f"step-{i + 1}", "title": title, "status": st})
    return out


def _clip_text(val: Any, max_len: int) -> str:
    s = str(val if val is not None else "").strip()
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def patch_clawcode_session_metadata(
    session_id: str,
    owner_user_id: str,
    updates: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    """
    Whitelisted PATCH fields for operator notes (not cwd/owner/session id).
    Returns (updated_record, error_message, http_status).
    """
    sid = (session_id or "").strip()
    oid = (owner_user_id or "").strip()
    if not sid or not oid:
        return None, "session_id and owner_user_id are required", 400
    if not clawcode_feature_enabled():
        return None, "Claw-Code API disabled (set clawcode.enabled: true in core.yml)", 404
    rec = get_session(sid)
    if not rec:
        return None, "session not found", 404
    if str(rec.get("owner_user_id") or "").strip() != oid:
        return None, "forbidden", 403
    allowed: Dict[str, Any] = {}
    if not isinstance(updates, dict):
        return None, "invalid body", 400
    for k, v in updates.items():
        if k not in _PATCHABLE_SESSION_KEYS:
            continue
        if v is None:
            continue
        if k == "mode":
            vv = str(v).strip().lower()
            if vv not in ("plan", "agent"):
                continue
            allowed[k] = vv
            continue
        if k == "task_plan":
            allowed[k] = _normalize_task_plan(v)
            continue
        if k == "checkpoint":
            allowed[k] = _clip_text(v, 4000)
            continue
        if k == "resume_hint":
            allowed[k] = _clip_text(v, 8000)
            continue
        if k == "last_run_error":
            allowed[k] = _clip_text(v, 8000)
            continue
        allowed[k] = str(v).strip() if not isinstance(v, str) else v.strip()
    if not allowed:
        return (
            None,
            "no valid fields (allowed: git_remote_hint, main_llm_ref, tool_llm_ref, mode, "
            "task_plan, checkpoint, resume_hint, last_run_error)",
            400,
        )
    out = touch_session(sid, **allowed)
    return out, None, 200


def clawcode_usage_hint() -> str:
    """Short operator-facing note for UIs (tokens / observability). Override with clawcode.usage_hint in core.yml."""
    custom = str(_clawcode_config().get("usage_hint") or "").strip()
    if custom:
        return custom
    return (
        "After each completed Claw-Code turn, Core stores aggregated LLM usage on the session as "
        "`last_usage` when the model returns prompt_tokens/completion_tokens (multi-round turns are summed). "
        "If your stack omits usage, use workflow trace (python3 -m main clawcode attach) or your provider dashboard."
    )


def clawcode_mcp_allowlist_entries() -> List[str]:
    """Non-empty list means Claw-Code turns may only call MCP tools listed as `server_id/tool_name` (case-insensitive)."""
    raw = _clawcode_config().get("mcp_tool_allowlist")
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def clawcode_mcp_preset_note() -> str:
    """Operator text from clawcode.mcp_preset_note; injected into the system prompt when a Claw-Code session is active."""
    return str(_clawcode_config().get("mcp_preset_note") or "").strip()


def clawcode_mcp_pair_allowed(server_id: str, tool_name: str) -> bool:
    entries = clawcode_mcp_allowlist_entries()
    if not entries:
        return True
    key = f"{(server_id or '').strip()}/{(tool_name or '').strip()}".lower()
    return any((e or "").strip().lower() == key for e in entries)


def format_worktree_hint(cwd: str) -> str:
    """Suggested git worktree command for the session repo (shell-safe quoted paths)."""
    c = _normalize_cwd((cwd or "").strip())
    if not c or not os.path.isdir(c):
        return ""
    parent = os.path.dirname(c.rstrip(os.sep)) or c
    leaf = os.path.basename(c.rstrip(os.sep)) or "repo"
    wt_path = os.path.join(parent, f"{leaf}-clawcode-wt")
    return f"git -C {shlex.quote(c)} worktree add {shlex.quote(wt_path)} -b clawcode-branch"


def resolve_path_under_session_cwd(root: str, relative: str) -> Optional[str]:
    """Resolve relative path under session cwd; reject .. and escapes. Returns realpath or None."""
    root_norm = os.path.realpath(_normalize_cwd((root or "").strip()))
    if not root_norm or not os.path.isdir(root_norm):
        return None
    rel = (relative or "").strip().replace("\\", "/")
    if rel in ("", ".", "/"):
        return root_norm
    if os.path.isabs(rel):
        return None
    segments = [s for s in rel.split("/") if s and s != "."]
    if ".." in segments:
        return None
    cur = root_norm
    for seg in segments:
        cur = os.path.realpath(os.path.join(cur, seg))
        try:
            if os.path.commonpath([cur, root_norm]) != root_norm:
                return None
        except ValueError:
            return None
    return cur


def list_workspace_files(
    session_id: str, owner_user_id: str, relative: str = ""
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], int]:
    """
    List non-hidden names in a directory under the session cwd (owner-checked).
    Returns (entries, error_message, http_status).
    """
    if not clawcode_feature_enabled():
        return None, "Claw-Code API disabled (set clawcode.enabled: true in core.yml)", 404
    sid = (session_id or "").strip()
    rec = get_session(sid)
    if not rec:
        return None, "session not found", 404
    if str(rec.get("owner_user_id") or "").strip() != (owner_user_id or "").strip():
        return None, "forbidden", 403
    root = str(rec.get("cwd") or "")
    abs_dir = resolve_path_under_session_cwd(root, relative)
    if abs_dir is None:
        return None, "invalid path", 400
    if not os.path.isdir(abs_dir):
        return None, "not a directory", 404
    try:
        names = sorted(os.listdir(abs_dir))
    except OSError as e:
        return None, str(e), 500
    out: List[Dict[str, Any]] = []
    cap = 400
    for name in names:
        if name in (".", "..") or name.startswith("."):
            continue
        if len(out) >= cap:
            break
        p = os.path.join(abs_dir, name)
        try:
            is_dir = os.path.isdir(p)
        except OSError:
            continue
        out.append({"name": name, "type": "directory" if is_dir else "file"})
    return out, None, 200


def record_clawcode_turn_finished(
    clawcode_session_id: Optional[str],
    prompt_request_id: Optional[str],
    request: Any = None,
) -> None:
    """After a completed Claw-Code turn (inbound or /process), refresh session file (last_run_id, last_usage, updated_at)."""
    sid = (clawcode_session_id or "").strip()
    if not sid or not clawcode_feature_enabled():
        return
    rid = (prompt_request_id or "").strip()
    try:
        from base.llm_usage_buffer import fallback_clawcode_usage_from_request, pop_clawcode_accumulated_usage

        merged = pop_clawcode_accumulated_usage(request)
        if merged is None:
            merged = fallback_clawcode_usage_from_request(request)
        else:
            md = getattr(request, "request_metadata", None)
            if isinstance(md, dict):
                md.pop("_clawcode_last_user_text", None)
                md.pop("_clawcode_last_assistant_text", None)
        kw: Dict[str, Any] = {"status": "idle", "last_run_error": ""}
        if rid:
            kw["last_run_id"] = rid
        if merged:
            kw["last_usage"] = merged
        touch_session(sid, **kw)
    except Exception:
        pass
