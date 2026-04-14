"""Claw-Code risky-tool approvals (file-backed, per approval id). See docs_design/ClawCode_Design.md P4."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from base.util import Util

from core.clawcode_store import clawcode_feature_enabled, get_session as _cc_get_session


def _cc_cfg() -> Dict[str, Any]:
    meta = Util().get_core_metadata()
    raw = getattr(meta, "clawcode", None)
    return raw if isinstance(raw, dict) else {}


def approval_tool_names() -> Set[str]:
    raw = _cc_cfg().get("approval_tools")
    if not isinstance(raw, list):
        return set()
    return {str(x).strip() for x in raw if x is not None and str(x).strip()}


def approval_ttl_seconds() -> int:
    try:
        t = int(_cc_cfg().get("approval_ttl_seconds") or 1800)
    except (TypeError, ValueError):
        t = 1800
    return max(60, min(86400 * 7, t))


def approvals_base_dir() -> Path:
    root = Util().root_path()
    return Path(root) / "database" / "clawcode_approvals"


def _approval_path(approval_id: str) -> Path:
    aid = (approval_id or "").strip()
    if not aid or "/" in aid or "\\" in aid or aid.startswith("."):
        raise ValueError("invalid approval id")
    return approvals_base_dir() / f"{aid}.json"


def get_approval(approval_id: str) -> Optional[Dict[str, Any]]:
    path = _approval_path(approval_id)
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_approval(rec: Dict[str, Any]) -> None:
    aid = (rec.get("approval_id") or "").strip()
    path = _approval_path(aid)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)


def list_pending_for_owner(owner_user_id: str) -> List[Dict[str, Any]]:
    owner = (owner_user_id or "").strip()
    if not owner:
        return []
    base = approvals_base_dir()
    if not base.is_dir():
        return []
    now = time.time()
    out: List[Dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            if str(data.get("owner_user_id") or "").strip() != owner:
                continue
            if str(data.get("status") or "") != "pending":
                continue
            exp = float(data.get("expires_at") or 0)
            if exp and now > exp:
                continue
            out.append(data)
        except Exception:
            continue
    out.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
    return out


def create_pending_approval(
    *,
    owner_user_id: str,
    friend_id: str,
    clawcode_session_id: str,
    chat_session_id: str,
    run_id: str,
    app_id: str,
    user_name: Optional[str],
    system_user_id: Optional[str],
    tool_name: str,
    arguments: Dict[str, Any],
    summary: str,
) -> str:
    aid = str(uuid.uuid4())
    now = time.time()
    ttl = approval_ttl_seconds()
    rec: Dict[str, Any] = {
        "approval_id": aid,
        "status": "pending",
        "owner_user_id": (owner_user_id or "").strip(),
        "friend_id": (friend_id or "").strip() or "HomeClaw",
        "clawcode_session_id": (clawcode_session_id or "").strip(),
        "chat_session_id": (chat_session_id or "").strip(),
        "run_id": (run_id or "").strip(),
        "app_id": (app_id or "").strip() or "homeclaw",
        "user_name": (user_name or "").strip() or None,
        "system_user_id": (system_user_id or "").strip() or None,
        "tool_name": (tool_name or "").strip(),
        "arguments": dict(arguments) if isinstance(arguments, dict) else {},
        "summary": (summary or "").strip() or None,
        "created_at": now,
        "expires_at": now + ttl,
        "resolved_at": None,
        "execute_error": None,
    }
    _write_approval(rec)
    return aid


def maybe_block_clawcode_tool(tool_name: str, arguments: Dict[str, Any], context: Any) -> Optional[str]:
    """
    If Claw-Code session is active and tool is in clawcode.approval_tools, persist a pending approval and return
    the tool result string (do not execute). Otherwise return None (caller runs the tool).
    """
    if not clawcode_feature_enabled():
        return None
    allow = approval_tool_names()
    if not allow:
        return None
    name = (tool_name or "").strip()
    if name not in allow:
        return None
    req = getattr(context, "request", None)
    md = getattr(req, "request_metadata", None) if req is not None else None
    if not isinstance(md, dict):
        return None
    csid = str(md.get("clawcode_session_id") or "").strip()
    if not csid:
        return None
    sess = _cc_get_session(csid)
    if not sess:
        return None
    owner = str(sess.get("owner_user_id") or "").strip()
    uid = str(getattr(context, "user_id", None) or "").strip()
    if not owner or owner != uid:
        return None
    summary = f"Claw-Code: approve tool `{name}` (session {csid[:8]}…)?"
    try:
        aid = create_pending_approval(
            owner_user_id=owner,
            friend_id=str(getattr(context, "friend_id", None) or "") or "HomeClaw",
            clawcode_session_id=csid,
            chat_session_id=str(getattr(context, "session_id", None) or ""),
            run_id=str(getattr(context, "run_id", None) or ""),
            app_id=str(getattr(context, "app_id", None) or "") or "homeclaw",
            user_name=getattr(context, "user_name", None),
            system_user_id=getattr(context, "system_user_id", None) or uid,
            tool_name=name,
            arguments=dict(arguments) if isinstance(arguments, dict) else {},
            summary=summary,
        )
    except Exception as e:
        logger.warning("clawcode approval create failed: {}", e)
        return f"Error: could not create approval record ({e!s})."
    try:
        from base.workflow_trace import emit_event

        emit_event(
            event_type="clawcode_approval_requested",
            component="clawcode",
            summary="tool execution blocked pending approval",
            details={
                "approval_id": aid,
                "clawcode_session_id": csid,
                "tool_name": name,
                "owner_user_id": owner,
            },
        )
    except Exception:
        pass
    try:
        from base.push_send import send_push_to_user

        _title = "Claw-Code approval needed"
        _body = f"Tool `{name}` — open Companion to approve or reject."
        _link = (
            "homeclaw://clawcode?"
            f"approval_id={quote(aid, safe='')}&clawcode_session_id={quote(csid, safe='')}"
        )
        _sent = send_push_to_user(
            owner,
            _title,
            _body,
            source="clawcode_approval",
            from_friend="HomeClaw",
            link=_link,
        )
        if _sent <= 0:
            logger.info(
                "Claw-Code approval {}: push reached 0 devices for user_id={} — enable push_notifications in core.yml and ensure Companion registered a token",
                (aid[:16] + "…") if len(aid) > 16 else aid,
                owner,
            )
        else:
            logger.debug("Claw-Code approval push: {} message(s) for user_id={}", _sent, owner)
    except Exception as _push_e:
        logger.debug("clawcode approval push skipped: {}", _push_e)
    return (
        f"This tool call requires approval for Claw-Code.\n"
        f"approval_id: {aid}\n"
        f"Approve via POST /api/clawcode/approvals/{aid}/resolve?owner_user_id=<your_user_id> "
        f'with JSON body {{"decision":"approve"}} or {{"decision":"reject"}} (same auth as /inbound).\n'
        f"Or use: python3 -m main clawcode approvals resolve --id {aid} --decision approve"
    )


def _mark_status(rec: Dict[str, Any], status: str, **extra: Any) -> None:
    out = dict(rec)
    out["status"] = status
    out["resolved_at"] = time.time()
    out.update(extra)
    _write_approval(out)


async def resolve_approval(
    core: Any,
    *,
    approval_id: str,
    owner_user_id: str,
    decision: str,
) -> Tuple[bool, str, Optional[str]]:
    """
    Approve or reject a pending Claw-Code tool approval. On approve, runs the tool with a ToolContext rebuilt
    from the stored record. Returns (ok, message, tool_result_or_none).
    """
    from base.tools import ToolContext, get_tool_registry
    from base.tool_permissions import tool_permission_context_from_meta

    oid = (owner_user_id or "").strip()
    aid = (approval_id or "").strip()
    dec = (decision or "").strip().lower()
    if not oid or not aid or dec not in ("approve", "reject"):
        return False, "invalid request", None
    rec = get_approval(aid)
    if not rec:
        return False, "approval not found", None
    if str(rec.get("owner_user_id") or "").strip() != oid:
        return False, "forbidden", None
    if str(rec.get("status") or "") != "pending":
        return False, "already resolved", None
    now = time.time()
    if float(rec.get("expires_at") or 0) and now > float(rec.get("expires_at") or 0):
        _mark_status(rec, "expired")
        try:
            from base.workflow_trace import emit_event

            emit_event(
                event_type="clawcode_approval_resolved",
                component="clawcode",
                summary="approval expired",
                details={"approval_id": aid, "decision": "expired"},
            )
        except Exception:
            pass
        return False, "approval expired", None
    if dec == "reject":
        _mark_status(rec, "rejected")
        try:
            from base.workflow_trace import emit_event

            emit_event(
                event_type="clawcode_approval_resolved",
                component="clawcode",
                summary="approval rejected",
                details={"approval_id": aid, "decision": "reject", "tool_name": rec.get("tool_name")},
            )
        except Exception:
            pass
        return True, "rejected", None
    allow = approval_tool_names()
    tname = str(rec.get("tool_name") or "").strip()
    if tname not in allow:
        _mark_status(rec, "failed", execute_error="tool not in approval_tools allowlist")
        return False, "tool no longer allowlisted for approval path", None
    args = rec.get("arguments")
    if not isinstance(args, dict):
        args = {}
    meta = Util().get_core_metadata()
    try:
        timeout_sec = max(0, int(getattr(meta, "tool_timeout_seconds", 120) or 0))
    except (TypeError, ValueError):
        timeout_sec = 120
    suid = str(rec.get("system_user_id") or rec.get("owner_user_id") or "").strip() or oid
    ctx = ToolContext(
        core=core,
        app_id=str(rec.get("app_id") or "homeclaw"),
        user_name=rec.get("user_name"),
        user_id=oid,
        system_user_id=suid,
        friend_id=str(rec.get("friend_id") or "HomeClaw"),
        session_id=str(rec.get("chat_session_id") or "") or None,
        run_id=str(rec.get("run_id") or "") or None,
        request=None,
        permission_context=tool_permission_context_from_meta(meta, None),
    )
    registry = get_tool_registry()
    if registry is None:
        _mark_status(rec, "failed", execute_error="no tool registry")
        return False, "tool registry unavailable", None
    try:
        if timeout_sec > 0:
            result = await asyncio.wait_for(registry.execute_async(tname, args, ctx), timeout=timeout_sec)
        else:
            result = await registry.execute_async(tname, args, ctx)
    except asyncio.TimeoutError:
        err = f"tool timed out after {timeout_sec}s"
        _mark_status(dict(rec), "failed", execute_error=err)
        try:
            from base.workflow_trace import emit_event

            emit_event(
                event_type="clawcode_approval_resolved",
                component="clawcode",
                summary="approval execute timed out",
                details={"approval_id": aid, "decision": "approve", "tool_name": tname, "error": err},
            )
        except Exception:
            pass
        return False, err, None
    except Exception as e:
        err = str(e)
        _r = dict(rec)
        _mark_status(_r, "failed", execute_error=err)
        try:
            from base.workflow_trace import emit_event

            emit_event(
                event_type="clawcode_approval_resolved",
                component="clawcode",
                summary="approval execute failed",
                details={"approval_id": aid, "decision": "approve", "tool_name": tname, "error": err[:500]},
            )
        except Exception:
            pass
        return False, f"execute failed: {err}", None
    res_str = result if isinstance(result, str) else (str(result) if result is not None else "")
    _r = dict(rec)
    _mark_status(_r, "executed", execute_error=None)
    try:
        from base.workflow_trace import emit_event

        emit_event(
            event_type="clawcode_approval_resolved",
            component="clawcode",
            summary="approval approved and tool executed",
            details={
                "approval_id": aid,
                "decision": "approve",
                "tool_name": tname,
                "result_preview": (res_str[:400] + "…") if len(res_str) > 400 else res_str,
            },
        )
    except Exception:
        pass
    return True, "executed", res_str
