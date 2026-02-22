---
name: weather
description: Get current weather and forecasts (no API key required). Use run_skill with script get_weather.py.
homepage: https://wttr.in/:help
keywords: "weather forecast temperature rain wttr.in 天气 气温 预报"
# Optional: when to force-include and auto-invoke (no need to add a rule in core.yml)
trigger:
  patterns: ["weather|forecast|temperature|what'?s the weather|how'?s the weather|weather in|天气"]
  instruction: "The user asked about weather or forecast. Call run_skill(skill_name='weather-1.0.0', script='get_weather.py', args=['<city or place>']) with the location from the message. Do not say you cannot fetch weather."
  auto_invoke:
    script: get_weather.py
    args: ["{{query}}"]
---

# Weather

Get current weather via wttr.in (no API key). **Skill folder name for run_skill:** `weather-1.0.0`.

## Run via run_skill (recommended)

Call: **run_skill(skill_name=`weather-1.0.0`, script=`get_weather.py`, args=[\"Location\"])**

Examples:
- `args: ["London"]` → current weather for London
- `args: ["New York"]` or `args: ["北京"]` → any city name
- `args: ["--full", "Tokyo"]` → full forecast

No API key or config required.

## wttr.in (primary)

Quick one-liner:
```bash
curl -s "wttr.in/London?format=3"
# Output: London: ⛅️ +8°C
```

Compact format:
```bash
curl -s "wttr.in/London?format=%l:+%c+%t+%h+%w"
# Output: London: ⛅️ +8°C 71% ↙5km/h
```

Full forecast:
```bash
curl -s "wttr.in/London?T"
```

Format codes: `%c` condition · `%t` temp · `%h` humidity · `%w` wind · `%l` location · `%m` moon

Tips:
- URL-encode spaces: `wttr.in/New+York`
- Airport codes: `wttr.in/JFK`
- Units: `?m` (metric) `?u` (USCS)
- Today only: `?1` · Current only: `?0`
- PNG: `curl -s "wttr.in/Berlin.png" -o /tmp/weather.png`

## Open-Meteo (fallback, JSON)

Free, no key, good for programmatic use:
```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true"
```

Find coordinates for a city, then query. Returns JSON with temp, windspeed, weathercode.

Docs: https://open-meteo.com/en/docs
