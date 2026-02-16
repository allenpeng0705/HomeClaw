from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Dict, List, Tuple, Optional
from base.base import PromptRequest, ChannelType, ContentType
from memory.chat.message import ChatMessage

class CoreInterface(ABC):

    @abstractmethod
    def check_permission(self, user_name: str, user_id: str, channel_type: ChannelType, content_type: ContentType) -> bool:
        pass

    @abstractmethod
    def get_latest_chat_info(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        pass

    @abstractmethod
    def get_latest_chats(self, app_id: str, user_name: str, user_id: str, num_rounds: int)-> List[ChatMessage]:
        pass

    @abstractmethod
    def get_latest_chats_by_role(self, sender_name: str, responder_name: str, num_rounds: int, timestamp=None)-> List[ChatMessage]:
        pass

    @abstractmethod
    def add_chat_history_by_role(self, sender_name: str, responder_name: str, sender_text: str, responder_text: str):
        pass
    
    @abstractmethod
    def add_chat_history(self, user_message: str, ai_message: str, app_id: Optional[str] = None, user_name: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None):
        pass

    @abstractmethod
    async def openai_chat_completion(self, messages: list[dict], 
                                     grammar: str=None,
                                     tools: Optional[List[Dict]] = None,
                                     tool_choice: str = "auto", 
                                     llm_name: str = None) -> str | None:  
        pass

    @abstractmethod
    async def send_response_to_latest_channel(self, response: str):
        pass
    
    @abstractmethod
    async def send_response_to_request_channel(self, response: str, request: PromptRequest):
        pass
    
    
    @abstractmethod
    async def add_user_input_to_memory(self, user_input:str, user_name: Optional[str] = None, user_id: Optional[str] = None, agent_id: Optional[str] = None, run_id: Optional[str] = None, metadata: Optional[dict] = None, filters: Optional[dict] = None):
        pass
    
    @abstractmethod
    def get_session_id(self, app_id, user_name=None, user_id=None, channel_name=None, account_id=None, validity_period=timedelta(hours=24)):
        pass
    
    @abstractmethod
    def get_run_id(self, agent_id, user_name=None, user_id=None, validity_period=timedelta(hours=24)):
        pass

    def get_session_transcript(
        self,
        app_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
        fetch_all: bool = False,
    ) -> list:
        """Return session transcript as list of {role, content, timestamp}. Optional on interface for tool layer."""
        return []