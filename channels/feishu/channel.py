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

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv(_root / "channels" / ".env")
from base.util import Util

app = FastAPI(title="HomeClaw Feishu Channel")
INBOUND_URL = f"{Util().get_channels_core_url()}/inbound"

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_BASE_URL = os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/")
FEISHU_EVENT_PATH = os.getenv("FEISHU_EVENT_PATH", "/feishu/events")


def get_tenant_access_token() -> str | None:
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        return None
    url = f"{FEISHU_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal"
    try:
        with httpx.Client() as client:
            r = client.post(
                url,
                json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
                timeout=10,
            )
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("code") != 0:
            return None
        return data.get("tenant_access_token")
    except Exception:
        return None


def send_feishu_message(chat_id: str, text: str) -> bool:
    token = get_tenant_access_token()
    if not token:
        return False
    url = f"{FEISHU_BASE_URL}/open-apis/im/v1/messages"
    params = {"receive_id_type": "chat_id", "receive_id": chat_id}
    body = {"msg_type": "text", "content": json.dumps({"text": text})}
    try:
        with httpx.Client() as client:
            r = client.post(
                url,
                params=params,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=15,
            )
        return r.status_code in (200, 201)
    except Exception:
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


@app.get("/")
def read_root():
    return {
        "channel": "feishu",
        "usage": f"Configure Feishu event callback URL to this server: ...{FEISHU_EVENT_PATH}. Core from channels/.env.",
    }


@app.post(FEISHU_EVENT_PATH)
async def handle_event(request: Request):
    """
    Feishu event subscription callback.
    - url_verification: return challenge for URL verification.
    - im.message.receive_v1: forward to Core /inbound, send reply via Feishu API.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={})
    # URL verification (Feishu sends this when configuring callback URL)
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}
    # Encrypted payload: Feishu can send { "encrypt": "..." }; we'd need decrypt with encrypt_key.
    # For simplicity we support non-encrypted or already-decrypted event in body.
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
    content_str = message.get("content", "{}")
    text = extract_message_text(content_str)
    if not text or not chat_id:
        return JSONResponse(status_code=200, content={})
    sender_id_obj = sender.get("sender_id") or sender
    sender_id = sender_id_obj.get("user_id") if isinstance(sender_id_obj, dict) else str(sender_id_obj or "")
    user_name = (sender_id_obj.get("name") or sender.get("name")) if isinstance(sender_id_obj, dict) else str(sender_id)
    if not user_name:
        user_name = sender_id or "feishu_user"
    user_id = f"feishu_{sender_id}" if sender_id else "feishu_unknown"
    payload = {
        "user_id": user_id,
        "text": text,
        "channel_name": "feishu",
        "user_name": user_name,
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(INBOUND_URL, json=payload, timeout=120.0)
        data = r.json() if r.content else {}
        reply = data.get("text", "")
        if not reply and r.status_code != 200:
            reply = data.get("error", "Request failed")
    except httpx.ConnectError:
        reply = "Core unreachable. Is HomeClaw running?"
    except Exception as e:
        reply = f"Error: {e}"
    reply = reply or "(no reply)"
    send_feishu_message(chat_id, reply)
    return JSONResponse(status_code=200, content={})


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
