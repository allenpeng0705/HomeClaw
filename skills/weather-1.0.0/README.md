# weather-1.0.0

Current weather and short forecasts via **wttr.in** (no API key). This README is for **humans**: how to ask in natural language, how HomeClaw fills in missing **place** or **time context**, and how to debug. Agent-oriented rules live in **`SKILL.md`**.

## Requirements

- **Python 3** (same as Core when using `run_skill`).
- **Outbound HTTPS** to `wttr.in` from the machine running Core.

## How the model should call it

```text
run_skill(skill_name="weather-1.0.0", script="get_weather.py", args=["<user message or city>"])
```

Prefer **one string** that is the user’s full question so `get_weather.py` can parse phrasing, time words (*tomorrow*, *明天*), and optional place. A **city alone** (e.g. `["Oslo"]`) also works.

---

## Natural language (what you can say)

### English

| Example | What happens |
|--------|----------------|
| *What’s the weather in Paris?* | Extracts **Paris**. |
| *How about Beijing’s weather?* | Extracts **Beijing** (possessive). |
| *Weather in New York tomorrow* | **New York**; fuller forecast if *tomorrow* is detected. |
| *How’s the weather?* / *Weather tomorrow?* (no place) | Uses **HomeClaw context** — Companion latest location or profile **city/location** (see below). |
| *JFK* / *SFO* | Airport-style codes work as locations. |

### Chinese

| Example | What happens |
|--------|----------------|
| *北京天气* / *上海天气怎么样* | Extracts the city from common patterns. |
| *明天天气* (no city) | Uses **device/profile location** when the sentence does not name a place. |

### Explicit CLI-style (advanced)

- One-line summary (default): pass the place or sentence only.
- **Full terminal-style block** from wttr: `["--full", "Berlin"]` **or** ask using words like *tomorrow*, *forecast*, *下周* so the script switches to extended output.

### Formatted output (VMPrint policy)

- For pretty weather reports, prefer **browser preview link** first (`browser_preview_html`).
- Generate **PDF** only when user explicitly asks for print/download/export.

---

## When location is “missing” from the message

The script does **not** guess a random city. It uses **system context** injected by Core when you run **`run_skill`**:

1. **`HOMECLAW_USER_LAT_LNG`** — if Companion stored coordinates (preferred for wttr).
2. **`HOMECLAW_USER_LOCATION`** — latest Companion location text or **profile** `location` / `city` / short **address** prefix.

So: **share location in Companion** and/or set **user profile** location in HomeClaw. Then questions like *“how’s the weather tomorrow?”* still work.

If you run the script **by hand** outside Core (plain shell), those variables are unset unless you export them—pass an explicit city or place.

---

## When “datetime” is missing

The weather API returns **conditions for the named place**; it does not need your clock.

For an **“as of”** line on the answer, Core can inject **server-side** time when the skill runs:

| Variable | Meaning |
|----------|--------|
| `HOMECLAW_SERVER_DATETIME` | Human-readable host time (e.g. `2025-03-24 15:30`). |
| `HOMECLAW_SERVER_DATETIME_ISO` | ISO timestamp from the host. |
| `HOMECLAW_SERVER_TIMEZONE` | Label (often **system local** or zone name). |

The script may print one line such as:

`HomeClaw server time: …`  

That is **HomeClaw’s host clock**, not necessarily the **local time** of the city you asked about (e.g. Beijing vs your server).

---

## Troubleshooting

| Issue | What to check |
|--------|----------------|
| *Could not determine location* | Name a place in the message, or set **profile** location / **Companion** latest location. |
| Wrong city | Pass the **full user message** as one arg so extraction runs; avoid splitting into wrong tokens. |
| Timeout / network error | Core host must reach **https://wttr.in**; corporate proxies or offline hosts block the request. |
| Odd extraction | Rare phrases may need a simpler wording (*weather in X*) or a **city-only** arg. |

---

## Implementation notes (short)

- **wttr.in** is queried; responses are **UTF-8** text; the script retries a few times on transient errors.
- **No API keys** in this skill; respect wttr.in fair use and rate limits.

For trigger behavior, **`auto_invoke`**, and full tool wording, see **`SKILL.md`**.
