"""Claw-Code session HTTP API. See docs_design/ClawCode_API_Sketch.md."""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from fastapi import Query
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from base.workflow_trace import emit_event
from core import clawcode_approvals, clawcode_channel_bindings, clawcode_store


class ClawcodeSessionCreateBody(BaseModel):
    owner_user_id: str = Field(..., min_length=1)
    cwd: str = Field(..., min_length=1)


class ClawcodeApprovalResolveBody(BaseModel):
    decision: Literal["approve", "reject"]


class ClawcodeChannelBindingPutBody(BaseModel):
    owner_user_id: str = Field(..., min_length=1)
    clawcode_session_id: str = Field(..., min_length=1)


class ClawcodeSessionPatchBody(BaseModel):
    """Operator metadata; cwd and owner are not patchable here (use POST …/rebind for cwd)."""

    git_remote_hint: Optional[str] = None
    main_llm_ref: Optional[str] = None
    tool_llm_ref: Optional[str] = None
    mode: Optional[Literal["plan", "agent"]] = None
    task_plan: Optional[List[Any]] = None
    checkpoint: Optional[str] = None
    resume_hint: Optional[str] = None
    last_run_error: Optional[str] = None


class ClawcodeMcpHealthBody(BaseModel):
    """Optional subset of server_ids to probe; empty = all configured servers."""

    server_ids: Optional[List[str]] = None


class ClawcodeSessionRebindBody(BaseModel):
    cwd: str = Field(..., min_length=1)


def _feature_disabled_response() -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "Claw-Code API disabled (set clawcode.enabled: true in core.yml)"})


def get_api_clawcode_sessions_post_handler(core: Any):
    async def handler(body: ClawcodeSessionCreateBody):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        try:
            rec = clawcode_store.create_session(
                owner_user_id=body.owner_user_id.strip(),
                cwd=body.cwd.strip(),
            )
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except PermissionError as e:
            return JSONResponse(status_code=403, content={"error": str(e)})
        except Exception as e:
            logger.exception("clawcode session create failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "session create failed"})
        try:
            emit_event(
                event_type="clawcode_session_started",
                component="clawcode",
                summary="session created",
                details={
                    "clawcode_session_id": rec.get("clawcode_session_id"),
                    "owner_user_id": rec.get("owner_user_id"),
                    "cwd": rec.get("cwd"),
                },
            )
        except Exception:
            pass
        return JSONResponse(status_code=201, content=rec)

    return handler


def get_api_clawcode_sessions_list_handler(core: Any):
    async def handler(owner_user_id: Optional[str] = Query(None)):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        oid = (owner_user_id or "").strip()
        if not oid:
            return JSONResponse(
                status_code=400,
                content={"error": "owner_user_id query parameter is required"},
            )
        sessions = clawcode_store.list_sessions_for_owner(oid)
        return JSONResponse(content={"sessions": sessions})

    return handler


def get_api_clawcode_session_files_handler(core: Any):
    async def handler(
        session_id: str,
        owner_user_id: str = Query(..., min_length=1),
        path: str = Query(""),
    ):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        entries, err, code = clawcode_store.list_workspace_files(
            session_id, owner_user_id, path
        )
        if err:
            return JSONResponse(status_code=code, content={"error": err, "entries": []})
        return JSONResponse(
            content={
                "entries": entries or [],
                "path": (path or "").strip().replace("\\", "/"),
            }
        )

    return handler


def get_api_clawcode_session_detail_handler(core: Any):
    async def handler(
        session_id: str,
        owner_user_id: str = Query(..., min_length=1),
    ):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        sid = (session_id or "").strip()
        rec = clawcode_store.get_session(sid)
        if not rec:
            return JSONResponse(status_code=404, content={"error": "session not found"})
        if str(rec.get("owner_user_id") or "").strip() != owner_user_id.strip():
            return JSONResponse(status_code=403, content={"error": "forbidden"})
        enriched = dict(rec)
        enriched["worktree_hint"] = clawcode_store.format_worktree_hint(
            str(rec.get("cwd") or "")
        )
        enriched["usage_hint"] = clawcode_store.clawcode_usage_hint()
        return JSONResponse(content=enriched)

    return handler


def get_api_clawcode_session_patch_handler(core: Any):
    async def handler(
        session_id: str,
        body: ClawcodeSessionPatchBody,
        owner_user_id: str = Query(..., min_length=1),
    ):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        patch = body.model_dump(exclude_unset=True)
        rec, err, code = clawcode_store.patch_clawcode_session_metadata(
            session_id.strip(),
            owner_user_id.strip(),
            patch,
        )
        if err:
            return JSONResponse(status_code=code, content={"error": err})
        enriched = dict(rec) if isinstance(rec, dict) else {}
        enriched["worktree_hint"] = clawcode_store.format_worktree_hint(
            str((rec or {}).get("cwd") or "")
        )
        enriched["usage_hint"] = clawcode_store.clawcode_usage_hint()
        try:
            emit_event(
                event_type="clawcode_session_patched",
                component="clawcode",
                summary="session metadata updated",
                details={
                    "clawcode_session_id": (rec or {}).get("clawcode_session_id"),
                    "owner_user_id": owner_user_id.strip(),
                    "keys": list(patch.keys()),
                },
            )
        except Exception:
            pass
        return JSONResponse(content=enriched)

    return handler


def get_api_clawcode_session_rebind_handler(core: Any):
    async def handler(
        session_id: str,
        body: ClawcodeSessionRebindBody,
        owner_user_id: str = Query(..., min_length=1),
    ):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        rec, err, code = clawcode_store.rebind_session_cwd(
            session_id.strip(),
            owner_user_id.strip(),
            body.cwd.strip(),
        )
        if err:
            return JSONResponse(status_code=code, content={"error": err})
        enriched = dict(rec) if isinstance(rec, dict) else {}
        enriched["worktree_hint"] = clawcode_store.format_worktree_hint(
            str((rec or {}).get("cwd") or "")
        )
        enriched["usage_hint"] = clawcode_store.clawcode_usage_hint()
        try:
            emit_event(
                event_type="clawcode_session_patched",
                component="clawcode",
                summary="session cwd rebound",
                details={
                    "clawcode_session_id": (rec or {}).get("clawcode_session_id"),
                    "owner_user_id": owner_user_id.strip(),
                    "keys": ["cwd"],
                },
            )
        except Exception:
            pass
        return JSONResponse(content=enriched)

    return handler


def get_api_clawcode_approvals_list_handler(core: Any):
    async def handler(owner_user_id: Optional[str] = Query(None)):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        oid = (owner_user_id or "").strip()
        if not oid:
            return JSONResponse(
                status_code=400,
                content={"error": "owner_user_id query parameter is required"},
            )
        raw = clawcode_approvals.list_pending_for_owner(oid)
        rows = [
            {
                "approval_id": r.get("approval_id"),
                "status": r.get("status"),
                "tool_name": r.get("tool_name"),
                "summary": r.get("summary"),
                "clawcode_session_id": r.get("clawcode_session_id"),
                "created_at": r.get("created_at"),
                "expires_at": r.get("expires_at"),
            }
            for r in raw
        ]
        return JSONResponse(content={"approvals": rows})

    return handler


def get_api_clawcode_approvals_resolve_handler(core: Any):
    async def handler(
        approval_id: str,
        body: ClawcodeApprovalResolveBody,
        owner_user_id: str = Query(..., min_length=1),
    ):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        try:
            ok, msg, tool_result = await clawcode_approvals.resolve_approval(
                core,
                approval_id=approval_id.strip(),
                owner_user_id=owner_user_id.strip(),
                decision=body.decision,
            )
        except Exception as e:
            logger.exception("clawcode approval resolve failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "resolve failed"})
        code = 200 if ok else 400
        if ok and body.decision == "approve" and tool_result is not None:
            return JSONResponse(
                status_code=code,
                content={"status": msg, "tool_result": tool_result},
            )
        return JSONResponse(status_code=code, content={"status": msg, "ok": ok})

    return handler


def get_api_clawcode_channel_bindings_get_handler(core: Any):
    async def handler(owner_user_id: str = Query(..., min_length=1)):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        sid = clawcode_channel_bindings.get_binding(owner_user_id.strip())
        return JSONResponse(content={"clawcode_session_id": sid})

    return handler


def get_api_clawcode_channel_bindings_put_handler(core: Any):
    async def handler(body: ClawcodeChannelBindingPutBody):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        oid = body.owner_user_id.strip()
        sid = body.clawcode_session_id.strip()
        rec = clawcode_store.get_session(sid)
        if not rec:
            return JSONResponse(status_code=404, content={"error": "Unknown clawcode_session_id"})
        if str(rec.get("owner_user_id") or "").strip() != oid:
            return JSONResponse(
                status_code=403,
                content={"error": "Session owner_user_id must match binding owner_user_id"},
            )
        clawcode_channel_bindings.set_binding(oid, sid)
        return JSONResponse(content={"ok": True, "owner_user_id": oid, "clawcode_session_id": sid})

    return handler


def get_api_clawcode_channel_bindings_delete_handler(core: Any):
    async def handler(owner_user_id: str = Query(..., min_length=1)):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        clawcode_channel_bindings.clear_binding(owner_user_id.strip())
        return JSONResponse(content={"ok": True})

    return handler


def get_api_clawcode_mcp_servers_handler(core: Any):
    """Milestone C: list configured MCP servers (sanitized metadata)."""

    async def handler():
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        from core.clawcode_mcp_diagnostics import list_mcp_servers_sanitized

        return JSONResponse(content=list_mcp_servers_sanitized())

    return handler


def get_api_clawcode_mcp_health_handler(core: Any):
    """Milestone C: probe list_tools per MCP server (may spawn subprocesses)."""

    async def handler(body: Optional[ClawcodeMcpHealthBody] = None):
        if not clawcode_store.clawcode_feature_enabled():
            return _feature_disabled_response()
        from core.clawcode_mcp_diagnostics import probe_mcp_servers_health

        b = body or ClawcodeMcpHealthBody()
        ids = b.server_ids if b.server_ids else None
        out = await probe_mcp_servers_health(ids)
        return JSONResponse(content=out)

    return handler
