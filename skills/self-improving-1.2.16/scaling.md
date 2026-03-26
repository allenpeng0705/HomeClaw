# Scaling and compaction

## Tier limits (targets)

| Tier | Location | Target size | When to load |
|------|-----------|-------------|--------------|
| HOT | `memory.md` | ≤ ~100 lines | Whenever this skill is active |
| WARM | `projects/`, `domains/` | ≤ ~200 lines per file | On topic match |
| COLD | `archive/` | unlimited | Explicit recall only |

## Compaction steps (when over limit)

1. Merge duplicate bullets in `memory.md`.
2. Move long examples to `archive/` with a short HOT pointer.
3. Summarize verbose corrections into one rule + “see corrections.md @ date”.
4. **Do not** delete confirmed preferences without user OK.

## Context pressure

If the session is tight on tokens: load **only** `memory.md` + one WARM file; tell the user what was skipped.
