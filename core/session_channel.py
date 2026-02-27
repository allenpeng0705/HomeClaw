"""
Last-channel persistence, location cache, and session/chat ID resolution.
Extracted from core/core.py (Phase 5 refactor). All functions take core as first argument.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from base import last_channel as last_channel_store
from base.util import Util
from base.base import PromptRequest
from memory.chat.message import ChatMessage


def _latest_location_path(core: Any) -> Path:
    """Path to latest_locations.json. Never raises."""
    try:
        root = Path(Util().root_path()).resolve()
        meta = Util().get_core_metadata()
        db = getattr(meta, "database", None)
        if getattr(db, "path", None):
            base = root / str(db.path).strip()
        else:
            base = root / "database"
        base.mkdir(parents=True, exist_ok=True)
        return base / "latest_locations.json"
    except Exception as e:
        logger.debug("Latest location path: {}", e)
        return Path("database") / "latest_locations.json"


def _normalize_location_to_address(core: Any, location_input: Any) -> Tuple[Optional[str], Optional[str]]:
    """If location is lat/lng, convert to address. Returns (display_location, lat_lng_str). Never raises."""
    try:
        from base.geocode import location_to_address
        return location_to_address(location_input)
    except Exception as e:
        logger.debug("Normalize location failed: {}", e)
        if isinstance(location_input, str) and location_input.strip():
            return location_input.strip()[:2000], None
        return None, None


def _get_latest_location_entry(core: Any, system_user_id: str) -> Optional[Dict[str, Any]]:
    """Return latest location entry {location, updated_at} for this user or None. Never raises."""
    if not system_user_id:
        return None
    try:
        path = _latest_location_path(core)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        entry = data.get(str(system_user_id))
        if isinstance(entry, dict) and entry.get("location"):
            return entry
        return None
    except Exception as e:
        logger.debug("Get latest location failed: {}", e)
        return None


def _set_latest_location(
    core: Any,
    system_user_id: str,
    location_str: str,
    lat_lng_str: Optional[str] = None,
) -> None:
    """Store latest location for this user. Never raises."""
    if not system_user_id or not isinstance(location_str, str) or not location_str.strip():
        return
    try:
        path = _latest_location_path(core)
        data = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        entry = {
            "location": location_str.strip()[:2000],
            "updated_at": datetime.now().isoformat(),
        }
        if lat_lng_str and isinstance(lat_lng_str, str) and lat_lng_str.strip():
            entry["lat_lng"] = lat_lng_str.strip()[:100]
        data[str(system_user_id)] = entry
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0, ensure_ascii=False)
    except Exception as e:
        logger.debug("Set latest location failed: {}", e)


def _get_latest_location(core: Any, system_user_id: str) -> Optional[str]:
    """Return latest location for this user or None. Never raises."""
    entry = _get_latest_location_entry(core, system_user_id)
    if isinstance(entry, dict) and entry.get("location"):
        return str(entry.get("location", "")).strip() or None
    return None


def _resolve_session_key(
    core: Any,
    app_id: str,
    user_id: str,
    channel_name: Optional[str] = None,
    account_id: Optional[str] = None,
) -> str:
    """Derive session key from dmScope and identityLinks. Never raises."""
    session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
    dm_scope = (session_cfg.get("dm_scope") or "main").strip().lower()
    identity_links = session_cfg.get("identity_links") or {}
    peer_id = user_id or ""
    if isinstance(identity_links, dict):
        for canonical, prefixes in identity_links.items():
            if isinstance(prefixes, list) and (user_id in prefixes or peer_id in prefixes):
                peer_id = str(canonical)
                break
            if isinstance(prefixes, str) and (user_id == prefixes or peer_id == prefixes):
                peer_id = str(canonical)
                break
    app = (app_id or "homeclaw").strip() or "homeclaw"
    channel = (channel_name or "").strip() or "im"
    account = (account_id or "").strip() or "default"
    if dm_scope == "main":
        return f"{app}:main"
    if dm_scope == "per-peer":
        return f"{app}:dm:{peer_id}"
    if dm_scope == "per-channel-peer":
        return f"{app}:{channel}:dm:{peer_id}"
    if dm_scope == "per-account-channel-peer":
        return f"{app}:{channel}:{account}:dm:{peer_id}"
    return f"{app}:dm:{peer_id}"


def get_session_id(
    core: Any,
    app_id: Any,
    user_name: Any = None,
    user_id: Any = None,
    channel_name: Optional[str] = None,
    account_id: Optional[str] = None,
    friend_id: Optional[str] = None,
    validity_period: timedelta = None,
) -> str:
    """Resolve or create session ID for (app_id, user_id, friend_id). Never raises."""
    if validity_period is None:
        validity_period = timedelta(hours=24)
    session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
    dm_scope = (session_cfg.get("dm_scope") or "").strip().lower()
    if dm_scope in ("main", "per-peer", "per-channel-peer", "per-account-channel-peer"):
        return _resolve_session_key(
            core,
            app_id=app_id,
            user_id=user_id or "",
            channel_name=channel_name,
            account_id=account_id,
        )
    fid = (str(friend_id or "").strip() or "HomeClaw") if friend_id is not None else "HomeClaw"
    cache_key = f"{user_id or ''}|{fid}"
    if cache_key in core.session_ids:
        session_id, _ = core.session_ids[cache_key]
        return session_id
    sessions: List[dict] = core.chatDB.get_sessions(
        app_id=app_id,
        user_name=user_name,
        user_id=user_id,
        friend_id=fid,
        num_rounds=1,
        fetch_all=False,
    )
    for session in sessions:
        session_id = session.get("session_id")
        if session_id:
            return session_id
    return user_id


def _persist_last_channel(core: Any, request: PromptRequest) -> None:
    """Persist last channel to DB and atomic file. Also saves per-session key for cron. Never raises."""
    if request is None:
        return
    try:
        app_id = getattr(request, "app_id", None) or ""
        last_channel_store.save_last_channel(
            request_id=request.request_id,
            host=request.host,
            port=int(request.port),
            channel_name=request.channel_name,
            request_metadata=request.request_metadata or {},
            key=last_channel_store._DEFAULT_KEY,
            app_id=app_id,
        )
        try:
            session_id = get_session_id(
                core,
                app_id=app_id,
                user_name=getattr(request, "user_name", None),
                user_id=getattr(request, "user_id", None),
                channel_name=getattr(request, "channel_name", None),
                friend_id=getattr(request, "friend_id", None),
            )
            if session_id and app_id and getattr(request, "user_id", None):
                session_key = f"{app_id}:{request.user_id}:{session_id}"
                last_channel_store.save_last_channel(
                    request_id=request.request_id,
                    host=request.host,
                    port=int(request.port),
                    channel_name=request.channel_name,
                    request_metadata=request.request_metadata or {},
                    key=session_key,
                    app_id=app_id,
                )
        except Exception as sk:
            logger.debug("Failed to persist last channel session key: {}", sk)
    except Exception as e:
        logger.warning("Failed to persist last channel: {}", e)


def get_run_id(
    core: Any,
    agent_id: Any,
    user_name: Any = None,
    user_id: Any = None,
    validity_period: timedelta = None,
) -> str:
    """Return run_id for agent/user from chatDB or user_id. Never raises."""
    if validity_period is None:
        validity_period = timedelta(hours=24)
    if user_id in core.run_ids:
        run_id, _ = core.run_ids[user_id]
        return run_id
    runs: List[dict] = core.chatDB.get_runs(
        agent_id=agent_id,
        user_name=user_name,
        user_id=user_id,
        num_rounds=1,
        fetch_all=False,
    )
    for run in runs:
        run_id = run.get("run_id")
        if run_id:
            return run_id
    return user_id


def get_latest_chat_info(
    core: Any,
    app_id: Any = None,
    user_name: Any = None,
    user_id: Any = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (app_id, user_name, user_id) of latest session or (None, None, None). Never raises."""
    chat_sessions = core.chatDB.get_sessions(
        app_id=app_id,
        user_name=user_name,
        user_id=user_id,
        num_rounds=1,
    )
    if len(chat_sessions) == 0:
        return None, None, None
    chat_session: dict = chat_sessions[0]
    return (
        chat_session.get("app_id"),
        chat_session.get("user_name"),
        chat_session.get("user_id"),
    )


def get_latest_chats(
    core: Any,
    app_id: Any = None,
    user_name: Any = None,
    user_id: Any = None,
    num_rounds: int = 10,
    timestamp: Optional[datetime] = None,
) -> List[ChatMessage]:
    """Return latest chat messages. Never raises."""
    histories: List[ChatMessage] = core.chatDB.get(
        app_id=app_id,
        user_name=user_name,
        user_id=user_id,
        num_rounds=num_rounds,
        fetch_all=False,
        display_format=False,
    )
    if timestamp is None:
        return histories
    return [h for h in histories if timestamp - h.created_at < timedelta(minutes=30)]


def get_latest_chats_by_role(
    core: Any,
    sender_name: Any = None,
    responder_name: Any = None,
    num_rounds: int = 10,
    timestamp: Optional[datetime] = None,
):
    """Return latest chats by role. Never raises."""
    histories = core.chatDB.get_hist_by_role(sender_name, responder_name, num_rounds)
    if timestamp is None:
        return histories
    return [h for h in histories if timestamp - h.created_at < timedelta(minutes=30)]


def get_system_context_for_plugins(
    core: Any,
    system_user_id: Optional[str] = None,
    request: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Build system context (datetime, timezone, location) for plugin parameter resolution.
    Returns dict with: datetime, datetime_iso, timezone, location (optional), location_source, location_confidence.
    """
    out: Dict[str, Any] = {}
    try:
        now = datetime.now()
        try:
            now = now.astimezone()
        except Exception:
            pass
        out["datetime"] = now.strftime("%Y-%m-%d %H:%M")
        out["datetime_iso"] = now.isoformat()
        out["timezone"] = getattr(now.tzinfo, "tzname", lambda: None)() or "system local"
    except Exception:
        out["datetime"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        out["datetime_iso"] = datetime.now().isoformat()
        out["timezone"] = "system local"

    user_id = system_user_id or (getattr(request, "user_id", None) if request else None) or ""
    loc_str = None
    location_source = None
    location_confidence = "low"
    try:
        meta = getattr(request, "request_metadata", None) if request else {}
        raw_loc = meta.get("location") if isinstance(meta, dict) else None
        if raw_loc is not None:
            display_loc, _ = _normalize_location_to_address(core, raw_loc)
            if display_loc:
                loc_str = display_loc
                location_source = "request"
                location_confidence = "high"
        if not loc_str and user_id:
            entry = _get_latest_location_entry(core, user_id)
            if isinstance(entry, dict) and entry.get("location"):
                loc_str = str(entry.get("location", "")).strip()
                location_source = "latest"
                updated = entry.get("updated_at") or ""
                if updated:
                    try:
                        updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                        now_ref = datetime.now(updated_dt.tzinfo) if getattr(updated_dt, "tzinfo", None) else datetime.now()
                        if (now_ref - updated_dt) < timedelta(hours=24):
                            location_confidence = "high"
                    except Exception:
                        pass
        if not loc_str and user_id:
            profile_cfg = getattr(Util().get_core_metadata(), "profile", None) or {}
            if isinstance(profile_cfg, dict) and profile_cfg.get("enabled", True):
                try:
                    from base.profile_store import get_profile
                    profile_base_dir = (profile_cfg.get("dir") or "").strip() or None
                    profile_data = get_profile(user_id or "", base_dir=profile_base_dir)
                    if isinstance(profile_data, dict) and profile_data.get("location"):
                        loc_str = str(profile_data.get("location", "")).strip()
                        location_source = "profile"
                except Exception:
                    pass
        if not loc_str:
            loc_str = (getattr(Util().get_core_metadata(), "default_location", None) or "").strip() or None
            if loc_str:
                location_source = "config"
        if not loc_str:
            shared_key = getattr(core, "_LATEST_LOCATION_SHARED_KEY", "companion")
            entry = _get_latest_location_entry(core, shared_key)
            if isinstance(entry, dict) and entry.get("location"):
                loc_str = str(entry.get("location", "")).strip()
                location_source = "shared"
    except Exception as e:
        logger.debug("System context location: {}", e)
    if loc_str:
        out["location"] = loc_str[:500]
        out["location_source"] = location_source or "unknown"
        out["location_confidence"] = location_confidence
    return out
