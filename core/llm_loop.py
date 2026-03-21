"""
LLM/tool loop: answer_from_memory implementation.
Extracted from core/core.py (Phase 6 refactor). Takes core as first argument; no import of core.core.
"""

import asyncio
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from base.base import PromptRequest, PluginResult
from base.prompt_manager import get_prompt_manager
from base.tools import ToolContext, get_tool_registry, ROUTING_RESPONSE_ALREADY_SENT
from base.util import Util, redact_params_for_log, strip_reasoning_from_assistant_text, _sanitize_tool_calls
from base.workspace import (
    get_workspace_dir,
    load_workspace,
    build_workspace_system_prefix,
    load_agent_memory_file,
    load_daily_memory_for_dates,
    trim_content_bootstrap,
    load_friend_identity_file,
)
from base.friend_presets import (
    get_tool_names_for_preset,
    get_tool_names_for_preset_value,
    get_friend_preset_config,
    trim_messages_to_last_n_turns,
)
from base.tool_profiles import get_tools_for_llm
from base.tools_rag import search_tools_by_query as tools_rag_search
from base.intent_router import (
    route as intent_router_route,
    get_tools_filter_for_category,
    get_tools_filter_for_categories,
    get_skills_filter_for_category,
    get_skills_filter_for_categories,
    verify_tool_selection as intent_verify_tool_selection,
    DEFAULT_VERIFY_TOOLS as INTENT_VERIFY_TOOLS_DEFAULT,
)
from base.planner_executor import (
    get_flow_for_categories,
    get_last_assistant_content,
    is_send_email_confirmation,
    parse_email_draft,
    parse_delayed_minutes,
    run_dag as dag_run_dag,
    run_planner as planner_run_planner,
    run_executor as planner_run_executor,
)
from base.skills import (
    get_all_skills_dirs,
    get_skills_dir,
    load_skills_from_dirs,
    load_skill_by_folder_from_dirs,
    build_skills_system_block,
)
from memory.prompts import RESPONSE_TEMPLATE
from memory.chat.message import ChatMessage

try:
    from memory import tam_storage as _tam_storage_module
except ImportError:
    _tam_storage_module = None


def _is_confirmation_phrase(text: str) -> bool:
    """True if the user message is a short confirmation (send, confirm, 确认, etc.) for delayed actions."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip().lower()
    if not t:
        return False
    return t in (
        "send", "confirm", "ok", "okay", "yes", "y", "发", "发吧", "发送", "批准",
        "确认", "好", "行", "可以", "同意",
    )


from tools.builtin import close_browser_session
from core.log_helpers import (
    _component_log,
    _truncate_for_log,
    _strip_leading_route_label,
    format_folder_list_file_find_result,
    format_json_for_user,
    format_web_search_result,
)


def _messages_sanitized_for_tool_role(messages: List[dict]) -> List[dict]:
    """
    Ensure every message with role 'tool' is preceded by an assistant message with 'tool_calls'.
    Some cloud APIs (e.g. DeepSeek) reject requests where a 'tool' message is not a response to
    a preceding message with 'tool_calls'. Strip any orphaned tool messages (e.g. after fallback
    when the assistant message lost tool_calls in serialization, or malformed history).
    Returns a new list; does not mutate the input.
    """
    if not messages or not isinstance(messages, list):
        return list(messages) if isinstance(messages, list) else []
    out: List[dict] = []
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            out.append(m)
            continue
        role = (m.get("role") or "").strip().lower()
        if role != "tool":
            out.append(m)
            continue
        # This message is role='tool'; the previous must be assistant with tool_calls
        prev = out[-1] if out else None
        if not isinstance(prev, dict):
            logger.debug("messages_sanitized: dropping orphan 'tool' message (no valid preceding assistant)")
            continue
        prev_role = (prev.get("role") or "").strip().lower()
        prev_tool_calls = prev.get("tool_calls") if isinstance(prev.get("tool_calls"), list) else []
        if prev_role == "assistant" and prev_tool_calls:
            out.append(m)
        elif prev_role == "tool":
            out.append(m)
        else:
            logger.debug(
                "messages_sanitized: dropping orphan 'tool' message (preceding role=%s has tool_calls=%s)",
                prev_role, bool(prev_tool_calls),
            )
    return out


# Tokens that suggest scheduling/reminder intent across languages (for logging when model didn't call a tool).
# Add tokens for new languages here; we only need a loose signal. Use lowercase for ASCII; CJK/others as-is.
_SCHEDULING_INTENT_TOKENS = (
    # Chinese
    "提醒", "每隔", "每小时", "个小时", "小时", "早上", "点", "每天", "定时", "预约", "问候",
    "喝水", "吃药", "能提醒", "帮我提醒", "到时提醒", "分钟后", "分钟",
    # English
    "remind", "every", "hour", "schedule", "recurring", "cron", "wake", "greet", "check in",
    "in 5 min", "in 10 min", "set a reminder", "set reminder",
    # Korean (remind, hour, daily, etc.)
    "알림", "알려", "시간", "매시간", "매일", "예약",
    # Japanese
    "リマインド", "毎時", "毎日", "予定", "予約", "通知",
    # Spanish / Portuguese
    "recordar", "recordarme", "cada hora", "recordar", "lembrar", "agendar",
    # German / French
    "erinnern", "stunde", "planen", "rappeler", "heure", "planifier",
)


def _query_looks_like_scheduling(q: Optional[str]) -> bool:
    """
    True if user message looks like a request for reminders or recurring schedule (for logging when model didn't call a tool).
    Uses a multilingual token list so we don't depend on one language. Why no schedule? The model chose to reply in
    text only instead of calling cron_schedule/remind_me/route_to_tam — often with soft phrasing ('可以嘛', '好呀')
    or ambiguous timing; strengthening the prompt or asking the user to rephrase can help.
    """
    if not q or not isinstance(q, str):
        return False
    s = q.strip()
    if len(s) < 3:
        return False
    s_lower = s.lower()
    for tok in _SCHEDULING_INTENT_TOKENS:
        if not tok:
            continue
        # ASCII tokens: case-insensitive; CJK/others: substring in original
        if tok.isascii():
            if tok in s_lower:
                return True
        else:
            if tok in s:
                return True
    # Digit + time-like: e.g. "4 hours", "每4小时", "8点"
    if re.search(r"\d+\s*(?:hours?|hour|小时|시간|時|点|點)", s, re.IGNORECASE):
        return True
    if re.search(r"(?:every|每|매)\s*\d+", s, re.IGNORECASE):
        return True
    return False


try:
    from core.services.tool_helpers import (
        tool_result_usable_as_final_response as _tool_result_usable_as_final_response,
        parse_raw_tool_calls_from_content as _parse_raw_tool_calls_from_content,
        infer_route_to_plugin_fallback as _infer_route_to_plugin_fallback,
        infer_remind_me_fallback as _infer_remind_me_fallback,
        infer_cron_schedule_fallback as _infer_cron_schedule_fallback,
        remind_me_needs_clarification as _remind_me_needs_clarification,
        remind_me_clarification_question as _remind_me_clarification_question,
    )
except (ImportError, ModuleNotFoundError):
    from core.tool_helpers_fallback import (
        tool_result_usable_as_final_response as _tool_result_usable_as_final_response,
        parse_raw_tool_calls_from_content as _parse_raw_tool_calls_from_content,
        infer_route_to_plugin_fallback as _infer_route_to_plugin_fallback,
        infer_remind_me_fallback as _infer_remind_me_fallback,
        infer_cron_schedule_fallback as _infer_cron_schedule_fallback,
        remind_me_needs_clarification as _remind_me_needs_clarification,
        remind_me_clarification_question as _remind_me_clarification_question,
    )


def _normalize_for_chat_match(text: str) -> str:
    """Normalize user message for accurate chat/shortcut matching: strip, remove trailing punctuation, collapse spaces. Never raises."""
    if not text or not isinstance(text, str):
        return ""
    s = text.strip()
    s = re.sub(r"[。！？!?.,，、\s]+$", "", s)  # trailing punctuation and spaces
    s = re.sub(r"^\s*[。！？!?.,，、]+", "", s)  # leading punctuation
    s = re.sub(r"\s+", " ", s).strip()  # collapse internal spaces
    return s


def _cursor_bridge_capability_and_params(query: str) -> tuple:
    """
    For Cursor preset: route message to the right bridge capability (no LLM).
    Supported phrasings:
    - open_project: "open X project", "open <path>", "open X in cursor"
    - open_file: "open file <path>"
    - run_command: "run npm/pip/pnpm/yarn/python/node/npx/cargo/go ...", "execute <command>"
    - run_agent: everything else (natural-language task, e.g. "fix the bug", "add unit tests")
    Returns (capability_id, parameters).
    """
    q = (query or "").strip()
    if not q:
        return "run_agent", {"task": q}
    q_lower = q.lower()
    # ---- status ----
    if q_lower in ("status", "cursor status", "current project", "current cwd", "which project", "what project", "active project"):
        return "get_status", {}
    # ---- open_project ----
    # "open X project" → path is X
    m = re.match(r"open\s+(.+?)\s+project\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "open_project", {"path": path}
    # "open <path>" where path contains / or \
    m = re.match(r"open\s+([^\s]+(?:[/\\][^\s]*)+)\s*$", q, re.IGNORECASE)
    if m:
        return "open_project", {"path": m.group(1).strip()}
    # "open X in cursor" / "open project X in cursor"
    m = re.match(r"open\s+(?:project\s+)?(.+?)\s+in\s+cursor\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "open_project", {"path": path}
    # ---- open_file ----
    m = re.match(r"open\s+file\s+(.+)\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "open_file", {"path": path}
    # ---- run_command (only when clearly a shell command: run/execute + npm|pip|... or short single token) ----
    run_command_prefixes = ("npm ", "pnpm ", "yarn ", "pip ", "python ", "node ", "npx ", "cargo ", "go ")
    if q_lower.startswith("run ") and len(q) > 4:
        rest = q[4:].strip()
        if any(rest.lower().startswith(p) for p in run_command_prefixes):
            return "run_command", {"command": rest}
        # "run ls", "run pwd", "run dotnet build" — single command, no "agent"/"cursor"
        if re.match(r"^[a-zA-Z0-9_.-]+\s*$", rest) or (len(rest) < 50 and "agent" not in rest.lower() and "cursor" not in rest.lower() and " the " not in rest.lower()):
            return "run_command", {"command": rest}
    if q_lower.startswith("execute ") and len(q) > 8:
        rest = q[8:].strip()
        if any(rest.lower().startswith(p) for p in run_command_prefixes):
            return "run_command", {"command": rest}
        if len(rest) < 50 and "agent" not in rest.lower() and " the " not in rest.lower():
            return "run_command", {"command": rest}
    if q_lower in (
        "clear cursor session",
        "new cursor session",
        "reset cursor session",
        "forget cursor session",
        "start fresh cursor session",
    ):
        return "clear_cursor_session", {}
    # ---- default: run_agent (natural-language task) ----
    return "run_agent", {"task": q}


def _trae_bridge_capability_and_params(query: str) -> tuple:
    """
    For Trae preset: route message to the Trae bridge capability (no LLM).
    Same patterns as Cursor but with "in trae": open_project, open_file, run_command, run_agent, get_status.
    """
    q = (query or "").strip()
    if not q:
        return "run_agent", {"task": q}
    q_lower = q.lower()
    if q_lower in ("status", "trae status", "current project", "current cwd", "which project", "what project", "active project"):
        return "get_status", {}
    m = re.match(r"open\s+(.+?)\s+project\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "open_project", {"path": path}
    m = re.match(r"open\s+([^\s]+(?:[/\\][^\s]*)+)\s*$", q, re.IGNORECASE)
    if m:
        return "open_project", {"path": m.group(1).strip()}
    m = re.match(r"open\s+(?:project\s+)?(.+?)\s+in\s+trae\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "open_project", {"path": path}
    m = re.match(r"open\s+file\s+(.+)\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "open_file", {"path": path}
    run_command_prefixes = ("npm ", "pnpm ", "yarn ", "pip ", "python ", "node ", "npx ", "cargo ", "go ")
    if q_lower.startswith("run ") and len(q) > 4:
        rest = q[4:].strip()
        if any(rest.lower().startswith(p) for p in run_command_prefixes):
            return "run_command", {"command": rest}
        if re.match(r"^[a-zA-Z0-9_.-]+\s*$", rest) or (len(rest) < 50 and "agent" not in rest.lower() and "trae" not in rest.lower() and " the " not in rest.lower()):
            return "run_command", {"command": rest}
    if q_lower.startswith("execute ") and len(q) > 8:
        rest = q[8:].strip()
        if any(rest.lower().startswith(p) for p in run_command_prefixes):
            return "run_command", {"command": rest}
        if len(rest) < 50 and "agent" not in rest.lower() and " the " not in rest.lower():
            return "run_command", {"command": rest}
    return "run_agent", {"task": q}


def _claude_bridge_capability_and_params(query: str) -> tuple:
    """
    For ClaudeCode preset: route message to the Claude bridge plugin (no LLM).
    - set_cwd: "open X project" / "open <path>" / "cd <path>"
    - get_status: "status", "current project"
    - run_command: "run <cmd>" / "execute <cmd>"
    - run_agent: everything else
    """
    q = (query or "").strip()
    if not q:
        return "run_agent", {"task": q}
    q_lower = q.lower()
    if q_lower in ("status", "claude status", "current project", "current cwd", "which project", "what project", "active project"):
        return "get_status", {}
    # set_cwd via "open project <path>" (e.g. "Open project D:\mygithub\summBox")
    m = re.match(r"open\s+project\s+(.+)\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "set_cwd", {"path": path}
    # set_cwd via "open X project" at end (e.g. "open my project")
    m = re.match(r"open\s+(.+?)\s+project\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "set_cwd", {"path": path}
    # set_cwd via "open <path>" where path contains / or \
    m = re.match(r"open\s+([^\s]+(?:[/\\][^\s]*)+)\s*$", q, re.IGNORECASE)
    if m:
        return "set_cwd", {"path": m.group(1).strip()}
    # set_cwd via "cd <path>"
    m = re.match(r"cd\s+(.+)\s*$", q, re.IGNORECASE)
    if m:
        path = m.group(1).strip()
        if path:
            return "set_cwd", {"path": path}
    # run_command (same heuristic as cursor)
    run_command_prefixes = ("npm ", "pnpm ", "yarn ", "pip ", "python ", "node ", "npx ", "cargo ", "go ")
    if q_lower.startswith("run ") and len(q) > 4:
        rest = q[4:].strip()
        if any(rest.lower().startswith(p) for p in run_command_prefixes):
            return "run_command", {"command": rest}
        if re.match(r"^[a-zA-Z0-9_.-]+\s*$", rest) or (len(rest) < 50 and " the " not in rest.lower()):
            return "run_command", {"command": rest}
    if q_lower.startswith("execute ") and len(q) > 8:
        rest = q[8:].strip()
        if any(rest.lower().startswith(p) for p in run_command_prefixes) or (len(rest) < 50 and " the " not in rest.lower()):
            return "run_command", {"command": rest}
    if q_lower in (
        "clear claude session",
        "new claude session",
        "reset claude session",
        "forget claude session",
        "start fresh claude session",
    ):
        return "clear_claude_session", {}
    return "run_agent", {"task": q}


def _try_chat_shortcut(query: str, shortcut_cfg: dict) -> Optional[str]:
    """
    If the query is a short greeting or capabilities question, return the shortcut reply (greeting_reply or identity+TOOLS). Otherwise return None.
    Used when intent_router is disabled (early) or when intent_router returned general_chat (chatting intent).
    """
    if not query or not isinstance(shortcut_cfg, dict) or not shortcut_cfg.get("enabled"):
        return None
    _q_norm = _normalize_for_chat_match(query)
    _greeting_max = max(0, int(shortcut_cfg.get("greeting_max_length", 20) or 20))
    _cap_max = max(0, int(shortcut_cfg.get("capabilities_max_length", 60) or 60))
    # Greeting
    _greeting_phrases = shortcut_cfg.get("greeting_phrases") or []
    if isinstance(_greeting_phrases, list) and _greeting_phrases and (_greeting_max == 0 or len(_q_norm) <= _greeting_max):
        _q_norm_lower = _q_norm.lower()
        for _gp in _greeting_phrases:
            if not isinstance(_gp, str):
                continue
            _g = _normalize_for_chat_match(_gp.strip())
            if not _g:
                continue
            if _q_norm == _g or _q_norm_lower == _g.lower():
                _reply = (shortcut_cfg.get("greeting_reply") or "").strip()
                if not _reply:
                    _reply = "你好！我是 HomeClaw，有什么可以帮你？ / Hello! I'm HomeClaw, how can I help?"
                logger.debug("Greeting shortcut: replying without main LLM (chat detected)")
                return _reply
    # Capabilities
    _phrases = shortcut_cfg.get("match_phrases") or []
    if isinstance(_phrases, list) and _phrases and (_cap_max == 0 or len(_q_norm) <= _cap_max):
        _q_lower = _q_norm.lower()
        for _p in _phrases:
            if not isinstance(_p, str) or not _p.strip():
                continue
            _p_strip = _normalize_for_chat_match(_p.strip())
            if not _p_strip:
                continue
            if _p_strip in _q_norm or _p_strip.lower() in _q_lower:
                try:
                    _ws_dir = get_workspace_dir(getattr(Util().core_metadata, "workspace_dir", None) or "config/workspace")
                    _workspace = load_workspace(_ws_dir)
                    _id_block = (_workspace.get("identity") or "").strip()
                    _tools_block = (_workspace.get("tools") or "").strip()
                    _parts = []
                    if _id_block:
                        _parts.append("## Identity\n" + _id_block)
                    if _tools_block:
                        _parts.append("## Tools / capabilities\n" + _tools_block)
                    if _parts:
                        logger.debug("Identity/capabilities shortcut: replying from workspace (chat detected)")
                        return "\n\n".join(_parts)
                except Exception as _e:
                    logger.debug("Identity/capabilities shortcut failed: {}; continuing normal flow", _e)
                break
    return None


async def answer_from_memory(
    core: Any,
    query: str,
    messages: Optional[List] = None,
    app_id: Optional[str] = None,
    user_name: Optional[str] = None,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    filters: Optional[dict] = None,
    limit: Optional[int] = 10,
    response_format: Optional[dict] = None,
    tools: Optional[List] = None,
    tool_choice: Optional[Union[str, dict]] = None,
    logprobs: Optional[bool] = None,
    top_logprobs: Optional[int] = None,
    parallel_tool_calls: Optional[bool] = None,
    deployment_id=None,
    extra_headers: Optional[dict] = None,
    functions: Optional[List] = None,
    function_call: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    request: Optional[PromptRequest] = None,
) -> Optional[tuple]:
    if messages is None:
        messages = []
    if not any([user_name, user_id, agent_id, run_id]):
        raise ValueError("One of user_name, user_id, agent_id, run_id must be provided")
    # Step 9: RAG/Cognee memory scope by (user_id, friend_id). Use friend_id from request for add/search.
    try:
        _mem_scope = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else (str(agent_id or "").strip() or "HomeClaw")
    except (TypeError, AttributeError):
        _mem_scope = "HomeClaw"
    uid = (user_id or getattr(request, "user_id", None) or "").strip() or "companion"
    # Delayed action confirm: if user says "confirm"/"发送"/"确认" and there is a pending scheduled action, schedule the one-shot and return.
    if _tam_storage_module and (query or "").strip() and _is_confirmation_phrase((query or "").strip()):
        try:
            action = _tam_storage_module.get_pending_confirmation_for_user(uid)
            if action:
                action_id = action.get("id")
                run_at = action.get("run_at")
                if action_id is not None and run_at is not None:
                    action_id_str = str(action_id).strip()
                    if action_id_str:
                        if hasattr(run_at, "strftime"):
                            run_at_str = run_at.strftime("%Y-%m-%d %H:%M:%S")
                            delta_mins = (run_at - datetime.now()).total_seconds() / 60
                        else:
                            s = str(run_at).strip()
                            run_at_str = s.replace("T", " ")[:19] if s else ""
                            delta_mins = 0
                        if run_at_str:
                            orchestrator = getattr(core, "orchestratorInst", None)
                            tam = getattr(orchestrator, "tam", None) if orchestrator else None
                            if tam and hasattr(tam, "schedule_one_shot"):
                                msg = _tam_storage_module.PENDING_ACTION_PREFIX + action_id_str + _tam_storage_module.PENDING_ACTION_SUFFIX
                                tam.schedule_one_shot(
                                    msg,
                                    run_at_str,
                                    user_id=action.get("user_id") or uid,
                                    channel_key=action.get("channel_key"),
                                    friend_id=action.get("friend_id"),
                                )
                                _tam_storage_module.mark_scheduled_action_scheduled(action_id_str)
                                n_mins = max(0, int(round(delta_mins)))
                                return (f"Scheduled. The action will run in {n_mins} minutes. （已安排。）", None)
        except Exception as _confirm_e:
            logger.debug("Delayed action confirm failed (non-fatal): {}", _confirm_e)
    try:
        # If user is replying to a "missing parameters" question, fill and retry the pending plugin call
        app_id_val = app_id or "homeclaw"
        user_id_val = user_id or ""
        session_id_val = session_id or ""
        pending = core.get_pending_plugin_call(app_id_val, user_id_val, session_id_val)
        if pending and (query or "").strip():
            missing = pending.get("missing") or []
            params = dict(pending.get("params") or {})
            if missing and len(missing) == 1:
                # Single missing param: use the user's message as the value
                name = missing[0]
                params[name] = query.strip()
                key = name.lower().replace(" ", "_")
                if key != name:
                    params[key] = query.strip()
                plugin_id = pending.get("plugin_id") or ""
                capability_id = pending.get("capability_id")
                plugin_manager = getattr(core, "plugin_manager", None)
                plugin = plugin_manager.get_plugin_by_id(plugin_id) if plugin_manager else None
                if plugin and isinstance(plugin, dict) and request:
                    core.clear_pending_plugin_call(app_id_val, user_id_val, session_id_val)
                    from base.base import PromptRequest, PluginResult
                    req_copy = request.model_copy(deep=True)
                    req_copy.request_metadata = dict(getattr(request, "request_metadata", None) or {})
                    req_copy.request_metadata["capability_id"] = capability_id
                    req_copy.request_metadata["capability_parameters"] = params
                    try:
                        result = await plugin_manager.run_external_plugin(plugin, req_copy)
                        if result is None:
                            return ("Done.", None)
                        if isinstance(result, PluginResult):
                            if not result.success:
                                return (result.error or result.text or "The action could not be completed.", None)
                            return (result.text or "Done.", None)
                        return (str(result) if result else "Done.", None)
                    except Exception as e:
                        logger.debug("Pending plugin retry failed: {}", e)
                        pending["params"] = params
                        core.set_pending_plugin_call(app_id_val, user_id_val, session_id_val, pending)
                elif not plugin:
                    core.clear_pending_plugin_call(app_id_val, user_id_val, session_id_val)

        # Unified workflow layer: if a tool previously returned need_input/need_confirmation, resume on user reply.
        pending_wf = core.get_pending_workflow(app_id_val, user_id_val, session_id_val)
        if isinstance(pending_wf, dict) and pending_wf and (query or "").strip():
            try:
                from core.workflow_result import (
                    parse_workflow_result,
                    is_confirm_reply,
                    STATUS_NEED_INPUT,
                    STATUS_NEED_CONFIRMATION,
                )
                status = (pending_wf.get("workflow_status") or "").strip().lower()
                if status == STATUS_NEED_INPUT:
                    missing = list(pending_wf.get("missing_fields") or [])
                    if missing and (pending_wf.get("resume_tool") or "").strip():
                        resume_tool = (pending_wf.get("resume_tool") or "").strip()
                        resume_args = dict(pending_wf.get("resume_args") or {})
                        name = missing[0]
                        resume_args[name] = (query or "").strip()
                        key = name.lower().replace(" ", "_")
                        if key != name:
                            resume_args[key] = (query or "").strip()
                        core.clear_pending_workflow(app_id_val, user_id_val, session_id_val)
                        _reg = get_tool_registry()
                        _ctx = ToolContext(
                            core=core,
                            app_id=app_id_val or "homeclaw",
                            user_name=user_name or "",
                            user_id=user_id_val or "",
                            system_user_id=getattr(request, "system_user_id", None) or user_id_val,
                            friend_id=(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"),
                            session_id=session_id_val or "",
                            run_id=run_id,
                            request=request,
                        )
                        _res = await _reg.execute_async(resume_tool, resume_args, _ctx)
                        _res_str = str(_res) if _res is not None else ""
                        _s2, _wf2 = parse_workflow_result(_res_str)
                        if _s2 in (STATUS_NEED_INPUT, STATUS_NEED_CONFIRMATION) and _wf2:
                            core.set_pending_workflow(app_id_val, user_id_val, session_id_val, {"workflow_status": _s2, **_wf2})
                            return ((_wf2.get("message") or _res_str or "Done.").strip(), None)
                        return (_res_str.strip() or "Done.", None)
                elif status == STATUS_NEED_CONFIRMATION:
                    if is_confirm_reply((query or "").strip()):
                        confirm_tool = (pending_wf.get("confirm_tool") or "").strip()
                        confirm_args = dict(pending_wf.get("confirm_args") or {})
                        if confirm_tool:
                            core.clear_pending_workflow(app_id_val, user_id_val, session_id_val)
                            _reg = get_tool_registry()
                            _ctx = ToolContext(
                                core=core,
                                app_id=app_id_val or "homeclaw",
                                user_name=user_name or "",
                                user_id=user_id_val or "",
                                system_user_id=getattr(request, "system_user_id", None) or user_id_val,
                                friend_id=(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"),
                                session_id=session_id_val or "",
                                run_id=run_id,
                                request=request,
                            )
                            _res = await _reg.execute_async(confirm_tool, confirm_args, _ctx)
                            return (str(_res).strip() if _res is not None else "Done.", None)
                    core.clear_pending_workflow(app_id_val, user_id_val, session_id_val)
            except Exception as _wf_e:
                logger.debug("Workflow resume failed (non-fatal): {}", _wf_e)
                core.clear_pending_workflow(app_id_val, user_id_val, session_id_val)

        # When intent_router is disabled, apply greeting/capabilities shortcut early (no LLM). When enabled, shortcut runs after intent router and only when category is general_chat (see below).
        _shortcut_cfg = getattr(Util().get_core_metadata(), "identity_capabilities_shortcut_config", None) or {}
        _intent_router_enabled = isinstance(getattr(Util().get_core_metadata(), "intent_router_config", None), dict) and (getattr(Util().get_core_metadata(), "intent_router_config", None) or {}).get("enabled")
        if not _intent_router_enabled and isinstance(_shortcut_cfg, dict) and _shortcut_cfg.get("enabled") and (query or "").strip():
            _early_reply = _try_chat_shortcut((query or "").strip(), _shortcut_cfg)
            if _early_reply is not None:
                return (_early_reply, None)

        # Hybrid router (mix mode): run before injecting tools, skills, plugins. Router uses only user message (query).
        effective_llm_name = None
        mix_route_this_request = None  # "local" | "cloud" when in mix mode; used for optional response label
        mix_route_layer_this_request = None  # which layer chose the route: heuristic, semantic, classifier, perplexity, default_route
        mix_show_route_label = False
        main_llm_mode = (getattr(Util().core_metadata, "main_llm_mode", None) or "").strip().lower()
        if main_llm_mode == "mix":
            _router_t0 = time.perf_counter()
            hr = getattr(Util().core_metadata, "hybrid_router", None) or {}
            default_route = (hr.get("default_route") or "local").strip().lower()
            if default_route not in ("local", "cloud"):
                default_route = "local"
            route = None
            route_layer = "default_route"
            # Vision override: if request has images and local model does not support image but cloud does, use cloud so we can understand the image.
            request_images = list(getattr(request, "images", None) or []) if request else []
            if request_images:
                local_ref = (getattr(Util().core_metadata, "main_llm_local", None) or "").strip()
                cloud_ref = (getattr(Util().core_metadata, "main_llm_cloud", None) or "").strip()
                local_media = Util().main_llm_supported_media_for_ref(local_ref) if local_ref else []
                cloud_media = Util().main_llm_supported_media_for_ref(cloud_ref) if cloud_ref else []
                if "image" not in local_media and "image" in cloud_media and cloud_ref:
                    route = "cloud"
                    route_layer = "vision_fallback"
                    logger.info("Mix mode: request has images; local does not support vision, using cloud for this request.")
            route_score = 0.0
            # Layer 1: heuristic (keywords, long-input); no threshold—first match wins when enabled (skip if already chose cloud for vision)
            heuristic_cfg = hr.get("heuristic") if isinstance(hr.get("heuristic"), dict) else {}
            h_enabled = bool(heuristic_cfg.get("enabled", False))
            if h_enabled and route is None:
                from hybrid_router.heuristic import load_heuristic_rules, run_heuristic_layer
                root_dir = Path(__file__).resolve().parent.parent
                rules_path = (heuristic_cfg.get("rules_path") or "").strip()
                rules_data = load_heuristic_rules(rules_path, root_dir=root_dir) if rules_path else None
                score, selection = run_heuristic_layer(query or "", rules_data, enabled=h_enabled)
                if selection:
                    route = selection
                    route_layer = "heuristic"
                    route_score = score
            # Layer 2: semantic (only when route not yet set, e.g. not overridden by vision_fallback).
            if route is None:
                semantic_cfg = hr.get("semantic") if isinstance(hr.get("semantic"), dict) else {}
                s_enabled = bool(semantic_cfg.get("enabled", False))
                s_threshold = float(semantic_cfg.get("threshold") or 0)
                if s_enabled and s_threshold > 0:
                    try:
                        from hybrid_router.semantic import (
                            build_semantic_router,
                            run_semantic_layer_async,
                            load_semantic_routes,
                        )
                        root_dir = Path(__file__).resolve().parent.parent
                        routes_path = (semantic_cfg.get("routes_path") or "").strip()
                        loc, cloud = load_semantic_routes(
                            routes_path=routes_path or None,
                            root_dir=root_dir,
                        )
                        router = build_semantic_router(
                            local_utterances=loc,
                            cloud_utterances=cloud,
                            routes_path=routes_path or None,
                            root_dir=root_dir,
                            use_cache=True,
                        )
                        score, selection = await run_semantic_layer_async(
                            query or "", router, threshold=s_threshold
                        )
                        if selection and score >= s_threshold:
                            route = selection
                            route_layer = "semantic"
                            route_score = score
                    except Exception as e:
                        logger.debug("Semantic router Layer 2 failed: {}", e)
            # Optional: long queries use default_route (only when route not yet set).
            if route is None:
                prefer_long = hr.get("prefer_cloud_if_long_chars")
                if prefer_long is not None and isinstance(prefer_long, (int, float)) and int(prefer_long) > 0:
                    if len((query or "")) > int(prefer_long):
                        route = default_route
                        route_layer = "default_route"
            # Layer 3: classifier (small model) or perplexity (main local model confidence probe)
            if route is None:
                slm_cfg = hr.get("slm") if isinstance(hr.get("slm"), dict) else {}
                slm_enabled = bool(slm_cfg.get("enabled", False))
                slm_mode = (slm_cfg.get("mode") or "classifier").strip().lower()
                slm_model_ref = (slm_cfg.get("model") or "").strip()
                if slm_enabled:
                    try:
                        if slm_mode == "perplexity":
                            # Probe main local model with logprobs; avg logprob >= perplexity_threshold → local
                            main_local_ref = (getattr(Util().core_metadata, "main_llm_local", None) or "").strip()
                            if main_local_ref:
                                from hybrid_router.perplexity import (
                                    run_perplexity_probe_async,
                                    resolve_local_model_ref,
                                )
                                host, port, raw_id = resolve_local_model_ref(main_local_ref)
                                if host is not None and port is not None and raw_id:
                                    probe_max = int(slm_cfg.get("perplexity_max_tokens") or 5)
                                    probe_threshold = float(slm_cfg.get("perplexity_threshold") or -0.6)
                                    score, selection = await run_perplexity_probe_async(
                                        query or "",
                                        host,
                                        port,
                                        raw_id,
                                        max_tokens=probe_max,
                                        threshold=probe_threshold,
                                        timeout_sec=5.0,
                                    )
                                    if selection:
                                        route = selection
                                        route_layer = "perplexity"
                                        route_score = score
                        else:
                            # Classifier: small model returns Local or Cloud; no threshold, we use its answer when valid
                            if slm_model_ref:
                                from hybrid_router.slm import run_slm_layer_async, resolve_slm_model_ref
                                host, port, _path_rel, raw_id = resolve_slm_model_ref(slm_model_ref)
                                if host is not None and port is not None and raw_id:
                                    score, selection = await run_slm_layer_async(
                                        query or "", host, port, raw_id
                                    )
                                    if selection:
                                        route = selection
                                        route_layer = "classifier"
                                        route_score = score
                    except Exception as e:
                        logger.debug("Layer 3 (slm) failed: {}", e)
            if route is None:
                route = default_route
            mix_route_this_request = route
            mix_route_layer_this_request = route_layer
            mix_show_route_label = bool(hr.get("show_route_in_response", False))
            if route == "local":
                effective_llm_name = (getattr(Util().core_metadata, "main_llm_local", None) or "").strip()
            else:
                effective_llm_name = (getattr(Util().core_metadata, "main_llm_cloud", None) or "").strip()
            if not effective_llm_name:
                effective_llm_name = None
            logger.info("Mix mode: route=%s (layer=%s)", route, route_layer)
            # Per-request log and aggregated counts (mix mode only)
            try:
                from hybrid_router.metrics import log_router_decision
                latency_ms = (time.perf_counter() - _router_t0) * 1000
                req_id = getattr(request, "request_id", None) if request else None
                log_router_decision(
                    route=route,
                    layer=route_layer,
                    score=route_score,
                    reason="",
                    request_id=req_id,
                    session_id=session_id,
                    latency_ms=latency_ms,
                )
            except Exception as e:
                logger.debug("Router metrics log failed: {}", e)

        use_memory = Util().has_memory()
        llm_input = []
        response = ''
        memory_turn_tool_messages = []  # collect tool name + result per turn for MemOS full-turn add (user+assistant+tool)
        system_parts = []
        force_include_instructions = []  # collected from skills_force_include_rules and plugins_force_include_rules; appended at end of system so model sees it last
        force_include_auto_invoke = []  # when model returns no tool_calls, run these (e.g. run_skill) so the skill runs anyway; each item: {"tool": str, "arguments": dict}
        force_include_plugin_ids = set()  # plugin ids to add to plugin list when skills_force_include_rules match (optional "plugins" in rule)
        _injected_skill_folders = []  # skill folder names in prompt; used to constrain run_skill skill_name to enum (Phase 1.1)
        _document_read_forced_path = None  # when user message contains explicit path (e.g. documents/norm-v4.pdf), override first document_read(path) to this

        # Resolve current user once: used to decide workspace Identity vs who-based identity and for who injection.
        _sys_uid = getattr(request, "system_user_id", None) or user_id
        _companion_with_who = False
        _current_user_for_identity = None
        _current_friend = None  # When set, identity block is built from friend (who + optional identity file)
        try:
            if _sys_uid:
                _users = Util().get_users() or []
                _current_user_for_identity = next(
                    (u for u in _users if (getattr(u, "id", None) or getattr(u, "name", "") or "").strip().lower() == str(_sys_uid or "").strip().lower()),
                    None,
                )
                _req_fid = (str(getattr(request, "friend_id", None) or "").strip().lower()) or "homeclaw"
                _friends = getattr(_current_user_for_identity, "friends", None) if _current_user_for_identity else []
                if isinstance(_friends, list):
                    _current_friend = next(
                        (f for f in _friends if (getattr(f, "name", "") or "").strip().lower() == _req_fid),
                        None,
                    )
                if _current_friend and (getattr(_current_friend, "name", "") or "").strip().lower() != "homeclaw":
                    _fwho = getattr(_current_friend, "who", None)
                    _fident = getattr(_current_friend, "identity", None)
                    if (isinstance(_fwho, dict) and _fwho) or _fident is not None:
                        _companion_with_who = True
                elif _current_user_for_identity and str(getattr(_current_user_for_identity, "type", "normal") or "normal").strip().lower() == "companion":
                    _who = getattr(_current_user_for_identity, "who", None)
                    if isinstance(_who, dict) and _who:
                        _companion_with_who = True
        except Exception:
            pass

        # Friend preset (Step 5): model_routing local_only — in cloud-only mode refuse; in mix mode force local for this friend.
        if _current_friend:
            try:
                preset_name = (getattr(_current_friend, "preset", None) or "").strip()
                if preset_name:
                    preset_cfg = get_friend_preset_config(preset_name)
                    if isinstance(preset_cfg, dict) and str(preset_cfg.get("model_routing") or "").strip().lower() == "local_only":
                        if main_llm_mode == "cloud":
                            return ("This friend is configured to use only a local model. Please switch to local or mix mode in Core settings to use it.", None)
                        if main_llm_mode == "mix" and effective_llm_name:
                            main_llm_cloud = (getattr(Util().core_metadata, "main_llm_cloud", None) or "").strip()
                            if main_llm_cloud and effective_llm_name == main_llm_cloud:
                                main_llm_local = (getattr(Util().core_metadata, "main_llm_local", None) or "").strip()
                                if main_llm_local:
                                    effective_llm_name = main_llm_local
                                    logger.debug("Friend preset local_only: forcing local model for this friend.")
            except Exception:
                pass

        # Cursor/ClaudeCode preset friends: pure bridge — no LLM. Route by pattern then call the bridge plugin.
        if request and _current_friend and (query or "").strip():
            try:
                _preset = (getattr(_current_friend, "preset", None) or "").strip().lower()
                if _preset in ("cursor", "claudecode", "trae"):
                    if _preset == "trae" and not getattr(Util().core_metadata, "trae_agent_enabled", False):
                        return (
                            "Trae Agent is disabled. Set trae_agent_enabled: true in config/skills_and_plugins.yml (and restart Core) to register the Trae Bridge and use preset: trae.",
                            None,
                        )
                    if _preset == "cursor":
                        _plugin_id = "cursor-bridge"
                        _cap, _params = _cursor_bridge_capability_and_params((query or "").strip())
                        _yo = getattr(request, "cursor_agent_yolo", None)
                        if _yo is not None and _cap == "run_agent":
                            _params = {**dict(_params), "yolo": bool(_yo)}
                    elif _preset == "claudecode":
                        _plugin_id = "claude-code-bridge"
                        _cap, _params = _claude_bridge_capability_and_params((query or "").strip())
                        _csp = getattr(request, "claude_skip_permissions", None)
                        if _csp is not None and _cap == "run_agent":
                            _params = {**dict(_params), "skip_permissions": bool(_csp)}
                    else:
                        _plugin_id = "trae-bridge"
                        _cap, _params = _trae_bridge_capability_and_params((query or "").strip())
                    _q = (query or "").strip()
                    _reg = get_tool_registry()
                    if _reg:
                        _ctx = ToolContext(
                            core=core,
                            app_id=app_id or "homeclaw",
                            user_name=user_name,
                            user_id=user_id,
                            system_user_id=getattr(request, "system_user_id", None) or user_id,
                            friend_id=(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"),
                            session_id=session_id,
                            run_id=run_id,
                            request=request,
                        )
                        _bridge_result = await _reg.execute_async(
                            "route_to_plugin",
                            {
                                "plugin_id": _plugin_id,
                                "capability_id": _cap,
                                "parameters": _params,
                            },
                            _ctx,
                        )
                        if _bridge_result == ROUTING_RESPONSE_ALREADY_SENT:
                            return (ROUTING_RESPONSE_ALREADY_SENT, None)
                        if isinstance(_bridge_result, str) and _bridge_result.strip():
                            return (_bridge_result.strip(), None)
                        return ("Done.", None)
            except Exception as _cursor_bridge_e:
                logger.debug("Cursor bridge failed: {}", _cursor_bridge_e)

        # Workspace bootstrap (identity / agents / tools). When companion user has "who", skip workspace Identity so we inject only who-based identity below.
        if getattr(Util().core_metadata, 'use_workspace_bootstrap', True):
            ws_dir = get_workspace_dir(getattr(Util().core_metadata, 'workspace_dir', None) or 'config/workspace')
            workspace = load_workspace(ws_dir)
            workspace_prefix = build_workspace_system_prefix(workspace, skip_identity=_companion_with_who)
            if workspace_prefix:
                system_parts.append(workspace_prefix)

        # Companion identity (who): from friend (who + optional identity file) or legacy companion user who. Replaces default assistant description.
        if _companion_with_who and _current_user_for_identity:
            try:
                _who = None
                _name = getattr(_current_user_for_identity, "name", "") or _sys_uid or ""
                if _current_friend and (getattr(_current_friend, "name", "") or "").strip().lower() != "homeclaw":
                    _who = getattr(_current_friend, "who", None)
                    _name = (getattr(_current_friend, "name", "") or "").strip() or _name
                if _who is None:
                    _who = getattr(_current_user_for_identity, "who", None)
                _has_who = isinstance(_who, dict) and _who
                _friend_identity = _current_friend and getattr(_current_friend, "identity", None) is not None
                if _has_who or _friend_identity:
                    _lines = ["## Identity\n"]
                    if _has_who:
                        _desc = (_who.get("description") or "").strip() if isinstance(_who.get("description"), str) else ""
                        if _desc:
                            _lines.append(_desc)
                        _lines.append(f"You are {_name}.")
                        if _who.get("gender"):
                            _lines.append(f"Gender: {_who.get('gender')}.")
                        if _who.get("roles"):
                            _roles = _who["roles"] if isinstance(_who["roles"], list) else [_who["roles"]] if _who.get("roles") else []
                            if _roles:
                                _lines.append(f"Roles: {', '.join(str(r) for r in _roles)}.")
                        if _who.get("personalities"):
                            _pers = _who["personalities"] if isinstance(_who["personalities"], list) else [_who["personalities"]] if _who.get("personalities") else []
                            if _pers:
                                _lines.append(f"Personalities: {', '.join(str(p) for p in _pers)}.")
                        if _who.get("language"):
                            _lines.append(f"Reply in language: {_who.get('language')}.")
                        if _who.get("response_length"):
                            _rl = str(_who.get("response_length", "")).strip().lower()
                            if _rl == "short":
                                _lines.append("Keep replies brief: one or two sentences unless the user asks for more.")
                            elif _rl == "long":
                                _lines.append("You may reply at length when the topic deserves it; be thorough but natural.")
                            else:
                                _lines.append("Keep replies to a short paragraph unless the user asks for more or less.")
                    else:
                        _lines.append(f"You are {_name}.")
                    _lines.append("Stay in character and chat as a human would: natural, conversational, and in-person. Do not say you are an AI, assistant, or language model; do not break character to explain how you work. Reply only as this person would reply.")
                    if _friend_identity:
                        _hroot = (Util().get_core_metadata().get_homeclaw_root() or "").strip()
                        if _hroot:
                            _ident_content = load_friend_identity_file(
                                _hroot,
                                _sys_uid,
                                (getattr(_current_friend, "name", "") or "").strip() or "HomeClaw",
                                getattr(_current_friend, "identity", None),
                                max_chars=12000,
                            )
                            if _ident_content:
                                _lines.append("")
                                _lines.append(_ident_content)
                    system_parts.append("\n".join(_lines) + "\n\n")
                else:
                    # Default HomeClaw: no custom who/identity — give a minimal identity line so the model can generate greetings by itself (name + reply in user's language).
                    _default_name = (getattr(_current_friend, "name", "") or "").strip() or "HomeClaw"
                    system_parts.append(
                        f"## Identity\nYou are {_default_name}, a friendly home assistant. When the user greets you (e.g. 你好, hi, hello), reply naturally and briefly in their language. Do not mix grammar across languages.\n\n"
                    )
            except Exception as e:
                logger.debug("Companion identity (who) inject failed: {}", e)

        # System context: current date/time (system timezone) + optional location. Built here but appended at END of system_parts so the prefix (identity, tools, instructions) is static for KV cache reuse (cache_prompt: true). See SystemContextDateTimeAndLocation.md.
        _system_context_block = None
        try:
            now = datetime.now()
            try:
                now = datetime.now().astimezone()
            except Exception:
                pass
            date_str = now.strftime("%Y-%m-%d")
            time_24 = now.strftime("%H:%M")  # 24-hour, no AM/PM ambiguity
            dow = now.strftime("%A")
            datetime_line = f"{date_str} {time_24}"  # single canonical form so model does not invent 26号 15:49 or 2026-1月 3号
            # Chinese form so model uses correct day when saying "当前是X号" (e.g. 26号 not 19号)
            m, d = int(now.strftime("%m")), int(now.strftime("%d"))
            month_day_cn = f"{m}月{d}日"
            day_num_cn = str(d)
            ctx_line = f"Current date: {date_str}. Day of week: {dow}. Current time: {time_24} (24-hour, system local). Current datetime (use this only, never invent): {datetime_line}. 今日（中文）：{month_day_cn}，{day_num_cn}号。回复中提及「今天」「当前是」时只使用此日期（如 当前是{day_num_cn}号）。"
            core._request_current_time_24 = time_24  # so routing block can inject it; model must use this, not invent 2:49 etc.
            core._request_current_datetime_line = datetime_line  # inject again next to last user message so model does not use chat history time
            loc_str = None
            try:
                meta = request.request_metadata if getattr(request, "request_metadata", None) else {}
                loc_str = (meta.get("location") or "").strip() if isinstance(meta, dict) else None
                if not loc_str and user_id:
                    loc_str = core._get_latest_location(user_id)
                if not loc_str and user_id:
                    profile_cfg = getattr(Util().get_core_metadata(), "profile", None) or {}
                    if isinstance(profile_cfg, dict) and profile_cfg.get("enabled", True):
                        try:
                            from base.profile_store import get_profile
                            profile_base_dir = (profile_cfg.get("dir") or "").strip() or None
                            profile_data = get_profile(user_id or "", base_dir=profile_base_dir)
                            if isinstance(profile_data, dict) and profile_data.get("location"):
                                loc_str = str(profile_data.get("location", "")).strip()
                        except Exception:
                            pass
                if not loc_str:
                    loc_str = (getattr(Util().get_core_metadata(), "default_location", None) or "").strip() or None
                # When Companion app did not combine to any user, location is stored under shared key; use as fallback for all users
                if not loc_str:
                    shared_key = getattr(core, "_LATEST_LOCATION_SHARED_KEY", "companion")
                    loc_str = core._get_latest_location(shared_key)
                if loc_str:
                    ctx_line += f" User location: {loc_str[:500]}."
            except Exception as e:
                logger.debug("System context location resolve: {}", e)
            ctx_line += "\nCritical for cron jobs and reminders: this current datetime is the single source of truth. The server uses it when scheduling; you must use it for all time calculations. Do not use any other time (e.g. from memory or prior turns—they may be outdated). Use this block only when the user explicitly asks (e.g. \"what day is it?\", \"what time is it?\", scheduling with remind_me, record_date, cron_schedule). Do not volunteer date/time in greetings. For any reminder or schedule request (in any wording), you MUST call the tool (remind_me, cron_schedule, or record_date)—replying with text only does not create a reminder. For reminders and cron: use ONLY the Current time above; do not invent or guess any time (e.g. never output 26号 15:49, 明天下午7点, 2026-1月 3号, or 2:49 PM). If the user says \"in N minutes\", reminder time = Current time + N minutes (e.g. Current time 17:58 + 30 min = 18:28). For remind_me(message=...): do NOT put any date or time inside the message; use a short label only (e.g. 会议提醒, Reminder: meeting)."
            _system_context_block = "## System context (date/time and location)\n" + ctx_line + "\n\n"
        except Exception as e:
            logger.debug("System context block failed: {}", e)
            try:
                fallback = f"Current date: {date.today().isoformat()}."
                _system_context_block = "## System context\n" + fallback + "\n\n"
                # Still set a minimal datetime line so prepend and routing blocks can use it
                core._request_current_datetime_line = getattr(core, "_request_current_datetime_line", None) or date.today().isoformat() + " 00:00"
            except Exception:
                pass

        # Friend preset (Step 4): resolve memory_sources so we can skip agent/daily/cognee when preset restricts.
        _preset_allow_agent_memory = True
        _preset_allow_daily_memory = True
        _preset_allow_cognee = True
        if _current_friend:
            try:
                preset_name = (getattr(_current_friend, "preset", None) or "").strip()
                if preset_name:
                    preset_cfg = get_friend_preset_config(preset_name)
                    if isinstance(preset_cfg, dict) and "memory_sources" in preset_cfg:
                        src = preset_cfg.get("memory_sources")
                        if isinstance(src, (list, tuple)):
                            src_set = {str(x).strip().lower() for x in src if x is not None}
                            _preset_allow_agent_memory = "agent_memory" in src_set or "md" in src_set
                            _preset_allow_daily_memory = "daily_memory" in src_set or "md" in src_set
                            _preset_allow_cognee = "cognee" in src_set
            except Exception:
                pass

        # Agent memory: when use_agent_memory_search is true, leverage retrieval only (no bulk inject). Otherwise inject capped AGENT_MEMORY + optional daily block.
        # When memory_flush_primary is true (default), only the dedicated flush turn writes memory; main prompt does not ask the model to call append_*.
        try:
            _compaction_cfg = getattr(Util().get_core_metadata(), "compaction", None) or {}
            if not isinstance(_compaction_cfg, dict):
                _compaction_cfg = {}
            _memory_flush_primary = bool(_compaction_cfg.get("memory_flush_primary", True))
        except Exception:
            _compaction_cfg = {}
            _memory_flush_primary = True
        try:
            use_agent_memory_search = getattr(Util().core_metadata, "use_agent_memory_search", True)
        except Exception:
            use_agent_memory_search = True
        if use_agent_memory_search:
            # Retrieval-first: do not inject AGENT_MEMORY or daily content; inject a strong directive to use tools.
            try:
                directive = (
                    "## Agent memory (bootstrap + tools)\n"
                    "A capped bootstrap of AGENT_MEMORY.md and daily memory is included below. "
                    "For more detail or when answering about prior work, decisions, dates, people, preferences, or todos: "
                    "run agent_memory_search with a relevant query; then use agent_memory_get to pull the needed lines. "
                    "If low confidence after search, say you checked. "
                    "This curated agent memory is authoritative when it conflicts with RAG context below."
                )
                use_agent_file = getattr(Util().core_metadata, "use_agent_memory_file", True) and _preset_allow_agent_memory
                use_daily = getattr(Util().core_metadata, "use_daily_memory", True) and _preset_allow_daily_memory
                if _memory_flush_primary:
                    directive += " Durable and daily memory are written in a dedicated step; you do not need to call append_agent_memory or append_daily_memory in this conversation."
                elif use_agent_file or use_daily:
                    directive += " When useful, write to memory: "
                    if use_agent_file:
                        directive += "use append_agent_memory for lasting facts or preferences the user wants to remember (e.g. 'remember that', 'my preference is'). "
                    if use_daily:
                        directive += "Use append_daily_memory for short-term notes (e.g. what was discussed today, session summary)."
                system_parts.append(directive + "\n\n")
                # OpenClaw-style bootstrap: inject a capped chunk of AGENT_MEMORY + daily so memory is always in context (not only when the model calls tools)
                if use_agent_file or use_daily:
                    try:
                        meta_mem = Util().get_core_metadata()
                        main_llm_mode = (getattr(meta_mem, "main_llm_mode", None) or "").strip().lower()
                        main_llm_local = (getattr(meta_mem, "main_llm_local", None) or "").strip()
                        use_local_cap = (
                            main_llm_mode == "mix"
                            and main_llm_local
                            and effective_llm_name == main_llm_local
                        )
                        bootstrap_max = (
                            max(500, int(getattr(meta_mem, "agent_memory_bootstrap_max_chars_local", 8000) or 8000))
                            if use_local_cap
                            else max(500, int(getattr(meta_mem, "agent_memory_bootstrap_max_chars", 20000) or 20000))
                        )
                        ws_dir = get_workspace_dir(getattr(meta_mem, "workspace_dir", None) or "config/workspace")
                        _sys_uid_bootstrap = getattr(request, "system_user_id", None) or user_id if request else user_id
                        _fid = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"
                        parts_bootstrap = []
                        if use_agent_file:
                            agent_raw = load_agent_memory_file(
                                workspace_dir=ws_dir,
                                agent_memory_path=getattr(meta_mem, "agent_memory_path", None) or None,
                                max_chars=0,
                                system_user_id=_sys_uid_bootstrap,
                                friend_id=_fid,
                            )
                            if agent_raw and agent_raw.strip():
                                parts_bootstrap.append("## Agent memory (bootstrap)\n\n" + agent_raw.strip())
                        if use_daily:
                            today = date.today()
                            yesterday = today - timedelta(days=1)
                            daily_dir = (getattr(meta_mem, "daily_memory_dir", None) or "").strip() or None
                            daily_raw = load_daily_memory_for_dates(
                                [yesterday, today],
                                workspace_dir=ws_dir,
                                daily_memory_dir=daily_dir,
                                max_chars=0,
                                system_user_id=_sys_uid_bootstrap,
                                friend_id=_fid,
                            )
                            if daily_raw and daily_raw.strip():
                                parts_bootstrap.append("## Daily memory (bootstrap)\n\n" + daily_raw.strip())
                        if parts_bootstrap:
                            combined = "\n\n".join(parts_bootstrap)
                            trimmed = trim_content_bootstrap(combined, bootstrap_max)
                            if trimmed and trimmed.strip():
                                system_parts.append(trimmed.strip() + "\n\n")
                                _component_log("agent_memory", f"injected bootstrap (cap={bootstrap_max}, local_cap={use_local_cap})")
                    except Exception as e:
                        logger.debug("Agent/daily memory bootstrap inject failed: {}", e)
            except Exception as e:
                logger.warning("Skipping agent memory directive due to error: {}", e, exc_info=False)
        else:
            # Legacy: inject AGENT_MEMORY content (capped) and optionally daily memory.
            if _preset_allow_agent_memory and getattr(Util().core_metadata, 'use_agent_memory_file', True):
                try:
                    ws_dir = get_workspace_dir(getattr(Util().core_metadata, 'workspace_dir', None) or 'config/workspace')
                    agent_path = getattr(Util().core_metadata, 'agent_memory_path', None) or ''
                    max_chars = max(0, int(getattr(Util().core_metadata, 'agent_memory_max_chars', 20000) or 0))
                    _sys_uid_legacy = getattr(request, "system_user_id", None) if request else None
                    _fid_legacy = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"
                    agent_content = load_agent_memory_file(
                        workspace_dir=ws_dir, agent_memory_path=agent_path or None, max_chars=max_chars, system_user_id=_sys_uid_legacy, friend_id=_fid_legacy
                    )
                    if agent_content:
                        system_parts.append(
                            "## Agent memory (curated)\n" + agent_content + "\n\n"
                            "When both this section and the RAG context below mention the same fact, prefer this curated agent memory as authoritative.\n\n"
                        )
                    if not _memory_flush_primary:
                        system_parts.append("You can add lasting facts or preferences with append_agent_memory when the user says to remember something.\n\n")
                except Exception as e:
                    logger.warning("Skipping AGENT_MEMORY.md injection due to error: {}", e, exc_info=False)

            # Daily memory (memory/YYYY-MM-DD.md): yesterday + today; only when not using retrieval-first.
            if _preset_allow_daily_memory and getattr(Util().core_metadata, 'use_daily_memory', True):
                try:
                    today = date.today()
                    yesterday = today - timedelta(days=1)
                    ws_dir = get_workspace_dir(getattr(Util().core_metadata, 'workspace_dir', None) or 'config/workspace')
                    daily_dir = getattr(Util().core_metadata, 'daily_memory_dir', None) or ''
                    _sys_uid_daily = getattr(request, "system_user_id", None) if request else None
                    _fid_daily = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"
                    daily_content = load_daily_memory_for_dates(
                        [yesterday, today],
                        workspace_dir=ws_dir,
                        daily_memory_dir=daily_dir if daily_dir else None,
                        max_chars=80_000,
                        system_user_id=_sys_uid_daily,
                        friend_id=_fid_daily,
                    )
                    if daily_content:
                        system_parts.append("## Recent (daily memory)\n" + daily_content + "\n\n")
                    if not _memory_flush_primary:
                        system_parts.append("You can add to today's daily memory with append_daily_memory when useful (e.g. session summary, today's context).\n\n")
                except Exception as e:
                    logger.warning("Skipping daily memory injection due to error: {}", e, exc_info=False)

        # Phase 3: call intent router once early so we can filter both skills (3.1) and tools by category.
        _intent_router_category = None
        _intent_router_config = getattr(Util().get_core_metadata(), "intent_router_config", None) or {}
        if not isinstance(_intent_router_config, dict):
            _intent_router_config = {}
        if _intent_router_config.get("enabled") and (query or "").strip():
            try:
                _ir_timeout = max(0, int(_intent_router_config.get("timeout_seconds", 25) or 25))
                _route_coro = intent_router_route(
                    query=(query or "").strip(),
                    config=_intent_router_config,
                    completion_fn=core,
                    llm_name=None,
                    recent_messages=messages if isinstance(messages, list) else None,
                )
                if _ir_timeout > 0:
                    _intent_router_category = await asyncio.wait_for(_route_coro, timeout=float(_ir_timeout))
                else:
                    _intent_router_category = await _route_coro
                _component_log("intent_router", f"category={_intent_router_category}")
            except asyncio.TimeoutError:
                logger.warning("Intent router timed out ({}s); fallback general_chat", _intent_router_config.get("timeout_seconds", 25))
                _intent_router_category = "general_chat"
            except Exception as _e:
                logger.debug("Intent router failed (early): {}; fallback general_chat", _e)
                _intent_router_category = "general_chat"
        # Parse comma-separated categories for multi-category tasks (union of tools/skills).
        _intent_router_categories = [
            c.strip() for c in ((_intent_router_category or "").split(","))
            if (c or "").strip()
        ] if _intent_router_category else []

        # When intent router says general_chat (chatting intent), apply shortcut so greeting/capabilities skip the main LLM.
        _general_chat_norm = "general_chat"
        if _intent_router_categories and any((c or "").strip().lower() == _general_chat_norm for c in _intent_router_categories):
            _shortcut_cfg_ir = getattr(Util().get_core_metadata(), "identity_capabilities_shortcut_config", None) or {}
            if isinstance(_shortcut_cfg_ir, dict) and _shortcut_cfg_ir.get("enabled") and (query or "").strip():
                _chat_reply = _try_chat_shortcut((query or "").strip(), _shortcut_cfg_ir)
                if _chat_reply is not None:
                    return (_chat_reply, None)

        # Planner–Executor: when enabled and category not in skip list, use planner path (Phase 2+). Never crash on config.
        try:
            _planner_executor_config = getattr(Util().get_core_metadata(), "planner_executor_config", None) or {}
            if not isinstance(_planner_executor_config, dict):
                _planner_executor_config = {}
        except Exception:
            _planner_executor_config = {}
        try:
            _skip_list = _planner_executor_config.get("skip_planner_for_categories")
            _skip_planner_cats = {str(x).strip().lower() for x in (_skip_list if isinstance(_skip_list, (list, tuple)) else []) if x is not None}
        except Exception:
            _skip_planner_cats = set()
        _use_planner_executor = bool(_planner_executor_config.get("enabled")) and bool(_intent_router_categories) and not any(
            (c or "").strip().lower() in _skip_planner_cats for c in _intent_router_categories
        )

        # Skills (SKILL.md from skills_dir + skills_extra_dirs); skills_disabled excluded
        if getattr(Util().core_metadata, 'use_skills', True):
            try:
                root = Path(__file__).resolve().parent.parent
                meta_skills = Util().core_metadata
                skills_dirs = get_all_skills_dirs(
                    getattr(meta_skills, 'skills_dir', None) or 'skills',
                    (getattr(meta_skills, 'external_skills_dir', None) or "").strip(),
                    getattr(meta_skills, 'skills_extra_dirs', None) or [],
                    root,
                )
                disabled_folders = getattr(meta_skills, 'skills_disabled', None) or []
                skills_list = []
                use_vector_search = bool(getattr(meta_skills, 'skills_use_vector_search', False))
                if not use_vector_search:
                    # skills_use_vector_search=false means include ALL skills (no RAG, no cap)
                    skills_list = load_skills_from_dirs(skills_dirs, disabled_folders=disabled_folders, include_body=False)
                    if skills_list:
                        _component_log("skills", f"included all {len(skills_list)} skill(s) (skills_use_vector_search=false)")
                if not skills_list and use_vector_search and getattr(core, 'skills_vector_store', None) and getattr(core, 'embedder', None):
                    from base.skills import search_skills_by_query, load_skill_by_folder, TEST_ID_PREFIX
                    max_retrieved = max(1, min(100, int(getattr(meta_skills, 'skills_max_retrieved', 10) or 10)))
                    threshold = float(getattr(meta_skills, 'skills_similarity_threshold', 0.0) or 0.0)
                    hits = await search_skills_by_query(
                        core.skills_vector_store, core.embedder, query or "",
                        limit=max_retrieved, min_similarity=threshold,
                    )
                    skills_test_dir_str = (getattr(meta_skills, 'skills_test_dir', None) or "").strip()
                    skills_test_path = get_skills_dir(skills_test_dir_str, root=root) if skills_test_dir_str else None
                    for item in (hits or []):
                        try:
                            if not isinstance(item, (list, tuple)) or len(item) < 2:
                                continue
                            hit_id, _ = item[0], item[1]
                        except (TypeError, IndexError, ValueError):
                            continue
                        if hit_id.startswith(TEST_ID_PREFIX):
                            load_path = skills_test_path if skills_test_path and skills_test_path.is_dir() else None
                            folder_name = hit_id[len(TEST_ID_PREFIX):]
                            skill_dict = load_skill_by_folder(load_path, folder_name, include_body=False) if load_path else None
                        else:
                            folder_name = hit_id
                            skill_dict = load_skill_by_folder_from_dirs(skills_dirs, folder_name, include_body=False)
                        if skill_dict is None:
                            try:
                                core.skills_vector_store.delete(hit_id)
                            except Exception:
                                pass
                            continue
                        skills_list.append(skill_dict)
                    if skills_list:
                        _component_log("skills", f"retrieved {len(skills_list)} skill(s) by vector search")
                    skills_max = max(0, int(getattr(meta_skills, 'skills_max_in_prompt', 5) or 5))
                    if skills_max > 0 and len(skills_list) > skills_max:
                        skills_list = skills_list[:skills_max]
                        _component_log("skills", f"capped to {skills_max} skill(s) after threshold (skills_max_in_prompt)")
                if not skills_list:
                    # RAG returned nothing; fallback: load all skills from disk
                    skills_list = load_skills_from_dirs(skills_dirs, disabled_folders=disabled_folders, include_body=False)
                    if skills_list:
                        _component_log("skills", f"loaded {len(skills_list)} skill(s) from disk (RAG had no hits)")
                # Special cases only: force-include rules (e.g. reminder, scheduling) and skill-driven triggers add skills/auto_invoke when query matches. For all other cases the LLM decides whether to use run_skill from the available skills list.
                matched_instructions = []
                skills_list = skills_list or []
                q = (query or "").strip().lower()
                folders_present = {s.get("folder") for s in skills_list if isinstance(s, dict)}
                for rule in (getattr(meta_skills, "skills_force_include_rules", None) or []):
                    if not isinstance(rule, dict):
                        continue
                    # Support single "pattern" (str) or "patterns" (list) for multi-language / general matching
                    patterns = rule.get("patterns")
                    if patterns is None and rule.get("pattern") is not None:
                        patterns = [rule.get("pattern")]
                    pattern = rule.get("pattern")
                    folders = rule.get("folders")
                    folders = list(folders) if isinstance(folders, (list, tuple)) else []
                    if not patterns and not pattern:
                        continue
                    to_try = list(patterns) if patterns else ([pattern] if pattern else [])
                    matched_rule = False
                    for pat in to_try:
                        if not pat or not isinstance(pat, str):
                            continue
                        try:
                            if re.search(pat, q):
                                matched_rule = True
                                break
                        except re.error:
                            continue
                    if not matched_rule:
                        continue
                    for folder in folders:
                        folder = str(folder).strip()
                        if not folder or folder in folders_present:
                            continue
                        skill_dict = load_skill_by_folder_from_dirs(skills_dirs, folder, include_body=False)
                        if skill_dict:
                            skills_list = [skill_dict] + [s for s in skills_list if s.get("folder") != folder]
                            folders_present.add(folder)
                            _component_log("skills", f"included {folder} for force-include rule")
                    instr = rule.get("instruction") if isinstance(rule, dict) else None
                    if instr and isinstance(instr, str) and instr.strip():
                        matched_instructions.append(instr.strip())
                    auto_invoke = rule.get("auto_invoke") if isinstance(rule, dict) else None
                    if isinstance(auto_invoke, dict) and auto_invoke.get("tool") and isinstance(auto_invoke.get("arguments"), dict):
                        args = dict(auto_invoke["arguments"])
                        user_q = (query or "").strip()

                        def _replace_query_in_obj(obj):
                            if isinstance(obj, str):
                                return obj.replace("{{query}}", user_q) if "{{query}}" in obj else obj
                            if isinstance(obj, dict):
                                return {k: _replace_query_in_obj(v) for k, v in obj.items()}
                            if isinstance(obj, list):
                                return [_replace_query_in_obj(s) for s in obj]
                            return obj

                        args = _replace_query_in_obj(args)
                        always_run = bool(rule.get("always_run", False))
                        force_include_auto_invoke.append({
                            "tool": str(auto_invoke["tool"]).strip(),
                            "arguments": args,
                            "always_run": always_run,
                        })
                    # Optional: when this rule matches, also force-include these plugins in the plugin list (so model sees them for route_to_plugin)
                    plugins_in_rule = rule.get("plugins") if isinstance(rule, dict) else None
                    if isinstance(plugins_in_rule, (list, tuple)):
                        for pid in plugins_in_rule:
                            pid = str(pid).strip().lower().replace(" ", "_")
                            if pid:
                                force_include_plugin_ids.add(pid)
                # Skill-driven triggers: declare trigger.patterns + instruction + auto_invoke in each skill's SKILL.md; no need to repeat in core.yml
                for skill_dict in load_skills_from_dirs(skills_dirs, disabled_folders=disabled_folders, include_body=False):
                    if not isinstance(skill_dict, dict):
                        continue
                    trigger = skill_dict.get("trigger") if isinstance(skill_dict.get("trigger"), dict) else None
                    if not isinstance(trigger, dict):
                        continue
                    patterns = trigger.get("patterns")
                    if not patterns and trigger.get("pattern"):
                        patterns = [trigger.get("pattern")]
                    if not patterns or not isinstance(patterns, (list, tuple)):
                        continue
                    matched_trigger = False
                    for pat in patterns:
                        if not pat or not isinstance(pat, str):
                            continue
                        try:
                            if re.search(pat, q):
                                matched_trigger = True
                                break
                        except re.error:
                            continue
                    if not matched_trigger:
                        continue
                    folder = (skill_dict.get("folder") or skill_dict.get("name") or "").strip()
                    if not folder:
                        continue
                    if folder not in folders_present:
                        skills_list = [skill_dict] + [s for s in skills_list if s.get("folder") != folder]
                        folders_present.add(folder)
                        _component_log("skills", f"included {folder} for skill trigger")
                    instr = trigger.get("instruction")
                    if isinstance(instr, str) and instr.strip():
                        matched_instructions.append(instr.strip())
                    auto_invoke = trigger.get("auto_invoke")
                    if isinstance(auto_invoke, dict) and auto_invoke.get("script"):
                        user_q = (query or "").strip()
                        args = list(auto_invoke.get("args") or [])
                        args = [s.replace("{{query}}", user_q) if isinstance(s, str) else s for s in args]
                        force_include_auto_invoke.append({
                            "tool": "run_skill",
                            "arguments": {"skill_name": folder, "script": str(auto_invoke["script"]).strip(), "args": args},
                        })
                # Built-in "list folder" intent: when user asks for local files/folders (e.g. "list documents", "list images", "what files in X"),
                # add folder_list to force_include_auto_invoke. Images are files; "list images" = list the images folder, same as "list documents".
                # We use fallbacks as little as possible; when intent is clearly local files, we only run folder_list/file_find (no web_search).
                _list_folder_phrases = (
                    "documents folder", "files in documents", "what files in", "in the documents", "list documents",
                    "list file", "list files", "list directory", "list folder", "what's in my", "files in my",
                    "folder content", "folder list", "目录", "哪些文件", "列出文件", "目录下", "有什么文件", "文件列表",
                    "list images", "search images", "image files", "图片", "列出图片", "搜索图片", "我的图片", "local images", "my images",
                )
                _q_lo = (query or "").strip().lower()
                _q_raw = (query or "").strip()
                if any((p in _q_lo if p.isascii() else p in _q_raw) for p in _list_folder_phrases):
                    _sandbox_subdirs = ("documents", "downloads", "output", "images", "work", "knowledge", "share")
                    _inferred_path = "."
                    for _key in _sandbox_subdirs:
                        if _key in _q_lo or _key in _q_raw:
                            _inferred_path = _key
                            break
                    force_include_auto_invoke.append({
                        "tool": "folder_list",
                        "arguments": {"path": _inferred_path},
                        "always_run": True,
                    })
                if use_vector_search:
                    skills_max = max(0, int(getattr(meta_skills, "skills_max_in_prompt", 5) or 5))
                    if skills_max > 0 and len(skills_list) > skills_max:
                        skills_list = skills_list[:skills_max]
                # Friend preset (Step 3): restrict skills to preset's list when preset has "skills" as list (including []).
                if _current_friend and skills_list:
                    try:
                        preset_name = (getattr(_current_friend, "preset", None) or "").strip()
                        if preset_name:
                            preset_cfg = get_friend_preset_config(preset_name)
                            if isinstance(preset_cfg, dict) and "skills" in preset_cfg:
                                allowed = preset_cfg.get("skills")
                                if isinstance(allowed, (list, tuple)):
                                    allowed_set = {str(x).strip().lower() for x in allowed if x is not None and str(x).strip()}
                                    skills_list = [
                                        s for s in skills_list
                                        if ((s.get("folder") or s.get("name") or "").strip().lower() in allowed_set)
                                    ]
                                    _component_log("friend_preset", f"filtered skills to preset list ({len(skills_list)} skills)")
                    except Exception as e:
                        logger.debug("Friend preset skills filter failed: {}", e)
                # OpenClaw-style skills_filter: when set, only these skill folders are in the prompt.
                _skills_filter = getattr(meta_skills, "skills_filter", None) or []
                if _skills_filter and skills_list:
                    allowed_folders = {str(f).strip().lower() for f in _skills_filter if f and str(f).strip()}
                    if allowed_folders:
                        skills_list = [
                            s for s in skills_list
                            if ((s.get("folder") or s.get("name") or "").strip().lower() in allowed_folders)
                        ]
                        _component_log("skills_filter", f"filtered to {len(skills_list)} skill(s)")
                # Phase 3.1: if router provided a category with category_skills, filter skills so skill_name enum matches router output.
                # Multi-category: when router returns comma-separated categories, use union of skills from all.
                if _intent_router_categories and skills_list:
                    try:
                        if len(_intent_router_categories) > 1:
                            _cat_skills = get_skills_filter_for_categories(_intent_router_config, _intent_router_categories)
                        elif len(_intent_router_categories) == 1 and _intent_router_categories[0]:
                            _cat_skills = get_skills_filter_for_category(_intent_router_config, (_intent_router_categories[0] or "").strip())
                        else:
                            _cat_skills = None
                        if _cat_skills:
                            _allowed_skill_folders = {str(s).strip().lower() for s in _cat_skills if s is not None and str(s).strip()}
                            if _allowed_skill_folders:
                                _new_list = []
                                for s in skills_list:
                                    if not isinstance(s, dict):
                                        _new_list.append(s)
                                        continue
                                    folder = (s.get("folder") or s.get("name") or "").strip().lower()
                                    if folder in _allowed_skill_folders:
                                        _new_list.append(s)
                                skills_list = _new_list
                                _component_log("intent_router", f"filtered skills by category: {len(skills_list)} skill(s)")
                    except Exception as _e:
                        logger.debug("Phase 3.1 category skills filter failed: {}", _e)
                # Phase 1.1: list of skill folder names in prompt; used to constrain run_skill skill_name to enum when building tools for LLM.
                _injected_skill_folders = [
                    (s.get("folder") or s.get("name") or "").strip()
                    for s in (skills_list or [])
                    if isinstance(s, dict) and ((s.get("folder") or s.get("name") or "").strip())
                ]
                # Skills list is built from RAG/load + force-include (e.g. reminder/scheduling). LLM decides when to call run_skill; we only force-include for special cases.
                if skills_list:
                    selected_names = [s.get("folder") or s.get("name") or "?" for s in skills_list]
                    _component_log("skills", f"selected: {', '.join(selected_names)}")
                # OpenClaw-style: when skills_use_location_only is true, inject only name + description + location; model reads SKILL.md via file_read(path='skill:folder') to reduce context tokens.
                use_location_only = bool(getattr(meta_skills, "skills_use_location_only", False))
                _body_for_raw = getattr(meta_skills, "skills_include_body_for", None)
                include_body_for = list(_body_for_raw) if isinstance(_body_for_raw, (list, tuple)) else []
                body_max_chars = max(0, int(getattr(meta_skills, "skills_include_body_max_chars", 0) or 0))
                if not use_location_only and include_body_for:
                    for i, s in enumerate(skills_list):
                        folder = (s.get("folder") or "").strip()
                        if folder and folder in include_body_for:
                            full_skill = load_skill_by_folder_from_dirs(
                                skills_dirs, folder, include_body=True, body_max_chars=body_max_chars
                            )
                            if full_skill:
                                skills_list[i] = full_skill
                include_body = bool(include_body_for) and not use_location_only
                skills_block = build_skills_system_block(skills_list, include_body=include_body, use_location_only=use_location_only)
                if skills_block:
                    system_parts.append(skills_block)
                    # Hint so the model can suggest installing more skills via HomeClaw (Companion, Portal, or converter script).
                    system_parts.append(
                        "When no available skill fits the user's request, suggest they can search and install more skills using HomeClaw: "
                        "Companion app (Settings → Skills), Portal (Skills), or the Python script scripts/convert_openclaw_skill.py to convert an OpenClaw skill folder to HomeClaw (output to external_skills). New skills are loaded on next session."
                    )
                elif not skills_list:
                    # use_skills is true but no skills loaded yet: still hint that user can add skills.
                    system_parts.append(
                        "No skills are loaded yet. If the user needs a capability you don't have, suggest they can add skills via "
                        "the Companion app (Settings → Skills), Portal (Skills), or scripts/convert_openclaw_skill.py to convert an OpenClaw skill folder."
                    )
                force_include_instructions.extend(matched_instructions)
            except Exception as e:
                logger.warning("Failed to load skills: {}", e)

        if use_memory:
            if _preset_allow_cognee:
                relevant_memories = await core._fetch_relevant_memories(query,
                    messages, user_name, user_id, _mem_scope, run_id, filters, 10
                )
                # Optional: sort by newest first so "1" in the prompt is most recent (default is relevance order from vector search).
                try:
                    _mem_order = getattr(Util().get_core_metadata(), "memory_context_order", None) or "relevance"
                    if _mem_order == "newest_first" and relevant_memories:
                        def _ts_key(m):
                            ca = m.get("created_at") if isinstance(m, dict) else None
                            if ca is None:
                                return (1, 0)
                            if hasattr(ca, "timestamp"):
                                return (0, -ca.timestamp())
                            if isinstance(ca, (int, float)):
                                return (0, -float(ca))
                            return (1, 0)
                        relevant_memories = sorted(relevant_memories or [], key=_ts_key)
                except Exception as _e:
                    logger.debug("memory_context_order sort failed (non-fatal): {}", _e)
                memories_text = ""
                if relevant_memories:
                    i = 1
                    for memory in (relevant_memories or []):
                        if not isinstance(memory, dict):
                            continue
                        mem_text = memory.get("memory") or ""
                        memories_text += (str(i) + ": " + str(mem_text) + " ")
                        logger.debug("RelevantMemory: {} : {}", i, (str(mem_text)[:80] + "..." if len(str(mem_text)) > 80 else str(mem_text)))
                        i += 1
                else:
                    memories_text = ""
            else:
                memories_text = ""
            context_val = memories_text if memories_text else "None."
            # Optional: inject knowledge base (documents, web, URLs) — only chunks that pass threshold; none is fine
            kb = getattr(core, "knowledge_base", None)
            meta = Util().get_core_metadata()
            kb_cfg = getattr(meta, "knowledge_base", None) or {}
            if kb and (user_id or user_name):
                try:
                    kb_timeout = 10
                    try:
                        kb_results = await asyncio.wait_for(
                            kb.search(user_id=(user_id or user_name or ""), query=(query or ""), limit=5, friend_id=_mem_scope),
                            timeout=kb_timeout,
                        )
                    except TypeError:
                        kb_results = await asyncio.wait_for(
                            kb.search(user_id=(user_id or user_name or ""), query=(query or ""), limit=5),
                            timeout=kb_timeout,
                        )
                    # Filter by similarity threshold (0-1, higher = more relevant); none left is fine
                    retrieval_min_score = kb_cfg.get("retrieval_min_score")
                    if retrieval_min_score is not None:
                        try:
                            min_s = float(retrieval_min_score)
                            kb_results = [r for r in (kb_results or []) if r.get("score") is not None and float(r["score"]) >= min_s]
                        except (TypeError, ValueError):
                            pass
                    if kb_results:
                        kb_lines = [f"- [{r.get('source_type', '')}] {r.get('content', '')[:1500]}" for r in kb_results]
                        system_parts.append("## Knowledge base (from your saved documents/web/notes)\n" + "\n\n".join(kb_lines))
                except asyncio.TimeoutError:
                    logger.debug("Knowledge base search timed out")
                except Exception as e:
                    logger.debug("Knowledge base search failed: {}", e)
            # Per-user profile: inject "About the user" only when active friend is HomeClaw (UserFriendsModelFullDesign.md Step 4)
            meta = Util().get_core_metadata()
            profile_cfg = getattr(meta, "profile", None) or {}
            _fid_for_profile = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"
            if profile_cfg.get("enabled", True) and (user_id or user_name) and _fid_for_profile == "HomeClaw":
                try:
                    from base.profile_store import get_profile, format_profile_for_prompt
                    profile_base_dir = (profile_cfg.get("dir") or "").strip() or None
                    profile_data = get_profile(user_id or user_name or "", base_dir=profile_base_dir)
                    if profile_data:
                        profile_text = format_profile_for_prompt(profile_data, max_chars=2000)
                        if profile_text:
                            system_parts.append("## About the user\n" + profile_text)
                except Exception as e:
                    logger.debug("Profile load for prompt failed: {}", e)
            meta = Util().get_core_metadata()
            if getattr(meta, "use_prompt_manager", False):
                try:
                    pm = get_prompt_manager(
                        prompts_dir=getattr(meta, "prompts_dir", None),
                        default_language=getattr(meta, "prompt_default_language", "en"),
                        cache_ttl_seconds=float(getattr(meta, "prompt_cache_ttl_seconds", 0) or 0),
                    )
                    lang = Util().main_llm_language()
                    prompt = pm.get_content("chat", "response", lang=lang, context=context_val)
                except Exception as e:
                    logger.debug("Prompt manager fallback for chat/response: {}", e)
                    prompt = None
            else:
                prompt = None
            if not prompt or not prompt.strip():
                prompt = RESPONSE_TEMPLATE.format(context=context_val)
            system_parts.append(prompt)
            # Language and format: use main_llm_languages so reply matches user and stays direct
            allowed = Util().main_llm_languages()
            if allowed:
                lang_list = ", ".join(allowed)
                system_parts.append(
                    f"## Response language and format\n"
                    f"Respond only in one of these languages: {lang_list}. Prefer the same language as the user's message (e.g. if the user writes in Chinese, respond in Chinese; if in English, respond in English). "
                    f"Output only your direct reply to the user. Do not explain your response, translate it, or add commentary (e.g. do not say \"The user said...\", \"My response was...\", or \"which translates to...\")."
                )

        unified = (
            getattr(Util().get_core_metadata(), "orchestrator_unified_with_tools", True)
            and getattr(Util().get_core_metadata(), "use_tools", True)
        )
        if unified and getattr(core, "plugin_manager", None):
            plugin_list = []
            meta_plugins = Util().get_core_metadata()
            use_plugin_vector_search = bool(getattr(meta_plugins, "plugins_use_vector_search", False))
            if not use_plugin_vector_search:
                # plugins_use_vector_search=false → include ALL plugins (no RAG, no cap)
                plugin_list = getattr(core.plugin_manager, "get_plugin_list_for_prompt", lambda: [])()
                if plugin_list:
                    _component_log("plugin", f"included all {len(plugin_list)} plugin(s) (plugins_use_vector_search=false)")
            if use_plugin_vector_search and getattr(core, "plugins_vector_store", None) and getattr(core, "embedder", None):
                from base.plugins_registry import search_plugins_by_query
                max_retrieved = max(1, min(100, int(getattr(meta_plugins, "plugins_max_retrieved", 10) or 10)))
                threshold = float(getattr(meta_plugins, "plugins_similarity_threshold", 0.0) or 0.0)
                try:
                    hits = await search_plugins_by_query(
                        core.plugins_vector_store, core.embedder, query or "",
                        limit=max_retrieved, min_similarity=threshold,
                    )
                    desc_max_rag = max(0, int(getattr(meta_plugins, "plugins_description_max_chars", 0) or 0))
                    for hit_id, _ in hits:
                        plug = core.plugin_manager.get_plugin_by_id(hit_id)
                        if plug is None:
                            continue
                        if isinstance(plug, dict):
                            pid = (plug.get("id") or hit_id).strip().lower().replace(" ", "_")
                            desc_raw = (plug.get("description") or "").strip()
                        else:
                            pid = getattr(plug, "plugin_id", None) or hit_id
                            desc_raw = (plug.get_description() or "").strip()
                        desc = desc_raw[:desc_max_rag] if desc_max_rag > 0 else desc_raw
                        plugin_list.append({"id": pid, "description": desc})
                    if plugin_list:
                        _component_log("plugin", f"retrieved {len(plugin_list)} plugin(s) by vector search")
                    plugins_max = max(0, int(getattr(Util().get_core_metadata(), "plugins_max_in_prompt", 5) or 5))
                    if plugins_max > 0 and len(plugin_list) > plugins_max:
                        plugin_list = plugin_list[:plugins_max]
                        _component_log("plugin", f"capped to {plugins_max} plugin(s) after threshold (plugins_max_in_prompt)")
                except Exception as e:
                    logger.warning("Plugin vector search failed: {}", e)
            if not plugin_list and use_plugin_vector_search:
                # RAG returned nothing; fallback: include all plugins, then cap
                plugin_list = getattr(core.plugin_manager, "get_plugin_list_for_prompt", lambda: [])()
                if plugin_list:
                    _component_log("plugin", f"loaded {len(plugin_list)} plugin(s) from registry (RAG had no hits)")
                plugins_max = max(0, int(getattr(Util().get_core_metadata(), "plugins_max_in_prompt", 5) or 5))
                if plugins_max > 0 and len(plugin_list) > plugins_max:
                    plugin_list = plugin_list[:plugins_max]
            # Config-driven force-include: when user query matches a rule pattern, ensure those plugins are in the list and optionally collect an instruction
            plugin_force_instructions = []
            if plugin_list is not None:
                q = (query or "").strip().lower()
                ids_present = {str(p.get("id") or "").strip().lower().replace(" ", "_") for p in plugin_list}
                for rule in (getattr(meta_plugins, "plugins_force_include_rules", None) or []):
                    pattern = rule.get("pattern") if isinstance(rule, dict) else None
                    plugins_in_rule = rule.get("plugins") if isinstance(rule, dict) else None
                    if not pattern or not plugins_in_rule or not isinstance(plugins_in_rule, (list, tuple)):
                        continue
                    try:
                        if not re.search(pattern, q):
                            continue
                    except re.error:
                        continue
                    desc_max_rag = max(0, int(getattr(meta_plugins, "plugins_description_max_chars", 0) or 0))
                    for pid in plugins_in_rule:
                        pid = str(pid).strip().lower().replace(" ", "_")
                        if not pid or pid in ids_present:
                            continue
                        plug = core.plugin_manager.get_plugin_by_id(pid)
                        if plug is None:
                            continue
                        if isinstance(plug, dict):
                            desc_raw = (plug.get("description") or "").strip()
                        else:
                            desc_raw = (getattr(plug, "get_description", lambda: "")() or "").strip()
                        desc = desc_raw[:desc_max_rag] if desc_max_rag > 0 else desc_raw
                        plugin_list = [{"id": pid, "description": desc}] + [p for p in plugin_list if (p.get("id") or "").strip().lower().replace(" ", "_") != pid]
                        ids_present.add(pid)
                        _component_log("plugin", f"included {pid} for force-include rule")
                    instr = rule.get("instruction") if isinstance(rule, dict) else None
                    if instr and isinstance(instr, str) and instr.strip():
                        plugin_force_instructions.append(instr.strip())
                # Plugins from skills_force_include_rules (rule has optional "plugins: [id, ...]"); ensure they are in the list
                desc_max_rag = max(0, int(getattr(meta_plugins, "plugins_description_max_chars", 0) or 0))
                for pid in force_include_plugin_ids:
                    if not pid or pid in ids_present:
                        continue
                    plug = core.plugin_manager.get_plugin_by_id(pid)
                    if plug is None:
                        continue
                    if isinstance(plug, dict):
                        desc_raw = (plug.get("description") or "").strip()
                    else:
                        desc_raw = (getattr(plug, "get_description", lambda: "")() or "").strip()
                    desc = desc_raw[:desc_max_rag] if desc_max_rag > 0 else desc_raw
                    plugin_list = [{"id": pid, "description": desc}] + [p for p in plugin_list if (p.get("id") or "").strip().lower().replace(" ", "_") != pid]
                    ids_present.add(pid)
                    _component_log("plugin", f"included {pid} for skills_force_include_rules (plugins)")
                if use_plugin_vector_search:
                    plugins_max = max(0, int(getattr(meta_plugins, "plugins_max_in_prompt", 5) or 5))
                    if plugins_max > 0 and len(plugin_list) > plugins_max:
                        plugin_list = plugin_list[:plugins_max]
                # Friend preset (Step 3): restrict plugins to preset's list when preset has "plugins" as list (including []).
                if _current_friend and plugin_list is not None:
                    try:
                        preset_name = (getattr(_current_friend, "preset", None) or "").strip()
                        if preset_name:
                            preset_cfg = get_friend_preset_config(preset_name)
                            if isinstance(preset_cfg, dict) and "plugins" in preset_cfg:
                                allowed = preset_cfg.get("plugins")
                                if isinstance(allowed, (list, tuple)):
                                    allowed_set = {str(x).strip().lower().replace(" ", "_") for x in allowed if x is not None and str(x).strip()}
                                    plugin_list = [
                                        p for p in plugin_list
                                        if (p.get("id") or "").strip().lower().replace(" ", "_") in allowed_set
                                    ]
                                    _component_log("friend_preset", f"filtered plugins to preset list ({len(plugin_list)} plugins)")
                    except Exception as e:
                        logger.debug("Friend preset plugins filter failed: {}", e)
            plugin_lines = []
            if plugin_list:
                desc_max = max(0, int(getattr(Util().get_core_metadata(), "plugins_description_max_chars", 0) or 0))
                def _desc(d: str) -> str:
                    s = d or ""
                    return s[:desc_max] if desc_max > 0 else s
                plugin_lines = [f"  - {p.get('id', '') or 'plugin'}: {_desc(p.get('description'))}" for p in plugin_list]
            _req_time_24 = getattr(core, "_request_current_time_24", "") or ""
            # Qwen: llm.yml → llama_cpp.qwen_mode only. qwen3/qwen35 -> <tool_call> format + NO_TOOL_REQUIRED; qwen35 uses dedicated block + optional grammar.
            tool_format_line = ""
            try:
                meta = Util().get_core_metadata()
                llama_cpp = getattr(meta, "llama_cpp", None) if meta is not None else None
                if not isinstance(llama_cpp, dict):
                    llama_cpp = {}
                qwen_model = Util._get_qwen_model()
                qwen3_style = qwen_model in ("qwen3", "qwen35") or bool(llama_cpp.get("qwen3_tool_format_instruction"))
                if qwen_model == "qwen35":
                    tool_format_line = (
                        "<tools> Output one or more tool calls per turn when the task needs multiple steps (e.g. document_read then save_result_page). "
                        "Exact format required (the system only parses these): "
                        "JSON: <tool_call>{\"name\": \"tool_name\", \"arguments\": {\"key\": \"value\"}}</tool_call> "
                        "or XML: <tool_call><function>tool_name</function><key>value</key></tool_call>. "
                        "Example: <tool_call>{\"name\": \"time\", \"arguments\": {}}</tool_call> or <tool_call><function>folder_list</function><path>.</path></tool_call>. "
                        "Use <function> for the tool name in XML (not <tool>). Use JSON \"arguments\" or XML child tags; do NOT use (key=value) or (text=\"...\") syntax. Always close with </tool_call>. "
                        "When you call a tool, you MUST output the <tool_call>...</tool_call> block in your response content (the main message body) so the system can parse and execute it—do not put only reasoning or narrative text like \"I'll call folder_list\"; output the actual <tool_call> block. "
                        "If NO tool matches the user's intent, respond with plain text only—do NOT output any <tool_call>. "
                        "For simple greetings (e.g. 你好, hello, hi, 嗨, thanks, 谢谢) or short identity/thanks: reply directly in your message content with a short friendly response—do NOT call any tool. "
                        "When the user asks what you can do, your capabilities, or 你能为我做什么/你能做什么, answer with plain text only from your role and system prompt—do not call any tool (no agent_memory_search or other tools for capability questions). "
                        "Never output <tool_call> with empty name or mix <response> or other tags with <tool_call>. Do not invent parameters. No <think> or conversational text.</tools>\n"
                    )
                elif qwen3_style:
                    tool_format_line = (
                        "Tool calls: one or more per turn when needed. Exact format (system only parses these): "
                        "JSON <tool_call>{\"name\": \"tool_name\", \"arguments\": {\"key\": \"value\"}}</tool_call> or "
                        "XML <tool_call><function>tool_name</function><key>value</key></tool_call>. "
                        "Example: <tool_call>{\"name\": \"time\", \"arguments\": {}}</tool_call>. Use <function> in XML (not <tool>); use JSON/XML for arguments, not (key=value). Always close with </tool_call>. "
                        "When you call a tool, output the <tool_call>...</tool_call> block in your response content (main message body), not only in reasoning—the system parses it from content to execute the tool. "
                        "If NO tool matches the user's intent, respond with plain text only—do NOT output <tool_call>. For simple greetings (你好, hello, hi, 谢谢) or short thanks: reply directly in message content—do not call any tool. For capability questions (你能为我做什么, what can you do), answer in plain text only—do not call any tool. Never use empty name or mix other tags. "
                        "Do not invent or guess parameters for tools that do not fit.\n"
                    )
            except Exception:
                pass
            # When the user only said a short greeting, tell the model explicitly: reply with text only, no tools, no invented follow-up requests.
            _greeting_only = False
            if isinstance(query, str) and len(query.strip()) <= 30:
                _q = query.strip().lower()
                _q_raw = query.strip()
                _greeting_phrases = ("你好", "hi", "hello", "嗨", "hey", "thanks", "谢谢", "thank you", "help", "哈喽")
                if any((p in _q if p.isascii() else p in _q_raw) for p in _greeting_phrases) and not any(c in _q_raw for c in ("?", "？", "吗", "什么", "怎么", "how", "what", "why", "can you", "帮我")):
                    _greeting_only = True
            _greeting_instruction = ""
            if _greeting_only:
                _greeting_instruction = (
                    "**This turn:** The user message is only a short greeting (e.g. 你好, hello). "
                    "Reply with a brief friendly greeting in your message content only. Do NOT call any tool. "
                    "Do NOT invent or act on hypothetical user requests (e.g. do not say \"I want to make a presentation\" and then call run_skill).\n\n"
                )
            routing_block = (
                _greeting_instruction
                + "## Routing (choose one)\n"
                + tool_format_line
                + "Do NOT use route_to_tam for: opening URLs, listing nodes, canvas, camera/video on a node, or any non-scheduling request. Use route_to_plugin for those.\n"
                "Recording a video or taking a photo on a node (e.g. \"record video on test-node-1\", \"take a photo on test-node-1\") -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=node_camera_clip or node_camera_snap, parameters={\"node_id\": \"<node_id>\"}; for clip add duration and includeAudio). Do NOT use browser_navigate for node ids; test-node-1 is a node id, not a URL.\n"
                "Opening a URL in a browser (real web URLs only, e.g. https://example.com) -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=browser_navigate, parameters={\"url\": \"<URL>\"}). Node ids like test-node-1 are NOT URLs.\n"
                "Listing connected nodes or \"what nodes are connected\" -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=node_list).\n"
                "If the request clearly matches one of the available plugins below, call route_to_plugin with that plugin_id (and capability_id/parameters when relevant).\n"
                "Rule (scheduling): For any reminder or schedule request—in any wording or language (e.g. \"提醒我\", \"remind me\", \"7分钟后喝水\", \"in 10 minutes\", \"every day at 9\")—you MUST call the tool (remind_me, cron_schedule, or record_date). Replying with text only does NOT create a reminder; the user will not be notified. Always invoke the tool in this turn.\n"
                "For time-related requests: one-shot reminders -> remind_me(minutes or at_time, message); recording a date/event -> record_date(event_name, when); recurring -> cron_schedule(cron_expr, message). Use route_to_tam only when the user clearly asks to schedule or remind.\n"
                f"When the user asks to be reminded in N minutes (any phrasing: \"N分钟后\", \"N分钟提醒\", \"remind me in N minutes\", \"in N min\"), you MUST call remind_me with minutes=N (use the number from the user's message) and message= a short label only (e.g. \"喝水\", \"会议提醒\"; do NOT put date/time in message). Current time: {_req_time_24}. Use only this time; never invent times (e.g. never 2:49 PM, 明天下午7点).\n"
                "For script-based workflows use run_skill(skill_name, script, ...). For instruction-only skills (no scripts/) use run_skill(skill_name) with no script—then you MUST continue in the same turn (document_read, generate content, file_write or save_result_page, return link); do not reply with only the confirmation. skill_name can be folder or short name (e.g. html-slides).\n"
                "When the user asks to generate an HTML slide or report from a document/file: (1) call document_read(path) to get the file content, (2) use that returned text as the source and generate the full HTML yourself, (3) call save_result_page(title=..., content=<your generated full HTML>, format='html') so the user gets a view link. You MUST call save_result_page—do NOT return the raw HTML in your message. The user must receive the link (e.g. /files/out?token=...) so they can open the slides; returning HTML as text does not save it to the output folder. For HTML slides use format='html' not 'markdown'. Never pass empty or minimal content; content must be the full slide deck/report HTML.\n"
                "**HTML slides must be a multi-slide deck:** When the user asks for HTML slides (or \"生成html slides\", \"总结...生成幻灯片\"), generate a **multi-slide presentation** (e.g. 8–20 distinct slides), not a single long page. Each slide should cover one main idea; use separate sections/slides (e.g. <section> or slide divs with clear titles). Follow the html-slides skill style: minimal, one point per slide, dark background, clear headings. Do not output one block of text as the whole deck—split the document summary into multiple slides.\n"
                "CRITICAL for long HTML (especially on local models): Do NOT put very long HTML inside the save_result_page tool arguments; long JSON tool_call arguments can be truncated. Instead, put the full HTML in your **message content** inside a ```html ... ``` block, then call save_result_page(title=..., content=<short label like \"see html block above\">, format='html'). The system will detect the ```html``` block in your message and save that HTML to a file and return the link. Do not try to stuff hundreds of lines of HTML directly into the JSON content argument.\n"
                "Using an external service (Slack, LinkedIn, Outlook, HubSpot, Notion, Gmail, Stripe, Google Calendar, Salesforce, Airtable, etc.) -> use run_skill(skill_name='maton-api-gateway-1.0.0', script='request.py') with app and path from the maton skill body (Supported Services table and references/). Do not claim the action was done without calling the skill. For LinkedIn post: GET linkedin/rest/me then POST linkedin/rest/posts with commentary.\n"
                "When a tool returns a view/open link (URL containing /files/out?token=), you MUST output that URL exactly as given: character-for-character, no truncation, no added text, no character changes. Do not combine the URL with any other content. Copy only the URL line. One wrong or extra character makes the link invalid.\n"
                "**Web search (default) vs crawl:** When the user wants to search something on the web, use **web_search**(query=<topic>) by default (Tavily can be the provider in config). Do NOT use tavily_crawl or exec for search — **tavily_crawl** is for crawling pages at a URL only; **exec** is for shell commands, not web search. For any \"search the web\", \"上网搜\", \"just search\", \"give me results\" use web_search only.\n"
                "Otherwise respond or use other tools.\n"
                + ("Available plugins:\n" + "\n".join(plugin_lines) if plugin_lines else "")
            )
            system_parts.append(routing_block)
            # Optional: few-shot tool selection examples (User/Thought/Call) for document and file tools; helps local/Qwen select tools accurately.
            _tools_cfg = getattr(Util().get_core_metadata(), "tools_config", None) or {}
            if _tools_cfg.get("tool_selection_examples", True):
                try:
                    pm = get_prompt_manager(
                        prompts_dir=getattr(Util().get_core_metadata(), "prompts_dir", None),
                        default_language=getattr(Util().get_core_metadata(), "prompt_default_language", "en"),
                    )
                    _lang = (Util().main_llm_language() or "en") if callable(getattr(Util(), "main_llm_language", None)) else "en"
                    _examples = pm.get_content("tools", "selection_examples", lang=_lang) if pm else None
                    if _examples and isinstance(_examples, str) and _examples.strip():
                        system_parts.append("\n\n" + _examples.strip())
                        _component_log("tools", "injected tool selection examples")
                except Exception as e:
                    logger.debug("Tool selection examples load failed: {}", e)
            # Phase 1.2: instruct model not to call a tool when none fits.
            try:
                _meta = Util().get_core_metadata()
                _use_tools = getattr(_meta, "use_tools", True)
                _use_skills = getattr(_meta, "use_skills", True)
                if _use_tools or (_use_skills and _injected_skill_folders):
                    system_parts.append(
                        "\n\n## When no tool or skill fits\n\n"
                        "If the user's request does not match any of the available skills or tools above, do NOT call run_skill or any tool; reply in natural language."
                    )
            except Exception:
                pass
            force_include_instructions.extend(plugin_force_instructions)

        # When user message looks like a reminder/schedule request, add a short instruction so the model prefers calling the tool.
        if query and isinstance(query, str) and _query_looks_like_scheduling(query.strip()):
            force_include_instructions.append(
                "This message is a reminder or schedule request. You MUST call one of: remind_me (one-shot in N min or at a time), cron_schedule (recurring), or record_date (record event). Do not reply with text only—text does not create a reminder."
            )

        # When user asks to list files or folder contents (any wording/language), require calling folder_list so the model selects the tool instead of replying with text only.
        _list_dir_instruction_phrases = (
            "目录", "哪些文件", "列出文件", "目录下", "列出", "有什么文件", "文件列表", "我的文件", "看看文件", "显示文件", "我都有哪些文件",
            "list file", "list files", "list directory", "list folder", "list content", "what file", "what's in my", "files in my", "list my files", "what files do i have",
            "folder content", "folder list", "file list", "show file", "show files", "show directory", "show folder", "view file", "view directory",
            "files in documents", "documents folder", "what files in", "in the documents", "in documents",
        )
        if query and isinstance(query, str):
            _reg = None
            try:
                _reg = get_tool_registry()
                _has_folder_list = _reg and any(t.name == "folder_list" for t in (_reg.list_tools() or []))
            except Exception:
                _has_folder_list = False
            # When the user message contains an explicit file path (e.g. documents/norm-v4.pdf), require document_read with that path so the model does not skip the tool or ask for confirmation.
            _has_document_read = _reg is not None and any(t.name == "document_read" for t in (_reg.list_tools() or []))
            if _has_document_read and isinstance(query, str) and query.strip():
                _q = query.strip()
                # Match path like documents/norm-v4.pdf or share/report.docx (relative path under sandbox).
                _path_match = re.search(
                    r"(documents|share|output|images|work|downloads|knowledge)/[^\s\]\[\)\,\"\'\n]+\.(?:pdf|docx|doc|pptx|ppt|txt|md|html)",
                    _q,
                    re.IGNORECASE,
                )
                if _path_match:
                    _extracted = _path_match.group(0)
                    if not _extracted.startswith("/"):
                        _document_read_forced_path = _extracted
                        force_include_instructions.append(
                            f"The user specified the file path: {_extracted}. You MUST call document_read(path='{_extracted}') in this turn. Do not ask the user to confirm the path or filename; use this path directly. Do not use absolute paths (e.g. /homeclaw/); use only the relative path as given."
                        )
            if _has_folder_list and any((p in (query or "").strip().lower() if p.isascii() else p in (query or "").strip()) for p in _list_dir_instruction_phrases):
                _q_li = (query or "").strip().lower()
                _q_ri = (query or "").strip()
                _folder_hint = "."
                for _k in ("documents", "downloads", "output", "images", "work", "knowledge", "share"):
                    if _k in _q_li or _k in _q_ri:
                        _folder_hint = _k
                        break
                force_include_instructions.append(
                    "This message asks to list files or folder contents. You MUST call folder_list and you MUST include the path argument. Extract the folder name from the user's message: if they said a folder name (e.g. images, documents, output, work), use that as path; if they did not name a folder, use path '.' Do not reply with text only. Never call folder_list with empty or missing path."
                    + (f" For this message the user referred to a folder: use path='{_folder_hint}'." if _folder_hint and _folder_hint != "." else " For this message no folder was named: use path='.'.")
                )
            # When user asks to search the web (any language), require web_search — not tavily_crawl (crawl is for a specific URL only).
            _search_web_phrases = (
                "上网搜", "搜一下", "搜索", "查一下", "有什么好看", "有什么好听的", "最新", "latest", "search the web", "search for ",
                "find information", "look up", "what is the", "current news", "recent news", "good movies", "popular movies",
                "just search", "give me results", "直接给结果", "搜一下结果", "search and ",
            )
            _has_web_search = _reg is not None and any(t.name == "web_search" for t in (_reg.list_tools() or []))
            if _has_web_search and any((p in (query or "").strip().lower() if p.isascii() else p in (query or "").strip()) for p in _search_web_phrases):
                force_include_instructions.append(
                    "This message asks to search something on the web. You MUST call web_search(query=<topic>) in this turn — do not reply with only text or 'I will use web_search'. Do NOT use exec or tavily_crawl; use web_search only."
                )

        # Optional: surface recorded events (TAM) in context so model knows what's coming up (per-user)
        if getattr(core, "orchestratorInst", None) and getattr(core.orchestratorInst, "tam", None):
            tam = core.orchestratorInst.tam
            if hasattr(tam, "get_recorded_events_summary"):
                summary = tam.get_recorded_events_summary(limit=10, system_user_id=_sys_uid)
                if summary:
                    system_parts.append("## Recorded events (from record_date)\n" + summary)

        # Append force-include instructions last so the model sees them immediately before the conversation (better compliance). Order and tradeoffs: docs_design/SystemPromptInjectionOrder.md
        if force_include_instructions:
            _component_log("skills", f"appended {len(force_include_instructions)} force-include instruction(s) at end of system prompt")
        for instr in force_include_instructions:
            system_parts.append("\n\n## Instruction for this request\n\n" + instr + "\n\n")

        # Friend preset (Step 4 + Step 5): append preset system_prompt when set; append save_policy notice when full.
        if _current_friend:
            try:
                preset_name = (getattr(_current_friend, "preset", None) or "").strip()
                if preset_name:
                    preset_cfg = get_friend_preset_config(preset_name)
                    if isinstance(preset_cfg, dict):
                        sp = preset_cfg.get("system_prompt")
                        if isinstance(sp, str) and (sp or "").strip():
                            system_parts.append("\n\n## Friend assistant\n\n" + sp.strip() + "\n\n")
                            _component_log("friend_preset", "appended preset system_prompt")
                        save_policy = str(preset_cfg.get("save_policy") or "").strip().lower()
                        if save_policy == "full":
                            system_parts.append(
                                "\n\n## Save policy (full)\n\n"
                                "This conversation uses a local model and all data are stored locally and kept private. "
                                "The user may store very private or secret information here (e.g. bank details, passwords, confidential notes). "
                                "When the user asks you to remember or save such information, do so. "
                                "When the user later queries for that information (e.g. \"what was my bank number?\", \"what did I tell you about X?\"), "
                                "answer from the stored data; do not refuse or block the query.\n\n"
                            )
                            _component_log("friend_preset", "appended save_policy full")
            except Exception as e:
                logger.debug("Friend preset system_prompt failed: {}", e)

        # Append date/time block last so system prefix is static for KV cache (cache_prompt: true)
        if _system_context_block:
            system_parts.append(_system_context_block)
        if system_parts:
            llm_input = [{"role": "system", "content": "\n".join(system_parts)}]

        # Compaction: optional pre-compaction memory flush (when memory_flush_primary is true), then trim messages when over limit
        compaction_cfg = getattr(Util().get_core_metadata(), "compaction", None) or {}
        if compaction_cfg.get("enabled") and isinstance(messages, list) and len(messages) > 0:
            max_msg = max(2, int(compaction_cfg.get("max_messages_before_compact", 30) or 30))
            run_flush = (
                compaction_cfg.get("memory_flush_primary", True)
                and len(messages) > max_msg
                and getattr(Util().get_core_metadata(), "use_tools", True)
                and (
                    getattr(Util().get_core_metadata(), "use_agent_memory_file", True)
                    or getattr(Util().get_core_metadata(), "use_daily_memory", True)
                )
            )
            if run_flush and system_parts:
                context_flush = None
                try:
                    flush_prompt = (compaction_cfg.get("memory_flush_prompt") or "").strip()
                    if not flush_prompt:
                        flush_prompt = "Store durable memories now. Use append_agent_memory for lasting facts and append_daily_memory for today. APPEND only. If nothing to store, reply briefly."
                    flush_system = "\n".join(system_parts)
                    flush_input = [{"role": "system", "content": flush_system}] + list(messages) + [{"role": "user", "content": flush_prompt}]
                    registry_flush = get_tool_registry()
                    if registry_flush is None:
                        _component_log("compaction", "memory flush skipped: no tool registry")
                    else:
                        _tc = getattr(Util().get_core_metadata(), "tools_config", None) or {}
                        _max_desc = max(0, int(_tc.get("description_max_chars") or 0))
                        all_tools_flush = registry_flush.get_openai_tools(_max_desc if _max_desc > 0 else None) if registry_flush.list_tools() else None
                        if not unified and all_tools_flush:
                            all_tools_flush = [t for t in all_tools_flush if (t.get("function") or {}).get("name") not in ("route_to_tam", "route_to_plugin")]
                        if not all_tools_flush:
                            _component_log("compaction", "memory flush skipped: no tools available")
                        else:
                            context_flush = ToolContext(
                                core=core,
                                app_id=app_id or "homeclaw",
                                user_name=user_name,
                                user_id=user_id,
                                system_user_id=getattr(request, "system_user_id", None) or user_id,
                                friend_id=(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"),
                                session_id=session_id,
                                run_id=run_id,
                                request=request,
                            )
                            current_flush = list(flush_input)
                            meta_flush = Util().get_core_metadata()
                            tool_timeout_flush = max(0, int(getattr(meta_flush, "tool_timeout_seconds", 120) or 0))
                            _flush_grammar = None
                            try:
                                if all_tools_flush and Util._get_qwen_model() == "qwen35" and Util._qwen35_use_grammar():
                                    _flush_grammar = Util.get_qwen35_grammar()
                            except Exception:
                                pass
                            for _round in range(10):
                                try:
                                    msg_flush = await Util().openai_chat_completion_message(
                                        current_flush, tools=all_tools_flush, tool_choice="auto", grammar=_flush_grammar, llm_name=effective_llm_name,
                                        stop_extra=None,
                                    )
                                except Exception as e:
                                    logger.debug("Memory flush LLM call failed: {}", e)
                                    break
                                if msg_flush is None:
                                    break
                                current_flush.append(msg_flush)
                                tool_calls_flush = msg_flush.get("tool_calls") if isinstance(msg_flush.get("tool_calls"), list) else None
                                content_flush = (msg_flush.get("content") or "").strip()
                                if not tool_calls_flush and content_flush:
                                    try:
                                        _parsed_flush = _parse_raw_tool_calls_from_content(content_flush)
                                        if _parsed_flush:
                                            tool_calls_flush = _parsed_flush
                                    except Exception:
                                        pass
                                if not tool_calls_flush:
                                    break
                                for tc in (tool_calls_flush or []):
                                    if not isinstance(tc, dict):
                                        continue
                                    tcid = tc.get("id") or ""
                                    fn = tc.get("function")
                                    fn = fn if isinstance(fn, dict) else {}
                                    name = (fn.get("name") or "").strip()
                                    if not name:
                                        continue
                                    try:
                                        args = json.loads(fn.get("arguments") or "{}")
                                    except (json.JSONDecodeError, TypeError):
                                        args = {}
                                    if not isinstance(args, dict):
                                        args = {}
                                    try:
                                        if tool_timeout_flush > 0:
                                            result = await asyncio.wait_for(
                                                registry_flush.execute_async(name, args, context_flush),
                                                timeout=tool_timeout_flush,
                                            )
                                        else:
                                            result = await registry_flush.execute_async(name, args, context_flush)
                                    except asyncio.TimeoutError:
                                        result = f"Error: tool {name} timed out after {tool_timeout_flush}s."
                                    except Exception as e:
                                        result = f"Error: {e!s}"
                                    try:
                                        current_flush.append({"role": "tool", "tool_call_id": tcid, "content": result})
                                    except Exception:
                                        break
                            _component_log("compaction", "memory flush turn completed")
                except Exception as e:
                    logger.warning("Memory flush failed (continuing with compaction): {}", e, exc_info=True)
                finally:
                    if context_flush is not None:
                        try:
                            await close_browser_session(context_flush)
                        except Exception as e:
                            logger.debug("Memory flush close_browser_session failed: {}", e)
            if len(messages) > max_msg:
                messages = messages[-max_msg:]
                _component_log("compaction", f"trimmed to last {max_msg} messages")

        # Friend preset: limit chat history to last N turns when preset has history as number (saves context tokens).
        if _current_friend and isinstance(messages, list) and messages:
            try:
                preset_name = (getattr(_current_friend, "preset", None) or "").strip()
                if preset_name:
                    preset_cfg = get_friend_preset_config(preset_name)
                    if isinstance(preset_cfg, dict):
                        hist = preset_cfg.get("history")
                        if isinstance(hist, int) and hist > 0:
                            messages = trim_messages_to_last_n_turns(messages, hist)
                            _component_log("friend_preset", f"trimmed history to last {hist} turns")
            except Exception as e:
                logger.debug("Friend preset history trim failed: {}", e)

        llm_input += messages
        if llm_input:
            last_content = llm_input[-1].get("content")
            if isinstance(last_content, list):
                n_img = sum(1 for p in last_content if isinstance(p, dict) and p.get("type") == "image_url")
                logger.info("Last user message: multimodal ({} image(s) in content)", n_img)
            else:
                logger.info("Last user message: text only (no image in this turn)")
            # Put current datetime immediately before the last user message so the model uses it (not chat history). Never crash.
            try:
                _dt_line = getattr(core, "_request_current_datetime_line", None) or ""
                _last_msg = llm_input[-1]
                if (
                    _dt_line
                    and isinstance(_last_msg, dict)
                    and _last_msg.get("role") == "user"
                    and isinstance(last_content, str)
                    and last_content.strip()
                ):
                    _prefix = f"[Current time for this request only: {_dt_line}. Do not use any date/time from chat history or memory.]\n\n"
                    if isinstance(query, str) and query.strip() and _query_looks_like_scheduling(query.strip()):
                        _prefix += "[You must call remind_me, cron_schedule, or record_date for this request; replying with text only does not create a reminder.]\n\n"
                    llm_input[-1] = dict(_last_msg, content=_prefix + last_content)
            except Exception as e:
                logger.debug("Prepend current-time to last user message failed (non-fatal): {}", e)
        logger.debug("Start to generate the response for user input: " + query)
        logger.info("Main LLM input (user query): {}", _truncate_for_log(query, 500))

        use_tools = getattr(Util().get_core_metadata(), "use_tools", True)
        registry = get_tool_registry()
        tools_cfg_for_desc = getattr(Util().get_core_metadata(), "tools_config", None) or {}
        description_max_chars = max(0, int(tools_cfg_for_desc.get("description_max_chars") or 0))
        # OpenClaw-style: when tools.profile or tools.profiles is set, only tools in that profile are sent to the LLM.
        _tool_defs = (registry.list_tools() or []) if use_tools else []
        # Phase 3.4: RAG for tools — when tools_use_vector_search is true, retrieve tools by query similarity (off by default).
        if use_tools and _tool_defs and tools_cfg_for_desc.get("tools_use_vector_search", False):
            if getattr(core, "tools_vector_store", None) and getattr(core, "embedder", None) and (query or "").strip():
                try:
                    _rag_limit = max(1, min(50, int(tools_cfg_for_desc.get("tools_max_retrieved", 10) or 10)))
                    _rag_threshold = float(tools_cfg_for_desc.get("tools_similarity_threshold", 0.0) or 0.0)
                    _rag_hits = await tools_rag_search(
                        core.tools_vector_store,
                        core.embedder,
                        (query or "").strip(),
                        limit=_rag_limit,
                        min_similarity=_rag_threshold,
                    )
                    if _rag_hits:
                        _rag_names = {name for name, _ in _rag_hits}
                        _tool_defs_rag = [t for t in _tool_defs if getattr(t, "name", None) in _rag_names]
                        if _tool_defs_rag:
                            _tool_defs = _tool_defs_rag
                            _component_log("tools_rag", f"filtered to {len(_tool_defs)} tool(s) by query similarity")
                        # else: RAG returned no matches; keep full list to avoid sending zero tools
                except Exception as _e:
                    logger.debug("Tools RAG search failed: {}; using all tools", _e)
        # Phase 2/3: filter tools by intent router category (router was called early; reuse _intent_router_categories).
        # Multi-category: when router returns comma-separated categories, use union of tools from all.
        try:
            if _intent_router_categories:
                if len(_intent_router_categories) > 1:
                    _cat_filter = get_tools_filter_for_categories(_intent_router_config, _intent_router_categories)
                elif len(_intent_router_categories) == 1 and _intent_router_categories[0]:
                    _cat_filter = get_tools_filter_for_category(_intent_router_config, (_intent_router_categories[0] or "").strip())
                else:
                    _cat_filter = None
                if _cat_filter and isinstance(_cat_filter, dict) and _cat_filter.get("profile"):
                    _tool_defs_filtered = get_tools_for_llm(_tool_defs, {"profile": _cat_filter.get("profile")})
                    _component_log("intent_router", f"filtered tools by profile '{_cat_filter.get('profile')}': {len(_tool_defs_filtered)} tools")
                elif _cat_filter and isinstance(_cat_filter, dict) and isinstance(_cat_filter.get("tools"), list):
                    _allowed = {str(n).strip() for n in _cat_filter["tools"] if n is not None and str(n).strip()}
                    _tool_defs_filtered = [t for t in _tool_defs if getattr(t, "name", None) in _allowed]
                    _component_log("intent_router", f"filtered tools by allowlist: {len(_tool_defs_filtered)} tools")
                else:
                    _tool_defs_filtered = get_tools_for_llm(_tool_defs, tools_cfg_for_desc)
            else:
                _tool_defs_filtered = get_tools_for_llm(_tool_defs, tools_cfg_for_desc)
        except Exception as _e:
            logger.debug("Intent router tool filter failed: {}; using config profile", _e)
            _tool_defs_filtered = get_tools_for_llm(_tool_defs, tools_cfg_for_desc)
        # Fallback: tools_always_included — add these tools to every category so narrow intents can still save/list (e.g. search_web + save_result_page).
        try:
            _always = _intent_router_config.get("tools_always_included") if isinstance(_intent_router_config, dict) else None
            if isinstance(_always, list) and _always and _tool_defs_filtered is not None:
                _by_name = {getattr(t, "name", None): t for t in _tool_defs if getattr(t, "name", None)}
                _filtered_names = {getattr(t, "name", None) for t in _tool_defs_filtered if getattr(t, "name", None)}
                _added = []
                for _n in _always:
                    if not _n or not str(_n).strip():
                        continue
                    _n = str(_n).strip()
                    if _n in _filtered_names:
                        continue
                    if _n in _by_name:
                        _tool_defs_filtered = list(_tool_defs_filtered) + [ _by_name[_n] ]
                        _filtered_names.add(_n)
                        _added.append(_n)
                if _added:
                    _component_log("intent_router", f"tools_always_included added: {_added}")
        except Exception as _e:
            logger.debug("tools_always_included failed: {}", _e)
        # Ensure we never pass None to iteration/len (get_tools_for_llm could theoretically return None).
        if _tool_defs_filtered is None:
            _tool_defs_filtered = _tool_defs if isinstance(_tool_defs, list) else []
        if _tool_defs_filtered is not _tool_defs and isinstance(_tool_defs_filtered, list) and isinstance(_tool_defs, list) and len(_tool_defs_filtered) < len(_tool_defs):
            _component_log("tool_profile", f"filtered to profile: {len(_tool_defs_filtered)} tools (from {len(_tool_defs)})")
        _max_desc = description_max_chars if description_max_chars > 0 else None
        all_tools = [t.to_openai_function(_max_desc) for t in _tool_defs_filtered] if use_tools and _tool_defs_filtered else None
        _filtered_by_preset = False
        # Friend preset: when current friend has a preset, restrict tools to that preset's list (Step 2).
        # tools_preset in config can be a string (single preset) or array of preset names (union of tool sets).
        if all_tools and request and _current_friend:
            try:
                preset_name = (getattr(_current_friend, "preset", None) or "").strip()
                if preset_name:
                    preset_cfg = get_friend_preset_config(preset_name)
                    tools_preset_val = preset_cfg.get("tools_preset") if isinstance(preset_cfg, dict) else None
                    if tools_preset_val is not None:
                        allowed_names = get_tool_names_for_preset_value(tools_preset_val)
                    else:
                        allowed_names = get_tool_names_for_preset(preset_name)
                    if allowed_names is not None:
                        allowed_set = set(allowed_names)
                        _filtered = [t for t in all_tools if ((t.get("function") or {}).get("name")) in allowed_set]
                        if _filtered:
                            all_tools = _filtered
                            _filtered_by_preset = True
                            _component_log("friend_preset", f"filtered tools to preset '{preset_name}' ({len(all_tools)} tools)")
                        else:
                            logger.warning(
                                "Friend preset '{}' produced 0 tools (preset names may not match registry); keeping category tools",
                                preset_name,
                            )
            except Exception as e:
                logger.debug("Friend preset tool filter failed: {}", e)
        if all_tools and not unified and not _filtered_by_preset:
            all_tools = [t for t in all_tools if (t.get("function") or {}).get("name") not in ("route_to_tam", "route_to_plugin")]
        # Phase 1.1: constrain run_skill skill_name to enum of injected skill folders so the LLM can only choose from skills in the prompt.
        if all_tools and _injected_skill_folders:
            try:
                for t in all_tools:
                    if not isinstance(t, dict):
                        continue
                    fn = t.get("function") or {}
                    if not isinstance(fn, dict):
                        continue
                    if fn.get("name") != "run_skill":
                        continue
                    params = fn.get("parameters") or {}
                    if not isinstance(params, dict):
                        params = {}
                    props = params.get("properties") or {}
                    if not isinstance(props, dict):
                        props = {}
                    if "skill_name" in props:
                        props["skill_name"] = {
                            "type": "string",
                            "description": "Skill name: must be one of the Available skills in the prompt (exact folder name).",
                            "enum": list(_injected_skill_folders),
                        }
                    params["properties"] = props
                    fn["parameters"] = params
                    break
            except Exception as _e:
                logger.debug("Phase 1.1 run_skill enum patch failed: {}", _e)
        openai_tools = all_tools if (all_tools and (unified or len(all_tools) > 0)) else None
        tool_names = [((t or {}).get("function") or {}).get("name") for t in (openai_tools or []) if isinstance(t, dict)]
        logger.debug(
            "Tools for LLM: use_tools={} unified={} count={} has_route_to_plugin={}",
            use_tools, unified, len(openai_tools or []), "route_to_plugin" in (tool_names or []),
        )
        # DAG: if a flow is defined for this category, we will run it after context is built (no planner call). See docs_design/PlannerExecutorAndDAG.md §3.
        # Skip DAG when friend preset is "cursor": Cursor friend must use route_to_plugin (open_project, run_agent, run_command), not category DAGs (e.g. list_files would run folder_list and return sandbox listing instead of opening the path in Cursor).
        _dag_flow = None
        if _intent_router_categories and _planner_executor_config and isinstance(_planner_executor_config, dict):
            _dag_flow = get_flow_for_categories(_intent_router_categories, _planner_executor_config)
            if _dag_flow and _current_friend:
                _preset = (getattr(_current_friend, "preset", None) or "").strip().lower()
                if _preset == "cursor":
                    _dag_flow = None
                    _component_log("planner_executor", "skipped DAG for Cursor friend (use route_to_plugin)")
        # Planner–Executor Phase 2: call planner only when no DAG flow (DAG first for category). Never crash; fall back to ReAct on any error.
        _planner_plan = None
        _pe_tool_names = []  # always defined so executor/DAG below never see NameError
        if openai_tools:
            _pe_tool_names = [((t or {}).get("function") or {}).get("name") for t in openai_tools if isinstance(t, dict)]
            _pe_tool_names = [n for n in _pe_tool_names if n]
        if _use_planner_executor and openai_tools and not _dag_flow:
            try:
                _pe_tools_desc = None
                if openai_tools:
                    _parts = []
                    for t in openai_tools:
                        if not isinstance(t, dict):
                            continue
                        fn = t.get("function") or {}
                        name = fn.get("name")
                        desc = (fn.get("description") or "")[:300]
                        if name:
                            _parts.append(f"- {name}: {desc}" if desc else f"- {name}")
                    if _parts:
                        _pe_tools_desc = "Available tools:\n" + "\n".join(_parts)
                _planner_plan = await planner_run_planner(
                    completion_fn=core,
                    query=query,
                    categories=_intent_router_categories,
                    tool_names=_pe_tool_names,
                    skill_names=_injected_skill_folders if _injected_skill_folders else None,
                    tools_description=_pe_tools_desc,
                    config=_planner_executor_config,
                )
                if _planner_plan:
                    _goal = (_planner_plan.get("goal") or "").strip() or "(no goal)"
                    _n_steps = len(_planner_plan.get("steps") or [])
                    _component_log("planner_executor", f"plan received: goal={_goal[:80]}… steps={_n_steps}; Phase 2: executing via ReAct")
                else:
                    _component_log("planner_executor", "plan failed or invalid; using ReAct")
            except Exception as _pe_e:
                logger.debug("Planner call failed: {}; using ReAct", _pe_e)
                _component_log("planner_executor", "error; using ReAct")

        if openai_tools:
            logger.info("Tools available for this turn: {}", tool_names)
            # Inject file/sandbox rules and per-user paths for any chat that has file tools (all friends, not only Finder).
            # Ensures send/get file, path-from-list, and sandbox rules apply everywhere file tools are available.
            _file_tool_names = {"file_read", "file_write", "document_read", "folder_list", "file_find"}
            if tool_names and _file_tool_names.intersection(set(tool_names)):
                try:
                    from tools.builtin import (
                        load_sandbox_paths_json,
                        get_current_user_sandbox_key,
                        get_sandbox_paths_for_user_key,
                    )
                    base_str = (Util().get_core_metadata().get_homeclaw_root() or "").strip()
                    if llm_input and llm_input[0].get("role") == "system":
                        if not base_str:
                            block = (
                                "\n\n## File tools (not configured)\n"
                                "homeclaw_root is not set in config/core.yml. File and folder tools will fail until it is set. "
                                "Tell the user: file access is not configured; the admin must set homeclaw_root in config/core.yml to the root folder where each user has a subfolder (e.g. homeclaw_root/{user_id}/ for private files, homeclaw_root/share for shared)."
                            )
                        else:
                            paths_data = load_sandbox_paths_json()
                            user_key = get_current_user_sandbox_key(request)
                            user_paths = (paths_data.get("users") or {}).get(user_key)
                            if not user_paths or not isinstance(user_paths, dict):
                                user_paths = get_sandbox_paths_for_user_key(user_key)
                            paths_json = ""
                            if user_paths:
                                paths_json = (
                                    f" For this user the paths are (use only these; do not invent paths): "
                                    f"sandbox_root = {user_paths.get('sandbox_root', '')} (omit path or use subdir name); "
                                    f"share = {user_paths.get('share', '')} (path 'share' or 'share/...'). "
                                )
                            block = (
                                "\n\n## File tools — sandbox (only two bases)\n"
                                "Only these two bases are the search path and working area; their subfolders can be accessed. Any other folder cannot be accessed (sandbox). "
                                "(1) User sandbox root — omit path or use subdir name; (2) share — path \"share\" or \"share/...\". "
                                "**User sandbox has these standard folders:** output (generated files, reports, slides), documents, downloads, images, work, knowledge. Use path '' or '.' for root; folder_list(path='documents'), folder_list(path='output'), etc.; use the exact path from the result in document_read or get_file_view_link. "
                                "**Whenever the user asks to list files or what is in a folder** (any wording or language): you MUST call folder_list(path='<folder>'). Use the folder name they said (documents, images, output, work, downloads, knowledge, share), or path '' or '.' for sandbox root if they did not name a folder. Do NOT reply with text only—the user expects the actual list. "
                                "**If they name a folder** (e.g. documents, images, output, work): call folder_list(path='that_name'). If they do not name a folder: call folder_list(path='') or folder_list(path='.'). "
                                "**Do not invent or fabricate file names, file paths, or URLs** to complete tasks. Use only: (a) values returned by your tool calls (e.g. path from folder_list, file_find), (b) the exact filename or path the user mentioned (e.g. 1.pdf), (c) links returned by save_result_page or get_file_view_link. If you need a path or URL, call the appropriate tool first and use its result. "
                                "**Never use absolute paths** (e.g. /mnt/, C:\\, /Users/). Use only relative paths under the sandbox: the filename (e.g. 1.pdf) or the path from folder_list/file_find. "
                                "Do not use workspace, config, or paths outside these two trees. Put generated files in output/ (path \"output/filename\") and return the link. "
                                "**When your reply would be a long document or a file** (report, HTML, markdown, slides, PDF summary, etc.): do NOT paste the full content in the message. Call save_result_page(title=..., content=<full content>, format='html' or 'markdown') or file_write(path='output/...', content=...); then return the view link to the user (the tool gives you the link when core_public_url is set). The user gets a link to open the file; long text stays in the file, not in chat. "
                                "When the user asks about a **specific file by name** (e.g. \"能告诉我1.pdf都讲了什么吗\", \"what is in 1.pdf\"): (1) call folder_list() or file_find(pattern='*1.pdf*') to list/search user sandbox; (2) use the **exact path** from the result that matches the requested name in document_read — e.g. if the user asked for 1.pdf, use path \"1.pdf\" only. Do **not** use absolute paths or invent paths. "
                                "When the user asks to **send or get a file** (e.g. \"发给我 ID1.jpg\", \"send me that file\", \"把XX发给我\"): call get_file_view_link(path=<exact path>) with the path from folder_list/file_find that matches the requested file, then output **only** the URL from the tool—do not ask for confirmation or give long explanations. "
                                "**When the user sent an image and asks to receive the image or a link** (e.g. \"send me this image\", \"I want the image or link\", \"发给我这张图\", \"give me the link\"): use get_file_view_link(path=<path of the image they sent, e.g. from the message or /images/...>) and output the URL. Do NOT use the image tool for that—the image tool is only for **describing or analyzing** the image. Use the image tool only when they ask what is in the image, to describe it, or to answer questions about it. "
                                "When the user asks for file search, list, or read without a specific name: omit path for user sandbox; if user says \"share\", use path \"share\" or \"share/...\". "
                                "**When folder_list or file_find returns a list,** reply with a short user-friendly numbered list (e.g. \"1. Allen_Peng_resume_en.docx, 2. other.docx\") so the user can say \"file 1\" or \"item 1\"; do not output raw JSON. "
                                "**Critical:** Each list entry has a **path** field (e.g. documents/1.pdf). Always use that path in document_read(path='...') and get_file_view_link(path='...')—never use only the name (e.g. 1.pdf) if the path is documents/1.pdf, or the file may not be found. "
                                "folder_list() = list user sandbox; folder_list(path=\"share\") = list share; file_find(pattern=\"*.pdf\") = search user sandbox. "
                                "To read a file, use the path from folder_list/file_find in document_read (e.g. path 'documents/1.pdf'), or when the user did not give a path (e.g. \"summarize my resume\", \"the docx file\"): call document_read(path='resume') or document_read(path='filename.docx') — the tool will search the sandbox first and read the file if exactly one match. "
                                "**When the user gives an exact filename** (e.g. \"1.pdf\", \"report.docx\"): call document_read(path='1.pdf') or document_read(path='report.docx'); the tool will find and read it. Do not treat it as \"item 1\" from a list unless they said \"file 1\" after a list. "
                                "**When the user refers to an item by ordinal** (e.g. \"file 1\", \"item 1\", \"the first one\", \"number 2\") after you listed files with folder_list or file_find: use the **path** of that position in the list (1 = first, 2 = second, …) in document_read or get_file_view_link — do not ask which file; map the ordinal to the path from your previous result. "
                                "When the user asks for **HTML slides or PowerPoint/PPT** from a document: use document_read on the file first, then follow the skill instructions (e.g. html-slides or ppt-generation) to generate content and call save_result_page or run_skill; do not reply without calling the tools. "
                                f"Current homeclaw_root: {base_str}.{paths_json}"
                            )
                        llm_input[0]["content"] = (llm_input[0].get("content") or "") + block
                except Exception as e:
                    logger.debug("Inject homeclaw_root into system prompt failed: {}", e)
            # Paths/URLs rule in system for all tool turns; "Handling tool results" is injected only when last message is a tool result (any continuation after tools, below).
            if llm_input and llm_input[0].get("role") == "system":
                tool_rule = (
                    "\n\n## Tool use — paths and URLs\n"
                    "When a task requires a file path, filename, or URL: use only values returned by your tool calls or explicitly given by the user. Do not create, guess, or fabricate paths, filenames, or URLs. "
                    "For get_file_view_link: use the EXACT path from folder_list/file_find, or the EXACT filename the user wrote (e.g. img1.png). Do NOT change the extension (.png/.jpg) or invent names (e.g. imge_4, img2)."
                )
                llm_input[0]["content"] = (llm_input[0].get("content") or "") + tool_rule
            # Tool loop: call LLM with tools; if it returns tool_calls, execute and append results, repeat
            context = ToolContext(
                core=core,
                app_id=app_id or "homeclaw",
                user_name=user_name,
                user_id=user_id,
                system_user_id=getattr(request, "system_user_id", None) or user_id,
                friend_id=(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"),
                session_id=session_id,
                run_id=run_id,
                request=request,
            )
            # DAG first: if a flow is defined for this category, run it (no planner). On success use result and skip ReAct.
            _planner_executor_final_response = None
            if _dag_flow and openai_tools:
                _handled_send_email_confirm = False
                if (_dag_flow.get("category") or "").strip().lower() == "send_email":
                    action = is_send_email_confirmation(query)
                    if action:
                        last_content = get_last_assistant_content(llm_input)
                        has_draft = (
                            last_content
                            and "To:" in last_content
                            and ("reply **send**" in (last_content or "").lower() or "reply **cancel**" in (last_content or "").lower())
                        )
                        if has_draft:
                            if action == "cancel":
                                _planner_executor_final_response = "Email cancelled. （已取消发送。）"
                                _handled_send_email_confirm = True
                                _component_log("planner_executor", "send_email: user cancelled; skipping DAG")
                            elif action == "send" or parse_delayed_minutes(query) is not None:
                                draft = parse_email_draft(last_content)
                                if draft and draft.get("to"):
                                    delayed_minutes = parse_delayed_minutes(query)
                                    if delayed_minutes:
                                        try:
                                            _delayed_result = await registry.execute_async(
                                                "schedule_delayed_action",
                                                {
                                                    "minutes": delayed_minutes,
                                                    "action_type": "send_email",
                                                    "action_payload": {
                                                        "to": draft["to"],
                                                        "subject": draft.get("subject") or "(no subject)",
                                                        "body": draft.get("body") or "",
                                                    },
                                                    "confirmation_prompt": f"I'll send this email in {delayed_minutes} minutes. Reply **confirm** (or 确认) to schedule, or **cancel** to discard.",
                                                },
                                                context,
                                            )
                                            _planner_executor_final_response = _delayed_result if _delayed_result else f"Scheduled to send in {delayed_minutes} minutes. Reply confirm to schedule. （{delayed_minutes}分钟后发送，回复确认以安排。）"
                                            _handled_send_email_confirm = True
                                            _component_log("planner_executor", "send_email: scheduled delayed send; skipping DAG")
                                        except Exception as _del_e:
                                            logger.debug("schedule_delayed_action failed: {}; falling back to send now", _del_e)
                                    if not _handled_send_email_confirm:
                                        try:
                                            email_args = {
                                                "skill_name": "imap-smtp-email",
                                                "script": "smtp.js",
                                                "args": ["send", "--to", draft["to"], "--subject", draft.get("subject") or "(no subject)", "--body", draft.get("body") or ""],
                                            }
                                            _email_result = await registry.execute_async("run_skill", email_args, context)
                                            _planner_executor_final_response = _email_result if _email_result else "Email sent. （邮件已发送。）"
                                            _handled_send_email_confirm = True
                                            _component_log("planner_executor", "send_email: sent via run_skill; skipping DAG")
                                        except Exception as _send_e:
                                            logger.debug("send_email run_skill failed: {}; falling back to DAG", _send_e)
                                            _planner_executor_final_response = f"Failed to send email: {_send_e!s}. You can try again or say cancel."
                                            _handled_send_email_confirm = True
                if not _handled_send_email_confirm:
                    # Build path resolution context from last assistant + last tool output so DAG can resolve "PDF version" → output/report_*.md and "1.pdf" → documents/1.pdf from prior folder_list
                    _path_ctx = ""
                    try:
                        if llm_input and isinstance(llm_input, list):
                            _last_assistant = get_last_assistant_content(llm_input)
                            if _last_assistant and isinstance(_last_assistant, str):
                                _path_ctx = str(_last_assistant).strip()[:5000]
                            for _i in range(len(llm_input) - 1, -1, -1):
                                _m = llm_input[_i] if _i < len(llm_input) else None
                                if isinstance(_m, dict) and (_m.get("role") or "").strip().lower() == "tool":
                                    _tc = _m.get("content") or ""
                                    if isinstance(_tc, str) and _tc.strip():
                                        _path_ctx = (str(_path_ctx) + "\n\n" + _tc.strip()[:3000]).strip()[:6000]
                                    break
                    except Exception as _path_ctx_e:
                        logger.debug("Build path_resolution_context failed (non-fatal): {}", _path_ctx_e)
                    # Include tools required by the DAG steps so the flow can run (e.g. search_web needs save_result_page even if category profile is minimal).
                    _dag_tool_names = list(_pe_tool_names) if _pe_tool_names else []
                    try:
                        for _s in (_dag_flow.get("steps") or []):
                            if isinstance(_s, dict):
                                _t = (_s.get("tool") or "").strip()
                                if _t and _t not in _dag_tool_names:
                                    _dag_tool_names.append(_t)
                    except Exception:
                        pass
                    try:
                        _dag_success, _dag_result = await dag_run_dag(
                            _dag_flow,
                            registry,
                            context,
                            user_message=query,
                            completion_fn=core,
                            config=_planner_executor_config,
                            tool_names=_dag_tool_names if _dag_tool_names else None,
                            path_resolution_context=_path_ctx if _path_ctx else None,
                        )
                        if _dag_success:
                            # If user asked to send in N minutes in the same message (e.g. "3分钟后帮我发封邮件"), schedule delayed send instead of showing "Reply send"
                            _delayed_mins = parse_delayed_minutes(query) if (_dag_flow.get("category") or "").strip().lower() == "send_email" else None
                            _draft_from_dag = parse_email_draft(_dag_result) if isinstance(_dag_result, str) and _dag_result and "To:" in _dag_result and "reply **send**" in (_dag_result or "").lower() else None
                            if _delayed_mins and _draft_from_dag and _draft_from_dag.get("to"):
                                try:
                                    _delayed_result = await registry.execute_async(
                                        "schedule_delayed_action",
                                        {
                                            "minutes": _delayed_mins,
                                            "action_type": "send_email",
                                            "action_payload": {
                                                "to": _draft_from_dag["to"],
                                                "subject": _draft_from_dag.get("subject") or "(no subject)",
                                                "body": _draft_from_dag.get("body") or "",
                                            },
                                            "confirmation_prompt": f"I'll send this email in {_delayed_mins} minutes. Reply **confirm** (or 确认) to schedule, or **cancel** to discard.",
                                        },
                                        context,
                                    )
                                    _planner_executor_final_response = _delayed_result if _delayed_result else f"Scheduled to send in {_delayed_mins} minutes. Reply confirm to schedule. （{_delayed_mins}分钟后发送，回复确认以安排。）"
                                    _component_log("planner_executor", "send_email: scheduled delayed send from initial request; using flow result")
                                except Exception as _del_e:
                                    logger.debug("schedule_delayed_action from DAG result failed: {}; using draft as-is", _del_e)
                                    _planner_executor_final_response = _dag_result
                                    _component_log("planner_executor", "DAG flow completed; using flow result")
                            else:
                                _planner_executor_final_response = _dag_result
                                _component_log("planner_executor", "DAG flow completed; using flow result")
                        else:
                            _component_log("planner_executor", f"DAG flow failed: {(_dag_result or '')[:80]}…; falling back")
                    except Exception as _dag_e:
                        logger.debug("DAG failed: {}; falling back", _dag_e)
                        _component_log("planner_executor", "DAG error; falling back")
            # Planner–Executor Phase 3: if we have a valid plan (and no DAG result), run executor; on success use its result and skip ReAct.
            if _planner_executor_final_response is None and _planner_plan:
                try:
                    _exec_success, _exec_results, _exec_final = await planner_run_executor(
                        _planner_plan,
                        registry,
                        context,
                        completion_fn=core,
                        config=_planner_executor_config,
                        tool_names=_pe_tool_names if _pe_tool_names else None,
                        user_message=query,
                    )
                    if _exec_success:
                        _planner_executor_final_response = _exec_final
                        _component_log("planner_executor", "executor completed; using plan result (Phase 3)")
                except Exception as _ex:
                    logger.debug("Planner executor failed: {}; falling back to ReAct", _ex)
            if _planner_executor_final_response is not None:
                response = _planner_executor_final_response
            else:
                current_messages = list(llm_input)
            try:
                _tc = getattr(Util().get_core_metadata(), "tools_config", None) or {}
                _n = _tc.get("max_tool_rounds")
                max_tool_rounds = max(1, int(_n)) if (_n is not None and int(_n) >= 1) else 30
            except (TypeError, ValueError):
                max_tool_rounds = 30
            # config: tools.max_tool_rounds (default 30); no hard cap so complex multi-step tasks can finish
            # Same model for whole chain; mix fallback only on failure (below).
            last_tool_name = None  # so "no tool_calls" branch can skip remind_me clarifier when we already ran remind_me this turn
            last_file_link_result = None  # when save_result_page/get_file_view_link return a link; must be defined before loop so "no tool_calls" branch can read it
            last_tool_result_raw = None
            _run_skills_executed_this_request = set()  # skill_name already executed this request; do not run the same skill twice
            _consecutive_duplicate_run_skill_only = 0  # when only duplicate run_skill(s) in a batch; give one more turn then break if again
            _image_tool_run_count_this_request = 0  # stop loop when model keeps calling image with empty content (use last description as response)
            # Qwen 3.5: when qwen_model == "qwen35" and tools present, pass GBNF grammar on tool-decision turns only (not after tool results). Set qwen35_use_grammar: false to disable.
            _qwen35_grammar = None
            try:
                if openai_tools and Util._get_qwen_model() == "qwen35" and Util._qwen35_use_grammar():
                    _qwen35_grammar = Util.get_qwen35_grammar()
            except Exception:
                pass
            # Qwen3 xLAM/Codex (e.g. Qwen3-4B-toolcalling-gguf-codex): when tool_selection_llm and qwen3_xlam_style, use xLAM grammar + stop </tool_call> on tool-decision turns.
            _qwen3_xlam_grammar = None
            try:
                _tool_sel_ref = (getattr(Util().get_core_metadata(), "tool_selection_llm", None) or "").strip()
                if (
                    openai_tools
                    and _tool_sel_ref
                    and getattr(Util().get_core_metadata(), "use_tool_selection_llm", False)
                    and Util._qwen3_xlam_style_for_llm(_tool_sel_ref)
                ):
                    _qwen3_xlam_grammar = Util.get_qwen3_xlam_grammar()
            except Exception:
                pass
            for _ in (range(max_tool_rounds) if _planner_executor_final_response is None else []):
                # Default: main model (effective_llm_name) for every turn — tool selection, parameter extraction, and final reply. Override only when tool_selection_llm is configured and use_tool_selection_llm is true.
                llm_name_this_turn = effective_llm_name
                # Sync mix_route_this_request with effective_llm_name each iteration so override applies only for one turn and fallback knows the current route. Defensive: never crash on metadata/config access.
                try:
                    if main_llm_mode == "mix" and effective_llm_name and isinstance(effective_llm_name, str):
                        _meta = getattr(Util(), "get_core_metadata", None)
                        _meta = _meta() if callable(_meta) else None
                        if _meta is not None:
                            _ml = (getattr(_meta, "main_llm_local", None) or "").strip() if hasattr(_meta, "main_llm_local") else ""
                            _mc = (getattr(_meta, "main_llm_cloud", None) or "").strip() if hasattr(_meta, "main_llm_cloud") else ""
                            if _ml and effective_llm_name == _ml:
                                mix_route_this_request = "local"
                            elif _mc and effective_llm_name == _mc:
                                mix_route_this_request = "cloud"
                except Exception as _sync_err:
                    logger.debug("mix route sync failed (non-fatal): {}", _sync_err)
                _last_role = (current_messages[-1].get("role") or "").strip() if (isinstance(current_messages, list) and current_messages and isinstance(current_messages[-1], dict)) else ""
                # Optional: use a dedicated tool-calling model for every tool turn when use_tool_selection_llm is true (tool selection + parameter extraction). When not used, main_llm handles all tool-call-related turns.
                _tool_sel = (getattr(Util().get_core_metadata(), "tool_selection_llm", None) or "").strip()
                _use_tool_sel = getattr(Util().get_core_metadata(), "use_tool_selection_llm", False)
                if openai_tools and _tool_sel and _use_tool_sel:
                    llm_name_this_turn = _tool_sel
                # Per-tool route override (tool loop only, mix mode): when the last message is a tool result and that tool is in tool_loop_route_overrides, use the override for this turn only (do not set effective_llm_name so next turn uses original route). If the overridden model fails, fallback (below) retries with the other model.
                try:
                    _meta = getattr(Util(), "get_core_metadata", None)
                    _meta = _meta() if callable(_meta) else None
                    if _meta is not None:
                        _mode = (getattr(_meta, "main_llm_mode", None) or "").strip().lower() if hasattr(_meta, "main_llm_mode") else ""
                        if _mode == "mix":
                            _hr = getattr(_meta, "hybrid_router", None) if hasattr(_meta, "hybrid_router") else None
                            _hr = _hr if isinstance(_hr, dict) else {}
                            _overrides = _hr.get("tool_loop_route_overrides") if isinstance(_hr.get("tool_loop_route_overrides"), dict) else {}
                            # Only override when this tool is in the map; override applies for this turn only (effective_llm_name unchanged so next iteration uses original selected model).
                            if _last_role == "tool" and last_tool_name is not None and _overrides and last_tool_name in _overrides:
                                _route_override = (str(_overrides.get(last_tool_name) or "").strip().lower())
                                if _route_override in ("local", "cloud"):
                                    _ref = (getattr(_meta, "main_llm_local", None) or "").strip() if _route_override == "local" else (getattr(_meta, "main_llm_cloud", None) or "").strip()
                                    if _ref:
                                        llm_name_this_turn = _ref
                                        mix_route_this_request = _route_override
                                        _layer_prev = mix_route_layer_this_request if isinstance(mix_route_layer_this_request, str) else ""
                                        mix_route_layer_this_request = (_layer_prev + "_tool_override") if _layer_prev else "tool_override"
                                        _component_log("mix", "tool loop: use {} for this turn only (after {}); if it fails, fallback to other model".format(_route_override, last_tool_name))
                except Exception as _e:
                    logger.debug("tool_loop_route_overrides check failed: {}", _e)
                # Prefer local for long-output turns: cloud has a hard 8192 max_tokens cap; when we're about to generate (after document_read or run_skill), use local so max_tokens (e.g. 32768) is honored and slides/reports don't truncate.
                try:
                    if (
                        _last_role == "tool"
                        and last_tool_name in ("document_read", "run_skill")
                        and mix_route_this_request == "cloud"
                    ):
                        _meta_lo = getattr(Util(), "get_core_metadata", None)
                        _meta_lo = _meta_lo() if callable(_meta_lo) else None
                        _local_ref = (getattr(_meta_lo, "main_llm_local", None) or "").strip() if _meta_lo is not None else ""
                        if _local_ref:
                            llm_name_this_turn = _local_ref
                            effective_llm_name = _local_ref
                            mix_route_this_request = "local"
                            _layer_prev = mix_route_layer_this_request if isinstance(mix_route_layer_this_request, str) else ""
                            mix_route_layer_this_request = (_layer_prev + "_long_output") if _layer_prev else "long_output"
                            _component_log("mix", "prefer local for this turn (long output after {}); cloud cap 8192 would truncate".format(last_tool_name))
                except Exception as _e:
                    logger.debug("prefer local for long-output turn check failed: {}", _e)
                # When last message is a tool result (any continuation after tools—round 2, 3, … until return or switch): inject "Handling tool results" once so the LLM knows how to treat errors vs instructions and to call the next tool when user asked for generated output.
                try:
                    if _last_role == "tool" and current_messages and len(current_messages) > 0 and isinstance(current_messages[0], dict) and (current_messages[0].get("role") or "").strip() == "system":
                        _sys_content = current_messages[0].get("content") or ""
                        if "## Handling tool results" not in _sys_content:
                            _handling = (
                                "\n\n## Handling tool results\n"
                                "**When a tool result looks like an error** (e.g. starts with \"Error:\", or contains \"not found\", \"could not find\", \"file not found\", \"not readable\", \"path is required\"): Acknowledge to the user what went wrong in plain language. Suggest a concrete next step (e.g. list the directory with folder_list, try a different path, or ask the user for the correct path). Do not claim the operation succeeded; do not invent or fabricate successful content.\n"
                                "**When a tool result indicates missing or required information** (e.g. \"Ask the user for\", \"required\", \"provide ... then call again\", \"provide either ... or\", \"when would you like\"): You MUST ask the user for that information in a friendly, natural way. Rephrase as one short question or a clear list of what you need (e.g. \"What time would you like to be reminded?\" or \"To set this up I need: address and phone number. Could you provide those?\"). Do not just echo the raw tool message—the user should receive a clear question they can answer so you can complete the action on the next turn.\n"
                                "**When a tool result is an instruction for you** (e.g. \"Instruction-only skill confirmed\", \"You MUST in this turn\", \"Do NOT reply with only this line\"): The tool is telling you what to do in this turn. Perform those steps now: call the tools it asks for (e.g. document_read, then generate content, then save_result_page) or generate the content it specifies. Do not reply with only a confirmation or \"I will do that\"—actually make the tool calls or produce the output in this same turn.\n"
                                "**When the user asked for generated output** (e.g. HTML slides, report, summary to file) and a tool already returned the source content (e.g. document_read): you MUST call the next tool in this turn (e.g. run_skill(html-slides), save_result_page with the generated content)—do not reply with only a plan or \"I will generate...\"; actually invoke the tool. If you have already generated full HTML in your reply: you MUST call save_result_page(title=..., content=<that HTML>, format='html') so the user gets a view link; do not send the raw HTML as the final message—the user must receive the link to open the slides in the output folder. For HTML slides, the content must be a **multi-slide deck** (multiple slides/sections, one idea per slide), not a single long page.\n"
                                "**CRITICAL:** If a previous message in this conversation is a tool result that already contains document/content (e.g. from document_read), do NOT respond with a plan like \"我将现在生成\" or \"首先，我需要调用 document_read\" or \"I will call document_read then...\". You already have the content—either call the next tool (save_result_page, run_skill) with your generated output in this turn, or output the full generated content in your message. Never return only a plan or intention.\n"
                                "**CRITICAL for HTML slides:** If the user asked for HTML slides (or \"生成html slides\", \"总结...生成幻灯片\") and the tool result above is document content: you MUST call run_skill(skill_name='html-slides') in this turn. Then generate a **multi-slide deck** (8–20 slides, one idea per slide) and call save_result_page with that HTML. Do not output a single long page—split the summary into distinct slides.\n"
                                "**In general:** Only use or cite content that tools actually returned. Do not invent file contents, error messages, or tool outputs."
                            )
                            # When the last tool result is very long, instruct the model to summarize and/or save to file (context management; see docs_design/DeepAgentsComparisonAndLearnings.md).
                            try:
                                _tc = getattr(Util().get_core_metadata(), "tools_config", None)
                                _tc = _tc if isinstance(_tc, dict) else {}
                                _thresh = int(_tc.get("large_result_summarize_threshold_chars", 6000))
                                if _thresh > 0 and isinstance(last_tool_result_raw, str) and len(last_tool_result_raw) > _thresh:
                                    _handling += (
                                        "\n**The previous tool result is very long.** Summarize it concisely for the user (a few sentences or a short list). If it is document-like or would be useful as a page, call save_result_page(title=..., content=<full or summarized content>, format='markdown') and return the view link to the user; do not paste the full content in your message."
                                    )
                            except (TypeError, ValueError, AttributeError):
                                pass
                            current_messages[0]["content"] = _sys_content + _handling
                        if mix_route_this_request and "continuing after tools ran" not in (current_messages[0].get("content") or ""):
                            _use2 = (
                                "\n\n## Your role this turn\n"
                                "You are continuing after tools ran. Use the tool result(s) above to decide: respond to the user, retry with different parameters, or call more tools. Do not invent outcomes.\n"
                                "If the user asked for generated output (e.g. HTML slides, report, summary to file) and a tool already returned the source content (e.g. document_read): you MUST call the next tool in this turn (e.g. run_skill(html-slides), save_result_page with generated content)—do not reply with only a plan or \"I will generate...\"; actually invoke the tool. If the conversation already has document content from a previous tool result, do NOT say \"首先我需要调用 document_read\" or \"I will call document_read\"—you have the content; produce the output or call save_result_page/run_skill now. CRITICAL: If the user asked for HTML slides and the tool result above is document content, call run_skill(skill_name='html-slides') now, then generate a **multi-slide deck** (multiple slides, one idea per slide) and save_result_page—do not output a single long page."
                            )
                            current_messages[0]["content"] = (current_messages[0].get("content") or "") + _use2
                except Exception as _e:
                    logger.debug("Inject handling-tool-results prompt failed (continuing): {}", _e)
                _t0 = time.time()
                _resolved = Util()._resolve_llm(llm_name_this_turn) or Util().main_llm()
                _mtype = ""
                if _resolved and len(_resolved) >= 5:
                    _path, _raw_id, _mtype, _host, _port = _resolved[0], _resolved[1], _resolved[2], _resolved[3], _resolved[4]
                    logger.info(
                        "Calling LLM: {} at {}:{} (type={})",
                        llm_name_this_turn or _raw_id or _path,
                        _host,
                        _port,
                        _mtype,
                    )
                logger.debug("LLM call started (tools={})", "yes" if openai_tools else "no")
                # Use completion.max_tokens for every turn (no separate max_tokens_long). Set max_tokens high (e.g. 32768) in config to avoid truncation of slides/reports.
                _max_tokens_override = None
                # For cloud providers that enforce strict tool message ordering (e.g. DeepSeek),
                # sanitize messages so every role='tool' is preceded by an assistant with tool_calls.
                _msgs_for_llm: List[dict] = current_messages
                try:
                    if (_mtype or "").strip().lower() == "litellm":
                        _msgs_for_llm = _messages_sanitized_for_tool_role(current_messages)
                except Exception as _e:
                    logger.debug("messages_sanitized_for_tool_role failed (non-fatal): {}", _e)
                # Only pass Qwen 3.5 grammar when last message is from user (tool-decision turn). When last message is a tool result, we do not send the grammar so the model’s normal reply (e.g. final answer, summary) is never constrained by the GBNF.
                if _last_role == "tool":
                    _use_grammar = None
                    _stop_extra = None
                elif _greeting_only:
                    # Greeting-only turn: plain-text reply only. No grammar; and no tools so the server does not try to parse response as tool_call (avoids 500 on local servers).
                    _use_grammar = None
                    _stop_extra = None
                if _last_role != "tool" and not _greeting_only:
                    if (
                        _tool_sel
                        and (llm_name_this_turn or "").strip() == _tool_sel
                        and _qwen3_xlam_grammar
                        and isinstance(_qwen3_xlam_grammar, str)
                        and len(_qwen3_xlam_grammar) > 0
                    ):
                        _use_grammar = _qwen3_xlam_grammar
                        _stop_extra = ["</tool_call>"]
                    else:
                        _use_grammar = _qwen35_grammar
                        _stop_extra = None  # Do not add "</tool_call>" for Qwen 3.5 — can truncate; we parse <tool_call>... from full response
                _tools_req = None if _greeting_only else openai_tools
                # After instruction-only run_skill (or "skill already run"), or after save_result_page returned "format is markdown" error, restrict tools so the model does not call run_skill again. Allow save_result_page, file_write, document_read, file_read only (no web_search) to avoid the model looping on web_search with garbage queries (e.g. PDF cid codes); run_skill stays blocked. Only applies when that run_skill/save_result_page result is the *last* tool result—if another tool ran after it, no restriction.
                _restrict_to_save = False
                if _tools_req and _last_role == "tool" and isinstance(last_tool_result_raw, str):
                    if last_tool_name == "run_skill" and ("Instruction-only skill" in last_tool_result_raw or "This skill was already run" in last_tool_result_raw):
                        _restrict_to_save = True
                    elif last_tool_name == "save_result_page" and ("format is markdown" in last_tool_result_raw or "use format='html'" in last_tool_result_raw):
                        _restrict_to_save = True
                if _restrict_to_save:
                    _allow_after_run = {"save_result_page", "file_write", "document_read", "file_read"}
                    _tools_save_only = [t for t in _tools_req if isinstance(t, dict) and ((t.get("function") or {}).get("name") or "") in _allow_after_run]
                    # Profile may not include these; fetch from registry so we can restrict to them.
                    if not _tools_save_only and registry:
                        try:
                            _all_reg = registry.get_openai_tools(_max_desc if _max_desc else None)
                            _tools_save_only = [t for t in (_all_reg or []) if isinstance(t, dict) and ((t.get("function") or {}).get("name") or "") in _allow_after_run]
                        except Exception:
                            pass
                    if _tools_save_only:
                        _tools_req = _tools_save_only
                        _component_log("tools", "restricted to save_result_page, file_write, document_read, file_read this turn (last result was instruction-only or already run)")
                _tool_choice_req = "none" if _greeting_only else "auto"
                try:
                    msg = await Util().openai_chat_completion_message(
                        _msgs_for_llm, tools=_tools_req, tool_choice=_tool_choice_req, grammar=_use_grammar, llm_name=llm_name_this_turn,
                        max_tokens_override=_max_tokens_override, stop_extra=_stop_extra,
                    )
                except Exception as e:
                    logger.warning("LLM call failed (will try fallback if available): {}", e)
                    msg = None
                _elapsed = time.time() - _t0
                logger.debug("LLM call returned in {:.1f}s", _elapsed)
                if msg is not None:
                    _content = (msg.get("content") or "").strip()
                    _tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
                    # Count usable tool_calls (have function.name) so we can treat "truncated/malformed" as no tool_calls
                    _usable_tool_calls = [tc for tc in (_tool_calls or []) if isinstance(tc, dict) and isinstance((tc.get("function") or {}), dict) and ((tc.get("function") or {}).get("name") or "").strip()]
                    # Empty content is normal when the model returns tool_calls (many local servers omit text). Only warn when there are no tool_calls.
                    if (not _content or len(_content) < 10) and not _usable_tool_calls:
                        _log_empty = logger.debug if mix_route_this_request else logger.warning
                        _log_empty(
                            "Local LLM returned empty or very short content (len={}) in {:.1f}s — ensure the server on the logged host:port is the correct model and fully loaded (e.g. llama-server for main_llm_port).",
                            len(_content), _elapsed,
                        )
                    # When tool_selection_llm returned content only (no tool call), optionally use main_llm for the reply so the final response to the user comes from the main model (first turn or after tools). Default true.
                    if (
                        msg is not None
                        and openai_tools
                        and _tool_sel
                        and _use_tool_sel
                        and not _usable_tool_calls
                        and getattr(Util().get_core_metadata(), "use_main_llm_for_direct_reply", True)
                    ):
                        try:
                            msg_main = await Util().openai_chat_completion_message(
                                _msgs_for_llm, tools=None, tool_choice="auto", grammar=None, llm_name=effective_llm_name,
                                max_tokens_override=_max_tokens_override, stop_extra=None,
                            )
                            if msg_main is not None and isinstance(msg_main, dict):
                                msg = msg_main
                                _content = (msg.get("content") or "").strip()
                                _tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
                                _usable_tool_calls = [tc for tc in (_tool_calls or []) if isinstance(tc, dict) and isinstance((tc.get("function") or {}), dict) and ((tc.get("function") or {}).get("name") or "").strip()]
                        except Exception as e_main:
                            logger.debug("use_main_llm_for_direct_reply call failed: {}", e_main)
                # Mix fallback: retry with the other route when (1) first model raised / returned None (e.g. 4xx), (2) first model returned empty content and no usable tool_calls, or (3) cloud returned finish_reason=length (truncation) — retry that turn with local so we get higher max_tokens.
                _truncated = isinstance(msg, dict) and (msg.get("_finish_reason") or "").strip() == "length"
                _should_fallback = msg is None or (
                    isinstance(msg, dict)
                    and (not (msg.get("content") or "").strip() or len((msg.get("content") or "").strip()) < 10)
                    and not [tc for tc in (msg.get("tool_calls") or []) if isinstance(tc, dict) and isinstance((tc.get("function") or {}), dict) and ((tc.get("function") or {}).get("name") or "").strip()]
                ) or (mix_route_this_request == "cloud" and _truncated)
                if _should_fallback:
                    _meta_fb = None
                    hr = {}
                    try:
                        _meta_fb = getattr(Util(), "get_core_metadata", None)
                        _meta_fb = _meta_fb() if callable(_meta_fb) else None
                        if _meta_fb is not None:
                            _hr_val = getattr(_meta_fb, "hybrid_router", None)
                            hr = _hr_val if isinstance(_hr_val, dict) else {}
                    except Exception:
                        hr = {}
                    _current_route = mix_route_this_request if mix_route_this_request in ("local", "cloud") else None
                    fallback_ok = bool(hr.get("fallback_on_llm_error", True)) and _current_route is not None
                    if fallback_ok and _meta_fb is not None:
                        _local_ref = (getattr(_meta_fb, "main_llm_local", None) or "").strip()
                        _cloud_ref = (getattr(_meta_fb, "main_llm_cloud", None) or "").strip()
                        if _local_ref and _cloud_ref:
                            other_route = "cloud" if _current_route == "local" else "local"
                            other_llm = _cloud_ref if other_route == "cloud" else _local_ref
                            # Retry with other model (local->cloud or cloud->local); applies when override model failed or any model returned empty/truncated
                            if other_llm:
                                _reason = "first model failed" if msg is None else ("cloud truncated (finish_reason=length); retrying with local" if _truncated else "local returned empty or no usable tool_calls (e.g. truncated); retrying with cloud")
                                _component_log("mix", "{} — retrying with {} ({})".format(_reason, other_route, other_llm))
                                # Sanitize so cloud API never sees orphaned 'tool' messages (DeepSeek etc. require tool to follow assistant with tool_calls)
                                _msgs_for_cloud = _messages_sanitized_for_tool_role(current_messages)
                                try:
                                    msg = await Util().openai_chat_completion_message(
                                        _msgs_for_cloud, tools=openai_tools, tool_choice="auto", grammar=_use_grammar, llm_name=other_llm,
                                        stop_extra=_stop_extra,
                                    )
                                    if msg is not None:
                                        mix_route_this_request = other_route
                                        effective_llm_name = other_llm  # use working model for rest of tool rounds
                                        _layer_prev = mix_route_layer_this_request if isinstance(mix_route_layer_this_request, str) else ""
                                        mix_route_layer_this_request = (_layer_prev + "_fallback") if _layer_prev else "fallback"
                                except Exception as e2:
                                    logger.warning("Fallback LLM call also failed: {}", e2)
                                    msg = None
                    if msg is None:
                        response = None
                        break
                if msg is None or not isinstance(msg, dict):
                    response = None
                    break
                _last_finish_reason = msg.get("_finish_reason") if isinstance(msg, dict) else None
                _msg_to_append = {k: v for k, v in msg.items() if k != "_finish_reason"} if isinstance(msg, dict) else msg
                current_messages.append(_msg_to_append)
                tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else None
                content_str = (msg.get("content") or "").strip() if isinstance(msg.get("content"), str) else ""
                # On tool-selection rounds the server may put output in reasoning_content and leave content empty; use it only for parsing <tool_call>, never as the user-facing reply.
                content_str_from_reasoning = False
                try:
                    _rc = msg.get("reasoning_content") if isinstance(msg, dict) else None
                    if not content_str and _rc is not None and isinstance(_rc, str) and _rc.strip() and "<tool_call>" in _rc:
                        content_str = _rc.strip()
                        content_str_from_reasoning = True
                except Exception:
                    pass
                # Some backends return tool_call as raw text in content instead of structured tool_calls (supports multiple <tool_call>...</tool_call> in one turn)
                _parsed_raw = _parse_raw_tool_calls_from_content(content_str) if (not tool_calls and content_str) else None
                if _parsed_raw:
                    tool_calls = _parsed_raw
                    # So the next LLM round sees a proper assistant message with tool_calls (ids must match tool result messages). Sanitize so each item has type="function" (required by OpenAI/llama.cpp/DeepSeek).
                    if tool_calls and current_messages and isinstance(current_messages[-1], dict) and (current_messages[-1].get("role") or "").strip() == "assistant":
                        current_messages[-1] = dict(current_messages[-1])
                        current_messages[-1]["tool_calls"] = _sanitize_tool_calls(tool_calls)
                # For search-intent queries, ignore wrong tool (e.g. exec) parsed from content so web_search fallback can run
                if tool_calls and isinstance(query, str) and len(tool_calls) == 1:
                    _fn = tool_calls[0].get("function") if isinstance(tool_calls[0], dict) else {}
                    _name = (_fn.get("name") or "").strip().lower() if isinstance(_fn, dict) else ""
                    if _name == "exec":
                        _search_q = (query or "").strip().lower()
                        if any(p in _search_q for p in ("搜", "search", "上网", "find", "look up", "latest", "news", "movies", "结果", "results")):
                            tool_calls = None
                            logger.debug("Ignoring parsed exec tool_call for search-intent query; web_search fallback will run if model does not call tool.")
                if not tool_calls:
                    logger.debug(
                        "LLM returned no tool_calls (content={})",
                        _truncate_for_log(content_str or "(empty)", 120),
                    )
                    # Grammar returned literal NO_TOOL_REQUIRED: get the actual reply by retrying without tools so the user doesn't see that string.
                    if content_str and (content_str.strip() == "NO_TOOL_REQUIRED"):
                        try:
                            msg_no_tools = await Util().openai_chat_completion_message(
                                _msgs_for_llm, tools=None, tool_choice="auto", grammar=None, llm_name=llm_name_this_turn,
                                max_tokens_override=_max_tokens_override, stop_extra=None,
                            )
                            if msg_no_tools and isinstance(msg_no_tools.get("content"), str) and msg_no_tools.get("content").strip():
                                _tc = msg_no_tools.get("tool_calls") or []
                                if not any((t.get("function") or {}).get("name") for t in _tc if isinstance(t, dict)):
                                    response = (msg_no_tools.get("content") or "").strip()
                                    if "<think>" in response or "</think>" in response:
                                        response = strip_reasoning_from_assistant_text(response)
                                    if response and len(response.strip()) > 0:
                                        logger.debug("NO_TOOL_REQUIRED: using plain reply from no-tools retry (len=%s)", len(response))
                                        break
                        except Exception as _e:
                            logger.debug("NO_TOOL_REQUIRED retry without tools failed: {}", _e)
                        # Fallback so user never sees literal NO_TOOL_REQUIRED (retry failed or returned empty)
                        if not response or str(response).strip() == "NO_TOOL_REQUIRED":
                            response = "What can I help you with?"
                    # If content looks like raw tool_call but we didn't parse it, avoid sending raw tags to the user.
                    # Model may output valid text then a stray <tool_call> (e.g. reasoning or incomplete tag); use text before <tool_call> if substantial.
                    if content_str and ("<tool_call>" in content_str or "</tool_call>" in content_str):
                        _before_tag = content_str.split("<tool_call>")[0].strip()
                        # Strip <think>...</think> so user never sees reasoning (model may still emit it even with reasoning_budget: 0)
                        if "<think>" in _before_tag or "</think>" in _before_tag:
                            _before_tag = strip_reasoning_from_assistant_text(_before_tag)
                        if len(_before_tag) >= 20:
                            response = _before_tag
                            logger.debug("Using content before stray <tool_call> as response (len=%s)", len(_before_tag))
                            # If we already ran folder_list/file_find, append the formatted list so the user sees the actual files
                            if last_tool_name in ("file_find", "folder_list") and last_tool_result_raw and isinstance(last_tool_result_raw, str):
                                _formatted = format_folder_list_file_find_result(last_tool_result_raw, is_file_find=(last_tool_name == "file_find"))
                                if _formatted:
                                    response = (response or "").strip() + "\n\n" + _formatted
                            # Same as below: if user asked for slides and _before_tag has a real ```html block, extract and save so user gets a link
                            if (
                                response and not last_file_link_result and registry
                                and ("```html" in (response or "") or "```HTML" in (response or ""))
                            ):
                                _q_lower = (query or "").strip().lower()
                                _q_raw = (query or "").strip()
                                _slides_ask = any(p in _q_lower for p in ("slide", "slides", "html", "report", "ppt")) or any(
                                    p in _q_raw for p in ("总结", "生成", "幻灯片")
                                )
                                if _slides_ask:
                                    try:
                                        _m = re.search(r"```(?:html|HTML)\s*([\s\S]*?)```", response)
                                        if _m and _m.group(1):
                                            _html = _m.group(1).strip()
                                            # Skip placeholder blocks (e.g. "(full 乔布斯-style... layout) ... </ body ></html")
                                            _placeholder = ("(full " in _html or "..." in _html) and len(_html) < 800
                                            if len(_html) > 200 and "</html>" in _html.lower() and not _placeholder:
                                                _title = "Slides"
                                                _save_args = {"title": _title, "content": _html, "format": "html"}
                                                _link_result = await registry.execute_async("save_result_page", _save_args, context)
                                                if isinstance(_link_result, str) and (
                                                    "/files/out" in _link_result or ("http" in _link_result and "/files/" in _link_result)
                                                ):
                                                    for _line in _link_result.splitlines():
                                                        if "token=" in _line or ("http" in _line and "/files/" in _line):
                                                            _link_result = _line.strip()
                                                            break
                                                    response = _link_result
                                                    _component_log("tools", "save_result_page fallback: extracted HTML from content-before-tool_call; returning link")
                                    except Exception as _e:
                                        logger.debug("save_result_page fallback (html from content before <tool_call>) failed: {}", _e)
                        else:
                            # Content before <tool_call> was short (truncated or malformed). Before showing generic error: retry with other model if mix + document_read + slides intent (same as mix fallback in default branch).
                            _slides_retry = False
                            if mix_route_this_request and last_tool_name == "document_read" and registry and isinstance(current_messages, list) and len(current_messages) > 0:
                                _last_msg = current_messages[-1] if current_messages else None
                                if isinstance(_last_msg, dict) and (_last_msg.get("role") or "").strip() == "assistant":
                                    _q = (query or "").strip().lower()
                                    _q_raw = (query or "").strip()
                                    _slides_intent = any(p in _q for p in ("slide", "slides", "html", "report", "ppt")) or any(p in _q_raw for p in ("总结", "生成", "幻灯片"))
                                    if _slides_intent:
                                        try:
                                            _meta = Util().get_core_metadata()
                                            _cloud = (getattr(_meta, "main_llm_cloud", None) or "").strip()
                                            _local = (getattr(_meta, "main_llm_local", None) or "").strip()
                                            _is_local = mix_route_this_request == "local"
                                            if _is_local and _cloud:
                                                current_messages.pop()
                                                effective_llm_name = _cloud
                                                mix_route_this_request = "cloud"
                                                mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_slides_fallback"
                                                response = None
                                                _slides_retry = True
                                                _component_log("tools", "stray/truncated tool_call after document_read; retrying turn with cloud for slides")
                                                continue
                                            if not _is_local and _local:
                                                current_messages.pop()
                                                effective_llm_name = _local
                                                mix_route_this_request = "local"
                                                mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_slides_fallback"
                                                response = None
                                                _slides_retry = True
                                                continue
                                        except Exception as _e:
                                            logger.debug("Mix slides_fallback (stray tool_call branch) failed: {}", _e)
                            if not _slides_retry:
                                # Short greeting with malformed tool output: retry this turn without tools so the model returns plain text.
                                _q = (query or "").strip()
                                _greeting = len(_q) <= 40 and any(
                                    (p in _q.lower() if p.isascii() else p in _q) for p in ("你好", "hi", "hello", "嗨", "hey", "help")
                                )
                                if _greeting:
                                    try:
                                        msg_no_tools = await Util().openai_chat_completion_message(
                                            _msgs_for_llm, tools=None, tool_choice="auto", grammar=None, llm_name=llm_name_this_turn,
                                            max_tokens_override=_max_tokens_override, stop_extra=None,
                                        )
                                        if msg_no_tools and isinstance(msg_no_tools.get("content"), str) and msg_no_tools.get("content").strip():
                                            _tc = msg_no_tools.get("tool_calls") or []
                                            if not any((t.get("function") or {}).get("name") for t in _tc if isinstance(t, dict)):
                                                response = (msg_no_tools.get("content") or "").strip()
                                                if "<think>" in response or "</think>" in response:
                                                    response = strip_reasoning_from_assistant_text(response)
                                                if response and len(response.strip()) > 0:
                                                    logger.debug("Greeting/no-tool retry: using plain reply (len=%s)", len(response))
                                                    break
                                    except Exception as _e:
                                        logger.debug("Greeting retry without tools failed: {}", _e)
                                # Malformed tool_call (e.g. name="") but model may have put the actual reply in <response>...</response> or similar
                                _extracted = None
                                try:
                                    _m = re.search(r"<response\s*>([\s\S]*?)</re?sponse\s*>", content_str or "", re.IGNORECASE)
                                    if _m and _m.group(1):
                                        _extracted = _m.group(1).strip()
                                    if not _extracted and content_str:
                                        # After first </tool_call>, take short text that looks like a reply (e.g. 我是Homecl)
                                        _parts = (content_str or "").split("</tool_call>", 1)
                                        if len(_parts) > 1:
                                            _after = _parts[1].strip()
                                            _after = re.sub(r"<[^>]+>", " ", _after).strip()
                                            _after = _after.split("<")[0].strip() if "<" in _after else _after
                                            if 2 <= len(_after) <= 300 and any(p in _after for p in ("我是", "你好", "hello", "hi", "help")):
                                                _extracted = _after
                                        # Malformed tool_call without </tool_call>, e.g. <tool_call><tool>echo</tools>(text="我是 HomeClaw") — extract (text="...") as reply
                                        if not _extracted and content_str and "<tool_call>" in content_str:
                                            _m_echo = re.search(r'\(\s*text\s*=\s*["\']([^"\']*)["\']\s*\)', content_str)
                                            if _m_echo and 2 <= len(_m_echo.group(1)) <= 300:
                                                _extracted = _m_echo.group(1).strip()
                                    if _extracted and 2 <= len(_extracted) <= 500:
                                        response = _extracted
                                        logger.debug("Using extracted reply from malformed tool_call content (len=%s)", len(_extracted))
                                    else:
                                        response = "The assistant tried to use a tool but the response format was not recognized. Please try again."
                                except Exception:
                                    response = "The assistant tried to use a tool but the response format was not recognized. Please try again."
                    else:
                        # Default: use LLM's reply so we never leave response unset (e.g. simple "你好" -> friendly reply)
                        # Do not surface content that came from reasoning_content on tool-selection rounds (it was used only for parsing <tool_call>).
                        if content_str_from_reasoning:
                            response = None
                        else:
                            # Strip <think>...</think> so user never sees reasoning (model may still emit it even with reasoning_budget: 0)
                            if content_str and ("<think>" in content_str or "</think>" in content_str):
                                content_str = strip_reasoning_from_assistant_text(content_str)
                            # Never show literal NO_TOOL_REQUIRED to user (grammar output); keep existing response or friendly fallback
                            if content_str and content_str.strip() == "NO_TOOL_REQUIRED":
                                if not response or str(response).strip() == "NO_TOOL_REQUIRED":
                                    response = "What can I help you with?"
                            else:
                                response = content_str if (content_str and content_str.strip()) else None
                        # Fallback: model returned full HTML in content instead of calling save_result_page — extract and save so user gets a link.
                        if (
                            response
                            and not last_file_link_result
                            and ("```html" in (response or "") or "```HTML" in (response or ""))
                            and registry
                        ):
                            _q_lower = (query or "").strip().lower()
                            _q_raw = (query or "").strip()
                            _slides_ask = any(p in _q_lower for p in ("slide", "slides", "html", "report", "ppt")) or any(
                                p in _q_raw for p in ("总结", "生成", "幻灯片")
                            )
                            if _slides_ask:
                                try:
                                    _m = re.search(r"```(?:html|HTML)\s*([\s\S]*?)```", response)
                                    if _m and _m.group(1):
                                        _html = _m.group(1).strip()
                                        _ph = ("(full " in _html or "..." in _html) and len(_html) < 800
                                        if len(_html) > 200 and "</html>" in _html.lower() and not _ph:
                                            _title = "Slides"  # or from query; keep short
                                            _save_args = {"title": _title, "content": _html, "format": "html"}
                                            _link_result = await registry.execute_async("save_result_page", _save_args, context)
                                            if isinstance(_link_result, str) and (
                                                "/files/out" in _link_result or ("http" in _link_result and "/files/" in _link_result)
                                            ):
                                                for _line in _link_result.splitlines():
                                                    if "token=" in _line or ("http" in _line and "/files/" in _line):
                                                        _link_result = _line.strip()
                                                        break
                                                response = _link_result
                                                _component_log("tools", "save_result_page fallback: extracted HTML from reply and saved; returning link")
                                except Exception as _e:
                                    logger.debug("save_result_page fallback (extract HTML from reply) failed: {}", _e)
                        # Fallback: long Markdown or document-like text in content — save to file and return link (avoids truncation when model puts long output in message instead of tool call).
                        if (
                            response
                            and not last_file_link_result
                            and registry
                            and len((response or "").strip()) > 250
                        ):
                            _to_save = None
                            _fmt = "markdown"
                            _title = "Report"
                            if "```markdown" in (response or "") or "```md" in (response or "").lower():
                                _m = re.search(r"```(?:markdown|md)\s*([\s\S]*?)```", response, re.IGNORECASE)
                                if _m and _m.group(1) and len(_m.group(1).strip()) > 500:
                                    _to_save = _m.group(1).strip()
                            elif len((response or "").strip()) > 4000 and (
                                (response or "").strip().startswith("#") or "## " in (response or "")
                            ):
                                _to_save = (response or "").strip()
                            if _to_save:
                                try:
                                    _save_args = {"title": _title, "content": _to_save, "format": "markdown"}
                                    _link_result = await registry.execute_async("save_result_page", _save_args, context)
                                    if isinstance(_link_result, str) and (
                                        "/files/out" in _link_result or ("http" in _link_result and "/files/" in _link_result)
                                    ):
                                        for _line in _link_result.splitlines():
                                            if "token=" in _line or ("http" in _line and "/files/" in _line):
                                                _link_result = _line.strip()
                                                break
                                        response = _link_result
                                        _component_log("tools", "save_result_page fallback: saved long markdown/document from reply; returning link")
                                except Exception as _e:
                                    logger.debug("save_result_page fallback (markdown from reply) failed: {}", _e)
                        # Mix fallback: user asked for slides/report, last tool was document_read, but model returned a plan (no tool_calls)—retry this turn with the other model so it can call run_skill(html-slides) / save_result_page.
                        if mix_route_this_request and last_tool_name == "document_read" and (content_str or "").strip():
                            _q = (query or "").strip().lower()
                            _q_raw = (query or "").strip()
                            _slides_intent = any(
                                p in _q for p in ("slide", "slides", "html", "report", "ppt")
                            ) or any(p in _q_raw for p in ("总结", "生成", "幻灯片"))
                            if _slides_intent:
                                try:
                                    _meta = Util().get_core_metadata()
                                    _cloud = (getattr(_meta, "main_llm_cloud", None) or "").strip()
                                    _local = (getattr(_meta, "main_llm_local", None) or "").strip()
                                    _is_local = mix_route_this_request == "local"
                                    if _is_local and _cloud and current_messages and len(current_messages) > 0 and current_messages[-1].get("role") == "assistant":
                                        current_messages.pop()
                                        effective_llm_name = _cloud
                                        mix_route_this_request = "cloud"
                                        mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_slides_fallback"
                                        response = None
                                        continue
                                    if not _is_local and _local and current_messages and len(current_messages) > 0 and current_messages[-1].get("role") == "assistant":
                                        current_messages.pop()
                                        effective_llm_name = _local
                                        mix_route_this_request = "local"
                                        mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_slides_fallback"
                                        response = None
                                        continue
                                except Exception as _e:
                                    logger.debug("Mix slides_fallback check failed: {}", _e)
                        # After run_skill(html-slides) the skill returns "Instruction-only... You MUST in this turn: generate and save_result_page". If local returned plan-like text (e.g. "我将现在生成...首先，我需要调用 document_read") with no tool_calls, retry this turn with cloud so cloud can actually generate and call save_result_page.
                        if (
                            mix_route_this_request == "local"
                            and last_tool_name == "run_skill"
                            and response
                            and isinstance(last_tool_result_raw, str)
                            and ("Instruction-only skill" in last_tool_result_raw or "You MUST in this turn" in last_tool_result_raw)
                            and any(
                                p in (response or "")
                                for p in ("我将现在生成", "首先，我需要调用", "I will call document_read", "First, I need to call document_read")
                            )
                            and current_messages
                            and isinstance(current_messages[-1], dict)
                            and (current_messages[-1].get("role") or "").strip() == "assistant"
                        ):
                            try:
                                _cloud = (getattr(Util().get_core_metadata(), "main_llm_cloud", None) or "").strip()
                                if _cloud:
                                    current_messages.pop()
                                    effective_llm_name = _cloud
                                    mix_route_this_request = "cloud"
                                    mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_slides_fallback"
                                    response = None
                                    _component_log("mix", "local returned plan after run_skill(instruction-only); retrying with cloud to generate and save_result_page")
                                    continue
                            except Exception as _e:
                                logger.debug("Mix run_skill plan fallback failed: {}", _e)
                        # When model returned empty after we ran file_find/folder_list, show the list so the user sees the files (e.g. "list images" -> file_find ran but second LLM returned empty).
                        if (not response or not str(response).strip()) and last_tool_name in ("file_find", "folder_list") and last_tool_result_raw and isinstance(last_tool_result_raw, str):
                            formatted = format_folder_list_file_find_result(last_tool_result_raw, is_file_find=(last_tool_name == "file_find"))
                            if formatted:
                                response = formatted
                            # If formatted is None (error message or invalid JSON), leave response as-is; user may see tool error message in next fallback or we show generic below
                        # When strict_fallback is true (default): do not auto-invoke any tool; let the model drive decisions. Only use model reply or prior tool result (above).
                        meta_tools = Util().get_core_metadata()
                        tools_cfg = getattr(meta_tools, "tools_config", None) or {}
                        _strict_fallback = bool(tools_cfg.get("strict_fallback", True))
                        if not _strict_fallback:
                            # Legacy fallbacks: only when strict_fallback is false (opt-in).
                            content_lower = (content_str or "").strip().lower()
                            unhelpful_for_auto_invoke = (
                                not content_str or len(content_str) < 100
                                or any(phrase in content_lower for phrase in (
                                    "no tool", "don't have", "doesn't have", "not have", "not available", "no image tool", "no such tool",
                                    "can't generate", "cannot generate", "i'm sorry", "i cannot",
                                    "stderr:", "modulenotfounderror", "traceback", "no module named",
                                    "error occurred while generating", "error while generating", "please try again",
                                ))
                            )
                            any_always_run = any(inv.get("always_run") for inv in (force_include_auto_invoke or []) if isinstance(inv, dict))
                            run_force_include = bool(force_include_auto_invoke and registry and (unhelpful_for_auto_invoke or any_always_run))
                            _component_log("tools", "model returned no tool_calls; unhelpful={} auto_invoke_count={} run_force_include={}".format(unhelpful_for_auto_invoke, len(force_include_auto_invoke or []), run_force_include))
                        else:
                            run_force_include = False
                        # When strict_fallback is True, still run folder_list fallback for clear "list directory" queries so user gets file list even if model returned only reasoning/no tool_calls.
                        if _strict_fallback and isinstance(query, str) and registry and any(t.name == "folder_list" for t in (registry.list_tools() or [])):
                            _list_dir_phrases = (
                                "目录", "哪些文件", "列出文件", "目录下", "列出", "有什么文件", "文件列表", "我的文件", "看看文件", "显示文件", "我都有哪些文件",
                                "list file", "list files", "list directory", "list folder", "list content", "what file", "what's in my", "files in my", "list my files", "what files do i have",
                                "folder content", "folder list", "file list", "show file", "show files", "show directory", "show folder", "view file", "view directory",
                                "files in documents", "documents folder", "what files in", "in the documents", "in documents",
                            )
                            _q_lo = (query or "").strip().lower()
                            _q_raw = (query or "").strip()
                            if any((p in _q_lo if p.isascii() else p in _q_raw) for p in _list_dir_phrases):
                                _fallback_path = "."
                                for _key in ("documents", "downloads", "output", "images", "work", "knowledge", "share"):
                                    if _key in _q_lo or _key in _q_raw:
                                        _fallback_path = _key
                                        break
                                try:
                                    _component_log("tools", "fallback folder_list (strict_fallback=True; model did not call tool)")
                                    _res = await registry.execute_async("folder_list", {"path": _fallback_path}, context)
                                    if isinstance(_res, str) and _res.strip():
                                        _fmt = format_folder_list_file_find_result(_res, is_file_find=False)
                                        response = _fmt if _fmt else _res
                                    else:
                                        response = "Directory is empty or could not be listed."
                                except Exception as e:
                                    logger.debug("Fallback folder_list failed: {}", e)
                        # When strict_fallback is True, run web_search fallback for clear "search the web" queries when model returned no tool_calls (e.g. model said "I will use web_search" but didn't call it).
                        if _strict_fallback and isinstance(query, str) and registry and any(t.name == "web_search" for t in (registry.list_tools() or [])):
                            _search_phrases = (
                                "上网搜", "搜一下", "搜索", "查一下", "有什么好看", "有什么好听的", "最新", "latest", "search the web", "search for ",
                                "find information", "look up", "current news", "recent news", "good movies", "popular movies",
                                "just search", "give me results", "直接给结果", "搜一下结果", "search and ",
                            )
                            _q_lo_sw = (query or "").strip().lower()
                            _q_raw_sw = (query or "").strip()
                            if any((p in _q_lo_sw if p.isascii() else p in _q_raw_sw) for p in _search_phrases):
                                try:
                                    _search_query = (query or "").strip() or "trending now"
                                    if len(_search_query) < 5 and "result" in _q_lo_sw:
                                        _search_query = "popular movies and trending topics"
                                    _component_log("tools", "fallback web_search (strict_fallback=True; model did not call tool)")
                                    _res = await registry.execute_async("web_search", {"query": _search_query, "count": 8}, context)
                                    if isinstance(_res, str) and _res.strip() and "error" not in _res[:200].lower():
                                        response = format_json_for_user(_res) or _res.strip()
                                    elif isinstance(_res, str) and _res.strip():
                                        response = _res.strip()
                                except Exception as e_sw:
                                    logger.debug("Fallback web_search failed: {}", e_sw)
                        # Log when user clearly asked for scheduling but model didn't call any tool (informational only; no auto-invoke when strict_fallback).
                        # Do not log if we already ran remind_me/cron_schedule/route_to_tam this request (e.g. model replied with text after a successful reminder).
                        if isinstance(query, str) and _query_looks_like_scheduling(query) and registry and last_tool_name not in ("remind_me", "cron_schedule", "route_to_tam"):
                            try:
                                _tool_names = [getattr(t, "name", None) for t in (registry.list_tools() or []) if getattr(t, "name", None)]
                                if any(n in _tool_names for n in ("cron_schedule", "remind_me", "route_to_tam")):
                                    logger.info(
                                        "TAM did not set schedule: user asked for scheduling/reminder but model returned no tool_calls (no cron_schedule/remind_me/route_to_tam invoked). Suggest user rephrase e.g. 'remind me at 8am' or 'every 4 hours remind me to chat'."
                                    )
                            except Exception:
                                pass
                        if not _strict_fallback:
                            if isinstance(query, str) and force_include_auto_invoke and any(
                                inv.get("tool") == "folder_list" for inv in (force_include_auto_invoke or []) if isinstance(inv, dict)
                            ):
                                logger.info(
                                    "User asked to list a folder (e.g. 'what files in documents folder') but model returned no tool_calls; running folder_list via force_include (local models often omit tool calls)."
                                )
                            if run_force_include:
                                _local_file_phrases = (
                                    "list images", "search images", "image files", "list file", "list files", "list directory", "list folder",
                                    "documents folder", "files in documents", "what files in", "folder list", "files in my", "what's in my",
                                    "目录", "哪些文件", "列出文件", "文件列表", "图片", "列出图片", "搜索图片", "我的图片", "local images", "my images",
                                )
                                _q_lo_fi = (query or "").strip().lower()
                                _q_raw_fi = (query or "").strip()
                                _local_file_intent = any((p in _q_lo_fi if p.isascii() else p in _q_raw_fi) for p in _local_file_phrases)
                                ran = False
                                for inv in (force_include_auto_invoke or []):
                                    if not isinstance(inv, dict):
                                        continue
                                    tname = inv.get("tool") or ""
                                    targs = inv.get("arguments") or {}
                                    if not tname or not isinstance(targs, dict):
                                        continue
                                    if not any(t.name == tname for t in (registry.list_tools() or [])):
                                        continue
                                    # When user clearly asked for local files, only run folder_list or file_find; skip run_skill/route_to_plugin so we don't run web search.
                                    if _local_file_intent and tname not in ("folder_list", "file_find"):
                                        continue
                                    try:
                                        _component_log("tools", f"fallback auto_invoke {tname} (model did not call tool)")
                                        if tname == "run_skill":
                                            _component_log("tools", "executing run_skill (in_process from run_skill_py_in_process_skills if listed)")
                                        result = await registry.execute_async(tname, targs, context)
                                        if result == ROUTING_RESPONSE_ALREADY_SENT:
                                            return (ROUTING_RESPONSE_ALREADY_SENT, None)
                                        if isinstance(result, str) and result.strip():
                                            # Format folder_list/file_find JSON as user-friendly text so the user does not see raw JSON
                                            if tname in ("folder_list", "file_find"):
                                                formatted = format_folder_list_file_find_result(result, is_file_find=(tname == "file_find"))
                                                response = formatted if formatted else result
                                            elif (result.strip() == "(no output)" or not result.strip()) and (content_str or "").strip():
                                                # General rule: auto_invoke tool returned empty/placeholder; keep model's existing reply instead of replacing with "(no output)"
                                                response = content_str.strip()
                                            else:
                                                response = result
                                            ran = True
                                        break
                                    except Exception as e:
                                        logger.debug("Fallback auto_invoke {} failed: {}", tname, e)
                                if not ran:
                                    response = content_str
                            else:
                                # Fallback: model didn't call a tool.
                                remind_fallback = None
                                # Run folder_list fallback first when user asked to list files/folder, so we don't overwrite with remind_me clarification (e.g. "images里有哪些文件" matched remind_me_needs_clarification and never got the list).
                                _list_dir_phrases_first = (
                                    "目录", "哪些文件", "列出文件", "目录下", "列出", "有什么文件", "文件列表", "我的文件", "看看文件", "显示文件", "我都有哪些文件",
                                    "list file", "list files", "list directory", "list folder", "list content", "what file", "what's in my", "files in my", "list my files", "what files do i have",
                                    "folder content", "folder list", "file list", "show file", "show files", "show directory", "show folder", "view file", "view directory",
                                    "files in documents", "documents folder", "what files in", "in the documents", "in documents",
                                )
                                _ql_first = (query or "").strip().lower()
                                _qr_first = (query or "").strip()
                                _list_dir_match = registry and any(t.name == "folder_list" for t in (registry.list_tools() or [])) and any(
                                    (p in _ql_first if p.isascii() else p in _qr_first) for p in _list_dir_phrases_first
                                )
                                if _list_dir_match:
                                    _fallback_path = "."
                                    for _key in ("documents", "downloads", "output", "images", "work", "knowledge", "share"):
                                        if _key in _ql_first or _key in _qr_first:
                                            _fallback_path = _key
                                            break
                                    try:
                                        _component_log("tools", "fallback folder_list (model did not call tool)")
                                        _res = await registry.execute_async("folder_list", {"path": _fallback_path}, context)
                                        if isinstance(_res, str) and _res.strip():
                                            _fmt = format_folder_list_file_find_result(_res, is_file_find=False)
                                            response = _fmt if _fmt else _res
                                        else:
                                            response = content_str or "Directory is empty or could not be listed."
                                    except Exception as e:
                                        logger.debug("Fallback folder_list failed: {}", e)
                                        response = content_str or "Could not list directory. Please try again."
                                # Check remind_me (e.g. "15分钟后有个会能提醒一下吗") so we set the reminder and return a clean response instead of messy 2:49 text.
                                if response is None or (response == content_str and not _list_dir_match):
                                    try:
                                        remind_fallback = _infer_remind_me_fallback(query) if query else None
                                    except Exception:
                                        remind_fallback = None
                                _remind_me_ask_generic = "您希望什么时候提醒？例如：「15分钟后」或「下午3点」。 When would you like to be reminded? E.g. in 15 minutes or at 3:00 PM."
                                def _remind_me_ask_message():
                                    try:
                                        q = _remind_me_clarification_question(query) if query else None
                                        out = (q or _remind_me_ask_generic) or ""
                                        return str(out).strip()
                                    except Exception:
                                        return str(_remind_me_ask_generic).strip()
                                _has_remind_me = False
                                try:
                                    if registry:
                                        _tools = registry.list_tools() or []
                                        _has_remind_me = any(getattr(t, "name", None) == "remind_me" for t in _tools)
                                except Exception:
                                    pass
                                if remind_fallback and isinstance(remind_fallback, dict) and _has_remind_me and last_tool_name != "remind_me":
                                    try:
                                        _component_log("tools", "fallback remind_me (model did not call tool)")
                                        _args = remind_fallback.get("arguments") if isinstance(remind_fallback.get("arguments"), dict) else {}
                                        result = await registry.execute_async("remind_me", _args, context)
                                        if isinstance(result, str) and result.strip():
                                            if "provide either minutes" in result or "at_time" in result:
                                                response = _remind_me_ask_message()
                                            else:
                                                # If remind_me is in needs_llm_tools, do a second LLM round so the model synthesizes a proper reply (don't trust 1st LLM content when it didn't call the tool).
                                                meta = Util().get_core_metadata()
                                                use_result_config = (getattr(meta, "tools_config", None) or {}).get("use_result_as_response") if meta else None
                                                if not _tool_result_usable_as_final_response("remind_me", result, use_result_config, _args):
                                                    tcid = "fallback_remind_me_1"
                                                    current_messages.append({
                                                        "role": "assistant",
                                                        "content": "",
                                                        "tool_calls": [{
                                                            "id": tcid,
                                                            "type": "function",
                                                            "function": {"name": "remind_me", "arguments": json.dumps(_args)},
                                                        }],
                                                    })
                                                    current_messages.append({"role": "tool", "tool_call_id": tcid, "content": result})
                                                    last_tool_name = "remind_me"
                                                    last_tool_result_raw = result
                                                    last_tool_args = _args
                                                    continue
                                                response = result
                                                if mix_route_this_request and mix_show_route_label:
                                                    layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
                                                    label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
                                                    response = label + (_strip_leading_route_label(response or "") or "")
                                        else:
                                            response = content_str or "Reminder set."
                                    except Exception as e:
                                        logger.debug("Fallback remind_me failed: {}", e)
                                        response = _remind_me_ask_message()
                                elif _has_remind_me and last_tool_name != "remind_me":
                                    # Only ask for clarification when we did not already run remind_me this turn (otherwise use LLM's reply)
                                    try:
                                        if _remind_me_needs_clarification(query):
                                            response = _remind_me_ask_message()
                                    except Exception:
                                        pass
                                # When model didn't call any tool and query looks like recurring (e.g. "every day at 9"), try cron_schedule fallback so the reminder is actually set. Never crash.
                                if (response is None or response == content_str) and isinstance(query, str) and query.strip() and _query_looks_like_scheduling(query.strip()):
                                    try:
                                        cron_fallback = _infer_cron_schedule_fallback(query)
                                        _tools_list = (registry.list_tools() or []) if registry else []
                                        _has_cron = any(getattr(t, "name", None) == "cron_schedule" for t in _tools_list)
                                        if cron_fallback and isinstance(cron_fallback.get("arguments"), dict) and registry and _has_cron and last_tool_name != "cron_schedule":
                                            _component_log("tools", "fallback cron_schedule (model did not call tool)")
                                            _cargs = cron_fallback.get("arguments") or {}
                                            result = await registry.execute_async("cron_schedule", _cargs, context)
                                            if isinstance(result, str) and result.strip() and "Error:" not in result:
                                                response = result
                                    except Exception as e:
                                        logger.debug("Fallback cron_schedule failed: {}", e)
                                if response is None or response == content_str:
                                    # Fallback: model didn't call a tool. Use as few fallbacks as possible; if no tools, it may really mean no tools.
                                    unhelpful = not content_str or len(content_str) < 80 or content_str.strip().lower() in ("no", "i can't", "i cannot", "sorry", "nope")
                                    # Do not run route_to_plugin (e.g. web search) when the user clearly asked for local files/images.
                                    _local_intent_phrases = (
                                        "list images", "search images", "image files", "list file", "list files", "list directory", "list folder",
                                        "documents folder", "files in documents", "what files in", "folder list", "files in my", "目录", "哪些文件", "列出文件", "文件列表", "图片", "列出图片", "搜索图片", "我的图片",
                                    )
                                    _ql = (query or "").strip().lower()
                                    _qr = (query or "").strip()
                                    _is_local_file_intent = any((p in _ql if p.isascii() else p in _qr) for p in _local_intent_phrases)
                                    fallback_route = _infer_route_to_plugin_fallback(query) if (unhelpful and not _is_local_file_intent) else None
                                    if isinstance(fallback_route, dict) and fallback_route and registry:
                                        tool_names = [t.name for t in (registry.list_tools() or [])]
                                        if fallback_route.get("tool") == "run_skill" and "run_skill" in tool_names:
                                            try:
                                                _component_log("tools", "fallback run_skill (model did not call tool)")
                                                args = fallback_route.get("arguments") if isinstance(fallback_route.get("arguments"), dict) else {}
                                                result = await registry.execute_async("run_skill", args or {}, context)
                                                if isinstance(result, str) and result.strip():
                                                    response = result
                                                else:
                                                    response = content_str or "Done."
                                            except Exception as e:
                                                logger.debug("Fallback run_skill failed: {}", e)
                                                response = content_str or "The action could not be completed. Try a model that supports tool calling."
                                        elif "route_to_plugin" in tool_names:
                                            try:
                                                _component_log("tools", "fallback route_to_plugin (model did not call tool)")
                                                result = await registry.execute_async("route_to_plugin", fallback_route, context)
                                                if result == ROUTING_RESPONSE_ALREADY_SENT:
                                                    return (ROUTING_RESPONSE_ALREADY_SENT, None)
                                                if isinstance(result, str) and result.strip():
                                                    response = result
                                                else:
                                                    response = content_str or "Done."
                                            except Exception as e:
                                                logger.debug("Fallback route_to_plugin failed: {}", e)
                                                response = content_str or "The action could not be completed. Try a model that supports tool calling."
                                    elif (
                                        registry
                                        and any(t.name == "file_find" for t in (registry.list_tools() or []))
                                        and any(t.name == "document_read" for t in (registry.list_tools() or []))
                                        and "summarize" in (query or "").lower()
                                        and (".pdf" in (query or "") or ".docx" in (query or ""))
                                        and not (content_str and ("/files/out?" in content_str or "已生成" in content_str or "generated" in content_str.lower() or "链接" in content_str or "view link" in content_str.lower()))
                                    ):
                                        # Fallback: user asked to summarize a document but model didn't call file_find/document_read. Skip if model already returned a success (link or "generated").
                                        try:
                                            _component_log("tools", "fallback summarize document (model did not call tool)")
                                            ext = ".pdf" if ".pdf" in (query or "") else ".docx"
                                            pattern = "*" + ext
                                            roots = [(".", "")]
                                            if "share" in (query or "").lower():
                                                roots.append(("share", "share/"))
                                            files = []
                                            for path_arg, prefix in roots:
                                                find_result = await registry.execute_async("file_find", {"path": path_arg, "pattern": pattern}, context)
                                                if isinstance(find_result, str) and find_result.strip():
                                                    try:
                                                        entries = json.loads(find_result)
                                                        if isinstance(entries, list):
                                                            for e in entries:
                                                                if isinstance(e, dict) and e.get("type") == "file":
                                                                    p = (e.get("path") or "").strip()
                                                                    if p and p != "(truncated)":
                                                                        files.append({"path": prefix + p, "name": (e.get("name") or "").strip()})
                                                    except (json.JSONDecodeError, TypeError):
                                                        pass
                                            doc_path = None
                                            if len(files) == 1:
                                                doc_path = files[0]["path"]
                                            elif files:
                                                q_lower = (query or "").lower()
                                                best = max(
                                                    files,
                                                    key=lambda e: sum(1 for w in q_lower.replace(".", " ").split() if len(w) > 2 and w in (e.get("name") or "").lower()),
                                                )
                                                doc_path = best["path"]
                                            if doc_path:
                                                doc_content = await registry.execute_async("document_read", {"path": doc_path}, context)
                                                if isinstance(doc_content, str) and doc_content.strip() and "not found" not in doc_content.lower() and "error" not in doc_content.lower():
                                                    summary_messages = [
                                                        {"role": "user", "content": (
                                                            f"The user asked: {query}\n\n"
                                                            "Provide a concise summary of the following document. Do not invent content; base your summary only on the text below.\n\n"
                                                            "---\n\n" + (doc_content[:120000] if len(doc_content) > 120000 else doc_content)
                                                        )},
                                                    ]
                                                    response = await core.openai_chat_completion(summary_messages, llm_name=effective_llm_name)
                                                    if not response or not response.strip():
                                                        response = "I read the document but could not generate a summary. You can ask for a specific section."
                                                else:
                                                    response = content_str or "Could not read the document. It may be empty or in an unsupported format."
                                            else:
                                                response = content_str or "No matching PDF or document found in your private folder. Try listing files with folder_list or use a more specific filename. Say 'share folder' if the file is in the shared folder."
                                        except Exception as e:
                                            logger.debug("Fallback summarize document failed: {}", e)
                                            response = content_str or "Could not find or summarize the document. Please try again."
                                    else:
                                        # Fallback: user may have asked to list directory (e.g. 你的目录下都有哪些文件) but model didn't call folder_list (common when local model returns no tool_calls)
                                        list_dir_phrases = (
                                            "目录", "哪些文件", "列出文件", "目录下", "列出", "有什么文件", "文件列表", "我的文件", "看看文件", "显示文件", "我都有哪些文件",
                                            "list file", "list files", "list directory", "list folder", "list content", "what file", "what's in my", "files in my", "list my files", "what files do i have",
                                            "folder content", "folder list", "file list", "show file", "show files", "show directory", "show folder", "view file", "view directory",
                                            "files in documents", "documents folder", "what files in", "in the documents", "in documents",
                                        )
                                        _query_lower = (query or "").lower()
                                        _query_raw = query or ""
                                        if registry and any(t.name == "folder_list" for t in (registry.list_tools() or [])) and any(
                                            (p in _query_lower if p.isascii() else p in _query_raw) for p in list_dir_phrases
                                        ):
                                            # Infer subfolder from query so "documents folder" / "files in documents" list documents/, not root
                                            _fallback_path = "."
                                            _sandbox_subdirs = ("documents", "downloads", "output", "images", "work", "knowledge", "share")
                                            for _key in _sandbox_subdirs:
                                                if _key in _query_lower or _key in _query_raw:
                                                    _fallback_path = _key
                                                    break
                                            try:
                                                _component_log("tools", "fallback folder_list (model did not call tool)")
                                                result = await registry.execute_async("folder_list", {"path": _fallback_path}, context)
                                                if isinstance(result, str) and result.strip():
                                                    formatted = format_folder_list_file_find_result(result, is_file_find=False)
                                                    response = formatted if formatted else result
                                                else:
                                                    response = content_str or "Directory is empty or could not be listed."
                                            except Exception as e:
                                                logger.debug("Fallback folder_list failed: {}", e)
                                                response = content_str or "Could not list directory. Please try again."
                                        else:
                                            response = content_str
                    break
                routing_sent = False
                routing_response_text = None  # when route_to_plugin/route_to_tam return text (sync inbound/ws), use as final response
                last_file_link_result = None  # when save_result_page/get_file_view_link return a link, use as final response so model cannot corrupt it
                last_tool_name = None  # for remind_me and fallback when 2nd LLM returns empty
                last_tool_result_raw = None
                last_tool_args = None  # for run_skill: skills_results_need_llm per-skill override
                meta = Util().get_core_metadata()
                tool_timeout_sec = max(0, int(getattr(meta, "tool_timeout_seconds", 120) or 0))
                # Track whether we execute any tool this batch; if we only skip duplicate run_skill(s), return to user after appending results.
                _executed_any_this_batch = False
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    tcid = tc.get("id") or ""
                    fn = tc.get("function")
                    fn = fn if isinstance(fn, dict) else {}
                    name = (fn.get("name") or "").strip()
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    if not isinstance(args, dict):
                        args = {}
                    args_redacted = redact_params_for_log(args) if isinstance(args, dict) else args
                    logger.info("Tool selected: name={} parameters={}", name, args_redacted)
                    # Override document_read path when user specified an explicit path (e.g. documents/norm-v4.pdf) so we use it even if the model returned a wrong path (e.g. norm/v4/pdf).
                    if name == "document_read" and _document_read_forced_path and isinstance(args, dict):
                        args = dict(args)
                        args["path"] = _document_read_forced_path
                        _document_read_forced_path = None  # only override the first document_read for this request
                        logger.info("document_read path overridden to user-specified path: %s", args.get("path"))
                    # remind_me: if model omitted minutes/at_time but user said e.g. "5分钟后", infer from query so execution succeeds (avoids repeated failed tool calls).
                    if name == "remind_me" and isinstance(args, dict) and (query or "").strip():
                        has_minutes = args.get("minutes") is not None
                        has_at_time = bool((args.get("at_time") or "").strip())
                        if not has_minutes and not has_at_time:
                            try:
                                _inferred = _infer_remind_me_fallback((query or "").strip())
                                if isinstance(_inferred, dict) and isinstance(_inferred.get("arguments"), dict):
                                    _ia = _inferred["arguments"]
                                    if _ia.get("minutes") is not None or (_ia.get("at_time") or "").strip():
                                        args = dict(args)
                                        if not has_minutes and _ia.get("minutes") is not None:
                                            args["minutes"] = _ia["minutes"]
                                        if not has_at_time and (_ia.get("at_time") or "").strip():
                                            args["at_time"] = (_ia.get("at_time") or "").strip()
                                        if not (args.get("message") or "").strip() and (_ia.get("message") or "").strip():
                                            args["message"] = (_ia.get("message") or "Reminder").strip()
                                        _component_log("tools", "remind_me: completed missing minutes/at_time from user query (model sent message only)")
                            except Exception as _e:
                                logger.debug("remind_me infer from query failed: {}", _e)
                    # Avoid infinite loop: if remind_me still lacks minutes/at_time and last result was the "provide either minutes" error, skip re-execution and return clarification.
                    _remind_me_skip_repeat = (
                        name == "remind_me"
                        and isinstance(args, dict)
                        and args.get("minutes") is None
                        and not (args.get("at_time") or "").strip()
                        and last_tool_name == "remind_me"
                        and isinstance(last_tool_result_raw, str)
                        and "provide either minutes" in last_tool_result_raw
                    )
                    if name == "run_skill":
                        _component_log("tools", "executing run_skill (in_process from run_skill_py_in_process_skills if listed)")
                    # When response was truncated (finish_reason=length), tool_call arguments (e.g. save_result_page content) may be cut off; executor will reject bad HTML.
                    if name == "save_result_page" and _last_finish_reason == "length":
                        logger.warning(
                            "Executing save_result_page after truncated response (finish_reason=length). Content may be incomplete; if so, put full HTML/Markdown in message content (e.g. ```html or ```markdown block)."
                        )
                    if name == "route_to_plugin" and isinstance(args, dict):
                        logger.info(
                            "Plugin routing: plugin_id={} capability_id={} parameters={}",
                            args.get("plugin_id"),
                            args.get("capability_id"),
                            args_redacted.get("parameters") if isinstance(args_redacted.get("parameters"), dict) else args_redacted.get("parameters"),
                        )
                    # Progress for stream=true: let the user know a long-running step is starting
                    progress_queue = None
                    if getattr(context, "request", None) and isinstance(getattr(context.request, "request_metadata", None), dict):
                        progress_queue = context.request.request_metadata.get("progress_queue")
                    if progress_queue and hasattr(progress_queue, "put_nowait") and name in ("route_to_plugin", "run_skill", "document_read", "save_result_page"):
                        msg = "Working on it…"
                        if name == "route_to_plugin" and isinstance(args, dict):
                            pid = (args.get("plugin_id") or "").strip().lower()
                            if "ppt" in pid or "slide" in pid:
                                msg = "Generating your presentation…"
                            elif pid:
                                msg = f"Running {pid}…"
                        elif name == "document_read":
                            msg = "Reading the document…"
                        elif name == "save_result_page":
                            msg = "Saving the result…"
                        try:
                            progress_queue.put_nowait({"event": "progress", "message": msg, "tool": name})
                        except Exception:
                            pass
                    # save_result_page: if tool-call content was truncated (no </html>), try to recover full HTML from assistant message content (```html ... ```)
                    if name == "save_result_page" and isinstance(args, dict):
                        _cnt = (args.get("content") or "").strip()
                        _fmt = (args.get("format") or "").strip().lower() or "html"
                        if _fmt == "html" and _cnt and len(_cnt) > 500 and ("</html>" not in _cnt.lower()) and (
                            _cnt.lstrip().lower().startswith("<!doctype") or _cnt.lstrip().lower().startswith("<html")
                        ):
                            _assistant = current_messages[-1] if current_messages and isinstance(current_messages[-1], dict) else None
                            _body = (_assistant.get("content") or "").strip() if _assistant else ""
                            if _body and "```html" in _body.lower():
                                try:
                                    _m = re.search(r"```(?:html|HTML)\s*([\s\S]*?)```", _body, re.IGNORECASE)
                                    if _m and _m.group(1):
                                        _extracted = _m.group(1).strip()
                                        if "</html>" in _extracted.lower() and len(_extracted) > len(_cnt):
                                            args = dict(args)
                                            args["content"] = _extracted
                                            _component_log("tools", "save_result_page: using full HTML from message content (tool call was truncated)")
                                except Exception as _e:
                                    logger.debug("save_result_page recover HTML from content failed: {}", _e)
                    # Phase 3.3: optional verification — ask LLM if tool matches user intent before executing (e.g. exec, file_write).
                    _tool_verified_skip = False
                    try:
                        _ir_cfg = _intent_router_config if isinstance(_intent_router_config, dict) else {}
                        _verify_cfg = _ir_cfg.get("verify_tool_selection")
                        _verify_tools = _ir_cfg.get("verify_tools") or list(INTENT_VERIFY_TOOLS_DEFAULT)
                        if not isinstance(_verify_tools, (list, tuple)):
                            _verify_tools = list(INTENT_VERIFY_TOOLS_DEFAULT)
                    except Exception:
                        _verify_cfg = False
                        _verify_tools = list(INTENT_VERIFY_TOOLS_DEFAULT)
                    if _verify_cfg and name in _verify_tools and (query or "").strip():
                        try:
                            _verified = await intent_verify_tool_selection(
                                query=(query or "").strip(),
                                tool_name=name,
                                tool_args=args,
                                completion_fn=core,
                            )
                            if not _verified:
                                _tool_verified_skip = True
                                logger.info("Tool {} skipped by verification (Phase 3.3)", name)
                        except Exception:
                            pass  # on error allow execution
                    # Do not run the same run_skill(skill_name) twice in this request; skip and return a short result so other tools in this batch can still run.
                    _skill_key = (str(args.get("skill_name") or "").strip()) if name == "run_skill" and isinstance(args, dict) else ""
                    _skip_duplicate_run_skill = name == "run_skill" and _skill_key and _skill_key in _run_skills_executed_this_request
                    if _skip_duplicate_run_skill:
                        result = "This skill was already run in this conversation. Use the results above or call another tool (e.g. save_result_page)."
                        logger.info("Skipping duplicate run_skill({}); already executed this request", _skill_key)
                    elif _remind_me_skip_repeat:
                        try:
                            _ask = _remind_me_clarification_question((query or "").strip()) if (query or "").strip() else None
                            result = (str(_ask).strip() if _ask else "您希望什么时候提醒？例如：「15分钟后」或「下午3点」。 When would you like to be reminded? E.g. in 15 minutes or at 3:00 PM.")
                        except Exception:
                            result = "您希望什么时候提醒？例如：「15分钟后」或「下午3点」。 When would you like to be reminded? E.g. in 15 minutes or at 3:00 PM."
                        logger.info("Skipping repeated remind_me without minutes/at_time (avoid loop); returning clarification")
                    else:
                        try:
                            if _tool_verified_skip:
                                result = "Verification: tool selection did not match user intent; execution skipped."
                            elif tool_timeout_sec > 0:
                                result = await asyncio.wait_for(
                                    registry.execute_async(name, args, context),
                                    timeout=tool_timeout_sec,
                                )
                            else:
                                result = await registry.execute_async(name, args, context)
                        except asyncio.TimeoutError:
                            result = f"Error: tool {name} timed out after {tool_timeout_sec}s. The system did not hang; you can retry or use a different approach."
                        except Exception as e:
                            result = f"Error: {e!s}"
                        if name == "run_skill" and _skill_key:
                            _run_skills_executed_this_request.add(_skill_key)
                        _executed_any_this_batch = True
                    if name == "route_to_tam":
                        _component_log("TAM", "routed from model")
                    elif name == "route_to_plugin":
                        _component_log("plugin", f"routed from model: plugin_id={args.get('plugin_id', args)}")
                    _component_log("tools", f"tool {name}({list(args.keys()) if isinstance(args, dict) else '...'})")
                    if name in ("route_to_tam", "route_to_plugin"):
                        if result == ROUTING_RESPONSE_ALREADY_SENT:
                            routing_sent = True
                        elif isinstance(result, str) and result.strip():
                            # route_to_plugin: sync inbound/ws returns text so caller can send it
                            if name == "route_to_plugin":
                                routing_sent = True
                                routing_response_text = result
                            # route_to_tam: fallback string means TAM couldn't parse as scheduling; don't set routing_sent so the tool result is appended and the loop continues — model can then try route_to_plugin or other tools
                    if name in ("save_result_page", "get_file_view_link") and isinstance(result, str) and (
                        ("/files/out" in result and "token=" in result) or ("http" in result and "/files/" in result)
                    ):
                        last_file_link_result = result
                    last_tool_name = name
                    last_tool_result_raw = result if isinstance(result, str) else None
                    last_tool_args = args if isinstance(args, dict) else None
                    tool_content = result
                    # Workflow envelope: if tool returned need_input/need_confirmation, store and use message as reply.
                    if isinstance(result, str) and result.strip():
                        try:
                            from core.workflow_result import parse_workflow_result, STATUS_NEED_INPUT, STATUS_NEED_CONFIRMATION
                            _wf_status, _wf_obj = parse_workflow_result(result)
                            if _wf_status in (STATUS_NEED_INPUT, STATUS_NEED_CONFIRMATION) and _wf_obj:
                                _aid = getattr(context, "app_id", None) or "homeclaw"
                                _uid = getattr(context, "user_id", None) or ""
                                _sid = getattr(context, "session_id", None) or ""
                                core.set_pending_workflow(_aid, _uid, _sid, {"workflow_status": _wf_status, **_wf_obj})
                                _msg = (_wf_obj.get("message") or result).strip()
                                routing_sent = True
                                routing_response_text = _msg
                                tool_content = _msg
                        except Exception as _wfe:
                            logger.debug("Workflow parse after tool failed (non-fatal): {}", _wfe)
                    if name == "image":
                        _image_tool_run_count_this_request += 1
                    # Collect for memory full-turn (MemOS user+assistant+tool)
                    try:
                        _tr = str(result) if result is not None else ""
                        if len(_tr) > 2000:
                            _tr = _tr[:2000] + "\n[Output truncated for memory.]"
                        memory_turn_tool_messages.append({"role": "tool", "content": _tr, "toolName": name})
                    except Exception:
                        pass
                    if compaction_cfg.get("compact_tool_results") and isinstance(tool_content, str):
                        # document_read: keep more context so the model can generate HTML/summary from it; other tools: 4000
                        limit = 28000 if name == "document_read" else 4000
                        if len(tool_content) > limit:
                            tool_content = tool_content[:limit] + "\n[Output truncated for context.]"
                    current_messages.append({"role": "tool", "tool_call_id": tcid, "content": tool_content})
                # If the only tool call(s) this batch were duplicate run_skill (skipped), give the model one more turn to call save_result_page (or another tool); break only if we already did that once.
                if not _executed_any_this_batch:
                    _consecutive_duplicate_run_skill_only += 1
                    if _consecutive_duplicate_run_skill_only >= 2:
                        response = "The same skill was already run. Use the content above or try again with a different request. (同一技能已执行过，请使用上方内容或换一种方式重试。)"
                        logger.info("Stopping tool loop: only duplicate run_skill(s) again; no other tools to run")
                        break
                    logger.info("Only duplicate run_skill(s) this batch; continuing one more turn so model can call save_result_page or another tool")
                else:
                    _consecutive_duplicate_run_skill_only = 0
                # Stop image-tool loop: when the model keeps returning empty content and calling the image tool again, use the last description as the response
                if _image_tool_run_count_this_request >= 2 and last_tool_name == "image" and last_tool_result_raw and (last_tool_result_raw or "").strip():
                    response = last_tool_result_raw.strip()
                    logger.info("Stopping tool loop: image tool already ran %s time(s); using last description as response", _image_tool_run_count_this_request)
                    break
                if routing_sent:
                    out = routing_response_text if routing_response_text is not None else ROUTING_RESPONSE_ALREADY_SENT
                    if mix_route_this_request and mix_show_route_label and isinstance(out, str) and out is not ROUTING_RESPONSE_ALREADY_SENT:
                        layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
                        label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
                        out = label + (_strip_leading_route_label(out or "") or "")
                    return (out, None)
                # Use exact tool result as response when it contains a file view link, so the model cannot corrupt the URL in a follow-up reply
                if last_file_link_result:
                    out = last_file_link_result
                    if mix_route_this_request and mix_show_route_label and isinstance(out, str):
                        layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
                        label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
                        out = label + (_strip_leading_route_label(out or "") or "")
                    response = out
                    break
                # Always run 2nd LLM round after tools; let the LLM decide whether the output is fine, how to refine it, or how to respond to errors (no if/else on tool result content).
            else:
                # Loop exhausted (e.g. max_tool_rounds). Use last message content only if it is from the assistant; never use a tool result as the user-facing response. Do not overwrite planner-executor response.
                if _planner_executor_final_response is None:
                    if current_messages:
                        _last = current_messages[-1]
                        if isinstance(_last, dict) and (_last.get("role") or "").strip() == "assistant":
                            _c = _last.get("content")
                            response = (_c if isinstance(_c, str) else (str(_c) if _c is not None else "")).strip() or None
                        else:
                            response = None
                    else:
                        response = None
            await close_browser_session(context)
        else:
            try:
                response = await core.openai_chat_completion(
                    messages=llm_input, llm_name=effective_llm_name
                )
            except Exception as e:
                logger.warning("LLM call failed (no-tool path, will try fallback if available): {}", e)
                response = None
            # Mix fallback: first model failed (returned empty or raised); retry once with the other route so the task is not blocked.
            if (response is None or (isinstance(response, str) and len(response.strip()) == 0)) and mix_route_this_request:
                hr = getattr(Util().get_core_metadata(), "hybrid_router", None) or {}
                if bool(hr.get("fallback_on_llm_error", True)) and (getattr(Util().get_core_metadata(), "main_llm_local", None) or "").strip() and (getattr(Util().get_core_metadata(), "main_llm_cloud", None) or "").strip():
                    other_route = "cloud" if mix_route_this_request == "local" else "local"
                    other_llm = (getattr(Util().get_core_metadata(), "main_llm_cloud", None) or "").strip() if other_route == "cloud" else (getattr(Util().get_core_metadata(), "main_llm_local", None) or "").strip()
                    if other_llm:
                        _component_log("mix", f"first model failed (no-tool path), retrying with {other_route} ({other_llm})")
                        try:
                            response = await core.openai_chat_completion(messages=llm_input, llm_name=other_llm)
                            if response and isinstance(response, str) and response.strip():
                                mix_route_this_request = other_route
                                mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_fallback" if mix_route_layer_this_request else "fallback"
                        except Exception as e2:
                            logger.warning("Fallback LLM call (no-tool path) also failed: {}", e2)
                            response = None

        if response is None or (isinstance(response, str) and len(response.strip()) == 0):
            try:
                err_hint = (getattr(Util(), "_last_llm_error", None) or "")
                err_hint = str(err_hint).strip() if err_hint else ""
            except Exception:
                err_hint = ""
            # If we ran a tool but the 2nd LLM returned empty: use tool output so we don't show "Done..." instead of real results (LLM had its chance to refine).
            # Do not use instruction-only skill output as the final response (e.g. "Instruction-only skill confirmed... You MUST in this turn").
            if last_tool_name and last_tool_result_raw and isinstance(last_tool_result_raw, str) and last_tool_result_raw.strip() and not err_hint:
                _raw = last_tool_result_raw.strip()
                _is_instruction_only = (
                    "Instruction-only skill confirmed" in _raw or "Instruction-only skill" in _raw
                ) and ("You MUST in this turn" in _raw or "Do NOT reply with only this line" in _raw)
                if not _is_instruction_only:
                    # When the tool asked for missing/required info, show a friendly question so the user can reply (instead of raw error).
                    _ask_user_phrases = ("Ask the user", "provide either", "required", "then call ", "parameters=")
                    if any(p in _raw for p in _ask_user_phrases) or (_raw.startswith("Error:") and ("required" in _raw or "provide" in _raw)):
                        if last_tool_name == "remind_me" and ("minutes" in _raw or "at_time" in _raw):
                            try:
                                response = (_remind_me_clarification_question((query or "").strip()) if (query or "").strip() else None) or "When would you like to be reminded? (e.g. in 15 minutes or at 3:00 PM). 您希望什么时候提醒？例如：15分钟后 或 下午3点。"
                            except Exception:
                                response = "When would you like to be reminded? (e.g. in 15 minutes or at 3:00 PM). 您希望什么时候提醒？例如：15分钟后 或 下午3点。"
                        else:
                            response = "I need a bit more information to do that. Please tell me the missing details (e.g. time, address, or whatever the previous step asked for), and I’ll try again. (请补充一下需要的信息，例如时间、地址等，我再帮您处理。)"
                    else:
                        if last_tool_name == "web_search":
                            response = format_web_search_result(last_tool_result_raw) or format_json_for_user(last_tool_result_raw) or _raw
                        else:
                            response = format_json_for_user(last_tool_result_raw) or _raw
            # Only show generic "Done..." when we have no usable response (no err_hint, and either no tool ran or tool output was empty/error-like).
            if response is None or (isinstance(response, str) and len(response.strip()) == 0):
                if last_tool_name and not err_hint:
                    # If the last tool was instruction-only (e.g. run_skill html-slides) and we skipped it, suggest retry or cloud.
                    _instruction_only = (
                        last_tool_result_raw
                        and isinstance(last_tool_result_raw, str)
                        and ("Instruction-only skill" in last_tool_result_raw or "You MUST in this turn" in last_tool_result_raw)
                    )
                    if _instruction_only and last_tool_name == "run_skill":
                        out = "The task could not be completed in this turn (e.g. slides generation). Try again or use a cloud model for long outputs. (本次未能完成，请重试或使用云端模型生成长内容。)"
                    else:
                        out = "Done. What would you like to do next? (已完成。还需要什么？)"
                elif err_hint:
                    try:
                        out = "Sorry, something went wrong. {} Please try again. (对不起，出错了，请再试一次)".format(err_hint)
                    except Exception:
                        out = "Sorry, something went wrong and please try again. (对不起，出错了，请再试一次)"
                else:
                    out = "Sorry, something went wrong and please try again. (对不起，出错了，请再试一次)"
                if mix_route_this_request and mix_show_route_label and isinstance(out, str):
                    layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
                    label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
                    out = label + (_strip_leading_route_label(out or "") or "")
                return (out, None)
        # If the model echoed raw "[]" (e.g. from empty folder_list/file_find), show a friendly message instead
        if isinstance(response, str) and response.strip() == "[]":
            response = "I couldn't find that file or path. Try asking me to list your files (e.g. 'list my files' or 'what files do I have'), then use the exact filename (e.g. 1.pdf) when you ask about a document."
        # If the model echoed raw folder_list/file_find JSON, format as user-friendly list so the user and memory never see raw JSON
        if isinstance(response, str) and response.strip():
            try:
                full = response.strip()
                content_only = _strip_leading_route_label(full)
                if content_only != full:
                    route_label = full[: full.find(content_only)].strip() + " " if content_only and content_only in full else ""
                else:
                    route_label = ""
                    content_only = full
                formatted = format_folder_list_file_find_result(content_only, is_file_find=False)
                if not formatted:
                    # Preserve short header (e.g. DAG summary "# 最火爆的电影推荐~") before JSON when formatting web_search results
                    content_for_search = content_only
                    search_header = ""
                    if "\n\n{" in content_only and '"results"' in content_only:
                        idx = content_only.index("\n\n{")
                        if idx > 0 and idx < 300:
                            search_header = (content_only[:idx].strip() + "\n\n") or ""
                            content_for_search = content_only[idx:].strip()
                    formatted = format_web_search_result(content_for_search)
                    if formatted and search_header:
                        formatted = search_header + formatted
                if not formatted and (content_only or "").strip().startswith("["):
                    formatted = format_json_for_user(content_only)
                if formatted:
                    response = (route_label + formatted).strip() if route_label else formatted
            except Exception:
                pass
        # If the model echoed raw JSON from a scheduling tool (cron_schedule, record_date), email send result, or session_status, show a short friendly line. Never crash.
        if isinstance(response, str) and response.strip().startswith("{"):
            try:
                _to_parse = response.strip()
                if "stderr:" in _to_parse:
                    _to_parse = _to_parse.split("stderr:")[0].strip()
                obj = json.loads(_to_parse)
                if isinstance(obj, dict):
                    if obj.get("success") is True and obj.get("to") and ("messageId" in obj or "message_id" in obj):
                        to_addr = str(obj.get("to") or "").strip()
                        response = f"Email sent to {to_addr}. （邮件已发送。）"
                    elif obj.get("scheduled") and ("job_id" in obj or "cron_expr" in obj):
                        msg = str(obj.get("message", "Scheduled reminder") or "Scheduled reminder")
                        response = f"**Recurring reminder scheduled.** I'll remind you: {msg}."
                    elif obj.get("recorded") and ("event_name" in obj or "when" in obj):
                        ev = str(obj.get("event_name") or "event")
                        wh = str(obj.get("when") or "")
                        response = f"**Recorded:** {ev} on {wh}."
                    elif "session_id" in obj and "app_id" in obj and "user_name" in obj:
                        # session_status-style JSON: internal context; show friendly line so we never surface raw JSON. Never crash.
                        try:
                            app_id_val = str(obj.get("app_id") or "HomeClaw")
                            user_name_val = str(obj.get("user_name") or "")
                            if user_name_val:
                                response = f"You're chatting with **{app_id_val}** as **{user_name_val}**. How can I help? （你正在与 {app_id_val} 对话，用户 {user_name_val}。需要什么帮助？）"
                            else:
                                response = f"You're chatting with **{app_id_val}**. How can I help? （你正在与 {app_id_val} 对话。需要什么帮助？）"
                        except (TypeError, ValueError, KeyError, AttributeError):
                            pass  # leave response unchanged on any error
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        # If the model echoed the internal file_write/save_result_page empty-content message, show a short user-facing message instead
        if isinstance(response, str) and ("Do NOT share this link" in response or ("empty or too small" in response and '"written"' in response)):
            response = "The slide wasn’t generated yet because the content was empty. Please try again; I’ll generate the HTML from the document and then save it. （幻灯片尚未生成，请再试一次。）"
        # When we just ran remind_me, ensure the user sees the correct trigger time (model sometimes hallucinates wrong time).
        if last_tool_name == "remind_me" and isinstance(last_tool_result_raw, str) and last_tool_result_raw.strip() and isinstance(response, str) and response.strip():
            _tr = last_tool_result_raw.strip()
            _time_match = re.search(r"Reminder set for (\d{1,2}:\d{2}(?::\d{2})?)", _tr) or re.search(r"run_at=['\"]?[\d-]+\s+(\d{1,2}:\d{2}(?::\d{2})?)", _tr)
            if _time_match:
                _correct_time = _time_match.group(1)
                _hm = _correct_time[:5] if len(_correct_time) >= 5 else _correct_time
                if _hm not in response and _correct_time not in response:
                    response = (response.strip() + "\n\n（提醒时间：{}）").format(_hm)
        if mix_route_this_request and mix_show_route_label:
            layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
            label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
            response = label + (_strip_leading_route_label(response or "") or "")
        # Never surface raw JSON to the end user: convert to readable text if it still looks like JSON
        # Strip reasoning blocks (e.g. <think>...</think>) so they are not stored in chat history, memory, or embeddings
        if isinstance(response, str) and response.strip():
            response = strip_reasoning_from_assistant_text(response)
        if isinstance(response, str) and response.strip() and (response.strip().startswith("[") or response.strip().startswith("{")):
            _fmt = format_json_for_user(response)
            if _fmt:
                response = _fmt
        logger.info("Main LLM output (final response): {}", _truncate_for_log(response, 2000))
        message: ChatMessage = ChatMessage()
        message.add_user_message(query)
        message.add_ai_message(response)
        _fid_add = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"
        core.chatDB.add(app_id=app_id, user_name=user_name, user_id=user_id, session_id=session_id, friend_id=_fid_add, chat_message=message)
        # Session pruning: optionally keep only last N turns per session after each reply
        session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
        if session_cfg.get("prune_after_turn") and app_id and user_id and session_id:
            keep_n = max(10, int(session_cfg.get("prune_keep_last_n", 50) or 50))
            try:
                pruned = core.prune_session_transcript(app_id=app_id, user_name=user_name, user_id=user_id, session_id=session_id, friend_id=_fid_add, keep_last_n=keep_n)
                if pruned > 0:
                    _component_log("session", f"pruned {pruned} old turns, kept last {keep_n}")
            except Exception as e:
                logger.debug("Session prune after turn failed: {}", e)
        #if use_memory:
        #    await core.mem_instance.add(query, user_name=user_name, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata, filters=filters)

        # Build full-turn data for MemOS (user + assistant + tool messages)
        memory_turn_data = None
        if response is not None and isinstance(response, str) and (response.strip() or memory_turn_tool_messages):
            _assistant = str(response or "").strip()
            # Don't store instruction-only boilerplate as assistant message (pollutes memory and embeddings).
            if _assistant and ("Instruction-only skill confirmed" in _assistant or "Instruction-only skill" in _assistant) and "You MUST in this turn" in _assistant:
                _assistant = "[Task could not be completed in this turn; instruction-only skill result.]"
            # Trim tool_messages when there are many (e.g. repeated run_skill rounds) so memory stays useful.
            _tool_msgs = list(memory_turn_tool_messages)
            if len(_tool_msgs) > 12:
                _keep_first, _keep_last = 5, 5
                _tool_msgs = (
                    _tool_msgs[:_keep_first]
                    + [{"role": "tool", "content": f"[... {len(memory_turn_tool_messages) - _keep_first - _keep_last} tool results omitted ...]", "toolName": "..."}]
                    + _tool_msgs[-_keep_last:]
                )
            memory_turn_data = {
                "user_message": str(query or "").strip(),
                "assistant_message": _assistant,
                "tool_messages": _tool_msgs,
            }
        return (response, memory_turn_data)
    except Exception as e:
        logger.exception(e)
        return (None, None)


