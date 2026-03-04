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

# Re-use single robust implementation for reminder inference (many NL styles/languages).
from core.tool_helpers_fallback import (
    infer_remind_me_fallback,
    remind_me_clarification_question,
    remind_me_needs_clarification,
)


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
