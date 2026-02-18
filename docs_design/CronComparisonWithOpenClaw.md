# Cron Implementation: HomeClaw vs OpenClaw

This document compares HomeClaw's cron (TAM + tools) with OpenClaw's cron (in `../clawdbot`) for completeness and stability. OpenClaw source: **clawdbot** (Gateway cron service, UI, isolated-agent execution).

---

## 1. HomeClaw Cron (Current)

### 1.1 Entry points

- **Tools:** `cron_schedule(cron_expr, message, tz?, delivery_target?)`, `cron_list`, `cron_remove`, `cron_update(job_id, enabled)`, `cron_run(job_id)`, `cron_status`.
- **TAM:** Holds the scheduler; `schedule_cron_task()`, `remove_cron_job()`, `update_cron_job()`, `run_cron_job_now()`, `get_cron_status()`; in-memory `cron_jobs` list; background thread runs `run_scheduler()` which every 10s calls `_run_cron_pending()`.

### 1.2 Schedule model

- **Recurring only:** 5-field cron expression (minute hour day month weekday) via **croniter**. Optional **timezone** per job (`tz`, e.g. `America/New_York`) using `zoneinfo` when available.
- **One-shot reminders:** Handled separately by TAM (`schedule_one_shot`, `remind_me` tool), not in the same “cron” API.

### 1.3 Persistence

- **SQLite** via `memory/tam_storage.py`: `TamCronJobModel` (job_id, cron_expr, params JSON). Params include message, tz, enabled, channel_key, last_run_at, last_status, last_error, last_duration_ms. Load on TAM init, save on add, update_cron_job/update_cron_job_state, delete on remove. Survives Core restart.

### 1.4 Execution

- **Action:** Send a fixed message to “latest channel” or to the **per-session channel** when `delivery_target='session'` (uses `channel_key` = `app_id:user_id:session_id`; Core persists last channel per session and exposes `send_response_to_channel_by_key(key, response)`). No LLM. Run history (last_run_at, last_status, last_error, last_duration_ms) is persisted after each run.
- **Thread:** Scheduler runs in a daemon thread; due jobs run with `asyncio.run(job["task"]())` from that thread.

### 1.5 Stability considerations

| Aspect | HomeClaw | Note |
|--------|----------|------|
| **Polling interval** | 10s | Jobs can fire up to ~10s late. |
| **Duplicate fire** | next_run advanced before running | Same as OpenClaw’s “next strictly after now” idea; advancing before run avoids double-fire in same tick. |
| **Event loop** | `asyncio.run()` in worker thread | Creates new event loop per run; fine for “send to channel” but can conflict if task assumed main loop. |
| **Lock** | `_cron_lock` around list and next_run updates | Prevents races when reading/updating cron_jobs. |
| **Failure** | Exception logged; next_run already advanced; run state persisted | Job keeps running on schedule; no auto-disable or backoff. |
| **Restart** | Load from DB and re-schedule | No “missed run” catch-up; next_run is recomputed on first tick after load (via croniter from now). |

### 1.6 Gaps vs OpenClaw (addressed where implemented)

- **Timezone (implemented):** `tz` per job in `cron_schedule`; uses `zoneinfo` (Python 3.9+) for next-run computation.
- **Enable/disable (implemented):** `cron_update(job_id, enabled=true|false)` toggles a job; state in params and persisted.
- **Manual run now (implemented):** `cron_run(job_id)` runs the job once and records run state.
- **Run history (implemented):** last_run_at, last_status, last_error, last_duration_ms stored in params and shown in `cron_list`; persisted after each run and after `cron_run`.
- **cron.status (implemented):** `cron_status()` returns scheduler_enabled, next_wake_at, jobs_count.
- **Per-job channel (implemented):** `delivery_target='session'` in `cron_schedule` delivers to the current conversation channel; Core persists last channel with key `app_id:user_id:session_id` and sends via `send_response_to_channel_by_key`.
- **Single payload (not implemented):** Message only; no “agent turn” (LLM) option, no systemEvent vs agentTurn.

---

## 2. OpenClaw Cron (Reference)

### 2.1 API (Gateway RPC)

- **cron.add** — Create job (name, description, schedule, sessionTarget, wakeMode, payload, delivery, enabled).
- **cron.update** — Patch job (e.g. enabled, payload, delivery).
- **cron.remove** — Delete by id.
- **cron.list** — List jobs (optional includeDisabled).
- **cron.status** — Scheduler status (enabled, nextWakeAtMs).
- **cron.run** — Run job now (mode: force | due).
- **cron.runs** — Run log for a job (entries with status, duration, etc.).

### 2.2 Schedule model

- **kind: "cron"** — expr + optional **tz** (timezone; default system TZ). Uses **croner** with `timezone`.
- **kind: "at"** — One-shot at a given time (string or atMs).
- **kind: "every"** — Every N ms (anchor optional).

### 2.3 Job model

- **sessionTarget:** `main` (systemEvent only) vs `isolated` (full agent turn in isolated session).
- **wakeMode:** `next-heartbeat` vs `now` (trigger heartbeat immediately for main).
- **payload:** `systemEvent` (text) or `agentTurn` (message, optional model, thinking, deliver, channel, to).
- **delivery:** mode (none | announce), channel, to, bestEffort (for isolated jobs).
- **state:** nextRunAtMs, runningAtMs, lastRunAtMs, lastStatus, lastError, lastDurationMs, consecutiveErrors, scheduleErrorCount (auto-disable after N schedule errors).
- **Stuck run:** If runningAtMs older than 2h, clear and allow re-run.

### 2.4 Execution

- **Main:** Enqueue system event; optionally trigger heartbeat once (wakeMode “now”).
- **Isolated:** Run agent (CLI/embedded) in isolated session; optional delivery to channel/to (announce).

### 2.5 Persistence and timer

- **Store:** JSON file (version + jobs array). Migration for schema changes.
- **Timer:** Recompute next runs; run due jobs; on startup run “missed” jobs (catch-up). Single timer, no 10s sleep for cron (wake at next due time or interval).

### 2.6 Stability and tests

- Duplicate fire fixed (e.g. #14164): next run strictly after current second.
- E2E and unit tests: cron.add/list/remove/run, cron.runs, cron.status, restart catch-up, one-shot disable after run, delivery, schedule errors.

---

## 3. Summary: Is HomeClaw Cron Full and Stable?

### 3.1 Full?

- **Core use case (recurring reminder, same message, to “current” channel):** Yes. Schedule, list, remove, persist, survive restart.
- **Compared to OpenClaw:** Not full. Missing: timezone, enable/disable, run now, run history, status, per-job delivery, “agent turn” payload, one-shot “at” and “every” in same cron system.

### 3.2 Stable?

- **Generally:** Yes for the current scope. Persistence and lock are correct; next_run advanced before run avoids duplicate fire in the same tick.
- **Caveats:**
  - **Granularity:** 10s polling means up to ~10s delay; acceptable for “daily at 9” but not for “every minute”.
  - **asyncio.run in thread:** Safe for simple “send to channel”; if cron tasks ever need shared Core state or main loop, this may need refactor (e.g. submit to main loop instead of asyncio.run).
  - **No run history:** Harder to debug “did it run?” without logs.
  - **No catch-up on restart:** If Core is down when a job would have run, that run is skipped (next_run is recomputed from “now” on load, so the next occurrence is correct).

### 3.3 Recommendations (optional improvements)

1. **Timezone (high value):** Add optional `tz` to cron_schedule (e.g. `America/New_York`). Use croniter with timezone or migrate to croner; document “server local” when tz omitted.
2. **Enable/disable (medium):** Add `enabled` to persisted job and `cron_update(job_id, enabled=…)` tool so users can pause without deleting.
3. **Run now (medium):** Add `cron_run(job_id)` tool that runs the job once immediately (same as OpenClaw’s cron.run force).
4. **Run history (low):** Persist last run time and status per job; optional `cron_runs(job_id)` or at least last_run in `cron_list`.
5. **Finer granularity (low):** Reduce sleep from 10s to e.g. 60s or use a timer that wakes at next due time to reduce latency and CPU (OpenClaw-style).
6. **Delivery (later):** If multi-channel matters, add per-job delivery target (channel/to) and optional “announce” mode; requires TAM/core to know channel routing.

---

## 4. References

- **HomeClaw:** `core/tam.py`, `tools/builtin.py` (cron_*), `memory/tam_storage.py`, `docs_design/TimeAndSchedulingDesign.md`.
- **OpenClaw (clawdbot):** `src/cron/` (types, service, timer, isolated-agent, normalize), `src/gateway/server-methods/cron.ts`, `src/gateway/protocol/schema/cron.ts`, `ui/src/ui/views/cron.ts`, `ui/src/ui/controllers/cron.ts`.
