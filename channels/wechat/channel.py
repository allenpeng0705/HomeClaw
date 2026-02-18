import asyncio
import base64
import tempfile
from datetime import datetime
import json
import os
import sys
from pathlib import Path
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
from loguru import logger
from pydantic import BaseModel
from dotenv import dotenv_values
import yaml
from wcferry import Wcf, WxMsg
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from base.util import Util
from base.base import PromptRequest, AsyncResponse, ChannelType, ContentType
from base.BaseChannel import ChannelMetadata, BaseChannel



channel_app: FastAPI = FastAPI()  

class Channel(BaseChannel):
    def __init__(self, metadata: ChannelMetadata):
        super().__init__(metadata=metadata, app=channel_app)
        # Determine the root running path
        root_running_path = Path.cwd()  # This gives the current working directory

        # Define the logs folder and wcf.txt file path relative to the root running directory
        logs_folder = os.path.join(root_running_path, "logs")
        if not os.path.exists(logs_folder):
            os.makedirs(logs_folder)
        wcf_file = os.path.join(logs_folder, "wcf.txt")

        if not os.path.isfile(wcf_file):
            with open(wcf_file, "x") as f:
                pass
        self.wcf_file = wcf_file
        self.wcf = Wcf(debug=False)
        self.wcf.LOG = False
        self.wcf.enable_recv_msg(self.on_wechat_message)


    def on_wechat_message(self, msg: WxMsg):
        logger.debug(f"Received request: {msg}")
        contacts = self.wcf.get_contacts()
        name = ''
        for contact in contacts:
            logger.debug(contact)

        name = msg.sender
        roomid = msg.roomid
        action = 'respond'
        text = getattr(msg, 'content', '') or ''
        images = []

        # Image message: WxMsg has type, extra (path for image/video), and is_text()
        if not getattr(msg, 'is_text', lambda: True)() and getattr(msg, 'extra', None):
            try:
                msg_id_int = int(msg.id) if str(msg.id).isdigit() else 0
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = self.wcf.download_image(msg_id_int, msg.extra, tmpdir)
                    if path and os.path.isfile(path):
                        with open(path, 'rb') as f:
                            b64 = base64.b64encode(f.read()).decode('ascii')
                        images.append(f"data:image/jpeg;base64,{b64}")
                        text = 'User sent an image' if not text else text
                if not images and os.path.isfile(getattr(msg, 'extra', '') or ''):
                    with open(msg.extra, 'rb') as f:
                        b64 = base64.b64encode(f.read()).decode('ascii')
                    images.append(f"data:image/jpeg;base64,{b64}")
                    text = 'User sent an image' if not text else text
            except Exception as e:
                logger.debug("WeChat image download: {}", e)
            if not text:
                text = 'Image'
        else:
            text = (text or '').lower()
            if text.startswith('+') or text.startswith('+'):
                action = 'store'
                text = msg.content[1:]
            elif text.startswith('?') or text.startswith('？'):
                action = 'retrieve'
                text = msg.content[1:]
            else:
                text = msg.content

        logger.debug(f"msg_id: {msg.id}, msg sender: {name}, roomid: {roomid}, action: {action}, text: {text[:64] if text else ''}")
        try:
            request = PromptRequest(
                request_id=str(msg.id),
                channel_name=self.metadata.name,
                request_metadata={'sender': msg.sender},
                channelType=ChannelType.IM.value,
                user_name=name,
                app_id='wechat',
                user_id='wechat:' + name,
                contentType=ContentType.TEXTWITHIMAGE.value if images else ContentType.TEXT.value,
                text=text,
                action=action,
                host=self.metadata.host,
                port=self.metadata.port,
                images=images or [],
                videos=[],
                audios=[],
                files=None,
                timestamp=datetime.now().timestamp()
            )
            self.syncTransferTocore(request=request)
        except Exception as e:
            logger.exception(e)


    def initialize(self):
        logger.debug("Wechat Channel initializing...")
        super().initialize()
            
         # add more endpoints here    
        logger.debug("IM Channel initialized and all the endpoints are registered!")


    def stop(self):
        # do some deinitialization here
        self.wcf.cleanup()
        super().stop()    
        logger.debug("Wechat Channel is stopping!")
        
        
    async def handle_async_response(self, response: AsyncResponse):
        """Handle the response from the core. Never raises; logs errors."""
        try:
            response_data = getattr(response, "response_data", None) or {}
            request_meta = getattr(response, "request_metadata", None) or {}
            sender = request_meta.get("sender")
            if not sender:
                logger.debug("WeChat: no sender in response")
                return
            if "text" in response_data:
                text = response_data.get("text")
                if isinstance(text, str) and text:
                    try:
                        self.wcf.send_text(text, sender)
                    except Exception as e:
                        logger.error("WeChat send_text: {}", e)
            if "image" in response_data:
                image_path = response_data.get("image")
                if isinstance(image_path, str) and os.path.isfile(image_path):
                    try:
                        await asyncio.to_thread(self.wcf.send_image, image_path, sender)
                    except Exception as e:
                        logger.error("WeChat send_image: {}", e)
            if "video" in response_data:
                video_path = response_data.get("video")
                if isinstance(video_path, str) and os.path.isfile(video_path):
                    try:
                        await asyncio.to_thread(self.wcf.send_file, video_path, sender)
                    except Exception as e:
                        logger.error("WeChat send_file (video): %s", e)
            if "file" in response_data:
                file_path = response_data.get("file")
                if isinstance(file_path, str) and os.path.isfile(file_path):
                    try:
                        await asyncio.to_thread(self.wcf.send_file, file_path, sender)
                    except Exception as e:
                        logger.error("WeChat send_file: {}", e)
            if "audio" in response_data:
                audio_path = response_data.get("audio")
                if isinstance(audio_path, str) and os.path.isfile(audio_path):
                    try:
                        await asyncio.to_thread(self.wcf.send_file, audio_path, sender)
                    except Exception as e:
                        logger.error("WeChat send_file (audio): %s", e)
        except Exception as e:
            logger.exception("WeChat handle_async_response: {}", e)   

shutdown_url = ""
def main():
    try:
        root = Util().channels_path()
        config_path = os.path.join(root, 'wechat', 'config.yml')
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            #logger.debug(config)
            metadata = ChannelMetadata(**config)

        global shutdown_url
        host = metadata.host
        if host == '0.0.0.0':
            host = '127.0.0.1'
        shutdown_url = "http://" + host + ":" + str(metadata.port) + "/shutdown"
        with Channel(metadata=metadata) as channel:
                asyncio.run(channel.run())
    except Exception as e:
        logger.exception(e)


def suicide():
    try:
        global shutdown_url
        httpx.get(shutdown_url)
    except Exception as e:
        logger.exception(e)

if __name__ == "__main__":
    main()

