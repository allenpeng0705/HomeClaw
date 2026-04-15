---
id: open_url
display_name: Open or fetch a URL
enabled: true
priority: 56
classifier_description: "Open, fetch, or read a specific http(s) URL or single page — user gave the link or one clear destination, not a broad keyword search."

category_tools:
  tools:
  - fetch_url
  - route_to_plugin
  - browser_navigate
---

## Description
The user wants to **load or interact with a known web address**: paste `https://…`, “open this link”, fetch article HTML, *在浏览器打开*, follow a single doc page. Distinct from **search_web** (keywords, no URL) and from **read_document** (local file path). If they paste **multiple** unrelated URLs, still often **open_url** if the task is **visit these pages**.

## Positive examples
- “Open https://example.com/docs and tell me the first H1.”
- “Fetch this URL and summarize the article.”
- “在浏览器里打开这个链接”
- “What’s on the status page at …?”
- “Compare the pricing tables on these two URLs.” (URL-centric)
- “打开这个链接并告诉我核心结论。”
- “Fetch https://... and extract the main points.”

## Negative boundaries
- **search_web**: **No URL** — only search terms or vague “look up X”.
- **read_document**: Target is a **local path** (`documents/...`), not primarily http(s).
- **news_digest**: User wants **RSS/daily digest product**, not one arbitrary page — unless they only manage a **feed URL** as setup (still often **open_url** for “fetch this feed once”).
- **general_chat**: They quoted a URL **only** as illustration — classify by the real question.

## Workflow hints
- `fetch_url`, `browser_navigate`, `route_to_plugin` as configured; pass the exact URL in tool args when possible.
