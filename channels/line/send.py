"""
Send text (and optionally media) via LINE Messaging API (reply or push).
Never raises; returns False on failure. Logs errors.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import httpx
from loguru import logger


def _reply_message(reply_token: str, channel_access_token: str, messages: list) -> bool:
    if not reply_token or not channel_access_token or not messages:
        return False
    try:
        url = "https://api.line.me/v2/bot/message/reply"
        headers = {
            "Authorization": f"Bearer {channel_access_token.strip()}",
            "Content-Type": "application/json",
        }
        body = {"replyToken": reply_token.strip(), "messages": messages}
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, headers=headers, json=body)
            if r.status_code != 200:
                logger.warning("LINE reply failed: {} {}", r.status_code, r.text[:200])
                return False
            return True
    except Exception as e:
        logger.error("LINE reply: {}", e)
        return False


def _push_message(to: str, channel_access_token: str, messages: list) -> bool:
    if not to or not channel_access_token or not messages:
        return False
    try:
        to = to.strip().replace("line:user:", "").replace("line:group:", "").replace("line:room:", "").replace("line:", "")
        if not to:
            return False
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Authorization": f"Bearer {channel_access_token.strip()}",
            "Content-Type": "application/json",
        }
        body = {"to": to, "messages": messages}
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, headers=headers, json=body)
            if r.status_code != 200:
                logger.warning("LINE push failed: {} {}", r.status_code, r.text[:200])
                return False
            return True
    except Exception as e:
        logger.error("LINE push: {}", e)
        return False


def send_line_text(
    to_or_reply_token: str,
    text: str,
    channel_access_token: str,
    *,
    is_reply_token: bool = False,
) -> bool:
    """
    Send a text message. If is_reply_token=True, use reply API; else use push API (to = user/group/room ID).
    Never raises. Returns True on success.
    """
    if not text or not isinstance(text, str):
        text = ""
    messages = [{"type": "text", "text": text[:5000]}]
    if is_reply_token:
        return _reply_message(to_or_reply_token, channel_access_token, messages)
    return _push_message(to_or_reply_token, channel_access_token, messages)
