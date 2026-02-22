#!/usr/bin/env python3
"""
Baidu AI Search (智能搜索生成) via Qianfan API.
Uses POST /v2/ai_search/chat/completions: search + AI summarization.
Doc: https://cloud.baidu.com/doc/qianfan-api/s/Hmbu8m06u

Usage: python search.py '<JSON>'
  JSON must include "query". Optional: model, search_source, resource_type_filter,
  search_recency_filter, search_filter, instruction, stream, enable_deep_search, etc.
"""
import json
import os
import sys
from pathlib import Path

import requests

_API_URL = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"


def _get_api_key():
    """BAIDU_API_KEY from environment, or from config/core.yml tools.baidu_api_key."""
    key = (os.getenv("BAIDU_API_KEY") or "bce-v3/ALTAK-xMqTr4gbFSEXU5qFZMcLp/50685eb84cb5306d57405d0bfd265270194587c6").strip()
    if key:
        return key
    try:
        script_dir = Path(__file__).resolve().parent
        root = script_dir.parent.parent.parent.parent
        core_yml = root / "config" / "core.yml"
        if core_yml.is_file():
            import yaml
            with open(core_yml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            tools = data.get("tools") or {}
            key = (tools.get("baidu_api_key") or "").strip()
            if key:
                return key
    except Exception:
        pass
    return ""


def ai_search(api_key: str, body: dict) -> dict:
    """
    Call Baidu 智能搜索生成 (AI Search). Returns dict with summary and references.
    """
    headers = {
        "Authorization": "Bearer %s" % api_key,
        "X-Appbuilder-From": "homeclaw",
        "Content-Type": "application/json",
    }
    resp = requests.post(_API_URL, json=body, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code"):
        raise RuntimeError(data.get("message", "API error"))

    # Response: choices[0].message.content (summary), references (list of refs)
    choices = data.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    content = (message.get("content") or "").strip()
    references = data.get("references") or []

    return {"summary": content, "references": references, "usage": data.get("usage")}


def main():
    if len(sys.argv) < 2:
        print("Usage: python search.py '<JSON>'  e.g.  python search.py '{\"query\": \"search terms\"}'")
        sys.exit(1)

    raw = sys.argv[1].strip()
    try:
        params = json.loads(raw) if raw.startswith("{") else {"query": raw}
    except json.JSONDecodeError:
        params = {"query": raw}

    query = (params.get("query") or "").strip()
    if not query:
        print("Error: pass a JSON string with \"query\" or a plain search query as the first argument.")
        sys.exit(1)

    api_key = _get_api_key()
    if not api_key:
        print(
            "Error: Baidu AI Search requires an API key. Set BAIDU_API_KEY in the environment where Core runs, "
            "or in config/core.yml under tools: baidu_api_key: \"your-key\". "
            "Get a key from Baidu Qianfan: https://cloud.baidu.com/doc/qianfan-api/s/Hmbu8m06u"
        )
        sys.exit(1)

    # Build request per 智能搜索生成 API (qianfan doc)
    # When "model" is set = 智能搜索生成 (search + LLM summary); when omitted = 百度搜索 (raw search)
    body = {
        "messages": [{"role": "user", "content": query}],
        "stream": False,
        "model": params.get("model") or "ernie-4.5-turbo-32k",
        "search_source": params.get("search_source") or "baidu_search_v2",
        "resource_type_filter": params.get("resource_type_filter") or [{"type": "web", "top_k": 20}],
        "search_recency_filter": params.get("search_recency_filter") or "year",
        "search_filter": params.get("search_filter") or {},
        "search_mode": params.get("search_mode") or "auto",
        "enable_deep_search": bool(params.get("enable_deep_search", False)),
        "enable_reasoning": bool(params.get("enable_reasoning", True)),
        "enable_corner_markers": bool(params.get("enable_corner_markers", True)),
    }
    if params.get("instruction") is not None:
        body["instruction"] = str(params["instruction"])[:4000]
    if params.get("temperature") is not None:
        body["temperature"] = float(params["temperature"])
    if params.get("top_p") is not None:
        body["top_p"] = float(params["top_p"])
    if params.get("safety_level") is not None:
        body["safety_level"] = str(params["safety_level"])
    if params.get("max_completion_tokens") is not None:
        body["max_completion_tokens"] = int(params["max_completion_tokens"])

    try:
        result = ai_search(api_key, body)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except requests.HTTPError as e:
        err_body = ""
        if e.response is not None and e.response.text:
            try:
                err_body = json.dumps(json.loads(e.response.text), ensure_ascii=False)
            except Exception:
                err_body = e.response.text[:500]
        print(f"Error: HTTP {e.response.status_code if e.response else '?'}: {err_body or str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
