"""
Misc API routes: skills clear-vector-store, skills list/search/install (Companion->Core), testing clear-all, sessions list, reports usage.
"""
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger

from base.util import Util


def _install_failure_detail(out: dict) -> str:
    """Build a short, readable error message for skill install failure (no raw JSON/stderr dump)."""
    err = (out.get("error") or "").strip()
    if err:
        return err[:600]
    convert = out.get("convert") or {}
    install = out.get("install") or {}
    err = (convert.get("error") or "").strip()
    if err:
        return err[:600]
    err = (install.get("error") or "").strip()
    # If install only has generic "Command failed (N)", prefer stderr so user sees real reason
    if err and not (err.startswith("Command failed (") and "): " not in err):
        return err[:600]
    stderr = (install.get("stderr") or "").strip()
    if stderr:
        lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
        for ln in lines:
            ln_lower = ln.lower()
            if "experimental" in ln_lower or "deprecat" in ln_lower or "warning" in ln_lower:
                continue
            if len(ln) > 10:
                return ln[:600]
        return (lines[0] if lines else stderr[:400])[:600]
    if err:
        return err[:600]
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
            from base.clawhub_integration import clawhub_available, clawhub_search
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
    """GET /api/skills/clawhub-login-status — whether ClawHub CLI is logged in (whoami). Companion->Core."""
    async def api_skills_clawhub_login_status(request: Request):
        try:
            from base.clawhub_integration import clawhub_available, clawhub_whoami
            if not clawhub_available():
                return JSONResponse(
                    status_code=200,
                    content={"logged_in": False, "message": "clawhub not found on PATH", "clawhub_available": False},
                )
            logged_in, message = clawhub_whoami()
            return JSONResponse(
                content={"logged_in": logged_in, "message": message, "clawhub_available": True},
            )
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e), "logged_in": False})
    return api_skills_clawhub_login_status


def get_api_skills_clawhub_login_handler(core):  # noqa: ARG001
    """POST /api/skills/clawhub-login — start ClawHub login; returns URL to open in browser if available. Companion->Core."""
    async def api_skills_clawhub_login(request: Request):
        try:
            from base.clawhub_integration import clawhub_available, clawhub_login
            if not clawhub_available():
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "clawhub not found on PATH. Install the ClawHub CLI (e.g. npm i -g clawhub), then restart Core.",
                        "url": None,
                        "ok": False,
                    },
                )
            out = clawhub_login(timeout_s=120)
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
            root = Path(__file__).resolve().parent.parent.parent
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
