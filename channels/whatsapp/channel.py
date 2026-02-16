import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
import sys
from pathlib import Path
import threading
import httpx
from abc import ABC, abstractmethod
import signal
from datetime import timedelta
from neonize.client import NewClient
from neonize.events import (
    ConnectedEv,
    MessageEv,
    PairStatusEv,
    event,
    ReceiptEv,
    CallOfferEv,
)
from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
    Message,
    FutureProofMessage,
    InteractiveMessage,
    MessageContextInfo,
    DeviceListMetadata,
)
from neonize.types import MessageServerID
from neonize.utils import log
from neonize.utils.enum import ReceiptType
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel
from dotenv import dotenv_values
import yaml
from os import getenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from base.util import Util
from base.BaseChannel import ChannelMetadata, BaseChannel
from base.base import PromptRequest, AsyncResponse, ChannelType, ContentType



channel_app: FastAPI = FastAPI()  

client: NewClient = NewClient("db.sqlite3")


class Channel(BaseChannel):
    def __init__(self, metadata: ChannelMetadata):
        super().__init__(metadata=metadata, app=channel_app)

        self.message_queue = asyncio.Queue()
        self.whatsapp_task = None
        self.message_queue_task = None
        self.chats = {}


    def handle_message(self, client: NewClient, message: MessageEv):
        try:
            sender = message.Info.MessageSource.Sender.User
            msg_id = message.Info.ID
            chat = message.Info.MessageSource.Chat
            self.chats[msg_id] = chat

            im_name = 'whatsapp'
            sender_str = 'whatsapp:' + sender
            content = ''
            text = ''
            action = 'respond'
            images = []

            # Image message: message.Message.imageMessage
            if message.Message.HasField('imageMessage'):
                im_msg = message.Message.imageMessage
                content = getattr(im_msg, 'caption', '') or 'Image'
                text = content
                try:
                    # Neonize may expose download_media or similar; try to get image bytes/path
                    if hasattr(client, 'download_media') and callable(getattr(client, 'download_media')):
                        result = client.download_media(message)
                        if result:
                            if isinstance(result, bytes):
                                b64 = base64.b64encode(result).decode('ascii')
                                images.append(f"data:image/jpeg;base64,{b64}")
                            elif isinstance(result, str) and os.path.isfile(result):
                                with open(result, 'rb') as f:
                                    b64 = base64.b64encode(f.read()).decode('ascii')
                                images.append(f"data:image/jpeg;base64,{b64}")
                    elif hasattr(message, 'download_media') and callable(getattr(message, 'download_media')):
                        result = message.download_media()
                        if result:
                            if isinstance(result, bytes):
                                b64 = base64.b64encode(result).decode('ascii')
                                images.append(f"data:image/jpeg;base64,{b64}")
                            elif isinstance(result, str) and os.path.isfile(result):
                                with open(result, 'rb') as f:
                                    b64 = base64.b64encode(f.read()).decode('ascii')
                                images.append(f"data:image/jpeg;base64,{b64}")
                except Exception as e:
                    logger.debug("WhatsApp image download: %s", e)
                if not text:
                    text = 'Image'
            else:
                content = message.Message.conversation or (message.Message.extendedTextMessage.text if message.Message.HasField('extendedTextMessage') else '')
                content = content or ''
                logger.debug(f"whatsapp Received message from {sender_str}: {content}")
                if content.startswith('+') or content.startswith('+'):
                    action = 'store'
                    text = content[1:]
                elif content.startswith('?') or content.startswith('？'):
                    action = 'retrieve'
                    text = content[1:]
                else:
                    text = content

            request = PromptRequest(
                request_id=msg_id,
                channel_name=self.metadata.name,
                request_metadata={'sender': sender_str, 'msg_id': msg_id, 'channel': 'whatsapp'},
                channelType=ChannelType.IM.value,
                user_name=sender_str,
                app_id=im_name,
                user_id=sender_str,
                contentType=ContentType.TEXTWITHIMAGE.value if images else ContentType.TEXT.value,
                text=text,
                action=action,
                host=self.metadata.host,
                port=self.metadata.port,
                images=images,
                videos=[],
                audios=[],
                timestamp=datetime.now().timestamp()
            )
            self.syncTransferTocore(request=request)

        except Exception as e:
            logger.exception(e)
            return {"message": "System Internal Error", "response": "Sorry, something went wrong. Please try again later."}         
    


    async def process_message_queue(self):
        while True:
            try: 
                global client
                response: AsyncResponse = await self.message_queue.get()
                logger.debug(f"Got response: {response} from message queue")
                """Handle the response from the core"""
                request_id = response.request_id
                response_data = response.response_data
                to = response.request_metadata['sender']
                msg_id = response.request_metadata['msg_id']
                if 'text' in response_data:
                    text = response_data['text']
                    logger.debug(f"sending text: {text} to {to}") 
                    chat = self.chats.pop(msg_id)  
                    try:
                        client.send_message(chat, text)
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout sending message to whatsapp user {to}")
                    except Exception as e:
                        logger.error(f"Error sending message: {str(e)}")
                    

                self.message_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing whatsapp message queue: {str(e)}")


    def initialize(self):
        logger.debug("whatsapp Channel initializing...")
        self.message_queue_task = asyncio.create_task(self.process_message_queue())
        super().initialize()
        


    def stop(self):
        # do some deinitialization here
        super().stop()
        self.message_queue_task.cancel()
        logger.debug("Whatsapp Channel is stopping!")
        
        
    async def handle_async_response(self, response: AsyncResponse):
        logger.debug(f"Put response: {response} into message queue")
        await self.message_queue.put(response) 


channel: Channel = None

@client.event(ConnectedEv)
def on_connected(_: NewClient, __: ConnectedEv):
    logger.debug("whatsapp Connected\n")


@client.event(ReceiptEv)
def on_receipt(_: NewClient, receipt: ReceiptEv):
    logger.debug(receipt)


@client.event(CallOfferEv)
def on_call(_: NewClient, call: CallOfferEv):
    logger.debug(call)


@client.event(PairStatusEv)
def PairStatusMessage(_: NewClient, message: PairStatusEv):
    logger.debug(f"logged as {message.ID.User}")

@client.event(MessageEv)
def on_message(client: NewClient, message: MessageEv):
    channel.handle_message(client, message)  


def run_client_connect_forever():
    # This function will run in a separate thread
    # Assuming client.connect() is a blocking function with an endless loop
    logger.debug("client connecting...")
    global client
    client.connect()     

shutdown_url = ""         
def main():
    root = Util().channels_path()
    config_path = os.path.join(root, 'whatsapp', 'config.yml')
    with open(config_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
        metadata = ChannelMetadata(**config)
        global shutdown_url
        host = metadata.host
        if host == '0.0.0.0':
            host = '127.0.0.1'
        shutdown_url = "http://" + host + ":" + str(metadata.port) + "/shutdown"
    
    try:
        global channel
        channel = Channel(metadata=metadata)

        # Start client.connect() in a background thread
        thread = threading.Thread(target=run_client_connect_forever, daemon=True)
        thread.start()        
        logger.debug("client connected...")
        asyncio.run(channel.run()) 
    except KeyboardInterrupt:
        logger.debug("Shutting down...")
    except Exception as e:
        logger.exception(f"An error occurred: {e}")
    finally:
        channel.stop()
            
def suicide():
    try:
        global shutdown_url
        httpx.get(shutdown_url)
    except Exception as e:
        logger.exception(e)


if __name__ == "__main__":
    main()

