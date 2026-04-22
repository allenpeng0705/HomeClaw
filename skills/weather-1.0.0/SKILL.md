---
name: weather
description: |
  Current weather and forecasts via wttr.in (no API key). Natural language in English or Chinese; optional city or implicit location from Companion/profile (Core injects HOMECLAW_USER_LOCATION / lat/lng). Server time line comes from Core when available. Prefer passing the user's full message as one arg so extraction handles phrasing ("weather in Paris", "How about Beijing's weather?", "明天天气", vague "weather tomorrow" uses device location).
retry_safe: true
homepage: https://wttr.in/:help
keywords: "weather forecast temperature rain wttr.in 天气 气温 预报 明天 怎么样"
trigger:
  patterns: ["weather|forecast|temperature|wttr|what'?s the weather|how'?s the weather|how about.*weather|weather in|天气|气温|预报|明天"]
  instruction: |
    The user asked about weather. Call run_skill(skill_name='weather-1.0.0', script='get_weather.py', args=[...]).
    Prefer args=["<user message>"] or ["{{query}}"] so the script can extract the place from natural language. A city alone (e.g. ["London"]) is fine.
    If the message names no place (e.g. "weather tomorrow?"), Core still injects Companion/profile location—do not refuse; do not require a separate profile lookup unless the tool fails.
    Multi-line forecast: ["--full", "Tokyo"] or a message mentioning tomorrow/forecast/下周 so the script uses full output. See README.md in this skill folder for phrasing examples.
    If user asks for prettier/magazine-style formatting:
    1) Run weather skill as usual to get output.
    2) Build structured weather JSON from the result (location, now, forecast).
    3) Call AST-first renderer:
       run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                args=["render-template-ast", "--template", "weather", "--title", "Weather Brief", "--theme", "dispatch", "--json", "<WEATHER_JSON>", "--output_format", "browser_preview_html", "--out", "weather_brief.preview.html"])
    4) Generate PDF only when user explicitly asks for print/download/export (same call with --output_format pdf and .pdf out file).
  auto_invoke:
    script: get_weather.py
    args: ["{{query}}"]
---

# Weather

Get current weather via **wttr.in** (no API key). **Skill folder:** `weather-1.0.0`.

## Natural language in HomeClaw (users do not type `run_skill`)

End users speak or type **normal questions** (“What’s the weather in Tokyo?”, “明天会下雨吗”). HomeClaw does **not** expose `run_skill` in the chat UI; the **model** chooses the skill and calls **`run_skill`** with the right `args`.

How the skill gets picked:

1. **`trigger.patterns`** (this skill) — If the user message matches the regex list, Core **force-includes** this skill and appends **`trigger.instruction`** so the model is steered to call **`run_skill`** with **`get_weather.py`**.
2. **`trigger.auto_invoke`** — If the model still does not call a tool, Core can run **`run_skill`** once with **`args: ["{{query}}"]`** (the raw user message).
3. **Keywords / RAG** — With vector skill search, **`keywords`** help retrieval; with **include-all** skills, the description alone helps the model pick weather among many skills.

**Best practice for the model:** pass **`args=[ "<the user’s full message>" ]`** (or **`["{{query}}"]`** in triggers) so **`get_weather.py`** can parse place, time words (*tomorrow* / *明天*), and “full forecast” intent. A **city-only** arg like **`["Seoul"]`** is also fine.

## run_skill

```text
run_skill(skill_name="weather-1.0.0", script="get_weather.py", args=["<city or full sentence>"])
```

The script **extracts the location** from common English and Chinese phrasing. When the user does not name a place, **Core injects** latest Companion location, coordinates (if stored), and profile city/location—see **README.md** for longer tables and edge cases.

### Example user phrases → what to pass

| User says (natural language) | Suggested `args` |
|------------------------------|------------------|
| `London` | `["London"]` |
| `What's the weather like?` / `How's the weather?` | `["What's the weather like?"]` — no city → use injected location |
| `Will it rain in Seattle today?` | `["Will it rain in Seattle today?"]` |
| `How about Beijing's weather?` | `["How about Beijing's weather?"]` |
| `weather in Shanghai` | `["weather in Shanghai"]` |
| `What's the weather tomorrow?` (no city) | `["What's the weather tomorrow?"]` — injected location + fuller output when script detects “tomorrow” |
| `Is it hot in Dubai right now?` | `["Is it hot in Dubai right now?"]` |
| `北京天气` / `请问上海天气怎么样` | one string with the full Chinese sentence |
| `明天天气怎么样` (no city) | `["明天天气怎么样"]` |
| `下周东京天气` | full sentence — script may treat as extended / multi-day phrasing |
| Full wttr-style block for one place | `["--full", "Tokyo"]` **or** a sentence containing *forecast* / *下周* / *tomorrow* / *明天* so the script widens output |

## CLI (debug)

From repo root (adjust path):

```bash
python3 skills/weather-1.0.0/scripts/get_weather.py Beijing
python3 skills/weather-1.0.0/scripts/get_weather.py "weather in New York"
python3 skills/weather-1.0.0/scripts/get_weather.py --full London
```

## More documentation

- **README.md** — natural-language examples, HomeClaw env vars, troubleshooting.
- **wttr.in** — spaces and airport codes are handled; the script URL-encodes the location.
