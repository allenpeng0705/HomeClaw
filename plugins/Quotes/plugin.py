import asyncio
import os
from base.SchedulerPlugin import SchedulerPlugin
from loguru import logger

from base.base import PromptRequest
from base.util import Util
from core.coreInterface import CoreInterface
from memory.chat.message import ChatMessage

class QuotePlugin(SchedulerPlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        self.prompt =  """
                        You are an expert at summarizing chat histories and generating motivational quotes based on the conversation.

                        Guidelines:
                        1. Read through the provided chat history.
                        2. Summarize the main points of the conversation in a concise manner.
                        3. Generate an insightful and relevant motivational quote based on the summarized information.

                        Chat History:
                        {chat_history}

                        Motivational Quote:
                        """
        # Automatically determine the path to the config.yml file
        logger.debug('QuotePlugin __init__...')
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.yml')
        logger.debug(f'config_path: {config_path}')
        if not os.path.exists(config_path):
            logger.debug(f"Config file does not exist: {config_path}")  # Debugging line
            return
        self.config = Util().load_yml_config(config_path) 
        logger.debug(f'QuotePlugin config: {self.config}')   


    def format_chat_history(self, chat_messages: list[ChatMessage]) -> str:
        if not chat_messages:
            return ""
        chat_history_str = ""
        for chat in chat_messages:
            if chat.human_message:
                chat_history_str += f"Human: {chat.human_message.content}\n"
            if chat.ai_message:
                chat_history_str += f"AI: {chat.ai_message.content}\n"
        return chat_history_str

    def create_prompt(self, chat_messages: list[ChatMessage]) -> str:
        chat_history = self.format_chat_history(chat_messages)
        return self.prompt.format(chat_history=chat_history)

    async def generate_random_quote(self):
        app_id, user_name, user_id = self.coreInst.get_latest_chat_info()
        if app_id is None or user_id is None or user_name is None:
            return
        hist = self.coreInst.get_latest_chats(app_id=app_id, user_name=user_name, user_id=user_id, num_rounds=10)
        logger.debug(f'QuotePlugin generate_random_quote Chat history: {hist}')
        text = ""
        if len(hist) > 0:
            text = Util().convert_chats_to_text(hist)
            text = await Util().llm_summarize(text)
        prompt = self.prompt.format(chat_history=text)
        #prompt = self.create_prompt(text)
        if self.coreInst:
            logger.debug(f'QuotePlugin generate_random_quote Prompt: {prompt}')
        messages = []
        if not messages or messages[0]["role"] != "system":
            messages = [{"role": "system", "content": prompt}]

        resp = await Util().openai_chat_completion(messages)
        resp = resp.strip()
        if not resp:
            logger.error('QuotePlugin generate_random_quote response is empty')
            return
        logger.debug(f'QuotePlugin generate_random_quote Response: {resp}')
        await self.coreInst.send_response_to_latest_channel(response=resp)
        logger.debug(f"Sent {resp} to user")



    async def run(self):
        await self.generate_random_quote()

    def initialize(self):
        if self.initialized:
            return
        logger.debug("Initializing Quotes plugin")
        super().initialize()
        self.initialized = True