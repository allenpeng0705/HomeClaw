# Heartbeat rules (maintenance)

When a scheduled reminder fires (HomeClaw **`cron_schedule`**) or the user asks for maintenance:

1. Read `~/self-improving/heartbeat-state.md` for last run time and last reviewed change.
2. Scan `corrections.md` for items not yet reflected in `memory.md` (promote if 3× pattern).
3. Check `memory.md` line count; compact per `scaling.md` if over limit.
4. Update `index.md` if files were added/moved.
5. Write back `heartbeat-state.md` with **timestamp** and a one-line **note**.

Do **not** bulk-delete or rewrite user history during heartbeat unless the user asked.
