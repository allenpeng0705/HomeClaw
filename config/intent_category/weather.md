---
id: weather
display_name: Weather and forecast
enabled: true
priority: 58
classifier_description: "Current weather, forecast, temperature, rain/snow, or what to wear for a named place and/or time (including 天气, 气温, 明天, 本周)."

match_patterns:
  - 天气预报
  - 明天.*天气
  - (?i)\b(weather|forecast|temperature)\b

category_tools:
  tools:
  - run_skill
  - web_search
  - time
  skills:
  - weather-1.0.0
---

## Description
The user wants **meteorological conditions or forecasts**: temperature, precipitation, wind, humidity, *天气*, *气温*, *forecast*, *明天*, *本周末*, for a **specific place and/or time window**. Includes “what should I wear tomorrow”, “will it rain when I land”, “hourly for Tokyo” when the goal is **actual weather data**, not climate science essays.

## Positive examples
- “Weather in London tomorrow?”
- “北京明天会下雨吗”
- “Highs this weekend in SF?”
- “Hourly forecast for Tokyo Friday afternoon.”
- “Do I need an umbrella in Seattle on Tuesday?”
- “Compare NYC vs Boston weather next week.”
- “广州后天温度大概多少？”
- “上海今晚风大吗，体感温度如何？”

## Negative boundaries
- **news_digest**: **News headlines / daily brief / 今日新闻** — not a weather lookup.
- **stock_monitor**: **Markets, tickers, portfolio** — financial data, not weather.
- **search_web**: **Research** (“why are hurricanes stronger now?”) — long-form or scientific **without** a local forecast ask — prefer **search_web**; **tomorrow’s rain in X** is **weather**.

## Workflow hints
- Often `run_skill(weather)` first; `web_search` or `time` as fallback if the skill is unavailable.
