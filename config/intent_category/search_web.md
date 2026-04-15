---
id: search_web
display_name: Web search
enabled: true
priority: 55
classifier_description: "Look up facts, documentation, errors, prices, or current events on the public web using keywords — not a file already in the workspace and not only a single pasted URL."

category_tools:
  profile: minimal
---

## Description
The user wants **information from the public internet**: search-engine style queries, “what is X”, “latest Y”, troubleshooting errors, official docs, tutorials, product comparisons, or **verify** something that is not (only) in a local file they named. Cues: *search*, *google*, *look up*, *查一下*, *网上*, *帮我搜*. The intent is **discovery or verification online**, not primarily **opening one URL** they already provided (see **open_url**).

## Positive examples
- “Latest Python 3.12 release notes.”
- “What’s the capital of Mongolia?”
- “Does Home Assistant support Matter in 2025?”
- “帮我搜一下这个报错是什么意思”
- “Docker permission denied linux fix”
- “Current CEO of …” / “When did … ship?”
- “帮我上网查一下伊美冲突最新进展（给我要点）”
- “Find the latest official docs for LiteLLM retries.”

## Negative boundaries
- **read_document** / **list_files**: User points at **local paths** or **sandbox files** as the source (“read `docs/x.md`”, “what’s in `share/`”).
- **open_url**: User supplied a **full http(s) URL** and wants that **page** opened or fetched — not a broad keyword search.
- **news_digest**: **RSS / daily brief / 简报** product — not a one-off fact lookup.
- **stock_monitor**: **Quotes, watchlist, 自选股** — prefer stock tools when **tickers and prices** dominate.
- **knowledge_base**: User wants **their KB / 知识库** indexed content — not the open web.
- **weather**: **Forecast for a place** — not generic web search.
- **get_file_link**: Wording like “发给我” is not enough by itself; without a concrete local filename/path, web/news retrieval should win first.

## Workflow hints
- Typical: `web_search` → optionally `save_result_page` for long results. Prefer when the user did **not** attach or name a local document as the sole source.
