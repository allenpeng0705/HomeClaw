"""
LLM-backed inference for remind_me / cron_schedule / record_date when regex heuristics miss.

Used by Companion scheduling fast-path and strict_fallback scheduling recovery. On failure or
invalid JSON, callers fall back to tool_helpers_fallback regex. Never raises from public entrypoints.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

from core.tool_helpers_fallback import (
    infer_annual_birthday_advance_reminder_fallback,
    infer_cron_schedule_fallback,
    infer_remind_me_fallback,
)

_REMINDER_SCHEDULING_SYSTEM = """You are a scheduling intent parser for a personal assistant.
Given the user's message and the CURRENT REFERENCE TIME, output ONE JSON object only (no markdown, no prose).

Schema (all string values UTF-8; use null only when the user is NOT asking to schedule a reminder, recurring job, or record a date):
{
  "tool": "remind_me" | "cron_schedule" | "record_date" | null,
  "arguments": { ... }  // empty object {} if tool is null
}

Rules:
- Use ONLY the current reference time for "tomorrow", "next Monday", relative times, etc. Ignore any dates/times in older chat context.
- remind_me: one-shot reminder. Provide EITHER "minutes" (positive integer, minutes from now) OR "at_time" (string "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD" for 09:00:00), and "message" (short label, <=120 chars).
- cron_schedule: recurring schedule. "cron_expr" must be a standard 5-field cron (minute hour day month weekday), e.g. "0 8 * * *" for daily 08:00. Include "message".
- record_date: remember an event (birthday, anniversary). Require "event_name" and "when" (natural phrase). Optional: "event_date" (YYYY-MM-DD), "note", "remind_on" ("day_before"|"on_day"), "remind_days_before" (0-120), "remind_message", "repeat_yearly" (boolean). If the user only wants a simple one-shot reminder with a clear clock time, prefer remind_me over record_date.

If ambiguous or not a scheduling request, return {"tool": null, "arguments": {}}.
Output JSON only, one line if possible."""


def _strip_json_fence(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if m:
        return (m.group(1) or "").strip()
    return s


def _parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    s = _strip_json_fence(raw)
    if not s:
        return None
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _validate_remind_me_args(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(args, dict):
        return None
    msg = (args.get("message") or "").strip() or "Reminder"
    if len(msg) > 200:
        msg = msg[:200]
    minutes = args.get("minutes")
    at_time = (args.get("at_time") or "").strip()
    if minutes is not None and str(minutes).strip() != "":
        try:
            mi = int(minutes)
        except (TypeError, ValueError):
            mi = None
        if mi is not None and 0 < mi <= 43200:
            return {"minutes": mi, "message": msg}
    if at_time:
        at_norm = at_time.replace("T", " ").strip()
        try:
            if len(at_norm) >= 19:
                run_time_str = at_norm[:19]
                datetime.strptime(run_time_str, "%Y-%m-%d %H:%M:%S")
            elif len(at_norm) >= 10:
                datetime.strptime(at_norm[:10], "%Y-%m-%d")
                run_time_str = at_norm[:10] + " 09:00:00"
            else:
                return None
        except ValueError:
            return None
        return {"at_time": run_time_str, "message": msg}
    return None


def _validate_cron_args(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(args, dict):
        return None
    expr = (args.get("cron_expr") or "").strip()
    if not expr:
        return None
    parts = expr.split()
    if len(parts) != 5:
        return None
    msg = (args.get("message") or "").strip() or "Scheduled reminder"
    if len(msg) > 200:
        msg = msg[:200]
    return {"cron_expr": expr, "message": msg}


def _validate_record_date_args(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(args, dict):
        return None
    event_name = (args.get("event_name") or "").strip()
    when = (args.get("when") or "").strip()
    if not event_name or not when:
        return None
    out: Dict[str, Any] = {"event_name": event_name, "when": when}
    note = (args.get("note") or "").strip()
    if note:
        out["note"] = note[:500]
    ed = (args.get("event_date") or "").strip()
    if ed:
        out["event_date"] = ed[:32]
    ro = (args.get("remind_on") or "").strip().lower()
    if ro in ("day_before", "on_day"):
        out["remind_on"] = ro
    rdb = args.get("remind_days_before")
    if rdb is not None and str(rdb).strip() != "":
        try:
            iv = int(rdb)
            if 0 <= iv <= 120:
                out["remind_days_before"] = iv
        except (TypeError, ValueError):
            pass
    rm = (args.get("remind_message") or "").strip()
    if rm:
        out["remind_message"] = rm[:200]
    if args.get("repeat_yearly") is True:
        out["repeat_yearly"] = True
    return out


def normalize_llm_scheduling_result(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn parsed LLM JSON into the same shape as infer_remind_me_fallback / infer_cron_schedule_fallback, or None."""
    try:
        tool = obj.get("tool")
        if tool is None or (isinstance(tool, str) and tool.strip().lower() in ("null", "none", "")):
            return None
        if not isinstance(tool, str):
            return None
        t = tool.strip().lower()
        args = obj.get("arguments")
        if not isinstance(args, dict):
            args = {}
        if t == "remind_me":
            v = _validate_remind_me_args(args)
            return {"tool": "remind_me", "arguments": v} if v else None
        if t == "cron_schedule":
            v = _validate_cron_args(args)
            return {"tool": "cron_schedule", "arguments": v} if v else None
        if t == "record_date":
            v = _validate_record_date_args(args)
            return {"tool": "record_date", "arguments": v} if v else None
    except Exception:
        return None
    return None


async def infer_scheduling_tools_from_llm(
    core: Any,
    user_message: str,
    current_datetime_line: str,
    tools_cfg: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    One short LLM completion: JSON with tool + arguments, or null. Never raises.
    """
    cfg = tools_cfg if isinstance(tools_cfg, dict) else {}
    if not cfg.get("reminder_scheduling_llm_infer", True):
        return None
    text = (user_message or "").strip()
    if not text or core is None:
        return None
    preview = (text[:2000] + "…") if len(text) > 2000 else text
    dt = (current_datetime_line or "").strip() or "(unknown)"
    user_block = f"Current reference time (authoritative): {dt}\n\nUser message:\n{preview}"
    messages = [
        {"role": "system", "content": _REMINDER_SCHEDULING_SYSTEM},
        {"role": "user", "content": user_block},
    ]
    timeout = float(cfg.get("reminder_scheduling_llm_infer_timeout_seconds") or 22.0)
    if timeout <= 0:
        timeout = 22.0
    llm_name = cfg.get("reminder_scheduling_llm_infer_llm") or None
    try:
        coro = core.openai_chat_completion(messages=messages, llm_name=llm_name)
        raw = await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.debug("reminder_scheduling LLM infer timed out after {}s", timeout)
        return None
    except Exception as e:
        logger.debug("reminder_scheduling LLM infer failed: {}", e)
        return None
    if not raw or not isinstance(raw, str):
        return None
    obj = _parse_json_object(raw)
    if not obj:
        return None
    return normalize_llm_scheduling_result(obj)


async def merge_companion_scheduling_inference(
    query: str,
    core: Any,
    current_datetime_line: str,
    tools_cfg: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Order: annual birthday heuristic (stable), LLM infer, regex remind_me, regex cron.
    Returns a dict with tool+arguments, or None. Never raises.
    """
    if not query or not isinstance(query, str):
        return None
    q = query.strip()
    if not q:
        return None
    try:
        ann = infer_annual_birthday_advance_reminder_fallback(q)
        if ann:
            return ann
        llm = await infer_scheduling_tools_from_llm(core, q, current_datetime_line, tools_cfg)
        if llm:
            return llm
        return infer_remind_me_fallback(q) or infer_cron_schedule_fallback(q)
    except Exception as e:
        logger.debug("merge_companion_scheduling_inference failed: {}", e)
        return None
