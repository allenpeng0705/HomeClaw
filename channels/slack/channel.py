"""
Minimal Slack channel using Core POST /inbound (Socket Mode: no public URL needed).
Supports text and file attachments. Run: set SLACK_APP_TOKEN, SLACK_BOT_TOKEN in channels/.env.
Add slack_<user_id> to config/user.yml (im: list) for allowed users.
"""
import base64
import os
from pathlib import Path
from typing import List, Optional

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_root))

from dotenv import load_dotenv
import httpx

# Core connection: channels/.env only
load_dotenv(_root / "channels" / ".env")
from base.util import Util
CORE_URL = Util().get_channels_core_url()
INBOUND_URL = f"{CORE_URL}/inbound"

# Bot tokens: channels/.env or channels/slack/.env
load_dotenv(Path(__file__).resolve().parent / ".env")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")  # xapp-...
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # xoxb-...

if not SLACK_APP_TOKEN or not SLACK_BOT_TOKEN:
    raise SystemExit("Set SLACK_APP_TOKEN and SLACK_BOT_TOKEN in .env or environment")


def download_slack_file_to_data_url(url: str, bot_token: str, content_type: Optional[str] = None) -> Optional[str]:
    """Download Slack file URL (with auth) and return data URL. Never raises."""
    try:
        headers = {"Authorization": f"Bearer {bot_token}"}
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url, headers=headers)
        if r.status_code != 200 or not r.content:
            return None
        ct = content_type or r.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        b64 = base64.b64encode(r.content).decode("ascii")
        return f"data:{ct};base64,{b64}"
    except Exception:
        return None


def post_to_core_sync(
    user_id: str,
    user_name: str,
    text: str,
    images: Optional[List[str]] = None,
    videos: Optional[List[str]] = None,
    audios: Optional[List[str]] = None,
    files: Optional[List[str]] = None,
) -> str:
    payload = {
        "user_id": user_id,
        "text": text or "(no text)",
        "channel_name": "slack",
        "user_name": user_name,
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
        with httpx.Client() as client:
            r = client.post(INBOUND_URL, json=payload, timeout=120.0)
        data = r.json()
        reply = data.get("text", "")
        if not reply and r.status_code != 200:
            reply = data.get("error", "Request failed")
    except httpx.ConnectError:
        reply = "Core unreachable. Is HomeClaw running?"
    except Exception as e:
        reply = f"Error: {e}"
    return reply or "(no reply)"


def main():
    try:
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.response import SocketModeResponse
        from slack_sdk.socket_mode.request import SocketModeRequest
    except ImportError:
        raise SystemExit("Install slack_sdk: pip install -r requirements.txt")

    web_client = WebClient(token=SLACK_BOT_TOKEN)
    socket_client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

    def process(client: SocketModeClient, req: SocketModeRequest):
        if req.type != "events_api":
            return
        event = req.payload.get("event", {})
        if event.get("type") != "message" or event.get("subtype"):
            return
        text = (event.get("text") or "").strip()
        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        ts = event.get("ts", "")
        if not user_id or not channel_id:
            return
        images, videos, audios, files = [], [], [], []
        for f in event.get("files") or []:
            url = f.get("url_private") or f.get("url_private_download")
            if not url:
                continue
            mimetype = (f.get("mimetype") or "").lower()
            data_url = download_slack_file_to_data_url(url, SLACK_BOT_TOKEN, f.get("mimetype"))
            if not data_url:
                continue
            if "image/" in mimetype:
                images.append(data_url)
            elif "video/" in mimetype:
                videos.append(data_url)
            elif "audio/" in mimetype:
                audios.append(data_url)
            else:
                files.append(data_url)
        if not text and not (images or videos or audios or files):
            return
        if not text:
            text = "Image" if images else "Video" if videos else "Audio" if audios else "File" if files else "(no text)"
        # Acknowledge immediately
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        try:
            u = web_client.users_info(user=user_id)
            user_name = (u.get("user") or {}).get("real_name") or user_id
        except Exception:
            user_name = user_id
        inbound_id = f"slack_{user_id}"
        reply = post_to_core_sync(
            inbound_id,
            user_name,
            text,
            images=images if images else None,
            videos=videos if videos else None,
            audios=audios if audios else None,
            files=files if files else None,
        )
        try:
            web_client.chat_postMessage(channel=channel_id, thread_ts=ts, text=reply[:4000] if len(reply) > 4000 else reply)
        except Exception as e:
            print("Slack post error:", e)

    socket_client.socket_mode_request_listeners.append(process)
    print(f"Slack channel: forwarding to {INBOUND_URL} (Socket Mode)")
    socket_client.connect()


if __name__ == "__main__":
    main()
