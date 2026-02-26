"""
Push notification router: APNs for iOS/Apple devices, FCM for Android and other platforms.
Core calls send_push_to_user here; this routes each token by platform.
"""
from loguru import logger

from base import push_tokens as push_tokens_store

_APPLE_PLATFORMS = frozenset(("ios", "macos", "tvos", "ipados", "watchos"))


def send_push_to_user(user_id: str, title: str, body: str) -> int:
    """
    Send push to all tokens registered for user_id.
    APNs for iOS/macOS/tvOS/etc.; FCM for Android and other platforms.
    title/body are used for the notification payload.
    Returns total number of messages successfully sent. Never raises.
    """
    user_id = (user_id or "").strip() or "companion"
    entries = push_tokens_store.get_tokens_for_user(user_id)
    if not entries:
        return 0
    sent = 0
    for entry in entries:
        token = (entry.get("token") or "").strip()
        if not token:
            continue
        platform = (entry.get("platform") or "android").strip().lower()
        if platform in _APPLE_PLATFORMS:
            try:
                from base import apns_send
                if apns_send.send_apns_one(token, title or "HomeClaw", body or ""):
                    sent += 1
                else:
                    logger.debug("APNs send to ...{} failed; token may be invalid", token[-8:] if len(token) > 8 else token)
            except Exception as e:
                logger.debug("APNs send failed: {}", e)
        else:
            try:
                from base import fcm_send
                if fcm_send.send_fcm_one(token, title or "HomeClaw", body or ""):
                    sent += 1
                else:
                    logger.debug("FCM send to ...{} failed", token[-8:] if len(token) > 8 else token)
            except Exception as e:
                logger.debug("FCM send failed: {}", e)
                err_lower = str(e).lower()
                if "not a valid FCM registration token" in err_lower or "unregistered" in err_lower:
                    push_tokens_store.unregister_push_token(user_id, token)
    return sent
