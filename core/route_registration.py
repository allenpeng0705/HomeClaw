"""
Register all FastAPI routes and inline POST handlers for Core.
Extracted from core/core.py (Phase 2 refactor). No dependency on core.core to avoid circular imports.
"""

import asyncio
import base64
import copy
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from loguru import logger

from base.base import (
    AsyncResponse,
    ChannelType,
    ContentType,
    InboundRequest,
    PromptRequest,
    User,
)
from base.tools import ROUTING_RESPONSE_ALREADY_SENT
from base.util import Util

from core.routes import (
    auth,
    companion_auth,
    companion_push_api,
    config_api,
    files,
    inbound as inbound_routes,
    knowledge_base_routes,
    lifecycle,
    memory_routes,
    misc_api,
    plugins_api,
    portal_proxy,
    ui_routes,
    websocket_routes,
)


def register_all_routes(core: Any) -> None:
    """
    Register all API routes, WebSocket route, exception handler, and inline POST handlers
    (/process, /local_chat, /inbound) on core.app. Use core (Core instance) for all handler logic.
    """
    app = core.app

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.error(f"Validation error: {exc} for request: {await request.body()}")
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "body": exc.body},
        )

    # Lifecycle routes (pinggy: callable that returns the shared state dict)
    _pinggy_getter = getattr(core, "_pinggy_state_getter", None)
    if not callable(_pinggy_getter):

        def _default_pinggy() -> Dict[str, Any]:
            return {"public_url": None, "connect_url": None, "qr_base64": None, "error": None}

        _pinggy_getter = _default_pinggy
    app.add_api_route(
        "/register_channel",
        lifecycle.get_register_channel_handler(core),
        methods=["POST"],
    )
    app.add_api_route(
        "/deregister_channel",
        lifecycle.get_deregister_channel_handler(core),
        methods=["POST"],
    )
    app.add_api_route("/ready", lifecycle.get_ready_handler(core), methods=["GET"])
    app.add_api_route(
        "/pinggy",
        lifecycle.get_pinggy_handler(core, _pinggy_getter),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route("/shutdown", lifecycle.get_shutdown_handler(core), methods=["GET"])
    app.add_api_route(
        "/inbound/result",
        inbound_routes.get_inbound_result_handler(core),
        methods=["GET"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/config/core",
        config_api.get_api_config_core_get_handler(core),
        methods=["GET"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/config/core",
        config_api.get_api_config_core_patch_handler(core),
        methods=["PATCH"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/config/users",
        config_api.get_api_config_users_get_handler(core),
        methods=["GET"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/config/users",
        config_api.get_api_config_users_post_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/config/users/{user_name}",
        config_api.get_api_config_users_patch_handler(core),
        methods=["PATCH"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/config/users/{user_name}",
        config_api.get_api_config_users_delete_handler(core),
        methods=["DELETE"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    # Portal auth (Phase 5): POST /api/portal/auth returns token for portal admin; no Core API key required.
    app.add_api_route(
        "/api/portal/auth",
        portal_proxy.post_portal_auth_handler,
        methods=["POST"],
    )
    # Diagnostic: GET /api/portal/proxy-status returns portal_url and whether Portal is reachable (no auth).
    app.add_api_route(
        "/api/portal/proxy-status",
        portal_proxy.get_portal_proxy_status_handler,
        methods=["GET"],
    )
    # Portal UI reverse proxy (Phase 4.2): /portal-ui and /portal-ui/* -> Portal. Phase 5: require portal admin auth.
    app.add_api_route(
        "/portal-ui",
        portal_proxy.get_portal_ui_handler(),
        methods=["GET"],
    )
    app.add_api_route(
        "/portal-ui/{path:path}",
        portal_proxy.get_portal_ui_path_handler(),
        methods=["GET"],
    )
    app.add_api_route(
        "/files/out",
        files.get_files_out_handler(core),
        methods=["GET"],
    )
    app.add_api_route(
        "/files/{scope}/{path:path}",
        files.get_files_static_handler(core),
        methods=["GET"],
    )
    app.add_api_route(
        "/api/sandbox/list",
        files.get_api_sandbox_list_handler(core),
        methods=["GET"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/upload",
        files.get_api_upload_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/memory/summarize",
        memory_routes.get_memory_summarize_handler(core),
        methods=["POST"],
    )
    app.add_api_route(
        "/memory/reset",
        memory_routes.get_memory_reset_handler(core),
        methods=["GET", "POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/knowledge_base/reset",
        knowledge_base_routes.get_knowledge_base_reset_handler(core),
        methods=["GET", "POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/knowledge_base/folder_sync_config",
        knowledge_base_routes.get_knowledge_base_folder_sync_config_handler(core),
        methods=["GET"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/knowledge_base/sync_folder",
        knowledge_base_routes.get_knowledge_base_sync_folder_handler(core),
        methods=["GET", "POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/plugins/register",
        plugins_api.get_api_plugins_register_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/plugins/unregister",
        plugins_api.get_api_plugins_unregister_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/plugins/unregister-all",
        plugins_api.get_api_plugins_unregister_all_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/plugins/health/{plugin_id}",
        plugins_api.get_api_plugins_health_handler(core),
        methods=["GET"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/plugins/llm/generate",
        plugins_api.get_api_plugins_llm_generate_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/plugins/memory/add",
        plugins_api.get_api_plugins_memory_add_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/plugins/memory/search",
        plugins_api.get_api_plugins_memory_search_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/plugin-ui",
        plugins_api.get_api_plugin_ui_list_handler(core),
        methods=["GET"],
    )
    app.add_api_route(
        "/api/skills/clear-vector-store",
        misc_api.get_api_skills_clear_vector_store_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/testing/clear-all",
        misc_api.get_api_testing_clear_all_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/sessions",
        misc_api.get_api_sessions_list_handler(core),
        methods=["GET"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/reports/usage",
        misc_api.get_api_reports_usage_handler(core),
        methods=["GET"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/companion/push-token",
        companion_push_api.get_api_companion_push_token_register_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/companion/push-token",
        companion_push_api.get_api_companion_push_token_unregister_handler(core),
        methods=["DELETE"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/auth/login",
        companion_auth.get_api_auth_login_handler(core),
        methods=["POST"],
        dependencies=[Depends(auth.verify_inbound_auth)],
    )
    app.add_api_route(
        "/api/me",
        companion_auth.get_api_me_handler(core),
        methods=["GET"],
        dependencies=[Depends(companion_auth.get_companion_token_user)],
    )
    app.add_api_route(
        "/api/me/friends",
        companion_auth.get_api_me_friends_handler(core),
        methods=["GET"],
        dependencies=[Depends(companion_auth.get_companion_token_user)],
    )
    app.add_api_route("/ui", ui_routes.get_ui_launcher_handler(core), methods=["GET"])
    app.add_websocket_route("/ws", websocket_routes.get_websocket_handler(core))

    @app.post("/process")
    async def process_request(request: PromptRequest):
        try:
            user_name: str = request.user_name
            user_id: str = request.user_id
            channel_type: ChannelType = request.channelType
            content_type: ContentType = request.contentType
            channel_name: str = getattr(request, "channel_name", "?")
            logger.info(
                f"Core: received /process from channel={channel_name} user={user_id} type={content_type}"
            )
            logger.debug(
                f"Received request from channel: {user_name}, {user_id}, {channel_type}, {content_type}"
            )
            user: User = None
            has_permission, user = core.check_permission(
                user_name, user_id, channel_type, content_type
            )
            if not has_permission or user is None:
                try:
                    meta = Util().get_core_metadata()
                    if getattr(meta, "notify_unknown_request", False):
                        from base.last_channel import get_last_channel

                        last = get_last_channel()
                        if last and getattr(core, "response_queue", None):
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
                                response_data={
                                    "text": core._format_outbound_text(msg),
                                    "format": "plain",
                                },
                            )
                            await core.response_queue.put(async_resp)
                except Exception as notify_e:
                    logger.debug("notify_unknown_request failed: {}", notify_e)
                return Response(content="Permission denied", status_code=401)

            if request is not None:
                try:
                    if len(user.name) > 0:
                        request.user_name = user.name
                except (TypeError, AttributeError):
                    pass
                try:
                    request.system_user_id = user.id or user.name
                except (TypeError, AttributeError):
                    request.system_user_id = ""
                try:
                    request.friend_id = "HomeClaw"
                except (TypeError, AttributeError):
                    pass
                core.latestPromptRequest = copy.deepcopy(request)
                logger.debug(f"latestPromptRequest set to: {core.latestPromptRequest}")
                try:
                    core._persist_last_channel(request)
                except Exception as pe:
                    logger.debug("_persist_last_channel failed: {}", pe)
            await core.request_queue.put(request)

            return Response(content="Request received", status_code=200)
        except Exception as e:
            logger.exception(e)
            return Response(content="Server Internal Error", status_code=500)

    @app.post("/local_chat")
    async def process_request_local(request: PromptRequest):
        try:
            user_name: str = request.user_name
            user_id: str = request.user_id
            channel_type: ChannelType = request.channelType
            content_type: ContentType = request.contentType
            logger.debug(
                f"Received request from channel: {user_name}, {user_id}, {channel_type}, {content_type}"
            )
            user: User = None
            has_permission, user = core.check_permission(
                user_name, user_id, channel_type, content_type
            )
            if not has_permission or user is None:
                return Response(content="Permission denied", status_code=401)

            try:
                if len(user.name) > 0:
                    request.user_name = user.name
            except (TypeError, AttributeError):
                pass
            try:
                request.system_user_id = user.id or user.name
            except (TypeError, AttributeError):
                request.system_user_id = ""
            try:
                request.friend_id = "HomeClaw"
            except (TypeError, AttributeError):
                pass

            core.latestPromptRequest = copy.deepcopy(request)
            logger.debug(f"latestPromptRequest set to: {core.latestPromptRequest}")
            try:
                core._persist_last_channel(request)
            except Exception as pe:
                logger.debug("_persist_last_channel failed: {}", pe)

            if not getattr(core, "orchestrator_unified_with_tools", True):
                flag = await core.orchestrator_handler(request)
                if flag:
                    logger.debug("Orchestrator and plugin handled the request")
                    return Response(
                        content="Orchestrator and plugin handled the request",
                        status_code=200,
                    )

            resp_text = await core.process_text_message(request)
            if resp_text is None:
                return Response(content="Response is None", status_code=200)
            if resp_text == ROUTING_RESPONSE_ALREADY_SENT:
                return Response(
                    content="Handled by routing (TAM or plugin).", status_code=200
                )

            return Response(content=resp_text, status_code=200)
        except Exception as e:
            logger.exception(e)
            return Response(content="Server Internal Error", status_code=500)

    @app.post("/inbound")
    async def inbound_post_handler(
        request: InboundRequest,
        raw_request: Request,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            if getattr(request, "async_mode", False):
                request_id = str(uuid.uuid4())
                core._inbound_async_results[request_id] = {
                    "status": "pending",
                    "created_at": time.time(),
                }
                asyncio.create_task(core._run_async_inbound(request_id, request))
                return JSONResponse(
                    status_code=202,
                    content={
                        "request_id": request_id,
                        "status": "accepted",
                        "message": "Processing in background. Poll GET /inbound/result?request_id="
                        + request_id,
                    },
                )
            if getattr(request, "stream", False):
                progress_queue = asyncio.Queue()
                try:
                    progress_queue.put_nowait(
                        {
                            "event": "progress",
                            "message": "Processing your request…",
                            "tool": "",
                        }
                    )
                except Exception:
                    pass
                task = asyncio.create_task(
                    core._handle_inbound_request_impl(
                        request, progress_queue=progress_queue
                    )
                )
                return StreamingResponse(
                    core._inbound_sse_generator(progress_queue, task),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            ok, text, status, image_paths = await core._handle_inbound_request(request)
            if not ok:
                return JSONResponse(
                    status_code=status, content={"error": text, "text": ""}
                )
            out_text, out_fmt = (
                core._outbound_text_and_format(text) if text else ("", "plain")
            )
            content = {"text": out_text, "format": out_fmt}
            if not image_paths and text and (
                "Image saved:" in text or "HOMECLAW_IMAGE_PATH=" in text
            ):
                import re as _re

                for pattern in (
                    r"Image saved:\s*(.+)",
                    r"HOMECLAW_IMAGE_PATH=(.+)",
                ):
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
            if image_paths:
                data_urls = []
                for image_path in image_paths:
                    if not isinstance(image_path, str) or not os.path.isfile(
                        image_path
                    ):
                        continue
                    try:
                        with open(image_path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("ascii")
                        ext = (
                            (
                                image_path.lower().split(".")[-1]
                                if "." in image_path
                                else "png"
                            )
                            or "png"
                        )
                        mime = (
                            "image/png"
                            if ext == "png"
                            else (
                                "image/jpeg"
                                if ext in ("jpg", "jpeg")
                                else "image/" + ext
                            )
                        )
                        if mime == "image/jpg":
                            mime = "image/jpeg"
                        data_urls.append(f"data:{mime};base64,{b64}")
                    except Exception as e:
                        logger.debug(
                            "inbound: could not attach image as data URL: {}", e
                        )
                if data_urls:
                    content["images"] = data_urls
                    content["image"] = data_urls[0]
            try:
                raw_req = raw_request
                disconnected = (
                    getattr(raw_req, "is_disconnected", None)
                    if raw_req is not None
                    else None
                )
                if callable(disconnected):
                    try:
                        is_disc = await disconnected()
                    except Exception:
                        is_disc = False
                    if is_disc:
                        inbound_uid = (
                            str(getattr(request, "user_id", None) or "").strip()
                            or "companion"
                        )
                        body_text = (
                            str(
                                content.get("text")
                                if isinstance(content, dict)
                                else ""
                            )[:1024]
                        )
                        ws_sent = 0
                        _ws_by_user = getattr(core, "_ws_user_by_session", None)
                        _ws_sessions = getattr(core, "_ws_sessions", None)
                        if isinstance(_ws_by_user, dict) and isinstance(
                            _ws_sessions, dict
                        ):
                            for sid, uid in list(_ws_by_user.items()):
                                if not isinstance(uid, str) or uid != inbound_uid:
                                    continue
                                ws = (
                                    _ws_sessions.get(sid)
                                    if isinstance(sid, str)
                                    else None
                                )
                                if ws is not None:
                                    try:
                                        payload = {
                                            "event": "push",
                                            "source": "inbound",
                                            "from_friend": content.get(
                                                "from_friend"
                                            )
                                            or "HomeClaw",
                                            "text": body_text,
                                            "format": str(
                                                content.get("format", "plain")
                                                or "plain"
                                            ),
                                        }
                                        if (
                                            isinstance(
                                                content.get("images"), list
                                            )
                                            and content["images"]
                                        ):
                                            payload["images"] = content["images"]
                                            payload["image"] = content.get(
                                                "image"
                                            )
                                        await ws.send_json(payload)
                                        ws_sent += 1
                                    except Exception as ws_e:
                                        logger.debug(
                                            "inbound: WS fallback send failed: {}",
                                            ws_e,
                                        )
                        if ws_sent == 0:
                            try:
                                from base import push_send

                                push_send.send_push_to_user(
                                    inbound_uid,
                                    title="HomeClaw",
                                    body=body_text,
                                    source="inbound",
                                    from_friend=content.get("from_friend")
                                    or "HomeClaw",
                                )
                            except Exception as push_e:
                                logger.debug(
                                    "inbound: push fallback failed: {}", push_e
                                )
            except Exception as fallback_e:
                logger.debug(
                    "inbound: connection-check/fallback failed: {}",
                    fallback_e,
                )
            return JSONResponse(content=content)
        except Exception as e:
            logger.exception(e)
            return JSONResponse(
                status_code=500,
                content={"error": str(e), "text": ""},
            )

    logger.debug("core initialized and all the endpoints are registered!")
