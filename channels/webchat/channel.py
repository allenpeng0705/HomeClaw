"""
WebChat channel: serves a minimal browser UI that talks to Core over WebSocket /ws.
Core URL from channels/.env only. No IM bot token; add webchat_<user_id> to config/user.yml if you restrict by user.
"""
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse

load_dotenv(_root / "channels" / ".env")
from base.util import Util

app = FastAPI(title="HomeClaw WebChat")
CHANNEL_DIR = Path(__file__).resolve().parent


def get_ws_url() -> str:
    core_url = Util().get_channels_core_url()
    if core_url.startswith("https://"):
        ws_url = "wss://" + core_url[8:] + "/ws"
    else:
        ws_url = "ws://" + core_url.replace("http://", "").replace("https://", "") + "/ws"
    return ws_url


@app.get("/config")
def config():
    """Return Core WebSocket URL and default user_id for the client. From channels/.env only."""
    return {
        "ws_url": get_ws_url(),
        "user_id": os.getenv("WEBCHAT_USER_ID", "webchat_local"),
    }


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the WebChat UI."""
    html_path = CHANNEL_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse(
            "<!DOCTYPE html><html><body><p>WebChat: index.html not found.</p><p>Connect to Core WebSocket: "
            + get_ws_url()
            + "</p></body></html>"
        )
    return FileResponse(html_path, media_type="text/html")


def main():
    import uvicorn
    port = int(os.getenv("WEBCHAT_PORT", "8014"))
    host = os.getenv("WEBCHAT_HOST", "0.0.0.0")
    print(f"WebChat: http://{host}:{port}/ (Core WS from channels/.env)")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
