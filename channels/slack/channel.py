"""
Minimal Slack channel using Core POST /inbound (Socket Mode: no public URL needed).
Run: set SLACK_APP_TOKEN, SLACK_BOT_TOKEN in channels/.env; core connection from channels/.env (core_host, core_port or CORE_URL).
Add slack_<user_id> to config/user.yml (im: list) for allowed users.
"""
import os
from pathlib import Path

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


def post_to_core_sync(user_id: str, user_name: str, text: str) -> str:
    payload = {
        "user_id": user_id,
        "text": text,
        "channel_name": "slack",
        "user_name": user_name,
    }
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
        if not text:
            return
        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        ts = event.get("ts", "")
        if not user_id or not channel_id:
            return
        # Acknowledge immediately
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        # Resolve user name
        try:
            u = web_client.users_info(user=user_id)
            user_name = (u.get("user") or {}).get("real_name") or user_id
        except Exception:
            user_name = user_id
        inbound_id = f"slack_{user_id}"
        reply = post_to_core_sync(inbound_id, user_name, text)
        try:
            web_client.chat_postMessage(channel=channel_id, thread_ts=ts, text=reply)
        except Exception as e:
            print("Slack post error:", e)

    socket_client.socket_mode_request_listeners.append(process)
    print(f"Slack channel: forwarding to {INBOUND_URL} (Socket Mode)")
    socket_client.connect()


if __name__ == "__main__":
    main()
