"""
Google Chat channel: receives Google Chat API interaction events (HTTP endpoint).
Configure your Chat app in Google Cloud (Chat API) with this server's URL.
Core connection from channels/.env only.
"""
import os
import sys
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

app = FastAPI(title="HomeClaw Google Chat Channel")
INBOUND_URL = f"{Util().get_channels_core_url()}/inbound"


def get_text_from_event(event: dict) -> str:
    """Extract message text from Google Chat Event (MESSAGE type)."""
    msg = event.get("message") or {}
    if isinstance(msg.get("text"), str):
        return msg["text"].strip()
    # Slash command or argumentText
    if isinstance(msg.get("argumentText"), str):
        return msg["argumentText"].strip()
    return ""


def get_user_id(event: dict) -> str:
    """Google Chat user id for allowlist (e.g. google_chat_<id>)."""
    user = event.get("user") or {}
    uid = user.get("name") or user.get("displayName") or ""
    if uid.startswith("users/"):
        uid = uid.replace("users/", "")
    return f"google_chat_{uid}" if uid else "google_chat_unknown"


@app.get("/")
def read_root():
    return {"channel": "google_chat", "usage": "Configure this URL as your Google Chat app HTTP endpoint."}


@app.post("/")
async def handle_event(request: Request):
    """
    Google Chat sends interaction events here. Handle MESSAGE: forward to Core /inbound, return text.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"text": "Invalid JSON"})
    event_type = body.get("type") or ""
    if event_type == "ADDED_TO_SPACE":
        return {"text": "Hi! I'm HomeClaw. Send me a message and I'll reply. (Add google_chat_<your_id> to config/user.yml to allow access.)"}
    if event_type != "MESSAGE":
        return {}
    text = get_text_from_event(body)
    if not text:
        return {"text": "(Send a text message.)"}
    user_id = get_user_id(body)
    user = (body.get("user") or {})
    user_name = user.get("displayName") or user_id
    payload = {
        "user_id": user_id,
        "text": text or "(no text)",
        "channel_name": "google_chat",
        "user_name": user_name,
    }
    # Optional: attachment data URLs (if bridge or app provides them)
    msg = body.get("message") or {}
    if msg.get("images"):
        payload["images"] = msg["images"]
    if msg.get("videos"):
        payload["videos"] = msg["videos"]
    if msg.get("audios"):
        payload["audios"] = msg["audios"]
    if msg.get("files"):
        payload["files"] = msg["files"]
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
    return {"text": reply or "(no reply)"}


def main():
    import uvicorn
    port = int(os.getenv("GOOGLE_CHAT_PORT", "8010"))
    host = os.getenv("GOOGLE_CHAT_HOST", "0.0.0.0")
    print(f"Google Chat channel: HTTP endpoint http://{host}:{port}/ (Core from channels/.env)")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
