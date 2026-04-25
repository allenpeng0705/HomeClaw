---
name: self-improving
description: |
  Local self-improving memory under ~/self-improving/: corrections, preferences, tiered HOT/WARM/COLD files,
  self-reflection after significant work. Instruction-only; uses file_read/file_write or user-approved edits.
  HomeClaw-adapted from ClawHub ivangdavila/self-improving (MIT-0).
homepage: https://clawhub.ai/ivangdavila/self-improving
trigger:
  patterns:
    - "what (have you|did you) learn(ed)?"
    - "memory stats|show my patterns|my corrections"
    - "forget .+|export memory|wipe memory"
    - "remember that I|I always (want|prefer)|never do|stop doing|you('re| are) wrong|actually,? it should"
    - "self[- ]?improv|reflection log|corrections\\.md"
  instruction: |
    The user is using self-improving memory. Follow this skill and peer docs in skills/self-improving-1.2.16/
    (setup.md, boundaries.md, operations.md). State lives in ~/self-improving/ only.
    Use file_read/file_write (or equivalent) for those paths; never store secrets (see boundaries.md).
    For recurring maintenance, suggest cron_schedule in HomeClaw instead of OpenClaw-specific runners.
---

# Self-Improving memory (HomeClaw)

**Upstream:** [Self-Improving + Proactive Agent](https://clawhub.ai/ivangdavila/self-improving) (MIT-0). This bundle is **instruction-only** and **HomeClaw-specific** where noted.

## When to use

- User corrects you or points out mistakes.
- You finish significant work and should evaluate outcome vs intent.
- You notice your own output could be better (log reflection; do not invent preferences from silence).
- Knowledge should compound across sessions without manual re-explaining.

## Architecture

Memory lives in **`~/self-improving/`** with a tiered layout. If it does not exist, follow **`setup.md`** in this skill folder.

```
~/self-improving/
├── memory.md          # HOT: ≤100 lines, load when this skill applies
├── index.md           # Topic index with line counts
├── heartbeat-state.md # Last run, reviewed change, notes
├── projects/          # Per-project learnings
├── domains/           # Domain-specific (code, writing, comms)
├── archive/           # COLD: decayed patterns
└── corrections.md     # Last ~50 corrections / lessons
```

Optional: non-destructive steering snippets in the **workspace** repo — see **`homeclaw-heartbeat.md`** and **`HEARTBEAT.md`** (template in this folder). Only edit **`AGENTS.md`** / repo docs if the user agrees.

## Quick reference (peer files)

| Topic | File in this skill folder |
|-------|---------------------------|
| Setup | setup.md |
| Security | boundaries.md |
| Learning mechanics | learning.md |
| Read/write ops | operations.md |
| Scaling / compaction | scaling.md |
| Reflection format | reflections.md |
| Heartbeat rules | heartbeat-rules.md |
| HomeClaw cron / heartbeat | homeclaw-heartbeat.md |
| HOT memory template | memory-template.md |

## HomeClaw-specific notes

1. **No `clawhub` CLI required** for this skill to work; files are local. To install *other* ClawHub skills, use Portal/Companion or `clawhub install` on the Core host plus HomeClaw’s converter (see project docs).
2. **Optional “Proactivity” companion** (upstream): only mention or install if the user **explicitly** consents; it may pull additional packages or network installs.
3. **`cron` / heartbeat:** Prefer HomeClaw **`cron_schedule`** + a short reminder message (e.g. weekly “review self-improving memory”) instead of OpenClaw-only daemons.
4. **Tools:** Use **`file_read`**, **`file_write`**, **`folder_list`** (or exec with user approval) for `~/self-improving/*`. Do not read arbitrary paths “for memory” outside that tree except when the user asks or workspace steering files are explicitly in scope.

## Learning signals (summary)

**Corrections** → append to `corrections.md`, evaluate for promotion to `memory.md`:

- “No, that’s not right…”, “Actually, it should be…”, “You’re wrong about…”
- “I prefer X, not Y”, “Remember that I always…”, “Stop doing X”

**Preferences** (explicit only) → `memory.md`:

- “I like when you…”, “Always do X”, “Never do Y”, “My style is…”

**Pattern candidates** → track; promote after **3×** successful use (see `learning.md`).

**Ignore:** one-off instructions, pure hypotheticals, silence (no inference).

## Self-reflection (after significant work)

1. Did it meet expectations?
2. What could be better next time?
3. Is this a repeatable pattern? If yes, log to `corrections.md` / promote per rules.

Log format (see `reflections.md`):

```
CONTEXT: [task type]
REFLECTION: [what you noticed]
LESSON: [what to do differently]
```

## Quick user queries

| User says | Action |
|-----------|--------|
| “What do you know about X?” | Search HOT + index + relevant `projects/` / `domains/` |
| “What have you learned?” | Show recent `corrections.md` (e.g. last 10) |
| “Show my patterns” | Summarize `memory.md` |
| “Memory stats” | Counts per tier (see `operations.md`) |
| “Forget X” | Confirm, then remove across tiers |
| “Export memory” | Offer to zip `~/self-improving/` (user runs zip or approves command) |

## Core rules (short)

1. Learn from **explicit** corrections and reflection — not from silence.
2. **Tiered storage** — HOT/WARM/COLD per `scaling.md`.
3. **Promotion/demotion** — repeated use vs decay; never delete without confirmation when user-facing.
4. **Specificity:** project > domain > global when rules conflict.
5. **Transparency** — cite source file when applying a rule: “Using … (from `~/self-improving/projects/foo.md`)”.
6. **Security** — see `boundaries.md` (no credentials, no sensitive third-party data).

## Scope

**This skill ONLY:** maintains local learnings under `~/self-improving/`, optional agreed steering file tweaks, reads those memory files when relevant.

**This skill does NOT:** imply calendar/email access; does not require network; does not rewrite its own **`SKILL.md`** in the repo without user request.
