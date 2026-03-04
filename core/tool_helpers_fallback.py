"""
Fallback implementations for tool helpers when core.services.tool_helpers fails to import.
Same logic as core/services/tool_helpers.py (and the former inline block in core/core.py).
Used so Core never crashes if the primary module is missing or broken.
Never raises; never imports from core.core.
"""
import json
import re
import uuid
from typing import Any, Dict, Optional

from loguru import logger


def tool_result_looks_like_error(result: Any) -> bool:
    """True if the tool result looks like an error or not-found; do not use as final response. Never raises."""
    try:
        if result is None or not isinstance(result, str):
            return False
        if len(result) > 2000:
            return False
        r = result.strip().lower()
        if not r:
            return False
        if r == "[]":
            return True
        if "wasn't found" in r or "was not found" in r or "couldn't find" in r or "could not find" in r:
            return True
        if "no entries" in r and "directory" in r:
            return True
        if "no files or folders matched" in r or "no files matched" in r:
            return True
        if "path is required" in r or "that path is outside" in r or "path wasn't found" in r:
            return True
        if "file not found" in r or "not readable" in r or "not found or not readable" in r:
            return True
        if r.startswith("error:") or "error: " in r[:200]:
            return True
        if "do not reply with only this line" in r or "you must in this turn" in r:
            return True
    except Exception:
        return False
    return False


def tool_result_usable_as_final_response(
    tool_name: str,
    tool_result: str,
    config: Optional[Dict[str, Any]] = None,
    tool_args: Optional[Dict[str, Any]] = None,
) -> bool:
    """Whether we can use the tool result as final reply and skip second LLM call. Never raises."""
    try:
        if not isinstance(tool_name, str) or not tool_name.strip():
            return False
        if not isinstance(tool_result, str):
            return False
    except Exception:
        return False
    try:
        result = tool_result.strip()
        if not result or result == "(no output)":
            return False
        if tool_result_looks_like_error(result):
            return False
        cfg = config if isinstance(config, dict) else {}
        enabled = cfg.get("enabled", True)
        if not enabled:
            return False
        if isinstance(tool_name, str) and tool_name.strip() == "run_skill":
            try:
                r = (result if isinstance(result, str) else str(result or "")).lower()
                if "instruction-only skill confirmed" in r or "do not reply with only this line" in r or "you must in this turn" in r:
                    logger.debug("run_skill instruction-only result: skipping use as final response (will do second LLM round)")
                    return False
            except Exception:
                pass
        _need_llm_raw = cfg.get("needs_llm_tools")
        needs_llm = tuple(_need_llm_raw) if isinstance(_need_llm_raw, (list, tuple)) else (
            "document_read", "file_read", "file_understand",
            "web_search", "tavily_extract", "tavily_crawl", "tavily_research",
            "memory_search", "memory_get", "agent_memory_search", "agent_memory_get",
            "knowledge_base_search", "fetch_url", "web_extract", "web_crawl",
            "browser_navigate", "web_search_browser", "image", "sessions_transcript",
        )
        if tool_name in needs_llm:
            return False
        if tool_name == "run_skill" and isinstance(tool_args, dict):
            try:
                skill_name = str(tool_args.get("skill_name") or tool_args.get("skill") or "").strip()
            except (TypeError, ValueError):
                skill_name = ""
            if skill_name:
                need_llm_skills = cfg.get("skills_results_need_llm")
                if isinstance(need_llm_skills, (list, tuple)):
                    need_llm_set = {str(s).strip() for s in need_llm_skills if isinstance(s, str) and str(s).strip()}
                    if skill_name in need_llm_set:
                        return False
        if tool_name in ("save_result_page", "get_file_view_link"):
            return ("/files/out" in result and "token=" in result) or ("http" in result and "/files/" in result)
        _self_raw = cfg.get("self_contained_tools")
        self_contained = tuple(_self_raw) if isinstance(_self_raw, (list, tuple)) else (
            "run_skill", "echo", "time", "profile_get", "profile_list", "models_list", "agents_list",
            "platform_info", "cwd", "env", "session_status", "sessions_list", "sessions_send", "sessions_spawn",
            "cron_list", "cron_status", "cron_schedule", "cron_remove", "cron_update", "cron_run",
            "remind_me", "record_date", "recorded_events_list", "profile_update",
            "append_agent_memory", "append_daily_memory", "usage_report", "channel_send",
            "exec", "process_list", "process_poll", "process_kill",
            "file_write", "file_edit", "apply_patch", "folder_list", "file_find",
            "http_request", "webhook_trigger",
            "knowledge_base_add", "knowledge_base_remove", "knowledge_base_list",
            "browser_snapshot", "browser_click", "browser_type",
        )
        try:
            _max = cfg.get("max_self_contained_length", 2000)
            max_len = int(_max) if isinstance(_max, (int, float)) else 2000
        except (TypeError, ValueError):
            max_len = 2000
        max_len = max(100, min(max_len, 50000))
        if tool_name in self_contained:
            return len(result) <= max_len
        return False
    except Exception:
        return False


# Broad reminder/scheduling intent keywords across languages. Not limited to specific actions (drink, meeting).
# If the user says "remind me to X" or "N分钟后提醒我 X" in any language, we want to match on the reminder part.
_REMINDER_INTENT_KEYWORDS = (
    # Chinese (generic reminder / alarm / notify)
    "提醒", "提醒我", "闹钟", "定时", "通知", "到点", "到点提醒", "提前提醒", "能提醒", "帮我提醒",
    "记得提醒", "到时提醒", "到时间提醒", "叫我", "闹铃", "提醒一下", "设个提醒", "设提醒",
    # English (generic)
    "remind", "remind me", "reminder", "reminders", "notify", "notify me", "alert", "alert me",
    "alarm", "wake me", "call me", "ping me", "tell me", "set reminder", "set a reminder",
    "add reminder", "create reminder", "schedule reminder", "wake up", "check in",
    # Korean
    "알림", "알려줘", "알려주", "알려", "리마인드", "알려주세요",
    # Japanese
    "リマインド", "思い出させて", "通知", "アラーム", "覚えて",
    # Spanish / Portuguese
    "recordar", "recordarme", "avisar", "avísame", "lembrar", "lembre-me", "avisa",
    # German / French
    "erinnern", "erinnere mich", "rappeler", "rappelle-moi",
    # Italian / Dutch
    "ricordare", "ricordami", "herinner", "herinner me",
    # Other
    "hatırlat", "napomni", "напомни", "przypomnij",
)
# Patterns (order matters): (regex, group_index, multiplier). multiplier 1 = minutes, 60 = hours->minutes.
# "提前 X 分钟 ... Y 分钟后" is handled above with m_ev/m_bef, not here.
# Multilingual: Chinese, English, and common European time phrases.
_REMIND_ME_MINUTES_PATTERNS = [
    # Chinese
    (r"(\d+)\s*分钟(?:后|以后|之后)?", 1, 1),
    (r"(\d+)\s*分钟", 1, 1),
    (r"过\s*(\d+)\s*分钟", 1, 1),
    (r"(\d+)\s*分钟\s*后", 1, 1),
    (r"(\d+)\s*小时\s*后", 1, 60),
    (r"(\d+)\s*个小时\s*后", 1, 60),
    # English
    (r"(?:remind|tell|ping|call)\s+(?:me\s+)?in\s+(\d+)\s*(?:min|minutes?)\b", 1, 1),
    (r"in\s+(\d+)\s*(?:min|minutes?)\s*(?:from now|later)?", 1, 1),
    (r"(\d+)\s*(?:min|minutes?)\s+(?:from now|later|from now on)", 1, 1),
    (r"(\d+)\s*(?:min|mins?)\b", 1, 1),
    (r"after\s+(\d+)\s*(?:min|minutes?)", 1, 1),
    (r"in\s+(\d+)\s*hours?\b", 1, 60),
    (r"(\d+)\s*hours?\s+(?:from now|later)", 1, 60),
    # French, German, Spanish, Italian (e.g. "dans 10 minutes", "in 10 Minuten")
    (r"(?:dans|en|in|tra)\s+(\d+)\s*(?:min|minutes?|minuten|minuti|minutos?)\b", 1, 1),
    (r"(\d+)\s*(?:min|minutes?|minuten|minuti|minutos?)\s*(?:plus tard|later)", 1, 1),
]
# When user says "event in N min" but no "remind M min before", we don't guess — return None (ask).
_EVENT_ONLY_KEYWORDS = ("有个会", "开会", "meeting", "会议", "appointment", "会")


def _has_reminder_intent(q: str) -> bool:
    """
    True if query suggests a one-shot reminder. Uses:
    (1) Multilingual reminder keywords (any language), not limited to specific actions.
    (2) Fallback: clear time phrase (e.g. "in 5 min", "10分钟后") + first-person or imperative
        so "5分钟后叫我" or "in 10 minutes tell me" match without needing "喝水" or "meeting".
    """
    if not q or len(q.strip()) < 2:
        return False
    q_lower = q.lower()
    for kw in _REMINDER_INTENT_KEYWORDS:
        if kw.isascii() and kw in q_lower:
            return True
        if not kw.isascii() and kw in q:
            return True
    # Time phrase + first-person or tell/remind verb (any language) -> treat as reminder intent
    has_time = bool(
        re.search(r"\d+\s*分钟(?:后|以后|之后)?|\d+\s*分钟", q)
        or re.search(r"in\s+\d+\s*(?:min|minutes?|hours?)\b", q, re.IGNORECASE)
        or re.search(r"\d+\s*(?:min|minutes?|hours?)\s+(?:from now|later)", q, re.IGNORECASE)
    )
    first_person_or_imperative = bool(
        re.search(r"我|me\b|mich|moi", q, re.IGNORECASE)
        or re.search(r"(提醒|叫|告诉|remind|tell|notify|call|wake|ping)\s*(me|我)?", q, re.IGNORECASE)
    )
    if has_time and first_person_or_imperative:
        return True
    return False


def _is_event_without_advance(q: str) -> bool:
    """True if user mentioned an event (e.g. meeting) but not 'M minutes before'."""
    for kw in _EVENT_ONLY_KEYWORDS:
        if kw in q or kw in q.lower():
            if re.search(r"提前\s*\d+\s*分钟", q) or re.search(r"\d+\s*(?:min|minutes?)\s+(?:before|in advance|ahead)", q, re.IGNORECASE):
                return False
            return True
    return False


def infer_remind_me_fallback(query: str) -> Optional[Dict[str, Any]]:
    """
    Infer remind_me(minutes, message) from natural-language reminder phrases (many styles/languages).
    When the LLM did not call remind_me, this allows Core to run the tool anyway so the reminder is actually set.
    Never raises.
    """
    if not query or not isinstance(query, str):
        return None
    try:
        q = query.strip()
        if not q or not _has_reminder_intent(q):
            return None
        # "Event in N min" without "M min before" -> do not guess; ask user.
        if _is_event_without_advance(q):
            return None
        minutes = None
        mult = 1
        # Prefer "X分钟后...提前Y分钟" -> minutes = X - Y
        m_ev = re.search(r"(\d+)\s*分钟(?:后|以后|之后)?", q)
        m_bef = re.search(r"提前\s*(\d+)\s*分钟", q)
        if m_ev and m_bef:
            try:
                ev, bef = int(m_ev.group(1)), int(m_bef.group(1))
                if 1 <= ev <= 43200 and 0 <= bef <= ev:
                    minutes = max(1, ev - bef)
            except (ValueError, TypeError):
                pass
        if minutes is None:
            for pat, grp_idx, mul in _REMIND_ME_MINUTES_PATTERNS:
                m = re.search(pat, q, re.IGNORECASE)
                if m:
                    try:
                        n = int(m.group(grp_idx))
                        if 0 < n <= (43200 if mul == 1 else 720):  # cap 30d in min, 12h in hours
                            minutes = n * mul
                            break
                    except (ValueError, IndexError, TypeError):
                        continue
        if minutes is None or minutes <= 0 or minutes > 43200:
            return None
        # Short message without date/time (tool will show time; we avoid inventing)
        msg = (q[:80].strip() if len(q) > 80 else q.strip()) or "Reminder"
        # If message is only a clock/time fragment (e.g. "下午5:19"), use generic label so we don't duplicate time in UI
        if len(msg) <= 25 and re.search(r"\d{1,2}\s*[点:]\s*\d{1,2}|下午\d|上午\d|^\d{1,2}:\d{2}", msg):
            msg = "Reminder"
        return {"tool": "remind_me", "arguments": {"minutes": minutes, "message": msg[:120] or "Reminder"}}
    except Exception:
        pass
    return None


def remind_me_needs_clarification(query: str) -> bool:
    """True when user wants a reminder but we couldn't extract when. Never raises."""
    if not query or not isinstance(query, str):
        return False
    if not _has_reminder_intent(query.strip()):
        return False
    return infer_remind_me_fallback(query) is None


def remind_me_clarification_question(query: str) -> Optional[str]:
    """Contextual question when we can't infer when to remind. Never raises."""
    if not query or not isinstance(query, str):
        return None
    q = query.strip()
    if ("有个会" in q or "开会" in q or "meeting" in q) and re.search(r"\d+\s*分钟", q) and not re.search(r"提前\s*\d+\s*分钟", q):
        return "提前几分钟提醒你啊？ How many minutes before should I remind you?"
    if ("生日" in q or "月" in q) and ("提前" in q or "提醒" in q) and not re.search(r"提前\s*(?:一周|几天|\d+\s*天)", q):
        return "提前一周提醒你可以吗？或者提前几天？ Remind you one week before, or how many days before?"
    return None


def infer_route_to_plugin_fallback(query: str) -> Optional[Dict[str, Any]]:
    """Infer route_to_plugin from user query when LLM returns no tool call. Never raises."""
    if not query or not isinstance(query, str):
        return None
    q = query.strip().lower()
    if "photo" in q or "snap" in q:
        node_id = None
        for m in re.finditer(r"(?:on\s+)([a-zA-Z0-9_-]+)", query, re.IGNORECASE):
            node_id = m.group(1)
        if not node_id:
            m = re.search(r"([a-zA-Z0-9]+-node-[a-zA-Z0-9]+)", query, re.IGNORECASE)
            node_id = m.group(1) if m else None
        if node_id:
            return {"plugin_id": "homeclaw-browser", "capability_id": "node_camera_snap", "parameters": {"node_id": node_id}}
    if ("record" in q and "video" in q) or ("video" in q and "record" in q):
        node_id = None
        for m in re.finditer(r"(?:on\s+)([a-zA-Z0-9_-]+)", query, re.IGNORECASE):
            node_id = m.group(1)
        if not node_id:
            m = re.search(r"([a-zA-Z0-9]+-node-[a-zA-Z0-9]+)", query, re.IGNORECASE)
            node_id = m.group(1) if m else None
        if node_id:
            return {"plugin_id": "homeclaw-browser", "capability_id": "node_camera_clip", "parameters": {"node_id": node_id}}
    if ("list" in q and "node" in q) or ("node" in q and ("connect" in q or "list" in q or "what" in q)):
        return {"plugin_id": "homeclaw-browser", "capability_id": "node_list", "parameters": {}}
    if any(kw in q for kw in ("open ", "navigate", "go to ", "打开", "访问", "浏览")) or re.search(r"https?://", query):
        url = None
        m = re.search(r"(https?://[^\s]+)", query)
        if m:
            url = m.group(1).strip().rstrip(".,;:)")
        if not url and re.search(r"(?:open|navigate to|go to)\s+([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,})", q):
            m = re.search(r"(?:open|navigate to|go to)\s+([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,})", q)
            if m:
                url = "https://" + m.group(1).strip()
        if not url:
            for m in re.finditer(r"(?:打开|访问)\s*(\S+)", query):
                cand = m.group(1).strip()
                if cand.startswith(("http://", "https://")):
                    url = cand
                    break
                if "." in cand and len(cand) > 3:
                    url = "https://" + cand
                    break
        if url:
            return {"plugin_id": "homeclaw-browser", "capability_id": "browser_navigate", "parameters": {"url": url}}
    if any(kw in q for kw in ("ppt", "powerpoint", "slides", "presentation", ".pptx", "幻灯片", "演示文稿")):
        return {"tool": "run_skill", "arguments": {"skill_name": "ppt-generation-1.0.0", "script": "create_pptx.py", "args": ["--capability", "source", "--source", query.strip()]}}
    return None


def parse_raw_tool_calls_from_content(content: str):
    """Parse <tool_call>...</tool_call> from LLM content. Returns list of tool_call dicts or None. Never raises."""
    if not content or not isinstance(content, str):
        return None
    text = content.strip()
    if "<tool_call>" not in text and "</tool_call>" not in text:
        return None
    pattern = re.compile(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>", re.IGNORECASE)
    matches = pattern.findall(text)
    if not matches:
        return None
    tool_calls = []
    for i, raw_json in enumerate(matches):
        try:
            obj = json.loads(raw_json)
            name = obj.get("name") or (obj.get("function") or {}).get("name")
            args = obj.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not name:
                continue
            if not isinstance(args, dict):
                args = {}
            tool_calls.append({
                "id": f"raw_tool_{i}_{uuid.uuid4().hex[:8]}",
                "function": {"name": name, "arguments": json.dumps(args)},
            })
        except (json.JSONDecodeError, TypeError):
            continue
    return tool_calls if tool_calls else None
