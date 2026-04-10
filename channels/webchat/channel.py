"""
WebChat channel: serves a minimal browser UI that talks to Core over WebSocket /ws.
Also serves /clawcode (IDE-style Claw-Code UI) and proxies /api/clawcode/* and POST /api/inbound to Core.
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
from starlette.responses import Response, StreamingResponse

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


def _core_auth_headers(request: Request) -> dict:
    """Use client X-API-Key if present (from UI settings), else CORE_API_KEY from env. So WebChat/control-ui can set API key in UI. Never raises."""
    try:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        key = (request.headers.get("x-api-key") or "").strip()
        if not key:
            auth = (request.headers.get("authorization") or "").strip()
            if auth.lower().startswith("bearer "):
                key = auth[7:].strip()
        if key:
            headers["x-api-key"] = key
            headers["authorization"] = f"Bearer {key}"
        else:
            env_key = (os.getenv("CORE_API_KEY") or "").strip()
            if env_key:
                headers["x-api-key"] = env_key
                headers["authorization"] = f"Bearer {env_key}"
        return headers
    except Exception:
        return {}


@app.post("/api/upload")
async def api_upload_proxy(request: Request):
    """Proxy upload to Core so the client can POST same-origin; Core saves to database/uploads/ and returns paths. Use API key from client X-API-Key (UI settings) or CORE_API_KEY in channels/.env."""
    import httpx
    upload_url = get_core_url() + "/api/upload"
    headers = _core_auth_headers(request)
    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            r = await client.post(upload_url, content=body, headers=headers)
        ct = r.headers.get("content-type", "")
        if "application/json" in ct:
            return JSONResponse(status_code=r.status_code, content=r.json())
        return JSONResponse(status_code=r.status_code, content={"paths": [], "detail": r.text})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e), "paths": []})


@app.api_route("/api/clawcode/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def api_clawcode_proxy(request: Request, path: str):
    """Forward Claw-Code REST API to Core (same-origin from browser; auth via client X-API-Key or CORE_API_KEY)."""
    import httpx

    base = get_core_url().rstrip("/")
    target = f"{base}/api/clawcode/{path}"
    q = request.url.query
    if q:
        target = target + "?" + q
    headers = dict(_core_auth_headers(request))
    for drop in ("host", "content-length", "connection"):
        headers.pop(drop, None)
    body = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
    if body and "content-type" not in {k.lower() for k in headers}:
        ct = (request.headers.get("content-type") or "").strip()
        if ct:
            headers["content-type"] = ct
    try:
        async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
            r = await client.request(request.method, target, content=body, headers=headers)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    ct = r.headers.get("content-type") or ""
    if "application/json" in ct:
        try:
            return JSONResponse(status_code=r.status_code, content=r.json())
        except Exception:
            return Response(content=r.content or b"", status_code=r.status_code, media_type=ct or "text/plain")
    return Response(content=r.content or b"", status_code=r.status_code, media_type=ct or "application/octet-stream")


@app.post("/api/inbound")
async def api_inbound_proxy(request: Request):
    """Proxy POST /inbound to Core. When JSON body has stream: true, stream SSE back to the client (Claw-Code UI progress)."""
    import json

    import httpx

    body = await request.body()
    url = get_core_url().rstrip("/") + "/inbound"
    headers = dict(_core_auth_headers(request))
    for drop in ("host", "content-length", "connection"):
        headers.pop(drop, None)
    headers["content-type"] = (request.headers.get("content-type") or "application/json").strip() or "application/json"
    is_stream = False
    try:
        jd = json.loads(body.decode("utf-8") or "{}")
        is_stream = bool(jd.get("stream"))
    except Exception:
        pass

    if is_stream:

        async def sse_gen():
            async with httpx.AsyncClient(timeout=600.0, trust_env=False) as client:
                async with client.stream("POST", url, content=body, headers=headers) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk

        return StreamingResponse(sse_gen(), media_type="text/event-stream")

    try:
        async with httpx.AsyncClient(timeout=600.0, trust_env=False) as client:
            r = await client.post(url, content=body, headers=headers)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e), "text": ""})
    ct = r.headers.get("content-type") or ""
    if "application/json" in ct:
        try:
            return JSONResponse(status_code=r.status_code, content=r.json())
        except Exception:
            return JSONResponse(status_code=r.status_code, content={"detail": r.text, "text": ""})
    return Response(content=r.content or b"", status_code=r.status_code, media_type=ct or "text/plain")


@app.get("/api/knowledge_base/sync_folder")
@app.post("/api/knowledge_base/sync_folder")
async def api_kb_sync_folder_proxy(request: Request):
    """Proxy to Core GET/POST /knowledge_base/sync_folder so the client can trigger manual KB folder sync (same-origin). Pass user_id as query param or in POST body. Use API key from client X-API-Key or CORE_API_KEY in env."""
    import httpx
    sync_url = get_core_url() + "/knowledge_base/sync_folder"
    if request.method == "GET":
        sync_url = sync_url + "?" + request.url.query
    headers = _core_auth_headers(request)
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
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


@app.get("/clawcode", response_class=HTMLResponse)
def clawcode_page():
    """Dedicated Claw-Code coding UI (sessions, SSE progress, approvals)."""
    html_path = CHANNEL_DIR / "clawcode.html"
    if not html_path.exists():
        return HTMLResponse(
            "<!DOCTYPE html><html><body><p>clawcode.html not found.</p></body></html>",
            status_code=404,
        )
    return FileResponse(html_path, media_type="text/html")


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
