"""
Friends external plugin — HTTP server with single capability "chat".
All persona settings (name, character, language, response_length, idle_days) live in this plugin only; Core only routes.
Stores chat only in friends store; uses Core's LLM via POST /api/plugins/llm/generate.
Run: python -m external_plugins.friends.server
Then register with Core: python -m external_plugins.friends.register
"""
import os
import sys
from pathlib import Path

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import uvicorn
import yaml
from fastapi import FastAPI
from typing import Dict, Any

from external_plugins.friends import store

app = FastAPI()

_FRIENDS_CONFIG: Dict[str, Any] = {}


def _load_plugin_config() -> Dict[str, Any]:
    """Load plugin config from config.yml (next to this file). Env overrides: FRIENDS_NAME, FRIENDS_PERSONA_NAME, etc."""
    global _FRIENDS_CONFIG
    if _FRIENDS_CONFIG:
        return _FRIENDS_CONFIG
    config_path = Path(__file__).resolve().parent / "config.yml"
    out = {
        "name": (os.environ.get("FRIENDS_PERSONA_NAME") or os.environ.get("FRIENDS_NAME") or "Veda").strip() or "Veda",
        "character": "friend",
        "language": "en",
        "response_length": "medium",
        "idle_days_before_nudge": 0,
    }
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for k in ("name", "character", "language", "response_length", "idle_days_before_nudge"):
                if k in data and data[k] is not None:
                    if k == "idle_days_before_nudge":
                        out[k] = max(0, int(data[k]))
                    else:
                        out[k] = str(data[k]).strip().lower() if k != "name" else str(data[k]).strip()
        except Exception:
            pass
    if os.environ.get("FRIENDS_PERSONA_NAME") or os.environ.get("FRIENDS_NAME"):
        out["name"] = (os.environ.get("FRIENDS_PERSONA_NAME") or os.environ.get("FRIENDS_NAME") or "").strip() or out["name"]
    _FRIENDS_CONFIG.update(out)
    return _FRIENDS_CONFIG


def _persona_name_from_request(_body: Dict[str, Any]) -> str:
    """Persona name: from plugin config only (Core does not pass it)."""
    return _load_plugin_config().get("name") or "Veda"


def _merge_friends_settings(user_id: str, _body: Dict[str, Any]) -> Dict[str, Any]:
    """Merge plugin config (defaults) with per-user settings. Per-user overrides."""
    defaults = {
        "character": (_load_plugin_config().get("character") or "friend").strip().lower(),
        "language": (_load_plugin_config().get("language") or "en").strip().lower(),
        "response_length": (_load_plugin_config().get("response_length") or "medium").strip().lower(),
        "idle_days_before_nudge": max(0, int(_load_plugin_config().get("idle_days_before_nudge") or 0)),
    }
    user_settings = store.get_user_settings(user_id)
    for k in ("character", "language", "response_length", "idle_days_before_nudge"):
        if k in user_settings and user_settings[k] is not None:
            if k == "idle_days_before_nudge":
                defaults[k] = max(0, int(user_settings[k]))
            else:
                defaults[k] = str(user_settings[k]).strip().lower() if user_settings[k] else defaults[k]
    return defaults


# Character defines who the persona is to the user — central to making the friend interesting and useful.
CHARACTER_ROLES = {
    "girlfriend": "the user's girlfriend. Be warm, affectionate, supportive, and emotionally attuned. Match their energy; be playful when they are, calm when they need it.",
    "boyfriend": "the user's boyfriend. Be warm, caring, supportive, and present. Show interest in their day; be steady and reassuring when they need it.",
    "wife": "the user's wife. Be loving, supportive, and a steady presence. You share a life together; be thoughtful and sometimes gently humorous.",
    "husband": "the user's husband. Be caring, supportive, and steady. You're in their corner; be attentive and reassuring.",
    "sister": "the user's sister. Be caring, sometimes playful, and supportive. You can tease a little and be real with them.",
    "brother": "the user's brother. Be supportive, friendly, and have their back. Keep it real; a bit of humor is fine.",
    "child": "the user's child. Be warm, respectful, and loving. Show that you care about them and look up to them.",
    "friend": "the user's close friend. Be warm, conversational, and supportive. Listen well; be someone they can relax and be themselves with.",
    "parent": "the user's parent. Be caring, wise, and supportive. Offer a steady, nurturing presence without being overbearing.",
}

LANGUAGE_INSTRUCTIONS = {
    "en": "Reply in English only.",
    "zh": "只用中文回复。",
    "ja": "必ず日本語で返答してください。",
    "ko": "반드시 한국어로 답변하세요.",
    "es": "Responde solo en español.",
    "fr": "Réponds uniquement en français.",
    "de": "Antworte nur auf Deutsch.",
    "pt": "Responda apenas em português.",
    "it": "Rispondi solo in italiano.",
    "ru": "Отвечай только на русском языке.",
    "ar": "رد بالعربية فقط.",
}


def _language_instruction(lang: str) -> str:
    if not lang:
        return "Reply in English."
    key = lang.lower()[:2] if len(lang) >= 2 else lang.lower()
    return LANGUAGE_INSTRUCTIONS.get(key) or f"Always reply in {lang}."


def _response_length_instruction(length: str) -> str:
    if length == "short":
        return "Keep replies brief: one or two sentences unless the user asks for more."
    if length == "long":
        return "You may reply at length when the topic deserves it; be thorough but natural."
    return "Keep replies to a short paragraph unless the user asks for more or less."


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/settings/{user_id}")
def get_settings(user_id: str):
    """Get per-user friends settings (character, language, response_length, idle_days_before_nudge)."""
    return store.get_user_settings(user_id or "default")


@app.post("/settings/{user_id}")
def post_settings(user_id: str, body: Dict[str, Any]):
    """Update per-user friends settings. Body: { character?, language?, response_length?, idle_days_before_nudge? }. Omitted keys are unchanged."""
    user_id = (user_id or "default").strip() or "default"
    store.set_user_settings(user_id, body or {})
    return {"ok": True, "settings": store.get_user_settings(user_id)}


def _build_messages(user_id: str, user_input: str, persona_name: str, settings: Dict[str, Any], memory_context: str = "") -> list:
    """Build messages for LLM. Character and language define who the persona is and how they reply. memory_context is injected from Core RAG if enabled."""
    history = store.get_history(user_id, persona_name, num_rounds=10)
    character = settings.get("character") or "friend"
    role_desc = CHARACTER_ROLES.get(character) or CHARACTER_ROLES["friend"]
    lang_inst = _language_instruction(settings.get("language") or "en")
    length_inst = _response_length_instruction(settings.get("response_length") or "medium")
    system = (
        f"You are {persona_name}, {role_desc}\n"
        f"Language: {lang_inst}\n"
        f"Length: {length_inst}\n"
        "Stay in character and be natural and conversational."
    )
    if memory_context and memory_context.strip():
        system += "\n\nRelevant things you remember about the user (use naturally in conversation):\n" + memory_context.strip()
    messages = [{"role": "system", "content": system}]
    for t in history:
        messages.append({"role": t["role"], "content": t["content"]})
    messages.append({"role": "user", "content": user_input})
    return messages


# When the Companion app is in system mode (not combined with a user), Core sends user_id "companion" to the plugin. Use a dedicated Core memory user_id for that case so Friend memories are never mixed with Assistant (Companion app talking to Core with user_id "companion").
MEMORY_USER_FRIEND = "companion_friend"


def _core_headers() -> Dict[str, str]:
    """Headers for Core API (memory, LLM)."""
    api_key = os.environ.get("CORE_API_KEY", "").strip()
    h = {"Content-Type": "application/json"}
    if api_key:
        h["X-API-Key"] = api_key
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _memory_user_id(user_id: str) -> str:
    """When app is in system mode (Core sends user_id 'companion'), use dedicated memory user so Friend memories are not mixed with Assistant."""
    return MEMORY_USER_FRIEND if (user_id or "").strip().lower() == "companion" else (user_id or "").strip() or "default"


async def _call_core_memory_add(user_id: str, text: str, user_name: str = "", app_id: str = "homeclaw") -> bool:
    """Add user message to Core RAG memory. Returns True if added or memory disabled; False on error. Uses companion_friend when app is in system mode to avoid mixing with Assistant."""
    try:
        import httpx
    except ImportError:
        return False
    mem_uid = _memory_user_id(user_id)
    core_url = os.environ.get("CORE_URL", "http://127.0.0.1:9000").rstrip("/")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{core_url}/api/plugins/memory/add",
            json={"user_id": mem_uid, "text": text, "user_name": user_name or mem_uid, "app_id": app_id},
            headers=_core_headers(),
        )
        if r.status_code in (200, 400):
            data = r.json() if r.text else {}
            return data.get("ok", False) or "Memory not enabled" in str(data.get("error", ""))
        return False


async def _call_core_memory_search(user_id: str, query: str, limit: int = 8) -> list:
    """Search Core RAG memory for user_id. Returns list of {memory, score}. Uses companion_friend when app is in system mode (user_id 'companion')."""
    try:
        import httpx
    except ImportError:
        return []
    mem_uid = _memory_user_id(user_id)
    core_url = os.environ.get("CORE_URL", "http://127.0.0.1:9000").rstrip("/")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{core_url}/api/plugins/memory/search",
            json={"user_id": mem_uid, "query": query, "app_id": "homeclaw", "limit": limit},
            headers=_core_headers(),
        )
        if r.status_code != 200:
            return []
        data = r.json() if r.text else {}
        return data.get("memories") or []


async def _call_core_llm(messages: list) -> str:
    """Call Core POST /api/plugins/llm/generate. Returns generated text or raises."""
    try:
        import httpx
    except ImportError:
        return "Error: install httpx to use Core LLM."
    core_url = os.environ.get("CORE_URL", "http://127.0.0.1:9000").rstrip("/")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{core_url}/api/plugins/llm/generate",
            json={"messages": messages, "llm_name": None},
            headers=_core_headers(),
        )
        if r.status_code != 200:
            return f"Friends plugin could not reach Core (HTTP {r.status_code})."
        data = r.json()
        if isinstance(data.get("error"), str):
            return data.get("error", "Unknown error")
        return (data.get("text") or "").strip()


@app.post("/run")
async def run(body: Dict[str, Any]):
    """Accept PluginRequest; capability_id 'chat' → persona reply. Return PluginResult."""
    request_id = (body.get("request_id") or "").strip()
    plugin_id = (body.get("plugin_id") or "friends").strip()
    user_id = (body.get("user_id") or "").strip() or "default"
    user_name = (body.get("user_name") or "").strip() or user_id
    user_input = (body.get("user_input") or "").strip()
    cap_id = ((body.get("capability_id") or "").strip().lower().replace(" ", "_")) or "chat"
    persona_name = _persona_name_from_request(body)
    settings = _merge_friends_settings(user_id, body)

    if cap_id != "chat":
        return {
            "request_id": request_id,
            "plugin_id": plugin_id,
            "success": False,
            "text": "",
            "error": f"Unknown capability: {cap_id}",
            "metadata": {},
        }

    if not user_input:
        return {
            "request_id": request_id,
            "plugin_id": plugin_id,
            "success": False,
            "text": "",
            "error": "user_input is required",
            "metadata": {},
        }

    await _call_core_memory_add(user_id, user_input, user_name=user_name, app_id="homeclaw")
    memory_list = await _call_core_memory_search(user_id, user_input, limit=8)
    memory_context = "\n".join((m.get("memory") or "").strip() for m in memory_list if (m.get("memory") or "").strip())[:2000]
    messages = _build_messages(user_id, user_input, persona_name, settings, memory_context=memory_context)
    try:
        reply = await _call_core_llm(messages)
    except Exception as e:
        return {
            "request_id": request_id,
            "plugin_id": plugin_id,
            "success": False,
            "text": "",
            "error": str(e),
            "metadata": {},
        }

    store.append_turn(user_id, persona_name, user_input, reply)
    return {
        "request_id": request_id,
        "plugin_id": plugin_id,
        "success": True,
        "text": reply,
        "error": None,
        "metadata": {},
    }


if __name__ == "__main__":
    port = int(os.environ.get("FRIENDS_PORT", "3103"))
    uvicorn.run(app, host="0.0.0.0", port=port)
