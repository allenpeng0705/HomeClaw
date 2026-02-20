"""
Layer 3 (optional): Perplexity / confidence probe using the main local model.

When hybrid_router.slm.mode == "perplexity", we call the main local model (llama.cpp
server) with a short probe: max_tokens=5 and logprobs=true. The average log probability
of the generated tokens indicates how "confident" the model is. Above threshold → local;
below → escalate to cloud. See docs_design/StrongLocalModelAndPerplexityRouting.md.
"""
from typing import Optional, Tuple
import aiohttp


async def run_perplexity_probe_async(
    query: str,
    host: str,
    port: int,
    model: str,
    *,
    max_tokens: int = 5,
    threshold: float = -0.6,
    timeout_sec: float = 5.0,
) -> Tuple[float, Optional[str]]:
    """
    Probe the local model with the user message; request max_tokens with logprobs.
    Returns (score, selection). selection is "local" | "cloud" or None on error.
    - If avg logprob >= threshold: return (1.0, "local") (model is confident).
    - If avg logprob < threshold: return (0.0, "cloud") (escalate to cloud).
    - On timeout, parse error, or missing logprobs: return (0.0, None) so caller uses default_route.
    """
    if not query or not isinstance(query, str):
        return (0.0, None)
    if not host or port is None:
        return (0.0, None)
    port = int(port)
    url = f"http://{host}:{port}/v1/chat/completions"
    body = {
        "model": model or "default",
        "messages": [{"role": "user", "content": (query or "").strip()}],
        "max_tokens": max(1, min(20, int(max_tokens))),
        "temperature": 0.0,
        "logprobs": True,
        "top_logprobs": 1,
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
    # OpenAI-compatible: choices[0].logprobs.content = list of { "token", "logprob", ... }
    logprobs_list = []
    if isinstance(data, dict) and "choices" in data and isinstance(data["choices"], list) and data["choices"]:
        choice = data["choices"][0]
        logprobs = choice.get("logprobs")
        if isinstance(logprobs, dict) and "content" in logprobs:
            content = logprobs["content"]
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "logprob" in item:
                        lp = item["logprob"]
                        if lp is not None and isinstance(lp, (int, float)):
                            logprobs_list.append(float(lp))
    if not logprobs_list:
        return (0.0, None)
    avg_logprob = sum(logprobs_list) / len(logprobs_list)
    if avg_logprob >= threshold:
        return (1.0, "local")
    return (0.0, "cloud")


def resolve_local_model_ref(model_ref: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Resolve a local model ref (e.g. main_llm_local) to (host, port, raw_id) for the probe.
    Returns (None, None, None) if not found or not a local model.
    """
    ref = (model_ref or "").strip()
    if not ref:
        return (None, None, None)
    from hybrid_router.slm import resolve_slm_model_ref
    host, port, _path_rel, raw_id = resolve_slm_model_ref(ref)
    return (host, port, raw_id)
