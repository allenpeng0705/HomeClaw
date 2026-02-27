"""
WebSocket route: /ws for WebChat and async inbound push.
"""
import json
import os
import uuid

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from loguru import logger

from base.base import InboundRequest

from core.routes import auth


def get_websocket_handler(core):
    """Return WebSocket handler for /ws. Uses core._ws_sessions, core._ws_user_by_session, core._handle_inbound_request, core._outbound_text_and_format."""
    async def websocket_chat(websocket: WebSocket):
        session_id = str(uuid.uuid4())
        try:
            if not auth.ws_auth_ok(websocket):
                await websocket.close(code=1008, reason="Unauthorized: invalid or missing API key")
                return
            await websocket.accept()
            core._ws_sessions[session_id] = websocket
            try:
                await websocket.send_json({"event": "connected", "session_id": session_id})
            except Exception:
                pass
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                raw = msg.get("text")
                if raw is None and "bytes" in msg:
                    raw = msg["bytes"].decode("utf-8", errors="replace")
                if raw is None:
                    await websocket.send_json({"error": "Invalid frame: expected text or bytes", "text": ""})
                    continue
                try:
                    data = json.loads(raw)
                except Exception as e:
                    await websocket.send_json({"error": str(e), "text": ""})
                    continue
                if not isinstance(data, dict):
                    await websocket.send_json({"error": "Expected JSON object", "text": ""})
                    continue
                if data.get("event") == "register":
                    uid = (str(data.get("user_id") or "").strip() or "companion")
                    core._ws_user_by_session[session_id] = uid
                    try:
                        await websocket.send_json({"event": "registered", "user_id": uid})
                    except Exception:
                        pass
                    continue
                if data.get("event") == "ping":
                    try:
                        await websocket.send_json({"event": "pong"})
                    except Exception:
                        pass
                    continue
                try:
                    _ni = len(data.get("images") or [])
                    _nf = len(data.get("files") or [])
                    if _ni or _nf:
                        logger.info("WS inbound: images={} files={} (client must send payload.images or data:image/ in payload.files)", _ni, _nf)
                    req = InboundRequest(
                        user_id=(data.get("user_id") or "").strip() or "companion",
                        friend_id=(data.get("friend_id") or "").strip() or None,
                        text=data.get("text", ""),
                        channel_name=data.get("channel_name", "ws"),
                        user_name=data.get("user_name"),
                        app_id=data.get("app_id"),
                        action=data.get("action"),
                        session_id=data.get("session_id"),
                        conversation_type=data.get("conversation_type"),
                        images=data.get("images"),
                        videos=data.get("videos"),
                        audios=data.get("audios"),
                        files=data.get("files"),
                        location=(data.get("location") or "").strip() or None,
                    )
                except Exception as e:
                    await websocket.send_json({"error": str(e), "text": ""})
                    continue
                has_media = bool(
                    (getattr(req, "images", None) or [])
                    or (getattr(req, "videos", None) or [])
                    or (getattr(req, "audios", None) or [])
                    or (getattr(req, "files", None) or [])
                )
                if not req.user_id or (not req.text and not has_media):
                    await websocket.send_json({"error": "user_id and (text or media) required", "text": ""})
                    continue
                ok, text, _, image_paths = await core._handle_inbound_request(req)
                if ok and text:
                    out_text, out_fmt = core._outbound_text_and_format(text)
                else:
                    out_text, out_fmt = (text or "", "plain")
                if not ok:
                    out_text = ""
                ws_payload = {"text": out_text, "format": out_fmt, "error": "" if ok else text}
                if image_paths:
                    data_urls = []
                    for image_path in image_paths:
                        if not isinstance(image_path, str) or not os.path.isfile(image_path):
                            continue
                        try:
                            with open(image_path, "rb") as f:
                                b64 = __import__("base64").b64encode(f.read()).decode("ascii")
                            ext = (image_path.lower().split(".")[-1] if "." in image_path else "png") or "png"
                            mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext)
                            if mime == "image/jpg":
                                mime = "image/jpeg"
                            data_urls.append(f"data:{mime};base64,{b64}")
                        except Exception as e:
                            logger.debug("ws: could not attach image: {}", e)
                    if data_urls:
                        ws_payload["images"] = data_urls
                        ws_payload["image"] = data_urls[0]
                await websocket.send_json(ws_payload)
        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")
        except Exception as e:
            logger.exception(e)
            try:
                await websocket.send_json({"error": str(e), "text": ""})
            except Exception:
                pass
        finally:
            core._ws_sessions.pop(session_id, None)
            core._ws_user_by_session.pop(session_id, None)
    return websocket_chat
