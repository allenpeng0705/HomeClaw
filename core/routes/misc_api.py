"""
Misc API routes: skills clear-vector-store, testing clear-all, sessions list, reports usage.
"""
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger

from base.util import Util


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
