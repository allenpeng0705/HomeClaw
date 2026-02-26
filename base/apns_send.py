"""
Optional APNs (Apple Push Notification service) send for Companion on iOS/macOS/tvOS.
Requires: pip install pyjwt cryptography httpx (httpx with http2 extra).
Config: core.yml push_notifications.ios (or apns): key_path (.p8), key_id, team_id, bundle_id, sandbox (bool).
Used for Apple devices; FCM is used for Android and other platforms.
"""
import time
from pathlib import Path
from typing import Optional

from loguru import logger

_apns_jwt_cache: Optional[str] = None
_apns_jwt_exp: float = 0


def _get_apns_config() -> Optional[dict]:
    """Read APNs config from core.yml push_notifications.ios (or .apns)."""
    try:
        from base.util import Util
        config_path = Path(Util().config_path()) / "core.yml"
        if not config_path.is_file():
            return None
        data = Util().load_yml_config(str(config_path)) or {}
        push_cfg = data.get("push_notifications") if isinstance(data.get("push_notifications"), dict) else None
        if not push_cfg or not push_cfg.get("enabled"):
            return None
        ios_cfg = push_cfg.get("ios") or push_cfg.get("apns")
        if not isinstance(ios_cfg, dict):
            return None
        key_path = (ios_cfg.get("key_path") or "").strip()
        key_id = (ios_cfg.get("key_id") or "").strip()
        team_id = (ios_cfg.get("team_id") or "").strip()
        bundle_id = (ios_cfg.get("bundle_id") or "").strip()
        if not key_path or not key_id or not team_id or not bundle_id:
            return None
        root = Path(Util().root_path())
        p = (root / key_path).resolve() if not Path(key_path).is_absolute() else Path(key_path)
        if not p.is_file():
            return None
        return {
            "key_path": str(p),
            "key_id": key_id,
            "team_id": team_id,
            "bundle_id": bundle_id,
            "sandbox": bool(ios_cfg.get("sandbox", True)),
        }
    except Exception as e:
        logger.debug("apns_send: config resolve failed: {}", e)
    return None


def _make_apns_jwt(config: dict) -> Optional[str]:
    """Build JWT for APNs (ES256, kid, iss=team_id, iat). Cached for ~50 min."""
    global _apns_jwt_cache, _apns_jwt_exp
    now = time.time()
    if _apns_jwt_cache and now < _apns_jwt_exp:
        return _apns_jwt_cache
    try:
        import jwt
        with open(config["key_path"], "rb") as f:
            key_bytes = f.read()
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            key_content = load_pem_private_key(key_bytes, password=None)
        except Exception:
            key_content = key_bytes.decode("utf-8")
        payload = {"iss": config["team_id"], "iat": int(now)}
        token = jwt.encode(
            payload,
            key_content,
            algorithm="ES256",
            headers={"alg": "ES256", "kid": config["key_id"]},
        )
        if hasattr(token, "decode"):
            token = token.decode("utf-8")
        _apns_jwt_cache = token
        _apns_jwt_exp = now + 3000  # ~50 min
        return _apns_jwt_cache
    except Exception as e:
        logger.debug("apns_send: JWT build failed: {}", e)
    return None


def send_apns_one(
    token: str,
    title: str,
    body: str,
    user_id: Optional[str] = None,
    source: Optional[str] = None,
) -> bool:
    """
    Send one APNs notification to one device token.
    Custom keys user_id and source are included so the app can show which user the push is for (multi-user on one device).
    Returns True if sent successfully. Never raises.
    """
    try:
        token = (token or "").strip() if isinstance(token, str) else ""
        if not token:
            return False
        config = _get_apns_config()
        if not config or not isinstance(config, dict):
            return False
        jwt_token = _make_apns_jwt(config)
        if not jwt_token:
            return False
        base_url = "https://api.sandbox.push.apple.com" if config.get("sandbox", True) else "https://api.push.apple.com"
        url = f"{base_url}/3/device/{token}"
        title_s = str(title or "HomeClaw")[:50]
        body_s = str(body or "")[:1024]
        payload = {
            "aps": {
                "alert": {"title": title_s, "body": body_s},
                "sound": "default",
            },
        }
        if user_id is not None and str(user_id).strip():
            payload["user_id"] = str(user_id).strip()[:256]
        if source is not None and str(source).strip():
            payload["source"] = str(source).strip()[:64]
        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": str(config.get("bundle_id", "")),
            "apns-push-type": "alert",
            "apns-priority": "10",
            "content-type": "application/json",
        }
        import httpx
        with httpx.Client(http2=True) as client:
            resp = client.post(url, json=payload, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            return True
        resp_text = getattr(resp, "text", None) or ""
        logger.debug("APNs send to ...{} failed: {} {}", token[-8:] if len(token) > 8 else token, resp.status_code, resp_text[:200])
        if resp.status_code in (400, 410, 404):  # bad token / unregistered
            return False
    except Exception as e:
        logger.debug("APNs send failed: {}", e)
    return False
