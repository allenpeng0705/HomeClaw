"""
Persistent storage for TAM cron jobs and one-shot reminders.
Survives Core restart: on TAM init we load from DB and re-schedule.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from memory.database.database import DatabaseManager
from memory.database.models import TamCronJobModel, TamOneShotReminderModel, ScheduledActionModel


def _get_session():
    return DatabaseManager().get_session()


def load_cron_jobs() -> List[Dict[str, Any]]:
    """Load all persisted cron jobs. Returns list of {job_id, cron_expr, params}."""
    session = _get_session()
    try:
        rows = session.query(TamCronJobModel).all()
        out = []
        for r in rows:
            try:
                params = json.loads(r.params) if r.params else {}
            except Exception:
                params = {}
            out.append({"job_id": r.job_id, "cron_expr": r.cron_expr, "params": params})
        return out
    except Exception as e:
        logger.warning("TAM storage: load_cron_jobs failed: {}", e)
        return []
    finally:
        try:
            session.close()
        except Exception:
            pass


def save_cron_job(job_id: str, cron_expr: str, params: Dict[str, Any]) -> bool:
    """Persist a cron job. Returns True on success."""
    session = _get_session()
    try:
        session.merge(
            TamCronJobModel(
                job_id=job_id,
                cron_expr=cron_expr,
                params=json.dumps(params) if params else "{}",
            )
        )
        session.commit()
        return True
    except Exception as e:
        logger.warning("TAM storage: save_cron_job failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


def remove_cron_job(job_id: str) -> bool:
    """Remove a persisted cron job. Returns True if removed."""
    session = _get_session()
    try:
        n = session.query(TamCronJobModel).filter(TamCronJobModel.job_id == job_id).delete()
        session.commit()
        return n > 0
    except Exception as e:
        logger.warning("TAM storage: remove_cron_job failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


def clear_all_cron_jobs() -> int:
    """Delete all persisted cron jobs (e.g. on memory reset). Returns number deleted."""
    session = _get_session()
    try:
        n = session.query(TamCronJobModel).delete()
        session.commit()
        return n
    except Exception as e:
        logger.warning("TAM storage: clear_all_cron_jobs failed: {}", e)
        session.rollback()
        return 0
    finally:
        try:
            session.close()
        except Exception:
            pass


def clear_all_one_shot_reminders() -> int:
    """Delete all one-shot reminders from DB (e.g. on memory reset). In-memory scheduled timers may still fire until restart. Returns number deleted."""
    session = _get_session()
    try:
        n = session.query(TamOneShotReminderModel).delete()
        session.commit()
        return n
    except Exception as e:
        logger.warning("TAM storage: clear_all_one_shot_reminders failed: {}", e)
        session.rollback()
        return 0
    finally:
        try:
            session.close()
        except Exception:
            pass


def update_cron_job(
    job_id: str,
    cron_expr: Optional[str] = None,
    params_update: Optional[Dict[str, Any]] = None,
) -> bool:
    """Update a cron job: merge params_update into params; optionally set cron_expr. Returns True on success."""
    session = _get_session()
    try:
        row = session.query(TamCronJobModel).filter(TamCronJobModel.job_id == job_id).first()
        if not row:
            return False
        params = {}
        if row.params:
            try:
                params = json.loads(row.params)
            except Exception:
                pass
        if params_update:
            params.update(params_update)
        if cron_expr is not None:
            row.cron_expr = cron_expr
        row.params = json.dumps(params)
        session.commit()
        return True
    except Exception as e:
        logger.warning("TAM storage: update_cron_job failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


def update_cron_job_state(
    job_id: str,
    last_run_at: Optional[datetime] = None,
    last_status: Optional[str] = None,
    last_error: Optional[str] = None,
    last_duration_ms: Optional[int] = None,
) -> bool:
    """Update run-history state for a cron job (stored in params). Returns True on success."""
    state: Dict[str, Any] = {}
    if last_run_at is not None:
        state["last_run_at"] = last_run_at.isoformat() if hasattr(last_run_at, "isoformat") else str(last_run_at)
    if last_status is not None:
        state["last_status"] = last_status
    if last_error is not None:
        state["last_error"] = last_error
    if last_duration_ms is not None:
        state["last_duration_ms"] = last_duration_ms
    return update_cron_job(job_id, params_update=state) if state else True


def cleanup_expired_one_shot_reminders(before: Optional[datetime] = None) -> int:
    """Delete one-shot reminders with run_at < before (default: now). Returns number deleted. Call on load so expired reminders don't accumulate."""
    session = _get_session()
    try:
        cutoff = before if before is not None else datetime.now()
        n = session.query(TamOneShotReminderModel).filter(TamOneShotReminderModel.run_at < cutoff).delete()
        session.commit()
        return n
    except Exception as e:
        logger.warning("TAM storage: cleanup_expired_one_shot_reminders failed: {}", e)
        session.rollback()
        return 0
    finally:
        try:
            session.close()
        except Exception:
            pass


def load_one_shot_reminders(after: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Load one-shot reminders with run_at > after (default: now). Returns list of {id, run_at, message, user_id, channel_key, friend_id}. Step 10: friend_id for from_friend when fire."""
    session = _get_session()
    try:
        q = session.query(TamOneShotReminderModel)
        if after is not None:
            q = q.filter(TamOneShotReminderModel.run_at > after)
        rows = q.all()
        out = []
        for r in rows:
            try:
                out.append({
                    "id": getattr(r, "id", None) or "",
                    "run_at": getattr(r, "run_at", None),
                    "message": (getattr(r, "message", None) or "") or "",
                    "user_id": getattr(r, "user_id", None),
                    "channel_key": getattr(r, "channel_key", None),
                    "friend_id": getattr(r, "friend_id", None),
                })
            except Exception as e:
                logger.debug("TAM storage: skip bad one-shot reminder row: {}", e)
        return out
    except Exception as e:
        logger.warning("TAM storage: load_one_shot_reminders failed: {}", e)
        return []
    finally:
        try:
            session.close()
        except Exception:
            pass


def add_one_shot_reminder(
    run_at: datetime,
    message: str,
    user_id: Optional[str] = None,
    channel_key: Optional[str] = None,
    friend_id: Optional[str] = None,
) -> Optional[str]:
    """Persist a one-shot reminder. Returns reminder id on success, None on failure. Step 10: friend_id used as from_friend when reminder fires."""
    session = _get_session()
    try:
        try:
            fid = (str(friend_id).strip() or None) if friend_id is not None else None
        except (TypeError, AttributeError):
            fid = None
        row = TamOneShotReminderModel(
            run_at=run_at,
            message=message,
            user_id=user_id or None,
            channel_key=channel_key or None,
            friend_id=fid,
        )
        session.add(row)
        session.flush()
        rid = row.id
        session.commit()
        return rid
    except Exception as e:
        logger.warning("TAM storage: add_one_shot_reminder failed: {}", e)
        session.rollback()
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass


def delete_one_shot_reminder(reminder_id: str) -> bool:
    """Delete a one-shot reminder (e.g. after it has fired). Returns True if deleted."""
    session = _get_session()
    try:
        n = session.query(TamOneShotReminderModel).filter(TamOneShotReminderModel.id == reminder_id).delete()
        session.commit()
        return n > 0
    except Exception as e:
        logger.warning("TAM storage: delete_one_shot_reminder failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


# --- Scheduled actions (confirm now, execute at run_at). Used for "3分钟后发邮件" etc. ---
PENDING_ACTION_PREFIX = "__ACTION:"
PENDING_ACTION_SUFFIX = "__"


def add_scheduled_action(
    user_id: str,
    run_at: datetime,
    action_type: str,
    action_payload: Dict[str, Any],
    friend_id: Optional[str] = None,
    channel_key: Optional[str] = None,
) -> Optional[str]:
    """Store a pending action (status=awaiting_confirmation). Returns action_id or None. Never raises."""
    session = _get_session()
    try:
        payload_str = json.dumps(action_payload) if isinstance(action_payload, dict) else "{}"
        row = ScheduledActionModel(
            user_id=(user_id or "").strip() or "companion",
            friend_id=(str(friend_id).strip() or None) if friend_id is not None else None,
            channel_key=(str(channel_key).strip() or None) if channel_key is not None else None,
            run_at=run_at,
            action_type=(action_type or "").strip() or "run_skill",
            action_payload=payload_str,
            status="awaiting_confirmation",
        )
        session.add(row)
        session.flush()
        aid = row.id
        session.commit()
        return aid
    except Exception as e:
        logger.warning("TAM storage: add_scheduled_action failed: {}", e)
        session.rollback()
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass


def get_scheduled_action(action_id: str) -> Optional[Dict[str, Any]]:
    """Load action by id. Returns {id, user_id, friend_id, channel_key, run_at, action_type, action_payload, status} or None. Never raises."""
    try:
        aid = (str(action_id).strip() if action_id is not None else "") or ""
    except (TypeError, AttributeError):
        return None
    if not aid:
        return None
    session = _get_session()
    try:
        row = session.query(ScheduledActionModel).filter(ScheduledActionModel.id == aid).first()
        if not row:
            return None
        try:
            payload = json.loads(row.action_payload) if row.action_payload else {}
        except Exception:
            payload = {}
        return {
            "id": row.id,
            "user_id": getattr(row, "user_id", None) or "companion",
            "friend_id": getattr(row, "friend_id", None),
            "channel_key": getattr(row, "channel_key", None),
            "run_at": row.run_at,
            "action_type": (row.action_type or "").strip() or "run_skill",
            "action_payload": payload,
            "status": (row.status or "").strip() or "awaiting_confirmation",
        }
    except Exception as e:
        logger.warning("TAM storage: get_scheduled_action failed: {}", e)
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass


def get_pending_confirmation_for_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get the most recent action for this user with status=awaiting_confirmation. For confirm flow. Never raises."""
    if not user_id or not isinstance(user_id, str):
        return None
    session = _get_session()
    try:
        row = (
            session.query(ScheduledActionModel)
            .filter(
                ScheduledActionModel.user_id == user_id.strip(),
                ScheduledActionModel.status == "awaiting_confirmation",
            )
            .order_by(ScheduledActionModel.created_at.desc())
            .first()
        )
        if not row:
            return None
        return get_scheduled_action(row.id)
    except Exception as e:
        logger.warning("TAM storage: get_pending_confirmation_for_user failed: {}", e)
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass


def mark_scheduled_action_scheduled(action_id: str) -> bool:
    """Set status=scheduled after we created the one-shot reminder. Returns True on success. Never raises."""
    session = _get_session()
    try:
        n = (
            session.query(ScheduledActionModel)
            .filter(ScheduledActionModel.id == action_id, ScheduledActionModel.status == "awaiting_confirmation")
            .update({"status": "scheduled"}, synchronize_session=False)
        )
        session.commit()
        return n > 0
    except Exception as e:
        logger.warning("TAM storage: mark_scheduled_action_scheduled failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


def mark_scheduled_action_executed(action_id: str) -> bool:
    """Set status=executed after action ran. Returns True on success. Never raises."""
    session = _get_session()
    try:
        n = session.query(ScheduledActionModel).filter(ScheduledActionModel.id == action_id).update({"status": "executed"}, synchronize_session=False)
        session.commit()
        return n > 0
    except Exception as e:
        logger.warning("TAM storage: mark_scheduled_action_executed failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


def delete_scheduled_action(action_id: str) -> bool:
    """Remove action (e.g. after executed or cancelled). Returns True if deleted. Never raises."""
    session = _get_session()
    try:
        n = session.query(ScheduledActionModel).filter(ScheduledActionModel.id == action_id).delete()
        session.commit()
        return n > 0
    except Exception as e:
        logger.warning("TAM storage: delete_scheduled_action failed: {}", e)
        session.rollback()
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass
