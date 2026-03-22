"""
Multi-instance coordination: instance_identity.yml, peers.yml, HTTP peer_call helper, pairing invite store.

See docs_design/MultiInstanceIdentityRosterAndPairing.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import yaml
from loguru import logger

INSTANCE_IDENTITY_FILENAME = "instance_identity.yml"
PEERS_FILENAME = "peers.yml"


def config_dir() -> str:
    from base.util import Util

    return Util().config_path()


def root_dir() -> str:
    from base.util import Util

    return Util().root_path()


def load_yaml_optional(path: str) -> Dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("peer_registry: failed to load {}: {}", path, e)
        return {}


def load_instance_identity(config_dir_path: Optional[str] = None) -> Dict[str, Any]:
    cfgd = config_dir_path or config_dir()
    path = os.path.join(cfgd, INSTANCE_IDENTITY_FILENAME)
    raw = load_yaml_optional(path)
    caps_raw = raw.get("capabilities")
    if isinstance(caps_raw, str):
        caps = [caps_raw.strip()] if caps_raw.strip() else []
    elif isinstance(caps_raw, list):
        caps = [str(c).strip() for c in caps_raw if c is not None and str(c).strip()]
    else:
        caps = []
    return {
        "instance_id": str(raw.get("instance_id") or "").strip(),
        "display_name": str(raw.get("display_name") or "").strip(),
        "capabilities": caps,
        "public_base_url": str(raw.get("public_base_url") or "").strip().rstrip("/"),
        "version_hint": str(raw.get("version_hint") or "").strip(),
        "pairing_inbound_user_id": str(raw.get("pairing_inbound_user_id") or "").strip(),
    }


def load_peers_list(config_dir_path: Optional[str] = None) -> List[Dict[str, Any]]:
    cfgd = config_dir_path or config_dir()
    path = os.path.join(cfgd, PEERS_FILENAME)
    raw = load_yaml_optional(path)
    peers = raw.get("peers")
    if peers is None:
        return []
    if isinstance(peers, dict):
        peers = list(peers.values())
    if not isinstance(peers, list):
        return []
    out: List[Dict[str, Any]] = []
    for p in peers:
        if not isinstance(p, dict):
            continue
        iid = str(p.get("instance_id") or "").strip()
        bu = str(p.get("base_url") or "").strip().rstrip("/")
        if not iid or not bu:
            continue
        uid = str(p.get("inbound_user_id") or p.get("user_id") or "").strip()
        out.append(
            {
                "instance_id": iid,
                "display_name": str(p.get("display_name") or "").strip(),
                "base_url": bu,
                "inbound_user_id": uid,
                "api_key_env": str(p.get("api_key_env") or "").strip(),
                "api_key": str(p.get("api_key") or "").strip(),
                "capabilities": _norm_cap_list(p.get("capabilities")),
            }
        )
    return out


def _norm_cap_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, str):
        s = val.strip()
        return [s] if s else []
    if isinstance(val, list):
        return [str(c).strip() for c in val if c is not None and str(c).strip()]
    return []


def resolve_peer_api_key(peer_row: Dict[str, Any]) -> Optional[str]:
    k = (peer_row.get("api_key") or "").strip()
    if k:
        return k
    env_name = (peer_row.get("api_key_env") or "").strip()
    if env_name:
        v = os.environ.get(env_name)
        if v and str(v).strip():
            return str(v).strip()
    return None


def find_peer_by_instance_id(instance_id: str, config_dir_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    needle = (instance_id or "").strip()
    if not needle:
        return None
    for p in load_peers_list(config_dir_path):
        if p.get("instance_id") == needle:
            return p
    return None


def peer_dict_from_import_payload(data: Any) -> Optional[Dict[str, Any]]:
    """
    Extract a peer row for merge_peer_entry / peer import:
    - Full invite-consume JSON: top-level peer (initiator adds recipient).
    - Wrapped symmetric block: recipient_import_peer.peer (recipient adds initiator).
    - Flat dict with instance_id + base_url + inbound_user_id.
    """
    if not isinstance(data, dict):
        return None
    main_peer = data.get("peer")
    if isinstance(main_peer, dict):
        iid = str(main_peer.get("instance_id") or "").strip()
        bu = str(main_peer.get("base_url") or "").strip()
        if iid and bu:
            return dict(main_peer)
    rip = data.get("recipient_import_peer")
    if isinstance(rip, dict) and isinstance(rip.get("peer"), dict):
        p = rip["peer"]
        if str(p.get("instance_id") or "").strip() and str(p.get("base_url") or "").strip():
            return dict(p)
    if (data.get("instance_id") or "").strip() and (data.get("base_url") or "").strip():
        return dict(data)
    return None


def merge_peer_entry(peer_in: Dict[str, Any], config_dir_path: Optional[str] = None) -> Tuple[bool, str]:
    """
    Merge one peer into config/peers.yml. Replaces an existing row with the same instance_id.
    Preserves other top-level keys in peers.yml when present. Atomic replace via .tmp file.
    """
    iid = str(peer_in.get("instance_id") or "").strip()
    bu = str(peer_in.get("base_url") or "").strip().rstrip("/")
    uid = str(peer_in.get("inbound_user_id") or peer_in.get("user_id") or "").strip()
    if not iid or not bu or not uid:
        return False, "peer needs instance_id, base_url, and inbound_user_id"
    cfgd = config_dir_path or config_dir()
    path = os.path.join(cfgd, PEERS_FILENAME)
    raw = load_yaml_optional(path)
    if not raw:
        raw = {}
    peers = raw.get("peers")
    if peers is None:
        rows: List[Any] = []
    elif isinstance(peers, dict):
        rows = list(peers.values())
    elif isinstance(peers, list):
        rows = list(peers)
    else:
        rows = []
    kept: List[Dict[str, Any]] = []
    for p in rows:
        if isinstance(p, dict) and str(p.get("instance_id") or "").strip() != iid:
            kept.append(p)
    new_row: Dict[str, Any] = {
        "instance_id": iid,
        "base_url": bu,
        "inbound_user_id": uid,
    }
    dn = str(peer_in.get("display_name") or "").strip()
    if dn:
        new_row["display_name"] = dn
    ake = str(peer_in.get("api_key_env") or "").strip()
    if ake:
        new_row["api_key_env"] = ake
    ak = str(peer_in.get("api_key") or "").strip()
    if ak:
        new_row["api_key"] = ak
    caps = _norm_cap_list(peer_in.get("capabilities"))
    if caps:
        new_row["capabilities"] = caps
    kept.append(new_row)
    raw["peers"] = kept
    try:
        os.makedirs(cfgd, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)
        return True, "merged peer '{}' into {}".format(iid, path)
    except Exception as e:
        logger.warning("merge_peer_entry failed: {}", e)
        return False, str(e)


# Dual rate limits for POST /api/peer/invite/consume (per client IP).
_consume_rate_lock = threading.Lock()
_consume_all_by_ip: Dict[str, List[float]] = {}
_consume_fail_by_ip: Dict[str, List[float]] = {}
CONSUME_ALL_WINDOW_SEC = 60.0
CONSUME_ALL_MAX_PER_WINDOW = 45
CONSUME_FAIL_WINDOW_SEC = 60.0
CONSUME_FAIL_MAX_PER_WINDOW = 18


def reset_peer_invite_rate_limits_for_testing() -> None:
    """Clear in-memory rate limit state (for unit tests only)."""
    with _consume_rate_lock:
        _consume_all_by_ip.clear()
        _consume_fail_by_ip.clear()


def _norm_rate_ip(client_ip: str) -> str:
    return (client_ip or "unknown").strip() or "unknown"


def peer_invite_consume_all_attempts_exceeded(client_ip: str) -> bool:
    """True before processing: too many consume POSTs in the rolling window."""
    ip = _norm_rate_ip(client_ip)
    now = time.time()
    with _consume_rate_lock:
        lst = [t for t in _consume_all_by_ip.get(ip, []) if now - t < CONSUME_ALL_WINDOW_SEC]
        _consume_all_by_ip[ip] = lst
        return len(lst) >= CONSUME_ALL_MAX_PER_WINDOW


def peer_invite_consume_record_attempt(client_ip: str) -> None:
    """Call after all_attempts_exceeded is False."""
    ip = _norm_rate_ip(client_ip)
    now = time.time()
    with _consume_rate_lock:
        lst = [t for t in _consume_all_by_ip.get(ip, []) if now - t < CONSUME_ALL_WINDOW_SEC]
        lst.append(now)
        _consume_all_by_ip[ip] = lst


def peer_invite_consume_record_failed_verify(client_ip: str) -> bool:
    """
    Record invalid/expired invite for this IP.
    Returns True if failure count is now over limit (caller should return 429 instead of 403).
    """
    ip = _norm_rate_ip(client_ip)
    now = time.time()
    with _consume_rate_lock:
        lst = [t for t in _consume_fail_by_ip.get(ip, []) if now - t < CONSUME_FAIL_WINDOW_SEC]
        lst.append(now)
        _consume_fail_by_ip[ip] = lst
        return len(lst) > CONSUME_FAIL_MAX_PER_WINDOW


def format_peer_roster_for_tool_prompt(max_chars: int = 5000) -> str:
    try:
        lines = ["## Configured peer HomeClaw instances (config/peers.yml)", ""]
        peers = load_peers_list()
        if not peers:
            lines.append("(No peers configured. Add entries to config/peers.yml to call another Core via peer_call.)")
        else:
            for p in peers:
                caps = p.get("capabilities") or []
                cap_s = ",".join(caps) if caps else "-"
                uid = p.get("inbound_user_id") or "(missing — set inbound_user_id)"
                dn = p.get("display_name") or "-"
                lines.append(
                    f"- instance_id={p.get('instance_id')}  base_url={p.get('base_url')}  "
                    f"inbound_user_id={uid}  capabilities={cap_s}  display_name={dn}"
                )
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[: max_chars - 24] + "\n…(truncated)"
        return text
    except Exception as e:
        logger.debug("format_peer_roster_for_tool_prompt: {}", e)
        return ""


def post_inbound_sync(
    base_url: str,
    user_id: str,
    text: str,
    api_key: Optional[str] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """POST /inbound on another Core. Returns parsed JSON dict plus ok/status_code when possible. Never raises."""
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/inbound"
    payload = json.dumps(
        {"user_id": user_id, "text": text, "channel_name": "peer"},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        try:
            data = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            data = {"error": body[:2000] or str(e.reason), "text": ""}
        if isinstance(data, dict):
            data["ok"] = False
            data["status_code"] = e.code
            return data
        return {"ok": False, "error": str(e), "text": "", "status_code": e.code}
    except Exception as e:
        return {"ok": False, "error": str(e), "text": ""}

    try:
        data = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        return {"ok": False, "error": "non_json_response", "text": "", "raw": body[:2000], "status_code": code}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_response", "text": "", "status_code": code}
    data["status_code"] = code
    err = data.get("error")
    data["ok"] = code == 200 and not (err and str(err).strip())
    return data


def post_federation_json_sync(
    base_url: str,
    path: str,
    body: Dict[str, Any],
    api_key: Optional[str] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """POST JSON to base_url + path (path must start with /). Returns parsed JSON plus ok/status_code when possible. Never raises."""
    import urllib.error
    import urllib.request

    p = (path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    url = base_url.rstrip("/") + p
    payload = json.dumps(body if isinstance(body, dict) else {}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body_text = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        try:
            data = json.loads(body_text) if body_text.strip() else {}
        except json.JSONDecodeError:
            data = {"error": body_text[:2000] or str(e.reason), "text": ""}
        if isinstance(data, dict):
            data["ok"] = False
            data["status_code"] = e.code
            return data
        return {"ok": False, "error": str(e), "text": "", "status_code": e.code}
    except Exception as e:
        return {"ok": False, "error": str(e), "text": ""}

    try:
        data = json.loads(body_text) if body_text.strip() else {}
    except json.JSONDecodeError:
        return {"ok": False, "error": "non_json_response", "text": "", "raw": body_text[:2000], "status_code": code}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_response", "text": "", "status_code": code}
    data["status_code"] = code
    err = data.get("error")
    data["ok"] = code == 200 and bool(data.get("ok", True)) and not (err and str(err).strip())
    return data


def get_federation_json_sync(
    base_url: str,
    path: str,
    api_key: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """GET base_url + path (path must start with /; may include ?query). Returns parsed JSON plus ok/status_code. Never raises."""
    import urllib.error
    import urllib.request

    p = (path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    url = base_url.rstrip("/") + p
    req = urllib.request.Request(url, method="GET")
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body_text = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        try:
            data = json.loads(body_text) if body_text.strip() else {}
        except json.JSONDecodeError:
            data = {"error": body_text[:2000] or str(e.reason), "text": ""}
        if isinstance(data, dict):
            data["ok"] = False
            data["status_code"] = e.code
            return data
        return {"ok": False, "error": str(e), "text": "", "status_code": e.code}
    except Exception as e:
        return {"ok": False, "error": str(e), "text": ""}

    try:
        data = json.loads(body_text) if body_text.strip() else {}
    except json.JSONDecodeError:
        return {"ok": False, "error": "non_json_response", "text": "", "raw": body_text[:2000], "status_code": code}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_response", "text": "", "status_code": code}
    data["status_code"] = code
    err = data.get("error")
    data["ok"] = code == 200 and bool(data.get("ok", True)) and not (err and str(err).strip())
    return data


def post_federation_user_message_sync(
    base_url: str,
    body: Dict[str, Any],
    api_key: Optional[str] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """POST /api/federation/user-message on another Core."""
    return post_federation_json_sync(base_url, "/api/federation/user-message", body, api_key=api_key, timeout=timeout)


# --- Pairing invite store (persisted under database/peer_invites.json) ---

_invite_lock = threading.Lock()
_invite_by_id: Dict[str, Dict[str, Any]] = {}
_invites_loaded = False


def _invites_file_path() -> str:
    return os.path.join(root_dir(), "database", "peer_invites.json")


def _load_invites_from_disk() -> None:
    global _invite_by_id, _invites_loaded
    if _invites_loaded:
        return
    path = _invites_file_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            inv = data.get("invites") if isinstance(data, dict) else None
            if isinstance(inv, dict):
                with _invite_lock:
                    for k, v in inv.items():
                        if isinstance(k, str) and isinstance(v, dict):
                            _invite_by_id[k] = v
        except Exception as e:
            logger.warning("peer invites load failed: {}", e)
    _invites_loaded = True


def _save_invites_to_disk() -> None:
    path = _invites_file_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _invite_lock:
            snap = dict(_invite_by_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"invites": snap}, f, indent=2)
    except Exception as e:
        logger.warning("peer invites save failed: {}", e)


def prune_stale_invites() -> None:
    """Drop expired unused invites and old consumed rows. Best-effort."""
    _load_invites_from_disk()
    now = int(time.time())
    to_del: List[str] = []
    with _invite_lock:
        for k, v in _invite_by_id.items():
            exp = int(v.get("expires_at") or 0)
            consumed = v.get("consumed_at")
            if consumed:
                if now - int(consumed) > 86400 * 7:
                    to_del.append(k)
            elif now > exp:
                to_del.append(k)
        for k in to_del:
            _invite_by_id.pop(k, None)
    if to_del:
        _save_invites_to_disk()


def create_pairing_invite(ttl_seconds: int = 900) -> Tuple[str, str, int]:
    """Returns (invite_id, plain_token, expires_at_unix)."""
    _load_invites_from_disk()
    prune_stale_invites()
    invite_id = secrets.token_urlsafe(12)
    plain = secrets.token_urlsafe(32)
    th = hashlib.sha256(plain.encode("utf-8")).hexdigest()
    now = int(time.time())
    ttl = int(ttl_seconds) if ttl_seconds else 900
    ttl = max(60, min(ttl, 86400))
    exp = now + ttl
    row = {"token_hash": th, "created_at": now, "expires_at": exp, "consumed_at": None}
    with _invite_lock:
        _invite_by_id[invite_id] = row
    _save_invites_to_disk()
    return invite_id, plain, exp


def verify_and_consume_invite(invite_id: str, plain_token: str) -> bool:
    """Validate token and mark invite consumed. Returns False on any failure."""
    _load_invites_from_disk()
    invite_id = (invite_id or "").strip()
    if not invite_id or not plain_token:
        return False
    th = hashlib.sha256(plain_token.encode("utf-8")).hexdigest()
    now = int(time.time())
    with _invite_lock:
        row = _invite_by_id.get(invite_id)
        if not row or row.get("consumed_at"):
            return False
        if now > int(row.get("expires_at") or 0):
            return False
        if row.get("token_hash") != th:
            return False
        row = dict(row)
        row["consumed_at"] = now
        _invite_by_id[invite_id] = row
    _save_invites_to_disk()
    return True


def peek_invite_valid(invite_id: str) -> bool:
    """True if invite exists, not consumed, not expired (does not consume)."""
    _load_invites_from_disk()
    invite_id = (invite_id or "").strip()
    now = int(time.time())
    with _invite_lock:
        row = _invite_by_id.get(invite_id)
        if not row or row.get("consumed_at"):
            return False
        return now <= int(row.get("expires_at") or 0)
