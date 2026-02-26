"""
Optional FCM (Firebase Cloud Messaging) send for Companion push when app is killed/background.
Requires: pip install firebase-admin and a service account JSON key.
Config: core.yml push_notifications.enabled: true, push_notifications.credentials_path: path/to/serviceAccountKey.json
Or env: GOOGLE_APPLICATION_CREDENTIALS=/path/to/serviceAccountKey.json
"""
from pathlib import Path
from typing import Optional

from loguru import logger

_fcm_initialized = False


def _get_credentials_path() -> Optional[Path]:
    """Resolve Firebase credentials path from config or env."""
    try:
        from base.util import Util
        config_path = Path(Util().config_path()) / "core.yml"
        if config_path.is_file():
            data = Util().load_yml_config(str(config_path)) or {}
            push_cfg = data.get("push_notifications") if isinstance(data.get("push_notifications"), dict) else None
            if push_cfg and push_cfg.get("enabled"):
                path = (push_cfg.get("fcm") or {}).get("credentials_path") if isinstance(push_cfg.get("fcm"), dict) else None
                if not path:
                    path = push_cfg.get("credentials_path") or ""  # legacy top-level
                if path:
                    root = Path(Util().root_path())
                    p = (root / path).resolve() if not Path(path).is_absolute() else Path(path)
                    if p.is_file():
                        return p
        import os
        env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if env_path and Path(env_path).is_file():
            return Path(env_path)
    except Exception as e:
        logger.debug("fcm_send: credentials path resolve failed: {}", e)
    return None


def _ensure_fcm_initialized() -> bool:
    """Initialize Firebase Admin SDK once. Returns True if FCM is available and initialized."""
    global _fcm_initialized
    if _fcm_initialized:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.debug("firebase_admin not installed; push notifications disabled")
        _fcm_initialized = True  # avoid retry
        return False
    cred_path = _get_credentials_path()
    if not cred_path:
        logger.debug("FCM credentials path not set; push notifications disabled")
        _fcm_initialized = True
        return False
    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            firebase_admin.initialize_app(credentials.Certificate(str(cred_path)))
        except Exception as e:
            logger.warning("FCM initialize failed: {}", e)
            _fcm_initialized = True
            return False
    _fcm_initialized = True
    return True


def send_fcm_one(token: str, title: str, body: str) -> bool:
    """
    Send one FCM notification to one device token (Android or other non-Apple).
    Returns True if sent successfully. Never raises.
    """
    if not _ensure_fcm_initialized():
        return False
    try:
        from firebase_admin import messaging
        msg = messaging.Message(
            notification=messaging.Notification(title=title or "HomeClaw", body=(body or "")[:1024]),
            data={"source": "reminder", "text": (body or "")[:1024]},
            token=token,
        )
        messaging.send(msg)
        return True
    except Exception as e:
        logger.debug("FCM send to token ...{} failed: {}", token[-8:] if len(token) > 8 else token, e)
    return False


def send_push_to_user(user_id: str, title: str, body: str) -> int:
    """
    Send FCM notification to all non-Apple tokens registered for user_id.
    For APNs (iOS/Apple) use base.push_send.send_push_to_user which routes by platform.
    title/body are used for the notification payload.
    Returns number of messages successfully sent. Never raises.
    """
    if not _ensure_fcm_initialized():
        return 0
    try:
        from base import push_tokens as push_tokens_store
        from firebase_admin import messaging
    except ImportError:
        return 0
    user_id = (user_id or "").strip() or "companion"
    entries = push_tokens_store.get_tokens_for_user(user_id)
    if not entries:
        return 0
    sent = 0
    for entry in entries:
        platform = (entry.get("platform") or "android").strip().lower()
        if platform in ("ios", "macos", "tvos", "ipados", "watchos"):
            continue
        token = (entry.get("token") or "").strip()
        if not token:
            continue
        try:
            msg = messaging.Message(
                notification=messaging.Notification(title=title or "HomeClaw", body=(body or "")[:1024]),
                data={"source": "reminder", "text": (body or "")[:1024]},
                token=token,
            )
            messaging.send(msg)
            sent += 1
        except Exception as e:
            logger.debug("FCM send to token ...{} failed: {}", token[-8:] if len(token) > 8 else token, e)
            if "not a valid FCM registration token" in str(e).lower() or "unregistered" in str(e).lower():
                push_tokens_store.unregister_push_token(user_id, token)
    return sent
