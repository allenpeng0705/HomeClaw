"""
Peer / multi-instance API: instance identity, pairing invites.

GET /api/instance/identity — public metadata (no auth).
POST /api/peer/invite/create — requires Core API key when auth_enabled.
POST /api/peer/invite/consume — authenticated by invite_token only (no Core API key).
"""

from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from base.peer_registry import (
    create_pairing_invite,
    load_instance_identity,
    peer_invite_consume_all_attempts_exceeded,
    peer_invite_consume_record_attempt,
    peer_invite_consume_record_failed_verify,
    prune_stale_invites,
    verify_and_consume_invite,
)
from base.util import Util


class InviteConsumeBody(BaseModel):
    invite_id: str = Field(..., min_length=1)
    invite_token: str = Field(..., min_length=1)
    instance_id: str = ""
    display_name: str = ""
    initiator_base_url: str = ""
    # user_id the recipient Core should use when calling the initiator's POST /inbound (must exist on initiator's user.yml).
    initiator_inbound_user_id: str = ""


def _pairing_enabled() -> bool:
    try:
        return bool(getattr(Util().get_core_metadata(), "peer_pairing_enabled", True))
    except Exception:
        return True


def _client_ip_for_rate_limit(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    try:
        if request.client and request.client.host:
            return str(request.client.host)
    except Exception:
        pass
    return "unknown"


def _resolve_public_base_url(request: Request, configured: str) -> str:
    c = (configured or "").strip().rstrip("/")
    if c:
        return c
    try:
        xf_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
        xf_host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
        if xf_host:
            proto = xf_proto or "https"
            return f"{proto}://{xf_host}".rstrip("/")
    except Exception:
        pass
    try:
        u = str(request.base_url).rstrip("/")
        if u and u.startswith("http"):
            return u
    except Exception:
        pass
    return ""


def get_api_instance_identity_get_handler(core: Any):
    async def _handler() -> JSONResponse:
        try:
            ident = load_instance_identity()
            body = {
                "instance_id": ident.get("instance_id") or "",
                "display_name": ident.get("display_name") or "",
                "capabilities": ident.get("capabilities") or [],
                "version_hint": ident.get("version_hint") or "",
                "pairing_inbound_user_id": ident.get("pairing_inbound_user_id") or "",
            }
            return JSONResponse(content=body)
        except Exception as e:
            logger.warning("instance identity GET failed: {}", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    return _handler


def get_api_peer_invite_create_handler(core: Any):
    async def _handler(request: Request) -> JSONResponse:
        try:
            if not _pairing_enabled():
                return JSONResponse(
                    status_code=404,
                    content={"error": "peer_pairing_disabled", "hint": "Set peer_pairing_enabled: true in config/core.yml"},
                )
            ttl = 900
            try:
                data = await request.json()
                if isinstance(data, dict) and data.get("ttl_seconds") is not None:
                    ttl = int(data["ttl_seconds"])
            except Exception:
                pass
            ttl = max(60, min(ttl, 86400))
            invite_id, token, exp = create_pairing_invite(ttl_seconds=ttl)
            base = _resolve_public_base_url(request, load_instance_identity().get("public_base_url") or "")
            out: Dict[str, Any] = {
                "invite_id": invite_id,
                "token": token,
                "expires_at": exp,
                "consume_http_method": "POST",
                "consume_path": "/api/peer/invite/consume",
            }
            if base:
                out["consume_url"] = f"{base}/api/peer/invite/consume"
            return JSONResponse(content=out)
        except Exception as e:
            logger.warning("peer invite create failed: {}", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    return _handler


def get_api_peer_invite_consume_handler(core: Any):
    async def _handler(request: Request, body: InviteConsumeBody) -> JSONResponse:
        try:
            if not _pairing_enabled():
                return JSONResponse(
                    status_code=404,
                    content={"error": "peer_pairing_disabled", "peer": None},
                )
            ip = _client_ip_for_rate_limit(request)
            if peer_invite_consume_all_attempts_exceeded(ip):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": "too_many_consume_attempts",
                        "peer": None,
                        "retry_after_sec": 60,
                    },
                )
            peer_invite_consume_record_attempt(ip)
            prune_stale_invites()
            ok = verify_and_consume_invite(body.invite_id.strip(), body.invite_token)
            if not ok:
                if peer_invite_consume_record_failed_verify(ip):
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "rate_limited",
                            "detail": "too_many_failed_invite_checks",
                            "peer": None,
                            "retry_after_sec": 60,
                        },
                    )
                return JSONResponse(
                    status_code=403,
                    content={"error": "invalid_or_expired_invite", "peer": None},
                )
            ident = load_instance_identity()
            base_url = _resolve_public_base_url(request, ident.get("public_base_url") or "")
            pairing_uid = (ident.get("pairing_inbound_user_id") or "").strip()
            peer_block = {
                "instance_id": ident.get("instance_id") or "",
                "display_name": ident.get("display_name") or "",
                "base_url": base_url,
                "inbound_user_id": pairing_uid,
            }
            note = (
                "Initiator: save this JSON to a file and run: python -m main peer import <file> [api_key_env_name] "
                "to merge the top-level peer into config/peers.yml. "
                "Set api_key_env (or api_key) to a key accepted by this Core's POST /inbound when auth_enabled. "
                "Ensure inbound_user_id exists in config/user.yml on this Core."
            )
            recipient_import_peer: Optional[Dict[str, Any]] = None
            if (
                (body.instance_id or "").strip()
                and (body.initiator_base_url or "").strip()
                and (body.initiator_inbound_user_id or "").strip()
            ):
                recipient_import_peer = {
                    "peer": {
                        "instance_id": (body.instance_id or "").strip(),
                        "display_name": (body.display_name or "").strip(),
                        "base_url": (body.initiator_base_url or "").strip().rstrip("/"),
                        "inbound_user_id": (body.initiator_inbound_user_id or "").strip(),
                    },
                    "note": (
                        "Recipient (this Core): save only this object as JSON, or the full response; "
                        "run python -m main peer import <file> [api_key_env] to add the initiator to peers.yml here."
                    ),
                }
            content: Dict[str, Any] = {
                "peer": peer_block,
                "initiator": {
                    "instance_id": (body.instance_id or "").strip(),
                    "display_name": (body.display_name or "").strip(),
                    "initiator_base_url": (body.initiator_base_url or "").strip().rstrip("/"),
                    "initiator_inbound_user_id": (body.initiator_inbound_user_id or "").strip(),
                },
                "note": note,
            }
            if recipient_import_peer is not None:
                content["recipient_import_peer"] = recipient_import_peer
            return JSONResponse(content=content)
        except Exception as e:
            logger.warning("peer invite consume failed: {}", e)
            return JSONResponse(status_code=500, content={"error": str(e), "peer": None})

    return _handler
