"""
Quotes plugin: generate motivational quotes from chat history. Extends BasePlugin only.
Scheduling (e.g. daily quote) is done via cron_schedule(task_type='run_plugin', plugin_id='quotes').
"""
import asyncio
import logging
import os

from base.BasePlugin import BasePlugin
from base.util import Util
from core.coreInterface import CoreInterface

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)

_PROMPT = """
You are an expert at summarizing chat histories and generating motivational quotes based on the conversation.

Guidelines:
1. Read through the provided chat history.
2. Summarize the main points of the conversation in a concise manner.
3. Generate an insightful and relevant motivational quote based on the summarized information.

Chat History:
{chat_history}

Motivational Quote:
"""


class QuotePlugin(BasePlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        self.prompt = _PROMPT
        self.config = {}
        try:
            config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.yml")
            if os.path.exists(config_path):
                self.config = Util().load_yml_config(config_path) or {}
        except Exception as e:
            logger.debug("Quotes plugin config load: {}", e)

    def initialize(self):
        if self.initialized:
            return
        try:
            super().initialize()
            self.initialized = True
        except Exception as e:
            logger.debug("Quotes plugin initialize: {}", e)
            self.initialized = True

    async def generate_random_quote(self) -> str:
        """Generate a quote from latest chat history and return text. Never raises."""
        try:
            app_id, user_name, user_id = self.coreInst.get_latest_chat_info()
            if not app_id or not user_id:
                return "No recent chat to generate a quote from."
            hist = self.coreInst.get_latest_chats(app_id=app_id, user_name=user_name or "", user_id=user_id, num_rounds=10)
            text = ""
            if hist:
                try:
                    text = Util().convert_chats_to_text(hist)
                    if text:
                        text = await Util().llm_summarize(text)
                except Exception as e:
                    logger.debug("Quotes summarize: {}", e)
            prompt = self.prompt.format(chat_history=text or "(no content)")
            messages = [{"role": "system", "content": prompt}]
            resp = await Util().openai_chat_completion(messages)
            if not resp or not isinstance(resp, str):
                return "Could not generate a quote."
            resp = resp.strip()
            if not resp:
                return "Quote response was empty."
            return resp
        except Exception as e:
            logger.exception("Quotes generate_random_quote: {}", e)
            return f"Error generating quote: {e!s}"

    async def run(self) -> str:
        """Generate and return a quote. Core sends the result to the user."""
        try:
            quote = await self.generate_random_quote()
            if quote and not quote.startswith("Error"):
                try:
                    await self.coreInst.send_response_to_latest_channel(response=quote)
                except Exception as send_err:
                    logger.debug("Quotes send_response: {}", send_err)
            return quote or "(no output)"
        except Exception as e:
            logger.exception("Quotes run: {}", e)
            return f"Error: {e!s}"
