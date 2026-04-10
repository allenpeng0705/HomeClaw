"""
Claw-Code P5: /clawcode and !clawcode commands + HTTP helpers for Core channel-bindings API.

Use across all channels that POST /inbound or /process: merge binding into payload / PromptRequest.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx

from base.util import Util


def parse_clawcode_command(text: str) -> Optional[Tuple[str, List[str]]]:
    """
    If the message is a Claw-Code channel control line, return (subcommand, args).
    Subcommands: help, status, bind, clear.
    Supports Telegram /clawcode@BotName and Discord !clawcode.
    """
    t = (text or "").strip()
    if not t:
        return None
    parts = t.split()
    head = parts[0]
    rest = parts[1:]
    if head.startswith("/"):
        base = head.split("@", 1)[0].lower()
        if base != "/clawcode":
            return None
    elif head.lower() == "!clawcode":
        pass
    else:
        return None
    if not rest:
        return ("help", [])
    sub = rest[0].lower()
    args = rest[1:]
    if sub in ("help", "status", "clear", "bind"):
        return (sub, args)
    return ("help", [])


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID((s or "").strip())
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _bindings_url() -> str:
    return f"{Util().get_channels_core_url().rstrip('/')}/api/clawcode/channel-bindings"


def _core_headers_json() -> Dict[str, str]:
    return {**Util().get_channels_core_api_headers(), "Content-Type": "application/json"}


def fetch_binding_for_owner_sync(owner_user_id: str) -> Optional[str]:
    """GET binding (sync). On error or non-200, return None."""
    uid = (owner_user_id or "").strip()
    if not uid:
        return None
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            r = client.get(_bindings_url(), params={"owner_user_id": uid}, headers=Util().get_channels_core_api_headers())
        if r.status_code != 200:
            return None
        data = r.json() if r.content else {}
        sid = (data.get("clawcode_session_id") or "").strip()
        return sid or None
    except Exception:
        return None


def put_binding_sync(owner_user_id: str, session_id: str) -> Tuple[bool, str]:
    uid = (owner_user_id or "").strip()
    sid = (session_id or "").strip()
    if not _is_uuid(sid):
        return False, "Invalid session id (expected UUID)."
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            r = client.put(
                _bindings_url(),
                json={"owner_user_id": uid, "clawcode_session_id": sid},
                headers=_core_headers_json(),
            )
        if r.status_code == 200:
            return True, "Bound this channel identity to Claw-Code session. Further messages use that session."
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text or "request failed"
        return False, str(err)[:2000]
    except httpx.ConnectError:
        return False, "Core unreachable."
    except Exception as e:
        return False, str(e)[:2000]


def delete_binding_sync(owner_user_id: str) -> Tuple[bool, str]:
    uid = (owner_user_id or "").strip()
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            r = client.delete(_bindings_url(), params={"owner_user_id": uid}, headers=Util().get_channels_core_api_headers())
        if r.status_code == 200:
            return True, "Claw-Code binding cleared. Messages use normal chat until you bind again."
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text or "request failed"
        return False, str(err)[:2000]
    except httpx.ConnectError:
        return False, "Core unreachable."
    except Exception as e:
        return False, str(e)[:2000]


def get_status_message_sync(owner_user_id: str) -> str:
    sid = fetch_binding_for_owner_sync(owner_user_id)
    if sid:
        return f"Claw-Code: bound to session {sid}."
    return "Claw-Code: no binding for this channel identity. Use /clawcode bind <session_uuid> (create a session with the CLI first)."


_HELP = (
    "Claw-Code (any channel):\n"
    "/clawcode status — show binding\n"
    "/clawcode bind <uuid> — session from `clawcode session new` "
    "(session owner must match this channel's Core user_id, or your user.yml id when using API bindings)\n"
    "/clawcode clear — remove binding\n"
    "Discord: !clawcode … (same subcommands)\n"
    "Tip: PUT /api/clawcode/channel-bindings with owner_user_id = your Core user id (e.g. from user.yml) "
    "so Telegram/Discord messages use that session after permission resolution.\n"
)


def handle_clawcode_command_sync(owner_user_id: str, subcommand: str, args: List[str]) -> str:
    """Build reply text for a parsed clawcode command (sync HTTP to Core)."""
    if subcommand == "help":
        return _HELP
    if subcommand == "status":
        return get_status_message_sync(owner_user_id)
    if subcommand == "clear":
        _ok, msg = delete_binding_sync(owner_user_id)
        return msg
    if subcommand == "bind":
        if not args:
            return "Usage: /clawcode bind <session_uuid>"
        _ok, msg = put_binding_sync(owner_user_id, args[0])
        return msg
    return _HELP


def try_clawcode_command_reply(owner_user_id: str, text: str) -> Optional[str]:
    """
    If *text* is a /clawcode or !clawcode command, return the reply to send to the user.
    Otherwise return None (caller should forward to Core as usual).
    """
    parsed = parse_clawcode_command(text)
    if not parsed:
        return None
    sub, args = parsed
    return handle_clawcode_command_sync(owner_user_id, sub, args)


def merge_clawcode_binding_into_inbound_payload(payload: Dict[str, Any], owner_user_id: str) -> None:
    """Mutate inbound JSON payload: set clawcode_session_id when a binding exists."""
    uid = (owner_user_id or "").strip()
    if not uid:
        return
    sid = fetch_binding_for_owner_sync(uid)
    if sid:
        payload["clawcode_session_id"] = sid


def merge_clawcode_binding_into_prompt_request(request: Any) -> None:
    """Mutate PromptRequest.request_metadata with clawcode_session_id when bound."""
    uid = (getattr(request, "user_id", None) or "").strip()
    if not uid:
        return
    sid = fetch_binding_for_owner_sync(uid)
    if sid:
        md = dict(getattr(request, "request_metadata", None) or {})
        md["clawcode_session_id"] = sid
        request.request_metadata = md


def apply_clawcode_inbound_flow(owner_user_id: str, text: str, payload: Dict[str, Any]) -> Optional[str]:
    """
    Handle clawcode commands; else merge binding into *payload*.
    Returns reply text if the message is fully handled (skip POST /inbound), else None.
    """
    cmd_reply = try_clawcode_command_reply(owner_user_id, text)
    if cmd_reply is not None:
        return cmd_reply
    merge_clawcode_binding_into_inbound_payload(payload, owner_user_id)
    return None


async def fetch_binding_for_owner(owner_user_id: str) -> Optional[str]:
    """Async wrapper (uses sync HTTP)."""
    return fetch_binding_for_owner_sync(owner_user_id)


async def put_binding(owner_user_id: str, session_id: str) -> Tuple[bool, str]:
    return put_binding_sync(owner_user_id, session_id)


async def delete_binding(owner_user_id: str) -> Tuple[bool, str]:
    return delete_binding_sync(owner_user_id)


async def get_status_message(owner_user_id: str) -> str:
    return get_status_message_sync(owner_user_id)


async def handle_clawcode_command(
    owner_user_id: str,
    subcommand: str,
    args: List[str],
    reply,
) -> None:
    msg = handle_clawcode_command_sync(owner_user_id, subcommand, args)
    await reply(msg)
