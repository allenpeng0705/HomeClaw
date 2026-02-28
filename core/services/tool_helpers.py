"""
Stateless tool helpers used by Core (orchestrator / inbound flow).

- tool_result_looks_like_error: detect error-like or instruction-only tool results.
- tool_result_usable_as_final_response: whether to use tool result as final reply (skip second LLM).
- parse_raw_tool_calls_from_content: parse <tool_call>...</tool_call> from LLM content.
- infer_route_to_plugin_fallback: infer route_to_plugin from user query when LLM returns no tool call.
- infer_remind_me_fallback: infer remind_me(minutes, message) from "N分钟后提醒" / "remind me in N minutes" when LLM returns no tool call.
- remind_me_needs_clarification: True when user wants a reminder but we couldn't extract when (so Core can ask).
- remind_me_clarification_question: Contextual question when we can't infer (e.g. "提前几分钟提醒你啊？" for event-in-N-min).

Never raises; never imports from core.core to avoid circular imports.
See docs_design/CoreRefactoringModularCore.md and CoreRefactorPhaseSummary.md.
"""

import json
import re
import uuid
from typing import Any, Dict, Optional

from loguru import logger


def tool_result_looks_like_error(result: Any) -> bool:
    """True if the tool result is an error or not-found message; we should not use it as final response (do 2nd LLM round instead). Never raises."""
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
        # File/path errors (directory may not be empty; model used wrong path)
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
        # Results that are instructions to the model (not user-facing) should not be used as final response
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
    """
    Deterministic (no LLM) check: whether we can use the tool result as the final user response
    and skip the second LLM call.
    - Plugins: Handled by route_to_plugin (returns immediately with plugin result; no second LLM).
    - Skills: By default use result for all skills (run_skill); list skills in skills_results_need_llm to force a second LLM call.
    - Config: tools.use_result_as_response (self_contained_tools, needs_llm_tools, max_self_contained_length, skills_results_need_llm).
    - No response: Empty or "(no output)" returns False so we do a second LLM round; the model can reply "Done." or we keep prior content (e.g. auto_invoke).
    - Error-like result: If the result looks like "not found" / error, return False so we do the 2nd LLM round (model can rephrase or suggest listing files).
    - Instruction-only run_skill: Skills without a script return instructions to the model; we never use that as final response (default in Core, no config).
    """
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
        # Default: run_skill for instruction-only skills (no script) returns instructions to the model, not a user-facing answer. Always do another LLM round so the model continues with document_read / save_result_page etc. No config needed. Never raise.
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
        # Per-skill: skills in skills_results_need_llm always get a second LLM call (e.g. maton-api-gateway for richer reply). Instruction-only skills are already handled above by default.
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
        # save_result_page / get_file_view_link: use when result contains the link (token-style or static www_root-style)
        if tool_name in ("save_result_page", "get_file_view_link"):
            return ("/files/out" in result and "token=" in result) or ("http" in result and "/files/" in result)
        # folder_list / file_find: excluded from self_contained so we always do a second LLM round.
        # Otherwise "what does 1.pdf say?" → file_find returns JSON list → user gets raw JSON instead of document_read + summary.
        _self_raw = cfg.get("self_contained_tools")
        self_contained = tuple(_self_raw) if isinstance(_self_raw, (list, tuple)) else (
            "run_skill", "echo", "time", "profile_get", "profile_list", "models_list", "agents_list",
            "platform_info", "cwd", "env", "session_status", "sessions_list", "sessions_send", "sessions_spawn",
            "cron_list", "cron_status", "cron_schedule", "cron_remove", "cron_update", "cron_run",
            "remind_me", "record_date", "recorded_events_list", "profile_update",
            "append_agent_memory", "append_daily_memory", "usage_report", "channel_send",
            "exec", "process_list", "process_poll", "process_kill",
            "file_write", "file_edit", "apply_patch",
            "http_request", "webhook_trigger",
            "knowledge_base_add", "knowledge_base_remove", "knowledge_base_list",
            "browser_snapshot", "browser_click", "browser_type",
        )
        try:
            _max = cfg.get("max_self_contained_length", 2000)
            max_len = int(_max) if isinstance(_max, (int, float)) else 2000
        except (TypeError, ValueError):
            max_len = 2000
        max_len = max(100, min(max_len, 50000))  # clamp so bad config never breaks
        if tool_name in self_contained:
            return len(result) <= max_len
        return False
    except Exception:
        return False


def infer_remind_me_fallback(query: str) -> Optional[Dict[str, Any]]:
    """
    When the user clearly asks for a reminder in N minutes but the LLM didn't call remind_me,
    return arguments to run remind_me so we can set the reminder and return a clean response.
    Returns {"tool": "remind_me", "arguments": {"minutes": N, "message": "..."}} or None.
    """
    if not query or not isinstance(query, str):
        return None
    q = query.strip()
    # Match: "15分钟后", "30分钟后有个会", "remind me in 5 minutes", "in 10 minutes", "5 分钟后提醒"
    minutes = None
    # Chinese: N分钟后, N 分钟后
    m = re.search(r"(\d+)\s*分钟后", q)
    if m:
        minutes = int(m.group(1))
    if minutes is None:
        m = re.search(r"(\d+)\s*分钟", q)
        if m:
            minutes = int(m.group(1))
    if minutes is None:
        # English: "in N minutes", "remind me in N minutes", "N minutes"
        m = re.search(r"(?:remind\s+me\s+)?in\s+(\d+)\s+minutes?", q, re.IGNORECASE)
        if m:
            minutes = int(m.group(1))
    if minutes is None:
        m = re.search(r"(\d+)\s+minutes?\s+(?:from\s+now|later)?", q, re.IGNORECASE)
        if m:
            minutes = int(m.group(1))
    if minutes is None or minutes <= 0 or minutes > 43200:  # cap 30 days in minutes
        return None
    # Must look like a reminder intent (提醒, remind, 有个会, meeting, etc.)
    reminder_kw = ("提醒", "remind", "会", "meeting", "通知", "notify", "闹钟", "alarm", "分钟")
    if not any(kw in q for kw in reminder_kw):
        return None
    message = q[:120].strip() if len(q) > 120 else q
    if not message:
        message = "Reminder"
    return {"tool": "remind_me", "arguments": {"minutes": minutes, "message": message}}


def infer_route_to_plugin_fallback(query: str) -> Optional[Dict[str, Any]]:
    """
    When the LLM returns no tool call (e.g. model doesn't support tools or replied "No"), infer route_to_plugin
    from clear user intent so the action still runs. Returns dict with plugin_id, capability_id, parameters or None.
    """
    if not query or not isinstance(query, str):
        return None
    q = query.strip().lower()
    # "take a photo on test-node-1", "photo on X" -> node_camera_snap
    if "photo" in q or "snap" in q:
        node_id = None
        for m in re.finditer(r"(?:on\s+)([a-zA-Z0-9_-]+)", query, re.IGNORECASE):
            node_id = m.group(1)
        if not node_id:
            m = re.search(r"([a-zA-Z0-9]+-node-[a-zA-Z0-9]+)", query, re.IGNORECASE)
            node_id = m.group(1) if m else None
        if node_id:
            return {"plugin_id": "homeclaw-browser", "capability_id": "node_camera_snap", "parameters": {"node_id": node_id}}
    # "record video on X", "record a video on X"
    if ("record" in q and "video" in q) or ("video" in q and "record" in q):
        node_id = None
        for m in re.finditer(r"(?:on\s+)([a-zA-Z0-9_-]+)", query, re.IGNORECASE):
            node_id = m.group(1)
        if not node_id:
            m = re.search(r"([a-zA-Z0-9]+-node-[a-zA-Z0-9]+)", query, re.IGNORECASE)
            node_id = m.group(1) if m else None
        if node_id:
            return {"plugin_id": "homeclaw-browser", "capability_id": "node_camera_clip", "parameters": {"node_id": node_id}}
    # "list nodes", "what nodes are connected"
    if ("list" in q and "node" in q) or ("node" in q and ("connect" in q or "list" in q or "what" in q)):
        return {"plugin_id": "homeclaw-browser", "capability_id": "node_list", "parameters": {}}
    # "open URL", "navigate to X", "go to https://..." — use homeclaw-browser (plugin or built-in tool path). Extract URL from query.
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
    # PPT / slides / presentation — use skill so user gets the file + link
    if any(kw in q for kw in ("ppt", "powerpoint", "slides", "presentation", ".pptx", "幻灯片", "演示文稿")):
        return {"tool": "run_skill", "arguments": {"skill_name": "ppt-generation-1.0.0", "script": "create_pptx.py", "args": ["--capability", "source", "--source", query.strip()]}}
    return None


def infer_remind_me_fallback(query: str) -> Optional[Dict[str, Any]]:
    """
    When the LLM returns no tool call but the user clearly asked for a reminder in N minutes,
    return remind_me arguments so Core can run the tool and return a clean response (avoids
    model inventing wrong times like 2:49 PM). Returns {"tool": "remind_me", "arguments": {minutes, message}} or None.
    """
    if not query or not isinstance(query, str):
        return None
    q = query.strip()
    if not q:
        return None
    # Match "N分钟后" (N minutes later), "remind me in N minutes", "in N minutes", "N 分钟后", "N分钟"
    minutes = None
    for pat in (
        r"(\d+)\s*分钟\s*后",  # 15分钟后, 30 分钟后
        r"(\d+)\s*分钟",       # 15分钟 (if 后 appears elsewhere)
        r"in\s+(\d+)\s*minutes?",
        r"remind\s+.*?(\d+)\s*minutes?",
        r"(\d+)\s*minutes?\s*(?:from now|later)?",
    ):
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            try:
                minutes = int(m.group(1))
                if minutes <= 0 or minutes > 43200:  # cap 30 days
                    continue
                break
            except (ValueError, IndexError):
                continue
    if minutes is None:
        return None
    # Only if the query also suggests a reminder (提醒, remind, meeting, 会, etc.)
    reminder_keywords = ("提醒", "remind", "会", "meeting", "开会", "通知", "notify", "call", "有个")
    if not any(kw in q for kw in reminder_keywords):
        return None
    message = "Reminder"  # tool will run; user sees "Reminder set for HH:MM. I'll remind you: Reminder" or we could use first 50 chars of query
    if len(q) <= 80 and not any(c in q for c in "{}"):
        message = q.strip()
    return {"tool": "remind_me", "arguments": {"minutes": minutes, "message": message[:200] if isinstance(message, str) else "Reminder"}}


def infer_remind_me_fallback(query: str) -> Optional[Dict[str, Any]]:
    """
    When the LLM returns no tool call but the user clearly asked for a reminder in N minutes,
    return remind_me arguments so Core can auto-invoke. Extracts minutes from patterns like
    "30分钟后提醒", "remind me in 30 minutes", "我30分钟后有个会能提醒一下".
    Returns {"tool": "remind_me", "arguments": {"minutes": N, "message": "..."}} or None.
    Never raises.
    """
    if not query or not isinstance(query, str):
        return None
    q = query.strip()
    if not q:
        return None
    # Reminder intent: 提醒, remind, 闹钟, 定时, 有个会, meeting in N minutes
    reminder_kw = (
        "remind", "提醒", "闹钟", "定时", "分钟后", "minutes", "minute",
        "有个会", "开会", "meeting", "提前提醒", "到点提醒",
    )
    if not any(kw in q.lower() if kw.isascii() else kw in q for kw in reminder_kw):
        return None
    # Base = "when" from user; we schedule reminder at (base - advance) from now.
    # E.g. "15分钟后有个会，请提前5分钟提醒我" → event in 15 min, remind 5 min before → remind in 10 min.
    minutes = None
    event_min = None  # event in N minutes
    before_min = None  # remind M minutes before
    # Chinese: "X分钟后...提前Y分钟" or "提前Y分钟...X分钟后"
    m_event_cn = re.search(r"(\d+)\s*分钟(?:后|以后|之后)?", q)
    m_before_cn = re.search(r"提前\s*(\d+)\s*分钟", q)
    if m_event_cn and m_before_cn:
        try:
            event_min = int(m_event_cn.group(1))
            before_min = int(m_before_cn.group(1))
            if 1 <= event_min <= 40320 and 0 <= before_min <= event_min:
                minutes = max(1, event_min - before_min)
        except (ValueError, IndexError, TypeError):
            pass
    if minutes is None:
        # English: "meeting in 15 minutes, remind me 5 minutes before" / "in 15 min, 5 min before"
        m_event_en = re.search(r"(?:meeting|remind|event)\s+in\s+(\d+)\s*(?:min|minutes?)", q, re.IGNORECASE)
        if not m_event_en:
            m_event_en = re.search(r"in\s+(\d+)\s+(?:min|minutes?)", q, re.IGNORECASE)
        m_before_en = re.search(r"(\d+)\s*(?:min|minutes?)\s+(?:before|in advance|ahead)", q, re.IGNORECASE)
        if m_event_en and m_before_en:
            try:
                event_min = int(m_event_en.group(1))
                before_min = int(m_before_en.group(1))
                if 1 <= event_min <= 40320 and 0 <= before_min <= event_min:
                    minutes = max(1, event_min - before_min)
            except (ValueError, IndexError, TypeError):
                pass
    got_advance = m_before_cn is not None or (
        re.search(r"(\d+)\s*(?:min|minutes?)\s+(?:before|in advance|ahead)", q, re.IGNORECASE) is not None
    )
    if minutes is None:
        # Single number: "30分钟后提醒我", "in 30 minutes", etc. Do NOT use when user said an event time but not "when to remind".
        event_keywords = ("有个会", "开会", "meeting", "会议")
        has_event = any(kw in q if kw.isascii() else kw in q for kw in event_keywords)
        for pat in [
            r"(\d+)\s*分钟后",           # 30分钟后
            r"(\d+)\s*分钟(?:后|以后|之后)?",  # 30分钟 / 30分钟后 / 30分钟以后
            r"(\d+)\s*分钟",             # 30 分钟 (space)
            r"in\s+(\d+)\s+minutes?",
            r"in\s+(\d+)\s*min\b",
            r"(\d+)\s+minutes?\s+(?:from now|later|remind)?",
            r"(\d+)\s*min\b",
            r"(\d+)\s*mins?\b",
            r"meeting\s+in\s+(\d+)\s*(?:min|minutes?)",  # meeting in 15 minutes
            r"(?:有个会|开会).*?(\d+)\s*分钟",  # 有个会...15分钟 (flexible order)
            r"(\d+)\s*分钟.*?(?:会|提醒)",      # 15分钟...会/提醒
        ]:
            m = re.search(pat, q, re.IGNORECASE)
            if m:
                try:
                    minutes = int(m.group(1))
                    if 1 <= minutes <= 40320:  # cap ~4 weeks in minutes
                        # If user gave an event time (e.g. "15分钟后有个会") but no "提前Y分钟", don't guess — ask instead.
                        if has_event and not got_advance:
                            minutes = None
                        break
                except (ValueError, IndexError):
                    pass
    if minutes is None:
        return None
    message = (q[:200] + "…") if len(q) > 200 else q
    if not isinstance(message, str):
        message = str(message) if message is not None else "Reminder"
    # Core expects {"tool": "remind_me", "arguments": {...}} and uses .get("arguments") for execute_async.
    return {"tool": "remind_me", "arguments": {"minutes": minutes, "message": message}}


def remind_me_needs_clarification(query: str) -> bool:
    """
    True when the user clearly wants a reminder but we couldn't extract when (minutes/at_time).
    Core can then ask e.g. "When would you like to be reminded? (e.g. in 15 minutes or at 3:00 PM)"
    or use remind_me_clarification_question() for a contextual prompt.
    """
    if not query or not isinstance(query, str):
        return False
    q = query.strip()
    if not q:
        return False
    reminder_kw = (
        "remind", "提醒", "闹钟", "定时", "分钟后", "minutes", "minute",
        "有个会", "开会", "meeting", "提前提醒", "到点提醒",
    )
    if not any(kw in q.lower() if kw.isascii() else kw in q for kw in reminder_kw):
        return False
    # If we could infer arguments, no need to ask.
    return infer_remind_me_fallback(query) is None


def remind_me_clarification_question(query: str) -> Optional[str]:
    """
    When we can't infer when to remind, return a contextual question instead of a generic one.
    E.g. "15分钟后有个会，能提醒我一下吗" → "提前几分钟提醒你啊？"
    E.g. "儿子生日8月19号，提前提醒我" → "提前一周提醒你可以吗？" or "提前几天提醒你？"
    Returns None if no contextual question fits (Core can use generic "When would you like to be reminded?").
    """
    if not query or not isinstance(query, str):
        return None
    q = query.strip()
    if not q:
        return None
    # Event in N minutes but no "提前Y分钟" given → ask how many minutes before
    event_min_keywords = ("有个会", "开会", "meeting", "会议")
    has_min_event = any(kw in q if kw.isascii() else kw in q for kw in event_min_keywords)
    has_minutes = re.search(r"\d+\s*分钟", q) is not None
    has_before_min = re.search(r"提前\s*\d+\s*分钟", q) or re.search(r"\d+\s*(?:min|minutes?)\s+(?:before|in advance)", q, re.IGNORECASE)
    if has_min_event and has_minutes and not has_before_min:
        return "提前几分钟提醒你啊？ How many minutes before should I remind you?"
    # Date-like event (生日, 8月19号, etc.) + 提前提醒 but no "提前多久"
    date_keywords = ("生日", "月", "号", "日", "纪念日")
    has_date = any(kw in q for kw in date_keywords) and re.search(r"\d{1,2}\s*[月/]\s*\d{1,2}|生日|纪念", q)
    has_advance_days = re.search(r"提前\s*(?:一周|几天|\d+\s*天)", q)
    if has_date and ("提前" in q or "提醒" in q) and not has_advance_days:
        return "提前一周提醒你可以吗？或者提前几天？ Remind you one week before, or how many days before?"
    return None


def parse_raw_tool_calls_from_content(content: str):
    """
    If the LLM backend returned a raw tool_call in message content (e.g. <tool_call>{"name":..., "arguments":...}</tool_call>)
    instead of structured tool_calls, parse it so we can execute and avoid sending that raw text to the user.
    Returns list of OpenAI-style tool_call dicts (with id, function.name, function.arguments) or None if not detected / parse failed.
    """
    if not content or not isinstance(content, str):
        return None
    text = content.strip()
    if "<tool_call>" not in text and "</tool_call>" not in text:
        return None
    # Extract all <tool_call>...</tool_call> blocks (non-greedy)
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
