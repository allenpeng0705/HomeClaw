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


def _media_to_data_urls(
    items: Optional[List[str]],
    data_prefix: str,
    default_mime: str,
    ext_to_mime: Optional[dict] = None,
) -> List[str]:
    """Convert list of data URLs or file paths to data URLs. data_prefix e.g. 'data:image/' or 'data:audio/'. Never raises."""
    result: List[str] = []
    if not items:
        return result
    ext_map = ext_to_mime or {}
    for item in items:
        if not isinstance(item, str) or not item.strip():
            continue
        s = item.strip()
        if s.lower().startswith(data_prefix):
            result.append(s)
            continue
        if not os.path.isfile(s):
            continue
        try:
            with open(s, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            ext = (s.lower().split(".")[-1] if "." in s else "").strip() or ""
            mime = ext_map.get(ext) if ext in ext_map else default_mime
            if mime == "image/jpg":
                mime = "image/jpeg"
            result.append(f"data:{mime};base64,{b64}")
        except Exception:
            pass
    return result


async def deliver_to_user(
    core: Any,
    user_id: str,
    text: str,
    images: Optional[List[str]] = None,
    audios: Optional[List[str]] = None,
    videos: Optional[List[str]] = None,
    channel_key: Optional[str] = None,
    source: str = "push",
    from_friend: str = "HomeClaw",
    from_user_id: Optional[str] = None,
    e2e_encrypted: bool = False,
) -> None:
    """Push to user: WebSocket sessions, then push notification, then channel. Never raises. audios = voice; videos = short video (e.g. 10s). from_user_id: for user_message, sender id so Companion can match chat thread."""
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
        if e2e_encrypted:
            out_text = ""
            out_fmt = "plain"
        payload = {"event": "push", "source": source, "from_friend": from_friend, "text": out_text, "format": out_fmt}
        if e2e_encrypted:
            payload["e2e_encrypted"] = True
        if (from_user_id or "").strip():
            payload["from_user_id"] = (from_user_id or "").strip()
        data_urls = _media_to_data_urls(
            images,
            "data:image/",
            "image/png",
            {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"},
        )
        if data_urls:
            payload["images"] = data_urls
            payload["image"] = data_urls[0]
        audio_urls = _media_to_data_urls(
            audios,
            "data:audio/",
            "audio/mpeg",
            {"mp3": "audio/mpeg", "ogg": "audio/ogg", "wav": "audio/wav", "webm": "audio/webm", "m4a": "audio/mp4"},
        )
        if audio_urls:
            payload["audios"] = audio_urls
            payload["audio"] = audio_urls[0]
        video_urls = _media_to_data_urls(
            videos,
            "data:video/",
            "video/mp4",
            {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime", "m4v": "video/x-m4v"},
        )
        if video_urls:
            payload["videos"] = video_urls
            payload["video"] = video_urls[0]
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
        # Push: reminders/cron (time-sensitive) and user_message (so recipient gets notified when app is in background).
        try:
            if source in ("reminder", "cron", "user_message"):
                from base import push_send
                if source == "reminder":
                    title = "Reminder"
                elif source == "user_message":
                    title = f"Message from {from_friend}"
                else:
                    title = from_friend
                if e2e_encrypted and source == "user_message":
                    body_safe = "Encrypted message — open the app to read"
                else:
                    body_safe = (out_text if out_text is not None else "")[:1024]
                max_tokens = 1
                push_sent = push_send.send_push_to_user(
                    user_id, title=title, body=body_safe, source=source, from_friend=from_friend, max_tokens_per_user=max_tokens
                )
                if push_sent:
                    logger.info("deliver_to_user: sent {} push(es) (APNs/FCM) for user_id={} source={}", push_sent, user_id, source)
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
