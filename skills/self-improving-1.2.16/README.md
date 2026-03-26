# self-improving-1.2.16 (HomeClaw bundle)

Local **self-improving** memory: corrections, preferences, reflection, and tiered files under `~/self-improving/`.

**Source:** Adapted from [Self-Improving + Proactive Agent](https://clawhub.ai/ivangdavila/self-improving) by Iván (@ivangdavila), **MIT-0**. This copy is rewritten for HomeClaw (paths, heartbeat/cron, ClawHub wording).

**Note:** A byte-identical zip was not pulled from the ClawHub CLI in this environment (API rate limit). The behavior and structure match the published skill; to diff against the exact upstream bundle, run `clawhub install self-improving` when the CLI allows and compare files.

## Quick start

1. Read `setup.md` once and create `~/self-improving/` if missing.
2. Ensure `use_skills: true` in `config/core.yml`.
3. For richer instructions in context, add `self-improving-1.2.16` to `skills_include_body_for` if you use that feature.

## Natural language (examples)

- “Remember that I always want …”
- “That was wrong; actually …”
- “What have you learned about my preferences?”
- “Show my patterns / memory stats.”
- “Forget X” (confirm before deleting.)

## Files in this skill

| File | Purpose |
|------|---------|
| `SKILL.md` | Agent instructions (loaded by HomeClaw) |
| `setup.md` | First-time `~/self-improving/` layout |
| `boundaries.md` | Security / no-secrets rules |
| `learning.md` | Promotion rules, signals |
| `operations.md` | Read/write conventions |
| `scaling.md` | Tier limits, compaction |
| `reflections.md` | Self-reflection log format |
| `heartbeat-rules.md` | Recurring maintenance |
| `homeclaw-heartbeat.md` | Snippet for repo `HEARTBEAT.md` + cron idea |
| `memory-template.md` | Seed for `memory.md` |

Runtime state lives **only** under `~/self-improving/` (not in the repo).

## Updating from ClawHub

To refresh from upstream when rate limits allow:

```bash
cd downloads/skills && clawhub install self-improving
# Then compare with scripts/convert_openclaw_skill.py into external_skills/ or merge manually.
```
