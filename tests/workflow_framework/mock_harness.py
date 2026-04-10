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
        layout = "digest_table"
        if any(
            k in q
            for k in (
                "报纸排版",
                "报纸版式",
                "头版",
                "新闻报纸",
                "杂志排版",
                "杂志版式",
                "杂志布局",
                "杂志格式",
                "杂志样式",
                "杂志风",
            )
        ) or any(
            k in q_lo
            for k in (
                "newspaper layout",
                "front page layout",
                "broadsheet layout",
                "broadsheet",
                "magazine layout",
                "folio layout",
                "real magazine",
                "editorial layout",
                "magazine format",
            )
        ):
            layout = "newspaper"
        out += ["--document-layout", layout]
    return out


def _emit_mock_skill_trace(skill_name: str, script: str, argv: List[str]) -> None:
    emit_event(
        event_type="skill_call_started",
        component="run_skill",
        summary="run_skill started",
        details={"skill_name": skill_name, "script": script},
    )
    emit_event(
        event_type="arg_normalization",
        component="run_skill",
        summary="run_skill argv finalized",
        details={"argv": argv},
    )


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
    elif "stock monitor" in p_lo or "stock-monitor" in p_lo:
        _emit_mock_skill_trace("stock-monitor-1.0.0", "mock.py", ["alerts", "--dry-run"])
        response = "mock stock monitor skill done"
    elif "weather skill" in p_lo or "天气技能" in p:
        _emit_mock_skill_trace("weather-1.0.0", "mock.py", ["forecast", "--city", "Seattle"])
        response = "mock weather skill done"
    elif "magazine render" in p_lo or "杂志排版渲染" in p:
        _emit_mock_skill_trace("magazine-render-1.0.0", "render.py", ["--preview", "newsletter"])
        response = "mock magazine render done"
    elif "vmprint ast" in p_lo:
        _emit_mock_skill_trace("vmprint-ast-layout-1.0.0", "mock.py", ["--layout", "digest"])
        response = "mock vmprint ast layout done"
    elif "ppt generation" in p_lo:
        _emit_mock_skill_trace("ppt-generation-1.0.0", "mock.py", ["outline", "--slides", "8"])
        response = "mock ppt generation done"
    elif "ip camera" in p_lo:
        _emit_mock_skill_trace("ip-cameras", "mock.py", ["snapshot", "--rtsp", "mock://cam"])
        response = "mock ip cameras done"
    elif "desktop ui" in p_lo:
        _emit_mock_skill_trace("desktop-ui", "mock.py", ["focus", "--window", "Terminal"])
        response = "mock desktop ui done"
    elif "summarize this article url" in p_lo:
        _emit_mock_skill_trace(
            "summarize-1.0.0",
            "mock.py",
            ["https://example.com/page", "--length", "short"],
        )
        response = "mock summarize skill done"
    elif "self improving" in p_lo:
        _emit_mock_skill_trace("self-improving-1.2.16", "mock.py", ["feedback", "--capture"])
        response = "mock self improving done"
    elif "cli anything bridge" in p_lo:
        _emit_mock_skill_trace("cli-anything-bridge-1.0.0", "mock.py", ["exec", "--wrapped", "true"])
        response = "mock cli anything bridge done"
    elif "html slides" in p_lo:
        _emit_mock_skill_trace("html-slides-1.0.0", "mock.py", ["build", "--engine", "reveal"])
        response = "mock html slides done"
    elif "x api twitter" in p_lo:
        _emit_mock_skill_trace("x-api-1.0.0", "mock.py", ["post", "--dry-run"])
        response = "mock x api done"
    elif "social media agent" in p_lo:
        _emit_mock_skill_trace("social-media-agent-1.0.0", "mock.py", ["schedule", "--cross-post"])
        response = "mock social media agent done"
    elif "openai whisper" in p_lo:
        _emit_mock_skill_trace("openai-whisper-1.0.0", "mock.py", ["transcribe", "meeting.m4a"])
        response = "mock openai whisper done"
    elif "meta social" in p_lo:
        _emit_mock_skill_trace("meta-social-1.0.0", "mock.py", ["insights", "--page", "demo"])
        response = "mock meta social done"
    elif "maton api" in p_lo:
        _emit_mock_skill_trace("maton-api-gateway-1.0.0", "mock.py", ["webhook", "--test"])
        response = "mock maton api gateway done"
    elif "linkedin writer" in p_lo:
        _emit_mock_skill_trace("linkedin-writer-1.0.0", "mock.py", ["draft", "--tone", "professional"])
        response = "mock linkedin writer done"
    elif "image generation" in p_lo:
        _emit_mock_skill_trace("image-generation-1.0.0", "mock.py", ["prompt", "sunset over mountains"])
        response = "mock image generation done"
    elif "hootsuite" in p_lo:
        _emit_mock_skill_trace("hootsuite-1.0.0", "mock.py", ["schedule", "--calendar", "main"])
        response = "mock hootsuite done"
    elif "gog gmail" in p_lo:
        _emit_mock_skill_trace("gog-1.0.0", "mock.py", ["gmail", "search", "in:inbox"])
        response = "mock gog done"
    elif "baidu search" in p_lo:
        _emit_mock_skill_trace("baidu-search-1.1.0", "mock.py", ["query", "北京 新闻"])
        response = "mock baidu search done"
    elif "apple notes" in p_lo:
        _emit_mock_skill_trace("apple-notes-1.0.0", "mock.py", ["list", "--folder", "Notes"])
        response = "mock apple notes done"
    elif "answeroverflow" in p_lo:
        _emit_mock_skill_trace("answeroverflow-1.0.2", "mock.py", ["search", "discord topic"])
        response = "mock answeroverflow done"
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

