"""
Persisted pending user actions (offer → confirm → execute).
Used when the assistant asks e.g. "Want a magazine PDF?" and the user replies naturally on a later turn.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import or_

from memory.database.database import DatabaseManager
from memory.database.models import PendingUserActionModel


def _session():
    return DatabaseManager().get_session()


def _utc_naive_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def cancel_pending_for_user(user_id: str) -> int:
    """Mark all pending rows for user as cancelled. Returns update count."""
    if not user_id or not isinstance(user_id, str):
        return 0
    uid = user_id.strip()
    if not uid:
        return 0
    session = _session()
    try:
        n = (
            session.query(PendingUserActionModel)
            .filter(
                PendingUserActionModel.user_id == uid,
                PendingUserActionModel.status == "pending",
            )
            .update({"status": "cancelled"}, synchronize_session=False)
        )
        session.commit()
        return int(n or 0)
    except Exception as e:
        logger.warning("pending_user_actions: cancel_pending_for_user failed: {}", e)
        session.rollback()
        return 0
    finally:
        try:
            session.close()
        except Exception:
            pass


def insert_pending(
    user_id: str,
    friend_id: Optional[str],
    kind: str,
    payload: Dict[str, Any],
    summary: Optional[str],
    ttl_seconds: int,
) -> Optional[str]:
    """Insert one pending action; cancels previous pending for same user. Returns id or None.

    For kinds without a dedicated handler in core/pending_user_action_dispatch.py, you may store a generic
    single-tool payload: {\"tool\": \"run_skill\", \"arguments\": {...}} (see tools_config.pending_user_action_generic_tools).
    """
    if not user_id or not isinstance(user_id, str):
        return None
    uid = user_id.strip()
    if not uid or not kind or not isinstance(kind, str):
        return None
    try:
        ttl = max(60, min(86400, int(ttl_seconds or 1800)))
    except (TypeError, ValueError):
        ttl = 1800
    cancel_pending_for_user(uid)
    session = _session()
    try:
        row = PendingUserActionModel(
            user_id=uid,
            friend_id=(str(friend_id).strip() or None) if friend_id is not None else None,
            kind=kind.strip(),
            payload_json=json.dumps(payload, ensure_ascii=False),
            summary=(summary or "").strip() or None,
            status="pending",
            expires_at=_utc_naive_now() + timedelta(seconds=ttl),
        )
        session.add(row)
        session.flush()
        rid = row.id
        session.commit()
        return str(rid) if rid else None
    except Exception as e:
        logger.warning("pending_user_actions: insert_pending failed: {}", e)
        session.rollback()
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass


def get_active_pending(user_id: str, friend_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Latest pending row for user if not expired. Auto-marks expired rows.

    When friend_id is set, only rows for that friend match (or legacy rows with NULL friend_id for same user).
    """
    if not user_id or not isinstance(user_id, str):
        return None
    uid = user_id.strip()
    if not uid:
        return None
    now = _utc_naive_now()
    session = _session()
    try:
        try:
            session.query(PendingUserActionModel).filter(
                PendingUserActionModel.user_id == uid,
                PendingUserActionModel.status == "pending",
                PendingUserActionModel.expires_at < now,
            ).update({"status": "expired"}, synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()

        q = session.query(PendingUserActionModel).filter(
            PendingUserActionModel.user_id == uid,
            PendingUserActionModel.status == "pending",
            PendingUserActionModel.expires_at >= now,
        )
        if friend_id is not None:
            fid_norm = str(friend_id).strip() or "HomeClaw"
            q = q.filter(
                or_(
                    PendingUserActionModel.friend_id == fid_norm,
                    PendingUserActionModel.friend_id.is_(None),
                )
            )
        row = q.order_by(PendingUserActionModel.created_at.desc()).first()
        if not row:
            return None
        try:
            payload = json.loads(row.payload_json) if row.payload_json else {}
        except Exception:
            payload = {}
        return {
            "id": row.id,
            "user_id": row.user_id,
            "friend_id": getattr(row, "friend_id", None),
            "kind": (row.kind or "").strip(),
            "payload": payload if isinstance(payload, dict) else {},
            "summary": getattr(row, "summary", None),
            "created_at": row.created_at,
            "expires_at": row.expires_at,
        }
    except Exception as e:
        logger.warning("pending_user_actions: get_active_pending failed: {}", e)
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass


def mark_executed(action_id: str) -> bool:
    if not action_id or not isinstance(action_id, str):
        return False
    aid = action_id.strip()
    if not aid:
        return False
    session = _session()
    try:
        n = (
            session.query(PendingUserActionModel)
            .filter(PendingUserActionModel.id == aid, PendingUserActionModel.status == "pending")
            .update({"status": "executed"}, synchronize_session=False)
        )
        session.commit()
        return n > 0
    except Exception as e:
        logger.warning("pending_user_actions: mark_executed failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


def mark_cancelled(action_id: str) -> bool:
    if not action_id or not isinstance(action_id, str):
        return False
    aid = action_id.strip()
    if not aid:
        return False
    session = _session()
    try:
        n = (
            session.query(PendingUserActionModel)
            .filter(PendingUserActionModel.id == aid, PendingUserActionModel.status == "pending")
            .update({"status": "cancelled"}, synchronize_session=False)
        )
        session.commit()
        return n > 0
    except Exception as e:
        logger.warning("pending_user_actions: mark_cancelled failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


def response_looks_like_magazine_pdf_offer(text: str) -> bool:
    """True if assistant text asks whether to create magazine/PDF (English or Chinese)."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if not t:
        return False
    low = t.lower()
    has_pdf_theme = (
        "magazine" in low
        or "pdf" in low
        or "杂志" in t
        or "排版" in t
    )
    if not has_pdf_theme:
        return False
    asks = (
        "would you like" in low
        or "do you want" in low
        or "shall i" in low
        or "should i" in low
        or "要不要" in t
        or "是否" in t
        or "需要我" in t
        or "要我帮你" in t
        or "要我吗" in t
        or ("生成" in t and ("pdf" in low or "杂志" in t))
    )
    return bool(asks)


def parse_daily_brief_fetch_params(args_dict: Optional[Dict[str, Any]]) -> tuple:
    """From run_skill args for daily-brief, return (max_items, lang)."""
    max_items = 20
    lang = "all"
    if not isinstance(args_dict, dict):
        return max_items, lang
    if (args_dict.get("skill_name") or "").strip() != "daily-brief-1.0.0":
        return max_items, lang
    al = args_dict.get("args")
    if not isinstance(al, list):
        return max_items, lang
    i = 0
    while i < len(al):
        x = al[i]
        if x == "--max" and i + 1 < len(al):
            try:
                max_items = max(1, min(100, int(str(al[i + 1]).strip())))
            except (TypeError, ValueError):
                pass
            i += 2
        elif x == "--lang" and i + 1 < len(al):
            lang = str(al[i + 1]).strip() or "all"
            i += 2
        else:
            i += 1
    return max_items, lang


def maybe_store_daily_brief_magazine_offer(
    *,
    response: Optional[str],
    last_tool_name: Optional[str],
    last_tool_args: Optional[Dict[str, Any]],
    user_id: str,
    friend_id: Optional[str],
    ttl_seconds: int,
) -> None:
    """If the model offered a magazine/PDF after daily-brief, persist params for confirm."""
    if not response or not isinstance(response, str) or not response.strip():
        return
    _txt = response.strip()
    try:
        from core.log_helpers import _strip_leading_route_label

        _txt = (_strip_leading_route_label(_txt) or _txt).strip()
    except Exception:
        pass
    if last_tool_name != "run_skill" or not isinstance(last_tool_args, dict):
        return
    if (last_tool_args.get("skill_name") or "").strip() != "daily-brief-1.0.0":
        return
    if not response_looks_like_magazine_pdf_offer(_txt):
        return
    # Already produced a file link in this reply — nothing to confirm.
    if "/files/out" in response and ("token=" in response or "dev_unsigned=1" in response):
        return
    max_items, lang = parse_daily_brief_fetch_params(last_tool_args)
    payload = {"max_items": max_items, "lang": lang}
    summary = "Magazine-style PDF from Daily Brief"
    rid = insert_pending(
        user_id,
        friend_id,
        "daily_brief_magazine_pdf",
        payload,
        summary,
        ttl_seconds,
    )
    if rid:
        logger.info("pending_user_actions: stored offer id={} user={} ttl={}s", rid, user_id, ttl_seconds)
