"""Claw-Code Milestone C: list configured MCP servers (sanitized) and optional health probes."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tools.builtin import _get_tools_config, _mcp_run_with_session


def list_mcp_servers_sanitized() -> Dict[str, Any]:
    """
    Return server ids and non-secret metadata from merged tools.mcp.servers.
    """
    try:
        cfg = _get_tools_config()
    except Exception:
        cfg = {}
    mcp = cfg.get("mcp") if isinstance(cfg, dict) else None
    if not isinstance(mcp, dict):
        return {"servers": [], "mcp_enabled": False}
    servers = mcp.get("servers")
    if not isinstance(servers, dict):
        return {"servers": [], "mcp_enabled": True}
    out: List[Dict[str, Any]] = []
    for sid, sc in servers.items():
        if not isinstance(sc, dict):
            continue
        sid_s = str(sid).strip()
        if not sid_s:
            continue
        transport = str(sc.get("transport") or "stdio").strip().lower()
        cmd = sc.get("command")
        args = sc.get("args")
        url = (sc.get("url") or "").strip()
        args_preview = ""
        if isinstance(args, list):
            args_preview = " ".join(str(a) for a in args[:16])[:400]
        out.append(
            {
                "server_id": sid_s,
                "transport": transport,
                "command": (str(cmd) if cmd is not None else "")[:200],
                "args_preview": args_preview,
                "has_url": bool(url),
            }
        )
    out.sort(key=lambda x: x["server_id"])
    return {"servers": out, "mcp_enabled": True}


async def probe_mcp_server_health(server_id: str) -> Dict[str, Any]:
    """
    Run list_tools on one server; return ok + tool_count or error string.
    """

    async def _list(session: Any) -> int:
        result = await session.list_tools()
        tools = getattr(result, "tools", None) or []
        return len(tools) if isinstance(tools, list) else 0

    out = await _mcp_run_with_session(server_id, _list)
    if isinstance(out, str):
        try:
            obj = json.loads(out)
            err = obj.get("error") or out
            return {"server_id": server_id, "ok": False, "error": str(err)[:800]}
        except Exception:
            return {"server_id": server_id, "ok": False, "error": out[:800]}
    try:
        n = int(out)
    except (TypeError, ValueError):
        n = 0
    return {"server_id": server_id, "ok": True, "tool_count": n}


async def probe_mcp_servers_health(server_ids: Optional[List[str]], *, cap: int = 20) -> Dict[str, Any]:
    """
    Probe each server_id (or all configured if None / empty).
    """
    summary = list_mcp_servers_sanitized()
    all_ids = [s["server_id"] for s in summary.get("servers") or []]
    if server_ids:
        want = {str(x).strip() for x in server_ids if str(x).strip()}
        ids = [i for i in all_ids if i in want][:cap]
    else:
        ids = all_ids[:cap]
    results: List[Dict[str, Any]] = []
    for sid in ids:
        results.append(await probe_mcp_server_health(sid))
    return {"results": results, "probed": len(results)}
