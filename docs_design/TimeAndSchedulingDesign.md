# Time-related handling: TAM vs Cron

This doc discusses what kinds of time-related things we need to handle and how **TAM** and **Cron** can split responsibility so they complement each other instead of overlapping.

---

## 1. Design principle: different inputs, different roles

| Component | Input | Role |
|-----------|--------|------|
| **Cron (tool)** | **Structured**: `cron_expr` + `message` (and later maybe `action`). | Handle **recurring** schedules. The model (or code) supplies the schedule explicitly. No natural-language parsing. |
| **TAM** | **Natural language**. User says "remind me in 5 minutes" or "my meeting is Tuesday 3pm". | Handle **reminders** (one-shot, relative or absolute), **record dates/events** for future handling, and **complex time expressions** that need context. TAM's LLM parses the message and then schedules or stores. |

So:

- **Cron** = recurring things, **structured** (cron expression + payload).
- **TAM** = reminder-related things + record dates for future, **natural language**.

They can share the same execution layer (TAM holds the scheduler); the difference is **who produces** the schedule and **what kind of time intent** each handles.

---

## 2. Categories of time-related things

### 2.1 One-shot reminders (relative time)

- **Examples**: "Remind me in 5 minutes", "remind me in 2 hours", "remind me when we're done" (if we had context).
- **Handler**: **TAM** (natural language). User does not give a cron expression; TAM parses "in 5 minutes" and schedules a one-time job.
- **Cron**: Not a fit; cron is for recurring patterns, not "once in N minutes".

### 2.2 One-shot reminders (absolute time)

- **Examples**: "Remind me tomorrow at 9am", "remind me on March 15 at 10", "remind me next Tuesday".
- **Handler**: **TAM** (natural language). TAM parses the date/time and schedules a single run.
- **Cron**: Could express "tomorrow 9am" as a one-off cron, but that's awkward; TAM is the right place for one-shot absolute times.

### 2.3 Recurring schedules (explicit or easy to map)

- **Examples**: "Every day at 9am", "every Monday at 10", "every 2 hours", "give me weather 9am every day".
- **Handler**: **Cron (tool)**. The model (or TAM if we allow it) produces a cron expression and message/action. Input can still be natural language from the user, but the **tool** receives structured data (`cron_expr`, `message`).
- **Why Cron**: Recurring is exactly what cron expressions are for. One place for all recurring jobs, no need for TAM to re-parse "every day at 9am".

### 2.4 Recurring described in natural language

- **Examples**: "Remind me to take pills every 8 hours", "remind me every morning at 9".
- **Options**:
  - **Model → Cron**: Model maps to `cron_schedule("0 */8 * * *", "Take pills")` or `cron_schedule("0 9 * * *", "Morning reminder")`. One LLM step, no TAM parse.
  - **TAM**: User says "every 8 hours" → route to TAM → TAM parses and creates a cron job internally (TAM still uses the same scheduler). Two LLM steps (route + TAM parse).
- **Recommendation**: Prefer **Cron (tool)** for recurring so we don't need a second LLM round. If the user phrase is complex ("every 8 hours except at night"), TAM can remain an option.

### 2.5 Record a date/event for future handling

- **Examples**: "My birthday is March 15", "The project deadline is Dec 31", "Meeting with John is next Tuesday at 3pm".
- **Handler**: **TAM** (natural language). TAM parses and **stores** the event/date (calendar-like). Optionally: remind on that day, or surface when the user asks "what's coming up?".
- **Cron**: Not a fit; this is "record for later" not "run every X". Could eventually trigger a one-shot reminder on the day, but the primary action is store + maybe future reminder.

### 2.6 Complex / context-dependent reminders

- **Examples**: "Remind me the day before the meeting", "remind me 30 minutes before my next call".
- **Handler**: **TAM** (natural language). Needs context (when is the meeting? what's the next call?) and NL to interpret "day before" / "30 minutes before".
- **Cron**: Cannot express "day before X" without knowing X; this belongs in TAM.

---

## 3. Coverage matrix

| Category | Example | TAM (NL) | Cron (structured) |
|----------|---------|----------|--------------------|
| One-shot, relative | "Remind me in 5 minutes" | Yes | No |
| One-shot, absolute | "Remind me tomorrow 9am" | Yes | Awkward |
| Recurring | "Every day at 9am" | Can parse and create cron | Yes (primary) |
| Recurring, NL | "Every 8 hours" | Yes (parse → cron) | Yes (model → cron_expr) |
| Record date/event | "My birthday is March 15" | Yes | No |
| Complex | "Day before the meeting" | Yes | No |

So:

- **TAM** covers: reminders (one-shot), record dates/events, complex time expressions. Input = **natural language**.
- **Cron** covers: **recurring** schedules. Input = **structured** (cron_expr + message/action).

Both can create jobs in the same scheduler; TAM may create one-shot timers or recurring jobs (by generating a cron_expr internally when the user says "every day at 9am").

---

## 4. How they work together

1. **Execution**: TAM owns the scheduler. Cron the **tool** just calls TAM's `schedule_cron_task(cron_expr, message)` (and later maybe `action`). So all recurring jobs run inside TAM's execution layer.
2. **Entry points**:
   - User says something **recurring** and the model can map to cron → model calls **cron_schedule(cron_expr, message)**. No TAM parse.
   - User says something **reminder-like or record-like** (one-shot, record date, complex) → model calls **route_to_tam** (or a future `tam_remind` tool that still passes NL to TAM). TAM parses natural language and schedules or stores.
3. **Prompting**: System prompt can say: "For **recurring** schedules (every day at X, every N hours), use **cron_schedule** with a cron expression and message. For **reminders** (in 5 minutes, tomorrow at 9, my birthday is X, day before meeting), use **route_to_tam** so TAM can interpret natural language."

That way:

- **Cron** = recurring, structured, one LLM round (model → tool args).
- **TAM** = reminders + record dates + complex time, natural language, one dedicated parse step.

---

## 5. Summary

| We need to handle | Primary handler | Input |
|-------------------|-----------------|--------|
| Recurring schedules | Cron (tool) | Structured: cron_expr + message (and later action) |
| One-shot reminders (relative/absolute) | TAM | Natural language |
| Record date/event for future | TAM | Natural language |
| Complex / context-dependent time | TAM | Natural language |

So: **Cron handles recurring with structure; TAM handles reminder-related and record-for-future with natural language.** They cover different things and can both feed the same scheduling/execution layer.

**Removing the LLM from TAM:** The main model can supply **structured** args via **tools** (function_call). Then TAM does not need to parse natural language. Tools: **remind_me**(minutes or at_time, message) for one-shot reminders; **record_date**(event_name, when, note) for "Tomorrow is national holiday", "Spring Festival is in two weeks"; **cron_schedule**(cron_expr, message) for recurring. The model does the understanding once and calls the right tool; TAM only executes (schedule_one_shot, record_event, schedule_cron_task). So **no LLM inside TAM** when using these tools. route_to_tam (which triggers TAM LLM parse) can be reserved for complex cases only.

---

## 6. Using recorded events and inference (when and how to remind)

### 6.1 How recorded events are used

1. **List** — User asks "what is coming up?" or "what did I record?". The model can call **recorded_events_list** to return all recorded events (event_name, when, event_date, remind_on, recorded_at).
2. **Surface in context** — Core optionally injects a short **Recorded events** summary into the system prompt (from TAM.get_recorded_events_summary), so the model sees upcoming events without calling the tool. Useful for answering "what's coming up?" from context.
3. **Inference at record time** — When the user says something like "my girlfriend's birthday is in two weeks, remind me", the model can call **record_date** with:
   - event_name, when (natural-language "in two weeks"),
   - **event_date** (YYYY-MM-DD) — the model computes "in two weeks" → e.g. 2025-02-28,
   - **remind_on** — "day_before" (remind the day before) or "on_day" (remind on the day at 9am),
   - **remind_message** (optional) — e.g. "Don't forget: girlfriend's birthday tomorrow!".

   TAM then stores the event and, if event_date and remind_on are set, **schedules the reminder(s)** via schedule_one_shot (no extra LLM). So "when to remind" and "how to remind" are inferred by the **model** (it computes the date and chooses day_before/on_day and message); TAM only executes.

### 6.2 Inference: who decides when and how to remind

- **When**: The **model** infers the date from "in two weeks" (or "tomorrow", "March 15") and passes **event_date** (YYYY-MM-DD). TAM uses that to schedule the one-shot reminder.
- **How**: The **model** chooses **remind_on** ("day_before" or "on_day") and optionally **remind_message**. TAM sends that message at the scheduled time (day before at 9am, or on the day at 9am).

So inference (when + how) is done by the **main model** in one turn; TAM does not run an LLM, it only stores the event and schedules the reminder(s) from the structured args.
