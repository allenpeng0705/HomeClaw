---
name: baidu-search
description: "Use Baidu Qianfan 智能搜索生成 to search and get an AI-written summary in one call. Use this skill when the user asks for Baidu or 百度搜索. For generic 'search the web' or 'search for X' without mentioning Baidu, use the web_search tool instead."
trigger:
  patterns: ["百度搜索|百度.*搜|Baidu\\s+search|智能搜索|用百度搜|baidu\\s+搜"]
  instruction: "The user asked for Baidu search or 百度/智能搜索. Use run_skill(skill_name='baidu-search-1.1.0', script='search.py', args=['{\"query\": \"<search terms>\"}']). For plain 'search the web' or 'search for X' without mentioning Baidu, use the web_search tool instead."
  auto_invoke:
    script: search.py
    args: ["{{query}}"]
---

# Baidu AI Search (智能搜索生成)

Uses Baidu Qianfan **智能搜索生成** API: search the web and get an **AI-written summary** plus references in one call.  
**When to use which:** Use **this skill** when the user asks for **Baidu** or **百度搜索**. For generic "search the web", "search for X", or "look up Y" use the built-in **web_search** tool (Tavily/DuckDuckGo/etc.) instead.  
**Skill folder name for run_skill:** `baidu-search-1.1.0`.  
API reference: [智能搜索生成](https://cloud.baidu.com/doc/qianfan-api/s/Hmbu8m06u).

## API key (required)

**The key is configured with the skill**, not in core.yml. Set one of:

1. **Skill config (recommended):** In this skill's folder edit `config/skills/baidu-search-1.1.0/config.yml` and set:
   ```yaml
   api_key: "your-baidu-qianfan-api-key"
   ```
2. **Environment:** `BAIDU_API_KEY` where Core runs (overrides skill config if set).

Get a key from [Baidu Qianfan](https://cloud.baidu.com/doc/qianfan-api/s/Hmbu8m06u) (千帆 AI 应用开发者中心). If you see "Authentication error" or code 216003, the key is missing or invalid.

## When to use this skill vs web_search (built-in tool)

| User says | Use | Why |
|------------|-----|-----|
| "百度搜索 X", "用百度搜", "Baidu search for X", "智能搜索" | **This skill** (baidu-search-1.1.0) | User explicitly wants Baidu or AI-summarized search in one step. |
| "search the web for X", "search for X", "look up X", "google X" | **web_search** tool | Generic web search; built-in tool (Tavily/DuckDuckGo/etc.) returns raw results for you to summarize. |

Do not use this skill for generic "search the web" or "search for" — use the **web_search** tool instead.

## Run via run_skill

**run_skill(skill_name=`baidu-search-1.1.0`, script=`search.py`, args=[\"{\\\"query\\\": \\\"your search terms\\\"}\"])**

First argument: **JSON string** with at least `"query"`. Examples:
- `args: ["{\"query\": \"人工智能\"}"]`
- `args: ["{\"query\": \"最新新闻\", \"search_recency_filter\": \"week\"}"]`
- `args: ["{\"query\": \"北京景点\", \"model\": \"ernie-4.5-turbo-32k\", \"enable_deep_search\": true}"]`

## Response

The script returns a JSON object:
- **summary**: AI-generated answer (text) based on search results.
- **references**: List of sources (title, url, content snippet, date, type: web/video/image).
- **usage**: Token usage if returned by the API.

## Request parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| query | str | yes | - | Search query (user question or keywords). |
| model | str | no | ernie-4.5-turbo-32k | Qianfan model for summarization. Other options: ernie-4.5-turbo-128k, deepseek-r1, deepseek-v3. |
| search_source | str | no | baidu_search_v2 | `baidu_search_v1` or `baidu_search_v2` (v2 recommended). |
| resource_type_filter | list | no | [{"type":"web","top_k":20}] | For v2: web (top_k ≤20), video (top_k ≤20). |
| search_recency_filter | str | no | year | Time filter: `week`, `month`, `semiyear`, `year`. |
| search_filter | obj | no | {} | V2 only: e.g. `{"match":{"site":["news.baidu.com"]}}`. |
| search_mode | str | no | auto | `auto` (decide if search needed), `required`, `disabled`. |
| enable_deep_search | bool | no | false | If true, more search rounds (up to ~10); more refs, higher cost. |
| enable_reasoning | bool | no | true | Deep reasoning for DeepSeek-R1 / 文心X1. |
| instruction | str | no | - | System instruction / style (max 4000 chars). |
| temperature | float | no | - | Sampling (0, 1]. |
| top_p | float | no | - | Sampling diversity. |
| safety_level | str | no | standard | `standard` or `strict`. |
| max_completion_tokens | int | no | - | Max output tokens. |

## Examples

```bash
# Basic: query only
python search.py '{"query":"北京有哪些景点"}'

# Recent week + site filter
python search.py '{"query":"最新新闻","search_recency_filter":"week","search_filter":{"match":{"site":["news.baidu.com"]}}}'

# Deep search + custom model
python search.py '{"query":"人工智能发展趋势","model":"ernie-4.5-turbo-128k","enable_deep_search":true}'
```

## Status

Uses 智能搜索生成 (chat/completions) endpoint; returns summary + references.
