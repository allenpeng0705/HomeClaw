# Memory operations

## Load order (typical)

1. `~/self-improving/memory.md` (HOT)
2. `~/self-improving/index.md` — pick relevant `projects/*` or `domains/*` by topic
3. Deeper files only when the query matches

## Writes

- **Append** to `corrections.md` with ISO date + one paragraph.
- **Edit** `memory.md` in small chunks; keep ≤ **100 lines** (summarize when over).
- Update `index.md` when adding/removing major topics.

## Heartbeat

- Read/update `~/self-improving/heartbeat-state.md` when running scheduled maintenance (see `heartbeat-rules.md`).

## Memory stats (when asked)

Report approximate counts:

- Lines or entries in `memory.md`
- Number of files in `projects/`, `domains/`, `archive/`
- Recent corrections count (e.g. last 7 days)

## Export

- User requests export: create a zip of `~/self-improving/` (user-approved command or tool), excluding transient editor backups if any.
