# TAM Scheduling Stability: LLM as Translator

This doc summarizes improvements to make scheduling/cron more stable by treating the LLM as a **translator** from natural language to rigid cron syntax or immediate actions, and by using **delimited output** plus **clarifier** handling.

## Goals

- **Stable parsing**: Prefer a strict text format the backend can parse with regex, instead of relying only on free-form JSON.
- **Clear rules**: Give the LLM explicit rules for time calculation (immediate vs lead-time vs daily vs relative).
- **No guessing on ambiguity**: When the LLM needs to ask the user (e.g. "when to remind?"), it must not output a CRON/EXECUTE_NOW tag so we don't schedule until the user answers.

## Output Format (Primary)

The LLM is instructed to always end its response with one of:

- `[CRON: 'min hour day month dow' / MSG: 'message']` — for recurring or one-time cron
- `[EXECUTE_NOW: 'message']` — for "remind me now" or events in under ~15 minutes

If the LLM needs to **ask the user** (e.g. "When would you like me to remind you?"), it outputs the question and ends with `?` and does **not** include a CRON or EXECUTE_NOW tag. The Python side then treats the response as a clarifier: show it to the user and do not schedule.

## Rules for Time Calculation (in prompt)

- **Immediate**: Reminder for something in &lt; 15 minutes → `EXECUTE_NOW`.
- **Lead time**: Meetings/calls → reminder N minutes before (default 5 min unless user says otherwise).
- **Daily habits**: Cron at the exact time (e.g. "every morning at 8" → `0 8 * * *`).
- **Special events (birthdays)**: Cron at 9:00 AM on the day; can suggest a lead-time reminder in the friendly text.
- **Relative**: "tomorrow", "next Monday", "in 2 hours" → compute from **Current Reference Time** (single source of truth).

## Implementation

### TAM (`core/tam.py`)

1. **`_parse_tam_delimited_response(response_str)`**  
   Uses regex to extract:
   - `[CRON: '...' / MSG: '...']` (single- or double-quoted) → `data_object = { type: "cron", cron_expr, params: { message } }`.
   - `[EXECUTE_NOW: '...']` → `data_object = { type: "execute_now", params: { message } }`.
   - If the response contains `?` and no CRON/EXECUTE_NOW tag → `(None, response_str, clarifier=True)` so we don't schedule and return the question to the user.

2. **`analyze_intent_with_llm`**  
   - First runs `_parse_tam_delimited_response`. If it gets a `data_object` or a clarifier, returns `{ "data", "friendly", "clarifier" }`.
   - Otherwise falls back to existing JSON extraction and returns the same shape.

3. **`process_intent`**  
   - Uses the new return shape. If `clarifier` and `friendly`, returns `friendly` (user sees the question). If `data` is set, calls `schedule_job_from_intent` and returns `friendly` when present (user sees confirmation).

4. **`schedule_job_from_intent`**  
   - Handles `type == "execute_now"`: schedules a one-shot reminder 1 minute from now via `schedule_one_shot(message, run_time_str, user_id, channel_key)`.
   - `type == "cron"` unchanged.

### Prompts

- **`config/prompts/tam/scheduling.en.yml`**  
  Structured for stability (including Gemini-inspired categories and rules):
  - **Single source of truth**: Reference Time only; recompute relative times from it; 24h internally.
  - **Cron syntax**: Field order, day_of_week 0=Sun..6=Sat, patterns including **every N minutes** (e.g. `*/45 * * * *` for every 45 min) and Mon/Wed/Fri (`0 6 * * 1,3,5`).
  - **Rules**: Immediate (EXECUTE_NOW); lead time (5–15 min before); recurring; **past-time** (if requested time already passed, ask "Set for tomorrow?" and do NOT output a tag); ambiguity (ask, no tag).
  - **Categories & examples**: (1) Sub-hour immediate, (2) One-time lead-time (call/dentist), (3) Simple habits (daily, weekly, 1st of month), (4) Interval (every 2h, every 45 min), (5) Social/special day (birthday/anniversary — note + suggest lead or ask), (6) Vague (clarifier), (7) Past-time (ask to reschedule).
  - **Output format**: Exactly one of [CRON: '...' / MSG: '...'] or [EXECUTE_NOW: '...'], or a question ending with ? (no tag).
  - **Do NOT**: Raw JSON; invent time; reuse old time; output two tags.

- **`_create_prompt_fallback`** (in `core/tam.py`)  
  Same structure in short form when the prompt manager is not used: reference time, cron patterns, rules, and minimal examples.

## Extraction in Python

- **CRON**: `re.search(r"\[CRON:\s*'([^']*)'\s*/\s*MSG:\s*'([^']*)'\]", s)` (and a double-quote variant).
- **EXECUTE_NOW**: `re.search(r"\[EXECUTE_NOW:\s*'([^']*)'\]", s)`.
- **Friendly text**: Everything before the `[CRON:...]` or `[EXECUTE_NOW:...]` is shown to the user as the confirmation.

## Backward compatibility

- JSON output is still supported: if no delimited tag is found, TAM falls back to `Util().extract_json_str()` and the existing `schedule_job_from_intent` logic for `type: "cron"` and `type: "reminder"` (repeated/fixed/random).

## Stability: never crash Core

- **TAM**  
  - `_parse_tam_delimited_response`: wrapped in try/except; returns `(None, None, False)` on any exception so caller can fall back to JSON.  
  - `analyze_intent_with_llm`: full body in try/except; always returns a dict `{data, friendly, clarifier}`; on any exception returns `fallback` and logs.  
  - `process_intent`: validates `result` is a dict; uses `str(...).strip()` for friendly; outer try/except returns a user-facing message on exception.  
  - `schedule_job_from_intent`: `params` taken as `_params if isinstance(_params, dict) else {}`; entire scheduling logic in try/except; logs and returns on exception so it never raises.

- **Core reminder fallback**  
  - `_remind_me_ask_message`: try/except; returns `str(...).strip()` so callers never get a non-string.  
  - `registry.list_tools()`: wrapped in try/except; `_has_remind_me` defaults to False on exception.  
  - `remind_fallback`: only used if `isinstance(remind_fallback, dict)`; `_args` built with `isinstance(..., dict)` check.  
  - `_infer_remind_me_fallback(query)` call: wrapped in try/except; on exception `remind_fallback = None`.

- **tool_helpers**  
  - `infer_remind_me_fallback`: docstring states "Never raises"; callers (Core) also wrap the call in try/except.

## References

- Design discussion (Gemini): use LLM as translator; delimited output; rules for immediate/lead-time/daily/special/relative; examples; treat `?` as clarifier and do not schedule.
- Existing design: `docs_design/TimeAndSchedulingDesign.md`, `core/tam.py`, `config/prompts/tam/scheduling.en.yml`.
