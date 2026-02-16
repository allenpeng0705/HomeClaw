import json
import os
from typing import Dict, List, Optional

import httpx
from base.util import Util
from memory.base import LLMBase
from loguru import logger

class LlamaCppLLM(LLMBase):
    def __init__(self):
        super().__init__()
                

    def _parse_response(self, resp, tools):
        """
        Process the response based on whether tools are used or not.

        Args:
            response: The raw response from API.
            tools: The list of tools provided in the request.

        Returns:
            str or dict: The processed response.
        """
        # Check if response is a bytes object and decode it
        #logger.debug(f"instance type before decoding: {type(resp)}")
        #if isinstance(resp, bytes):
        #    resp = resp.decode('utf-8')
        #logger.debug(f"instance type after decoding: {type(resp)}")

        # Decode JSON string to a dictionary
        try:
            resp_json = json.loads(resp)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {"error": "Invalid JSON format."}

         # Check if response is a string again, indicating double-encoded JSON
        if isinstance(resp_json, str):
            try:
                resp_json = json.loads(resp_json)
            except json.JSONDecodeError as e:
                logger.error(f"Second JSON decode error: {e}")
                return {"error": "Invalid JSON format after second decoding."}

        # Check if 'choices' exists in the response
        if 'choices' not in resp_json:
            logger.error("The response does not contain 'choices'.")
            return {"error": "Invalid response format. 'choices' not found."}

        choices = resp_json.get('choices', [])
        if not choices:
            logger.error("The 'choices' list is empty.")
            return {"error": "Invalid response format. 'choices' list is empty."}

        # Access the first choice's message content
        first_choice = choices[0]
        message = first_choice.get('message', {})
        content = message.get('content', "")
        if tools:
            processed_response = {
                "content": content,
                "tool_calls": [],
            }

            tool_calls = message.get('tool_calls', [])
            if tool_calls is not None:
                for tool_call in tool_calls:
                    processed_response["tool_calls"].append(
                        {
                            "name": tool_call['function']['name'],
                            "arguments": json.loads(tool_call['function']['arguments']),
                        }
                    )

            return processed_response
        else:
            return content

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        grammar: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        functions: Optional[List] = None,
        function_call: Optional[str] = None
    ):
        """
        Generate a response based on the given messages using OpenAI.

        Args:
            messages (list): List of message dicts containing 'role' and 'content'.
            response_format (str or object, optional): Format of the response. Defaults to "text".
            tools (list, optional): List of tools that the model can call. Defaults to None.
            tool_choice (str, optional): Tool choice method. Defaults to "auto".

        Returns:
            str: The generated response.
        """
        # sync call using httpx
        async with httpx.AsyncClient() as client:  
            response = await Util().openai_chat_completion(messages=messages, grammar=grammar, tools=tools, tool_choice=tool_choice, functions=functions, function_call=function_call)
        return self._parse_response(response.content.decode('utf-8'), tools)
