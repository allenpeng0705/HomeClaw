import copy
from datetime import datetime
from enum import Enum
import json
import logging
import os
from typing import List, Dict, Optional, Union
import uuid
from pydantic import BaseModel, Field
import uvicorn
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Any
    
class ChannelType(Enum):
    """Enum representing different communication channels."""
    Email = "EMAIL"
    SMS = "SMS"
    Phone = "PHONE"
    IM = "IM"

    @classmethod
    def list(cls):
        """Returns a list of all channel types."""
        return list(map(lambda c: c.value, cls))

class ContentType(Enum):
    """Enum representing different content types."""
    TEXT = "TEXT"
    TEXTWITHIMAGE = "TEXTWITHIMAGE"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    HTML = "HTML"
    OTHER = "OTHER"

    @classmethod
    def list(cls):
        """Returns a list of all content types."""
        return list(map(lambda c: c.value, cls))
      

class PromptRequest(BaseModel):
    request_id: str
    channel_name: str
    request_metadata: dict
    channelType: ChannelType
    user_name: str
    app_id: str
    user_id: str  # Channel identity: email, IM id, phone (used for permission match and reply delivery)
    contentType: ContentType
    system_user_id: Optional[str] = None  # Our system user id (from user.yml id/name); used for all storage when set
    friend_id: Optional[str] = None  # Which friend this conversation is with (e.g. "HomeClaw", "Sabrina"). Channels use "HomeClaw"; Companion sends from client. Default "HomeClaw" when not set.
    text: str
    action: str
    host: str
    port: int  
    images: List[str] # only for TEXTWITHIMAGE and IMAGE, the value is path with name of the images
    videos: List[str] # only for VIDEO, the value is path with the name of videos
    audios: List[str] # only for AUDIO, the value is path with the name of audios
    files: Optional[List[str]] = None  # optional: list of file paths; Core runs file-understanding (detect type, handle image/audio/video/doc)
    timestamp: float


class InboundRequest(BaseModel):
    """Minimal payload for POST /inbound so any bot can talk to the Core without building a full channel."""
    user_id: str = "companion"  # e.g. telegram chat_id, discord user id; default for companion/apps that don't send it
    friend_id: Optional[str] = None  # Which friend this conversation is with (e.g. "HomeClaw", "Sabrina"). Omitted or empty → "HomeClaw".
    text: str  # required; use "See attached." etc. when sending only media
    channel_name: Optional[str] = "webhook"
    user_name: Optional[str] = None  # display name; defaults to user_id if omitted
    app_id: Optional[str] = None  # agent id for memory/scoping; Core uses "homeclaw" when omitted
    action: Optional[str] = "respond"
    # Companion/assistant disambiguation: when client sends conversation_type=companion or session_id=companion, Core routes to companion plugin only (see docs_design/CompanionFeatureDesign.md).
    session_id: Optional[str] = None
    conversation_type: Optional[str] = None
    # For multimodal: list of data URLs (data:...;base64,...) or paths Core can read
    images: Optional[List[str]] = None
    videos: Optional[List[str]] = None
    audios: Optional[List[str]] = None
    # Optional file paths (Core must be able to read) or data URLs; Core runs file-understanding
    files: Optional[List[str]] = None
    # Optional location (e.g. from Companion/WebChat/browser when user grants permission); Core stores as latest per user and injects into system context
    location: Optional[str] = None
    # When true, POST /inbound returns Server-Sent Events (SSE) with progress messages during long tasks (e.g. "Generating your PPT...") then a final event with the result. Clients can show progress instead of a static loading state.
    stream: Optional[bool] = False
    # When true, POST /inbound returns immediately with 202 and request_id; Core processes in background. Client polls GET /inbound/result?request_id=... until status is "done". Use when proxy (e.g. Cloudflare) closes the connection before the response completes.
    async_mode: Optional[bool] = Field(False, alias="async")
    # When set with async: true, Core pushes the result to the WebSocket that registered this session_id (see /ws "connected" event). Companion opens /ws, gets session_id, then POST /inbound with async + push_ws_session_id so Core can push the reply directly instead of polling.
    push_ws_session_id: Optional[str] = None

class IntentType(Enum):
    TIME = "TIME"
    OTHER = "OTHER"

class Intent:
    def __init__(self, type: IntentType, text: str, intent_text: str, timestamp: float, chatHistory: str):
        self.type = type
        self.text = text
        self.intent_text = intent_text
        self.timestamp = timestamp
        self.chatHistory = chatHistory
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Intent':
        return cls(
            type=data.get('type'),
            text=data.get('text'),
            intent_text=data.get('intent_text'),
            timestamp=data.get('timestamp'),
            chatHistory = ''
        )

    def to_json(self) -> str:
        return json.dumps(self.__dict__)

    def from_json(cls, data: str) -> 'Intent':
        return cls.from_dict(json.loads(data))
    
    
class AsyncResponse(BaseModel):
    request_id: str
    host: str
    port: int
    from_channel: str
    request_metadata: Dict
    response_data: Dict


class PluginRequest(BaseModel):
    """Standard request payload for external plugins (subprocess/http/mcp)."""
    request_id: str
    plugin_id: str
    user_input: str
    user_id: str = ""
    user_name: str = ""
    channel_name: str = ""
    channel_type: str = ""
    app_id: str = ""
    chat_context: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)
    capability_id: Optional[str] = None
    capability_parameters: Optional[Dict[str, Any]] = None


class PluginResult(BaseModel):
    """Standard result from external plugins (subprocess stdout or HTTP response body)."""
    request_id: str = ""
    plugin_id: str = ""
    success: bool = True
    text: str = ""
    error: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)


class PluginCapabilityParam(BaseModel):
    """Parameter for one plugin capability (function or REST API). Same for built-in and external. See docs/PluginParameterCollection.md."""
    name: str
    type: str = "string"  # string, number, boolean, object, array
    required: bool = True
    default: Optional[Union[str, int, float, bool, Dict, List]] = None
    description: Optional[str] = None
    profile_key: Optional[str] = None   # Map to user profile key; executor fills from profile when missing
    config_key: Optional[str] = None   # Map to config default_parameters key
    confirm_if_uncertain: Optional[bool] = None   # When value from profile/config, confirm with user before use


class PluginCapability(BaseModel):
    """
    One capability: a function (built-in) or REST API (external).
    post_process: if True, Core runs LLM on output (optional post_process_prompt) before sending to channel; else send directly.
    """
    id: str
    name: str
    description: Optional[str] = None
    parameters: List[PluginCapabilityParam] = Field(default_factory=list)
    output_description: Optional[str] = None
    post_process: bool = False
    post_process_prompt: Optional[str] = None
    method: Optional[str] = None   # for external REST API, e.g. GET, POST
    path: Optional[str] = None     # for external REST API, relative to base_url


class PluginRegistration(BaseModel):
    """Unified registration descriptor (same for built-in and external). See docs/PluginRegistration.md."""
    id: str
    name: str
    description: str
    description_long: Optional[str] = None
    capabilities: List[PluginCapability] = Field(default_factory=list)
    source: Optional[str] = None  # "built-in" | "external"; set by Core
    health_check_url: Optional[str] = None  # required for external
    type: Optional[str] = None    # http, subprocess, mcp; external only
    config: Dict = Field(default_factory=dict)  # external only


class PluginToolParam(BaseModel):
    """Parameter definition for a plugin tool/API (unified for built-in and external)."""
    name: str
    type: str = "string"  # string, number, boolean, object, array
    required: bool = True
    default: Optional[Union[str, int, float, bool, Dict, List]] = None
    description: Optional[str] = None


class ResponseExtraction(BaseModel):
    """How Core extracts the reply text from a plugin response."""
    field: Optional[str] = None   # JSON key, e.g. "text" or "message"
    json_path: Optional[str] = None  # e.g. "$.result.message"


class PluginToolDefinition(BaseModel):
    """Tool/API definition: what the plugin exposes, params, and how to get the result."""
    id: str
    name: str
    description: Optional[str] = None
    method: Optional[str] = "POST"
    path: Optional[str] = None
    url_template: Optional[str] = None
    parameters: List[PluginToolParam] = Field(default_factory=list)
    response_extraction: Optional[ResponseExtraction] = None


class PluginLLMGenerateRequest(BaseModel):
    """Request body for POST /api/plugins/llm/generate. Lets external plugins (or any authorised caller) use Core's LLM. See docs_design/PluginLLMAndQueueDesign.md."""
    messages: List[Dict[str, Any]]  # e.g. [{"role": "user", "content": "..."}] or content as list for multimodal
    llm_name: Optional[str] = None  # optional model key from config; None = main LLM


class ExternalPluginRegisterRequest(BaseModel):
    """Request body for POST /api/plugins/register (external plugins only). Same schema as PluginRegistration + capabilities. See docs/PluginRegistration.md."""
    plugin_id: str
    name: str
    description: str
    description_long: Optional[str] = None
    health_check_url: str
    type: str  # http, subprocess, mcp
    config: Dict = Field(default_factory=dict)
    capabilities: Optional[List[PluginCapability]] = None  # required for unified registration
    tools: Optional[List[PluginToolDefinition]] = None     # legacy; prefer capabilities
    # Optional: UIs this plugin provides (dashboard, webchat, control, tui, custom). See docs_design/PluginUIsAndHomeClawControlUI.md.
    ui: Optional[Dict[str, Any]] = None  # e.g. { "dashboard": "http://...", "webchat": "http://...", "control": "http://...", "tui": "npx ...", "custom": [{ "id": "...", "name": "...", "url": "..." }] }


@dataclass
class Friend:
    """One friend in a user's friends list. name = friend_id (used in paths and storage)."""
    name: str  # required; display name and friend_id (sanitized for paths)
    relation: Optional[Union[str, List[str]]] = None  # e.g. girlfriend, friend, or [friend]
    who: Optional[Dict[str, Any]] = None  # persona: description, gender, roles, personalities, language, response_length
    identity: Optional[str] = None  # None = do not read file; "" or "identity.md" = default file; "other.md" = that filename in friend root
    preset: Optional[str] = None  # optional: name of friend preset (e.g. "reminder", "note", "finder"); when set, Core applies preset config for tools/skills/plugins/memory. See docs_design/FriendConfigFrameworkImplementation.md.


@dataclass
class User:
    name: str
    email: List[str] = field(default_factory=list)
    im: List[str] = field(default_factory=list)
    phone: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    # Unique system user id for all storage (chat, memory, KB, profile). If omitted in yaml, defaults to name.
    id: Optional[str] = None
    # Optional: for Companion login. If present, used with password to authenticate.
    username: Optional[str] = None
    password: Optional[str] = None
    # Optional: API keys for keyed skills (maton-api-gateway, x-api, meta-social, hootsuite). If missing for a user, that skill is not available. Keys: maton_api_key, x_access_token, meta_access_token, hootsuite_access_token.
    skill_api_keys: Optional[Dict[str, str]] = None
    # User type: "normal" (can use channels, combine with companion app) or "companion" (dedicated to companion app / webchat / control UI only; no channels). Default "normal".
    type: str = "normal"
    # Optional identity/persona for companion-type users. Dict: description (free-text summary), gender, roles, personalities, language, response_length; idle_days_before_nudge is reserved for future proactive nudge (not injected). Used to build a system-prompt section so the model behaves as this identity; no LLM call for injection.
    who: Optional[Dict[str, Any]] = None
    # Friends list for this user. First friend must be HomeClaw (system); then named friends. Loaded from user.yml; if missing, defaults to [HomeClaw].
    friends: Optional[List['Friend']] = None

    @staticmethod
    def from_yaml(yaml_file: str) -> List['User']:
        """Load users from user.yml. Never raises: on any error returns [] so Core never crashes."""
        try:
            with open(yaml_file, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        raw_list = data.get('users')
        if not isinstance(raw_list, list):
            return []
        users = []
        for i, u in enumerate(raw_list):
            if not isinstance(u, dict):
                continue
            try:
                name = (u.get('name') or '').strip() or f"user_{i}"
                uid = (u.get('id') or u.get('name') or name).strip() or name
                email = u.get('email')
                im = u.get('im')
                phone = u.get('phone')
                permissions = u.get('permissions')
                if not isinstance(email, list):
                    email = []
                if not isinstance(im, list):
                    im = []
                if not isinstance(phone, list):
                    phone = []
                if not isinstance(permissions, list):
                    permissions = []
                raw_keys = u.get('skill_api_keys')
                skill_api_keys = None
                if isinstance(raw_keys, dict):
                    try:
                        skill_api_keys = {
                            str(k).strip(): str(v).strip()
                            for k, v in raw_keys.items()
                            if k and v and str(v).strip()
                        }
                        if not skill_api_keys:
                            skill_api_keys = None
                    except Exception:
                        skill_api_keys = None
                user_type = str(u.get('type') or 'normal').strip().lower() or 'normal'
                if user_type not in ('normal', 'companion'):
                    user_type = 'normal'
                who = u.get('who')
                if not isinstance(who, dict):
                    who = None
                username = (u.get('username') or '').strip() or None
                if not username:
                    username = None
                password = u.get('password')
                if password is not None and not isinstance(password, str):
                    password = str(password)
                if password is not None and not (password or '').strip():
                    password = None
                friends = User._parse_friends(u.get('friends'))
                users.append(User(
                    name=name,
                    email=email,
                    im=im,
                    phone=phone,
                    permissions=permissions,
                    id=uid,
                    username=username,
                    password=password,
                    skill_api_keys=skill_api_keys,
                    type=user_type,
                    who=who,
                    friends=friends,
                ))
            except Exception:
                continue
        return users

    @staticmethod
    def _parse_friends(raw: Any) -> List['Friend']:
        """Parse friends list from user.yml. Never raises; returns at least [Friend(name='HomeClaw')] if empty/missing. Ensures HomeClaw is first."""
        result: List[Friend] = []
        if not isinstance(raw, list):
            raw = []
        for idx, f in enumerate(raw):
            if not isinstance(f, dict):
                continue
            try:
                fname = (f.get('name') or '').strip()
                if not fname:
                    continue
                relation = f.get('relation')
                fwho = f.get('who')
                if not isinstance(fwho, dict):
                    fwho = None
                ident_raw = f.get('identity')
                if ident_raw is None:
                    identity = None
                elif isinstance(ident_raw, bool):
                    identity = 'identity.md' if ident_raw else None
                elif isinstance(ident_raw, str):
                    ident_s = ident_raw.strip()
                    identity = ident_s if ident_s else 'identity.md'
                else:
                    identity = None
                preset_raw = f.get('preset')
                if preset_raw is not None and isinstance(preset_raw, str):
                    preset = (preset_raw or "").strip() or None
                else:
                    preset = None
                result.append(Friend(name=fname, relation=relation, who=fwho, identity=identity, preset=preset))
            except Exception:
                continue
        if not result:
            return [Friend(name='HomeClaw', relation=None, who=None, identity=None, preset=None)]
        first_name = (result[0].name or '').strip().lower()
        if first_name != 'homeclaw':
            result.insert(0, Friend(name='HomeClaw', relation=None, who=None, identity=None, preset=None))
        return result

    @staticmethod
    def _friends_to_dict_list(friends: List['Friend']) -> List[Dict[str, Any]]:
        """Serialize friends to list of dicts for YAML. Never raises."""
        out = []
        for f in friends:
            if not isinstance(f, Friend):
                continue
            try:
                entry = {"name": (getattr(f, "name", None) or "").strip() or "Friend"}
                if getattr(f, "relation", None) is not None:
                    entry["relation"] = f.relation
                if isinstance(getattr(f, "who", None), dict) and f.who:
                    entry["who"] = f.who
                ident = getattr(f, "identity", None)
                if ident is not None and str(ident).strip():
                    entry["identity"] = str(ident).strip()
                preset_val = getattr(f, "preset", None)
                if preset_val is not None and str(preset_val).strip():
                    entry["preset"] = str(preset_val).strip()
                out.append(entry)
            except Exception:
                continue
        return out

    @staticmethod
    def to_yaml(users: List['User'], yaml_file: str) -> None:
        """Write users to user.yml; preserve comments and other keys. Never raises: logs and returns on write failure."""
        users_data = []
        for user in users:
            try:
                d = {
                    "name": getattr(user, "name", "") or "",
                    "email": list(getattr(user, "email", None) or []),
                    "im": list(getattr(user, "im", None) or []),
                    "phone": list(getattr(user, "phone", None) or []),
                    "permissions": list(getattr(user, "permissions", None) or []),
                    "id": getattr(user, "id", None) or getattr(user, "name", ""),
                    "type": str(getattr(user, "type", None) or "normal").strip().lower() or "normal",
                }
                username = getattr(user, "username", None)
                if username is not None and str(username).strip():
                    d["username"] = str(username).strip()
                password = getattr(user, "password", None)
                if password is not None and str(password).strip():
                    d["password"] = str(password)
                keys = getattr(user, "skill_api_keys", None)
                if isinstance(keys, dict) and keys:
                    d["skill_api_keys"] = {str(k): str(v) for k, v in keys.items() if k and v}
                who = getattr(user, "who", None)
                if isinstance(who, dict) and who:
                    d["who"] = who
                friends = getattr(user, "friends", None)
                if isinstance(friends, list) and friends:
                    d["friends"] = User._friends_to_dict_list(friends)
                users_data.append(d)
            except Exception:
                continue
        try:
            from ruamel.yaml import YAML
            yaml_rt = YAML()
            yaml_rt.preserve_quotes = True
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml_rt.load(f)
            if data is not None:
                data['users'] = users_data
                with open(yaml_file, 'w', encoding='utf-8') as f:
                    yaml_rt.dump(data, f)
                return
        except Exception:
            pass
        try:
            with open(yaml_file, 'w', encoding='utf-8') as file:
                yaml.safe_dump({'users': users_data}, file, default_flow_style=False, sort_keys=False)
        except Exception:
            pass

    @staticmethod
    def validate_no_overlapping_channel_ids(users: List['User']) -> None:
        """Raise ValueError if two users share the same email/im/phone (we require distinct channel ids per user)."""
        seen_email: Dict[str, str] = {}
        seen_im: Dict[str, str] = {}
        seen_phone: Dict[str, str] = {}
        for user in users:
            uid = user.id or user.name
            for e in (user.email or []):
                if e in seen_email and seen_email[e] != uid:
                    raise ValueError(f"user.yml: email '{e}' is used by more than one user (must be unique per user)")
                seen_email[e] = uid
            for i in (user.im or []):
                if i in seen_im and seen_im[i] != uid:
                    raise ValueError(f"user.yml: im '{i}' is used by more than one user (must be unique per user)")
                seen_im[i] = uid
            for p in (user.phone or []):
                if p in seen_phone and seen_phone[p] != uid:
                    raise ValueError(f"user.yml: phone '{p}' is used by more than one user (must be unique per user)")
                seen_phone[p] = uid


class EmailAccount:
    def __init__(self, imap_host: str, imap_port: int, smtp_host: str, smtp_port: int, email_user: str, email_pass: str):
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.email_user = email_user
        self.email_pass = email_pass

    @classmethod
    def from_yaml(cls, filepath: str):
        with open(filepath, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
            account_data = data['EmailAccount']
            return cls(**account_data)

    def to_yaml(self, filepath: str):
        """Serializes the account data to a YAML file."""
        account_data = {
            'EmailAccount': {
                'imap_host': self.imap_host,
                'imap_port': self.imap_port,
                'smtp_host': self.smtp_host,
                'smtp_port': self.smtp_port,
                'email_user': self.email_user,
                'email_pass': self.email_pass,
            }
        }
        with open(filepath, 'w', encoding='utf-8') as file:
            yaml.dump(account_data, file, default_flow_style=False)

            
# Supported models            
# https://github.com/BerriAI/litellm/blob/57f37f743886a0249f630a6792d49dffc2c5d9b7/model_prices_and_context_window.json#L835            
class ChatRequest(BaseModel):
    model: str
    # OpenAI-style messages: list of {role, content}; content can be str or list of parts (text, image_url, input_audio, etc.)
    messages: List[Any] = []
    extra_body: Dict[str, Union[str, int, float, dict, list]] = None
    timeout: Union[float, int, None] = None
    temperature: Union[float, None] = None
    top_p: Union[float, None] = None
    n: Union[int, None] = None
    stream: Union[bool, None] = None
    stream_options: Union[Dict[str, Union[str, int, float, dict, list]], None] = None
    max_tokens: Union[int, None] = 2048
    presence_penalty: Union[float, None] = None
    frequency_penalty: Union[float, None] = None
    logit_bias: Union[Dict[str, Union[str, int, float, dict, list]], None] = None
    user: Union[str, None] = None
    response_format: Union[Dict[str, Union[str, int, float, dict, list]], None] = None
    seed: Union[int, None] = None
    tools: Union[List, None] = None
    tool_choice: Union[str, None] = None
    parallel_tool_calls: Union[bool, None] = None
    logprobs: Union[bool, None] = None
    top_logprobs: Union[int, None] = None
    # soon to be deprecated params by OpenAI
    functions: Union[List, None] = None
    function_call: Union[str, None] = None
    # set api_base, api_version, api_key
    base_url: Union[str, None] = None
    api_version: Union[str, None] = None
    api_key: Union[str, None] = None

    
    
class EmbeddingRequest(BaseModel):
    model: str
    input: list[str]
    '''
    Cohere v3 Models have a required parameter: input_type, it can be one of the following four values:

    input_type="search_document": (default) Use this for texts (documents) you want to store in your vector database
    input_type="search_query": Use this for search queries to find the most relevant documents in your vector database
    input_type="classification": Use this if you use the embeddings as an input for a classification system
    input_type="clustering": Use this if you use the embeddings for text clustering
    '''
    dimensions: int | None = None
    timeout: int = 600
    input_type: Optional[str] = None
    api_base: Optional[str] = None,
    api_version: Optional[str] = None,
    api_key: Optional[str] = None
    api_type: str | None = None
    
    
class ImageGenerationRequest(BaseModel):
    model: str  #The model to use for image generation. Defaults to openai/dall-e-2
    prompt: str
    n: Optional[int] = None  # number of images (1-10; dall-e-3 only n=1)
    quality: Optional[str] = None  # hd for finer quality
    response_format: Optional[str] = None  # url or b64_json
    size: Optional[str] = None  # 256x256, 512x512, 1024x1024 (dall-e-2); 1024x1024, 1792x1024, 1024x1792 (dall-e-3)
    style: Optional[str] = None
    timeout: Optional[int] = 600  # max seconds to wait
    api_key: Optional[str] = None, #The API key to authenticate and authorize requests. If not provided, the default API key is used.
    api_base: Optional[str] = None, #The api endpoint you want to call the model with
    api_version: Optional[str] = None #(Azure-specific) the api version for the call; required for dall-e-3 on Azure
    

@dataclass
class LLM:
    name: str
    type: str
    alias: str
    path: str
    description: str
    languages: List[str]
    introduction: str
    capabilities: List[str]
    host: str
    port: int
    parameters: Dict[str, Any]

    @staticmethod
    def from_yaml(yaml_file: str) -> List['LLM']:
        with open(yaml_file, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        
        llms = []
        for name, details in data['llms'].items():
            llms.append(LLM(name=name, **details))
        
        return llms

    @staticmethod
    def to_yaml(llms: List['LLM'], yaml_file: str):
        with open(yaml_file, 'w', encoding='utf-8') as file:
            llms_dict = {'llms': {llm.name: llm.__dict__ for llm in llms}}
            for llm in llms_dict['llms'].values():
                llm.pop('name')
            yaml.safe_dump(llms_dict, file)
    
'''
class EndPoint(BaseModel):
    path: str
    method: str
    description: str
    capabilities: List[str]
    input: Dict[str, str]
    output: Dict[str, str]


class VectorDB(BaseModel):
    host: str
    port: int
    api: str
    path: str
    persist_path: str
    is_persistent: bool
    anonymized_telemetry: bool
'''

import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class Database:
    """Relational DB: sqlite (default), mysql, postgresql. url empty for sqlite = default path."""
    backend: str = "sqlite"
    url: str = ""

@dataclass
class Chroma:
    host: str = "0.0.0.0"
    port: int = 5000
    api: str = "chromadb.api.fastapi.FastAPI"
    is_persistent: bool = True
    anonymized_telemetry: bool = False
    path: str = ""

@dataclass
class Qdrant:
    host: str = "localhost"
    port: int = 6333
    url: str = ""
    api_key: str = ""

@dataclass
class Milvus:
    host: str = "localhost"
    port: int = 19530
    uri: str = ""

@dataclass
class Pinecone:
    api_key: str = ""
    environment: str = ""
    index_name: str = "memory"

@dataclass
class Weaviate:
    url: str = "http://localhost:8080"
    api_key: str = ""

@dataclass
class Kuzu:
    """Graph store: file-based, no extra service. path empty = use app data_path/graph_kuzu."""
    path: str = ""

@dataclass
class Neo4jConfig:
    """Graph store: Neo4j server (enterprise / multi-process)."""
    url: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = ""

@dataclass
class GraphDB:
    """Graph DB: kuzu (default, file-based) or neo4j."""
    backend: str = "kuzu"
    Kuzu: Kuzu = field(default_factory=lambda: Kuzu())
    Neo4j: Neo4jConfig = field(default_factory=lambda: Neo4jConfig())

@dataclass
class VectorDB:
    backend: str = "chroma"
    Chroma: Chroma = field(default_factory=lambda: Chroma())
    Qdrant: Qdrant = field(default_factory=lambda: Qdrant())
    Milvus: Milvus = field(default_factory=lambda: Milvus())
    Pinecone: Pinecone = field(default_factory=lambda: Pinecone())
    Weaviate: Weaviate = field(default_factory=lambda: Weaviate())

@dataclass
class Endpoint:
    path: str
    method: str
    description: str
    capabilities: List[str]
    input: Dict[str, Any]
    output: Dict[str, Any]


def _get_gpu_count() -> int:
    """Return number of CUDA GPUs (0 if CPU-only). Uses torch if installed, else nvidia-smi. Used only for default concurrency; never raises."""
    try:
        import torch
        n = getattr(torch.cuda, 'device_count', lambda: 0)()
        return int(n) if n is not None else 0
    except Exception:
        pass
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return 0
        lines = (result.stdout or b"").decode().strip().splitlines()
        return len([l for l in lines if l.strip()]) if lines else 0
    except Exception:
        return 0


def _default_llm_max_concurrent_local() -> int:
    """Default for llm_max_concurrent_local when not in config: 1 for CPU or 1 GPU; min(gpu_count, 4) for 2+ GPUs."""
    n = _get_gpu_count()
    if n <= 1:
        return 1
    return min(n, 4)


def _default_llm_max_concurrent_cloud(main_llm_mode: Any) -> int:
    """Default for llm_max_concurrent_cloud when not in config: 4 for mix; 6 for cloud-only; 2 for local-only. Never raises."""
    try:
        mode = str(main_llm_mode or "").strip().lower()
    except Exception:
        return 4
    if mode == "cloud":
        return 6
    if mode == "local":
        return 2
    return 4  # mix or empty


def _normalize_llm_max_concurrent(raw: Any) -> int:
    """Normalize llm_max_concurrent_local/cloud: clamp to 1–32; invalid/missing → default from caller."""
    try:
        v = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        return 1
    if v == 0:
        return 0
    return max(1, min(32, v))


def _normalize_file_view_link_expiry(raw: Any) -> int:
    """Normalize file_view_link_expiry_sec: seconds (int or '7d' style); default 7 days; clamp 1 to 365 days."""
    _default = 7 * 86400
    _max_sec = 365 * 86400
    if raw is None:
        return _default
    if isinstance(raw, str):
        s = (raw or "").strip().lower()
        if not s:
            return _default
        if s.endswith("d"):
            try:
                days = int(s[:-1])
                return max(1, min(_max_sec, days * 86400))
            except ValueError:
                return _default
        try:
            return max(1, min(_max_sec, int(s)))
        except ValueError:
            return _default
    try:
        return max(1, min(_max_sec, int(raw)))
    except (TypeError, ValueError):
        return _default


def _normalize_main_llm_language(raw: Union[str, List[str], None]) -> List[str]:
    """Normalize main_llm_language config to List[str]. Accepts string (e.g. 'en') or list (e.g. [zh, en]). Default ['en']."""
    if raw is None:
        return ["en"]
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip()]
        return out if out else ["en"]
    s = str(raw).strip() or "en"
    return [s]


@dataclass
class CoreMetadata:
    name: str
    host: str
    port: int
    mode: str
    model_path: str
    embedding_llm: str
    embedding_host: str
    embedding_port: int
    embedding_health_check_timeout_sec: int  # seconds to wait for embedding server; default 120
    embedding_llm_type: str
    main_llm: str
    main_llm_host: str
    main_llm_port: int
    main_llm_type: str
    # Response languages: list of allowed/preferred languages (e.g. [zh, en]). First = primary (prompt file loading) and default when user language unknown. See config/core.yml main_llm_language comment.
    main_llm_language: List[str]
    main_llm_api_key_name: str
    main_llm_api_key: str
    silent: bool
    log_to_console: bool  # when False, all logs go only to file (no stdout); use with tail to monitor logs
    use_memory: bool
    memory_backend: str  # cognee (default) | chroma (in-house RAG)
    database: Database
    vectorDB: VectorDB
    graphDB: GraphDB
    memory_check_before_add: bool = False  # when True, for small/local models run an extra LLM call to gate what gets added to RAG memory; default False = store every message, rely on retrieval quality
    default_location: str = ""  # optional; fallback location when no request/profile location (e.g. "New York, US"); see SystemContextDateTimeAndLocation.md
    cognee: Dict[str, Any] = field(default_factory=dict)  # optional; when set, applied as Cognee env before Cognee loads (see docs/MemoryAndDatabase.md)
    endpoints: List[Endpoint] = field(default_factory=list)
    llama_cpp: Dict[str, Any] = field(default_factory=dict)
    completion: Dict[str, Any] = field(default_factory=dict)  # max_tokens, temperature for chat completion (overrides llama_cpp when set)
    local_models: List[Dict[str, Any]] = field(default_factory=list)   # [{ id, path, host, port, alias?, capabilities? }]
    cloud_models: List[Dict[str, Any]] = field(default_factory=list)    # [{ id, path, host, port, api_key_name?, capabilities? }]
    use_workspace_bootstrap: bool = True  # inject config/workspace (IDENTITY.md, AGENTS.md, TOOLS.md) into system prompt
    workspace_dir: str = "config/workspace"  # which workspace dir to load (e.g. config/workspace_day vs config/workspace_night for day/night agents)
    # Root for file/folder tools and links (share + per-user + companion). Empty or missing = same as workspace_dir. Required conceptually; when unset we fall back to workspace_dir.
    homeclaw_root: str = ""
    use_agent_memory_file: bool = True  # inject AGENT_MEMORY.md (curated long-term memory); default true when missing. See SessionAndDualMemoryDesign.md
    agent_memory_path: str = ""  # empty = workspace_dir/AGENT_MEMORY.md; default "" when missing
    agent_memory_max_chars: int = 20000  # max chars to inject; default 20k when missing. 0 = no truncation. When > 0, only last N chars; see MemoryFilesUsage.md
    use_daily_memory: bool = True  # inject memory/YYYY-MM-DD.md for today + yesterday; default true when missing. See SessionAndDualMemoryDesign.md
    daily_memory_dir: str = ""  # empty = workspace_dir/memory when missing; or path relative to project (e.g. database/daily_memory)
    use_agent_memory_search: bool = True  # when True (default), inject capped bootstrap (OpenClaw-style) + tools; set false for legacy bulk inject only
    agent_memory_vector_collection: str = "homeclaw_agent_memory"  # Chroma collection for agent memory chunks
    agent_memory_bootstrap_max_chars: int = 20000  # max chars for agent+daily bootstrap block (default/cloud); over cap = head 70% + tail 20% + marker
    agent_memory_bootstrap_max_chars_local: int = 8000  # when request uses local model (mix mode); smaller cap for small context
    session: Dict[str, Any] = field(default_factory=dict)  # prune_keep_last_n, prune_after_turn, daily_reset_at_hour, idle_minutes, api_enabled
    compaction: Dict[str, Any] = field(default_factory=dict)  # enabled, reserve_tokens, max_messages_before_compact, compact_tool_results
    use_tools: bool = True   # always on; kept for optional override. Tool layer (tool registry, execute tool_calls in chat loop).
    use_skills: bool = True  # always on; kept for optional override. Inject skills (SKILL.md from skills_dir) into system prompt.
    skills_dir: str = "skills"  # directory to scan for skill folders (each with SKILL.md); project root, same level as plugin
    skills_extra_dirs: List[str] = field(default_factory=list)  # optional extra dirs (paths relative to project root); user can put more skills here
    skills_disabled: List[str] = field(default_factory=list)  # folder names to not load (e.g. ["x-api-1.0.0"]); case-insensitive match
    skills_max_in_prompt: int = 5  # when skills_use_vector_search=true, cap RAG results to this many in prompt; when false (include all) this is not used
    plugins_max_in_prompt: int = 5  # when plugins_use_vector_search=true, cap RAG results to this many; when false (include all) this is not used
    plugins_use_vector_search: bool = False  # default: load all plugins; when True, use vector store and RAG to pick top-N
    plugins_vector_collection: str = "homeclaw_plugins"  # Chroma collection when plugins_use_vector_search
    plugins_description_max_chars: int = 0  # max chars per plugin description in routing block; 0 = no truncation. With RAG or plugins_max_in_prompt we already cap how many plugins appear; this only limits per-item length. Use 0 (default) for full descriptions; set 512 or 300 only if you need to shrink prompt or cap one very long description.
    # Vector retrieval for skills (separate collection from memory); see docs/ToolsSkillsPlugins.md §8
    skills_use_vector_search: bool = False  # when True, retrieve skills by similarity to user query instead of injecting all/first N
    skills_vector_collection: str = "homeclaw_skills"  # Chroma collection name for skills (separate from memory)
    skills_max_retrieved: int = 10  # max skills to retrieve and inject per request when skills_use_vector_search
    skills_similarity_threshold: float = 0.0  # min similarity (0..1); results below are dropped (similarity = 1 - distance for cosine)
    skills_refresh_on_startup: bool = True  # resync skills_dir → vector DB on Core startup when skills_use_vector_search
    skills_test_dir: str = ""  # optional; if set, full sync every time (id = test__<folder>); for testing skills
    skills_incremental_sync: bool = False  # when true, skills_dir only processes folders not already in vector store (new only)
    # Optional: for these skill folders, include SKILL.md body (and USAGE.md if present) in the prompt so the model can answer "how do I use this?". List of folder names.
    skills_include_body_for: List[str] = field(default_factory=list)
    # When > 0, cap the body for skills in skills_include_body_for to this many chars (avoids blowing up context). 0 = no truncation.
    skills_include_body_max_chars: int = 0
    # Optional: when user query matches a regex, ensure these skill folders are in the prompt and optionally append an instruction. List of { pattern: str, folders: [str], instruction?: str }.
    skills_force_include_rules: List[Dict[str, Any]] = field(default_factory=list)
    # Optional: when user query matches a regex, ensure these plugin ids are in the routing block and optionally append an instruction. List of { pattern: str, plugins: [str], instruction?: str }.
    plugins_force_include_rules: List[Dict[str, Any]] = field(default_factory=list)
    # Optional: path to a YAML file (relative to config dir) with skills_*, plugins_*, system_plugins* keys. When set, those keys are loaded from that file and core.yml stays short.
    skills_and_plugins_config_file: str = field(default='')
    # Optional: path to a YAML file (relative to config dir) with memory, knowledge_base, database, vectorDB, graphDB, cognee, profile, file_understanding. When set, those keys are loaded from that file.
    memory_kb_config_file: str = field(default='')
    # Optional: path to a YAML file (relative to config dir) with local_models, cloud_models, main_llm*, hybrid_router, embedding_llm, embedding_host/port, main_llm_host/port. When set, those keys are loaded from that file.
    llm_config_file: str = field(default='')
    # Optional extra dirs to scan for manifest-based external plugins (http/subprocess/mcp). Paths relative to project root or absolute. Python plugins are not loaded from here.
    plugins_extra_dirs: List[str] = field(default_factory=list)
    orchestrator_timeout_seconds: int = 60  # timeout for intent/plugin call and plugin.run() when unified is false; 0 = no timeout. Default when missing: 60.
    tool_timeout_seconds: int = 120  # per-tool execution timeout; prevents one tool from hanging the system; 0 = no timeout (from config tools.tool_timeout_seconds)
    tools_config: Dict[str, Any] = field(default_factory=dict)  # merged tools dict from core.yml + optional skills_and_plugins file; used by tool layer (exec_allowlist, web.search, etc.)
    orchestrator_unified_with_tools: bool = True  # when True (default), main LLM with tools routes TAM/plugin/chat; when False, separate orchestrator_handler runs first (one LLM for intent+plugin)
    inbound_request_timeout_seconds: int = 0  # recommended max seconds for clients/proxies waiting for Core; 0 = unlimited. Default when missing: 0. Not enforced by Core; set proxies read_timeout >= this when >0.
    use_prompt_manager: bool = True  # load prompts from config/prompts (language/model overrides); see docs/PromptManagement.md
    prompts_dir: str = "config/prompts"  # base dir for section/name.lang.model layout
    prompt_default_language: str = "en"  # fallback when lang not in request/metadata
    prompt_cache_ttl_seconds: float = 0  # 0 = cache by mtime only; >0 = TTL in seconds
    auth_enabled: bool = False  # when True, require API key for /inbound and /ws; see RemoteAccess.md
    auth_api_key: str = ""  # key to require (X-API-Key header or Authorization: Bearer <key>); also used to sign file links when core_public_url is set
    core_public_url: str = ""  # public URL that reaches Core (e.g. https://homeclaw.example.com). Used for file/report links: core_public_url/files/out?path=...&token=...
    # File link style: "token" = signed /files/out?token=... (default); "static" = direct URL under web server doc root so link = core_public_url/file_static_prefix/scope/path (e.g. /files/AllenPeng/images/ID1.jpg). When static, set web server doc root (www_root) to homeclaw_root and alias file_static_prefix to it so all sandbox files are served.
    file_link_style: str = "token"  # "token" | "static"
    file_static_prefix: str = "files"  # URL path prefix when file_link_style is static (e.g. "files" → /files/scope/path)
    file_view_link_expiry_sec: int = 7 * 86400  # how long file/view links (token) are valid, in seconds; default 7 days; max 365 days
    llm_max_concurrent_local: int = 1   # max concurrent local (llama.cpp) calls; 1 = typical for single GPU/process; see PluginLLMAndQueueDesign.md
    llm_max_concurrent_cloud: int = 4   # max concurrent cloud (LiteLLM) calls; 2–10 for parallel channel + plugin under provider RPM/TPM
    knowledge_base: Dict[str, Any] = field(default_factory=dict)  # optional: enabled, collection_name, chunk_size, unused_ttl_days, folder_sync (enabled, folder_name, schedule, allowed_extensions, max_file_size_bytes, resync_on_mtime_change); see docs/MemoryAndDatabase.md and PerUserKnowledgeBaseFolder.md
    profile: Dict[str, Any] = field(default_factory=dict)  # optional: enabled, dir (base path for profiles); see docs/UserProfileDesign.md
    result_viewer: Dict[str, Any] = field(default_factory=dict)  # deprecated; kept for backward compat when loading old config. File serving uses core_public_url + GET /files/out.
    # When true, Core starts and registers all (or allowlisted) plugins in system_plugins/ so one command runs Core + system plugins.
    system_plugins_auto_start: bool = False
    system_plugins: List[str] = field(default_factory=list)  # optional allowlist; empty = start all discovered system plugins
    system_plugins_env: Dict[str, Dict[str, str]] = field(default_factory=dict)  # per-plugin env: plugin_id -> { VAR: "value" }; e.g. homeclaw-browser: { BROWSER_HEADLESS: "false" }
    system_plugins_start_delay: float = 2.0  # seconds to wait after starting plugin processes before running register; increase on slow Windows if register fails
    # When true, on permission denied (unknown user) notify owner via last-used channel so they can add to user.yml. See docs_design/OutboundMarkdownAndUnknownRequest.md.
    notify_unknown_request: bool = False
    # Outbound text format: Core converts assistant reply (Markdown) before sending to channels. "whatsapp" (default) = *bold* _italic_ ~strikethrough~ (works for most IMs); "plain" = strip Markdown; "none" = no conversion.
    outbound_markdown_format: str = "whatsapp"
    # Mix mode (3-layer router): "local" | "cloud" | "mix". Empty or missing = derive from main_llm (cloud_models/ → cloud, else local). When "mix", main_llm_local and main_llm_cloud are used per request by the router.
    main_llm_mode: str = ""
    main_llm_local: str = ""   # e.g. local_models/main_vl_model_4B; required when main_llm_mode == "mix"
    main_llm_cloud: str = ""  # e.g. cloud_models/Gemini-2.5-Flash; required when main_llm_mode == "mix"
    hybrid_router: Dict[str, Any] = field(default_factory=dict)  # default_route, heuristic, semantic, slm (enabled, threshold, paths/model)
    # Companion: config kept for backward compat; Core no longer routes to Friends plugin. All users (normal + companion type) use the same main flow. See docs_design/CompanionFeatureDesign.md.
    companion: Dict[str, Any] = field(default_factory=dict)
    # RAG memory summarization: periodic summarization + TTL for originals; summaries kept forever. See docs_design/RAGMemorySummarizationDesign.md
    memory_summarization: Dict[str, Any] = field(default_factory=dict)  # enabled, schedule (daily|weekly|next_run), interval_days, keep_original_days, min_age_days, max_memories_per_batch
    # Portal (Phase 4): when set, Core proxies /api/config/* and /portal-ui to Portal. Same secret as Portal's PORTAL_SECRET or portal_secret.txt.
    portal_url: str = ""
    portal_secret: str = ""

    @staticmethod
    def _safe_str_strip(val: Any) -> str:
        """Return stripped string; non-string or None → ''. Never raises."""
        try:
            if val is None or val == "":
                return ""
            return str(val).strip()
        except Exception:
            return ""

    def get_homeclaw_root(self) -> str:
        """Effective root for file/folder tools and links (sandbox + share). When homeclaw_root is empty or missing, returns '' — do not use workspace_dir for user file access; workspace is internal. Set homeclaw_root in config/core.yml for channel/companion file and folder tools. Never raises."""
        try:
            raw = getattr(self, "homeclaw_root", None)
            root = (str(raw).strip() if raw is not None and raw != "" else "")
            return root
        except Exception:
            return ""

    @staticmethod
    def _normalize_system_plugins_env(raw: Any) -> Dict[str, Dict[str, str]]:
        """Convert system_plugins_env from YAML to Dict[plugin_id, Dict[var_name, str]]. Values may be non-string in YAML."""
        if not raw or not isinstance(raw, dict):
            return {}
        out: Dict[str, Dict[str, str]] = {}
        for plugin_id, vars_dict in raw.items():
            if not isinstance(vars_dict, dict):
                continue
            normalized = {}
            for k, v in vars_dict.items():
                if v is True:
                    normalized[str(k)] = "true"
                elif v is False:
                    normalized[str(k)] = "false"
                else:
                    normalized[str(k)] = str(v)
            out[str(plugin_id)] = normalized
        return out

    @staticmethod
    def _parse_agent_memory_max_chars(raw: Any) -> int:
        """Default 20000 when key missing; 0 = no truncation when explicitly set."""
        if raw is None:
            return 20000
        return max(0, int(raw) if raw != '' else 20000)

    @staticmethod
    def from_yaml(yaml_file: str) -> 'CoreMetadata':
        """Load CoreMetadata from core.yml. Never modifies the file. On parse error or invalid content, raises with a clear message so callers do not write back partial data."""
        try:
            with open(yaml_file, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)
        except FileNotFoundError:
            raise RuntimeError(f"config/core.yml not found at {yaml_file}. Create it or fix the path.") from None
        except Exception as e:
            raise RuntimeError(f"config/core.yml could not be read or parsed: {e}. Fix the file (do not overwrite with defaults).") from e
        if not isinstance(data, dict):
            raise RuntimeError("config/core.yml is empty or invalid (root must be a YAML object). Fix the file before starting Core.")
        data = data or {}

        # Optional: merge skills/plugins config from external file so core.yml stays short.
        # Never crash: file missing/malformed or bad value types are logged and skipped; Core starts with core.yml + safe merged keys only.
        _ext_file = (data.get('skills_and_plugins_config_file') or '').strip()
        if _ext_file:
            _config_dir = os.path.dirname(os.path.abspath(yaml_file))
            _ext_path = os.path.join(_config_dir, _ext_file)
            if os.path.isfile(_ext_path):
                try:
                    with open(_ext_path, 'r', encoding='utf-8') as _f:
                        _ext_data = yaml.safe_load(_f)
                    if isinstance(_ext_data, dict):
                        for _k, _v in _ext_data.items():
                            if not (_k.startswith('skills_') or _k.startswith('plugins_') or _k.startswith('system_plugins') or _k == 'tools'):
                                continue
                            # Avoid injecting wrong types so later from_yaml never raises on this key
                            if _k in ('skills_force_include_rules', 'plugins_force_include_rules', 'system_plugins', 'skills_include_body_for', 'skills_extra_dirs', 'skills_disabled', 'plugins_extra_dirs') and not isinstance(_v, list):
                                logging.warning("skills_and_plugins config %s: %s must be a list, got %s; skipping", _ext_path, _k, type(_v).__name__)
                                continue
                            if _k == 'system_plugins_env' and not isinstance(_v, dict):
                                logging.warning("skills_and_plugins config %s: system_plugins_env must be a dict, got %s; skipping", _ext_path, type(_v).__name__)
                                continue
                            if _k == 'tools' and not isinstance(_v, dict):
                                logging.warning("skills_and_plugins config %s: tools must be a dict, got %s; skipping", _ext_path, type(_v).__name__)
                                continue
                            # Numeric/string keys: only set if value is safe so int/float/str later never raise
                            if _k in ('skills_max_in_prompt', 'plugins_max_in_prompt', 'plugins_description_max_chars', 'skills_max_retrieved', 'skills_include_body_max_chars'):
                                try:
                                    _ = int(_v) if _v is not None else 0
                                except (TypeError, ValueError):
                                    logging.warning("skills_and_plugins config %s: %s must be an integer, got %s; skipping", _ext_path, _k, type(_v).__name__)
                                    continue
                            if _k == 'skills_similarity_threshold':
                                try:
                                    _ = float(_v) if _v is not None else 0.0
                                except (TypeError, ValueError):
                                    logging.warning("skills_and_plugins config %s: %s must be a number, got %s; skipping", _ext_path, _k, type(_v).__name__)
                                    continue
                            if _k == 'system_plugins_start_delay':
                                try:
                                    _ = float(_v) if _v is not None else 2.0
                                except (TypeError, ValueError):
                                    logging.warning("skills_and_plugins config %s: %s must be a number, got %s; skipping", _ext_path, _k, type(_v).__name__)
                                    continue
                            data[_k] = _v
                except Exception as _e:
                    logging.warning("Could not load skills_and_plugins config from %s: %s", _ext_path, _e)

        # Optional: merge memory/kb/database config from external file (memory_kb.yml).
        _mem_kb_file = (data.get('memory_kb_config_file') or '').strip()
        _MEMORY_KB_KEYS = frozenset({
            'use_memory', 'memory_backend', 'memory_check_before_add', 'memory_summarization',
            'database', 'vectorDB', 'graphDB', 'cognee', 'knowledge_base', 'profile', 'session',
            'use_agent_memory_file', 'agent_memory_path', 'agent_memory_max_chars',
            'use_daily_memory', 'daily_memory_dir', 'use_agent_memory_search',
            'agent_memory_vector_collection', 'agent_memory_bootstrap_max_chars', 'agent_memory_bootstrap_max_chars_local',
        })
        if _mem_kb_file:
            _config_dir = os.path.dirname(os.path.abspath(yaml_file))
            _mem_kb_path = os.path.join(_config_dir, _mem_kb_file)
            if os.path.isfile(_mem_kb_path):
                try:
                    with open(_mem_kb_path, 'r', encoding='utf-8') as _f:
                        _mem_kb_data = yaml.safe_load(_f)
                    if isinstance(_mem_kb_data, dict):
                        for _k, _v in _mem_kb_data.items():
                            if _k not in _MEMORY_KB_KEYS:
                                continue
                            _dict_keys = ('database', 'vectorDB', 'graphDB', 'cognee', 'knowledge_base', 'memory_summarization', 'profile', 'session')
                            if _k in _dict_keys and not isinstance(_v, dict):
                                logging.warning("memory_kb config %s: %s must be a dict, got %s; skipping", _mem_kb_path, _k, type(_v).__name__)
                                continue
                            if _k in ('agent_memory_max_chars', 'agent_memory_bootstrap_max_chars', 'agent_memory_bootstrap_max_chars_local'):
                                try:
                                    _ = int(_v) if _v is not None else 0
                                except (TypeError, ValueError):
                                    logging.warning("memory_kb config %s: %s must be an integer, got %s; skipping", _mem_kb_path, _k, type(_v).__name__)
                                    continue
                            data[_k] = _v
                except Exception as _e:
                    logging.warning("Could not load memory_kb config from %s: %s", _mem_kb_path, _e)

        # Optional: merge LLM config from external file (llm.yml).
        _llm_file = (data.get('llm_config_file') or '').strip()
        _LLM_KEYS = frozenset({
            'local_models', 'cloud_models', 'main_llm', 'main_llm_mode', 'main_llm_local', 'main_llm_cloud',
            'hybrid_router', 'main_llm_language', 'embedding_llm',
            'embedding_host', 'embedding_port', 'main_llm_host', 'main_llm_port', 'embedding_health_check_timeout_sec',
        })
        if _llm_file:
            _config_dir = os.path.dirname(os.path.abspath(yaml_file))
            _llm_path = os.path.join(_config_dir, _llm_file)
            if os.path.isfile(_llm_path):
                try:
                    with open(_llm_path, 'r', encoding='utf-8') as _f:
                        _llm_data = yaml.safe_load(_f)
                    if isinstance(_llm_data, dict):
                        for _k, _v in _llm_data.items():
                            if _k not in _LLM_KEYS:
                                continue
                            if _k in ('local_models', 'cloud_models') and not isinstance(_v, list):
                                logging.warning("llm config %s: %s must be a list, got %s; skipping", _llm_path, _k, type(_v).__name__)
                                continue
                            if _k == 'hybrid_router' and not isinstance(_v, dict):
                                logging.warning("llm config %s: hybrid_router must be a dict, got %s; skipping", _llm_path, type(_v).__name__)
                                continue
                            if _k in ('embedding_port', 'main_llm_port'):
                                try:
                                    _ = int(_v) if _v is not None else 0
                                except (TypeError, ValueError):
                                    logging.warning("llm config %s: %s must be an integer, got %s; skipping", _llm_path, _k, type(_v).__name__)
                                    continue
                            data[_k] = _v
                except Exception as _e:
                    logging.warning("Could not load llm config from %s: %s", _llm_path, _e)

        # Relational database (optional; default sqlite)
        db_cfg = data.get('database') or {}
        database = Database(
            backend=str(db_cfg.get('backend', 'sqlite')).lower(),
            url=(db_cfg.get('url') or '').strip(),
        )
        # Vector DB: backend + optional per-backend config
        vdb = data.get('vectorDB') or {}
        backend = (vdb.get('backend') or 'chroma').lower()
        chroma_cfg = vdb.get('Chroma') or {}
        chroma = Chroma(
            host=chroma_cfg.get('host', '0.0.0.0'),
            port=int(chroma_cfg.get('port', 5000)),
            api=chroma_cfg.get('api', 'chromadb.api.fastapi.FastAPI'),
            is_persistent=chroma_cfg.get('is_persistent', True),
            anonymized_telemetry=chroma_cfg.get('anonymized_telemetry', False),
            path=(chroma_cfg.get('path') or '').strip(),
        )
        qdrant_cfg = vdb.get('Qdrant') or {}
        qdrant = Qdrant(
            host=qdrant_cfg.get('host', 'localhost'),
            port=int(qdrant_cfg.get('port', 6333)),
            url=(qdrant_cfg.get('url') or '').strip(),
            api_key=(qdrant_cfg.get('api_key') or '').strip(),
        )
        milvus_cfg = vdb.get('Milvus') or {}
        milvus = Milvus(
            host=milvus_cfg.get('host', 'localhost'),
            port=int(milvus_cfg.get('port', 19530)),
            uri=(milvus_cfg.get('uri') or '').strip(),
        )
        pinecone_cfg = vdb.get('Pinecone') or {}
        pinecone = Pinecone(
            api_key=(pinecone_cfg.get('api_key') or '').strip(),
            environment=(pinecone_cfg.get('environment') or '').strip(),
            index_name=(pinecone_cfg.get('index_name') or 'memory').strip(),
        )
        weaviate_cfg = vdb.get('Weaviate') or {}
        weaviate = Weaviate(
            url=(weaviate_cfg.get('url') or 'http://localhost:8080').strip(),
            api_key=(weaviate_cfg.get('api_key') or '').strip(),
        )
        vectorDB = VectorDB(
            backend=backend,
            Chroma=chroma,
            Qdrant=qdrant,
            Milvus=milvus,
            Pinecone=pinecone,
            Weaviate=weaviate,
        )
        gdb = data.get('graphDB') or {}
        gdb_backend = (gdb.get('backend') or 'kuzu').lower()
        kuzu_cfg = gdb.get('Kuzu') or {}
        neo4j_cfg = gdb.get('Neo4j') or {}
        graphDB = GraphDB(
            backend=gdb_backend,
            Kuzu=Kuzu(path=(kuzu_cfg.get('path') or '').strip()),
            Neo4j=Neo4jConfig(
                url=(neo4j_cfg.get('url') or 'bolt://localhost:7687').strip(),
                username=(neo4j_cfg.get('username') or 'neo4j').strip(),
                password=(neo4j_cfg.get('password') or '').strip(),
            ),
        )
        endpoints_raw = data.get('endpoints')
        if not isinstance(endpoints_raw, list):
            endpoints_raw = []
        endpoints = [Endpoint(**ep) for ep in endpoints_raw]
        
        llama_cpp = data.get('llama_cpp')
        if not isinstance(llama_cpp, dict):
            llama_cpp = {}
        completion = data.get('completion')
        if not isinstance(completion, dict):
            completion = {}
        local_models = data.get('local_models')
        if not isinstance(local_models, list):
            local_models = []
        cloud_models = data.get('cloud_models')
        if not isinstance(cloud_models, list):
            cloud_models = []
        # If main_llm points to a cloud model and that entry has api_key set, use it for main_llm_api_key
        main_llm_ref = (data.get('main_llm') or '').strip()
        main_llm_api_key_val = (data.get('main_llm_api_key') or '').strip()
        main_llm_api_key_name_val = (data.get('main_llm_api_key_name') or '').strip()
        if main_llm_ref.startswith('cloud_models/'):
            entry_id = main_llm_ref[len('cloud_models/'):].strip()
            for m in cloud_models:
                if (m.get('id') or '').strip() == entry_id:
                    entry_key = (m.get('api_key') or '').strip() if isinstance(m.get('api_key'), str) else ''
                    if entry_key:
                        main_llm_api_key_val = entry_key
                        main_llm_api_key_name_val = (m.get('api_key_name') or main_llm_api_key_name_val or '').strip()
                    break
        # main_llm_mode: "local" | "cloud" | "mix". Default: derive from main_llm so existing configs stay valid.
        main_llm_mode_raw = (data.get('main_llm_mode') or '').strip().lower()
        if main_llm_mode_raw in ('local', 'cloud', 'mix'):
            main_llm_mode_val = main_llm_mode_raw
        else:
            main_llm_mode_val = 'cloud' if main_llm_ref.startswith('cloud_models/') else 'local'
        main_llm_local_val = (data.get('main_llm_local') or '').strip()
        main_llm_cloud_val = (data.get('main_llm_cloud') or '').strip()
        # When mode is set, derive main_llm from main_llm_local/main_llm_cloud so main_llm can be omitted in config.
        if main_llm_mode_val == 'local' and main_llm_local_val:
            main_llm_ref = main_llm_local_val
        elif main_llm_mode_val == 'cloud' and main_llm_cloud_val:
            main_llm_ref = main_llm_cloud_val
        elif main_llm_mode_val == 'mix':
            hr_default = ((data.get('hybrid_router') or {}).get('default_route') or 'local').strip().lower()
            main_llm_ref = main_llm_local_val if hr_default == 'local' else main_llm_cloud_val
            if not main_llm_ref:
                main_llm_ref = main_llm_local_val or main_llm_cloud_val or (data.get('main_llm') or '').strip()
        # If we derived a cloud ref (e.g. main_llm omitted but main_llm_mode: cloud), pull api_key from that entry.
        if main_llm_ref.startswith('cloud_models/'):
            entry_id = main_llm_ref[len('cloud_models/'):].strip()
            for m in cloud_models:
                if (m.get('id') or '').strip() == entry_id:
                    entry_key = (m.get('api_key') or '').strip() if isinstance(m.get('api_key'), str) else ''
                    if entry_key:
                        main_llm_api_key_val = entry_key
                        main_llm_api_key_name_val = (m.get('api_key_name') or main_llm_api_key_name_val or '').strip()
                    break
        hybrid_router_raw = data.get('hybrid_router')
        hybrid_router_val = hybrid_router_raw if isinstance(hybrid_router_raw, dict) else {}
        cognee = data.get('cognee')
        if not isinstance(cognee, dict):
            cognee = {}

        try:
            return CoreMetadata(
            name=data['name'],
            host=data['host'],
            port=data['port'],
            mode=data['mode'],
            model_path=data['model_path'],
            embedding_llm=data.get('embedding_llm', ''),
            embedding_host=data.get('embedding_host', '127.0.0.1'),
            embedding_port=data.get('embedding_port', 5066),
            embedding_health_check_timeout_sec=max(30, int(data.get('embedding_health_check_timeout_sec', 120) or 120)),
            embedding_llm_type=data.get('embedding_llm_type', 'local'),
            main_llm_type=data.get('main_llm_type', 'local'),
            main_llm=main_llm_ref,
            main_llm_host=data.get('main_llm_host', '127.0.0.1'),
            main_llm_port=data.get('main_llm_port', 5088),
            main_llm_language=_normalize_main_llm_language(data.get('main_llm_language', 'en')),
            main_llm_api_key_name=main_llm_api_key_name_val,
            main_llm_api_key=main_llm_api_key_val,
            silent=data.get('silent', False),
            log_to_console=data.get('log_to_console', False),
            use_memory=data.get('use_memory', True),
            memory_backend=(data.get('memory_backend') or 'cognee').strip().lower(),
            memory_check_before_add=bool(data.get('memory_check_before_add', False)),
            default_location=(data.get('default_location') or '').strip(),
            database=database,
            vectorDB=vectorDB,
            graphDB=graphDB,
            cognee=cognee,
            endpoints=endpoints,
            llama_cpp=llama_cpp,
            completion=completion,
            local_models=local_models,
            cloud_models=cloud_models,
            use_workspace_bootstrap=data.get('use_workspace_bootstrap', True),
            workspace_dir=data.get('workspace_dir', 'config/workspace'),
            homeclaw_root=CoreMetadata._safe_str_strip(data.get('homeclaw_root')),
            use_agent_memory_file=bool(data.get('use_agent_memory_file', True)),
            agent_memory_path=(data.get('agent_memory_path') or '').strip(),
            agent_memory_max_chars=max(0, int(data.get('agent_memory_max_chars', 20000) or 0)),
            use_daily_memory=bool(data.get('use_daily_memory', True)),
            daily_memory_dir=(data.get('daily_memory_dir') or '').strip(),
            use_agent_memory_search=bool(data.get('use_agent_memory_search', True)),
            agent_memory_vector_collection=(data.get('agent_memory_vector_collection') or 'homeclaw_agent_memory').strip(),
            agent_memory_bootstrap_max_chars=max(500, int(data.get('agent_memory_bootstrap_max_chars', 20000) or 20000)),
            agent_memory_bootstrap_max_chars_local=max(500, int(data.get('agent_memory_bootstrap_max_chars_local', 8000) or 8000)),
            session=data.get('session') if isinstance(data.get('session'), dict) else {},
            compaction=data.get('compaction') if isinstance(data.get('compaction'), dict) else {},
            use_tools=data.get('use_tools', True),
            use_skills=data.get('use_skills', True),
            skills_dir=(data.get('skills_dir') or 'skills').strip() or 'skills',
            skills_extra_dirs=[str(p).strip() for p in (data.get('skills_extra_dirs') or []) if str(p).strip()],
            skills_disabled=[str(f).strip() for f in (data.get('skills_disabled') or []) if str(f).strip()],
            skills_max_in_prompt=max(0, int(data.get('skills_max_in_prompt', 5) or 5)),
            plugins_max_in_prompt=max(0, int(data.get('plugins_max_in_prompt', 5) or 5)),
            plugins_use_vector_search=bool(data.get('plugins_use_vector_search', False)),
            plugins_vector_collection=(data.get('plugins_vector_collection') or 'homeclaw_plugins').strip(),
            plugins_description_max_chars=max(0, int(data.get('plugins_description_max_chars', 0) or 0)),
            skills_use_vector_search=bool(data.get('skills_use_vector_search', False)),
            skills_vector_collection=(data.get('skills_vector_collection') or 'homeclaw_skills').strip(),
            skills_max_retrieved=max(1, min(100, int(data.get('skills_max_retrieved', 10) or 10))),
            skills_similarity_threshold=float(data.get('skills_similarity_threshold', 0.0) or 0.0),
            skills_refresh_on_startup=bool(data.get('skills_refresh_on_startup', True)),
            skills_test_dir=(data.get('skills_test_dir') or '').strip(),
            skills_incremental_sync=bool(data.get('skills_incremental_sync', False)),
            skills_include_body_for=[str(f).strip() for f in (data.get('skills_include_body_for') or []) if f],
            skills_include_body_max_chars=max(0, int(data.get('skills_include_body_max_chars', 0) or 0)),
            skills_force_include_rules=[r for r in (data.get('skills_force_include_rules') or []) if isinstance(r, dict) and (r.get('pattern') or r.get('patterns')) and (r.get('folders') is not None or r.get('auto_invoke'))],
            plugins_force_include_rules=[r for r in (data.get('plugins_force_include_rules') or []) if isinstance(r, dict) and r.get('pattern') and r.get('plugins')],
            skills_and_plugins_config_file=(data.get('skills_and_plugins_config_file') or '').strip(),
            memory_kb_config_file=(data.get('memory_kb_config_file') or '').strip(),
            llm_config_file=(data.get('llm_config_file') or '').strip(),
            plugins_extra_dirs=[str(p).strip() for p in (data.get('plugins_extra_dirs') or []) if str(p).strip()],
            orchestrator_timeout_seconds=(lambda v: max(0, int(v)) if v is not None else 60)(data.get('orchestrator_timeout_seconds', 60)),
            tool_timeout_seconds=int((data.get('tools') or {}).get('tool_timeout_seconds', 120) or 0),
            tools_config=copy.deepcopy(data.get('tools')) if isinstance(data.get('tools'), dict) else {},
            orchestrator_unified_with_tools=data.get('orchestrator_unified_with_tools', True),
            inbound_request_timeout_seconds=max(0, int(data.get('inbound_request_timeout_seconds', 0) or 0)),
            use_prompt_manager=data.get('use_prompt_manager', True),
            prompts_dir=(data.get('prompts_dir') or 'config/prompts').strip(),
            prompt_default_language=(data.get('prompt_default_language') or 'en').strip() or 'en',
            prompt_cache_ttl_seconds=float(data.get('prompt_cache_ttl_seconds', 0) or 0),
            auth_enabled=data.get('auth_enabled', False),
            auth_api_key=(data.get('auth_api_key') or '').strip(),
            core_public_url=(data.get('core_public_url') or '').strip(),
            file_link_style=(data.get('file_link_style') or 'token').strip().lower() or 'token',
            file_static_prefix=(data.get('file_static_prefix') or 'files').strip().strip('/') or 'files',
            file_view_link_expiry_sec=_normalize_file_view_link_expiry(data.get('file_view_link_expiry_sec')),
            llm_max_concurrent_local=_normalize_llm_max_concurrent(
                data.get('llm_max_concurrent_local') if 'llm_max_concurrent_local' in data else _default_llm_max_concurrent_local()
            ),
            llm_max_concurrent_cloud=_normalize_llm_max_concurrent(
                data.get('llm_max_concurrent_cloud') if 'llm_max_concurrent_cloud' in data else _default_llm_max_concurrent_cloud(main_llm_mode_val)
            ),
            knowledge_base=data.get('knowledge_base') if isinstance(data.get('knowledge_base'), dict) else {},
            profile=data.get('profile') if isinstance(data.get('profile'), dict) else {},
            result_viewer=data.get('result_viewer') if isinstance(data.get('result_viewer'), dict) else {},
            system_plugins_auto_start=bool(data.get('system_plugins_auto_start', False)),
            system_plugins=list(data.get('system_plugins') or []) if isinstance(data.get('system_plugins'), list) else [],
            system_plugins_env=CoreMetadata._normalize_system_plugins_env(data.get('system_plugins_env')),
            system_plugins_start_delay=max(0.5, float(data.get('system_plugins_start_delay', 2) or 2)),
            notify_unknown_request=bool(data.get('notify_unknown_request', False)),
            outbound_markdown_format=(data.get('outbound_markdown_format') or 'whatsapp').strip().lower() or 'whatsapp',
            main_llm_mode=main_llm_mode_val,
            main_llm_local=main_llm_local_val,
            main_llm_cloud=main_llm_cloud_val,
            hybrid_router=hybrid_router_val,
            companion=data.get('companion') if isinstance(data.get('companion'), dict) else {},
            memory_summarization=data.get('memory_summarization') if isinstance(data.get('memory_summarization'), dict) else {},
            portal_url=(data.get('portal_url') or os.environ.get('PORTAL_URL') or '').strip(),
            portal_secret=(data.get('portal_secret') or os.environ.get('PORTAL_SECRET') or '').strip(),
        )
        except (KeyError, TypeError, ValueError) as e:
            raise RuntimeError(f"config/core.yml has invalid or missing content: {e}. Fix the file before starting Core.") from e

    # @staticmethod
    # def to_yaml(core: 'CoreMetadata', yaml_file: str):
    #     with open(yaml_file, 'w', encoding='utf-8') as file:
    #         # Convert the core instance to a dictionary
    #         yaml.safe_dump(core.__dict__, file, default_flow_style=False)

    @staticmethod
    def to_yaml(core: 'CoreMetadata', yaml_file: str):
        # Manually prepare a dictionary to serialize (only CoreMetadata fields)
        core_dict = {
                'name': core.name,
                'host': core.host,
                'port': core.port,
                'mode': core.mode,
                'model_path': core.model_path,
                'embedding_host': core.embedding_host,
                'embedding_port': core.embedding_port,
                'embedding_health_check_timeout_sec': getattr(core, 'embedding_health_check_timeout_sec', 120),
                'main_llm_host': core.main_llm_host,
                'main_llm_port': core.main_llm_port,
                'main_llm_language': core.main_llm_language,
                'main_llm': core.main_llm,
                'silent': core.silent,
                'log_to_console': getattr(core, 'log_to_console', False),
                'use_memory': core.use_memory,
                'memory_backend': getattr(core, 'memory_backend', 'cognee') or 'cognee',
                'default_location': getattr(core, 'default_location', '') or '',
                'use_workspace_bootstrap': getattr(core, 'use_workspace_bootstrap', True),
                'workspace_dir': getattr(core, 'workspace_dir', 'config/workspace'),
                'homeclaw_root': CoreMetadata._safe_str_strip(getattr(core, 'homeclaw_root', None)),
                # use_tools / use_skills omitted from core_dict so core.yml stays minimal; both default True in from_yaml
                'skills_dir': getattr(core, 'skills_dir', 'skills'),
                'skills_extra_dirs': getattr(core, 'skills_extra_dirs', None) or [],
                'skills_disabled': getattr(core, 'skills_disabled', None) or [],
                'skills_max_in_prompt': getattr(core, 'skills_max_in_prompt', 0),
                'plugins_max_in_prompt': getattr(core, 'plugins_max_in_prompt', 0),
                'plugins_use_vector_search': getattr(core, 'plugins_use_vector_search', False),
                'plugins_vector_collection': getattr(core, 'plugins_vector_collection', 'homeclaw_plugins') or 'homeclaw_plugins',
                'plugins_description_max_chars': getattr(core, 'plugins_description_max_chars', 0),
                'skills_use_vector_search': getattr(core, 'skills_use_vector_search', False),
                'skills_vector_collection': getattr(core, 'skills_vector_collection', 'homeclaw_skills') or 'homeclaw_skills',
                'skills_max_retrieved': getattr(core, 'skills_max_retrieved', 10),
                'skills_similarity_threshold': getattr(core, 'skills_similarity_threshold', 0.0),
                'skills_refresh_on_startup': getattr(core, 'skills_refresh_on_startup', True),
                'skills_test_dir': getattr(core, 'skills_test_dir', '') or '',
                'skills_incremental_sync': getattr(core, 'skills_incremental_sync', False),
                'skills_include_body_for': getattr(core, 'skills_include_body_for', None) or [],
                'skills_include_body_max_chars': getattr(core, 'skills_include_body_max_chars', 0),
                'skills_force_include_rules': getattr(core, 'skills_force_include_rules', None) or [],
                'plugins_force_include_rules': getattr(core, 'plugins_force_include_rules', None) or [],
                'skills_and_plugins_config_file': getattr(core, 'skills_and_plugins_config_file', '') or '',
                'memory_kb_config_file': getattr(core, 'memory_kb_config_file', '') or '',
                'llm_config_file': getattr(core, 'llm_config_file', '') or '',
                'plugins_extra_dirs': getattr(core, 'plugins_extra_dirs', None) or [],
                'orchestrator_timeout_seconds': getattr(core, 'orchestrator_timeout_seconds', 60),
                # tool_timeout_seconds is written under data["tools"] below, not as top-level
                'orchestrator_unified_with_tools': getattr(core, 'orchestrator_unified_with_tools', True),
                'inbound_request_timeout_seconds': getattr(core, 'inbound_request_timeout_seconds', 0),
                'notify_unknown_request': getattr(core, 'notify_unknown_request', False),
                'outbound_markdown_format': getattr(core, 'outbound_markdown_format', 'whatsapp') or 'whatsapp',
                'use_prompt_manager': getattr(core, 'use_prompt_manager', True),
                'prompts_dir': getattr(core, 'prompts_dir', 'config/prompts') or 'config/prompts',
                'prompt_default_language': getattr(core, 'prompt_default_language', 'en') or 'en',
                'prompt_cache_ttl_seconds': getattr(core, 'prompt_cache_ttl_seconds', 0),
                'auth_enabled': getattr(core, 'auth_enabled', False),
                'auth_api_key': getattr(core, 'auth_api_key', '') or '',
                'core_public_url': getattr(core, 'core_public_url', '') or '',
                'file_link_style': getattr(core, 'file_link_style', 'token') or 'token',
                'file_static_prefix': getattr(core, 'file_static_prefix', 'files') or 'files',
                'file_view_link_expiry_sec': getattr(core, 'file_view_link_expiry_sec', 7 * 86400),
                'llm_max_concurrent_local': getattr(core, 'llm_max_concurrent_local', 1),
                'llm_max_concurrent_cloud': getattr(core, 'llm_max_concurrent_cloud', 4),
                'embedding_llm': core.embedding_llm,
                'llama_cpp': core.llama_cpp or {},
                'completion': getattr(core, 'completion', {}) or {},
                'local_models': core.local_models or [],
                # Write actual api_key from config (do not redact); redaction is for logs only.
                'cloud_models': list(core.cloud_models or []),
                'database': {'backend': core.database.backend, 'url': core.database.url},
                'vectorDB': {
                    'backend': core.vectorDB.backend,
                    'Chroma': vars(core.vectorDB.Chroma),
                    'Qdrant': vars(core.vectorDB.Qdrant),
                    'Milvus': vars(core.vectorDB.Milvus),
                    'Pinecone': vars(core.vectorDB.Pinecone),
                    'Weaviate': vars(core.vectorDB.Weaviate),
                },
                'graphDB': {
                    'backend': getattr(core, 'graphDB', GraphDB()).backend,
                    'Kuzu': vars(getattr(core, 'graphDB', GraphDB()).Kuzu),
                    'Neo4j': vars(getattr(core, 'graphDB', GraphDB()).Neo4j),
                },
                'cognee': getattr(core, 'cognee', {}) or {},
                'endpoints': [
                    vars(ep) for ep in core.endpoints
                ]
        }
        # When using external skills/plugins config file, do not write those keys into core.yml (keep them only in the external file)
        _ext = (getattr(core, 'skills_and_plugins_config_file', None) or '').strip()
        if _ext:
            for _k in list(core_dict.keys()):
                if _k.startswith('skills_') or _k.startswith('plugins_') or _k.startswith('system_plugins'):
                    core_dict.pop(_k, None)
            core_dict['skills_and_plugins_config_file'] = _ext
        # When using external memory_kb config file, do not write memory/kb/database keys into core.yml
        _mem_kb_ext = (getattr(core, 'memory_kb_config_file', None) or '').strip()
        _MEMORY_KB_POP = frozenset({
            'use_memory', 'memory_backend', 'memory_check_before_add', 'memory_summarization',
            'database', 'vectorDB', 'graphDB', 'cognee', 'knowledge_base', 'profile', 'session',
            'use_agent_memory_file', 'agent_memory_path', 'agent_memory_max_chars',
            'use_daily_memory', 'daily_memory_dir', 'use_agent_memory_search',
            'agent_memory_vector_collection', 'agent_memory_bootstrap_max_chars', 'agent_memory_bootstrap_max_chars_local',
        })
        if _mem_kb_ext:
            for _k in list(core_dict.keys()):
                if _k in _MEMORY_KB_POP:
                    core_dict.pop(_k, None)
            core_dict['memory_kb_config_file'] = _mem_kb_ext
        # When using external llm config file, do not write LLM keys into core.yml
        _llm_ext = (getattr(core, 'llm_config_file', None) or '').strip()
        _LLM_POP = frozenset({
            'local_models', 'cloud_models', 'main_llm', 'main_llm_mode', 'main_llm_local', 'main_llm_cloud',
            'hybrid_router', 'main_llm_language', 'embedding_llm',
            'embedding_host', 'embedding_port', 'main_llm_host', 'main_llm_port', 'embedding_health_check_timeout_sec',
        })
        if _llm_ext:
            for _k in list(core_dict.keys()):
                if _k in _LLM_POP:
                    core_dict.pop(_k, None)
            core_dict['llm_config_file'] = _llm_ext
        # Only write api key fields when set (cloud main model; key can be set via CLI)
        if (core.main_llm_api_key_name or '').strip():
            core_dict['main_llm_api_key_name'] = core.main_llm_api_key_name
        if (core.main_llm_api_key or '').strip():
            core_dict['main_llm_api_key'] = core.main_llm_api_key
        # Mix mode and hybrid router (optional; omit when not used so existing configs stay clean)
        if getattr(core, 'main_llm_mode', None) and str(core.main_llm_mode).strip().lower() == 'mix':
            core_dict['main_llm_mode'] = 'mix'
            if (getattr(core, 'main_llm_local', None) or '').strip():
                core_dict['main_llm_local'] = (core.main_llm_local or '').strip()
            if (getattr(core, 'main_llm_cloud', None) or '').strip():
                core_dict['main_llm_cloud'] = (core.main_llm_cloud or '').strip()
            if getattr(core, 'hybrid_router', None) and isinstance(core.hybrid_router, dict) and core.hybrid_router:
                core_dict['hybrid_router'] = core.hybrid_router
        if (getattr(core, 'portal_url', None) or '').strip():
            core_dict['portal_url'] = (core.portal_url or '').strip()
        if (getattr(core, 'portal_secret', None) or '').strip():
            core_dict['portal_secret'] = (core.portal_secret or '').strip()

        def _deep_merge_into_existing(existing_node, updates):
            """Merge updates into existing_node in place. Keeps existing_node (and ruamel comments) when both are dicts."""
            if not isinstance(existing_node, dict) or not isinstance(updates, dict):
                return
            for k, v in updates.items():
                if k not in existing_node:
                    existing_node[k] = v
                elif isinstance(v, dict) and isinstance(existing_node.get(k), dict):
                    _deep_merge_into_existing(existing_node[k], v)
                else:
                    existing_node[k] = v

        def _merge_core_dict_into_data(data: dict, core_dict: dict) -> None:
            """Update data with core_dict values; deep-merge nested dicts so ruamel comments in data are preserved."""
            for k, v in core_dict.items():
                if k in data and isinstance(data.get(k), dict) and isinstance(v, dict):
                    _deep_merge_into_existing(data[k], v)
                else:
                    data[k] = v

        def _reorder_core_yml_keys(data: dict) -> None:
            """Move main_llm, endpoints to logical positions so they don't always end up at EOF. tool_timeout_seconds lives under tools:, not top-level."""
            keys = list(data.keys())
            to_place = [k for k in ("main_llm", "endpoints") if k in data]
            if not to_place:
                return
            # Start with keys in current order, minus the ones we want to move
            new_order = [k for k in keys if k not in to_place]
            def insert_after(anchor: str, key: str) -> bool:
                if key not in data or key not in to_place:
                    return False
                try:
                    i = new_order.index(anchor) + 1
                    new_order.insert(i, key)
                    return True
                except ValueError:
                    return False
            # Place main_llm after main_llm_port (or main_llm_cloud); then endpoints after main_llm
            if not insert_after("main_llm_port", "main_llm"):
                insert_after("main_llm_cloud", "main_llm")
            insert_after("main_llm", "endpoints")
            # Append any to_place that weren't inserted (anchor missing)
            for k in to_place:
                if k not in new_order:
                    new_order.append(k)
            # Reorder: build new dict in desired order (preserve type for ruamel)
            if type(data).__name__ == "CommentedMap":
                from ruamel.yaml.comments import CommentedMap
                reordered = CommentedMap()
                for k in new_order:
                    if k in data:
                        reordered[k] = data[k]
                data.clear()
                data.update(reordered)
            else:
                reordered = {k: data[k] for k in new_order if k in data}
                data.clear()
                data.update(reordered)

        def _restore_api_keys_from_original(merged_data: dict, original: dict) -> None:
            """Never write redacted api_key to config; restore from original file when merged value is *** or missing."""
            orig_cloud = (original.get('cloud_models') or []) if isinstance(original.get('cloud_models'), list) else []
            merged_cloud = merged_data.get('cloud_models')
            if not isinstance(merged_cloud, list) or not orig_cloud:
                return
            by_id = {(m.get('id') or '').strip(): m for m in orig_cloud if isinstance(m, dict) and (m.get('id') or '').strip()}
            for i, entry in enumerate(merged_cloud):
                if not isinstance(entry, dict):
                    continue
                eid = (entry.get('id') or '').strip()
                orig_entry = by_id.get(eid) if eid else None
                if not orig_entry:
                    continue
                orig_key = (orig_entry.get('api_key') or '').strip() if isinstance(orig_entry.get('api_key'), str) else None
                if not orig_key:
                    continue
                current = entry.get('api_key')
                if current is None or (isinstance(current, str) and (current.strip() == '' or current.strip() == '***')):
                    entry['api_key'] = orig_key

        # core.yml must never be overwritten with only CoreMetadata keys — always load full file, merge, then write.
        # Always write to a .tmp file first, then atomic rename; never truncate or overwrite the live file on failure.
        # to_yaml must never raise — any exception is caught so Core never crashes and core.yml is never corrupted.
        def _write_atomic(target_path: str, dump_fn) -> bool:
            """Write via dump_fn(open(tmp)) then os.replace(tmp, target). Returns True on success. Never raises."""
            tmp_path = target_path + ".tmp"
            try:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    dump_fn(f)
                os.replace(tmp_path, target_path)
                return True
            except Exception as e:
                logging.warning("core.yml: atomic write failed (skipping to avoid corrupting file): %s", e)
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                return False

        try:  # outer: never raise; never corrupt core.yml
            try:
                from ruamel.yaml import YAML
                yaml_rt = YAML()
                yaml_rt.preserve_quotes = True
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml_rt.load(f)
                if data is None:
                    data = {}
                original_snapshot = {k: v for k, v in data.items()}  # shallow copy for api_key restore
                _merge_core_dict_into_data(data, core_dict)  # deep-merge nested dicts so comments (e.g. cognee) are preserved
                if data.get("tools") is not None and isinstance(data["tools"], dict):
                    data["tools"]["tool_timeout_seconds"] = getattr(core, "tool_timeout_seconds", 120)
                if "tool_timeout_seconds" in data:
                    del data["tool_timeout_seconds"]  # avoid duplicate; only under tools:
                if _ext:
                    data.pop("tools", None)  # tools live in skills_and_plugins config file; do not write to core.yml
                data.pop("use_tools", None)
                data.pop("use_skills", None)  # always on; omit from file so core.yml stays minimal
                if _mem_kb_ext:
                    for _k in _MEMORY_KB_POP:
                        data.pop(_k, None)
                if _llm_ext:
                    for _k in _LLM_POP:
                        data.pop(_k, None)
                _restore_api_keys_from_original(data, original_snapshot)
                _reorder_core_yml_keys(data)
                _write_atomic(yaml_file, lambda f: yaml_rt.dump(data, f))
                return
            except Exception as e:
                logging.debug("CoreMetadata.to_yaml ruamel path failed: %s", e)
            # Fallback: ruamel failed — merge into existing; never overwrite a non-empty file with only core_dict
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    existing = yaml.safe_load(f) or {}
            except Exception as e:
                logging.debug("CoreMetadata.to_yaml load existing failed: %s", e)
                existing = {}
            if not existing and os.path.exists(yaml_file) and os.path.getsize(yaml_file) > 0:
                logging.warning(
                    "core.yml: could not load existing file (parse error?); skipping write to avoid removing keys. Fix the file or install ruamel.yaml."
                )
            else:
                original_snapshot = {k: v for k, v in existing.items()}
                _merge_core_dict_into_data(existing, core_dict)
                if existing.get("tools") is not None and isinstance(existing["tools"], dict):
                    existing["tools"]["tool_timeout_seconds"] = getattr(core, "tool_timeout_seconds", 120)
                if "tool_timeout_seconds" in existing:
                    del existing["tool_timeout_seconds"]  # avoid duplicate; only under tools:
                if _ext:
                    existing.pop("tools", None)  # tools live in skills_and_plugins config file; do not write to core.yml
                existing.pop("use_tools", None)
                existing.pop("use_skills", None)  # always on; omit from file so core.yml stays minimal
                if _mem_kb_ext:
                    for _k in _MEMORY_KB_POP:
                        existing.pop(_k, None)
                if _llm_ext:
                    for _k in _LLM_POP:
                        existing.pop(_k, None)
                _restore_api_keys_from_original(existing, original_snapshot)
                _reorder_core_yml_keys(existing)
                def _dump_safe(f):
                    yaml.safe_dump(existing, f, default_flow_style=False, sort_keys=False)
                _write_atomic(yaml_file, _dump_safe)
        except Exception as e:
            logging.warning("CoreMetadata.to_yaml failed (core.yml unchanged): %s", e)

 
class RegisterAgentRequest(BaseModel):
    name: str
    host: str
    port: str
    endpoints: List[Dict]


class RegisterChannelRequest(BaseModel):
    name: str
    host: str
    port: str
    endpoints: List[Dict]
    
    
class Server(uvicorn.Server):

    # Override
    def install_signal_handlers(self) -> None:

        # Do nothing
        pass
    