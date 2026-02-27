"""
Memory routes: /memory/summarize, /memory/reset (GET + POST).
Step 13: /memory/reset accepts optional user_id and friend_id (query or body); when set, clear only that scope (chat, agent memory, daily); else clear all (backward compat).
"""
from datetime import date, timedelta
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from base.util import Util
from base.workspace import (
    get_workspace_dir,
    clear_agent_memory_file,
    clear_daily_memory_for_dates,
)


def _safe_str_strip(val) -> str:
    """Return stripped string or empty. Never raises."""
    try:
        if val is None:
            return ""
        return (str(val).strip() if isinstance(val, (str, int, float)) else str(val)) or ""
    except Exception:
        return ""


async def _memory_reset_user_friend(request: Request) -> tuple:
    """Get user_id and friend_id from query (GET) or body (POST). Returns (user_id or None, friend_id or None). Never raises."""
    try:
        uid = _safe_str_strip(request.query_params.get("user_id")) or None
        fid = _safe_str_strip(request.query_params.get("friend_id")) or None
        if uid and fid is not None and not fid:
            fid = None
        if getattr(request, "method", "") == "POST" and (request.headers.get("content-type") or "").strip().lower().startswith("application/json"):
            try:
                body = await request.json()
            except Exception:
                body = {}
            if isinstance(body, dict):
                if not uid:
                    uid = _safe_str_strip(body.get("user_id")) or None
                if fid is None:
                    fid = _safe_str_strip(body.get("friend_id")) or None
        return uid, fid
    except Exception:
        return None, None


def get_memory_summarize_handler(core):
    """Return handler for POST /memory/summarize."""
    async def memory_summarize():
        """
        Run one pass of RAG memory summarization (batch old memories → LLM summary, then TTL delete of originals).
        """
        try:
            result = await core.run_memory_summarization()
            return JSONResponse(content=result)
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"ok": False, "message": str(e), "summaries_created": 0, "ttl_deleted": 0})
    return memory_summarize


def get_memory_reset_handler(core):
    """Return handler for GET/POST /memory/reset. Step 13: optional user_id, friend_id (query/body) for scoped clear."""
    async def memory_reset(request: Request):
        """
        Empty the memory store (for testing). When user_id (and optional friend_id) provided, clear only that scope (chat, AGENT_MEMORY, daily). Else clear all (RAG, chat, agent/daily, profiles, TAM).
        """
        try:
            uid, fid = await _memory_reset_user_friend(request)
        except Exception:
            uid, fid = None, None
        mem = getattr(core, "mem_instance", None)
        chat_db = getattr(core, "chatDB", None)
        if uid:
            message = "Memory cleared for user."
            chat_cleared = False
            if chat_db is not None:
                try:
                    chat_db.reset(user_id=uid, friend_id=fid)
                    chat_cleared = True
                except Exception as e:
                    logger.debug("Chat reset (scoped) during memory reset: {}", e)
            try:
                meta = Util().get_core_metadata()
                if getattr(meta, "use_agent_memory_file", True):
                    try:
                        workspace_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "")
                        agent_path = getattr(meta, "agent_memory_path", "") or ""
                        if clear_agent_memory_file(workspace_dir=workspace_dir, agent_memory_path=agent_path if agent_path else None, system_user_id=uid, friend_id=fid):
                            message = (message + " AGENT_MEMORY cleared.") if message else "AGENT_MEMORY cleared."
                    except Exception as e:
                        logger.debug("clear_agent_memory_file (scoped) during reset: {}", e)
                if getattr(meta, "use_daily_memory", True):
                    try:
                        workspace_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "")
                        daily_dir = getattr(meta, "daily_memory_dir", "") or ""
                        today = date.today()
                        yesterday = today - timedelta(days=1)
                        n = clear_daily_memory_for_dates([yesterday, today], workspace_dir=workspace_dir, daily_memory_dir=daily_dir if daily_dir else None, system_user_id=uid, friend_id=fid)
                        if n > 0:
                            message = (message + " Daily memory cleared.") if message else "Daily memory cleared."
                    except Exception as e:
                        logger.debug("clear_daily_memory (scoped) during reset: {}", e)
            except Exception as e:
                logger.debug("Memory reset (scoped) agent/daily: {}", e)
            if chat_cleared:
                message = (message + " Chat history cleared.") if message else "Chat history cleared."
            return JSONResponse(content={"result": "ok", "message": message})
        if mem is None:
            return JSONResponse(status_code=404, content={"detail": "Memory not enabled or not initialized."})
        try:
            mem.reset()
            logger.info("Memory reset completed (backend={})", type(mem).__name__)
            message = "Memory cleared."
            chat_cleared = False
            if chat_db is not None:
                try:
                    chat_db.reset()
                    chat_cleared = True
                except Exception as e:
                    logger.debug("Chat history reset during memory reset: {}", e)
            try:
                meta = Util().get_core_metadata()
                if getattr(meta, "use_agent_memory_file", True):
                    try:
                        workspace_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "")
                        agent_path = getattr(meta, "agent_memory_path", "") or ""
                        if clear_agent_memory_file(workspace_dir=workspace_dir, agent_memory_path=agent_path if agent_path else None):
                            logger.info("AGENT_MEMORY.md cleared.")
                            message = "Memory and AGENT_MEMORY.md cleared."
                    except Exception as e:
                        logger.debug("clear_agent_memory_file during reset: {}", e)
                if getattr(meta, "use_daily_memory", True):
                    try:
                        workspace_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "")
                        daily_dir = getattr(meta, "daily_memory_dir", "") or ""
                        today = date.today()
                        yesterday = today - timedelta(days=1)
                        n = clear_daily_memory_for_dates([yesterday, today], workspace_dir=workspace_dir, daily_memory_dir=daily_dir if daily_dir else None)
                        if n > 0:
                            logger.info("Daily memory cleared ({} file(s)).", n)
                            message = (message + " Daily memory (yesterday/today) cleared.") if message else "Memory and daily memory cleared."
                    except Exception as e:
                        logger.debug("clear_daily_memory during reset: {}", e)
                profile_cfg = getattr(meta, "profile", None) or {}
                if isinstance(profile_cfg, dict) and profile_cfg.get("enabled", True):
                    try:
                        from base.profile_store import clear_all_profiles
                        profile_base_dir = (profile_cfg.get("dir") or "").strip() or None
                        n_profiles = clear_all_profiles(base_dir=profile_base_dir)
                        if n_profiles > 0:
                            logger.info("Profiles cleared ({} file(s)).", n_profiles)
                            message = (message + " Profiles cleared.") if message else "Profiles cleared."
                    except Exception as e:
                        logger.debug("clear_all_profiles during reset: {}", e)
                try:
                    orch = getattr(core, "orchestratorInst", None)
                    tam = getattr(orch, "tam", None) if orch else None
                    if tam is not None:
                        if hasattr(tam, "clear_recorded_events") and tam.clear_recorded_events():
                            logger.info("Recorded events (record_date) cleared.")
                            message = (message + " Recorded events cleared.") if message else "Recorded events cleared."
                        if hasattr(tam, "clear_all_cron_jobs"):
                            n_cron = tam.clear_all_cron_jobs()
                            if n_cron > 0:
                                logger.info("Cron jobs cleared ({}).", n_cron)
                                message = (message + " Cron jobs cleared.") if message else "Cron jobs cleared."
                        if hasattr(tam, "clear_all_one_shot_reminders"):
                            n_oneshot = tam.clear_all_one_shot_reminders()
                            if n_oneshot > 0:
                                logger.info("One-shot reminders cleared from DB ({}).", n_oneshot)
                                message = (message + " One-shot reminders cleared.") if message else "One-shot reminders cleared."
                except Exception as e:
                    logger.debug("TAM clear during reset: {}", e)
            except Exception as e:
                logger.debug("Memory reset agent/daily clear: {}", e)
            if chat_cleared:
                message = (message + " Chat history cleared.") if message else "Chat history cleared."
            return JSONResponse(content={"result": "ok", "message": message})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return memory_reset
