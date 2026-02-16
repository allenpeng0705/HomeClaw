import asyncio
from datetime import datetime
import time
import os

import re
from threading import Thread
from typing import Tuple
import urllib
import urllib.parse
import urllib.request as request
import urllib.response as response
import urllib.error as error
import json
from email.header import Header

import schedule

from base.BasePlugin import BasePlugin
from loguru import logger
from base.util import Util
from core.coreInterface import CoreInterface

class PartnerPlugin(BasePlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        # Automatically determine the path to the config.yml file
        logger.debug('PartnerPlugin __init__...')
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.yml')
        logger.debug(f'config_path: {config_path}')
        if not os.path.exists(config_path):
            logger.debug(f"Config file does not exist: {config_path}")  # Debugging line
            return
        self.config = Util().load_yml_config(config_path)
        logger.debug(f'PartnerPlugin config: {self.config}')   
        self.last_interaction_time = datetime.now()
        self.idle_duration = self.config['idle_duration'] * 3600  # convert hours to seconds
        self.morning_time = self.config['morning_time']
        self.sleeping_time = self.config['sleeping_time'] 

        # Initialize and start the scheduler
        self.scheduler_thread = Thread(target=self.run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()


    def run_scheduler(self):
        # Schedule the tasks
        schedule.every().day.at(self.morning_time).do(lambda: asyncio.run(self.send_morning_message()))
        schedule.every().day.at(self.sleeping_time).do(lambda: asyncio.run(self.send_sleeping_message()))
        schedule.every(10).minutes.do(lambda: asyncio.run(self.check_and_start_conversation()))

        # Run the scheduler in the background
        while True:
            schedule.run_pending()
            time.sleep(30)
        

    def generate_prompt(self, chat_hist: str, user_input: str = None, time_of_day: str = None) -> str:
            partner_name = self.config['partner_name']
            partner_gender = self.config['partner_gender']
            partner_hobbies = ", ".join(self.config['partner_hobbies'])
            partner_personality = ", ".join(self.config['partner_personality'])
            
            if user_input is None:
                if time_of_day == "morning":
                    additional_context = "It's morning time, and you want to greet the user warmly to start their day positively."
                    example_message = "Good morning! I hope you have a wonderful day ahead."
                elif time_of_day == "night":
                    additional_context = "It's night time, and you want to wish the user a good night with a warm message."
                    example_message = "Good night! Sweet dreams."
                else:
                    additional_context = "It's been a while since you last talked, and you want to start a casual conversation."
                    example_message = "Hey! How's it going? Missed chatting with you. What's new?"
                    
                return f"""
                You are {partner_name}, a caring {partner_gender} partner to the user. You are described as {partner_personality}. {additional_context}

                Keep it casual and friendly, just like you'd talk to a close friend. Be warm and supportive.

                **Context:**

                * Relationship: You've been together for a while and have a strong bond. You've had many fun moments together, like vacations, trying new restaurants, and watching movies.
                * Shared experiences: You both enjoy {partner_hobbies} and love spending time together. You've supported each other through tough times too.
                * Time since last conversation: It's been a while since you last talked, and you're curious about what's been going on in their life.
                * User's emotional state: Guess the user's emotional state based on the chat history and show empathy.

                **Example Message:**
                "{example_message}"

                **Respond as {partner_name}:**

                Start a conversation with the user in a friendly, casual way:

                Chat History:
                {chat_hist}
                """
            else:
                return f"""
                You are {partner_name}, a caring {partner_gender} partner to the user. You are described as {partner_personality}. You're responding to their message: '{user_input}'.

                Keep it casual and friendly, just like you'd talk to a close friend. Be warm and supportive.

                **Context:**

                * Relationship: You've been together for a while and have a strong bond. You've had many fun moments together, like vacations, trying new restaurants, and watching movies.
                * Shared experiences: You both enjoy {partner_hobbies} and love spending time together. You've supported each other through tough times too.
                * User's emotional state: Guess the user's emotional state based on the chat history and their latest message, and show empathy.

                **Examples:**

                * If the user is feeling down: "I'm sorry you're feeling this way. Want to talk about it? I'm here for you."
                * If the user is excited: "That's awesome! Tell me more about it!"
                * If the user is stressed: "I know it's tough right now. Take a deep breath. You've got this."
                * If the user is sharing something neutral: "That sounds interesting! Tell me more."

                **Respond as {partner_name}:**

                Respond to the user's message in a friendly, casual way:

                Chat History:
                {chat_hist}

                Latest User Input:
                {user_input}
                """
            

    async def check_and_start_conversation(self):
        current_time = datetime.now()
        if (current_time - self.last_interaction_time).total_seconds() > self.idle_duration:
            chat_hist = self.coreInst.get_latest_chats_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], num_rounds=10)
            prompt = self.generate_prompt(chat_hist)
            
            # Call OpenAI API with the generated prompt
            resp = await self.coreInst.openai_chat_completion(messages=[{"role": "system", "content": prompt}])
            resp = resp.strip()
            
            if not resp:
                logger.error('PartnerPlugin generate response is empty')
                return
            
            logger.debug(f'PartnerPlugin generate Response: {resp}')
            self.coreInst.add_chat_history_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], sender_text="It's been a while since we last talked.", responder_text=resp)
            await self.coreInst.send_response_to_latest_channel(response=resp)
            logger.debug(f"Sent {resp} to user")

            self.last_interaction_time = current_time

    async def send_morning_message(self):
        chat_hist = self.coreInst.get_latest_chats_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], num_rounds=10)
        prompt = self.generate_prompt(chat_hist, time_of_day="morning")
        
        # Call OpenAI API with the generated prompt
        resp = await self.coreInst.openai_chat_completion(messages=[{"role": "system", "content": prompt}])
        resp = resp.strip()
        
        if not resp:
            logger.error('PartnerPlugin generate response is empty')
            return
        
        logger.debug(f'PartnerPlugin generate Response: {resp}')
        self.coreInst.add_chat_history_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], sender_text="Good morning!", responder_text=resp)
        await self.coreInst.send_response_to_latest_channel(response=resp)
        logger.debug(f"Sent {resp} to user")

    async def send_sleeping_message(self):
        chat_hist = self.coreInst.get_latest_chats_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], num_rounds=10)
        prompt = self.generate_prompt(chat_hist, time_of_day="night")
        
        # Call OpenAI API with the generated prompt
        resp = await self.coreInst.openai_chat_completion(messages=[{"role": "system", "content": prompt}])
        resp = resp.strip()
        
        if not resp:
            logger.error('PartnerPlugin generate response is empty')
            return
        
        logger.debug(f'PartnerPlugin generate Response: {resp}')
        self.coreInst.add_chat_history_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], sender_text="Good night!", responder_text=resp)
        await self.coreInst.send_response_to_latest_channel(response=resp)
        logger.debug(f"Sent {resp} to user")


    async def run(self):
        logger.debug("Running partner plugin")
        chat_hist = self.coreInst.get_latest_chats_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], num_rounds=10)
        user_input = self.promptRequest.text

        # Generate the prompt
        prompt = self.generate_prompt(chat_hist, user_input)
        try:
            # Call OpenAI API with the generated prompt
            resp = await self.coreInst.openai_chat_completion(messages=[{"role": "system", "content": prompt}])
            resp = resp.strip()
            if not resp:
                logger.error('PartnerPlugin generate response is empty')
                return
            logger.debug(f'PartnerPlugin generate Response: {resp}')
            self.coreInst.add_chat_history_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], sender_text=user_input, responder_text=resp)
            await self.coreInst.send_response_to_latest_channel(response=resp)
            logger.debug(f"Sent {resp} to user")

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return
        

    def evaluate_response_prompt(self, chat_hist: str, user_input: str, resp: str) -> str:
        return f"""
        You are an expert conversational AI evaluator. Your task is to evaluate whether the given response is reasonable based on the chat history and the latest user input. Consider the relevance, coherence, empathy, and appropriateness of the response.

        **Chat History**:
        {chat_hist}

        **User Input**:
        {user_input}

        **Response**:
        {resp}

        **Evaluation Criteria**:
        1. Relevance: Is the response relevant to the user's input and the context of the chat history?
        2. Coherence: Is the response logically coherent and easy to understand?
        3. Empathy: Does the response show understanding and empathy towards the user's feelings and situation?
        4. Appropriateness: Is the response appropriate given the user's input and the context of the chat history?

        **Your Task**:
        Based on the criteria above, please determine if the response is reasonable. Return "Yes" if the response is reasonable, and "No" if the response is not reasonable.

        **Result**:
        [Yes/No] (Please fill in based on your evaluation)
        """
        

    async def check_best_plugin(self, text: str) -> Tuple[bool, str]:
        return False, ''
        logger.debug("checking partner plugin")
        chat_hist = self.coreInst.get_latest_chats_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], num_rounds=10)
        user_input = text

        logger.debug(f'check_best_plugin chat_hist: {chat_hist}')
        logger.debug(f'check_best_plugin user_input: {user_input}')

        # Generate the prompt
        prompt = self.generate_prompt(chat_hist, user_input)
        try:
            # Call OpenAI API with the generated prompt
            resp = await self.coreInst.openai_chat_completion(messages=[{"role": "system", "content": prompt}])
            resp = resp.strip()
            if not resp:
                logger.error('PartnerPlugin generate response is empty')
                return False, ''
            logger.debug(f'PartnerPlugin generate Response: {resp}')

            prompt = self.evaluate_response_prompt(chat_hist=chat_hist, user_input=user_input, resp=resp)
            eval_resp = await self.coreInst.openai_chat_completion(messages=[{"role": "system", "content": prompt}])
            eval_resp = eval_resp.strip()
            if not eval_resp:
                logger.error('PartnerPlugin evaluate response is empty')
                return False, ''
            logger.debug(f'PartnerPlugin evaluate Response: {eval_resp}')
            if "Yes" in eval_resp or "yes" in eval_resp:
                self.coreInst.add_chat_history_by_role(sender_name=self.promptRequest.user_name, responder_name=self.config['partner_name'], sender_text=user_input, responder_text=resp)
                await self.coreInst.send_response_to_latest_channel(response=resp)
                logger.debug(f"Sent {resp} to user")                
                return True, resp
            else:
                return False, ''


        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return False, ''


    def initialize(self):
        if self.initialized:
            return
        logger.debug("Initializing Partner plugin")
        super().initialize()
        self.initialized = True