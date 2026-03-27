from __future__ import annotations

import time
import uuid
import re
from pathlib import Path
from typing import Any, Dict, List

from base.workflow_trace import emit_event, start_turn, end_turn


def _derive_daily_brief_args_from_query_local(user_text: str, plain_markdown_requested: bool) -> List[str]:
    q = (user_text or "").strip()
    q_lo = q.lower()
    if (
        ("list" in q_lo and "feed" in q_lo)
        or ("列出" in q and "源" in q)
        or ("有哪些订阅" in q)
    ):
        return ["list"]
    max_items = 20
    m_cn = re.search(r"(\d{1,3})\s*条", q)
    m_en = re.search(r"\b(\d{1,3})\s*(items?|headlines?)\b", q_lo)
    m = m_cn or m_en
    if m:
        try:
            max_items = max(1, min(100, int(m.group(1))))
        except Exception:
            max_items = 20
    lang = "all"
    if any(k in q for k in ("中文", "汉语", "国内")):
        lang = "cn"
    elif any(k in q for k in ("英文", "英语")):
        lang = "en"
    cmd = "fetch" if plain_markdown_requested else "fetch-vmprint"
    out = [cmd, "--max", str(max_items), "--lang", lang]
    if cmd == "fetch-vmprint":
        out += ["--theme", "dispatch", "--output_format", "browser_preview_html"]
    return out


def run_mock_turn(prompt: str, trace_dir: Path) -> Dict[str, Any]:
    trace_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    start_turn(run_id=run_id, query=prompt, user_id="workflow-test-user", session_id="workflow-mock")
    p = (prompt or "").strip()
    p_lo = p.lower()
    if ("今日新闻" in p) or ("daily brief" in p_lo) or ("每日简报" in p):
        plain_md = ("markdown" in p_lo) or ("纯markdown" in p_lo) or ("纯文本" in p)
        argv = _derive_daily_brief_args_from_query_local(p, plain_md)
        emit_event(
            event_type="skill_call_started",
            component="run_skill",
            summary="run_skill started",
            details={"skill_name": "daily-brief-1.0.0", "script": "fetch_rss.py"},
        )
        emit_event(
            event_type="arg_normalization",
            component="run_skill",
            summary="run_skill argv finalized",
            details={"argv": argv},
        )
        response = "mock daily brief done"
    elif ("天气" in p) or ("weather" in p_lo):
        emit_event(
            event_type="tool_call_started",
            component="tool_registry",
            summary="tool call started: run_skill",
            details={"tool_name": "run_skill"},
        )
        response = "mock weather done"
    elif ("自选股" in p) or ("stock" in p_lo):
        missing_symbol = ("context" in p_lo and "自选股" not in p and "portfolio" not in p_lo and "watchlist" not in p_lo)
        if missing_symbol:
            emit_event(
                event_type="arg_normalization",
                component="run_skill",
                summary="run_skill argv finalized",
                details={"argv": ["portfolio"]},
            )
        else:
            emit_event(
                event_type="arg_normalization",
                component="run_skill",
                summary="run_skill argv finalized",
                details={"argv": ["portfolio"]},
            )
            emit_event(
                event_type="tool_call_started",
                component="tool_registry",
                summary="tool call started: run_skill",
                details={"tool_name": "run_skill"},
            )
        response = "mock stock done"
    elif ("remind me" in p_lo) or ("提醒" in p):
        emit_event(
            event_type="tool_call_started",
            component="tool_registry",
            summary="tool call started: remind_me",
            details={"tool_name": "remind_me"},
        )
        if ("in " not in p_lo and " at " not in p_lo and "分钟" not in p and "小时" not in p):
            emit_event(
                event_type="tool_call_finished",
                component="tool_registry",
                summary="tool call finished: remind_me",
                details={"tool_name": "remind_me", "status": "error"},
            )
        response = "mock reminder done"
    elif ("read " in p_lo and "document" in p_lo) or ("open " in p_lo and "file" in p_lo):
        if "report-2028.pdf" in p:
            emit_event(
                event_type="tool_call_started",
                component="tool_registry",
                summary="tool call started: file_find",
                details={"tool_name": "file_find"},
            )
        else:
            emit_event(
                event_type="tool_call_started",
                component="tool_registry",
                summary="tool call started: document_read",
                details={"tool_name": "document_read"},
            )
        response = "mock file done"
    elif ("knowledge base" in p_lo) or ("knowledgebase" in p_lo) or ("知识库" in p):
        if "quantum banana protocol" in p_lo:
            emit_event(
                event_type="tool_call_started",
                component="tool_registry",
                summary="tool call started: knowledge_base_search",
                details={"tool_name": "knowledge_base_search"},
            )
            emit_event(
                event_type="tool_call_finished",
                component="tool_registry",
                summary="tool call finished: knowledge_base_search",
                details={"tool_name": "knowledge_base_search", "status": "ok"},
            )
        else:
            emit_event(
                event_type="tool_call_started",
                component="tool_registry",
                summary="tool call started: document_read",
                details={"tool_name": "document_read"},
            )
        response = "mock kb done"
    elif "search" in p_lo and "web" in p_lo:
        emit_event(
            event_type="tool_call_started",
            component="tool_registry",
            summary="tool call started: web_search",
            details={"tool_name": "web_search"},
        )
        emit_event(
            event_type="tool_call_finished",
            component="tool_registry",
            summary="tool call finished: web_search",
            details={"tool_name": "web_search", "status": "ok", "result_len": 120},
        )
        response = "mock web search done"
    elif "remember that" in p_lo or "what do you remember" in p_lo:
        if "what do you remember" in p_lo:
            emit_event(
                event_type="tool_call_started",
                component="tool_registry",
                summary="tool call started: agent_memory_search",
                details={"tool_name": "agent_memory_search"},
            )
        else:
            emit_event(
                event_type="tool_call_started",
                component="tool_registry",
                summary="tool call started: append_agent_memory",
                details={"tool_name": "append_agent_memory"},
            )
        response = "mock memory done"
    elif "send an email" in p_lo:
        emit_event(
            event_type="tool_call_started",
            component="tool_registry",
            summary="tool call started: file_read",
            details={"tool_name": "file_read"},
        )
        response = "mock email done"
    else:
        emit_event(
            event_type="model_selected",
            component="llm_loop",
            summary="mock model selected",
            details={"mode": "mock", "model": "mock-model"},
        )
        response = "mock generic done"
    end_turn(final_output=response, artifact={"mode": "mock"})
    trace_path = trace_dir / f"{run_id}.jsonl"
    # give filesystem a tiny moment when very fast tests run on CI
    time.sleep(0.01)
    return {"run_id": run_id, "trace_path": str(trace_path), "response": response}

