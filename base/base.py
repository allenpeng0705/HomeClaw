from datetime import datetime
from enum import Enum
import json
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
    user_id: str  # e.g. telegram chat_id, discord user id, email
    text: str
    channel_name: Optional[str] = "webhook"
    user_name: Optional[str] = None  # display name; defaults to user_id if omitted
    app_id: Optional[str] = "homeclaw"
    action: Optional[str] = "respond"
    # For multimodal: list of data URLs (data:...;base64,...) or paths Core can read
    images: Optional[List[str]] = None
    videos: Optional[List[str]] = None
    audios: Optional[List[str]] = None
    # Optional file paths (Core must be able to read) or data URLs; Core runs file-understanding
    files: Optional[List[str]] = None

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
class User:
    name: str
    email: List[str] = field(default_factory=list)
    im: List[str] = field(default_factory=list)
    phone: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    # Unique system user id for all storage (chat, memory, KB, profile). If omitted in yaml, defaults to name.
    id: Optional[str] = None

    @staticmethod
    def from_yaml(yaml_file: str) -> List['User']:
        with open(yaml_file, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        users = []
        for u in data.get('users') or []:
            uid = u.get('id') or u.get('name')
            users.append(User(
                name=u.get('name', ''),
                email=u.get('email') or [],
                im=u.get('im') or [],
                phone=u.get('phone') or [],
                permissions=u.get('permissions') or [],
                id=uid,
            ))
        return users

    @staticmethod
    def to_yaml(users: List['User'], yaml_file: str):
        with open(yaml_file, 'w', encoding='utf-8') as file:
            yaml.safe_dump({'users': [user.__dict__ for user in users]}, file)

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
    use_memory: bool
    reset_memory: bool
    memory_backend: str  # cognee (default) | chroma (in-house RAG)
    database: Database
    vectorDB: VectorDB
    graphDB: GraphDB
    cognee: Dict[str, Any] = field(default_factory=dict)  # optional; when set, applied as Cognee env before Cognee loads (see docs/MemoryAndDatabase.md)
    endpoints: List[Endpoint] = field(default_factory=list)
    llama_cpp: Dict[str, Any] = field(default_factory=dict)
    completion: Dict[str, Any] = field(default_factory=dict)  # max_tokens, temperature for chat completion (overrides llama_cpp when set)
    local_models: List[Dict[str, Any]] = field(default_factory=list)   # [{ id, path, host, port, alias?, capabilities? }]
    cloud_models: List[Dict[str, Any]] = field(default_factory=list)    # [{ id, path, host, port, api_key_name?, capabilities? }]
    use_workspace_bootstrap: bool = True  # inject config/workspace (IDENTITY.md, AGENTS.md, TOOLS.md) into system prompt
    workspace_dir: str = "config/workspace"  # which workspace dir to load (e.g. config/workspace_day vs config/workspace_night for day/night agents)
    use_agent_memory_file: bool = False  # inject AGENT_MEMORY.md (curated long-term memory); see SessionAndDualMemoryDesign.md
    agent_memory_path: str = ""  # empty = workspace_dir/AGENT_MEMORY.md
    agent_memory_max_chars: int = 5000  # max chars to inject; default 5k. 0 = no truncation. When > 0, only last N chars; see MemoryFilesUsage.md
    use_daily_memory: bool = False  # inject memory/YYYY-MM-DD.md for today + yesterday (short-term, bounded context); see SessionAndDualMemoryDesign.md
    daily_memory_dir: str = ""  # empty = workspace_dir/memory; or path relative to project (e.g. database/daily_memory)
    use_agent_memory_search: bool = True  # when True (default), retrieval-only: no bulk inject; model uses agent_memory_search + agent_memory_get. Set false for legacy bulk inject.
    agent_memory_vector_collection: str = "homeclaw_agent_memory"  # Chroma collection for agent memory chunks
    session: Dict[str, Any] = field(default_factory=dict)  # prune_keep_last_n, prune_after_turn, daily_reset_at_hour, idle_minutes, api_enabled
    compaction: Dict[str, Any] = field(default_factory=dict)  # enabled, reserve_tokens, max_messages_before_compact, compact_tool_results
    use_tools: bool = False  # enable tool layer (tool registry, execute tool_calls in chat loop)
    use_skills: bool = False  # inject skills (SKILL.md from skills_dir) into system prompt; see Design.md §3.6
    skills_dir: str = "config/skills"  # directory to scan for skill folders (each with SKILL.md)
    skills_top_n_candidates: int = 10  # retrieve/load this many skills first; then threshold; then cap by skills_max_in_prompt
    skills_max_in_prompt: int = 5  # max skills in prompt after threshold (top 10 → threshold → up to 5)
    plugins_top_n_candidates: int = 10  # same for plugins
    plugins_max_in_prompt: int = 5  # max plugins in prompt after threshold (top 10 → threshold → up to 5)
    plugins_description_max_chars: int = 0  # max chars per plugin description in routing block; 0 = no truncation. With RAG or plugins_max_in_prompt we already cap how many plugins appear; this only limits per-item length. Use 0 (default) for full descriptions; set 512 or 300 only if you need to shrink prompt or cap one very long description.
    # Vector retrieval for skills (separate collection from memory); see docs/ToolsSkillsPlugins.md §8
    skills_use_vector_search: bool = False  # when True, retrieve skills by similarity to user query instead of injecting all/first N
    skills_vector_collection: str = "homeclaw_skills"  # Chroma collection name for skills (separate from memory)
    skills_max_retrieved: int = 10  # max skills to retrieve and inject per request when skills_use_vector_search
    skills_similarity_threshold: float = 0.0  # min similarity (0..1); results below are dropped (similarity = 1 - distance for cosine)
    skills_refresh_on_startup: bool = True  # resync skills_dir → vector DB on Core startup when skills_use_vector_search
    skills_test_dir: str = ""  # optional; if set, full sync every time (id = test__<folder>); for testing skills
    skills_incremental_sync: bool = False  # when true, skills_dir only processes folders not already in vector store (new only)
    orchestrator_timeout_seconds: int = 30  # timeout for intent/plugin call and plugin.run(); 0 = no timeout
    tool_timeout_seconds: int = 120  # per-tool execution timeout; prevents one tool from hanging the system; 0 = no timeout (from config tools.tool_timeout_seconds)
    orchestrator_unified_with_tools: bool = True  # when True (default), main LLM with tools routes TAM/plugin/chat; when False, separate orchestrator_handler runs first (one LLM for intent+plugin)
    use_prompt_manager: bool = True  # load prompts from config/prompts (language/model overrides); see docs/PromptManagement.md
    prompts_dir: str = "config/prompts"  # base dir for section/name.lang.model layout
    prompt_default_language: str = "en"  # fallback when lang not in request/metadata
    prompt_cache_ttl_seconds: float = 0  # 0 = cache by mtime only; >0 = TTL in seconds
    auth_enabled: bool = False  # when True, require API key for /inbound and /ws; see RemoteAccess.md
    auth_api_key: str = ""  # key to require (X-API-Key header or Authorization: Bearer <key>); empty = auth disabled
    llm_max_concurrent: int = 1  # max concurrent LLM calls (channel + plugin API); 1 = serialize, avoid backend overload; see PluginLLMAndQueueDesign.md
    knowledge_base: Dict[str, Any] = field(default_factory=dict)  # optional: enabled, collection_name, chunk_size, unused_ttl_days; see docs/MemoryAndDatabase.md
    profile: Dict[str, Any] = field(default_factory=dict)  # optional: enabled, dir (base path for profiles); see docs/UserProfileDesign.md
    result_viewer: Dict[str, Any] = field(default_factory=dict)  # optional: enabled, dir, retention_days, base_url; see docs/ComplexResultViewerDesign.md
    # When true, Core starts and registers all (or allowlisted) plugins in system_plugins/ so one command runs Core + system plugins.
    system_plugins_auto_start: bool = False
    system_plugins: List[str] = field(default_factory=list)  # optional allowlist; empty = start all discovered system plugins
    system_plugins_env: Dict[str, Dict[str, str]] = field(default_factory=dict)  # per-plugin env: plugin_id -> { VAR: "value" }; e.g. homeclaw-browser: { BROWSER_HEADLESS: "false" }
    # When true, on permission denied (unknown user) notify owner via last-used channel so they can add to user.yml. See docs_design/OutboundMarkdownAndUnknownRequest.md.
    notify_unknown_request: bool = False
    # Outbound text format: Core converts assistant reply (Markdown) before sending to channels. "whatsapp" (default) = *bold* _italic_ ~strikethrough~ (works for most IMs); "plain" = strip Markdown; "none" = no conversion.
    outbound_markdown_format: str = "whatsapp"

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
        """Default 5000 when key missing; 0 = no truncation when explicitly set."""
        if raw is None:
            return 5000
        return max(0, int(raw) if raw != '' else 5000)

    @staticmethod
    def from_yaml(yaml_file: str) -> 'CoreMetadata':
        with open(yaml_file, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        
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
        cognee = data.get('cognee')
        if not isinstance(cognee, dict):
            cognee = {}

        return CoreMetadata(
            name=data['name'],
            host=data['host'],
            port=data['port'],
            mode=data['mode'],
            model_path=data['model_path'],
            embedding_llm=data.get('embedding_llm', ''),
            embedding_host=data.get('embedding_host', '127.0.0.1'),
            embedding_port=data.get('embedding_port', 5066),
            embedding_llm_type=data.get('embedding_llm_type', 'local'),
            main_llm_type=data.get('main_llm_type', 'local'),
            main_llm=data.get('main_llm', ''),
            main_llm_host=data.get('main_llm_host', '127.0.0.1'),
            main_llm_port=data.get('main_llm_port', 5088),
            main_llm_language=_normalize_main_llm_language(data.get('main_llm_language', 'en')),
            main_llm_api_key_name=main_llm_api_key_name_val,
            main_llm_api_key=main_llm_api_key_val,
            silent=data.get('silent', False),
            use_memory=data.get('use_memory', True),
            reset_memory=data.get('reset_memory', False),
            memory_backend=(data.get('memory_backend') or 'cognee').strip().lower(),
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
            use_agent_memory_file=bool(data.get('use_agent_memory_file', False)),
            agent_memory_path=(data.get('agent_memory_path') or '').strip(),
            agent_memory_max_chars=max(0, int(data.get('agent_memory_max_chars', 5000) or 0)),
            use_daily_memory=bool(data.get('use_daily_memory', False)),
            daily_memory_dir=(data.get('daily_memory_dir') or '').strip(),
            use_agent_memory_search=bool(data.get('use_agent_memory_search', True)),
            agent_memory_vector_collection=(data.get('agent_memory_vector_collection') or 'homeclaw_agent_memory').strip(),
            session=data.get('session') if isinstance(data.get('session'), dict) else {},
            compaction=data.get('compaction') if isinstance(data.get('compaction'), dict) else {},
            use_tools=data.get('use_tools', False),
            use_skills=data.get('use_skills', False),
            skills_dir=data.get('skills_dir', 'config/skills'),
            skills_top_n_candidates=max(1, min(100, int(data.get('skills_top_n_candidates', 10) or 10))),
            skills_max_in_prompt=max(0, int(data.get('skills_max_in_prompt', 5) or 5)),
            plugins_top_n_candidates=max(1, min(100, int(data.get('plugins_top_n_candidates', 10) or 10))),
            plugins_max_in_prompt=max(0, int(data.get('plugins_max_in_prompt', 5) or 5)),
            plugins_description_max_chars=max(0, int(data.get('plugins_description_max_chars', 0) or 0)),
            skills_use_vector_search=bool(data.get('skills_use_vector_search', False)),
            skills_vector_collection=(data.get('skills_vector_collection') or 'homeclaw_skills').strip(),
            skills_max_retrieved=max(1, min(100, int(data.get('skills_max_retrieved', 10) or 10))),
            skills_similarity_threshold=float(data.get('skills_similarity_threshold', 0.0) or 0.0),
            skills_refresh_on_startup=bool(data.get('skills_refresh_on_startup', True)),
            skills_test_dir=(data.get('skills_test_dir') or '').strip(),
            skills_incremental_sync=bool(data.get('skills_incremental_sync', False)),
            orchestrator_timeout_seconds=int(data.get('orchestrator_timeout_seconds', 30) or 0),
            tool_timeout_seconds=int((data.get('tools') or {}).get('tool_timeout_seconds', 120) or 0),
            orchestrator_unified_with_tools=data.get('orchestrator_unified_with_tools', True),
            use_prompt_manager=data.get('use_prompt_manager', True),
            prompts_dir=(data.get('prompts_dir') or 'config/prompts').strip(),
            prompt_default_language=(data.get('prompt_default_language') or 'en').strip() or 'en',
            prompt_cache_ttl_seconds=float(data.get('prompt_cache_ttl_seconds', 0) or 0),
            auth_enabled=data.get('auth_enabled', False),
            auth_api_key=(data.get('auth_api_key') or '').strip(),
            llm_max_concurrent=max(1, min(32, int(data.get('llm_max_concurrent', 1) or 1))),
            knowledge_base=data.get('knowledge_base') if isinstance(data.get('knowledge_base'), dict) else {},
            profile=data.get('profile') if isinstance(data.get('profile'), dict) else {},
            result_viewer=data.get('result_viewer') if isinstance(data.get('result_viewer'), dict) else {},
            system_plugins_auto_start=bool(data.get('system_plugins_auto_start', False)),
            system_plugins=list(data.get('system_plugins') or []) if isinstance(data.get('system_plugins'), list) else [],
            system_plugins_env=CoreMetadata._normalize_system_plugins_env(data.get('system_plugins_env')),
            notify_unknown_request=bool(data.get('notify_unknown_request', False)),
            outbound_markdown_format=(data.get('outbound_markdown_format') or 'whatsapp').strip().lower() or 'whatsapp',
        )

    # @staticmethod
    # def to_yaml(core: 'CoreMetadata', yaml_file: str):
    #     with open(yaml_file, 'w', encoding='utf-8') as file:
    #         # Convert the core instance to a dictionary
    #         yaml.safe_dump(core.__dict__, file, default_flow_style=False)

    @staticmethod
    def to_yaml(core: 'CoreMetadata', yaml_file: str):
        with open(yaml_file, 'w', encoding='utf-8') as file:
            # Manually prepare a dictionary to serialize
            core_dict = {
                'name': core.name,
                'host': core.host,
                'port': core.port,
                'mode': core.mode,
                'model_path': core.model_path,
                'embedding_host': core.embedding_host,
                'embedding_port': core.embedding_port,
                'main_llm_host': core.main_llm_host,
                'main_llm_port': core.main_llm_port,
                'main_llm_language': core.main_llm_language,
                'main_llm': core.main_llm,
                'silent': core.silent,
                'use_memory': core.use_memory,
                'reset_memory': core.reset_memory,
                'memory_backend': getattr(core, 'memory_backend', 'cognee') or 'cognee',
                'use_workspace_bootstrap': getattr(core, 'use_workspace_bootstrap', True),
                'workspace_dir': getattr(core, 'workspace_dir', 'config/workspace'),
                'use_tools': getattr(core, 'use_tools', False),
                'use_skills': getattr(core, 'use_skills', False),
                'skills_dir': getattr(core, 'skills_dir', 'config/skills'),
                'skills_max_in_prompt': getattr(core, 'skills_max_in_prompt', 0),
                'plugins_max_in_prompt': getattr(core, 'plugins_max_in_prompt', 0),
                'plugins_description_max_chars': getattr(core, 'plugins_description_max_chars', 0),
                'skills_use_vector_search': getattr(core, 'skills_use_vector_search', False),
                'skills_vector_collection': getattr(core, 'skills_vector_collection', 'homeclaw_skills') or 'homeclaw_skills',
                'skills_max_retrieved': getattr(core, 'skills_max_retrieved', 10),
                'skills_similarity_threshold': getattr(core, 'skills_similarity_threshold', 0.0),
                'skills_refresh_on_startup': getattr(core, 'skills_refresh_on_startup', True),
                'skills_test_dir': getattr(core, 'skills_test_dir', '') or '',
                'skills_incremental_sync': getattr(core, 'skills_incremental_sync', False),
                'orchestrator_timeout_seconds': getattr(core, 'orchestrator_timeout_seconds', 30),
                'tool_timeout_seconds': getattr(core, 'tool_timeout_seconds', 120),
                'orchestrator_unified_with_tools': getattr(core, 'orchestrator_unified_with_tools', True),
                'notify_unknown_request': getattr(core, 'notify_unknown_request', False),
                'outbound_markdown_format': getattr(core, 'outbound_markdown_format', 'whatsapp') or 'whatsapp',
                'use_prompt_manager': getattr(core, 'use_prompt_manager', True),
                'prompts_dir': getattr(core, 'prompts_dir', 'config/prompts') or 'config/prompts',
                'prompt_default_language': getattr(core, 'prompt_default_language', 'en') or 'en',
                'prompt_cache_ttl_seconds': getattr(core, 'prompt_cache_ttl_seconds', 0),
                'auth_enabled': getattr(core, 'auth_enabled', False),
                'auth_api_key': getattr(core, 'auth_api_key', '') or '',
                'llm_max_concurrent': getattr(core, 'llm_max_concurrent', 1),
                'embedding_llm': core.embedding_llm,
                'llama_cpp': core.llama_cpp or {},
                'completion': getattr(core, 'completion', {}) or {},
                'local_models': core.local_models or [],
                'cloud_models': [
                    {k: ("***" if k == "api_key" and v else v) for k, v in (m if isinstance(m, dict) else {}).items()}
                    for m in (core.cloud_models or [])
                ],
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
            # Only write api key fields when set (cloud main model; key can be set via CLI)
            if (core.main_llm_api_key_name or '').strip():
                core_dict['main_llm_api_key_name'] = core.main_llm_api_key_name
            if (core.main_llm_api_key or '').strip():
                core_dict['main_llm_api_key'] = core.main_llm_api_key
            yaml.safe_dump(core_dict, file, default_flow_style=False)

 
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
    