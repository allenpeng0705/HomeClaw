"""
Plugin API routes: register, unregister, health, llm/generate, memory/add, memory/search, plugin-ui.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from base.base import ExternalPluginRegisterRequest, PluginLLMGenerateRequest


def get_api_plugins_register_handler(core):
    """Return handler for POST /api/plugins/register."""
    async def api_plugins_register(body: ExternalPluginRegisterRequest):
        try:
            descriptor = body.model_dump()
            descriptor["id"] = descriptor.get("plugin_id") or descriptor.get("id")
            plugin_id = core.plugin_manager.register_external_via_api(descriptor)
            return JSONResponse(content={"plugin_id": plugin_id, "registered": True})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"detail": str(e), "registered": False})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e), "registered": False})
    return api_plugins_register


def get_api_plugins_unregister_handler(core):
    """Return handler for POST /api/plugins/unregister."""
    async def api_plugins_unregister(request: Request):
        try:
            data = await request.json()
            plugin_id = (data or {}).get("plugin_id") or ""
            if not plugin_id:
                return JSONResponse(status_code=400, content={"detail": "plugin_id is required"})
            removed = core.plugin_manager.unregister_external_plugin(plugin_id)
            return JSONResponse(content={"removed": removed, "plugin_id": plugin_id})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_plugins_unregister


def get_api_plugins_unregister_all_handler(core):
    """Return handler for POST /api/plugins/unregister-all."""
    async def api_plugins_unregister_all():
        try:
            removed = core.plugin_manager.unregister_all_external_plugins()
            return JSONResponse(content={"removed": removed, "count": len(removed)})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_plugins_unregister_all


def get_api_plugins_health_handler(core):
    """Return handler for GET /api/plugins/health/{plugin_id}."""
    async def api_plugins_health(plugin_id: str):
        plug = core.plugin_manager.get_plugin_by_id(plugin_id)
        if plug is None or not isinstance(plug, dict):
            return JSONResponse(status_code=404, content={"detail": "Plugin not found", "ok": False})
        ok = await core.plugin_manager.check_plugin_health(plug)
        return JSONResponse(content={"ok": ok, "plugin_id": plugin_id})
    return api_plugins_health


def get_api_plugins_llm_generate_handler(core):
    """Return handler for POST /api/plugins/llm/generate."""
    async def api_plugins_llm_generate(body: PluginLLMGenerateRequest):
        try:
            messages = getattr(body, "messages", None) or []
            if not messages or not isinstance(messages, list):
                return JSONResponse(status_code=400, content={"error": "messages (list) is required", "text": ""})
            llm_name = getattr(body, "llm_name", None)
            text = await core.openai_chat_completion(messages, llm_name=llm_name)
            if text is None:
                return JSONResponse(status_code=502, content={"error": "LLM returned no response", "text": ""})
            return JSONResponse(content={"text": text})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"error": str(e), "text": ""})
    return api_plugins_llm_generate


def get_api_plugins_memory_add_handler(core):
    """Return handler for POST /api/plugins/memory/add."""
    async def api_plugins_memory_add(request: Request):
        try:
            try:
                body = await request.json()
            except Exception:
                body = {}
            if not isinstance(body, dict):
                body = {}
            user_id = (body.get("user_id") or "").strip()
            text = (body.get("text") or "").strip()
            if not user_id or not text:
                return JSONResponse(status_code=400, content={"error": "user_id and text are required", "ok": False})
            app_id = (body.get("app_id") or "").strip() or "homeclaw"
            user_name = (body.get("user_name") or "").strip() or user_id
            mem = getattr(core, "mem_instance", None)
            if mem is None:
                return JSONResponse(content={"ok": False, "error": "Memory not enabled"})
            await mem.add(text, user_name=user_name, user_id=user_id, agent_id=app_id, run_id=None, metadata=None, filters=None)
            return JSONResponse(content={"ok": True})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"error": str(e), "ok": False})
    return api_plugins_memory_add


def get_api_plugins_memory_search_handler(core):
    """Return handler for POST /api/plugins/memory/search."""
    async def api_plugins_memory_search(request: Request):
        try:
            try:
                body = await request.json()
            except Exception:
                body = {}
            if not isinstance(body, dict):
                body = {}
            user_id = (body.get("user_id") or "").strip()
            query = (body.get("query") or "").strip()
            if not user_id or not query:
                return JSONResponse(status_code=400, content={"error": "user_id and query are required", "memories": []})
            app_id = (body.get("app_id") or "").strip() or "homeclaw"
            try:
                limit = max(1, min(50, int(body.get("limit", 10) or 10)))
            except (TypeError, ValueError):
                limit = 10
            mem = getattr(core, "mem_instance", None)
            if mem is None:
                return JSONResponse(content={"memories": []})
            results = await mem.search(
                query=query,
                user_name=user_id,
                user_id=user_id,
                agent_id=app_id,
                run_id=None,
                filters={},
                limit=limit,
            )
            out = []
            if isinstance(results, list):
                for r in results:
                    if isinstance(r, dict):
                        out.append({"memory": r.get("memory", r.get("data", "")), "score": r.get("score", 0.0)})
                    else:
                        out.append({"memory": str(r), "score": 0.0})
            return JSONResponse(content={"memories": out})
        except Exception as e:
            logger.exception(e)
            return JSONResponse(status_code=500, content={"error": str(e), "memories": []})
    return api_plugins_memory_search


def get_api_plugin_ui_list_handler(core):
    """Return handler for GET /api/plugin-ui."""
    async def api_plugin_ui_list():
        out = []
        for pid, plug in (getattr(core.plugin_manager, "plugin_by_id", None) or {}).items():
            if not isinstance(plug, dict) or not plug.get("ui"):
                continue
            ui = plug["ui"]
            entry = {"plugin_id": pid, "name": plug.get("name") or pid, "ui": ui}
            out.append(entry)
        return JSONResponse(content={"plugins": out})
    return api_plugin_ui_list
