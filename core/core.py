import asyncio
import base64
import copy
from datetime import datetime, timedelta
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

# Reduce third-party FutureWarning noise (transformers, huggingface_hub); see docs/ResultViewerAndCommonLogs.md
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers.utils.generic")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")
import chromadb
import chromadb.config
import aiohttp
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from typing import Optional, Dict, List, Tuple, Union
from fastapi.responses import HTMLResponse, JSONResponse
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
from base.util import Util
from base.base import (
    LLM, EmbeddingRequest, Intent, IntentType, RegisterChannelRequest, PromptRequest, AsyncResponse, User, InboundRequest,
    ExternalPluginRegisterRequest,
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
from memory.prompts import RESPONSE_TEMPLATE, MEMORY_CHECK_PROMPT
from base.workspace import get_workspace_dir, load_workspace, build_workspace_system_prefix, load_agent_memory_file
from base.skills import get_skills_dir, load_skills, build_skills_system_block
from base.tools import ToolContext, get_tool_registry, ROUTING_RESPONSE_ALREADY_SENT
from base import last_channel as last_channel_store
from tools.builtin import register_builtin_tools, register_routing_tools, close_browser_session
from core.coreInterface import CoreInterface
from core.emailChannel import channel

logging.basicConfig(level=logging.CRITICAL)


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


def _parse_raw_tool_calls_from_content(content: str):
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
            self.orchestrator_timeout_seconds = max(0, int(getattr(meta, "orchestrator_timeout_seconds", 30) or 0))
            self.orchestrator_unified_with_tools = getattr(meta, "orchestrator_unified_with_tools", True)
            root = Util().root_path()
            db_folder = os.path.join(root, 'database')
            if not os.path.exists(db_folder):
                os.makedirs(db_folder)

            self.app = FastAPI()
            self.plugin_manager: PluginManager = None
            self.channels: List[BaseChannel] = []
            self.server = None
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
        """Poll GET {base_url}/ui until Core responds 200 or timeout. So plugins only register when Core is ready."""
        url = (base_url.rstrip("/") + "/ui")
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return True
            except Exception:
                pass
            await asyncio.sleep(interval_sec)
        return False

    async def _run_system_plugins_startup(self) -> None:
        """Start each discovered system plugin (server process) then run register. Waits for Core to be ready first."""
        meta = Util().get_core_metadata()
        allowlist = getattr(meta, "system_plugins", None) or []
        candidates = self._discover_system_plugins()
        if not candidates:
            return
        to_start = [c for c in candidates if not allowlist or c["id"] in allowlist]
        if not to_start:
            return
        core_url = f"http://{meta.host}:{meta.port}"
        env = os.environ.copy()
        env["CORE_URL"] = core_url
        if getattr(meta, "auth_enabled", False) and getattr(meta, "auth_api_key", ""):
            env["CORE_API_KEY"] = getattr(meta, "auth_api_key", "")
        # Wait for Core to be ready so registration succeeds (poll GET /ui until 200)
        ready = await self._wait_for_core_ready(core_url)
        if not ready:
            logger.warning("system_plugins: Core did not become ready in time; starting plugins anyway.")
        else:
            _component_log("system_plugins", "Core ready, starting plugin(s)")
        for item in to_start:
            cwd = item["cwd"]
            start_argv = item["start_argv"]
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
                logger.warning("system_plugins: failed to start %s: %s", item["id"], e)
        await asyncio.sleep(2)
        for item in to_start:
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
                    logger.debug("system_plugins: register %s stderr: %s", item["id"], (stderr or b"").decode(errors="replace")[:500])
            except Exception as e:
                logger.debug("system_plugins: register %s failed: %s", item["id"], e)

    # try to reduce the misunderstanding. All the input tests in EmbeddingBase should be
    # in a list[str]. If you just want to embedding one string, ok, put into one list first.
    async def get_embedding(self, request: EmbeddingRequest)-> List[List[float]]:
        # Initialize the embedder, now it is using one existing llama_cpp server with local LLM model
        try:
            _, _, _, host, port = Util().embedding_llm()
            embedding_url = "http://" + host + ":" + str(port) + "/v1/embeddings"
            text = text.replace("\n", " ")
            request_json = request.model_dump_json()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    embedding_url,
                    headers={"accept": "application/json", "Content-Type": "application/json"},
                    data=request_json,
                ) as response:
                    response_json = await response.json()
                    # Extract embeddings from the response
                    embeddings = [item["embedding"] for item in response_json["data"]]
                    return embeddings
        except asyncio.CancelledError:
            logger.debug("Embedding request was cancelled.")
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
            logger.debug("Knowledge base initialized (built-in RAG, collection=%s)", kb_cfg.get("collection_name") or "homeclaw_kb")
        except Exception as e:
            logger.warning("Knowledge base not initialized: %s", e)
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
                    model = _path if mtype == "litellm" else (_model_id or "local")
                    cognee_config.setdefault("llm", {})
                    cognee_config["llm"].update({
                        "provider": (cognee_config["llm"].get("provider") or "custom").strip() or "custom",
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (cognee_config["llm"].get("model") or model or "local").strip() or "local",
                        "api_key": (getattr(meta, "main_llm_api_key", "") or "").strip() or "local",
                    })
            if not (cognee_config.get("embedding") or {}).get("endpoint"):
                resolved = Util().embedding_llm()
                if resolved:
                    _path, _model_id, mtype, host, port = resolved
                    model = _path if mtype == "litellm" else (_model_id or "local")
                    cognee_config.setdefault("embedding", {})
                    cognee_config["embedding"].update({
                        "provider": (cognee_config["embedding"].get("provider") or "custom").strip() or "custom",
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (cognee_config["embedding"].get("model") or model or "local").strip() or "local",
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
            logger.warning("Knowledge base (Cognee) not initialized: %s", e)
            self.knowledge_base = None

    def initialize(self):
        logger.debug("core initializing...")
        self.initialize_vector_store(collection_name="memory")
        self.embedder = LlamaCppEmbedding()
        meta = Util().get_core_metadata()
        self._create_skills_vector_store()
        self._create_plugins_vector_store()
        self.knowledge_base = None
        self._create_knowledge_base()
        memory_backend = (getattr(meta, "memory_backend", None) or "cognee").strip().lower()

        if memory_backend == "cognee" and Util().has_memory():
            try:
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
                        model = _path if mtype == "litellm" else (_model_id or "local")
                        cognee_config["llm"] = {
                            **llm_cfg,
                            "provider": (llm_cfg.get("provider") or "custom").strip() or "custom",
                            "endpoint": f"http://{host}:{port}/v1",
                            "model": (llm_cfg.get("model") or model or "local").strip() or "local",
                        }
                        cognee_config["llm"]["api_key"] = (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                    else:
                        host = getattr(meta, "main_llm_host", "127.0.0.1") or "127.0.0.1"
                        port = getattr(meta, "main_llm_port", 5088) or 5088
                        cognee_config["llm"] = {
                            **llm_cfg,
                            "provider": (llm_cfg.get("provider") or "custom").strip() or "custom",
                            "endpoint": f"http://{host}:{port}/v1",
                            "model": (llm_cfg.get("model") or getattr(meta, "main_llm", "") or "local").strip() or "local",
                        }
                        cognee_config["llm"]["api_key"] = (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                emb_cfg = cognee_config.get("embedding") or {}
                if not isinstance(emb_cfg, dict):
                    emb_cfg = {}
                if not (emb_cfg.get("endpoint") or emb_cfg.get("model")):
                    resolved = Util().embedding_llm()
                    if resolved:
                        _path, _model_id, mtype, host, port = resolved
                        model = _path if mtype == "litellm" else (_model_id or "local")
                        cognee_config["embedding"] = {
                            **emb_cfg,
                            "provider": (emb_cfg.get("provider") or "custom").strip() or "custom",
                            "endpoint": f"http://{host}:{port}/v1",
                            "model": (emb_cfg.get("model") or model or "local").strip() or "local",
                        }
                        cognee_config["embedding"]["api_key"] = (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                    else:
                        host = getattr(meta, "embedding_host", "127.0.0.1") or "127.0.0.1"
                        port = getattr(meta, "embedding_port", 5066) or 5066
                        cognee_config["embedding"] = {
                            **emb_cfg,
                            "provider": (emb_cfg.get("provider") or "custom").strip() or "custom",
                            "endpoint": f"http://{host}:{port}/v1",
                            "model": (emb_cfg.get("model") or getattr(meta, "embedding_llm", "") or "local").strip() or "local",
                        }
                        cognee_config["embedding"]["api_key"] = (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                self.mem_instance = CogneeMemory(config=cognee_config if cognee_config else None)
                logger.debug("Memory backend: Cognee")
            except ImportError as e:
                logger.warning("Cognee backend requested but cognee not installed: %s. Using chroma.", e)
                memory_backend = "chroma"
            except Exception as e:
                logger.warning("Cognee backend failed: %s. Using chroma.", e)
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
                    logger.debug("Graph store not initialized: %s", e)
            if not getattr(self, "mem_instance", None):
                self.mem_instance = Memory(
                    embedding_model=self.embedder,
                    vector_store=self.vector_store,
                    llm=LlamaCppLLM(),
                    graph_store=graph_store,
                )

        self.request_queue_task = asyncio.create_task(self.process_request_queue())
        self.response_queue_task = asyncio.create_task(self.process_response_queue())
        self.memory_queue_task = asyncio.create_task(self.process_memory_queue())

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

        @self.app.post("/register_channel")
        async def register_channel(request: RegisterChannelRequest):
            logger.debug(f"Received channel registration request: {request.name}")
            try:
                self.register_channel(request.name, request.host, request.port, request.endpoints)
                _, _, _, host, port = Util().main_llm()
                language = Util().main_llm_language()

                return {"result": "Succeed", "host": host, "port": port, "language": language}
            except Exception as e:
                logger.exception(e)
                return {"result": str(e)}


        @self.app.post("/deregister_channel")
        async def deregister_channel(request: RegisterChannelRequest):
            logger.debug(f"Received channel deregistration request: {request.name}")
            try:
                self.deregister_channel(request.name, request.host, request.port, request.endpoints)
                return {"result": "Channel deregistration successful " + request.name}
            except Exception as e:
                logger.exception(e)
                return {"result": str(e)}

        @self.app.get("/shutdown")
        async def shutdown():
            try:
                logger.debug("Shutdown request received, shutting down...")
                self.stop()

            except Exception as e:
                logger.exception(e)

        @self.app.post("/process")
        async def process_request(request: PromptRequest):
            try:
                user_name: str = request.user_name
                user_id: str = request.user_id
                channel_type: ChannelType = request.channelType
                content_type: ContentType = request.contentType
                channel_name: str = getattr(request, "channel_name", "?")
                logger.info(f"Core: received /process from channel={channel_name} user={user_id} type={content_type}")
                if request is not None:
                    self.latestPromptRequest = copy.deepcopy(request)
                    logger.debug(f'latestPromptRequest set to: {self.latestPromptRequest}')
                    self._persist_last_channel(request)

                logger.debug(f"Received request from channel: {user_name}, {user_id}, {channel_type}, {content_type}")
                user: User = None
                has_permission, user = self.check_permission(user_name, user_id, channel_type, content_type)
                if not has_permission or user is None:
                    return Response(content="Permission denied", status_code=401)

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

        async def _verify_inbound_auth(request: Request) -> None:
            """When auth_enabled and auth_api_key are set, require X-API-Key or Authorization: Bearer for /inbound and /ws."""
            meta = Util().get_core_metadata()
            if not getattr(meta, 'auth_enabled', False):
                return
            expected = (getattr(meta, 'auth_api_key', '') or '').strip()
            if not expected:
                return
            key = (request.headers.get("X-API-Key") or "").strip()
            if not key:
                auth_h = (request.headers.get("Authorization") or "").strip()
                if auth_h.startswith("Bearer "):
                    key = auth_h.split(" ", 1)[1].strip()
            if key != expected:
                raise HTTPException(status_code=401, detail="Invalid or missing API key")

        def _ws_auth_ok(websocket: WebSocket) -> bool:
            """Check API key from WebSocket handshake headers; return True if auth disabled or key valid."""
            meta = Util().get_core_metadata()
            if not getattr(meta, 'auth_enabled', False):
                return True
            expected = (getattr(meta, 'auth_api_key', '') or '').strip()
            if not expected:
                return True
            headers = dict((k.decode().lower(), v.decode()) for k, v in websocket.scope.get("headers", []))
            key = (headers.get("x-api-key") or "").strip()
            if not key and (headers.get("authorization") or "").strip().startswith("Bearer "):
                key = (headers.get("authorization") or "").strip().split(" ", 1)[1].strip()
            return key == expected

        @self.app.post("/inbound")
        async def inbound(request: InboundRequest, _: None = Depends(_verify_inbound_auth)):
            """
            Minimal API for any bot: POST {"user_id": "...", "text": "..."} and get {"text": "..."} back.
            No channel process needed; add user_id to config/user.yml allowlist. Use channel_name to tag the source (e.g. telegram, discord).
            When auth_enabled and auth_api_key are set in config, require X-API-Key or Authorization: Bearer.
            """
            try:
                ok, text, status = await self._handle_inbound_request(request)
                if not ok:
                    return JSONResponse(status_code=status, content={"error": text, "text": ""})
                return JSONResponse(content={"text": text})
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"error": str(e), "text": ""})

        @self.app.post("/memory/reset")
        @self.app.get("/memory/reset")
        async def memory_reset():
            """
            Empty the memory store (for testing). Uses the configured memory backend's reset().
            No auth required by default; protect in production if needed.
            """
            mem = getattr(self, "mem_instance", None)
            if mem is None:
                return JSONResponse(status_code=404, content={"detail": "Memory not enabled or not initialized."})
            try:
                mem.reset()
                logger.info("Memory reset completed (backend=%s)", type(mem).__name__)
                return JSONResponse(content={"result": "ok", "message": "Memory cleared."})
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})

        @self.app.post("/knowledge_base/reset")
        @self.app.get("/knowledge_base/reset")
        async def knowledge_base_reset():
            """
            Empty the knowledge base (all users, all sources). Uses the configured KB backend's reset().
            For testing or to clear all saved documents/web/notes. No auth required by default; protect in production if needed.
            """
            kb = getattr(self, "knowledge_base", None)
            if kb is None:
                return JSONResponse(status_code=404, content={"detail": "Knowledge base not enabled or not initialized."})
            try:
                out = await kb.reset()
                if out.startswith("Error:"):
                    return JSONResponse(status_code=500, content={"detail": out, "result": "error"})
                logger.info("Knowledge base reset: %s", out)
                return JSONResponse(content={"result": "ok", "message": out})
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})

        # External plugin registration API (see docs/PluginStandard.md §3)
        @self.app.post("/api/plugins/register")
        async def api_plugins_register(body: ExternalPluginRegisterRequest):
            """
            Register an external plugin. Plugin sends id, name, description, health_check_url, type, config; optional description_long, tools.
            Built-in (Python) plugins do not use this; they are discovered by scanning plugins_dir.
            """
            try:
                descriptor = body.model_dump()
                descriptor["id"] = descriptor.get("plugin_id") or descriptor.get("id")
                plugin_id = self.plugin_manager.register_external_via_api(descriptor)
                return JSONResponse(content={"plugin_id": plugin_id, "registered": True})
            except ValueError as e:
                return JSONResponse(status_code=400, content={"detail": str(e), "registered": False})
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e), "registered": False})

        @self.app.post("/api/plugins/unregister")
        async def api_plugins_unregister(request: Request):
            """Unregister an API-registered external plugin. Body: { "plugin_id": "..." }."""
            try:
                data = await request.json()
                plugin_id = (data or {}).get("plugin_id") or ""
                if not plugin_id:
                    return JSONResponse(status_code=400, content={"detail": "plugin_id is required"})
                removed = self.plugin_manager.unregister_external_plugin(plugin_id)
                return JSONResponse(content={"removed": removed, "plugin_id": plugin_id})
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})

        @self.app.post("/api/plugins/unregister-all")
        async def api_plugins_unregister_all():
            """Unregister all API-registered external plugins. For testing."""
            try:
                removed = self.plugin_manager.unregister_all_external_plugins()
                return JSONResponse(content={"removed": removed, "count": len(removed)})
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})

        @self.app.get("/api/plugins/health/{plugin_id}")
        async def api_plugins_health(plugin_id: str):
            """Core calls the plugin's health_check_url and returns { ok: true/false }."""
            plug = self.plugin_manager.get_plugin_by_id(plugin_id)
            if plug is None or not isinstance(plug, dict):
                return JSONResponse(status_code=404, content={"detail": "Plugin not found", "ok": False})
            ok = await self.plugin_manager.check_plugin_health(plug)
            return JSONResponse(content={"ok": ok, "plugin_id": plugin_id})

        @self.app.get("/api/plugin-ui")
        async def api_plugin_ui_list():
            """Return list of plugins that declare UIs (dashboard, webchat, control, tui, custom). For launcher page."""
            out = []
            for pid, plug in (getattr(self.plugin_manager, "plugin_by_id", None) or {}).items():
                if not isinstance(plug, dict) or not plug.get("ui"):
                    continue
                ui = plug["ui"]
                entry = {"plugin_id": pid, "name": plug.get("name") or pid, "ui": ui}
                out.append(entry)
            return JSONResponse(content={"plugins": out})

        @self.app.post("/api/skills/clear-vector-store")
        async def api_skills_clear_vector_store():
            """Clear all skills from the skills vector store. For testing (e.g. no skills retrieved until next sync)."""
            try:
                vs = getattr(self, "skills_vector_store", None)
                if not vs:
                    return JSONResponse(content={"cleared": 0, "message": "Skills vector store not enabled"})
                list_ids_fn = getattr(vs, "list_ids", None)
                if not list_ids_fn:
                    return JSONResponse(content={"cleared": 0, "message": "Vector store has no list_ids"})
                ids = list_ids_fn(limit=10000)
                if ids:
                    delete_ids_fn = getattr(vs, "delete_ids", None)
                    if delete_ids_fn:
                        delete_ids_fn(ids)
                    else:
                        for vid in ids:
                            try:
                                vs.delete(vid)
                            except Exception:
                                pass
                return JSONResponse(content={"cleared": len(ids)})
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})

        @self.app.post("/api/testing/clear-all")
        async def api_testing_clear_all():
            """Unregister all external plugins and clear the skills vector store. For testing."""
            try:
                removed_plugins = self.plugin_manager.unregister_all_external_plugins()
                cleared_skills = 0
                vs = getattr(self, "skills_vector_store", None)
                if vs:
                    list_ids_fn = getattr(vs, "list_ids", None)
                    if list_ids_fn:
                        ids = list_ids_fn(limit=10000)
                        if ids:
                            delete_ids_fn = getattr(vs, "delete_ids", None)
                            if delete_ids_fn:
                                delete_ids_fn(ids)
                            else:
                                for vid in ids:
                                    try:
                                        vs.delete(vid)
                                    except Exception:
                                        pass
                        cleared_skills = len(ids)
                return JSONResponse(content={
                    "removed_plugins": removed_plugins,
                    "plugins_count": len(removed_plugins),
                    "skills_cleared": cleared_skills,
                })
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})

        @self.app.get("/api/sessions")
        async def api_sessions_list():
            """List sessions for plugin UIs. Requires session.api_enabled in config. Returns app_id, user_name, user_id, session_id, created_at."""
            try:
                session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
                if not session_cfg.get("api_enabled", True):
                    return JSONResponse(status_code=403, content={"detail": "Session API disabled"})
                limit = max(1, min(500, int(session_cfg.get("sessions_list_limit", 100))))
                sessions = self.get_sessions(num_rounds=limit, fetch_all=True)
                return JSONResponse(content={"sessions": sessions})
            except Exception as e:
                logger.exception(e)
                return JSONResponse(status_code=500, content={"detail": str(e)})

        @self.app.get("/ui")
        async def ui_launcher():
            """Launcher page: Sessions list (from Core) and plugin UIs (WebChat, Control UI, Dashboard, TUI)."""
            session_cfg = getattr(Util().get_core_metadata(), "session", None) or {}
            sessions_enabled = session_cfg.get("api_enabled", True)
            sessions_list = []
            if sessions_enabled:
                try:
                    sessions_list = self.get_sessions(num_rounds=50, fetch_all=True)
                except Exception:
                    pass
            plugins_with_ui = []
            for pid, plug in (getattr(self.plugin_manager, "plugin_by_id", None) or {}).items():
                if not isinstance(plug, dict) or not plug.get("ui"):
                    continue
                plugins_with_ui.append({"plugin_id": pid, "name": plug.get("name") or pid, "ui": plug["ui"]})
            html_parts = [
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>HomeClaw UI</title>",
                "<style>body{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;}",
                "h1,h2{color:#333;} ul{list-style:none;padding:0;} li{margin:0.5rem 0;}",
                "a{color:#e65100;} a:hover{text-decoration:underline;} .meta{color:#666;font-size:0.9rem;}",
                "table{border-collapse:collapse;width:100%;margin-top:0.5rem;} th,td{border:1px solid #ddd;padding:0.4rem 0.6rem;text-align:left;} th{background:#f5f5f5;}</style></head><body>",
                "<h1>HomeClaw</h1>",
                "<h2>Sessions</h2>",
                "<p class='meta'>Recent chat sessions (session_id, app_id, user_id, created). Data from Core; session.api_enabled in config.</p>",
            ]
            if sessions_list:
                html_parts.append("<table><thead><tr><th>session_id</th><th>app_id</th><th>user_id</th><th>created_at</th></tr></thead><tbody>")
                for s in sessions_list[:30]:
                    sid = (s.get("session_id") or "").replace("<", "&lt;").replace(">", "&gt;")
                    aid = (s.get("app_id") or "").replace("<", "&lt;").replace(">", "&gt;")
                    uid = (s.get("user_id") or "").replace("<", "&lt;").replace(">", "&gt;")
                    created = (s.get("created_at") or "").replace("<", "&lt;").replace(">", "&gt;") if s.get("created_at") else ""
                    html_parts.append(f"<tr><td><code>{sid}</code></td><td>{aid}</td><td>{uid}</td><td>{created}</td></tr>")
                html_parts.append("</tbody></table>")
            else:
                html_parts.append("<p class='meta'>No sessions yet, or session API disabled.</p>")
            html_parts.append("<h2>Plugin UIs</h2><p class='meta'>WebChat, Control UI, Dashboard, TUI. Open a link to use the UI.</p><ul>")
            for p in plugins_with_ui:
                name = p["name"]
                ui = p["ui"]
                for label, val in [("WebChat", ui.get("webchat")), ("Control UI", ui.get("control")), ("Dashboard", ui.get("dashboard")), ("TUI", ui.get("tui"))]:
                    url = val if isinstance(val, str) else (val.get("url") or val.get("base_path") if isinstance(val, dict) else None)
                    if url:
                        if label == "TUI" and not (url.startswith("http://") or url.startswith("https://")):
                            html_parts.append(f"<li><strong>{name}</strong> — <span class='meta'>{label}: run <code>{url}</code></span></li>")
                        else:
                            html_parts.append(f"<li><strong>{name}</strong> — <a href='{url}' target='_blank' rel='noopener'>{label}</a></li>")
                for c in (ui.get("custom") or []):
                    c_url = c.get("url") or c.get("base_path") if isinstance(c, dict) else None
                    c_name = (c.get("name") or c.get("id") or "Custom") if isinstance(c, dict) else "Custom"
                    if c_url:
                        html_parts.append(f"<li><strong>{name}</strong> — <a href='{c_url}' target='_blank' rel='noopener'>{c_name}</a></li>")
            html_parts.append("</ul><p class='meta'>Add plugins that declare <code>ui</code> in registration to see them here. See docs_design/PluginUIsAndHomeClawControlUI.md.</p></body></html>")
            return HTMLResponse(content="".join(html_parts))

        @self.app.websocket("/ws")
        async def websocket_chat(websocket: WebSocket):
            """
            WebSocket for our own clients (e.g. WebChat). Send JSON {"user_id": "...", "text": "..."}; receive {"text": "..."}.
            Same permission as /inbound (user_id in config/user.yml). When auth_enabled, send X-API-Key or Authorization: Bearer in handshake headers.
            """
            try:
                if not _ws_auth_ok(websocket):
                    await websocket.close(code=1008, reason="Unauthorized: invalid or missing API key")
                    return
                await websocket.accept()
                while True:
                    # Receive handles both text and binary frames (e.g. from plugin proxy); Starlette receive_text() expects "text" key and can KeyError when frame has "bytes".
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
                    raw = msg.get("text")
                    if raw is None and "bytes" in msg:
                        raw = msg["bytes"].decode("utf-8", errors="replace")
                    if raw is None:
                        await websocket.send_json({"error": "Invalid frame: expected text or bytes", "text": ""})
                        continue
                    try:
                        data = json.loads(raw)
                        req = InboundRequest(
                            user_id=data.get("user_id", ""),
                            text=data.get("text", ""),
                            channel_name=data.get("channel_name", "ws"),
                            user_name=data.get("user_name"),
                            app_id=data.get("app_id"),
                            action=data.get("action"),
                            images=data.get("images"),
                        )
                    except Exception as e:
                        await websocket.send_json({"error": str(e), "text": ""})
                        continue
                    if not req.user_id or not req.text:
                        await websocket.send_json({"error": "user_id and text required", "text": ""})
                        continue
                    ok, text, _ = await self._handle_inbound_request(req)
                    await websocket.send_json({"text": text if ok else "", "error": "" if ok else text})
            except WebSocketDisconnect:
                logger.debug("WebSocket client disconnected")
            except Exception as e:
                logger.exception(e)
                try:
                    await websocket.send_json({"error": str(e), "text": ""})
                except Exception:
                    pass

        # add more endpoints here
        logger.debug("core initialized and all the endpoints are registered!")


    async def _handle_inbound_request(self, request: InboundRequest) -> Tuple[bool, str, int]:
        """Shared logic for POST /inbound and WebSocket /ws. Returns (success, text_or_error, status_code)."""
        from datetime import datetime
        req_id = str(datetime.now().timestamp())
        user_name = request.user_name or request.user_id
        images_list = list(request.images) if getattr(request, "images", None) else []
        pr = PromptRequest(
            request_id=req_id,
            channel_name=request.channel_name or "webhook",
            request_metadata={"user_id": request.user_id, "channel": request.channel_name},
            channelType=ChannelType.IM,
            user_name=user_name,
            app_id=request.app_id or "homeclaw",
            user_id=request.user_id,
            contentType=ContentType.TEXTWITHIMAGE if images_list else ContentType.TEXT,
            text=request.text,
            action=request.action or "respond",
            host="inbound",
            port=0,
            images=images_list,
            videos=[],
            audios=[],
            timestamp=datetime.now().timestamp(),
        )
        content_type_for_perm = ContentType.TEXTWITHIMAGE if images_list else ContentType.TEXT
        has_permission, user = self.check_permission(pr.user_name, pr.user_id, ChannelType.IM, content_type_for_perm)
        if not has_permission or user is None:
            return False, "Permission denied", 401
        if user and len(user.name) > 0:
            pr.user_name = user.name
        if user:
            pr.system_user_id = user.id or user.name
        self.latestPromptRequest = copy.deepcopy(pr)
        self._persist_last_channel(pr)
        if not getattr(self, "orchestrator_unified_with_tools", True):
            flag = await self.orchestrator_handler(pr)
            if flag:
                return True, "Orchestrator and plugin handled the request", 200
        resp_text = await self.process_text_message(pr)
        if resp_text is None:
            return True, "", 200
        if resp_text == ROUTING_RESPONSE_ALREADY_SENT:
            return True, "Handled by routing (TAM or plugin).", 200
        return True, resp_text, 200

    def _persist_last_channel(self, request: PromptRequest) -> None:
        """Persist last channel to DB and atomic file (database/latest_channel.json) for robust send_response_to_latest_channel."""
        if request is None:
            return
        try:
            last_channel_store.save_last_channel(
                request_id=request.request_id,
                host=request.host,
                port=int(request.port),
                channel_name=request.channel_name,
                request_metadata=request.request_metadata or {},
                key=last_channel_store._DEFAULT_KEY,
                app_id=getattr(request, "app_id", None) or "",
            )
        except Exception as e:
            logger.warning("Failed to persist last channel: %s", e)

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
        timeout_sec = getattr(self, "orchestrator_timeout_seconds", 0) or 0
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
                        result_text = await asyncio.wait_for(
                            self.plugin_manager.run_external_plugin(plugin, request),
                            timeout=timeout_sec or 30,
                        ) if timeout_sec > 0 else await self.plugin_manager.run_external_plugin(plugin, request)
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
                        response_data={"text": "Permission denied.", "error": True},
                    )
                    await self.response_queue.put(err_resp)
                    continue

                if len(user.name) > 0:
                    request.user_name = user.name
                request.system_user_id = user.id or user.name

                #if intent is not None and (intent.type == IntentType.RESPOND or intent.type == IntentType.QUERY):
                if request.contentType == ContentType.TEXT:
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
                    resp_data = {"text": resp_text}
                    async_resp: AsyncResponse = AsyncResponse(request_id=request.request_id, request_metadata=request.request_metadata, host=request.host, port=request.port, from_channel=request.channel_name, response_data=resp_data)
                    await self.response_queue.put(async_resp)
                else:
                    # Handle other content types
                    pass

            except Exception as e:
                logger.exception(f"Error processing request: {e}")
            finally:
                self.request_queue.task_done()


    async def send_response_to_latest_channel(self, response: str):
        resp_data = {"text": response}
        request: Optional[PromptRequest] = self.latestPromptRequest
        if request is None:
            # Load from DB or atomic file (database/latest_channel.json)
            stored = last_channel_store.get_last_channel()
            if stored is None:
                logger.warning("send_response_to_latest_channel: no last channel (in-memory, DB, or file)")
                return
            app_id = stored.get("app_id") or ""
            if app_id == "homeclaw":
                print(response)
                return
            async_resp = AsyncResponse(
                request_id=stored["request_id"],
                request_metadata=stored.get("request_metadata") or {},
                host=stored["host"],
                port=stored["port"],
                from_channel=stored["channel_name"],
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


    async def send_response_to_request_channel(self, response: str, request: PromptRequest):
        resp_data = {"text": response}
        if request is None:
            return
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

                    # Check if the user input should be added to memory, For performance, comment this for now.
                    if (((main_llm_size <= 14) and (has_gpu == True)) or (main_llm_size <= 8)):
                        meta = Util().get_core_metadata()
                        prompt = None
                        if getattr(meta, "use_prompt_manager", False):
                            try:
                                pm = get_prompt_manager(
                                    prompts_dir=getattr(meta, "prompts_dir", None),
                                    default_language=getattr(meta, "prompt_default_language", "en"),
                                    cache_ttl_seconds=float(getattr(meta, "prompt_cache_ttl_seconds", 0) or 0),
                                )
                                lang = getattr(meta, "main_llm_language", "en") or "en"
                                prompt = pm.get_content("memory", "memory_check", lang=lang, user_input=human_message)
                            except Exception as e:
                                logger.debug("Prompt manager fallback for memory_check: %s", e)
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

    def _image_item_to_data_url(self, item: str) -> str:
        """Convert image item (data URL, file path, or raw base64) to a data URL for vision API."""
        if not item or not isinstance(item, str):
            return ""
        item = item.strip()
        if item.startswith("data:"):
            return item
        if os.path.isfile(item):
            try:
                with open(item, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                return f"data:image/jpeg;base64,{b64}"
            except Exception as e:
                logger.warning("Failed to read image file %s: %s", item, e)
                return ""
        return f"data:image/jpeg;base64,{item}"

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
            images_list = getattr(request, "images", None) or []
            if images_list:
                content_parts: List[Dict] = [{"type": "text", "text": human_message or ""}]
                for img in images_list:
                    data_url = self._image_item_to_data_url(img)
                    if data_url:
                        content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                messages.append({"role": "user", "content": content_parts})
            else:
                messages.append({'role': 'user', 'content': human_message})
            use_memory = Util().has_memory()
            if use_memory:
                await self.memory_queue.put(request)
            start = time.time()
            answer = await self.answer_from_memory(query=human_message, messages=messages, app_id=app_id, user_name=user_name, user_id=user_id, agent_id=app_id, session_id=session_id, run_id=run_id, request=request)
            end = time.time()
            logger.info(f"Core: response generated in {end - start:.1f}s for user={user_id}")
            logger.debug(f"LLM handling time: {end - start} seconds")
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


    def check_permission(self, user_name: str, user_id: str, channel_type: ChannelType, content_type: ContentType) -> bool:
        user: User = None
        users = Util().get_users()
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


    async def run(self):
        """Run the core using uvicorn"""
        try:
            logger.debug("core is running!")
            core_metadata: CoreMetadata = Util().get_core_metadata()
            logger.debug(f"Running core on {core_metadata.host}:{core_metadata.port}")
            config = uvicorn.Config(self.app, host=core_metadata.host, port=core_metadata.port, log_level="critical")
            self.server = Server(config=config)
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
                    incremental = bool(getattr(core_metadata, "skills_incremental_sync", False))
                    try:
                        n = await sync_skills_to_vector_store(
                            skills_path, self.skills_vector_store, self.embedder,
                            skills_test_dir=skills_test_path, incremental=incremental,
                        )
                        _component_log("skills", f"synced {n} skill(s) to vector store")
                    except Exception as e:
                        logger.warning("Skills vector sync failed: %s", e)

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
                            logger.warning("Plugins vector sync failed: %s", e)

            # Result viewer: start report web server on its own port (different from Core). Stops when Core stops.
            try:
                from core.result_viewer import start_report_server
                if start_report_server():
                    cfg = getattr(core_metadata, "result_viewer", None) or {}
                    port = int(cfg.get("port") or 9001)
                    _component_log("result_viewer", f"report server on port {port} (HTTP)")
            except Exception as e:
                logger.debug("Result viewer server skipped: %s", e)

            # Schedule llmManager.run() to run concurrently
            #llm_task = asyncio.create_task(self.llmManager.run())
            logger.debug("Starting LLM manager...")
            self.llmManager.run()
            logger.debug("LLM manager started!")
            # Optionally start and register system_plugins (e.g. homeclaw-browser) so one command runs Core + plugins
            if getattr(core_metadata, "system_plugins_auto_start", False):
                asyncio.create_task(self._run_system_plugins_startup())
            # Start the server
            #server_task = asyncio.create_task(self.server.serve())
            #await asyncio.gather(llm_task, server_task)
            await self.server.serve()

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

        # Stop result viewer report server (runs on its own port)
        try:
            from core.result_viewer import stop_report_server
            stop_report_server()
        except Exception:
            pass

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
            use_memory = Util().has_memory()
            llm_input = []
            response = ''
            system_parts = []

            # Workspace bootstrap (identity / agents / tools) — optional; see Comparison.md §7.4
            if getattr(Util().core_metadata, 'use_workspace_bootstrap', True):
                ws_dir = get_workspace_dir(getattr(Util().core_metadata, 'workspace_dir', None) or 'config/workspace')
                workspace = load_workspace(ws_dir)
                workspace_prefix = build_workspace_system_prefix(workspace)
                if workspace_prefix:
                    system_parts.append(workspace_prefix)

            # AGENT_MEMORY.md (curated long-term memory); see SessionAndDualMemoryDesign.md. Authoritative when conflict with RAG.
            if getattr(Util().core_metadata, 'use_agent_memory_file', False):
                ws_dir = get_workspace_dir(getattr(Util().core_metadata, 'workspace_dir', None) or 'config/workspace')
                agent_path = getattr(Util().core_metadata, 'agent_memory_path', None) or ''
                agent_content = load_agent_memory_file(workspace_dir=ws_dir, agent_memory_path=agent_path or None)
                if agent_content:
                    system_parts.append(
                        "## Agent memory (curated)\n" + agent_content + "\n\n"
                        "When both this section and the RAG context below mention the same fact, prefer this curated agent memory as authoritative."
                    )

            # Skills (SKILL.md from skills_dir) — optional; see Design.md §3.6
            if getattr(Util().core_metadata, 'use_skills', False):
                try:
                    root = Path(__file__).resolve().parent.parent
                    meta_skills = Util().core_metadata
                    skills_path = get_skills_dir(getattr(meta_skills, 'skills_dir', None), root=root)
                    skills_list = []
                    if getattr(meta_skills, 'skills_use_vector_search', False) and getattr(self, 'skills_vector_store', None) and getattr(self, 'embedder', None):
                        from base.skills import search_skills_by_query, load_skill_by_folder, TEST_ID_PREFIX
                        max_retrieved = max(1, min(100, int(getattr(meta_skills, 'skills_top_n_candidates', 10) or 10)))
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
                            else:
                                load_path = skills_path
                                folder_name = hit_id
                            if load_path is None:
                                continue
                            skill_dict = load_skill_by_folder(load_path, folder_name, include_body=False)
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
                        skills_list = load_skills(skills_path, include_body=False)
                        top_n = max(1, min(100, int(getattr(meta_skills, 'skills_top_n_candidates', 10) or 10)))
                        if len(skills_list) > top_n:
                            skills_list = skills_list[:top_n]
                        skills_max = max(0, int(getattr(meta_skills, 'skills_max_in_prompt', 5) or 5))
                        if skills_max > 0 and len(skills_list) > skills_max:
                            skills_list = skills_list[:skills_max]
                            _component_log("skills", f"capped to {skills_max} skill(s) in prompt (skills_max_in_prompt)")
                        if skills_list:
                            _component_log("skills", f"loaded {len(skills_list)} skill(s) from {skills_path}")
                    skills_block = build_skills_system_block(skills_list, include_body=False)
                    if skills_block:
                        system_parts.append(skills_block)
                except Exception as e:
                    logger.warning("Failed to load skills: %s", e)

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
                        logger.debug("Knowledge base search failed: %s", e)
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
                        logger.debug("Profile load for prompt failed: %s", e)
                meta = Util().get_core_metadata()
                if getattr(meta, "use_prompt_manager", False):
                    try:
                        pm = get_prompt_manager(
                            prompts_dir=getattr(meta, "prompts_dir", None),
                            default_language=getattr(meta, "prompt_default_language", "en"),
                            cache_ttl_seconds=float(getattr(meta, "prompt_cache_ttl_seconds", 0) or 0),
                        )
                        lang = getattr(meta, "main_llm_language", "en") or "en"
                        prompt = pm.get_content("chat", "response", lang=lang, context=context_val)
                    except Exception as e:
                        logger.debug("Prompt manager fallback for chat/response: %s", e)
                        prompt = None
                else:
                    prompt = None
                if not prompt or not prompt.strip():
                    prompt = RESPONSE_TEMPLATE.format(context=context_val)
                system_parts.append(prompt)

            unified = (
                getattr(Util().get_core_metadata(), "orchestrator_unified_with_tools", True)
                and getattr(Util().get_core_metadata(), "use_tools", False)
            )
            if unified and getattr(self, "plugin_manager", None):
                plugin_list = []
                meta_plugins = Util().get_core_metadata()
                if getattr(meta_plugins, "plugins_use_vector_search", False) and getattr(self, "plugins_vector_store", None) and getattr(self, "embedder", None):
                    from base.plugins_registry import search_plugins_by_query
                    max_retrieved = max(1, min(100, int(getattr(meta_plugins, "plugins_top_n_candidates", 10) or 10)))
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
                        logger.warning("Plugin vector search failed: %s", e)
                if not plugin_list:
                    plugin_list = getattr(self.plugin_manager, "get_plugin_list_for_prompt", lambda: [])()
                    plugins_top = max(1, min(100, int(getattr(Util().get_core_metadata(), "plugins_top_n_candidates", 10) or 10)))
                    if len(plugin_list) > plugins_top:
                        plugin_list = plugin_list[:plugins_top]
                    plugins_max = max(0, int(getattr(Util().get_core_metadata(), "plugins_max_in_prompt", 5) or 5))
                    if plugins_max > 0 and len(plugin_list) > plugins_max:
                        plugin_list = plugin_list[:plugins_max]
                plugin_lines = []
                if plugin_list:
                    desc_max = max(0, int(getattr(Util().get_core_metadata(), "plugins_description_max_chars", 0) or 0))
                    def _desc(d: str) -> str:
                        s = d or ""
                        return s[:desc_max] if desc_max > 0 else s
                    plugin_lines = [f"  - {p.get('id', '') or 'plugin'}: {_desc(p.get('description'))}" for p in plugin_list]
                routing_block = (
                    "## Routing (choose one)\n"
                    "For time-related requests prefer tools (no second LLM): one-shot reminders -> remind_me(minutes or at_time, message); recording a date/event -> record_date(event_name, when); recurring -> cron_schedule(cron_expr, message). Use route_to_tam only if the request is time-related but too complex for those tools.\n"
                    "If it clearly matches one of these plugins, call route_to_plugin with that plugin_id.\n"
                    "For script-based workflows (see Available skills above), use run_skill(skill_name, script, ...).\n"
                    "Otherwise respond or use other tools.\n"
                    + ("Available plugins:\n" + "\n".join(plugin_lines) if plugin_lines else "")
                )
                system_parts.append(routing_block)

            # Optional: surface recorded events (TAM) in context so model knows what's coming up
            if getattr(self, "orchestratorInst", None) and getattr(self.orchestratorInst, "tam", None):
                tam = self.orchestratorInst.tam
                if hasattr(tam, "get_recorded_events_summary"):
                    summary = tam.get_recorded_events_summary(limit=10)
                    if summary:
                        system_parts.append("## Recorded events (from record_date)\n" + summary)

            if system_parts:
                llm_input = [{"role": "system", "content": "\n".join(system_parts)}]

            # Compaction: trim messages when over limit so we stay within context window
            compaction_cfg = getattr(Util().get_core_metadata(), "compaction", None) or {}
            if compaction_cfg.get("enabled") and isinstance(messages, list) and len(messages) > 0:
                max_msg = max(2, int(compaction_cfg.get("max_messages_before_compact", 30) or 30))
                if len(messages) > max_msg:
                    messages = messages[-max_msg:]
                    _component_log("compaction", f"trimmed to last {max_msg} messages")

            llm_input += messages
            if len(llm_input) > 0:
            #    llm_input[-1]["content"] = f"Context for your reference: '{memories_text}'. When responding to the following user input: {query}, aim for a natural interaction instead of trying to provide a direct response. Let's focus on having an engaging conversation based on the chat histories, using the context only when it seamlessly fits."
                llm_input[-1]["content"] = f"Please provide a response to my input: '{query}'. Assume that you have memory and all content provided in this context is authorized for discussion and is your memory, no privacy issues at all.If you need more context or information to answer accurately, please let me know."
            logger.debug("Start to generate the response for user input: " + query)
            logger.info("Main LLM input (user query): %s", _truncate_for_log(query, 500))

            use_tools = getattr(Util().get_core_metadata(), "use_tools", False)
            registry = get_tool_registry()
            all_tools = registry.get_openai_tools() if use_tools and registry.list_tools() else None
            if all_tools and not unified:
                all_tools = [t for t in all_tools if (t.get("function") or {}).get("name") not in ("route_to_tam", "route_to_plugin")]
            openai_tools = all_tools if (all_tools and (unified or len(all_tools) > 0)) else None

            if openai_tools:
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
                for _ in range(max_tool_rounds):
                    msg = await Util().openai_chat_completion_message(current_messages, tools=openai_tools, tool_choice="auto")
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
                        # If content looks like raw tool_call but we didn't parse it, don't send that to the user
                        if content_str and ("<tool_call>" in content_str or "</tool_call>" in content_str):
                            response = "The assistant tried to use a tool but the response format was not recognized. Please try again."
                        else:
                            response = content_str
                        break
                    routing_sent = False
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
                        if result == ROUTING_RESPONSE_ALREADY_SENT and name in ("route_to_tam", "route_to_plugin"):
                            routing_sent = True
                        tool_content = result
                        if compaction_cfg.get("compact_tool_results") and isinstance(tool_content, str) and len(tool_content) > 4000:
                            tool_content = tool_content[:4000] + "\n[Output truncated for context.]"
                        current_messages.append({"role": "tool", "tool_call_id": tcid, "content": tool_content})
                    if routing_sent:
                        return ROUTING_RESPONSE_ALREADY_SENT
                else:
                    response = (current_messages[-1].get("content") or "").strip() if current_messages else None
                await close_browser_session(context)
            else:
                response = await self.openai_chat_completion(messages=llm_input)

            if response is None or len(response) == 0:
                return "Sorry, something went wrong and please try again. (对不起，出错了，请再试一次)"
            logger.info("Main LLM output (final response): %s", _truncate_for_log(response, 2000))
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
                    logger.debug("Session prune after turn failed: %s", e)
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

    async def analyze_image(self, prompt: str, image_base64: str, mime_type: str = "image/jpeg") -> Optional[str]:
        """Analyze an image with the LLM (vision/multimodal). For image tool. Returns model response or None."""
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
        try:
            #logger.debug("CTRL+C received, shutting down...")
            # shut down the chromadb server
            # self.shutdown_chroma_server()  # Shut down ChromaDB server
            # End the main thread
            self.stop()
            sys.exit(0)
            #logger.debug("CTRL+C Done...")
        except Exception as e:
            logger.exception(e)

    def __enter__(self):
        #if threading.current_thread() == threading.main_thread():
        try:
            #logger.debug("channel initializing..., register the ctrl+c signal handler")
            signal.signal(signal.SIGINT, self.exit_gracefully)
            signal.signal(signal.SIGTERM, self.exit_gracefully)
        except Exception as e:
            # It's a good practice to at least log the exception
            # logger.error(f"Error setting signal handlers: {e}")
            pass

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

def main():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with Core() as core:
            loop.run_until_complete(core.run())
    except Exception as e:
        logger.exception(e)
    finally:
        loop.close()

if __name__ == "__main__":
    main()
