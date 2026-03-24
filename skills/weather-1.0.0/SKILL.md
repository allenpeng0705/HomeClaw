---
name: weather
description: |
  Current weather and forecasts via wttr.in (no API key). Natural language in English or Chinese; optional city or implicit location from Companion/profile (Core injects HOMECLAW_USER_LOCATION / lat/lng). Server time line comes from Core when available. Prefer passing the user's full message as one arg so extraction handles phrasing ("weather in Paris", "How about Beijing's weather?", "明天天气", vague "weather tomorrow" uses device location).
homepage: https://wttr.in/:help
keywords: "weather forecast temperature rain wttr.in 天气 气温 预报 明天 怎么样"
trigger:
  patterns: ["weather|forecast|temperature|wttr|what'?s the weather|how'?s the weather|how about.*weather|weather in|天气|气温|预报|明天"]
  instruction: |
    The user asked about weather. Call run_skill(skill_name='weather-1.0.0', script='get_weather.py', args=[...]).
    Prefer args=["<user message>"] or ["{{query}}"] so the script can extract the place from natural language. A city alone (e.g. ["London"]) is fine.
    If the message names no place (e.g. "weather tomorrow?"), Core still injects Companion/profile location—do not refuse; do not require a separate profile lookup unless the tool fails.
    Multi-line forecast: ["--full", "Tokyo"] or a message mentioning tomorrow/forecast/下周 so the script uses full output. See README.md in this skill folder for phrasing examples.
  auto_invoke:
    script: get_weather.py
    args: ["{{query}}"]
---

# Weather

Get current weather via **wttr.in** (no API key). **Skill folder:** `weather-1.0.0`.

## run_skill

```text
run_skill(skill_name="weather-1.0.0", script="get_weather.py", args=["<city or full sentence>"])
```

The script **extracts the location** from common English and Chinese phrasing. When the user does not name a place, **Core injects** latest Companion location, coordinates (if stored), and profile city/location—see **README.md** for details and natural-language examples.

| User says | Args (examples) |
|-----------|-----------------|
| `London` | `["London"]` |
| `How about Beijing's weather?` | `["How about Beijing's weather?"]` |
| `weather in Shanghai` | `["weather in Shanghai"]` |
| `What's the weather tomorrow?` (no city) | `["What's the weather tomorrow?"]` — uses device/profile location |
| `北京天气` / `请问上海天气怎么样` | full sentence in one string |
| Full forecast | `["--full", "Tokyo"]` or any message with *tomorrow* / *forecast* / *下周* |

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
