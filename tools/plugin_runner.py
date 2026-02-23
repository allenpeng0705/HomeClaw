"""
Run a built-in (inline) plugin in a subprocess so a buggy plugin cannot crash Core.
Used when run_plugin_in_process_plugins does not include this plugin_id.
Reads JSON from stdin: { "plugin_id", "capability_id"?, "parameters"?, "request_text"? }
Writes JSON to stdout: { "success": true, "text": "..." } or { "success": false, "error": "..." }
Never raises; exits 0 on success, 1 on failure.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure project root on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _minimal_core_stub():
    """Build a minimal CoreInterface stub so PluginManager can load plugins. All methods no-op or safe return."""
    from base.base import PromptRequest, ChannelType, ContentType
    from datetime import timedelta
    from typing import List, Optional, Dict

    class MinimalCoreStub:
        def check_permission(self, user_name: str, user_id: str, channel_type, content_type) -> bool:
            return True

        def get_latest_chat_info(self):
            return None, None, None

        def get_latest_chats(self, app_id: str, user_name: str, user_id: str, num_rounds: int) -> List:
            return []

        def get_latest_chats_by_role(self, sender_name: str, responder_name: str, num_rounds: int, timestamp=None) -> List:
            return []

        def add_chat_history_by_role(self, sender_name: str, responder_name: str, sender_text: str, responder_text: str):
            pass

        def add_chat_history(self, user_message: str, ai_message: str, app_id=None, user_name=None, user_id=None, session_id=None):
            pass

        async def openai_chat_completion(self, messages: list, grammar=None, tools=None, tool_choice="auto", llm_name=None) -> Optional[str]:
            return None

        async def send_response_to_latest_channel(self, response: str):
            pass

        async def send_response_to_channel_by_key(self, key: str, response: str):
            pass

        async def send_response_to_request_channel(self, response: str, request: PromptRequest):
            pass

        async def add_user_input_to_memory(self, user_input: str, user_name=None, user_id=None, agent_id=None, run_id=None, metadata=None, filters=None):
            pass

        def get_session_id(self, app_id, user_name=None, user_id=None, channel_name=None, account_id=None, validity_period=timedelta(hours=24)):
            return ""

        def get_run_id(self, agent_id, user_name=None, user_id=None, validity_period=timedelta(hours=24)):
            return ""

    return MinimalCoreStub()


def _run_plugin_sync(plugin_id: str, capability_id: Optional[str], parameters: Dict[str, Any], request_text: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Load plugin, run capability or run(), return result dict. All exceptions caught."""
    try:
        stub = _minimal_core_stub()
        from base.PluginManager import PluginManager
        pm = PluginManager(stub)
        pm.load_plugins()
        pid = (plugin_id or "").strip().lower().replace(" ", "_").replace("-", "_")
        plugin = pm.get_plugin_by_id(pid)
        if plugin is None:
            return {"success": False, "error": f"Plugin not found: {plugin_id}"}
        if isinstance(plugin, dict):
            return {"success": False, "error": "External plugins cannot run in plugin_runner subprocess"}
        params = dict(parameters) if isinstance(parameters, dict) else {}
        cap_id = (capability_id or "").strip().lower().replace(" ", "_") or None
        capability = pm.get_capability(plugin, cap_id) if cap_id else None
        if not capability and cap_id:
            return {"success": False, "error": f"Capability not found: {capability_id}"}
        plugin.user_input = request_text or ""
        if output_dir and output_dir.strip():
            try:
                plugin.request_output_dir = Path(output_dir.strip()).resolve()
            except Exception:
                pass  # leave request_output_dir unset on invalid path
        if capability and cap_id:
            method_name = (capability.get("id") or cap_id)
            if hasattr(plugin, method_name):
                old_config = getattr(plugin, "config", None) or {}
                try:
                    plugin.config = {**old_config, **params}
                    method = getattr(plugin, method_name)
                    result = asyncio.run(method())
                finally:
                    plugin.config = old_config
            else:
                return {"success": False, "error": f"Plugin has no capability {method_name}"}
        else:
            result = asyncio.run(plugin.run())
        text = result if isinstance(result, str) else (str(result) if result is not None else "(no output)")
        return {"success": True, "text": text or ""}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main() -> int:
    try:
        raw = sys.stdin.read()
        raw = raw if raw is not None else ""
        try:
            data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        plugin_id = (data.get("plugin_id") or "").strip()
        if not plugin_id:
            out = {"success": False, "error": "plugin_id is required"}
            print(json.dumps(out, ensure_ascii=False))
            return 1
        capability_id = data.get("capability_id")
        parameters = data.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        request_text = (data.get("request_text") or "").strip()
        output_dir = (data.get("output_dir") or "").strip() or None
        result = _run_plugin_sync(plugin_id, capability_id, parameters, request_text, output_dir)
        try:
            out = json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            out = json.dumps({"success": False, "error": "Could not serialize result"}, ensure_ascii=False)
        print(out)
        return 0 if result.get("success") else 1
    except Exception as e:
        try:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        except Exception:
            print('{"success":false,"error":"Unknown error"}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
