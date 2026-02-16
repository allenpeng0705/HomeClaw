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
        with httpx.Client() as client:
            r = client.post(TOKEN_URL, data=data, timeout=10)
        if r.status_code != 200:
            return None
        return r.json().get("access_token")
    except Exception:
        return None


def send_reply(activity: dict, reply_text: str) -> bool:
    """Send reply via Bot Framework Connector API."""
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
    # Bot Framework: POST to .../activities/{activityId} to send reply
    url = f"{service_url}/v3/conversations/{conv_id}/activities/{reply_to_id}" if reply_to_id else f"{service_url}/v3/conversations/{conv_id}/activities"
    try:
        with httpx.Client() as client:
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


@app.post("/api/messages")
async def api_messages(request: Request):
    """
    Bot Framework sends activities here. On type=message: forward to Core /inbound, send reply via Connector.
    """
    try:
        activity = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={})
    if activity.get("type") != "message":
        return JSONResponse(status_code=200, content={})
    text = (activity.get("text") or "").strip()
    if not text:
        return JSONResponse(status_code=200, content={})
    from_act = activity.get("from") or {}
    user_id = from_act.get("id", "")
    user_name = from_act.get("name") or user_id
    inbound_id = f"teams_{user_id}"
    payload = {
        "user_id": inbound_id,
        "text": text,
        "channel_name": "teams",
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
    if not send_reply(activity, reply):
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
