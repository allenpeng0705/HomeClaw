# Skills Test Prompts (Natural Language + run_skill)

Use this file as a one-stop checklist to test all current bundled skill READMEs:

- `daily-brief-1.0.0`
- `stock-monitor-1.0.0`
- `weather-1.0.0`
- `linkedin-writer-1.0.0`
- `magazine-render-1.0.0`

---

## 1) daily-brief-1.0.0

### Natural language prompts

#### English
- Daily brief, 25 items, all sources.
- Morning report for Chinese tech news.
- RSS digest filtered to AI.
- List the configured daily brief feeds.
- Daily brief, and make it a magazine-style PDF.

#### Chinese
- 今日新闻 / 每日简报（25条，中文）
- RSS 新闻订阅，筛选 AI 相关
- 列出 daily brief 的 RSS 源
- 把今日新闻做成杂志风格 PDF（排版更好看）

### run_skill calls

```text
run_skill(skill_name="daily-brief-1.0.0", script="fetch_rss.py", args=["list"])
run_skill(skill_name="daily-brief-1.0.0", script="fetch_rss.py", args=["fetch", "--max", "25", "--lang", "all"])
run_skill(skill_name="daily-brief-1.0.0", script="fetch_rss.py", args=["fetch", "--max", "20", "--lang", "cn"])
run_skill(skill_name="daily-brief-1.0.0", script="fetch_rss.py", args=["fetch", "--max", "20", "--lang", "all", "--filter", "AI"])
```

---

## 2) stock-monitor-1.0.0

### Natural language prompts

#### English
- Show my stock watchlist / portfolio.
- Check my stock alerts now.
- Alert me if NVDA drops 3% today.
- What happened to 0700.HK today? Give me context.
- Make this stock report a magazine-style PDF.

#### Chinese
- 看看我的自选股 / 组合今天怎么样？
- 检查一下股票提醒规则有没有触发
- NVDA 跌 3% 就提醒我
- 把自选股结果做成杂志风格 PDF（排版更好看）

### run_skill calls

```text
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["portfolio"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["check"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["news", "NVDA"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["context", "AAPL"])
```

---

## 3) weather-1.0.0

### Natural language prompts

#### English
- What’s the weather in Paris?
- How about Beijing’s weather?
- Weather in New York tomorrow.
- How’s the weather?
- Weather tomorrow?
- JFK weather.

#### Chinese
- 北京天气
- 上海天气怎么样
- 明天天气

### run_skill calls

```text
run_skill(skill_name="weather-1.0.0", script="get_weather.py", args=["What's the weather in Paris?"])
run_skill(skill_name="weather-1.0.0", script="get_weather.py", args=["明天天气"])
run_skill(skill_name="weather-1.0.0", script="get_weather.py", args=["--full", "Berlin"])
```

---

## 4) linkedin-writer-1.0.0

### Natural language prompts

#### English
- Write a LinkedIn post about how we lost our biggest client and what it taught us about customer success.
- Turn these bullet points into a LinkedIn post in a warm, humble tone.
- Write 3 variations: story style, contrarian style, and a checklist style.
- Make it shorter and punchier; keep it under 1,200 characters.

#### Chinese
- 帮我写一篇 LinkedIn 帖子，主题是：我们如何在一次事故中学到稳定性的重要性。
- 把下面要点改写成 LinkedIn 帖子（更像真人口吻）。

---

## 5) magazine-render-1.0.0

### Natural language prompts

#### English
- Make this a magazine-style PDF.
- Format this nicely and export as PDF.
- Make it pretty and readable as a PDF.
- Use the dispatch theme and include a cover preview image.

#### Chinese
- 把这个做成杂志风格 PDF。
- 排版更好看，并导出 PDF。
- 用 dispatch 主题，顺便生成一张封面预览图。

### run_skill calls

```text
run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py", args=["render-md", "--title", "Morning Brief", "--theme", "dispatch", "--profile", "literature", "--md", "# Morning Brief\n\n- Item 1\n- Item 2\n", "--preview", "auto", "--out", "morning_brief.pdf"])
```

```text
run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py", args=["render-json", "--template", "daily_brief", "--theme", "dispatch", "--profile", "literature", "--json", "{\"as_of\":\"2026-03-25\",\"items\":[{\"title\":\"Headline\",\"link\":\"https://example.com\",\"source\":\"RSS\"}]}", "--preview", "auto", "--out", "daily_brief.pdf"])
```

---

## Quick smoke-test order (recommended)

1. Weather simple query
2. Daily brief fetch
3. Stock portfolio
4. Magazine render from simple markdown
5. Daily brief + “magazine-style PDF” natural language

