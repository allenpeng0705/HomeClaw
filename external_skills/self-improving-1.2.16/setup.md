# Setup: `~/self-improving/`

Run once (or let the agent create with user approval).

## 1. Create directories

```bash
mkdir -p ~/self-improving/projects ~/self-improving/domains ~/self-improving/archive
```

## 2. Seed files

If missing, create:

- `~/self-improving/memory.md` — copy from `memory-template.md` in this skill folder.
- `~/self-improving/corrections.md` — empty or with one line: `# Corrections log`
- `~/self-improving/index.md` — `# Index\n\n| Topic | File | Lines |\n|-------|------|-------|`
- `~/self-improving/heartbeat-state.md` — see `heartbeat-state.md` template in this folder.

## 3. Workspace heartbeat (optional)

If the user wants recurring review, append the snippet from **`homeclaw-heartbeat.md`** to the repo’s **`HEARTBEAT.md`** (create if needed), then add a **`cron_schedule`** job in HomeClaw (e.g. weekly) with a short reminder to run maintenance per **`heartbeat-rules.md`**.

## 4. Permissions

Restrict `~/self-improving/` if others use the same OS user account (file mode / separate user).
