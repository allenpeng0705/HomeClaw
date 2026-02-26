"""
Core API auth: verify X-API-Key or Bearer for HTTP and WebSocket.
Used by /inbound, /ws, and other protected routes. Never raises except HTTPException(401).
"""
from fastapi import Request, HTTPException
from fastapi import WebSocket

from base.util import Util


def verify_inbound_auth(request: Request) -> None:
    """When auth_enabled and auth_api_key are set, require X-API-Key or Authorization: Bearer for /inbound and protected routes."""
    try:
        meta = Util().get_core_metadata()
        if not getattr(meta, "auth_enabled", False):
            return
        expected = (getattr(meta, "auth_api_key", "") or "").strip()
        if not expected:
            return
        key = (request.headers.get("X-API-Key") or "").strip()
        if not key:
            auth_h = (request.headers.get("Authorization") or "").strip()
            if auth_h.startswith("Bearer "):
                key = auth_h[7:].strip()
        if key != expected:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def ws_auth_ok(websocket: WebSocket) -> bool:
    """Check API key from WebSocket handshake headers or query (?api_key= or ?X-API-Key=). Return True if auth disabled or key valid."""
    try:
        meta = Util().get_core_metadata()
        if not getattr(meta, "auth_enabled", False):
            return True
        expected = (getattr(meta, "auth_api_key", "") or "").strip()
        if not expected:
            return True
        key = ""
        headers = dict((k.decode().lower(), v.decode()) for k, v in websocket.scope.get("headers", []))
        key = (headers.get("x-api-key") or "").strip()
        if not key and (headers.get("authorization") or "").strip().startswith("Bearer "):
            auth_h = (headers.get("authorization") or "").strip()
            key = auth_h[7:].strip() if len(auth_h) > 7 else ""
        if not key and websocket.scope.get("query_string"):
            from urllib.parse import parse_qs
            qs = parse_qs(websocket.scope["query_string"].decode())
            key = (qs.get("api_key") or qs.get("x-api-key") or [""])[0].strip()
        return key == expected
    except Exception:
        return False
