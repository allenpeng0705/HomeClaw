# HomeClaw compatibility notes: social-media-agent

This skill was written for another agent platform. It **loads and is used** by HomeClaw when `use_skills: true`: the model sees the skill **name** and **description** and can use it to suggest social media strategy, content ideas, and high-level workflows.

## What works in HomeClaw

- **Discovery**: The model knows "social-media-agent" exists and what it's for (X/Twitter management, content, engagement).
- **Strategy and content**: Content pillars, posting rules, draft format, and analytics ideas from the skill can be discussed and applied.
- **Approximate tools**:  
  - **Research**: Use `fetch_url` to get content from news sites (similar to `web_fetch`).  
  - **Read pages**: Use `browser_navigate` or `fetch_url` to read x.com or articles.  
  - **Files**: Use `file_read` / `folder_list` for drafts or logs if you store them under `tools.file_read_base`.

## Full browser support (HomeClaw)

HomeClaw now supports **full browser** tools in one request: **browser_navigate**, **browser_snapshot** (get elements with selectors), **browser_click**, **browser_type**. So you can:

1. **browser_navigate** to x.com/compose/post  
2. **browser_snapshot** to get the tweet input and Post button selectors  
3. **browser_type** (selector for the textbox, tweet text)  
4. **browser_click** (selector for Post button)  

Enable with **use_tools: true** and install Playwright (`pip install playwright && playwright install chromium`).

## What doesn't (yet)

- **Cron**: No `cron` tool yet; scheduling would need to be external or a future tool.
- **sessions_spawn**: No parallel session spawn; content generation runs in the same conversation.

So: use this skill for **strategy and content**; use the **browser** tools for posting (navigate → snapshot → type → click).
