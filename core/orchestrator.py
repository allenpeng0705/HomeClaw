import asyncio
import json
import re
from datetime import datetime
from itertools import count
from typing import List, Dict, Optional, Tuple, Any
from loguru import logger
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from base.base import IntentType, Intent, PromptRequest
from base.prompt_manager import get_prompt_manager
from base.util import Util
from core.coreInterface import CoreInterface
from core.tam import TAM

class Orchestrator:
    """
    Classifies user intent (TIME vs OTHER). For TIME, delegates to TAM to analyze and schedule
    (reminder or cron). Time scheduling can also be done via tools (cron_schedule, cron_list)
    when use_tools is enabled—see TAM module docstring for the two paths.
    """
    def __init__(self, coreInst: CoreInterface):
        self.coreInst = coreInst  # This should be an instance of the core's LLM
        self.tam = TAM(coreInst)
        self.tam.run()
        #asyncio.run(self.tam.start_intent_queue_handler()) #self.tam.start_intent_queue_handler()
        #self.intents = []

    def _create_prompt_fallback(self, text: str, chat_history: str) -> str:
        """Fallback when use_prompt_manager is false or config/prompts/orchestrator/intent not found."""
        return f"""
            You are an expert at understanding user intentions based on chat history and user input. Use the provided chat history and user input to determine the user's intent and classify it as either TIME or OTHER. Consider the entire chat history, as the intent might change based on multiple rounds of conversation.

            Guidelines:
            1. Use the provided chat history and user input to determine the user's intent.
            2. Ensure the intent classification is accurate, concise, and directly addresses the user's query.
            3. If the intent is related to scheduling or time-based events (like reminders, repeated events, or upcoming significant events), classify the intent type as TIME.
            4. For non-time-related intents, classify the intent type as OTHER.
            5. Recognize implicit time references (e.g., "Please remind me every 10 minutes", "Please call me in 5 minutes", "I have a meeting with Gary next Monday", "There are 10 days left in the US presidential election").
            6. Also classify as TIME when the user asks for cron-style or recurring schedules: "every day at 9am", "daily at 9", "every Monday at 10", "every hour", "remind me at 8am every morning", "post at 9am daily". These will be handled by the time/scheduling module (TAM).
            7. If the first round of conversation does not provide enough time-related information, classify it as OTHER and wait for further rounds.
            8. If the user input or chat history contains time-related words but the context is not about scheduling, reminders, or significant events, classify it as OTHER.

            Provide the JSON object in the following format:
            {{ "type": "TIME | OTHER" }}

            Chat History:
            {chat_history}

            User Input:
            {text}

            Determine the user's intent and create a JSON object:
        """

    def create_prompt(self, text: str, chat_history: str) -> str:
        meta = Util().get_core_metadata()
        if getattr(meta, "use_prompt_manager", False):
            try:
                pm = get_prompt_manager(
                    prompts_dir=getattr(meta, "prompts_dir", None),
                    default_language=getattr(meta, "prompt_default_language", "en"),
                    cache_ttl_seconds=float(getattr(meta, "prompt_cache_ttl_seconds", 0) or 0),
                )
                lang = getattr(meta, "main_llm_language", "en") or "en"
                content = pm.get_content("orchestrator", "intent", lang=lang, text=text, chat_history=chat_history or "")
                if content and content.strip():
                    return content.strip()
            except Exception as e:
                logger.debug("Orchestrator prompt manager fallback: %s", e)
        return self._create_prompt_fallback(text, chat_history)
    
    def get_hist_chats(self, request: PromptRequest) -> str:
        user_id_for_storage = getattr(request, 'system_user_id', None) or request.user_id
        hist = self.coreInst.get_latest_chats(app_id=request.app_id, user_name=request.user_name, user_id=user_id_for_storage, num_rounds=10)
        return Util().convert_chats_to_text(hist)

    async def translate_to_intent(self, request: PromptRequest) -> Intent:
        # Combine the input text and chat history into a single context
        text = request.text
        hist = self.get_hist_chats(request)
        logger.debug(f'Orchestrator get Chat history: {hist}')
        if hist is not None and len(hist) > 0:
            hist = await Util().llm_summarize(hist, 4096)
        else:
            hist = ""
        prompt = self.create_prompt(text, hist)
        logger.debug(f'Orchestrator Prompt: {prompt}')       
        messages = [{"role": "system", "content": prompt}]
        intent_str = await Util().openai_chat_completion(messages)
        if not intent_str:
            logger.error('Orchestrator response is empty')
            return None
        intent_str = intent_str.strip()
        logger.debug(f'Orchestrator got intent: {intent_str}')
        # Process the intent string to create an Intent object
        intent = await self.process_intent(hist, text, intent_str, request)
        #self.intents.append(intent)
        
        return intent
    

    def _parse_intent_type(self, intent_str: str) -> IntentType:
        """Extract intent type from LLM output. Expects JSON like {"type": "TIME"} or {"type": "OTHER"}. Default OTHER."""
        s = (intent_str or "").strip()
        if not s:
            return IntentType.OTHER
        # Try to find a JSON object (first {...})
        match = re.search(r'\{[^{}]*\}', s)
        if match:
            try:
                obj = json.loads(match.group(0))
                t = (obj.get("type") or "").strip().upper()
                if t == "TIME":
                    return IntentType.TIME
                return IntentType.OTHER
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: legacy string check
        if '"type": "time"' in s.lower() or "'type': 'time'" in s.lower():
            return IntentType.TIME
        return IntentType.OTHER

    async def process_intent(self, chatHistory: str, text: str, intent_str: str, request: PromptRequest) -> Intent:
        intent_type = self._parse_intent_type(intent_str)
        intent = Intent(
            type=intent_type,
            text=text,
            intent_text=(intent_str or "").strip(),
            timestamp=datetime.now().timestamp(),
            chatHistory=chatHistory,
        )
        if intent_type == IntentType.TIME:
            await self.tam.process_intent(intent, request)
        logger.debug(
            f"Orchestrator got intent: {intent.type} {intent.text} {intent.intent_text} {intent.timestamp} {intent.chatHistory}"
        )
        return intent

    @staticmethod
    def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
        """
        Extract a single JSON object from LLM output. Handles markdown code blocks,
        nested braces, and trailing commas. Returns None if no valid object found.
        """
        if not raw or not raw.strip():
            return None
        s = raw.strip()
        # Strip markdown code blocks (```json ... ``` or ``` ... ```)
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.IGNORECASE)
        if code_block:
            s = code_block.group(1).strip()
        # Find balanced {...} (handles nested braces)
        start = s.find("{")
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = s[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        try:
                            # Allow trailing commas for leniency
                            normalized = re.sub(r",\s*([}\]])", r"\1", candidate)
                            return json.loads(normalized)
                        except json.JSONDecodeError:
                            pass
                    break
        # Fallback: first {...} with no nested braces
        match = re.search(r"\{[^{}]*\}", s)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _normalize_plugin_ref(plug_val: Any, plugin_infos: List[Dict[str, Any]]) -> Optional[Any]:
        """
        Normalize plugin ref from LLM: int/float -> 1-based index (validated), str -> id slug.
        Returns None for invalid or out-of-range values.
        """
        if plug_val is None or plug_val == "" or str(plug_val).strip().lower() in ("null", "none"):
            return None
        n = len(plugin_infos)
        if n == 0:
            return None
        # Numeric: treat as 1-based index
        if isinstance(plug_val, (int, float)):
            idx = int(plug_val)
            if 1 <= idx <= n:
                return idx
            return None
        # String: could be id or numeric string (e.g. "1")
        s = str(plug_val).strip().lower().replace(" ", "_")
        if not s:
            return None
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= n:
                return idx
            return None
        return s

    def _create_combined_intent_and_plugin_fallback(self, text: str, chat_history: str, plugin_infos: List[Dict[str, Any]]) -> str:
        """Fallback when use_prompt_manager is false or config prompt not found."""
        if not plugin_infos:
            return self.create_prompt(text, chat_history)
        lines = []
        for i, p in enumerate(plugin_infos):
            pid = (p.get("id") or "").strip() or f"plugin_{i + 1}"
            desc = (p.get("description") or "")[:200]
            lines.append(f"  {i + 1}. id: \"{pid}\", description: {desc}")
        plugin_list = "\n".join(lines)
        first_id = (plugin_infos[0].get("id") or "").strip() or "plugin_1"
        return f"""You are an expert at understanding user intentions and routing to the right handler.

Task:
1. Classify intent as TIME (scheduling, reminders, cron) or OTHER.
2. If OTHER, choose the best matching plugin by its id or by number (1-based), or use null if no plugin fits.

Output exactly one JSON object, no markdown, no explanation:
{{ "type": "TIME" | "OTHER", "plugin": <string id or number 1-{len(plugin_infos)} or null> }}

Rules:
- TIME: reminders, "every day at 9am", "in 5 minutes", cron. Always use "type": "TIME", "plugin": null.
- OTHER + match: use "plugin": "id" (e.g. "{first_id}") or "plugin": 1 (number = line number above).
- OTHER + no match: general chat. Use "type": "OTHER", "plugin": null.

Available plugins (use id or number 1-{len(plugin_infos)}):
{plugin_list}

Chat History:
{chat_history or "(none)"}

User Input:
{text}

Reply with only the JSON object:"""

    def create_combined_intent_and_plugin_prompt(self, text: str, chat_history: str, plugin_infos: List[Dict[str, Any]]) -> str:
        """Single-call prompt: output type (TIME/OTHER) and plugin (id or index or null)."""
        if not plugin_infos:
            return self.create_prompt(text, chat_history)
        meta = Util().get_core_metadata()
        if getattr(meta, "use_prompt_manager", False):
            try:
                pm = get_prompt_manager(
                    prompts_dir=getattr(meta, "prompts_dir", None),
                    default_language=getattr(meta, "prompt_default_language", "en"),
                    cache_ttl_seconds=float(getattr(meta, "prompt_cache_ttl_seconds", 0) or 0),
                )
                lang = getattr(meta, "main_llm_language", "en") or "en"
                lines = []
                for i, p in enumerate(plugin_infos):
                    pid = (p.get("id") or "").strip() or f"plugin_{i + 1}"
                    desc = (p.get("description") or "")[:200]
                    lines.append(f"  {i + 1}. id: \"{pid}\", description: {desc}")
                plugin_list = "\n".join(lines)
                first_plugin_id = (plugin_infos[0].get("id") or "").strip() or "plugin_1"
                content = pm.get_content(
                    "orchestrator", "intent_and_plugin", lang=lang,
                    plugin_list=plugin_list, plugin_count=len(plugin_infos),
                    first_plugin_id=first_plugin_id, chat_history=chat_history or "(none)", text=text,
                )
                if content and content.strip():
                    return content.strip()
            except Exception as e:
                logger.debug("Orchestrator combined prompt manager fallback: %s", e)
        return self._create_combined_intent_and_plugin_fallback(text, chat_history, plugin_infos)

    async def translate_to_intent_and_plugin(
        self, request: PromptRequest, plugin_infos: List[Dict[str, Any]]
    ) -> Tuple[Optional["Intent"], Any]:
        """
        Single LLM call: classify intent and optionally select plugin. Returns (Intent, plugin_id or plugin_index or None).
        plugin_infos: list of {"id": str, "description": str} (index is implicit 0-based).
        Uses robust JSON extraction and plugin_ref normalization/validation.
        """
        text = (request.text or "").strip()
        hist = self.get_hist_chats(request)
        logger.debug("Orchestrator get Chat history (combined): %s", (hist or "")[:200])
        if hist and len(hist) > 0:
            hist = await Util().llm_summarize(hist, 4096)
        else:
            hist = ""
        if not plugin_infos:
            intent = await self.translate_to_intent(request)
            return (intent, None)
        prompt = self.create_combined_intent_and_plugin_prompt(text, hist, plugin_infos)
        messages = [{"role": "system", "content": prompt}]
        raw = await Util().openai_chat_completion(messages)
        if not raw or not raw.strip():
            logger.error("Orchestrator combined response is empty")
            return (None, None)
        raw = raw.strip()
        logger.debug("Orchestrator combined response: %s", raw[:300])
        obj = self._extract_json_object(raw)
        if obj is None:
            logger.warning("Orchestrator combined: no valid JSON found in response, falling back to intent-only")
            intent = await self.process_intent(hist, text, raw, request)
            return (intent, None)
        try:
            t = (obj.get("type") or "").strip().upper()
            intent_type = IntentType.TIME if t == "TIME" else IntentType.OTHER
            plug_val = obj.get("plugin")
            plugin_ref = self._normalize_plugin_ref(plug_val, plugin_infos)
            intent = Intent(
                type=intent_type,
                text=text,
                intent_text=raw,
                timestamp=datetime.now().timestamp(),
                chatHistory=hist,
            )
            if intent_type == IntentType.TIME:
                await self.tam.process_intent(intent, request)
            logger.debug("Orchestrator combined parsed: type=%s plugin_ref=%s", intent_type, plugin_ref)
            return (intent, plugin_ref)
        except Exception as e:
            logger.warning("Orchestrator combined parse failed: %s, falling back to intent-only", e)
            intent = await self.translate_to_intent(request)
            return (intent, None)