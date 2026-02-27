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
from base.util import Util, redact_params_for_log
from base.workspace import (
    get_workspace_dir,
    load_workspace,
    build_workspace_system_prefix,
    load_agent_memory_file,
    load_daily_memory_for_dates,
    trim_content_bootstrap,
    load_friend_identity_file,
)
from base.skills import (
    get_skills_dir,
    load_skills_from_dirs,
    load_skill_by_folder_from_dirs,
    build_skills_system_block,
)
from memory.prompts import RESPONSE_TEMPLATE
from memory.chat.message import ChatMessage
from tools.builtin import close_browser_session
from core.log_helpers import _component_log, _truncate_for_log, _strip_leading_route_label

try:
    from core.services.tool_helpers import (
        tool_result_looks_like_error as _tool_result_looks_like_error,
        tool_result_usable_as_final_response as _tool_result_usable_as_final_response,
        parse_raw_tool_calls_from_content as _parse_raw_tool_calls_from_content,
        infer_route_to_plugin_fallback as _infer_route_to_plugin_fallback,
        infer_remind_me_fallback as _infer_remind_me_fallback,
        remind_me_needs_clarification as _remind_me_needs_clarification,
        remind_me_clarification_question as _remind_me_clarification_question,
    )
except Exception:
    from core.tool_helpers_fallback import (
        tool_result_looks_like_error as _tool_result_looks_like_error,
        tool_result_usable_as_final_response as _tool_result_usable_as_final_response,
        parse_raw_tool_calls_from_content as _parse_raw_tool_calls_from_content,
        infer_route_to_plugin_fallback as _infer_route_to_plugin_fallback,
        infer_remind_me_fallback as _infer_remind_me_fallback,
        remind_me_needs_clarification as _remind_me_needs_clarification,
        remind_me_clarification_question as _remind_me_clarification_question,
    )


async def answer_from_memory(
    core: Any,
    query: str,
    messages: List = [],
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
) -> Optional[str]:
    if not any([user_name, user_id, agent_id, run_id]):
        raise ValueError("One of user_name, user_id, agent_id, run_id must be provided")
    # Step 9: RAG/Cognee memory scope by (user_id, friend_id). Use friend_id from request for add/search.
    try:
        _mem_scope = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else (str(agent_id or "").strip() or "HomeClaw")
    except (TypeError, AttributeError):
        _mem_scope = "HomeClaw"
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
                            return "Done."
                        if isinstance(result, PluginResult):
                            if not result.success:
                                return result.error or result.text or "The action could not be completed."
                            return result.text or "Done."
                        return str(result) if result else "Done."
                    except Exception as e:
                        logger.debug("Pending plugin retry failed: {}", e)
                        pending["params"] = params
                        core.set_pending_plugin_call(app_id_val, user_id_val, session_id_val, pending)
                elif not plugin:
                    core.clear_pending_plugin_call(app_id_val, user_id_val, session_id_val)

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
        system_parts = []
        force_include_instructions = []  # collected from skills_force_include_rules and plugins_force_include_rules; appended at end of system so model sees it last
        force_include_auto_invoke = []  # when model returns no tool_calls, run these (e.g. run_skill) so the skill runs anyway; each item: {"tool": str, "arguments": dict}
        force_include_plugin_ids = set()  # plugin ids to add to plugin list when skills_force_include_rules match (optional "plugins" in rule)

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
            except Exception as e:
                logger.debug("Companion identity (who) inject failed: {}", e)

        # System context: current date/time (system timezone) + optional location. Never crash; see SystemContextDateTimeAndLocation.md
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
            ctx_line += "\nCritical for cron jobs and reminders: this current datetime is the single source of truth. The server uses it when scheduling; you must use it for all time calculations. Do not use any other time (e.g. from memory or prior turns—they may be outdated). Use this block only when the user explicitly asks (e.g. \"what day is it?\", \"what time is it?\", scheduling with remind_me, record_date, cron_schedule). Do not volunteer date/time in greetings. For reminders and cron: use ONLY the Current time above; do not invent or guess any time (e.g. never output 26号 15:49, 明天下午7点, 2026-1月 3号, or 2:49 PM). If the user says \"in N minutes\", reminder time = Current time + N minutes (e.g. Current time 17:58 + 30 min = 18:28). For remind_me(message=...): do NOT put any date or time inside the message; use a short label only (e.g. 会议提醒, Reminder: meeting)."
            system_parts.append("## System context (date/time and location)\n" + ctx_line + "\n\n")
        except Exception as e:
            logger.debug("System context block failed: {}", e)
            try:
                fallback = f"Current date: {date.today().isoformat()}."
                system_parts.append("## System context\n" + fallback + "\n\n")
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
                use_agent_file = getattr(Util().core_metadata, "use_agent_memory_file", True)
                use_daily = getattr(Util().core_metadata, "use_daily_memory", True)
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
                        _sys_uid = getattr(request, "system_user_id", None) if request else None
                        _fid = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"
                        parts_bootstrap = []
                        if use_agent_file:
                            agent_raw = load_agent_memory_file(
                                workspace_dir=ws_dir,
                                agent_memory_path=getattr(meta_mem, "agent_memory_path", None) or None,
                                max_chars=0,
                                system_user_id=_sys_uid,
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
                                system_user_id=_sys_uid,
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
            if getattr(Util().core_metadata, 'use_agent_memory_file', True):
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
            if getattr(Util().core_metadata, 'use_daily_memory', True):
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

        # Skills (SKILL.md from skills_dir + skills_extra_dirs); skills_disabled excluded
        if getattr(Util().core_metadata, 'use_skills', True):
            try:
                root = Path(__file__).resolve().parent.parent
                meta_skills = Util().core_metadata
                skills_path = get_skills_dir(getattr(meta_skills, 'skills_dir', None), root=root)
                skills_extra_raw = getattr(meta_skills, 'skills_extra_dirs', None) or []
                skills_dirs = [skills_path] + [root / p if not Path(p).is_absolute() else Path(p) for p in skills_extra_raw if (p or "").strip()]
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
                    for hit_id, _ in hits:
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
                # Force-include: config rules (core.yml) and skill-driven triggers (SKILL.md trigger:). Query-matched skills get instruction + optional auto_invoke.
                matched_instructions = []
                skills_list = skills_list or []
                q = (query or "").strip().lower()
                folders_present = {s.get("folder") for s in skills_list}
                for rule in (getattr(meta_skills, "skills_force_include_rules", None) or []):
                    # Support single "pattern" (str) or "patterns" (list) for multi-language / general matching
                    patterns = rule.get("patterns") if isinstance(rule, dict) else None
                    if patterns is None and isinstance(rule, dict) and rule.get("pattern") is not None:
                        patterns = [rule.get("pattern")]
                    pattern = rule.get("pattern") if isinstance(rule, dict) else None
                    folders = rule.get("folders") if isinstance(rule, dict) else None
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
                        force_include_auto_invoke.append({"tool": str(auto_invoke["tool"]).strip(), "arguments": args})
                    # Optional: when this rule matches, also force-include these plugins in the plugin list (so model sees them for route_to_plugin)
                    plugins_in_rule = rule.get("plugins") if isinstance(rule, dict) else None
                    if isinstance(plugins_in_rule, (list, tuple)):
                        for pid in plugins_in_rule:
                            pid = str(pid).strip().lower().replace(" ", "_")
                            if pid:
                                force_include_plugin_ids.add(pid)
                # Skill-driven triggers: declare trigger.patterns + instruction + auto_invoke in each skill's SKILL.md; no need to repeat in core.yml
                for skill_dict in load_skills_from_dirs(skills_dirs, disabled_folders=disabled_folders, include_body=False):
                    trigger = skill_dict.get("trigger") if isinstance(skill_dict, dict) else None
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
                if use_vector_search:
                    skills_max = max(0, int(getattr(meta_skills, "skills_max_in_prompt", 5) or 5))
                    if skills_max > 0 and len(skills_list) > skills_max:
                        skills_list = skills_list[:skills_max]
                if skills_list:
                    selected_names = [s.get("folder") or s.get("name") or "?" for s in skills_list]
                    _component_log("skills", f"selected: {', '.join(selected_names)}")
                # For skills in skills_include_body_for, re-load with body (and USAGE.md if present) so the model can answer "how do I use this?"
                include_body_for = list(getattr(meta_skills, "skills_include_body_for", None) or [])
                body_max_chars = max(0, int(getattr(meta_skills, "skills_include_body_max_chars", 0) or 0))
                if include_body_for:
                    for i, s in enumerate(skills_list):
                        folder = (s.get("folder") or "").strip()
                        if folder and folder in include_body_for:
                            full_skill = load_skill_by_folder_from_dirs(
                                skills_dirs, folder, include_body=True, body_max_chars=body_max_chars
                            )
                            if full_skill:
                                skills_list[i] = full_skill
                include_body = bool(include_body_for)
                skills_block = build_skills_system_block(skills_list, include_body=include_body)
                if skills_block:
                    system_parts.append(skills_block)
                force_include_instructions.extend(matched_instructions)
            except Exception as e:
                logger.warning("Failed to load skills: {}", e)

        if use_memory:
            relevant_memories = await core._fetch_relevant_memories(query,
                messages, user_name, user_id, _mem_scope, run_id, filters, 10
            )
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
            plugin_lines = []
            if plugin_list:
                desc_max = max(0, int(getattr(Util().get_core_metadata(), "plugins_description_max_chars", 0) or 0))
                def _desc(d: str) -> str:
                    s = d or ""
                    return s[:desc_max] if desc_max > 0 else s
                plugin_lines = [f"  - {p.get('id', '') or 'plugin'}: {_desc(p.get('description'))}" for p in plugin_list]
            _req_time_24 = getattr(core, "_request_current_time_24", "") or ""
            routing_block = (
                "## Routing (choose one)\n"
                "Do NOT use route_to_tam for: opening URLs, listing nodes, canvas, camera/video on a node, or any non-scheduling request. Use route_to_plugin for those.\n"
                "Recording a video or taking a photo on a node (e.g. \"record video on test-node-1\", \"take a photo on test-node-1\") -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=node_camera_clip or node_camera_snap, parameters={\"node_id\": \"<node_id>\"}; for clip add duration and includeAudio). Do NOT use browser_navigate for node ids; test-node-1 is a node id, not a URL.\n"
                "Opening a URL in a browser (real web URLs only, e.g. https://example.com) -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=browser_navigate, parameters={\"url\": \"<URL>\"}). Node ids like test-node-1 are NOT URLs.\n"
                "Listing connected nodes or \"what nodes are connected\" -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=node_list).\n"
                "If the request clearly matches one of the available plugins below, call route_to_plugin with that plugin_id (and capability_id/parameters when relevant).\n"
                "For time-related requests only: one-shot reminders -> remind_me(minutes or at_time, message); recording a date/event -> record_date(event_name, when); recurring -> cron_schedule(cron_expr, message). Use route_to_tam only when the user clearly asks to schedule or remind (e.g. \"remind me in 5 minutes\", \"every day at 9am\").\n"
                f"When the user asks to be reminded in N minutes (e.g. \"30分钟后提醒我\", \"remind me in 30 minutes\", \"我30分钟后有个会能提醒一下吗\"), you MUST call the remind_me tool with minutes=N (use the number from the user's message; 30分钟后 = 30 minutes) and message= a short reminder text WITHOUT any date or time (e.g. \"会议提醒\" or \"Reminder: meeting\"; do NOT put \"26号 15:49\" or \"7pm\" in message). Do NOT reply with text-only or fake JSON; always call remind_me so the reminder is actually scheduled. The current time for this request is {_req_time_24}. Use only this time in your reply; never invent times (e.g. never 2:49 PM, 明天下午7点, 2026-1月 3号)—if current time is {_req_time_24} and user says 15 minutes, say that time or \"in 15 minutes\".\n"
                "For script-based workflows use run_skill(skill_name, script, ...). For instruction-only skills (no scripts/) use run_skill(skill_name) with no script—then you MUST continue in the same turn (document_read, generate content, file_write or save_result_page, return link); do not reply with only the confirmation. skill_name can be folder or short name (e.g. html-slides).\n"
                "When the user asks to generate an HTML slide or report from a document/file: (1) call document_read(path) to get the file content, (2) use that returned text as the source and generate the full HTML yourself, (3) call save_result_page(title=..., content=<your generated full HTML>, format='html'). For HTML slides do NOT use format='markdown'—use format='html'. Never pass empty or minimal content; content must be the full slide deck/report HTML.\n"
                "Using an external service (Slack, LinkedIn, Outlook, HubSpot, Notion, Gmail, Stripe, Google Calendar, Salesforce, Airtable, etc.) -> use run_skill(skill_name='maton-api-gateway-1.0.0', script='request.py') with app and path from the maton skill body (Supported Services table and references/). Do not claim the action was done without calling the skill. For LinkedIn post: GET linkedin/rest/me then POST linkedin/rest/posts with commentary.\n"
                "When a tool returns a view/open link (URL containing /files/out?token=), you MUST output that URL exactly as given: character-for-character, no truncation, no added text, no character changes. Do not combine the URL with any other content. Copy only the URL line. One wrong or extra character makes the link invalid.\n"
                "Otherwise respond or use other tools.\n"
                + ("Available plugins:\n" + "\n".join(plugin_lines) if plugin_lines else "")
            )
            system_parts.append(routing_block)
            force_include_instructions.extend(plugin_force_instructions)

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
                        all_tools_flush = registry_flush.get_openai_tools() if registry_flush.list_tools() else None
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
                            for _round in range(10):
                                try:
                                    msg_flush = await Util().openai_chat_completion_message(
                                        current_flush, tools=all_tools_flush, tool_choice="auto", llm_name=effective_llm_name
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
                                        if _parse_raw_tool_calls_from_content(content_flush):
                                            tool_calls_flush = _parse_raw_tool_calls_from_content(content_flush)
                                    except Exception:
                                        pass
                                if not tool_calls_flush:
                                    break
                                for tc in (tool_calls_flush or []):
                                    if not isinstance(tc, dict):
                                        continue
                                    tcid = tc.get("id") or ""
                                    fn = tc.get("function") or {}
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

        llm_input += messages
        if llm_input:
            last_content = llm_input[-1].get("content")
            if isinstance(last_content, list):
                n_img = sum(1 for p in last_content if isinstance(p, dict) and p.get("type") == "image_url")
                logger.info("Last user message: multimodal ({} image(s) in content)", n_img)
            else:
                logger.info("Last user message: text only (no image in this turn)")
        logger.debug("Start to generate the response for user input: " + query)
        logger.info("Main LLM input (user query): {}", _truncate_for_log(query, 500))

        use_tools = getattr(Util().get_core_metadata(), "use_tools", True)
        registry = get_tool_registry()
        all_tools = registry.get_openai_tools() if use_tools and registry.list_tools() else None
        if all_tools and not unified:
            all_tools = [t for t in all_tools if (t.get("function") or {}).get("name") not in ("route_to_tam", "route_to_plugin")]
        openai_tools = all_tools if (all_tools and (unified or len(all_tools) > 0)) else None
        tool_names = [((t or {}).get("function") or {}).get("name") for t in (openai_tools or []) if isinstance(t, dict)]
        logger.debug(
            "Tools for LLM: use_tools={} unified={} count={} has_route_to_plugin={}",
            use_tools, unified, len(openai_tools or []), "route_to_plugin" in (tool_names or []),
        )

        if openai_tools:
            logger.info("Tools available for this turn: {}", tool_names)
            # Inject file/sandbox rules and per-user paths JSON so the model uses correct paths (avoids wrong base and "file not found")
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
                                "**Do not invent or fabricate file names, file paths, or URLs** to complete tasks. Use only: (a) values returned by your tool calls (e.g. path from folder_list, file_find), (b) the exact filename or path the user mentioned (e.g. 1.pdf), (c) links returned by save_result_page or get_file_view_link. If you need a path or URL, call the appropriate tool first and use its result. "
                                "**Never use absolute paths** (e.g. /mnt/, C:\\, /Users/). Use only relative paths under the sandbox: the filename (e.g. 1.pdf) or the path from folder_list/file_find. "
                                "Do not use workspace, config, or paths outside these two trees. Put generated files in output/ (path \"output/filename\") and return the link. "
                                "When the user asks about a **specific file by name** (e.g. \"能告诉我1.pdf都讲了什么吗\", \"what is in 1.pdf\"): (1) call folder_list() or file_find(pattern='*1.pdf*') to list/search user sandbox; (2) use the **exact path** from the result that matches the requested name in document_read — e.g. if the user asked for 1.pdf, use path \"1.pdf\" only. Do **not** use absolute paths or invent paths. "
                                "When the user asks for file search, list, or read without a specific name: omit path for user sandbox; if user says \"share\", use path \"share\" or \"share/...\". "
                                "folder_list() = list user sandbox; folder_list(path=\"share\") = list share; file_find(pattern=\"*.pdf\") = search user sandbox. "
                                "To read a file, use **only** the exact path returned by folder_list or file_find in document_read (e.g. 1.pdf). "
                                f"Current homeclaw_root: {base_str}.{paths_json}"
                            )
                        llm_input[0]["content"] = (llm_input[0].get("content") or "") + block
                except Exception as e:
                    logger.debug("Inject homeclaw_root into system prompt failed: {}", e)
            # General rule when tools are present: do not invent paths, filenames, or URLs
            if llm_input and llm_input[0].get("role") == "system":
                tool_rule = (
                    "\n\n## Tool use — paths and URLs\n"
                    "When a task requires a file path, filename, or URL: use only values returned by your tool calls or explicitly given by the user. Do not create, guess, or fabricate paths, filenames, or URLs."
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
            current_messages = list(llm_input)
            max_tool_rounds = 10
            use_other_model_next_turn = False  # mix mode: when last tool result was error-like, use cloud (or local) for next turn
            last_tool_name = None  # so "no tool_calls" branch can skip remind_me clarifier when we already ran remind_me this turn
            for _ in range(max_tool_rounds):
                llm_name_this_turn = effective_llm_name
                if use_other_model_next_turn and mix_route_this_request:
                    try:
                        meta_hr = Util().get_core_metadata()
                        main_local = (getattr(meta_hr, "main_llm_local", None) or "").strip()
                        main_cloud = (getattr(meta_hr, "main_llm_cloud", None) or "").strip()
                        if main_local and main_cloud:
                            other_route = "cloud" if (mix_route_this_request == "local") else "local"
                            other_llm = main_cloud if other_route == "cloud" else main_local
                            if other_llm:
                                llm_name_this_turn = other_llm
                                mix_route_this_request = other_route
                                mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_error_retry" if mix_route_layer_this_request else "error_retry"
                                _component_log("mix", f"tool result was error-like, retrying with {other_route} ({other_llm})")
                    except Exception as e:
                        logger.debug("mix error_retry resolve failed: {}", e)
                    use_other_model_next_turn = False
                _t0 = time.time()
                logger.debug("LLM call started (tools={})", "yes" if openai_tools else "no")
                msg = await Util().openai_chat_completion_message(
                    current_messages, tools=openai_tools, tool_choice="auto", llm_name=llm_name_this_turn
                )
                logger.debug("LLM call returned in {:.1f}s", time.time() - _t0)
                if msg is None:
                    # Mix fallback: one model failed (timeout/error); retry once with the other route so the task is not blocked.
                    hr = getattr(Util().get_core_metadata(), "hybrid_router", None) or {}
                    fallback_ok = bool(hr.get("fallback_on_llm_error", True)) and mix_route_this_request
                    if fallback_ok and (getattr(Util().get_core_metadata(), "main_llm_local", None) or "").strip() and (getattr(Util().get_core_metadata(), "main_llm_cloud", None) or "").strip():
                        other_route = "cloud" if mix_route_this_request == "local" else "local"
                        other_llm = (getattr(Util().get_core_metadata(), "main_llm_cloud", None) or "").strip() if other_route == "cloud" else (getattr(Util().get_core_metadata(), "main_llm_local", None) or "").strip()
                        if other_llm:
                            _component_log("mix", f"first model failed, retrying with {other_route} ({other_llm})")
                            msg = await Util().openai_chat_completion_message(
                                current_messages, tools=openai_tools, tool_choice="auto", llm_name=other_llm
                            )
                            if msg is not None:
                                mix_route_this_request = other_route
                                mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_fallback" if mix_route_layer_this_request else "fallback"
                    if msg is None:
                        response = None
                        break
                current_messages.append(msg)
                tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else None
                content_str = (msg.get("content") or "").strip()
                # Some backends return tool_call as raw text in content instead of structured tool_calls
                if not tool_calls and content_str and _parse_raw_tool_calls_from_content(content_str):
                    tool_calls = _parse_raw_tool_calls_from_content(content_str)
                if not tool_calls:
                    logger.debug(
                        "LLM returned no tool_calls (content={})",
                        _truncate_for_log(content_str or "(empty)", 120),
                    )
                    # If content looks like raw tool_call but we didn't parse it, don't send that to the user
                    if content_str and ("<tool_call>" in content_str or "</tool_call>" in content_str):
                        response = "The assistant tried to use a tool but the response format was not recognized. Please try again."
                    else:
                        # Default: use LLM's reply so we never leave response unset (e.g. simple "你好" -> friendly reply)
                        response = content_str if (content_str and content_str.strip()) else None
                        # Fallback: model didn't call a tool. When we have force_include_auto_invoke (user query matched a rule, e.g. "create an image"), always run it so the skill runs and we return real output instead of model hallucination (e.g. fake "Image saved"). Otherwise run only when the reply looks unhelpful (e.g. "no tool available").
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
                        run_force_include = bool(force_include_auto_invoke and registry)
                        _component_log("tools", "model returned no tool_calls; unhelpful=%s auto_invoke_count=%s" % (unhelpful_for_auto_invoke, len(force_include_auto_invoke or [])))
                        # When we have force-include auto_invoke (e.g. image rule), always run it so the skill runs and we return real output instead of model hallucination
                        if run_force_include:
                            ran = False
                            for inv in force_include_auto_invoke:
                                tname = inv.get("tool") or ""
                                targs = inv.get("arguments") or {}
                                if not tname or not isinstance(targs, dict):
                                    continue
                                if not any(t.name == tname for t in (registry.list_tools() or [])):
                                    continue
                                try:
                                    _component_log("tools", f"fallback auto_invoke {tname} (model did not call tool)")
                                    if tname == "run_skill":
                                        _component_log("tools", "executing run_skill (in_process from run_skill_py_in_process_skills if listed)")
                                    result = await registry.execute_async(tname, targs, context)
                                    if result == ROUTING_RESPONSE_ALREADY_SENT:
                                        return ROUTING_RESPONSE_ALREADY_SENT
                                    if isinstance(result, str) and result.strip():
                                        # Format folder_list/file_find JSON as user-friendly text so the user does not see raw JSON
                                        if tname in ("folder_list", "file_find"):
                                            try:
                                                entries = json.loads(result)
                                                if isinstance(entries, list):
                                                    lines = [f"- {e.get('name', '?')} ({e.get('type', '?')})" for e in entries if isinstance(e, dict) and e.get("path") != "(truncated)" and (e.get("name") or e.get("path"))]
                                                    header = "目录下的内容：\n" if tname == "folder_list" else "找到的文件：\n"
                                                    response = header + "\n".join(lines) if lines else ("目录为空。" if tname == "folder_list" else "无匹配文件。")
                                                else:
                                                    response = result
                                            except (json.JSONDecodeError, TypeError):
                                                response = result
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
                            # Fallback: model didn't call a tool. Check remind_me first (e.g. "15分钟后有个会能提醒一下吗") so we set the reminder and return a clean response instead of messy 2:49 text.
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
                            if remind_fallback and isinstance(remind_fallback, dict) and _has_remind_me:
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
                            else:
                                # Fallback: model didn't call a tool (e.g. replied "No"). If user intent is clear, run plugin anyway.
                                unhelpful = not content_str or len(content_str) < 80 or content_str.strip().lower() in ("no", "i can't", "i cannot", "sorry", "nope")
                                fallback_route = _infer_route_to_plugin_fallback(query) if unhelpful else None
                                if fallback_route and registry and any(t.name == "route_to_plugin" for t in (registry.list_tools() or [])):
                                    try:
                                        _component_log("tools", "fallback route_to_plugin (model did not call tool)")
                                        result = await registry.execute_async("route_to_plugin", fallback_route, context)
                                        if result == ROUTING_RESPONSE_ALREADY_SENT:
                                            return ROUTING_RESPONSE_ALREADY_SENT
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
                                                if not (response or (response and response.strip())):
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
                                        "目录", "哪些文件", "列出文件", "目录下", "列出", "有什么文件", "文件列表", "我的文件", "看看文件", "显示文件",
                                        "list file", "list files", "list directory", "list folder", "list content", "what file", "what's in my", "files in my",
                                        "folder content", "folder list", "file list", "show file", "show files", "show directory", "show folder", "view file", "view directory",
                                    )
                                    _query_lower = (query or "").lower()
                                    _query_raw = query or ""
                                    if registry and any(t.name == "folder_list" for t in (registry.list_tools() or [])) and any(
                                        (p in _query_lower if p.isascii() else p in _query_raw) for p in list_dir_phrases
                                    ):
                                        try:
                                            _component_log("tools", "fallback folder_list (model did not call tool)")
                                            result = await registry.execute_async("folder_list", {"path": "."}, context)
                                            if isinstance(result, str) and result.strip():
                                                try:
                                                    entries = json.loads(result)
                                                    if isinstance(entries, list) and entries:
                                                        lines = [f"- {e.get('name', '?')} ({e.get('type', '?')})" for e in entries if isinstance(e, dict)]
                                                        response = "目录下的内容：\n" + "\n".join(lines) if lines else result
                                                    else:
                                                        response = "目录为空。" if isinstance(entries, list) else result
                                                except (json.JSONDecodeError, TypeError):
                                                    response = result
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
                last_tool_name = None  # for _tool_result_usable_as_final_response: skip second LLM when tool result is core-contained
                last_tool_result_raw = None
                last_tool_args = None  # for run_skill: skills_results_need_llm per-skill override
                meta = Util().get_core_metadata()
                tool_timeout_sec = max(0, int(getattr(meta, "tool_timeout_seconds", 120) or 0))
                for tc in tool_calls:
                    tcid = tc.get("id") or ""
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    args_redacted = redact_params_for_log(args) if isinstance(args, dict) else args
                    logger.info("Tool selected: name={} parameters={}", name, args_redacted)
                    if name == "run_skill":
                        _component_log("tools", "executing run_skill (in_process from run_skill_py_in_process_skills if listed)")
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
                    try:
                        if tool_timeout_sec > 0:
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
                    if name in ("save_result_page", "get_file_view_link") and isinstance(result, str) and "/files/out" in result and "token=" in result:
                        last_file_link_result = result
                    last_tool_name = name
                    last_tool_result_raw = result if isinstance(result, str) else None
                    last_tool_args = args if isinstance(args, dict) else None
                    tool_content = result
                    if compaction_cfg.get("compact_tool_results") and isinstance(tool_content, str):
                        # document_read: keep more context so the model can generate HTML/summary from it; other tools: 4000
                        limit = 28000 if name == "document_read" else 4000
                        if len(tool_content) > limit:
                            tool_content = tool_content[:limit] + "\n[Output truncated for context.]"
                    current_messages.append({"role": "tool", "tool_call_id": tcid, "content": tool_content})
                if routing_sent:
                    out = routing_response_text if routing_response_text is not None else ROUTING_RESPONSE_ALREADY_SENT
                    if mix_route_this_request and mix_show_route_label and isinstance(out, str) and out is not ROUTING_RESPONSE_ALREADY_SENT:
                        layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
                        label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
                        out = label + (_strip_leading_route_label(out or "") or "")
                    return out
                # Use exact tool result as response when it contains a file view link, so the model cannot corrupt the URL in a follow-up reply
                if last_file_link_result:
                    out = last_file_link_result
                    if mix_route_this_request and mix_show_route_label and isinstance(out, str):
                        layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
                        label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
                        out = label + (_strip_leading_route_label(out or "") or "")
                    response = out
                    break
                # Skip second LLM when tool result is core-contained (deterministic check, no LLM). Config: tools.use_result_as_response.
                try:
                    use_result_config = (getattr(meta, "tools_config", None) or {}).get("use_result_as_response") if meta else None
                    if last_tool_name and last_tool_result_raw and _tool_result_usable_as_final_response(last_tool_name, last_tool_result_raw, use_result_config, last_tool_args):
                        out = last_tool_result_raw
                        if mix_route_this_request and mix_show_route_label and isinstance(out, str):
                            layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
                            label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
                            out = label + (_strip_leading_route_label(out or "") or "")
                        response = out
                        break
                    elif last_tool_name and last_tool_result_raw and _tool_result_looks_like_error(last_tool_result_raw) and mix_route_this_request:
                        # Don't use error-like result; in mix mode use the other model for the next turn
                        use_other_model_next_turn = True
                except Exception as e:
                    logger.debug("use_result_as_response check failed (continuing to second LLM): {}", e)
            else:
                response = (current_messages[-1].get("content") or "").strip() if current_messages else None
            await close_browser_session(context)
        else:
            response = await core.openai_chat_completion(
                messages=llm_input, llm_name=effective_llm_name
            )
            # Mix fallback: first model failed; retry once with the other route so the task is not blocked.
            if (response is None or (isinstance(response, str) and len(response.strip()) == 0)) and mix_route_this_request:
                hr = getattr(Util().get_core_metadata(), "hybrid_router", None) or {}
                if bool(hr.get("fallback_on_llm_error", True)) and (getattr(Util().get_core_metadata(), "main_llm_local", None) or "").strip() and (getattr(Util().get_core_metadata(), "main_llm_cloud", None) or "").strip():
                    other_route = "cloud" if mix_route_this_request == "local" else "local"
                    other_llm = (getattr(Util().get_core_metadata(), "main_llm_cloud", None) or "").strip() if other_route == "cloud" else (getattr(Util().get_core_metadata(), "main_llm_local", None) or "").strip()
                    if other_llm:
                        _component_log("mix", f"first model failed (no-tool path), retrying with {other_route} ({other_llm})")
                        response = await core.openai_chat_completion(messages=llm_input, llm_name=other_llm)
                        if response and isinstance(response, str) and response.strip():
                            mix_route_this_request = other_route
                            mix_route_layer_this_request = (mix_route_layer_this_request or "") + "_fallback" if mix_route_layer_this_request else "fallback"

        if response is None or (isinstance(response, str) and len(response.strip()) == 0):
            return "Sorry, something went wrong and please try again. (对不起，出错了，请再试一次)"
        # If the model echoed raw "[]" (e.g. from empty folder_list/file_find), show a friendly message instead
        if isinstance(response, str) and response.strip() == "[]":
            response = "I couldn't find that file or path. Try asking me to list your files (e.g. 'list my files' or 'what files do I have'), then use the exact filename (e.g. 1.pdf) when you ask about a document."
        # If the model echoed the internal file_write/save_result_page empty-content message, show a short user-facing message instead
        if isinstance(response, str) and ("Do NOT share this link" in response or ("empty or too small" in response and '"written"' in response)):
            response = "The slide wasn’t generated yet because the content was empty. Please try again; I’ll generate the HTML from the document and then save it. （幻灯片尚未生成，请再试一次。）"
        if mix_route_this_request and mix_show_route_label:
            layer_suffix = f" · {mix_route_layer_this_request}" if mix_route_layer_this_request else ""
            label = f"[Local{layer_suffix}] " if mix_route_this_request == "local" else f"[Cloud{layer_suffix}] "
            response = label + (_strip_leading_route_label(response or "") or "")
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

        return response
    except Exception as e:
        logger.exception(e)
        return None


