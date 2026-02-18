"""
LINE channel: LINE Messaging API webhook. Receives message/image/video/audio/file events,
downloads media, forwards to Core; sends replies via LINE reply or push API.
Configure LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET in channels/line/.env.
Set webhook URL in LINE Developers Console to https://<your-host>:<port>/line/webhook
"""
import asyncio
import base64
import hmac
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from dotenv import dotenv_values
from fastapi import FastAPI, Request, Response
from loguru import logger
import yaml

from base.util import Util
from base.BaseChannel import ChannelMetadata, BaseChannel
from base.base import PromptRequest, AsyncResponse, ChannelType, ContentType

from .download import download_line_media
from .send import send_line_text

channel_app = FastAPI()
LINE_MEDIA_MAX_BYTES = 10 * 1024 * 1024  # 10MB


def _get_line_config():
    root = Path(__file__).resolve().parent
    env_path = root / ".env"
    env = dotenv_values(env_path) if env_path.exists() else {}
    token = (env.get("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()
    secret = (env.get("LINE_CHANNEL_SECRET") or os.getenv("LINE_CHANNEL_SECRET") or "").strip()
    return {"channel_access_token": token, "channel_secret": secret}


def _verify_line_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    if not body or not signature or not channel_secret:
        return False
    try:
        expected = base64.b64encode(hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()).decode("ascii")
        return hmac.compare_digest(expected, signature.strip())
    except Exception:
        return False


class Channel(BaseChannel):
    def __init__(self, metadata: ChannelMetadata):
        super().__init__(metadata=metadata, app=channel_app)
        self.message_queue = asyncio.Queue()
        self.message_queue_task = None
        self.chats = {}

    def _build_request(
        self,
        request_id: str,
        user_id: str,
        text: str,
        images: list,
        videos: list,
        audios: list,
        files: list,
        reply_token: str | None,
        request_metadata: dict,
    ) -> PromptRequest:
        if videos:
            contentType = ContentType.VIDEO.value
        elif audios:
            contentType = ContentType.AUDIO.value
        elif images:
            contentType = ContentType.TEXTWITHIMAGE.value
        elif files:
            contentType = ContentType.TEXT.value
        else:
            contentType = ContentType.TEXT.value
        if not text:
            text = "(no text)"
        return PromptRequest(
            request_id=request_id,
            channel_name=self.metadata.name,
            request_metadata=request_metadata,
            channelType=ChannelType.IM.value,
            user_name=user_id,
            app_id="line",
            user_id=user_id,
            contentType=contentType,
            text=text,
            action="respond",
            host=self.metadata.host,
            port=self.metadata.port,
            images=images or [],
            videos=videos or [],
            audios=audios or [],
            files=files if files else None,
            timestamp=datetime.now().timestamp(),
        )

    async def process_message_queue(self):
        config = _get_line_config()
        token = config.get("channel_access_token") or ""
        while True:
            try:
                response: AsyncResponse = await self.message_queue.get()
                response_data = getattr(response, "response_data", None) or {}
                request_meta = getattr(response, "request_metadata", None) or {}
                to = request_meta.get("line_user_id") or request_meta.get("to")
                reply_token = request_meta.get("reply_token")
                if "text" in response_data and (to or reply_token):
                    text = response_data.get("text")
                    if isinstance(text, str) and text and token:
                        if reply_token:
                            send_line_text(reply_token, text, token, is_reply_token=True)
                        elif to:
                            send_line_text(to, text, token, is_reply_token=False)
                self.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Line process_message_queue: {}", e)
                try:
                    self.message_queue.task_done()
                except ValueError:
                    pass

    def initialize(self):
        self.message_queue_task = asyncio.create_task(self.process_message_queue())
        super().initialize()

    def stop(self):
        if self.message_queue_task:
            self.message_queue_task.cancel()
        super().stop()

    async def handle_async_response(self, response: AsyncResponse):
        try:
            await self.message_queue.put(response)
        except Exception as e:
            logger.error("Line handle_async_response: {}", e)

    def _handle_message_event(self, event: dict, config: dict):
        message = event.get("message", {})
        msg_type = message.get("type", "text")
        msg_id = message.get("id")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        user_id = source.get("userId") or ""
        if source.get("type") == "group":
            group_id = source.get("groupId", "")
            line_user_id = f"line:group:{group_id}"
        elif source.get("type") == "room":
            room_id = source.get("roomId", "")
            line_user_id = f"line:room:{room_id}"
        else:
            line_user_id = f"line:user:{user_id}" if user_id else f"line:{user_id}"
        request_id = msg_id or str(datetime.now().timestamp())
        request_metadata = {
            "line_user_id": line_user_id,
            "reply_token": reply_token,
            "msg_id": request_id,
            "channel": "line",
            "to": line_user_id,
        }
        text = ""
        images = []
        videos = []
        audios = []
        files = []
        token = config.get("channel_access_token") or ""

        if msg_type == "text":
            text = message.get("text", "") or ""
        elif msg_type in ("image", "video", "audio", "file") and msg_id and token:
            path = download_line_media(msg_id, token, LINE_MEDIA_MAX_BYTES)
            if path and os.path.isfile(path):
                if msg_type == "image":
                    images = [path]
                    text = "User sent an image"
                elif msg_type == "video":
                    videos = [path]
                    text = "User sent a video"
                elif msg_type == "audio":
                    audios = [path]
                    text = "User sent audio"
                else:
                    files = [path]
                    text = "User sent a file"
        else:
            text = f"Unsupported message type: {msg_type}"

        self.chats[request_id] = request_metadata
        req = self._build_request(
            request_id=request_id,
            user_id=line_user_id,
            text=text,
            images=images,
            videos=videos,
            audios=audios,
            files=files,
            reply_token=reply_token,
            request_metadata=request_metadata,
        )
        try:
            self.syncTransferTocore(request=req)
        except Exception as e:
            logger.exception("Line syncTransferTocore: {}", e)

    def _handle_events(self, body: dict, config: dict):
        events = body.get("events") or []
        for event in events:
            try:
                ev_type = event.get("type")
                if ev_type == "message":
                    self._handle_message_event(event, config)
                elif ev_type in ("follow", "unfollow", "join", "leave"):
                    logger.debug("Line event {}", ev_type)
            except Exception as e:
                logger.exception("Line event handler: {}", e)


@channel_app.get("/")
def read_root():
    return {"channel": "line", "webhook": "POST /line/webhook"}


@channel_app.post("/line/webhook")
async def line_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("x-line-signature") or ""
    config = _get_line_config()
    secret = config.get("channel_secret") or ""
    if not _verify_line_signature(raw, signature, secret):
        return Response(content='{"error":"Invalid signature"}', status_code=401, media_type="application/json")
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception as e:
        logger.debug("Line webhook parse: {}", e)
        return Response(content='{"error":"Invalid JSON"}', status_code=400, media_type="application/json")
    channel = getattr(channel_app, "_line_channel", None)
    if channel and isinstance(channel, Channel):
        import threading
        def run_events():
            try:
                channel._handle_events(body, config)
            except Exception as e:
                logger.exception("Line webhook _handle_events: {}", e)
        threading.Thread(target=run_events, daemon=True).start()
    return Response(content='{"status":"ok"}', status_code=200, media_type="application/json")


def main():
    root = Util().channels_path()
    config_path = Path(root) / "line" / "config.yml"
    if not config_path.exists():
        logger.error("Line config not found: {}", config_path)
        return
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    metadata = ChannelMetadata(**config)
    channel = Channel(metadata=metadata)
    channel_app._line_channel = channel
    try:
        import asyncio
        asyncio.run(channel.run())
    except KeyboardInterrupt:
        logger.debug("Line channel shutting down")
    except Exception as e:
        logger.exception("Line channel: {}", e)
    finally:
        channel.stop()


if __name__ == "__main__":
    main()
