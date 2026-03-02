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
        with httpx.Client(timeout=15.0, trust_env=False) as client:
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
        with httpx.Client(timeout=15.0, trust_env=False) as client:
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


def send_line_messages(
    to_or_reply_token: str,
    messages: list,
    channel_access_token: str,
    *,
    is_reply_token: bool = False,
) -> bool:
    """
    Send a list of messages (text, image, etc.). LINE allows up to 5 per request; reply token is one-time use.
    Never raises. Returns True on success.
    """
    if not messages or not channel_access_token:
        return False
    messages = messages[:5]
    if is_reply_token:
        return _reply_message(to_or_reply_token, channel_access_token, messages)
    return _push_message(to_or_reply_token, channel_access_token, messages)


def send_line_image(
    to_or_reply_token: str,
    original_content_url: str,
    preview_image_url: str,
    channel_access_token: str,
    *,
    is_reply_token: bool = False,
) -> bool:
    """
    Send an image message. original_content_url and preview_image_url must be HTTPS (LINE requirement).
    Never raises. Returns True on success.
    """
    if not original_content_url or not original_content_url.strip().lower().startswith("https://"):
        return False
    preview = (preview_image_url or "").strip()
    if not preview or not preview.lower().startswith("https://"):
        preview = original_content_url
    messages = [{
        "type": "image",
        "originalContentUrl": original_content_url.strip(),
        "previewImageUrl": preview,
    }]
    return send_line_messages(to_or_reply_token, messages, channel_access_token, is_reply_token=is_reply_token)
