import asyncio
import base64
import copy
from datetime import date, datetime, timedelta
import html as html_module
import importlib
import json
import logging
from multiprocessing import Process
import os
import runpy
import signal
import socket
import subprocess
import sys
import warnings
from pathlib import Path
import threading
import time
import uuid
import webbrowser

# Reduce third-party FutureWarning noise (transformers, huggingface_hub); see docs/ResultViewerAndCommonLogs.md
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers.utils.generic")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")
import chromadb
import chromadb.config
import aiohttp
from aiohttp.client_exceptions import ClientConnectorError
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from typing import Any, Optional, Dict, List, Tuple, Union
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi import FastAPI, Request, Response
from loguru import logger
import requests
import yaml
import uvicorn
import httpx
from contextlib import asynccontextmanager
import re
from jinja2 import Template
#import logging

# Ensure the project root is in the PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.orchestrator import Orchestrator
from base.PluginManager import PluginManager
from base.util import Util, redact_params_for_log
from base.base import (
    LLM, EmbeddingRequest, Intent, IntentType, RegisterChannelRequest, PromptRequest, AsyncResponse, User, InboundRequest,
    ExternalPluginRegisterRequest, PluginLLMGenerateRequest, PluginResult,
)
from base.BaseChannel import BaseChannel
from base.BasePlugin import BasePlugin
from base.base import ChannelType, ContentType, User, CoreMetadata, Server
from llm.llmService import LLMServiceManager
from memory.embedding import LlamaCppEmbedding
from memory.mem import Memory
from memory.llm import LlamaCppLLM
from memory.chat.message import ChatMessage
from memory.chat.chat import ChatHistory
from memory.base import MemoryBase, VectorStoreBase, EmbeddingBase, LLMBase
from base.prompt_manager import get_prompt_manager
from memory.prompts import RESPONSE_TEMPLATE, MEMORY_CHECK_PROMPT, MEMORY_BATCH_SUMMARIZE_PROMPT
from base.workspace import (
    ensure_user_sandbox_folders,
    get_workspace_dir,
    get_user_knowledgebase_dir,
    load_workspace,
    build_workspace_system_prefix,
    load_agent_memory_file,
    clear_agent_memory_file,
    load_daily_memory_for_dates,
    clear_daily_memory_for_dates,
    trim_content_bootstrap,
)
from base.skills import get_skills_dir, load_skills, load_skills_from_dirs, load_skill_by_folder_from_dirs, build_skills_system_block
from base.tools import ToolContext, get_tool_registry, ROUTING_RESPONSE_ALREADY_SENT
from base import last_channel as last_channel_store
from base.markdown_outbound import markdown_to_channel, looks_like_markdown, classify_outbound_format
from tools.builtin import register_builtin_tools, register_routing_tools, close_browser_session
from core.coreInterface import CoreInterface
from core.emailChannel import channel
from core.routes import (
    auth, lifecycle, inbound as inbound_routes, config_api, files, memory_routes, knowledge_base_routes,
    plugins_api, misc_api, ui_routes, websocket_routes,
)
# Tool helpers: prefer core.services.tool_helpers; fallback to inline definitions so Core never crashes if the module is missing or broken.
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
    # Inline fallback: same logic as core/services/tool_helpers.py (compare with original single core.py).
    def _tool_result_looks_like_error(result: Any) -> bool:
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

    def _tool_result_usable_as_final_response(
        tool_name: str,
        tool_result: str,
        config: Optional[Dict[str, Any]] = None,
        tool_args: Optional[Dict[str, Any]] = None,
    ) -> bool:
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
            if _tool_result_looks_like_error(result):
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
                return "/files/out" in result and "token=" in result
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

    def _infer_remind_me_fallback(query: str) -> Optional[Dict[str, Any]]:
        if not query or not isinstance(query, str):
            return None
        try:
            q = query.strip()
            # "15分钟后有个会，请提前5分钟提醒我" → remind in (15-5)=10 min (base = event time, minus advance)
            m_ev = re.search(r"(\d+)\s*分钟(?:后|以后|之后)?", q)
            m_bef = re.search(r"提前\s*(\d+)\s*分钟", q)
            if m_ev and m_bef:
                ev, bef = int(m_ev.group(1)), int(m_bef.group(1))
                if 1 <= ev <= 43200 and 0 <= bef <= ev:
                    n = max(1, ev - bef)
                    return {"tool": "remind_me", "arguments": {"minutes": n, "message": q[:120] or "Reminder"}}
            m = re.search(r"(\d+)\s*分钟后", q)
            if m:
                n = int(m.group(1))
                if 0 < n <= 43200:
                    # Don't guess: if user said event time (有个会, etc.) but no "提前Y分钟", ask instead
                    event_kw = ("有个会", "开会", "meeting", "会议")
                    if not m_bef and any(k in q for k in event_kw):
                        return None
                    return {"tool": "remind_me", "arguments": {"minutes": n, "message": q[:120] or "Reminder"}}
        except Exception:
            pass
        return None

    def _remind_me_needs_clarification(query: str) -> bool:
        if not query or not isinstance(query, str):
            return False
        q = query.strip()
        reminder_kw = ("remind", "提醒", "闹钟", "定时", "有个会", "开会", "meeting", "提前提醒", "到点提醒")
        if not any(kw in q.lower() if kw.isascii() else kw in q for kw in reminder_kw):
            return False
        return _infer_remind_me_fallback(query) is None

    def _remind_me_clarification_question(query: str):
        if not query or not isinstance(query, str):
            return None
        q = query.strip()
        if ("有个会" in q or "开会" in q or "meeting" in q) and re.search(r"\d+\s*分钟", q) and not re.search(r"提前\s*\d+\s*分钟", q):
            return "提前几分钟提醒你啊？ How many minutes before should I remind you?"
        if ("生日" in q or "月" in q) and ("提前" in q or "提醒" in q) and not re.search(r"提前\s*(?:一周|几天|\d+\s*天)", q):
            return "提前一周提醒你可以吗？或者提前几天？ Remind you one week before, or how many days before?"
        return None

    def _infer_route_to_plugin_fallback(query: str) -> Optional[Dict[str, Any]]:
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
            return {"plugin_id": "ppt-generation", "capability_id": "create_from_source", "parameters": {"source": query.strip()}}
        return None

    def _parse_raw_tool_calls_from_content(content: str):
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

logging.basicConfig(level=logging.CRITICAL)


class _SuppressConfigCoreAccessFilter(logging.Filter):
    """Filter out uvicorn access log lines for GET /api/config/core (Companion connection checks)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage() if hasattr(record, "getMessage") else (getattr(record, "msg", "") or "")
            if "/api/config/core" in str(msg) and " 200 " in str(msg):
                return False
        except Exception:
            pass
        return True


# Pinggy tunnel state: set by _start_pinggy_and_open_browser when tunnel is ready. Read by GET /pinggy.
_pinggy_state: Dict[str, Any] = {"public_url": None, "connect_url": None, "qr_base64": None, "error": None}


def _component_log(component: str, message: str) -> None:
    """Log component activity when core is not silent (silent: false in core.yml). Toggle via config/core.yml silent: true/false."""
    try:
        if not Util().is_silent():
            logger.info(f"[{component}] {message}")
    except Exception:
        pass


def _truncate_for_log(s: str, max_len: int = 2000) -> str:
    """Truncate string for logging; append ... if truncated."""
    if not s or len(s) <= max_len:
        return s or ""
    return s[:max_len] + "\n... (truncated)"


def _strip_leading_route_label(s: str) -> str:
    """Remove leading [Local], [Cloud], or [Local · ...] / [Cloud · ...] so we don't duplicate labels."""
    if not s or not isinstance(s, str):
        return s or ""
    t = s.strip()
    # Match [Local], [Cloud], or [Local · heuristic], [Cloud · semantic], etc.
    if re.match(r"^\[(?:Local|Cloud)(?:\s*·\s*[^\]]*)?\]\s*", t):
        return re.sub(r"^\[(?:Local|Cloud)(?:\s*·\s*[^\]]*)?\]\s*", "", t, count=1).strip()
    return s


class Core(CoreInterface):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(Core, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.hasEmailChannel = False
            self.initialized = True
            self.latestPromptRequest: PromptRequest = None
            Util().setup_logging("core", Util().get_core_metadata().mode)
            meta = Util().get_core_metadata()
            self.orchestrator_timeout_seconds = max(0, int(getattr(meta, "orchestrator_timeout_seconds", 60) or 0))
            self.orchestrator_unified_with_tools = getattr(meta, "orchestrator_unified_with_tools", True)
            self.inbound_request_timeout_seconds = max(0, int(getattr(meta, "inbound_request_timeout_seconds", 0) or 0))
            root = Util().root_path()
            db_folder = os.path.join(root, 'database')
            if not os.path.exists(db_folder):
                os.makedirs(db_folder)

            self.app = FastAPI()
            self.plugin_manager: PluginManager = None
            self.channels: List[BaseChannel] = []
            self.server = None
            self._core_http_ready = False  # True when Core init is done; /ready returns 503 until then
            self.embedder: EmbeddingBase = None
            self.mem_instance: MemoryBase = None
            self.vector_store: VectorStoreBase = None
            self.llmManager: LLMServiceManager = LLMServiceManager()

            #self.chroma_server_process = self.start_chroma_server()
            self.chromra_memory_client = None
            logger.debug("Before initialize chat history")
            self.chatDB: ChatHistory = ChatHistory()
            logger.debug("After initialize chat history")
            self.run_ids = {}
            self.session_ids = {}

            self.request_queue = asyncio.Queue(100)
            self.response_queue = asyncio.Queue(100)
            self.memory_queue = asyncio.Queue(100)
            self.request_queue_task = None
            self.response_queue_task = None
            self.memory_queue_task = None
            self._system_plugin_processes: List[asyncio.subprocess.Process] = []
            self._pending_plugin_calls: Dict[str, Dict[str, Any]] = {}  # session_key -> {plugin_id, capability_id, params, missing, ...}
            self._inbound_async_results: Dict[str, dict] = {}  # request_id -> {status, ok?, text?, images?, error?, created_at}; TTL 5 min
            self._inbound_async_results_ttl_sec = 300
            self._ws_sessions: Dict[str, WebSocket] = {}  # session_id -> WebSocket for push (Companion/channel holds /ws open; Core pushes async result and proactive messages)
            self._ws_user_by_session: Dict[str, str] = {}  # session_id -> user_id (so we can deliver_to_user for cron/reminder)
            #self.active_plugin = None
            logger.debug("Before initialize orchestrator")
            self.orchestratorInst = Orchestrator(self)
            logger.debug("After initialize orchestrator")


    def create_homeclaw_account(
        self,
        email: str,
        password: str
    ) ->int:
        url = "https://mail.homeclaw.ai/api/v1/user"  # Replace with your API URL
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "email": email,
            "raw_password": password,
            "comment": "my comment",
            "quota_bytes": 1000000000,
            "global_admin": True,
            "enabled": True,
            "change_pw_next_login": False,
            "enable_imap": True,
            "enable_pop": True,
            "allow_spoofing": True,
            "forward_enabled": False,
            "forward_destination": [],
            "forward_keep": False,
            "reply_enabled": False,
            "reply_subject": "",
            "reply_body": "",
            "reply_startdate": "",
            "reply_enddate": "",
            "displayed_name": "",
            "spam_enabled": True,
            "spam_mark_as_read": True,
            "spam_threshold": 80
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            logger.debug(f"User created successfully: {response.json()}")
        elif response.status_code == 400:
            logger.debug(f"Input validation exception: {response.json()}")
        elif response.status_code == 401:
            logger.debug(f"Authorization header missing: {response.json()}")
        elif response.status_code == 403:
            logger.debug(f"Authorization header invalid: {response.json()}")
        elif response.status_code == 409:
            logger.debug(f"Duplicate user: {response.json()}")
        else:
            logger.debug(f"Unknown error: {response.json()}")

        return response.status_code


    def find_plugin_prompt(self, user_input: str) -> str:
        plugin_descriptions_text = "\n\n".join(
            [f"{i+1}. {desc}" for i, desc in enumerate(self.plugin_manager.plugin_descriptions.keys())]
        )

        return f"""
        You are an expert at understanding user intentions based on input text and available plugin descriptions. Analyze the latest user input and determine which plugin description best matches the user's needs. If the user input does not require any plugin, indicate that as well.
        Provide the index of the best matching plugin description. If no plugin is needed, return "None".
        Focus primarily on the latest user input, even if there is chat history.

        Examples:

        User Input:
        "What's the weather like today?"

        Plugin Descriptions:
        1. This plugin retrieves the latest news headlines and provides summaries of news articles based on specified categories, countries, sources, and keywords.
        2. This plugin generates motivational and uplifting quotes based on chat histories using a language model (LLM). It is designed to detect user emotions, such as depression or sadness, and provide comforting and encouraging quotes to help improve their mood. The plugin can be used to offer emotional support and positivity to users during their conversations.
        3. This plugin retrieves the current weather and weather forecast for specified locations. It provides detailed information including temperature, humidity, weather conditions, wind direction, wind power, and air quality index (AQI). This plugin can be used to provide users with real-time weather updates and forecasts for any city.

        Output:
        3

        User Input:
        "Can you tell me a joke?"

        Plugin Descriptions:
        1. This plugin retrieves the latest news headlines and provides summaries of news articles based on specified categories, countries, sources, and keywords.
        2. This plugin generates motivational and uplifting quotes based on chat histories using a language model (LLM). It is designed to detect user emotions, such as depression or sadness, and provide comforting and encouraging quotes to help improve their mood. The plugin can be used to offer emotional support and positivity to users during their conversations.
        3. This plugin retrieves the current weather and weather forecast for specified locations. It provides detailed information including temperature, humidity, weather conditions, wind direction, wind power, and air quality index (AQI). This plugin can be used to provide users with real-time weather updates and forecasts for any city.

        Output:
        None

        User Input:
        "I need some motivation."

        Plugin Descriptions:
        1. This plugin retrieves the latest news headlines and provides summaries of news articles based on specified categories, countries, sources, and keywords.
        2. This plugin generates motivational and uplifting quotes based on chat histories using a language model (LLM). It is designed to detect user emotions, such as depression or sadness, and provide comforting and encouraging quotes to help improve their mood. The plugin can be used to offer emotional support and positivity to users during their conversations.
        3. This plugin retrieves the current weather and weather forecast for specified locations. It provides detailed information including temperature, humidity, weather conditions, wind direction, wind power, and air quality index (AQI). This plugin can be used to provide users with real-time weather updates and forecasts for any city.

        Output:
        2

        User Input:
        "Give me the top news for today."

        Plugin Descriptions:
        1. This plugin retrieves the latest news headlines and provides summaries of news articles based on specified categories, countries, sources, and keywords.
        2. This plugin generates motivational and uplifting quotes based on chat histories using a language model (LLM). It is designed to detect user emotions, such as depression or sadness, and provide comforting and encouraging quotes to help improve their mood. The plugin can be used to offer emotional support and positivity to users during their conversations.
        3. This plugin retrieves the current weather and weather forecast for specified locations. It provides detailed information including temperature, humidity, weather conditions, wind direction, wind power, and air quality index (AQI). This plugin can be used to provide users with real-time weather updates and forecasts for any city.

        Output:
        1

        User Input:
        "我想看新闻！"

        Plugin Descriptions:
        1. This plugin retrieves the latest news headlines and provides summaries of news articles based on specified categories, countries, sources, and keywords.
        2. This plugin generates motivational and uplifting quotes based on chat histories using a language model (LLM). It is designed to detect user emotions, such as depression or sadness, and provide comforting and encouraging quotes to help improve their mood. The plugin can be used to offer emotional support and positivity to users during their conversations.
        3. This plugin retrieves the current weather and weather forecast for specified locations. It provides detailed information including temperature, humidity, weather conditions, wind direction, wind power, and air quality index (AQI). This plugin can be used to provide users with real-time weather updates and forecasts for any city.

        Output:
        1

        Please select the most proper plugin for the following user input and plugin descriptions:
        User Input:
        "{user_input}"

        Plugin Descriptions:
        {plugin_descriptions_text}

        Output:
        """
    async def is_proper_plugin(self, plugin: BasePlugin, text: str):
        """
        Implement logic to check if the active plugin is appropriate for the given text.
        This could involve checking for certain keywords or contextual clues.
        """
        return await plugin.check_best_plugin(text)

    async def find_plugin_for_text(self, text: str) -> Optional[BasePlugin]:
        if self.plugin_manager.num_plugins() == 0:
            logger.debug("No plugins loaded.")
            return None
        # Prioritize the active plugin if it is set
        #if self.active_plugin:
        #    result, text = await self.is_proper_plugin(self.active_plugin, text)
        #    if result:
        #        logger.debug(f"Found plugin: {self.active_plugin.get_description()}")
        #        return self.active_plugin

        prompt = self.find_plugin_prompt(text)
        logger.debug(f"Find plugin Prompt: {prompt}")

        messages = [{"role": "system", "content": prompt}]
        best_description = await self.openai_chat_completion(messages=messages) # Replace with your actual method to get LLM response
        if best_description is None:
            return None
        if best_description.lower().strip() == "none" or best_description.strip() == "":
            return None

        logger.debug(f"Best description: {best_description}")
        # Convert plugin descriptions to a list
        original_descriptions = list(self.plugin_manager.plugin_descriptions.keys())

        # Extract the index of the best description from the LLM's output
        match = re.search(r"(\d+)", best_description)
        if match:
            best_index = int(match.group(1)) - 1  # Assuming LLM output is 1-indexed
        else:
            logger.error(f"Failed to extract index from best description: {best_description}")
            return None

        if 0 <= best_index < len(original_descriptions):
            best_match_description = original_descriptions[best_index]
            found_plugin = self.plugin_manager.plugin_descriptions.get(best_match_description, None)
            logger.debug(f"Found plugin: {found_plugin.get_description()}")
            return found_plugin
        else:
            logger.error(f"Best index {best_index} is out of range for description keys")
            return None

    def load_plugins(self):
        self.plugin_manager.load_plugins()

    def initialize_plugins(self):
        self.plugin_manager.initialize_plugins()


    def start_hot_reload(self):
        self.plugin_manager.start_hot_reload()

    def _pending_plugin_call_key(self, app_id: str, user_id: str, session_id: str) -> str:
        return f"{app_id or ''}:{user_id or ''}:{session_id or ''}"

    def get_pending_plugin_call(self, app_id: str, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        key = self._pending_plugin_call_key(app_id, user_id, session_id)
        return self._pending_plugin_calls.get(key)

    def set_pending_plugin_call(self, app_id: str, user_id: str, session_id: str, data: Dict[str, Any]) -> None:
        key = self._pending_plugin_call_key(app_id, user_id, session_id)
        self._pending_plugin_calls[key] = data

    def clear_pending_plugin_call(self, app_id: str, user_id: str, session_id: str) -> None:
        key = self._pending_plugin_call_key(app_id, user_id, session_id)
        self._pending_plugin_calls.pop(key, None)

    def _discover_system_plugins(self) -> List[Dict]:
        """Discover plugins in system_plugins/ that have register.js and a server (server.js or package.json start). Returns list of {id, cwd, start_argv, register_argv}."""
        root = Util().root_path()
        base = getattr(Util(), "system_plugins_path", lambda: os.path.join(root, "system_plugins"))()
        if not os.path.isdir(base):
            return []
        out = []
        for name in sorted(os.listdir(base)):
            if name.startswith("."):
                continue
            folder = os.path.join(base, name)
            if not os.path.isdir(folder):
                continue
            register_js = os.path.join(folder, "register.js")
            server_js = os.path.join(folder, "server.js")
            pkg_json = os.path.join(folder, "package.json")
            if not os.path.isfile(register_js):
                continue
            start_argv = None
            if os.path.isfile(server_js):
                start_argv = ["node", "server.js"]
            elif os.path.isfile(pkg_json):
                try:
                    with open(pkg_json, "r", encoding="utf-8") as f:
                        pkg = json.load(f)
                    scripts = (pkg.get("scripts") or {})
                    start_script = (scripts.get("start") or "").strip()
                    if start_script:
                        # "node server.js" -> ["node", "server.js"]; "npm run x" -> ["npm", "run", "x"]
                        parts = start_script.split()
                        if parts and parts[0] == "node" and len(parts) >= 2:
                            start_argv = parts
                        elif parts and parts[0] == "npm":
                            start_argv = ["npm", "start"]
                except Exception:
                    pass
            if not start_argv:
                continue
            out.append({
                "id": name,
                "cwd": folder,
                "start_argv": start_argv,
                "register_argv": ["node", "register.js"],
            })
        return out

    async def _wait_for_core_ready(self, base_url: str, timeout_sec: float = 60.0, interval_sec: float = 0.5) -> bool:
        """Poll GET {base_url}/ready until Core responds 200 or timeout. Uses /ready (lightweight) so DB/plugins don't delay readiness."""
        url = (base_url.rstrip("/") + "/ready")
        deadline = time.monotonic() + timeout_sec
        last_err = None
        logged_non200 = False
        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return True
                    last_err = f"status {r.status_code}"
                    # 503 = Core still initializing (expected). Log WARNING only for unexpected codes (e.g. 502).
                    if r.status_code != 503 and not logged_non200:
                        logged_non200 = True
                        try:
                            body_preview = (r.text or "")[:200]
                        except Exception:
                            body_preview = ""
                        logger.warning(
                            "system_plugins: GET {} returned {} (body: {}). If timeout, something else may be handling this URL.",
                            url, r.status_code, body_preview or "(empty)",
                        )
            except Exception as e:
                last_err = e
            await asyncio.sleep(interval_sec)
        if last_err is not None:
            logger.debug("system_plugins: last ready probe failed: {}", last_err)
        return False

    async def _run_system_plugins_startup(self) -> None:
        """Start each discovered system plugin (server process) then run register. Waits for Core to be ready first.
        Called via asyncio.create_task() so it runs in the background and does not block Core or the HTTP server.
        Each plugin runs in a separate OS process (node server.js)."""
        meta = Util().get_core_metadata()
        allowlist = getattr(meta, "system_plugins", None) or []
        candidates = self._discover_system_plugins()
        if not candidates:
            return
        to_start = [c for c in candidates if not allowlist or c["id"] in allowlist]
        if not to_start:
            return
        core_url = f"http://{meta.host}:{meta.port}"
        base_env = os.environ.copy()
        base_env["CORE_URL"] = core_url
        if getattr(meta, "auth_enabled", False) and getattr(meta, "auth_api_key", ""):
            base_env["CORE_API_KEY"] = getattr(meta, "auth_api_key", "")
        plugin_env_config = getattr(meta, "system_plugins_env", None) or {}
        # Give the HTTP server a moment to bind (avoids "Core did not become ready" on Windows where the task can poll before server.serve() is listening).
        await asyncio.sleep(2)
        # Wait for Core to be ready so registration succeeds (poll GET /ready until 200).
        # Use 127.0.0.1 for the probe when host is 0.0.0.0 so readiness works on Windows (connecting to 0.0.0.0 often fails there).
        ready_host = "127.0.0.1" if (getattr(meta, "host", None) or "").strip() in ("0.0.0.0", "") else meta.host
        ready_url = f"http://{ready_host}:{meta.port}"
        timeout_ready = max(30.0, float(getattr(meta, "system_plugins_ready_timeout", 90) or 90))
        ready = await self._wait_for_core_ready(ready_url, timeout_sec=timeout_ready)
        if not ready:
            logger.warning("system_plugins: Core did not become ready in time; starting plugins anyway.")
        else:
            _component_log("system_plugins", "Core ready, starting plugin(s)")
        for item in to_start:
            cwd = item["cwd"]
            start_argv = item["start_argv"]
            env = {**base_env}
            for k, v in plugin_env_config.get(item["id"], {}).items():
                env[k] = v
            try:
                proc = await asyncio.create_subprocess_exec(
                    start_argv[0],
                    *start_argv[1:],
                    cwd=cwd,
                    env=env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                self._system_plugin_processes.append(proc)
                _component_log("system_plugins", f"started {item['id']} (pid={proc.pid})")
            except Exception as e:
                logger.warning("system_plugins: failed to start {}: {}", item["id"], e)
        delay = max(0.5, float(getattr(meta, "system_plugins_start_delay", 2) or 2))
        await asyncio.sleep(delay)
        for item in to_start:
            env = {**base_env}
            for k, v in plugin_env_config.get(item["id"], {}).items():
                env[k] = v
            try:
                reg = await asyncio.create_subprocess_exec(
                    "node", "register.js",
                    cwd=item["cwd"],
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await reg.communicate()
                if reg.returncode == 0:
                    _component_log("system_plugins", f"registered {item['id']}")
                else:
                    logger.debug("system_plugins: register {} stderr: {}", item["id"], (stderr or b"").decode(errors="replace")[:500])
            except Exception as e:
                logger.debug("system_plugins: register {} failed: {}", item["id"], e)

    # try to reduce the misunderstanding. All the input tests in EmbeddingBase should be
    # in a list[str]. If you just want to embedding one string, ok, put into one list first.
    async def get_embedding(self, request: EmbeddingRequest)-> List[List[float]]:
        # Initialize the embedder, now it is using one existing llama_cpp server with local LLM model
        try:
            resolved = Util().embedding_llm()
            if not resolved or len(resolved) < 5:
                logger.error("Embedding LLM not configured.")
                return {}
            mtype = resolved[2] if len(resolved) > 2 else "local"
            host, port = resolved[3], resolved[4]
            sem = Util()._get_llm_semaphore(mtype)
            embedding_url = "http://" + host + ":" + str(port) + "/v1/embeddings"
            request_json = request.model_dump_json()
            async with sem:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        embedding_url,
                        headers={"accept": "application/json", "Content-Type": "application/json"},
                        data=request_json,
                    ) as response:
                        response_json = await response.json()
                        # Extract embeddings from the response; guard malformed response
                        if not isinstance(response_json, dict) or "data" not in response_json or not isinstance(response_json["data"], list):
                            return []
                        embeddings = [item["embedding"] for item in response_json["data"] if isinstance(item, dict) and "embedding" in item]
                        return embeddings
        except asyncio.CancelledError:
            logger.debug("Embedding request was cancelled.")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in embedding: {e}")
            return {}


    def initialize_vector_store(self, collection_name: str, client: Optional[chromadb.Client] = None,
                                host: Optional[str] = None, port: Optional[int] = None,
                                path: Optional[str] = None,):
        from memory.vector_store_factory import create_vector_store
        metadata = Util().get_core_metadata()
        vdb = metadata.vectorDB
        backend = getattr(vdb, "backend", "chroma") or "chroma"
        config = {
            "backend": backend,
            "Chroma": vars(vdb.Chroma),
            "Qdrant": vars(vdb.Qdrant),
            "Milvus": vars(vdb.Milvus),
            "Pinecone": vars(vdb.Pinecone),
            "Weaviate": vars(vdb.Weaviate),
        }
        chroma_client = None
        if backend == "chroma":
            if client is None:
                self.chromra_memory_client = self.start_chroma_client()
            else:
                self.chromra_memory_client = client
            chroma_client = self.chromra_memory_client
        self.vector_store = create_vector_store(
            backend=backend,
            config=config,
            collection_name=collection_name,
            chroma_client=chroma_client,
        )

    def _create_skills_vector_store(self):
        """Create a dedicated vector store for skills (separate collection from memory). Used when skills_use_vector_search."""
        from memory.vector_store_factory import create_vector_store
        meta = Util().get_core_metadata()
        if not getattr(meta, "skills_use_vector_search", False):
            return
        vdb = meta.vectorDB
        backend = getattr(vdb, "backend", "chroma") or "chroma"
        config = {
            "backend": backend,
            "Chroma": vars(vdb.Chroma),
            "Qdrant": vars(vdb.Qdrant),
            "Milvus": vars(vdb.Milvus),
            "Pinecone": vars(vdb.Pinecone),
            "Weaviate": vars(vdb.Weaviate),
        }
        chroma_client = getattr(self, "chromra_memory_client", None) if backend == "chroma" else None
        self.skills_vector_store = create_vector_store(
            backend=backend,
            config=config,
            collection_name=getattr(meta, "skills_vector_collection", "homeclaw_skills") or "homeclaw_skills",
            chroma_client=chroma_client,
        )

    def _create_plugins_vector_store(self):
        """Create a dedicated vector store for plugins (separate collection). Used when plugins_use_vector_search."""
        from memory.vector_store_factory import create_vector_store
        meta = Util().get_core_metadata()
        if not getattr(meta, "plugins_use_vector_search", False):
            return
        vdb = meta.vectorDB
        backend = getattr(vdb, "backend", "chroma") or "chroma"
        config = {
            "backend": backend,
            "Chroma": vars(vdb.Chroma),
            "Qdrant": vars(vdb.Qdrant),
            "Milvus": vars(vdb.Milvus),
            "Pinecone": vars(vdb.Pinecone),
            "Weaviate": vars(vdb.Weaviate),
        }
        chroma_client = getattr(self, "chromra_memory_client", None) if backend == "chroma" else None
        self.plugins_vector_store = create_vector_store(
            backend=backend,
            config=config,
            collection_name=getattr(meta, "plugins_vector_collection", "homeclaw_plugins") or "homeclaw_plugins",
            chroma_client=chroma_client,
        )

    def _create_agent_memory_vector_store(self):
        """Create vector store for AGENT_MEMORY + daily memory when use_agent_memory_search. Never raises; on failure sets agent_memory_vector_store to None."""
        meta = Util().get_core_metadata()
        if not getattr(meta, "use_agent_memory_search", True):
            return
        try:
            from memory.vector_store_factory import create_vector_store
            vdb = getattr(meta, "vectorDB", None)
            if vdb is None:
                logger.warning("Agent memory vector store: vectorDB not configured; skipping.")
                return
            backend = getattr(vdb, "backend", "chroma") or "chroma"
            config = {
                "backend": backend,
                "Chroma": vars(getattr(vdb, "Chroma", None) or {}),
                "Qdrant": vars(getattr(vdb, "Qdrant", None) or {}),
                "Milvus": vars(getattr(vdb, "Milvus", None) or {}),
                "Pinecone": vars(getattr(vdb, "Pinecone", None) or {}),
                "Weaviate": vars(getattr(vdb, "Weaviate", None) or {}),
            }
            chroma_client = getattr(self, "chromra_memory_client", None) if backend == "chroma" else None
            self.agent_memory_vector_store = create_vector_store(
                backend=backend,
                config=config,
                collection_name=getattr(meta, "agent_memory_vector_collection", "homeclaw_agent_memory") or "homeclaw_agent_memory",
                chroma_client=chroma_client,
            )
        except Exception as e:
            logger.warning("Agent memory vector store not created: {}", e, exc_info=False)
            self.agent_memory_vector_store = None

    def _create_knowledge_base(self):
        """Create user knowledge base. Backend follows knowledge_base.backend (auto = memory_backend): cognee or chroma (built-in RAG). Never raises."""
        try:
            meta = Util().get_core_metadata()
            kb_cfg = getattr(meta, "knowledge_base", None) or {}
            if not kb_cfg.get("enabled"):
                return
            # Backend: explicit (cognee | chroma) or "auto" = same as memory_backend
            kb_backend = (kb_cfg.get("backend") or "auto").strip().lower()
            if kb_backend == "auto":
                kb_backend = (getattr(meta, "memory_backend", None) or "cognee").strip().lower()
            if kb_backend == "cognee":
                self._create_knowledge_base_cognee(meta, kb_cfg)
                return
            # Built-in RAG (chroma / vectorDB)
            from memory.vector_store_factory import create_vector_store
            from memory.knowledge_base import KnowledgeBase
            vdb = getattr(meta, "vectorDB", None)
            if not vdb:
                logger.warning("Knowledge base (chroma) enabled but vectorDB not configured; skipping.")
                return
            backend = getattr(vdb, "backend", "chroma") or "chroma"
            config = {
                "backend": backend,
                "Chroma": vars(getattr(vdb, "Chroma", {})),
                "Qdrant": vars(getattr(vdb, "Qdrant", {})),
                "Milvus": vars(getattr(vdb, "Milvus", {})),
                "Pinecone": vars(getattr(vdb, "Pinecone", {})),
                "Weaviate": vars(getattr(vdb, "Weaviate", {})),
            }
            chroma_client = getattr(self, "chromra_memory_client", None) if backend == "chroma" else None
            kb_store = create_vector_store(
                backend=backend,
                config=config,
                collection_name=(kb_cfg.get("collection_name") or "homeclaw_kb").strip(),
                chroma_client=chroma_client,
            )
            self.knowledge_base = KnowledgeBase(
                vector_store=kb_store,
                embed_fn=self.embedder,
                config={
                    "chunk_size": int(kb_cfg.get("chunk_size", 800) or 800),
                    "chunk_overlap": int(kb_cfg.get("chunk_overlap", 100) or 100),
                    "unused_ttl_days": float(kb_cfg.get("unused_ttl_days", 30) or 30),
                    "embed_timeout": float(kb_cfg.get("embed_timeout", 30) or 30),
                    "store_timeout": float(kb_cfg.get("store_timeout", 15) or 15),
                    "score_is_distance": True,  # Chroma returns distance; we normalize to similarity in search()
                },
            )
            logger.debug("Knowledge base initialized (built-in RAG, collection={})", kb_cfg.get("collection_name") or "homeclaw_kb")
        except Exception as e:
            logger.warning("Knowledge base not initialized: {}", e)
            self.knowledge_base = None

    def _create_knowledge_base_cognee(self, meta, kb_cfg):
        """Create knowledge base using Cognee (same DB/vector as memory when memory_backend is cognee). Never raises."""
        try:
            from memory.cognee_knowledge_base import CogneeKnowledgeBase
            cognee_config = dict(getattr(meta, "cognee", None) or {})
            # Reuse same LLM/embedding auto-fill as Cognee memory so KB uses same endpoints
            if not (cognee_config.get("llm") or {}).get("endpoint"):
                resolved = Util().main_llm()
                if resolved:
                    _path, _model_id, mtype, host, port = resolved
                    if mtype == "litellm":
                        model = _path
                        provider = "openai"
                    else:
                        model_id = (_model_id or "local").strip() or "local"
                        model = f"openai/{model_id}"
                        provider = "openai"
                    cognee_config.setdefault("llm", {})
                    cognee_config["llm"].update({
                        "provider": (cognee_config["llm"].get("provider") or provider).strip() or provider,
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (cognee_config["llm"].get("model") or model).strip() or model,
                        "api_key": (getattr(meta, "main_llm_api_key", "") or "").strip() or "local",
                    })
            if not (cognee_config.get("embedding") or {}).get("endpoint"):
                resolved = Util().embedding_llm()
                if resolved:
                    _path, _model_id, mtype, host, port = resolved
                    if mtype == "litellm":
                        model = _path
                        provider = "openai"
                    else:
                        model_id = (_model_id or "local").strip() or "local"
                        model = f"openai/{model_id}"
                        provider = "openai"
                    cognee_config.setdefault("embedding", {})
                    cognee_config["embedding"].update({
                        "provider": (cognee_config["embedding"].get("provider") or provider).strip() or provider,
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (cognee_config["embedding"].get("model") or model).strip() or model,
                        "api_key": (getattr(meta, "main_llm_api_key", "") or "").strip() or "local",
                    })
            self.knowledge_base = CogneeKnowledgeBase(
                config=cognee_config if cognee_config else None,
                kb_config={
                    "unused_ttl_days": float(kb_cfg.get("unused_ttl_days", 30) or 30),
                    "max_sources_per_user": int(kb_cfg.get("max_sources_per_user", 0) or 0),
                },
            )
            logger.debug("Knowledge base initialized (Cognee backend)")
        except Exception as e:
            logger.exception("Knowledge base (Cognee) not initialized: {}", e)
            self.knowledge_base = None

    def initialize(self):
        logger.debug("core initializing...")
        self.initialize_vector_store(collection_name="memory")
        logger.debug("core init: vector_store done")
        self.embedder = LlamaCppEmbedding()
        logger.debug("core init: embedder done")
        meta = Util().get_core_metadata()
        self._create_skills_vector_store()
        self._create_plugins_vector_store()
        self._create_agent_memory_vector_store()
        logger.debug("core init: skills/plugins/agent_memory vector stores done")
        self.knowledge_base = None
        self._create_knowledge_base()
        logger.debug("core init: knowledge_base done")
        memory_backend = (getattr(meta, "memory_backend", None) or "cognee").strip().lower()

        if memory_backend == "cognee" and Util().has_memory():
            try:
                logger.debug("core init: creating Cognee memory (LLM/embedding must be reachable)...")
                from memory.cognee_adapter import CogneeMemory
                cognee_config = dict(getattr(meta, "cognee", None) or {})
                # If cognee.llm / cognee.embedding endpoints are not set, use same resolved LLM/embedding as Core and chroma memory (OpenAI-compatible: base URL http://host:port/v1)
                llm_cfg = cognee_config.get("llm") or {}
                if not isinstance(llm_cfg, dict):
                    llm_cfg = {}
                if not (llm_cfg.get("endpoint") or llm_cfg.get("model")):
                    resolved = Util().main_llm()
                    if resolved:
                        _path, _model_id, mtype, host, port = resolved
                        # LiteLLM (used by Cognee) requires model with provider prefix, e.g. openai/model_name; local = OpenAI-compatible
                        if mtype == "litellm":
                            model = _path
                            provider = (llm_cfg.get("provider") or "openai").strip() or "openai"
                        else:
                            model_id = (_model_id or "local").strip() or "local"
                            model = f"openai/{model_id}"
                            provider = "openai"
                        cognee_config["llm"] = {
                            **llm_cfg,
                            "provider": (llm_cfg.get("provider") or provider).strip() or provider,
                            "endpoint": f"http://{host}:{port}/v1",
                            "model": (llm_cfg.get("model") or model).strip() or model,
                        }
                        cognee_config["llm"]["api_key"] = (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                    else:
                        host = getattr(meta, "main_llm_host", "127.0.0.1") or "127.0.0.1"
                        port = getattr(meta, "main_llm_port", 5088) or 5088
                        main_llm_ref = (getattr(meta, "main_llm", "") or "").strip()
                        model_id = main_llm_ref.split("/")[-1] if "/" in main_llm_ref else (main_llm_ref or "local")
                        if not model_id:
                            model_id = "local"
                        model = f"openai/{model_id}"
                        cognee_config["llm"] = {
                            **llm_cfg,
                            "provider": (llm_cfg.get("provider") or "openai").strip() or "openai",
                            "endpoint": f"http://{host}:{port}/v1",
                            "model": (llm_cfg.get("model") or model).strip() or model,
                        }
                        cognee_config["llm"]["api_key"] = (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                emb_cfg = cognee_config.get("embedding") or {}
                if not isinstance(emb_cfg, dict):
                    emb_cfg = {}
                if not (emb_cfg.get("endpoint") or emb_cfg.get("model")):
                    resolved = Util().embedding_llm()
                    if resolved:
                        _path, _model_id, mtype, host, port = resolved
                        if mtype == "litellm":
                            model = _path
                            provider = (emb_cfg.get("provider") or "openai").strip() or "openai"
                        else:
                            model_id = (_model_id or "local").strip() or "local"
                            model = f"openai/{model_id}"
                            provider = "openai"
                        cognee_config["embedding"] = {
                            **emb_cfg,
                            "provider": (emb_cfg.get("provider") or provider).strip() or provider,
                            "endpoint": f"http://{host}:{port}/v1",
                            "model": (emb_cfg.get("model") or model).strip() or model,
                        }
                        cognee_config["embedding"]["api_key"] = (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                    else:
                        host = getattr(meta, "embedding_host", "127.0.0.1") or "127.0.0.1"
                        port = getattr(meta, "embedding_port", 5066) or 5066
                        emb_ref = (getattr(meta, "embedding_llm", "") or "").strip()
                        model_id = emb_ref.split("/")[-1] if "/" in emb_ref else (emb_ref or "local")
                        if not model_id:
                            model_id = "local"
                        model = f"openai/{model_id}"
                        cognee_config["embedding"] = {
                            **emb_cfg,
                            "provider": (emb_cfg.get("provider") or "openai").strip() or "openai",
                            "endpoint": f"http://{host}:{port}/v1",
                            "model": (emb_cfg.get("model") or model).strip() or model,
                        }
                        cognee_config["embedding"]["api_key"] = (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                self.mem_instance = CogneeMemory(config=cognee_config if cognee_config else None)
                logger.debug("core init: Cognee memory done")
            except ImportError as e:
                logger.warning("Cognee backend requested but cognee not installed: {}. Using chroma.", e)
                memory_backend = "chroma"
            except Exception as e:
                logger.warning("Cognee backend failed: {}. Using chroma.", e)
                memory_backend = "chroma"

        if memory_backend != "cognee":
            graph_store = None
            if Util().has_memory():
                try:
                    from memory.graph import get_graph_store
                    gdb = getattr(meta, "graphDB", None)
                    if gdb:
                        graph_store = get_graph_store(
                            backend=getattr(gdb, "backend", "kuzu"),
                            path=getattr(gdb.Kuzu, "path", "") or "",
                            neo4j_url=getattr(gdb.Neo4j, "url", "") or "",
                            neo4j_username=getattr(gdb.Neo4j, "username", "") or "",
                            neo4j_password=getattr(gdb.Neo4j, "password", "") or "",
                        )
                except Exception as e:
                    logger.debug("Graph store not initialized: {}", e)
            if not getattr(self, "mem_instance", None):
                self.mem_instance = Memory(
                    embedding_model=self.embedder,
                    vector_store=self.vector_store,
                    llm=LlamaCppLLM(),
                    graph_store=graph_store,
                )
        logger.debug("core init: memory backend done")

        self.request_queue_task = asyncio.create_task(self.process_request_queue())
        self.response_queue_task = asyncio.create_task(self.process_response_queue())
        self.memory_queue_task = asyncio.create_task(self.process_memory_queue())
        self.memory_summarization_scheduler_task = asyncio.create_task(self.process_memory_summarization_scheduler())
        self.kb_folder_sync_task = asyncio.create_task(self._process_kb_folder_sync_scheduler())

        # Register built-in tools (sessions_transcript, etc.); used when use_tools is True
        register_builtin_tools(get_tool_registry())
        if getattr(self, "orchestrator_unified_with_tools", True):
            register_routing_tools(get_tool_registry(), self)

        # Orchestrator + TAM + plugins always enabled; routing via tools (unified) or separate handler (non-unified)
        self.plugin_manager: PluginManager = PluginManager(self)

        @self.app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError):
            logger.error(f"Validation error: {exc} for request: {await request.body()}")
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors(), "body": exc.body},
            )

        # Lifecycle routes (from core.routes.lifecycle)
        self.app.add_api_route("/register_channel", lifecycle.get_register_channel_handler(self), methods=["POST"])
        self.app.add_api_route("/deregister_channel", lifecycle.get_deregister_channel_handler(self), methods=["POST"])
        self.app.add_api_route("/ready", lifecycle.get_ready_handler(self), methods=["GET"])
        self.app.add_api_route("/pinggy", lifecycle.get_pinggy_handler(self, lambda: _pinggy_state), methods=["GET"], response_class=HTMLResponse)
        self.app.add_api_route("/shutdown", lifecycle.get_shutdown_handler(self), methods=["GET"])
        self.app.add_api_route("/inbound/result", inbound_routes.get_inbound_result_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/config/core", config_api.get_api_config_core_get_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/config/core", config_api.get_api_config_core_patch_handler(self), methods=["PATCH"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/config/users", config_api.get_api_config_users_get_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/config/users", config_api.get_api_config_users_post_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/config/users/{user_name}", config_api.get_api_config_users_patch_handler(self), methods=["PATCH"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/config/users/{user_name}", config_api.get_api_config_users_delete_handler(self), methods=["DELETE"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/files/out", files.get_files_out_handler(self), methods=["GET"])
        self.app.add_api_route("/api/sandbox/list", files.get_api_sandbox_list_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/upload", files.get_api_upload_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/memory/summarize", memory_routes.get_memory_summarize_handler(self), methods=["POST"])
        self.app.add_api_route("/memory/reset", memory_routes.get_memory_reset_handler(self), methods=["GET", "POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/knowledge_base/reset", knowledge_base_routes.get_knowledge_base_reset_handler(self), methods=["GET", "POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/knowledge_base/folder_sync_config", knowledge_base_routes.get_knowledge_base_folder_sync_config_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/knowledge_base/sync_folder", knowledge_base_routes.get_knowledge_base_sync_folder_handler(self), methods=["GET", "POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        # Plugin API
        self.app.add_api_route("/api/plugins/register", plugins_api.get_api_plugins_register_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/plugins/unregister", plugins_api.get_api_plugins_unregister_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/plugins/unregister-all", plugins_api.get_api_plugins_unregister_all_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/plugins/health/{plugin_id}", plugins_api.get_api_plugins_health_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/plugins/llm/generate", plugins_api.get_api_plugins_llm_generate_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/plugins/memory/add", plugins_api.get_api_plugins_memory_add_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/plugins/memory/search", plugins_api.get_api_plugins_memory_search_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/plugin-ui", plugins_api.get_api_plugin_ui_list_handler(self), methods=["GET"])
        # Misc API
        self.app.add_api_route("/api/skills/clear-vector-store", misc_api.get_api_skills_clear_vector_store_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/testing/clear-all", misc_api.get_api_testing_clear_all_handler(self), methods=["POST"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/sessions", misc_api.get_api_sessions_list_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])
        self.app.add_api_route("/api/reports/usage", misc_api.get_api_reports_usage_handler(self), methods=["GET"], dependencies=[Depends(auth.verify_inbound_auth)])
        # UI and WebSocket
        self.app.add_api_route("/ui", ui_routes.get_ui_launcher_handler(self), methods=["GET"])
        self.app.add_websocket_route("/ws", websocket_routes.get_websocket_handler(self))

        @self.app.post("/process")
        async def process_request(request: PromptRequest):
            try:
                user_name: str = request.user_name
                user_id: str = request.user_id
                channel_type: ChannelType = request.channelType
                content_type: ContentType = request.contentType
                channel_name: str = getattr(request, "channel_name", "?")
                logger.info(f"Core: received /process from channel={channel_name} user={user_id} type={content_type}")
                logger.debug(f"Received request from channel: {user_name}, {user_id}, {channel_type}, {content_type}")
                user: User = None
                has_permission, user = self.check_permission(user_name, user_id, channel_type, content_type)
                if not has_permission or user is None:
                    # Optional: notify owner via last-used channel so they can add this identity to user.yml (do not update last channel so owner gets the notification)
                    try:
                        meta = Util().get_core_metadata()
                        if getattr(meta, "notify_unknown_request", False):
                            from base.last_channel import get_last_channel
                            last = get_last_channel()
                            if last and getattr(self, "response_queue", None):
                                ch_name = last.get("channel_name") or "?"
                                msg = (
                                    f"Unknown request from channel={channel_name} user_id={user_id}. "
                                    "Add this identity to config/user.yml (under im, email, or phone) to allow access."
                                )
                                try:
                                    port = int(last.get("port") or 0)
                                except (TypeError, ValueError):
                                    port = 0
                                async_resp = AsyncResponse(
                                    request_id=last.get("request_id") or "",
                                    request_metadata=last.get("request_metadata") or {},
                                    host=last.get("host") or "",
                                    port=port,
                                    from_channel=ch_name,
                                    response_data={"text": self._format_outbound_text(msg), "format": "plain"},
                                )
                                await self.response_queue.put(async_resp)
                    except Exception as notify_e:
                        logger.debug("notify_unknown_request failed: {}", notify_e)
                    return Response(content="Permission denied", status_code=401)

                if request is not None:
                    self.latestPromptRequest = copy.deepcopy(request)
                    logger.debug(f'latestPromptRequest set to: {self.latestPromptRequest}')
                    self._persist_last_channel(request)
                if len(user.name) > 0:
                    request.user_name = user.name
                request.system_user_id = user.id or user.name

                await self.request_queue.put(request)

                return Response(content="Request received", status_code=200)
            except Exception as e:
                logger.exception(e)
                return Response(content="Server Internal Error", status_code=500)


        @self.app.post("/local_chat")
        async def process_request(request: PromptRequest):
            try:
                user_name: str = request.user_name
                user_id: str = request.user_id
                channel_type: ChannelType = request.channelType
                content_type: ContentType = request.contentType
                logger.debug(f"Received request from channel: {user_name}, {user_id}, {channel_type}, {content_type}")
                user: User = None
                has_permission, user = self.check_permission(user_name, user_id, channel_type, content_type)
                if not has_permission or user is None:
                    return Response(content="Permission denied", status_code=401)

                if len(user.name) > 0:
                    request.user_name = user.name
                request.system_user_id = user.id or user.name

                self.latestPromptRequest = copy.deepcopy(request)
                logger.debug(f'latestPromptRequest set to: {self.latestPromptRequest}')
                self._persist_last_channel(request)

                if not getattr(self, "orchestrator_unified_with_tools", True):
                    flag = await self.orchestrator_handler(request)
                    if flag:
                        logger.debug(f"Orchestrator and plugin handled the request")
                        return Response(content="Orchestrator and plugin handled the request", status_code=200)

                resp_text = await self.process_text_message(request)
                if resp_text is None:
                    return Response(content="Response is None", status_code=200)
                if resp_text == ROUTING_RESPONSE_ALREADY_SENT:
                    return Response(content="Handled by routing (TAM or plugin).", status_code=200)

                return Response(content=resp_text, status_code=200)
            except Exception as e:
                logger.exception(e)
                return Response(content="Server Internal Error", status_code=500)

        @self.app.post("/inbound")
        async def inbound_post_handler(request: InboundRequest, _: None = Depends(auth.verify_inbound_auth)):
            """
            Minimal API for any bot: POST {"user_id": "...", "text": "..."} and get {"text": "..."} back.
            No channel process needed; add user_id to config/user.yml allowlist. Use channel_name to tag the source (e.g. telegram, discord).
            When auth_enabled and auth_api_key are set in config, require X-API-Key or Authorization: Bearer.
            Optional stream: true — returns Server-Sent Events (text/event-stream): progress messages during long tasks (e.g. "Generating your presentation…") then a final event with event "done" and the result (same shape as non-stream). Use stream: true for long requests (e.g. HTML slides, document_read) to avoid "Connection closed while receiving data" from client/proxy timeouts.
            Optional async: true — returns immediately with 202 and request_id; Core processes in background. Poll GET /inbound/result?request_id=... until status is "done". Use when proxy (e.g. Cloudflare) closes the connection before the response completes; each poll is a short request so it won't time out.
            Long requests (e.g. 2+ minutes): set proxy read_timeout and client timeout >= 300s, or use stream: true (with heartbeat), or async: true + poll.
            """
            try:
                if getattr(request, "async_mode", False):
                    request_id = str(uuid.uuid4())
                    self._inbound_async_results[request_id] = {"status": "pending", "created_at": time.time()}
                    asyncio.create_task(self._run_async_inbound(request_id, request))
                    return JSONResponse(
                        status_code=202,
                        content={"request_id": request_id, "status": "accepted", "message": "Processing in background. Poll GET /inbound/result?request_id=" + request_id},
                    )
                if getattr(request, "stream", False):
                    progress_queue = asyncio.Queue()
                    try:
                        progress_queue.put_nowait({"event": "progress", "message": "Processing your request…", "tool": ""})
                    except Exception:
                        pass
                    task = asyncio.create_task(self._handle_inbound_request_impl(request, progress_queue=progress_queue))
                    return StreamingResponse(
                        self._inbound_sse_generator(progress_queue, task),
                        media_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
                    )
                ok, text, status, image_paths = await self._handle_inbound_request(request)
                if not ok:
                    return JSONResponse(status_code=status, content={"error": text, "text": ""})
                out_text, out_fmt = self._outbound_text_and_format(text) if text else ("", "plain")
                content = {"text": out_text, "format": out_fmt}
                # Images: send directly as data URLs (companion/channel display inline). File/folder: shown via link (format "link").
                # Last-resort: if response text contains "Image saved: <path>" but we have no image_paths, parse it
                if not image_paths and text and ("Image saved:" in text or "HOMECLAW_IMAGE_PATH=" in text):
                    import re as _re
                    for pattern in (r"Image saved:\s*(.+)", r"HOMECLAW_IMAGE_PATH=(.+)"):
                        m = _re.search(pattern, text, _re.IGNORECASE)
                        if m:
                            p = m.group(1).strip().split("\n")[0].strip()
                            if p:
                                try:
                                    resolved = Path(p).resolve()
                                    if resolved.is_file():
                                        image_paths = [str(resolved)]
                                        break
                                except (OSError, RuntimeError):
                                    pass
                # Any output that includes images: include as data URLs so companion/remote clients can display
                if image_paths:
                    data_urls = []
                    for image_path in image_paths:
                        if not isinstance(image_path, str) or not os.path.isfile(image_path):
                            continue
                        try:
                            with open(image_path, "rb") as f:
                                b64 = __import__("base64").b64encode(f.read()).decode("ascii")
                            ext = (image_path.lower().split(".")[-1] if "." in image_path else "png") or "png"
                            mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext)
                            if mime == "image/jpg":
                                mime = "image/jpeg"
                            data_urls.append(f"data:{mime};base64,{b64}")
                        except Exception as e:
                            logger.debug("inbound: could not attach image as data URL: {}", e)
                    if data_urls:
                        content["images"] = data_urls
                        content["image"] = data_urls[0]
                return JSONResponse(content=content)
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"error": str(e), "text": ""})

        logger.debug("core initialized and all the endpoints are registered!")


    async def _handle_inbound_request(self, request: InboundRequest, progress_queue: Optional[asyncio.Queue] = None) -> Tuple[bool, str, int, Optional[List[str]]]:
        """Shared logic for POST /inbound and WebSocket /ws. Returns (success, text_or_error, status_code, image_paths_or_none). When progress_queue is set (stream=true), progress messages are put on the queue during long-running tools."""
        try:
            return await self._handle_inbound_request_impl(request, progress_queue=progress_queue)
        except Exception as e:
            logger.exception(e)
            msg = (str(e) or "Internal error").strip()[:500]
            return False, msg or "Internal error", 500, None

    async def _run_async_inbound(self, request_id: str, request: InboundRequest) -> None:
        """Background task for async /inbound: run the request and store result for GET /inbound/result. Same response shape as sync /inbound."""
        try:
            ok, text, status, image_paths = await self._handle_inbound_request(request)
            try:
                out_text, out_fmt = self._outbound_text_and_format(text) if text else ("", "plain")
            except Exception:
                out_text, out_fmt = (str(text)[:50000] if text else "", "plain")
            data_urls = []
            if image_paths:
                for image_path in image_paths:
                    if not isinstance(image_path, str) or not os.path.isfile(image_path):
                        continue
                    try:
                        with open(image_path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("ascii")
                        ext = (image_path.lower().split(".")[-1] if "." in image_path else "png") or "png"
                        mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext)
                        if mime == "image/jpg":
                            mime = "image/jpeg"
                        data_urls.append(f"data:{mime};base64,{b64}")
                    except Exception:
                        pass
            entry = {"status": "done", "ok": ok, "text": out_text, "format": out_fmt, "created_at": time.time()}
            if not ok:
                entry["error"] = (text or "")[:2000]
            if data_urls:
                entry["images"] = data_urls
                entry["image"] = data_urls[0]
            self._inbound_async_results[request_id] = entry
        except Exception as e:
            logger.exception(e)
            self._inbound_async_results[request_id] = {
                "status": "done",
                "ok": False,
                "text": "",
                "format": "plain",
                "error": (str(e) or "Internal error")[:2000],
                "created_at": time.time(),
            }
        # If client passed push_ws_session_id, push the result to that WebSocket so Companion gets it without polling.
        try:
            push_sid = getattr(request, "push_ws_session_id", None)
            if isinstance(push_sid, str) and push_sid.strip():
                ws = self._ws_sessions.get(push_sid.strip())
                if ws is not None:
                    entry = self._inbound_async_results.get(request_id)
                    if entry and entry.get("status") == "done":
                        push_payload = {"event": "inbound_result", "request_id": request_id, "status": "done", "text": entry.get("text", ""), "format": entry.get("format", "plain"), "ok": entry.get("ok", True)}
                        if entry.get("error"):
                            push_payload["error"] = entry["error"]
                        imgs = entry.get("images") or []
                        if imgs:
                            push_payload["images"] = imgs
                            push_payload["image"] = imgs[0] if imgs else None
                        try:
                            await ws.send_json(push_payload)
                        except Exception as push_err:
                            logger.debug("Push to WebSocket session {} failed: {}", (push_sid or "")[:8], push_err)
        except Exception as e:
            logger.debug("push_ws_session_id delivery failed: {}", e)

    async def _handle_inbound_request_impl(self, request: InboundRequest, progress_queue: Optional[asyncio.Queue] = None) -> Tuple[bool, str, int, Optional[List[str]]]:
        """Implementation of _handle_inbound_request. Do not call directly; use _handle_inbound_request for crash-safe handling. When progress_queue is set, progress events are put on it during long-running tools so stream=true clients can show status."""
        from datetime import datetime
        req_id = str(datetime.now().timestamp())
        user_name = request.user_name or request.user_id
        images_list = list(request.images) if getattr(request, "images", None) else []
        videos_list = list(request.videos) if getattr(request, "videos", None) else []
        audios_list = list(request.audios) if getattr(request, "audios", None) else []
        files_list = list(request.files) if getattr(request, "files", None) else []
        # Treat image data URLs in files as images (e.g. webchat sends as "files" when file.type is generic).
        # Accept "data:image/..." and "data: image/..." (some browsers add a space).
        # Non-image items stay in files_list and are handled by file-understanding in process_text_message (video/audio → media parts; documents → document_read notice).
        if files_list:
            remaining_files = []
            for f in files_list:
                if isinstance(f, str):
                    s = f.strip().lower().replace("data: ", "data:", 1)
                    if s.startswith("data:image/"):
                        images_list.append(f.strip())
                        continue
                remaining_files.append(f)
            files_list = remaining_files
        if images_list:
            logger.info("Inbound request has {} image(s) (from images + image data URLs moved from files)", len(images_list))
        if videos_list:
            content_type_for_perm = ContentType.VIDEO
        elif audios_list:
            content_type_for_perm = ContentType.AUDIO
        elif images_list:
            content_type_for_perm = ContentType.TEXTWITHIMAGE
        else:
            content_type_for_perm = ContentType.TEXT
        request_metadata = {"user_id": request.user_id, "channel": request.channel_name}
        if getattr(request, "session_id", None):
            request_metadata["session_id"] = request.session_id
        if getattr(request, "conversation_type", None):
            request_metadata["conversation_type"] = request.conversation_type
        loc = getattr(request, "location", None)
        if isinstance(loc, str) and loc.strip():
            request_metadata["location"] = loc.strip()[:2000]
        # Memory/Cognee scope: user_id and app_id; companion often omits app_id, so default to homeclaw
        inbound_user_id = (getattr(request, "user_id", None) or "").strip() or "companion"
        inbound_app_id = getattr(request, "app_id", None) or "homeclaw"
        pr = PromptRequest(
            request_id=req_id,
            channel_name=request.channel_name or "webhook",
            request_metadata=request_metadata,
            channelType=ChannelType.IM,
            user_name=user_name,
            app_id=inbound_app_id,
            user_id=inbound_user_id,
            contentType=content_type_for_perm,
            text=request.text,
            action=request.action or "respond",
            host="inbound",
            port=0,
            images=images_list,
            videos=videos_list,
            audios=audios_list,
            files=files_list if files_list else None,
            timestamp=datetime.now().timestamp(),
        )
        has_permission, user = self.check_permission(pr.user_name, pr.user_id, ChannelType.IM, content_type_for_perm)
        if not has_permission or user is None:
            return False, "Permission denied", 401, None
        if user and len(user.name) > 0:
            pr.user_name = user.name
        if user:
            pr.system_user_id = user.id or user.name
        # Store latest location when client sends it (Companion, WebChat, browser). When app did not combine (system/companion), store under shared key so it can be used for all users.
        # If location is lat/lng (from mobile), convert to address (country, city, street) for display and plugins.
        try:
            loc_in = request_metadata.get("location") or getattr(request, "location", None)
            if loc_in is not None:
                display_loc, lat_lng_str = self._normalize_location_to_address(loc_in)
                if display_loc:
                    sid = (inbound_user_id or "").strip().lower()
                    if sid in ("system", "companion"):
                        self._set_latest_location(getattr(self, "_LATEST_LOCATION_SHARED_KEY", "companion"), display_loc, lat_lng_str=lat_lng_str)
                    elif getattr(pr, "system_user_id", None):
                        self._set_latest_location(pr.system_user_id, display_loc, lat_lng_str=lat_lng_str)
        except Exception as e:
            logger.debug("Store latest location on inbound: {}", e)
        if progress_queue is not None:
            pr.request_metadata["progress_queue"] = progress_queue
        self.latestPromptRequest = copy.deepcopy(pr)
        self._persist_last_channel(pr)
        # All users (normal + companion type) use the same main flow: tools, memory, chat, sandbox per user. No Friends plugin; list all users and chat with each separately. See docs_design/CompanionFeatureDesign.md.
        if not getattr(self, "orchestrator_unified_with_tools", True):
            flag = await self.orchestrator_handler(pr)
            if flag:
                return True, "Orchestrator and plugin handled the request", 200, None
        resp_text = await self.process_text_message(pr)
        if resp_text is None:
            return True, "", 200, None
        if resp_text == ROUTING_RESPONSE_ALREADY_SENT:
            return True, "Handled by routing (TAM or plugin).", 200, None
        img_paths = (pr.request_metadata or {}).get("response_image_paths")
        if not isinstance(img_paths, list):
            single = (pr.request_metadata or {}).get("response_image_path")
            img_paths = [single] if single and isinstance(single, str) else None
        # Fallback: run_skill stores paths on Core by request_id so companion gets image even if request_metadata didn't persist
        if not img_paths and getattr(self, "_response_image_paths_by_request_id", None):
            img_paths = self._response_image_paths_by_request_id.pop(pr.request_id, None)
        return True, resp_text, 200, img_paths

    async def _inbound_sse_generator(self, progress_queue: asyncio.Queue, task: asyncio.Task) -> Any:
        """Yield Server-Sent Events: progress messages from the queue, then a final 'done' event with the result (same shape as non-stream /inbound). Used when POST /inbound has stream=true. Sends a heartbeat (comment or progress) every 40s so proxies (e.g. Cloudflare) do not close the connection. Never raises; on any error yields a 'done' event with ok=False."""
        _INBOUND_SSE_HEARTBEAT_INTERVAL = 40.0  # seconds; send something so proxy read timeout does not close the connection
        def _yield_done(ok: bool, text: str = "", error: str = "", status: int = 200, data_urls: Optional[List[str]] = None) -> str:
            """Build and return one SSE line for event 'done'. Never raises."""
            payload = {"event": "done", "ok": ok, "text": (text or "")[:50000], "format": "plain", "status": status}
            if error:
                payload["error"] = (error or "")[:2000]
            if data_urls:
                payload["images"] = data_urls
                payload["image"] = data_urls[0] if data_urls else None
            try:
                return f"data: {json.dumps(payload)}\n\n"
            except Exception:
                return f"data: {json.dumps({'event': 'done', 'ok': False, 'error': 'Serialization error', 'text': ''})}\n\n"

        last_yield_time = time.time()
        try:
            while not task.done():
                try:
                    msg = await asyncio.wait_for(progress_queue.get(), timeout=0.4)
                    if isinstance(msg, dict):
                        try:
                            out = f"data: {json.dumps(msg)}\n\n"
                            yield out
                            last_yield_time = time.time()
                        except Exception:
                            pass
                except asyncio.TimeoutError:
                    if time.time() - last_yield_time >= _INBOUND_SSE_HEARTBEAT_INTERVAL:
                        try:
                            yield f"data: {json.dumps({'event': 'progress', 'message': 'Still working…', 'tool': ''})}\n\n"
                            last_yield_time = time.time()
                        except Exception:
                            yield ": heartbeat\n\n"
                            last_yield_time = time.time()
                    continue
                except Exception:
                    continue
            try:
                ok, text, status, image_paths = task.result()
            except Exception as e:
                logger.exception("inbound stream task failed: {}", e)
                yield _yield_done(ok=False, error=str(e)[:2000])
                return
            try:
                out_text, out_fmt = self._outbound_text_and_format(text) if text else ("", "plain")
            except Exception as e:
                logger.debug("inbound SSE outbound_text_and_format: {}", e)
                out_text, out_fmt = (str(text)[:50000] if text else "", "plain")
            content = {"event": "done", "ok": ok, "text": out_text, "format": out_fmt, "status": status}
            if not ok:
                content["error"] = (text or "")[:2000]
            data_urls = []
            if image_paths:
                for image_path in image_paths:
                    if not isinstance(image_path, str) or not os.path.isfile(image_path):
                        continue
                    try:
                        with open(image_path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("ascii")
                        ext = (image_path.lower().split(".")[-1] if "." in image_path else "png") or "png"
                        mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext)
                        if mime == "image/jpeg":
                            pass
                        elif mime == "image/jpg":
                            mime = "image/jpeg"
                        data_urls.append(f"data:{mime};base64,{b64}")
                    except Exception:
                        pass
            if data_urls:
                content["images"] = data_urls
                content["image"] = data_urls[0]
            try:
                yield f"data: {json.dumps(content)}\n\n"
            except Exception:
                yield _yield_done(ok=ok, text=out_text, error=content.get("error", ""), status=status, data_urls=data_urls if data_urls else None)
        except Exception as e:
            logger.exception("inbound SSE generator: {}", e)
            try:
                yield _yield_done(ok=False, error=str(e)[:2000])
            except Exception:
                yield "data: {\"event\":\"done\",\"ok\":false,\"error\":\"SSE error\",\"text\":\"\"}\n\n"

    def _persist_last_channel(self, request: PromptRequest) -> None:
        """Persist last channel to DB and atomic file (database/latest_channel.json) for robust send_response_to_latest_channel. Also saves with per-session key for cron delivery_target='session'."""
        if request is None:
            return
        try:
            app_id = getattr(request, "app_id", None) or ""
            last_channel_store.save_last_channel(
                request_id=request.request_id,
                host=request.host,
                port=int(request.port),
                channel_name=request.channel_name,
                request_metadata=request.request_metadata or {},
                key=last_channel_store._DEFAULT_KEY,
                app_id=app_id,
            )
            # Per-session key so cron can deliver to this session (delivery_target='session')
            try:
                session_id = self.get_session_id(
                    app_id=app_id,
                    user_name=getattr(request, "user_name", None),
                    user_id=getattr(request, "user_id", None),
                    channel_name=getattr(request, "channel_name", None),
                )
                if session_id and app_id and getattr(request, "user_id", None):
                    session_key = f"{app_id}:{request.user_id}:{session_id}"
                    last_channel_store.save_last_channel(
                        request_id=request.request_id,
                        host=request.host,
                        port=int(request.port),
                        channel_name=request.channel_name,
                        request_metadata=request.request_metadata or {},
                        key=session_key,
                        app_id=app_id,
                    )
            except Exception as sk:
                logger.debug("Failed to persist last channel session key: {}", sk)
        except Exception as e:
            logger.warning("Failed to persist last channel: {}", e)

    # Shared key for "latest location when Companion app is not combined" — used as fallback for all users (see SystemContextDateTimeAndLocation.md)
    _LATEST_LOCATION_SHARED_KEY = "companion"

    def _latest_location_path(self) -> Path:
        """Path to latest_locations.json. Persisted under database dir: {project_root}/database/latest_locations.json (or core database.path if set). Never raises."""
        try:
            root = Path(Util().root_path()).resolve()
            meta = Util().get_core_metadata()
            db = getattr(meta, "database", None)
            if getattr(db, "path", None):
                base = root / str(db.path).strip()
            else:
                base = root / "database"
            base.mkdir(parents=True, exist_ok=True)
            return base / "latest_locations.json"
        except Exception as e:
            logger.debug("Latest location path: {}", e)
            return Path("database") / "latest_locations.json"

    def _normalize_location_to_address(self, location_input: Any) -> Tuple[Optional[str], Optional[str]]:
        """If location is lat/lng (string or dict from Companion/mobile), convert to address. Returns (display_location, lat_lng_str). Never raises."""
        try:
            from base.geocode import location_to_address
            return location_to_address(location_input)
        except Exception as e:
            logger.debug("Normalize location failed: {}", e)
            if isinstance(location_input, str) and location_input.strip():
                return location_input.strip()[:2000], None
            return None, None

    def _set_latest_location(self, system_user_id: str, location_str: str, lat_lng_str: Optional[str] = None) -> None:
        """Store latest location for this user. location_str is the address or display text; lat_lng_str optional 'lat,lng' for plugins that need coords. Never raises."""
        if not system_user_id or not isinstance(location_str, str) or not location_str.strip():
            return
        try:
            path = self._latest_location_path()
            data = {}
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            if not isinstance(data, dict):
                data = {}
            entry = {
                "location": location_str.strip()[:2000],
                "updated_at": datetime.now().isoformat(),
            }
            if lat_lng_str and isinstance(lat_lng_str, str) and lat_lng_str.strip():
                entry["lat_lng"] = lat_lng_str.strip()[:100]
            data[str(system_user_id)] = entry
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=0, ensure_ascii=False)
        except Exception as e:
            logger.debug("Set latest location failed: {}", e)

    def _get_latest_location(self, system_user_id: str) -> Optional[str]:
        """Return latest location for this user or None. Never raises."""
        entry = self._get_latest_location_entry(system_user_id)
        if isinstance(entry, dict) and entry.get("location"):
            return str(entry.get("location", "")).strip() or None
        return None

    def _get_latest_location_entry(self, system_user_id: str) -> Optional[Dict[str, Any]]:
        """Return latest location entry {location, updated_at} for this user or None. Never raises."""
        if not system_user_id:
            return None
        try:
            path = self._latest_location_path()
            if not path.exists():
                return None
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            entry = data.get(str(system_user_id))
            if isinstance(entry, dict) and entry.get("location"):
                return entry
            return None
        except Exception as e:
            logger.debug("Get latest location failed: {}", e)
            return None

    def get_system_context_for_plugins(
        self,
        system_user_id: Optional[str] = None,
        request: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Build system context (datetime, timezone, location) for plugin parameter resolution.
        Used when resolving params so plugins can get current time and user location without the user typing them.
        Returns dict with: datetime, datetime_iso, timezone, location (optional), location_source, location_confidence.
        location_confidence is 'high' when from request or recent latest; 'low' when from profile/config/shared so caller may ask user to confirm when scheduling.
        """
        out = {}
        try:
            now = datetime.now()
            try:
                now = now.astimezone()
            except Exception:
                pass
            out["datetime"] = now.strftime("%Y-%m-%d %H:%M")
            out["datetime_iso"] = now.isoformat()
            out["timezone"] = getattr(now.tzinfo, "tzname", lambda: None)() or "system local"
        except Exception:
            out["datetime"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            out["datetime_iso"] = datetime.now().isoformat()
            out["timezone"] = "system local"

        user_id = system_user_id or (getattr(request, "user_id", None) if request else None) or ""
        loc_str = None
        location_source = None
        location_confidence = "low"
        try:
            meta = getattr(request, "request_metadata", None) if request else {}
            raw_loc = meta.get("location") if isinstance(meta, dict) else None
            if raw_loc is not None:
                display_loc, _ = self._normalize_location_to_address(raw_loc)
                if display_loc:
                    loc_str = display_loc
                    location_source = "request"
                    location_confidence = "high"
            if not loc_str and user_id:
                entry = self._get_latest_location_entry(user_id)
                if isinstance(entry, dict) and entry.get("location"):
                    loc_str = str(entry.get("location", "")).strip()
                    location_source = "latest"
                    updated = entry.get("updated_at") or ""
                    if updated:
                        try:
                            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                            now_ref = datetime.now(updated_dt.tzinfo) if getattr(updated_dt, "tzinfo", None) else datetime.now()
                            if (now_ref - updated_dt) < timedelta(hours=24):
                                location_confidence = "high"
                        except Exception:
                            pass
            if not loc_str and user_id:
                profile_cfg = getattr(Util().get_core_metadata(), "profile", None) or {}
                if isinstance(profile_cfg, dict) and profile_cfg.get("enabled", True):
                    try:
                        from base.profile_store import get_profile
                        profile_base_dir = (profile_cfg.get("dir") or "").strip() or None
                        profile_data = get_profile(user_id or "", base_dir=profile_base_dir)
                        if isinstance(profile_data, dict) and profile_data.get("location"):
                            loc_str = str(profile_data.get("location", "")).strip()
                            location_source = "profile"
                    except Exception:
                        pass
            if not loc_str:
                loc_str = (getattr(Util().get_core_metadata(), "default_location", None) or "").strip() or None
                if loc_str:
                    location_source = "config"
            if not loc_str:
                shared_key = getattr(self, "_LATEST_LOCATION_SHARED_KEY", "companion")
                entry = self._get_latest_location_entry(shared_key)
                if isinstance(entry, dict) and entry.get("location"):
                    loc_str = str(entry.get("location", "")).strip()
                    location_source = "shared"
        except Exception as e:
            logger.debug("System context location: {}", e)
        if loc_str:
            out["location"] = loc_str[:500]
            out["location_source"] = location_source or "unknown"
            out["location_confidence"] = location_confidence
        return out

    def save_latest_prompt_request_to_file(self, filename: str):
        """Legacy: save to file (e.g. for debugging). Prefer _persist_last_channel which uses DB + atomic file in database/."""
        if getattr(self, 'latestPromptRequest', None) is None:
            return
        try:
            with open(filename, 'w') as file:
                json.dump(self.latestPromptRequest.__dict__, file, default=str)
            logger.debug(f"latestPromptRequest saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving latestPromptRequest: {e}")

    def read_latest_prompt_request_from_file(self, filename: str) -> PromptRequest:
        """Legacy: read from file. Prefer last_channel_store.get_last_channel() for robust load."""
        try:
            with open(filename, 'r') as file:
                data = json.load(file)
                logger.debug(f"latestPromptRequest read from {data}")
                channel_type = data['channelType'].split('.')[-1]
                content_type = data['contentType'].split('.')[-1]
                data['channelType'] = ChannelType[channel_type]
                data['contentType'] = ContentType[content_type]
                logger.debug(f"latestPromptRequest read from {data}")
                request = PromptRequest(**data)
                logger.debug(f"latestPromptRequest : {request}")
            logger.debug(f"latestPromptRequest read from {filename}")
            return request
        except Exception as e:
            logger.error(f"Error reading latestPromptRequest: {e}")
            return None

    async def orchestrator_handler(self, request: PromptRequest):
        """
        Separate orchestrator path: one LLM call for intent (TIME/OTHER) + plugin selection.
        Only used when orchestrator_unified_with_tools is false. When true (default), routing is done via
        route_to_tam / route_to_plugin tools in the main chat.
        """
        timeout_sec = getattr(self, "orchestrator_timeout_seconds", 60) or 0
        request_id = getattr(request, "request_id", None) or ""
        t0 = time.time()

        try:
            if self.plugin_manager and getattr(self.plugin_manager, "plugin_instances", None):
                plugin_infos = [
                    {"id": getattr(p, "plugin_id", "") or "", "description": (p.description or "")[:500]}
                    for p in self.plugin_manager.plugin_instances
                ]
                if plugin_infos:
                    async def do_translate():
                        return await self.orchestratorInst.translate_to_intent_and_plugin(request, plugin_infos)
                    if timeout_sec > 0:
                        intent, plugin_ref = await asyncio.wait_for(do_translate(), timeout=timeout_sec)
                    else:
                        intent, plugin_ref = await do_translate()

                    if intent is None:
                        return False
                    _component_log("orchestrator", f"intent={getattr(intent, 'type', None)}")
                    if intent.type != IntentType.OTHER:
                        logger.debug(f"Got intent: {intent.type} (not OTHER), skipping plugin")
                        return False

                    plugin = None
                    if plugin_ref is not None:
                        if isinstance(plugin_ref, int):
                            plugin = self.plugin_manager.get_plugin_by_index(plugin_ref - 1)
                        else:
                            plugin = self.plugin_manager.get_plugin_by_id(str(plugin_ref))
                    if plugin is None:
                        logger.debug("Orchestrator: no plugin resolved, skipping")
                        return False

                    pid = getattr(plugin, "plugin_id", "") or (plugin.get("id", "") if isinstance(plugin, dict) else "") or "?"
                    _component_log("plugin", f"orchestrator selected: {pid}")
                    if isinstance(plugin, dict):
                        result = await asyncio.wait_for(
                            self.plugin_manager.run_external_plugin(plugin, request),
                            timeout=timeout_sec or 30,
                        ) if timeout_sec > 0 else await self.plugin_manager.run_external_plugin(plugin, request)
                        if isinstance(result, PluginResult):
                            result_text = result.error or "Plugin returned an error" if not result.success else (result.text or "(no response)")
                            metadata = dict(result.metadata or {})
                        else:
                            result_text = result if isinstance(result, str) else "(no response)"
                            metadata = {}
                        media_data_url = metadata.get("media") if isinstance(metadata.get("media"), str) else None
                        if media_data_url:
                            try:
                                from base.media_io import save_data_url_to_media_folder
                                meta = Util().get_core_metadata()
                                ws_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "config/workspace")
                                media_base = Path(ws_dir) / "media" if ws_dir else None
                                path, media_kind = save_data_url_to_media_folder(media_data_url, media_base)
                                if path and media_kind:
                                    await self.send_response_to_request_channel(
                                        result_text, request,
                                        image_path=path if media_kind == "image" else None,
                                        video_path=path if media_kind == "video" else None,
                                        audio_path=path if media_kind == "audio" else None,
                                    )
                                else:
                                    await self.send_response_to_request_channel(result_text, request)
                            except Exception as e:
                                logger.warning("Orchestrator: save/send media failed: {}", e)
                                await self.send_response_to_request_channel(result_text, request)
                        else:
                            await self.send_response_to_request_channel(result_text, request)
                    else:
                        plugin.user_input = intent.text
                        try:
                            plugin.promptRequest = request.model_copy(deep=True)
                        except Exception:
                            plugin.promptRequest = PromptRequest(**request.model_dump())
                        if timeout_sec > 0:
                            await asyncio.wait_for(plugin.run(), timeout=timeout_sec)
                        else:
                            await plugin.run()
                    duration_ms = (time.time() - t0) * 1000
                    logger.debug(f"orchestrator request_id={request_id} intent=OTHER plugin_id={pid} duration_ms={duration_ms:.0f}")
                    return True
            return False

        except asyncio.TimeoutError:
            logger.error(f"orchestrator request_id={request_id} timed out after {timeout_sec}s")
            return False
        except Exception as e:
            logger.error(f"An error occurred in orchestrator_handler: {e}")
            return False


    async def process_request_queue(self):
        while True:
            request: PromptRequest = await self.request_queue.get()
            try:
                if request is None:
                    return
                logger.debug(f"Received request from channel: {request.user_name}, {request.user_id}, {request.channelType}, {request.contentType}")
                # When unified (default), skip separate orchestrator call; routing is via tools. When false, run orchestrator_handler first.
                if not getattr(self, "orchestrator_unified_with_tools", True):
                    flag = await self.orchestrator_handler(request)
                    if flag:
                        logger.debug(f"Orchestrator and plugin handled the request")
                        continue

                user: User = None
                has_permission, user = self.check_permission(request.user_name, request.user_id, request.channelType, request.contentType)
                if not has_permission or user is None:
                    # Push error to channel and continue loop (do not return Response here)
                    err_resp = AsyncResponse(
                        request_id=request.request_id,
                        request_metadata=request.request_metadata or {},
                        host=request.host,
                        port=request.port,
                        from_channel=request.channel_name,
                        response_data={"text": self._format_outbound_text("Permission denied."), "format": "plain", "error": True},
                    )
                    await self.response_queue.put(err_resp)
                    continue

                if len(user.name) > 0:
                    request.user_name = user.name
                request.system_user_id = user.id or user.name

                #if intent is not None and (intent.type == IntentType.RESPOND or intent.type == IntentType.QUERY):
                # Process all message content types (text, text+image, image, audio, video); process_text_message uses request.images/videos/audios/files
                processable = request.contentType in (
                    ContentType.TEXT,
                    ContentType.TEXTWITHIMAGE,
                    ContentType.IMAGE,
                    ContentType.AUDIO,
                    ContentType.VIDEO,
                )
                if processable:
                    txt = (request.text or "")[:50]
                    if len(request.text or "") > 50:
                        txt += "..."
                    logger.info(f"Core: processing message for {request.channel_name} user={request.user_id} text={txt!r}")
                    resp_text = await self.process_text_message(request)
                    if resp_text is None:
                        logger.debug(f"response_text is None")
                        continue
                    if resp_text == ROUTING_RESPONSE_ALREADY_SENT:
                        logger.debug("Routing tool already sent response to channel")
                        continue
                    # Channel queue gets converted (channel-ready) text; format must be "plain" so it matches content (avoid markdown/link hint with whatsapp/plain text).
                    resp_data = {"text": self._format_outbound_text(resp_text), "format": "plain"}
                    # Any skill/tool output that includes images: HOMECLAW_IMAGE_PATH=<path> → send to channel/companion
                    img_paths = (request.request_metadata or {}).get("response_image_paths")
                    if not isinstance(img_paths, list):
                        img_paths = [(request.request_metadata or {}).get("response_image_path")] if (request.request_metadata or {}).get("response_image_path") else []
                    img_paths = [p for p in img_paths if isinstance(p, str) and os.path.isfile(p)]
                    if img_paths:
                        resp_data["images"] = img_paths
                        resp_data["image"] = img_paths[0]
                    async_resp: AsyncResponse = AsyncResponse(request_id=request.request_id, request_metadata=request.request_metadata, host=request.host, port=request.port, from_channel=request.channel_name, response_data=resp_data)
                    await self.response_queue.put(async_resp)
                else:
                    # Unsupported content type (e.g. HTML, OTHER)
                    pass

            except Exception as e:
                logger.exception(f"Error processing request: {e}")
            finally:
                self.request_queue.task_done()


    def _format_outbound_text(self, text: str) -> str:
        """Convert outbound reply only when it looks like Markdown; otherwise return original. Format from config (outbound_markdown_format). Never raises."""
        if text is None or not isinstance(text, str):
            return text if text is not None else ""
        try:
            meta = Util().get_core_metadata()
            fmt = (getattr(meta, "outbound_markdown_format", None) or "whatsapp").strip().lower()
            if fmt == "none" or fmt == "":
                return text
            if not looks_like_markdown(text):
                return text
            if fmt != "plain" and fmt != "whatsapp":
                fmt = "whatsapp"
            return markdown_to_channel(text, fmt)
        except Exception:
            return text

    def _safe_classify_format(self, text: str) -> str:
        """Return classify_outbound_format(text) or 'plain' on any exception. Never raises."""
        try:
            return classify_outbound_format(text) if (text is not None and isinstance(text, str)) else "plain"
        except Exception:
            return "plain"

    def _outbound_text_and_format(self, text: str) -> tuple[str, str]:
        """Return (text_to_send, format) for clients that support markdown (Companion, web chat, Control UI). format is 'plain'|'markdown'|'link'. For markdown/link we send raw text; for plain we apply _format_outbound_text. Never raises."""
        try:
            if text is None or not isinstance(text, str):
                return (str(text)[:50000] if text is not None else "", "plain")
            fmt = self._safe_classify_format(text)
            if fmt == "markdown" or fmt == "link":
                return (text, fmt)
            return (self._format_outbound_text(text), "plain")
        except Exception:
            return (str(text)[:50000] if text is not None else "", "plain")

    async def send_response_to_latest_channel(self, response: str):
        """Send to the default (latest) channel. See send_response_to_channel_by_key for per-session delivery."""
        await self.send_response_to_channel_by_key(last_channel_store._DEFAULT_KEY, response)

    async def send_response_to_channel_by_key(self, key: str, response: str):
        """Send response to the channel identified by key (e.g. 'default' or 'app_id:user_id:session_id' for cron per-session delivery). Never raises (logs and returns)."""
        try:
            if not key:
                key = last_channel_store._DEFAULT_KEY
            # Channel queue: use _outbound_text_and_format so markdown/link responses keep links clickable.
            out_text, out_fmt = self._outbound_text_and_format(response) if response else ("", "plain")
            resp_data = {"text": out_text, "format": out_fmt}
            request: Optional[PromptRequest] = self.latestPromptRequest
            if key != last_channel_store._DEFAULT_KEY or request is None:
                stored = last_channel_store.get_last_channel(key)
                if stored is None:
                    if key != last_channel_store._DEFAULT_KEY:
                        logger.warning("send_response_to_channel_by_key: no channel for key={}", key)
                    return
                app_id = stored.get("app_id") or ""
                if app_id == "homeclaw":
                    print(response)
                    return
                async_resp = AsyncResponse(
                    request_id=stored.get("request_id", ""),
                    request_metadata=stored.get("request_metadata") or {},
                    host=stored.get("host", ""),
                    port=int(stored.get("port", 0)),
                    from_channel=stored.get("channel_name", ""),
                    response_data=resp_data,
                )
                await self.response_queue.put(async_resp)
                return
            if request.app_id == "homeclaw":
                print(response)
            else:
                async_resp = AsyncResponse(
                    request_id=request.request_id,
                    request_metadata=request.request_metadata,
                    host=request.host,
                    port=request.port,
                    from_channel=request.channel_name,
                    response_data=resp_data,
                )
                await self.response_queue.put(async_resp)
        except Exception as e:
            logger.warning("send_response_to_channel_by_key failed: {}", e)

    async def deliver_to_user(
        self,
        user_id: str,
        text: str,
        images: Optional[List[str]] = None,
        channel_key: Optional[str] = None,
        source: str = "push",
    ) -> None:
        """Push a message to a user: (1) to all WebSocket sessions registered for this user_id (Companion/channel), (2) to the channel identified by channel_key if provided, else to latest channel. Used by cron, reminders, record_date follow-ups, and any proactive delivery. Never raises (logs and returns)."""
        try:
            user_id = (user_id or "").strip() or "companion"
            try:
                out_text, out_fmt = self._outbound_text_and_format(text) if text else ("", "plain")
            except Exception:
                out_text = str(text)[:50000] if text else ""
                out_fmt = "plain"
            if not text:
                out_text, out_fmt = "", "plain"
            payload = {"event": "push", "source": source, "text": out_text, "format": out_fmt}
            data_urls = []
            if images:
                for image_path in images:
                    if not isinstance(image_path, str) or not os.path.isfile(image_path):
                        continue
                    try:
                        with open(image_path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("ascii")
                        ext = (image_path.lower().split(".")[-1] if "." in image_path else "png") or "png"
                        mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext)
                        if mime == "image/jpg":
                            mime = "image/jpeg"
                        data_urls.append(f"data:{mime};base64,{b64}")
                    except Exception:
                        pass
            if data_urls:
                payload["images"] = data_urls
                payload["image"] = data_urls[0]
            for sid, uid in list(self._ws_user_by_session.items()):
                if uid != user_id:
                    continue
                ws = self._ws_sessions.get(sid)
                if ws is not None:
                    try:
                        await ws.send_json(payload)
                    except Exception as e:
                        logger.debug("deliver_to_user: push to session {} failed: {}", (sid or "")[:8], e)
            if channel_key:
                await self.send_response_to_channel_by_key(channel_key, text)
            else:
                await self.send_response_to_latest_channel(text)
        except Exception as e:
            logger.warning("deliver_to_user failed: {}", e)

    async def send_response_to_request_channel(
        self,
        response: str,
        request: PromptRequest,
        image_path: Optional[str] = None,
        video_path: Optional[str] = None,
        audio_path: Optional[str] = None,
    ):
        """Send text and optional media (file paths) to the channel. Channels that support image/video/audio send them; others use text only."""
        # Channel queue: converted text; format "plain" so it matches content.
        out_text, out_fmt = self._outbound_text_and_format(response) if response else ("", "plain")
        resp_data = {"text": out_text, "format": out_fmt}
        if request is None:
            return
        if image_path and isinstance(image_path, str) and os.path.isfile(image_path):
            resp_data["image"] = image_path
        if video_path and isinstance(video_path, str) and os.path.isfile(video_path):
            resp_data["video"] = video_path
        if audio_path and isinstance(audio_path, str) and os.path.isfile(audio_path):
            resp_data["audio"] = audio_path
        async_resp: AsyncResponse = AsyncResponse(request_id=request.request_id, request_metadata=request.request_metadata, host=request.host, port=request.port, from_channel=request.channel_name, response_data=resp_data)
        await self.response_queue.put(async_resp)

    async def send_response_for_plugin(self, response: str, request: Optional[PromptRequest] = None):
        """Send response to the channel that issued the request when request is known (concurrency-safe). When request is None, falls back to send_response_to_latest_channel."""
        if request is not None:
            await self.send_response_to_request_channel(response, request)
        else:
            await self.send_response_to_latest_channel(response)

    async def process_memory_queue(self):
        main_llm_size = Util().main_llm_size()
        use_memory = Util().has_memory()
        has_gpu = Util().has_gpu_cuda()
        while True:
            # if main_llm_size is None:
            #     logger.debug("main_llm_size is None")
            #     time.sleep(30)
            #     continue
            # else:
            time.sleep(2)

            request: PromptRequest = await self.memory_queue.get()
            if use_memory:
                try:
                    if request is None:
                        return
                    user_name: str = request.user_name
                    user_id: str = getattr(request, 'system_user_id', None) or request.user_id
                    action: str = request.action
                    channel_type: ChannelType = request.channelType
                    content_type: ContentType = request.contentType
                    content = request.text
                    app_id: str = request.app_id
                    human_message = ''
                    email_addr = ''
                    subject = ''
                    body = ''

                    if channel_type == ChannelType.Email:
                        content_json = json.loads(content)
                        msg_id = content_json["MessageID"]
                        email_addr = content_json["From"]
                        subject = content_json["Subject"]
                        body = content_json["Body"]
                        human_message = body
                        logger.debug(f"email_addr: {email_addr}, subject: {subject}, body: {body}")
                    else:
                        human_message = content

                    if channel_type == ChannelType.Email:
                        content_json = json.loads(content)
                        msg_id = content_json["MessageID"]
                        email_addr = content_json["From"]
                        subject = content_json["Subject"]
                        body = content_json["Body"]
                        human_message = body
                        logger.debug(f"email_addr: {email_addr}, subject: {subject}, body: {body}")
                    else:
                        human_message = content
                    channel_name = getattr(request, "channel_name", None)
                    account_id = (request.request_metadata or {}).get("account_id") if getattr(request, "request_metadata", None) else None
                    session_id = self.get_session_id(app_id=app_id, user_name=user_name, user_id=user_id, channel_name=channel_name, account_id=account_id)
                    run_id = self.get_run_id(agent_id=app_id, user_name=user_name, user_id=user_id)

                    # When memory_check_before_add is True and model is small/local: run one LLM call to decide "should we store?"; else store every message (default).
                    meta = Util().get_core_metadata()
                    use_memory_check = getattr(meta, "memory_check_before_add", False)
                    if use_memory_check and (((main_llm_size <= 14) and (has_gpu == True)) or (main_llm_size <= 8)):
                        prompt = None
                        if getattr(meta, "use_prompt_manager", False):
                            try:
                                pm = get_prompt_manager(
                                    prompts_dir=getattr(meta, "prompts_dir", None),
                                    default_language=getattr(meta, "prompt_default_language", "en"),
                                    cache_ttl_seconds=float(getattr(meta, "prompt_cache_ttl_seconds", 0) or 0),
                                )
                                lang = Util().main_llm_language()
                                prompt = pm.get_content("memory", "memory_check", lang=lang, user_input=human_message)
                            except Exception as e:
                                logger.debug("Prompt manager fallback for memory_check: {}", e)
                        if not prompt or not prompt.strip():
                            prompt = MEMORY_CHECK_PROMPT.format(user_input=human_message)
                        llm_input = []
                        llm_input = [{"role": "system", "content": "You are a helpful assistant, please follow the instructions from user."}, {"role": "user", "content": prompt}]
                        logger.debug("Start to check if the user input should be added to memory")
                        result =await self.openai_chat_completion(messages=llm_input)
                        if result is not None and len(result) > 0:
                            result = result.strip().lower()
                            if result.find("yes") != -1:
                                await self.mem_instance.add(human_message, user_name=user_name, user_id=user_id, agent_id=app_id, run_id=run_id, metadata=None, filters=None)
                                _component_log("memory", f"add (yes): user_id={user_id} text={human_message[:60]}...")
                                logger.debug(f"User input added to memory: {human_message}")
                    else:
                        await self.mem_instance.add(human_message, user_name=user_name, user_id=user_id, agent_id=app_id, run_id=run_id, metadata=None, filters=None)
                        _component_log("memory", f"add: user_id={user_id} text={(human_message or '')[:60]}...")
                        logger.debug(f"User input added to memory: {human_message}")
                except Exception as e:
                    logger.exception(f"Error check whether to save to memory: {e}")
                finally:
                    self.memory_queue.task_done()

    async def _process_kb_folder_sync_scheduler(self) -> None:
        """Background loop: when knowledge_base.folder_sync.enabled and schedule set, run sync for all users periodically. Never raises."""
        await asyncio.sleep(120)  # let Core settle
        while True:
            try:
                interval = 3600 * 6  # default 6 hours
                meta = Util().get_core_metadata()
                kb_cfg = getattr(meta, "knowledge_base", None) or {}
                if isinstance(kb_cfg, dict):
                    fs = kb_cfg.get("folder_sync") or {}
                    if isinstance(fs, dict) and fs.get("enabled") and (fs.get("schedule") or "").strip():
                        try:
                            users = Util().get_users() or []
                            for u in users:
                                uid = getattr(u, "id", None) or getattr(u, "name", "") or ""
                                if not uid:
                                    continue
                                try:
                                    await self.sync_user_kb_folder(str(uid))
                                except Exception as e:
                                    logger.debug("KB folder sync for user {} failed: {}", uid, e)
                        except Exception as e:
                            logger.debug("KB folder sync scheduler: {}", e)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("KB folder sync scheduler loop: {}", e)
                await asyncio.sleep(interval)

    async def process_memory_summarization_scheduler(self):
        """Background loop: when memory_summarization.enabled, check next_run and run summarization when due (daily/weekly/next_run). Runs at free time."""
        await asyncio.sleep(60)  # let Core settle before first check
        while True:
            try:
                await asyncio.sleep(3600)  # check every hour
                meta = Util().get_core_metadata()
                cfg = getattr(meta, "memory_summarization", None) or {}
                if not cfg.get("enabled"):
                    continue
                state = self._read_memory_summarization_state()
                next_run_s = state.get("next_run")
                try:
                    tz = datetime.now().astimezone().tzinfo
                    now = datetime.now(tz)
                except Exception:
                    now = datetime.utcnow()
                if next_run_s:
                    try:
                        next_run = datetime.fromisoformat(str(next_run_s).replace("Z", "+00:00"))
                        if next_run.tzinfo is None:
                            next_run = next_run.replace(tzinfo=now.tzinfo)
                        if now < next_run:
                            continue
                    except Exception:
                        pass
                await self.run_memory_summarization()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Memory summarization scheduler: {}", e)

    async def process_response_queue(self):
        async with httpx.AsyncClient() as client:
            while True:
                response: AsyncResponse = await self.response_queue.get()
                try:
                    host = response.host if response.host != '0.0.0.0' else '127.0.0.1'
                    port = response.port
                    # Sync inbound (/inbound or /ws) use host=inbound, port=0; response was already returned in the HTTP/WS response.
                    if host == "inbound" and (port == 0 or port == "0"):
                        logger.debug(f"Skip get_response for sync inbound channel {response.from_channel}; response already sent.")
                    else:
                        path = '/get_response'
                        resp_url = f"http://{host}:{port}{path}"
                        logger.debug(f"Attempting to send response to {resp_url}")

                        response_dict = response.model_dump()

                        try:
                            resp = await client.post(url=resp_url, json=response_dict, timeout=10.0)
                            if resp.status_code == 200:
                                logger.info(f"Core: response sent to channel {response.from_channel}")
                                logger.debug(f"Response sent to channel: {response.from_channel}")
                            else:
                                logger.error(f"Failed to send response to channel: {response.from_channel}. Status: {resp.status_code}")
                        except httpx.ConnectError as e:
                            logger.error(f"Connection error when sending to {resp_url}: {str(e)}")
                        except httpx.TimeoutException:
                            logger.error(f"Timeout when sending to {resp_url}")
                        except Exception as e:
                            logger.error(f"Unexpected error when sending to {resp_url}: {str(e)}")
                except Exception as e:
                    logger.exception(f"Error sending response back to channel {response.from_channel}: {e}")
                finally:
                    self.response_queue.task_done()


    def get_run_id(self, agent_id, user_name=None, user_id=None, validity_period=timedelta(hours=24)):
        if user_id in self.run_ids:
            run_id, timestamp = self.run_ids[user_id]
            return run_id
            #if datetime.now() - timestamp < validity_period:
            #    return run_id

        current_time = datetime.now()
        runs: List[dict] =self.chatDB.get_runs(agent_id=agent_id, user_name=user_name, user_id=user_id, num_rounds=1, fetch_all=False)
        for run in runs:
            run_id = run['run_id']
            return run_id
            #timestamp = run['created_at']
            #if current_time - timestamp < validity_period:
            #    return run_id
        return user_id
        #new_run_id = uuid.uuid4().hex
        #self.run_ids[user_id] = (new_run_id, current_time)
        #self.chatDB.add_run(agent_id=agent_id, user_name=user_name, user_id=user_id, run_id=new_run_id, created_at=current_time)
        #return new_run_id

    def get_latest_chat_info(self, app_id=None, user_name=None, user_id=None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        chat_sessions =  self.chatDB.get_sessions(app_id=app_id, user_name=user_name, user_id=user_id, num_rounds=1)
        if len(chat_sessions) == 0:
            return None, None, None
        logger.debug(f'chat_sessions: {chat_sessions}')
        if len(chat_sessions) > 0:
            chat_session: dict = chat_sessions[0]
            app_id = chat_session['app_id']
            user_name = chat_session['user_name']
            user_id = chat_session['user_id']
            logger.debug(f'app_id: {app_id}, user_id: {user_id}')
            return app_id, user_name, user_id

    def get_latest_chats(self, app_id=None, user_name=None, user_id=None, num_rounds=10, timestamp=None) -> List[ChatMessage]:
        histories: List[ChatMessage] = self.chatDB.get(app_id=app_id, user_name=user_name, user_id=user_id, num_rounds=num_rounds, fetch_all=False, display_format=False)
        if timestamp is None:
            return histories
        else:
            histories = [history for history in histories if timestamp - history.created_at < timedelta(minutes=30)]
        return histories

    def get_latest_chats_by_role(self, sender_name=None, responder_name=None, num_rounds = 10, timestamp=None):
        histories = self.chatDB.get_hist_by_role(sender_name, responder_name, num_rounds)
        if timestamp is None:
            return histories
        else:
            histories = [history for history in histories if timestamp - history.created_at < timedelta(minutes=30)]
        return histories

    def _resolve_session_key(
        self,
        app_id: str,
        user_id: str,
        channel_name: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> str:
        """
        Derive session key from dmScope and identityLinks.
        main: one session for all DMs. per-peer: by sender. per-channel-peer: by channel+sender. per-account-channel-peer: by account+channel+sender.
        identity_links maps canonical id -> list of provider-prefixed ids (e.g. telegram:123); peer_id used in key is canonical when matched.
        """
        session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
        dm_scope = (session_cfg.get("dm_scope") or "main").strip().lower()
        identity_links = session_cfg.get("identity_links") or {}
        peer_id = user_id or ""
        if isinstance(identity_links, dict):
            for canonical, prefixes in identity_links.items():
                if isinstance(prefixes, list) and (user_id in prefixes or peer_id in prefixes):
                    peer_id = str(canonical)
                    break
                if isinstance(prefixes, str) and (user_id == prefixes or peer_id == prefixes):
                    peer_id = str(canonical)
                    break
        app = (app_id or "homeclaw").strip() or "homeclaw"
        channel = (channel_name or "").strip() or "im"
        account = (account_id or "").strip() or "default"
        if dm_scope == "main":
            return f"{app}:main"
        if dm_scope == "per-peer":
            return f"{app}:dm:{peer_id}"
        if dm_scope == "per-channel-peer":
            return f"{app}:{channel}:dm:{peer_id}"
        if dm_scope == "per-account-channel-peer":
            return f"{app}:{channel}:{account}:dm:{peer_id}"
        return f"{app}:dm:{peer_id}"

    def get_session_id(
        self,
        app_id,
        user_name=None,
        user_id=None,
        channel_name: Optional[str] = None,
        account_id: Optional[str] = None,
        validity_period=timedelta(hours=24),
    ):
        session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
        dm_scope = (session_cfg.get("dm_scope") or "").strip().lower()
        if dm_scope in ("main", "per-peer", "per-channel-peer", "per-account-channel-peer"):
            return self._resolve_session_key(
                app_id=app_id,
                user_id=user_id or "",
                channel_name=channel_name,
                account_id=account_id,
            )
        if user_id in self.session_ids:
            session_id, timestamp = self.session_ids[user_id]
            return session_id

        current_time = datetime.now()
        sessions: List[dict] = self.chatDB.get_sessions(app_id=app_id, user_name=user_name, user_id=user_id, num_rounds=1, fetch_all=False)
        for session in sessions:
            session_id = session["session_id"]
            return session_id
        return user_id

    def _resize_image_data_url_if_needed(self, data_url: str, max_dimension: int) -> str:
        """If max_dimension > 0 and Pillow is available, resize image so max(w,h) <= max_dimension; return data URL. Else return original."""
        if not data_url or not isinstance(data_url, str) or max_dimension <= 0:
            return data_url or ""
        try:
            from PIL import Image
            import io
        except ImportError:
            return data_url
        try:
            idx = data_url.find(";base64,")
            if idx <= 0:
                return data_url
            b64 = data_url[idx + 8:]
            raw = base64.b64decode(b64)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            w, h = img.size
            if w <= max_dimension and h <= max_dimension:
                return data_url
            if w >= h:
                new_w, new_h = max_dimension, max(1, int(h * max_dimension / w))
            else:
                new_w, new_h = max(1, int(w * max_dimension / h)), max_dimension
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            out_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{out_b64}"
        except Exception as e:
            logger.debug("Image resize skipped: {}", e)
            return data_url

    def _image_item_to_data_url(self, item: str) -> str:
        """Convert image item (data URL, file path, or raw base64) to a data URL for vision API. Optionally resizes if completion.image_max_dimension is set."""
        if not item or not isinstance(item, str):
            return ""
        item = item.strip()
        if item.lower().replace("data: ", "data:", 1).startswith("data:image/"):
            # Normalize so URL is always "data:image/...;base64,..." (some clients send "data: image/...")
            data_url = item.replace("data: ", "data:", 1) if item.startswith("data: ") else item
        elif item.startswith("data:"):
            data_url = item.replace("data: ", "data:", 1) if item.startswith("data: ") else item
        elif os.path.isfile(item):
            try:
                with open(item, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                data_url = f"data:image/jpeg;base64,{b64}"
            except Exception as e:
                logger.warning("Failed to read image file {}: {}", item, e)
                return ""
        else:
            # Path-like but file not found: do not treat as base64
            if ("/" in item or "\\" in item) and not os.path.isfile(item):
                logger.warning("Image file not found (path not readable): {}", item[:200])
                return ""
            data_url = f"data:image/jpeg;base64,{item}"
        max_dim = 0
        try:
            comp = getattr(Util().get_core_metadata(), "completion", None) or {}
            max_dim = int(comp.get("image_max_dimension") or 0)
        except (TypeError, ValueError):
            pass
        return self._resize_image_data_url_if_needed(data_url, max_dim)

    def _audio_item_to_base64_and_format(self, item: str) -> Optional[Tuple[str, str]]:
        """Convert audio item (data URL or file path) to (base64_string, format) for input_audio. Format: wav, mp3, etc."""
        if not item or not isinstance(item, str):
            return None
        item = item.strip()
        if item.startswith("data:"):
            # data:audio/wav;base64,... or data:audio/mpeg;base64,...
            try:
                header, _, b64 = item.partition(",")
                if not b64:
                    return None
                mime = header.replace("data:", "").split(";")[0].strip().lower()
                if "wav" in mime or "wave" in mime:
                    return (b64, "wav")
                if "mpeg" in mime or "mp3" in mime:
                    return (b64, "mp3")
                if "ogg" in mime:
                    return (b64, "ogg")
                if "webm" in mime:
                    return (b64, "webm")
                return (b64, "wav")
            except Exception:
                return None
        if os.path.isfile(item):
            try:
                with open(item, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                ext = (os.path.splitext(item)[1] or "").lower()
                fmt = "wav"
                if ext in (".mp3", ".mpeg"):
                    fmt = "mp3"
                elif ext == ".ogg":
                    fmt = "ogg"
                elif ext == ".webm":
                    fmt = "webm"
                elif ext == ".wav":
                    fmt = "wav"
                return (b64, fmt)
            except Exception as e:
                logger.warning("Failed to read audio file {}: {}", item, e)
                return None
        return None

    def _video_item_to_base64_and_format(self, item: str) -> Optional[Tuple[str, str]]:
        """Convert video item (data URL or file path) to (base64_string, format) for input_video. Format: mp4, webm, etc."""
        if not item or not isinstance(item, str):
            return None
        item = item.strip()
        if item.startswith("data:"):
            try:
                header, _, b64 = item.partition(",")
                if not b64:
                    return None
                mime = header.replace("data:", "").split(";")[0].strip().lower()
                if "mp4" in mime:
                    return (b64, "mp4")
                if "webm" in mime:
                    return (b64, "webm")
                return (b64, "mp4")
            except Exception:
                return None
        if os.path.isfile(item):
            try:
                with open(item, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                ext = (os.path.splitext(item)[1] or "").lower()
                fmt = "mp4"
                if ext == ".webm":
                    fmt = "webm"
                elif ext in (".mp4", ".m4v"):
                    fmt = "mp4"
                return (b64, fmt)
            except Exception as e:
                logger.warning("Failed to read video file {}: {}", item, e)
                return None
        return None

    async def process_text_message(self, request: PromptRequest):
        try:
            user_name: str = request.user_name
            # Use system user id for all storage (chat, session, memory); fallback to channel identity if not set
            storage_user_id: str = getattr(request, 'system_user_id', None) or request.user_id
            user_id: str = storage_user_id
            action: str = request.action
            channel_type: ChannelType = request.channelType
            content_type: ContentType = request.contentType
            content = request.text
            app_id: str = request.app_id
            human_message = ''
            email_addr = ''
            subject = ''
            body = ''

            if channel_type == ChannelType.Email:
                content_json = json.loads(content)
                msg_id = content_json["MessageID"]
                email_addr = content_json["From"]
                subject = content_json["Subject"]
                body = content_json["Body"]
                human_message = body
                logger.debug(f"email_addr: {email_addr}, subject: {subject}, body: {body}")
            else:
                human_message = content
            channel_name = getattr(request, "channel_name", None)
            account_id = (request.request_metadata or {}).get("account_id") if getattr(request, "request_metadata", None) else None
            session_id = self.get_session_id(app_id=app_id, user_name=user_name, user_id=user_id, channel_name=channel_name, account_id=account_id)
            run_id = self.get_run_id(agent_id=app_id, user_name=user_name, user_id=user_id)
            histories: List[ChatMessage] = self.chatDB.get(app_id=app_id, user_name=user_name, user_id=user_id, session_id=session_id, num_rounds=6, fetch_all=False, display_format=False)
            messages = []

            if histories is not None and len(histories) > 0:
                for item in histories:
                    messages.append({'role': 'user', 'content': item.human_message.content})
                    messages.append({'role': 'assistant', 'content': item.ai_message.content})
            images_list = list(getattr(request, "images", None) or [])
            audios_list = list(getattr(request, "audios", None) or [])
            videos_list = list(getattr(request, "videos", None) or [])
            files_raw = getattr(request, "files", None) or []
            files_raw_count = len(files_raw) if isinstance(files_raw, list) else 0
            logger.info(
                "process_text_message: request.images count={} request.files count={} (if 0 images, client/upload or inbound did not pass images)",
                len(images_list),
                files_raw_count,
            )
            supported_media = []
            try:
                supported_media = Util().main_llm_supported_media() or []
            except Exception:
                supported_media = []
            # Fallback: if we have images but supported_media is empty, and main_llm id looks like a vision model, include image anyway
            if images_list and "image" not in supported_media:
                main_llm_ref = (getattr(Util().get_core_metadata(), "main_llm", None) or "").strip()
                raw_id = main_llm_ref.split("/")[-1].strip().lower() if main_llm_ref else ""
                if raw_id and ("vl" in raw_id or "vision" in raw_id or raw_id == "main_vl_model"):
                    supported_media = ["image"]
                    logger.info(
                        "Vision fallback: main_llm_supported_media was empty but main_llm id looks like vision ({}); including image(s).",
                        raw_id,
                    )
            text_only = human_message or ""

            # File-understanding: process request.files (detect type, handle image/audio/video/doc). Stable: catch all, merge results, never crash.
            # Documents: always inject short notice with paths so the model uses document_read / knowledge_base_add. When user sent file(s) only (no text) and doc size <= add_to_kb_max_chars, add to KB directly so they can query/summarize without saying more.
            # Resolve data URLs to temp paths so process_files can read from disk (e.g. /inbound sends files as data URLs).
            files_list = getattr(request, "files", None) or []
            if not isinstance(files_list, list):
                files_list = []
            resolved_files = []
            for f in files_list:
                if not f or not isinstance(f, str):
                    continue
                if f.strip().startswith("data:"):
                    try:
                        import base64
                        import tempfile
                        idx = f.find(";base64,")
                        if idx > 0:
                            payload = f[idx + 8:]
                            raw = base64.b64decode(payload)
                            suffix = ".bin"
                            if f.startswith("data:application/pdf"):
                                suffix = ".pdf"
                            elif "image/" in f[:30]:
                                suffix = ".jpg"
                            elif "audio/" in f[:30]:
                                suffix = ".m4a"
                            elif "video/" in f[:30]:
                                suffix = ".mp4"
                            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
                                tf.write(raw)
                                resolved_files.append(tf.name)
                        else:
                            resolved_files.append(f)
                    except Exception as _e:
                        logger.debug("file_understanding data URL resolve: {}", _e)
                else:
                    resolved_files.append(f)
            files_list = resolved_files
            if files_list:
                try:
                    try:
                        root = Util().root_path()
                    except Exception as root_e:
                        logger.debug("file_understanding root_path failed: {}", root_e)
                        root = Path(".").resolve()
                    from base.file_understanding import process_files
                    config_path = Path(str(root)) / "config" / "core.yml"
                    data = {}
                    if Path(config_path).exists():
                        try:
                            data = Util().load_yml_config(str(config_path)) or {}
                        except Exception as cfg_e:
                            logger.debug("file_understanding config load failed: {}", cfg_e)
                    tools_cfg = (data or {}).get("tools") or {}
                    fu_cfg = (data or {}).get("file_understanding") or {}
                    try:
                        base_dir = str(Util().get_core_metadata().get_homeclaw_root() or ".")
                    except Exception:
                        base_dir = "."
                    try:
                        max_chars = int(tools_cfg.get("file_read_max_chars") or 0) or 64000
                    except (TypeError, ValueError):
                        max_chars = 64000
                    try:
                        add_to_kb_max = int(fu_cfg.get("add_to_kb_max_chars") or 0)
                    except (TypeError, ValueError):
                        add_to_kb_max = 0
                    try:
                        result = process_files(files_list, supported_media, base_dir, max_chars)
                    except Exception as proc_e:
                        logger.debug("file_understanding process_files raised: {}", proc_e)
                        result = None
                    if result is None:
                        result = type("_Empty", (), {"document_texts": [], "document_paths": [], "images": [], "audios": [], "videos": [], "errors": []})()
                    # Defensive: ensure result has list attributes so we never crash on extend/iterate
                    def _safe_list(val):
                        return val if isinstance(val, list) else []

                    doc_texts = _safe_list(getattr(result, "document_texts", None))
                    doc_paths = _safe_list(getattr(result, "document_paths", None))
                    images_list.extend(_safe_list(getattr(result, "images", None)))
                    audios_list.extend(_safe_list(getattr(result, "audios", None)))
                    videos_list.extend(_safe_list(getattr(result, "videos", None)))

                    if doc_texts and doc_paths and len(doc_texts) == len(doc_paths):
                        try:
                            base_path = Path(base_dir).resolve()
                        except Exception:
                            base_path = Path(".").resolve()

                        def path_for_tool(p: str) -> str:
                            try:
                                if p is None or not isinstance(p, str):
                                    return str(p) if p is not None else ""
                                rel = Path(p).resolve().relative_to(base_path)
                                return str(rel)
                            except (ValueError, TypeError, OSError):
                                return str(p) if p is not None else ""

                        notice_lines = []
                        for p in doc_paths:
                            try:
                                notice_lines.append("- " + os.path.basename(str(p) if p is not None else "") + " (path: " + path_for_tool(p) + ")")
                            except Exception:
                                try:
                                    notice_lines.append("- (path: " + path_for_tool(p) + ")")
                                except Exception:
                                    notice_lines.append("- (path: )")
                        try:
                            sep = "\n".join(notice_lines) if notice_lines else ""
                            doc_block = (
                                "User attached the following document(s). Use **document_read**(path) when the user asks to summarize, query, or edit; use **knowledge_base_add** after reading if they ask to save to their knowledge base.\n\n"
                                + sep
                            )
                            text_only = (doc_block + "\n\n" + text_only).strip() if text_only else doc_block
                        except Exception as block_e:
                            logger.debug("file_understanding doc_block build failed: {}", block_e)

                        # When user sent file(s) only (no or negligible text) and KB enabled: add docs to KB if size <= add_to_kb_max_chars; too big = skip
                        user_text_only = (human_message or "").strip()
                        if not user_text_only and add_to_kb_max > 0:
                            kb = getattr(self, "knowledge_base", None)
                            kb_cfg = (data or {}).get("knowledge_base") or {}
                            if kb and kb_cfg.get("enabled") and user_id:
                                for path, text in zip(doc_paths, doc_texts):
                                    if path is None or text is None:
                                        continue
                                    if not isinstance(text, str):
                                        continue
                                    try:
                                        if len(text) > add_to_kb_max:
                                            continue
                                    except Exception:
                                        continue
                                    try:
                                        source_id = path_for_tool(path) if path is not None else "doc"
                                        if not source_id or not isinstance(source_id, str):
                                            source_id = (str(path)[:200] if path is not None else "doc") or "doc"
                                        err = await asyncio.wait_for(
                                            kb.add(user_id=user_id, content=text, source_type="document", source_id=source_id, metadata=None),
                                            timeout=60,
                                        )
                                        if err and "Error" in str(err):
                                            logger.debug("file_understanding add_to_kb: {}", err)
                                    except asyncio.TimeoutError:
                                        logger.debug("file_understanding add_to_kb timed out for {}", path)
                                    except Exception as e:
                                        logger.debug("file_understanding add_to_kb failed for {}: {}", path, e)
                    for err in getattr(result, "errors", None) or []:
                        logger.debug("file_understanding: {}", err)
                except Exception as e:
                    logger.debug("file_understanding failed: {}", e)
            if images_list:
                main_llm_ref = (getattr(Util().get_core_metadata(), "main_llm", None) or "").strip()
                will_include = "image" in supported_media
                logger.info(
                    "Vision request: images_count={} main_llm={} supported_media={} will_include_images={}",
                    len(images_list),
                    main_llm_ref or "(empty)",
                    supported_media,
                    will_include,
                )
            if images_list and "image" not in supported_media:
                main_llm_ref = (getattr(Util().get_core_metadata(), "main_llm", None) or "").strip()
                logger.warning(
                    "Vision input skipped: main_llm does not support images (main_llm={}). "
                    "Fix: in config/core.yml set main_llm to a local_models entry with mmproj and supported_media: [image], or a cloud_models entry with supported_media: [image]. "
                    "For local vision: the llama.cpp server must be started with --mmproj (Core does this when it auto-starts the main LLM; if you start llama-server yourself, add --mmproj <path_to_mmproj.gguf>).",
                    main_llm_ref or "(empty)",
                )
                text_only = (text_only + " (Image(s) omitted - model does not support images.)").strip()
            elif images_list and "image" in supported_media:
                logger.debug("Including {} image(s) in user message for vision model", len(images_list))
            if (audios_list or videos_list) and "audio" not in supported_media and "video" not in supported_media:
                text_only = (text_only + " (Audio/video omitted - model does not support media.)").strip()
            # Build content_parts when we have any supported media (image/audio/video).
            # Images: Core always converts to data URL (path -> read file -> base64 -> data:image/...;base64,...).
            # Same format is used for both local (llama.cpp) and cloud (Gemini, OpenAI, etc.): inline base64 in the
            # request body; cloud APIs accept image_url with data URL, local LiteLLM/llama-server accept it too.
            content_parts: List[Dict] = []
            if images_list and "image" in supported_media:
                content_parts.append({"type": "text", "text": text_only or ""})
                for i, img in enumerate(images_list):
                    data_url = self._image_item_to_data_url(img)
                    if data_url:
                        # Log so we confirm the image URL is passed correctly (no base64 content)
                        prefix = data_url[:50] if len(data_url) > 50 else data_url
                        if ";base64," in data_url:
                            prefix = data_url.split(";base64,")[0] + ";base64,<...>"
                        logger.debug("Vision image {}: url length={} prefix={}", i + 1, len(data_url), prefix)
                        content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                    else:
                        input_kind = "data_url" if (isinstance(img, str) and img.strip().lower().startswith("data:")) else ("path" if (isinstance(img, str) and len(img) < 2048 and os.path.isfile(img)) else "other")
                        logger.warning(
                            "Vision image {} produced empty data URL (input: {}). Check image source (data URL, file path, or base64).",
                            i + 1,
                            input_kind,
                        )
                num_added = sum(1 for p in content_parts if isinstance(p, dict) and p.get("type") == "image_url")
                if images_list and num_added == 0:
                    logger.warning("Vision: had {} image(s) but all produced empty data URL; sending text-only user message", len(images_list))
            if audios_list and "audio" in supported_media:
                if not content_parts:
                    content_parts.append({"type": "text", "text": text_only or ""})
                for aud in audios_list:
                    out = self._audio_item_to_base64_and_format(aud)
                    if out:
                        b64_str, fmt = out
                        content_parts.append({"type": "input_audio", "input_audio": {"data": b64_str, "format": fmt}})
            if videos_list and "video" in supported_media:
                if not content_parts:
                    content_parts.append({"type": "text", "text": text_only or ""})
                for vid in videos_list:
                    out = self._video_item_to_base64_and_format(vid)
                    if out:
                        b64_str, fmt = out
                        content_parts.append({"type": "input_video", "input_video": {"data": b64_str, "format": fmt}})
            if content_parts:
                num_images = sum(1 for p in content_parts if isinstance(p, dict) and p.get("type") == "image_url")
                if num_images:
                    logger.info("Sending multimodal user message to LLM ({} image(s), OpenAI image_url format)", num_images)
                messages.append({"role": "user", "content": content_parts})
            else:
                if images_list:
                    logger.warning(
                        "User message sent as TEXT ONLY (no image). Had images_list={} but content_parts empty. supported_media={}. Check main_llm has mmproj/supported_media in config.",
                        len(images_list),
                        supported_media,
                    )
                messages.append({"role": "user", "content": text_only})
            use_memory = Util().has_memory()
            if use_memory:
                await self.memory_queue.put(request)
            start = time.time()
            answer = await self.answer_from_memory(query=human_message, messages=messages, app_id=app_id, user_name=user_name, user_id=user_id, agent_id=app_id, session_id=session_id, run_id=run_id, request=request)
            end = time.time()
            elapsed = end - start
            logger.info("Core: response generated in {:.1f}s for user={}", elapsed, user_id)
            logger.debug("LLM handling time: {} seconds", elapsed)
            if elapsed > 90:
                logger.warning(
                    "Inbound request took {:.0f}s. If the client sees 'Connection closed while receiving data', use POST /inbound with stream: true (SSE) or set proxy/client read_timeout >= {:.0f}s (e.g. inbound_request_timeout_seconds in config).",
                    elapsed, max(300, elapsed + 60),
                )
            if answer is None:
                answer = "I'm sorry, I don't have the answer to that question. Please try asking a different question or restart your system."
            return answer
        except Exception as e:
            logger.exception(e)


    def prompt_template(self, section: str, prompt_name: str) -> List[Dict] | None:
        try:
            main_language = Util().main_llm_language()
            current_path = os.path.dirname(os.path.abspath(__file__))
            prompt_file_name = "prompt_" + main_language + ".yml"
            prompt_file_path = os.path.join(current_path, 'prompts',prompt_file_name)
            with open(prompt_file_path, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)

            for item in data['Prompts'][section]:
                if item['name'] == prompt_name:
                    template = item['prompt']
                    return template

        except Exception as e:
            logger.exception(e)
            return None


    def check_permission(self, user_name: str, user_id: str, channel_type: ChannelType, content_type: ContentType) -> Tuple[bool, Optional[User]]:
        """Match request to a user; return (has_permission, user). Never raises. Caller must check has_permission and user is not None before using user."""
        user: Optional[User] = None
        users = Util().get_users() or []
        # For IM: prefer user.yml when user_id matches a user's id or name (e.g. "companion", "math_teacher"). So adding "companion" (or Math, Music, Sport) in user.yml makes them work like any other user.
        if channel_type == ChannelType.IM and users:
            uid = str(user_id or "").strip().lower()
            for u in users:
                u_id = (getattr(u, "id", None) or "").strip().lower()
                u_name = (getattr(u, "name", None) or "").strip().lower()
                if uid and (uid == u_id or uid == u_name):
                    return (ChannelType.IM in u.permissions or len(u.permissions) == 0), u
        for user in users:
            logger.debug(f"User:  + {user}")
            if channel_type == ChannelType.Email:
                logger.debug(f"Email:  + {user.email}, email_id: {user_id}")
                if ((user_id in user.email) or (len(user.email) == 0)):
                    return (ChannelType.Email in user.permissions or len(user.permissions) == 0), user
            if channel_type == ChannelType.IM:
                if ((user_id in user.im) or (len(user.im) == 0)):
                    return (ChannelType.IM in user.permissions or len(user.permissions) == 0), user
                elif user_id  == 'homeclaw:local':
                    return True, user
            if channel_type == ChannelType.Phone:
                if ((user_id in user.phone) or (len(user.phone) == 0)):
                    return (ChannelType.Phone in user.permissions or len(user.permissions) == 0), user
        return False, None


    def start_email_channel(self):
        if self.hasEmailChannel:
            try:
                thread = threading.Thread(target=channel.main)
                thread.start()

            except Exception as e:
                logger.exception(e)

    async def _start_pinggy_and_open_browser(self):
        """If pinggy.token is set in core.yml: start tunnel in a daemon thread, set _pinggy_state when ready, optionally open browser to /pinggy."""
        global _pinggy_state
        try:
            core_yml_path = os.path.join(Util().config_path(), "core.yml")
            if not os.path.isfile(core_yml_path):
                return
            with open(core_yml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            pinggy_cfg = data.get("pinggy") or {}
            token = (pinggy_cfg.get("token") or "").strip()
            open_browser = bool(pinggy_cfg.get("open_browser", True))
            if not token:
                return
            meta = Util().get_core_metadata()
            port = int(getattr(meta, "port", 9000) or 9000)
            auth_enabled = bool(getattr(meta, "auth_enabled", False))
            auth_api_key = (getattr(meta, "auth_api_key", None) or "").strip()
            try:
                import pinggy
            except ImportError:
                _pinggy_state["error"] = "pinggy package not installed (pip install pinggy)"
                return
            tunnel = pinggy.start_tunnel(forwardto=f"127.0.0.1:{port}", token=token)

            def run_tunnel():
                try:
                    tunnel.start()
                except Exception as e:
                    _pinggy_state["error"] = str(e)

            t = threading.Thread(target=run_tunnel, daemon=True)
            t.start()
            # Poll until tunnel exposes public URL (up to 30s)
            for _ in range(30):
                await asyncio.sleep(1)
                urls = getattr(tunnel, "urls", None)
                if urls and len(urls) > 0:
                    break
            urls = getattr(tunnel, "urls", None)
            if not urls or len(urls) == 0:
                _pinggy_state["error"] = "Pinggy tunnel did not return a public URL in time"
                return
            public_url = urls[0] if isinstance(urls[0], str) else str(urls[0])
            connect_url = f"homeclaw://connect?url={public_url}"
            if auth_enabled and auth_api_key:
                connect_url += f"&api_key={auth_api_key}"
            qr_base64 = None
            try:
                import qrcode
                import io
                qr = qrcode.QRCode(version=1, box_size=6, border=2)
                qr.add_data(connect_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                qr_base64 = base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception as e:
                logger.debug("QR code generation skipped: {}", e)
            _pinggy_state["public_url"] = public_url
            _pinggy_state["connect_url"] = connect_url
            _pinggy_state["qr_base64"] = qr_base64
            _pinggy_state["error"] = None
            try:
                from core.result_viewer import set_runtime_public_url
                set_runtime_public_url(public_url)
            except Exception:
                pass
            if open_browser:
                webbrowser.open(f"http://127.0.0.1:{port}/pinggy")
        except Exception as e:
            logger.exception(e)
            _pinggy_state["error"] = str(e)

    async def run(self):
        """Run the core using uvicorn"""
        try:
            # On Windows you may see "Task was destroyed but it is pending! task: ... IocpProactor.accept ..." at startup. This is a known asyncio/Proactor quirk: an accept coroutine can be reported as pending during init. It is harmless and the server runs normally; you can ignore it.
            logger.debug("core is running!")
            # Periodic wakeup so the event loop can process signals (e.g. Ctrl+C). Required on Windows;
            # harmless on macOS/Linux. Shorter interval (0.2s) improves responsiveness on Windows.
            _loop = asyncio.get_running_loop()
            _wakeup_interval = 0.2
            def _wakeup():
                _loop.call_later(_wakeup_interval, _wakeup)
            _loop.call_later(_wakeup_interval, _wakeup)
            core_metadata: CoreMetadata = Util().get_core_metadata()
            logger.debug(f"Running core on {core_metadata.host}:{core_metadata.port}")
            # Suppress access log for GET /api/config/core (Companion connection checks every 30s)
            _uvicorn_access = logging.getLogger("uvicorn.access")
            if not any(isinstance(f, _SuppressConfigCoreAccessFilter) for f in _uvicorn_access.filters):
                _uvicorn_access.addFilter(_SuppressConfigCoreAccessFilter())
            config = uvicorn.Config(self.app, host=core_metadata.host, port=core_metadata.port, log_level="critical", access_log=False)
            self.server = Server(config=config)
            # Start HTTP server early so GET /ready is served by this process (avoids 502 from another process on same port). /ready returns 503 until init done.
            server_task = asyncio.create_task(self.server.serve())
            await asyncio.sleep(0.5)
            # Start embedding (and main LLM) server before initializing Cognee.
            logger.debug("Starting LLM manager (embedding + main LLM)...")
            self.llmManager.run()
            logger.debug("LLM manager started!")
            # When embedding is local, wait for the embedding server BEFORE initialize() so Cognee (and other init) does not block waiting for embedding. Cognee may wait for embedding to be ready during CogneeMemory(config=...).
            need_embedder = (
                (getattr(core_metadata, "memory_backend", None) or "cognee").strip().lower() == "cognee"
                or getattr(core_metadata, "skills_use_vector_search", False)
                or getattr(core_metadata, "plugins_use_vector_search", False)
                or getattr(core_metadata, "use_agent_memory_search", True)
            )
            if need_embedder and Util()._effective_embedding_llm_type() == "local":
                try:
                    logger.debug("Waiting for embedding server before init (Cognee/skills/plugins need it)...")
                    ready = await asyncio.to_thread(Util().check_embedding_model_server_health, None)
                    if not ready:
                        logger.warning("Embedding server did not become ready in time; Cognee memory and skills/plugins/agent_memory sync may fail.")
                    else:
                        logger.debug("Embedding server ready.")
                except Exception as e:
                    logger.warning("Embedding server health check failed: {}; Cognee/sync may fail.", e)
            self.initialize()
            self.start_email_channel()

            # Sync skills to vector store when skills_use_vector_search and skills_refresh_on_startup
            if getattr(core_metadata, "skills_use_vector_search", False) and getattr(core_metadata, "skills_refresh_on_startup", True):
                if getattr(self, "skills_vector_store", None) and getattr(self, "embedder", None):
                    from base.skills import get_skills_dir, sync_skills_to_vector_store
                    root = Path(__file__).resolve().parent.parent
                    skills_path = get_skills_dir(getattr(core_metadata, "skills_dir", None), root=root)
                    skills_test_dir_str = (getattr(core_metadata, "skills_test_dir", None) or "").strip()
                    skills_test_path = get_skills_dir(skills_test_dir_str, root=root) if skills_test_dir_str else None
                    skills_extra_raw = getattr(core_metadata, "skills_extra_dirs", None) or []
                    skills_extra_paths = [root / p if not Path(p).is_absolute() else Path(p) for p in skills_extra_raw if (p or "").strip()]
                    disabled_folders = getattr(core_metadata, "skills_disabled", None) or []
                    incremental = bool(getattr(core_metadata, "skills_incremental_sync", False))
                    try:
                        n = await sync_skills_to_vector_store(
                            skills_path, self.skills_vector_store, self.embedder,
                            skills_test_dir=skills_test_path, incremental=incremental,
                            skills_extra_dirs=skills_extra_paths if skills_extra_paths else None,
                            disabled_folders=disabled_folders if disabled_folders else None,
                        )
                        _component_log("skills", f"synced {n} skill(s) to vector store")
                    except Exception as e:
                        logger.warning("Skills vector sync failed: {}", e)

            # Load plugins (orchestrator/TAM/plugins always enabled)
            self.load_plugins()
            n_plugins = self.plugin_manager.num_plugins()
            _component_log("plugin", f"loaded {n_plugins} plugin(s)")
            self.plugin_manager.run()
            self.start_hot_reload()

            # Sync plugins to vector store when plugins_use_vector_search and plugins_refresh_on_startup (same design as skills)
            if getattr(core_metadata, "plugins_use_vector_search", False) and getattr(core_metadata, "plugins_refresh_on_startup", True):
                if getattr(self, "plugins_vector_store", None) and getattr(self, "embedder", None):
                    from base.plugins_registry import sync_plugins_to_vector_store
                    regs = getattr(self.plugin_manager, "get_plugin_registrations_for_sync", lambda: [])()
                    if regs:
                        try:
                            n = await sync_plugins_to_vector_store(
                                regs, self.plugins_vector_store, self.embedder,
                            )
                            _component_log("plugin", f"synced {n} plugin(s) to vector store")
                        except Exception as e:
                            logger.warning("Plugins vector sync failed: {}", e)

            # Sync agent memory (AGENT_MEMORY + daily markdown) to vector store when use_agent_memory_search. Index global + per-user when multiple users.
            if getattr(core_metadata, "use_agent_memory_search", True):
                if getattr(self, "agent_memory_vector_store", None) and getattr(self, "embedder", None):
                    from base.workspace import get_workspace_dir
                    from base.agent_memory_index import sync_agent_memory_to_vector_store
                    ws_dir = get_workspace_dir(getattr(core_metadata, "workspace_dir", None) or "config/workspace")
                    try:
                        users = Util().get_users() or []
                        system_user_ids = [None] + [
                            getattr(u, "id", None) or getattr(u, "name", None)
                            for u in users
                            if getattr(u, "id", None) or getattr(u, "name", None)
                        ]
                    except Exception:
                        system_user_ids = [None]
                    try:
                        n = await sync_agent_memory_to_vector_store(
                            workspace_dir=Path(ws_dir),
                            agent_memory_path=(getattr(core_metadata, "agent_memory_path", None) or "").strip() or None,
                            daily_memory_dir=(getattr(core_metadata, "daily_memory_dir", None) or "").strip() or None,
                            vector_store=self.agent_memory_vector_store,
                            embedder=self.embedder,
                            system_user_ids=system_user_ids,
                        )
                        _component_log("agent_memory", f"synced {n} chunk(s) to vector store")
                    except Exception as e:
                        logger.warning("Agent memory vector sync failed: {}", e)

            # Create per-user and shared sandbox folders (private, output, knowledgebase, share, companion) when homeclaw_root is set in config
            root_str = (getattr(core_metadata, "homeclaw_root", None) or "").strip() if core_metadata else ""
            if root_str:
                try:
                    users = Util().get_users() or []
                    user_ids = [
                        (getattr(u, "id", None) or getattr(u, "name", None) or "")
                        for u in users
                        if getattr(u, "id", None) or getattr(u, "name", None)
                    ]
                    user_ids = [uid for uid in user_ids if str(uid).strip()]
                    ensure_user_sandbox_folders(root_str, user_ids)
                    from tools.builtin import build_and_save_sandbox_paths_json
                    build_and_save_sandbox_paths_json()
                except Exception as e:
                    logger.debug("ensure_user_sandbox_folders / sandbox_paths at startup: {}", e)

            # File serving: sandbox files and folder listings at GET /files/out (core_public_url/files/out?path=...&token=...)
            if (getattr(core_metadata, "core_public_url", None) or "").strip():
                _component_log("files", "serving sandbox files at GET /files/out (core_public_url set)")
            self._core_http_ready = True
            # LLM manager (embedding + main LLM) was started earlier, before skills/plugins/agent_memory sync.
            # Optionally start and register system_plugins (e.g. homeclaw-browser) so one command runs Core + plugins.
            # GET /ready now returns 200 so probe will succeed.
            if getattr(core_metadata, "system_plugins_auto_start", False):
                asyncio.create_task(self._run_system_plugins_startup())
            # Pinggy: only when pinggy.token is set — start tunnel and optionally open browser to /pinggy (public URL + QR). If neither core_public_url nor token is set, we just run Core and do not pop up QR.
            try:
                core_yml_path = os.path.join(Util().config_path(), "core.yml")
                if os.path.isfile(core_yml_path):
                    with open(core_yml_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    pinggy_cfg = data.get("pinggy") or {}
                    token = (pinggy_cfg.get("token") or "").strip()
                    if token:
                        asyncio.create_task(self._start_pinggy_and_open_browser())
            except Exception:
                pass
            # Keep running until server stops (server was started early so /ready is served during init)
            await server_task

        except asyncio.CancelledError:
            logger.debug("core uvicorn server was cancelled.")
            sys.exit(0)


        except Exception as e:
            logger.exception(e)
            sys.exit(0)


    def stop(self):
        self.shutdown_all_channels()
        self.llmManager.stop_all_llama_cpp_processes()
        # do some deinitialization here
        #logger.debug("core is stopping!")
        self.llmManager.stop_all_apps()
        #logger.debug("LLM apps are stopped!")

        if getattr(self, "plugin_manager", None):
            self.plugin_manager.deinitialize_plugins()
        #logger.debug("Plugins are deinitialized!")
        for proc in getattr(self, "_system_plugin_processes", []) or []:
            try:
                if proc.returncode is None:
                    proc.terminate()
            except Exception:
                pass
        self._system_plugin_processes = []
        self.stop_chroma_client()

        def shutdown():
            try:
                #asyncio.run(Util().stop_uvicorn_server(self.server))
                Util().stop_uvicorn_server(self.server)
            except Exception as e:
                #logger.exception(e)
                pass

        thread = threading.Thread(target=shutdown)
        thread.start()
        #thread.join()
        #logger.debug("Uvicorn server is stopped!")

    def register_channel(self, name: str, host: str, port: str, endpoints: list):
        channel = {
            "name": name,
            "host": host,
            "port": port,
            "endpoints": endpoints
        }
        for  channel in self.channels:
            if channel["host"] == host and channel["port"] == port:
                return
        self.channels.append(channel)


    def deregister_channel(self, name: str, host: str, port: str, endpoints: list):
        for channel in self.channels:
            if channel["name"] == name and channel["host"] == host and channel["port"] == port and channel["endpoints"] == endpoints:
                self.channels.remove(channel)
                logger.debug(f"Channel {name} is deregistered from {host}:{port}")
                return


    def shutdown_channel(self, name: str, host: str, port: str):
        for channel in self.channels:
            if channel["name"] == name and channel["host"] == host and channel["port"] == port:
                with httpx.Client() as client:
                    client.get(f"http://{host}:{port}/shutdown")

                self.channels.remove(channel)
                logger.debug(f"Channel {name} is deregistered from {host}:{port}")
                return


    def shutdown_all_channels(self):
        for channel in self.channels:
            try:
                self.shutdown_channel(channel["name"], channel["host"], channel["port"])
                #logger.debug(f"Channel {channel['name']} is shutdown from {channel['host']}:{channel['port']}")
            except Exception as e:
                continue
        #logger.debug("All channels are shutdown!")


    def start_chroma_client(self):
        metadata = Util().get_core_metadata()
        db = metadata.vectorDB.Chroma
        path = (getattr(db, "path", None) or "").strip() or Util().data_path()
        settings = chromadb.config.Settings(anonymized_telemetry=getattr(db, "anonymized_telemetry", False))
        settings.persist_directory = path
        settings.is_persistent = True
        client = chromadb.Client(settings=settings)
        logger.debug("ChromaDB client created")
        return client


    def stop_chroma_client(self):
        #self.chromra_memory_client.()
        logger.debug("ChromaDB client disconnected")

    '''
    def start_chroma_server(self):
        db = self.metadata.vectorDB['Chroma']
        args = [
            "chroma-server",
            "--host", db.host,
            "--port", str(db.port),
            "--api", db.api,
            "--persist", db.persist_path,
            "--is-persistent", str(db.is_persistent).lower(),
            "--anonymized-telemetry", str(db.anonymized_telemetry).lower()
        ]
        logger.debug(f"args: {args}")
        try:
            self.chroma_server_process = subprocess.Popen(args)
        except Exception as e:
            logger.exception(f"Failed to start Chroma server: {e}")
            raise
        logger.debug(f"ChromaDB server started on {db.host}:{db.port}")
        return self.chroma_server_process


    def shutdown_chroma_server(self):
        if self.chroma_server_process:
            self.chroma_server_process.terminate()
            self.chroma_server_process.wait()
            logger.debug("ChromaDB server has been terminated.")
    '''


    async def openai_chat_completion(self, messages: list[dict],
                                     grammar: str=None,
                                     tools: Optional[List[Dict]] = None,
                                     tool_choice: str = "auto",
                                     llm_name: str = None) -> str | None:
        try:
            resp = await Util().openai_chat_completion(messages, grammar, tools, tool_choice, llm_name=llm_name)
            return resp
        except Exception as e:
            logger.exception(e)
            return None


    def extract_json_str(self, response) -> str:
        # Allow {} to be matched in response
        # This regular expression pattern matches all JSON-like strings in the response.
        # The pattern is explained in the following steps:
        # 1. The pattern starts with a left curly brace "{" and matches any character (except newline) zero or more times.
        #    The "?" after "*" makes the match non-greedy, meaning it will match as few characters as possible.
        # 2. The pattern ends with a right curly brace "}" and matches any character (except newline) zero or more times.
        #    The "?" after "*" makes the match non-greedy, meaning it will match as few characters as possible.
        # 3. The pattern uses a negative lookbehind "(?<!\\)" to ensure that the left curly brace "{" is not preceded by a backslash.
        #    This ensures that the pattern does not match escaped curly braces "{\\}".
        # 4. The pattern uses a negative lookbehind "(?<!\\)" to ensure that the right curly brace "}" is not preceded by a backslash.
        #    This ensures that the pattern does not match escaped curly braces "\}{".
        # 5. The pattern is compiled with the flag "re.DOTALL" to allow the dot "." to match any character, including newline.
        #    This ensures that the pattern can match multiline JSON strings.
        json_pattern = re.compile(r'''
            (?<!\\)         # Negative lookbehind for a backslash (to avoid escaped braces)
            (\{             # Match the opening brace and start capturing
                [^{}]*      # Match any character except braces
                (?:         # Non-capturing group for nested braces
                    (?:     # Non-capturing group for repeated patterns
                        [^{}]   # Match any character except braces
                        |       # OR
                        \{[^{}]*\}  # Match nested braces
                    )*          # Zero or more times
                )*          # Zero or more times
            \})             # Match the closing brace and end capturing
        ''', re.VERBOSE | re.DOTALL)
        matches = json_pattern.findall(response)

        if matches:
            return matches[0]
        return response


    def extract_tuple_str(self, response):
        # Define the refined pattern to match one or more capability items
        pattern = re.compile(
            r"\(\{\{'capabilities':.*?, 'score':.*?, 'can_solve':.*?\}\}(?:, \{\{'capabilities':.*?, 'score':.*?, 'can_solve':.*?\}\})*\)"
        )
        matches = pattern.findall(response)
        if matches:
            return matches[0]
        return response

    async def openai_completion(self, prompt: str, llm_name: str = "") -> str | None:
        try:
            llm = Util().get_llm(llm_name)
            model_host = llm.host
            model_port = llm.port
            model = llm.path

            data = {
                "model": model,
                "prompt": prompt,
                "n": 1,
            }
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Anything'
            }
            data_json = json.dumps(data, ensure_ascii=False).encode('utf-8')

            completion_api_url = 'http://' + model_host + ':' + str(model_port) + '/v1/completions'
            logger.debug(f"completion_api_url: {completion_api_url}")
            async with aiohttp.ClientSession() as session:
                async with session.post(completion_api_url, headers=headers, data=data_json) as resp:
                    ret = (await resp.json())
                    logger.debug(f"Resp: {ret}")
                    resp = ret['content']
                    logger.debug(f"Resp: {resp}")
                    ret = self.extract_json_str(resp)
                    return ret
                    #return (ret)['choices'][0]['text']
        except Exception as e:
            logger.exception(e)
            return None


    async def answer_from_memory(self,
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
                                 # soon to be deprecated params by OpenAI
                                 functions: Optional[List] = None,
                                 function_call: Optional[str] = None,
                                 host: Optional[str] = None,
                                 port: Optional[int] = None,
                                 request: Optional[PromptRequest] = None,
                                 ):
        if not any([user_name, user_id, agent_id, run_id]):
            raise ValueError("One of user_name, user_id, agent_id, run_id must be provided")
        try:
            # If user is replying to a "missing parameters" question, fill and retry the pending plugin call
            app_id_val = app_id or "homeclaw"
            user_id_val = user_id or ""
            session_id_val = session_id or ""
            pending = self.get_pending_plugin_call(app_id_val, user_id_val, session_id_val)
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
                    plugin_manager = getattr(self, "plugin_manager", None)
                    plugin = plugin_manager.get_plugin_by_id(plugin_id) if plugin_manager else None
                    if plugin and isinstance(plugin, dict) and request:
                        self.clear_pending_plugin_call(app_id_val, user_id_val, session_id_val)
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
                            self.set_pending_plugin_call(app_id_val, user_id_val, session_id_val, pending)
                    elif not plugin:
                        self.clear_pending_plugin_call(app_id_val, user_id_val, session_id_val)

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
                route_score = 0.0
                # Layer 1: heuristic (keywords, long-input); no threshold—first match wins when enabled
                heuristic_cfg = hr.get("heuristic") if isinstance(hr.get("heuristic"), dict) else {}
                h_enabled = bool(heuristic_cfg.get("enabled", False))
                if h_enabled:
                    from hybrid_router.heuristic import load_heuristic_rules, run_heuristic_layer
                    root_dir = Path(__file__).resolve().parent.parent
                    rules_path = (heuristic_cfg.get("rules_path") or "").strip()
                    rules_data = load_heuristic_rules(rules_path, root_dir=root_dir) if rules_path else None
                    score, selection = run_heuristic_layer(query or "", rules_data, enabled=h_enabled)
                    if selection:
                        route = selection
                        route_layer = "heuristic"
                        route_score = score
                # Layer 2: semantic (aurelio-labs/semantic-router + existing embedding). Only accepts when similarity_score >= threshold; otherwise falls through to Layer 3.
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
                # Optional: long queries use default_route and skip perplexity (avoids local overconfidence on complex prompts)
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
            try:
                if _sys_uid:
                    _users = Util().get_users() or []
                    _current_user_for_identity = next(
                        (u for u in _users if (getattr(u, "id", None) or getattr(u, "name", "") or "").strip().lower() == str(_sys_uid or "").strip().lower()),
                        None,
                    )
                    if _current_user_for_identity and str(getattr(_current_user_for_identity, "type", "normal") or "normal").strip().lower() == "companion":
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

            # Companion identity (who): when companion-type user has "who", inject a single identity from who (pre-defined template; no LLM). Replaces default assistant description; all other behavior (memory, chat, KB) same as normal user.
            if _companion_with_who and _current_user_for_identity:
                try:
                    _who = getattr(_current_user_for_identity, "who", None)
                    if isinstance(_who, dict) and _who:
                        _lines = ["## Identity\n"]
                        _desc = (_who.get("description") or "").strip() if isinstance(_who.get("description"), str) else ""
                        if _desc:
                            _lines.append(_desc)
                        _name = getattr(_current_user_for_identity, "name", "") or _sys_uid or ""
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
                        _lines.append("Stay in character and chat as a human would: natural, conversational, and in-person. Do not say you are an AI, assistant, or language model; do not break character to explain how you work. Reply only as this person would reply.")
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
                ctx_line = f"Current date: {date_str}. Day of week: {dow}. Current time: {time_24} (24-hour, system local)."
                self._request_current_time_24 = time_24  # so routing block can inject it; model must use this, not invent 2:49 etc.
                loc_str = None
                try:
                    meta = request.request_metadata if getattr(request, "request_metadata", None) else {}
                    loc_str = (meta.get("location") or "").strip() if isinstance(meta, dict) else None
                    if not loc_str and user_id:
                        loc_str = self._get_latest_location(user_id)
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
                        shared_key = getattr(self, "_LATEST_LOCATION_SHARED_KEY", "companion")
                        loc_str = self._get_latest_location(shared_key)
                    if loc_str:
                        ctx_line += f" User location: {loc_str[:500]}."
                except Exception as e:
                    logger.debug("System context location resolve: {}", e)
                ctx_line += "\nCritical for cron jobs and reminders: this current datetime is the single source of truth. The server uses it when scheduling; you must use it for all time calculations. Do not use any other time (e.g. from memory or prior turns—they may be outdated). Use this block only when the user explicitly asks (e.g. \"what day is it?\", \"what time is it?\", scheduling with remind_me, record_date, cron_schedule). Do not volunteer date/time in greetings. For reminders and cron: use ONLY the Current time above; do not invent or guess any time. If the user says \"in N minutes\", reminder time = Current time + N minutes (e.g. Current time 17:58 + 30 min = 18:28)."
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
                            parts_bootstrap = []
                            if use_agent_file:
                                agent_raw = load_agent_memory_file(
                                    workspace_dir=ws_dir,
                                    agent_memory_path=getattr(meta_mem, "agent_memory_path", None) or None,
                                    max_chars=0,
                                    system_user_id=_sys_uid,
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
                        agent_content = load_agent_memory_file(
                            workspace_dir=ws_dir, agent_memory_path=agent_path or None, max_chars=max_chars, system_user_id=_sys_uid_legacy
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
                        daily_content = load_daily_memory_for_dates(
                            [yesterday, today],
                            workspace_dir=ws_dir,
                            daily_memory_dir=daily_dir if daily_dir else None,
                            max_chars=80_000,
                            system_user_id=_sys_uid_daily,
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
                    if not skills_list and use_vector_search and getattr(self, 'skills_vector_store', None) and getattr(self, 'embedder', None):
                        from base.skills import search_skills_by_query, load_skill_by_folder, TEST_ID_PREFIX
                        max_retrieved = max(1, min(100, int(getattr(meta_skills, 'skills_max_retrieved', 10) or 10)))
                        threshold = float(getattr(meta_skills, 'skills_similarity_threshold', 0.0) or 0.0)
                        hits = await search_skills_by_query(
                            self.skills_vector_store, self.embedder, query or "",
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
                                    self.skills_vector_store.delete(hit_id)
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
                relevant_memories = await self._fetch_relevant_memories(query,
                    messages, user_name, user_id, agent_id, run_id, filters, 10
                )
                memories_text = ""
                if relevant_memories:
                    i = 1
                    for memory in relevant_memories:
                        memories_text += (str(i) + ": " + memory["memory"] + " ")
                        logger.debug(f"RelevantMemory: {str(i) } ': ' {memory['memory']}")
                        i += 1
                else:
                    memories_text = ""
                context_val = memories_text if memories_text else "None."
                # Optional: inject knowledge base (documents, web, URLs) — only chunks that pass threshold; none is fine
                kb = getattr(self, "knowledge_base", None)
                meta = Util().get_core_metadata()
                kb_cfg = getattr(meta, "knowledge_base", None) or {}
                if kb and (user_id or user_name):
                    try:
                        kb_timeout = 10
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
                # Per-user profile: inject "About the user" when enabled (docs/UserProfileDesign.md)
                meta = Util().get_core_metadata()
                profile_cfg = getattr(meta, "profile", None) or {}
                if profile_cfg.get("enabled", True) and (user_id or user_name):
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
            if unified and getattr(self, "plugin_manager", None):
                plugin_list = []
                meta_plugins = Util().get_core_metadata()
                use_plugin_vector_search = bool(getattr(meta_plugins, "plugins_use_vector_search", False))
                if not use_plugin_vector_search:
                    # plugins_use_vector_search=false → include ALL plugins (no RAG, no cap)
                    plugin_list = getattr(self.plugin_manager, "get_plugin_list_for_prompt", lambda: [])()
                    if plugin_list:
                        _component_log("plugin", f"included all {len(plugin_list)} plugin(s) (plugins_use_vector_search=false)")
                if use_plugin_vector_search and getattr(self, "plugins_vector_store", None) and getattr(self, "embedder", None):
                    from base.plugins_registry import search_plugins_by_query
                    max_retrieved = max(1, min(100, int(getattr(meta_plugins, "plugins_max_retrieved", 10) or 10)))
                    threshold = float(getattr(meta_plugins, "plugins_similarity_threshold", 0.0) or 0.0)
                    try:
                        hits = await search_plugins_by_query(
                            self.plugins_vector_store, self.embedder, query or "",
                            limit=max_retrieved, min_similarity=threshold,
                        )
                        desc_max_rag = max(0, int(getattr(meta_plugins, "plugins_description_max_chars", 0) or 0))
                        for hit_id, _ in hits:
                            plug = self.plugin_manager.get_plugin_by_id(hit_id)
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
                    plugin_list = getattr(self.plugin_manager, "get_plugin_list_for_prompt", lambda: [])()
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
                            plug = self.plugin_manager.get_plugin_by_id(pid)
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
                        plug = self.plugin_manager.get_plugin_by_id(pid)
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
                _req_time_24 = getattr(self, "_request_current_time_24", "") or ""
                routing_block = (
                    "## Routing (choose one)\n"
                    "Do NOT use route_to_tam for: opening URLs, listing nodes, canvas, camera/video on a node, or any non-scheduling request. Use route_to_plugin for those.\n"
                    "Recording a video or taking a photo on a node (e.g. \"record video on test-node-1\", \"take a photo on test-node-1\") -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=node_camera_clip or node_camera_snap, parameters={\"node_id\": \"<node_id>\"}; for clip add duration and includeAudio). Do NOT use browser_navigate for node ids; test-node-1 is a node id, not a URL.\n"
                    "Opening a URL in a browser (real web URLs only, e.g. https://example.com) -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=browser_navigate, parameters={\"url\": \"<URL>\"}). Node ids like test-node-1 are NOT URLs.\n"
                    "Listing connected nodes or \"what nodes are connected\" -> route_to_plugin(plugin_id=homeclaw-browser, capability_id=node_list).\n"
                    "If the request clearly matches one of the available plugins below, call route_to_plugin with that plugin_id (and capability_id/parameters when relevant).\n"
                    "For time-related requests only: one-shot reminders -> remind_me(minutes or at_time, message); recording a date/event -> record_date(event_name, when); recurring -> cron_schedule(cron_expr, message). Use route_to_tam only when the user clearly asks to schedule or remind (e.g. \"remind me in 5 minutes\", \"every day at 9am\").\n"
                    f"When the user asks to be reminded in N minutes (e.g. \"30分钟后提醒我\", \"remind me in 30 minutes\", \"我30分钟后有个会能提醒一下吗\"), you MUST call the remind_me tool with minutes=N (use the number from the user's message; 30分钟后 = 30 minutes) and message= a short reminder text. Do NOT reply with text-only or fake JSON; always call remind_me so the reminder is actually scheduled. The current time for this request is {_req_time_24}. Use only this time in your reply; never output 2:49 PM or any other invented time—if current time is {_req_time_24} and user says 15 minutes, add 15 to the minutes part and say that time or \"in 15 minutes\".\n"
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
            if getattr(self, "orchestratorInst", None) and getattr(self.orchestratorInst, "tam", None):
                tam = self.orchestratorInst.tam
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
                                    core=self,
                                    app_id=app_id or "homeclaw",
                                    user_name=user_name,
                                    user_id=user_id,
                                    system_user_id=getattr(request, "system_user_id", None) or user_id,
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
                    core=self,
                    app_id=app_id or "homeclaw",
                    user_name=user_name,
                    user_id=user_id,
                    system_user_id=getattr(request, "system_user_id", None) or user_id,
                    session_id=session_id,
                    run_id=run_id,
                    request=request,
                )
                current_messages = list(llm_input)
                max_tool_rounds = 10
                use_other_model_next_turn = False  # mix mode: when last tool result was error-like, use cloud (or local) for next turn
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
                                elif _has_remind_me:
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
                                                    response = await self.openai_chat_completion(summary_messages, llm_name=effective_llm_name)
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
                    last_tool_name = None  # for _tool_result_usable_as_final_response: skip second LLM when tool result is self-contained
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
                    # Skip second LLM when tool result is self-contained (deterministic check, no LLM). Config: tools.use_result_as_response.
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
                response = await self.openai_chat_completion(
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
                            response = await self.openai_chat_completion(messages=llm_input, llm_name=other_llm)
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
            self.chatDB.add(app_id=app_id, user_name=user_name, user_id=user_id, session_id=session_id, chat_message=message)
            # Session pruning: optionally keep only last N turns per session after each reply
            session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
            if session_cfg.get("prune_after_turn") and app_id and user_id and session_id:
                keep_n = max(10, int(session_cfg.get("prune_keep_last_n", 50) or 50))
                try:
                    pruned = self.prune_session_transcript(app_id=app_id, user_name=user_name, user_id=user_id, session_id=session_id, keep_last_n=keep_n)
                    if pruned > 0:
                        _component_log("session", f"pruned {pruned} old turns, kept last {keep_n}")
                except Exception as e:
                    logger.debug("Session prune after turn failed: {}", e)
            #if use_memory:
            #    await self.mem_instance.add(query, user_name=user_name, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata, filters=filters)

            return response
        except Exception as e:
            logger.exception(e)
            return None


    def add_chat_history(self, user_message: str, ai_message: str, app_id: Optional[str] = None, user_name: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None):
        try:
            message: ChatMessage = ChatMessage()
            message.add_user_message(user_message)
            message.add_ai_message(ai_message)
            self.chatDB.add(app_id=app_id, user_name=user_name, user_id=user_id, session_id=session_id, chat_message=message)
        except Exception as e:
            logger.exception(e)

    def get_sessions(
        self,
        app_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        num_rounds: int = 50,
        fetch_all: bool = False,
    ) -> list:
        """Return list of sessions (app_id, user_name, user_id, session_id, created_at). For tools/sessions_list."""
        return self.chatDB.get_sessions(
            app_id=app_id,
            user_name=user_name,
            user_id=user_id,
            session_id=session_id,
            num_rounds=num_rounds,
            fetch_all=fetch_all,
        )

    async def send_message_to_session(
        self,
        message: str,
        session_id: Optional[str] = None,
        app_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ) -> Optional[str]:
        """
        Inject a message into another session and return that session's agent reply.
        For sessions_send tool. Target by session_id, or by (app_id, user_id).
        Does not change latestPromptRequest; the reply is returned to the caller.
        """
        target_app_id = app_id
        target_user_id = user_id
        target_user_name = user_name
        if session_id:
            sessions = self.get_sessions(session_id=session_id, num_rounds=1)
            if not sessions:
                logger.warning(f"send_message_to_session: no session found for session_id={session_id}")
                return None
            row = sessions[0]
            target_app_id = row.get("app_id")
            target_user_id = row.get("user_id")
            target_user_name = target_user_name or row.get("user_name") or target_user_id
        if not target_app_id or not target_user_id:
            logger.warning("send_message_to_session: need session_id or (app_id, user_id)")
            return None
        target_user_name = target_user_name or target_user_id
        req_id = str(datetime.now().timestamp())
        pr = PromptRequest(
            request_id=req_id,
            channel_name="sessions_send",
            request_metadata={"source": "sessions_send", "target_session_id": session_id},
            channelType=ChannelType.IM,
            user_name=target_user_name,
            app_id=target_app_id,
            user_id=target_user_id,
            contentType=ContentType.TEXT,
            text=message,
            action="respond",
            host="internal",
            port=0,
            images=[],
            videos=[],
            audios=[],
            timestamp=datetime.now().timestamp(),
        )
        try:
            if timeout_seconds and timeout_seconds > 0:
                reply = await asyncio.wait_for(
                    self.process_text_message(pr),
                    timeout=timeout_seconds,
                )
            else:
                reply = await self.process_text_message(pr)
            return reply
        except asyncio.TimeoutError:
            logger.warning(f"send_message_to_session timed out after {timeout_seconds}s")
            return None
        except Exception as e:
            logger.exception(e)
            return None

    def get_session_transcript(
        self,
        app_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
        fetch_all: bool = False,
    ) -> list:
        """
        Return session transcript as list of { "role": "user"|"assistant", "content": str, "timestamp": str }.
        See Comparison.md §7.4 — session transcript as first-class artifact.
        """
        return self.chatDB.get_transcript(
            app_id=app_id,
            user_name=user_name,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            fetch_all=fetch_all,
        )

    def get_session_transcript_jsonl(
        self,
        app_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
        fetch_all: bool = False,
    ) -> str:
        """
        Return session transcript as JSONL (one JSON object per line). For export or session transcript.
        See Comparison.md §7.6 — transcript (e.g. JSONL) per session.
        """
        return self.chatDB.get_transcript_jsonl(
            app_id=app_id,
            user_name=user_name,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            fetch_all=fetch_all,
        )

    def prune_session_transcript(
        self,
        app_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        keep_last_n: int = 50,
    ) -> int:
        """
        Prune session transcript: delete old turns, keeping only the last keep_last_n turns.
        Returns the number of rows deleted. See Comparison.md §7.6 — transcript may be pruned.
        """
        return self.chatDB.prune_session(
            app_id=app_id,
            user_name=user_name,
            user_id=user_id,
            session_id=session_id,
            keep_last_n=keep_last_n,
        )

    async def summarize_session_transcript(
        self,
        app_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> Optional[str]:
        """
        Summarize the session transcript using the main LLM. Returns a short summary string.
        See Comparison.md §7.6 — transcript may be summarized.
        """
        transcript = self.get_session_transcript(
            app_id=app_id,
            user_name=user_name,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            fetch_all=False,
        )
        if not transcript:
            return None
        lines = []
        for turn in transcript:
            role = turn.get("role", "user")
            content = (turn.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        if not lines:
            return None
        conversation_text = "\n".join(lines)
        system_prompt = "Summarize the following conversation in a few sentences. Be concise."
        user_prompt = f"Conversation:\n\n{conversation_text}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        summary = await self.openai_chat_completion(messages=messages)
        return summary.strip() if summary else None

    def add_chat_history_by_role(self, sender_name, responder_name, sender_text, responder_text):
        return self.chatDB.add_by_role(sender_name, responder_name, sender_text, responder_text)


    async def add_user_input_to_memory(self, user_input:str, user_name: Optional[str] = None, user_id: Optional[str] = None, agent_id: Optional[str] = None, run_id: Optional[str] = None, metadata: Optional[dict] = None, filters: Optional[dict] = None):
        try:
            await self.mem_instance.add(user_input, user_name=user_name, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata, filters=filters)
        except Exception as e:
            logger.exception(e)

    async def sync_user_kb_folder(self, user_id: str) -> Dict[str, Any]:
        """
        Sync the user's knowledge base folder to the KB: add new/changed files, remove when file deleted.
        source_id for folder files = "folder/" + relative path. Never raises; returns {ok, message, added, removed, errors}.
        """
        out = {"ok": False, "message": "", "added": 0, "removed": 0, "errors": []}
        try:
            meta = Util().get_core_metadata()
            kb_cfg = getattr(meta, "knowledge_base", None) or {}
            if not isinstance(kb_cfg, dict):
                kb_cfg = {}
            fs_cfg = kb_cfg.get("folder_sync") or {}
            if not isinstance(fs_cfg, dict) or not fs_cfg.get("enabled"):
                out["message"] = "folder_sync is disabled or not configured."
                return out
            kb = getattr(self, "knowledge_base", None)
            if kb is None:
                out["message"] = "Knowledge base not initialized."
                return out
            root = (meta.get_homeclaw_root() or "").strip()
            if not root:
                out["message"] = "homeclaw_root not set; cannot sync folder."
                return out
            folder_name = (fs_cfg.get("folder_name") or "knowledgebase").strip() or "knowledgebase"
            kb_dir = get_user_knowledgebase_dir(root, user_id, folder_name)
            if kb_dir is None or not kb_dir.is_dir():
                out["ok"] = True
                out["message"] = "User knowledge base folder does not exist or is not a directory."
                return out
            allowed = fs_cfg.get("allowed_extensions") or [".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".rst", ".csv", ".ppt", ".pptx"]
            if not isinstance(allowed, list):
                allowed = [".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".rst", ".csv", ".ppt", ".pptx"]
            allowed_set = {str(e).strip().lower() for e in allowed if e}
            max_bytes = max(0, int(fs_cfg.get("max_file_size_bytes", 5_000_000) or 5_000_000))
            resync = bool(fs_cfg.get("resync_on_mtime_change", True))

            # List current KB sources that are from folder (source_id starts with "folder/")
            try:
                all_sources = await kb.list_sources(user_id, limit=1000)
            except Exception as e:
                out["message"] = f"list_sources failed: {e}"
                out["errors"].append(str(e))
                return out
            folder_source_ids = {s["source_id"]: s for s in (all_sources or []) if (s.get("source_id") or "").startswith("folder/")}

            # Remove from KB when file no longer exists
            for sid in list(folder_source_ids.keys()):
                rel = sid[7:] if len(sid) > 7 else ""  # "folder/" prefix
                if not rel:
                    continue
                full = (kb_dir / rel).resolve()
                try:
                    if not full.is_file():
                        try:
                            msg = await kb.remove_by_source_id(user_id, sid)
                            if "Error" not in str(msg):
                                out["removed"] += 1
                        except Exception as e:
                            out["errors"].append(f"remove {sid}: {e}")
                except Exception:
                    pass

            # List files on disk (one level; use path relative to kb_dir)
            files_on_disk = []
            try:
                for p in kb_dir.iterdir():
                    if not p.is_file():
                        continue
                    suf = p.suffix.lower()
                    if suf not in allowed_set:
                        continue
                    try:
                        if p.stat().st_size > max_bytes:
                            continue
                    except OSError:
                        continue
                    rel = str(p.relative_to(kb_dir)).replace("\\", "/")
                    source_id = "folder/" + rel
                    files_on_disk.append((p, rel, source_id))
            except Exception as e:
                out["message"] = f"listdir failed: {e}"
                out["errors"].append(str(e))
                return out

            # Add or update each file
            from base.file_understanding import extract_document_text
            base_str = str(kb_dir.resolve())
            for p, rel, source_id in files_on_disk:
                try:
                    if source_id not in folder_source_ids and not resync:
                        # already in KB and we're not resyncing
                        continue
                    if resync and source_id in folder_source_ids:
                        await kb.remove_by_source_id(user_id, source_id)
                    text = extract_document_text(str(p), base_str, max_chars=500_000)
                    if not text or not text.strip():
                        out["errors"].append(f"no text extracted: {rel}")
                        continue
                    err = await asyncio.wait_for(
                        kb.add(user_id=user_id, content=text, source_type="folder", source_id=source_id, metadata=None),
                        timeout=120,
                    )
                    if err and "Error" in str(err):
                        out["errors"].append(f"add {rel}: {err}")
                    else:
                        out["added"] += 1
                except asyncio.TimeoutError:
                    out["errors"].append(f"add {rel}: timeout")
                except Exception as e:
                    out["errors"].append(f"add {rel}: {e}")

            out["ok"] = True
            out["message"] = f"Sync done: added={out['added']}, removed={out['removed']}" + (f"; errors={len(out['errors'])}" if out["errors"] else "")
        except Exception as e:
            logger.debug("sync_user_kb_folder failed: {}", e)
            out["message"] = str(e)
            out["errors"].append(str(e))
        return out

    def _memory_summarization_state_path(self) -> Path:
        """Path to memory summarization state JSON (last_run, next_run). Uses database dir under project root. Never raises."""
        try:
            root = Path(Util().root_path()).resolve()
            meta = Util().get_core_metadata()
            db = getattr(meta, "database", None)
            if getattr(db, "path", None):
                base = root / str(db.path).strip()
            else:
                base = root / "database"
            base.mkdir(parents=True, exist_ok=True)
            return base / "memory_summarization_state.json"
        except Exception as e:
            logger.debug("Memory summarization state path: {}", e)
            return Path("database") / "memory_summarization_state.json"

    def _read_memory_summarization_state(self) -> Dict[str, str]:
        """Read last_run and next_run from state file. Returns {} on error or missing."""
        try:
            p = self._memory_summarization_state_path()
            if p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.debug("Read memory summarization state: {}", e)
        return {}

    def _write_memory_summarization_state(self, last_run: str, next_run: str) -> None:
        """Write last_run and next_run (ISO datetime strings) to state file."""
        try:
            p = self._memory_summarization_state_path()
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"last_run": last_run, "next_run": next_run}, f, indent=0)
        except Exception as e:
            logger.warning("Write memory summarization state: {}", e)

    async def run_memory_summarization(self) -> Dict[str, Any]:
        """
        Run one pass of RAG memory summarization: batch old raw memories per user, LLM-summarize, store summary (kept forever);
        then delete raw memories older than keep_original_days (TTL). Supported for Chroma and Cognee.
        Returns dict with ok, message, summaries_created, ttl_deleted, next_run. Never raises; returns error dict on failure.
        """
        def _fail(msg: str) -> Dict[str, Any]:
            return {"ok": False, "message": msg, "summaries_created": 0, "ttl_deleted": 0}

        try:
            meta = Util().get_core_metadata()
            if not getattr(meta, "use_memory", False):
                return _fail("use_memory is disabled.")
            cfg = getattr(meta, "memory_summarization", None) or {}
            if not cfg.get("enabled"):
                return _fail("memory_summarization.enabled is false.")
            mem = getattr(self, "mem_instance", None)
            if mem is None or not getattr(mem, "supports_summarization", lambda: False)():
                return _fail("Memory backend does not support summarization (requires list + get_data + delete_data).")

            keep_original_days = max(1, int(cfg.get("keep_original_days", 365) or 365))
            min_age_days = max(1, int(cfg.get("min_age_days", 7) or 7))
            max_per_batch = max(1, min(200, int(cfg.get("max_memories_per_batch", 50) or 50)))
            tz = datetime.now().astimezone().tzinfo
            now = datetime.now(tz)
            cutoff_min_age = now - timedelta(days=min_age_days)
            cutoff_ttl = now - timedelta(days=keep_original_days)

            def parse_created(s: Any) -> Optional[datetime]:
                if not s:
                    return None
                try:
                    if isinstance(s, datetime):
                        return s
                    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
                except Exception:
                    return None

            try:
                if hasattr(mem, "get_all_async") and asyncio.iscoroutinefunction(mem.get_all_async):
                    all_items = await mem.get_all_async(limit=10000)
                else:
                    all_items = mem.get_all(limit=10000)
            except Exception as e:
                logger.exception(e)
                return _fail(f"get_all failed: {e}")

            if not all_items or not isinstance(all_items, list):
                all_items = []

            def _is_summary_item(item: dict) -> bool:
                if item.get("metadata", {}).get("is_summary") or item.get("is_summary"):
                    return True
                return (item.get("memory") or "").strip().startswith("[HomeClaw summary]")

            # Build set of memory ids that are already covered by a summary (so we don't re-summarize)
            summarized_ids = set()
            for item in all_items:
                if not isinstance(item, dict):
                    continue
                meta_item = item.get("metadata") or {}
                if _is_summary_item(item):
                    raw = meta_item.get("summarized_memory_ids") or item.get("summarized_memory_ids")
                    if isinstance(raw, str):
                        try:
                            for mid in json.loads(raw):
                                summarized_ids.add(str(mid))
                        except Exception:
                            pass
                    elif isinstance(raw, list):
                        for mid in raw:
                            summarized_ids.add(str(mid))

            # Group by (user_id, agent_id); for each group take raw memories older than min_age_days, not in summarized_ids, sorted by created_at asc
            by_user: Dict[Tuple[str, str], List[Dict]] = {}
            for item in all_items:
                if not isinstance(item, dict):
                    continue
                if _is_summary_item(item):
                    continue
                mid = item.get("id")
                if mid in summarized_ids:
                    continue
                created = parse_created(item.get("created_at"))
                if created is None or created >= cutoff_min_age:
                    continue
                user_id = (item.get("user_id") or "").strip() or "default"
                agent_id = (item.get("agent_id") or "").strip() or "default"
                key = (user_id, agent_id)
                by_user.setdefault(key, []).append({**item, "_created": created})

            for key in by_user:
                by_user[key].sort(key=lambda x: x["_created"])
                by_user[key] = by_user[key][:max_per_batch]

            summaries_created = 0
            for (user_id, agent_id), batch in by_user.items():
                if not batch:
                    continue
                texts = []
                ids = []
                latest_created = None
                for m in batch:
                    ids.append(m.get("id"))
                    texts.append((m.get("memory") or "").strip())
                    c = m.get("_created")
                    if c and (latest_created is None or c > latest_created):
                        latest_created = c
                if not texts or not ids:
                    continue
                memories_text = "\n".join(f"- {t}" for t in texts if t)
                if not memories_text.strip():
                    continue
                prompt = MEMORY_BATCH_SUMMARIZE_PROMPT.format(memories_text=memories_text[:50000])
                messages = [
                    {"role": "system", "content": "You output only the summary text, no preamble or explanation."},
                    {"role": "user", "content": prompt},
                ]
                try:
                    summary = await self.openai_chat_completion(messages=messages)
                except Exception as e:
                    logger.warning("Summarization LLM failed for user_id={}: {}", user_id, e)
                    continue
                if not summary or not (summary := (summary or "").strip()):
                    continue
                latest_str = latest_created.isoformat() if latest_created else ""
                extra_meta = {
                    "is_summary": "true",
                    "summarized_memory_ids": json.dumps(ids),
                    "summarized_until": latest_str,
                }
                summary_to_store = "[HomeClaw summary] " + summary
                try:
                    await mem.add(
                        summary_to_store,
                        user_id=user_id,
                        agent_id=agent_id,
                        metadata=extra_meta,
                    )
                    summaries_created += 1
                    _component_log("memory", f"summarized: user_id={user_id} batch={len(ids)}")
                except Exception as e:
                    logger.warning("Add summary failed for user_id={}: {}", user_id, e)

            ttl_deleted = 0
            try:
                if hasattr(mem, "get_all_async") and asyncio.iscoroutinefunction(mem.get_all_async):
                    all_items_after = await mem.get_all_async(limit=10000)
                else:
                    all_items_after = mem.get_all(limit=10000)
            except Exception:
                all_items_after = all_items
            else:
                if not isinstance(all_items_after, list):
                    all_items_after = []
            for item in all_items_after or []:
                if not isinstance(item, dict):
                    continue
                if _is_summary_item(item):
                    continue
                created = parse_created(item.get("created_at"))
                if created is None or created >= cutoff_ttl:
                    continue
                mid = item.get("id")
                if not mid:
                    continue
                try:
                    if hasattr(mem, "delete_async") and asyncio.iscoroutinefunction(mem.delete_async):
                        await mem.delete_async(mid)
                    else:
                        mem.delete(mid)
                    ttl_deleted += 1
                except Exception as e:
                    logger.debug("TTL delete memory {}: {}", mid, e)

            schedule = (cfg.get("schedule") or "daily").strip().lower()
            interval_days = max(1, int(cfg.get("interval_days", 1) or 1))
            next_run_dt = now + timedelta(days=interval_days)
            if schedule == "weekly":
                next_run_dt = now + timedelta(days=7)
            elif schedule == "next_run":
                next_run_dt = now + timedelta(days=interval_days)
            try:
                self._write_memory_summarization_state(now.isoformat(), next_run_dt.isoformat())
            except Exception as e:
                logger.warning("Write memory summarization state: {}", e)

            return {
                "ok": True,
                "message": f"Summaries created: {summaries_created}, TTL deleted: {ttl_deleted}.",
                "summaries_created": summaries_created,
                "ttl_deleted": ttl_deleted,
                "next_run": next_run_dt.isoformat(),
            }
        except Exception as e:
            logger.exception(e)
            return _fail(str(e))

    async def _fetch_relevant_memories(
        self, query, messages, user_name,user_id, agent_id, run_id, filters, limit
    ):
        # Currently, only pass the last 6 messages to the search API to prevent long query
        #message_input = [
        #    f"{message['role']}: {message['content']}\n" for message in messages
        #][-6:]
        #query = "\n".join(message_input)
        memories = await self.mem_instance.search(
            query=query,
            user_name=user_name,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            filters=filters,
            limit=limit,
        )
        _component_log("memory", f"search: user_id={user_id} limit={limit} results={len(memories) if isinstance(memories, list) else 0}")

        '''
        message_input = [
            f"{message['role']}: {message['content']}\n" for message in messages
        ][-1:]
        logger.debug(f"Memory: Message Input, latest chat: {message_input}")
        tmp_memories = await self.mem_instance.search(
            query="\n".join(message_input),
            user_name=user_name,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            filters=filters,
            limit=limit,
        )
        logger.debug(f"Memory: Memories from latest chat: {tmp_memories}")
        for item in  tmp_memories:
            existed: bool = False
            for memory in memories:
                if item['memory'] == memory['memory']:
                    memory['score'] *= 2
                    existed = True
                    break
            if not existed:
                memories.append(item)
        '''
        return  memories

    async def search_memory(
        self,
        query: str,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        app_id: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """Search RAG memory (Chroma). For use by memory_search tool. Returns list of {memory, score} or [] if memory not enabled."""
        mem = getattr(self, "mem_instance", None)
        if mem is None:
            return []
        filters = {}
        if app_id:
            filters["agent_id"] = app_id
        try:
            results = await mem.search(
                query=query,
                user_name=user_name,
                user_id=user_id,
                agent_id=app_id,
                run_id=None,
                filters=filters,
                limit=limit,
            )
            return results or []
        except Exception:
            return []

    def get_memory_by_id(self, memory_id: str) -> Optional[dict]:
        """Get a single memory by id (for memory_get tool). Returns dict with memory, id, etc. or None."""
        mem = getattr(self, "mem_instance", None)
        if mem is None:
            return None
        try:
            return mem.get(memory_id)
        except Exception:
            return None

    async def re_sync_agent_memory(self, system_user_id: Optional[str] = None) -> int:
        """Re-index AGENT_MEMORY + daily memory (markdown) into the vector store for the given user (or global when None). Call after append so new content is searchable. Returns number of chunks synced."""
        if not getattr(Util().get_core_metadata(), "use_agent_memory_search", True):
            return 0
        store = getattr(self, "agent_memory_vector_store", None)
        embedder = getattr(self, "embedder", None)
        if not store or not embedder:
            return 0
        try:
            from base.workspace import get_workspace_dir
            from base.agent_memory_index import sync_agent_memory_to_vector_store
            meta = Util().get_core_metadata()
            ws_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "config/workspace")
            n = await sync_agent_memory_to_vector_store(
                workspace_dir=Path(ws_dir),
                agent_memory_path=(getattr(meta, "agent_memory_path", None) or "").strip() or None,
                daily_memory_dir=(getattr(meta, "daily_memory_dir", None) or "").strip() or None,
                vector_store=store,
                embedder=embedder,
                system_user_ids=[system_user_id],
            )
            if n > 0:
                _component_log("agent_memory", f"re-synced {n} chunk(s) after append")
            return n
        except Exception as e:
            logger.debug("re_sync_agent_memory failed: {}", e)
            return 0

    async def search_agent_memory(
        self,
        query: str,
        max_results: int = 10,
        min_score: Optional[float] = None,
        system_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search AGENT_MEMORY + daily memory (vector store). For agent_memory_search tool. Filters by system_user_id when set. Returns list of {path, start_line, end_line, snippet, score}. Never raises."""
        store = getattr(self, "agent_memory_vector_store", None)
        embedder = getattr(self, "embedder", None)
        if not store or not embedder:
            return []
        try:
            if not (query or "").strip():
                return []
            emb = await embedder.embed((query or "").strip())
            if not emb:
                return []
            from base.workspace import _is_global_agent_memory_user, _sanitize_system_user_id
            scope_key = "" if _is_global_agent_memory_user(system_user_id) else _sanitize_system_user_id(system_user_id)
            filters = {"system_user_id": scope_key}
            raw = store.search(query=[emb], limit=max(1, min(max_results, 50)), filters=filters)
        except Exception as e:
            logger.debug("search_agent_memory failed: {}", e)
            return []
        if not isinstance(raw, list):
            return []
        out = []
        for r in raw:
            try:
                payload = getattr(r, "payload", None) or {}
                if not isinstance(payload, dict):
                    payload = {}
                dist = getattr(r, "score", None)
                try:
                    score = (1.0 - float(dist)) if dist is not None else None
                except (TypeError, ValueError):
                    score = None
                if min_score is not None and score is not None and score < min_score:
                    continue
                out.append({
                    "path": payload.get("path", "") or "",
                    "start_line": int(payload.get("start_line", 1)) if payload.get("start_line") is not None else 1,
                    "end_line": int(payload.get("end_line", 1)) if payload.get("end_line") is not None else 1,
                    "snippet": payload.get("snippet", "") or "",
                    "score": score,
                })
            except Exception:
                continue
        return out

    def get_agent_memory_file(
        self,
        path: str,
        from_line: Optional[int] = None,
        lines: Optional[int] = None,
        system_user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Read AGENT_MEMORY or daily memory markdown (by path). For agent_memory_get tool. Resolves per-user paths when system_user_id is set. Returns {path, text, start_line, end_line} or None. Never raises."""
        try:
            from base.workspace import get_workspace_dir, get_agent_memory_file_path, get_daily_memory_dir, get_daily_memory_path_for_date
            meta = Util().get_core_metadata()
            ws_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "config/workspace")
            path = (path or "").strip()
            if not path:
                return None
            fp = None
            if path == "AGENT_MEMORY.md":
                fp = get_agent_memory_file_path(workspace_dir=ws_dir, agent_memory_path=getattr(meta, "agent_memory_path", None) or None, system_user_id=system_user_id)
            elif path.startswith("agent_memory/") and path.endswith(".md"):
                try:
                    user_part = path.replace("agent_memory/", "").replace(".md", "").strip()
                    if user_part:
                        fp = get_agent_memory_file_path(workspace_dir=ws_dir, agent_memory_path=None, system_user_id=user_part)
                except Exception:
                    fp = Path(ws_dir) / path
            elif path.startswith("memory/") and path.endswith(".md"):
                try:
                    date_str = path.replace("memory/", "").replace(".md", "")
                    d = date.fromisoformat(date_str)
                    base = get_daily_memory_dir(workspace_dir=ws_dir, daily_memory_dir=(getattr(meta, "daily_memory_dir", None) or "").strip() or None, system_user_id=system_user_id)
                    fp = base / f"{d.isoformat()}.md"
                except Exception:
                    fp = Path(ws_dir) / path
            elif path.startswith("daily_memory/") and "/" in path.replace("daily_memory/", "", 1):
                try:
                    rest = path.replace("daily_memory/", "", 1)
                    user_part, file_part = rest.split("/", 1)
                    date_str = file_part.replace(".md", "")
                    d = date.fromisoformat(date_str)
                    fp = get_daily_memory_path_for_date(d, workspace_dir=ws_dir, daily_memory_dir=(getattr(meta, "daily_memory_dir", None) or "").strip() or None, system_user_id=user_part.strip() or system_user_id)
                except Exception:
                    fp = Path(ws_dir) / path
            else:
                fp = Path(ws_dir) / path
            if fp is None or not fp.is_file():
                return None
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                return None
            start_line = from_line if from_line is not None else 1
            line_list = text.splitlines()
            total_lines = len(line_list)
            if from_line is not None or lines is not None:
                start = max(0, (from_line or 1) - 1)
                n = lines if lines is not None else max(0, total_lines - start)
                end = min(total_lines, start + n) if n else total_lines
                line_list = line_list[start:end]
                start_line = start + 1
                end_line = start + len(line_list)
                text = "\n".join(line_list)
            else:
                end_line = total_lines if total_lines else 1
            return {"path": path, "text": text, "start_line": start_line, "end_line": end_line}
        except Exception as e:
            logger.debug("get_agent_memory_file failed: {}", e)
            return None

    async def analyze_image(self, prompt: str, image_base64: str, mime_type: str = "image/jpeg") -> Optional[str]:
        """Analyze an image with the LLM (vision/multimodal). For image tool. Returns model response or None."""
        try:
            supported = Util().main_llm_supported_media() or []
        except Exception:
            supported = []
        if "image" not in supported:
            return "Image analysis is not supported by the current model."
        data_url = f"data:{mime_type};base64,{image_base64}"
        content = [
            {"type": "text", "text": prompt or "Describe the image."},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        messages = [{"role": "user", "content": content}]
        try:
            return await self.openai_chat_completion(messages)
        except Exception as e:
            logger.exception(e)
            return None

    async def run_spawn(self, task: str, llm_name: Optional[str] = None) -> str:
        """
        Sub-agent run: one-off completion for a task (one agent, optional different LLM).
        For sessions_spawn tool. No RAG, no tools, no session; same identity via system prompt is optional.
        Returns the model response text or an error string.
        """
        if not (task and str(task).strip()):
            return "Error: task is required and must be non-empty."
        messages = [
            {"role": "system", "content": "You are a sub-agent. Answer concisely and directly."},
            {"role": "user", "content": str(task).strip()},
        ]
        try:
            out = await self.openai_chat_completion(messages, llm_name=llm_name)
            return out if out is not None else "Error: no response from model."
        except Exception as e:
            logger.exception(e)
            return f"Error: {e!s}"

    def get_grammar(self, file: str, path: str = None) -> str | None:
        try:
            if not path:
                config_path = Util().config_path()
                path = os.path.join(config_path, "grammars")
            file_path = os.path.join(path, file)
            with open(file_path) as f:
                return f.read()
        except Exception as e:
            logger.exception(e)
            return None

    def exit_gracefully(self, signum, frame):
        if getattr(self, "_shutdown_started", False):
            # Second Ctrl+C: force exit so user is not blocked by slow plugin cleanup
            os._exit(1)
        self._shutdown_started = True
        logger.info("Shutting down (press Ctrl+C again to force exit)...")
        def run_stop():
            try:
                self.stop()
            except Exception as e:
                logger.exception(e)
        stop_thread = threading.Thread(target=run_stop, daemon=True)
        stop_thread.start()
        stop_thread.join(timeout=10)
        if stop_thread.is_alive():
            logger.warning("Shutdown taking longer than 10s; forcing exit.")
        os._exit(0 if not stop_thread.is_alive() else 1)

    def __enter__(self):
        global _core_instance_for_ctrl_c, _core_ctrl_handler_ready_time
        _core_instance_for_ctrl_c = self
        _is_main = threading.current_thread() is threading.main_thread()
        # Grace period for Windows: ignore CTRL_C_EVENT in first N seconds when Core runs in daemon thread (browser open can trigger spurious event).
        _core_ctrl_handler_ready_time = time.time()
        if _is_main:
            try:
                signal.signal(signal.SIGINT, self.exit_gracefully)
                signal.signal(signal.SIGTERM, self.exit_gracefully)
            except Exception:
                pass
        # On Windows, always register console Ctrl handler so Ctrl+C works (python -m main start runs Core in daemon thread; SIGINT may not be delivered). When daemon thread, handler ignores events in first _CORE_CTRL_GRACE_SEC.
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                PHANDLER = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_ulong)
                _win_console_ctrl_handler._handler = PHANDLER(_win_console_ctrl_handler)
                if kernel32.SetConsoleCtrlHandler(_win_console_ctrl_handler._handler, True):
                    pass  # registered
                else:
                    _win_console_ctrl_handler._handler = None
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        global _core_instance_for_ctrl_c, _core_ctrl_handler_ready_time
        _core_instance_for_ctrl_c = None
        _core_ctrl_handler_ready_time = None
        if sys.platform == "win32":
            try:
                handler = getattr(_win_console_ctrl_handler, "_handler", None)
                if handler is not None:
                    import ctypes
                    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, False)
            except Exception:
                pass
        return None

def main():
    # Print which Python runs Core and whether common skill deps (e.g. google.genai) are importable (before logging is configured)
    try:
        import google.genai as _  # noqa: F401
        _google_ok = "ok"
    except Exception:
        _google_ok = "missing"
    print("Core startup: Python=%s ; google.genai=%s" % (sys.executable, _google_ok), file=sys.stderr, flush=True)
    loop = None
    core = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with Core() as core:
            loop.run_until_complete(core.run())
    except KeyboardInterrupt:
        if core is not None:
            try:
                core.stop()
            except Exception:
                pass
        sys.exit(0)
    except Exception as e:
        logger.exception(e)
    finally:
        if loop is not None:
            # Let the uvicorn server task see should_exit and exit before closing the loop, to avoid
            # "Task was destroyed but it is pending! ... Server.serve()" on Windows.
            if core is not None and getattr(core, "server", None) is not None:
                try:
                    core.server.should_exit = True
                    core.server.force_exit = True
                    loop.run_until_complete(asyncio.sleep(0.5))
                except Exception:
                    pass
            loop.close()

# Set by Core.__enter__ so Windows console Ctrl handler can trigger shutdown when Python SIGINT is not delivered.
_core_instance_for_ctrl_c = None
# When Core runs in a daemon thread (python -m main start), ignore CTRL_C_EVENT in the first N seconds so opening the browser does not trigger shutdown.
_core_ctrl_handler_ready_time = None
_CORE_CTRL_GRACE_SEC = 5.0


def _win_console_ctrl_handler(event):
    """Windows-only: handle Ctrl+C so shutdown works when Python signal is not delivered. Second Ctrl+C = force exit 100% (same as old Core)."""
    if event == 0:  # CTRL_C_EVENT
        core = globals().get("_core_instance_for_ctrl_c")
        if core is None:
            return False
        # Second Ctrl+C: force exit so user is not blocked by slow cleanup (same as old Core exit_gracefully).
        if getattr(core, "_shutdown_started", False):
            try:
                print("\nForce exit (second Ctrl+C).", flush=True)
            except Exception:
                pass
            os._exit(1)
        # When Core runs in a daemon thread, ignore events in the first few seconds (browser open can trigger a spurious event).
        global _core_ctrl_handler_ready_time
        if _core_ctrl_handler_ready_time is not None:
            try:
                elapsed = time.time() - _core_ctrl_handler_ready_time
                if elapsed < _CORE_CTRL_GRACE_SEC:
                    return True  # ignore (don't shutdown)
            except Exception:
                pass
        core._shutdown_started = True
        try:
            print("\nShutting down (press Ctrl+C again to force exit)... 正在关闭...", flush=True)
            core.stop()
            time.sleep(2.0)
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            sys.exit(0)
        return True
    return False


if __name__ == "__main__":
    main()
