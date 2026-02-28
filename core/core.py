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
    load_friend_identity_file,
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
    plugins_api, misc_api, ui_routes, websocket_routes, companion_push_api, companion_auth,
)
from core.route_registration import register_all_routes
from core.initialization import run_initialize
from core.inbound_handlers import (
    handle_inbound_request as _handle_inbound_request_fn,
    run_async_inbound as _run_async_inbound_fn,
    handle_inbound_request_impl as _handle_inbound_request_impl_fn,
    inbound_sse_generator as _inbound_sse_generator_fn,
)
from core.session_channel import (
    _persist_last_channel as _persist_last_channel_fn,
    _latest_location_path as _latest_location_path_fn,
    _normalize_location_to_address as _normalize_location_to_address_fn,
    _set_latest_location as _set_latest_location_fn,
    _get_latest_location as _get_latest_location_fn,
    _get_latest_location_entry as _get_latest_location_entry_fn,
    get_run_id as _get_run_id_fn,
    get_latest_chat_info as _get_latest_chat_info_fn,
    get_latest_chats as _get_latest_chats_fn,
    get_latest_chats_by_role as _get_latest_chats_by_role_fn,
    _resolve_session_key as _resolve_session_key_fn,
    get_session_id as _get_session_id_fn,
    get_system_context_for_plugins as _get_system_context_for_plugins_fn,
)
from core.outbound import (
    format_outbound_text as _format_outbound_text_fn,
    safe_classify_format as _safe_classify_format_fn,
    outbound_text_and_format as _outbound_text_and_format_fn,
    send_response_to_latest_channel as _send_response_to_latest_channel_fn,
    send_response_to_channel_by_key as _send_response_to_channel_by_key_fn,
    deliver_to_user as _deliver_to_user_fn,
    send_response_to_request_channel as _send_response_to_request_channel_fn,
    send_response_for_plugin as _send_response_for_plugin_fn,
)
from core.llm_loop import answer_from_memory as _answer_from_memory_fn
from core.plugins_startup import (
    _discover_system_plugins as _discover_system_plugins_fn,
    _wait_for_core_ready as _wait_for_core_ready_fn,
    _run_system_plugins_startup as _run_system_plugins_startup_fn,
)
from core.media_utils import (
    resize_image_data_url_if_needed as _resize_image_data_url_if_needed_fn,
    image_item_to_data_url as _image_item_to_data_url_fn,
    audio_item_to_base64_and_format as _audio_item_to_base64_and_format_fn,
    video_item_to_base64_and_format as _video_item_to_base64_and_format_fn,
)
from core.entry import main
# Tool helpers: prefer core.services.tool_helpers; fallback to core.tool_helpers_fallback so Core never crashes if the module is missing or broken.
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
logging.basicConfig(level=logging.CRITICAL)
from core.log_helpers import (
    _component_log,
    _truncate_for_log,
    _strip_leading_route_label,
    _SuppressConfigCoreAccessFilter,
)

# Pinggy tunnel state: set by _start_pinggy_and_open_browser when tunnel is ready. Read by GET /pinggy.
_pinggy_state: Dict[str, Any] = {"public_url": None, "connect_url": None, "qr_base64": None, "error": None}


class Core(CoreInterface):
    """Singleton. Attributes set in __init__; most methods delegate to core.* modules (session_channel, outbound, llm_loop, etc.)."""
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
        """Discover plugins in system_plugins/ that have register.js and a server. Delegates to core.plugins_startup."""
        return _discover_system_plugins_fn(self)

    async def _wait_for_core_ready(self, base_url: str, timeout_sec: float = 60.0, interval_sec: float = 0.5) -> bool:
        """Poll GET {base_url}/ready until Core responds 200 or timeout. Delegates to core.plugins_startup."""
        return await _wait_for_core_ready_fn(self, base_url, timeout_sec=timeout_sec, interval_sec=interval_sec)

    async def _run_system_plugins_startup(self) -> None:
        """Start each discovered system plugin then run register. Delegates to core.plugins_startup."""
        await _run_system_plugins_startup_fn(self)

    # try to reduce the misunderstanding. All the input tests in EmbeddingBase should be
    # in a list[str]. If you just want to embedding one string, ok, put into one list first.
    async def get_embedding(self, request: EmbeddingRequest)-> List[List[float]]:
        # Initialize the embedder: llama.cpp/cloud use /v1/embeddings; Ollama uses /api/embed (adapter below).
        try:
            resolved = Util().embedding_llm()
            if not resolved or len(resolved) < 5:
                logger.error("Embedding LLM not configured.")
                return []
            path_or_name, _, mtype, host, port = resolved[0], resolved[1], resolved[2] if len(resolved) > 2 else "local", resolved[3], resolved[4]
            sem = Util()._get_llm_semaphore(mtype)
            async with sem:
                async with aiohttp.ClientSession() as session:
                    if mtype == "ollama":
                        # Ollama: POST /api/embed with {"model": name, "input": list of strings}
                        embedding_url = "http://" + str(host) + ":" + str(port) + "/api/embed"
                        body = {"model": path_or_name or request.model, "input": getattr(request, "input", []) or []}
                        if not body["input"]:
                            return []
                        async with session.post(
                            embedding_url,
                            headers={"accept": "application/json", "Content-Type": "application/json"},
                            data=json.dumps(body),
                        ) as response:
                            response_json = await response.json() if response.content_type and "json" in response.content_type else {}
                            if not isinstance(response_json, dict) or "embeddings" not in response_json:
                                return []
                            emb = response_json["embeddings"]
                            return emb if isinstance(emb, list) else []
                    # OpenAI-compatible /v1/embeddings (llama.cpp, LiteLLM)
                    embedding_url = "http://" + str(host) + ":" + str(port) + "/v1/embeddings"
                    request_json = request.model_dump_json()
                    async with session.post(
                        embedding_url,
                        headers={"accept": "application/json", "Content-Type": "application/json"},
                        data=request_json,
                    ) as response:
                        response_json = await response.json()
                        if not isinstance(response_json, dict) or "data" not in response_json or not isinstance(response_json["data"], list):
                            return []
                        embeddings = [item["embedding"] for item in response_json["data"] if isinstance(item, dict) and "embedding" in item]
                        return embeddings
        except asyncio.CancelledError:
            logger.debug("Embedding request was cancelled.")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in embedding: {e}")
            return []


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

    def initialize(self):
        """Run full initialization: vector store, embedder, skills/plugins/agent_memory stores, knowledge base, memory backend. Delegates to core.initialization.run_initialize."""
        run_initialize(self)

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

        self._pinggy_state_getter = lambda: _pinggy_state
        register_all_routes(self)

    async def _handle_inbound_request(self, request: InboundRequest, progress_queue: Optional[asyncio.Queue] = None) -> Tuple[bool, str, int, Optional[List[str]]]:
        """Shared logic for POST /inbound and WebSocket /ws. Delegates to core.inbound_handlers.handle_inbound_request."""
        return await _handle_inbound_request_fn(self, request, progress_queue=progress_queue)

    async def _run_async_inbound(self, request_id: str, request: InboundRequest) -> None:
        """Background task for async /inbound. Delegates to core.inbound_handlers.run_async_inbound."""
        await _run_async_inbound_fn(self, request_id, request)

    async def _handle_inbound_request_impl(self, request: InboundRequest, progress_queue: Optional[asyncio.Queue] = None) -> Tuple[bool, str, int, Optional[List[str]]]:
        """Implementation of _handle_inbound_request. Delegates to core.inbound_handlers.handle_inbound_request_impl."""
        return await _handle_inbound_request_impl_fn(self, request, progress_queue=progress_queue)

    async def _inbound_sse_generator(self, progress_queue: asyncio.Queue, task: asyncio.Task) -> Any:
        """Yield Server-Sent Events for stream=true /inbound. Delegates to core.inbound_handlers.inbound_sse_generator."""
        async for chunk in _inbound_sse_generator_fn(self, progress_queue, task):
            yield chunk

    # Shared key for "latest location when Companion app is not combined" — used as fallback for all users
    _LATEST_LOCATION_SHARED_KEY = "companion"

    def _persist_last_channel(self, request: PromptRequest) -> None:
        """Persist last channel to DB and file. Delegates to core.session_channel._persist_last_channel."""
        _persist_last_channel_fn(self, request)

    def _latest_location_path(self) -> Path:
        """Path to latest_locations.json. Delegates to core.session_channel._latest_location_path."""
        return _latest_location_path_fn(self)

    def _normalize_location_to_address(self, location_input: Any) -> Tuple[Optional[str], Optional[str]]:
        """Convert lat/lng to address. Delegates to core.session_channel._normalize_location_to_address."""
        return _normalize_location_to_address_fn(self, location_input)

    def _set_latest_location(self, system_user_id: str, location_str: str, lat_lng_str: Optional[str] = None) -> None:
        """Store latest location. Delegates to core.session_channel._set_latest_location."""
        _set_latest_location_fn(self, system_user_id, location_str, lat_lng_str)

    def _get_latest_location(self, system_user_id: str) -> Optional[str]:
        """Return latest location. Delegates to core.session_channel._get_latest_location."""
        return _get_latest_location_fn(self, system_user_id)

    def _get_latest_location_entry(self, system_user_id: str) -> Optional[Dict[str, Any]]:
        """Return latest location entry. Delegates to core.session_channel._get_latest_location_entry."""
        return _get_latest_location_entry_fn(self, system_user_id)

    def get_system_context_for_plugins(
        self,
        system_user_id: Optional[str] = None,
        request: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Build system context (datetime, timezone, location) for plugins. Delegates to core.session_channel."""
        return _get_system_context_for_plugins_fn(self, system_user_id, request)

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
                request.friend_id = "HomeClaw"

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
        """Convert outbound reply when Markdown. Delegates to core.outbound.format_outbound_text."""
        return _format_outbound_text_fn(self, text)

    def _safe_classify_format(self, text: str) -> str:
        """Classify format or 'plain'. Delegates to core.outbound.safe_classify_format."""
        return _safe_classify_format_fn(self, text)

    def _outbound_text_and_format(self, text: str) -> tuple[str, str]:
        """Return (text_to_send, format). Delegates to core.outbound.outbound_text_and_format."""
        return _outbound_text_and_format_fn(self, text)

    async def send_response_to_latest_channel(self, response: str):
        """Send to default channel. Delegates to core.outbound.send_response_to_latest_channel."""
        await _send_response_to_latest_channel_fn(self, response)

    async def send_response_to_channel_by_key(self, key: str, response: str):
        """Send to channel by key. Delegates to core.outbound.send_response_to_channel_by_key."""
        await _send_response_to_channel_by_key_fn(self, key, response)

    async def deliver_to_user(
        self,
        user_id: str,
        text: str,
        images: Optional[List[str]] = None,
        channel_key: Optional[str] = None,
        source: str = "push",
        from_friend: str = "HomeClaw",
    ) -> None:
        """Push to user (WebSocket, push, channel). Delegates to core.outbound.deliver_to_user."""
        await _deliver_to_user_fn(self, user_id, text, images=images, channel_key=channel_key, source=source, from_friend=from_friend)

    async def send_response_to_request_channel(
        self,
        response: str,
        request: PromptRequest,
        image_path: Optional[str] = None,
        video_path: Optional[str] = None,
        audio_path: Optional[str] = None,
    ):
        """Send text and optional media to channel. Delegates to core.outbound.send_response_to_request_channel."""
        await _send_response_to_request_channel_fn(self, response, request, image_path=image_path, video_path=video_path, audio_path=audio_path)

    async def send_response_for_plugin(self, response: str, request: Optional[PromptRequest] = None):
        """Send to request channel or latest. Delegates to core.outbound.send_response_for_plugin."""
        await _send_response_for_plugin_fn(self, response, request)

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
                    _fid = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"
                    session_id = self.get_session_id(app_id=app_id, user_name=user_name, user_id=user_id, channel_name=channel_name, account_id=account_id, friend_id=_fid)
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
                                await self.mem_instance.add(human_message, user_name=user_name, user_id=user_id, agent_id=_fid, run_id=run_id, metadata=None, filters=None)
                                _component_log("memory", f"add (yes): user_id={user_id} friend_id={_fid} text={human_message[:60]}...")
                                logger.debug(f"User input added to memory: {human_message}")
                    else:
                        await self.mem_instance.add(human_message, user_name=user_name, user_id=user_id, agent_id=_fid, run_id=run_id, metadata=None, filters=None)
                        _component_log("memory", f"add: user_id={user_id} friend_id={_fid} text={(human_message or '')[:60]}...")
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
        """Delegates to core.session_channel.get_run_id."""
        return _get_run_id_fn(self, agent_id, user_name=user_name, user_id=user_id, validity_period=validity_period)

    def get_latest_chat_info(self, app_id=None, user_name=None, user_id=None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Delegates to core.session_channel.get_latest_chat_info."""
        return _get_latest_chat_info_fn(self, app_id=app_id, user_name=user_name, user_id=user_id)

    def get_latest_chats(self, app_id=None, user_name=None, user_id=None, num_rounds=10, timestamp=None) -> List[ChatMessage]:
        """Delegates to core.session_channel.get_latest_chats."""
        return _get_latest_chats_fn(self, app_id=app_id, user_name=user_name, user_id=user_id, num_rounds=num_rounds, timestamp=timestamp)

    def get_latest_chats_by_role(self, sender_name=None, responder_name=None, num_rounds=10, timestamp=None):
        """Delegates to core.session_channel.get_latest_chats_by_role."""
        return _get_latest_chats_by_role_fn(self, sender_name=sender_name, responder_name=responder_name, num_rounds=num_rounds, timestamp=timestamp)

    def _resolve_session_key(
        self,
        app_id: str,
        user_id: str,
        channel_name: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> str:
        """Delegates to core.session_channel._resolve_session_key."""
        return _resolve_session_key_fn(self, app_id, user_id, channel_name=channel_name, account_id=account_id)

    def get_session_id(
        self,
        app_id,
        user_name=None,
        user_id=None,
        channel_name: Optional[str] = None,
        account_id: Optional[str] = None,
        friend_id: Optional[str] = None,
        validity_period=timedelta(hours=24),
    ):
        """Delegates to core.session_channel.get_session_id."""
        return _get_session_id_fn(
            self,
            app_id,
            user_name=user_name,
            user_id=user_id,
            channel_name=channel_name,
            account_id=account_id,
            friend_id=friend_id,
            validity_period=validity_period,
        )

    def _resize_image_data_url_if_needed(self, data_url: str, max_dimension: int) -> str:
        """If max_dimension > 0 and Pillow is available, resize image. Delegates to core.media_utils."""
        return _resize_image_data_url_if_needed_fn(self, data_url, max_dimension)

    def _image_item_to_data_url(self, item: str) -> str:
        """Convert image item to data URL for vision API. Delegates to core.media_utils."""
        return _image_item_to_data_url_fn(self, item)

    def _audio_item_to_base64_and_format(self, item: str) -> Optional[Tuple[str, str]]:
        """Convert audio item to (base64_string, format). Delegates to core.media_utils."""
        return _audio_item_to_base64_and_format_fn(self, item)

    def _video_item_to_base64_and_format(self, item: str) -> Optional[Tuple[str, str]]:
        """Convert video item to (base64_string, format). Delegates to core.media_utils."""
        return _video_item_to_base64_and_format_fn(self, item)

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
            _fid = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"
            session_id = self.get_session_id(app_id=app_id, user_name=user_name, user_id=user_id, channel_name=channel_name, account_id=account_id, friend_id=_fid)
            run_id = self.get_run_id(agent_id=app_id, user_name=user_name, user_id=user_id)
            histories: List[ChatMessage] = self.chatDB.get(app_id=app_id, user_name=user_name, user_id=user_id, session_id=session_id, friend_id=_fid, num_rounds=6, fetch_all=False, display_format=False)
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
            # Mix mode: if request has images and cloud model supports image, include images in message (answer_from_memory will route to cloud when local does not support vision).
            main_llm_mode = (getattr(Util().get_core_metadata(), "main_llm_mode", None) or "").strip().lower()
            if images_list and "image" not in supported_media and main_llm_mode == "mix":
                cloud_ref = (getattr(Util().get_core_metadata(), "main_llm_cloud", None) or "").strip()
                if cloud_ref and "image" in (Util().main_llm_supported_media_for_ref(cloud_ref) or []):
                    supported_media = list(supported_media) if supported_media else []
                    if "image" not in supported_media:
                        supported_media.append("image")
                    logger.info("Mix mode: including image(s) in message; will use cloud for vision if local does not support.")
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
                # Local-only mode: save images to user's images folder and return polite message (no LLM call).
                if main_llm_mode != "mix" and Util()._effective_main_llm_type() == "local":
                    try:
                        try:
                            root = str(Util().get_core_metadata().get_homeclaw_root() or "").strip()
                        except Exception:
                            root = (getattr(Util().get_core_metadata(), "homeclaw_root", None) or "").strip()
                        if root and user_id:
                            images_dir = Path(root) / str(user_id) / "images"
                            images_dir.mkdir(parents=True, exist_ok=True)
                            ts = int(time.time())
                            saved = 0
                            for i, img in enumerate(images_list):
                                data_url = self._image_item_to_data_url(img) if getattr(self, "_image_item_to_data_url", None) else None
                                if not data_url or not data_url.strip().lower().startswith("data:image/"):
                                    if isinstance(img, str) and os.path.isfile(img):
                                        import shutil
                                        ext = (img.lower().split(".")[-1] if "." in img else "jpg") or "jpg"
                                        dest = images_dir / f"{ts}_{i}.{ext}"
                                        shutil.copy2(img, dest)
                                        saved += 1
                                    continue
                                idx = data_url.find(";base64,")
                                if idx > 0:
                                    import base64
                                    payload = data_url[idx + 8:]
                                    try:
                                        raw = base64.b64decode(payload)
                                        ext = "jpg"
                                        if "png" in data_url[:30]:
                                            ext = "png"
                                        dest = images_dir / f"{ts}_{i}.{ext}"
                                        dest.write_bytes(raw)
                                        saved += 1
                                    except Exception:
                                        pass
                            if saved:
                                polite = "I've saved your image(s) to your images folder. The current model doesn't support image understanding. You can switch to a vision-capable model (e.g. in mix mode or a local vision model) to ask about the image."
                                return polite
                    except Exception as e:
                        logger.debug("vision save image to user folder failed: {}", e)
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
            return "Something went wrong on our side. Please try again. If it keeps happening, the service may be temporarily unavailable."


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

            # Sync agent memory (AGENT_MEMORY + daily markdown) to vector store when use_agent_memory_search. Index global + per (user_id, friend_id).
            if getattr(core_metadata, "use_agent_memory_search", True):
                if getattr(self, "agent_memory_vector_store", None) and getattr(self, "embedder", None):
                    from base.workspace import get_workspace_dir
                    from base.agent_memory_index import sync_agent_memory_to_vector_store
                    ws_dir = get_workspace_dir(getattr(core_metadata, "workspace_dir", None) or "config/workspace")
                    try:
                        users = Util().get_users() or []
                        scope_pairs: List[Tuple[Optional[str], str]] = [(None, "HomeClaw")]
                        for u in users:
                            uid = getattr(u, "id", None) or getattr(u, "name", None)
                            if not uid:
                                continue
                            uid = str(uid).strip() or None
                            if not uid:
                                continue
                            friends = getattr(u, "friends", None) or []
                            if not friends:
                                scope_pairs.append((uid, "HomeClaw"))
                            else:
                                for f in friends:
                                    fid = getattr(f, "name", None) or "HomeClaw"
                                    fid = (str(fid).strip() or "HomeClaw") if fid else "HomeClaw"
                                    if fid:
                                        scope_pairs.append((uid, fid))
                    except Exception:
                        scope_pairs = [(None, "HomeClaw")]
                    try:
                        n = await sync_agent_memory_to_vector_store(
                            workspace_dir=Path(ws_dir),
                            agent_memory_path=(getattr(core_metadata, "agent_memory_path", None) or "").strip() or None,
                            daily_memory_dir=(getattr(core_metadata, "daily_memory_dir", None) or "").strip() or None,
                            vector_store=self.agent_memory_vector_store,
                            embedder=self.embedder,
                            scope_pairs=scope_pairs,
                        )
                        _component_log("agent_memory", f"synced {n} chunk(s) to vector store")
                    except Exception as e:
                        logger.warning("Agent memory vector sync failed: {}", e)

            # Create per-user, per-friend, and shared sandbox folders when homeclaw_root is set (UserFriendsModelFullDesign.md Step 5)
            root_str = (getattr(core_metadata, "homeclaw_root", None) or "").strip() if core_metadata else ""
            if root_str:
                try:
                    users = Util().get_users() or []
                    user_ids = []
                    friends_by_user: Dict[str, List[str]] = {}
                    for u in users:
                        uid = getattr(u, "id", None) or getattr(u, "name", None)
                        if not uid:
                            continue
                        uid = str(uid).strip()
                        if not uid:
                            continue
                        user_ids.append(uid)
                        friends = getattr(u, "friends", None) or []
                        if isinstance(friends, (list, tuple)):
                            friend_names = []
                            for f in friends:
                                name = getattr(f, "name", None)
                                name = (str(name).strip() or "HomeClaw") if name is not None else "HomeClaw"
                                if name:
                                    friend_names.append(name)
                            if friend_names:
                                friends_by_user[uid] = friend_names
                    ensure_user_sandbox_folders(root_str, user_ids, friends_by_user=friends_by_user, companion=False)
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
        """Delegate to core.llm_loop.answer_from_memory."""
        return await _answer_from_memory_fn(
            self, query, messages,
            app_id=app_id, user_name=user_name, user_id=user_id, agent_id=agent_id,
            session_id=session_id, run_id=run_id, metadata=metadata, filters=filters,
            limit=limit, response_format=response_format, tools=tools, tool_choice=tool_choice,
            logprobs=logprobs, top_logprobs=top_logprobs, parallel_tool_calls=parallel_tool_calls,
            deployment_id=deployment_id, extra_headers=extra_headers,
            functions=functions, function_call=function_call, host=host, port=port, request=request,
        )


    def add_chat_history(self, user_message: str, ai_message: str, app_id: Optional[str] = None, user_name: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None, friend_id: Optional[str] = None):
        try:
            message: ChatMessage = ChatMessage()
            message.add_user_message(user_message)
            message.add_ai_message(ai_message)
            self.chatDB.add(app_id=app_id, user_name=user_name, user_id=user_id, session_id=session_id, friend_id=friend_id, chat_message=message)
        except Exception as e:
            logger.exception(e)

    def get_sessions(
        self,
        app_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        friend_id: Optional[str] = None,
        num_rounds: int = 50,
        fetch_all: bool = False,
    ) -> list:
        """Return list of sessions (app_id, user_name, user_id, session_id, friend_id, created_at). For tools/sessions_list. Step 8: filter by friend_id when provided."""
        return self.chatDB.get_sessions(
            app_id=app_id,
            user_name=user_name,
            user_id=user_id,
            session_id=session_id,
            friend_id=friend_id,
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
        friend_id: Optional[str] = None,
        keep_last_n: int = 50,
    ) -> int:
        """Prune session transcript: keep last keep_last_n turns. Step 8: friend_id scopes the session."""
        return self.chatDB.prune_session(
            app_id=app_id,
            user_name=user_name,
            user_id=user_id,
            session_id=session_id,
            friend_id=friend_id,
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
        friend_id: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """Search RAG memory. Step 9: scoped by (user_id, friend_id). For use by memory_search tool. Returns list of {memory, score} or [] if memory not enabled."""
        mem = getattr(self, "mem_instance", None)
        if mem is None:
            return []
        try:
            scope = (str(friend_id or "").strip() or "HomeClaw") if friend_id is not None else (str(app_id or "").strip() or "HomeClaw")
        except (TypeError, AttributeError):
            scope = "HomeClaw"
        filters = {}
        if scope:
            filters["agent_id"] = scope
        try:
            results = await mem.search(
                query=query,
                user_name=user_name,
                user_id=user_id,
                agent_id=scope,
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

    async def re_sync_agent_memory(self, system_user_id: Optional[str] = None, friend_id: Optional[str] = None) -> int:
        """Re-index AGENT_MEMORY + daily memory (markdown) into the vector store for the given (user_id, friend_id). Call after append so new content is searchable. Returns number of chunks synced."""
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
            fid = (str(friend_id or "").strip() or "HomeClaw") if friend_id is not None else "HomeClaw"
            scope_pairs = [(system_user_id, fid)]
            n = await sync_agent_memory_to_vector_store(
                workspace_dir=Path(ws_dir),
                agent_memory_path=(getattr(meta, "agent_memory_path", None) or "").strip() or None,
                daily_memory_dir=(getattr(meta, "daily_memory_dir", None) or "").strip() or None,
                vector_store=store,
                embedder=embedder,
                scope_pairs=scope_pairs,
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
        friend_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search AGENT_MEMORY + daily memory (vector store). For agent_memory_search tool. Filters by (system_user_id, friend_id). Returns list of {path, start_line, end_line, snippet, score}. Never raises."""
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
            from base.agent_memory_index import _scope_key_for_pair
            fid = (str(friend_id or "").strip() or "HomeClaw") if friend_id is not None else "HomeClaw"
            scope_key = _scope_key_for_pair(system_user_id, fid)
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
        friend_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Read AGENT_MEMORY or daily memory markdown (by path). For agent_memory_get tool. Resolves per (user_id, friend_id) paths. Returns {path, text, start_line, end_line} or None. Never raises."""
        try:
            from base.workspace import get_workspace_dir, get_agent_memory_file_path, get_daily_memory_dir, get_daily_memory_path_for_date
            meta = Util().get_core_metadata()
            ws_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "config/workspace")
            path = (path or "").strip()
            if not path:
                return None
            fid = (str(friend_id or "").strip() or "HomeClaw") if friend_id is not None else "HomeClaw"
            fp = None
            if path == "AGENT_MEMORY.md":
                fp = get_agent_memory_file_path(workspace_dir=ws_dir, agent_memory_path=getattr(meta, "agent_memory_path", None) or None, system_user_id=system_user_id, friend_id=fid)
            elif path.startswith("memories/") and "/agent_memory.md" in path:
                try:
                    rest = path.replace("memories/", "", 1).replace("/agent_memory.md", "")
                    parts = rest.split("/", 1)
                    if len(parts) >= 2:
                        uid, f = parts[0], parts[1]
                        fp = get_agent_memory_file_path(workspace_dir=ws_dir, agent_memory_path=None, system_user_id=uid, friend_id=f)
                    elif len(parts) == 1 and parts[0]:
                        fp = get_agent_memory_file_path(workspace_dir=ws_dir, agent_memory_path=None, system_user_id=parts[0], friend_id=fid)
                except Exception:
                    fp = Path(ws_dir) / path
            elif path.startswith("agent_memory/") and path.endswith(".md"):
                try:
                    user_part = path.replace("agent_memory/", "").replace(".md", "").strip()
                    if user_part:
                        fp = get_agent_memory_file_path(workspace_dir=ws_dir, agent_memory_path=None, system_user_id=user_part, friend_id=fid)
                except Exception:
                    fp = Path(ws_dir) / path
            elif path.startswith("memories/") and "/memory/" in path and path.endswith(".md"):
                try:
                    rest = path.replace("memories/", "", 1)
                    parts = rest.split("/memory/", 1)
                    if len(parts) >= 2 and "/" in parts[0]:
                        uid, f = parts[0].split("/", 1)[0], parts[0].split("/", 1)[1]
                        date_str = parts[1].replace(".md", "")
                        d = date.fromisoformat(date_str)
                        fp = get_daily_memory_path_for_date(d, workspace_dir=ws_dir, daily_memory_dir=(getattr(meta, "daily_memory_dir", None) or "").strip() or None, system_user_id=uid, friend_id=f)
                    else:
                        date_str = parts[-1].replace(".md", "")
                        d = date.fromisoformat(date_str)
                        base = get_daily_memory_dir(workspace_dir=ws_dir, daily_memory_dir=(getattr(meta, "daily_memory_dir", None) or "").strip() or None, system_user_id=system_user_id, friend_id=fid)
                        fp = base / f"{d.isoformat()}.md"
                except Exception:
                    fp = Path(ws_dir) / path
            elif path.startswith("memory/") and path.endswith(".md"):
                try:
                    date_str = path.replace("memory/", "").replace(".md", "")
                    d = date.fromisoformat(date_str)
                    base = get_daily_memory_dir(workspace_dir=ws_dir, daily_memory_dir=(getattr(meta, "daily_memory_dir", None) or "").strip() or None, system_user_id=system_user_id, friend_id=fid)
                    fp = base / f"{d.isoformat()}.md"
                except Exception:
                    fp = Path(ws_dir) / path
            elif path.startswith("daily_memory/") and "/" in path.replace("daily_memory/", "", 1):
                try:
                    rest = path.replace("daily_memory/", "", 1)
                    user_part, file_part = rest.split("/", 1)
                    date_str = file_part.replace(".md", "")
                    d = date.fromisoformat(date_str)
                    fp = get_daily_memory_path_for_date(d, workspace_dir=ws_dir, daily_memory_dir=(getattr(meta, "daily_memory_dir", None) or "").strip() or None, system_user_id=user_part.strip() or system_user_id, friend_id=fid)
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
        import core.entry as _entry
        _entry._core_instance_for_ctrl_c = self
        _is_main = threading.current_thread() is threading.main_thread()
        _entry._core_ctrl_handler_ready_time = time.time()
        if _is_main:
            try:
                signal.signal(signal.SIGINT, self.exit_gracefully)
                signal.signal(signal.SIGTERM, self.exit_gracefully)
            except Exception:
                pass
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                PHANDLER = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_ulong)
                _entry._win_console_ctrl_handler._handler = PHANDLER(_entry._win_console_ctrl_handler)
                if kernel32.SetConsoleCtrlHandler(_entry._win_console_ctrl_handler._handler, True):
                    pass
                else:
                    _entry._win_console_ctrl_handler._handler = None
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        import core.entry as _entry
        _entry._core_instance_for_ctrl_c = None
        _entry._core_ctrl_handler_ready_time = None
        if sys.platform == "win32":
            try:
                handler = getattr(_entry._win_console_ctrl_handler, "_handler", None)
                if handler is not None:
                    import ctypes
                    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, False)
            except Exception:
                pass
        return None


if __name__ == "__main__":
    main()
