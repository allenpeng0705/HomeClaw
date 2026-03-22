import os
import socket
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
import requests


from memory.chat.message import ChatMessage
from memory.prompts import MEMORY_SUMMARIZATION_PROMPT
from base.base import CoreMetadata, Friend, User, LLM, EmailAccount

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
core_metadata =CoreMetadata.from_yaml(os.path.join(root_dir, 'config', 'core.yml'))
data_root = os.path.join(root_dir, 'database')

# Keys (case-insensitive) whose values are redacted in plugin/tool logs
_SENSITIVE_PARAM_KEYS = frozenset(k.lower() for k in (
    "password", "api_key", "api_key_name", "token", "secret", "authorization",
    "auth", "credentials", "key", "access_token", "refresh_token",
))



def _extract_arg_from_malformed_json(raw: str, key: str) -> Optional[str]:
    """Best-effort extract a string value for key from truncated/malformed JSON. Returns None if not found. Never raises."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    # Match "path":"documents/1.pdf" or "path": "documents/1.pdf" or 'path':'...' (allow escaped quotes in value)
    for pattern in (
        re.compile(r'"' + re.escape(key) + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', re.IGNORECASE),
        re.compile(r"'" + re.escape(key) + r"'\s*:\s*'((?:[^'\\]|\\.)*)'", re.IGNORECASE),
    ):
        m = pattern.search(raw)
        if m:
            return m.group(1).strip()
    return None


def _sanitize_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    """Ensure each tool_call has function.arguments as valid JSON so we never send malformed args back to the server (avoids HTTP 500). Returns a new list; never mutates input. Never raises."""
    if not isinstance(tool_calls, list) or not tool_calls:
        return list(tool_calls) if isinstance(tool_calls, list) else []
    out = []
    for tc in tool_calls:
        try:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                out.append(dict(tc))
                continue
            args_raw = fn.get("arguments")
            if args_raw is None:
                args_raw = "{}"
            if isinstance(args_raw, dict):
                try:
                    args_str = json.dumps(args_raw)
                except (TypeError, ValueError):
                    args_str = "{}"
            else:
                args_str = str(args_raw).strip() if args_raw else "{}"
            try:
                json.loads(args_str)
                sanitized_args = args_str
            except (json.JSONDecodeError, TypeError):
                # Best-effort: extract common keys from truncated/malformed JSON so we don't lose e.g. document_read(path), save_result_page(title, content)
                fallback = {}
                for arg_key in ("path", "skill_name", "title", "content"):
                    val = _extract_arg_from_malformed_json(args_str, arg_key)
                    if val is not None:
                        # Cap recovered "content" to avoid huge payloads (e.g. truncated HTML)
                        if arg_key == "content" and len(val) > 500000:
                            val = val[:500000] + "\n...[truncated]"
                        fallback[arg_key] = val
                if fallback:
                    try:
                        sanitized_args = json.dumps(fallback)
                        logger.debug(
                            "Recovered args from malformed tool_call for {}: {}",
                            fn.get("name") or "?",
                            {k: (v[:80] + "..." if len(str(v)) > 80 else v) for k, v in fallback.items()},
                        )
                    except (TypeError, ValueError):
                        sanitized_args = "{}"
                else:
                    sanitized_args = "{}"
                if not fallback:
                    logger.debug(
                        "Sanitized malformed tool_call arguments (finish_reason=length or invalid JSON); using {} for tool {}",
                        fn.get("name") or "?",
                    )
            fn_copy = dict(fn)
            fn_copy["arguments"] = sanitized_args
            out.append({"id": tc.get("id"), "type": tc.get("type", "function"), "function": fn_copy})
        except Exception as e:
            # Per-item failure: append minimal valid tool_call so we don't drop the call (e.g. save_result_page with huge args)
            try:
                _fn = tc.get("function") if isinstance(tc, dict) else None
                name = (_fn.get("name") if isinstance(_fn, dict) else None) or "unknown"
                out.append({
                    "id": tc.get("id"),
                    "type": tc.get("type", "function"),
                    "function": {"name": name, "arguments": "{}"},
                })
                logger.debug("Sanitize tool_call failed for one item (keeping name), error: {}", e)
            except Exception:
                pass
    if not out and tool_calls:
        # Outer fallback: input had items but we produced nothing; return minimal list so caller doesn't treat as "no tool_calls"
        try:
            for i, tc in enumerate(tool_calls):
                if isinstance(tc, dict):
                    fn = tc.get("function")
                    name = (fn.get("name") if isinstance(fn, dict) else None) or "unknown"
                    out.append({"id": tc.get("id") or f"call_{i}", "type": "function", "function": {"name": name, "arguments": "{}"}})
        except Exception:
            pass
    return out


def strip_reasoning_from_assistant_text(text: Any) -> str:
    """Remove reasoning blocks (e.g. <think>...</think>) from assistant text so it is not stored in memory, chat history, or embeddings. We filter out <think>xxx</think> first, then handle unclosed tags. If no think tags but text looks like 'reasoning then short reply', keep only the last paragraph. Returns stripped string; never raises."""
    if not isinstance(text, str):
        return (str(text).strip() if text is not None else "") or ""
    s = text.strip()
    if not s:
        return ""
    # Step 1: Filter out full <think>...</think> blocks first (optional ">" on </think> so truncated output is still stripped)
    out = re.sub(r"<think>\s*>.*?</think>\s*>?", "", s, flags=re.DOTALL | re.IGNORECASE)
    # Step 2: If <think> without closing </think>, remove from <think> to end (keep text before it)
    match_open = re.search(r"<think>\s*>", out, re.IGNORECASE)
    if match_open:
        out = out[: match_open.start()]
    # Step 3: If </think> without opening <think>, keep only text after the last </think> (match </think> with optional whitespace and optional ">" so we strip even when truncated)
    if re.search(r"</think>\s*>?", out, re.IGNORECASE):
        parts = re.split(r"</think>\s*>?", out, flags=re.IGNORECASE)
        out = parts[-1] if parts else ""
    out = out.strip()
    # Remove leading ">" if the closing tag was </think>> and we split before it
    if out.startswith(">"):
        out = out.lstrip(">").strip()
    # Step 4: No think tags but model output reasoning as plain text (e.g. "The user is asking... According to the instructions... 我是 HomeClaw"). Keep only the last short paragraph so user doesn't see reasoning.
    if out and "<think>" not in s and "</think>" not in s and len(s) > 150:
        _reasoning_marks = (
            "according to the instructions", "the user is asking", "i should respond", "since this appears",
            "however,", "this isn't an identification", "but this isn't", "the instruction says",
        )
        _lower = out.lower()
        if any(m in _lower for m in _reasoning_marks):
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", out) if p.strip()]
            if paragraphs and len(paragraphs[-1]) <= 120:
                out = paragraphs[-1]
    # Normalize excessive newlines so Markdown stays readable (collapse 3+ to 2)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _sanitize_message_content_for_local_tools(content: Any) -> Any:
    """Replace <tool_call>...</tool_call> in string content with [tool call] so local servers that parse input (e.g. GBNF) don't fail at that position. Returns content unchanged if not a string or no tool_call. Never raises."""
    if not isinstance(content, str) or "<tool_call>" not in content:
        return content
    try:
        out = re.sub(r"<tool_call>\s*[\s\S]*?</tool_call>", "[tool call]", content, flags=re.IGNORECASE)
        out = re.sub(r"<tool_call>\s*[\s\S]*", "[tool call]", out, flags=re.IGNORECASE)
        return out
    except Exception:
        return content


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
            try:
                from base import user_store
                self.users = user_store.get_all(self.config_path, self.data_path)
                if not isinstance(self.users, list):
                    self.users = []
            except Exception:
                self.users = []
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
        log_to_console = getattr(self.core_metadata, 'log_to_console', False)
        if log_to_console:
            if self.silent:
                logger.remove(sys.stdout)
                logger.add(sys.stdout, format=log_format, level="INFO")
            else:
                logger.remove(sys.stdout)
                logger.add(sys.stdout, format=log_format, level="DEBUG")
        else:
            logger.remove(sys.stdout)

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
        """Check if CUDA GPU is available. Uses torch if installed, else nvidia-smi (no torch required)."""
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            pass
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except Exception:
            return False


    def root_path(self):
        current_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(current_path)
    
    def log_path(self):
        root = self.root_path()
        return os.path.join(root, 'logs')
    
    def data_path(self):
        root = self.root_path()
        return os.path.join(root, 'database')    

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

    def get_channels_core_api_headers(self) -> dict:
        """Headers for Core API when auth_enabled (X-API-Key, Authorization). From channels/.env CORE_API_KEY. Channels that POST to Core /inbound should use these. Never raises: returns {} on missing/empty key or any error (e.g. bad .env)."""
        try:
            env_path = os.path.join(self.channels_path(), '.env')
            env_vars = dotenv_values(env_path) if os.path.exists(env_path) else {}
            key = (env_vars.get('CORE_API_KEY') or os.getenv('CORE_API_KEY') or '').strip()
            if not key:
                return {}
            return {'x-api-key': key, 'Authorization': f'Bearer {key}'}
        except Exception:
            return {}

    @staticmethod
    def data_url_to_bytes(data_url: str) -> Optional[bytes]:
        """Decode a data URL (e.g. data:image/png;base64,...) to raw bytes. Returns None on failure. Used by channels to send Core response images to the user."""
        if not data_url or not isinstance(data_url, str) or not data_url.strip().startswith("data:"):
            return None
        idx = data_url.find(";base64,")
        if idx < 0:
            return None
        try:
            import base64
            return base64.b64decode(data_url[idx + 8 :].strip(), validate=True)
        except Exception:
            return None

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
        r"""Base path for local models (GGUF, tokenizer, etc.). Uses config model_path when set (relative to project root); else root_path()/models. Resolved with pathlib.Path so paths work on Windows, Mac, and Linux (config may use / or \)."""
        root = self.root_path()
        meta = self.get_core_metadata()
        raw = (getattr(meta, 'model_path', None) or '').strip()
        if raw:
            # Path accepts both / and \ on all platforms; resolve() yields a normalized absolute path
            p = Path(root) / raw
            return str(p.resolve())
        return os.path.join(root, 'models')
    
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
        log_to_console = getattr(self.core_metadata, 'log_to_console', False)
        if mode == "production":
            file_name = module_name + '_production.log'
            log_file = os.path.join(log_path, file_name)
            logger.add(log_file, format="{time} {level} {message}", filter=filter_production, level="INFO", encoding="utf-8")
            if log_to_console:
                logger.add(sys.stdout, format="{time} {level} {message}", filter=filter_production, level="INFO")
        else:
            file_name = module_name + '_debug.log'
            log_file = os.path.join(log_path, file_name)
            if log_to_console:
                if self.silent:
                    logger.add(sys.stdout, format=log_format, level="INFO")
                else:
                    logger.add(sys.stdout, format=log_format, level="DEBUG")
            # The filter is to avoid to record long text into file. UTF-8 so Chinese/special chars display when tailing on Windows (use -Encoding UTF8).
            logger.add(log_file, format=log_format, filter=filter_debug, level="DEBUG", encoding="utf-8")
   
              
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

    def _effective_main_llm_ref(self) -> str:
        """Effective main LLM ref from mode: local -> main_llm_local, cloud -> main_llm_cloud, mix -> default_route's ref; else main_llm. Simplifies config: no need to set main_llm when main_llm_mode is set."""
        mode = (getattr(self.core_metadata, "main_llm_mode", None) or "").strip().lower()
        if mode == "local":
            ref = (getattr(self.core_metadata, "main_llm_local", None) or "").strip()
            if ref:
                return ref
        if mode == "cloud":
            ref = (getattr(self.core_metadata, "main_llm_cloud", None) or "").strip()
            if ref:
                return ref
        if mode == "mix":
            hr = getattr(self.core_metadata, "hybrid_router", None) or {}
            default = (hr.get("default_route") or "local").strip().lower()
            ref = (getattr(self.core_metadata, "main_llm_local", None) or "").strip() if default == "local" else (getattr(self.core_metadata, "main_llm_cloud", None) or "").strip()
            if ref:
                return ref
        return (self.core_metadata.main_llm or "").strip()

    def _effective_main_llm_type(self) -> str:
        """Derive main LLM type from effective main ref: cloud_models/ -> litellm; local_models/ with type ollama -> ollama, else local. Fallback to core_metadata for legacy."""
        ref = self._effective_main_llm_ref()
        list_key, _ = self._parse_model_ref(ref)
        if list_key == "cloud":
            return "litellm"
        if list_key == "local":
            _, mtype = self._get_model_entry(ref)
            return mtype if mtype in ("local", "ollama") else "local"
        return self.core_metadata.main_llm_type or "local"

    def _effective_embedding_llm_type(self) -> str:
        """Derive embedding LLM type from embedding_llm ref: cloud_models/ -> litellm, else local. Fallback to core_metadata for legacy."""
        list_key, _ = self._parse_model_ref(self.core_metadata.embedding_llm)
        if list_key == "cloud":
            return "litellm"
        if list_key == "local":
            return "local"
        return self.core_metadata.embedding_llm_type or "local"

    def _is_ollama_entry(self, entry: Any) -> bool:
        """True if entry is a dict with type == 'ollama'. Safe when entry is None or not a dict."""
        if not isinstance(entry, dict):
            return False
        t = entry.get("type")
        return str(t or "").strip().lower() == "ollama"

    def _ollama_port(self, entry: Any) -> int:
        """Default Ollama port 11434, or entry['port'] if valid. Never raises."""
        try:
            if isinstance(entry, dict) and "port" in entry and entry["port"] is not None:
                return max(1, min(65535, int(entry["port"])))
        except (TypeError, ValueError):
            pass
        return 11434

    def model_entry_available(self, entry: Optional[Dict[str, Any]]) -> bool:
        """False only when config sets available: false on a local_models/cloud_models entry (catalog placeholder). Default True when missing."""
        if not entry or not isinstance(entry, dict):
            return True
        return entry.get("available") is not False

    @staticmethod
    def _normalize_capability_list(val: Any) -> List[Any]:
        """YAML may list capabilities as a string or list; normalize for matching and display."""
        if val is None:
            return []
        if isinstance(val, str):
            s = val.strip()
            return [s] if s else []
        if isinstance(val, list):
            return val
        return []

    def _get_model_entry(self, model_id: str):
        """Resolve model id to (entry_dict, 'local'|'ollama'|'litellm'). model_id can be 'local_models/<id>', 'cloud_models/<id>', or plain id. Returns (None, None) if not found."""
        list_key, raw_id = self._parse_model_ref(model_id)
        if list_key == "local":
            for m in (self.core_metadata.local_models or []):
                if m.get('id') == raw_id:
                    return m, ('ollama' if self._is_ollama_entry(m) else 'local')
            return None, None
        if list_key == "cloud":
            for m in (self.core_metadata.cloud_models or []):
                if m.get('id') == raw_id:
                    return m, 'litellm'
            return None, None
        # No prefix: search local then cloud (backward compat)
        for m in (self.core_metadata.local_models or []):
            if m.get('id') == raw_id:
                return m, ('ollama' if self._is_ollama_entry(m) else 'local')
        for m in (self.core_metadata.cloud_models or []):
            if m.get('id') == raw_id:
                return m, 'litellm'
        return None, None

    def main_llm(self):
        """Return (path_or_model, raw_id, mtype, host, port). Never returns None so callers can always unpack. Uses main_llm_local/main_llm_cloud when main_llm_mode is set (no need for main_llm in config)."""
        main_llm_name = self._effective_main_llm_ref()
        if not main_llm_name:
            main_llm_name = (self.llms[0] if self.llms else "local_models/main_vl_model")
        entry, mtype = self._get_model_entry(main_llm_name)
        if entry is not None:
            _, raw_id = self._parse_model_ref(main_llm_name)
            raw_id = raw_id or main_llm_name
            # Local/ollama: use main_llm_host / main_llm_port. Litellm (cloud): use cloud_llm_host / cloud_llm_port (single proxy for cloud-only and mix).
            if mtype == 'litellm':
                host = str(getattr(self.core_metadata, 'cloud_llm_host', None) or '127.0.0.1').strip() or '127.0.0.1'
                try:
                    port = max(1, min(65535, int(getattr(self.core_metadata, 'cloud_llm_port', None) or 14005)))
                except (TypeError, ValueError):
                    port = 14005
                return entry.get('path', main_llm_name), raw_id, 'litellm', host, port
            host = str(getattr(self.core_metadata, 'main_llm_host', None) or '127.0.0.1').strip() or '127.0.0.1'
            try:
                port = max(1, min(65535, int(getattr(self.core_metadata, 'main_llm_port', None) or 5088)))
            except (TypeError, ValueError):
                port = 5088
            if mtype == 'ollama':
                path = (entry.get('path') or raw_id or '').strip() or raw_id
                return path, raw_id, 'ollama', host, port
            if mtype == 'local':
                path = os.path.normpath(entry.get('path', ''))
                full_path = os.path.join(self.models_path(), path)
                return full_path, raw_id, 'local', host, port
            return entry.get('path', main_llm_name), raw_id, 'litellm', host, port
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

    def main_llm_for_route(self, route: Optional[str] = None) -> Tuple[str, str, str, str, int]:
        """Return (path_or_model, raw_id, mtype, host, port) for the main LLM to use for this request.
        When main_llm_mode is not 'mix', ignores route and returns same as main_llm() (unchanged behavior).
        When main_llm_mode == 'mix' and route in ('local', 'cloud'), returns the tuple for main_llm_local or main_llm_cloud.
        When main_llm_mode == 'mix' and route is None or invalid, uses hybrid_router.default_route (default 'local') then resolves."""
        mode = (getattr(self.core_metadata, "main_llm_mode", None) or "").strip().lower()
        if mode != "mix":
            return self.main_llm()
        ref = None
        if route in ("local", "cloud"):
            ref = (self.core_metadata.main_llm_local or "").strip() if route == "local" else (self.core_metadata.main_llm_cloud or "").strip()
        if not ref:
            hr = getattr(self.core_metadata, "hybrid_router", None) or {}
            default = (hr.get("default_route") or "local").strip().lower()
            ref = (self.core_metadata.main_llm_local or "").strip() if default == "local" else (self.core_metadata.main_llm_cloud or "").strip()
        if not ref:
            return self.main_llm()
        main_llm_name = ref
        entry, mtype = self._get_model_entry(main_llm_name)
        if entry is not None:
            _, raw_id = self._parse_model_ref(main_llm_name)
            raw_id = raw_id or main_llm_name
            # Litellm (cloud): use cloud_llm_host / cloud_llm_port (single proxy for cloud-only and mix).
            if mtype == 'litellm':
                host = str(getattr(self.core_metadata, 'cloud_llm_host', None) or '127.0.0.1').strip() or '127.0.0.1'
                try:
                    port = max(1, min(65535, int(getattr(self.core_metadata, 'cloud_llm_port', None) or 14005)))
                except (TypeError, ValueError):
                    port = 14005
                return entry.get('path', main_llm_name), raw_id, 'litellm', host, port
            host = str(getattr(self.core_metadata, 'main_llm_host', None) or '127.0.0.1').strip() or '127.0.0.1'
            try:
                port = max(1, min(65535, int(getattr(self.core_metadata, 'main_llm_port', None) or 5088)))
            except (TypeError, ValueError):
                port = 5088
            if mtype == 'ollama':
                path = (entry.get('path') or raw_id or '').strip() or raw_id
                return path, raw_id, 'ollama', host, port
            if mtype == 'local':
                path = os.path.normpath(entry.get('path', ''))
                full_path = os.path.join(self.models_path(), path)
                return full_path, raw_id, 'local', host, port
            return entry.get('path', main_llm_name), raw_id, 'litellm', host, port
        return self.main_llm()

    def _llm_request_model_and_headers(self, path_or_model: str, raw_id: str, mtype: str, llm_ref: Optional[str] = None) -> Tuple[str, dict]:
        """Return (model string for request body, headers dict) for local (llama.cpp), ollama, or cloud (LiteLLM).
        When mtype is litellm, api_key is taken from the cloud model entry (llm_ref, e.g. cloud_models/Gemini-2.5-Flash)
        so mix mode and per-model keys work; falls back to main_llm_api_key if no ref or entry has no key.
        Ollama uses path_or_model as the model name (same as litellm); no API key."""
        # LiteLLM/Ollama: use path_or_model (provider/model or ollama model name). Local llama.cpp: use raw_id.
        model_for_request = path_or_model if mtype in ("litellm", "ollama") else (raw_id or path_or_model)
        headers = {"Content-Type": "application/json"}
        if mtype == "litellm":
            key = ""
            if llm_ref and (llm_ref or "").strip():
                entry, _ = self._get_model_entry((llm_ref or "").strip())
                if entry:
                    key = (entry.get("api_key") or "").strip() if isinstance(entry.get("api_key"), str) else ""
                    if not key and entry.get("api_key_name"):
                        key = (os.environ.get((entry.get("api_key_name") or "").strip()) or "").strip()
            if not key:
                key = (getattr(self.core_metadata, "main_llm_api_key", "") or "").strip()
            if key:
                headers["Authorization"] = "Bearer " + key
            else:
                headers["Authorization"] = "Anything"
        else:
            # local (llama.cpp) and ollama: no API key
            headers["Authorization"] = "Anything"
        return model_for_request, headers

    def _resolve_llm(self, llm_name: Optional[str] = None):
        """Return (path, model_id, type, host, port) for llm_name, or for main_llm if llm_name is None/empty. Returns None if llm_name given but not found.
        When the resolved model is the current main LLM, host/port are taken from main_llm_host/main_llm_port.
        When the resolved model is vision_llm, host/port are taken from vision_llm_host/vision_llm_port.
        When the resolved model is tool_selection_llm, host/port are taken from tool_selection_llm_host/tool_selection_llm_port."""
        if llm_name and str(llm_name).strip():
            name = str(llm_name).strip()
            entry, mtype = self._get_model_entry(name)
            if entry is not None:
                main_ref = (self._effective_main_llm_ref() or "").strip()
                use_main_port = main_ref and name.strip() == main_ref
                if use_main_port:
                    host = str(getattr(self.core_metadata, 'main_llm_host', None) or '127.0.0.1').strip() or '127.0.0.1'
                    try:
                        port = max(1, min(65535, int(getattr(self.core_metadata, 'main_llm_port', None) or 5088)))
                    except (TypeError, ValueError):
                        port = 5088
                else:
                    vision_ref = ""
                    try:
                        if getattr(self, 'core_metadata', None):
                            vision_ref = (getattr(self.core_metadata, 'vision_llm', None) or '').strip() or ""
                    except Exception:
                        pass
                    use_vision_port = vision_ref and name.strip() == vision_ref
                    if use_vision_port:
                        host = str(getattr(self.core_metadata, 'vision_llm_host', None) or '127.0.0.1').strip() or '127.0.0.1'
                        try:
                            port = max(1, min(65535, int(getattr(self.core_metadata, 'vision_llm_port', None) or 5024)))
                        except (TypeError, ValueError):
                            port = 5024
                    else:
                        tool_sel_ref = (getattr(self.core_metadata, 'tool_selection_llm', None) or '').strip()
                        use_tool_sel_port = bool(tool_sel_ref and name.strip() == tool_sel_ref)
                        if use_tool_sel_port:
                            host = str(getattr(self.core_metadata, 'tool_selection_llm_host', None) or '127.0.0.1').strip() or '127.0.0.1'
                            try:
                                port = max(1, min(65535, int(getattr(self.core_metadata, 'tool_selection_llm_port', None) or 5031)))
                            except (TypeError, ValueError):
                                port = 5031
                        elif mtype == 'litellm':
                            host = str(getattr(self.core_metadata, 'cloud_llm_host', None) or '127.0.0.1').strip() or '127.0.0.1'
                            try:
                                port = max(1, min(65535, int(getattr(self.core_metadata, 'cloud_llm_port', None) or 14005)))
                            except (TypeError, ValueError):
                                port = 14005
                        else:
                            try:
                                host = str(entry.get('host') or '127.0.0.1').strip() or '127.0.0.1'
                            except Exception:
                                host = '127.0.0.1'
                            try:
                                port = max(1, min(65535, int(entry.get('port', 5088))))
                            except (TypeError, ValueError):
                                port = 5088
                _, raw_id = self._parse_model_ref(name)
                rid = raw_id or name
                if mtype == 'ollama':
                    path = (entry.get('path') or rid or '').strip() or rid
                    if not use_main_port:
                        port = self._ollama_port(entry)
                    return path, rid, 'ollama', host, port
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
        if self._effective_main_llm_type() in ("local", "ollama"):
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
        """Return (path, raw_id, mtype, host, port). Embedding always uses embedding_host / embedding_port for connection; per-model host/port are for multi-model use."""
        embedding_llm_name = self.core_metadata.embedding_llm
        entry, mtype = self._get_model_entry(embedding_llm_name)
        if entry is not None:
            _, raw_id = self._parse_model_ref(embedding_llm_name)
            raw_id = raw_id or embedding_llm_name
            host = str(getattr(self.core_metadata, 'embedding_host', None) or '127.0.0.1').strip() or '127.0.0.1'
            try:
                port = max(1, min(65535, int(getattr(self.core_metadata, 'embedding_port', None) or 5066)))
            except (TypeError, ValueError):
                port = 5066
            if mtype == 'ollama':
                path = (entry.get('path') or raw_id or '').strip() or raw_id
                return path, raw_id, 'ollama', host, port
            if mtype == 'local':
                path = os.path.normpath(entry.get('path', ''))
                full_path = os.path.join(self.models_path(), path)
                return full_path, raw_id, 'local', host, port
            return entry.get('path', embedding_llm_name), raw_id, 'litellm', host, port
        eff_type = self._effective_embedding_llm_type()
        if eff_type == "local":
            for llm_name in self.llms:
                if llm_name == embedding_llm_name:
                    return os.path.join(self.models_path(), llm_name), llm_name, eff_type, self.core_metadata.embedding_host, self.core_metadata.embedding_port
            return None
        return embedding_llm_name, embedding_llm_name, eff_type, self.core_metadata.embedding_host, self.core_metadata.embedding_port
        
            
    def main_llm_size(self):
        eff_ref = self._effective_main_llm_ref()
        _, raw = self._parse_model_ref(eff_ref)
        name = (raw or eff_ref).lower()  
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
            main_llm_name = self._effective_main_llm_ref()
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

    def main_llm_supported_media_for_ref(self, model_ref: str) -> List[str]:
        """Return supported_media (image/audio/video) for a given model ref (e.g. main_llm_local or main_llm_cloud).
        Used in mix mode to decide if we should force cloud when request has images and local does not support vision."""
        try:
            ref = (model_ref or "").strip()
            if not ref:
                return []
            entry, mtype = self._get_model_entry(ref)
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
                    return normalize(explicit)
                if mtype == "litellm":
                    return ["image", "audio", "video"]
                if mtype == "local":
                    if entry.get("mmproj"):
                        return ["image"]
                    return []
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
        # Strip <think>...</think> (or text before </think>) so reasoning is not shown; use shared implementation
        if isinstance(text, str) and ("<think>" in text or "</think>" in text):
            processed_text = strip_reasoning_from_assistant_text(text)
        else:
            processed_text = text if isinstance(text, str) else (str(text) if text is not None else "")
        
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
    
    def _is_port_open(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """Return True if a TCP connection to host:port can be opened (something is listening)."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (socket.error, OSError):
            return False

    def check_embedding_model_server_health(self, timeout: Optional[int] = None) -> bool:
        """Check if the embedding server is ready. Tries GET /health first; on 404/ConnectionError tries GET /v1/models (OpenAI-compatible). Timeout from config embedding_health_check_timeout_sec or 120."""
        meta = self.get_core_metadata()
        _timeout = timeout if timeout is not None else max(30, int(getattr(meta, "embedding_health_check_timeout_sec", 120) or 120))
        res = self.embedding_llm()
        if not res or len(res) < 5:
            logger.error("Embedding LLM not configured; cannot check health.")
            return False
        _, model, _type, model_host, model_port = res
        base_url = f"http://{model_host}:{model_port}"
        health_url = f"{base_url}/health"
        models_url = f"{base_url}/v1/models"
        logger.info("Embedding health check: {} (timeout {}s)", health_url, _timeout)
        start_time = time.time()
        last_err = None
        last_progress_log_at = [0]  # elapsed seconds when we last logged progress

        while time.time() - start_time < _timeout:
            elapsed = int(time.time() - start_time)
            port_open = self._is_port_open(model_host, model_port)

            try:
                response = requests.get(health_url, timeout=10)
                if response.status_code == 200:
                    logger.info("Embedding server is ready ({}s).", elapsed)
                    return True
                if response.status_code == 503:
                    last_err = "503 (server still loading)"
                    time.sleep(1)
                    continue
                if response.status_code == 404:
                    last_err = "404 on /health (port open)"
            except requests.exceptions.ConnectionError as e:
                last_err = "connection refused" if not port_open else str(e)
            except requests.exceptions.RequestException as e:
                last_err = str(e)
            # Fallback: some llama-server builds use /v1/models for readiness
            try:
                r2 = requests.get(models_url, timeout=5)
                if r2.status_code == 200:
                    logger.info("Embedding server ready via /v1/models ({}s).", elapsed)
                    return True
            except requests.exceptions.RequestException:
                pass
            # Log progress every 15s so we know what is blocking
            if elapsed - last_progress_log_at[0] >= 15:
                logger.warning(
                    "Embedding server not ready after {}s. Port {}:{} open: {}. Last: {}.",
                    elapsed, model_host, model_port, port_open, last_err or "waiting",
                )
                last_progress_log_at[0] = elapsed
            time.sleep(1)
        emb_res = self.embedding_llm()
        _port = emb_res[4] if emb_res and len(emb_res) > 4 else 5066
        port_open_final = self._is_port_open(model_host, _port)
        logger.error(
            "Embedding server did not become ready within {} seconds. Diagnostic: port {}:{} open={}. Last error: {}. "
            "Check above for: (1) 'Model file not found' or 'Using fallback model path'; (2) 'llama-server not found'; (3) 'Port ... already in use'; (4) 'llama.cpp server exited quickly. stderr: ...'.",
            _timeout, model_host, _port, port_open_final, last_err or "timeout",
        )
        return False

    def _get_completion_and_llama_cpp_for_llm(self, llm_name: Optional[str] = None) -> Tuple[Dict, Dict]:
        """Return (completion, llama_cpp) merged for the given llm_name. When llm_name matches vision_llm or tool_selection_llm, merge per-role overrides."""
        meta = self.get_core_metadata()
        comp = getattr(meta, "completion", None) if meta is not None else None
        lcpp = getattr(meta, "llama_cpp", None) if meta is not None else None
        if not isinstance(comp, dict):
            comp = {}
        if not isinstance(lcpp, dict):
            lcpp = {}
        name = (llm_name or "").strip()
        vision_ref = (getattr(meta, "vision_llm", None) or "").strip() if meta is not None else ""
        tool_ref = (getattr(meta, "tool_selection_llm", None) or "").strip() if meta is not None else ""
        if name == vision_ref and vision_ref:
            _cv = getattr(meta, "completion_vision", None) if meta is not None else None
            if isinstance(_cv, dict):
                comp = {**comp, **_cv}
            _vis = lcpp.get("vision") if isinstance(lcpp.get("vision"), dict) else {}
            lcpp_base = {k: v for k, v in lcpp.items() if k not in ("embedding", "vision", "tool_selection")}
            lcpp = {**lcpp_base, **_vis}
        elif name == tool_ref and tool_ref:
            _ct = getattr(meta, "completion_tool_selection", None) if meta is not None else None
            if isinstance(_ct, dict):
                comp = {**comp, **_ct}
            _ts = lcpp.get("tool_selection") if isinstance(lcpp.get("tool_selection"), dict) else {}
            lcpp_base = {k: v for k, v in lcpp.items() if k not in ("embedding", "vision", "tool_selection")}
            lcpp = {**lcpp_base, **_ts}
        return comp, lcpp

    def _get_qwen_model_for_llm(self, llm_name: Optional[str] = None) -> Optional[str]:
        """Return qwen_mode for the given llm_name: from merged llama_cpp for that LLM (so main uses root, tool_selection uses llama_cpp.tool_selection then root). Falls back to root when not set per-role."""
        try:
            _, lcpp = self._get_completion_and_llama_cpp_for_llm(llm_name)
            if isinstance(lcpp, dict):
                val = lcpp.get("qwen_mode") or lcpp.get("qwen_model")
                if val is not None:
                    s = str(val).strip().lower()
                    if s in ("qwen3", "qwen35"):
                        return s
        except Exception:
            pass
        return self._get_qwen_model()

    def _get_completion_params(self, max_tokens_override: Optional[int] = None, llm_name: Optional[str] = None) -> Tuple[Dict, Dict]:
        """
        Build completion request params from config/core.yml completion (and llama_cpp fallbacks).
        Returns (data_updates, extra_body_updates). Merge into request data and data["extra_body"].
        When max_tokens_override is set (e.g. for long-output turns like HTML slides/reports), use it instead of completion.max_tokens.
        When llm_name is set, use per-role completion_vision/completion_tool_selection and llama_cpp.vision/.tool_selection if the ref matches.
        """
        comp, lcpp = self._get_completion_and_llama_cpp_for_llm(llm_name)
        data_updates = {}
        extra_body_updates = {}

        try:
            if max_tokens_override is not None and int(max_tokens_override) > 0:
                max_tokens = int(max_tokens_override)
            else:
                _raw = comp.get("max_tokens") or lcpp.get("predict") or 8192
                max_tokens = int(_raw) if _raw is not None else 8192
            data_updates["max_tokens"] = max(1, max_tokens)
        except (TypeError, ValueError):
            data_updates["max_tokens"] = 8192

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
        # stop: completion.stop overrides; fallback to llama_cpp.stop for local models
        stop = comp.get("stop") if comp.get("stop") is not None else lcpp.get("stop")
        if stop is not None:
            if isinstance(stop, list):
                data_updates["stop"] = [str(s) for s in stop]
            else:
                data_updates["stop"] = [str(stop)]
        # When reasoning_budget is not 0 (thinking allowed), do NOT stop at </think> or the answer after <think> will be truncated
        _rb = lcpp.get("reasoning_budget") if isinstance(lcpp, dict) else None
        _allow_thinking = True
        if _rb is not None:
            try:
                _allow_thinking = int(_rb) != 0
            except (TypeError, ValueError):
                pass
        if data_updates.get("stop") and _allow_thinking:
            _stop = data_updates["stop"]
            if isinstance(_stop, list):
                data_updates["stop"] = [s for s in _stop if "</think>" not in str(s).strip().lower()]
            elif isinstance(_stop, str) and "</think>" in _stop.strip().lower():
                data_updates["stop"] = []
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

    @staticmethod
    def _get_qwen_model() -> Optional[str]:
        """
        One flag for Qwen variants: "qwen3" (8B), "qwen35" (9B), or None (others).
        Single entry point: llm.yml → llama_cpp.qwen_mode or llama_cpp.qwen_model only.
        """
        try:
            meta = Util().get_core_metadata()
            if meta is None:
                return None
            llama_cpp = getattr(meta, "llama_cpp", None)
            if not isinstance(llama_cpp, dict):
                llama_cpp = {}
            val = llama_cpp.get("qwen_mode") or llama_cpp.get("qwen_model")
            if val is not None:
                s = str(val).strip().lower()
                if s in ("qwen3", "qwen35"):
                    return s
        except Exception:
            pass
        return None

    @staticmethod
    def _qwen35_use_grammar() -> bool:
        """
        Whether to send the Qwen 3.5 GBNF grammar when qwen35 + tools. Default False:
        we support both JSON and XML <tool_call> via prompt + parsing, so grammar is optional.
        Set llama_cpp.qwen35_use_grammar: true in llm.yml to enable strict grammar sampling.
        """
        try:
            meta = Util().get_core_metadata()
            if meta is None:
                return False
            llama_cpp = getattr(meta, "llama_cpp", None)
            if not isinstance(llama_cpp, dict):
                llama_cpp = {}
            v = llama_cpp.get("qwen35_use_grammar")
            if v is not None:
                if isinstance(v, bool):
                    return v
                if str(v).strip().lower() in ("true", "1", "yes", "on"):
                    return True
                if str(v).strip().lower() in ("false", "0", "no", "off"):
                    return False
            return False
        except Exception:
            return False

    @staticmethod
    def get_qwen35_grammar() -> Optional[str]:
        """
        Load Qwen 3.5 GBNF grammar. Used when qwen_mode/qwen_model == "qwen35" and tools are present.
        Grammar choice from reasoning_budget: 0 → qwen35_tools.gbnf (no <think>); -1 or non-zero → qwen35_tools_with_think.gbnf (optional <think>...</think>).
        Base path from llama_cpp.qwen35_grammar_path (default: config/grammars/qwen35_tools.gbnf).
        """
        try:
            meta = Util().get_core_metadata()
            if meta is None:
                return None
            llama_cpp = getattr(meta, "llama_cpp", None)
            if not isinstance(llama_cpp, dict):
                llama_cpp = {}
            rel = llama_cpp.get("qwen35_grammar_path") or "config/grammars/qwen35_tools.gbnf"
            rel = (str(rel).strip() if rel is not None else "") or "config/grammars/qwen35_tools.gbnf"
            root = Path(__file__).resolve().parent.parent
            path = (root / rel).resolve()
            # reasoning_budget 0 → no think block; -1 or other → allow <think> (use _with_think grammar)
            use_with_think = True
            rb = llama_cpp.get("reasoning_budget")
            if rb is not None:
                try:
                    if int(rb) == 0:
                        use_with_think = False
                except (TypeError, ValueError):
                    pass
            if use_with_think:
                with_think_path = path.parent / "qwen35_tools_with_think.gbnf"
                if with_think_path.is_file():
                    return with_think_path.read_text(encoding="utf-8")
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except Exception:
            pass
        return None

    @staticmethod
    def _qwen3_xlam_style_for_llm(llm_name: Optional[str]) -> bool:
        """
        True when the given LLM is the tool_selection_llm and llama_cpp.tool_selection has qwen3_xlam_style enabled.
        Used for Qwen3-4B xLAM/Codex (e.g. Manojb/Qwen3-4B-toolcalling-gguf-codex): tools in prompt, xLAM grammar, no tools array.
        """
        try:
            meta = Util().get_core_metadata()
            if meta is None:
                return False
            tool_sel = (getattr(meta, "tool_selection_llm", None) or "").strip()
            if not tool_sel or (llm_name or "").strip() != tool_sel:
                return False
            llama_cpp = getattr(meta, "llama_cpp", None) or {}
            ts = llama_cpp.get("tool_selection") if isinstance(llama_cpp.get("tool_selection"), dict) else {}
            v = ts.get("qwen3_xlam_style")
            if v is True:
                return True
            if v is not None and str(v).strip().lower() in ("true", "1", "yes", "on"):
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def get_qwen3_xlam_grammar() -> Optional[str]:
        """
        Load Qwen3 xLAM/Codex GBNF grammar (config/grammars/qwen3_xlam.gbnf by default).
        Used when tool_selection_llm is Qwen3-4B Codex and llama_cpp.tool_selection.qwen3_xlam_style is true.
        Path from llama_cpp.tool_selection.qwen3_xlam_grammar_path.
        """
        try:
            meta = Util().get_core_metadata()
            if meta is None:
                return None
            llama_cpp = getattr(meta, "llama_cpp", None) or {}
            ts = llama_cpp.get("tool_selection") if isinstance(llama_cpp.get("tool_selection"), dict) else {}
            rel = ts.get("qwen3_xlam_grammar_path") or "config/grammars/qwen3_xlam.gbnf"
            rel = (str(rel).strip() if rel is not None else "") or "config/grammars/qwen3_xlam.gbnf"
            root = Path(__file__).resolve().parent.parent
            path = (root / rel).resolve()
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except Exception:
            pass
        return None

    @staticmethod
    def _format_tools_for_prompt(tools: List[Dict]) -> str:
        """Format OpenAI-style tools list as text for injection into the prompt (Qwen 3.5 + grammar: no tools array)."""
        if not tools:
            return ""
        lines = ["## Available tools", "Use these tools when needed. Respond with <tool_call>...</tool_call> as required.", ""]
        for t in tools:
            if not isinstance(t, dict):
                continue
            fn = t.get("function") if t.get("type") == "function" else t.get("function", t)
            if not isinstance(fn, dict):
                continue
            name = fn.get("name") or "unknown"
            desc = (fn.get("description") or "").strip()
            params = fn.get("parameters")
            lines.append(f"- **{name}**: {desc or '(no description)'}")
            if isinstance(params, dict):
                try:
                    lines.append("  Parameters (JSON schema): " + json.dumps(params, ensure_ascii=False))
                except Exception:
                    lines.append("  Parameters: (see schema)")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _format_tools_for_prompt_xlam(tools: List[Dict]) -> str:
        """Format tools for xLAM/Codex: wrap in <tools></tools> and add the instruction that mentions <tool_call></tool_call>."""
        if not tools:
            return ""
        preamble = (
            "You are an expert at using tools. You are provided with function signatures within <tools></tools> XML tags. "
            "For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags."
        )
        parts = ["<tools>"]
        for t in tools:
            if not isinstance(t, dict):
                continue
            fn = t.get("function") if t.get("type") == "function" else t.get("function", t)
            if not isinstance(fn, dict):
                continue
            name = fn.get("name") or "unknown"
            desc = (fn.get("description") or "").strip()
            params = fn.get("parameters")
            try:
                params_str = json.dumps(params, ensure_ascii=False) if isinstance(params, dict) else "{}"
            except Exception:
                params_str = "{}"
            parts.append(f"  - name: {name}\n    description: {desc or '(no description)'}\n    parameters: {params_str}")
        parts.append("</tools>")
        return preamble + "\n\n" + "\n".join(parts)

    @staticmethod
    def _inject_tools_into_messages(messages: List[Dict], tools_text: str) -> List[Dict]:
        """Prepend tools text to the first system message, or add a system message. Returns a new list of messages."""
        if not tools_text or not messages:
            return list(messages)
        out = []
        injected = False
        for m in messages:
            if not isinstance(m, dict):
                out.append(m)
                continue
            m_copy = dict(m)
            if not injected and (m_copy.get("role") == "system"):
                existing = (m_copy.get("content") or "")
                if isinstance(existing, str):
                    m_copy["content"] = tools_text + "\n\n" + existing
                else:
                    m_copy["content"] = tools_text + "\n\n" + str(existing)
                injected = True
            out.append(m_copy)
        if not injected:
            out.insert(0, {"role": "system", "content": tools_text})
        return out

    def _filter_extra_body_for_model(self, extra_body_params: dict, model_for_request: Optional[str]) -> dict:
        """Remove extra_body keys that the target model does not support (e.g. Gemini rejects repeat_penalty)."""
        if not extra_body_params or not model_for_request:
            return extra_body_params
        if "gemini" not in model_for_request.lower():
            return extra_body_params
        return {k: v for k, v in extra_body_params.items() if k not in self._GEMINI_UNSUPPORTED_EXTRA_KEYS}

    def _get_llm_semaphore(self, mtype: str):
        """Lazy-create semaphores for local (llama.cpp), ollama, and cloud (LiteLLM). mtype 'local' or 'ollama' use llm_max_concurrent_local; 'litellm' uses llm_max_concurrent_cloud. Never raises: uses defaults on bad config."""
        lock = getattr(Util, '_llm_semaphore_creation_lock', None)
        if lock is None:
            Util._llm_semaphore_creation_lock = threading.Lock()
            lock = Util._llm_semaphore_creation_lock
        with lock:
            if getattr(self, '_llm_semaphore_local', None) is None or getattr(self, '_llm_semaphore_cloud', None) is None:
                n_local, n_cloud = 1, 4
                try:
                    meta = self.get_core_metadata()
                    n_local_raw = int(getattr(meta, 'llm_max_concurrent_local', 1) or 1)
                    n_cloud_raw = int(getattr(meta, 'llm_max_concurrent_cloud', 4) or 4)
                    n_local = max(1, min(32, n_local_raw))
                    n_cloud = max(1, min(32, n_cloud_raw))
                except (TypeError, ValueError, AttributeError, Exception):
                    pass
                self._llm_semaphore_local = asyncio.Semaphore(n_local)
                self._llm_semaphore_cloud = asyncio.Semaphore(n_cloud)
        return self._llm_semaphore_local if mtype in ('local', 'ollama') else self._llm_semaphore_cloud

    async def openai_chat_completion(self, messages: list[dict], 
                                     grammar: str=None,
                                     tools: Optional[List[Dict]] = None,
                                     tool_choice: str = "auto", 
                                     functions: Optional[List] = None,
                                     function_call: Optional[str] = None,
                                     llm_name: Optional[str] = None,
                                     ) -> str | None:
        resolved = self._resolve_llm(llm_name) or self.main_llm()
        mtype = resolved[2] if (resolved and len(resolved) > 2) else 'local'
        sem = self._get_llm_semaphore(mtype)
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
            if not resolved or len(resolved) < 5:
                logger.warning("LLM resolve failed: resolved=%s; skipping request", type(resolved).__name__ if resolved is not None else "None")
                return None
            path_or_model, raw_id, mtype, model_host, model_port = resolved
            _meta = Util().get_core_metadata()
            llm_ref = (llm_name or "").strip() if (llm_name and str(llm_name).strip()) else (getattr(_meta, "main_llm", None) or "").strip() if _meta else ""
            if mtype == "litellm":
                try:
                    from hybrid_router.metrics import log_cloud_usage
                    log_cloud_usage()
                except Exception:
                    pass
            model_for_request, headers = Util()._llm_request_model_and_headers(path_or_model, raw_id, mtype, llm_ref=llm_ref)
            qwen_model = self._get_qwen_model_for_llm(llm_name)
            _grammar_ok = isinstance(grammar, str) and len(grammar) > 0
            use_tools_in_prompt_q35 = (
                _grammar_ok and tools
                and mtype in ("local", "ollama")
                and qwen_model == "qwen35"
                and Util._qwen35_use_grammar()
            )
            use_tools_in_prompt_xlam = (
                _grammar_ok and tools
                and mtype in ("local", "ollama")
                and qwen_model == "qwen3"
                and Util._qwen3_xlam_style_for_llm(llm_name)
            )
            use_tools_in_prompt = use_tools_in_prompt_q35 or use_tools_in_prompt_xlam
            data = {"model": model_for_request, "messages": messages}
            if use_tools_in_prompt:
                tools_text = (
                    self._format_tools_for_prompt_xlam(tools)
                    if use_tools_in_prompt_xlam
                    else self._format_tools_for_prompt(tools)
                )
                if tools_text:
                    data["messages"] = self._inject_tools_into_messages(data["messages"], tools_text)
                logger.debug(
                    "LLM request: %s: tools injected into prompt, not sending tools array",
                    "Qwen3 xLAM" if use_tools_in_prompt_xlam else "Qwen 3.5 + grammar",
                )
            if grammar and isinstance(grammar, str) and len(grammar) > 0:
                # llama.cpp returns 400 when both grammar and tools array are present. For Qwen 3.5 we use tools-in-prompt (omit tools array) so grammar can be sent.
                if use_tools_in_prompt:
                    if mtype in ("local", "ollama"):
                        data["grammar"] = grammar
                    else:
                        data.setdefault("extra_body", {})["grammar"] = grammar
                elif mtype in ("local", "ollama") and tools:
                    pass  # do not add grammar
                elif mtype in ("local", "ollama"):
                    data["grammar"] = grammar
                else:
                    data.setdefault("extra_body", {})["grammar"] = grammar
            if tools and not use_tools_in_prompt:
                data["tools"] = tools
                data["tool_choice"] = tool_choice
            if functions:
                data["functions"] = functions
            if function_call:
                data["function_call"] = function_call
            data_params, extra_body_params = self._get_completion_params(llm_name=llm_name)
            data.update(data_params)
            meta = Util().get_core_metadata()
            comp, llama_cpp = self._get_completion_and_llama_cpp_for_llm(llm_name)
            if meta is None:
                tools_cfg = {}
            else:
                tools_cfg = getattr(meta, "tools_config", None) or {}
                if not isinstance(tools_cfg, dict):
                    tools_cfg = {}
            # When tools are present (or tools-in-prompt): qwen_model "qwen3" or "qwen35" -> tool_temperature 0.1, disable thinking; qwen35 -> presence_penalty 1.5, stop </think> and "</tool_call>".
            if tools:
                if qwen_model in ("qwen3", "qwen35"):
                    tool_temp = llama_cpp.get("tool_temperature") or comp.get("tool_temperature") or tools_cfg.get("tool_temperature") or 0.1
                    try:
                        data["temperature"] = float(tool_temp)
                    except (TypeError, ValueError):
                        pass
                    # When reasoning_budget is 0, or when user sets disable_thinking_when_tools: true, send enable_thinking: false. Default is false (do not send) so server keeps thinking on and tool_calls/truncation stay stable; set true only if you see empty content with reasoning_content full.
                    _rb = llama_cpp.get("reasoning_budget")
                    _disable = False
                    if _rb is not None:
                        try:
                            _disable = int(_rb) == 0
                        except (TypeError, ValueError):
                            _disable = str(_rb).strip() == "0"
                    _disable_for_tools = llama_cpp.get("disable_thinking_when_tools")
                    if _disable_for_tools is None:
                        _disable_for_tools = False  # default: preserve server default (thinking on) to avoid truncation / no tool_calls; set true in config only if you need to fix empty content
                    if (_disable or (tools and _disable_for_tools)) and mtype in ("local", "ollama"):
                        eb = data.setdefault("extra_body", {})
                        eb["chat_template_kwargs"] = {"enable_thinking": False}
                        eb["enable_thinking"] = False
                        if tools and not _disable:
                            logger.debug("LLM request: enable_thinking=false for tool turn so full response goes to content (avoid empty content + reasoning_content only)")
                else:
                    tool_temp = comp.get("tool_temperature") or tools_cfg.get("tool_temperature")
                    if tool_temp is not None:
                        try:
                            data["temperature"] = float(tool_temp)
                        except (TypeError, ValueError):
                            pass
                    disable_thinking = comp.get("disable_thinking_when_tools") or tools_cfg.get("disable_thinking_when_tools")
                    if disable_thinking and mtype in ("local", "ollama"):
                        eb = data.setdefault("extra_body", {})
                        eb["chat_template_kwargs"] = {"enable_thinking": False}
                        eb["enable_thinking"] = False
                if qwen_model == "qwen35":
                    data["presence_penalty"] = 1.5
                    # stop: from config only (completion.stop or llama_cpp.stop in llm.yml). See comments there for Qwen/Qwen35.
            if mtype == "local":
                _cp = llama_cpp.get("cache_prompt")
                if _cp is None:
                    _cp = True
                if _cp:
                    data["cache_prompt"] = True
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
            meta = Util().get_core_metadata()
            _raw = getattr(meta, 'llm_completion_timeout_seconds', 300) if meta is not None else 300
            try:
                _raw = 300 if _raw is None else int(_raw)
            except (TypeError, ValueError):
                _raw = 300
            timeout_sec = None if _raw == 0 else max(60, _raw)  # 0 = no timeout (long tasks allowed; use shortcuts for simple replies)
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
                            choice0 = resp_json['choices'][0]
                            msg = (choice0.get('message') or {}) if isinstance(choice0, dict) else {}
                            if not isinstance(msg, dict):
                                msg = {}
                            content_val = msg.get('content') or None
                            try:
                                content_len = len(content_val) if isinstance(content_val, (str, bytes)) else (len(content_val) if content_val is not None and hasattr(content_val, "__len__") else 0)
                            except Exception:
                                content_len = 0
                            tool_calls_raw = msg.get('tool_calls')
                            tool_calls_list = tool_calls_raw if isinstance(tool_calls_raw, list) else []
                            num_tool_calls = len(tool_calls_list)
                            logger.info(
                                "LLM responded ({}:{}): role={} content_length={} tool_calls={}",
                                model_host, model_port,
                                msg.get('role', 'assistant'),
                                content_len,
                                num_tool_calls,
                            )
                            try:
                                content_preview = (content_val if isinstance(content_val, str) else str(content_val))[:2000] if content_val is not None else "(empty)"
                            except Exception:
                                content_preview = "(unable to preview)"
                            logger.debug("LLM response content: {}", content_preview)
                            if 'content' in msg and msg['content']:
                                message_content = msg['content'].strip() if isinstance(msg['content'], str) else ""
                                # Filter out the <think> tag and its content
                                filtered_message_content = self.process_text(message_content)
                                if filtered_message_content is not None:
                                    return filtered_message_content
                                else:
                                    #logger.error("filtered message content is None")
                                    return None
                    logger.error("Invalid response structure")
                    return None
        except asyncio.TimeoutError:
            logger.warning(
                "LLM chat completion timed out after {}s ({}:{})",
                timeout_sec if timeout_sec is not None else "(no limit)",
                model_host,
                model_port,
            )
            return None
        except asyncio.CancelledError:
            logger.info("LLM chat completion was cancelled (e.g. client disconnected)")
            return None
        except Exception as e:
            err_str = str(e).lower()
            _is_conn_err = (
                "connection refused" in err_str
                or "connection reset" in err_str
                or "cannot connect" in err_str
                or "refused" in err_str
                or "network name is no longer available" in err_str
                or "winerror 64" in err_str
                or isinstance(e, (ConnectionResetError, ConnectionAbortedError))
                or (isinstance(e, OSError) and getattr(e, "winerror", None) == 64)
            )
            if not _is_conn_err and hasattr(e, "__cause__") and e.__cause__ is not None:
                _is_conn_err = isinstance(e.__cause__, (ConnectionResetError, ConnectionAbortedError))
            if _is_conn_err:
                logger.warning(
                    "LLM unreachable at {}:{} — model server may have stopped or connection dropped (e.g. WinError 64). "
                    "Core can be running while the server on this port is not. Start the model server or restart Core. Timeouts are separate ('timed out after Xs'). Error: {}",
                    model_host, model_port, e,
                )
            else:
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
        llm_name: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        stop_extra: Optional[List[str]] = None,
    ) -> Optional[dict]:
        """
        Same as openai_chat_completion but returns the full assistant message dict for tool loop.
        Returns: {"role": "assistant", "content": str or None, "tool_calls": [...] or None}.
        Caller can append to messages and, if tool_calls present, execute tools and call again.
        Uses same llm_max_concurrent_local / llm_max_concurrent_cloud semaphores as openai_chat_completion.
        When llm_name is set (e.g. mix-mode route ref), uses that model for this call.
        When max_tokens_override is set (e.g. for long-output turns like HTML slides/reports), uses it instead of completion.max_tokens to avoid truncation.
        When stop_extra is set, those strings are appended to the stop list (if not already present). Use for conditional stop (e.g. add "</tool_call>" only on tool-decision turns).
        """
        resolved = self._resolve_llm(llm_name) or self.main_llm()
        mtype = resolved[2] if (resolved and len(resolved) > 2) else 'local'
        sem = self._get_llm_semaphore(mtype)
        async with sem:
            return await self._openai_chat_completion_message_impl(
                messages, tools=tools, tool_choice=tool_choice, grammar=grammar, llm_name=llm_name,
                max_tokens_override=max_tokens_override, stop_extra=stop_extra,
            )

    async def _openai_chat_completion_message_impl(
        self,
        messages: list[dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        grammar: Optional[str] = None,
        llm_name: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        stop_extra: Optional[List[str]] = None,
    ) -> Optional[dict]:
        try:
            if llm_name and str(llm_name).strip():
                resolved = self._resolve_llm(llm_name.strip())
            else:
                resolved = None
            if resolved is None:
                resolved = Util().main_llm()
            if not resolved or len(resolved) < 5:
                logger.warning("LLM resolve failed (message): resolved=%s; skipping request", type(resolved).__name__ if resolved is not None else "None")
                return None
            path_or_model, raw_id, mtype, model_host, model_port = resolved
            _meta = Util().get_core_metadata()
            llm_ref = (llm_name or "").strip() if (llm_name and str(llm_name).strip()) else (getattr(_meta, "main_llm", None) or "").strip() if _meta else ""
            if mtype == "litellm":
                try:
                    from hybrid_router.metrics import log_cloud_usage
                    log_cloud_usage()
                except Exception:
                    pass
            model_for_request, headers = Util()._llm_request_model_and_headers(path_or_model, raw_id, mtype, llm_ref=llm_ref)
            # Local/ollama servers with tool grammar can fail parsing when message content contains raw <tool_call> (e.g. from previous turn). Sanitize so we send placeholder instead.
            if mtype in ("local", "ollama") and tools:
                sanitized_messages = []
                for m in messages:
                    m_copy = dict(m)
                    if isinstance(m_copy.get("content"), str):
                        m_copy["content"] = _sanitize_message_content_for_local_tools(m_copy["content"])
                    sanitized_messages.append(m_copy)
                data = {"model": model_for_request, "messages": sanitized_messages}
            else:
                data = {"model": model_for_request, "messages": messages}
            qwen_model = self._get_qwen_model_for_llm(llm_name)
            _grammar_ok = isinstance(grammar, str) and len(grammar) > 0
            use_tools_in_prompt_q35 = (
                _grammar_ok and tools and mtype in ("local", "ollama")
                and qwen_model == "qwen35"
                and Util._qwen35_use_grammar()
            )
            use_tools_in_prompt_xlam = (
                _grammar_ok and tools and mtype in ("local", "ollama")
                and qwen_model == "qwen3"
                and Util._qwen3_xlam_style_for_llm(llm_name)
            )
            use_tools_in_prompt = use_tools_in_prompt_q35 or use_tools_in_prompt_xlam
            if use_tools_in_prompt:
                tools_text = (
                    self._format_tools_for_prompt_xlam(tools)
                    if use_tools_in_prompt_xlam
                    else self._format_tools_for_prompt(tools)
                )
                if tools_text:
                    data["messages"] = self._inject_tools_into_messages(data["messages"], tools_text)
                logger.debug(
                    "LLM request: %s: tools injected into prompt, not sending tools array",
                    "Qwen3 xLAM" if use_tools_in_prompt_xlam else "Qwen 3.5 + grammar",
                )
            if grammar and isinstance(grammar, str) and len(grammar) > 0:
                # llama.cpp returns 400 when both grammar and tools array are present. For Qwen 3.5 we use tools-in-prompt so grammar can be sent.
                if use_tools_in_prompt:
                    if mtype in ("local", "ollama"):
                        data["grammar"] = grammar
                        logger.debug("LLM request: grammar attached (len=%s chars) as top-level 'grammar'", len(grammar))
                    else:
                        data.setdefault("extra_body", {})["grammar"] = grammar
                        logger.debug("LLM request: grammar attached (len=%s chars) as extra_body.grammar", len(grammar))
                elif mtype in ("local", "ollama") and tools:
                    logger.debug("LLM request: skipping grammar (local/ollama does not allow grammar with tools)")
                elif mtype in ("local", "ollama"):
                    data["grammar"] = grammar
                    logger.debug("LLM request: grammar attached (len=%s chars) as top-level 'grammar'", len(grammar))
                else:
                    data.setdefault("extra_body", {})["grammar"] = grammar
                    logger.debug("LLM request: grammar attached (len=%s chars) as extra_body.grammar", len(grammar))
            if tools and not use_tools_in_prompt:
                data["tools"] = tools
                data["tool_choice"] = tool_choice
            data_params, extra_body_params = self._get_completion_params(max_tokens_override=max_tokens_override, llm_name=llm_name)
            data.update(data_params)
            # Cloud providers (e.g. DeepSeek) often enforce max_tokens in [1, 8192]; cap to avoid 400 Invalid max_tokens
            if mtype == "litellm":
                _cap = 8192
                try:
                    _meta_c = Util().get_core_metadata()
                    _comp, _ = self._get_completion_and_llama_cpp_for_llm(llm_name)
                    if not isinstance(_comp, dict):
                        _comp = {}
                    if _comp.get("cloud_max_tokens_cap") is not None:
                        _cap = max(1, int(_comp["cloud_max_tokens_cap"]))
                except (TypeError, ValueError, Exception):
                    pass
                try:
                    _mt = data.get("max_tokens")
                    _mt = int(_mt) if _mt is not None else 0
                except (TypeError, ValueError):
                    _mt = 0
                if _mt > _cap:
                    data["max_tokens"] = _cap
                    logger.info(
                        "Capped max_tokens to %s for cloud (config: cloud_max_tokens_cap or default 8192). Long replies may truncate; use local or raise cloud_max_tokens_cap if provider allows.",
                        _cap,
                    )
            if stop_extra and isinstance(stop_extra, list):
                stop_list = data.get("stop")
                if isinstance(stop_list, list):
                    existing = {str(s) for s in stop_list}
                    for s in stop_extra:
                        if s is not None and str(s).strip() and str(s) not in existing:
                            stop_list.append(str(s))
                            existing.add(str(s))
                elif stop_list is None:
                    data["stop"] = [str(s) for s in stop_extra if s is not None and str(s).strip()]
            meta = Util().get_core_metadata()
            comp, llama_cpp = self._get_completion_and_llama_cpp_for_llm(llm_name)
            if meta is None:
                tools_cfg = {}
            else:
                tools_cfg = getattr(meta, "tools_config", None) or {}
                if not isinstance(tools_cfg, dict):
                    tools_cfg = {}
            if tools:
                if qwen_model in ("qwen3", "qwen35"):
                    tool_temp = llama_cpp.get("tool_temperature") or comp.get("tool_temperature") or tools_cfg.get("tool_temperature") or 0.1
                    try:
                        data["temperature"] = float(tool_temp)
                    except (TypeError, ValueError):
                        pass
                    # When reasoning_budget is 0, or when user sets disable_thinking_when_tools: true, send enable_thinking: false. Default is false (do not send) so server keeps thinking on and tool_calls/truncation stay stable; set true only if you see empty content with reasoning_content full.
                    _rb = llama_cpp.get("reasoning_budget")
                    _disable = False
                    if _rb is not None:
                        try:
                            _disable = int(_rb) == 0
                        except (TypeError, ValueError):
                            _disable = str(_rb).strip() == "0"
                    _disable_for_tools = llama_cpp.get("disable_thinking_when_tools")
                    if _disable_for_tools is None:
                        _disable_for_tools = False  # default: preserve server default (thinking on) to avoid truncation / no tool_calls; set true in config only if you need to fix empty content
                    if (_disable or (tools and _disable_for_tools)) and mtype in ("local", "ollama"):
                        eb = data.setdefault("extra_body", {})
                        eb["chat_template_kwargs"] = {"enable_thinking": False}
                        eb["enable_thinking"] = False
                        if tools and not _disable:
                            logger.debug("LLM request: enable_thinking=false for tool turn so full response goes to content (avoid empty content + reasoning_content only)")
                else:
                    tool_temp = comp.get("tool_temperature") or tools_cfg.get("tool_temperature")
                    if tool_temp is not None:
                        try:
                            data["temperature"] = float(tool_temp)
                        except (TypeError, ValueError):
                            pass
                    disable_thinking = comp.get("disable_thinking_when_tools") or tools_cfg.get("disable_thinking_when_tools")
                    if disable_thinking and mtype in ("local", "ollama"):
                        eb = data.setdefault("extra_body", {})
                        eb["chat_template_kwargs"] = {"enable_thinking": False}
                        eb["enable_thinking"] = False
                if qwen_model == "qwen35":
                    data["presence_penalty"] = 1.5
                    # stop: from config only (completion.stop or llama_cpp.stop in llm.yml). See comments there for Qwen/Qwen35.
            if mtype == "local":
                _cp = llama_cpp.get("cache_prompt")
                if _cp is None:
                    _cp = True
                if _cp:
                    data["cache_prompt"] = True
            extra_body_params = self._filter_extra_body_for_model(extra_body_params, model_for_request)
            if extra_body_params:
                data.setdefault("extra_body", {}).update(extra_body_params)
            data_json = json.dumps(data, ensure_ascii=False) if self.is_utf8_compatible(data) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            chat_completion_api_url = "http://" + model_host + ":" + str(model_port) + "/v1/chat/completions"
            logger.debug("LLM request: mtype={} url={} model={}", mtype, chat_completion_api_url, model_for_request)
            meta = Util().get_core_metadata()
            _raw = getattr(meta, 'llm_completion_timeout_seconds', 300) if meta is not None else 300
            try:
                _raw = 300 if _raw is None else int(_raw)
            except (TypeError, ValueError):
                _raw = 300
            timeout_sec = None if _raw == 0 else max(60, _raw)  # 0 = no timeout (long tasks allowed; use shortcuts for simple replies)
            timeout = aiohttp.ClientTimeout(total=timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(chat_completion_api_url, headers=headers, data=data_json) as resp:
                    resp_text = await resp.text()
                    if resp.status != 200:
                        logger.warning(
                            "Local LLM returned HTTP {} ({}:{}). Response: {}",
                            resp.status, model_host, model_port, (resp_text or "")[:500],
                        )
                        try:
                            setattr(self, "_last_llm_error", "The model server at {}:{} returned HTTP {}. Check that the server is running and the model is loaded.".format(model_host, model_port, resp.status))
                        except Exception:
                            setattr(self, "_last_llm_error", "The model server returned an error. Check Core logs.")
                        return None
                    try:
                        resp_json = json.loads(resp_text) if resp_text else {}
                    except Exception as parse_err:
                        logger.warning(
                            "Local LLM response is not JSON ({}:{}): {}",
                            model_host, model_port, (resp_text or "")[:300],
                        )
                        setattr(self, "_last_llm_error", "The model server returned invalid JSON. Check Core logs.")
                        return None
                    if isinstance(resp_json, dict) and "choices" in resp_json and len(resp_json["choices"]) > 0:
                        choice0 = resp_json["choices"][0]
                        msg = choice0.get("message") if isinstance(choice0, dict) else None
                        if not isinstance(msg, dict):
                            msg = {}
                        # Content vs reasoning_content: if content has text, use it directly. If content is empty but reasoning_content has text, use reasoning_content and filter out <think>...</think> so only the text after them is shown.
                        _raw_content = msg.get("content")
                        if isinstance(_raw_content, str) and _raw_content.strip():
                            content_val = _raw_content.strip()
                        else:
                            content_val = None
                        # When content is empty, use reasoning_content when: (1) not a tool turn, or (2) tool turn but no tool_calls (server put full reply in reasoning_content). On tool turns with tool_calls we leave content empty and llm_loop parses <tool_call> from reasoning_content.
                        if not (content_val and isinstance(content_val, str)) and isinstance(msg, dict):
                            tool_calls_raw = msg.get("tool_calls")
                            _request_had_tools = bool(tools)
                            has_tool_calls = isinstance(tool_calls_raw, list) and len(tool_calls_raw) > 0
                            # Use reasoning_content as content when: no tool turn, or tool turn with no tool_calls (so the reply is just text in reasoning_content, avoid unnecessary cloud fallback).
                            _use_rc_as_content = not _request_had_tools or (_request_had_tools and not has_tool_calls)
                            if _use_rc_as_content:
                                try:
                                    _meta = Util().get_core_metadata()
                                    _comp = getattr(_meta, "completion", None) or {}
                                    _tools_cfg = getattr(_meta, "tools_config", None) or {}
                                    _always_fallback = _comp.get("qwen_always_use_fallback_for_empty") or _tools_cfg.get("qwen_always_use_fallback_for_empty")
                                    # When thinking is on (reasoning_budget != 0), the server often puts the full reply in reasoning_content and leaves content empty. Default to always using it so the user is not left with empty replies. Set qwen_always_use_fallback_for_empty: false to restore filtering.
                                    _lcpp = getattr(_meta, "llama_cpp", None) if _meta else None
                                    if _always_fallback is None and isinstance(_lcpp, dict):
                                        _rb = _lcpp.get("reasoning_budget")
                                        try:
                                            if _rb is not None and int(_rb) != 0:
                                                _always_fallback = True
                                        except (TypeError, ValueError):
                                            pass
                                    if _always_fallback is None:
                                        _always_fallback = False
                                except Exception:
                                    _always_fallback = False
                                for key in ("reasoning_content", "reasoning", "reason", "output", "text"):
                                    alt = msg.get(key)
                                    try:
                                        alt_str = str(alt).strip() if alt is not None else ""
                                    except Exception:
                                        continue
                                    if not alt_str:
                                        continue
                                    content_val = alt_str
                                    # Do not surface reasoning as the reply when the model also returned tool_calls (plan vs actual call).
                                    if has_tool_calls:
                                        content_val = None
                                        logger.debug("Skipping reasoning_content as reply (message has tool_calls) ({}:{})", model_host, model_port)
                                        break
                                    # Do not surface internal reasoning as the user-visible reply.
                                    if not _always_fallback:
                                        _len_alt = len(content_val)
                                        _short = _len_alt <= 180
                                        _strong_tool_phrases = (
                                            "需要调用", "folder_list", "我将提取", "必须使用", "根据指令需要调用",
                                            "document_read", "run_skill", "should call", "need to call", "must use", "will call",
                                            "tool_call", "tool_name", "arguments",
                                        )
                                        _looks_like_tool_reasoning = _short and any(
                                            phrase in content_val for phrase in _strong_tool_phrases
                                        )
                                        if _looks_like_tool_reasoning:
                                            content_val = None
                                            logger.debug("Skipping reasoning_content as reply (short and looks like tool-calling reasoning) ({}:{})", model_host, model_port)
                                            break
                                        # Do not surface workflow/planning text (e.g. "用户要求我... 流程: document_read → ... save_result_page") when the model put a plan in reasoning_content but no actual <tool_call> in content.
                                        if "<tool_call>" not in content_val:
                                            _workflow_markers = ("流程", "→", "then call", "用户要求我", "generate full", "full slide deck")
                                            _tool_name_markers = ("document_read", "save_result_page", "run_skill", "folder_list", "file_read")
                                            if any(p in content_val for p in _workflow_markers) and any(p in content_val for p in _tool_name_markers):
                                                content_val = None
                                                logger.debug("Skipping reasoning_content as reply (looks like workflow/planning, not actual tool call or reply) ({}:{})", model_host, model_port)
                                                break
                                    if content_val and ("<think>" in content_val or "</think>" in content_val):
                                        content_val = strip_reasoning_from_assistant_text(content_val)
                                    if content_val:
                                        logger.debug("Using {} for empty content ({}:{})", key, model_host, model_port)
                                    break
                        # When content is still empty, log raw server response at DEBUG so you can see why (e.g. wrong template, no tool_calls schema).
                        if not (content_val and isinstance(content_val, str)):
                            finish = choice0.get("finish_reason", "")
                            _rc_raw = msg.get("reasoning_content") if isinstance(msg, dict) else None
                            _rc_preview = ""
                            if _rc_raw is not None:
                                _rc_preview = (str(_rc_raw)[:200] + "..." if len(str(_rc_raw)) > 200 else str(_rc_raw)) if _rc_raw else "(empty)"
                            else:
                                _rc_preview = "(key missing)"
                            logger.debug(
                                "Local LLM returned empty content ({}:{}). finish_reason={} message_keys={} reasoning_content={} usage={}",
                                model_host, model_port,
                                finish,
                                list(msg.keys()) if isinstance(msg, dict) else "?",
                                _rc_preview,
                                resp_json.get("usage", ""),
                            )
                        # Always log what the LLM responded (summary at INFO, full at DEBUG); never crash on malformed response
                        try:
                            content_len = len(content_val) if isinstance(content_val, (str, bytes)) else (len(content_val) if content_val is not None and hasattr(content_val, "__len__") else 0)
                        except Exception:
                            content_len = 0
                        tool_calls_raw = msg.get("tool_calls")
                        tool_calls_list = tool_calls_raw if isinstance(tool_calls_raw, list) else []
                        num_tool_calls = len(tool_calls_list)
                        logger.info(
                            "LLM responded ({}:{}): role={} content_length={} tool_calls={}",
                            model_host, model_port,
                            msg.get("role", "assistant"),
                            content_len,
                            num_tool_calls,
                        )
                        try:
                            content_preview = (content_val if isinstance(content_val, str) else str(content_val))[:2000] if content_val is not None else "(empty)"
                        except Exception:
                            content_preview = "(unable to preview)"
                        logger.debug("LLM response content: {}", content_preview)
                        if tool_calls_list:
                            try:
                                tc_previews = []
                                for tc in tool_calls_list:
                                    if not isinstance(tc, dict):
                                        continue
                                    fn = tc.get("function") or {}
                                    name = fn.get("name") if isinstance(fn, dict) else None
                                    args_str = (fn.get("arguments") or "") if isinstance(fn, dict) else ""
                                    args_preview = (args_str[:200] if isinstance(args_str, str) else str(args_str)[:200])
                                    tc_previews.append((name, args_preview))
                                if tc_previews:
                                    logger.debug("LLM response tool_calls: {}", tc_previews)
                            except Exception:
                                logger.debug("LLM response tool_calls: (unable to parse)")
                        # Return message in OpenAI shape: role, content, tool_calls (optional). Attach finish_reason for truncation handling.
                        finish_reason = choice0.get("finish_reason") if isinstance(choice0, dict) else None
                        if finish_reason == "length":
                            logger.warning(
                                "LLM response was truncated (finish_reason=length). max_tokens limit reached; long content or tool_call arguments may be cut off. Consider putting long documents in message content (e.g. ```html or ```markdown block) so the system can save them."
                            )
                        out = {"role": msg.get("role", "assistant"), "content": content_val}
                        # When request had tools and content is empty, pass reasoning_content so caller can parse <tool_call> from it (but must not surface as user reply).
                        _rc = msg.get("reasoning_content") if isinstance(msg, dict) else None
                        if tools and not (content_val and isinstance(content_val, str)):
                            _rc_str = None
                            if isinstance(_rc, str) and _rc.strip():
                                _rc_str = _rc
                            elif _rc is not None:
                                try:
                                    _rc_str = str(_rc).strip()
                                except Exception:
                                    _rc_str = ""
                                if not _rc_str or "<tool_call>" not in _rc_str:
                                    _rc_str = None
                            if _rc_str:
                                out["reasoning_content"] = _rc_str
                        if finish_reason is not None:
                            out["_finish_reason"] = finish_reason
                        if "tool_calls" in msg and msg["tool_calls"]:
                            # Sanitize so each function.arguments is valid JSON (avoids HTTP 500 when this message is sent back to the server)
                            out["tool_calls"] = _sanitize_tool_calls(msg["tool_calls"])
                        setattr(self, "_last_llm_error", None)
                        return out
                    err_msg = (resp_json.get("error") or resp_json.get("message") or "").strip() if isinstance(resp_json, dict) else ""
                    logger.warning(
                        "Local LLM response has no choices ({}:{}). {}",
                        model_host, model_port, err_msg or "Check that the server is the correct model and loaded.",
                    )
                    try:
                        setattr(self, "_last_llm_error", "The model returned no valid response. Check that the correct model is loaded on {}:{}.".format(model_host, model_port))
                    except Exception:
                        setattr(self, "_last_llm_error", "The model returned no valid response. Check Core logs.")
                    return None
        except asyncio.TimeoutError:
            logger.warning(
                "LLM chat completion timed out after {}s ({}:{})",
                timeout_sec if timeout_sec is not None else "(no limit)",
                model_host,
                model_port,
            )
            try:
                setattr(
                    self,
                    "_last_llm_error",
                    "Request timed out ({}s). Try again or increase llm_completion_timeout_seconds in config (0 = no timeout).".format(
                        timeout_sec if timeout_sec is not None else "no limit"
                    ),
                )
            except Exception:
                setattr(self, "_last_llm_error", "Request timed out. Try again or increase llm_completion_timeout_seconds in config (0 = no timeout).")
            return None
        except asyncio.CancelledError:
            logger.info("LLM chat completion was cancelled (e.g. client disconnected)")
            setattr(self, "_last_llm_error", None)
            return None
        except Exception as e:
            err_str = str(e).lower()
            _is_conn_err = (
                "connection refused" in err_str
                or "connection reset" in err_str
                or "cannot connect" in err_str
                or "connectorerror" in err_str
                or "refused" in err_str
                or "network name is no longer available" in err_str
                or "winerror 64" in err_str
                or "no longer available" in err_str
                or isinstance(e, (ConnectionResetError, ConnectionAbortedError))
                or (isinstance(e, OSError) and getattr(e, "winerror", None) == 64)
            )
            if not _is_conn_err and hasattr(e, "__cause__") and e.__cause__ is not None:
                _is_conn_err = isinstance(e.__cause__, (ConnectionResetError, ConnectionAbortedError))
            if _is_conn_err:
                # Check if Core's main LLM process has exited (crashed) so we can log it and its stderr.
                _exited = None
                try:
                    from llm.llmService import LLMServiceManager
                    _mgr = LLMServiceManager()
                    _exited = _mgr.get_exited_process_info(model_host, model_port)
                except Exception:
                    pass
                if _exited:
                    logger.error(
                        "Main LLM process has exited ({}:{}). PID={} exit_code={}. "
                        "Restart Core to restart the model server. Process stderr (last 500 chars): {}",
                        model_host, model_port,
                        _exited.get("pid"), _exited.get("returncode"),
                        (_exited.get("stderr") or "(none)")[-500:],
                    )
                else:
                    # WinError 64 / "network name is no longer available" = connection was dropped (server not running, crashed, or restarted). Not a timeout — timeouts log "timed out after Xs".
                    logger.warning(
                        "Local LLM unreachable at {}:{} — model server may have stopped or the connection dropped (e.g. WinError 64). "
                        "Core can be running while the server on this port is not. Start the model server (or restart Core so it starts the main LLM), then try again. "
                        "Timeouts are separate (you would see 'timed out after Xs'). Error: {}",
                        model_host, model_port, e,
                    )
                try:
                    setattr(self, "_last_llm_error", "The model server at {}:{} was unreachable (connection dropped or server not running). Start the LLM server or restart Core.".format(model_host, model_port))
                except Exception:
                    setattr(self, "_last_llm_error", "The model server was unreachable. Start the LLM server or restart Core.")
            else:
                logger.exception(e)
                setattr(self, "_last_llm_error", "The model call failed. Check Core logs for details.")
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

    def update_yaml_preserving_comments(self, file_path: str, updates: dict) -> bool:
        """Update only the given keys in a YAML file; preserve comments and key order. Never corrupts the file: writes to .tmp then atomic replace. Returns True if ruamel was used, False if fallback. Skips write if existing file could not be loaded (parse error)."""
        def _atomic_write(path: str, dump_fn) -> bool:
            tmp = path + ".tmp"
            try:
                with open(tmp, 'w', encoding='utf-8') as f:
                    dump_fn(f)
                os.replace(tmp, path)
                return True
            except Exception as e:
                import logging
                logging.warning("update_yaml_preserving_comments: atomic write failed (%s unchanged): %s", path, e)
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass
                return False
        try:
            from ruamel.yaml import YAML
            yaml_rt = YAML()
            yaml_rt.preserve_quotes = True
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml_rt.load(f)
            if data is None:
                data = {}
            for k, v in updates.items():
                data[k] = v
            if _atomic_write(file_path, lambda f: yaml_rt.dump(data, f)):
                return True
        except Exception:
            pass
        existing = self.load_yml_config(file_path) or {}
        if not existing and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            import logging
            logging.warning(
                "update_yaml_preserving_comments: could not load %s; skipping write to avoid removing keys.",
                file_path,
            )
            return False
        for k, v in updates.items():
            existing[k] = v
        _atomic_write(file_path, lambda f: yaml.safe_dump(existing, f, default_flow_style=False, sort_keys=False))
        return False


    def get_users(self):
        """
        Loads the users from the configuration file.
        Validates that different users have distinct email/im/phone (no overlap).
        Never raises: on any error returns [] or previously loaded list so Core never crashes.

        Returns:
            Users: The users list, or [] if loading failed.
        """
        if self.users is None:
            try:
                from base import user_store
                self.users = user_store.get_all(self.config_path, self.data_path)
                if not isinstance(self.users, list):
                    self.users = []
                else:
                    User.validate_no_overlapping_channel_ids(self.users)
            except Exception:
                self.users = []
        return self.users or []
    
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
        if text is None:
            return None
        text = text.replace("\n", " ")
        logger.debug(f"LlamaCppEmbedding.embed: text: {text}")

        # Resolve host/port (and optional model + api_key) from configured embedding model (local or cloud)
        resolved = self.embedding_llm()
        if resolved is None or not isinstance(resolved, (list, tuple)) or len(resolved) < 5:
            try:
                host = getattr(self.core_metadata, 'embedding_host', None) or '127.0.0.1'
                port = getattr(self.core_metadata, 'embedding_port', None) or 5066
            except Exception:
                host, port = '127.0.0.1', 5066
            if host is None or port is None:
                return None
            model_for_body = None
            api_key = None
            mtype = "local"
        else:
            path_or_name, _, mtype, host, port = resolved[0], resolved[1], resolved[2] if len(resolved) > 2 else "local", resolved[3], resolved[4]
            if host is None or port is None:
                return None
            model_for_body = path_or_name if mtype == "litellm" else None
            api_key = None
            if mtype == "litellm":
                entry, _ = self._get_model_entry(self.core_metadata.embedding_llm)
                if entry:
                    api_key = (entry.get("api_key") or "").strip() if isinstance(entry.get("api_key"), str) else None
                    if not api_key and entry.get("api_key_name"):
                        api_key = (os.environ.get(entry["api_key_name"].strip()) or "").strip() or None

        headers = {"accept": "application/json", "Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        sem = self._get_llm_semaphore(mtype)
        try:
            async with sem:
                async with aiohttp.ClientSession() as session:
                    if mtype == "ollama":
                        embedding_url = "http://" + str(host) + ":" + str(port) + "/api/embed"
                        body = {"model": path_or_name or "", "input": text if isinstance(text, str) else (text if isinstance(text, list) else [str(text)])}
                        if isinstance(body["input"], str):
                            body["input"] = [body["input"]]
                        async with session.post(embedding_url, headers=headers, data=json.dumps(body)) as response:
                            response_json = await response.json() if getattr(response, "content_type", None) and "json" in str(getattr(response, "content_type", "")) else {}
                            if not isinstance(response_json, dict) or "embeddings" not in response_json:
                                return None
                            emb = response_json["embeddings"]
                            if not isinstance(emb, list) or not emb:
                                return None
                            return emb[0] if isinstance(emb[0], list) else None
                    embedding_url = "http://" + host + ":" + str(port) + "/v1/embeddings"
                    logger.debug(f"Embedding URL: {embedding_url}")
                    body = {"input": text}
                    if model_for_body:
                        body["model"] = model_for_body
                    async with session.post(
                        embedding_url,
                        headers=headers,
                        data=json.dumps(body),
                    ) as response:
                        response_json = await response.json()
                        if not isinstance(response_json, dict) or "data" not in response_json or not response_json["data"]:
                            return None
                        first = response_json["data"][0]
                        if not isinstance(first, dict) or "embedding" not in first:
                            return None
                        return first["embedding"]
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
        user = User(name="HomeClaw", email=[], phone=[], im=[])
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
        """Save users to TinyDB (database/users.json). Never raises. See docs_design/UserDataTinyDB.md."""
        try:
            from base import user_store
            user_store.save_all(users or [], self.config_path, self.data_path)
        except Exception:
            pass

    def update_user_password(self, user_id: str, new_password: str) -> bool:
        """
        Set the password for the given user and persist to TinyDB.
        Returns True if user was found and saved. Never raises.
        """
        try:
            uid = (user_id or "").strip()
            if not uid:
                return False
            users = self.get_users() or []
            for u in users:
                u_id = (getattr(u, "id", None) or getattr(u, "name", None) or "").strip()
                if u_id != uid:
                    continue
                u.password = (new_password or "").strip() or None
                self.save_users(users)
                return True
            return False
        except Exception as e:
            logger.warning("update_user_password failed: {}", e)
            return False

    def add_friend_bidirectional(self, user_id_a: str, user_id_b: str) -> bool:
        """
        Add user_id_b as a user-type friend to user_id_a and vice versa; persist to user.yml.
        Returns True if both were updated and saved. Never raises.
        Both users must exist; if either already has the other as a user-type friend, returns False (no-op).
        """
        try:
            users = self.get_users() or []
            if len(users) < 2:
                return False
            user_a = None
            user_b = None
            for u in users:
                uid = (getattr(u, "id", None) or getattr(u, "name", None) or "").strip()
                if uid == (user_id_a or "").strip():
                    user_a = u
                if uid == (user_id_b or "").strip():
                    user_b = u
            if not user_a or not user_b:
                return False
            friends_a = list(getattr(user_a, "friends", None) or [])
            friends_b = list(getattr(user_b, "friends", None) or [])
            for f in friends_a:
                if getattr(f, "type", None) and str(getattr(f, "type", "")).strip().lower() == "user":
                    if (getattr(f, "user_id", None) or "").strip() == (user_id_b or "").strip():
                        return False
            for f in friends_b:
                if getattr(f, "type", None) and str(getattr(f, "type", "")).strip().lower() == "user":
                    if (getattr(f, "user_id", None) or "").strip() == (user_id_a or "").strip():
                        return False
            name_b = (getattr(user_b, "name", None) or user_id_b or "").strip()
            name_a = (getattr(user_a, "name", None) or user_id_a or "").strip()
            friends_a.append(Friend(name=name_b, relation=None, who=None, identity=None, preset=None, type="user", user_id=(user_id_b or "").strip()))
            friends_b.append(Friend(name=name_a, relation=None, who=None, identity=None, preset=None, type="user", user_id=(user_id_a or "").strip()))
            user_a.friends = friends_a
            user_b.friends = friends_b
            self.save_users(users)
            return True
        except Exception as e:
            logger.warning("add_friend_bidirectional failed: {}", e)
            return False

    def add_ai_friend(
        self,
        user_id: str,
        name: str,
        relation: Optional[str] = None,
        who: Optional[Dict[str, Any]] = None,
        identity_filename: Optional[str] = "identity.md",
        preset: Optional[str] = None,
    ) -> bool:
        """
        Add an AI-type friend to the given user and persist to user.yml.
        name must be unique among this user's friends (no duplicate names). Returns True on success.
        """
        try:
            uid = (user_id or "").strip()
            fname = (name or "").strip()
            if not uid or not fname:
                return False
            users = self.get_users() or []
            user = None
            for u in users:
                u_id = (getattr(u, "id", None) or getattr(u, "name", None) or "").strip()
                if u_id == uid:
                    user = u
                    break
            if not user:
                return False
            friends = list(getattr(user, "friends", None) or [])
            for f in friends:
                n = (getattr(f, "name", None) or "").strip()
                if n.lower() == fname.lower():
                    return False  # duplicate name
            ident = (identity_filename or "").strip() or "identity.md"
            friends.append(
                Friend(
                    name=fname,
                    relation=relation,
                    who=who if isinstance(who, dict) else None,
                    identity=ident,
                    preset=preset,
                    type="ai",
                    user_id=None,
                )
            )
            user.friends = friends
            self.save_users(users)
            return True
        except Exception as e:
            logger.warning("add_ai_friend failed: {}", e)
            return False

    def update_ai_friend(
        self,
        user_id: str,
        friend_id: str,
        name: Optional[str] = None,
        relation: Optional[str] = None,
        who: Optional[Dict[str, Any]] = None,
        identity_filename: Optional[str] = None,
        preset: Optional[str] = None,
    ) -> bool:
        """Update an existing AI friend by name (friend_id). Returns True if found and updated."""
        try:
            uid = (user_id or "").strip()
            fid = (friend_id or "").strip()
            if not uid or not fid:
                return False
            users = self.get_users() or []
            for u in users:
                u_id = (getattr(u, "id", None) or getattr(u, "name", None) or "").strip()
                if u_id != uid:
                    continue
                friends = list(getattr(u, "friends", None) or [])
                for i, f in enumerate(friends):
                    n = (getattr(f, "name", None) or "").strip()
                    if n.lower() != fid.lower():
                        continue
                    ftype = (getattr(f, "type", None) or "").strip().lower()
                    if ftype != "ai" and ftype not in ("remote_ai",):
                        continue
                    new_name = (name or "").strip() or n
                    new_relation = relation if relation is not None else getattr(f, "relation", None)
                    new_who = who if isinstance(who, dict) else getattr(f, "who", None)
                    new_ident = (identity_filename or getattr(f, "identity", None) or "identity.md").strip() or "identity.md"
                    new_preset = preset if preset is not None else getattr(f, "preset", None)
                    friends[i] = Friend(
                        name=new_name,
                        relation=new_relation,
                        who=new_who,
                        identity=new_ident,
                        preset=new_preset,
                        type=ftype,
                        user_id=None,
                        peer_instance_id=getattr(f, "peer_instance_id", None),
                    )
                    u.friends = friends
                    self.save_users(users)
                    return True
            return False
        except Exception as e:
            logger.warning("update_ai_friend failed: {}", e)
            return False

    def remove_ai_friend(self, user_id: str, friend_id: str) -> bool:
        """Remove an AI friend by name (friend_id). Returns True if found and removed. Cannot remove HomeClaw."""
        try:
            uid = (user_id or "").strip()
            fid = (friend_id or "").strip()
            if not uid or not fid:
                return False
            if fid.lower() == "homeclaw":
                return False
            users = self.get_users() or []
            for u in users:
                u_id = (getattr(u, "id", None) or getattr(u, "name", None) or "").strip()
                if u_id != uid:
                    continue
                friends = list(getattr(u, "friends", None) or [])
                for i, f in enumerate(friends):
                    n = (getattr(f, "name", None) or "").strip()
                    if n.lower() != fid.lower():
                        continue
                    ftype = (getattr(f, "type", None) or "").strip().lower()
                    if ftype != "ai" and ftype not in ("remote_ai",):
                        continue
                    friends.pop(i)
                    u.friends = friends
                    self.save_users(users)
                    return True
            return False
        except Exception as e:
            logger.warning("remove_ai_friend failed: {}", e)
            return False

    def remove_user_friend(self, user_id: str, other_user_id: str) -> bool:
        """Remove a user friend (type=user) by the other user's id. Returns True if found and removed."""
        try:
            uid = (user_id or "").strip()
            oid = (other_user_id or "").strip()
            if not uid or not oid:
                return False
            users = self.get_users() or []
            for u in users:
                u_id = (getattr(u, "id", None) or getattr(u, "name", None) or "").strip()
                if u_id != uid:
                    continue
                friends = list(getattr(u, "friends", None) or [])
                for i, f in enumerate(friends):
                    ftype = (getattr(f, "type", None) or "").strip().lower()
                    if ftype != "user":
                        continue
                    f_uid = (getattr(f, "user_id", None) or "").strip()
                    if f_uid != oid:
                        continue
                    friends.pop(i)
                    u.friends = friends
                    self.save_users(users)
                    return True
            return False
        except Exception as e:
            logger.warning("remove_user_friend failed: {}", e)
            return False

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
        meta = getattr(self, "core_metadata", None)
        if not meta:
            return None
        cap = str(capability).strip().lower()
        main_llm_name = (getattr(meta, "main_llm", None) or "").strip()
        if main_llm_name:
            entry, _ = self._get_model_entry(main_llm_name)
            if entry and self.model_entry_available(entry):
                caps = self._normalize_capability_list(entry.get("capabilities"))
                if any((str(c).strip().lower() == cap for c in caps if c is not None)):
                    return main_llm_name
        for m in (meta.local_models or []):
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            mid_s = str(mid).strip() if mid is not None else ""
            if not mid_s or not self.model_entry_available(m):
                continue
            caps = self._normalize_capability_list(m.get("capabilities"))
            if any((str(c).strip().lower() == cap for c in caps if c is not None)):
                return f"local_models/{mid_s}"
        for m in (meta.cloud_models or []):
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            mid_s = str(mid).strip() if mid is not None else ""
            if not mid_s or not self.model_entry_available(m):
                continue
            caps = self._normalize_capability_list(m.get("capabilities"))
            if any((str(c).strip().lower() == cap for c in caps if c is not None)):
                return f"cloud_models/{mid_s}"
        return None

    def format_llm_catalog_for_tool_prompt(self, max_chars: int = 14000) -> str:
        """
        Build a compact text block of local_models + cloud_models (ref, capabilities, available, alias, description)
        for appending to models_list / sessions_spawn tool descriptions in the LLM prompt.
        """
        try:
            try:
                max_chars = max(400, int(max_chars))
            except (TypeError, ValueError):
                max_chars = 14000
            meta = getattr(self, "core_metadata", None)
            if not meta:
                return ""
            lines: List[str] = [
                "## Current LLM catalog (for models_list and sessions_spawn)",
                "Each entry: ref | capabilities | available | alias | description",
                "Use description + capabilities to choose llm_name; use capability= only when tags match (ignores available:false).",
                "---",
            ]
            main_llm = (getattr(meta, "main_llm", None) or "").strip()
            if main_llm:
                lines.append(f"Default chat main_llm: {main_llm}")
                lines.append("---")
            count = 0
            for m in (meta.local_models or []):
                if not isinstance(m, dict):
                    continue
                mid = m.get("id")
                mid_s = str(mid).strip() if mid is not None else ""
                if not mid_s:
                    continue
                count += 1
                ref = f"local_models/{mid_s}"
                caps = self._normalize_capability_list(m.get("capabilities"))
                cap_s = ",".join(str(c) for c in caps if c is not None) if caps else "-"
                avail = "true" if self.model_entry_available(m) else "false"
                alias = str(m.get("alias") or mid_s).strip() or mid_s
                desc_raw = m.get("description")
                desc = str(desc_raw).strip() if desc_raw is not None else ""
                if desc:
                    desc = " ".join(desc.split())
                line = f"- {ref} | [{cap_s}] | {avail} | {alias}"
                if desc:
                    line += f" | {desc}"
                lines.append(line)
            for m in (meta.cloud_models or []):
                if not isinstance(m, dict):
                    continue
                mid = m.get("id")
                mid_s = str(mid).strip() if mid is not None else ""
                if not mid_s:
                    continue
                count += 1
                ref = f"cloud_models/{mid_s}"
                caps = self._normalize_capability_list(m.get("capabilities"))
                cap_s = ",".join(str(c) for c in caps if c is not None) if caps else "-"
                avail = "true" if self.model_entry_available(m) else "false"
                alias = str(m.get("alias") or mid_s).strip() or mid_s
                desc_raw = m.get("description")
                desc = str(desc_raw).strip() if desc_raw is not None else ""
                if desc:
                    desc = " ".join(desc.split())
                line = f"- {ref} | [{cap_s}] | {avail} | {alias}"
                if desc:
                    line += f" | {desc}"
                lines.append(line)
            if count == 0:
                return ""
            body = "\n".join(lines)
            if len(body) > max_chars:
                cut = max(0, max_chars - 24)
                body = body[:cut].rstrip() + "\n…(catalog truncated)"
            return body
        except Exception as e:
            logger.debug("format_llm_catalog_for_tool_prompt failed: {}", e)
            return ""

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
        Monitor config and user data: user.yml (legacy) and database/users.json (TinyDB).
        On change, reload users so Core picks up edits.
        """
        if self.config_observer is None:
            class Handler(watchdog.events.PatternMatchingEventHandler):
                def __init__(self, util: Util):
                    super().__init__(patterns=['user.yml', 'users.json'])
                    self.util: Util = util

                def on_modified(self, event):
                    try:
                        if event.src_path.endswith('user.yml') or event.src_path.endswith('users.json'):
                            self.util.users = None
                            self.util.get_users()
                    except Exception:
                        pass

            self.config_observer = watchdog.observers.Observer()
            self.config_observer.schedule(Handler(self), self.config_path(), recursive=False)
            try:
                data_dir = self.data_path()
                if data_dir and os.path.isdir(data_dir):
                    self.config_observer.schedule(Handler(self), data_dir, recursive=False)
            except Exception:
                pass
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

