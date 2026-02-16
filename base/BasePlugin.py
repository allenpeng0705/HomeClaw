
import os
import sys
from typing import Tuple

import yaml
from loguru import logger
from base.base import PromptRequest
from base.util import Util
from core.coreInterface import CoreInterface
def _slug_from_description(description: str) -> str:
    """Generate a stable short id from plugin description (e.g. for routing)."""
    if not description:
        return ""
    # Use first few words lowercased, alphanumeric only
    words = description.lower().split()[:3]
    return "".join(w for w in words if w.isalnum())[:20] or "plugin"


class BasePlugin:
    def __init__(self, coreInst: CoreInterface):
        self.config: dict = None
        self.initialized = False
        self.coreInst = coreInst
        self.user_input = ''
        self.promptRequest: PromptRequest = None
        self.description = ''
        self.plugin_id = ''  # Stable id for routing (from config 'id' or slug of description)
        self.keywords = []
        self.parameters = {}
        self.registration = None  # Set by PluginManager from plugin.yaml (unified registration with capabilities)  

    def initialize(self):
        logger.debug(f"Initializing plugin: {self.config['description']}")
        self.set_description(self.config['description'])
        # Stable id: from config 'id' or slug from description or class name
        raw_id = (self.config.get('id') or '').strip() if self.config else ''
        if raw_id:
            self.plugin_id = raw_id.lower().replace(' ', '_')[:32]
        else:
            self.plugin_id = _slug_from_description(self.description) or (self.__class__.__name__.replace('Plugin', '').lower()[:20])
        #self.set_keywords(self.config['keywords'])
        #self.set_parameters(self.config.get('parameters', {}))


    def get_description(self):
        return self.description
    
    def set_description(self, description):
        self.description = description

    def get_keywords(self):
        return self.keywords
    
    def set_keywords(self, keywords):
        self.keywords = keywords

    def add_keyword(self, keyword):
        self.keywords.append(keyword)

    def remove_keyword(self, keyword):
        self.keywords.remove(keyword)

    def get_parameters(self):
        return self.parameters
  
    def set_parameters(self, parameters):
        self.parameters = parameters

    async def run(self):
        """Override to implement plugin logic. When invoked via orchestrator, self.promptRequest is set; for concurrency-safe reply use coreInst.send_response_for_plugin(response, self.promptRequest) or coreInst.send_response_to_request_channel(response, self.promptRequest)."""
        pass

    async def check_best_plugin(self, text: str) -> Tuple[bool, str]:
        return False, ''

    def cleanup(self):
        if not self.initialized:
            self.initialized = True