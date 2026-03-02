"""
Microsoft Teams channel: receives Bot Framework activities (HTTP endpoint).
On message activity: forward to Core /inbound, then send reply via Bot Framework Connector API.
Core connection from channels/.env only. Set TEAMS_APP_ID and TEAMS_APP_PASSWORD in channels/.env to send replies.
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

app = FastAPI(title="HomeClaw Teams Channel")
INBOUND_URL = f"{Util().get_channels_core_url()}/inbound"

TEAMS_APP_ID = os.getenv("TEAMS_APP_ID") or os.getenv("MICROSOFT_APP_ID")
TEAMS_APP_PASSWORD = os.getenv("TEAMS_APP_PASSWORD") or os.getenv("MICROSOFT_APP_PASSWORD")
TOKEN_URL = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"


def get_connector_token() -> str | None:
    if not TEAMS_APP_ID or not TEAMS_APP_PASSWORD:
        return None
    data = {
        "grant_type": "client_credentials",
        "client_id": TEAMS_APP_ID,
        "client_secret": TEAMS_APP_PASSWORD,
        "scope": "https://api.botframework.com/.default",
    }
    try:
        with httpx.Client(trust_env=False) as client:
            r = client.post(TOKEN_URL, data=data, timeout=10)
        if r.status_code != 200:
            return None
        return r.json().get("access_token")
    except Exception:
        return None


def _image_to_content_url(item: str) -> str | None:
    """Return a contentUrl for Bot Framework: data URL as-is, or path read and converted to data URL. Returns None on failure."""
    if not item or not isinstance(item, str):
        return None
    s = item.strip()
    if s.startswith("data:"):
        return s
    import base64
    if os.path.isfile(s):
        try:
            with open(s, "rb") as f:
                raw = f.read()
            ext = (s.lower().split(".")[-1] if "." in s else "png") or "png"
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return None
    return None


def send_reply(activity: dict, reply_text: str, image_content_urls: list | None = None) -> bool:
    """Send reply via Bot Framework Connector API. image_content_urls: list of data URLs or file paths (converted to data URL)."""
    token = get_connector_token()
    if not token:
        return False
    service_url = (activity.get("serviceUrl") or "").rstrip("/")
    conversation = activity.get("conversation") or {}
    conv_id = conversation.get("id", "")
    from_act = activity.get("from") or {}
    recipient = activity.get("recipient") or {}
    reply_to_id = activity.get("id", "")
    reply_activity = {
        "type": "message",
        "from": recipient,
        "recipient": from_act,
        "conversation": conversation,
        "text": reply_text,
        "replyToId": reply_to_id,
    }
    attachments = []
    for item in (image_content_urls or [])[:5]:
        url = _image_to_content_url(item)
        if url:
            mime = "image/png"
            if "image/jpeg" in url[:50] or "image/jpg" in url[:50]:
                mime = "image/jpeg"
            attachments.append({"contentType": mime, "contentUrl": url, "name": "image.png"})
    if attachments:
        reply_activity["attachments"] = attachments
    url = f"{service_url}/v3/conversations/{conv_id}/activities/{reply_to_id}" if reply_to_id else f"{service_url}/v3/conversations/{conv_id}/activities"
    try:
        with httpx.Client(trust_env=False) as client:
            r = client.post(
                url,
                json=reply_activity,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=30,
            )
        return r.status_code in (200, 201)
    except Exception:
        return False


@app.get("/")
def read_root():
    return {"channel": "teams", "usage": "Configure this URL as your Bot Framework / Teams bot messaging endpoint."}


def _content_type_media_kind(content_type: str) -> str:
    """Return 'image', 'video', 'audio', or 'file' from MIME type."""
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"
    return "file"


async def _download_teams_attachment_to_data_url(content_url: str) -> str | None:
    """Download Bot Framework attachment URL and return data URL. Returns None on failure."""
    if (content_url or "").startswith("data:"):
        return content_url
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.get(content_url, timeout=30)
        if r.status_code != 200:
            return None
        import base64
        b64 = base64.b64encode(r.content).decode("ascii")
        ct = r.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        return f"data:{ct};base64,{b64}"
    except Exception:
        return None


@app.post("/api/messages")
async def api_messages(request: Request):
    """
    Bot Framework sends activities here. On type=message: forward to Core /inbound, send reply via Connector.
    Supports text and attachments (image, video, audio, file).
    """
    try:
        activity = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={})
    if activity.get("type") != "message":
        return JSONResponse(status_code=200, content={})
    text = (activity.get("text") or "").strip()
    attachments = activity.get("attachments") or []
    from_act = activity.get("from") or {}
    user_id = from_act.get("id", "")
    user_name = from_act.get("name") or user_id
    inbound_id = f"teams_{user_id}"

    images, videos, audios, files = [], [], [], []
    for att in attachments[:15]:
        content_url = (att.get("contentUrl") or "").strip()
        if not content_url:
            continue
        content_type = att.get("contentType") or ""
        kind = _content_type_media_kind(content_type)
        data_url = await _download_teams_attachment_to_data_url(content_url)
        if data_url:
            if kind == "image":
                images.append(data_url)
            elif kind == "video":
                videos.append(data_url)
            elif kind == "audio":
                audios.append(data_url)
            else:
                files.append(data_url)

    if not text and not (images or videos or audios or files):
        return JSONResponse(status_code=200, content={})
    if not text:
        text = "(no text)"

    payload = {
        "user_id": inbound_id,
        "text": text,
        "channel_name": "teams",
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
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.post(INBOUND_URL, json=payload, headers=headers, timeout=120.0)
        data = r.json() if r.content else {}
        reply = data.get("text", "")
        if not reply and r.status_code != 200:
            reply = data.get("error", "Request failed")
        reply_images = data.get("images") or ([data["image"]] if data.get("image") else [])
    except httpx.ConnectError:
        reply = "Core unreachable. Is HomeClaw running?"
        reply_images = []
    except Exception as e:
        reply = f"Error: {e}"
        reply_images = []
    reply = reply or "(no reply)"
    if not send_reply(activity, reply, image_content_urls=reply_images if reply_images else None):
        # Still return 200 so Teams doesn't retry; reply may not have been sent
        pass
    return JSONResponse(status_code=200, content={})


def main():
    import uvicorn
    port = int(os.getenv("TEAMS_CHANNEL_PORT", "8013"))
    host = os.getenv("TEAMS_CHANNEL_HOST", "0.0.0.0")
    print(f"Teams channel: endpoint http://{host}:{port}/api/messages (Core from channels/.env)")
    if not TEAMS_APP_ID or not TEAMS_APP_PASSWORD:
        print("Set TEAMS_APP_ID and TEAMS_APP_PASSWORD (or MICROSOFT_APP_ID, MICROSOFT_APP_PASSWORD) in channels/.env to send replies.")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
