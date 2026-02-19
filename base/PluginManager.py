import importlib
import asyncio
import json
from inspect import getmembers, isclass, isfunction, signature
from pathlib import Path
import sys
import threading
import time
import os
from threading import Thread
from typing import Any, Dict, List, Optional
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from base.BasePlugin import BasePlugin
from base.base import PluginRequest, PluginResult, PromptRequest
from base.util import Util, redact_params_for_log
from core.coreInterface import CoreInterface

disable_plugins = False

# External plugin descriptor (from plugin.yaml): type in ("http", "subprocess", "mcp")
EXTERNAL_TYPES = ("http", "subprocess", "mcp")


def _load_plugin_manifest(plugin_folder: str) -> Optional[Dict[str, Any]]:
    """Load plugin.yaml or plugin.json from plugin folder. Returns dict with id, name, description, type, config or None."""
    folder = Path(plugin_folder)
    for name in ("plugin.yaml", "plugin.yml", "plugin.json"):
        path = folder / name
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            if path.suffix in (".json",):
                import json as _json
                data = _json.loads(raw)
            else:
                import yaml
                data = yaml.safe_load(raw) or {}
            if isinstance(data, dict) and data.get("id") and data.get("description"):
                data.setdefault("name", data.get("id", ""))
                data.setdefault("type", "inline")
                data.setdefault("config", {})
                return data
        except Exception as e:
            logger.warning(f"Failed to load manifest {path}: {e}")
    return None


def _normalize_plugin_id(plugin_id: str) -> str:
    """Normalize for lookup only: lowercase, spaces and hyphens to underscores. Enables both folder-style (homeclaw-browser) and identifier-style (homeclaw_browser) to resolve to the same plugin. The stored descriptor keeps the original id (e.g. from register.js) for display and prompts."""
    return (plugin_id or "").strip().lower().replace(" ", "_").replace("-", "_")


class PluginManager:
    def __init__(self, coreInst: CoreInterface):
        self.coreInst = coreInst
        self.plugins_dir = Util().plugins_path()
        self.loaded_plugins = {}
        self.plugin_instances: list[BasePlugin] = []
        self.external_plugins: List[Dict[str, Any]] = []  # all external: folder + API-registered
        self.api_registered_plugins: List[Dict[str, Any]] = []  # external plugins registered via Core API (persisted)
        self.hot_reload_thread = None
        self.stop_hot_reload = threading.Event()
        self.plugin_descriptions = {}  # description -> plugin
        self.plugin_by_id = {}  # stable id -> plugin (BasePlugin) or descriptor (dict for external)
        self._load_api_registered_from_file()


    def register_plugin(self, plugin: BasePlugin):
        if plugin is None:
            return
        logger.debug(f"Registering plugin: {plugin.description} id={getattr(plugin, 'plugin_id', '')}")
        self.plugin_descriptions[plugin.description] = plugin
        pid = getattr(plugin, 'plugin_id', None) or ''
        if pid:
            self.plugin_by_id[pid] = plugin
            # Also allow lookup by description slug if no id was set
        if not pid and plugin.description:
            from base.BasePlugin import _slug_from_description
            slug = _slug_from_description(plugin.description)
            if slug and slug not in self.plugin_by_id:
                self.plugin_by_id[slug] = plugin


    def num_plugins(self):
        """Total count of inline + external (http/subprocess/mcp) plugins."""
        return len(self.plugin_instances) + len(self.external_plugins)

    def get_plugin_by_id(self, plugin_id: str):
        """Return plugin by stable id. Either a BasePlugin (inline) or a descriptor dict (http/subprocess/mcp)."""
        if not plugin_id:
            return None
        pid = _normalize_plugin_id(plugin_id)
        return self.plugin_by_id.get(pid)

    def _api_plugins_file(self) -> Path:
        """Path to persisted API-registered plugins (JSON)."""
        try:
            config_dir = Path(Util().config_path())
            return config_dir / "external_plugins.json"
        except Exception:
            return Path("config/external_plugins.json")

    def _load_api_registered_from_file(self) -> None:
        """Load API-registered plugins from disk (called from __init__)."""
        path = self._api_plugins_file()
        if not path.is_file():
            return
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                self.api_registered_plugins = data
                for d in self.api_registered_plugins:
                    d["_source"] = "api"
                    d["id"] = d.get("id") or d.get("plugin_id") or ""
            else:
                self.api_registered_plugins = []
        except Exception as e:
            logger.warning("Failed to load external_plugins.json: {}", e)
            self.api_registered_plugins = []

    def _save_api_registered_to_file(self) -> None:
        """Persist API-registered plugins to disk (strip _source for serialization)."""
        path = self._api_plugins_file()
        try:
            to_save = []
            for d in self.api_registered_plugins:
                copy = {k: v for k, v in d.items() if k != "_source"}
                to_save.append(copy)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(to_save, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save external_plugins.json: {}", e)

    def register_external_via_api(self, descriptor: Dict[str, Any]) -> str:
        """
        Register an external plugin via the Core registration API.
        descriptor must include id, name, description, health_check_url, type, config; optional description_long, tools.
        Returns normalized plugin_id. Raises ValueError if invalid or duplicate id from folder-based plugin.
        """
        pid = _normalize_plugin_id(descriptor.get("id") or "")
        if not pid:
            raise ValueError("plugin_id is required")
        if not descriptor.get("name") or not descriptor.get("description"):
            raise ValueError("name and description are required")
        if not descriptor.get("health_check_url"):
            raise ValueError("health_check_url is required")
        t = (descriptor.get("type") or "").lower()
        if t not in EXTERNAL_TYPES:
            raise ValueError(f"type must be one of {EXTERNAL_TYPES}")
        # Avoid overwriting an existing inline or folder-based external with same id
        existing = self.plugin_by_id.get(pid)
        if existing is not None and not isinstance(existing, dict):
            raise ValueError(f"plugin_id {pid} already used by a built-in plugin")
        if isinstance(existing, dict) and existing.get("_source") == "manifest":
            raise ValueError(f"plugin_id {pid} already used by a folder-based plugin")
        descriptor = dict(descriptor)
        descriptor["_source"] = "api"
        # Preserve original id (e.g. homeclaw-browser from folder name / register.js); lookup key is normalized pid
        if not descriptor.get("id"):
            descriptor["id"] = descriptor.get("plugin_id") or pid
        # Replace if already api-registered (same plugin_id = update, not duplicate)
        self.api_registered_plugins = [d for d in self.api_registered_plugins if _normalize_plugin_id(d.get("id")) != pid]
        self.api_registered_plugins.append(descriptor)
        self.plugin_by_id[pid] = descriptor
        self.external_plugins = [d for d in self.external_plugins if _normalize_plugin_id(d.get("id")) != pid]
        self.external_plugins.append(descriptor)
        self._save_api_registered_to_file()
        logger.info("Registered external plugin via API: {}", pid)
        return pid

    def unregister_external_plugin(self, plugin_id: str) -> bool:
        """Unregister an API-registered external plugin. Returns True if removed."""
        pid = _normalize_plugin_id(plugin_id)
        existing = self.plugin_by_id.get(pid)
        if not isinstance(existing, dict) or existing.get("_source") != "api":
            return False
        self.api_registered_plugins = [d for d in self.api_registered_plugins if _normalize_plugin_id(d.get("id")) != pid]
        if pid in self.plugin_by_id:
            del self.plugin_by_id[pid]
        self.external_plugins = [d for d in self.external_plugins if _normalize_plugin_id(d.get("id")) != pid]
        self._save_api_registered_to_file()
        logger.info("Unregistered external plugin: {}", pid)
        return True

    def unregister_all_external_plugins(self) -> list:
        """Unregister all API-registered external plugins. Returns list of plugin_ids that were removed. For testing."""
        ids = [_normalize_plugin_id(d.get("id") or d.get("plugin_id") or "") for d in self.api_registered_plugins]
        removed = []
        for pid in ids:
            if pid and self.unregister_external_plugin(pid):
                removed.append(pid)
        return removed

    async def check_plugin_health(self, descriptor: Dict[str, Any]) -> bool:
        """Call the plugin's health_check_url (GET). Return True if 2xx."""
        url = (descriptor.get("health_check_url") or "").strip()
        if not url:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return 200 <= resp.status_code < 300
        except Exception as e:
            logger.debug("Plugin health check failed for {}: {}", descriptor.get("id"), e)
            return False

    def get_plugin_list_for_prompt(self) -> List[Dict[str, str]]:
        """Return list of { id, description } for all plugins (inline + external) for routing block. No truncation here; Core applies plugins_description_max_chars when building the prompt."""
        out = []
        for p in self.plugin_instances:
            pid = getattr(p, "plugin_id", None) or ""
            desc = (p.get_description() or "").strip()
            if pid:
                out.append({"id": pid, "description": desc})
        for d in self.external_plugins:
            pid = (d.get("id") or "").strip().lower().replace(" ", "_")
            desc = (d.get("description") or "").strip()
            if pid:
                out.append({"id": pid, "description": desc})
        return out

    def get_plugin_registrations_for_sync(self) -> List[Dict[str, Any]]:
        """
        Return list of registration dicts (id, name, description, description_long) for all plugins
        for syncing to the plugins vector store. Same shape for built-in and external.
        """
        out = []
        for p in self.plugin_instances:
            reg = getattr(p, "registration", None) or {}
            pid = _normalize_plugin_id(reg.get("id") or getattr(p, "plugin_id", None) or "")
            if not pid:
                continue
            name = (reg.get("name") or (getattr(p, "config", None) or {}).get("name") or pid).strip()
            desc = (reg.get("description") or p.get_description() or (getattr(p, "config", None) or {}).get("description") or "").strip()
            desc_long = (reg.get("description_long") or (getattr(p, "config", None) or {}).get("description_long") or "").strip() or None
            out.append({"id": pid, "name": name, "description": desc, "description_long": desc_long})
        for d in self.external_plugins:
            pid = _normalize_plugin_id(d.get("id") or "")
            if not pid:
                continue
            name = (d.get("name") or pid).strip()
            desc = (d.get("description") or "").strip()
            desc_long = (d.get("description_long") or "").strip() or None
            out.append({"id": pid, "name": name, "description": desc, "description_long": desc_long})
        return out

    async def run_external_plugin(self, descriptor: Dict[str, Any], request: PromptRequest) -> "PluginResult":
        """Run an external plugin (http or subprocess). Returns PluginResult (text + metadata, e.g. metadata.media). See docs/PluginStandard.md."""
        plugin_type = (descriptor.get("type") or "").lower()
        config = descriptor.get("config") or {}
        timeout = float(config.get("timeout_sec", 420))
        plugin_id = (descriptor.get("id") or "").strip().lower().replace(" ", "_")
        cap_id = (request.request_metadata or {}).get("capability_id")
        cap_params = (request.request_metadata or {}).get("capability_parameters")
        logger.info(
            "External plugin: plugin_id={} capability_id={} capability_parameters={}",
            plugin_id,
            cap_id,
            redact_params_for_log(cap_params) if cap_params is not None else None,
        )
        req = PluginRequest(
            request_id=request.request_id,
            plugin_id=plugin_id,
            user_input=request.text or "",
            user_id=request.user_id or "",
            user_name=request.user_name or "",
            channel_name=request.channel_name or "",
            channel_type=getattr(request.channelType, "value", str(request.channelType)),
            app_id=request.app_id or "",
            metadata=request.request_metadata or {},
            capability_id=cap_id,
            capability_parameters=cap_params,
        )
        if plugin_type == "http":
            base_url = (config.get("base_url") or "").rstrip("/")
            path = (config.get("path") or "/run").lstrip("/")
            url = f"{base_url}/{path}" if path else base_url
            if not base_url:
                return PluginResult(success=False, error=f"Error: plugin {plugin_id} type http has no base_url in config.")
            try:
                import httpx
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=req.model_dump())
                    if resp.status_code != 200:
                        body_preview = (resp.text or "").strip()[:300]
                        msg = f"Error: plugin returned {resp.status_code}: {body_preview}" if body_preview else f"Error: plugin returned {resp.status_code}"
                        if resp.status_code == 503:
                            msg += ". Service Unavailable — often a reverse proxy read timeout: the request (e.g. video recording) took longer than the proxy allows (e.g. 60–120s). Fix: call the plugin directly (base_url http://127.0.0.1:3020) or increase the proxy's read timeout to at least 420s. See plugin README."
                        return PluginResult(success=False, error=msg)
                    data = resp.json()
                    result = PluginResult(**data) if isinstance(data, dict) else PluginResult(success=False, error=str(data))
            except Exception as e:
                logger.debug("Plugin HTTP call failed: {} {}: {}", plugin_id, url, e)
                err_detail = f"{type(e).__name__}: {e!s}" if (e and str(e).strip()) else (type(e).__name__ or "Exception")
                hint = ""
                if "connect" in err_detail.lower() or "refused" in err_detail.lower() or "connection" in err_detail.lower():
                    hint = f" Is the plugin running? For {plugin_id} start it (e.g. cd system_plugins/{plugin_id} && npm start) and ensure base_url {config.get('base_url', '')} is reachable."
                elif "timeout" in err_detail.lower() or "timed out" in err_detail.lower():
                    hint = f" Long-running media (e.g. video) may need a higher timeout_sec (current {int(timeout)}s). Ensure the node (e.g. Nodes page tab) is connected and recording completes."
                return PluginResult(success=False, error=f"Error calling plugin {plugin_id}: {err_detail}.{hint}")
            if not result.success:
                return PluginResult(success=result.success, text=result.text or "", error=result.error, metadata=result.metadata or {})
            return result
        if plugin_type == "subprocess":
            command = config.get("command")
            args = config.get("args") or []
            if not command:
                return PluginResult(success=False, error=f"Error: plugin {plugin_id} type subprocess has no command in config.")
            cmd_list = [str(command)] + [str(a) for a in args]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd_list,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=descriptor.get("_folder") or None,
                )
                req_json = req.model_dump_json()
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=req_json.encode("utf-8")), timeout=timeout
                )
                out_str = stdout.decode("utf-8", errors="replace").strip()
                err_str = stderr.decode("utf-8", errors="replace").strip()
                if err_str:
                    logger.debug(f"Plugin {plugin_id} stderr: {err_str[:500]}")
                if not out_str:
                    return PluginResult(success=False, error=err_str or "(plugin produced no output)")
                try:
                    data = json.loads(out_str)
                    result = PluginResult(**data) if isinstance(data, dict) else PluginResult(success=True, text=out_str)
                except json.JSONDecodeError:
                    result = PluginResult(success=True, text=out_str)
                if not result.success:
                    return PluginResult(success=result.success, text=result.text or "", error=result.error, metadata=result.metadata or {})
                return result
            except asyncio.TimeoutError:
                return PluginResult(success=False, error=f"Error: plugin {plugin_id} timed out after {timeout}s")
            except FileNotFoundError:
                return PluginResult(success=False, error=f"Error: plugin command not found: {command}")
            except Exception as e:
                return PluginResult(success=False, error=f"Error running plugin {plugin_id}: {e!s}")
        if plugin_type == "mcp":
            return PluginResult(success=False, error="Error: MCP plugins not yet implemented. Use type http or subprocess for now.")
        return PluginResult(success=False, error=f"Error: unknown plugin type {plugin_type}")

    def get_capability(self, plugin_or_descriptor: Any, capability_id: str) -> Optional[Dict[str, Any]]:
        """Get capability by id from a plugin (BasePlugin with registration) or external descriptor."""
        if not capability_id:
            return None
        cap_id = (capability_id or "").strip().lower().replace(" ", "_")
        caps = None
        if isinstance(plugin_or_descriptor, dict):
            caps = plugin_or_descriptor.get("capabilities") or []
        else:
            reg = getattr(plugin_or_descriptor, "registration", None) or {}
            caps = reg.get("capabilities") or []
        for c in caps:
            if _normalize_plugin_id(c.get("id") or "") == cap_id:
                return c
        return None

    def get_plugin_by_index(self, index: int):
        """Return plugin by 0-based index in plugin_instances order."""
        if index is None or index < 0:
            return None
        plugins = self.plugin_instances
        if index >= len(plugins):
            return None
        return plugins[index]


    def _register_external(self, descriptor: Dict[str, Any]) -> None:
        """Register an external plugin (http/subprocess/mcp) by manifest descriptor."""
        pid = (descriptor.get("id") or "").strip().lower().replace(" ", "_")
        if not pid:
            return
        self.plugin_by_id[pid] = descriptor
        self.external_plugins.append(descriptor)
        logger.debug(f"Registered external plugin: {pid} type={descriptor.get('type')}")

    def load_plugins(self):
        if disable_plugins:
            return
        # Remove only folder-based external plugins from plugin_by_id (keep API-registered)
        to_remove = [
            pid for pid, p in self.plugin_by_id.items()
            if isinstance(p, dict) and p.get("_source") != "api"
        ]
        for pid in to_remove:
            del self.plugin_by_id[pid]
        self.external_plugins = [d for d in self.external_plugins if d.get("_source") == "api"]
        current_plugins = set()
        external_folders = set()
        # First pass: discover plugin.yaml (standard); register folder-based external (http/subprocess/mcp)
        for folder_name in os.listdir(self.plugins_dir):
            plugin_folder = os.path.join(self.plugins_dir, folder_name)
            if not os.path.isdir(plugin_folder):
                continue
            manifest = _load_plugin_manifest(plugin_folder)
            if manifest and (manifest.get("type") or "inline").lower() in EXTERNAL_TYPES:
                pid = _normalize_plugin_id(manifest.get("id") or folder_name)
                if pid in self.plugin_by_id and self.plugin_by_id[pid].get("_source") == "api":
                    continue  # API-registered takes precedence
                manifest["_folder"] = plugin_folder
                manifest["_source"] = "manifest"
                if not any(_normalize_plugin_id(d.get("id")) == pid for d in self.external_plugins):
                    self._register_external(manifest)
                external_folders.add(folder_name)
        # Merge API-registered into plugin_by_id and external_plugins
        for d in self.api_registered_plugins:
            d["_source"] = "api"
            pid = _normalize_plugin_id(d.get("id"))
            if pid:
                self.plugin_by_id[pid] = d
                if not any(_normalize_plugin_id(x.get("id")) == pid for x in self.external_plugins):
                    self.external_plugins.append(d)
        # Second pass: load Python plugins (inline or legacy)
        for folder_name in os.listdir(self.plugins_dir):
            plugin_folder = os.path.join(self.plugins_dir, folder_name)
            if os.path.isdir(plugin_folder) and folder_name not in external_folders:
                for filename in os.listdir(plugin_folder):
                    if filename.endswith('.py') and filename != '__init__.py':
                        module_name = filename[:-3]
                        module_path = f"plugins.{folder_name}.{module_name}"
                        plugin_mod_time = os.path.getmtime(plugin_folder)
                        current_plugins.add(module_path)
                        if (module_path not in self.loaded_plugins or
                                self.loaded_plugins[module_path] < plugin_mod_time):
                            module = importlib.import_module(module_path)
                            for attr_name, attr in getmembers(module, isclass):
                                # Filter out any intermediate base classes and only initialize final subclasses of BasePlugin
                                if issubclass(attr, BasePlugin) and attr is not BasePlugin:
                                    # Ensure we're dealing with the most derived class and not an intermediate class
                                    #if not any(issubclass(cls, attr) and cls is not attr for cls in BasePlugin.__subclasses__()):
                                        # Check if this plugin instance already exists
                                                                            # Skip loading intermediate base classes
                                    if len(attr.__subclasses__()) > 0:
                                        logger.debug(f"Skipping intermediate base class: {attr.__name__}")
                                        continue

                                    existing_instance = next((instance for instance in self.plugin_instances if isinstance(instance, attr)), None)
                                    if not existing_instance:
                                        logger.debug(f"Loading plugin: {module_path} - {attr_name}")
                                        # Log the [__init__](cci:1://file:///HomeClaw/base/PluginManager.py:15:4-19:52) method signature of the class
                                        init_method = attr.__init__
                                        
                                        if isfunction(init_method):
                                            init_signature = signature(init_method)
                                            logger.debug(f"__init__ signature for {attr_name}: {init_signature}")
                                        #init_signature = signature(attr.__init__)
                                            if 'coreInst' in init_signature.parameters:
                                                plugin_instance = attr(coreInst=self.coreInst)

                                                if hasattr(plugin_instance, 'initialize'):
                                                    logger.debug(f"Calling initialize for plugin: {module_path} - {attr_name}")
                                                    plugin_instance.initialize()
                                                # Load plugin.yaml (unified registration) and attach to instance
                                                manifest = _load_plugin_manifest(plugin_folder)
                                                if manifest and (manifest.get("type") or "inline").lower() == "inline":
                                                    plugin_instance.registration = manifest
                                                    for k in ("id", "name", "description", "description_long"):
                                                        if manifest.get(k) is not None:
                                                            if not hasattr(plugin_instance, "config") or plugin_instance.config is None:
                                                                plugin_instance.config = {}
                                                            plugin_instance.config[k] = manifest[k]
                                                    if manifest.get("id"):
                                                        plugin_instance.plugin_id = _normalize_plugin_id(manifest["id"])
                                                    if manifest.get("description"):
                                                        plugin_instance.set_description(manifest["description"])
                                                else:
                                                    plugin_instance.registration = None
                                                self.plugin_instances.append(plugin_instance)
                                                self.loaded_plugins[module_path] = plugin_mod_time
                                                self.register_plugin(plugin_instance)
                                                logger.debug(f"Loaded plugin: {module_path} - {attr_name}")
                                            else:
                                                logger.warning(f"__init__ method for {attr_name} is not a function or not defined")
                                    else:
                                        logger.debug(f"Plugin already loaded: {module_path} - {attr_name}")

        # Detect and unload deleted plugins
        to_unload = set(self.loaded_plugins.keys()) - current_plugins
        for module_path in to_unload:
            self.unload_plugin(module_path)
            logger.debug(f"Unloaded plugin: {module_path}")


    def unload_plugin(self, module_path):
        if disable_plugins:
            return
        # Find the plugin instance to remove
        plugin_instance = next((plugin for plugin in self.plugin_instances if plugin.__module__ == module_path), None)
        if plugin_instance:
            # Perform any necessary cleanup
            if hasattr(plugin_instance, 'cleanup'):
                plugin_instance.cleanup()
            self.plugin_instances.remove(plugin_instance)
            logger.debug(f"Unloaded plugin: {module_path}")
        
        # Remove the plugin module from sys.modules
        if module_path in sys.modules:
            del sys.modules[module_path]
        
        # Remove from loaded plugins
        if module_path in self.loaded_plugins:
            del self.loaded_plugins[module_path]

    def initialize_plugins(self):
        if  disable_plugins:
            return
        for plugin in self.plugin_instances:
            plugin.initialize()

    def run(self):
        if disable_plugins:
            return
        pass

    def hot_reload(self):
        if disable_plugins:
            return
        interval_seconds = 60
        while not self.stop_hot_reload.is_set():
            self.load_plugins()
            # Sleep in short chunks so we notice stop_hot_reload quickly (fixes Ctrl+C on Windows)
            for _ in range(interval_seconds):
                if self.stop_hot_reload.is_set():
                    break
                time.sleep(1)

        logger.debug("Hot reload thread stopped.")

    def start_hot_reload(self):
        if disable_plugins:
            return
        self.hot_reload_thread = threading.Thread(target=self.hot_reload)
        self.hot_reload_thread.daemon = True
        self.hot_reload_thread.start()


    def deinitialize_plugins(self):
        if self.hot_reload_thread is not None and self.hot_reload_thread.is_alive():
            # Signal the hot reload thread to stop
            self.stop_hot_reload.set()
            # Wait briefly (hot reload sleeps up to 60s; avoid blocking Ctrl+C)
            self.hot_reload_thread.join(timeout=2.0)

        to_unload = set(self.loaded_plugins.keys())
        for module_path in to_unload:
            self.unload_plugin(module_path)
            logger.debug(f"Unloaded plugin: {module_path}")

        self.loaded_plugins = {}
        self.plugin_instances = []
        self.external_plugins = []
        self.plugin_descriptions = {}
        self.plugin_by_id = {}
        logger.debug("Plugins deinitialized and hot reload thread stopped.")