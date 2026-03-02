"""
Feishu (飞书 / Lark) channel: receives event callbacks from Feishu Open Platform.
Handles im.message.receive_v1: forwards to Core /inbound, sends reply via Feishu API.
Core connection from channels/.env only. Set FEISHU_APP_ID, FEISHU_APP_SECRET in channels/.env.
Ref: https://github.com/m1heng/clawdbot-feishu (other agent Feishu plugin)
"""
import os
import sys
import json
from pathlib import Path
from collections import OrderedDict

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv(_root / "channels" / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")  # feishu/.env overrides for port, credentials
from base.util import Util

app = FastAPI(title="HomeClaw Feishu Channel")
INBOUND_URL = f"{Util().get_channels_core_url()}/inbound"

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_BASE_URL = os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/")
FEISHU_EVENT_PATH = os.getenv("FEISHU_EVENT_PATH", "/feishu/events")

# Deduplicate by message_id: Feishu may send the same event 2+ times; we only process and reply once.
# Use OrderedDict so we can evict oldest when full; never clear all (that would allow old duplicates to resend).
_processed_message_ids: OrderedDict = OrderedDict()
_MAX_PROCESSED_IDS = 5000


def get_tenant_access_token() -> str | None:
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        return None
    url = f"{FEISHU_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal"
    try:
        with httpx.Client(timeout=10, trust_env=False) as client:
            r = client.post(
                url,
                json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            )
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("code") != 0:
            return None
        return data.get("tenant_access_token")
    except Exception:
        return None


def _log_feishu_send_failure(where: str, r: httpx.Response) -> None:
    try:
        body = r.text[:500] if r.text else ""
        print("[Feishu] {} failed: status={} body={}".format(where, r.status_code, body))
    except Exception:
        print("[Feishu] {} failed: status={}".format(where, r.status_code))


def send_feishu_message(chat_id: str, text: str) -> bool:
    """Send a new message to a chat. Use reply_to_feishu_message when you have the message_id so the reply appears in the same thread."""
    token = get_tenant_access_token()
    if not token:
        print("[Feishu] Cannot send: no tenant_access_token (check FEISHU_APP_ID/FEISHU_APP_SECRET).")
        return False
    url = f"{FEISHU_BASE_URL}/open-apis/im/v1/messages"
    params = {"receive_id_type": "chat_id", "receive_id": chat_id}
    body = {"msg_type": "text", "content": json.dumps({"text": text})}
    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            r = client.post(
                url,
                params=params,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if r.status_code not in (200, 201):
            _log_feishu_send_failure("send_message(chat_id={})".format(chat_id[:20] if chat_id else ""), r)
            return False
        return True
    except Exception as e:
        print("[Feishu] send_message exception: {}".format(e))
        return False


def reply_to_feishu_message(message_id: str, text: str) -> bool:
    """Reply to a message (same thread). Preferred when responding to im.message.receive_v1."""
    if not message_id:
        return False
    token = get_tenant_access_token()
    if not token:
        print("[Feishu] Cannot reply: no tenant_access_token (check FEISHU_APP_ID/FEISHU_APP_SECRET).")
        return False
    url = f"{FEISHU_BASE_URL}/open-apis/im/v1/messages/{message_id}/reply"
    body = {"msg_type": "text", "content": json.dumps({"text": text})}
    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            r = client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if r.status_code not in (200, 201):
            _log_feishu_send_failure("reply(message_id={})".format(message_id[:20] if message_id else ""), r)
            return False
        return True
    except Exception as e:
        print("[Feishu] reply exception: {}".format(e))
        return False


def upload_feishu_image(token: str, image_bytes: bytes, mime_type: str = "image/png") -> str | None:
    """Upload image to Feishu; returns image_key or None. Ref: open.feishu.cn im-v1 image create."""
    if not image_bytes or not token:
        return None
    url = f"{FEISHU_BASE_URL}/open-apis/im/v1/images"
    ext = "png" if "png" in mime_type else "jpg"
    files = {"image": ("image." + ext, image_bytes, mime_type)}
    data = {"image_type": "message"}
    try:
        with httpx.Client(timeout=30, trust_env=False) as client:
            r = client.post(
                url,
                data=data,
                files=files,
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code not in (200, 201):
            _log_feishu_send_failure("upload_image", r)
            return None
        out = r.json()
        if out.get("code") != 0:
            return None
        return (out.get("data") or {}).get("image_key")
    except Exception as e:
        print("[Feishu] upload_image exception: {}".format(e))
        return None


def reply_to_feishu_message_with_image(message_id: str, image_key: str) -> bool:
    """Reply with a single image (same thread)."""
    if not message_id or not image_key:
        return False
    token = get_tenant_access_token()
    if not token:
        return False
    url = f"{FEISHU_BASE_URL}/open-apis/im/v1/messages/{message_id}/reply"
    body = {"msg_type": "image", "content": json.dumps({"image_key": image_key})}
    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            r = client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if r.status_code not in (200, 201):
            _log_feishu_send_failure("reply_image(message_id={})".format(message_id[:20] if message_id else ""), r)
            return False
        return True
    except Exception as e:
        print("[Feishu] reply_image exception: {}".format(e))
        return False


def send_feishu_image_message(chat_id: str, image_key: str) -> bool:
    """Send a new image message to a chat."""
    if not chat_id or not image_key:
        return False
    token = get_tenant_access_token()
    if not token:
        return False
    url = f"{FEISHU_BASE_URL}/open-apis/im/v1/messages"
    params = {"receive_id_type": "chat_id", "receive_id": chat_id}
    body = {"msg_type": "image", "content": json.dumps({"image_key": image_key})}
    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            r = client.post(
                url,
                params=params,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if r.status_code not in (200, 201):
            _log_feishu_send_failure("send_image(chat_id={})".format(chat_id[:20] if chat_id else ""), r)
            return False
        return True
    except Exception as e:
        print("[Feishu] send_image exception: {}".format(e))
        return False


def extract_message_text(content: str) -> str:
    """Parse Feishu message content JSON (e.g. {"text":"hello"} or {"json":"..."})."""
    if not content or not content.strip():
        return ""
    try:
        data = json.loads(content)
        if isinstance(data.get("text"), str):
            return data["text"].strip()
        return ""
    except Exception:
        return content.strip()


def _return_challenge(body: dict):
    """Return Feishu URL verification challenge. Used by both / and /feishu/events. Returns a dict for FastAPI to serialize as JSON."""
    if isinstance(body, dict) and body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        # Feishu requires challenge in response to be a string; ensure valid JSON.
        challenge_str = str(challenge) if challenge is not None else ""
        print("[Feishu] URL verification received, returning challenge (if you see this but Feishu says timeout, the response may not be reaching Feishu—check tunnel).")
        return {"challenge": challenge_str}
    return None


@app.get("/")
def read_root():
    return {
        "channel": "feishu",
        "usage": f"Configure Feishu event callback URL to this server: ...{FEISHU_EVENT_PATH}. Core from channels/.env.",
    }


async def _handle_event_body(body: dict):
    """Process Feishu event payload (after url_verification check). Used by both POST / and POST /feishu/events."""
    # Encrypted payload: Feishu can send { "encrypt": "..." }; we'd need decrypt with encrypt_key.
    if body.get("encrypt"):
        # TODO: decrypt with FEISHU_ENCRYPT_KEY if set
        return JSONResponse(status_code=200, content={})
    # Schema 2.0: header + event
    header = body.get("header") or {}
    event_type = header.get("event_type") or body.get("event_type")
    event = body.get("event") or body
    if event_type != "im.message.receive_v1":
        return JSONResponse(status_code=200, content={})
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    chat_id = message.get("chat_id", "")
    message_id = message.get("message_id", "")
    # Feishu often sends the same event twice; only process and reply once per message_id.
    if message_id:
        if message_id in _processed_message_ids:
            return JSONResponse(status_code=200, content={})
        while len(_processed_message_ids) >= _MAX_PROCESSED_IDS:
            _processed_message_ids.popitem(last=False)
        _processed_message_ids[message_id] = None
    content_str = message.get("content", "{}")
    text = extract_message_text(content_str)
    if not chat_id:
        return JSONResponse(status_code=200, content={})
    has_media = bool(
        message.get("images") or message.get("videos") or message.get("audios") or message.get("files")
    )
    if not text and not has_media:
        return JSONResponse(status_code=200, content={})
    sender_id_obj = sender.get("sender_id") or sender
    sender_id = sender_id_obj.get("user_id") if isinstance(sender_id_obj, dict) else str(sender_id_obj or "")
    user_name = (sender_id_obj.get("name") or sender.get("name")) if isinstance(sender_id_obj, dict) else str(sender_id)
    if not user_name:
        user_name = sender_id or "feishu_user"
    user_id = f"feishu_{sender_id}" if sender_id else "feishu_unknown"
    print("[Feishu] user_id={} (add to config/user.yml under im:)".format(user_id))
    payload = {
        "user_id": user_id,
        "text": text or "(no text)",
        "channel_name": "feishu",
        "user_name": user_name,
        "reply_accepts": ["text", "image"],
    }
    if message.get("images"):
        payload["images"] = message["images"]
    if message.get("videos"):
        payload["videos"] = message["videos"]
    if message.get("audios"):
        payload["audios"] = message["audios"]
    if message.get("files"):
        payload["files"] = message["files"]
    try:
        headers = Util().get_channels_core_api_headers()
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            r = await client.post(INBOUND_URL, json=payload, headers=headers)
        data = r.json() if r.content else {}
        reply = data.get("text", "")
        if not reply and r.status_code != 200:
            reply = data.get("error", "Request failed")
        _img = data.get("images")
        reply_images = _img if isinstance(_img, list) else []
        if reply:
            print("[Feishu] Core returned reply (len={}), images={}, sending to Feishu...".format(len(reply), len(reply_images)))
    except httpx.ConnectError:
        reply = "Core unreachable. Is HomeClaw running?"
        reply_images = []
    except Exception as e:
        reply = f"Error: {e}"
        reply_images = []
    reply = reply or "(no reply)"
    # Send text first (reply or send to chat).
    sent = bool(message_id and reply_to_feishu_message(message_id, reply))
    if not sent:
        sent = send_feishu_message(chat_id, reply)
    if not sent:
        print("[Feishu] Reply was not sent to Feishu (check logs above for Feishu API errors).")
    # Then send up to 5 images (upload to Feishu, then reply/send).
    token = get_tenant_access_token()
    for i, data_url in enumerate((reply_images or [])[:5]):
        if not data_url or not isinstance(data_url, str):
            continue
        raw = Util.data_url_to_bytes(data_url)
        if not raw:
            continue
        mime = "image/png" if "png" in (data_url[:50] or "") else "image/jpeg"
        if token:
            image_key = upload_feishu_image(token, raw, mime)
            if image_key:
                img_sent = bool(message_id and reply_to_feishu_message_with_image(message_id, image_key))
                if not img_sent:
                    img_sent = send_feishu_image_message(chat_id, image_key)
                if not img_sent:
                    print("[Feishu] Image {} was not sent (upload or send failed).".format(i + 1))
    return JSONResponse(status_code=200, content={})


@app.post("/")
async def read_root_post(request: Request):
    """Feishu callback at root: verification and events (when Request URL is set to tunnel root)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={})
    out = _return_challenge(body)
    if out is not None:
        return out
    return await _handle_event_body(body)


@app.post(FEISHU_EVENT_PATH)
async def handle_event(request: Request):
    """Feishu event callback at /feishu/events: verification and im.message.receive_v1."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={})
    out = _return_challenge(body)
    if out is not None:
        return out
    return await _handle_event_body(body)


def main():
    import uvicorn
    port = int(os.getenv("FEISHU_CHANNEL_PORT", "8016"))
    host = os.getenv("FEISHU_CHANNEL_HOST", "0.0.0.0")
    print(f"Feishu channel: event callback http://{host}:{port}{FEISHU_EVENT_PATH} (Core from channels/.env)")
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        print("Set FEISHU_APP_ID and FEISHU_APP_SECRET in channels/.env to send replies.")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
