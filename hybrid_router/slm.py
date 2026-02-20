"""
Layer 3: Small local classifier (llama.cpp on a separate port).
Calls the classifier model's /v1/chat/completions with a short judge prompt;
parses "Local" or "Cloud" from the response. Reuses existing llama.cpp server mechanism.
"""
import re
from typing import Optional, Tuple
import aiohttp


# Default judge prompt: short, clear instruction so a small model can answer Local vs Cloud.
DEFAULT_JUDGE_PROMPT = """You are a router. Does this user request need real-time internet search, latest news, or complex reasoning that benefits from a large cloud model? Answer with exactly one word: Cloud or Local.

User request:
"""
DEFAULT_JUDGE_PROMPT_ZH = """你是路由器。这个用户请求是否需要实时网络搜索、最新新闻或复杂推理（适合用大模型）？只回答一个词：Cloud 或 Local。

用户请求：
"""


async def run_slm_layer_async(
    query: str,
    host: str,
    port: int,
    model: str,
    threshold: float = 0.5,
    judge_prompt: Optional[str] = None,
    timeout_sec: float = 30.0,
) -> Tuple[float, Optional[str]]:
    """
    Run Layer 3 classifier: POST to host:port /v1/chat/completions with judge prompt + user message.
    Parse response for "Local" or "Cloud" (case-insensitive). Return (score, selection).
    selection is "local" | "cloud" or None on parse failure or error.
    If threshold > 0, we still return the parsed selection with score 1.0 when we get a valid answer;
    caller compares score >= threshold. If threshold is 0, any valid Local/Cloud is used.
    """
    if not query or not isinstance(query, str):
        return (0.0, None)
    if not host or not str(port).strip():
        return (0.0, None)
    port = int(port)
    prompt = (judge_prompt or DEFAULT_JUDGE_PROMPT).strip() + "\n" + (query.strip() or "")
    url = f"http://{host}:{port}/v1/chat/completions"
    body = {
        "model": model or "classifier",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16,
        "temperature": 0.0,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=body) as resp:
                if resp.status != 200:
                    return (0.0, None)
                data = await resp.json()
    except Exception:
        return (0.0, None)
    content = None
    if isinstance(data, dict) and "choices" in data and isinstance(data["choices"], list) and data["choices"]:
        msg = data["choices"][0].get("message") or {}
        content = (msg.get("content") or "").strip()
    if not content:
        return (0.0, None)
    # Parse "Local" or "Cloud" (allow lowercase, allow trailing punctuation)
    content_lower = content.lower().strip()
    if re.search(r"\bcloud\b", content_lower):
        return (1.0, "cloud")
    if re.search(r"\blocal\b", content_lower):
        return (1.0, "local")
    return (0.0, None)


def resolve_slm_model_ref(slm_model_ref: str):
    """
    Resolve hybrid_router.slm.model (e.g. local_models/classifier_0_5b) to (host, port, path_relative, raw_id).
    path_relative is for starting the server (relative to models_path); raw_id is for the request body 'model' field.
    Returns (host, port, path_relative, raw_id) or (None, None, None, None) if not found or not local.
    """
    from base.util import Util
    ref = (slm_model_ref or "").strip()
    if not ref:
        return (None, None, None, None)
    entry, mtype = Util()._get_model_entry(ref)
    if entry is None or mtype != "local":
        return (None, None, None, None)
    host = entry.get("host", "127.0.0.1")
    port = int(entry.get("port", 5089))
    path_rel = (entry.get("path") or "").strip()
    _, raw_id = Util()._parse_model_ref(ref)
    raw_id = raw_id or ref
    return (host, port, path_rel, raw_id)
