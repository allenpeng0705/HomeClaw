"""
DingTalk (钉钉) channel: Stream mode via dingtalk-stream SDK.
Receives messages over WebSocket, forwards to Core /inbound, replies with reply_text.
Core URL from channels/.env. Set DINGTALK_CLIENT_ID, DINGTALK_CLIENT_SECRET in channels/dingtalk/.env (or channels/.env).
Ref: https://github.com/soimy/other-agent-channel-dingtalk
"""
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
import httpx
from dingtalk_stream import (
    DingTalkStreamClient,
    Credential,
    AckMessage,
    ChatbotMessage,
    ChatbotHandler,
)

# Core connection: channels/.env
load_dotenv(_root / "channels" / ".env")
# DingTalk credentials: channels/dingtalk/.env (overrides channels/.env)
load_dotenv(Path(__file__).resolve().parent / ".env")
from base.util import Util

INBOUND_URL = f"{Util().get_channels_core_url()}/inbound"

DINGTALK_CLIENT_ID = os.getenv("DINGTALK_CLIENT_ID")
DINGTALK_CLIENT_SECRET = os.getenv("DINGTALK_CLIENT_SECRET")

# Cache access_token for media upload (old oapi gettoken; reuse for 2h)
_dingtalk_token_cache: dict = {"token": None, "expires": 0}


def get_dingtalk_access_token() -> str | None:
    """Get access token for DingTalk OpenAPI (media upload). Uses old gettoken with client_id/client_secret."""
    import time
    now = time.time()
    if _dingtalk_token_cache["token"] and now < _dingtalk_token_cache["expires"]:
        return _dingtalk_token_cache["token"]
    if not DINGTALK_CLIENT_ID or not DINGTALK_CLIENT_SECRET:
        return None
    url = "https://oapi.dingtalk.com/gettoken"
    params = {
        "appkey": DINGTALK_CLIENT_ID,
        "appsecret": DINGTALK_CLIENT_SECRET,
    }
    try:
        with httpx.Client(timeout=10, trust_env=False) as client:
            r = client.get(url, params=params)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("errcode") != 0:
            return None
        token = data.get("access_token")
        if not token:
            return None
        _dingtalk_token_cache["token"] = token
        _dingtalk_token_cache["expires"] = now + (data.get("expires_in") or 7200) - 60
        return token
    except Exception:
        return None


def upload_dingtalk_media(access_token: str, image_bytes: bytes, media_type: str = "image") -> str | None:
    """Upload image to DingTalk; returns media_id or None. Ref: oapi.dingtalk.com/media/upload."""
    if not image_bytes or not access_token:
        return None
    url = "https://oapi.dingtalk.com/media/upload"
    params = {"access_token": access_token}
    files = {"media": ("image.png", image_bytes, "image/png")}
    data = {"type": media_type}
    try:
        with httpx.Client(timeout=30, trust_env=False) as client:
            r = client.post(url, params=params, data=data, files=files)
        if r.status_code != 200:
            print("[DingTalk] upload_media failed: status={}".format(r.status_code))
            return None
        out = r.json()
        if out.get("errcode") != 0:
            print("[DingTalk] upload_media err: errcode={} errmsg={}".format(out.get("errcode"), out.get("errmsg", "")))
            return None
        return out.get("media_id")
    except Exception as e:
        print("[DingTalk] upload_media exception: {}".format(e))
        return None


def send_dingtalk_image_via_webhook(session_webhook: str, media_id: str) -> bool:
    """POST image message to session webhook. Returns True if sent successfully."""
    if not session_webhook or not media_id:
        return False
    body = {"msgtype": "image", "image": {"media_id": media_id}}
    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            r = client.post(session_webhook, json=body)
        if r.status_code not in (200, 201):
            print("[DingTalk] send_image_webhook failed: status={} body={}".format(r.status_code, (r.text or "")[:200]))
            return False
        out = r.json()
        if out.get("errcode") != 0:
            print("[DingTalk] send_image_webhook err: errcode={} errmsg={}".format(out.get("errcode"), out.get("errmsg", "")))
            return False
        return True
    except Exception as e:
        print("[DingTalk] send_image_webhook exception: {}".format(e))
        return False


class HomeClawDingTalkHandler(ChatbotHandler):
    """Forwards incoming DingTalk messages to Core /inbound and replies with the response."""

    async def process(self, callback_message):
        try:
            incoming_message = ChatbotMessage.from_dict(callback_message.data)
        except Exception as e:
            self.logger.warning("DingTalk parse message failed: {}", e)
            return AckMessage.STATUS_BAD_REQUEST, "invalid message"

        text_list = incoming_message.get_text_list() if incoming_message else []
        text = " ".join(text_list).strip() if text_list else ""
        # Optional: attachment data URLs if bridge/SDK provides them (e.g. from callback_message.data)
        raw = callback_message.data if isinstance(callback_message.data, dict) else {}
        images = raw.get("images") or getattr(incoming_message, "images", None) or []
        videos = raw.get("videos") or getattr(incoming_message, "videos", None) or []
        audios = raw.get("audios") or getattr(incoming_message, "audios", None) or []
        files = raw.get("files") or getattr(incoming_message, "files", None) or []
        if not text and not (images or videos or audios or files):
            return AckMessage.STATUS_OK, "ok"

        sender_id = incoming_message.sender_id or incoming_message.conversation_id or "unknown"
        user_id = "dingtalk_{}".format(sender_id)
        user_name = incoming_message.sender_nick or user_id
        print("[DingTalk] sender_id={} → add to config/user.yml im: dingtalk_{}".format(sender_id, sender_id))
        payload = {
            "user_id": user_id,
            "text": text or "(no text)",
            "channel_name": "dingtalk",
            "user_name": user_name,
            "reply_accepts": ["text", "image"],
        }
        if images:
            payload["images"] = images
        if videos:
            payload["videos"] = videos
        if audios:
            payload["audios"] = audios
        if files:
            payload["files"] = files
        try:
            headers = Util().get_channels_core_api_headers()
            # trust_env=False so we connect directly to Core (no HTTP_PROXY); same as Slack
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                r = await client.post(INBOUND_URL, json=payload, headers=headers)
            # So you can confirm request reached Core; Core will log "POST /inbound received: user_id=... channel_name=dingtalk"
            print("[DingTalk] → Core: user_id={} status={}".format(user_id, r.status_code))
            data = r.json() if r.content else {}
            reply = data.get("text", "")
            if not reply and r.status_code != 200:
                reply = data.get("error", "Request failed")
            _img = data.get("images")
            reply_images = _img if isinstance(_img, list) else []
        except httpx.ConnectError:
            print("[DingTalk] → Core: connection failed (check core_host/core_port in channels/.env and that Core is running)")
            reply = "Core unreachable. Is HomeClaw running?"
            reply_images = []
        except Exception as e:
            self.logger.exception(e)
            reply = "Error: {}".format(e)
            reply_images = []
        reply = reply or "(no reply)"
        self.reply_text(reply, incoming_message)
        # Send images via session webhook if available (upload to get media_id, then POST image message).
        raw_data = callback_message.data if isinstance(callback_message.data, dict) else {}
        session_webhook = raw_data.get("sessionWebhook") or raw_data.get("session_webhook") or ""
        token = get_dingtalk_access_token() if session_webhook else None
        for i, data_url in enumerate((reply_images or [])[:5]):
            if not data_url or not isinstance(data_url, str):
                continue
            raw_bytes = Util.data_url_to_bytes(data_url)
            if not raw_bytes or not token:
                continue
            media_id = upload_dingtalk_media(token, raw_bytes, "image")
            if media_id and session_webhook:
                send_dingtalk_image_via_webhook(session_webhook, media_id)
        return AckMessage.STATUS_OK, "ok"


def main():
    if not DINGTALK_CLIENT_ID or not DINGTALK_CLIENT_SECRET:
        print("Set DINGTALK_CLIENT_ID and DINGTALK_CLIENT_SECRET in channels/.env")
        return
    credential = Credential(DINGTALK_CLIENT_ID, DINGTALK_CLIENT_SECRET)
    client = DingTalkStreamClient(credential)
    client.register_callback_handler(ChatbotMessage.TOPIC, HomeClawDingTalkHandler())
    print("DingTalk channel: Stream mode (Core from channels/.env)")
    client.start_forever()


if __name__ == "__main__":
    main()
