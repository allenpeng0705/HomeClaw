"""
Misc API routes: skills clear-vector-store, skills list/search/install (Companion->Core), testing clear-all, sessions list, reports usage.
"""
from pathlib import Path

from fastapi import Depends
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger

from base.util import Util
from base.base import PromptRequest, ChannelType, ContentType
from core.routes import companion_auth


def get_api_cursor_bridge_status_handler(core):
    """GET /api/cursor-bridge/status — returns Dev Bridge active project cwd (if any).
    Query param: backend=cursor|claude (default cursor). Companion->Core direct.
    """
    async def api_cursor_bridge_status(
        request: Request,
        token_user=Depends(companion_auth.get_companion_token_user),  # noqa: ARG001
    ):
        try:
            pm = getattr(core, "plugin_manager", None)
            if pm is None:
                return JSONResponse(status_code=500, content={"detail": "Plugin manager not available"})
            backend = (request.query_params.get("backend") or "").strip().lower()
            if backend not in ("cursor", "claude", "trae"):
                backend = "cursor"
            plugin_id = "trae-bridge" if backend == "trae" else ("claude-code-bridge" if backend == "claude" else "cursor-bridge")
            plug = pm.get_plugin_by_id(plugin_id)
            if plug is None or not isinstance(plug, dict):
                return JSONResponse(status_code=404, content={"detail": f"{plugin_id} plugin not found"})
            # Build a minimal PromptRequest to run external plugin capability get_status.
            req = PromptRequest(
                request_id="cursor-bridge-status",
                channel_name="companion",
                request_metadata={"capability_id": "get_status", "capability_parameters": {"backend": backend}},
                channelType=ChannelType.IM,
                user_name="companion",
                app_id="homeclaw",
                user_id="companion",
                contentType=ContentType.TEXT,
                text="",
                action="respond",
                host="api",
                port=0,
                images=[],
                videos=[],
                audios=[],
                files=None,
                timestamp=0.0,
            )
            result = await pm.run_external_plugin(plug, req)
            if not getattr(result, "success", False):
                return JSONResponse(status_code=502, content={"detail": getattr(result, "error", "") or "cursor-bridge status failed"})
            text = (getattr(result, "text", "") or "").strip()
            try:
                import json as _json
                obj = _json.loads(text) if text else {}
            except Exception:
                obj = {}
            active = (obj.get("active_cwd") or "").strip() if isinstance(obj, dict) else ""
            return JSONResponse(content={"active_cwd": active})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_cursor_bridge_status


def _parse_bridge_session_id(session_id: str):
    """If session_id is 'bridge:plugin_id:bridge_sess_id', return (plugin_id, bridge_sess_id). Else return (None, None)."""
    if not session_id or not session_id.startswith("bridge:"):
        return None, None
    parts = session_id.split(":", 2)
    if len(parts) < 3:
        return None, None
    return parts[1], parts[2]


def get_api_interactive_start_handler(core):
    """POST /api/interactive/start — start an interactive session for a user (Companion->Core).
    Body: command + cwd (local PTY), or bridge_plugin (cursor-bridge | claude-code-bridge | trae-bridge) to start agent interactively on the bridge.
    """

    async def api_interactive_start(request: Request, token_user=Depends(companion_auth.get_companion_token_user)):  # noqa: ARG001
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        bridge_plugin = (body.get("bridge_plugin") or "").strip()
        if bridge_plugin:
            # Start interactive agent on the bridge; Core calls bridge and returns composite session_id.
            if bridge_plugin not in ("cursor-bridge", "claude-code-bridge", "trae-bridge"):
                return JSONResponse(status_code=400, content={"detail": "bridge_plugin must be cursor-bridge, claude-code-bridge, or trae-bridge"})
            pm = getattr(core, "plugin_manager", None)
            if pm is None:
                return JSONResponse(status_code=500, content={"detail": "Plugin manager not available"})
            plug = pm.get_plugin_by_id(bridge_plugin)
            if plug is None or not isinstance(plug, dict):
                return JSONResponse(status_code=404, content={"detail": f"Plugin {bridge_plugin} not found"})
            backend = "trae" if "trae" in bridge_plugin.lower() else ("claude" if "claude" in bridge_plugin.lower() else "cursor")
            req = PromptRequest(
                request_id="interactive-start",
                channel_name="companion",
                request_metadata={
                    "capability_id": "run_agent_interactive",
                    "capability_parameters": {"backend": backend, "cwd": (body.get("cwd") or "").strip() or None},
                },
                channelType=ChannelType.IM,
                user_name="companion",
                app_id="homeclaw",
                user_id="companion",
                contentType=ContentType.TEXT,
                text="",
                action="respond",
                host="api",
                port=0,
                images=[],
                videos=[],
                audios=[],
                files=None,
                timestamp=0.0,
            )
            try:
                result = await pm.run_external_plugin(plug, req)
            except Exception as e:
                return JSONResponse(status_code=502, content={"detail": str(e)})
            if not getattr(result, "success", False):
                return JSONResponse(
                    status_code=502,
                    content={"detail": (getattr(result, "error", "") or "Bridge run_agent_interactive failed").strip()},
                )
            text = (getattr(result, "text", "") or "").strip()
            try:
                import json as _json
                obj = _json.loads(text) if text else {}
            except Exception:
                return JSONResponse(status_code=502, content={"detail": "Bridge returned invalid JSON"})
            bridge_sess = (obj.get("session_id") or "").strip()
            initial = obj.get("initial_output") or ""
            if not bridge_sess:
                return JSONResponse(status_code=502, content={"detail": "Bridge did not return session_id"})
            composite_id = f"bridge:{bridge_plugin}:{bridge_sess}"
            return JSONResponse(
                content={"session_id": composite_id, "status": "running", "initial_output": initial},
            )
        # Local PTY session
        cmd = (body.get("command") or "").strip()
        cwd = (body.get("cwd") or "").strip() or None
        if not cmd:
            return JSONResponse(status_code=400, content={"detail": "command is required"})
        try:
            from core.interactive_sessions import InteractiveSessionManager, get_interactive_config  # type: ignore
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": f"Interactive sessions unavailable: {e!s}"})
        mgr = getattr(core, "interactive_sessions", None)  # type: ignore[attr-defined]
        if mgr is None:
            cfg = get_interactive_config()
            mgr = InteractiveSessionManager(
                max_sessions_per_user=cfg["max_sessions_per_user"],
                idle_ttl_sec=cfg["idle_ttl_sec"],
                max_buffer_chars=cfg["max_buffer_chars"],
            )
            setattr(core, "interactive_sessions", mgr)
        user_id = str(getattr(token_user, "id", None) or getattr(token_user, "name", "") or "companion")
        try:
            session_id, initial = await mgr.start_session(user_id, None, cmd, cwd=cwd)
            return JSONResponse(content={"session_id": session_id, "status": "running", "initial_output": initial})
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": str(e)})

    return api_interactive_start


def get_api_interactive_read_handler(core):
    """GET /api/interactive/read?session_id=...&from_seq=... — read output from interactive session. Supports bridge session_id (bridge:plugin_id:bridge_sess_id)."""

    async def api_interactive_read(
        request: Request,
        token_user=Depends(companion_auth.get_companion_token_user),  # noqa: ARG001
    ):
        q = request.query_params
        session_id = (q.get("session_id") or "").strip()
        if not session_id:
            return JSONResponse(status_code=400, content={"detail": "session_id is required"})
        try:
            from_seq = int(q.get("from_seq") or "1")
        except ValueError:
            from_seq = 1
        plugin_id, bridge_sess_id = _parse_bridge_session_id(session_id)
        if plugin_id and bridge_sess_id:
            pm = getattr(core, "plugin_manager", None)
            if pm is None:
                return JSONResponse(status_code=500, content={"detail": "Plugin manager not available"})
            plug = pm.get_plugin_by_id(plugin_id)
            if plug is None or not isinstance(plug, dict):
                return JSONResponse(status_code=404, content={"detail": f"Plugin {plugin_id} not found"})
            req = PromptRequest(
                request_id="interactive-read",
                channel_name="companion",
                request_metadata={
                    "capability_id": "interactive_read",
                    "capability_parameters": {"session_id": bridge_sess_id, "from_seq": from_seq},
                },
                channelType=ChannelType.IM,
                user_name="companion",
                app_id="homeclaw",
                user_id="companion",
                contentType=ContentType.TEXT,
                text="",
                action="respond",
                host="api",
                port=0,
                images=[],
                videos=[],
                audios=[],
                files=None,
                timestamp=0.0,
            )
            try:
                result = await pm.run_external_plugin(plug, req)
            except Exception as e:
                return JSONResponse(status_code=502, content={"detail": str(e)})
            if not getattr(result, "success", False):
                return JSONResponse(status_code=502, content={"detail": (getattr(result, "error", "") or "Bridge interactive_read failed").strip()})
            try:
                import json as _json
                data = _json.loads((getattr(result, "text", "") or "").strip())
            except Exception:
                return JSONResponse(status_code=502, content={"detail": "Bridge returned invalid JSON"})
            data["session_id"] = session_id
            return JSONResponse(content=data)
        try:
            from core.interactive_sessions import InteractiveSessionManager  # type: ignore
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": f"Interactive sessions unavailable: {e!s}"})
        mgr = getattr(core, "interactive_sessions", None)  # type: ignore[attr-defined]
        if mgr is None:
            return JSONResponse(status_code=404, content={"detail": "No interactive sessions"})
        try:
            chunks, status, exit_code, command = await mgr.read(session_id, from_seq=from_seq)
            return JSONResponse(
                content={
                    "session_id": session_id,
                    "status": status,
                    "exit_code": exit_code,
                    "command": command,
                    "chunks": [{"seq": c.seq, "text": c.text, "timestamp": c.timestamp} for c in chunks],
                }
            )
        except KeyError:
            return JSONResponse(status_code=404, content={"detail": "Unknown session_id"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": str(e)})

    return api_interactive_read


def get_api_interactive_write_handler(core):
    """POST /api/interactive/write — write input to interactive session. Supports bridge session_id."""

    async def api_interactive_write(request: Request, token_user=Depends(companion_auth.get_companion_token_user)):  # noqa: ARG001
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        session_id = (body.get("session_id") or "").strip()
        data = (body.get("data") or "").replace("\r\n", "\n")
        if not session_id:
            return JSONResponse(status_code=400, content={"detail": "session_id is required"})
        plugin_id, bridge_sess_id = _parse_bridge_session_id(session_id)
        if plugin_id and bridge_sess_id:
            pm = getattr(core, "plugin_manager", None)
            if pm is None:
                return JSONResponse(status_code=500, content={"detail": "Plugin manager not available"})
            plug = pm.get_plugin_by_id(plugin_id)
            if plug is None or not isinstance(plug, dict):
                return JSONResponse(status_code=404, content={"detail": f"Plugin {plugin_id} not found"})
            req = PromptRequest(
                request_id="interactive-write",
                channel_name="companion",
                request_metadata={
                    "capability_id": "interactive_write",
                    "capability_parameters": {"session_id": bridge_sess_id, "data": data},
                },
                channelType=ChannelType.IM,
                user_name="companion",
                app_id="homeclaw",
                user_id="companion",
                contentType=ContentType.TEXT,
                text="",
                action="respond",
                host="api",
                port=0,
                images=[],
                videos=[],
                audios=[],
                files=None,
                timestamp=0.0,
            )
            try:
                result = await pm.run_external_plugin(plug, req)
            except Exception as e:
                return JSONResponse(status_code=502, content={"detail": str(e)})
            if not getattr(result, "success", False):
                return JSONResponse(status_code=502, content={"detail": (getattr(result, "error", "") or "Bridge interactive_write failed").strip()})
            return JSONResponse(content={"ok": True})
        try:
            from core.interactive_sessions import InteractiveSessionManager  # type: ignore
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": f"Interactive sessions unavailable: {e!s}"})
        mgr = getattr(core, "interactive_sessions", None)  # type: ignore[attr-defined]
        if mgr is None:
            return JSONResponse(status_code=404, content={"detail": "No interactive sessions"})
        try:
            await mgr.write(session_id, data)
            return JSONResponse(content={"ok": True})
        except KeyError:
            return JSONResponse(status_code=404, content={"detail": "Unknown session_id"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": str(e)})

    return api_interactive_write


def get_api_interactive_stop_handler(core):
    """POST /api/interactive/stop — stop interactive session. Supports bridge session_id."""

    async def api_interactive_stop(request: Request, token_user=Depends(companion_auth.get_companion_token_user)):  # noqa: ARG001
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        session_id = (body.get("session_id") or "").strip()
        if not session_id:
            return JSONResponse(status_code=400, content={"detail": "session_id is required"})
        plugin_id, bridge_sess_id = _parse_bridge_session_id(session_id)
        if plugin_id and bridge_sess_id:
            pm = getattr(core, "plugin_manager", None)
            if pm is None:
                return JSONResponse(status_code=500, content={"detail": "Plugin manager not available"})
            plug = pm.get_plugin_by_id(plugin_id)
            if plug is None or not isinstance(plug, dict):
                return JSONResponse(status_code=404, content={"detail": f"Plugin {plugin_id} not found"})
            req = PromptRequest(
                request_id="interactive-stop",
                channel_name="companion",
                request_metadata={
                    "capability_id": "interactive_stop",
                    "capability_parameters": {"session_id": bridge_sess_id},
                },
                channelType=ChannelType.IM,
                user_name="companion",
                app_id="homeclaw",
                user_id="companion",
                contentType=ContentType.TEXT,
                text="",
                action="respond",
                host="api",
                port=0,
                images=[],
                videos=[],
                audios=[],
                files=None,
                timestamp=0.0,
            )
            try:
                result = await pm.run_external_plugin(plug, req)
            except Exception as e:
                return JSONResponse(status_code=502, content={"detail": str(e)})
            if not getattr(result, "success", False):
                return JSONResponse(status_code=502, content={"detail": (getattr(result, "error", "") or "Bridge interactive_stop failed").strip()})
            return JSONResponse(content={"ok": True})
        try:
            from core.interactive_sessions import InteractiveSessionManager  # type: ignore
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": f"Interactive sessions unavailable: {e!s}"})
        mgr = getattr(core, "interactive_sessions", None)  # type: ignore[attr-defined]
        if mgr is None:
            return JSONResponse(status_code=404, content={"detail": "No interactive sessions"})
        try:
            await mgr.stop(session_id)
            return JSONResponse(content={"ok": True})
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": str(e)})

    return api_interactive_stop


def _install_failure_detail(out: dict) -> str:
    """Build a short, readable error message for skill install failure (no raw JSON/stderr dump). Never raises."""
    try:
        err = str(out.get("error") or "").strip()
        if err:
            msg = err[:600]
        else:
            convert = out.get("convert") or {}
            install = out.get("install") or {}
            err = str(convert.get("error") or "").strip()
            if err:
                msg = err[:600]
            else:
                err = str(install.get("error") or "").strip()
                if err and not (err.startswith("Command failed (") and "): " not in err):
                    msg = err[:600]
                else:
                    stderr = str(install.get("stderr") or "").strip()
                    if stderr:
                        lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
                        msg = "Install or conversion failed. Check Core logs for details."
                        for ln in lines:
                            ln_lower = ln.lower()
                            if "experimental" in ln_lower or "deprecat" in ln_lower or "warning" in ln_lower:
                                continue
                            if len(ln) > 10:
                                msg = ln[:600]
                                break
                        else:
                            msg = (lines[0] if lines else stderr[:400])[:600]
                    else:
                        msg = err[:600] if err else "Install or conversion failed. Check Core logs for details."
        hint = str((out.get("install") or {}).get("hint") or "").strip()
        if hint and hint not in msg:
            msg = f"{msg}. {hint}"[:700]
        return msg
    except Exception:
        return "Install or conversion failed. Check Core logs for details."


def get_api_skills_clear_vector_store_handler(core):
    """Return handler for POST /api/skills/clear-vector-store."""
    async def api_skills_clear_vector_store():
        try:
            vs = getattr(core, "skills_vector_store", None)
            if not vs:
                return JSONResponse(content={"cleared": 0, "message": "Skills vector store not enabled"})
            list_ids_fn = getattr(vs, "list_ids", None)
            if not list_ids_fn:
                return JSONResponse(content={"cleared": 0, "message": "Vector store has no list_ids"})
            ids = list_ids_fn(limit=10000)
            if ids:
                delete_ids_fn = getattr(vs, "delete_ids", None)
                if delete_ids_fn:
                    delete_ids_fn(ids)
                else:
                    for vid in ids:
                        try:
                            vs.delete(vid)
                        except Exception:
                            pass
            return JSONResponse(content={"cleared": len(ids)})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_skills_clear_vector_store


def _core_skills_list(core) -> list:
    """Load all skills from skills_dir, external_skills_dir, skills_extra_dirs. Returns list of dicts. Never raises; returns [] on error."""
    try:
        from base.skills import get_all_skills_dirs, load_skills_from_dirs
        meta = Util().get_core_metadata()
        root = Path(Util().root_path())
        skills_dir = (getattr(meta, "skills_dir", None) or "skills").strip() or "skills"
        ext_dir = (getattr(meta, "external_skills_dir", None) or "").strip()
        extra_dirs = getattr(meta, "skills_extra_dirs", None) or []
        if not isinstance(extra_dirs, list):
            extra_dirs = []
        disabled = getattr(meta, "skills_disabled", None) or []
        if not isinstance(disabled, list):
            disabled = []
        dirs = get_all_skills_dirs(skills_dir, ext_dir, extra_dirs, root)
        skills = load_skills_from_dirs(dirs, disabled_folders=disabled, include_body=False)
        out = []
        for s in skills:
            if not isinstance(s, dict):
                continue
            desc = s.get("description")
            desc_str = (desc if isinstance(desc, str) else str(desc or ""))[:500]
            out.append({
                "folder": s.get("folder") or "",
                "name": s.get("name") or s.get("folder") or "",
                "description": desc_str,
                "path": s.get("path") or "",
            })
        return out
    except Exception as e:
        logger.debug("Core skills list failed: %s", e)
        return []


def get_api_skills_list_handler(core):  # noqa: ARG001
    """Return handler for GET /api/skills/list. Companion->Core direct; returns { skills: [...] }."""
    async def api_skills_list():
        try:
            skills = _core_skills_list(core)
            return JSONResponse(content={"skills": skills})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_skills_list


def get_api_skills_search_handler(core):  # noqa: ARG001
    """Return handler for GET /api/skills/search?query=... . Companion->Core direct; uses clawhub CLI."""
    async def api_skills_search(request: Request):
        try:
            from base.clawhub_integration import clawhub_available, clawhub_ensure_logged_in, clawhub_search
            q = (request.query_params.get("query") or "").strip()
            if not q:
                return JSONResponse(content={"results": []})
            if not clawhub_available():
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": (
                            "clawhub not found on PATH. Install the ClawHub CLI (e.g. npm i -g clawhub), "
                            "then restart Core from a terminal/session where 'clawhub' is on PATH."
                        )
                    },
                )
            meta = Util().get_core_metadata()
            token = (getattr(meta, "clawhub_token", None) or "").strip() if meta else ""
            clawhub_ensure_logged_in(token)
            results, raw = clawhub_search(q, limit=20)
            if not raw.ok and raw.error:
                return JSONResponse(status_code=502, content={"detail": raw.error, "stderr": (raw.stderr or "")[-1000:]})
            return JSONResponse(content={"results": results})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_skills_search


def get_api_skills_install_handler(core):  # noqa: ARG001
    """Return handler for POST /api/skills/install. Companion->Core direct; body { id, version?, dry_run?, with_deps? }."""
    async def api_skills_install(request: Request):
        try:
            from base.clawhub_integration import clawhub_available, clawhub_install_and_convert
            if not clawhub_available():
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": (
                            "clawhub not found on PATH. Install the ClawHub CLI (e.g. npm i -g clawhub), "
                            "then restart Core from a terminal/session where 'clawhub' is on PATH."
                        )
                    },
                )
            try:
                body = await request.json() if request.headers.get("content-type", "").strip().startswith("application/json") else {}
            except Exception:
                body = {}
            if not isinstance(body, dict):
                body = {}
            skill_id = (body.get("id") or body.get("skill") or "").strip()
            version = (body.get("version") or "").strip()
            dry_run = bool(body.get("dry_run", False))
            with_deps = bool(body.get("with_deps", False))
            if not skill_id:
                return JSONResponse(status_code=400, content={"detail": "Missing skill id"})
            spec = f"{skill_id}@{version}" if version else skill_id
            meta = Util().get_core_metadata()
            from base.clawhub_integration import clawhub_ensure_logged_in
            token = (getattr(meta, "clawhub_token", None) or "").strip() if meta else ""
            clawhub_ensure_logged_in(token)
            root = Path(Util().root_path())
            ext_dir = (getattr(meta, "external_skills_dir", None) or "external_skills").strip() or "external_skills"
            download_dir = (getattr(meta, "clawhub_download_dir", None) or "downloads").strip() or "downloads"
            out = clawhub_install_and_convert(
                skill_spec=spec,
                skill_id_hint=skill_id,
                homeclaw_root=root,
                external_skills_dir=ext_dir,
                clawhub_download_dir=download_dir,
                dry_run=dry_run,
                with_deps=with_deps,
            )
            status = 200 if out.get("ok") else (502 if (out.get("install") or {}).get("ok") else 500)
            if not out.get("ok"):
                detail = _install_failure_detail(out)
                out = dict(out)
                out["detail"] = detail
            return JSONResponse(status_code=status, content=out)
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_skills_install


def get_api_skills_clawhub_login_status_handler(core):  # noqa: ARG001
    """GET /api/skills/clawhub-login-status — whether ClawHub CLI is logged in (whoami). Uses clawhub_token from config if set."""
    async def api_skills_clawhub_login_status(request: Request):
        try:
            from base.clawhub_integration import clawhub_available, clawhub_ensure_logged_in
            if not clawhub_available():
                return JSONResponse(
                    status_code=200,
                    content={"logged_in": False, "message": "clawhub not found on PATH", "clawhub_available": False},
                )
            meta = Util().get_core_metadata()
            token = (getattr(meta, "clawhub_token", None) or "").strip() if meta else ""
            logged_in, message = clawhub_ensure_logged_in(token)
            return JSONResponse(
                content={"logged_in": logged_in, "message": message, "clawhub_available": True},
            )
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e), "logged_in": False})
    return api_skills_clawhub_login_status


def get_api_skills_clawhub_login_handler(core):  # noqa: ARG001
    """POST /api/skills/clawhub-login — start ClawHub login (browser or token). Body: {} or { \"token\": \"...\" }. Companion->Core."""
    async def api_skills_clawhub_login(request: Request):
        try:
            from base.clawhub_integration import clawhub_available, clawhub_login_start, clawhub_login_with_token
            if not clawhub_available():
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "clawhub not found on PATH. Install the ClawHub CLI (e.g. npm i -g clawhub), then restart Core.",
                        "url": None,
                        "ok": False,
                    },
                )
            body = {}
            try:
                if (request.headers.get("content-type") or "").strip().lower().startswith("application/json"):
                    body = await request.json() or {}
            except Exception:
                pass
            if not isinstance(body, dict):
                body = {}
            token = (str(body.get("token") or "")).strip()
            if token:
                out = clawhub_login_with_token(token)
            else:
                out = clawhub_login_start(wait_for_url_s=15)
            status = 200 if out.get("ok") else 400
            return JSONResponse(
                status_code=status,
                content={
                    "ok": out.get("ok", False),
                    "url": out.get("url"),
                    "message": out.get("message", ""),
                    "stdout": (out.get("stdout") or "")[-2000:],
                    "stderr": (out.get("stderr") or "")[-2000:],
                },
            )
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e), "ok": False, "url": None})
    return api_skills_clawhub_login


def get_api_skills_remove_handler(core):  # noqa: ARG001
    """Return handler for POST /api/skills/remove. Companion->Core direct; body { folder: "skill-folder-name" }. Only removes from external_skills_dir."""
    async def api_skills_remove(request: Request):
        try:
            from base.skills import get_all_skills_dirs, remove_skill_folder
            try:
                body = await request.json() if request.headers.get("content-type", "").strip().startswith("application/json") else {}
            except Exception:
                body = {}
            if not isinstance(body, dict):
                body = {}
            folder = (body.get("folder") or body.get("name") or "").strip()
            if not folder:
                return JSONResponse(status_code=400, content={"detail": "Missing folder name", "ok": False, "removed": False})
            meta = Util().get_core_metadata()
            root = Path(Util().root_path())
            skills_dir = (getattr(meta, "skills_dir", None) or "skills").strip() or "skills"
            ext_dir = (getattr(meta, "external_skills_dir", None) or "external_skills").strip()
            extra_dirs = getattr(meta, "skills_extra_dirs", None) or []
            if not isinstance(extra_dirs, list):
                extra_dirs = []
            out = remove_skill_folder(folder, root, skills_dir, ext_dir, extra_dirs)
            err = (out.get("error") or "").strip()
            if out.get("removed"):
                return JSONResponse(content=out)
            if "built-in" in err.lower() or "not configured" in err.lower():
                return JSONResponse(status_code=403, content={"detail": err, **out})
            if "not found" in err.lower():
                return JSONResponse(status_code=404, content={"detail": err, **out})
            return JSONResponse(status_code=400, content={"detail": err or "Remove failed", **out})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e), "ok": False, "removed": False})
    return api_skills_remove


def get_api_skills_sync_vector_store_handler(core):
    """Return handler for POST /api/skills/sync-vector-store."""
    async def api_skills_sync_vector_store():
        try:
            meta = None
            try:
                meta = Util().get_core_metadata()
            except Exception:
                meta = None
            if not meta or not getattr(meta, "skills_use_vector_search", False):
                return JSONResponse(content={"synced": 0, "message": "skills_use_vector_search is disabled"})

            vs = getattr(core, "skills_vector_store", None)
            embedder = getattr(core, "embedder", None)
            if not vs or not embedder:
                return JSONResponse(content={"synced": 0, "message": "Skills vector store not enabled"})

            from base.skills import get_all_skills_dirs, get_skills_dir, sync_skills_to_vector_store
            root = Path(Util().root_path()).resolve()
            all_dirs = get_all_skills_dirs(
                getattr(meta, "skills_dir", None) or "skills",
                (getattr(meta, "external_skills_dir", None) or "").strip(),
                getattr(meta, "skills_extra_dirs", None) or [],
                root,
            )
            skills_path = all_dirs[0] if all_dirs else get_skills_dir("skills", root=root)
            skills_extra_paths = list(all_dirs[1:]) if len(all_dirs) > 1 else []
            skills_test_dir_str = (getattr(meta, "skills_test_dir", None) or "").strip()
            skills_test_path = get_skills_dir(skills_test_dir_str, root=root) if skills_test_dir_str else None
            disabled_folders = getattr(meta, "skills_disabled", None) or []
            incremental = bool(getattr(meta, "skills_incremental_sync", False))
            n = await sync_skills_to_vector_store(
                skills_path, vs, embedder,
                skills_test_dir=skills_test_path, incremental=incremental,
                skills_extra_dirs=skills_extra_paths if skills_extra_paths else None,
                disabled_folders=disabled_folders if disabled_folders else None,
            )
            return JSONResponse(content={"synced": int(n) if n is not None else 0})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_skills_sync_vector_store


def get_api_testing_clear_all_handler(core):
    """Return handler for POST /api/testing/clear-all."""
    async def api_testing_clear_all():
        try:
            removed_plugins = core.plugin_manager.unregister_all_external_plugins()
            cleared_skills = 0
            vs = getattr(core, "skills_vector_store", None)
            if vs:
                list_ids_fn = getattr(vs, "list_ids", None)
                if list_ids_fn:
                    ids = list_ids_fn(limit=10000)
                    if ids:
                        delete_ids_fn = getattr(vs, "delete_ids", None)
                        if delete_ids_fn:
                            delete_ids_fn(ids)
                        else:
                            for vid in ids:
                                try:
                                    vs.delete(vid)
                                except Exception:
                                    pass
                    cleared_skills = len(ids) if ids else 0
            return JSONResponse(content={
                "removed_plugins": removed_plugins,
                "plugins_count": len(removed_plugins),
                "skills_cleared": cleared_skills,
            })
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_testing_clear_all


def get_api_sessions_list_handler(core):
    """Return handler for GET /api/sessions. Step 13: Requires user_id (query); optional friend_id. Returns only sessions for (user_id) or (user_id, friend_id)."""
    async def api_sessions_list(request: Request):
        try:
            try:
                uid = (request.query_params.get("user_id") or "").strip()
                fid = (request.query_params.get("friend_id") or "").strip() or None
            except Exception:
                uid, fid = "", None
            if not uid:
                return JSONResponse(status_code=400, content={"detail": "user_id is required (query param)."})
            try:
                session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
            except Exception:
                session_cfg = {}
            if not isinstance(session_cfg, dict):
                session_cfg = {}
            if not session_cfg.get("api_enabled", True):
                return JSONResponse(status_code=403, content={"detail": "Session API disabled"})
            try:
                raw_limit = session_cfg.get("sessions_list_limit", 100)
                limit = max(1, min(500, int(raw_limit) if raw_limit is not None else 100))
            except (TypeError, ValueError):
                limit = 100
            try:
                sessions = core.get_sessions(user_id=uid, friend_id=fid, num_rounds=limit, fetch_all=True)
            except Exception as ge:
                logger.debug("get_sessions failed: {}", ge)
                sessions = []
            return JSONResponse(content={"sessions": sessions if isinstance(sessions, list) else []})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_sessions_list


def get_api_reports_usage_handler(core):  # noqa: ARG001
    """Return handler for GET /api/reports/usage."""
    async def api_reports_usage(format: str = "json"):
        try:
            from hybrid_router.metrics import generate_usage_report
            out = generate_usage_report(format=format.strip().lower() or "json")
            if format.strip().lower() == "csv":
                return Response(content=out, media_type="text/csv")
            return JSONResponse(content=out)
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_reports_usage
