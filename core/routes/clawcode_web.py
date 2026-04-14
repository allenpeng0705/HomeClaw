"""Serve Claw-Code browser UI from Core (same port as /inbound) so operators need not expose WebChat 8014."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse, JSONResponse


def clawcode_html_path() -> Path:
    """Project-relative path to channels/webchat/clawcode.html."""
    return Path(__file__).resolve().parents[2] / "channels" / "webchat" / "clawcode.html"


def get_clawcode_page_handler():
    """GET /clawcode — single-page UI; API calls use same-origin /api/clawcode/* and /inbound."""

    def handler():
        p = clawcode_html_path()
        if not p.is_file():
            return JSONResponse(status_code=404, content={"detail": "clawcode.html not found"})
        return FileResponse(str(p), media_type="text/html", filename="clawcode.html")

    return handler


def get_clawcode_web_config_handler(_core: Any):
    """
    GET /clawcode/config — same shape as WebChat GET /config for default user_id.
    Optional core.yml: clawcode.web_ui_default_user_id (default webchat_user).
    No auth: page bootstrap only; APIs still use X-API-Key when auth_enabled.
    """

    async def handler():
        try:
            from base.util import Util

            meta = Util().get_core_metadata()
            cc = getattr(meta, "clawcode", None) or {}
            uid = ""
            if isinstance(cc, dict):
                uid = str(cc.get("web_ui_default_user_id") or "").strip()
            if not uid:
                uid = "webchat_user"
        except Exception:
            uid = "webchat_user"
        return JSONResponse(content={"user_id": uid})

    return handler
