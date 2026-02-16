"""
DingTalk (钉钉) channel: Stream mode via dingtalk-stream SDK.
Receives messages over WebSocket, forwards to Core /inbound, replies with reply_text.
Core connection from channels/.env only. Set DINGTALK_CLIENT_ID, DINGTALK_CLIENT_SECRET in channels/.env.
Ref: https://github.com/soimy/other-agent-channel-dingtalk
"""
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
import httpx
from dingtalk_stream import (
    DingTalkStreamClient,
    Credential,
    AckMessage,
    ChatbotMessage,
    ChatbotHandler,
)

load_dotenv(_root / "channels" / ".env")
from base.util import Util

INBOUND_URL = f"{Util().get_channels_core_url()}/inbound"

DINGTALK_CLIENT_ID = os.getenv("DINGTALK_CLIENT_ID")
DINGTALK_CLIENT_SECRET = os.getenv("DINGTALK_CLIENT_SECRET")


class HomeClawDingTalkHandler(ChatbotHandler):
    """Forwards incoming DingTalk messages to Core /inbound and replies with the response."""

    async def process(self, callback_message):
        try:
            incoming_message = ChatbotMessage.from_dict(callback_message.data)
        except Exception as e:
            self.logger.warning("DingTalk parse message failed: %s", e)
            return AckMessage.STATUS_BAD_REQUEST, "invalid message"

        text_list = incoming_message.get_text_list() if incoming_message else []
        text = " ".join(text_list).strip() if text_list else ""
        if not text:
            return AckMessage.STATUS_OK, "ok"

        user_id = "dingtalk_{}".format(
            incoming_message.sender_id or incoming_message.conversation_id or "unknown"
        )
        user_name = incoming_message.sender_nick or user_id
        payload = {
            "user_id": user_id,
            "text": text,
            "channel_name": "dingtalk",
            "user_name": user_name,
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(INBOUND_URL, json=payload, timeout=120.0)
            data = r.json() if r.content else {}
            reply = data.get("text", "")
            if not reply and r.status_code != 200:
                reply = data.get("error", "Request failed")
        except httpx.ConnectError:
            reply = "Core unreachable. Is HomeClaw running?"
        except Exception as e:
            reply = "Error: {}".format(e)
        reply = reply or "(no reply)"
        self.reply_text(reply, incoming_message)
        return AckMessage.STATUS_OK, "ok"


def main():
    if not DINGTALK_CLIENT_ID or not DINGTALK_CLIENT_SECRET:
        print("Set DINGTALK_CLIENT_ID and DINGTALK_CLIENT_SECRET in channels/.env")
        return
    credential = Credential(DINGTALK_CLIENT_ID, DINGTALK_CLIENT_SECRET)
    client = DingTalkStreamClient(credential)
    client.register_callback_handler(ChatbotMessage.TOPIC, HomeClawDingTalkHandler())
    print("DingTalk channel: Stream mode (Core from channels/.env)")
    client.start_forever()


if __name__ == "__main__":
    main()
