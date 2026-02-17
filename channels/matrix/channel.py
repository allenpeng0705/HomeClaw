# Test account for Matrix
# @allenpeng:matrix.org:Eficode232410@
# @pengshilei:matrix.org:Eficode232410@
# Tinode home server: https://matrix.org


import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
import sys
from pathlib import Path
import threading
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel
from dotenv import dotenv_values
import yaml
from os import getenv
import simplematrixbotlib as botlib
from nio.rooms import MatrixRoom
from nio.events.room_events import Event

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from base.util import Util
from base.BaseChannel import ChannelMetadata, BaseChannel
from base.base import PromptRequest, AsyncResponse, ChannelType, ContentType



channel_app: FastAPI = FastAPI()  


class MatrixRequest(BaseModel):
    im_name: str
    sender: str
    message: str
    msg_id: str


class Channel(BaseChannel):
    def __init__(self, metadata: ChannelMetadata):
        super().__init__(metadata=metadata, app=channel_app)
        channels_path = Util().root_path() + '/channels/' + 'matrix/'
        env_path = os.path.join(channels_path, '.env')
        env_vars = dotenv_values(env_path)
        home_srv = env_vars['home_server']
        home_srv = home_srv.strip()
        username = env_vars['username']
        username = username.strip()
        password = env_vars['password']
        password = password.strip()
        if home_srv is None or len(home_srv) == 0:
            print("Please enter the home server of Matrix(输入Matrix的主服务器地址): Eg: https://matrix.org \n")
            home_srv = input("Input the home server of Matrix：(输入Matrix的主服务器地址): ")
            print("Please enter the username of Matrix(输入Matrix的用户名): Eg: @allenpeng:matrix.org \n")
            username = input("Input the username of Matrix(输入Matrix的用户名): ")
            print("Please enter the password of Matrix(输入Matrix的密码): Eg: Eficode232410@ \n")
            password = input("Input the password of Matrix(输入Matrix的密码): ")
            with open(env_path, 'w') as f:
                f.write(f"home_server={home_srv}\n")
                f.write(f"username={username}\n")
                f.write(f"password={password}\n")

        self._home_srv = home_srv.strip().rstrip('/')
        self.creds = botlib.Creds(home_srv, username, password)
        self.config = botlib.Config()
        #self.config.encryption_enabled = True
        self.config.ignore_unverified_devices = True

        self.bot = botlib.Bot(creds=self.creds, config=self.config)
        self.PREFIX = '!'
        self.message_queue = asyncio.Queue()
        self.bot_task = None
        self.message_queue_task = None

    # def core_url(self) -> str | None:
    #     """Get the core url from sub class's .env file"""
    #     channels_path = Util().root_path() + '/channels/'
    #     env_path = os.path.join(channels_path, '.env')
    #     env_vars = dotenv_values(env_path)
    #     core_url = None
    #     if 'core_host' in env_vars and 'core_port' in env_vars:
    #         host = env_vars['core_host']
    #         port = env_vars['core_port']
    #         core_url = f"http://{host}:{port}"
    #     else:
    #         core_url = None
    #     return core_url


    async def run_bot(self):
        @self.bot.listener.on_message_event
        async def on_message(room: MatrixRoom, message: Event):
            try:
                match = botlib.MessageMatch(room, message, self.bot, self.PREFIX)
                logger.debug(f'room: {room.name}')
                content = message.source.get('content', {})
                msgtype = content.get('msgtype', 'm.text')
                body = content.get('body', '') or ''
                logger.debug(f"received message {message.sender} {body[:64] if isinstance(body, str) else body}")
                # Extract data from request
                im_name = 'matrix'
                sender = 'matrix:' + message.sender
                logger.debug(f"sender: {sender}")
                msg_id = message.event_id
                text = body if isinstance(body, str) else ''
                action = ''
                images = []

                videos = []
                audios = []
                files_list = []
                mxc_url = content.get('url') or content.get('info', {}).get('url')

                if msgtype == 'm.image' and mxc_url:
                    try:
                        if mxc_url.startswith('mxc://'):
                            server_media = mxc_url[6:]
                            if '/' in server_media:
                                server, media_id = server_media.split('/', 1)
                                base = self._home_srv.replace('https://', '').replace('http://', '').rstrip('/')
                                download_url = f"https://{base}/_matrix/media/r0/download/{server}/{media_id}"
                                async with httpx.AsyncClient() as client:
                                    r = await client.get(download_url, timeout=30.0)
                                    if r.status_code == 200:
                                        suffix = (content.get('info', {}).get('mimetype') or 'image/png').split('/')[-1] or 'png'
                                        with tempfile.NamedTemporaryFile(delete=False, suffix='.' + suffix) as f:
                                            f.write(r.content)
                                            images.append(f.name)
                    except Exception as e:
                        logger.debug("Matrix image download: %s", e)
                    text = text or 'Image'
                    action = 'respond'
                elif msgtype in ('m.video', 'm.audio', 'm.file') and mxc_url:
                    try:
                        if mxc_url.startswith('mxc://'):
                            server_media = mxc_url[6:]
                            if '/' in server_media:
                                server, media_id = server_media.split('/', 1)
                                base = self._home_srv.replace('https://', '').replace('http://', '').rstrip('/')
                                download_url = f"https://{base}/_matrix/media/r0/download/{server}/{media_id}"
                                async with httpx.AsyncClient() as client:
                                    r = await client.get(download_url, timeout=60.0)
                                    if r.status_code == 200:
                                        mimetype = content.get('info', {}).get('mimetype') or 'application/octet-stream'
                                        suffix = mimetype.split('/')[-1] or 'bin'
                                        if msgtype == 'm.video':
                                            suffix = 'mp4' if 'video' in mimetype else suffix
                                        elif msgtype == 'm.audio':
                                            suffix = 'm4a' if 'mpeg' not in mimetype else 'mp3'
                                        with tempfile.NamedTemporaryFile(delete=False, suffix='.' + suffix) as f:
                                            f.write(r.content)
                                            path = f.name
                                        if msgtype == 'm.video':
                                            videos.append(path)
                                            text = text or 'Video'
                                        elif msgtype == 'm.audio':
                                            audios.append(path)
                                            text = text or 'Audio'
                                        else:
                                            files_list.append(path)
                                            text = text or 'File'
                    except Exception as e:
                        logger.debug("Matrix media download: %s", e)
                    action = 'respond'
                else:
                    if isinstance(text, str):
                        if text.startswith('+') or text.startswith('＋'):
                            action = 'store'
                            text = text[1:]
                        elif text.startswith('?') or text.startswith('？'):
                            action = 'retrieve'
                            text = text[1:]
                        else:
                            action = 'respond'

                if not text:
                    text = ''
                if videos:
                    contentType = ContentType.VIDEO.value
                elif audios:
                    contentType = ContentType.AUDIO.value
                elif images:
                    contentType = ContentType.TEXTWITHIMAGE.value
                else:
                    contentType = ContentType.TEXT.value

                request = PromptRequest(
                    request_id=msg_id,
                    channel_name=self.metadata.name,
                    request_metadata={'matrix_room_id': room.room_id},
                    channelType=ChannelType.IM.value,
                    user_name=sender,
                    app_id=im_name,
                    user_id=sender,
                    contentType=contentType,
                    text=text,
                    action=action,
                    host=self.metadata.host,
                    port=self.metadata.port,
                    images=images,
                    videos=videos,
                    audios=audios,
                    files=files_list if files_list else None,
                    timestamp=datetime.now().timestamp()
                )

                await self.transferTocore(request=request)

            except Exception as e:
                logger.exception(e)
                return {"message": "System Internal Error", "response": "Sorry, something went wrong. Please try again later."}
            
        logger.debug("Matrix Channel is running now")  
        await self.bot.main()
        

    async def process_message_queue(self):
        while True:
            try:
                response: AsyncResponse = await self.message_queue.get()
                logger.debug(f"Got response from message queue")
                response_data = getattr(response, "response_data", None) or {}
                request_meta = getattr(response, "request_metadata", None) or {}
                room_id = request_meta.get("matrix_room_id")
                if not room_id:
                    logger.debug("Matrix: no room_id in response")
                    self.message_queue.task_done()
                    continue
                if "text" in response_data:
                    text = response_data.get("text")
                    if isinstance(text, str) and text:
                        try:
                            await self.bot.api.send_text_message(room_id, text)
                        except asyncio.TimeoutError:
                            logger.error("Timeout sending message to room %s", room_id)
                        except Exception as e:
                            logger.error("Error sending message: %s", e)
                if "image" in response_data:
                    image_path = response_data.get("image")
                    if isinstance(image_path, str) and os.path.isfile(image_path):
                        try:
                            await self.bot.api.send_image_message(room_id=room_id, image_filepath=image_path)
                        except Exception as e:
                            logger.error("Error sending image: %s", e)
                if "video" in response_data:
                    video_path = response_data.get("video")
                    if isinstance(video_path, str) and os.path.isfile(video_path):
                        try:
                            await self.bot.api.send_video_message(room_id=room_id, video_filepath=video_path)
                        except Exception as e:
                            logger.error("Error sending video: %s", e)
                self.message_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing message queue: {str(e)}")


    def initialize(self):
        logger.debug("Natrix Channel initializing...")
        self.bot_task = asyncio.create_task(self.run_bot())
        # Start processing the message queue
        self.message_queue_task = asyncio.create_task(self.process_message_queue())
        super().initialize()


    def stop(self):
        # do some deinitialization here
        # Implement proper shutdown logic here
        self.bot_task.cancel()
        self.message_queue_task.cancel()
        super().stop()
        logger.debug("Matrix Channel is stopping!")
        
        
    async def handle_async_response(self, response: AsyncResponse):
        logger.debug(f"Put response: {response} into message queue")
        await self.message_queue.put(response)        
        
shutdown_url = ""    
def main():
    root = Util().channels_path()
    config_path = os.path.join(root, 'matrix', 'config.yml')
    with open(config_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
        metadata = ChannelMetadata(**config)
        global shutdown_url
        host = metadata.host
        if host == '0.0.0.0':
            host = '127.0.0.1'
        shutdown_url = "http://" + host + ":" + str(metadata.port) + "/shutdown"
    with Channel(metadata=metadata) as channel:
        try:
            asyncio.run(channel.run())
        except KeyboardInterrupt:
            logger.debug("Shutting down...")
        except Exception as e:
            logger.exception(f"An error occurred: {e}")
        finally:
            channel.stop()
        '''
        bot_task = asyncio.create_task(run_bot_in_thread(channel.bot))
        matrix_task = asyncio.create_task(channel.run())
        
        try:
            await asyncio.gather(bot_task, matrix_task)
        except asyncio.CancelledError:
            logger.debug("Tasks were cancelled")
        except Exception as e:
            logger.debug(f"An error occurred: {e}")
        finally:
            # Cancel tasks if they haven't completed
            for task in [bot_task, matrix_task]:
                if not task.done():
                    task.cancel()
            # Wait for tasks to be cancelled
            await asyncio.gather(*[bot_task, matrix_task], return_exceptions=True)    
        '''


def suicide():
    try:
        global shutdown_url
        httpx.get(shutdown_url)
    except Exception as e:
        logger.exception(e)
            

if __name__ == "__main__":
    main()

