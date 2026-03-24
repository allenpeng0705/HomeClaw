"""
User-to-user message API (single HomeClaw social network).

POST /api/user-message — send a message to another user (Companion only; Core forwards, no LLM).
GET /api/user-inbox — list messages for the current user.

Auth: same as /inbound (X-API-Key or Bearer when auth_enabled).
Design: docs_design/UserToUserMessagingViaCompanion.md, SocialNetworkDesign.md.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import Depends
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from base.base import Friend, User
from base.federation import format_fid, parse_fid
from base.peer_registry import (
    find_peer_by_instance_id,
    load_instance_identity,
    post_federation_clear_thread_sync,
    post_federation_user_message_sync,
    resolve_peer_api_key,
)
from base.util import Util

from core.federated_friendships_store import list_accepted_for_recipient
from core.federation_e2e import validate_e2e_envelope
from core.routes import auth
from core.routes.federation_api import FederationE2EEnvelopeIn
from core.result_viewer import file_absolute_path_to_view_url, get_core_public_url
from core.user_inbox import (
    append_message as inbox_append,
    clear_thread as inbox_clear_thread,
    get_messages as inbox_get_messages,
    get_thread as inbox_get_thread,
    sanitize_message_dict_for_client,
    sanitize_messages_list_for_client,
)


def _get_user_by_id(user_id: str) -> Optional[User]:
    users = Util().get_users() or []
    uid = (user_id or "").strip()
    for u in users:
        if (getattr(u, "id", None) or "").strip() == uid or (getattr(u, "name", None) or "").strip() == uid:
            return u
    return None


def _friend_match_for_recipient(from_user: User, to_user_id: str) -> Optional[Friend]:
    """Return the user/remote_user friend entry matching to_user_id, or None.

    Checks TinyDB/YAML friends first, then accepted federated rows (SQLite) so UI-only merged
    remote friends (see companion_auth) can send without duplicating entries in users.json.
    """
    friends = getattr(from_user, "friends", None) or []
    to_id = (to_user_id or "").strip()
    for f in friends:
        ftype = (getattr(f, "type", None) or "").strip().lower()
        if ftype not in ("user", "remote_user"):
            continue
        uid = (getattr(f, "user_id", None) or "").strip()
        if uid == to_id:
            return f
    try:
        meta = Util().get_core_metadata()
        if not bool(getattr(meta, "federation_enabled", False)):
            return None
        sender_local = (getattr(from_user, "id", None) or getattr(from_user, "name", None) or "").strip()
        if not sender_local or not to_id:
            return None
        for row in list_accepted_for_recipient(sender_local):
            ff = (row.get("from_fid") or "").strip()
            parsed = parse_fid(ff)
            if not parsed:
                continue
            r_local, r_inst = parsed
            if r_local != to_id:
                continue
            if not r_inst:
                continue
            return Friend(
                name=f"{r_local} · {r_inst}",
                type="remote_user",
                user_id=r_local,
                peer_instance_id=r_inst,
            )
    except Exception as e:
        logger.debug("user-message: federated friend match lookup failed: {}", e)
    return None


def _to_shareable_ref_for_federation(item: str) -> tuple[str, bool]:
    """Normalize one media/file ref for cross-core delivery (no base64 payloads).

    - ``http(s)://`` and ``/files/...`` refs: pass through (peer fetches URL or uses path against sender).
    - ``data:``: not used for federation (returns unshareable).
    - absolute path under ``homeclaw_root``: full file view URL (set ``core_public_url`` so peers reach the sender).
    """
    try:
        s = (item or "").strip()
        if not s:
            return s, True
        lower = s.lower()
        if lower.startswith("data:"):
            return s, False
        if lower.startswith("http://") or lower.startswith("https://"):
            return s, True
        if lower.startswith("/files/") or lower.startswith("/files/out"):
            base = (get_core_public_url() or "").strip().rstrip("/")
            if not base:
                return s, False
            return f"{base}{s}", True
        p = Path(s)
        if not p.is_absolute() or not p.is_file():
            return s, False
        url, err = file_absolute_path_to_view_url(s)
        if url and not err:
            return url, True
        return s, False
    except Exception:
        return item, False


def _normalize_refs_for_federation(items: Optional[list]) -> tuple[Optional[list], bool]:
    if not items or not isinstance(items, list):
        return items, True
    out = []
    ok = True
    for it in items:
        if not isinstance(it, str):
            continue
        ref, shareable = _to_shareable_ref_for_federation(it)
        out.append(ref)
        if not shareable:
            ok = False
    return out, ok


class UserMessageRequest(BaseModel):
    from_user_id: str = Field(..., description="Sender user id (must exist in user.yml)")
    to_user_id: str = Field(..., description="Recipient user id")
    text: str = Field("", description="Message text")
    images: Optional[list] = None  # absolute paths under homeclaw_root or /files/... / http(s) URLs; stored + forwarded
    audios: Optional[list] = None  # same as images (voice clips)
    videos: Optional[list] = None  # same as images
    file_links: Optional[list] = None  # URLs or sandbox paths; stored in inbox for recipient
    e2e: Optional[FederationE2EEnvelopeIn] = None  # P5: hc-e2e-v1 for federated friends only


def get_user_message_post_handler(core):
    """Return handler for POST /api/user-message. Sender must have recipient as user-type friend."""

    async def post_user_message(
        body: UserMessageRequest,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            from_user_id = (body.from_user_id or "").strip()
            to_user_id = (body.to_user_id or "").strip()
            text = (body.text or "").strip()
            if not from_user_id or not to_user_id:
                return JSONResponse(status_code=400, content={"error": "from_user_id and to_user_id required"})
            from_user = _get_user_by_id(from_user_id)
            if not from_user:
                return JSONResponse(status_code=403, content={"error": "from_user_id not found"})
            friend_match = _friend_match_for_recipient(from_user, to_user_id)
            if not friend_match:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "Recipient is not a user-type friend of the sender.",
                        "hint": "Add them in the friends list (users.json / user.yml: type user, user_id) or complete an accepted federated friend link on both instances.",
                    },
                )
            if body.e2e is not None:
                peer_chk = (getattr(friend_match, "peer_instance_id", None) or "").strip()
                if not peer_chk:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "e2e_only_for_federated_friends", "hint": "E2E envelopes are only for friends with peer_instance_id."},
                    )
            peer_inst = (getattr(friend_match, "peer_instance_id", None) or "").strip()
            if peer_inst:
                meta = Util().get_core_metadata()
                if not bool(getattr(meta, "federation_enabled", False)):
                    return JSONResponse(
                        status_code=403,
                        content={"error": "federation_disabled", "hint": "Set federation_enabled: true in config/core.yml to message friends on another instance."},
                    )
                ident = load_instance_identity()
                my_iid = (ident.get("instance_id") or "").strip()
                if not my_iid:
                    return JSONResponse(
                        status_code=503,
                        content={"error": "Local instance_id missing", "hint": "Set instance_id in config/instance_identity.yml for federated messaging."},
                    )
                peer = find_peer_by_instance_id(peer_inst)
                if not peer:
                    return JSONResponse(
                        status_code=502,
                        content={"error": "peer_not_configured", "hint": f"No peers.yml entry for instance_id {peer_inst}."},
                    )
                api_key = resolve_peer_api_key(peer)
                base_url = (peer.get("base_url") or "").strip().rstrip("/")
                if not base_url:
                    return JSONResponse(status_code=502, content={"error": "peer base_url missing"})
                if not api_key:
                    # Normal when both Cores run without inbound auth; only noisy as WARNING.
                    logger.debug(
                        "user-message: peers.yml entry for {} has no api_key / api_key_env / "
                        "use_same_auth_api_key_as_local_core; fine if peer has auth disabled. "
                        "If peer returns 401, set api_key, api_key_env (env var name), or use_same_auth_api_key_as_local_core.",
                        peer_inst,
                    )
                e2e_on = bool(getattr(meta, "federation_e2e_enabled", False))
                e2e_req = bool(getattr(meta, "federation_e2e_require_encrypted", False))
                has_e2e = body.e2e is not None
                if e2e_req and not has_e2e:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "e2e_required", "hint": "This Core requires hc-e2e-v1 for federated user messages."},
                    )
                if has_e2e and not e2e_on:
                    return JSONResponse(status_code=403, content={"error": "federation_e2e_disabled"})
                if has_e2e:
                    ed = body.e2e.model_dump() if body.e2e else {}
                    ok_e, err_e = validate_e2e_envelope(ed)
                    if not ok_e:
                        return JSONResponse(status_code=400, content={"error": "invalid_e2e_envelope", "detail": err_e})
                    if body.images or body.audios or body.videos or body.file_links:
                        return JSONResponse(
                            status_code=400,
                            content={"error": "e2e_media_not_supported"},
                        )
                from_name = (getattr(from_user, "name", None) or from_user_id or "").strip()
                from_fid = format_fid(from_user_id, my_iid)
                if has_e2e:
                    images_payload, images_ok = None, True
                    audios_payload, audios_ok = None, True
                    videos_payload, videos_ok = None, True
                    file_links_payload, file_links_ok = None, True
                else:
                    images_payload, images_ok = _normalize_refs_for_federation(body.images)
                    audios_payload, audios_ok = _normalize_refs_for_federation(body.audios)
                    videos_payload, videos_ok = _normalize_refs_for_federation(body.videos)
                    file_links_payload, file_links_ok = _normalize_refs_for_federation(body.file_links)
                if not (images_ok and audios_ok and videos_ok and file_links_ok):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "federation_media_not_shareable",
                            "hint": "Attachments must resolve to GET /files/... on the sender: use absolute paths under "
                                    "homeclaw_root (Companion uploads go to homeclaw_root/database/uploads/), or full "
                                    "http(s) file URLs. Do not send data: base64. If core_public_url is set on both "
                                    "sides but this still fails, re-upload the file after restarting Core (old uploads "
                                    "may live only under the repo, outside homeclaw_root).",
                        },
                    )
                payload = {
                    "from_fid": from_fid,
                    "to_local_user_id": to_user_id,
                    "text": "" if has_e2e else text,
                    "images": images_payload,
                    "audios": audios_payload,
                    "videos": videos_payload,
                    "file_links": file_links_payload,
                    "from_display_name": from_name,
                }
                if has_e2e and body.e2e:
                    payload["e2e"] = body.e2e.model_dump()
                try:
                    approx_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                    if approx_bytes > 800_000:
                        logger.warning(
                            "user-message: federated POST body ~{} bytes. "
                            "If the peer returns 413/502, raise client_max_body_size on nginx (or similar) between Cores.",
                            approx_bytes,
                        )
                except Exception:
                    pass
                remote = post_federation_user_message_sync(base_url, payload, api_key=api_key)
                sc = int(remote.get("status_code") or 0)
                if remote.get("ok") and sc == 200:
                    mid = remote.get("message_id")
                    # Mirror local same-instance behavior: outbound is stored under the recipient's inbox
                    # file on this Core so GET /api/user-inbox/thread can merge sent + received (see user_inbox.get_thread).
                    try:
                        e2e_local = body.e2e.model_dump() if has_e2e and body.e2e else None
                        meta = {"federated_outbound": True}
                        if mid:
                            meta["remote_message_id"] = mid
                        local_mid = inbox_append(
                            to_user_id=to_user_id,
                            from_user_id=from_user_id,
                            from_user_name=from_name,
                            text="" if has_e2e else text,
                            images=images_payload,
                            audios=audios_payload,
                            videos=videos_payload,
                            file_links=file_links_payload,
                            metadata=meta,
                            e2e=e2e_local,
                        )
                        if not local_mid:
                            logger.warning(
                                "user-message: federated deliver ok but local inbox mirror failed (to={})",
                                to_user_id,
                            )
                    except Exception as e:
                        logger.warning("user-message: federated local inbox mirror failed: {}", e)
                    return JSONResponse(status_code=200, content={"ok": True, "message_id": mid, "federated": True})
                err = (remote.get("error") or "federation_failed") if isinstance(remote, dict) else "federation_failed"
                if sc <= 0:
                    sc = 502
                logger.warning(
                    "user-message: federated POST to {} failed status={} error={} (peer response: {})",
                    base_url,
                    sc,
                    err,
                    remote if isinstance(remote, dict) else str(remote)[:800],
                )
                return JSONResponse(status_code=sc, content={"error": err, "detail": remote if isinstance(remote, dict) else {}})
            to_user = _get_user_by_id(to_user_id)
            if not to_user:
                return JSONResponse(status_code=404, content={"error": "to_user_id not found"})
            if body.e2e is not None:
                return JSONResponse(status_code=400, content={"error": "e2e_only_for_federated_friends"})
            from_name = (getattr(from_user, "name", None) or from_user_id or "").strip()
            msg_id = inbox_append(
                to_user_id=to_user_id,
                from_user_id=from_user_id,
                from_user_name=from_name,
                text=text,
                images=body.images,
                audios=body.audios,
                videos=body.videos,
                file_links=body.file_links,
            )
            if not msg_id:
                return JSONResponse(status_code=500, content={"error": "Failed to store message"})
            try:
                if hasattr(core, "deliver_to_user"):
                    await core.deliver_to_user(
                        to_user_id,
                        text or "(no text)",
                        images=body.images,
                        audios=body.audios,
                        videos=body.videos,
                        source="user_message",
                        from_friend=from_name,
                        from_user_id=from_user_id,
                    )
            except Exception as e:
                logger.debug("user-message: deliver_to_user failed: {}", e)
            return JSONResponse(status_code=200, content={"ok": True, "message_id": msg_id})
        except Exception as e:
            logger.warning("user-message POST failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return post_user_message


def get_user_inbox_handler(core):  # noqa: ARG001
    """Return handler for GET /api/user-inbox."""

    async def get_user_inbox(
        user_id: str = "",
        limit: int = 50,
        after_id: Optional[str] = None,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            user_id = (user_id or "").strip()
            if not user_id:
                return JSONResponse(status_code=400, content={"error": "user_id required"})
            try:
                limit = int(limit) if limit is not None else 50
            except (TypeError, ValueError):
                limit = 50
            limit = max(1, min(100, limit))
            messages = inbox_get_messages(user_id, limit=limit, after_id=after_id)
            out_msgs = []
            for m in messages:
                if isinstance(m, dict):
                    mm = sanitize_message_dict_for_client(dict(m))
                    mm["to_user_id"] = user_id
                    out_msgs.append(mm)
                else:
                    out_msgs.append(m)
            return JSONResponse(status_code=200, content={"user_id": user_id, "messages": out_msgs})
        except Exception as e:
            logger.warning("user-inbox GET failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_user_inbox


def get_user_inbox_thread_handler(core):  # noqa: ARG001
    """Return handler for GET /api/user-inbox/thread. Returns full conversation between user_id and other_user_id (both directions)."""

    async def get_user_inbox_thread(
        user_id: str = "",
        other_user_id: str = "",
        limit: int = 100,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            user_id = (user_id or "").strip()
            other_user_id = (other_user_id or "").strip()
            if not user_id or not other_user_id:
                return JSONResponse(status_code=400, content={"error": "user_id and other_user_id required"})
            try:
                limit = int(limit) if limit is not None else 100
            except (TypeError, ValueError):
                limit = 100
            limit = max(1, min(200, limit))
            messages = inbox_get_thread(user_id, other_user_id, limit=limit)
            messages = sanitize_messages_list_for_client(messages)
            return JSONResponse(status_code=200, content={"user_id": user_id, "other_user_id": other_user_id, "messages": messages})
        except Exception as e:
            logger.warning("user-inbox thread GET failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_user_inbox_thread


def delete_user_inbox_thread_handler(core):  # noqa: ARG001
    """Return handler for DELETE /api/user-inbox/thread. Clears conversation between user_id and other_user_id."""

    async def delete_user_inbox_thread(
        user_id: str = "",
        other_user_id: str = "",
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            user_id = (user_id or "").strip()
            other_user_id = (other_user_id or "").strip()
            if not user_id or not other_user_id:
                return JSONResponse(status_code=400, content={"error": "user_id and other_user_id required"})
            removed = inbox_clear_thread(user_id=user_id, other_user_id=other_user_id)
            out: dict = {
                "ok": True,
                "user_id": user_id,
                "other_user_id": other_user_id,
                "removed": removed,
            }
            # Remote friend: ask peer Core to clear the same thread so both instances stay in sync.
            peer_cleared: Optional[bool] = None
            peer_error: Optional[str] = None
            try:
                from_user = _get_user_by_id(user_id)
                friend_match = _friend_match_for_recipient(from_user, other_user_id) if from_user else None
                peer_inst = (getattr(friend_match, "peer_instance_id", None) or "").strip() if friend_match else ""
                meta = Util().get_core_metadata()
                if peer_inst and bool(getattr(meta, "federation_enabled", False)):
                    peer = find_peer_by_instance_id(peer_inst)
                    if peer:
                        base_url = (peer.get("base_url") or "").strip().rstrip("/")
                        api_key = resolve_peer_api_key(peer)
                        ident = load_instance_identity()
                        my_iid = (ident.get("instance_id") or "").strip()
                        if base_url and my_iid:
                            remote = post_federation_clear_thread_sync(
                                base_url,
                                {
                                    "user_id": user_id,
                                    "other_user_id": other_user_id,
                                    "from_instance_id": my_iid,
                                },
                                api_key=api_key,
                            )
                            sc = int(remote.get("status_code") or 0)
                            if remote.get("ok") and sc == 200:
                                peer_cleared = True
                            else:
                                peer_cleared = False
                                peer_error = str(remote.get("error") or "peer_clear_failed")
                                logger.warning(
                                    "user-inbox DELETE: peer clear-thread failed status={} remote={}",
                                    sc,
                                    remote,
                                )
            except Exception as e:
                peer_cleared = False
                peer_error = str(e)
                logger.warning("user-inbox DELETE: peer clear-thread exception: {}", e)
            if peer_cleared is not None:
                out["peer_cleared"] = peer_cleared
            if peer_error:
                out["peer_error"] = peer_error
            return JSONResponse(status_code=200, content=out)
        except Exception as e:
            logger.warning("user-inbox thread DELETE failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return delete_user_inbox_thread
