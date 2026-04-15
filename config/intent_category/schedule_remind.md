---
id: schedule_remind
display_name: Reminders and scheduling
enabled: true
priority: 54
classifier_description: "Set or manage reminders, cron jobs, recurring tasks, record_date / events — 提醒我, 定时, 每周, agent-side scheduling not generic email."

category_tools:
  tools:
  - remind_me
  - cron_schedule
  - cron_list
  - cron_remove
  - cron_update
  - record_date
  - recorded_events_list
  - route_to_tam
  - time
---

## Description
The user wants **time-based automation inside the assistant**: one-off reminders, **cron**-style schedules, recurring jobs, *提醒我*, *明天下午*, *每週一*, **record_date** / list events, cancel or update prior schedules. This is **agent-managed timers**, not sending email (**send_email**) and not “how do I use cron on Linux?” as pure tutorial (**search_web** or **general_chat**) unless they ask you to **create** the reminder.

## Positive examples
- “Remind me in 20 minutes to call back.”
- “Every Friday 9:00 send me a weekly summary prompt.” (if **reminder/cron**, not email delivery — disambiguate: cron → here)
- “明天下午三点提醒我开会”
- “List my recorded dates.” / “Cancel the reminder about X.”
- “Record that the deadline is March 1.”
- “每个工作日早上 8 点提醒我看日报。”
- “10 分钟后提醒我喝水。”

## Negative boundaries
- **send_email**: User wants to **send a message now** — **send_email**; **remind me to email** → **schedule_remind** if the primary ask is the **reminder**.
- **general_chat**: “I’ll be busy tomorrow” — **no** scheduling verb.
- **search_web**: “How does cron syntax work?” — learning; **schedule_remind** when they want a **concrete schedule created**.
- **memory**: Storing a **fact** without a **time trigger** — **memory**.

## Workflow hints
- `remind_me`, `cron_*`, `record_date`, `recorded_events_list`, `time`; `route_to_tam` when configured for advanced scheduling.
