import asyncio
import base64
import tempfile
from datetime import datetime
import json
import os
import re
import sys
from pathlib import Path
import threading
import imaplib
import email
from email.mime.text import MIMEText
import re
import smtplib
from email.policy import default
from email.header import Header, decode_header
from email.message import Message
import time
from dotenv import dotenv_values
import yaml


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from base.BaseChannel import ChannelMetadata, BaseChannel
from base.base import PromptRequest, AsyncResponse, ChannelType, ContentType
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel
from base.BaseChannel import ChannelMetadata, BaseChannel
from base.util import Util


channel_app: FastAPI = FastAPI()    

class Channel(BaseChannel):
    def __init__(self, metadata: ChannelMetadata):
        super().__init__(metadata=metadata, app=channel_app)
        self.kill = False


    def initialize(self):
        logger.debug("Email channel initializing...")
        self.start_monitoring()
        
        
    def send(self, send_to, subject, body):
        if not re.match(r"[^@]+@[^@]+\.[^@]+", send_to):
            raise ValueError("Invalid email address: %s" % send_to)

        email_account = Util().get_email_account()
        smtp_host = email_account.smtp_host
        smtp_port = email_account.smtp_port
        email_user = email_account.email_user
        email_pass = email_account.email_pass       

        message = MIMEText(body, 'plain', 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')
        message['From'] = email_user
        message['To'] = send_to
        try:
            smtp_server = smtplib.SMTP_SSL(smtp_host, int(smtp_port))
            smtp_server.ehlo()
            smtp_server.login(email_user, email_pass)
            smtp_server.sendmail(email_user, send_to, message.as_string())
            smtp_server.close()
            logger.debug("Email sent to " + send_to)
        except Exception as e:
            logger.debug('Failed to send email. Error:', e)
            raise InterruptedError('Failed to send email. Error:', e)
        
    
    # We only handle text response for now.   
    async def handle_async_response(self, response: AsyncResponse):
        """Handle the response from the core"""
        request_id = response.request_id
        response_data = response.response_data
        email_addr = response.request_metadata['email']
        subject = 'Re: ' + response.request_metadata['subject']
        if 'text' in response_data:
            text = response_data['text']
            # self.send(email_addr, subject, text)  
            await asyncio.to_thread(self.send, email_addr, subject, text)  

    
    def start_monitoring(self):
        logger.debug("Email channel starting monitoring...")
        try:
            # any initialization code here
            email_account = Util().get_email_account()
            imap_host = email_account.imap_host
            imap_port = email_account.imap_port
            email_user = email_account.email_user
            email_pass = email_account.email_pass

            imap_server = self.connect_imap_server(imap_host, imap_port, email_user, email_pass)

            def run_async_in_thread(target, *args):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(target(*args))
                loop.close()
                
            t = threading.Thread(target=run_async_in_thread, args=(self.monitor_inbox, imap_server,))
            t.start()

        except Exception as e:
            logger.exception(e)
            return HTTPException(status_code=500, detail=str(e))
    

    def connect_imap_server(self, imap_host, imap_port, email_addr, email_pwd):
        imap_server = imaplib.IMAP4_SSL(imap_host, imap_port)
        imap_server.login(email_addr, email_pwd)

        imaplib.Commands['ID'] = ('AUTH')
        args = ("name", "IMAPClient", "contact", f'{email_addr}', "version", "1.0.0", "vendor", "myclient")
        imap_server._simple_command('ID', '("' + '" "'.join(args) + '")')
        imap_server.select()
        logger.debug("Connected to IMAP server!")
        return imap_server    


    def decode_str(self, s:str):
        value, charset = decode_header(s)[0]
        if charset:
            value = value.decode(charset)
        return value

    def get_email_content(self, msg: Message):
        content_type = msg.get('Content-Type', '').lower()
        if content_type.startswith('text/plain') or content_type.startswith('text/html'):
            content = msg.get_content()
            charset = msg.get_charset()
            if charset is None:
                content = self.decode_str(content)
            else:
                content = content.decode(charset)
            return content
        if content_type.startswith('multipart'):
            for part in msg.get_payload():
                ret = self.get_email_content(part)
                if ret:
                    return ret
        return None

    def _media_kind(self, content_type: str) -> str:
        """Return 'image', 'video', 'audio', or 'file' from MIME type."""
        ct = (content_type or "").lower().split(";")[0].strip()
        if ct.startswith("image/"):
            return "image"
        if ct.startswith("video/"):
            return "video"
        if ct.startswith("audio/"):
            return "audio"
        return "file"

    def _extract_attachments_from_message(self, msg: Message):
        """
        Walk email parts and collect attachments (Content-Disposition attachment or inline with filename).
        Returns (images, videos, audios, files) as lists of temp file paths.
        """
        images, videos, audios, files = [], [], [], []
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" not in disp and "inline" not in disp:
                continue
            filename = part.get_filename()
            if not filename:
                continue
            content_type = part.get_content_type() or "application/octet-stream"
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
            except Exception:
                continue
            kind = self._media_kind(content_type)
            ext = Path(filename).suffix or ".bin"
            if kind == "image" and not ext.lower().startswith("."):
                ext = ".jpg"
            try:
                fd, path = tempfile.mkstemp(suffix=ext)
                os.close(fd)
                with open(path, "wb") as f:
                    f.write(payload)
                if kind == "image":
                    images.append(path)
                elif kind == "video":
                    videos.append(path)
                elif kind == "audio":
                    audios.append(path)
                else:
                    files.append(path)
            except Exception as e:
                logger.debug("Email attachment write failed {}: {}", filename, e)
        return images, videos, audios, files

    # Fetch a number of email based on email address and email id.
    async def fetch_email_content(self, mail_server: imaplib, email_id: str):
        """
        Fetch email content based on email id
        """
        _, data = mail_server.fetch(email_id, '(RFC822)')
        if not data or not isinstance(data[0], (list, tuple)) or len(data[0]) < 2:
            return "", "", "", "", [], [], [], []

        def extract_email_address(email_str: str) -> str:
            match = re.search(r'<(.*?)>', email_str)
            if match:
                return match.group(1)
            return email_str

        try:
            msg = email.message_from_bytes(data[0][1], policy=default)
        except Exception as e:
            logger.debug("Email decode failed for id {}: {}", email_id, e)
            return "", "", "", "", [], [], [], []

        # Decode subject, From address and message id
        from_addr = extract_email_address(msg["From"])
        message_id = msg["Message-ID"]
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or 'utf-8', errors='replace')
        body = self.get_email_content(msg) or ""
        try:
            images, videos, audios, files = self._extract_attachments_from_message(msg)
        except Exception as e:
            logger.debug("Email attachment extraction failed: {}", e)
            images, videos, audios, files = [], [], [], []
        return message_id, from_addr, subject, body, images, videos, audios, files
        

    async def monitor_inbox(self, imap_server: imaplib):
        """
        Monitor the inbox change。
        """
        try:
            _, mails = imap_server.search(None, 'ALL')
            last_checked_ids = set(mails[0].split())
            current_ids = set()
            while self.kill == False:
                if imap_server is not None:
                    if len(current_ids) == 0:
                        current_ids = last_checked_ids
                    else:
                        _, mails = imap_server.search(None, 'ALL')
                        current_ids = set(mails[0].split())

                    new_ids = current_ids - last_checked_ids
                    if new_ids:
                        last_checked_ids = current_ids
                        logger.debug("New mail coming")
                        for email_id in new_ids:
                            msg_id, from_addr, subject, body, images, videos, audios, files = await self.fetch_email_content(imap_server, email_id)
                            if not msg_id and not from_addr:
                                continue
                            images = images or []
                            videos = videos or []
                            audios = audios or []
                            files = list(files) if files else None

                            prompt_json = {
                                "MessageID": msg_id,
                                "From": from_addr,
                                "Subject": subject,
                                "Body": body
                            }
                            logger.debug(prompt_json)

                            subject_lower = (subject or "").lower()
                            if subject_lower == '++' or subject_lower == 'store':
                                action = 'store'
                            elif subject_lower == '??' or subject_lower == 'retrieve':
                                action = 'retrieve'
                            else:
                                action = ''
                            prompt = json.dumps(prompt_json)
                            if videos:
                                content_type = ContentType.VIDEO.value
                            elif audios:
                                content_type = ContentType.AUDIO.value
                            elif images:
                                content_type = ContentType.TEXTWITHIMAGE.value
                            else:
                                content_type = ContentType.TEXT.value
                            request = PromptRequest(
                                request_id= msg_id,
                                channel_name= self.metadata.name,
                                request_metadata= {'email': from_addr, 'msgID': msg_id, 'subject': subject},
                                channelType=ChannelType.Email.value,
                                user_name= from_addr.split('@')[0],
                                app_id= 'email',
                                user_id= from_addr,
                                contentType=content_type,
                                text= prompt,
                                action=action,
                                host = self.metadata.host,
                                port = self.metadata.port,
                                images=images,
                                videos=videos,
                                audios=audios,
                                files=files,
                                timestamp= datetime.now().timestamp()
                            )
                            await self.transferTocore(request=request)

                        if self.kill == False:
                            time.sleep(30)
        except Exception as e:
            if e != KeyboardInterrupt:
                logger.exception(e)
                if self.kill == False:
                    self.start_monitoring()
            else:
                sys.exit(0)


    def register_channel(self, name, host, port, endpoints):
       pass


    def deregister_channel(self, name, host, port, endpoints):
       pass


    def stop(self):
        # do some deinitialization here
        logger.debug("Email channel is stopping!")
        try:
            self.kill = True
            if self.server is not None:
                #asyncio.run(Util().stop_uvicorn_server(self.server))
                Util().stop_uvicorn_server(self.server)
        except Exception as e:
            logger.debug(e)


def main():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yml')
    with open(config_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
        #logger.debug(config)
        metadata = ChannelMetadata(**config)

    channel = Channel(metadata=metadata)
    try:
        asyncio.run(channel.run()) # channel.run()
    except Exception as e:
        pass
        #logger.exception(e)
    
if __name__ == "__main__":
    main()



