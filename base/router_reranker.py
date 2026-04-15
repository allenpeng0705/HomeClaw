from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import aiohttp

_RESOLVE_LOG_CACHE: Dict[Tuple[str, str], Tuple[str, int, str, str]] = {}


def _build_prompt(query: str, candidates: List[Dict[str, str]]) -> str:
    lines = [
        "You are a reranker.",
        "Given one user query and candidate items, score each candidate from 0.0 to 1.0 by relevance.",
        "Return ONLY JSON object: {\"scores\": [{\"id\": \"...\", \"score\": 0.0}]}",
        "No markdown. No explanation.",
        "",
        f"Query: {query.strip()}",
        "",
        "Candidates:",
    ]
    for c in candidates:
        cid = str(c.get("id") or "").strip()
        text = str(c.get("text") or "").strip()
        lines.append(f"- id={cid} text={text[:1200]}")
    return "\n".join(lines)


def _parse_scores(content: str) -> Dict[str, float]:
    try:
        s = (content or "").strip()
        if not s:
            return {}
        # tolerate wrapped prose by extracting first JSON object
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            s = s[start : end + 1]
        obj = json.loads(s)
        out: Dict[str, float] = {}
        arr = obj.get("scores") if isinstance(obj, dict) else None
        if not isinstance(arr, list):
            return out
        for it in arr:
            if not isinstance(it, dict):
                continue
            cid = str(it.get("id") or "").strip()
            if not cid:
                continue
            try:
                score = float(it.get("score"))
            except (TypeError, ValueError):
                continue
            out[cid] = max(0.0, min(1.0, score))
        return out
    except Exception:
        return {}


async def rerank_with_local_model(
    *,
    query: str,
    candidates: List[Dict[str, str]],
    reranker_cfg: Dict[str, Any],
) -> Dict[str, float]:
    """
    candidates: [{id, text}]
    reranker_cfg: {enabled, host, port, model, timeout_seconds}
    """
    if not isinstance(reranker_cfg, dict) or not reranker_cfg.get("enabled"):
        return {}
    model_ref = str(reranker_cfg.get("model_ref") or reranker_cfg.get("model") or "local_models/classifier_0_6b").strip()
    host = str(reranker_cfg.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = max(1, min(65535, int(reranker_cfg.get("port") or 5033)))
    except (TypeError, ValueError):
        port = 5033
    model = model_ref
    # Preferred path: resolve reranker from llm.yml local_models entry (same style as slm classifier).
    try:
        from hybrid_router.slm import resolve_slm_model_ref

        r_host, r_port, _path_rel, r_model = resolve_slm_model_ref(model_ref)
        if r_host is not None and r_port is not None and r_model:
            host = str(r_host).strip() or host
            port = int(r_port)
            model = str(r_model).strip() or model
    except Exception:
        pass
    try:
        _tag = str(reranker_cfg.get("log_tag") or "router").strip() or "router"
        _k = (_tag, model_ref)
        _curr = (host, int(port), model, model_ref)
        _prev = _RESOLVE_LOG_CACHE.get(_k)
        if _prev != _curr:
            from loguru import logger

            logger.info(
                "{} reranker resolved: model_ref={} -> host={} port={} model={}",
                _tag,
                model_ref,
                host,
                port,
                model,
            )
            _RESOLVE_LOG_CACHE[_k] = _curr
    except Exception:
        pass
    try:
        timeout_sec = float(reranker_cfg.get("timeout_seconds") or 8)
    except (TypeError, ValueError):
        timeout_sec = 8.0
    if not query or not candidates:
        return {}

    prompt = _build_prompt(query, candidates)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
        "temperature": 0.0,
    }
    try:
        from base.util import Util

        u = Util()
        panda = u.panda_openai_chat_url("local")
        if panda:
            url = panda
        else:
            url = f"http://{host}:{port}{u.openai_chat_completions_path('local')}"
    except Exception:
        url = f"http://{host}:{port}/v1/chat/completions"

    try:
        from base.util import Util

        sem = Util()._get_llm_semaphore("local")
        async with sem:
            timeout = aiohttp.ClientTimeout(total=timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=body) as resp:
                    if resp.status != 200:
                        return {}
                    data = await resp.json()
    except Exception:
        return {}

    try:
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            return {}
        msg = choices[0].get("message") or {}
        content = (msg.get("content") or "").strip()
        return _parse_scores(content)
    except Exception:
        return {}


def apply_rerank_scores(
    base_hits: List[Tuple[str, float]],
    rerank_scores: Dict[str, float],
    alpha: float = 0.55,
) -> List[Tuple[str, float]]:
    if not base_hits:
        return []
    if not rerank_scores:
        return base_hits
    out: List[Tuple[str, float]] = []
    for cid, score in base_hits:
        rs = rerank_scores.get(cid)
        if rs is None:
            out.append((cid, score))
            continue
        combined = (1.0 - alpha) * float(score) + alpha * float(rs)
        out.append((cid, max(0.0, min(1.0, combined))))
    out.sort(key=lambda x: x[1], reverse=True)
    return out

