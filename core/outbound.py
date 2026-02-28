"""
Outbound response formatting and delivery to channels/WebSocket/push.
Extracted from core/core.py (Phase 5 refactor). All functions take core as first argument.
"""

import base64
import os
from typing import Any, List, Optional

from loguru import logger

from base.base import AsyncResponse, PromptRequest
from base import last_channel as last_channel_store
from base.markdown_outbound import markdown_to_channel, looks_like_markdown, classify_outbound_format
from base.util import Util


def format_outbound_text(core: Any, text: str) -> str:
    """Convert outbound reply when it looks like Markdown; otherwise return original. Never raises."""
    if text is None or not isinstance(text, str):
        return text if text is not None else ""
    try:
        meta = Util().get_core_metadata()
        fmt = (getattr(meta, "outbound_markdown_format", None) or "whatsapp").strip().lower()
        if fmt == "none" or fmt == "":
            return text
        if not looks_like_markdown(text):
            return text
        if fmt != "plain" and fmt != "whatsapp":
            fmt = "whatsapp"
        return markdown_to_channel(text, fmt)
    except Exception:
        return text


def safe_classify_format(core: Any, text: str) -> str:
    """Return classify_outbound_format(text) or 'plain' on any exception. Never raises."""
    try:
        return classify_outbound_format(text) if (text is not None and isinstance(text, str)) else "plain"
    except Exception:
        return "plain"


def outbound_text_and_format(core: Any, text: str) -> tuple:
    """Return (text_to_send, format). Never raises."""
    try:
        if text is None or not isinstance(text, str):
            return (str(text)[:50000] if text is not None else "", "plain")
        fmt = safe_classify_format(core, text)
        if fmt == "markdown" or fmt == "link":
            return (text, fmt)
        return (format_outbound_text(core, text), "plain")
    except Exception:
        return (str(text)[:50000] if text is not None else "", "plain")


async def send_response_to_channel_by_key(core: Any, key: str, response: str) -> None:
    """Send response to the channel identified by key. Never raises."""
    try:
        if not key:
            key = last_channel_store._DEFAULT_KEY
        out_text, out_fmt = outbound_text_and_format(core, response) if response else ("", "plain")
        resp_data = {"text": out_text, "format": out_fmt}
        request: Optional[PromptRequest] = core.latestPromptRequest
        if key != last_channel_store._DEFAULT_KEY or request is None:
            stored = last_channel_store.get_last_channel(key)
            if stored is None and key == "companion":
                stored = last_channel_store.get_last_channel(last_channel_store._DEFAULT_KEY)
            if stored is None:
                if key != last_channel_store._DEFAULT_KEY:
                    logger.warning("send_response_to_channel_by_key: no channel for key={}", key)
                return
            app_id = stored.get("app_id") or ""
            if app_id == "homeclaw":
                print(response)
                return
            async_resp = AsyncResponse(
                request_id=stored.get("request_id", ""),
                request_metadata=stored.get("request_metadata") or {},
                host=stored.get("host", ""),
                port=int(stored.get("port", 0)),
                from_channel=stored.get("channel_name", ""),
                response_data=resp_data,
            )
            await core.response_queue.put(async_resp)
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
            await core.response_queue.put(async_resp)
    except Exception as e:
        logger.warning("send_response_to_channel_by_key failed: {}", e)


async def send_response_to_latest_channel(core: Any, response: str) -> None:
    """Send to the default (latest) channel. Never raises."""
    await send_response_to_channel_by_key(core, last_channel_store._DEFAULT_KEY, response)


async def deliver_to_user(
    core: Any,
    user_id: str,
    text: str,
    images: Optional[List[str]] = None,
    channel_key: Optional[str] = None,
    source: str = "push",
    from_friend: str = "HomeClaw",
) -> None:
    """Push to user: WebSocket sessions, then push notification, then channel. Never raises."""
    try:
        user_id = (str(user_id or "").strip() or "companion")
        from_friend = (str(from_friend or "HomeClaw").strip() or "HomeClaw")
        try:
            out_text, out_fmt = outbound_text_and_format(core, text) if text else ("", "plain")
        except Exception:
            out_text = str(text)[:50000] if text else ""
            out_fmt = "plain"
        if not text:
            out_text, out_fmt = "", "plain"
        out_text = out_text if out_text is not None else ""
        out_fmt = out_fmt if out_fmt is not None else "plain"
        payload = {"event": "push", "source": source, "from_friend": from_friend, "text": out_text, "format": out_fmt}
        data_urls = []
        if images:
            for image_path in images:
                if not isinstance(image_path, str) or not os.path.isfile(image_path):
                    continue
                try:
                    with open(image_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    ext = (image_path.lower().split(".")[-1] if "." in image_path else "png") or "png"
                    mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext)
                    if mime == "image/jpg":
                        mime = "image/jpeg"
                    data_urls.append(f"data:{mime};base64,{b64}")
                except Exception:
                    pass
        if data_urls:
            payload["images"] = data_urls
            payload["image"] = data_urls[0]
        ws_count = 0
        _ws_by_session = getattr(core, "_ws_user_by_session", None)
        _ws_sessions = getattr(core, "_ws_sessions", None)
        if isinstance(_ws_by_session, dict) and isinstance(_ws_sessions, dict):
            for sid, uid in list(_ws_by_session.items()):
                if uid != user_id:
                    continue
                ws = _ws_sessions.get(sid) if sid is not None else None
                if ws is not None:
                    try:
                        await ws.send_json(payload)
                        ws_count += 1
                    except Exception as e:
                        logger.debug("deliver_to_user: push to session {} failed: {}", (str(sid or "")[:8]), e)
                        try:
                            core._ws_sessions.pop(sid, None)
                            core._ws_user_by_session.pop(sid, None)
                        except Exception:
                            pass
        if ws_count == 0:
            logger.info(
                "deliver_to_user: no WebSocket session for user_id={} (reminder/push may not reach app; ensure Companion opens /ws and sends register with this user_id)",
                user_id,
            )
        else:
            logger.info("deliver_to_user: pushed to {} WebSocket session(s) for user_id={} source={}", ws_count, user_id, source)
        try:
            from base import push_send
            title = "Reminder" if source == "reminder" else from_friend
            body_safe = (out_text if out_text is not None else "")[:1024]
            max_tokens = 1 if source == "reminder" else None
            push_sent = push_send.send_push_to_user(
                user_id, title=title, body=body_safe, source=source, from_friend=from_friend, max_tokens_per_user=max_tokens
            )
            if push_sent:
                logger.info("deliver_to_user: sent {} push(es) (APNs/FCM) for user_id={} from_friend={}", push_sent, user_id, from_friend)
        except Exception as push_e:
            logger.debug("deliver_to_user: push send failed: {}", push_e)
        try:
            if channel_key:
                await send_response_to_channel_by_key(core, channel_key, text)
            else:
                await send_response_to_latest_channel(core, text)
        except Exception as ch_e:
            logger.debug("deliver_to_user: send_response_to_channel failed: {}", ch_e)
    except Exception as e:
        logger.warning("deliver_to_user failed: {}", e)


async def send_response_to_request_channel(
    core: Any,
    response: str,
    request: PromptRequest,
    image_path: Optional[str] = None,
    video_path: Optional[str] = None,
    audio_path: Optional[str] = None,
) -> None:
    """Send text and optional media to the channel. Never raises."""
    out_text, out_fmt = outbound_text_and_format(core, response) if response else ("", "plain")
    resp_data = {"text": out_text, "format": out_fmt}
    if request is None:
        return
    if image_path and isinstance(image_path, str) and os.path.isfile(image_path):
        resp_data["image"] = image_path
    if video_path and isinstance(video_path, str) and os.path.isfile(video_path):
        resp_data["video"] = video_path
    if audio_path and isinstance(audio_path, str) and os.path.isfile(audio_path):
        resp_data["audio"] = audio_path
    async_resp = AsyncResponse(
        request_id=request.request_id,
        request_metadata=request.request_metadata,
        host=request.host,
        port=request.port,
        from_channel=request.channel_name,
        response_data=resp_data,
    )
    await core.response_queue.put(async_resp)


async def send_response_for_plugin(core: Any, response: str, request: Optional[PromptRequest] = None) -> None:
    """Send to request channel when request is known, else to latest channel. Never raises."""
    if request is not None:
        await send_response_to_request_channel(core, response, request)
    else:
        await send_response_to_latest_channel(core, response)
