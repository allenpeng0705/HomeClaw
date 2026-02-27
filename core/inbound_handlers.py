"""
Inbound request handlers: POST /inbound and WebSocket /ws shared logic.
Extracted from core/core.py (Phase 4 refactor). All functions take core as first argument.
"""

import asyncio
import base64
import copy
import json
import os
import time
from datetime import datetime
from typing import Any, List, Optional, Tuple

from loguru import logger

from base.base import ChannelType, ContentType, InboundRequest, PromptRequest
from base.tools import ROUTING_RESPONSE_ALREADY_SENT


async def handle_inbound_request(
    core: Any,
    request: InboundRequest,
    progress_queue: Optional[asyncio.Queue] = None,
) -> Tuple[bool, str, int, Optional[List[str]]]:
    """Shared logic for POST /inbound and WebSocket /ws. Returns (success, text_or_error, status_code, image_paths_or_none). When progress_queue is set (stream=true), progress messages are put on the queue during long-running tools."""
    try:
        return await handle_inbound_request_impl(core, request, progress_queue=progress_queue)
    except Exception as e:
        logger.exception(e)
        msg = (str(e) or "Internal error").strip()[:500]
        return False, msg or "Internal error", 500, None


async def run_async_inbound(core: Any, request_id: str, request: InboundRequest) -> None:
    """Background task for async /inbound: run the request and store result for GET /inbound/result. Same response shape as sync /inbound."""
    try:
        ok, text, status, image_paths = await handle_inbound_request(core, request)
        try:
            out_text, out_fmt = core._outbound_text_and_format(text) if text else ("", "plain")
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
                    ext = (
                        (image_path.lower().split(".")[-1] if "." in image_path else "png")
                        or "png"
                    )
                    mime = (
                        "image/png"
                        if ext == "png"
                        else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext)
                    )
                    if mime == "image/jpg":
                        mime = "image/jpeg"
                    data_urls.append(f"data:{mime};base64,{b64}")
                except Exception:
                    pass
        entry = {
            "status": "done",
            "ok": ok,
            "text": out_text,
            "format": out_fmt,
            "created_at": time.time(),
        }
        if not ok:
            entry["error"] = (text or "")[:2000]
        if data_urls:
            entry["images"] = data_urls
            entry["image"] = data_urls[0]
        core._inbound_async_results[request_id] = entry
    except Exception as e:
        logger.exception(e)
        core._inbound_async_results[request_id] = {
            "status": "done",
            "ok": False,
            "text": "",
            "format": "plain",
            "error": (str(e) or "Internal error")[:2000],
            "created_at": time.time(),
        }
    try:
        push_sid = getattr(request, "push_ws_session_id", None)
        if isinstance(push_sid, str) and push_sid.strip():
            ws = core._ws_sessions.get(push_sid.strip())
            if ws is not None:
                entry = core._inbound_async_results.get(request_id)
                if entry and entry.get("status") == "done":
                    push_payload = {
                        "event": "inbound_result",
                        "request_id": request_id,
                        "status": "done",
                        "text": entry.get("text", ""),
                        "format": entry.get("format", "plain"),
                        "ok": entry.get("ok", True),
                    }
                    if entry.get("error"):
                        push_payload["error"] = entry["error"]
                    imgs = entry.get("images") or []
                    if imgs:
                        push_payload["images"] = imgs
                        push_payload["image"] = imgs[0] if imgs else None
                    try:
                        await ws.send_json(push_payload)
                    except Exception as push_err:
                        logger.debug(
                            "Push to WebSocket session {} failed: {}",
                            (push_sid or "")[:8],
                            push_err,
                        )
    except Exception as e:
        logger.debug("push_ws_session_id delivery failed: {}", e)


async def handle_inbound_request_impl(
    core: Any,
    request: InboundRequest,
    progress_queue: Optional[asyncio.Queue] = None,
) -> Tuple[bool, str, int, Optional[List[str]]]:
    """Implementation of handle_inbound_request. When progress_queue is set, progress events are put on it during long-running tools."""
    req_id = str(datetime.now().timestamp())
    user_name = request.user_name or request.user_id
    images_list = list(request.images) if getattr(request, "images", None) else []
    videos_list = list(request.videos) if getattr(request, "videos", None) else []
    audios_list = list(request.audios) if getattr(request, "audios", None) else []
    files_list = list(request.files) if getattr(request, "files", None) else []
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
        logger.info(
            "Inbound request has {} image(s) (from images + image data URLs moved from files)",
            len(images_list),
        )
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
    inbound_user_id = (getattr(request, "user_id", None) or "").strip() or "companion"
    inbound_app_id = getattr(request, "app_id", None) or "homeclaw"
    _fid = getattr(request, "friend_id", None)
    inbound_friend_id = (str(_fid).strip() if _fid is not None else "") or "HomeClaw"
    pr = PromptRequest(
        request_id=req_id,
        channel_name=request.channel_name or "webhook",
        request_metadata=request_metadata,
        channelType=ChannelType.IM,
        user_name=user_name,
        app_id=inbound_app_id,
        user_id=inbound_user_id,
        contentType=content_type_for_perm,
        friend_id=inbound_friend_id,
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
    has_permission, user = core.check_permission(
        pr.user_name, pr.user_id, ChannelType.IM, content_type_for_perm
    )
    if not has_permission or user is None:
        return False, "Permission denied", 401, None
    if user and len(user.name) > 0:
        pr.user_name = user.name
    if user:
        pr.system_user_id = user.id or user.name
    pr.friend_id = inbound_friend_id
    try:
        loc_in = request_metadata.get("location") or getattr(request, "location", None)
        if loc_in is not None:
            display_loc, lat_lng_str = core._normalize_location_to_address(loc_in)
            if display_loc:
                sid = (inbound_user_id or "").strip().lower()
                if sid in ("system", "companion"):
                    core._set_latest_location(
                        getattr(core, "_LATEST_LOCATION_SHARED_KEY", "companion"),
                        display_loc,
                        lat_lng_str=lat_lng_str,
                    )
                elif getattr(pr, "system_user_id", None):
                    core._set_latest_location(
                        pr.system_user_id, display_loc, lat_lng_str=lat_lng_str
                    )
    except Exception as e:
        logger.debug("Store latest location on inbound: {}", e)
    if progress_queue is not None:
        pr.request_metadata["progress_queue"] = progress_queue
    core.latestPromptRequest = copy.deepcopy(pr)
    core._persist_last_channel(pr)
    if not getattr(core, "orchestrator_unified_with_tools", True):
        flag = await core.orchestrator_handler(pr)
        if flag:
            return True, "Orchestrator and plugin handled the request", 200, None
    resp_text = await core.process_text_message(pr)
    if resp_text is None:
        return True, "", 200, None
    if resp_text == ROUTING_RESPONSE_ALREADY_SENT:
        return True, "Handled by routing (TAM or plugin).", 200, None
    img_paths = (pr.request_metadata or {}).get("response_image_paths")
    if not isinstance(img_paths, list):
        single = (pr.request_metadata or {}).get("response_image_path")
        img_paths = [single] if single and isinstance(single, str) else None
    if not img_paths and getattr(core, "_response_image_paths_by_request_id", None):
        img_paths = core._response_image_paths_by_request_id.pop(pr.request_id, None)
    return True, resp_text, 200, img_paths


async def inbound_sse_generator(
    core: Any,
    progress_queue: asyncio.Queue,
    task: asyncio.Task,
) -> Any:
    """Yield Server-Sent Events: progress from queue, then final 'done' event. Heartbeat every 40s. Never raises; on error yields done with ok=False."""
    _INBOUND_SSE_HEARTBEAT_INTERVAL = 40.0

    def _yield_done(
        ok: bool,
        text: str = "",
        error: str = "",
        status: int = 200,
        data_urls: Optional[List[str]] = None,
    ) -> str:
        payload = {
            "event": "done",
            "ok": ok,
            "text": (text or "")[:50000],
            "format": "plain",
            "status": status,
        }
        if error:
            payload["error"] = (error or "")[:2000]
        if data_urls:
            payload["images"] = data_urls
            payload["image"] = data_urls[0] if data_urls else None
        try:
            return f"data: {json.dumps(payload)}\n\n"
        except Exception:
            return 'data: {"event":"done","ok":false,"error":"Serialization error","text":""}\n\n'

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
            out_text, out_fmt = core._outbound_text_and_format(text) if text else ("", "plain")
        except Exception as e:
            logger.debug("inbound SSE outbound_text_and_format: {}", e)
            out_text, out_fmt = (str(text)[:50000] if text else "", "plain")
        content = {
            "event": "done",
            "ok": ok,
            "text": out_text,
            "format": out_fmt,
            "status": status,
        }
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
                    ext = (
                        (image_path.lower().split(".")[-1] if "." in image_path else "png")
                        or "png"
                    )
                    mime = (
                        "image/png"
                        if ext == "png"
                        else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext)
                    )
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
            yield _yield_done(
                ok=ok,
                text=out_text,
                error=content.get("error", ""),
                status=status,
                data_urls=data_urls if data_urls else None,
            )
    except Exception as e:
        logger.exception("inbound SSE generator: {}", e)
        try:
            yield _yield_done(ok=False, error=str(e)[:2000])
        except Exception:
            yield 'data: {"event":"done","ok":false,"error":"SSE error","text":""}\n\n'
