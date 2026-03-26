# HomeClaw heartbeat integration

OpenClaw may run a dedicated heartbeat daemon; **HomeClaw** uses **`cron_schedule`** (and optional Companion push).

## Suggested cron job

In `config/core.yml` (or your cron UI), add something like:

- **`cron_expr`:** `0 9 * * 0` (Sundays 09:00 — adjust timezone)
- **`task_type`:** e.g. message to self / user reminder, or `run_skill` if you add a tiny maintenance script later.
- **Message body:** “Self-improving maintenance: read `skills/self-improving-1.2.16/heartbeat-rules.md`, update `~/self-improving/heartbeat-state.md`.”

The agent still performs the actual file updates when handling that turn.

## Steering files

Non-destructive additions to **`AGENTS.md`** (this repo) are optional: e.g. one bullet pointing to `~/self-improving/` and this skill. **Only with user consent.**
