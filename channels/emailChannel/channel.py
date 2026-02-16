import asyncio
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
    

    # Fetch a number of email based on email address and email id.
    async def fetch_email_content(self, mail_server: imaplib, email_id: str):
        """
        Fetch email content based on email id
        """
        _, data = mail_server.fetch(email_id, '(RFC822)')

        def extract_email_address(email_str: str) -> str:
            match = re.search(r'<(.*?)>', email_str)
            if match:
                return match.group(1)
            return email_str

        # Decode subject, From address and message id
        msg = email.message_from_bytes(data[0][1], policy=default)
        from_addr = extract_email_address(msg["From"])
        message_id = msg["Message-ID"]
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or 'utf-8', errors='replace')
        body = self.get_email_content(msg)
        return message_id, from_addr, subject, body
        

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
                            msg_id, from_addr, subject, body = await self.fetch_email_content(imap_server, email_id)
                            
                            prompt_json = {
                                "MessageID": msg_id,
                                "From": from_addr,
                                "Subject": subject,
                                "Body": body
                            }
                            logger.debug(prompt_json)

                            subject = subject.lower()
                            if subject == '++' or subject == 'store':
                                action = 'store'
                            elif subject == '??' or subject == 'retrieve':
                                action = 'retrieve'
                            else:
                                action = ''
                            prompt = json.dumps(prompt_json)
                            request = PromptRequest(
                                request_id= msg_id,
                                channel_name= self.metadata.name,
                                request_metadata= {'email': from_addr, 'msgID': msg_id, 'subject': subject},
                                channelType=ChannelType.Email.value,
                                user_name= from_addr.split('@')[0],
                                app_id= 'email',
                                user_id= from_addr,
                                contentType=ContentType.TEXT.value,
                                text= prompt,
                                action=action,
                                host = self.metadata.host,
                                port = self.metadata.port,
                                images=[],
                                videos=[],
                                audios=[],
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



