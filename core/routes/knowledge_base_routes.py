"""
Knowledge base routes: /knowledge_base/reset, /knowledge_base/folder_sync_config, /knowledge_base/sync_folder (GET + POST).
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from base.util import Util


async def _sync_folder_user_id(request: Request) -> tuple:
    """Get user_id from query (GET) or body (POST). Returns (user_id, None) or (None, error_response)."""
    user_id = (request.query_params.get("user_id") or "").strip()
    if not user_id and request.method == "POST":
        try:
            body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        user_id = (body.get("user_id") or "").strip()
    if not user_id and hasattr(request, "state") and getattr(request.state, "user_id", None):
        user_id = (request.state.user_id or "").strip()
    if not user_id:
        return None, JSONResponse(status_code=400, content={"detail": "user_id is required (query param or body)."})
    return user_id, None


def get_knowledge_base_reset_handler(core):
    """Return handler for GET/POST /knowledge_base/reset."""
    async def knowledge_base_reset():
        """Empty the knowledge base (all users, all sources)."""
        kb = getattr(core, "knowledge_base", None)
        if kb is None:
            meta = Util().get_core_metadata()
            kb_cfg = getattr(meta, "knowledge_base", None) or {}
            enabled = kb_cfg.get("enabled") if isinstance(kb_cfg, dict) else getattr(kb_cfg, "enabled", False)
            hint = ""
            if enabled:
                hint = " Knowledge base is enabled but failed to initialize at startup. Check Core startup logs for 'Knowledge base (Cognee) not initialized' (full traceback is logged). Common causes: (1) pip install cognee not run; (2) main_llm or embedding_llm not set in config so Cognee has no LLM/embedding endpoint; (3) Cognee DB/vector/graph (cognee section) not reachable or misconfigured."
            return JSONResponse(status_code=404, content={"detail": "Knowledge base not enabled or not initialized." + hint})
        try:
            out = await kb.reset()
            if out.startswith("Error:"):
                return JSONResponse(status_code=500, content={"detail": out, "result": "error"})
            logger.info("Knowledge base reset: {}", out)
            return JSONResponse(content={"result": "ok", "message": out})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return knowledge_base_reset


def get_knowledge_base_folder_sync_config_handler(core):  # noqa: ARG001
    """Return handler for GET /knowledge_base/folder_sync_config."""
    async def knowledge_base_folder_sync_config():
        """Return folder_sync config: allowed_extensions and max_file_size_bytes."""
        try:
            meta = Util().get_core_metadata()
            kb_cfg = getattr(meta, "knowledge_base", None) or {}
            if not isinstance(kb_cfg, dict):
                kb_cfg = {}
            fs_cfg = kb_cfg.get("folder_sync") or {}
            if not isinstance(fs_cfg, dict):
                fs_cfg = {}
            allowed = fs_cfg.get("allowed_extensions") or [".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".rst", ".csv", ".ppt", ".pptx"]
            if not isinstance(allowed, list):
                allowed = [".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".rst", ".csv", ".ppt", ".pptx"]
            allowed = [str(e).strip().lower() for e in allowed if e]
            max_bytes = max(0, int(fs_cfg.get("max_file_size_bytes", 5_000_000) or 5_000_000))
            return JSONResponse(content={
                "enabled": bool(fs_cfg.get("enabled")),
                "allowed_extensions": allowed,
                "max_file_size_bytes": max_bytes,
            })
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return knowledge_base_folder_sync_config


def get_knowledge_base_sync_folder_handler(core):
    """Return handler for GET/POST /knowledge_base/sync_folder."""
    async def knowledge_base_sync_folder(request: Request):
        """Trigger knowledge base folder sync manually for a user_id."""
        user_id, err = await _sync_folder_user_id(request)
        if err is not None:
            return err
        try:
            result = await core.sync_user_kb_folder(user_id)
            return JSONResponse(content=result)
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e), "ok": False})
    return knowledge_base_sync_folder
