"""
Companion push API: POST /api/companion/push-token (register), DELETE /api/companion/push-token (unregister).
Same auth as /inbound (auth.verify_inbound_auth). Used so Core can send FCM push when app is killed/background.
"""
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from base import push_tokens as push_tokens_store


class PushTokenRegister(BaseModel):
    user_id: str
    token: str
    platform: str = "android"
    device_id: str = ""


def get_api_companion_push_token_register_handler(core):  # noqa: ARG001
    """Return handler for POST /api/companion/push-token. Never raises; returns 500 only on unexpected error."""
    async def api_companion_push_token_register(body: PushTokenRegister):
        try:
            uid = (getattr(body, "user_id", None) or "companion")
            uid = uid.strip() if isinstance(uid, str) else "companion"
            tok = getattr(body, "token", None) or ""
            tok = str(tok).strip() if tok is not None else ""
            plat = getattr(body, "platform", None) or "android"
            plat = str(plat).strip().lower() or "android"
            dev_id = getattr(body, "device_id", None) or ""
            dev_id = str(dev_id).strip() if dev_id is not None else ""
            push_tokens_store.register_push_token(uid, tok, plat, device_id=dev_id or None)
            return JSONResponse(content={"ok": True})
        except Exception as e:
            logger.warning("push-token register failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_companion_push_token_register


def get_api_companion_push_token_unregister_handler(core):  # noqa: ARG001
    """Return handler for DELETE /api/companion/push-token. Query: user_id, token (optional), device_id (optional). Never raises."""
    async def api_companion_push_token_unregister(user_id: str = "", token: str | None = None, device_id: str | None = None):
        try:
            uid = (user_id or "companion").strip() if isinstance(user_id, str) else "companion"
            did = (device_id or "").strip() or None if device_id is not None else None
            push_tokens_store.unregister_push_token(uid, token=token, device_id=did)
            return JSONResponse(content={"ok": True})
        except Exception as e:
            logger.warning("push-token unregister failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_companion_push_token_unregister
