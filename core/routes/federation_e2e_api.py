"""
Federated E2E public keys (P5): register on own Core; fetch remote user key via peer GET.

Companion: PUT /api/me/federation-e2e-key, GET /api/me/federation-peer-e2e-public-key
Core–Core: GET /api/federation/e2e-public-key?local_user_id=
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

from fastapi import Depends
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from base.peer_registry import find_peer_by_instance_id, get_federation_json_sync, resolve_peer_api_key
from base.util import Util

from core.federation_e2e_store import get_public_key_b64, upsert_public_key
from core.routes import auth, companion_auth


class FederationE2eKeyBody(BaseModel):
    public_key_b64: str = Field(..., description="32-byte X25519 public key, standard base64")


def _validate_x25519_public_b64(s: str) -> bool:
    try:
        raw = base64.b64decode((s or "").strip(), validate=True)
        return len(raw) == 32
    except Exception:
        return False


def get_api_me_federation_e2e_key_put_handler(core):  # noqa: ARG001
    """PUT /api/me/federation-e2e-key — register X25519 public key (Bearer)."""

    async def put_key(
        body: FederationE2eKeyBody,
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            meta = Util().get_core_metadata()
            if not bool(getattr(meta, "federation_e2e_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_e2e_disabled"})
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            pk = (body.public_key_b64 or "").strip()
            if not user_id or not _validate_x25519_public_b64(pk):
                return JSONResponse(status_code=400, content={"error": "invalid_public_key_b64"})
            if not upsert_public_key(user_id, pk):
                return JSONResponse(status_code=500, content={"error": "failed_to_save"})
            return JSONResponse(content={"ok": True})
        except Exception as e:
            logger.warning("PUT federation-e2e-key failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return put_key


def get_api_me_federation_e2e_key_status_handler(core):  # noqa: ARG001
    """GET /api/me/federation-e2e-key-status — whether this user has registered a key."""

    async def get_status(
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            pk = get_public_key_b64(user_id)
            return JSONResponse(content={"registered": bool(pk), "federation_e2e_enabled": bool(getattr(Util().get_core_metadata(), "federation_e2e_enabled", False))})
        except Exception as e:
            logger.debug("GET federation-e2e-key-status failed: {}", e)
            return JSONResponse(content={"registered": False, "federation_e2e_enabled": False})

    return get_status


def get_api_me_federation_peer_e2e_public_key_handler(core):  # noqa: ARG001
    """GET /api/me/federation-peer-e2e-public-key?peer_instance_id=&remote_user_id= — proxy to peer Core."""

    async def get_peer_key(
        peer_instance_id: str = "",
        remote_user_id: str = "",
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            meta = Util().get_core_metadata()
            if not bool(getattr(meta, "federation_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_disabled"})
            if not bool(getattr(meta, "federation_e2e_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_e2e_disabled"})
            pid = (peer_instance_id or "").strip()
            ruid = (remote_user_id or "").strip()
            if not pid or not ruid:
                return JSONResponse(status_code=400, content={"error": "peer_instance_id and remote_user_id required"})
            peer = find_peer_by_instance_id(pid)
            if not peer:
                return JSONResponse(status_code=404, content={"error": "peer_not_configured"})
            base_url = (peer.get("base_url") or "").strip().rstrip("/")
            api_key = resolve_peer_api_key(peer)
            path = f"/api/federation/e2e-public-key?local_user_id={quote(ruid, safe='')}"
            remote = get_federation_json_sync(base_url, path, api_key=api_key)
            if remote.get("ok") and int(remote.get("status_code") or 0) == 200:
                return JSONResponse(
                    content={
                        "public_key_b64": remote.get("public_key_b64"),
                        "algorithm": remote.get("algorithm") or "x25519",
                    }
                )
            if int(remote.get("status_code") or 0) == 404:
                return JSONResponse(status_code=404, content={"error": "remote_key_not_registered"})
            return JSONResponse(
                status_code=int(remote.get("status_code") or 502),
                content={"error": remote.get("error") or "lookup_failed"},
            )
        except Exception as e:
            logger.warning("GET federation-peer-e2e-public-key failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_peer_key


def get_federation_e2e_public_key_get_handler(core):  # noqa: ARG001
    """GET /api/federation/e2e-public-key?local_user_id= — inbound for peer lookup."""

    async def get_inbound(
        local_user_id: str = "",
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            meta = Util().get_core_metadata()
            if not bool(getattr(meta, "federation_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_disabled"})
            if not bool(getattr(meta, "federation_e2e_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_e2e_disabled"})
            uid = (local_user_id or "").strip()
            if not uid:
                return JSONResponse(status_code=400, content={"error": "local_user_id required"})
            pk = get_public_key_b64(uid)
            if not pk:
                return JSONResponse(status_code=404, content={"error": "no_key"})
            return JSONResponse(content={"ok": True, "public_key_b64": pk, "algorithm": "x25519"})
        except Exception as e:
            logger.warning("GET federation e2e-public-key failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_inbound
