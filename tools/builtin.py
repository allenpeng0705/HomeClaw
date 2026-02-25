"""
Built-in tools for HomeClaw (sessions, exec, file, folder, webhook, browser, time, etc.).

All tools are implemented to work cross-platform (Mac, Linux, Windows). File paths use
pathlib for portability. Exec allowlist defaults to platform-appropriate commands when
empty in config. run_skill runs .sh via bash/WSL on Windows when available.

To add a new built-in tool:
1. Define an async executor: async def fn(arguments, context: ToolContext) -> str
2. Create ToolDefinition(name, description, parameters, fn)
3. Call registry.register(tool) in register_builtin_tools.
"""

import asyncio
import json
import os
import platform
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from base.tools import ToolContext, ToolDefinition, ToolRegistry, ROUTING_RESPONSE_ALREADY_SENT
from base.skills import get_skills_dir, resolve_skill_folder_name
from base.workspace import get_workspace_dir, get_agent_memory_file_path, append_daily_memory
from base.util import Util, redact_params_for_log
from base.base import PluginResult, User
from base.media_io import save_data_url_to_media_folder
from loguru import logger
import time as _time

# ---- Process job store (background exec) ----
_process_jobs: Dict[str, Dict[str, Any]] = {}
_process_jobs_lock = asyncio.Lock()

# Keyed skills: require API key from user.yml (per user) or from skill config/env (Companion without user).
# skill_name -> (user_yml_key, env_var)
KEYED_SKILLS = {
    "maton-api-gateway-1.0.0": ("maton_api_key", "MATON_API_KEY"),
    "x-api-1.0.0": ("x_access_token", "X_ACCESS_TOKEN"),
    "meta-social-1.0.0": ("meta_access_token", "META_ACCESS_TOKEN"),
    "hootsuite-1.0.0": ("hootsuite_access_token", "HOOTSUITE_ACCESS_TOKEN"),
    "weibo-api-1.0.0": ("weibo_access_token", "WEIBO_ACCESS_TOKEN"),
}


def _get_keyed_skill_env_overrides(
    skill_name: str, context: ToolContext
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Get env overrides for a keyed skill from current user's skill_api_keys in user.yml.
    Returns (env_overrides, error_msg). If error_msg is set, caller should return it.
    If env_overrides is not None and not empty, caller should add to skill env (subprocess) or pass to in-process.
    If system_user_id is None or 'system' or 'companion' (Companion without user): return (None, None) = use skill config/env directly.
    Never raises: on any exception returns (None, generic_error_msg) so Core never crashes.
    """
    try:
        if skill_name not in KEYED_SKILLS:
            return {}, None
        user_yml_key, env_var = KEYED_SKILLS[skill_name]
        system_user_id = (getattr(context, "system_user_id", None) or "").strip()
        if not system_user_id or system_user_id.lower() in ("system", "companion"):
            return None, None
        users = Util().get_users() or []
        if not isinstance(users, list):
            users = []
        user = next((u for u in users if (getattr(u, "id", None) or getattr(u, "name", "")) == system_user_id), None)
        keys = (getattr(user, "skill_api_keys", None) or {}) if user else {}
        if not isinstance(keys, dict):
            keys = {}
        raw_val = keys.get(user_yml_key)
        key_val = (str(raw_val).strip() if raw_val is not None else "") or ""
        if not key_val:
            return (
                None,
                f"This skill requires an API key. Add it under your user in config/user.yml (skill_api_keys.{user_yml_key}).",
            )
        return {env_var: key_val}, None
    except Exception as e:
        logger.debug("keyed skill env overrides failed: {}", e)
        return (
            None,
            "Could not load user config. Add your API key under config/user.yml (skill_api_keys) for this skill.",
        )


async def _process_reader(proc: asyncio.subprocess.Process, job_id: str, out_key: str, stream: asyncio.StreamReader) -> None:
    """Read stream into job buffer."""
    try:
        data = await stream.read()
        async with _process_jobs_lock:
            if job_id in _process_jobs:
                _process_jobs[job_id][out_key] = data.decode("utf-8", errors="replace")
    except Exception:
        pass


async def _start_background_process(executable: str, args: List[str], timeout: int) -> str:
    """Start a background process; return job_id. Stores process and buffers stdout/stderr."""
    job_id = f"proc_{uuid.uuid4().hex[:12]}"
    try:
        proc = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        raise RuntimeError(str(e))
    async with _process_jobs_lock:
        _process_jobs[job_id] = {
            "proc": proc,
            "command": executable + " " + " ".join(args),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "stdout": "",
            "stderr": "",
            "returncode": None,
        }
    asyncio.create_task(_process_reader(proc, job_id, "stdout", proc.stdout))
    asyncio.create_task(_process_reader(proc, job_id, "stderr", proc.stderr))
    return job_id

def _run_py_script_in_process(
    script_path: Path, args_list: List[str], skill_folder: Path, env_overrides: Optional[Dict[str, str]] = None
) -> tuple:
    """Run a .py script in Core's process (same env). Returns (stdout_str, stderr_str). Run from a thread to avoid blocking.
    Same logic for all Python skills. Script runs in Core's process so a buggy script (e.g. C extension crash, os._exit)
    could affect Core; only skills listed in run_skill_py_in_process_skills run in-process; others run in subprocess.
    env_overrides: optional dict of env var -> value to set for the duration of the script (e.g. per-user API keys); restored in finally. Never None inside (caller passes {})."""
    import io
    if env_overrides is None or not isinstance(env_overrides, dict):
        env_overrides = {}
    old_argv = list(sys.argv)
    old_cwd = os.getcwd()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    old_path = list(sys.path)
    old_env: Dict[str, Optional[str]] = {}
    for k, v in env_overrides.items():
        if k and isinstance(v, str):
            old_env[k] = os.environ.get(k)
            os.environ[k] = v
    out_io = io.StringIO()
    err_io = io.StringIO()
    try:
        sys.argv = [str(script_path)] + args_list
        os.chdir(str(skill_folder))
        # Match `python script.py`: script's directory is first on sys.path (for all .py skills)
        sys.path.insert(0, str(script_path.parent))
        # Pre-import so script's "from google import genai" finds it in sys.modules (same process, but exec() can miss otherwise)
        try:
            import google.genai  # noqa: F401
            import google.genai.types  # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:
            pass
        sys.stdout = out_io
        sys.stderr = err_io
        with open(script_path, "r", encoding="utf-8", errors="replace") as f:
            code = compile(f.read(), str(script_path), "exec")
        globals_dict = {"__name__": "__main__", "__file__": str(script_path), "__builtins__": __builtins__}
        exec(code, globals_dict)
    except SystemExit as e:
        if e.code and e.code != 0:
            err_io.write(f"Script exited with code {e.code}\n")
    except BaseException as e:
        # Catch all (Exception + KeyboardInterrupt etc.) so nothing propagates out of this thread
        err_io.write(f"{type(e).__name__}: {e}\n")
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.argv = old_argv
        os.chdir(old_cwd)
        sys.path[:] = old_path
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return out_io.getvalue(), err_io.getvalue()


# Optional: load tool config from core config (exec allowlist, file_read_shared_dir, etc.)
def _get_tools_config() -> Dict[str, Any]:
    try:
        from base.util import Util
        root = Util().root_path()
        config_path = Path(root) / "config" / "core.yml"
        if config_path.exists():
            data = Util().load_yml_config(str(config_path))
            return data.get("tools") or {}
    except Exception:
        pass
    return {}


def _get_homeclaw_root() -> str:
    """Effective file/folder root (homeclaw_root from config). Empty when not set — do not use workspace for user files. Never raises."""
    try:
        from base.util import Util
        out = Util().get_core_metadata().get_homeclaw_root()
        return (str(out).strip() if out else "") or ""
    except Exception:
        return ""


# ---- Sandbox paths JSON (per-user absolute paths; single source of truth for file tools) ----
SANDBOX_PATHS_FILENAME = "sandbox_paths.json"


def get_sandbox_paths_file_path() -> Path:
    """Path to database/sandbox_paths.json. Never raises."""
    try:
        from base.util import Util
        return Path(Util().data_root()) / SANDBOX_PATHS_FILENAME
    except Exception:
        return Path("database") / SANDBOX_PATHS_FILENAME


def get_sandbox_paths_for_user_key(user_key: str) -> Optional[Dict[str, str]]:
    """
    Resolve absolute sandbox_root and share for a user key (folder name under homeclaw_root: e.g. 'System', 'companion', 'default').
    Returns {"sandbox_root": "<abs>", "share": "<abs>"} or None if homeclaw_root not set. Never raises.
    """
    try:
        base_str = _get_homeclaw_root()
        if not (base_str or "").strip():
            return None
        config = _get_tools_config()
        shared_dir = (config.get("file_read_shared_dir") or "share").strip() or "share"
        base = Path(base_str).resolve()
        sandbox_root = (base / user_key).resolve()
        share = (base / shared_dir).resolve()
        return {"sandbox_root": str(sandbox_root), "share": str(share)}
    except Exception:
        return None


def build_and_save_sandbox_paths_json() -> Dict[str, Any]:
    """
    Build per-user sandbox_root and share (absolute paths), save to database/sandbox_paths.json, return the dict.
    Keys = folder names under homeclaw_root (one per user from user.yml + 'companion'). Always use this JSON for file tools.
    """
    out = {"users": {}}
    try:
        from base.util import Util
        base_str = _get_homeclaw_root()
        if not (base_str or "").strip():
            return out
        users = Util().get_users() or []
        keys = []
        for u in users:
            uid = getattr(u, "id", None) or getattr(u, "name", None)
            if uid:
                keys.append(_safe_user_dir(str(uid)))
        keys.append("companion")
        for k in keys:
            paths = get_sandbox_paths_for_user_key(k)
            if paths:
                out["users"][k] = paths
        path = get_sandbox_paths_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("build_and_save_sandbox_paths_json failed: %s", e)
    return out


def load_sandbox_paths_json() -> Dict[str, Any]:
    """Load database/sandbox_paths.json. Returns {"users": { user_key: {"sandbox_root": ..., "share": ...}}} or empty dict. Never raises."""
    try:
        path = get_sandbox_paths_file_path()
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("load_sandbox_paths_json failed: %s", e)
        return {}


def get_current_user_sandbox_key(request: Optional[Any]) -> str:
    """
    Return the sandbox path key for the current request (same as _get_file_workspace_subdir).
    Used to look up this user's sandbox_root/share from sandbox_paths.json. Never raises.
    """
    if request is None:
        return "default"
    system_user_id = (getattr(request, "system_user_id", None) or "").strip()
    if system_user_id:
        return _safe_user_dir(system_user_id)
    user_id = (getattr(request, "user_id", None) or getattr(request, "user_name", None) or "").strip().lower()
    app_id = (getattr(request, "app_id", None) or "").strip().lower()
    session_id = (getattr(request, "session_id", None) or "").strip().lower()
    if user_id == "companion" or app_id == "companion" or session_id == "companion":
        return "companion"
    channel_name = (getattr(request, "channel_name", None) or getattr(request, "channelType", None) or "").strip().lower()
    if channel_name == "companion":
        return "companion"
    meta = getattr(request, "request_metadata", None) or {}
    if isinstance(meta, dict) and (meta.get("conversation_type") or meta.get("session_id") or "").strip().lower() == "companion":
        return "companion"
    uid = getattr(request, "user_id", None) or getattr(request, "user_name", None)
    return _safe_user_dir(uid)


# ---- Session tools ----
async def _sessions_transcript_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Get session transcript for the current (or given) session."""
    core = context.core
    session_id = arguments.get("session_id") or context.session_id
    limit = int(arguments.get("limit", 20))
    transcript = core.get_session_transcript(
        app_id=context.app_id,
        user_name=context.user_name,
        user_id=context.user_id,
        session_id=session_id,
        limit=limit,
        fetch_all=False,
    )
    return json.dumps(transcript, ensure_ascii=False, indent=0)


async def _sessions_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List sessions for the current app/user (or given app_id, user_id)."""
    core = context.core
    app_id = arguments.get("app_id") or context.app_id
    user_name = arguments.get("user_name") or context.user_name
    user_id = arguments.get("user_id") or context.user_id
    limit = int(arguments.get("limit", 20))
    sessions = core.get_sessions(
        app_id=app_id,
        user_name=user_name,
        user_id=user_id,
        num_rounds=limit,
        fetch_all=False,
    )
    return json.dumps(sessions, ensure_ascii=False, indent=0, default=str)


async def _sessions_send_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Send a message to another session and return that session's agent reply. Target by session_id (from sessions_list) or by app_id + user_id."""
    core = context.core
    message = (arguments.get("message") or arguments.get("text") or "").strip()
    if not message:
        return "Error: message is required"
    session_id = (arguments.get("session_id") or arguments.get("session_key") or "").strip() or None
    app_id = (arguments.get("app_id") or "").strip() or None
    user_id = (arguments.get("user_id") or "").strip() or None
    user_name = (arguments.get("user_name") or "").strip() or None
    timeout_seconds = float(arguments.get("timeout_seconds", 60))
    if not session_id and not (app_id and user_id):
        return "Error: provide session_id (from sessions_list) or both app_id and user_id to target a session"
    try:
        reply = await core.send_message_to_session(
            message=message,
            session_id=session_id,
            app_id=app_id,
            user_id=user_id,
            user_name=user_name,
            timeout_seconds=timeout_seconds,
        )
    except Exception as e:
        return f"Error: {e!s}"
    if reply is None:
        return json.dumps({"status": "error", "message": "No reply (session not found or timeout)"})
    return json.dumps({"status": "ok", "reply": reply})


# ---- Time / system (cross-platform) ----
async def _time_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Return current date and time in system local time (ISO format). Use for age calculation, 'what day is it?', or scheduling when you need precise current time."""
    try:
        now = datetime.now()
        try:
            now = datetime.now().astimezone()
        except Exception:
            pass
        return now.isoformat()
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("Time tool failed: %s", e)
        return datetime.now(timezone.utc).isoformat()


async def _cron_schedule_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Schedule a reminder, run_skill, or run_plugin at cron times. task_type: 'message' (default), 'run_skill', or 'run_plugin'. Optional: tz, delivery_target 'latest' or 'session'."""
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return "Error: Orchestrator/TAM not available"
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "schedule_cron_task"):
        return "Error: TAM cron scheduling not available"
    cron_expr = (arguments.get("cron_expr") or "").strip()
    if not cron_expr:
        return "Error: cron_expr is required (e.g. '0 9 * * *' for daily at 9:00). Format: minute hour day month weekday (5 fields, * for every)."
    task_type = (arguments.get("task_type") or "message").strip().lower()
    tz = (arguments.get("tz") or "").strip() or None
    delivery_target = (arguments.get("delivery_target") or "latest").strip().lower()
    params: Dict[str, Any] = {}
    if tz:
        params["tz"] = tz
    # user_id for deliver_to_user (Companion push); channel_key for channel delivery
    user_id = (getattr(context, "system_user_id", None) or getattr(context, "user_id", None) or "").strip() or "companion"
    params["user_id"] = user_id
    if delivery_target == "session":
        if user_id.lower() in ("companion", "system"):
            params["channel_key"] = "companion"
        elif getattr(context, "app_id", None) and getattr(context, "user_id", None) and getattr(context, "session_id", None):
            params["channel_key"] = f"{context.app_id}:{context.user_id}:{context.session_id}"
    params["_cron"] = True
    hint = "\n(To cancel this recurring reminder, say 'list my recurring reminders' and ask to remove it.)"

    if task_type == "run_skill":
        skill_name = (arguments.get("skill_name") or "").strip()
        script = (arguments.get("script") or "").strip()
        args_list = arguments.get("args")
        if isinstance(args_list, str):
            args_list = [a.strip() for a in args_list.split(",") if a.strip()]
        elif not isinstance(args_list, list):
            args_list = []
        if not skill_name or not script:
            return "Error: For task_type 'run_skill', skill_name and script are required (e.g. skill_name='weather-1.0.0', script='get_weather.py', args=['Beijing'])."
        message = (arguments.get("message") or "").strip() or f"run_skill {skill_name} {script}"
        params["message"] = message
        params["task_type"] = "run_skill"
        params["skill_name"] = skill_name
        params["script"] = script
        params["args"] = args_list
        post_process_prompt = (arguments.get("post_process_prompt") or "").strip()
        if post_process_prompt:
            params["post_process_prompt"] = post_process_prompt

        def make_run_skill_task(prms: Dict[str, Any]):
            async def _task():
                from base.tools import get_tool_registry, ToolContext
                registry = get_tool_registry()
                if not registry:
                    await tam._send_reminder_to_channel_safe("Error: tool registry not available", prms)
                    return
                ctx = ToolContext(core=core)
                try:
                    result = await registry.execute_async(
                        "run_skill",
                        {"skill_name": prms["skill_name"], "script": prms["script"], "args": prms.get("args") or []},
                        ctx,
                    )
                except Exception as e:
                    result = f"Error: {e}"
                text = (result or "(no output)").strip()
                prompt = (prms.get("post_process_prompt") or "").strip()
                if prompt and hasattr(core, "openai_chat_completion"):
                    try:
                        refined = await core.openai_chat_completion([
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": text},
                        ])
                        if refined and isinstance(refined, str) and refined.strip():
                            text = refined.strip()
                    except Exception:
                        pass
                await tam._send_reminder_to_channel_safe(text, prms)
            return _task

        task = make_run_skill_task(params)
    elif task_type == "run_plugin":
        plugin_id = (arguments.get("plugin_id") or "").strip().lower().replace(" ", "_")
        if not plugin_id:
            return "Error: For task_type 'run_plugin', plugin_id is required (e.g. news, ppt-generation)."
        message = (arguments.get("message") or "").strip() or f"run_plugin {plugin_id}"
        params["message"] = message
        params["task_type"] = "run_plugin"
        params["plugin_id"] = plugin_id
        cap_id = (arguments.get("capability_id") or "").strip().lower().replace(" ", "_") or None
        if not cap_id and plugin_id == "headlines":
            cap_id = "fetch_headlines"
        params["capability_id"] = cap_id
        llm_params = arguments.get("parameters")
        plugin_params = llm_params if isinstance(llm_params, dict) else {}
        # At schedule-creation time: resolve and validate plugin params so we can ask the user now if something is missing.
        plugin_manager = getattr(core, "plugin_manager", None)
        if plugin_manager:
            plugin = plugin_manager.get_plugin_by_id(plugin_id)
            if not plugin:
                return f"Error: plugin not found: {plugin_id}. Cannot schedule."
            capability = plugin_manager.get_capability(plugin, cap_id) if cap_id else None
            if not capability and not isinstance(plugin, dict):
                reg = getattr(plugin, "registration", None) or {}
                caps = reg.get("capabilities") or []
                if caps:
                    capability = caps[0]
            if capability and (capability.get("parameters") or []):
                from base.plugin_param_resolver import (
                    _get_plugin_config,
                    resolve_and_validate_plugin_params,
                )
                from base.profile_store import get_profile
                request = getattr(context, "request", None)
                system_user_id = getattr(context, "system_user_id", None) or (getattr(request, "user_id", None) if request else None)
                profile = get_profile(system_user_id or "") if system_user_id else {}
                plugin_config = _get_plugin_config(plugin)
                system_context = getattr(core, "get_system_context_for_plugins", lambda *a, **k: {})(system_user_id, request) if callable(getattr(core, "get_system_context_for_plugins", None)) else {}
                resolved, err, ask_user = resolve_and_validate_plugin_params(
                    plugin_params, capability, profile, plugin_config,
                    plugin_id=plugin_id, capability_id=cap_id,
                    system_context=system_context,
                )
                if err and ask_user:
                    missing = ask_user.get("missing") or []
                    if missing:
                        return (
                            f"To schedule the plugin '{plugin_id}', the following parameters are required: {', '.join(missing)}. "
                            "Ask the user for these values, then call cron_schedule again with the parameters={\"param_name\": \"value\", ...} filled in."
                        )
                    uncertain = ask_user.get("uncertain") or []
                    if uncertain:
                        return (
                            "The plugin has parameters filled from system (datetime/location), profile, or config that are not 100% confident. "
                            "Ask the user to confirm or provide values (e.g. location, timezone), then call cron_schedule again with parameters={\"param_name\": \"value\", ...}."
                        )
                if err:
                    return err
                plugin_params = resolved
        # When scheduling headlines with no parameters, hint to ask for category/source/language so user can refine
        if plugin_id == "headlines" and (not plugin_params or not any(str(v).strip() for v in (plugin_params or {}).values())):
            return (
                "To schedule headlines (e.g. every 8 am), you can optionally set category (e.g. sports, business, technology), "
                "source (e.g. BBC), page_size (e.g. 5), or language. Ask the user: 'What category would you like? (sports, business, technology, or general)' "
                "or 'Which source? (e.g. BBC)' — then call cron_schedule again with parameters={\"category\": \"sports\", \"page_size\": 5} etc."
            )
        params["parameters"] = plugin_params
        post_process_prompt = (arguments.get("post_process_prompt") or "").strip()
        if post_process_prompt:
            params["post_process_prompt"] = post_process_prompt

        def make_run_plugin_task(prms: Dict[str, Any]):
            async def _task():
                from base.tools import get_tool_registry, ToolContext
                from base.base import PromptRequest, ChannelType, ContentType
                registry = get_tool_registry()
                if not registry:
                    await tam._send_reminder_to_channel_safe("Error: tool registry not available", prms)
                    return
                channel_key = prms.get("channel_key") or ""
                parts = channel_key.split(":") if channel_key else ["", ""]
                app_id = parts[0] if len(parts) > 0 else ""
                user_id = parts[1] if len(parts) > 1 else ""
                if channel_key == "companion":
                    app_id = app_id or "homeclaw"
                    user_id = "companion"
                req = PromptRequest(
                    request_id=str(uuid.uuid4()),
                    channel_name="cron",
                    request_metadata={"capability_id": prms.get("capability_id"), "capability_parameters": prms.get("parameters") or {}},
                    channelType=ChannelType.IM,
                    user_name="cron",
                    app_id=app_id,
                    user_id=user_id,
                    contentType=ContentType.TEXT,
                    text="",
                    action="respond",
                    host="cron",
                    port=0,
                    images=[],
                    videos=[],
                    audios=[],
                    files=[],
                    timestamp=_time.time(),
                )
                ctx = ToolContext(core=core, request=req, cron_scheduled=True)
                try:
                    result = await registry.execute_async(
                        "route_to_plugin",
                        {
                            "plugin_id": prms["plugin_id"],
                            "capability_id": prms.get("capability_id"),
                            "parameters": prms.get("parameters") or {},
                        },
                        ctx,
                    )
                except Exception as e:
                    result = f"Error: {e}"
                text = (result or "(no output)").strip()
                if not isinstance(text, str):
                    text = str(text)
                prompt = (prms.get("post_process_prompt") or "").strip()
                if prompt and hasattr(core, "openai_chat_completion"):
                    try:
                        refined = await core.openai_chat_completion([
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": text},
                        ])
                        if refined and isinstance(refined, str) and refined.strip():
                            text = refined.strip()
                    except Exception:
                        pass
                await tam._send_reminder_to_channel_safe(text, prms)
            return _task

        task = make_run_plugin_task(params)
    elif task_type == "run_tool":
        tool_name = (arguments.get("tool_name") or "").strip()
        if not tool_name:
            return "Error: For task_type 'run_tool', tool_name is required (e.g. web_search). Use this for 'search the latest sports news every 7 am' — use run_tool with tool_name=web_search, tool_arguments={query: 'latest sports news', count: 10}. Do NOT use run_plugin headlines for 'search'."
        message = (arguments.get("message") or "").strip() or f"run_tool {tool_name}"
        params["message"] = message
        params["task_type"] = "run_tool"
        params["tool_name"] = tool_name
        tool_args = arguments.get("tool_arguments")
        params["tool_arguments"] = tool_args if isinstance(tool_args, dict) else {}
        post_process_prompt = (arguments.get("post_process_prompt") or "").strip()
        if post_process_prompt:
            params["post_process_prompt"] = post_process_prompt

        def make_run_tool_task(prms: Dict[str, Any]):
            async def _task():
                from base.tools import get_tool_registry, ToolContext
                registry = get_tool_registry()
                if not registry:
                    await tam._send_reminder_to_channel_safe("Error: tool registry not available", prms)
                    return
                ctx = ToolContext(core=core)
                try:
                    result = await registry.execute_async(
                        prms["tool_name"],
                        prms.get("tool_arguments") or {},
                        ctx,
                    )
                except Exception as e:
                    result = f"Error: {e}"
                text = (result or "(no output)").strip()
                if not isinstance(text, str):
                    text = str(text)
                prompt = (prms.get("post_process_prompt") or "").strip()
                if prompt and hasattr(core, "openai_chat_completion"):
                    try:
                        refined = await core.openai_chat_completion([
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": text},
                        ])
                        if refined and isinstance(refined, str) and refined.strip():
                            text = refined.strip()
                    except Exception:
                        pass
                await tam._send_reminder_to_channel_safe(text, prms)
            return _task

        task = make_run_tool_task(params)
    else:
        message = (arguments.get("message") or "").strip() or "Scheduled reminder"
        params["message"] = message

        def make_task(msg: str, prms: Dict[str, Any]):
            async def _task():
                await tam._send_reminder_to_channel_safe(msg + hint, prms)
            return _task

        task = make_task(message, params)

    job_id = tam.schedule_cron_task(task, cron_expr, params=params)
    if job_id is None:
        return "Error: Failed to schedule (invalid cron expression or croniter not installed)."
    out = {"scheduled": True, "job_id": job_id, "cron_expr": cron_expr, "message": params.get("message", "Scheduled reminder")}
    if task_type == "run_skill":
        out["task_type"] = "run_skill"
        out["skill_name"] = params.get("skill_name")
        out["script"] = params.get("script")
    elif task_type == "run_plugin":
        out["task_type"] = "run_plugin"
        out["plugin_id"] = params.get("plugin_id")
    elif task_type == "run_tool":
        out["task_type"] = "run_tool"
        out["tool_name"] = params.get("tool_name")
    if tz:
        out["tz"] = tz
    if delivery_target:
        out["delivery_target"] = delivery_target
    return json.dumps(out)


async def _cron_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List all recurring (cron) reminders: job_id, message, cron_expr, next_run, enabled, last_run_at, last_status, delivery_target. User can identify which to remove by message then use cron_remove(job_id) or cron_update(job_id, enabled=false)."""
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return json.dumps({"cron_jobs": [], "error": "Orchestrator/TAM not available"})
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "cron_jobs"):
        return json.dumps({"cron_jobs": []})

    def _job_row(j):
        p = j.get("params") or {}
        row = {
            "job_id": j.get("job_id"),
            "message": p.get("message", ""),
            "cron_expr": j.get("cron_expr"),
            "next_run": str(j.get("next_run", "")),
            "enabled": p.get("enabled", True),
            "last_run_at": p.get("last_run_at"),
            "last_status": p.get("last_status"),
            "last_duration_ms": p.get("last_duration_ms"),
        }
        if p.get("channel_key"):
            row["delivery_target"] = "session"
            row["channel_key"] = p.get("channel_key")
        else:
            row["delivery_target"] = "latest"
        if p.get("tz"):
            row["tz"] = p.get("tz")
        if p.get("task_type") == "run_skill":
            row["task_type"] = "run_skill"
            row["skill_name"] = p.get("skill_name", "")
            row["script"] = p.get("script", "")
        elif p.get("task_type") == "run_plugin":
            row["task_type"] = "run_plugin"
            row["plugin_id"] = p.get("plugin_id", "")
        elif p.get("task_type") == "run_tool":
            row["task_type"] = "run_tool"
            row["tool_name"] = p.get("tool_name", "")
        return row

    lock = getattr(tam, "_cron_lock", None)
    if lock:
        with lock:
            jobs = [_job_row(j) for j in (tam.cron_jobs or [])]
    else:
        jobs = [_job_row(j) for j in (getattr(tam, "cron_jobs", []) or [])]
    return json.dumps({"cron_jobs": jobs})


async def _cron_remove_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Remove a scheduled cron job by job_id. Use cron_list to get job_ids."""
    job_id = (arguments.get("job_id") or "").strip()
    if not job_id:
        return "Error: job_id is required (use cron_list to get job_ids)"
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return json.dumps({"removed": False, "error": "Orchestrator/TAM not available"})
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "remove_cron_job"):
        return json.dumps({"removed": False, "error": "TAM cron not available"})
    removed = tam.remove_cron_job(job_id)
    return json.dumps({"removed": removed, "job_id": job_id})


async def _cron_update_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Update a cron job: enable or disable (enabled=true/false). Use cron_list to get job_ids."""
    job_id = (arguments.get("job_id") or "").strip()
    if not job_id:
        return "Error: job_id is required (use cron_list to get job_ids)"
    enabled = arguments.get("enabled")
    if enabled is None:
        return "Error: enabled is required (true or false)"
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return json.dumps({"updated": False, "error": "Orchestrator/TAM not available"})
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "update_cron_job"):
        return json.dumps({"updated": False, "error": "TAM cron not available"})
    ok = tam.update_cron_job(job_id, enabled=bool(enabled))
    return json.dumps({"updated": ok, "job_id": job_id, "enabled": bool(enabled)})


async def _cron_run_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Run a cron job once now (force run). Use cron_list to get job_ids."""
    job_id = (arguments.get("job_id") or "").strip()
    if not job_id:
        return "Error: job_id is required (use cron_list to get job_ids)"
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return json.dumps({"run": False, "error": "Orchestrator/TAM not available"})
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "run_cron_job_now"):
        return json.dumps({"run": False, "error": "TAM cron not available"})
    ok = tam.run_cron_job_now(job_id)
    return json.dumps({"run": ok, "job_id": job_id})


async def _cron_status_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Return cron scheduler status: scheduler_enabled, next_wake_at, jobs_count. For UI or debugging."""
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return json.dumps({"scheduler_enabled": False, "error": "Orchestrator/TAM not available"})
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "get_cron_status"):
        return json.dumps({"scheduler_enabled": False, "jobs_count": 0})
    status = tam.get_cron_status()
    return json.dumps(status)


async def _remind_me_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Schedule a one-shot reminder. Use minutes (e.g. 5 for 'in 5 minutes') or at_time (YYYY-MM-DD HH:MM:SS) for a specific time. No LLM in TAM; model supplies structured args."""
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return "Error: Orchestrator/TAM not available"
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "schedule_one_shot"):
        return "Error: TAM not available"
    message = (arguments.get("message") or "").strip() or "Reminder"
    minutes = arguments.get("minutes")
    at_time = (arguments.get("at_time") or "").strip()
    if minutes is not None:
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            return "Error: minutes must be an integer"
        if minutes <= 0:
            return "Error: minutes must be positive"
        run_time = datetime.now() + timedelta(minutes=minutes)
        run_time_str = run_time.strftime("%Y-%m-%d %H:%M:%S")
    elif at_time:
        # Accept "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD" (use 09:00:00) or ISO with T
        at_time_norm = at_time.replace("T", " ").strip()
        try:
            if len(at_time_norm) >= 19:
                run_time_str = at_time_norm[:19]
                datetime.strptime(run_time_str, "%Y-%m-%d %H:%M:%S")
            elif len(at_time_norm) >= 10:
                datetime.strptime(at_time_norm[:10], "%Y-%m-%d")
                run_time_str = at_time_norm[:10] + " 09:00:00"
            else:
                return f"Error: at_time must be YYYY-MM-DD HH:MM:SS or YYYY-MM-DD (got: {at_time!r})"
        except ValueError:
            return f"Error: at_time must be YYYY-MM-DD HH:MM:SS or YYYY-MM-DD (got: {at_time!r})"
    else:
        return "Error: provide either minutes (e.g. 5 for 'in 5 minutes') or at_time (e.g. '2025-02-16 09:00:00')"
    user_id = (getattr(context, "system_user_id", None) or getattr(context, "user_id", None) or "").strip() or "companion"
    channel_key = None
    if getattr(context, "app_id", None) and getattr(context, "user_id", None) and getattr(context, "session_id", None):
        channel_key = f"{context.app_id}:{context.user_id}:{context.session_id}"
    elif user_id.lower() in ("companion", "system"):
        channel_key = "companion"
    try:
        tam.schedule_one_shot(message, run_time_str, user_id=user_id, channel_key=channel_key)
        return json.dumps({"scheduled": True, "message": message, "run_at": run_time_str})
    except Exception as e:
        return f"Error: {e!s}"


async def _record_date_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Record a date/event for future reference. Optional: event_date (YYYY-MM-DD) if you can compute it from 'when'; remind_on ('day_before' or 'on_day') to schedule a reminder; remind_message for the reminder text. E.g. girlfriend's birthday in two weeks -> event_date=computed, remind_on=day_before."""
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return "Error: Orchestrator/TAM not available"
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "record_event"):
        return "Error: TAM not available"
    event_name = (arguments.get("event_name") or "").strip() or "event"
    when = (arguments.get("when") or "").strip()
    note = (arguments.get("note") or "").strip()
    event_date = (arguments.get("event_date") or "").strip()
    remind_on = (arguments.get("remind_on") or "").strip().lower()
    remind_message = (arguments.get("remind_message") or "").strip()
    if not when:
        return "Error: when is required (e.g. 'tomorrow', 'in two weeks', '2025-03-15')"
    if remind_on and remind_on not in ("day_before", "on_day"):
        return "Error: remind_on must be 'day_before' or 'on_day' if set"
    if remind_on and not event_date:
        return "Error: event_date (YYYY-MM-DD) is required when remind_on is set (compute from 'when')"
    try:
        system_user_id = getattr(context, "system_user_id", None) or getattr(context, "user_id", None)
        result = tam.record_event(
            event_name=event_name,
            when=when,
            note=note,
            event_date=event_date or None,
            remind_on=remind_on or None,
            remind_message=remind_message or None,
            system_user_id=system_user_id,
        )
        return json.dumps(result)
    except Exception as e:
        return f"Error: {e!s}"


async def _recorded_events_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List recorded dates/events (from record_date). Use when user asks 'what is coming up?' or 'what did I record?'."""
    core = context.core
    orchestrator = getattr(core, "orchestratorInst", None)
    if orchestrator is None:
        return json.dumps({"recorded_events": [], "error": "Orchestrator/TAM not available"})
    tam = getattr(orchestrator, "tam", None)
    if tam is None or not hasattr(tam, "list_recorded_events"):
        return json.dumps({"recorded_events": []})
    system_user_id = getattr(context, "system_user_id", None) or getattr(context, "user_id", None)
    events = tam.list_recorded_events(system_user_id=system_user_id)
    return json.dumps({"recorded_events": events})


async def _session_status_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Return current session info: session_id, app_id, user_name, user_id (from tool context)."""
    return json.dumps({
        "session_id": context.session_id,
        "app_id": context.app_id,
        "user_name": context.user_name,
        "user_id": context.user_id,
    }, indent=0)


def _profile_base_dir() -> Optional[str]:
    """Profile store base dir from core config. None = use default (database/profiles). Returns a sentinel if disabled."""
    try:
        from base.util import Util
        meta = Util().get_core_metadata()
        cfg = getattr(meta, "profile", None) or {}
        if not cfg.get("enabled", True):
            return "__disabled__"
        return (cfg.get("dir") or "").strip() or None
    except Exception:
        return None


async def _profile_get_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Get the current user's profile (or specific keys). Per-user: uses system user id from context."""
    from base.profile_store import get_profile
    uid = getattr(context, "system_user_id", None) or context.user_id
    if not (uid or "").strip():
        return json.dumps({"error": "No user context", "profile": {}})
    if _profile_base_dir() == "__disabled__":
        return json.dumps({"profile": {}, "message": "Profile is disabled in config."})
    keys = arguments.get("keys")
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.split(",") if k.strip()]
    base_dir = _profile_base_dir()
    base_dir = None if base_dir == "__disabled__" else base_dir
    profile = get_profile(uid, base_dir=base_dir)
    if not profile:
        return json.dumps({"profile": {}, "message": "No profile stored yet."})
    if keys:
        profile = {k: profile[k] for k in keys if k in profile}
    return json.dumps({"profile": profile}, ensure_ascii=False, indent=0)


async def _profile_update_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Update the current user's profile with new facts (e.g. name, birthday, favorite_foods, families). Use when the user tells you something about themselves to remember. Per-user. Pass updates as key-value pairs; use remove_keys to forget specific keys."""
    from base.profile_store import update_profile
    uid = getattr(context, "system_user_id", None) or context.user_id
    if not (uid or "").strip():
        return "Error: No user context; cannot update profile."
    updates = arguments.get("updates")
    if isinstance(updates, str):
        try:
            updates = json.loads(updates)
        except json.JSONDecodeError:
            updates = {}
    if not isinstance(updates, dict):
        updates = {}
    # Also allow flat key/value in arguments (e.g. name="Alice", birthday="1990-01-01")
    for k, v in arguments.items():
        if k in ("updates", "remove_keys") or v is None:
            continue
        if isinstance(v, (str, int, float, bool)) or (isinstance(v, (list, dict)) and k not in ("updates", "remove_keys")):
            updates[k] = v
    remove_keys = arguments.get("remove_keys")
    if isinstance(remove_keys, str):
        remove_keys = [k.strip() for k in remove_keys.split(",") if k.strip()]
    if not isinstance(remove_keys, list):
        remove_keys = []
    if _profile_base_dir() == "__disabled__":
        return "Profile is disabled in config."
    base_dir = _profile_base_dir()
    base_dir = None if base_dir == "__disabled__" else base_dir
    update_profile(uid, updates, remove_keys=remove_keys or None, base_dir=base_dir)
    return json.dumps({"message": "Profile updated.", "updated_keys": list(updates.keys()), "removed_keys": remove_keys})


async def _profile_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List what we know about the current user (profile keys and a short preview). Per-user."""
    from base.profile_store import get_profile, format_profile_for_prompt
    uid = getattr(context, "system_user_id", None) or context.user_id
    if not (uid or "").strip():
        return json.dumps({"keys": [], "message": "No user context."})
    if _profile_base_dir() == "__disabled__":
        return json.dumps({"keys": [], "message": "Profile is disabled in config."})
    base_dir = _profile_base_dir()
    base_dir = None if base_dir == "__disabled__" else base_dir
    profile = get_profile(uid, base_dir=base_dir)
    if not profile:
        return json.dumps({"keys": [], "preview": "", "message": "No profile stored yet. Use profile_update when the user tells you something to remember."})
    preview = format_profile_for_prompt(profile, max_chars=1500)
    return json.dumps({"keys": list(profile.keys()), "preview": preview}, ensure_ascii=False, indent=0)


async def _memory_search_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Search stored memories (RAG/Chroma). Returns relevant snippets. Only works when use_memory is enabled."""
    core = context.core
    query = (arguments.get("query") or "").strip()
    if not query:
        return "Error: query is required"
    limit = int(arguments.get("limit", 10))
    limit = min(max(1, limit), 50)
    try:
        results = await core.search_memory(
            query=query,
            user_name=context.user_name,
            user_id=context.user_id,
            app_id=context.app_id,
            limit=limit,
        )
    except Exception as e:
        return f"Error: {e!s}"
    if not results:
        return json.dumps({"memories": [], "message": "No memories found or memory not enabled."})
    out = [{"memory": r.get("memory", ""), "score": r.get("score")} for r in results]
    return json.dumps({"memories": out})


async def _memory_get_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Get a single memory by id (from memory_search results or known id). Only works when use_memory is enabled."""
    core = context.core
    memory_id = (arguments.get("memory_id") or arguments.get("id") or "").strip()
    if not memory_id:
        return "Error: memory_id is required"
    try:
        mem = core.get_memory_by_id(memory_id)
    except Exception as e:
        return f"Error: {e!s}"
    if mem is None:
        # Cognee backend does not implement get(memory_id); use memory_search results directly (they include the memory text).
        backend = type(getattr(core, "mem_instance", None)).__name__
        msg = "Get by id not supported with Cognee backend; use the memory content from memory_search results directly." if backend == "CogneeMemory" else "Not found or memory not enabled."
        return json.dumps({"memory": None, "message": msg})
    return json.dumps({"memory": mem.get("memory"), "id": mem.get("id"), "metadata": {k: v for k, v in mem.items() if k not in ("memory", "id")}})


async def _append_agent_memory_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Append content to AGENT_MEMORY.md (curated long-term memory). Only works when use_agent_memory_file is enabled."""
    content = (arguments.get("content") or "").strip()
    if not content:
        return "Error: content is required"
    try:
        meta = Util().get_core_metadata()
        if not getattr(meta, "use_agent_memory_file", True):
            return json.dumps({"ok": False, "message": "AGENT_MEMORY.md is disabled (use_agent_memory_file: false). Enable in config/core.yml to use append_agent_memory."})
        ws_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "config/workspace")
        agent_path = getattr(meta, "agent_memory_path", None) or ""
        sys_uid = getattr(context, "system_user_id", None) if context else None
        path = get_agent_memory_file_path(workspace_dir=ws_dir, agent_memory_path=agent_path or None, system_user_id=sys_uid)
        if path is None:
            return json.dumps({"ok": False, "message": "AGENT_MEMORY path not configured."})
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n\n")
            f.write(content)
            f.write("\n")
        # Re-sync so agent_memory_search finds the new content without restarting Core
        core = getattr(context, "core", None)
        if core and getattr(meta, "use_agent_memory_search", True):
            try:
                re_sync = getattr(core, "re_sync_agent_memory", None)
                if callable(re_sync):
                    n = await re_sync(system_user_id=sys_uid)
                    return json.dumps({"ok": True, "message": f"Appended to {path.name}", "path": str(path), "chunks_indexed": n})
            except Exception:
                pass
        return json.dumps({"ok": True, "message": f"Appended to {path.name}", "path": str(path)})
    except Exception as e:
        logger.exception("append_agent_memory failed")
        return json.dumps({"ok": False, "message": str(e)})


async def _append_daily_memory_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Append content to today's daily memory file (memory/YYYY-MM-DD.md). Only works when use_daily_memory is enabled."""
    content = (arguments.get("content") or "").strip()
    if not content:
        return "Error: content is required"
    try:
        meta = Util().get_core_metadata()
        if not getattr(meta, "use_daily_memory", True):
            return json.dumps({"ok": False, "message": "Daily memory is disabled (use_daily_memory: false). Enable in config/core.yml to use append_daily_memory."})
        ws_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "config/workspace")
        daily_dir = getattr(meta, "daily_memory_dir", None) or ""
        sys_uid = getattr(context, "system_user_id", None) if context else None
        ok = append_daily_memory(content, d=None, workspace_dir=ws_dir, daily_memory_dir=daily_dir if daily_dir else None, system_user_id=sys_uid)
        if ok:
            from datetime import date
            # Re-sync so agent_memory_search finds the new content without restarting Core
            core = getattr(context, "core", None)
            if core and getattr(meta, "use_agent_memory_search", True):
                try:
                    re_sync = getattr(core, "re_sync_agent_memory", None)
                    if callable(re_sync):
                        n = await re_sync(system_user_id=sys_uid)
                        return json.dumps({"ok": True, "message": f"Appended to daily memory ({date.today().isoformat()}.md)", "chunks_indexed": n})
                except Exception:
                    pass
            return json.dumps({"ok": True, "message": f"Appended to daily memory ({date.today().isoformat()}.md)"})
        return json.dumps({"ok": False, "message": "Failed to append to daily memory file."})
    except Exception as e:
        logger.exception("append_daily_memory failed")
        return json.dumps({"ok": False, "message": str(e)})


async def _agent_memory_search_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Search AGENT_MEMORY.md and daily memory by semantic similarity. Use before agent_memory_get to pull only relevant parts."""
    try:
        meta = Util().get_core_metadata()
    except Exception:
        return json.dumps({"results": [], "message": "Config unavailable."})
    if not getattr(meta, "use_agent_memory_search", True):
        return json.dumps({"results": [], "message": "Agent memory search is disabled. Set use_agent_memory_search: true in config/core.yml."})
    core = getattr(context, "core", None)
    if core is None:
        return json.dumps({"results": [], "message": "Core not available."})
    query = (arguments.get("query") or "").strip()
    if not query:
        return "Error: query is required"
    try:
        max_results = min(max(1, int(arguments.get("max_results", 10))), 50)
    except (TypeError, ValueError):
        max_results = 10
    min_score = arguments.get("min_score")
    if min_score is not None:
        try:
            min_score = float(min_score)
        except (TypeError, ValueError):
            min_score = None
    try:
        sys_uid = getattr(context, "system_user_id", None) if context else None
        results = await core.search_agent_memory(query=query, max_results=max_results, min_score=min_score, system_user_id=sys_uid)
    except Exception as e:
        return json.dumps({"results": [], "message": str(e)})
    return json.dumps({"results": results}, ensure_ascii=False, indent=0)


async def _agent_memory_get_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Read a snippet from AGENT_MEMORY.md or memory/YYYY-MM-DD.md by path and optional line range. Use after agent_memory_search to load only needed lines."""
    try:
        meta = Util().get_core_metadata()
    except Exception:
        return json.dumps({"path": "", "text": "", "message": "Config unavailable."})
    if not getattr(meta, "use_agent_memory_search", True):
        return json.dumps({"path": "", "text": "", "message": "Agent memory get is disabled. Set use_agent_memory_search: true in config/core.yml."})
    core = getattr(context, "core", None)
    if core is None:
        return json.dumps({"path": "", "text": "", "message": "Core not available."})
    path = (arguments.get("path") or "").strip()
    if not path:
        return "Error: path is required (e.g. AGENT_MEMORY.md or memory/2025-02-16.md)"
    from_line = arguments.get("from_line")
    if from_line is not None:
        try:
            from_line = int(from_line)
        except (TypeError, ValueError):
            from_line = None
    lines = arguments.get("lines")
    if lines is not None:
        try:
            lines = int(lines)
        except (TypeError, ValueError):
            lines = None
    try:
        sys_uid = getattr(context, "system_user_id", None) if context else None
        out = core.get_agent_memory_file(path=path, from_line=from_line, lines=lines, system_user_id=sys_uid)
    except Exception as e:
        return json.dumps({"path": path, "text": "", "message": str(e)})
    if out is None:
        return json.dumps({"path": path, "text": "", "message": "File not found or not readable."})
    return json.dumps(out, ensure_ascii=False, indent=0)


def _web_search_error_user_message(provider: str, status_code: Optional[int], body_text: str, fallback: str) -> str:
    """Build a user-friendly error message when web search fails. Informs about API key, free tier, or paid service."""
    detail = ""
    try:
        obj = json.loads(body_text) if body_text else {}
        d = obj.get("detail") or obj
        detail = (d.get("error") if isinstance(d, dict) else str(d)) or ""
    except Exception:
        detail = body_text[:200] if body_text else ""
    if status_code == 401:
        if provider == "tavily":
            return (
                "Invalid or missing Tavily API key. Get a free API key at https://tavily.com (free tier available). "
                "Set TAVILY_API_KEY or config tools.web.search.tavily.api_key. "
                "For paid or higher limits, set your API key in the Tavily dashboard."
            )
        return (
            "Invalid or missing Brave API key. Set BRAVE_API_KEY or config tools.web.search.api_key. "
            "Brave has a free tier ($5 monthly credits). Or use Tavily as default: set tools.web.search.provider to 'tavily' and TAVILY_API_KEY."
        )
    if status_code in (429, 432, 433):
        return (
            f"Web search rate or plan limit exceeded ({provider}). "
            "Free tier has limits; try again later or set API key for paid service at "
            "https://tavily.com (Tavily) or Brave API dashboard (Brave). " + (f"Detail: {detail}" if detail else "")
        ).strip()
    if status_code and status_code >= 500:
        return f"Web search server error ({provider}). Try again later. " + (f"Detail: {detail}" if detail else "")
    return fallback or (f"Web search failed: {detail}" if detail else "Web search failed. Check API key and try again.")


async def _web_search_tavily(query: str, count: int, api_key: str, search_config: Dict[str, Any]) -> str:
    """Search using Tavily API. POST /search with search_depth, topic, time_range. See https://docs.tavily.com/documentation/api-reference/endpoint/search"""
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required for web_search. pip install httpx", "results": []})
    search_depth = (search_config.get("search_depth") or "basic").strip().lower()
    if search_depth not in ("basic", "advanced", "fast", "ultra-fast"):
        search_depth = "basic"
    topic = (search_config.get("topic") or "general").strip().lower()
    if topic not in ("general", "news", "finance"):
        topic = "general"
    time_range = (search_config.get("time_range") or "").strip().lower() or None
    if time_range and time_range not in ("day", "week", "month", "year", "d", "w", "m", "y"):
        time_range = None
    chunks_per_source = search_config.get("chunks_per_source")
    if chunks_per_source is not None:
        chunks_per_source = max(1, min(3, int(chunks_per_source)))
    body = {
        "query": query,
        "max_results": min(max(1, count), 20),
        "search_depth": search_depth,
        "topic": topic,
        "include_answer": bool(search_config.get("include_answer", False)),
    }
    if time_range:
        body["time_range"] = time_range
    if chunks_per_source is not None and search_depth == "advanced":
        body["chunks_per_source"] = chunks_per_source
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code != 200:
                msg = _web_search_error_user_message("tavily", resp.status_code, resp.text, resp.reason_phrase)
                return json.dumps({"error": msg, "results": []})
            data = resp.json()
    except httpx.TimeoutException:
        return json.dumps({"error": "Tavily search timed out. Try again later.", "results": []})
    except Exception as e:
        return json.dumps({"error": f"Tavily search failed: {e!s}. Check API key at https://tavily.com or set TAVILY_API_KEY for free tier.", "results": []})
    results = []
    for r in (data.get("results") or [])[:count]:
        results.append({
            "title": r.get("title"),
            "url": r.get("url"),
            "description": r.get("content") or r.get("description"),
        })
    return json.dumps({"results": results, "provider": "tavily"})


def _brave_search_type_endpoint(st: str) -> str:
    """Return Brave API path for search_type: web, news, video, image."""
    st = (st or "web").strip().lower()
    if st == "news":
        return "https://api.search.brave.com/res/v1/news/search"
    if st == "video":
        return "https://api.search.brave.com/res/v1/videos/search"
    if st == "image":
        return "https://api.search.brave.com/res/v1/images/search"
    return "https://api.search.brave.com/res/v1/web/search"


def _brave_parse_results(data: dict, search_type: str, count: int) -> List[Dict[str, Any]]:
    """Normalize Brave response to list of {title, url, description} (or thumbnail for image)."""
    results = []
    st = (search_type or "web").strip().lower()
    if st == "news":
        arr = (data.get("news") or {}).get("results") or []
    elif st == "video":
        arr = (data.get("videos") or {}).get("results") or []
    elif st == "image":
        arr = (data.get("images") or {}).get("results") or []
    else:
        arr = (data.get("web") or {}).get("results") or []
    for r in arr[:count]:
        if not isinstance(r, dict):
            continue
        title = r.get("title") or r.get("name") or ""
        url = r.get("url") or r.get("link") or ""
        desc = r.get("description") or r.get("snippet") or r.get("text") or ""
        if st == "image" and not url:
            url = r.get("thumbnail") or r.get("src") or ""
        results.append({"title": title, "url": url, "description": desc})
    return results


async def _web_search_brave(query: str, count: int, api_key: str, search_type: str = "web") -> str:
    """Search using Brave Search API. search_type: web (default), news, video, image. Free tier: $5 monthly credits."""
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required for web_search. pip install httpx", "results": []})
    st = (search_type or "web").strip().lower()
    if st not in ("web", "news", "video", "image"):
        st = "web"
    count = min(max(1, count), 20) if st == "web" else min(max(1, count), 50)
    if st == "image":
        count = min(count, 20)
    url = _brave_search_type_endpoint(st)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                params={"q": query, "count": count},
                headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            )
            if resp.status_code != 200:
                msg = _web_search_error_user_message("brave", resp.status_code, resp.text, resp.reason_phrase)
                return json.dumps({"error": msg, "results": []})
            data = resp.json()
    except httpx.TimeoutException:
        return json.dumps({"error": "Brave search timed out. Try again later.", "results": []})
    except Exception as e:
        return json.dumps({"error": f"Brave search failed: {e!s}. Set BRAVE_API_KEY (free tier available) or use provider tavily with TAVILY_API_KEY.", "results": []})
    results = _brave_parse_results(data, st, count)
    return json.dumps({"results": results, "provider": "brave", "search_type": st})


def _web_search_duckduckgo_sync(query: str, count: int) -> List[Dict[str, Any]]:
    """Run DuckDuckGo text search (no API key). Returns list of {title, url, description}. Raises or returns [] on failure."""
    try:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            from ddgs import DDGS
    except ImportError:
        return []
    try:
        gen = DDGS().text(query, max_results=min(max(1, count), 10))
        raw = list(gen)[:count]
        results = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            title = r.get("title") or r.get("text") or ""
            url = r.get("href") or r.get("url") or ""
            body = r.get("body") or r.get("description") or r.get("snippet") or ""
            results.append({"title": title, "url": url, "description": body})
        return results
    except Exception:
        return []


async def _web_search_duckduckgo(query: str, count: int) -> str:
    """DuckDuckGo search fallback (no API key). Returns same JSON shape as Tavily/Brave. Use when primary provider is unconfigured or fails."""
    count = min(max(1, count), 10)
    try:
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _web_search_duckduckgo_sync(query, count)),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "DuckDuckGo fallback timed out.", "results": [], "provider": "duckduckgo"})
    except Exception as e:
        return json.dumps({"error": f"DuckDuckGo fallback failed: {e!s}", "results": [], "provider": "duckduckgo"})
    if not results:
        return json.dumps({
            "error": "DuckDuckGo returned no results. Install fallback: pip install duckduckgo-search",
            "results": [],
            "provider": "duckduckgo",
        })
    return json.dumps({"results": results, "provider": "duckduckgo"})


async def _web_search_google_cse(query: str, count: int, api_key: str, cx: str) -> str:
    """Search using Google Custom Search JSON API. Free tier: 100 queries/day. Needs API key + Search Engine ID (cx)."""
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required. pip install httpx", "results": []})
    if not cx or not cx.strip():
        return json.dumps({"error": "Google CSE requires Search Engine ID (cx). Create one at https://programmablesearchengine.google.com/", "results": []})
    count = min(max(1, count), 10)  # API max 10 per request
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://customsearch.googleapis.com/customsearch/v1",
                params={"key": api_key, "cx": cx.strip(), "q": query, "num": count},
            )
            if resp.status_code != 200:
                err = resp.text[:300]
                try:
                    j = resp.json()
                    err = j.get("error", {}).get("message", err)
                except Exception:
                    pass
                return json.dumps({"error": f"Google CSE {resp.status_code}: {err}", "results": []})
            data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"Google CSE failed: {e!s}", "results": []})
    results = []
    for r in (data.get("items") or [])[:count]:
        if not isinstance(r, dict):
            continue
        results.append({
            "title": r.get("title") or "",
            "url": r.get("link") or "",
            "description": r.get("snippet") or "",
        })
    return json.dumps({"results": results, "provider": "google_cse"})


async def _web_search_bing(query: str, count: int, api_key: str) -> str:
    """Search using Bing Web Search API v7. Free tier: 1000 transactions/month. Note: Bing Search APIs retiring Aug 2025."""
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required. pip install httpx", "results": []})
    count = min(max(1, count), 50)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.bing.microsoft.com/v7.0/search",
                params={"q": query, "count": count},
                headers={"Ocp-Apim-Subscription-Key": api_key},
            )
            if resp.status_code != 200:
                err = resp.text[:300]
                try:
                    j = resp.json()
                    err = j.get("error", {}).get("message", err)
                except Exception:
                    pass
                return json.dumps({"error": f"Bing Search {resp.status_code}: {err}", "results": []})
            data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"Bing Search failed: {e!s}", "results": []})
    results = []
    for r in (data.get("webPages") or {}).get("value") or []:
        if not isinstance(r, dict):
            continue
        results.append({
            "title": r.get("name") or "",
            "url": r.get("url") or "",
            "description": r.get("snippet") or "",
        })
    return json.dumps({"results": results[:count], "provider": "bing"})


async def _web_search_serpapi(query: str, count: int, api_key: str, engine: str) -> str:
    """Search using SerpAPI (Google, Bing, Baidu). engine: google (default), bing, baidu. Paid; free tier ~250/mo."""
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required for web_search. pip install httpx", "results": []})
    eng = (engine or "google").strip().lower()
    if eng not in ("google", "bing", "baidu"):
        eng = "google"
    count = min(max(1, count), 20)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={"q": query, "engine": eng, "api_key": api_key, "num": count},
            )
            if resp.status_code != 200:
                return json.dumps({"error": f"SerpAPI {resp.status_code}: {resp.text[:200]}", "results": []})
            data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"SerpAPI failed: {e!s}", "results": []})
    results = []
    # SerpAPI: organic_results (Google/Bing), or organic_results / results (Baidu)
    for r in (data.get("organic_results") or data.get("results") or [])[:count]:
        if not isinstance(r, dict):
            continue
        results.append({
            "title": r.get("title") or r.get("name") or "",
            "url": r.get("link") or r.get("url") or "",
            "description": r.get("snippet") or r.get("description") or "",
        })
    return json.dumps({"results": results, "provider": "serpapi", "engine": eng})


async def _web_search_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Search the web. Free (no key): duckduckgo. Free tier: tavily, google_cse (100/day), bing (1000/mo). Paid: brave, serpapi. Fallback: DuckDuckGo when no key."""
    config = _get_tools_config()
    web_config = config.get("web") or {}
    search_config = web_config.get("search") or {}
    use_fallback = search_config.get("fallback_no_key", True)
    fallback_max = max(1, min(10, int(search_config.get("fallback_max_results") or 5)))
    provider = (search_config.get("provider") or "tavily").strip().lower()
    if provider not in ("brave", "tavily", "serpapi", "duckduckgo", "google_cse", "bing"):
        provider = "tavily"
    query = (arguments.get("query") or "").strip()
    if not query:
        return "Error: query is required"
    count = int(arguments.get("count", 5))
    count = min(max(1, count), 20)

    async def _try_fallback() -> str:
        if not use_fallback:
            return ""
        fallback_result = await _web_search_duckduckgo(query, fallback_max)
        try:
            data = json.loads(fallback_result)
            if data.get("results"):
                return fallback_result
        except Exception:
            pass
        return ""

    if provider == "duckduckgo":
        result = await _web_search_duckduckgo(query, min(count, 10))
        try:
            data = json.loads(result)
            if data.get("error") and not data.get("results"):
                return result
        except Exception:
            pass
        return result
    if provider == "google_cse":
        api_key = (os.environ.get("GOOGLE_CSE_API_KEY") or "").strip()
        if not api_key:
            api_key = (search_config.get("google_cse") or {}).get("api_key") or ""
        api_key = (api_key or "").strip() if isinstance(api_key, str) else api_key
        cx = (os.environ.get("GOOGLE_CSE_CX") or "").strip()
        if not cx:
            cx = (search_config.get("google_cse") or {}).get("cx") or ""
        cx = (cx or "").strip() if isinstance(cx, str) else cx
        if not api_key or not cx:
            out = await _try_fallback()
            if out:
                return out
            return json.dumps({
                "error": "Google CSE not configured. Set GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX (Search Engine ID from https://programmablesearchengine.google.com/). Free: 100 queries/day.",
                "results": [],
            })
        result = await _web_search_google_cse(query, count, api_key, cx)
        try:
            data = json.loads(result)
            if data.get("error") and not data.get("results") and use_fallback:
                out = await _try_fallback()
                if out:
                    return out
        except Exception:
            pass
        return result
    if provider == "bing":
        api_key = (os.environ.get("BING_SEARCH_SUBSCRIPTION_KEY") or os.environ.get("BING_API_KEY") or "").strip()
        if not api_key:
            api_key = (search_config.get("bing") or {}).get("api_key") or ""
        api_key = (api_key or "").strip() if isinstance(api_key, str) else api_key
        if not api_key:
            out = await _try_fallback()
            if out:
                return out
            return json.dumps({
                "error": "Bing Search not configured. Set BING_SEARCH_SUBSCRIPTION_KEY (Azure). Free tier: 1000 transactions/month. Note: Bing Search APIs retiring Aug 2025.",
                "results": [],
            })
        result = await _web_search_bing(query, count, api_key)
        try:
            data = json.loads(result)
            if data.get("error") and not data.get("results") and use_fallback:
                out = await _try_fallback()
                if out:
                    return out
        except Exception:
            pass
        return result
    if provider == "tavily":
        api_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
        if not api_key:
            api_key = (search_config.get("tavily") or {}).get("api_key") or search_config.get("api_key")
        api_key = (api_key or "").strip() if isinstance(api_key, str) else api_key
        if not api_key:
            out = await _try_fallback()
            if out:
                return out
            return json.dumps({
                "error": (
                    "Web search (Tavily) is not configured: no API key. Tell the user exactly: "
                    "To enable web search, set TAVILY_API_KEY in the environment where Core runs, "
                    "or put your key in config/core.yml under tools.web.search.tavily.api_key. "
                    "Free tier: 1000 searches/month at https://tavily.com. Do not refuse the user request; report this setup step only."
                ),
                "results": [],
            })
        result = await _web_search_tavily(query, count, api_key, search_config.get("tavily") or {})
        try:
            data = json.loads(result)
            if data.get("error") and not data.get("results") and use_fallback:
                out = await _try_fallback()
                if out:
                    return out
        except Exception:
            pass
        return result
    if provider == "serpapi":
        api_key = (os.environ.get("SERPAPI_API_KEY") or "").strip()
        if not api_key:
            api_key = (search_config.get("serpapi") or {}).get("api_key") or search_config.get("api_key")
        api_key = (api_key or "").strip() if isinstance(api_key, str) else api_key
        engine = (arguments.get("engine") or "").strip().lower() or (search_config.get("serpapi") or {}).get("engine") or "google"
        if not api_key:
            out = await _try_fallback()
            if out:
                return out
            return json.dumps({
                "error": "SerpAPI key not set. Set SERPAPI_API_KEY or tools.web.search.serpapi.api_key. Engine: google (default), bing, baidu. Free tier ~250/mo at https://serpapi.com.",
                "results": [],
            })
        result = await _web_search_serpapi(query, count, api_key, engine)
        try:
            data = json.loads(result)
            if data.get("error") and not data.get("results") and use_fallback:
                out = await _try_fallback()
                if out:
                    return out
        except Exception:
            pass
        return result
    brave_cfg = search_config.get("brave") or {}
    api_key = (os.environ.get("BRAVE_API_KEY") or "").strip() or brave_cfg.get("api_key") or (search_config.get("api_key") or "").strip()
    search_type = (arguments.get("search_type") or "").strip().lower() or (brave_cfg.get("search_type") or "web").strip().lower()
    if search_type not in ("web", "news", "video", "image"):
        search_type = "web"
    if not api_key:
        out = await _try_fallback()
        if out:
            return out
        return json.dumps({
            "error": "Brave API key not set. Set BRAVE_API_KEY or tools.web.search.brave.api_key. search_type: web (default), news, video, image. Free tier: $5/mo at https://brave.com/search/api.",
            "results": [],
        })
    result = await _web_search_brave(query, count, api_key, search_type)
    try:
        data = json.loads(result)
        if data.get("error") and not data.get("results") and use_fallback:
            out = await _try_fallback()
            if out:
                return out
    except Exception:
        pass
    return result


def _get_tavily_api_key() -> str:
    """Return Tavily API key from env or config (tools.web.search.tavily.api_key). Empty if not set."""
    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        config = _get_tools_config()
        tavily = (config.get("web") or {}).get("search") or {}
        tavily = (tavily.get("tavily") or {}) if isinstance(tavily, dict) else {}
        key = (tavily.get("api_key") or "").strip()
        if isinstance(key, str):
            key = key.strip()
        else:
            key = ""
    return key or ""


async def _tavily_extract_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Extract content from one or more URLs using Tavily Extract API. Requires TAVILY_API_KEY or tools.web.search.tavily.api_key."""
    api_key = _get_tavily_api_key()
    if not api_key:
        return json.dumps({
            "error": "Tavily API key not set. Set TAVILY_API_KEY or config tools.web.search.tavily.api_key to use tavily_extract.",
            "results": [],
        })
    urls_arg = arguments.get("urls")
    if urls_arg is None:
        urls_arg = arguments.get("url") or ""
    if isinstance(urls_arg, str):
        urls_arg = [u.strip() for u in urls_arg.split() if u.strip()] if urls_arg.strip() else []
    if not urls_arg:
        return "Error: urls is required (comma/space-separated list or single url)."
    urls = urls_arg[:20]
    query = (arguments.get("query") or "").strip() or None
    extract_depth = (arguments.get("extract_depth") or "basic").strip().lower()
    if extract_depth not in ("basic", "advanced"):
        extract_depth = "basic"
    fmt = (arguments.get("format") or "markdown").strip().lower()
    if fmt not in ("markdown", "text"):
        fmt = "markdown"
    chunks_per_source = arguments.get("chunks_per_source")
    if chunks_per_source is not None:
        chunks_per_source = max(1, min(5, int(chunks_per_source)))
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required for tavily_extract. pip install httpx", "results": []})
    body = {"urls": urls[0] if len(urls) == 1 else urls, "extract_depth": extract_depth, "format": fmt}
    if query:
        body["query"] = query
        if chunks_per_source is not None:
            body["chunks_per_source"] = chunks_per_source
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.tavily.com/extract",
                json=body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                err = resp.text
                try:
                    data = resp.json()
                    err = (data.get("detail") or data)
                    if isinstance(err, dict):
                        err = err.get("error", str(err))
                except Exception:
                    pass
                return json.dumps({"error": f"Tavily Extract: {resp.status_code} — {err}", "results": []})
            return resp.text
    except Exception as e:
        return json.dumps({"error": str(e), "results": []})


async def _tavily_crawl_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Crawl a website from a base URL using Tavily Crawl API. Requires TAVILY_API_KEY or tools.web.search.tavily.api_key."""
    api_key = _get_tavily_api_key()
    if not api_key:
        return json.dumps({
            "error": "Tavily API key not set. Set TAVILY_API_KEY or config tools.web.search.tavily.api_key to use tavily_crawl.",
            "results": [],
        })
    url = (arguments.get("url") or "").strip()
    if not url:
        return "Error: url is required (root URL to start the crawl)."
    instructions = (arguments.get("instructions") or "").strip() or None
    max_depth = arguments.get("max_depth")
    max_depth = max(1, min(5, int(max_depth))) if max_depth is not None else 1
    max_breadth = arguments.get("max_breadth")
    max_breadth = max(1, min(500, int(max_breadth))) if max_breadth is not None else 20
    limit = arguments.get("limit")
    limit = max(1, int(limit)) if limit is not None else 50
    extract_depth = (arguments.get("extract_depth") or "basic").strip().lower()
    if extract_depth not in ("basic", "advanced"):
        extract_depth = "basic"
    fmt = (arguments.get("format") or "markdown").strip().lower()
    if fmt not in ("markdown", "text"):
        fmt = "markdown"
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required for tavily_crawl. pip install httpx", "results": []})
    body = {
        "url": url,
        "max_depth": max_depth,
        "max_breadth": max_breadth,
        "limit": limit,
        "extract_depth": extract_depth,
        "format": fmt,
    }
    if instructions:
        body["instructions"] = instructions
    try:
        async with httpx.AsyncClient(timeout=150.0) as client:
            resp = await client.post(
                "https://api.tavily.com/crawl",
                json=body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                err = resp.text
                try:
                    data = resp.json()
                    err = (data.get("detail") or data)
                    if isinstance(err, dict):
                        err = err.get("error", str(err))
                except Exception:
                    pass
                return json.dumps({"error": f"Tavily Crawl: {resp.status_code} — {err}", "results": []})
            return resp.text
    except Exception as e:
        return json.dumps({"error": str(e), "results": []})


async def _tavily_research_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Run a Tavily Research task (async: create then poll until done). Returns report content and sources. Requires TAVILY_API_KEY or tools.web.search.tavily.api_key."""
    api_key = _get_tavily_api_key()
    if not api_key:
        return json.dumps({
            "error": "Tavily API key not set. Set TAVILY_API_KEY or config tools.web.search.tavily.api_key to use tavily_research.",
            "content": "",
            "sources": [],
        })
    input_q = (arguments.get("input") or arguments.get("query") or arguments.get("question") or "").strip()
    if not input_q:
        return "Error: input (or query/question) is required — the research question or topic."
    model = (arguments.get("model") or "auto").strip().lower()
    if model not in ("mini", "pro", "auto"):
        model = "auto"
    max_wait = max(30, min(600, int(arguments.get("max_wait_seconds") or 120)))
    poll_interval = max(2, min(15, int(arguments.get("poll_interval_seconds") or 5)))
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required for tavily_research. pip install httpx", "content": "", "sources": []})
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.tavily.com/research",
                json={"input": input_q, "model": model},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            if resp.status_code not in (200, 201):
                err = resp.text
                try:
                    data = resp.json()
                    err = (data.get("detail") or data)
                    if isinstance(err, dict):
                        err = err.get("error", str(err))
                except Exception:
                    pass
                return json.dumps({"error": f"Tavily Research: {resp.status_code} — {err}", "content": "", "sources": []})
            data = resp.json()
            request_id = (data.get("request_id") or "").strip()
            if not request_id:
                return json.dumps({"error": "Tavily Research did not return request_id", "content": "", "sources": []})
    except Exception as e:
        return json.dumps({"error": str(e), "content": "", "sources": []})

    elapsed = 0
    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                poll_resp = await client.get(
                    f"https://api.tavily.com/research/{request_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if poll_resp.status_code == 202:
                    continue
                if poll_resp.status_code != 200:
                    err = poll_resp.text
                    try:
                        d = poll_resp.json()
                        err = (d.get("detail") or d)
                        if isinstance(err, dict):
                            err = err.get("error", str(err))
                    except Exception:
                        pass
                    return json.dumps({"error": f"Tavily Research poll: {poll_resp.status_code} — {err}", "content": "", "sources": []})
                result = poll_resp.json()
                status = (result.get("status") or "").lower()
                if status == "failed":
                    return json.dumps({
                        "error": result.get("error") or "Research task failed",
                        "content": "",
                        "sources": result.get("sources") or [],
                    })
                content = result.get("content") or ""
                sources = result.get("sources") or []
                return json.dumps({"content": content, "sources": sources, "request_id": request_id})
        except Exception as e:
            return json.dumps({"error": str(e), "content": "", "sources": []})
    return json.dumps({
        "error": f"Tavily Research timed out after {max_wait}s. request_id={request_id}. Check status later via API.",
        "content": "",
        "sources": [],
        "request_id": request_id,
    })


async def _sessions_spawn_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Sub-agent run: one-off task with optional model selection by llm_name (ref) or capability (e.g. Chat). Returns the model reply."""
    core = context.core
    task = (arguments.get("task") or arguments.get("message") or arguments.get("text") or "").strip()
    if not task:
        return "Error: task is required (the question or instruction for the sub-agent run)."
    llm_name = (arguments.get("llm_name") or "").strip() or None
    capability = (arguments.get("capability") or "").strip() or None
    if not llm_name and capability:
        try:
            from base.util import Util
            llm_name = Util().get_llm_ref_by_capability(capability)
            if not llm_name:
                return json.dumps({"error": f"No model found with capability '{capability}'. Use models_list to see model_details.capabilities."})
        except Exception as e:
            return json.dumps({"error": str(e)})
    try:
        return await core.run_spawn(task=task, llm_name=llm_name)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _models_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List available model refs with capabilities (from config). Use ref as llm_name in sessions_spawn, or use capability (e.g. Chat) in sessions_spawn to select by capability."""
    try:
        from base.util import Util
        util = Util()
        refs = util.get_llms()
        main_llm = getattr(util.core_metadata, "main_llm", "") or ""
        model_details = []
        for m in (util.core_metadata.local_models or []):
            mid = m.get("id")
            if mid:
                model_details.append({
                    "ref": f"local_models/{mid}",
                    "alias": m.get("alias") or mid,
                    "capabilities": m.get("capabilities") or [],
                })
        for m in (util.core_metadata.cloud_models or []):
            mid = m.get("id")
            if mid:
                model_details.append({
                    "ref": f"cloud_models/{mid}",
                    "alias": m.get("alias") or mid,
                    "capabilities": m.get("capabilities") or [],
                })
        if not model_details and refs:
            model_details = [{"ref": r, "alias": r, "capabilities": []} for r in refs]
        return json.dumps({
            "models": refs,
            "model_details": model_details,
            "main_llm": main_llm,
            "message": "For sessions_spawn: use llm_name (a ref from 'models') or capability (e.g. 'Chat') to select model. Omit both to use main_llm. capability selects a model that has that capability in config.",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e), "models": [], "model_details": [], "main_llm": ""})


async def _channel_send_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Send an additional message to the channel that last sent a request (same channel as current conversation). Enables multiple continuous messages to one channel."""
    core = context.core
    text = (arguments.get("text") or arguments.get("message") or "").strip()
    if not text:
        return "Error: text (or message) is required and must be non-empty."
    try:
        await core.send_response_to_latest_channel(response=text)
        return json.dumps({"status": "ok", "message": "Sent to last-used channel."})
    except Exception as e:
        return json.dumps({"error": str(e), "status": "failed"})


async def _agents_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List agent ids. HomeClaw runs a single Core; returns a note that only one agent is available."""
    return json.dumps({
        "agents": ["default"],
        "message": "HomeClaw runs a single agent (Core). Use sessions_spawn for a sub-agent one-off run (optional llm_name for a different model). Use models_list to see available llm_name values.",
    })


async def _image_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Analyze an image with the vision/multimodal model. Provide image as file path (relative to homeclaw_root) or URL, and an optional prompt."""
    import base64
    core = context.core
    path_arg = (arguments.get("path") or arguments.get("image") or "").strip()
    url_arg = (arguments.get("url") or "").strip()
    prompt = (arguments.get("prompt") or "Describe the image.").strip()
    if not path_arg and not url_arg:
        return "Error: path (or image) or url is required"
    mime = "image/jpeg"
    try:
        if url_arg:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url_arg)
                resp.raise_for_status()
                image_bytes = resp.content
                ct = resp.headers.get("content-type", "").split(";")[0].strip()
                if ct and ct.startswith("image/"):
                    mime = ct
        else:
            r = _resolve_file_path(path_arg, context, for_write=False)
            if r is None:
                return _file_resolve_error_msg()
            full, base = r
            used_request_image = False
            if not full.is_file():
                req_images = list(getattr(getattr(context, "request", None), "images", None) or [])
                for candidate in req_images:
                    if isinstance(candidate, str) and candidate.strip() and os.path.isfile(candidate.strip()):
                        full = Path(candidate.strip()).resolve()
                        used_request_image = True
                        break
                else:
                    if not _path_under(full, base):
                        return _FILE_ACCESS_DENIED_MSG
                    return _FILE_NOT_FOUND_MSG
            if not used_request_image and not _path_under(full, base):
                return _FILE_ACCESS_DENIED_MSG
            image_bytes = full.read_bytes()
            suffix = full.suffix.lower()
            if suffix in (".png",):
                mime = "image/png"
            elif suffix in (".gif",):
                mime = "image/gif"
            elif suffix in (".webp",):
                mime = "image/webp"
        if len(image_bytes) > 20 * 1024 * 1024:
            return "Error: image too large (max 20MB)"
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
    except Exception as e:
        return f"Error: {e!s}"
    result = await core.analyze_image(prompt=prompt, image_base64=image_base64, mime_type=mime)
    if result is None:
        return "Error: vision model did not return a response (check that your LLM supports multimodal/image input)."
    return result


async def _echo_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Echo back the given text. Useful for testing the tool layer."""
    return arguments.get("text", "")


async def _platform_info_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Return platform info: Python version, system (Darwin/Linux/Windows), machine."""
    return json.dumps({
        "python_version": sys.version.split()[0],
        "system": platform.system(),
        "machine": platform.machine(),
        "platform": platform.platform(),
    })


async def _cwd_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Return current working directory (path where the Core process is running)."""
    return str(Path.cwd())


async def _env_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Get the value of an environment variable. Read-only; only returns existing vars."""
    name = arguments.get("name", "").strip()
    if not name:
        return "Error: env var name is required"
    value = os.environ.get(name)
    if value is None:
        return f"Environment variable '{name}' is not set."
    return value


def _default_exec_allowlist() -> List[str]:
    """Return platform-appropriate default exec allowlist (Mac/Linux: ls, cat, pwd; Windows: dir, type, cd)."""
    if platform.system() == "Windows":
        return ["date", "whoami", "echo", "cd", "dir", "type", "where", "powershell"]
    return ["date", "whoami", "echo", "pwd", "ls", "cat", "which"]


# ---- Exec (cross-platform; allowlist for safety) ----
async def _exec_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Run a shell command. Only commands in the allowlist (config: tools.exec_allowlist) are allowed. Empty/missing = platform default (Unix: ls, cat, pwd; Windows: dir, type, cd). Set background=true to run in background and get a job_id; use process_poll/process_kill with that job_id."""
    config = _get_tools_config()
    allowlist: List[str] = config.get("exec_allowlist")
    if allowlist is None or (isinstance(allowlist, list) and len(allowlist) == 0):
        allowlist = _default_exec_allowlist()
    timeout = int(config.get("exec_timeout", 30))
    command = (arguments.get("command") or "").strip()
    background = arguments.get("background") is True
    if not command:
        return "Error: command is required"
    parts = command.split()
    if not parts:
        return "Error: command is required"
    executable = parts[0]
    args = parts[1:]
    if allowlist and executable not in allowlist:
        return f"Error: command '{executable}' is not in the allowlist. Allowed: {allowlist}"
    if background:
        try:
            job_id = await _start_background_process(executable, args, timeout)
            return json.dumps({"status": "running", "job_id": job_id, "command": command})
        except Exception as e:
            return f"Error: {e!s}"
    try:
        proc = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if err:
            out = out + "\nstderr:\n" + err if out else "stderr:\n" + err
        return out or "(no output)"
    except asyncio.TimeoutError:
        return f"Error: command timed out after {timeout}s"
    except FileNotFoundError:
        return f"Error: command not found: {executable}"
    except Exception as e:
        return f"Error: {e!s}"


def _attach_run_skill_image_path(script_output: str, context: ToolContext) -> None:
    """If script printed HOMECLAW_IMAGE_PATH=<path> or 'Image saved: <path>' (any skill/tool output that includes images), set request.request_metadata['response_image_paths'] and Core-level fallback so companion/channels get the image."""
    if not script_output or not context or not getattr(context, "request", None):
        return
    req = context.request
    meta = getattr(req, "request_metadata", None)
    if not isinstance(meta, dict):
        meta = None
    paths = []
    def _norm_path(p: str):
        p = p.strip().split("\n")[0].strip()
        if not p:
            return None
        try:
            resolved = Path(p).resolve()
            return str(resolved) if resolved.is_file() else None
        except (OSError, RuntimeError):
            return None
    # Primary: HOMECLAW_IMAGE_PATH=<path>
    for match in re.finditer(r"HOMECLAW_IMAGE_PATH=(.+)", script_output):
        path = _norm_path(match.group(1))
        if path:
            paths.append(path)
    # Fallback: "Image saved: <path>" (e.g. image-generation generate_image.py)
    if not paths:
        for match in re.finditer(r"Image saved:\s*(.+)", script_output, re.IGNORECASE):
            path = _norm_path(match.group(1))
            if path:
                paths.append(path)
                break
    if paths:
        if meta is not None:
            meta["response_image_paths"] = paths
        # Core-level fallback so /inbound can read even if request_metadata doesn't persist
        core = getattr(context, "core", None)
        req_id = getattr(req, "request_id", None)
        if core is not None and req_id:
            if not hasattr(core, "_response_image_paths_by_request_id"):
                core._response_image_paths_by_request_id = {}
            core._response_image_paths_by_request_id[req_id] = paths


async def _run_skill_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Run a script from a loaded skill's scripts/ folder. Supports Python (.py), Node.js (.js, .mjs, .cjs), shell (.sh). Skill name = folder name under skills_dir; script = filename or path relative to scripts/. Optional args as list of strings. Sandboxed: only scripts under <skill>/scripts/; optional allowlist in config. Skills without scripts/ are instruction-only: omit script and use the skill's instructions in your response."""
    try:
        from base.util import Util
    except ImportError:
        return "Error: Util not available"
    skill_name = (arguments.get("skill_name") or arguments.get("skill") or "").strip()
    script_arg = (arguments.get("script") or arguments.get("script_name") or "").strip()
    args_input = arguments.get("args")
    if not skill_name:
        return "Error: skill_name (or skill) is required"
    try:
        meta = Util().get_core_metadata()
        if meta is None:
            return "Error: Core config not available"
        skills_dir_str = str(getattr(meta, "skills_dir", None) or "config/skills").strip() or "config/skills"
        root = Path(Util().root_path())
        skills_base = get_skills_dir(skills_dir_str, root=root)
        resolved_folder = resolve_skill_folder_name(skills_base, skill_name)
        if resolved_folder is not None:
            skill_name = resolved_folder
        skill_folder = (skills_base / skill_name).resolve()
    except Exception as e:
        logger.debug("run_skill setup failed: %s", e)
        return f"Error: run_skill failed: {e!s}"
    if not skill_folder.is_dir():
        return f"Error: skill folder not found: {skill_name} (under {skills_base}). Try the exact folder name from Available skills (e.g. html-slides-1.0.0)."
    scripts_dir = (skill_folder / "scripts").resolve()
    if not scripts_dir.is_dir():
        if not script_arg:
            return (
                f"Instruction-only skill confirmed: {skill_name}. Do NOT reply with only this line. "
                "You MUST in this turn: (1) document_read(the file path the user asked about) to get the source text, (2) use that returned text to generate the full output (e.g. full HTML for slides), (3) call save_result_page(title=..., content=<the full HTML you just generated>, format='html') or file_write(path='output/...', content=<full HTML>). "
                "The content parameter must be the actual generated HTML/text—never empty. Then return the view link to the user."
            )
        return f"Error: skill has no scripts/ folder: {skill_name}. Use the skill's instructions in your response instead of run_skill."
    if not script_arg:
        return "Error: script (or script_name) is required for this skill; it has a scripts/ folder."
    # Normalize script path for cross-platform: accept both / and \ in script_arg
    script_parts = Path(script_arg).parts
    if not script_parts or any(p == ".." for p in script_parts):
        return "Error: script path must be under the skill's scripts/ directory"
    script_path = (scripts_dir.joinpath(*script_parts)).resolve()
    try:
        script_path.resolve().relative_to(scripts_dir)
    except ValueError:
        return "Error: script path must be under the skill's scripts/ directory"
    if not script_path.is_file():
        return f"Error: script not found: {script_arg} (under {skill_name}/scripts/)"
    config = _get_tools_config()
    allowlist = config.get("run_skill_allowlist")
    if allowlist and script_path.name not in allowlist:
        return f"Error: script '{script_path.name}' is not in run_skill_allowlist. Allowed: {allowlist}"
    timeout = int(config.get("run_skill_timeout", 60))
    # Resolve request output dir (user/companion output folder) when sandbox is active; pass to script via env so skills can save files there.
    skill_env = dict(os.environ)
    r_out = _resolve_file_path(FILE_OUTPUT_SUBDIR, context, for_write=True)
    if r_out:
        full_out, base_for_validation = r_out
        if base_for_validation is not None:
            skill_env["HOMECLAW_OUTPUT_DIR"] = str(full_out)
    # Keyed skills: inject per-user API keys from user.yml, or use skill config/env when Companion without user.
    try:
        keyed_overrides, keyed_error = _get_keyed_skill_env_overrides(skill_name, context)
    except Exception:
        keyed_overrides, keyed_error = None, "Could not load user config for this skill."
    if keyed_error:
        return keyed_error
    if isinstance(keyed_overrides, dict) and keyed_overrides:
        skill_env.update(keyed_overrides)
    args_list: List[str] = []
    if args_input is not None:
        if isinstance(args_input, list):
            args_list = [str(x) for x in args_input]
            # LLMs sometimes return one mangled string (e.g. '--prompt", "boat..."," --filename=...'); normalize so argparse gets proper argv
            if len(args_list) == 1 and '","' in args_list[0]:
                raw = args_list[0]
                parts = [p.strip() for p in raw.split('","')]
                if len(parts) == 2 and parts[0].startswith("--prompt") and ("--filename" in parts[1] or "=" in parts[1]):
                    # First segment like '--prompt", "boat on ocean at sunset"'; second like ' --filename=generated.png'
                    first = parts[0]
                    rest = parts[1].strip().lstrip('"')
                    if '", "' in first:
                        a, b = first.split('", "', 1)
                        args_list = [a.strip(), b.rstrip('"').strip(), rest]
                    else:
                        args_list = [first.strip('"'), rest]
                    # Ensure --filename is separate if it was --filename=value
                    normalized: List[str] = []
                    for p in args_list:
                        if p.startswith("--filename="):
                            normalized.append("--filename")
                            normalized.append(p.split("=", 1)[1].strip())
                        else:
                            normalized.append(p)
                    args_list = [x for x in normalized if x]
                else:
                    parts = [p.strip().strip('"').strip() for p in parts]
                    args_list = [p for p in parts if p]
        elif isinstance(args_input, str):
            args_list = [x.strip() for x in args_input.split() if x.strip()]
    try:
        if script_path.suffix.lower() in (".py", ".pyw"):
            # Default: subprocess (isolated, never break Core). In-process only when skill folder name is in run_skill_py_in_process_skills.
            in_process_list = config.get("run_skill_py_in_process_skills")
            in_process = isinstance(in_process_list, list) and (skill_name in in_process_list)
            logger.info("run_skill: .py script %s ; in_process=%s (skill=%s)", script_path.name, in_process, skill_name)
            print("run_skill: .py script %s ; in_process=%s (skill=%s)" % (script_path.name, in_process, skill_name), file=sys.stderr, flush=True)
            # Run .py in Core's process (same env, no subprocess) when True
            if in_process:
                logger.info("run_skill: executing Python script in-process (Core Python: %s)", sys.executable)
                loop = asyncio.get_event_loop()
                env_for_process = keyed_overrides if isinstance(keyed_overrides, dict) else {}
                out_str, err_str = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        _run_py_script_in_process,
                        script_path,
                        args_list,
                        skill_folder,
                        env_for_process,
                    ),
                    timeout=timeout,
                )
                out = (out_str or "").strip()
                err = (err_str or "").strip()
                if err:
                    out = out + "\nstderr:\n" + err if out else "stderr:\n" + err
                # In-process failed with ModuleNotFoundError => Core's process does not have that package
                if "ModuleNotFoundError" in err:
                    out = (out or "") + (
                        f"\n\n[In-process run: script ran in Core's process. Core's Python is: {sys.executable} "
                        f"- install missing package there, e.g. pip install requests pillow]"
                    )
                # Convention: script prints HOMECLAW_IMAGE_PATH=<path> so Core/channels can send image to companion/channel
                _attach_run_skill_image_path(out, context)
                return out or "(no output)"
            # Default: subprocess with same Python and env as Core
            python_exe = sys.executable
            logger.info("run_skill: executing Python script with: {} (same as Core)", python_exe)
            proc = await asyncio.create_subprocess_exec(
                python_exe,
                str(script_path),
                *args_list,
                cwd=str(skill_folder),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=skill_env,
            )
        elif script_path.suffix.lower() in (".js", ".mjs", ".cjs"):
            node_path = shutil.which("node")
            if not node_path:
                return "Error: Node.js script requires 'node' in PATH. Install Node.js (https://nodejs.org) or use a Python/shell script."
            proc = await asyncio.create_subprocess_exec(
                node_path,
                str(script_path),
                *args_list,
                cwd=str(skill_folder),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=skill_env,
            )
        elif script_path.suffix.lower() in (".sh", ".bash") and platform.system() == "Windows":
            # On Windows, .sh/.bash need a shell: try bash (Git Bash) or wsl
            bash_path = shutil.which("bash")
            if bash_path:
                proc = await asyncio.create_subprocess_exec(
                    bash_path,
                    str(script_path),
                    *args_list,
                    cwd=str(skill_folder),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=skill_env,
                )
            else:
                wsl_path = shutil.which("wsl")
                if wsl_path:
                    proc = await asyncio.create_subprocess_exec(
                        wsl_path,
                        "bash",
                        str(script_path),
                        *args_list,
                        cwd=str(skill_folder),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=skill_env,
                    )
                else:
                    return "Error: .sh script on Windows requires bash (e.g. Git Bash) or WSL. Install Git for Windows or WSL, or use a .py/.bat script."
        else:
            proc = await asyncio.create_subprocess_exec(
                str(script_path),
                *args_list,
                cwd=str(skill_folder),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=skill_env,
            )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if err:
            out = out + "\nstderr:\n" + err if out else "stderr:\n" + err
        # If .py script failed with ModuleNotFoundError, optionally try auto-install and retry once
        if script_path.suffix.lower() in (".py", ".pyw") and "ModuleNotFoundError" in err:
            auto_install = config.get("run_skill_auto_install_missing") or {}
            if isinstance(auto_install, dict):
                match = re.search(r"No module named ['\"]([^'\"]+)['\"]", err)
                module_name = match.group(1) if match else None
                pip_pkgs = (auto_install.get(module_name) or auto_install.get("google")) if module_name else None
                if pip_pkgs:
                    try:
                        proc_pip = await asyncio.create_subprocess_exec(
                            sys.executable, "-m", "pip", "install", *pip_pkgs.split(),
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            env=skill_env,
                        )
                        await asyncio.wait_for(proc_pip.communicate(), timeout=120)
                        # Retry script once after install
                        proc2 = await asyncio.create_subprocess_exec(
                            sys.executable, str(script_path), *args_list,
                            cwd=str(skill_folder),
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            env=skill_env,
                        )
                        stdout2, stderr2 = await asyncio.wait_for(proc2.communicate(), timeout=timeout)
                        out = stdout2.decode("utf-8", errors="replace").strip()
                        err2 = stderr2.decode("utf-8", errors="replace").strip()
                        if err2:
                            out = out + "\nstderr:\n" + err2 if out else "stderr:\n" + err2
                    except Exception as e:
                        out = (out or "") + f"\n\n[Auto-install retry failed: {e}]"
            if "ModuleNotFoundError" in (out or ""):
                out = (out or "") + f"\n\n[Fix] Install in Core's Python: {sys.executable} -m pip install <missing-package>"
        # Convention: script prints HOMECLAW_IMAGE_PATH=<path> so Core/channels can send image to companion/channel
        _attach_run_skill_image_path(out, context)
        return out or "(no output)"
    except asyncio.TimeoutError:
        return f"Error: script timed out after {timeout}s"
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        logger.debug("run_skill failed: %s", e)
        return f"Error: {e!s}"


async def _process_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List background exec jobs (job_id, command, started_at, status: running|done)."""
    async with _process_jobs_lock:
        jobs = []
        for jid, j in list(_process_jobs.items()):
            proc = j.get("proc")
            rc = proc.returncode if proc and hasattr(proc, "returncode") else None
            status = "done" if rc is not None else "running"
            jobs.append({
                "job_id": jid,
                "command": j.get("command", ""),
                "started_at": j.get("started_at", ""),
                "status": status,
                "returncode": rc,
            })
    return json.dumps({"jobs": jobs})


async def _process_poll_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Poll a background job: return stdout, stderr, returncode when done; status running otherwise. Use job_id from exec(background=true) or process_list."""
    job_id = (arguments.get("job_id") or "").strip()
    if not job_id:
        return "Error: job_id is required"
    async with _process_jobs_lock:
        j = _process_jobs.get(job_id)
        if not j:
            return json.dumps({"error": "job not found", "job_id": job_id})
        proc = j.get("proc")
        rc = proc.returncode if proc else None
        if rc is not None:
            out = (j.get("stdout") or "").strip()
            err = (j.get("stderr") or "").strip()
            if err:
                out = out + "\nstderr:\n" + err if out else "stderr:\n" + err
            return json.dumps({"status": "done", "returncode": rc, "output": out or "(no output)"})
        return json.dumps({"status": "running", "job_id": job_id})


async def _process_kill_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Kill a background job by job_id."""
    job_id = (arguments.get("job_id") or "").strip()
    if not job_id:
        return "Error: job_id is required"
    async with _process_jobs_lock:
        j = _process_jobs.get(job_id)
        if not j:
            return json.dumps({"killed": False, "error": "job not found", "job_id": job_id})
        proc = j.get("proc")
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        # leave in dict so poll can see returncode
    return json.dumps({"killed": True, "job_id": job_id})


# ---- File read (cross-platform; restricted to base path) ----
async def _file_read_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Read a file. When homeclaw_root is set: use 'share/...' for shared folder, or a path for your user or companion folder. When not set, absolute paths allowed."""
    path_arg = (arguments.get("path") or "").strip()
    if not path_arg:
        return "Path is required."
    try:
        r = _resolve_file_path(path_arg, context, for_write=False)
        if r is None:
            return _file_resolve_error_msg()
        full, base = r
        if not _path_under(full, base):
            return _FILE_ACCESS_DENIED_MSG
        config = _get_tools_config()
        if not full.is_file():
            return _FILE_NOT_FOUND_MSG
        content = full.read_text(encoding="utf-8", errors="replace")
        default_max = int(config.get("file_read_max_chars") or 0) or 32_000
        max_chars = int(arguments.get("max_chars", 0)) or default_max
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... (truncated; increase max_chars or ask for section-by-section summary)"
        return content
    except Exception as e:
        logger.debug("file_read failed: %s", e)
        return _FILE_NOT_FOUND_MSG


# Document types supported by Unstructured (one powerful tool for PDF, PPT, Word, MD, HTML, XML, JSON, etc.)
_DOCUMENT_EXTENSIONS_UNSTRUCTURED = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".html", ".htm", ".md", ".mdx", ".xml", ".json", ".xlsx", ".xls", ".csv", ".eml", ".msg", ".epub", ".rst", ".txt"}


def _extract_with_unstructured(full_path: Path, max_chars: int) -> str:
    """Extract text using Unstructured (PDF, PPT, Word, MD, HTML, XML, JSON, etc.). Returns text or raises ImportError."""
    from unstructured.partition.auto import partition
    elements = partition(filename=str(full_path))
    parts = []
    total = 0
    for el in elements:
        text = (getattr(el, "text", None) or "").strip()
        if not text:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(text) > remaining:
            parts.append(text[:remaining])
            total = max_chars
            break
        parts.append(text)
        total += len(text)
    out = "\n\n".join(parts) if parts else "(no text extracted)"
    if total >= max_chars:
        out += "\n... (truncated; increase max_chars or ask for section-by-section summary)"
    return out


def _extract_pdf_text(full_path: Path, max_chars: int) -> str:
    """Extract text from PDF using pypdf if available. Returns text or raises ImportError."""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            raise ImportError("PDF support requires: pip install pypdf (or PyPDF2)")
    reader = PdfReader(str(full_path))
    parts = []
    total = 0
    truncated = False
    for page in reader.pages:
        if total >= max_chars:
            truncated = True
            break
        text = (page.extract_text() or "").strip()
        if text:
            remaining = max_chars - total
            if len(text) > remaining:
                parts.append(text[:remaining])
                total = max_chars
                truncated = True
                break
            parts.append(text)
            total += len(text)
    out = "\n\n".join(parts) if parts else "(no text extracted)"
    if truncated:
        out += "\n... (truncated; increase max_chars or ask for section-by-section summary)"
    return out


def _document_read_plain_text(full_path: Path, max_chars: int, suffix: str) -> str:
    """Read as plain text (UTF-8). For JSON/XML, return as-is (readable)."""
    content = full_path.read_text(encoding="utf-8", errors="replace")
    if len(content) > max_chars:
        content = content[:max_chars] + "\n... (truncated; increase max_chars or ask for section-by-section summary)"
    return content


async def _document_read_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Read document content: PDF, PPT, Word, MD, HTML, XML, JSON, etc. Use 'share/...' or path in your user or companion folder. When base not set, absolute paths allowed."""
    config = _get_tools_config()
    path_arg = (arguments.get("path") or "").strip()
    if not path_arg:
        return "Path is required."
    default_max = int(config.get("file_read_max_chars") or 0) or 64_000
    max_chars = int(arguments.get("max_chars", 0)) or default_max
    try:
        r = _resolve_file_path(path_arg, context, for_write=False)
        if r is None:
            return _file_resolve_error_msg()
        full, base = r
        if not _path_under(full, base):
            return _FILE_ACCESS_DENIED_MSG
        if not full.is_file():
            return _FILE_NOT_FOUND_MSG
        suffix = full.suffix.lower()

        # 1) Try Unstructured first for supported types (one powerful tool for all)
        if suffix in _DOCUMENT_EXTENSIONS_UNSTRUCTURED:
            try:
                content = _extract_with_unstructured(full, max_chars)
                return content
            except ImportError:
                pass  # Fall back to pypdf or plain text
            except Exception as e:
                return f"Error extracting with Unstructured: {e!s}. Try: pip install 'unstructured[all-docs]'"

        # 2) PDF without Unstructured: use pypdf
        if suffix == ".pdf":
            try:
                content = _extract_pdf_text(full, max_chars)
                return content
            except ImportError as e:
                return (
                    f"Error: {e!s} For PDF + PPT/Word/HTML/MD/XML/JSON support install one powerful tool: "
                    "pip install 'unstructured[all-docs]' (or at least: pip install pypdf for PDF only)."
                )

        # 3) Office/docs without Unstructured: suggest install
        if suffix in {".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls", ".epub", ".eml", ".msg"}:
            return (
                "Error: Support for this format requires the Unstructured library. "
                "Install for full document support: pip install 'unstructured[all-docs]'. "
                "See https://unstructured.io/"
            )

        # 4) Plain text fallback (md, html, xml, json, csv, txt, etc.)
        return _document_read_plain_text(full, max_chars, suffix)
    except Exception as e:
        logger.debug("document_read failed: %s", e)
        return _FILE_NOT_FOUND_MSG


async def _file_understand_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Classify a file (image, audio, video, document) and for documents return extracted text. Reuses file-understanding; never raises."""
    try:
        from base.file_understanding import (
            FILE_TYPE_IMAGE,
            FILE_TYPE_AUDIO,
            FILE_TYPE_VIDEO,
            FILE_TYPE_DOCUMENT,
            FILE_TYPE_UNKNOWN,
            detect_file_type,
            extract_document_text,
        )
        try:
            config = _get_tools_config() or {}
        except Exception:
            config = {}
        path_arg = (arguments.get("path") or "").strip()
        if not path_arg:
            return "Error: path is required."
        try:
            default_max = int(config.get("file_read_max_chars") or 0) or 64_000
        except (TypeError, ValueError):
            default_max = 64_000
        try:
            max_chars = int(arguments.get("max_chars") or 0) or default_max
        except (TypeError, ValueError):
            max_chars = default_max
        r = _resolve_file_path(path_arg, context, for_write=False)
        if r is None:
            return _file_resolve_error_msg()
        full, base = r
        if not _path_under(full, base):
            return _FILE_ACCESS_DENIED_MSG
        if not full.is_file():
            return _FILE_NOT_FOUND_MSG
        base_str = str(full.parent)
        path_str = str(full)
        ftype = detect_file_type(path_str)
        if ftype == FILE_TYPE_DOCUMENT:
            text = extract_document_text(path_str, base_str, max_chars)
            if text:
                return f"type: document\npath: {path_arg}\n\nExtracted text:\n\n{text}"
            return f"type: document\npath: {path_arg}\n\nError: could not extract text from this document."
        if ftype == FILE_TYPE_IMAGE:
            return f"type: image\npath: {path_arg}\n\nThis is an image file. Use image_analyze(path) to describe or answer questions about the image if the user asks."
        if ftype == FILE_TYPE_AUDIO:
            return f"type: audio\npath: {path_arg}\n\nThis is an audio file. The model may support audio input; otherwise describe that you detected audio at this path."
        if ftype == FILE_TYPE_VIDEO:
            return f"type: video\npath: {path_arg}\n\nThis is a video file. The model may support video input; otherwise describe that you detected video at this path."
        return f"type: unknown\npath: {path_arg}\n\nFile type could not be determined. Use file_read(path) for raw content or document_read(path) if it might be a document."
    except ImportError as e:
        logger.debug("file_understand import failed: {}", e)
        return f"Error: file_understand is not available: {e!s}"
    except Exception as e:
        logger.debug("file_understand failed: {}", e)
        return f"Error: {e!s}"


# ---- Knowledge base tools (only when core.knowledge_base is enabled) ----
async def _knowledge_base_search_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Search the user's knowledge base (saved documents, web, URLs). Never raises; returns message on failure."""
    try:
        core = getattr(context, "core", None)
        kb = getattr(core, "knowledge_base", None) if core else None
        if not kb:
            return "Knowledge base is not available (disabled or not configured)."
        user_id = (getattr(context, "user_id", None) or getattr(context, "user_name", None) or "").strip()
        if not user_id:
            return "No user context; cannot search knowledge base."
        query = (arguments.get("query") or "").strip()
        if not query:
            return "Please provide a search query."
        limit = max(1, min(20, int(arguments.get("limit", 5) or 5)))
        results = await asyncio.wait_for(kb.search(user_id=user_id, query=query, limit=limit), timeout=15)
        if not results:
            return "No relevant items found in your knowledge base."
        lines = [f"[{r.get('source_type', '')}] (score {r.get('score', 0):.2f}): {r.get('content', '')[:2000]}" for r in results]
        return "\n\n---\n\n".join(lines)
    except asyncio.TimeoutError:
        return "Knowledge base search timed out."
    except Exception as e:
        logger.debug("knowledge_base_search failed: {}", e)
        return f"Knowledge base search failed: {e!s}"


async def _knowledge_base_add_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Add content to the user's knowledge base (e.g. after reading a document or web page). Only add when the user explicitly asks to save. Never raises."""
    try:
        core = getattr(context, "core", None)
        kb = getattr(core, "knowledge_base", None) if core else None
        if not kb:
            return "Knowledge base is not available (disabled or not configured)."
        user_id = (getattr(context, "user_id", None) or getattr(context, "user_name", None) or "").strip()
        if not user_id:
            return "No user context; cannot add to knowledge base."
        content = (arguments.get("content") or "").strip()
        if not content:
            return "Content is required to add to the knowledge base."
        source_type = (arguments.get("source_type") or "user").strip() or "user"
        source_id = (arguments.get("source_id") or "").strip()
        if not source_id:
            source_id = f"user_{_time.time():.0f}"
        metadata = arguments.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            metadata = None
        err = await asyncio.wait_for(
            kb.add(user_id=user_id, content=content, source_type=source_type, source_id=source_id, metadata=metadata),
            timeout=60,
        )
        if err:
            return f"Failed to add to knowledge base: {err}"
        return f"Added to your knowledge base (source_id={source_id}, source_type={source_type})."
    except asyncio.TimeoutError:
        return "Knowledge base add timed out."
    except Exception as e:
        logger.debug("knowledge_base_add failed: {}", e)
        return f"Failed to add to knowledge base: {e!s}"


async def _knowledge_base_remove_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Remove all chunks for a given source from the user's knowledge base (by source_id). Never raises."""
    try:
        core = getattr(context, "core", None)
        kb = getattr(core, "knowledge_base", None) if core else None
        if not kb:
            return "Knowledge base is not available (disabled or not configured)."
        user_id = (getattr(context, "user_id", None) or getattr(context, "user_name", None) or "").strip()
        if not user_id:
            return "No user context; cannot remove from knowledge base."
        source_id = (arguments.get("source_id") or "").strip()
        if not source_id:
            return "source_id is required to remove a source from the knowledge base."
        err = await asyncio.wait_for(kb.remove_by_source_id(user_id=user_id, source_id=source_id), timeout=15)
        if err:
            return f"Failed to remove: {err}"
        return f"Removed all knowledge base entries for source_id={source_id}."
    except asyncio.TimeoutError:
        return "Knowledge base remove timed out."
    except Exception as e:
        logger.debug("knowledge_base_remove failed: {}", e)
        return f"Failed to remove from knowledge base: {e!s}"


async def _knowledge_base_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List saved documents/sources in the user's knowledge base. Optionally check if a specific source_id is saved."""
    try:
        core = getattr(context, "core", None)
        kb = getattr(core, "knowledge_base", None) if core else None
        if not kb:
            return "Knowledge base is not available (disabled or not configured)."
        user_id = (getattr(context, "user_id", None) or getattr(context, "user_name", None) or "").strip()
        if not user_id:
            return "No user context; cannot list knowledge base."
        if not hasattr(kb, "list_sources"):
            return "This knowledge base backend does not support listing sources."
        limit = max(1, min(500, int(arguments.get("limit") or 0) or 100))
        sources = await asyncio.wait_for(kb.list_sources(user_id=user_id, limit=limit), timeout=15)
        source_id_filter = (arguments.get("source_id") or "").strip()
        if source_id_filter:
            for s in sources:
                if (s.get("source_id") or "") == source_id_filter:
                    return json.dumps({
                        "in_knowledge_base": True,
                        "source_id": source_id_filter,
                        "source_type": s.get("source_type", ""),
                        "added_at": s.get("added_at"),
                    }, ensure_ascii=False, indent=0)
            return json.dumps({"in_knowledge_base": False, "source_id": source_id_filter})
        if not sources:
            return "No documents are saved in your knowledge base yet."
        return json.dumps({
            "count": len(sources),
            "sources": [{"source_id": s.get("source_id"), "source_type": s.get("source_type", ""), "added_at": s.get("added_at")} for s in sources],
        }, ensure_ascii=False, indent=0)
    except asyncio.TimeoutError:
        return "Knowledge base list timed out."
    except Exception as e:
        logger.debug("knowledge_base_list failed: {}", e)
        return f"Failed to list knowledge base: {e!s}"


async def _save_result_page_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Save a result page as HTML or Markdown. format=markdown: returns markdown content + link so reply can show it in chat. format=html: returns link only (open in browser)."""
    try:
        from core.result_viewer import build_file_view_link, generate_result_html
        title = (arguments.get("title") or "").strip() or "Result"
        content = arguments.get("content") or ""
        fmt = (arguments.get("format") or "markdown").strip().lower() or "markdown"
        if fmt not in ("markdown", "md", "html"):
            fmt = "markdown"
        if fmt == "md":
            fmt = "markdown"
        content_str = str(content or "").strip()
        title_lower = title.lower()
        # When user asked for HTML slides, insist on format=html and full content
        if fmt == "markdown":
            if content_str and (content_str.lstrip().lower().startswith("<html") or content_str.lstrip().startswith("<!DOCTYPE")):
                return (
                    "Error: content is HTML but format is markdown. For HTML slides or HTML output use format='html'. "
                    "Call save_result_page again with format='html' and content=<your full HTML>."
                )
            if ("slide" in title_lower or "slides" in title_lower()) and len(content_str) < 500:
                return (
                    "Error: for HTML slides use format='html', not format='markdown'. "
                    "Generate the full HTML slide deck from the document_read result and call save_result_page(title=..., content=<full HTML>, format='html')."
                )
        if fmt == "html":
            if not content_str:
                return (
                    "Error: content is required for format=html. Use the **content from the previous document_read result** to generate the full HTML, then call save_result_page with that content. "
                    "**Stop calling tools now.** Reply to the user: say you need to generate the slide from the document content first, then save it."
                )
            # Reject title-only or minimal HTML so the page has real body content (e.g. full slide deck, not just a heading)
            if len(content_str) < 250:
                return (
                    "Error: content for format=html is too short. Use the **previous document_read result** to build the full HTML (all slides with content), then call save_result_page with that HTML. "
                    "**Stop calling tools now.** Reply to the user: explain that the slide needs full content from the document and ask them to try again or wait for you to generate it."
                )
        content = content_str or content
        scope = _get_file_workspace_subdir(context)
        file_id = uuid.uuid4().hex[:16]
        # Markdown → .md (suitable for in-chat display; client can fetch and render). HTML → .html (styled page, open in browser).
        is_md = fmt == "markdown"
        ext = ".md" if is_md else ".html"
        path_arg = f"{FILE_OUTPUT_SUBDIR}/report_{file_id}{ext}"
        r = _resolve_file_path(path_arg, context, for_write=True)
        if r is None:
            return _file_resolve_error_msg()
        full, base = r
        if not _path_under(full, base):
            return _FILE_ACCESS_DENIED_MSG
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            if is_md:
                # Raw markdown: title as first line, then content. Truncate if over limit (same as HTML path).
                try:
                    from base.util import Util
                    tools_cfg = getattr(Util().get_core_metadata(), "tools", None) or {}
                    max_kb = int(tools_cfg.get("save_result_page_max_file_size_kb") or 500)
                    max_bytes = max_kb * 1024
                except Exception:
                    max_bytes = 500 * 1024
                if len(content.encode("utf-8")) > max_bytes:
                    content = content[: max_bytes // 2] + "\n\n… [content truncated due to size limit]"
                md_content = f"# {title}\n\n" + content if title else content
                full.write_text(md_content, encoding="utf-8")
            else:
                html = generate_result_html(title=title, content=content, format="html")
                full.write_text(html, encoding="utf-8")
        except Exception as e:
            logger.debug("save_result_page write failed: {}", e)
            return "Failed to save the result page to your output folder."
        link, link_err = build_file_view_link(scope, path_arg)

        if is_md:
            # Return markdown so the model can include it in the reply → channel/companion/web chat display it in the chat view. Cap length for the reply.
            max_in_chat = 12000
            to_show = md_content if len(md_content) <= max_in_chat else md_content[:max_in_chat] + "\n\n… (full report: open link below)"
            if link:
                return f"{to_show}\n\n---\nReport saved. You MUST share this link with the user (full link in one line; if it does not open, tell user to copy the entire URL and paste in browser): {link}"
            return f"{to_show}\n\n---\nReport saved to your output folder. {link_err or 'Set auth_api_key in config for a shareable link.'}"

        # HTML: return the link — you MUST include this link in your reply to the user so they can view the report.
        if link:
            return f"SUCCESS. You MUST share this link with the user in your reply so they can view the report. Use the full link in one line; if it does not open when clicked, tell the user to copy the entire URL and paste it in the browser: {link}"
        return f"Report saved to your output folder. {link_err or 'Set core_public_url and auth_api_key in config for shareable links.'}"
    except Exception as e:
        logger.debug("save_result_page failed: {}", e)
        return f"Failed to save result page: {e!s}"


async def _file_write_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Write content to a file. Use 'share/...' for shared folder, or path for your user or companion folder. Folders created automatically."""
    path_arg = (arguments.get("path") or "").strip()
    content = arguments.get("content", "")
    if not path_arg:
        return "Path is required."
    try:
        r = _resolve_file_path(path_arg, context, for_write=True)
        if r is None:
            return _file_resolve_error_msg()
        full, base = r
        if not _path_under(full, base):
            return _FILE_ACCESS_DENIED_MSG
        full.parent.mkdir(parents=True, exist_ok=True)
        content_str = str(content or "")
        full.write_text(content_str, encoding="utf-8")
        out = json.dumps({"written": True, "path": path_arg})
        # When writing to output/, provide a view link only if the file has real content (avoid linking to empty pages).
        if path_arg.startswith(FILE_OUTPUT_SUBDIR + "/") or path_arg == FILE_OUTPUT_SUBDIR:
            scope = _get_file_workspace_subdir(context)
            if scope:
                from core.result_viewer import build_file_view_link
                # Do not return a view link for empty or minimal content (same threshold as save_result_page for HTML).
                content_size = len((content_str or "").strip())
                if content_size >= 250:
                    link, _ = build_file_view_link(scope, path_arg)
                    if link:
                        out = f"File saved. View (use full link in one line; if it does not open, copy the entire URL and paste in browser): {link}\n{out}"
                    else:
                        out = f"{out}\nPath: {path_arg}. To get a view link, set core_public_url and auth_api_key in config/core.yml."
                else:
                    out = (
                        f"{out}\nPath: {path_arg}. The file is empty or too small ({content_size} chars). "
                        "Do NOT share this link. You must use the **content from the previous document_read result** as the source: generate the full HTML from that text, then call save_result_page(title=..., content=<full HTML>, format='html'). "
                        "**Stop calling tools now.** Reply to the user: say the slide was not generated yet because content was empty; you need to use the document content to build the HTML first, then save it (or ask them to try again)."
                    )
        return out
    except Exception as e:
        logger.debug("file_write failed: %s", e)
        return _FILE_NOT_FOUND_MSG


async def _get_file_view_link_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Return a view link for a file already saved under output/ (e.g. after file_write or save_result_page). Use when the user asks for the link (e.g. 'send me the link', '能把链接发给我')."""
    path_arg = (arguments.get("path") or "").strip()
    if not path_arg or ".." in path_arg or path_arg.startswith("/"):
        return "Path is required and must be a relative path under output/ (e.g. output/report_xxx.html)."
    if not (path_arg.startswith(FILE_OUTPUT_SUBDIR + "/") or path_arg == FILE_OUTPUT_SUBDIR):
        return f"Only paths under {FILE_OUTPUT_SUBDIR}/ can have view links (e.g. output/allen_resume_slides.html)."
    try:
        from core.result_viewer import build_file_view_link
        scope = _get_file_workspace_subdir(context)
        if not scope:
            return "Could not determine user/companion scope. Use the path from the previous file save (e.g. output/allen_resume_slides.html)."
        link, link_err = build_file_view_link(scope, path_arg)
        if link:
            return f"View link (share this with the user; use the full link in one line): {link}"
        return f"View link is not available: {link_err or 'set core_public_url and auth_api_key in config/core.yml.'}"
    except Exception as e:
        logger.debug("get_file_view_link failed: %s", e)
        return f"Could not generate link: {e!s}"


# Reserved path prefix for user/companion generated files (reports, images, exports). Use path "output/<filename>" so files land in base/{user_id}/output/ or base/companion/output/. See docs_design/FileSandboxDesign.md.
FILE_OUTPUT_SUBDIR = "output"

# Polite messages for file tools (never crash; user-friendly responses)
_FILE_ACCESS_DENIED_MSG = (
    "That path is outside the sandbox. You can only access (1) the user sandbox root and its subfolders (path '.' or 'subdir'), "
    "or (2) share and its subfolders (path 'share' or 'share/...'). Any other folder cannot be accessed."
)
_FILE_NOT_FOUND_MSG = (
    "That file or path wasn't found. Only two bases are accessible (sandbox): user sandbox (path '.') and share (path 'share'), and their subfolders. "
    "Try: (1) folder_list(path='.') or file_find(path='.', pattern='*filename*') to get the path; (2) use the exact path that matches the filename the user asked for (e.g. user asked for 1.pdf → use path '1.pdf', not a path under output/ or another file)."
)
_FILE_PATH_INVALID_MSG = "I couldn't resolve that path. Please check the path and try again."
_FILE_HOMECLAW_ROOT_NOT_SET_MSG = (
    "File and folder access is not configured. Set homeclaw_root in config/core.yml to the root folder where each user has a subfolder (e.g. homeclaw_root/{user_id}/ for private files, homeclaw_root/share for shared). "
    "Then list or search with folder_list(path='.') or file_find(path='.', pattern='*')."
)


def _file_resolve_error_msg() -> str:
    """When _resolve_file_path returned None: homeclaw_root not set vs invalid path. Never raises."""
    try:
        root = _get_homeclaw_root()
        if not (root or "").strip():
            return _FILE_HOMECLAW_ROOT_NOT_SET_MSG
    except Exception:
        pass
    return _FILE_PATH_INVALID_MSG


def _path_under(full: Path, base: Optional[Path]) -> bool:
    """True if full is under base (or base is None). Cross-platform."""
    if base is None:
        return True
    try:
        full.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _safe_user_dir(user_id: Optional[str]) -> str:
    """Return a single path segment safe for use as a per-user subdirectory (no slashes, no '..'). Uses user id from user.yml."""
    if not user_id or not isinstance(user_id, str):
        return "default"
    # Keep only alphanumeric, underscore, hyphen; collapse to one segment
    safe = re.sub(r"[^\w\-]", "_", user_id.strip())
    return safe[:64] if safe else "default"


def _is_companion_context(context: Optional[Any]) -> bool:
    """True when the request is from the companion app and not tied to a specific user (so use companion folder)."""
    if context is None:
        return False
    req = getattr(context, "request", None)
    session_id = (getattr(context, "session_id", None) or "").strip().lower()
    user_id = (getattr(context, "user_id", None) or "").strip().lower()
    app_id = (getattr(context, "app_id", None) or "").strip().lower()
    channel_name = ""
    conversation_type = ""
    if req is not None:
        channel_name = (getattr(req, "channel_name", None) or getattr(req, "channelType", None) or "").strip().lower()
        meta = getattr(req, "request_metadata", None) or {}
        if isinstance(meta, dict):
            conversation_type = (meta.get("conversation_type") or meta.get("session_id") or "").strip().lower()
    return (
        session_id == "companion"
        or user_id == "companion"
        or app_id == "companion"
        or channel_name == "companion"
        or conversation_type == "companion"
    )


def _get_file_workspace_subdir(context: Optional[Any]) -> str:
    """Folder name under homeclaw_root: 'companion' when companion app without user, else user id from user.yml (or 'default')."""
    if context is None:
        return "default"
    system_user_id = (getattr(context, "system_user_id", None) or "").strip()
    if system_user_id:
        return _safe_user_dir(system_user_id)
    if _is_companion_context(context):
        return "companion"
    uid = getattr(context, "user_id", None) or getattr(context, "user_name", None)
    return _safe_user_dir(uid)


def _resolve_file_path(
    path_arg: str,
    context: Optional[Any],
    *,
    for_write: bool = False,
) -> Optional[Tuple[Path, Optional[Path]]]:
    """
    Resolve a file path for file tools. Returns (full_path, base_for_validation) or None on error (caller should return polite message).
    Sandbox: only two bases are allowed — (1) user sandbox homeclaw_root/{user_id}/, (2) share homeclaw_root/share/.
    Paths must stay under one of these; their subfolders are allowed; any other path is denied.
    - When homeclaw_root is SET: path "." or "subdir" → user sandbox; path "share" or "share/..." → share. Use "output/<filename>" for generated files.
    - When homeclaw_root is NOT SET: path_arg can be absolute. base_for_validation = None.
    Never raises; returns None on any exception.
    """
    try:
        config = _get_tools_config()
        base_str = _get_homeclaw_root()
        path_arg = (path_arg or "").strip()
        if not path_arg:
            if not base_str:
                return None  # homeclaw_root not set; caller should return clear message
            path_arg = "."  # default to user's private folder (homeclaw_root/{user_id}) when homeclaw_root is set

        if not base_str:
            # homeclaw_root not set: do not resolve relative paths (would be wrong). Require homeclaw_root in config.
            if not path_arg or path_arg == "." or not Path(path_arg).is_absolute():
                return None
            full = Path(path_arg).resolve()
            return (full, None)

        shared_dir = (config.get("file_read_shared_dir") or "share").strip() or "share"
        normalized = path_arg.replace("\\", "/").strip().lower()
        shared_dir_lower = shared_dir.lower()
        shared_prefix = shared_dir_lower + "/"

        # Prefer per-user paths from sandbox_paths.json (single source of truth; always use these when present)
        user_key = _get_file_workspace_subdir(context)
        paths_data = load_sandbox_paths_json()
        user_paths = (paths_data.get("users") or {}).get(user_key)
        if user_paths:
            base_sandbox = Path(user_paths.get("sandbox_root") or "").resolve()
            base_share = Path(user_paths.get("share") or "").resolve()
            if base_sandbox and base_share:
                if normalized == shared_dir_lower or normalized.startswith(shared_prefix):
                    rest = path_arg[len(shared_dir):].lstrip("/\\").strip() if path_arg.lower().startswith(shared_dir_lower) else path_arg
                    if not rest:
                        rest = "."
                    effective_base = base_share
                else:
                    effective_base = base_sandbox
                    rest = path_arg or "."
                try:
                    effective_base.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
                full = (effective_base / rest).resolve()
                return (full, effective_base)

        base = Path(base_str).resolve()
        if normalized == shared_dir_lower or normalized.startswith(shared_prefix):
            rest = path_arg[len(shared_dir):].lstrip("/\\").strip() if path_arg.lower().startswith(shared_dir_lower) else path_arg
            if not rest:
                rest = "."
            effective_base = (base / shared_dir).resolve()
            try:
                effective_base.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        else:
            user_sub = _get_file_workspace_subdir(context)
            effective_base = (base / user_sub).resolve()
            rest = path_arg or "."
            try:
                effective_base.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

        full = (effective_base / rest).resolve()
        # Validate under the allowed sandbox root (user folder or share); reject escape (e.g. ../other_user)
        return (full, effective_base)
    except Exception as e:
        logger.debug("_resolve_file_path failed: %s", e)
        return None


def _get_file_base_path(context: Optional[Any] = None) -> Path:
    """Resolved base for file tools (homeclaw_root; when empty = workspace_dir). Prefer _resolve_file_path() for per-request resolution (shared + per-user). Never raises."""
    try:
        base_str = _get_homeclaw_root()
        if not base_str or base_str == ".":
            return Path(".").resolve()
        return Path(base_str).resolve()
    except Exception:
        return Path(".").resolve()


async def _file_edit_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Replace old_string with new_string in a file (once or all). Use 'share/...' or path in your user or companion folder."""
    path_arg = (arguments.get("path") or "").strip()
    old_str = arguments.get("old_string", "")
    new_str = arguments.get("new_string", "")
    replace_all = arguments.get("replace_all") is True
    if not path_arg:
        return "Path is required."
    try:
        r = _resolve_file_path(path_arg, context, for_write=False)
        if r is None:
            return _file_resolve_error_msg()
        full, base = r
        if not _path_under(full, base):
            return _FILE_ACCESS_DENIED_MSG
        if not full.is_file():
            return _FILE_NOT_FOUND_MSG
        content = full.read_text(encoding="utf-8", errors="replace")
        if replace_all:
            if old_str not in content:
                return json.dumps({"edited": False, "message": "old_string not found"})
            new_content = content.replace(old_str, new_str)
        else:
            if old_str not in content:
                return json.dumps({"edited": False, "message": "old_string not found"})
            new_content = content.replace(old_str, new_str, 1)
        full.write_text(new_content, encoding="utf-8")
        return json.dumps({"edited": True, "path": path_arg})
    except Exception as e:
        logger.debug("file_edit failed: %s", e)
        return _FILE_NOT_FOUND_MSG


def _parse_unified_diff_patch(patch_text: str) -> List[Dict[str, Any]]:
    """Parse a simple unified diff (single file). Returns list of {path, hunks} where hunk is {start_old, count_old, start_new, count_new, lines}."""
    path, hunks = None, []
    current_hunk = None
    for line in patch_text.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            if line.startswith("+++ "):
                p = line[4:].strip()
                if p.startswith("b/"):
                    p = p[2:]
                path = p
            continue
        if line.startswith("@@ "):
            if current_hunk:
                hunks.append(current_hunk)
            m = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
            if m:
                current_hunk = {
                    "start_old": int(m.group(1)),
                    "count_old": int(m.group(2) or 1),
                    "start_new": int(m.group(3)),
                    "count_new": int(m.group(4) or 1),
                    "lines": [],
                }
            continue
        if current_hunk is not None:
            current_hunk["lines"].append(line)
    if current_hunk:
        hunks.append(current_hunk)
    return [{"path": path, "hunks": hunks}] if path else []


def _apply_hunk(content: str, hunk: Dict[str, Any]) -> str:
    """Apply one hunk (unified diff) to content. Returns new content."""
    lines = content.splitlines(keepends=True)
    if not lines and content:
        lines = [content]
    elif not lines:
        lines = [""]
    start_old = max(0, hunk["start_old"] - 1)
    count_old = max(0, hunk["count_old"])
    hunk_lines = hunk["lines"]
    new_parts = []
    old_idx = start_old
    for line in hunk_lines:
        if line.startswith(" "):
            if old_idx < len(lines):
                new_parts.append(lines[old_idx])
            old_idx += 1
        elif line.startswith("-"):
            old_idx += 1
        elif line.startswith("+"):
            new_parts.append((line[1:] if len(line) > 1 else "").rstrip("\n") + "\n")
    before = "".join(lines[:start_old])
    after = "".join(lines[old_idx:]) if old_idx <= len(lines) else ""
    return before + "".join(new_parts) + after


async def _apply_patch_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Apply a unified diff patch to a file. Path in patch: use 'share/...' or path in your user or companion folder. When base not set, absolute paths allowed."""
    patch_text = arguments.get("patch", "") or arguments.get("content", "")
    if not patch_text.strip():
        return "Error: patch is required"
    parsed = _parse_unified_diff_patch(patch_text)
    if not parsed:
        return "Error: could not parse patch (expected unified diff with ---/+++ and @@ hunks)"
    results = []
    for file_spec in parsed:
        path_arg = (file_spec.get("path") or "").strip()
        if not path_arg:
            results.append({"path": None, "error": "missing path in patch"})
            continue
        try:
            r = _resolve_file_path(path_arg, context, for_write=True)
            if r is None:
                results.append({"path": path_arg, "error": "invalid path"})
                continue
            full, base = r
            if not _path_under(full, base):
                results.append({"path": path_arg, "error": "path outside base"})
                continue
            content = full.read_text(encoding="utf-8", errors="replace") if full.is_file() else ""
            for hunk in file_spec.get("hunks") or []:
                content = _apply_hunk(content, hunk)
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            results.append({"path": path_arg, "applied": True})
        except Exception as e:
            results.append({"path": path_arg, "error": str(e)})
    return json.dumps({"results": results})


# ---- Folder / file explore (cross-platform) ----
async def _folder_list_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """List directory contents. Use 'share' or 'share/' for shared folder, '.' or path for your user or companion folder. When base not set, absolute path allowed."""
    path_arg = (arguments.get("path") or ".").strip()
    try:
        r = _resolve_file_path(path_arg, context, for_write=False)
        if r is None:
            return _file_resolve_error_msg()
        full, base = r
        if not _path_under(full, base):
            return _FILE_ACCESS_DENIED_MSG
        if not full.is_dir():
            return _FILE_NOT_FOUND_MSG
        max_entries = int(arguments.get("max_entries", 0)) or 500
        entries = []
        # Paths must be relative to the user sandbox (effective_base) so file_read/document_read(path=...) resolve to the same file.
        path_arg_normalized = (path_arg or ".").strip() in (".", "")
        base_for_rel = full if path_arg_normalized else full.parent
        for i, p in enumerate(sorted(full.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))):
            if i >= max_entries:
                entries.append({"name": "...", "type": "(truncated)", "path": ""})
                break
            try:
                rel = str(p.relative_to(base_for_rel)).replace("\\", "/")
            except ValueError:
                rel = p.name
            entries.append({
                "name": p.name,
                "type": "dir" if p.is_dir() else "file",
                "path": rel,
            })
        return json.dumps(entries, ensure_ascii=False, indent=0)
    except Exception as e:
        logger.debug("folder_list failed: %s", e)
        return _FILE_NOT_FOUND_MSG


async def _file_find_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Find files by pattern (glob). Search under 'share/', your user folder, or companion folder. When base not set, path can be absolute."""
    path_arg = (arguments.get("path") or ".").strip()
    pattern = (arguments.get("pattern") or arguments.get("name") or "*").strip()
    if not pattern:
        pattern = "*"
    try:
        r = _resolve_file_path(path_arg, context, for_write=False)
        if r is None:
            return _file_resolve_error_msg()
        full_dir, base = r
        if not _path_under(full_dir, base):
            return _FILE_ACCESS_DENIED_MSG
        if not full_dir.is_dir():
            return _FILE_NOT_FOUND_MSG
        max_results = int(arguments.get("max_results", 0)) or 200
        results = []
        base_for_rel = base if base is not None else full_dir
        for i, p in enumerate(full_dir.rglob(pattern)):
            if i >= max_results:
                results.append({"path": "(truncated)", "type": "", "name": ""})
                break
            try:
                rel = str(p.relative_to(base_for_rel))
            except ValueError:
                rel = p.name
            results.append({
                "path": rel,
                "type": "dir" if p.is_dir() else "file",
                "name": p.name,
            })
        return json.dumps(results, ensure_ascii=False, indent=0)
    except Exception as e:
        logger.debug("file_find failed: %s", e)
        return _FILE_NOT_FOUND_MSG


# ---- Browser: fetch URL (lightweight, no JS) and optional full browser (Playwright) ----
def _html_to_text(html: str, max_chars: int = 50_000) -> str:
    """Strip HTML to approximate plain text. Removes script/style and tags."""
    if not html:
        return ""
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html).strip()
    if len(html) > max_chars:
        html = html[:max_chars] + " ... (truncated)"
    return html


def _extract_main_content(html: str, url: str, max_chars: int) -> str:
    """Extract main article/content from HTML. Uses trafilatura if installed, else BeautifulSoup, else _html_to_text. No API key."""
    if not html or not html.strip():
        return ""
    try:
        import trafilatura
        text = trafilatura.extract(html, url=url or None, include_comments=False, include_tables=True)
        if text and text.strip():
            if len(text) > max_chars:
                text = text[:max_chars] + " ... (truncated)"
            return text.strip()
    except ImportError:
        pass
    except Exception:
        pass
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in ("script", "style", "nav", "footer", "header"):
            for e in soup.find_all(tag):
                e.decompose()
        body = soup.find("body") or soup
        text = body.get_text(separator=" ", strip=True) if body else ""
        text = re.sub(r"\s+", " ", text).strip()
        if text and len(text) > max_chars:
            text = text[:max_chars] + " ... (truncated)"
        return text or ""
    except ImportError:
        pass
    except Exception:
        pass
    return _html_to_text(html, max_chars)


async def _fetch_url_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Fetch a URL and return the page content as plain text (HTML stripped). No JavaScript execution; use browser_navigate for JS-rendered pages."""
    url = (arguments.get("url") or "").strip()
    if not url:
        return "Error: url is required"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    max_chars = int(arguments.get("max_chars", 0)) or 40_000
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = _html_to_text(resp.text, max_chars)
            return text or "(no text content)"
    except ImportError:
        return "Error: httpx is required (pip install httpx)"
    except Exception as e:
        return f"Error: {e!s}"


async def _web_extract_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Extract main content from one or more URLs using free Python libs (trafilatura or BeautifulSoup). No API key. Use for reading/summarizing pages when you have the URL."""
    urls_arg = arguments.get("urls") or arguments.get("url") or ""
    if isinstance(urls_arg, str):
        urls_arg = [u.strip() for u in re.split(r"[\s,]+", urls_arg) if u.strip()]
    if not urls_arg:
        return "Error: urls (or url) is required — comma/space-separated list or single URL."
    max_chars = int(arguments.get("max_chars", 0)) or 60_000
    max_urls = min(max(1, int(arguments.get("max_urls", 0)) or 10), 20)
    urls = urls_arg[:max_urls]
    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx required. pip install httpx", "results": []})
    results = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for u in urls:
            if not u.startswith(("http://", "https://")):
                u = "https://" + u
            try:
                resp = await client.get(u)
                resp.raise_for_status()
                text = _extract_main_content(resp.text, u, max_chars)
                results.append({"url": u, "content": text or "(no content extracted)", "status": "ok"})
            except Exception as e:
                results.append({"url": u, "content": "", "status": "error", "error": str(e)})
    return json.dumps({"results": results})


def _same_domain_or_allowed(link: str, base_url: str, same_domain_only: bool) -> bool:
    """Return True if link should be followed. If same_domain_only, require same netloc."""
    if not link or not link.startswith(("http://", "https://")):
        return False
    try:
        from urllib.parse import urlparse
        base = urlparse(base_url)
        parsed = urlparse(link)
        if not same_domain_only:
            return True
        return (parsed.netloc or "").lower() == (base.netloc or "").lower()
    except Exception:
        return False


async def _web_crawl_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Crawl from a start URL: fetch page, extract links, follow up to max_pages (free; no API key). Uses same extract as web_extract. Respects same_domain_only (default true)."""
    start_url = (arguments.get("url") or arguments.get("start_url") or "").strip()
    if not start_url:
        return "Error: url (or start_url) is required."
    if not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url
    max_pages = min(max(1, int(arguments.get("max_pages", 0)) or 10), 50)
    max_depth = min(max(1, int(arguments.get("max_depth", 0)) or 2), 5)
    same_domain_only = arguments.get("same_domain_only", True)
    if isinstance(same_domain_only, str):
        same_domain_only = same_domain_only.strip().lower() in ("1", "true", "yes")
    max_chars_per_page = int(arguments.get("max_chars", 0)) or 30_000
    try:
        import httpx
        from urllib.parse import urljoin, urlparse
    except ImportError:
        return json.dumps({"error": "httpx required. pip install httpx", "results": []})
    seen: set = set()
    results = []
    queue: List[tuple] = [(start_url, 0)]
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)
            if url in seen or depth > max_depth:
                continue
            seen.add(url)
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
                text = _extract_main_content(html, url, max_chars_per_page)
                results.append({"url": url, "depth": depth, "content": text or "(no content)", "status": "ok"})
                if depth < max_depth and len(results) < max_pages:
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, "html.parser")
                        for a in soup.find_all("a", href=True):
                            href = (a.get("href") or "").strip()
                            full = urljoin(url, href)
                            if _same_domain_or_allowed(full, start_url, same_domain_only) and full not in seen:
                                queue.append((full, depth + 1))
                    except ImportError:
                        pass
            except Exception as e:
                results.append({"url": url, "depth": depth, "content": "", "status": "error", "error": str(e)})
    return json.dumps({"results": results, "total": len(results)})


# ---- Full browser (Playwright session: navigate, snapshot, click, type) ----
# Uses context.browser_session to reuse the same page across tool calls in one request.

async def close_browser_session(context: ToolContext) -> None:
    """Close the browser and Playwright if open. Call from Core after the tool loop."""
    session = getattr(context, "browser_session", None)
    if not session:
        return
    browser = session.get("browser")
    if browser:
        try:
            await browser.close()
        except Exception as e:
            logger.warning("Error closing browser: {}", e)
        session.pop("browser", None)
        session.pop("page", None)
    pw_cm = session.get("playwright_cm")
    if pw_cm:
        try:
            await pw_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.warning("Error closing Playwright: {}", e)
        session.pop("playwright_cm", None)


async def _get_or_create_browser_page(context: ToolContext, url: Optional[str] = None):
    """Get or create Playwright browser and page; optionally navigate to url. Returns (browser, page)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright\n"
            "Then install the browser: python -m playwright install chromium"
        )
    session = getattr(context, "browser_session", None) or {}
    context.browser_session = session
    browser = session.get("browser")
    page = session.get("page")
    if not browser or not page:
        config = _get_tools_config()
        headless = config.get("browser_headless", True)
        if not isinstance(headless, bool):
            headless = str(headless).strip().lower() in ("1", "true", "yes")
        pw_cm = async_playwright()
        playwright = await pw_cm.__aenter__()
        try:
            browser = await playwright.chromium.launch(headless=headless)
        except Exception as e:
            err_msg = str(e).lower()
            if "executable" in err_msg or "does not exist" in err_msg or "not found" in err_msg:
                try:
                    exp_path = playwright.chromium.executable_path
                except Exception:
                    exp_path = "(unknown)"
                raise RuntimeError(
                    "Playwright browser (Chromium) not found. Common cause: you installed with a different Python than the one running Core.\n"
                    "Fix: using the SAME Python that starts Core, run: python -m playwright install chromium\n"
                    "Example: if Core is started as 'python core/main.py', run that same 'python -m playwright install chromium' (or activate the same venv first).\n"
                    "On Linux you may need: python -m playwright install --with-deps chromium\n"
                    "Path Playwright expects: %s\n"
                    "Original error: %s" % (exp_path, e)
                ) from e
            raise
        page = await browser.new_page()
        session["playwright_cm"] = pw_cm
        session["browser"] = browser
        session["page"] = page
    if url:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    return browser, page


async def _browser_navigate_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Open a URL in the shared browser session (or create one) and return the page text. Use browser_snapshot next to get clickable elements, then browser_click or browser_type."""
    url = (arguments.get("url") or "").strip()
    if not url:
        return "Error: url is required"
    max_chars = int(arguments.get("max_chars", 0)) or 50_000
    try:
        _, page = await _get_or_create_browser_page(context, url=url)
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        text = (text or "").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated)"
        return text or "(no text content)"
    except Exception as e:
        return f"Error: {e!s}"


async def _browser_snapshot_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Get a list of interactive elements (buttons, links, inputs) on the current page with selectors and text. Use these selectors with browser_click or browser_type. Optional: take a screenshot and return its path."""
    try:
        _, page = await _get_or_create_browser_page(context, url=None)
    except Exception as e:
        return f"Error: {e!s}"
    take_screenshot = arguments.get("screenshot", False)
    try:
        elements = await page.evaluate("""
            () => {
                const nodes = document.querySelectorAll('a[href], button, input, textarea, [role="button"], [onclick]');
                return Array.from(nodes).slice(0, 100).map((el, i) => {
                    el.setAttribute('data-homeclaw-ref', String(i));
                    const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 80);
                    return { selector: '[data-homeclaw-ref="' + i + '"]', text: text || '(no text)', tag: el.tagName.toLowerCase(), index: i };
                });
            }
        """)
        out = {"elements": elements}
        if take_screenshot:
            import tempfile
            fd, path = tempfile.mkstemp(suffix=".png", prefix="homeclaw_browser_")
            import os
            os.close(fd)
            await page.screenshot(path=path)
            out["screenshot_path"] = path
        return json.dumps(out, ensure_ascii=False, indent=0)
    except Exception as e:
        return f"Error: {e!s}"


async def _browser_click_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Click an element on the current page. Use the selector from browser_snapshot (e.g. "button", "#submit", "a")."""
    selector = (arguments.get("selector") or "").strip()
    if not selector:
        return "Error: selector is required"
    try:
        _, page = await _get_or_create_browser_page(context, url=None)
        await page.click(selector, timeout=5000)
        return "Clicked: " + selector
    except Exception as e:
        return f"Error: {e!s}"


async def _browser_type_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Type text into an input or textarea on the current page. Use selector from browser_snapshot. Clears the field first."""
    selector = (arguments.get("selector") or "").strip()
    text = arguments.get("text", "")
    if not selector:
        return "Error: selector is required"
    try:
        _, page = await _get_or_create_browser_page(context, url=None)
        await page.fill(selector, str(text))
        return "Typed into: " + selector
    except Exception as e:
        return f"Error: {e!s}"


def _parse_search_results_from_html(html: str, engine: str, max_count: int) -> List[Dict[str, Any]]:
    """Best-effort parse search result page HTML. engine: google, bing, baidu. Returns list of {title, url, description}."""
    results = []
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return results
    soup = BeautifulSoup(html, "html.parser")
    engine = (engine or "google").strip().lower()
    if engine == "google":
        for div in soup.select("div.g")[:max_count]:
            a = div.find("a", href=True)
            if not a or not a.get("href") or a["href"].startswith("/"):
                continue
            href = a["href"].strip()
            if href.startswith("http") and "google.com" not in href:
                title = (a.get_text() or "").strip()
                snippet_el = div.find("div", class_=lambda c: c and "VwiC3b" in str(c)) or div.find("span", class_=lambda c: c and "st" in str(c)) or div.find("div", class_="IsZvec")
                snippet = (snippet_el.get_text() if snippet_el else "").strip()[:500]
                results.append({"title": title or "(no title)", "url": href, "description": snippet})
    elif engine == "bing":
        for li in (soup.select("li.b_algo") or soup.select("li[class*='b_algo']"))[:max_count]:
            a = li.find("a", href=True)
            if not a or not a.get("href"):
                continue
            href = a["href"].strip()
            if href.startswith("http"):
                title = (a.get_text() or "").strip()
                p = li.find("p") or li.find("div", class_=lambda c: c and "b_caption" in str(c))
                snippet = (p.get_text() if p else "").strip()[:500]
                results.append({"title": title or "(no title)", "url": href, "description": snippet})
    elif engine == "baidu":
        for div in (soup.select("div.result") or soup.select("div[class*='result']"))[:max_count]:
            a = div.find("a", href=True)
            if not a or not a.get("href"):
                continue
            href = a.get("href", "").strip()
            if href.startswith("http"):
                title = (a.get_text() or "").strip()
                abstract = div.find("div", class_=lambda c: c and "c-abstract" in str(c)) or div.find("div", class_="content-right_8Zs40")
                snippet = (abstract.get_text() if abstract else "").strip()[:500]
                results.append({"title": title or "(no title)", "url": href, "description": snippet})
    return results[:max_count]


async def _web_search_browser_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Search Google, Bing, or Baidu using the browser (no API key). Fragile: HTML changes and CAPTCHA may break. Use when no paid/free API is configured."""
    from urllib.parse import quote_plus
    query = (arguments.get("query") or "").strip()
    if not query:
        return "Error: query is required"
    engine = (arguments.get("engine") or "google").strip().lower()
    if engine not in ("google", "bing", "baidu"):
        engine = "google"
    count = min(max(1, int(arguments.get("count", 5))), 10)
    if engine == "google":
        url = "https://www.google.com/search?q=" + quote_plus(query)
    elif engine == "bing":
        url = "https://www.bing.com/search?q=" + quote_plus(query)
    else:
        url = "https://www.baidu.com/s?wd=" + quote_plus(query)
    try:
        _, page = await _get_or_create_browser_page(context, url=url)
        await asyncio.sleep(2.5)
        html = await page.content()
        results = _parse_search_results_from_html(html, engine, count)
        return json.dumps({"results": results, "provider": "browser", "engine": engine})
    except Exception as e:
        return json.dumps({"error": f"Browser search failed: {e!s}. Try web_search with provider duckduckgo (no key) or configure google_cse/bing.", "results": [], "provider": "browser", "engine": engine})


# ---- HTTP request (generic API: GET/POST/PUT/PATCH/DELETE, headers) ----
async def _http_request_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Send an HTTP request (GET, POST, PUT, PATCH, DELETE). Use for REST APIs: read data (GET), create/update (POST/PUT/PATCH), delete (DELETE). Optional headers (e.g. Authorization)."""
    url = (arguments.get("url") or "").strip()
    if not url:
        return "Error: url is required"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    method = (arguments.get("method") or "GET").strip().upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return f"Error: method must be GET, POST, PUT, PATCH, or DELETE (got {method})"
    headers = arguments.get("headers")
    if isinstance(headers, str):
        try:
            headers = json.loads(headers)
        except json.JSONDecodeError:
            return "Error: headers must be valid JSON object"
    if not isinstance(headers, dict):
        headers = {}
    body = arguments.get("body")
    if isinstance(body, dict):
        pass
    elif isinstance(body, str) and body.strip().startswith("{"):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
    timeout_sec = float(arguments.get("timeout", 30) or 30)
    max_chars = int(arguments.get("max_response_chars", 0)) or 8000
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(
                    url, headers=headers,
                    json=body if isinstance(body, dict) else None,
                    content=body if isinstance(body, str) else None,
                )
            elif method == "PUT":
                resp = await client.put(
                    url, headers=headers,
                    json=body if isinstance(body, dict) else None,
                    content=body if isinstance(body, str) else None,
                )
            elif method == "PATCH":
                resp = await client.patch(
                    url, headers=headers,
                    json=body if isinstance(body, dict) else None,
                    content=body if isinstance(body, str) else None,
                )
            else:
                resp = await client.delete(url, headers=headers)
            text = resp.text
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            return json.dumps({"status_code": resp.status_code, "body": text})
    except ImportError:
        return "Error: httpx is required for http_request (pip install httpx)"
    except Exception as e:
        return f"Error: {e!s}"


# ---- Webhook (cross-platform) ----
async def _webhook_trigger_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Send an HTTP POST request to a URL (webhook). Optional JSON body."""
    url = (arguments.get("url") or "").strip()
    if not url:
        return "Error: url is required"
    body = arguments.get("body")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            if body is not None:
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        pass
                resp = await client.post(url, json=body if isinstance(body, dict) else None, content=body if isinstance(body, str) else None)
            else:
                resp = await client.post(url)
            return json.dumps({"status_code": resp.status_code, "body": resp.text[:2000]})
    except ImportError:
        return "Error: httpx is required for webhook_trigger (pip install httpx)"
    except Exception as e:
        return f"Error: {e!s}"


# ---- Routing tools (orchestrator_unified_with_tools): one LLM chooses TAM / plugin / chat ----
async def _route_to_tam_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Run TAM for time/scheduling intent; response is sent to the user. Return sentinel so Core does not send again."""
    core = context.core
    request = getattr(context, "request", None)
    if not request:
        return "Error: route_to_tam requires request context (unified orchestrator mode)."
    try:
        from base.base import Intent, IntentType
        intent = Intent(
            type=IntentType.TIME,
            text=getattr(request, "text", "") or "",
            intent_text="route_to_tam",
            timestamp=_time.time(),
            chatHistory="",
        )
        result = await core.orchestratorInst.tam.process_intent(intent, request)
        # Sync inbound/ws: return message so caller can send it (response queue is skipped for host=inbound port=0).
        if _is_sync_inbound(request) and isinstance(result, str) and result.strip():
            return result
        return ROUTING_RESPONSE_ALREADY_SENT
    except Exception as e:
        logger.exception(e)
        return f"Error running TAM: {e!s}"


async def _route_to_plugin_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Run the given plugin by id (inline Python or external http/subprocess/mcp). Optional capability_id and parameters. If capability has post_process, Core runs LLM on output before sending. Response is sent to the user. Return sentinel so Core does not send again. Supports param resolution (profile, config) and validation per docs/PluginParameterCollection.md."""
    core = context.core
    request = getattr(context, "request", None)
    if not request:
        return "Error: route_to_plugin requires request context (unified orchestrator mode)."
    cron_scheduled = getattr(context, "cron_scheduled", False)
    plugin_id = (arguments.get("plugin_id") or "").strip().lower().replace(" ", "_")
    if not plugin_id:
        return "Error: plugin_id is required."
    capability_id = (arguments.get("capability_id") or "").strip().lower().replace(" ", "_") or None
    llm_params = arguments.get("parameters")
    if not isinstance(llm_params, dict):
        llm_params = {}
    plugin_manager = getattr(core, "plugin_manager", None)
    if not plugin_manager:
        return "Error: no plugin manager available."
    plugin = plugin_manager.get_plugin_by_id(plugin_id)
    if not plugin:
        return f"Error: plugin not found: {plugin_id}"
    capability = plugin_manager.get_capability(plugin, capability_id) if capability_id else None
    # When no capability_id, use first capability for post_process (default entry point)
    if not capability and not isinstance(plugin, dict):
        reg = getattr(plugin, "registration", None) or {}
        caps = reg.get("capabilities") or []
        if caps:
            capability = caps[0]

    # Infer node_id from user message when plugin is homeclaw-browser and capability needs node_id but LLM didn't pass it
    if plugin_id in ("homeclaw_browser", "homeclaw-browser") and capability_id in ("node_camera_clip", "node_camera_snap"):
        if not (llm_params.get("node_id") or llm_params.get("nodeId")):
            user_text = (getattr(request, "text", None) or "") or ""
            if user_text:
                m = re.search(r"(?:on\s+)([a-zA-Z0-9_-]+)", user_text, re.IGNORECASE)
                node_id = m.group(1) if m else None
                if not node_id:
                    m = re.search(r"([a-zA-Z0-9]+-node-[a-zA-Z0-9]+)", user_text, re.IGNORECASE)
                    node_id = m.group(1) if m else None
                if node_id:
                    llm_params = {**llm_params, "node_id": node_id}

    # Resolve and validate parameters (profile, config, confirm_if_uncertain). See docs/PluginParameterCollection.md. Skip when cron_scheduled (no user to ask).
    params = dict(llm_params)
    if not cron_scheduled and capability and (capability.get("parameters") or []):
        from base.plugin_param_resolver import (
            _get_plugin_config,
            resolve_and_validate_plugin_params,
        )
        from base.profile_store import get_profile

        system_user_id = getattr(context, "system_user_id", None) or getattr(request, "user_id", None)
        profile = get_profile(system_user_id or "") if system_user_id else {}
        plugin_config = _get_plugin_config(plugin)
        system_context = getattr(core, "get_system_context_for_plugins", lambda *a, **k: {})(system_user_id, request) if callable(getattr(core, "get_system_context_for_plugins", None)) else {}
        resolved, err, ask_user = resolve_and_validate_plugin_params(
            llm_params, capability, profile, plugin_config,
            plugin_id=plugin_id, capability_id=capability_id,
            system_context=system_context,
        )
        if err and ask_user:
            # Ask user for missing/uncertain params and store pending so we can retry on next message
            missing = ask_user.get("missing") or []
            uncertain = ask_user.get("uncertain") or []
            app_id = getattr(context, "app_id", None) or ""
            user_id = getattr(context, "user_id", None) or getattr(request, "user_id", None) or ""
            session_id = getattr(context, "session_id", None) or ""
            if missing:
                hints = {
                    "node_id": "Which node should I use? (e.g. test-node-1)",
                    "nodeid": "Which node should I use? (e.g. test-node-1)",
                    "url": "Which URL should I open?",
                    "duration": "How long should the recording be? (e.g. 3 seconds)",
                }
                parts = []
                for m in missing:
                    key = m.lower().replace(" ", "_")
                    parts.append(hints.get(key, f"Please provide: {m}"))
                question = " ".join(parts) if len(parts) == 1 else "I need a few details: " + "; ".join(parts)
                core.set_pending_plugin_call(app_id, user_id, session_id, {
                    "plugin_id": plugin_id,
                    "capability_id": capability_id,
                    "params": dict(llm_params),
                    "missing": missing,
                    "uncertain": uncertain,
                })
                return question
            if uncertain:
                question = "Can you confirm the values above so I can proceed?"
                core.set_pending_plugin_call(app_id, user_id, session_id, {
                    "plugin_id": plugin_id,
                    "capability_id": capability_id,
                    "params": dict(resolved),
                    "missing": [],
                    "uncertain": uncertain,
                })
                return question
        if err:
            return err
        params = resolved

    plugin_id_for_log = plugin_id if isinstance(plugin, dict) else (
        (getattr(plugin, "registration", None) or {}).get("id") or getattr(plugin, "name", None) or "inline"
    )
    logger.info(
        "Plugin invoked: plugin_id={} capability_id={} parameters={}",
        plugin_id_for_log,
        capability_id,
        redact_params_for_log(params),
    )
    try:
        result_text = None
        metadata = {}
        # External plugin (http/subprocess/mcp): descriptor is a dict; run and get PluginResult
        if isinstance(plugin, dict):
            request_meta = dict(getattr(request, "request_metadata", None) or {})
            request_meta["capability_id"] = capability_id
            request_meta["capability_parameters"] = params
            from base.base import PromptRequest
            req_copy = request.model_copy(deep=True)
            req_copy.request_metadata = request_meta
            result = await plugin_manager.run_external_plugin(plugin, req_copy)
            if isinstance(result, PluginResult):
                if not result.success:
                    result_text = result.error or result.text or "Plugin returned an error"
                else:
                    result_text = result.text or "(no response)"
                    metadata = dict(result.metadata or {})
            else:
                result_text = result if isinstance(result, str) else "(no response)"
        else:
            # Inline Python plugin (BasePlugin). By default run in subprocess so a buggy plugin never crashes Core.
            tools_config = _get_tools_config()
            in_process_list = tools_config.get("run_plugin_in_process_plugins")
            run_in_process = isinstance(in_process_list, list) and (plugin_id in in_process_list)
            if run_in_process:
                # In-process: same as before (for plugins that need Core refs or are trusted)
                from base.base import PromptRequest
                try:
                    plugin.user_input = getattr(request, "text", "") or ""
                    try:
                        plugin.promptRequest = request.model_copy(deep=True)
                    except Exception:
                        plugin.promptRequest = PromptRequest(**request.model_dump())
                    r_out = _resolve_file_path(FILE_OUTPUT_SUBDIR, context, for_write=True)
                    if r_out:
                        full_out, base_for_validation = r_out
                        if base_for_validation is not None:
                            plugin.request_output_dir = full_out
                    if capability_id and capability:
                        method_name = capability.get("id") or capability_id
                        if hasattr(plugin, method_name):
                            old_config = getattr(plugin, "config", None) or {}
                            try:
                                plugin.config = {**old_config, **params}
                                method = getattr(plugin, method_name)
                                result_text = await method()
                            finally:
                                plugin.config = old_config
                        else:
                            result_text = f"Error: plugin has no capability {method_name}"
                    else:
                        result_text = await plugin.run()
                except Exception as e:
                    logger.exception("Inline plugin (in-process) failed: {}", e)
                    result_text = f"Error: {e!s}"
            else:
                # Subprocess: isolate plugin so it cannot crash Core
                timeout_sec = int(tools_config.get("run_plugin_timeout", 300) or 300)
                payload_obj = {
                    "plugin_id": plugin_id,
                    "capability_id": capability_id,
                    "parameters": params,
                    "request_text": (getattr(request, "text", None) or "").strip(),
                }
                r_out = _resolve_file_path(FILE_OUTPUT_SUBDIR, context, for_write=True)
                if r_out:
                    full_out, _ = r_out
                    if full_out is not None:
                        try:
                            payload_obj["output_dir"] = str(full_out.resolve())
                        except Exception:
                            pass  # do not crash Core on path resolve failure
                payload = json.dumps(payload_obj, ensure_ascii=False)
                try:
                    _proj_root = Path(__file__).resolve().parent.parent
                    _runner_script = Path(__file__).resolve().parent / "plugin_runner.py"
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable,
                        str(_runner_script),
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=str(_proj_root),
                    )
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(input=payload.encode("utf-8")),
                        timeout=timeout_sec,
                    )
                    out_str = (stdout or b"").decode("utf-8", errors="replace").strip()
                    try:
                        sub_result = json.loads(out_str) if out_str else {}
                    except (json.JSONDecodeError, TypeError):
                        sub_result = {"success": False, "error": out_str[:500] if out_str else "Plugin runner returned invalid JSON"}
                    if sub_result.get("success"):
                        result_text = (sub_result.get("text") or "").strip() or "(no output)"
                    else:
                        result_text = sub_result.get("error") or "Plugin subprocess failed"
                except asyncio.TimeoutError:
                    result_text = f"Error: plugin timed out after {timeout_sec}s"
                    try:
                        if proc is not None:
                            proc.kill()
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning("Plugin subprocess failed: {}", e)
                    result_text = f"Error: {e!s}"
        if result_text is None:
            # Plugin ran but returned no message; send fallback so user gets feedback (avoid "Handled by routing" with nothing else).
            fallback = "The action was completed."
            result_text = fallback
            if not cron_scheduled:
                try:
                    await core.send_response_to_request_channel(fallback, request)
                except Exception as send_err:
                    logger.warning("route_to_plugin: failed to send fallback message: {}", send_err)
                if _is_sync_inbound(request):
                    return fallback
                return ROUTING_RESPONSE_ALREADY_SENT
        # If plugin returned JSON with output_rel_path (e.g. ppt-generation saved to user/companion output), append open link (scope is dynamic per request: user id or 'companion')
        try:
            parsed = json.loads(result_text.strip()) if isinstance(result_text, str) else None
            if isinstance(parsed, dict) and parsed.get("success") and parsed.get("output_rel_path"):
                from core.result_viewer import build_file_view_link
                scope = _get_file_workspace_subdir(context)  # per-user or companion; same as resolution above
                path_rel = (parsed.get("output_rel_path") or "").strip()
                if path_rel and scope:
                    link, _ = build_file_view_link(scope, path_rel)
                    if link:
                        msg = (parsed.get("message") or "File saved.").strip()
                        result_text = f"{msg} Open: {link}"
        except (json.JSONDecodeError, TypeError):
            pass
        # Post-process with LLM if capability has post_process and post_process_prompt (only prompt + plugin output; no extra info)
        if capability and capability.get("post_process") and capability.get("post_process_prompt"):
            try:
                messages = [
                    {"role": "system", "content": (capability.get("post_process_prompt") or "").strip()},
                    {"role": "user", "content": result_text},
                ]
                refined = await core.openai_chat_completion(messages)
                if refined:
                    result_text = refined.strip()
            except Exception as e:
                logger.warning("Plugin post_process LLM failed: {}", e)
        # Save media to folder and send to channel (text + optional image/video/audio path)
        media_data_url = metadata.get("media") if isinstance(metadata.get("media"), str) else None
        if media_data_url and not cron_scheduled:
            try:
                meta = Util().get_core_metadata()
                ws_dir = get_workspace_dir(getattr(meta, "workspace_dir", None) or "config/workspace")
                media_base = Path(ws_dir) / "media" if ws_dir else None
                path, media_kind = save_data_url_to_media_folder(media_data_url, media_base)
                if path and media_kind:
                    kind_label = "Image" if media_kind == "image" else ("Video" if media_kind == "video" else "Audio")
                    path_line = f"\n\n{kind_label} saved to: {path}"
                    result_text = (result_text or "").strip() + path_line
                    await core.send_response_to_request_channel(
                        result_text,
                        request,
                        image_path=path if media_kind == "image" else None,
                        video_path=path if media_kind == "video" else None,
                        audio_path=path if media_kind == "audio" else None,
                    )
                else:
                    await core.send_response_to_request_channel(result_text, request)
            except Exception as e:
                logger.warning("route_to_plugin: save/send media failed: {}", e)
                await core.send_response_to_request_channel(result_text, request)
        elif not cron_scheduled:
            await core.send_response_to_request_channel(result_text, request)
        # When cron_scheduled: caller (cron task) will send result_text via TAM. Sync inbound: return text.
        if cron_scheduled:
            return result_text
        if _is_sync_inbound(request):
            return result_text
        return ROUTING_RESPONSE_ALREADY_SENT
    except BaseException as e:
        # Never break Core: catch all. Re-raise so process can exit on Ctrl+C / sys.exit
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        logger.exception(e)
        return f"Error running plugin: {e!s}"


def _is_sync_inbound(request: Any) -> bool:
    """True when request is from /inbound or /ws (host=inbound, port=0); response is returned directly, not via response_queue."""
    host = getattr(request, "host", None)
    port = getattr(request, "port", None)
    return host == "inbound" and (port in (0, "0") or port is None)


def register_routing_tools(registry: ToolRegistry, core: Any) -> None:
    """Register route_to_tam and route_to_plugin. Call when orchestrator_unified_with_tools is true (default)."""
    registry.register(
        ToolDefinition(
            name="route_to_tam",
            description="Route to TAM (time/scheduling) when time-related and too complex for remind_me/record_date/cron_schedule. Prefer: remind_me (one-shot), record_date (record event), cron_schedule (recurring) to avoid a second LLM parse.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_route_to_tam_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="route_to_plugin",
            description="Route this request to a specific plugin by plugin_id. Use when the user intent clearly matches one of the available plugins. You MUST call this tool (do not just reply 'I need some time' or 'working on it') — the user gets the result only when the plugin runs and returns. For PPT/slides/presentation: use plugin_id ppt-generation and capability create_from_source (parameters.source = user request or outline) or create_from_outline/create_presentation. For homeclaw-browser pass capability_id and parameters (e.g. node_id, url) when the user asks for photo, video, or browser.",
            parameters={
                "type": "object",
                "properties": {
                    "plugin_id": {"type": "string", "description": "The plugin id (e.g. homeclaw-browser, weather). Must match an available plugin."},
                    "capability_id": {"type": "string", "description": "The capability to call (e.g. node_camera_snap, node_camera_clip, browser_navigate, node_list). Required for homeclaw-browser when user asks for photo/video/URL/node; optional for plugins with a default run."},
                    "parameters": {"type": "object", "description": "Key-value parameters for the capability (e.g. node_id for camera/photo/video, url for browser_navigate). Required when capability_id is set."},
                },
                "required": ["plugin_id"],
            },
            execute_async=_route_to_plugin_executor,
        )
    )


async def _usage_report_executor(arguments: Dict[str, Any], context: ToolContext) -> str:
    """Return usage report: router stats (mix mode) + cloud usage. For calculating and reviewing cost."""
    try:
        from hybrid_router.metrics import generate_usage_report
        report = generate_usage_report(format="json")
        if not isinstance(report, dict):
            return str(report)
        lines = [
            f"Usage report (generated at {report.get('generated_at', '')})",
            "--- Summary ---",
            f"Total cloud requests: {report.get('summary', {}).get('total_cloud_requests', 0)}",
            f"Mix-mode requests: {report.get('summary', {}).get('mix_requests', 0)}",
            f"  Routed to local: {report.get('summary', {}).get('mix_routed_local', 0)}",
            f"  Routed to cloud: {report.get('summary', {}).get('mix_routed_cloud', 0)}",
            "--- Router (by layer) ---",
        ]
        by_layer = (report.get("router") or {}).get("by_layer") or {}
        for layer, count in by_layer.items():
            lines.append(f"  {layer}: {count}")
        lines.append("--- Raw (JSON) ---")
        lines.append(json.dumps(report, indent=2, ensure_ascii=False))
        return "\n".join(lines)
    except Exception as e:
        return f"Error generating report: {e}"


def _register_browser_tools_if_available(registry: ToolRegistry) -> None:
    """Register browser_* tools only if tools.browser_enabled and Playwright is installed. Otherwise skip so the model uses fetch_url only (no Chromium required)."""
    config = _get_tools_config()
    browser_enabled = config.get("browser_enabled", True)
    if not browser_enabled:
        logger.debug("Browser tools skipped (tools.browser_enabled=false). Use fetch_url for web content.")
        return
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        logger.info(
            "Browser tools skipped (Playwright not installed). Use fetch_url for web content. "
            "To enable browser: pip install playwright && python -m playwright install chromium"
        )
        return
    registry.register(
        ToolDefinition(
            name="browser_navigate",
            description="Open a URL in the shared browser session and return the page text. Use only when you need to click or type on the page; for reading content prefer fetch_url (no Chromium). Use browser_snapshot next for clickable elements, then browser_click or browser_type.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open."},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 50000).", "default": 50000},
                },
                "required": ["url"],
            },
            execute_async=_browser_navigate_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="browser_snapshot",
            description="Get interactive elements (buttons, links, inputs) on the current page with selectors. Use these selectors with browser_click or browser_type. Requires an open page (call browser_navigate first).",
            parameters={
                "type": "object",
                "properties": {
                    "screenshot": {"type": "boolean", "description": "If true, take a screenshot and return its path.", "default": False},
                },
                "required": [],
            },
            execute_async=_browser_snapshot_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="browser_click",
            description="Click an element on the current page. Use selector from browser_snapshot.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the element to click (from browser_snapshot)."},
                },
                "required": ["selector"],
            },
            execute_async=_browser_click_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="browser_type",
            description="Type text into an input or textarea on the current page. Use selector from browser_snapshot. Clears the field first.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the input/textarea."},
                    "text": {"type": "string", "description": "Text to type."},
                },
                "required": ["selector", "text"],
            },
            execute_async=_browser_type_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="web_search_browser",
            description="Search Google, Bing, or Baidu using the browser (no API key). Use when you want Google/Bing/Baidu results and have no API key. Fragile: may break on CAPTCHA or HTML changes. Prefer web_search with provider duckduckgo (no key) or google_cse/bing (free tier) when possible.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "engine": {"type": "string", "description": "google (default), bing, or baidu.", "default": "google"},
                    "count": {"type": "integer", "description": "Max results (default 5, max 10).", "default": 5},
                },
                "required": ["query"],
            },
            execute_async=_web_search_browser_executor,
        )
    )


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools. Call once at startup (e.g. from Core)."""
    # Session tools
    registry.register(
        ToolDefinition(
            name="sessions_transcript",
            description="Get the conversation transcript for the current session (or a given session_id). Returns a list of messages with role, content, and timestamp.",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Optional session id; if omitted, uses current session."},
                    "limit": {"type": "integer", "description": "Max number of turns to return (default 20).", "default": 20},
                },
                "required": [],
            },
            execute_async=_sessions_transcript_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="sessions_list",
            description="List chat sessions for the current app/user. Returns session_id, app_id, user_name, user_id, created_at.",
            parameters={
                "type": "object",
                "properties": {
                    "app_id": {"type": "string", "description": "Optional app id; if omitted, uses current."},
                    "user_name": {"type": "string", "description": "Optional user name filter."},
                    "user_id": {"type": "string", "description": "Optional user id filter."},
                    "limit": {"type": "integer", "description": "Max sessions to return (default 20).", "default": 20},
                },
                "required": [],
            },
            execute_async=_sessions_list_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="sessions_send",
            description="Send a message to another session and get that session's agent reply. Use session_id (from sessions_list) or app_id + user_id to target. Returns the reply from the target session.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to send to the target session (or use 'text')."},
                    "text": {"type": "string", "description": "Alias for message."},
                    "session_id": {"type": "string", "description": "Target session id (from sessions_list)."},
                    "session_key": {"type": "string", "description": "Alias for session_id."},
                    "app_id": {"type": "string", "description": "Target app_id (use with user_id if no session_id)."},
                    "user_id": {"type": "string", "description": "Target user_id (use with app_id if no session_id)."},
                    "user_name": {"type": "string", "description": "Optional target user name."},
                    "timeout_seconds": {"type": "number", "description": "Max seconds to wait for reply (default 60).", "default": 60},
                },
                "required": ["message"],
            },
            execute_async=_sessions_send_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="sessions_spawn",
            description="Sub-agent run: run a one-off task and get the model reply. Select model by llm_name (ref from models_list) or capability (e.g. 'Chat' — selects a model that has that capability in config). Omit both to use main_llm.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The question or instruction for the sub-agent (one-off run)."},
                    "message": {"type": "string", "description": "Alias for task."},
                    "text": {"type": "string", "description": "Alias for task."},
                    "llm_name": {"type": "string", "description": "Optional. Model ref (e.g. local_models/<id> or cloud_models/<id>) from models_list. Omit to use main_llm or capability."},
                    "capability": {"type": "string", "description": "Optional. Select model by capability from config (e.g. 'Chat'). Use models_list to see model_details.capabilities. If set, overrides llm_name; system picks a model that has this capability."},
                },
                "required": ["task"],
            },
            execute_async=_sessions_spawn_executor,
        )
    )

    registry.register(
        ToolDefinition(
            name="channel_send",
            description="Send an additional message to the channel that last sent a request (same conversation channel). Use when you want to send more than one continuous message to the user in that channel. Works with full channels (async delivery); for sync /inbound the client only gets one response per request.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Message text to send to the user's channel."},
                    "message": {"type": "string", "description": "Alias for text."},
                },
                "required": [],
            },
            execute_async=_channel_send_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="usage_report",
            description="Get the current usage report: hybrid router stats (mix mode) and cloud model request counts. Use when the user asks for cost, usage, or how many requests went to cloud vs local. Returns summary and by-layer breakdown.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_usage_report_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="run_skill",
            description="Run a script from a skill's scripts/ folder, or confirm an instruction-only skill. Use when a skill has a scripts/ directory: pass skill_name and script (e.g. run.sh, main.py). For instruction-only skills (no scripts/): call run_skill(skill_name=<name>) with no script; the tool will confirm the skill—then you MUST continue in the same turn: follow the skill's steps (e.g. document_read, generate content, file_write or save_result_page to output/) and return the link to the user. Do not reply with only the confirmation message. skill_name can be folder name (e.g. html-slides-1.0.0) or short name (html-slides, html slides).",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Skill name: folder name or short name (e.g. html-slides, html slides, linkedin-writer-1.0.0)."},
                    "skill": {"type": "string", "description": "Alias for skill_name."},
                    "script": {"type": "string", "description": "Script filename or path relative to the skill's scripts/ folder (e.g. run.sh, main.py, index.js). Omit for instruction-only skills."},
                    "script_name": {"type": "string", "description": "Alias for script."},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Optional list of arguments to pass to the script."},
                },
                "required": ["skill_name"],
            },
            execute_async=_run_skill_executor,
        )
    )

    # Time / system
    registry.register(
        ToolDefinition(
            name="time",
            description="Get current date and time (system local, ISO format). Use when you need precise current time for age calculation, 'what day is it?', or scheduling. Returns same timezone as the system context injected in the prompt.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_time_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="cron_schedule",
            description="Schedule a reminder, a skill, a plugin, or a tool at cron times. Use cron_expr (5 fields: minute hour day month weekday), e.g. '0 7 * * *' = daily at 7:00. task_type 'message' (default): send a fixed message. task_type 'run_tool': run a tool (e.g. web_search) and send its output — use for 'search the latest sports news every 7 am' with tool_name=web_search, tool_arguments={query: 'latest sports news', count: 10}. Do NOT use run_plugin headlines for 'search'. task_type 'run_skill': run a skill script. task_type 'run_plugin': run a plugin (e.g. headlines for top headlines from News API) — use for 'top 5 headlines every 8 am' or 'headlines about sports every 8 am', not for 'search'. Use post_process_prompt to refine output. Optional: tz, delivery_target.",
            parameters={
                "type": "object",
                "properties": {
                    "cron_expr": {"type": "string", "description": "Cron expression (e.g. '0 9 * * *' for daily at 9:00)."},
                    "task_type": {"type": "string", "description": "One of: 'message' (fixed message), 'run_tool' (run tool e.g. web_search for 'search news every 7 am'), 'run_skill' (run skill script), 'run_plugin' (run plugin e.g. headlines for 'top headlines every 8 am'). Default 'message'.", "default": "message"},
                    "message": {"type": "string", "description": "For message: text to send. For run_skill/run_plugin: optional label.", "default": "Scheduled reminder"},
                    "skill_name": {"type": "string", "description": "Required when task_type is run_skill. Skill folder name (e.g. weather-1.0.0)."},
                    "script": {"type": "string", "description": "Required when task_type is run_skill. Script name under skill (e.g. get_weather.py)."},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "When task_type is run_skill: args for the script (e.g. ['Beijing'])."},
                    "tool_name": {"type": "string", "description": "Required when task_type is run_tool. Tool name (e.g. web_search). Use for 'search the latest sports news every 7 am' with tool_arguments={query: 'latest sports news', count: 10}."},
                    "tool_arguments": {"type": "object", "description": "When task_type is run_tool: arguments for the tool (e.g. for web_search: {query: 'latest sports news', count: 10})."},
                    "plugin_id": {"type": "string", "description": "Required when task_type is run_plugin. Plugin id (e.g. headlines for top headlines from News API). Do NOT use for 'search news' — use run_tool web_search instead."},
                    "capability_id": {"type": "string", "description": "Optional when task_type is run_plugin. Capability to call (e.g. fetch_headlines for headlines)."},
                    "parameters": {"type": "object", "description": "When task_type is run_plugin: key-value parameters for the capability (e.g. for headlines: category, page_size, sources, language)."},
                    "post_process_prompt": {"type": "string", "description": "Optional. For run_skill or run_plugin: system prompt for LLM to refine output before sending (e.g. 'Summarize in 2 sentences.')."},
                    "tz": {"type": "string", "description": "Optional timezone (e.g. America/New_York, Europe/London). Server local if omitted."},
                    "delivery_target": {"type": "string", "description": "Where to deliver: 'latest' (default) or 'session' (this channel).", "default": "latest"},
                },
                "required": ["cron_expr"],
            },
            execute_async=_cron_schedule_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="cron_list",
            description="List all recurring (cron) reminders: job_id, message, cron_expr, next_run, enabled, last_run_at, last_status, delivery_target. Use so the user can see their recurring reminders and choose which to remove or disable (cron_remove, cron_update).",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_cron_list_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="cron_remove",
            description="Remove a recurring (cron) reminder by job_id. Get job_id from cron_list (user can say which to remove by message, e.g. 'the 9am pills reminder').",
            parameters={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job id from cron_list."}},
                "required": ["job_id"],
            },
            execute_async=_cron_remove_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="cron_update",
            description="Enable or disable a cron job by job_id. Get job_id from cron_list. Use enabled=false to pause, enabled=true to resume.",
            parameters={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job id from cron_list."},
                    "enabled": {"type": "boolean", "description": "True to enable, false to disable (pause) the job."},
                },
                "required": ["job_id", "enabled"],
            },
            execute_async=_cron_update_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="cron_run",
            description="Run a cron job once immediately (force run). Use cron_list to get job_ids.",
            parameters={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job id from cron_list."}},
                "required": ["job_id"],
            },
            execute_async=_cron_run_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="cron_status",
            description="Return cron scheduler status: scheduler_enabled, next_wake_at, jobs_count. For UI or debugging.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_cron_status_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="remind_me",
            description="Schedule a one-shot reminder. Use for 'remind me in 5 minutes' or 'remind me tomorrow at 9am'. No second LLM; supply minutes (e.g. 5) or at_time (YYYY-MM-DD HH:MM:SS).",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Reminder message to show at the scheduled time.", "default": "Reminder"},
                    "minutes": {"type": "integer", "description": "Remind in this many minutes (e.g. 5 for 'in 5 minutes'). Omit if using at_time."},
                    "at_time": {"type": "string", "description": "Remind at this time: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD. Omit if using minutes."},
                },
                "required": ["message"],
            },
            execute_async=_remind_me_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="record_date",
            description="Record a date/event for future reference. Use for: 'Tomorrow is national holiday', 'Girlfriend birthday in two weeks'. Optional inference: if user may want a reminder, pass event_date (YYYY-MM-DD, compute from 'when') and remind_on ('day_before' or 'on_day') to schedule a reminder; remind_message overrides default text.",
            parameters={
                "type": "object",
                "properties": {
                    "event_name": {"type": "string", "description": "Name of the event (e.g. 'Spring Festival', 'Girlfriend birthday')."},
                    "when": {"type": "string", "description": "When: 'tomorrow', 'in two weeks', 'in two months', or a date string."},
                    "note": {"type": "string", "description": "Optional note.", "default": ""},
                    "event_date": {"type": "string", "description": "Optional. Resolved date YYYY-MM-DD (compute from 'when' for reminders). Required if remind_on is set."},
                    "remind_on": {"type": "string", "description": "Optional. 'day_before' = remind day before event; 'on_day' = remind on event day at 9am. Requires event_date."},
                    "remind_message": {"type": "string", "description": "Optional. Custom reminder message (e.g. 'Don't forget: girlfriend birthday tomorrow!').", "default": ""},
                },
                "required": ["event_name", "when"],
            },
            execute_async=_record_date_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="recorded_events_list",
            description="List recorded dates/events (from record_date). Use when user asks 'what is coming up?' or 'what did I record?'.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_recorded_events_list_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="session_status",
            description="Get current session info: session_id, app_id, user_name, user_id.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_session_status_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="profile_get",
            description="Get the current user's stored profile (learned facts: name, birthday, preferences, families, etc.). Returns specific keys if 'keys' is provided (comma-separated). Per-user.",
            parameters={
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "Optional comma-separated keys to return (e.g. 'name,birthday'). If omitted, returns full profile."},
                },
                "required": [],
            },
            execute_async=_profile_get_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="profile_update",
            description="Update the current user's profile with facts they told you (e.g. name, birthday, favorite_foods, families, dietary restrictions). Use when the user says 'my name is X', 'remember I like Y', 'I'm allergic to Z', etc. Pass updates as key-value pairs. Use remove_keys to forget specific keys. Per-user.",
            parameters={
                "type": "object",
                "properties": {
                    "updates": {"type": "object", "description": "Key-value map to merge into profile (e.g. {\"name\": \"Alice\", \"birthday\": \"1990-01-15\"})."},
                    "remove_keys": {"type": "array", "items": {"type": "string"}, "description": "Keys to remove from profile (e.g. ['old_job'])."},
                    "name": {"type": "string", "description": "Shortcut: set name."},
                    "birthday": {"type": "string", "description": "Shortcut: set birthday."},
                },
                "required": [],
            },
            execute_async=_profile_update_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="profile_list",
            description="List what we know about the current user (profile keys and a short preview). Use when the user asks 'what do you know about me?' or to show stored facts. Per-user.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_profile_list_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="memory_search",
            description="Search stored memories (RAG). Returns relevant past snippets. Use when user asks what we remember or to recall context. Only works when use_memory is enabled.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g. 'user preferences', 'meeting with John')."},
                    "limit": {"type": "integer", "description": "Max results (default 10, max 50).", "default": 10},
                },
                "required": ["query"],
            },
            execute_async=_memory_search_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="memory_get",
            description="Get a single memory by id (from memory_search results). Only works when use_memory is enabled.",
            parameters={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "Memory id (or use id)."},
                    "id": {"type": "string", "description": "Alias for memory_id."},
                },
                "required": [],
            },
            execute_async=_memory_get_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="append_agent_memory",
            description="Append a note to the curated long-term memory file (AGENT_MEMORY.md). Use when the user says 'remember this' or to store important facts/preferences. This file is authoritative over RAG when both mention the same fact. Only works when use_agent_memory_file is true in config.",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Markdown to append. Recommended: one fact per paragraph; optional date prefix (YYYY-MM-DD: ...) or ## headings for grouping."},
                },
                "required": ["content"],
            },
            execute_async=_append_agent_memory_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="append_daily_memory",
            description="Append a note to today's daily memory file (memory/YYYY-MM-DD.md). Use for short-term notes that help avoid filling the context window; loaded as 'Recent (daily memory)' together with yesterday's file. Only works when use_daily_memory is true in config.",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Markdown to append. Recommended: one note per paragraph; optional bullet and label (e.g. '- **Session:** ...') for clarity."},
                },
                "required": ["content"],
            },
            execute_async=_append_daily_memory_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="agent_memory_search",
            description="Semantically search AGENT_MEMORY.md and daily memory (memory/YYYY-MM-DD.md). Use before agent_memory_get to pull only relevant parts. Returns path, start_line, end_line, snippet, score. Only works when use_agent_memory_search is true in config.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g. user preferences, past decisions, dates)."},
                    "max_results": {"type": "integer", "description": "Max results to return (default 10, max 50).", "default": 10},
                    "min_score": {"type": "number", "description": "Optional minimum similarity score (0-1) to include."},
                },
                "required": ["query"],
            },
            execute_async=_agent_memory_search_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="agent_memory_get",
            description="Read a snippet from AGENT_MEMORY.md or memory/YYYY-MM-DD.md by path. Use after agent_memory_search to load only the needed lines. path: e.g. AGENT_MEMORY.md or memory/2025-02-16.md; optional from_line and lines for a range. Only works when use_agent_memory_search is true in config.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path: AGENT_MEMORY.md or memory/YYYY-MM-DD.md."},
                    "from_line": {"type": "integer", "description": "Optional 1-based start line."},
                    "lines": {"type": "integer", "description": "Optional number of lines to return."},
                },
                "required": ["path"],
            },
            execute_async=_agent_memory_get_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="web_search",
            description="Search the web (generic). Use for 'search the web', 'search for X', 'search the latest sports news'. For 'search the latest sports news every 7 am' use cron_schedule with task_type=run_tool, tool_name=web_search, tool_arguments={query: 'latest sports news', count: 10} — do NOT use run_plugin headlines. Free (no key): duckduckgo. Free tier: google_cse, bing, tavily. Set provider in config; pass search_type for Brave, engine for SerpAPI.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "count": {"type": "integer", "description": "Number of results (default 5; max 20).", "default": 5},
                    "search_type": {"type": "string", "description": "Brave only: web (default), news, video, image.", "default": "web"},
                    "engine": {"type": "string", "description": "SerpAPI only: google (default), bing, baidu.", "default": "google"},
                },
                "required": ["query"],
            },
            execute_async=_web_search_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="tavily_extract",
            description="Extract content from one or more URLs using Tavily Extract. Use when the user wants to read or summarize specific web pages (by URL). Requires TAVILY_API_KEY or tools.web.search.tavily.api_key (same as web_search).",
            parameters={
                "type": "object",
                "properties": {
                    "urls": {"type": "string", "description": "Comma- or space-separated list of URLs to extract (max 20)."},
                    "url": {"type": "string", "description": "Single URL (alternative to urls)."},
                    "query": {"type": "string", "description": "Optional: user intent for reranking chunks; when provided, chunks_per_source applies."},
                    "extract_depth": {"type": "string", "description": "basic (default) or advanced.", "default": "basic"},
                    "format": {"type": "string", "description": "markdown (default) or text.", "default": "markdown"},
                    "chunks_per_source": {"type": "integer", "description": "When query is set: 1-5 chunks per URL (default 3)."},
                },
                "required": [],
            },
            execute_async=_tavily_extract_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="tavily_crawl",
            description="Crawl a website from a base URL using Tavily Crawl. Use when the user wants to explore or map a site (e.g. 'crawl this docs site'). Requires TAVILY_API_KEY or tools.web.search.tavily.api_key.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Root URL to start the crawl (e.g. docs.example.com)."},
                    "instructions": {"type": "string", "description": "Optional: natural language instructions for the crawler (e.g. 'Find all pages about API')."},
                    "max_depth": {"type": "integer", "description": "Max depth 1-5 (default 1).", "default": 1},
                    "max_breadth": {"type": "integer", "description": "Max links per page 1-500 (default 20).", "default": 20},
                    "limit": {"type": "integer", "description": "Total links to process (default 50).", "default": 50},
                    "extract_depth": {"type": "string", "description": "basic (default) or advanced.", "default": "basic"},
                    "format": {"type": "string", "description": "markdown (default) or text.", "default": "markdown"},
                },
                "required": ["url"],
            },
            execute_async=_tavily_crawl_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="tavily_research",
            description="Run a deep research task on a topic using Tavily Research. Use when the user wants a comprehensive report (e.g. 'research X', 'write a report on Y'). Creates a task and polls until done; returns content and sources. Requires TAVILY_API_KEY or tools.web.search.tavily.api_key.",
            parameters={
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Research question or topic (or use query/question)."},
                    "query": {"type": "string", "description": "Alias for input."},
                    "question": {"type": "string", "description": "Alias for input."},
                    "model": {"type": "string", "description": "mini (targeted) | pro (comprehensive) | auto (default).", "default": "auto"},
                    "max_wait_seconds": {"type": "integer", "description": "Max time to wait for completion (default 120).", "default": 120},
                    "poll_interval_seconds": {"type": "integer", "description": "Poll interval (default 5).", "default": 5},
                },
                "required": [],
            },
            execute_async=_tavily_research_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="models_list",
            description="List available model refs and main_llm. For sessions_spawn: omit llm_name to use main_llm; to use a different model pass one ref from the list — prefer a smaller/faster one (e.g. 7B in the id) for quick sub-tasks.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_models_list_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="agents_list",
            description="List agent ids. In HomeClaw returns single-agent note.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_agents_list_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="image",
            description="Analyze an image with the vision/multimodal model. Provide image as path (relative to homeclaw_root) or url, and optional prompt (e.g. 'What is in this image?'). Requires a vision-capable LLM.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to image file (or use 'image')."},
                    "image": {"type": "string", "description": "Alias for path."},
                    "url": {"type": "string", "description": "URL of image (alternative to path)."},
                    "prompt": {"type": "string", "description": "Question or instruction for the vision model (default: Describe the image).", "default": "Describe the image."},
                },
                "required": [],
            },
            execute_async=_image_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo back the given text. Useful for testing.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string", "description": "Text to echo back."}},
                "required": ["text"],
            },
            execute_async=_echo_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="platform_info",
            description="Get platform info: Python version, system (Darwin/Linux/Windows), machine.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_platform_info_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="cwd",
            description="Get current working directory of the Core process.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_cwd_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="env",
            description="Get the value of an environment variable (read-only).",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Environment variable name."}},
                "required": ["name"],
            },
            execute_async=_env_executor,
        )
    )

    # Exec (allowlist in config)
    registry.register(
        ToolDefinition(
            name="exec",
            description="Run a shell command. Only commands in the allowlist (config: tools.exec_allowlist) are allowed. Set background=true to run in background and get job_id; use process_list/process_poll/process_kill with that job_id.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run (e.g. 'date' or 'ls -la'). First token must be in allowlist."},
                    "background": {"type": "boolean", "description": "If true, run in background and return job_id for process_poll/process_kill.", "default": False},
                },
                "required": ["command"],
            },
            execute_async=_exec_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="process_list",
            description="List background exec jobs (job_id, command, started_at, status). Use after exec with background=true.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute_async=_process_list_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="process_poll",
            description="Poll a background job: get output and returncode when done, or status running. Use job_id from exec(background=true) or process_list.",
            parameters={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job id from exec(background=true) or process_list."}},
                "required": ["job_id"],
            },
            execute_async=_process_poll_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="process_kill",
            description="Kill a background job by job_id.",
            parameters={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Job id to kill."}},
                "required": ["job_id"],
            },
            execute_async=_process_kill_executor,
        )
    )

    # File read (base path in config)
    registry.register(
        ToolDefinition(
            name="file_read",
            description="Read contents of a file. When the user asks about a file by name (e.g. 1.pdf), use the path from folder_list or file_find that matches that name (e.g. path '1.pdf'); do not use a different file or output/ path. Default base: user sandbox; use path 'share/...' when user says share.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to user's private folder (e.g. 'file.txt', 'subdir/file.txt'). Use 'share/filename' when user says share."},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default from config tools.file_read_max_chars, or 32000).", "default": 32000},
                },
                "required": ["path"],
            },
            execute_async=_file_read_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="document_read",
            description="Read document content from PDF, PPT, Word, MD, HTML, XML, JSON, Excel, and more. When the user asks about a file by name (e.g. 1.pdf), use the path from folder_list or file_find that matches that name (e.g. path '1.pdf'); do not use a different file or a path under output/. Default base: user sandbox; use path 'share/...' when user says share. For long files, increase max_chars or ask for section-by-section summary.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to user's private folder (e.g. report.pdf). Use 'share/filename' when user says share."},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default from config tools.file_read_max_chars, or 64000).", "default": 64000},
                },
                "required": ["path"],
            },
            execute_async=_document_read_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="file_understand",
            description="Classify a file as image, audio, video, or document and return type + path. For documents, returns extracted text (same as document_read). For image/audio/video, returns type and path; use image_analyze(path) for images if the user asks to describe. Default base: user's private folder; use path 'share/...' only when the user says share folder.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to user's private folder. Use 'share/filename' when user says share."},
                    "max_chars": {"type": "integer", "description": "Max characters to extract for documents (default from config).", "default": 64000},
                },
                "required": ["path"],
            },
            execute_async=_file_understand_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="file_write",
            description="Write content to a file. Default base: user's private folder (homeclaw_root/{user_id}). Use path '.' or a path under it; use path 'share/...' only when the user says share folder.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to user's private folder. Use 'share/filename' when user says share."},
                    "content": {"type": "string", "description": "Content to write."},
                },
                "required": ["path", "content"],
            },
            execute_async=_file_write_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="file_edit",
            description="Replace old_string with new_string in a file. Default base: user's private folder; use path 'share/...' only when the user says share folder. Use replace_all=true to replace all occurrences.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to user's private folder. Use 'share/filename' when user says share."},
                    "old_string": {"type": "string", "description": "String to replace."},
                    "new_string": {"type": "string", "description": "Replacement string."},
                    "replace_all": {"type": "boolean", "description": "If true, replace all occurrences; else first only.", "default": False},
                },
                "required": ["path", "old_string", "new_string"],
            },
            execute_async=_file_edit_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="apply_patch",
            description="Apply a unified diff patch to a file. Patch should be a single-file unified diff (---/+++ and @@ hunks). Path in patch is relative to user's private folder; use 'share/...' when user says share folder. Provide patch or content.",
            parameters={
                "type": "object",
                "properties": {
                    "patch": {"type": "string", "description": "Unified diff patch content (or use content)."},
                    "content": {"type": "string", "description": "Alias for patch."},
                },
                "required": [],
            },
            execute_async=_apply_patch_executor,
        )
    )

    # Folder / file explore
    registry.register(
        ToolDefinition(
            name="folder_list",
            description="List contents of a directory (files and subdirectories). Sandbox: only two bases are the search path and working area — (1) user sandbox root and its subfolders (path '.' or 'subdir'); (2) share and its subfolders (path 'share' or 'share/...'). Any other folder cannot be accessed. Use when the user asks what files are in their directory. The returned 'path' is what to pass to file_read/document_read.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the directory (use '.' for the user's base directory).", "default": "."},
                    "max_entries": {"type": "integer", "description": "Max entries to return (default 500).", "default": 500},
                },
                "required": [],
            },
            execute_async=_folder_list_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="file_find",
            description="Find files or folders by name pattern (glob). Sandbox: only two bases are accessible — (1) user sandbox root and subfolders (path '.' or 'subdir'); (2) share and subfolders (path 'share' or 'share/...'). Any other folder cannot be accessed. E.g. file_find(path='.', pattern='*.pdf'). Use the returned path with file_read/document_read.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern for name (e.g. '*.pdf', '*notes*'). Default '*' lists all.", "default": "*"},
                    "path": {"type": "string", "description": "Directory to search: '.' = user's private folder (default); 'share' = shared folder when user says share.", "default": "."},
                    "max_results": {"type": "integer", "description": "Max results to return (default 200).", "default": 200},
                },
                "required": [],
            },
            execute_async=_file_find_executor,
        )
    )

    # Web: fetch_url (lightweight, no Chromium) is always available. Browser tools only if enabled and Playwright installed.
    registry.register(
        ToolDefinition(
            name="fetch_url",
            description="Fetch a URL and return the page content as plain text (HTML stripped). Prefer this for reading web pages; no Chromium or JavaScript. Use web_search for search. Use browser_navigate only when you need to click or type on the page (requires Playwright).",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch (e.g. https://example.com)."},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 40000).", "default": 40000},
                },
                "required": ["url"],
            },
            execute_async=_fetch_url_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="web_extract",
            description="Extract main content from one or more URLs using free Python libs (trafilatura or BeautifulSoup). No API key. Use when you have specific URLs to read or summarize. Prefer over fetch_url for article-style pages. Optional: pip install trafilatura (better) or beautifulsoup4.",
            parameters={
                "type": "object",
                "properties": {
                    "urls": {"type": "string", "description": "Comma- or space-separated list of URLs to extract."},
                    "url": {"type": "string", "description": "Single URL (alternative to urls)."},
                    "max_chars": {"type": "integer", "description": "Max characters per page (default 60000).", "default": 60000},
                    "max_urls": {"type": "integer", "description": "Max URLs to process (default 10, max 20).", "default": 10},
                },
                "required": [],
            },
            execute_async=_web_extract_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="web_crawl",
            description="Crawl from a start URL: fetch pages, follow links up to max_pages and max_depth. Free; no API key. Uses same extract as web_extract. Use when the user wants to explore or map a site. same_domain_only=true (default) limits to same domain.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Start URL (root to crawl)."},
                    "start_url": {"type": "string", "description": "Alias for url."},
                    "max_pages": {"type": "integer", "description": "Max pages to fetch (default 10, max 50).", "default": 10},
                    "max_depth": {"type": "integer", "description": "Max link depth (default 2, max 5).", "default": 2},
                    "same_domain_only": {"type": "boolean", "description": "Only follow links on same domain (default true).", "default": True},
                    "max_chars": {"type": "integer", "description": "Max characters per page (default 30000).", "default": 30000},
                },
                "required": [],
            },
            execute_async=_web_crawl_executor,
        )
    )
    _register_browser_tools_if_available(registry)

    # HTTP request (generic API) and webhook
    registry.register(
        ToolDefinition(
            name="http_request",
            description="Send an HTTP request (GET, POST, PUT, PATCH, DELETE). Use for REST APIs: read data (GET), create/update (POST/PUT/PATCH), delete (DELETE). Optional headers (e.g. Authorization: Bearer <token>).",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL (e.g. https://api.example.com/items)."},
                    "method": {"type": "string", "description": "HTTP method: GET, POST, PUT, PATCH, DELETE. Default GET.", "default": "GET"},
                    "headers": {"type": "object", "description": "Optional headers as JSON object (e.g. {\"Authorization\": \"Bearer <token>\", \"Content-Type\": \"application/json\"})."},
                    "body": {"type": "string", "description": "Optional request body (JSON string or object for POST/PUT/PATCH)."},
                    "timeout": {"type": "number", "description": "Request timeout in seconds (default 30).", "default": 30},
                    "max_response_chars": {"type": "integer", "description": "Max response body length to return (default 8000).", "default": 8000},
                },
                "required": ["url"],
            },
            execute_async=_http_request_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="webhook_trigger",
            description="Send an HTTP POST request to a URL (webhook). Optional JSON body. For full REST (GET/PUT/DELETE, headers) use http_request.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to POST to."},
                    "body": {"type": "string", "description": "Optional JSON body as string."},
                },
                "required": ["url"],
            },
            execute_async=_webhook_trigger_executor,
        )
    )

    # Knowledge base (when core.knowledge_base.enabled): search, add, remove by source_id
    registry.register(
        ToolDefinition(
            name="knowledge_base_search",
            description="Search the user's personal knowledge base (saved documents, web snippets, URLs). Use when the user asks about something they may have saved earlier. Returns relevant chunks; only available when knowledge base is enabled.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (natural language or keywords)."},
                    "limit": {"type": "integer", "description": "Max results to return (default 5, max 20).", "default": 5},
                },
                "required": ["query"],
            },
            execute_async=_knowledge_base_search_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="knowledge_base_add",
            description="Add content to the user's knowledge base. Only use when the user explicitly asks to save or remember this content (e.g. 'add this to my knowledge base', 'save this for later'). Do not auto-add every document_read or web result. Provide source_type (e.g. document, web, url) and optional source_id to remove or update later.",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Text to add (will be chunked and embedded)."},
                    "source_type": {"type": "string", "description": "Origin: document, web, url, user, etc. Default user.", "default": "user"},
                    "source_id": {"type": "string", "description": "Unique id for this source (e.g. path or URL); used to remove later. Auto-generated if omitted."},
                    "metadata": {"type": "object", "description": "Optional key-value metadata (if supported)."},
                },
                "required": ["content"],
            },
            execute_async=_knowledge_base_add_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="knowledge_base_remove",
            description="Remove all entries for a given source from the user's knowledge base. Use source_id that was used when adding (e.g. file path or URL).",
            parameters={
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "Source id to remove (same as used in knowledge_base_add)."},
                },
                "required": ["source_id"],
            },
            execute_async=_knowledge_base_remove_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="knowledge_base_list",
            description="List documents/sources saved in the user's knowledge base, or check if a specific document is saved. Use when the user asks 'was this saved?', 'what do I have in my knowledge base?', or 'is this document in my KB?'. Pass source_id to check a specific document (e.g. file path or URL used when adding).",
            parameters={
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "Optional. If provided, returns whether this document/source is in the knowledge base (in_knowledge_base: true/false). Use the same id as when adding (e.g. file path or URL)."},
                    "limit": {"type": "integer", "description": "Max number of sources to return when listing all (default 100, max 500).", "default": 100},
                },
                "required": [],
            },
            execute_async=_knowledge_base_list_executor,
        )
    )

    # Save result as page; returns link. Markdown (.md) for chat display; HTML (.html) for long/complex reports.
    registry.register(
        ToolDefinition(
            name="save_result_page",
            description="Save the result as a page and get a shareable link. **format=markdown:** Saves as .md; the tool returns the content so the companion app can display it directly in chat (include the returned content in your reply). **format=html:** Saves as .html; the tool returns only the link—share that link with the user so they can open the page in a browser. For html slide requests use format='html' and full HTML content. Link when auth_api_key is set.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the result page (e.g. 'Summary', 'Report')."},
                    "content": {"type": "string", "description": "The full result content — exact same content you generated. Use clean text so the page displays correctly."},
                    "format": {"type": "string", "description": "markdown: content is returned for companion to display in chat. html: only the view link is returned for the user to open in browser.", "default": "markdown"},
                },
                "required": ["title", "content"],
            },
            execute_async=_save_result_page_executor,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_file_view_link",
            description="Get a view link for a file already saved under output/ (e.g. output/report_xxx.html). Use when the user asks for the link (e.g. 'send me the link', '能把链接发给我') after a file was saved. Pass the same path that was used when saving (e.g. from the previous file_write or save_result_page result).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path under output/, e.g. output/allen_resume_slides.html (same as in the save result)."},
                },
                "required": ["path"],
            },
            execute_async=_get_file_view_link_executor,
        )
    )
