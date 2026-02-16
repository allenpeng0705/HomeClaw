import asyncio
from email.mime.text import MIMEText
import os

import re
import smtplib
import urllib
import urllib.parse
import urllib.request as request
import urllib.response as response
import urllib.error as error
import json
from email.header import Header

from base.BasePlugin import BasePlugin
from loguru import logger
from base.util import Util
from core.coreInterface import CoreInterface

class MailPlugin(BasePlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        # Automatically determine the path to the config.yml file
        logger.debug('MailPlugin __init__...')
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.yml')
        logger.debug(f'config_path: {config_path}')
        if not os.path.exists(config_path):
            logger.debug(f"Config file does not exist: {config_path}")  # Debugging line
            return
        self.config = Util().load_yml_config(config_path)
        logger.debug(f'MailPlugin config: {self.config}')      

    def send_email(self, send_to, subject, body):
        if not re.match(r"[^@]+@[^@]+\.[^@]+", send_to):
            raise ValueError("Invalid email address: %s" % send_to)

        smtp_host = self.config['smtp_host']
        smtp_port = self.config['smtp_port']
        email_user = self.config['email_user']
        email_pass = self.config['email_pass']
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
        

    def generate_email_prompt(self, chat_hist: str, user_input: str) -> str:
        contacts = self.config['contacts']
        contact_str = '\n'.join([f"{contact['name']} ({contact['email']})" for contact in contacts])

        return f"""
        You are an AI assistant. Based on the following chat history and the latest user input, extract the necessary information to send an email. The extracted information should include the email address (send_to), email subject, and email body.

        If the email address is not explicitly provided in the chat history or user input, select the most appropriate email address from the following contacts:

        {contact_str}

        If you cannot guarantee the target contact, keep asking the user for more details.

        Chat History:
        {chat_hist}

        Latest User Input:
        {user_input}

        Please provide the information in the following JSON format:
        {{
            "send_to": "recipient@example.com",
            "subject": "Email Subject",
            "body": "Email body content"
        }}

        Examples:

        Chat History:
        User: Hi, can you send an email to john.doe@example.com about the meeting?
        AI: Sure, what should be the subject and body of the email?
        User: The subject should be "Meeting Reminder" and the body should include the details of the meeting scheduled for tomorrow at 10 AM.

        Latest User Input:
        Please send the email now.

        Output:
        {{
            "send_to": "john.doe@example.com",
            "subject": "Meeting Reminder",
            "body": "The meeting is scheduled for tomorrow at 10 AM."
        }}

        Chat History:
        User: Can you contact jane.doe@example.com and tell her about the project update?
        AI: Sure, what should be the subject and body of the email?
        User: The subject should be "Project Update" and the body should include the latest progress report.

        Latest User Input:
        Send the email as discussed.

        Output:
        {{
            "send_to": "jane.doe@example.com",
            "subject": "Project Update",
            "body": "The latest progress report is as follows..."
        }}

        Chat History:
        User: Hi, I need to send an email to Jane about the meeting details.
        AI: Sure, what should be the subject and body of the email?
        User: The subject should be "Meeting Details" and the body should include the agenda for the meeting.

        Latest User Input:
        Please go ahead and send it.

        Output:
        {{
            "send_to": "jane.doe@example.com",
            "subject": "Meeting Details",
            "body": "The agenda for the meeting is as follows..."
        }}

        Chat History:
        User: Can you inform John about the deadlines?
        AI: Sure, what should be the subject and body of the email?
        User: The subject should be "Project Deadlines" and the body should detail the upcoming deadlines.

        Latest User Input:
        Please send the email now.

        Output:
        {{
            "send_to": "john.doe@example.com",
            "subject": "Project Deadlines",
            "body": "The upcoming deadlines are as follows..."
        }}

        Chat History:
        User: Hi, I need you to send an email about the meeting details.
        AI: Sure, who should I send it to?
        User: Send it to Jane.
        AI: What should be the subject and body of the email?
        User: The subject should be "Meeting Details" and the body should include the agenda for the meeting.

        Latest User Input:
        Please go ahead and send it.

        Output:
        {{
            "send_to": "jane.doe@example.com",
            "subject": "Meeting Details",
            "body": "The agenda for the meeting is as follows..."
        }}

        Chat History:
        User: Can you inform someone about the project deadlines?
        AI: Sure, who should I inform?
        User: Inform John.
        AI: What should be the subject and body of the email?
        User: The subject should be "Project Deadlines" and the body should detail the upcoming deadlines.

        Latest User Input:
        Please send the email now.

        Output:
        {{
            "send_to": "john.doe@example.com",
            "subject": "Project Deadlines",
            "body": "The upcoming deadlines are as follows..."
        }}
        """
        

    async def run(self):
        logger.debug("Running Email plugin")
        uid = getattr(self.promptRequest, 'system_user_id', None) or self.promptRequest.user_id
        chat_hist = self.coreInst.get_latest_chats(app_id=self.promptRequest.app_id, user_name=self.promptRequest.user_name, user_id=uid, num_rounds=10)
        user_input = self.user_input

        # Generate the prompt
        prompt = self.generate_email_prompt(chat_hist, user_input)
        try:
            # Call OpenAI API with the generated prompt
            response = await self.coreInst.openai_chat_completion(messages=[{"role": "system", "content": prompt}])
            response_data = json.loads(response)
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return
        
        session_id = self.coreInst.get_session_id(app_id=self.promptRequest.app_id, user_name=self.promptRequest.user_name, user_id=uid)
        self.coreInst.add_chat_history(user_message=user_input, ai_message=response, app_id=self.promptRequest.app_id, user_name=self.promptRequest.user_name, user_id=uid, session_id=session_id)
        run_id = self.coreInst.get_run_id(agent_id=self.promptRequest.app_id, user_name=self.promptRequest.user_name, user_id=uid)
        self.coreInst.add_user_input_to_memory(user_input, user_name=self.promptRequest.user_name, user_id=uid, run_id=run_id)

        # Check if any information is missing and handle follow-up questions
        missing_info = []
        if not response_data.get("send_to"):
            missing_info.append("send_to")
        if not response_data.get("subject"):
            missing_info.append("subject")
        if not response_data.get("body"):
            missing_info.append("body")

        if missing_info:
            follow_up_prompt = f"""
            It seems some information is missing: {', '.join(missing_info)}.
            Please provide the missing information.
            Chat History:
            {chat_hist}
            
            Latest User Input:
            {user_input}

            Follow-Up Questions:
            """
            follow_up_response = await self.coreInst.openai_chat_completion(messages=[{"role": "system", "content": follow_up_prompt}])
            follow_up_data = json.loads(follow_up_response)

            # Merge follow-up data with the initial response data
            response_data.update(follow_up_data)


        # Attempt to select the most appropriate email address from the contacts if not provided
        if not response_data.get("send_to"):
            potential_contacts = [contact for contact in self.config['contacts'] if contact['name'].lower() in chat_hist.lower()]
            if len(potential_contacts) == 1:
                response_data['send_to'] = potential_contacts[0]['email']
            else:
                raise ValueError("Cannot determine the correct email address. Need more information.")

        self.send_email(send_to=response_data['send_to'], subject=response_data['subject'], body=response_data['body'])
        # Send confirmation to the user so they see a reply in the channel
        self.coreInst.send_response_to_request_channel(
            f"Email sent to {response_data['send_to']} with subject \"{response_data['subject']}\".",
            self.promptRequest,
        )


    def initialize(self):
        if self.initialized:
            return
        logger.debug("Initializing Mail plugin")
        super().initialize()
        self.initialized = True