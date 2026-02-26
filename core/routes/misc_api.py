"""
Misc API routes: skills clear-vector-store, testing clear-all, sessions list, reports usage.
"""
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
    """Return handler for GET /api/sessions."""
    async def api_sessions_list():
        try:
            session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
            if not session_cfg.get("api_enabled", True):
                return JSONResponse(status_code=403, content={"detail": "Session API disabled"})
            limit = max(1, min(500, int(session_cfg.get("sessions_list_limit", 100))))
            sessions = core.get_sessions(num_rounds=limit, fetch_all=True)
            return JSONResponse(content={"sessions": sessions})
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
