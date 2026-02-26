"""
Core lifecycle routes: register_channel, deregister_channel, ready, pinggy, shutdown.
Handlers are returned as closures over core (and optional pinggy_state getter) so core.py can register them on self.app.
"""
import base64
import html as html_module
import os
from typing import Callable, Dict, Any

from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
import yaml

from base.base import RegisterChannelRequest
from base.util import Util


def get_register_channel_handler(core):
    """Returns async handler for POST /register_channel."""

    async def register_channel(request: RegisterChannelRequest):
        logger.debug(f"Received channel registration request: {request.name}")
        try:
            core.register_channel(request.name, request.host, request.port, request.endpoints)
            _, _, _, host_llm, port_llm = Util().main_llm()
            language = Util().main_llm_language()
            return {"result": "Succeed", "host": host_llm, "port": port_llm, "language": language}
        except Exception as e:
            logger.exception(e)
            return {"result": str(e)}

    return register_channel


def get_deregister_channel_handler(core):
    """Returns async handler for POST /deregister_channel."""

    async def deregister_channel(request: RegisterChannelRequest):
        logger.debug(f"Received channel deregistration request: {request.name}")
        try:
            core.deregister_channel(request.name, request.host, request.port, request.endpoints)
            return {"result": "Channel deregistration successful " + request.name}
        except Exception as e:
            logger.exception(e)
            return {"result": str(e)}

    return deregister_channel


def get_ready_handler(core):
    """Returns async handler for GET /ready."""

    async def ready():
        if getattr(core, "_core_http_ready", False):
            return JSONResponse(status_code=200, content={"status": "ok"})
        return JSONResponse(status_code=503, content={"status": "initializing"})

    return ready


def get_pinggy_handler(core, get_pinggy_state: Callable[[], Dict[str, Any]]):
    """Returns async handler for GET /pinggy. get_pinggy_state() returns the global _pinggy_state dict from core."""

    async def pinggy_page():
        try:
            core_yml_path = os.path.join(Util().config_path(), "core.yml")
            if os.path.isfile(core_yml_path):
                with open(core_yml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                configured_public_url = (data.get("core_public_url") or "").strip()
                if configured_public_url:
                    meta = Util().get_core_metadata()
                    auth_enabled = bool(getattr(meta, "auth_enabled", False))
                    auth_api_key = (getattr(meta, "auth_api_key", None) or "").strip()
                    connect_url_raw = f"homeclaw://connect?url={configured_public_url}"
                    if auth_enabled and auth_api_key:
                        connect_url_raw = f"homeclaw://connect?url={configured_public_url}&api_key={auth_api_key}"
                    qr_base64 = None
                    try:
                        import qrcode
                        import io
                        qr = qrcode.QRCode(version=1, box_size=6, border=2)
                        qr.add_data(connect_url_raw)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        qr_base64 = base64.b64encode(buf.getvalue()).decode("ascii")
                    except Exception:
                        pass
                    qr_img = f'<img src="data:image/png;base64,{qr_base64}" alt="QR code" style="max-width:280px;height:auto;">' if qr_base64 else ""
                    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>HomeClaw — Scan to connect</title></head><body style="font-family:sans-serif;padding:2rem;max-width:480px;">
                        <h1>Scan to connect</h1>
                        <p>Scan this QR code with <strong>HomeClaw Companion</strong>: Settings → Scan QR to connect.</p>
                        {qr_img}
                        <p><strong>Public URL:</strong> <code style="word-break:break-all;">{html_module.escape(configured_public_url)}</code></p>
                        <p><strong>Connect URL:</strong> <code style="word-break:break-all;">{html_module.escape(connect_url_raw)}</code></p>
                        </body></html>"""
                    return HTMLResponse(content=html)
        except Exception as e:
            logger.debug("core_public_url /pinggy page failed: {}", e)
        state = get_pinggy_state() if get_pinggy_state else {}
        err = state.get("error")
        if err:
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>HomeClaw — Pinggy</title></head><body style="font-family:sans-serif;padding:2rem;">
            <h1>Pinggy tunnel</h1><p>Error: {html_module.escape(str(err))}</p></body></html>"""
            return HTMLResponse(content=html)
        public_url = state.get("public_url")
        connect_url = state.get("connect_url")
        qr_base64 = state.get("qr_base64")
        if not public_url and not connect_url:
            html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>HomeClaw — Scan to connect</title></head><body style="font-family:sans-serif;padding:2rem;">
                <h1>Scan to connect</h1><p>Set <strong>core_public_url</strong> in core.yml (e.g. your Cloudflare Tunnel URL) or set <strong>pinggy.token</strong> to use Pinggy. Then open this page again.</p></body></html>"""
            return HTMLResponse(content=html)
        if not connect_url:
            connect_url = public_url or ""
        qr_img = f'<img src="data:image/png;base64,{qr_base64}" alt="QR code" style="max-width:280px;height:auto;">' if qr_base64 else ""
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>HomeClaw — Scan to connect</title></head><body style="font-family:sans-serif;padding:2rem;max-width:480px;">
            <h1>Scan to connect</h1>
            <p>Scan this QR code with <strong>HomeClaw Companion</strong>: Settings → Scan QR to connect.</p>
            {qr_img}
            <p><strong>Public URL:</strong> <code style="word-break:break-all;">{html_module.escape(public_url or "")}</code></p>
            <p><strong>Connect URL:</strong> <code style="word-break:break-all;">{html_module.escape(connect_url)}</code></p>
            </body></html>"""
        return HTMLResponse(content=html)

    return pinggy_page


def get_shutdown_handler(core):
    """Returns async handler for GET /shutdown."""

    async def shutdown():
        try:
            logger.debug("Shutdown request received, shutting down...")
            core.stop()
        except Exception as e:
            logger.exception(e)

    return shutdown
