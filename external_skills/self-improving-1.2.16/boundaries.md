# Security boundaries

## Never store

- Passwords, API keys, tokens, session cookies, private keys.
- Government IDs, full payment card numbers, medical records.
- Other people’s private data without consent.

## Corrections and preferences

- Only store what the **user explicitly** stated or what you **clearly** did wrong and they confirmed.
- If unsure whether something is sensitive, **do not log**; ask a yes/no question first.

## Scope of reads

- Default memory operations: **`~/self-improving/`** only.
- Reading the **workspace** (source tree) is normal for coding; do not conflate that with “loading memory” unless the user asked.

## Deletes

- **Forget X / wipe:** require **explicit confirmation** before bulk delete or destructive edits.

## Optional network installs

- Upstream may mention a **Proactivity** companion or `clawhub install …`. In HomeClaw: **only** after the user clearly agrees, and prefer documenting what will run.

## Audit

- User may ask for **export** (zip) or **list** of what is stored; comply from `~/self-improving/` only.
