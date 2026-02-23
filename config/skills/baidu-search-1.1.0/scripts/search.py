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
_TIMEOUT = 90


def _skill_root() -> Path:
    """Skill folder (baidu-search-1.1.0) containing config.yml and scripts/."""
    return Path(__file__).resolve().parent.parent


def _get_api_key() -> str:
    """API key from (1) skill config.yml (api_key), (2) BAIDU_API_KEY env. Key lives with the skill, not in core.yml."""
    # 1) Environment (allows override without editing skill config)
    key = (os.getenv("BAIDU_API_KEY") or "").strip()
    if key:
        return key
    # 2) Skill-level config: <skill_dir>/config.yml
    config_yml = _skill_root() / "config.yml"
    if config_yml.is_file():
        try:
            import yaml
            with open(config_yml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            key = (data.get("api_key") or "").strip()
            if key:
                return key
        except Exception:
            pass
    return ""


def ai_search(api_key: str, body: dict) -> dict:
    """
    Call Baidu 智能搜索生成 (AI Search). Returns dict with summary and references.
    Raises on HTTP error or when API returns error code in body.
    """
    headers = {
        "Authorization": "Bearer %s" % api_key,
        "X-Appbuilder-From": "homeclaw",
        "Content-Type": "application/json",
    }
    resp = requests.post(_API_URL, json=body, headers=headers, timeout=_TIMEOUT)
    try:
        data = resp.json() if resp.text else {}
    except Exception:
        data = {}

    # API can return 200 or 4xx with error in body (e.g. code 216003 = auth error)
    code = data.get("code")
    if code is not None and code != 0:
        msg = data.get("message") or data.get("error_msg") or "API error"
        raise RuntimeError("Baidu API error (code %s): %s" % (code, msg))

    resp.raise_for_status()

    choices = data.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    content = (message.get("content") or "").strip()
    references = data.get("references") or []

    return {"summary": content, "references": references, "usage": data.get("usage")}


def main() -> None:
    def fail(msg: str) -> None:
        print(msg, file=sys.stderr)
        print("Error: " + msg)
        sys.exit(1)

    if len(sys.argv) < 2:
        fail(
            "Usage: python search.py '<JSON>'  e.g.  python search.py '{\"query\": \"search terms\"}'"
        )
        return

    raw = (sys.argv[1] or "").strip()
    try:
        params = json.loads(raw) if raw.startswith("{") else {"query": raw}
    except json.JSONDecodeError:
        params = {"query": raw}

    query = (params.get("query") or "").strip()
    if not query:
        fail(
            'Pass a JSON string with "query" or a plain search query as the first argument.'
        )
        return

    api_key = _get_api_key()
    if not api_key:
        fail(
            "Baidu AI Search requires an API key. Set it in this skill's config: "
            "config/skills/baidu-search-1.1.0/config.yml (api_key: \"your-key\"), "
            "or set BAIDU_API_KEY in the environment. "
            "Get a key from Baidu Qianfan: https://cloud.baidu.com/doc/qianfan-api/s/Hmbu8m06u"
        )
        return

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
                err_body = (e.response.text or "")[:500]
        status = e.response.status_code if e.response else "?"
        fail("HTTP %s: %s" % (status, err_body or str(e)))
    except RuntimeError as e:
        msg = str(e)
        if "216003" in msg or "Authentication" in msg or "apikey" in msg.lower():
            fail(
                msg + " Check that api_key in config/skills/baidu-search-1.1.0/config.yml or BAIDU_API_KEY is set and valid (Baidu Qianfan console)."
            )
        fail(msg)
    except Exception as e:
        fail(str(e))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print("Error: %s" % e)
        sys.exit(1)
