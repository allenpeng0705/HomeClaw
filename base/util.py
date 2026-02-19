import os
import sys
from pathlib import Path

# Ensure project root is on path before importing project packages (e.g. memory.chat).
# Cross-platform (Windows/Mac): Path(__file__).resolve().parent.parent is the repo root.
# Only insert if not already present so Mac runs (e.g. from project root) are unchanged.
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import asyncio
import atexit
import json
from multiprocessing import Process
import re
import runpy
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import aiohttp
import uvicorn
import yaml
from dotenv import dotenv_values
from loguru import logger
import watchdog.events
import watchdog.observers
import torch
import requests


from memory.chat.message import ChatMessage
from memory.prompts import MEMORY_SUMMARIZATION_PROMPT
from base.base import CoreMetadata, User, LLM, EmailAccount

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
core_metadata =CoreMetadata.from_yaml(os.path.join(root_dir, 'config', 'core.yml'))
data_root = os.path.join(root_dir, 'database')
if  (os.path.exists(data_root) and core_metadata.reset_memory == True):
    core_metadata.reset_memory = False
    CoreMetadata.to_yaml(core_metadata, os.path.join(root_dir, 'config', 'core.yml'))
    shutil.rmtree(data_root)

# Keys (case-insensitive) whose values are redacted in plugin/tool logs
_SENSITIVE_PARAM_KEYS = frozenset(k.lower() for k in (
    "password", "api_key", "api_key_name", "token", "secret", "authorization",
    "auth", "credentials", "key", "access_token", "refresh_token",
))


def redact_params_for_log(obj: Any) -> Any:
    """Return a copy of obj safe for logging: dict values for sensitive keys are replaced with '***'."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key_lower = (k or "").lower()
            if any(s in key_lower for s in _SENSITIVE_PARAM_KEYS) or ("key" in key_lower and "api" in key_lower):
                out[k] = "***"
            else:
                out[k] = redact_params_for_log(v)
        return out
    if isinstance(obj, list):
        return [redact_params_for_log(x) for x in obj]
    return obj


def run_script_silent(script_path):
    with open(os.devnull, 'w') as devnull:
        sys.stdout = devnull
        sys.stderr = devnull
        result = runpy.run_path(script_path, run_name='__main__')

def run_script(script_path):
    result = runpy.run_path(script_path, run_name='__main__')


def _normalize_language_list(language):
    """Normalize language to List[str] for main_llm_language. Accepts str (e.g. 'en') or list (e.g. [zh, en])."""
    if language is None:
        return ["en"]
    if isinstance(language, list):
        out = [str(x).strip() for x in language if str(x).strip()]
        return out if out else ["en"]
    s = str(language).strip() or "en"
    return [s]


class Util:
    _instance = None
    _lock = threading.Lock() 

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(Util, cls).__new__(cls, *args, **kwargs)
        return cls._instance
    
    
    def __init__(self) -> None:
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.config_observer = None
            self.core_metadata = CoreMetadata.from_yaml(os.path.join(self.config_path(), 'core.yml'))
            self.silent = self.core_metadata.silent
            self.llms = self.get_llms()

            if self.has_gpu_cuda():
                if self.core_metadata.main_llm is None or len(self.core_metadata.main_llm) == 0:
                    self.core_metadata.main_llm = self.llm_for_gpu()
                    CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))
                logger.debug("CUDA is available. Using GPU.")
            else:
                if self.core_metadata.main_llm is None or len(self.core_metadata.main_llm) == 0:
                    self.core_metadata.main_llm = self.llm_for_cpu()
                    CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))
                logger.debug("CUDA is not available. Using CPU.")
            self.users : list = User.from_yaml(os.path.join(self.config_path(), 'user.yml'))
            self.email_account: EmailAccount = EmailAccount.from_yaml(os.path.join(self.config_path(), 'email_account.yml'))
            
            # Start to monitor the specified config files
            self.watch_config_file()

    def is_silent(self) -> bool:
        return self.silent
    
    def set_silent(self, silent: bool):
        self.silent = silent
        self.core_metadata.silent = silent
        CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))

        log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        if self.silent:
            logger.remove(sys.stdout)
            logger.add(sys.stdout, format=log_format, level="INFO")
        else:
            logger.remove(sys.stdout)
            logger.add(sys.stdout, format=log_format, level="DEBUG")

    def has_memory(self) -> bool:
        return self.core_metadata.use_memory
    
    def set_memory(self, use_memory: bool):
        self.core_metadata.use_memory = use_memory
        CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))


    def run_script_in_process(self, script_path) -> Process:
        process = None
        if self.silent:
            process = Process(target=run_script_silent, args=(script_path,))
        else:
            process = Process(target=run_script, args=(script_path,))

        process.start()
        return process
     
    
    def run_script_in_thread(self, script_path):
        thread = threading.Thread(target=run_script, args=(script_path,))
        thread.start()
        return thread

    def load_yml_config(self, config_path):
        """
        Load configuration from a YAML file.
        """
        config_file = Path(config_path)
        if not config_file.is_file():
            raise FileNotFoundError(f"Configuration file {config_path} not found.")
        
        with open(config_file, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    
    def has_gpu_cuda(self) -> bool:
        return torch.cuda.is_available()


    def root_path(self):
        current_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(current_path)
    
    def log_path(self):
        root = self.root_path()
        return os.path.join(root, 'logs')
    
    def data_path(self):
        root = self.root_path()
        return os.path.join(root, 'database')    

    def reset_memory(self): 
        self.core_metadata.reset_memory = True
        CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))
    
    def plugins_path(self):
        root = self.root_path()
        return os.path.join(root, 'plugins')

    def system_plugins_path(self):
        """Directory for system plugins (e.g. homeclaw-browser). When system_plugins_auto_start is true, Core starts and registers them."""
        root = self.root_path()
        return os.path.join(root, 'system_plugins')

    def channels_path(self):
        root = self.root_path()
        return os.path.join(root, 'channels')

    def get_channels_core_url(self) -> str:
        """Core URL from channels/.env only (core_host, core_port or CORE_URL). No other config."""
        env_path = os.path.join(self.channels_path(), '.env')
        env_vars = dotenv_values(env_path) if os.path.exists(env_path) else {}
        if env_vars.get('CORE_URL'):
            return str(env_vars['CORE_URL']).rstrip('/')
        host = env_vars.get('core_host', '127.0.0.1')
        port = env_vars.get('core_port', '9000')
        return f"http://{host}:{port}"

    def get_core_url(self) -> str:
        """Core's own HTTP URL (from config core.yml host/port). For built-in plugins calling Core REST API (e.g. /api/plugins/llm/generate). 0.0.0.0 -> 127.0.0.1."""
        meta = self.get_core_metadata()
        host = (getattr(meta, 'host', None) or '0.0.0.0').strip()
        if host == '0.0.0.0':
            host = '127.0.0.1'
        port = int(getattr(meta, 'port', 9000) or 9000)
        return f"http://{host}:{port}"

    def config_path(self):
        return os.path.join(self.root_path(), 'config')
    
      
    def models_path(self):
        return os.path.join(self.root_path(), 'models')
    
    def setup_logging(self, module_name, mode):
        """
        Setup logging configuration using the configuration file.
        """
        log_path = self.log_path()
        log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        def filter_production(record):
            return record["extra"].get("production", False)

        def filter_debug(record):
            return record["extra"].get("shorttext", True)

        # remove the stdio logger
        logger.remove()
        if mode == "production":
            file_name = module_name + '_production.log'
            log_file = os.path.join(log_path, file_name)
            logger.add(log_file, format="{time} {level} {message}", filter=filter_production, level="INFO")
            logger.add(sys.stdout, format="{time} {level} {message}", filter=filter_production, level="INFO")
        else:
            file_name = module_name + '_debug.log'
            log_file = os.path.join(log_path, file_name)
            if self.silent:
                logger.add(sys.stdout, format=log_format, level="INFO")
            else:
                logger.add(sys.stdout, format=log_format, level="DEBUG")
            # The filter is to avoid to record long text into file
            logger.add(log_file, format=log_format, filter=filter_debug, level="DEBUG")
   
              
    @staticmethod
    def _parse_model_ref(ref: str):
        """Parse main_llm/embedding_llm: 'local_models/<id>' or 'cloud_models/<id>' or plain '<id>'. Returns (list_key, id) or (None, ref)."""
        if not ref or not isinstance(ref, str):
            return None, ref or ""
        ref = ref.strip()
        if ref.startswith("local_models/"):
            return "local", ref[len("local_models/"):].strip()
        if ref.startswith("cloud_models/"):
            return "cloud", ref[len("cloud_models/"):].strip()
        return None, ref

    def _effective_main_llm_type(self) -> str:
        """Derive main LLM type from main_llm ref: cloud_models/ -> litellm, else local. Fallback to core_metadata for legacy."""
        list_key, _ = self._parse_model_ref(self.core_metadata.main_llm)
        if list_key == "cloud":
            return "litellm"
        if list_key == "local":
            return "local"
        return self.core_metadata.main_llm_type or "local"

    def _effective_embedding_llm_type(self) -> str:
        """Derive embedding LLM type from embedding_llm ref: cloud_models/ -> litellm, else local. Fallback to core_metadata for legacy."""
        list_key, _ = self._parse_model_ref(self.core_metadata.embedding_llm)
        if list_key == "cloud":
            return "litellm"
        if list_key == "local":
            return "local"
        return self.core_metadata.embedding_llm_type or "local"

    def _get_model_entry(self, model_id: str):
        """Resolve model id to (entry_dict, 'local'|'litellm'). model_id can be 'local_models/<id>', 'cloud_models/<id>', or plain id. Returns (None, None) if not found."""
        list_key, raw_id = self._parse_model_ref(model_id)
        if list_key == "local":
            for m in (self.core_metadata.local_models or []):
                if m.get('id') == raw_id:
                    return m, 'local'
            return None, None
        if list_key == "cloud":
            for m in (self.core_metadata.cloud_models or []):
                if m.get('id') == raw_id:
                    return m, 'litellm'
            return None, None
        # No prefix: search local then cloud (backward compat)
        for m in (self.core_metadata.local_models or []):
            if m.get('id') == raw_id:
                return m, 'local'
        for m in (self.core_metadata.cloud_models or []):
            if m.get('id') == raw_id:
                return m, 'litellm'
        return None, None

    def main_llm(self):
        """Return (path_or_model, raw_id, mtype, host, port). Never returns None so callers can always unpack."""
        main_llm_name = (self.core_metadata.main_llm or "").strip()
        if not main_llm_name:
            main_llm_name = (self.llms[0] if self.llms else "local_models/main_vl_model")
        entry, mtype = self._get_model_entry(main_llm_name)
        if entry is not None:
            host = entry.get('host', '127.0.0.1')
            port = int(entry.get('port', 5088))
            if mtype == 'local':
                path = os.path.normpath(entry.get('path', ''))
                full_path = os.path.join(self.models_path(), path)
                _, raw_id = self._parse_model_ref(main_llm_name)
                return full_path, raw_id or main_llm_name, 'local', host, port
            else:
                _, raw_id = self._parse_model_ref(main_llm_name)
                return entry.get('path', main_llm_name), raw_id or main_llm_name, 'litellm', host, port
        # Legacy: no local_models/cloud_models or id not found — return safe fallback so callers never get None
        eff_type = self._effective_main_llm_type()
        host = self.core_metadata.main_llm_host or '127.0.0.1'
        port = int(self.core_metadata.main_llm_port or 5088)
        if eff_type == "local":
            for llm_name in (self.llms or []):
                if llm_name == main_llm_name:
                    return os.path.join(self.models_path(), llm_name), llm_name, eff_type, host, port
            # Local ref not in llms: still return a tuple so request can be attempted (may get connection error)
            return main_llm_name, main_llm_name, eff_type, host, port
        return main_llm_name, main_llm_name, eff_type, host, port

    def _llm_request_model_and_headers(self, path_or_model: str, raw_id: str, mtype: str) -> Tuple[str, dict]:
        """Return (model string for request body, headers dict) for local (llama.cpp) or cloud (LiteLLM)."""
        # LiteLLM expects provider/model (e.g. gemini/gemini-2.5-flash); local servers expect model id (e.g. main_vl_model).
        model_for_request = path_or_model if mtype == "litellm" else (raw_id or path_or_model)
        headers = {"Content-Type": "application/json"}
        if mtype == "litellm":
            key = (getattr(self.core_metadata, "main_llm_api_key", "") or "").strip()
            if key:
                headers["Authorization"] = "Bearer " + key
            else:
                headers["Authorization"] = "Anything"
        else:
            headers["Authorization"] = "Anything"
        return model_for_request, headers

    def _resolve_llm(self, llm_name: Optional[str] = None):
        """Return (path, model_id, type, host, port) for llm_name, or for main_llm if llm_name is None/empty. Returns None if llm_name given but not found."""
        if llm_name and str(llm_name).strip():
            name = str(llm_name).strip()
            entry, mtype = self._get_model_entry(name)
            if entry is not None:
                host = entry.get('host', '127.0.0.1')
                port = int(entry.get('port', 5088))
                _, raw_id = self._parse_model_ref(name)
                rid = raw_id or name
                if mtype == 'local':
                    path = os.path.normpath(entry.get('path', ''))
                    full_path = os.path.join(self.models_path(), path)
                    return full_path, rid, 'local', host, port
                return entry.get('path', name), rid, 'litellm', host, port
            return None
        return self.main_llm()
            
            
    def set_mainllm(self, main_llm_name, type=None, language="en", api_key_name="", api_key=""):
        # Support prefixed ref: local_models/<id> or cloud_models/<id>; derive type from prefix if not given
        list_key, raw_id = self._parse_model_ref(main_llm_name)
        if type is None and list_key == "local":
            type = "local"
        if type is None and list_key == "cloud":
            type = "litellm"
        if type is None:
            type = "local"
        # Prefixed ref: accept if entry exists; store as-is (local_models/... or cloud_models/...)
        if list_key in ("local", "cloud"):
            entry, _ = self._get_model_entry(main_llm_name)
            if entry is None:
                return None
            self.core_metadata.main_llm = main_llm_name
            self.core_metadata.main_llm_language = _normalize_language_list(language)
            if type == "litellm":
                self.core_metadata.main_llm_api_key_name = api_key_name or entry.get("api_key_name") or ""
                self.core_metadata.main_llm_api_key = api_key
            else:
                self.core_metadata.main_llm_api_key_name = api_key_name
                self.core_metadata.main_llm_api_key = api_key
            CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))
            return main_llm_name
        if type == "local":
            if main_llm_name in self.llms:
                self.core_metadata.main_llm = main_llm_name
                self.core_metadata.main_llm_language = _normalize_language_list(language)
                self.core_metadata.main_llm_api_key_name = api_key_name
                self.core_metadata.main_llm_api_key = api_key
                CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))
                return main_llm_name
            return None
        self.core_metadata.main_llm = main_llm_name
        self.core_metadata.main_llm_language = _normalize_language_list(language)
        self.core_metadata.main_llm_api_key_name = api_key_name
        self.core_metadata.main_llm_api_key = api_key
        CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))
        return main_llm_name

    def set_api_key_for_llm(self):
        if self._effective_main_llm_type() == "local":
            return
        # Derive api_key_name from selected cloud model entry when possible
        entry, _ = self._get_model_entry(self.core_metadata.main_llm)
        api_key_name = (entry.get("api_key_name") if entry else None) or self.core_metadata.main_llm_api_key_name
        if not api_key_name or (isinstance(api_key_name, str) and len(api_key_name.strip()) == 0):
            return
        key = self.core_metadata.main_llm_api_key
        if key and isinstance(key, str) and len(key.strip()) > 0:
            os.environ[api_key_name.strip()] = key
        
            
    def embedding_llm(self):
        embedding_llm_name = self.core_metadata.embedding_llm
        entry, mtype = self._get_model_entry(embedding_llm_name)
        if entry is not None:
            host = entry.get('host', '127.0.0.1')
            port = int(entry.get('port', 5066))
            _, raw_id = self._parse_model_ref(embedding_llm_name)
            if mtype == 'local':
                path = os.path.normpath(entry.get('path', ''))
                full_path = os.path.join(self.models_path(), path)
                return full_path, raw_id or embedding_llm_name, 'local', host, port
            else:
                return entry.get('path', embedding_llm_name), raw_id or embedding_llm_name, 'litellm', host, port
        eff_type = self._effective_embedding_llm_type()
        if eff_type == "local":
            for llm_name in self.llms:
                if llm_name == embedding_llm_name:
                    return os.path.join(self.models_path(), llm_name), llm_name, eff_type, self.core_metadata.embedding_host, self.core_metadata.embedding_port
            return None
        return embedding_llm_name, embedding_llm_name, eff_type, self.core_metadata.embedding_host, self.core_metadata.embedding_port
        
            
    def main_llm_size(self):
        _, raw = self._parse_model_ref(self.core_metadata.main_llm)
        name = (raw or self.core_metadata.main_llm).lower()  
        # Regular expression to find the model size (e.g., "14b")
        model_size_pattern = re.compile(r'(\d+)b')
        
        # Find all matches of the pattern in the name
        matches = model_size_pattern.findall(name)
        if matches:
            # Assuming you want the first match if there are multiple
            size = matches[0]
            # Convert size to integer representing billions
            return int(size)
        else:
            return 0
        
    def llm_size(self, llm_name):
        _, raw = self._parse_model_ref(llm_name)
        name = (raw or llm_name or "").lower()
        model_size_pattern = re.compile(r'(\d+)b')
        matches = model_size_pattern.findall(name)
        if matches:
            return int(matches[0])
        return 0

    def llm_for_cpu(self):
        llms = self.available_llms()
        local_only = [x for x in llms if isinstance(x, str) and x.startswith("local_models/")]
        if local_only:
            llms = local_only
        llm_num = len(llms)
        if llm_num < 1:
            return None
        if len(llms) == 1:
            return llms[0]
        for llm_name in llms:
            if self.llm_size(llm_name) <= 7:
                return llm_name
        return llms[0]
        
            
    def llm_for_gpu(self):
        llms = self.available_llms()
        local_only = [x for x in llms if isinstance(x, str) and x.startswith("local_models/")]
        if local_only:
            llms = local_only
        llm_num = len(llms)
        if llm_num < 1:
            return None
        if len(llms) == 1:
            return llms[0]
        for llm_name in llms:
            size = self.llm_size(llm_name)
            if size >= 7 and size <= 14 :
                return llm_name
        return llms[0]
        
    def main_llm_language(self):
        """Primary language for prompt file loading (e.g. response.en.yml). First element of main_llm_language list."""
        lst = self.core_metadata.main_llm_language
        if not lst or not isinstance(lst, list):
            return "en"
        return (lst[0] or "en") if lst else "en"

    def main_llm_languages(self):
        """Full list of allowed/preferred response languages. Use in system prompt: respond only in one of these; if unknown use first."""
        lst = self.core_metadata.main_llm_language
        if not lst or not isinstance(lst, list):
            return ["en"]
        return [x for x in lst if x] or ["en"]

    def main_llm_type(self):
        return self._effective_main_llm_type()

    def main_llm_supported_media(self) -> List[str]:
        """What media types the main model can handle: image, audio, video. Used so Core does not send unsupported content and does not crash.
        - Cloud model (main_llm = cloud_models/...): default [image, audio, video] unless the model entry has supported_media.
        - Local model: default [] unless the entry has mmproj (vision) then [image], or has supported_media.
        Returns normalized list (lowercase, only image/audio/video). Never raises; returns [] on any error."""
        try:
            main_llm_name = (self.core_metadata.main_llm or "").strip()
            if not main_llm_name:
                return []
            entry, mtype = self._get_model_entry(main_llm_name)
            if entry is None:
                local_ids = [m.get("id") for m in (self.core_metadata.local_models or []) if m.get("id")]
                cloud_ids = [m.get("id") for m in (self.core_metadata.cloud_models or []) if m.get("id")]
                logger.warning(
                    "main_llm_supported_media: model entry not found for main_llm={}. "
                    "Available local_models ids: {}. Available cloud_models ids: {}. "
                    "Set main_llm to e.g. local_models/<id> (e.g. local_models/main_vl_model).",
                    main_llm_name,
                    local_ids or "(none)",
                    cloud_ids or "(none)",
                )
            allowed = {"image", "audio", "video"}

            def normalize(raw) -> List[str]:
                if not raw:
                    return []
                if isinstance(raw, list):
                    out = [str(x).strip().lower() for x in raw if x]
                else:
                    out = [str(raw).strip().lower()]
                return [x for x in out if x in allowed]

            if entry is not None:
                explicit = entry.get("supported_media")
                if explicit is not None:
                    out = normalize(explicit)
                    logger.info("main_llm_supported_media: using entry (supported_media={})", out)
                    return out
                if mtype == "litellm":
                    return ["image", "audio", "video"]
                if mtype == "local":
                    if entry.get("mmproj"):
                        logger.info("main_llm_supported_media: using entry (mmproj) -> [image]")
                        return ["image"]
                    return []
            if self._effective_main_llm_type() == "litellm":
                return ["image", "audio", "video"]
            return []
        except Exception:
            return []
    

    def get_ollama_supported_models(self):
        try:
            url = "http://localhost:11434/api/tags"
            response = requests.get(url)
            if response.status_code == 200:
                models_data = response.json()
                # Extract the first part of model names before the colon
                model_prefixes = [model["name"].split(':')[0] for model in models_data["models"]]
                return model_prefixes
            else:
                # Handle errors or unexpected status codes
                return []
        except Exception as e:
            # Handle exceptions
            return []
        
    def pull_model_from_ollama(self, model_name):
        url = "http://localhost:11434/api/pull"
        payload = {"model": model_name}
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data=json.dumps(payload), headers=headers)

        if response.ok:
            # Assuming the response contains multiple JSON objects (not standard JSON)
            # Split response by lines and parse each line as JSON
            #statuses = [json.loads(line) for line in response.iter_lines() if line.strip()]

            # Extract the 'status' values from the parsed JSON objects
            #status_contents = [status_dict["status"] for status_dict in statuses]
            return "Model successfully pulled from Ollama."
        else:
            # Handle errors, e.g., by returning None or raising an exception
            return "Failed to pull model from Ollama."
        
            
    def process_text(self, text):
        # Check if both <think> and </think> are in the text
        if '<think>' in text and '</think>' in text:
            # If so, remove the entire content within the first <think> to </think> (inclusive)
            processed_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        elif '<think>' in text:
            # If there is a <think> without a corresponding </think>, remove the <think> tag
            logger.debug(f'There is a <think> without a corresponding </think> in the text: {text}')
            processed_text = ''
        elif '</think>' in text:
            # If there is a </think> without a corresponding <think>, keep the text after </think>
            processed_text = text.split('</think>', 1)[-1]
        else:
            # If neither tag is present, keep the text as is
            processed_text = text
        
        answer_index = processed_text.find('**Step-by-Step Explanation and Answer:**')
        if answer_index != -1:
            answer_index = processed_text.find('**Answer:**')
            if answer_index != -1:
                processed_text = processed_text[answer_index + len('**Answer:**'):]
            else:
                answer_index = processed_text.find('**Final Answer:**')
                if answer_index != -1:
                    processed_text = processed_text[answer_index + len('**Final Answer:**'):]
                else:
                    processed_text = ''
        else:
            answer_index = processed_text.find('**Step-by-Step Explanation:**')
            if answer_index != -1:
                answer_index = processed_text.find('**Answer:**')
                if answer_index != -1:
                    processed_text = processed_text[answer_index + len('**Answer:**'):]
                else:
                    answer_index = processed_text.find('**Final Answer:**')
                    if answer_index != -1:
                        processed_text = processed_text[answer_index + len('**Final Answer:**'):]
                    else:
                        processed_text = ''

        if len(processed_text.strip()) > 0:
            return processed_text.strip()
        else:
            return None
        

    def is_utf8_compatible(self, data):
        try:
            # Attempt to convert the data to a JSON string without ASCII encoding,
            # then encode it to UTF-8. This will raise an error if data can't be
            # represented in UTF-8.
            json.dumps(data, ensure_ascii=False).encode('utf-8')
        except UnicodeEncodeError:
            return False
        return True
    
    def check_main_model_server_health(self, timeout: int = 300) -> bool:
        """Check if the LLM server is ready by making a request to its health endpoint."""
        _, model, type, model_host, model_port = Util().main_llm()
        health_url = f"http://{model_host}:{model_port}/health"
        logger.debug(f"Main model Health URL: {health_url}")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(health_url, timeout=10)
                if response.status_code == 200:
                    logger.debug("Main model server is healthy and ready to accept requests.")
                    return True
                elif response.status_code == 503:
                    # The server is not ready yet
                    #logger.debug("Main model server is not ready yet, retrying...")
                    time.sleep(1)  # Wait for 1 second before trying again
                    continue
                else:
                    # The server is up but returned an unexpected status code
                    logger.error(f"Main model server returned unexpected status code: {response.status_code}")
                    return False
            except requests.exceptions.ConnectionError:
                # The request failed because the server is not up yet
                logger.debug("Main model server is not connected yet, retrying...")
            time.sleep(1)  # Wait for 1 second before trying again
        logger.error(f"Main model server did not become ready within {timeout} seconds.")
        return False
    
    def check_embedding_model_server_health(self, timeout: int = 120) -> bool:
        """Check if the LLM server is ready by making a request to its health endpoint."""
        _, model, type, model_host, model_port = Util().embedding_llm()
        health_url = f"http://{model_host}:{model_port}/health"
        logger.debug(f"Embedding model Health URL: {health_url}")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(health_url, timeout=10)
                if response.status_code == 200:
                    logger.debug("Embedding server is healthy and ready to accept requests.")
                    return True
                elif response.status_code == 503:
                    # The server is not ready yet
                    # logger.debug("Embedding server is not ready yet, retrying...")
                    time.sleep(1)  # Wait for 1 second before trying again
                    continue
                else:
                    # The server is up but returned an unexpected status code
                    logger.error(f"Embedding server returned unexpected status code: {response.status_code}")
                    return False
            except requests.exceptions.ConnectionError:
                # The request failed because the server is not up yet
                logger.debug("Embedding server is not connected yet, retrying...")
            time.sleep(1)  # Wait for 1 second before trying again
        logger.error(f"LLM server did not become ready within {timeout} seconds.")
        return False

    def _get_completion_params(self) -> Tuple[Dict, Dict]:
        """
        Build completion request params from config/core.yml completion (and llama_cpp fallbacks).
        Returns (data_updates, extra_body_updates). Merge into request data and data["extra_body"].
        """
        meta = self.get_core_metadata()
        comp = getattr(meta, "completion", None) or {}
        lcpp = getattr(meta, "llama_cpp", None) or {}
        data_updates = {}
        extra_body_updates = {}

        max_tokens = comp.get("max_tokens") or lcpp.get("predict") or 8192
        data_updates["max_tokens"] = int(max_tokens)

        def _float(v):
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _int(v):
            if v is None:
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        temp = comp.get("temperature")
        if temp is None:
            temp = lcpp.get("temp")
        if temp is not None:
            data_updates["temperature"] = _float(temp)

        if comp.get("top_p") is not None:
            data_updates["top_p"] = _float(comp["top_p"])
        if comp.get("presence_penalty") is not None:
            data_updates["presence_penalty"] = _float(comp["presence_penalty"])
        if comp.get("frequency_penalty") is not None:
            data_updates["frequency_penalty"] = _float(comp["frequency_penalty"])
        if comp.get("seed") is not None:
            data_updates["seed"] = _int(comp["seed"])
        if comp.get("stop") is not None:
            stop = comp["stop"]
            if isinstance(stop, list):
                data_updates["stop"] = [str(s) for s in stop]
            else:
                data_updates["stop"] = [str(stop)]
        if comp.get("n") is not None:
            data_updates["n"] = _int(comp["n"])
        if comp.get("response_format") is not None:
            data_updates["response_format"] = comp["response_format"]
        if comp.get("timeout") is not None:
            data_updates["timeout"] = _float(comp["timeout"])
        if comp.get("logit_bias") is not None and isinstance(comp["logit_bias"], dict):
            data_updates["logit_bias"] = comp["logit_bias"]

        repeat_penalty = comp.get("repeat_penalty") or lcpp.get("repeat_penalty")
        if repeat_penalty is not None:
            rp = _float(repeat_penalty)
            if rp is not None:
                extra_body_updates["repeat_penalty"] = rp

        return data_updates, extra_body_updates

    # Extra-body keys that Google Gemini API does not accept (causes 400 "Unknown name")
    _GEMINI_UNSUPPORTED_EXTRA_KEYS = frozenset({"repeat_penalty"})

    def _filter_extra_body_for_model(self, extra_body_params: dict, model_for_request: Optional[str]) -> dict:
        """Remove extra_body keys that the target model does not support (e.g. Gemini rejects repeat_penalty)."""
        if not extra_body_params or not model_for_request:
            return extra_body_params
        if "gemini" not in model_for_request.lower():
            return extra_body_params
        return {k: v for k, v in extra_body_params.items() if k not in self._GEMINI_UNSUPPORTED_EXTRA_KEYS}

    def _get_llm_semaphore(self):
        """Lazy-create a semaphore to limit concurrent LLM calls (channel + plugin API). Config: llm_max_concurrent (default 1). Thread-safe creation."""
        if getattr(self, '_llm_semaphore', None) is None:
            lock = getattr(Util, '_llm_semaphore_creation_lock', None)
            if lock is None:
                Util._llm_semaphore_creation_lock = threading.Lock()
                lock = Util._llm_semaphore_creation_lock
            with lock:
                if getattr(self, '_llm_semaphore', None) is None:
                    meta = self.get_core_metadata()
                    n = max(1, min(32, int(getattr(meta, 'llm_max_concurrent', 1) or 1)))
                    self._llm_semaphore = asyncio.Semaphore(n)
        return self._llm_semaphore

    async def openai_chat_completion(self, messages: list[dict], 
                                     grammar: str=None,
                                     tools: Optional[List[Dict]] = None,
                                     tool_choice: str = "auto", 
                                     functions: Optional[List] = None,
                                     function_call: Optional[str] = None,
                                     llm_name: Optional[str] = None,
                                     ) -> str | None:    
        sem = self._get_llm_semaphore()
        async with sem:
            return await self._openai_chat_completion_impl(
                messages, grammar=grammar, tools=tools, tool_choice=tool_choice,
                functions=functions, function_call=function_call, llm_name=llm_name,
            )

    async def _openai_chat_completion_impl(self, messages: list[dict],
                                     grammar: str=None,
                                     tools: Optional[List[Dict]] = None,
                                     tool_choice: str = "auto",
                                     functions: Optional[List] = None,
                                     function_call: Optional[str] = None,
                                     llm_name: Optional[str] = None,
                                     ) -> str | None:
        try:
            resolved = Util()._resolve_llm(llm_name)
            if resolved is None:
                resolved = Util().main_llm()
            path_or_model, raw_id, mtype, model_host, model_port = resolved
            model_for_request, headers = Util()._llm_request_model_and_headers(path_or_model, raw_id, mtype)
            data = {}
            if grammar != None and len(grammar) > 0:
                data = {
                    "model": model_for_request,
                    "messages": messages,
                    "extra_body": {
                        "grammar": grammar
                    } 
                }
            else:
                data = {
                    "model": model_for_request,
                    "messages": messages,
                }
            if tools:
                data["tools"] = tools
                data["tool_choice"] = tool_choice
            if functions:
                data["functions"] = functions
            if function_call:
                data["function_call"] = function_call
            data_params, extra_body_params = self._get_completion_params()
            data.update(data_params)
            extra_body_params = self._filter_extra_body_for_model(extra_body_params, model_for_request)
            if extra_body_params:
                data.setdefault("extra_body", {}).update(extra_body_params)
            data_json = None
            if self.is_utf8_compatible(data):
                data_json = json.dumps(data, ensure_ascii=False)
            else:
                data_json = json.dumps(data, ensure_ascii=False).encode('utf-8')

            #logger.debug(f"Message Request to LLM: {data_json}")
            chat_completion_api_url = 'http://' + model_host + ':' + str(model_port) + '/v1/chat/completions'
            timeout_sec = 300
            timeout = aiohttp.ClientTimeout(total=timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(chat_completion_api_url, headers=headers, data=data_json) as resp:
                    resp_json = await resp.text(encoding='utf-8')
                    # Ensure resp_json is a dictionary
                    while isinstance(resp_json, dict) == False:
                        resp_json = json.loads(resp_json)
                    #logger.debug(f"Original Response from LLM: {resp_json}")
                    if isinstance(resp_json, dict) and 'choices' in resp_json:
                        if isinstance(resp_json['choices'], list) and len(resp_json['choices']) > 0:
                            if 'message' in resp_json['choices'][0] and 'content' in resp_json['choices'][0]['message']:
                                message_content = resp_json['choices'][0]['message']['content'].strip()
                                # Filter out the <think> tag and its content
                                filtered_message_content = self.process_text(message_content)
                                if filtered_message_content is not None:
                                    logger.debug(f"Message Response from LLM: {message_content}")
                                    return filtered_message_content
                                else:
                                    #logger.error("filtered message content is None")
                                    return None
                    logger.error("Invalid response structure")
                    return None
        except asyncio.TimeoutError:
            logger.warning("LLM chat completion timed out after {}s ({}:{})", timeout_sec, model_host, model_port)
            return None
        except asyncio.CancelledError:
            logger.info("LLM chat completion was cancelled (e.g. client disconnected)")
            return None
        except Exception as e:
            logger.exception(e)
            return None

    async def plugin_llm_generate(
        self,
        messages: list[dict],
        llm_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Call Core's REST API POST /api/plugins/llm/generate. Use this from built-in plugins so both built-in and external plugins use the same API.
        Returns generated text or None on error. Auth: when auth_enabled, uses auth_api_key from config (X-API-Key header).
        """
        try:
            base_url = self.get_core_url().rstrip('/')
            url = f"{base_url}/api/plugins/llm/generate"
            body = {"messages": messages}
            if llm_name is not None:
                body["llm_name"] = llm_name
            headers = {"Content-Type": "application/json"}
            meta = self.get_core_metadata()
            if getattr(meta, 'auth_enabled', False) and (getattr(meta, 'auth_api_key', '') or '').strip():
                key = (getattr(meta, 'auth_api_key', '') or '').strip()
                headers["X-API-Key"] = key
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    try:
                        data = await resp.json() if (getattr(resp, 'content_type', None) or '').startswith('application/json') else {}
                    except Exception:
                        data = {}
                    if resp.status_code != 200:
                        err = data.get("error") or data.get("detail") or resp.reason or str(resp.status_code)
                        logger.warning("plugin_llm_generate failed: {}", err)
                        return None
                    return (data.get("text") or "").strip() or None
        except Exception as e:
            logger.exception(e)
            return None

    async def openai_chat_completion_message(
        self,
        messages: list[dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        grammar: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Same as openai_chat_completion but returns the full assistant message dict for tool loop.
        Returns: {"role": "assistant", "content": str or None, "tool_calls": [...] or None}.
        Caller can append to messages and, if tool_calls present, execute tools and call again.
        Uses same llm_max_concurrent semaphore as openai_chat_completion.
        """
        sem = self._get_llm_semaphore()
        async with sem:
            return await self._openai_chat_completion_message_impl(
                messages, tools=tools, tool_choice=tool_choice, grammar=grammar,
            )

    async def _openai_chat_completion_message_impl(
        self,
        messages: list[dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        grammar: Optional[str] = None,
    ) -> Optional[dict]:
        try:
            path_or_model, raw_id, mtype, model_host, model_port = Util().main_llm()
            model_for_request, headers = Util()._llm_request_model_and_headers(path_or_model, raw_id, mtype)
            data = {"model": model_for_request, "messages": messages}
            if grammar:
                data["extra_body"] = {"grammar": grammar}
            if tools:
                data["tools"] = tools
                data["tool_choice"] = tool_choice
            data_params, extra_body_params = self._get_completion_params()
            data.update(data_params)
            extra_body_params = self._filter_extra_body_for_model(extra_body_params, model_for_request)
            if extra_body_params:
                data.setdefault("extra_body", {}).update(extra_body_params)
            data_json = json.dumps(data, ensure_ascii=False) if self.is_utf8_compatible(data) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            chat_completion_api_url = "http://" + model_host + ":" + str(model_port) + "/v1/chat/completions"
            # Generous timeout for tool-augmented calls (e.g. search + reply). Prevents indefinite wait.
            timeout_sec = 300
            timeout = aiohttp.ClientTimeout(total=timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(chat_completion_api_url, headers=headers, data=data_json) as resp:
                    resp_json = await resp.json()
                    if isinstance(resp_json, dict) and "choices" in resp_json and len(resp_json["choices"]) > 0:
                        msg = resp_json["choices"][0].get("message", {})
                        # Return message in OpenAI shape: role, content, tool_calls (optional)
                        out = {"role": msg.get("role", "assistant"), "content": msg.get("content") or None}
                        if "tool_calls" in msg and msg["tool_calls"]:
                            out["tool_calls"] = msg["tool_calls"]
                        return out
                    return None
        except asyncio.TimeoutError:
            logger.warning("LLM chat completion timed out after {}s ({}:{})", timeout_sec, model_host, model_port)
            return None
        except asyncio.CancelledError:
            logger.info("LLM chat completion was cancelled (e.g. client disconnected)")
            return None
        except Exception as e:
            logger.exception(e)
            return None

    
    def convert_chats_to_text(self, chats: list[ChatMessage]) -> str:
        text = ""
        for chat in chats:
            text += chat.human_message.content + "\n"
            text += chat.ai_message.content + "\n"
        return text
        

    async def llm_summarize(self, text: str,  lenLimit: int = 4096) -> str:
        if len(text) <= lenLimit or text == None:
            return text
        prompt = MEMORY_SUMMARIZATION_PROMPT
        prompt = prompt.format(text=text, size=lenLimit)
        resp = await self.openai_chat_completion([{"role": "user", "content": prompt}])
        if resp:
            logger.debug(f"Summary from LLM: {resp}")
            return resp
        else:
            logger.debug(f"Failed to get summary from LLM, return the original text, {text}")
            return text   


    def read_config(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config


    def write_config(self, file_path, config):
        with open(file_path, 'w', encoding='utf-8') as file:
            yaml.safe_dump(config, file, default_flow_style=False, sort_keys=False)


    def get_users(self):
        """
        Loads the users from the configuration file.
        Validates that different users have distinct email/im/phone (no overlap).

        Returns:
            Users: The users object, or None if the loading failed.
        """
        if self.users == None:
            self.users = User.from_yaml(os.path.join(self.config_path(), 'user.yml'))
            User.validate_no_overlapping_channel_ids(self.users)
        return self.users
    
    def add_user(self, user: User):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if user.name == u.name:
                return
        if self.users == None:
            self.users = []
        self.users.append(user)
        self.save_users(self.users)

    def remove_user(self, user: User):
        if self.users == None or len(self.users) == 0:
            return
        self.users = self.get_users()
        for u in self.users:
            if user.name == u.name:
                self.users.remove(u)
                self.save_users(self.users)
                break 

    async def embedding(self, text):
        """
        Get the embedding for the given text. Uses the configured embedding model:
        - Local: llama.cpp server (OpenAI-compatible) at the model's host/port.
        - Cloud: LiteLLM proxy at the model's host/port, with API key from env if set.
        RAG splits content before embedding; Cognee handles its own embedding. No summarization here.
        """
        text = text.replace("\n", " ")
        logger.debug(f"LlamaCppEmbedding.embed: text: {text}")

        # Resolve host/port (and optional model + api_key) from configured embedding model (local or cloud)
        resolved = self.embedding_llm()
        if resolved is None:
            host = self.core_metadata.embedding_host
            port = self.core_metadata.embedding_port
            model_for_body = None
            api_key = None
        else:
            path_or_name, _, mtype, host, port = resolved
            model_for_body = path_or_name if mtype == "litellm" else None
            api_key = None
            if mtype == "litellm":
                entry, _ = self._get_model_entry(self.core_metadata.embedding_llm)
                if entry:
                    api_key = (entry.get("api_key") or "").strip() if isinstance(entry.get("api_key"), str) else None
                    if not api_key and entry.get("api_key_name"):
                        api_key = (os.environ.get(entry["api_key_name"].strip()) or "").strip() or None

        embedding_url = "http://" + host + ":" + str(port) + "/v1/embeddings"
        logger.debug(f"Embedding URL: {embedding_url}")
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        body = {"input": text}
        if model_for_body:
            body["model"] = model_for_body
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    embedding_url,
                    headers=headers,
                    data=json.dumps(body),
                ) as response:
                    response_json = await response.json()
                    ret = response_json["data"][0]["embedding"]
                    return ret
        except Exception as e:
            logger.debug("Embedding error:Failed to get embedding from LLM")
            logger.debug(e)
            return None

    def get_user(self, name: str):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if u.name == name:
                return u
        return None
    
    def get_first_user(self) -> User:
        self.users = self.get_users()
        if self.users == None or len(self.users) == 0:
            self.create_default_user()
        return self.users[0]
    
    def create_default_user(self):
        user: User = User()
        user.name = 'HomeClaw'
        user.email = []
        user.phone = []
        user.im = []
        self.add_user(user)

    def change_user_name(self, old_name: str, new_name: str):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if u.name == old_name:
                u.name = new_name
                self.save_users(self.users)
                return

    def add_im_to_user(self, user_name: str, im: str):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if u.name == user_name:
                u.im.append(im)
                self.save_users(self.users)
                return

    def remove_im_from_user(self, user_name: str, im: str):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if u.name == user_name:
                u.im.remove(im)
                self.save_users(self.users)
                return
            
    def add_email_to_user(self, user_name: str, email: str):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if u.name == user_name:
                u.email.append(email)
                self.save_users(self.users)
                return
            
    def remove_email_from_user(self, user_name: str, email: str):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if u.name == user_name:
                u.email.remove(email)
                self.save_users(self.users)
                return
            
    def add_phone_to_user(self, user_name: str, phone: str):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if u.name == user_name:
                u.phone.append(phone)
                self.save_users(self.users)
                return
            
    def remove_phone_from_user(self, user_name: str, phone: str):
        if self.users == None or len(self.users) == 0:
            self.users = self.get_users()
        for u in self.users:
            if u.name == user_name:
                u.phone.remove(phone)
                self.save_users(self.users)
                return
        
    def save_users(self, users: List[User] = None):
        User.to_yaml(users, os.path.join(self.config_path(), 'user.yml'))
    
    def get_email_account(self):
        if self.email_account == None:
            self.email_account = EmailAccount.from_yaml(os.path.join(self.config_path(), 'email_account.yml'))
        return self.email_account

    def get_homeclaw_account(self):
        """Alias for get_email_account (HomeClaw account / email credentials)."""
        return self.get_email_account()

    def save_homeclaw_account(self):
        """Alias for save_email_account."""
        self.save_email_account()
    
    def save_email_account(self):
        self.email_account.to_yaml(os.path.join(self.config_path(), 'email_account.yml'))

    def get_core_metadata(self):
        if self.core_metadata == None:
            self.core_metadata = CoreMetadata.from_yaml(os.path.join(self.config_path(), 'core.yml'))
            if self.has_gpu_cuda():
                if self.core_metadata.main_llm is None or len(self.core_metadata.main_llm) == 0:
                    self.core_metadata.main_llm = self.llm_for_gpu
                    CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))

            else:
                if self.core_metadata.main_llm is None or len(self.core_metadata.main_llm) == 0:
                    self.core_metadata.main_llm = self.llm_for_cpu()
                    CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))
                
        return self.core_metadata
    
    def switch_llm(self, llm_name: str):
        if llm_name not in self.llms:
            return
        self.core_metadata.main_llm = llm_name
        CoreMetadata.to_yaml(self.core_metadata, os.path.join(self.config_path(), 'core.yml'))
    
    def stop_uvicorn_server(self, server: uvicorn.Server):
        try:
            if server:
                server.should_exit = True
                server.force_exit = True
                #await server.shutdown()
        except Exception as e:
            logger.exception(e)
        

    def get_llms(self):
        """Return list of model refs: from local_models + cloud_models if present (as 'local_models/<id>' and 'cloud_models/<id>'), else from .gguf filenames."""
        local = self.core_metadata.local_models or []
        cloud = self.core_metadata.cloud_models or []
        if local or cloud:
            self.llms = [f"local_models/{m['id']}" for m in local if m.get('id')] + [f"cloud_models/{m['id']}" for m in cloud if m.get('id')]
            logger.debug(f"llms (from config): {self.llms}")
            return self.llms
        models_directory = self.models_path()
        if not os.path.exists(models_directory):
            self.llms = []
            return self.llms
        self.llms = [f for f in os.listdir(models_directory) if f.endswith('.gguf') and os.path.isfile(os.path.join(models_directory, f))]
        logger.debug(f"llms (from disk): {self.llms}")
        return self.llms
    
    def available_llms(self):
        llms = self.llms
        if self.core_metadata.embedding_llm in llms:
            llms.remove(self.core_metadata.embedding_llm)
        return llms

    def get_llm_ref_by_capability(self, capability: str):
        """Return a model ref (local_models/<id> or cloud_models/<id>) that has the given capability in its capabilities array. Prefer main_llm if it has the capability; else first match in local then cloud. Case-insensitive. Returns None if no model has that capability."""
        if not capability or not str(capability).strip():
            return None
        cap = str(capability).strip().lower()
        main_llm_name = self.core_metadata.main_llm
        entry, _ = self._get_model_entry(main_llm_name)
        if entry:
            caps = entry.get("capabilities") or []
            if any((str(c).strip().lower() == cap for c in caps)):
                return main_llm_name
        for m in (self.core_metadata.local_models or []):
            mid = m.get("id")
            if not mid:
                continue
            caps = m.get("capabilities") or []
            if any((str(c).strip().lower() == cap for c in caps)):
                return f"local_models/{mid}"
        for m in (self.core_metadata.cloud_models or []):
            mid = m.get("id")
            if not mid:
                continue
            caps = m.get("capabilities") or []
            if any((str(c).strip().lower() == cap for c in caps)):
                return f"cloud_models/{mid}"
        return None
        
    def get_llm(self, name: str):
        entry, mtype = self._get_model_entry(name)
        if entry is not None:
            _, raw_id = self._parse_model_ref(name)
            rid = raw_id or name
            if mtype == 'local':
                path = os.path.normpath(entry.get('path', ''))
                full_path = os.path.join(self.models_path(), path)
                return full_path, rid
            return entry.get('path', rid), rid
        for llm_name in self.llms:
            if llm_name == name:
                return os.path.join(self.models_path(), llm_name), llm_name
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
    
        
    def watch_config_file(self):
        """
        Monitor the user.yml and core.yml changes in the config path.
        If some change happened, the users and core metadata can be reload automatically.
        """
        if self.config_observer is None:  
            class Handler(watchdog.events.PatternMatchingEventHandler):
                def __init__(self, util: Util):
                    super().__init__(patterns=['user.yml'])
                    self.util: Util = util

                def on_modified(self, event):
                    if event.src_path.endswith('user.yml'):
                        self.util.users = None
                        self.util.get_users()
        
      
            self.config_observer = watchdog.observers.Observer()
            self.config_observer.schedule(Handler(self), self.config_path(), recursive=False)
            self.config_observer.start()
                
            # Gracefully stop the observer
            atexit.register(lambda: self.stop_watching_config)
    
    
    def stop_watching_config(self):
        self.config_observer.stop()
        self.config_observer.join()    

        
# Example usage
if __name__ == "__main__":
    # Initialize Util
    util = Util()
    
    # Load and logger.debug core metadata
    core_metadata = util().get_core_metadata()
    logger.debug("core Metadata:", core_metadata)

    # Load and logger.debug users
    users = util().get_users()
    logger.debug("Users:", users)

    # Load and logger.debug llms
    llms = util().get_llms()
    logger.debug("LLMs:", llms)

    # logger.debug main LLM
    #main_llm = util().main_llm()
    #logger.debug("Main LLM:", main_llm)

    # logger.debug embedding LLM
    #embedding_llm = util.embedding_llm()
    #logger.debug("Embedding LLM:", embedding_llm)

