"""
WebChat channel: serves a minimal browser UI that talks to Core over WebSocket /ws.
Core URL from channels/.env only. No IM bot token; ensure the default user (e.g. webchat_user) exists in config/user.yml so Core accepts WebSocket/inbound by user id/name.
Sync with system_plugins/homeclaw-browser control-ui: same upload-then-path flow for images (POST /api/upload → Core saves → client sends paths).
"""
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

load_dotenv(_root / "channels" / ".env")
from base.util import Util

app = FastAPI(title="HomeClaw WebChat")
CHANNEL_DIR = Path(__file__).resolve().parent


def get_core_url() -> str:
    return Util().get_channels_core_url().rstrip("/")


def get_ws_url() -> str:
    core_url = get_core_url()
    if core_url.startswith("https://"):
        ws_url = "wss://" + core_url[8:] + "/ws"
    else:
        ws_url = "ws://" + core_url.replace("http://", "").replace("https://", "") + "/ws"
    return ws_url


@app.get("/config")
def config():
    """Return Core WebSocket URL and default user_id for the client. From channels/.env only. Default webchat_user matches sample config/user.yml."""
    return {
        "ws_url": get_ws_url(),
        "user_id": os.getenv("WEBCHAT_USER_ID", "webchat_user"),
    }


@app.post("/api/upload")
async def api_upload_proxy(request: Request):
    """Proxy upload to Core so the client can POST same-origin; Core saves to database/uploads/ and returns paths. Optional: set CORE_API_KEY in channels/.env if Core has auth_enabled."""
    import httpx
    upload_url = get_core_url() + "/api/upload"
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    if os.getenv("CORE_API_KEY"):
        headers["x-api-key"] = os.getenv("CORE_API_KEY", "").strip()
    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(upload_url, content=body, headers=headers)
        ct = r.headers.get("content-type", "")
        if "application/json" in ct:
            return JSONResponse(status_code=r.status_code, content=r.json())
        return JSONResponse(status_code=r.status_code, content={"paths": [], "detail": r.text})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e), "paths": []})


@app.get("/api/knowledge_base/sync_folder")
@app.post("/api/knowledge_base/sync_folder")
async def api_kb_sync_folder_proxy(request: Request):
    """Proxy to Core GET/POST /knowledge_base/sync_folder so the client can trigger manual KB folder sync (same-origin). Pass user_id as query param or in POST body."""
    import httpx
    sync_url = get_core_url() + "/knowledge_base/sync_folder"
    if request.method == "GET":
        sync_url = sync_url + "?" + request.url.query
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    if os.getenv("CORE_API_KEY"):
        headers["x-api-key"] = os.getenv("CORE_API_KEY", "").strip()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if request.method == "GET":
                r = await client.get(sync_url, headers=headers)
            else:
                body = await request.body()
                r = await client.post(sync_url, content=body, headers=headers)
        ct = r.headers.get("content-type", "")
        if "application/json" in ct:
            return JSONResponse(status_code=r.status_code, content=r.json())
        return JSONResponse(status_code=r.status_code, content={"ok": False, "message": r.text})
    except Exception as e:
        return JSONResponse(status_code=502, content={"ok": False, "message": str(e)})


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
