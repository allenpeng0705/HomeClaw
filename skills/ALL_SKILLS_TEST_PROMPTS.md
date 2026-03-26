# Skills Test Prompts (Natural Language + run_skill)

Use this file as a one-stop checklist to test all current bundled skill READMEs:

- `daily-brief-1.0.0`
- `stock-monitor-1.0.0`
- `weather-1.0.0`
- `linkedin-writer-1.0.0`
- `magazine-render-1.0.0`
- `cli-anything-bridge-1.0.0`
- `self-improving-1.2.16`

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
- 今日新闻（20条，中文），请做漂亮的输出（给我 VMPrint 预览链接，不要纯 Markdown）

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

```text
run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py", args=["render-daily-brief-ast", "--title", "Daily Brief", "--theme", "dispatch", "--json", "{\"as_of\":\"2026-03-26\",\"items\":[{\"title\":\"Headline\",\"source\":\"RSS\",\"link\":\"https://example.com\"}]}", "--output_format", "browser_preview_html", "--out", "daily_brief.preview.html"])
run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py", args=["render-daily-brief-ast", "--title", "Daily Brief", "--theme", "dispatch", "--json", "{\"as_of\":\"2026-03-26\",\"items\":[{\"title\":\"Headline\",\"source\":\"RSS\",\"link\":\"https://example.com\"}]}", "--output_format", "layout_json", "--out", "daily_brief.layout.json"])
run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py", args=["render-template-ast", "--template", "weather", "--title", "Weather Brief", "--theme", "dispatch", "--json", "{\"location\":\"Beijing\",\"now\":{\"condition\":\"Cloudy\",\"temp\":\"18C\"},\"forecast\":[{\"day\":\"Fri\",\"summary\":\"Cloudy\",\"high\":\"21C\",\"low\":\"14C\"}]}", "--output_format", "browser_preview_html", "--out", "weather_brief.preview.html"])
run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py", args=["render-template-ast", "--template", "stock", "--title", "Stock Brief", "--theme", "dispatch", "--json", "{\"items\":[{\"symbol\":\"NVDA\",\"name\":\"NVIDIA\",\"price\":\"100\",\"change_pct\":\"+1.2%\"}]}", "--output_format", "browser_preview_html", "--out", "stock_brief.preview.html"])
```

---

## Quick smoke-test order (recommended)

1. Weather simple query
2. Daily brief fetch
3. Stock portfolio
4. Magazine render from simple markdown
5. Daily brief + “magazine-style PDF” natural language

---

## 6) cli-anything-bridge-1.0.0 (pilot)

### Natural language prompts

- Use cli-anything-gimp and show available commands.
- Run cli-anything-libreoffice --help.
- Use cli-anything-drawio and show version.

### run_skill calls

```text
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["exec", "--bin", "cli-anything-gimp", "--args-json", "[\"--help\"]"])
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["exec", "--bin", "cli-anything-libreoffice", "--args-json", "[\"--version\"]"])
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["exec", "--bin", "cli-anything-drawio", "--args-json", "[\"--json\", \"--help\"]"])
```

JSON path (parsed `data.normalized` when stdout is JSON):

```text
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["exec", "--bin", "cli-anything-drawio", "--args-json", "[\"--json\", \"--help\"]", "--parse-json", "strict"])
```

Copy-out path (move produced artifact into HomeClaw output scope):

```text
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["copy-out", "--source", "/absolute/path/to/generated.pdf", "--out-name", "generated.pdf"])
```

---

## 7) self-improving-1.2.16 (instruction-only; no run_skill)

### Natural language prompts

- Remember that I always want concise answers with bullet lists.
- That was wrong; actually the config path is `config/core.yml`.
- What have you learned about my preferences?
- Show my patterns / memory stats.
- After this task, reflect on what could go better next time.

### Notes

- State lives under `~/self-improving/` — create layout per `skills/self-improving-1.2.16/setup.md`.
- The agent uses **file_read** / **file_write** (or your approved tools), not a bundled script.

