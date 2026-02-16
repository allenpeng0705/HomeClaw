# Roadmap

A simple overview of planned directions. See **README.md** § Roadmap for the short list.

---

## Next: Local + cloud model mix

**Goal:** Use local and cloud models together so that work is done **efficiently** and **cost stays low**.

**Ideas (to be designed):**

- **Routing by task** — Use local model for high-volume or simple tasks (e.g. intent classification, short replies, embedding). Use cloud model for complex reasoning, long answers, or when local is not good enough.
- **Fallback** — Prefer local; call cloud when local fails or when the request explicitly needs a stronger model.
- **Cost control** — Limit cloud usage by budget or by routing rules (e.g. only use cloud for “hard” queries or when the user asks for it).
- **Config** — Allow rules or policies (e.g. “embedding always local”, “chat: local first, cloud if confidence low”) without hardcoding.

**Status:** Design phase. No implementation yet.

---

## Later

- Simpler setup and onboarding.
- More channels and platform integrations.
- Stronger plugin/skill discovery and multi-agent options.
- Optional: directory, trust/reputation, blockchain-based verification for agent-to-agent use cases.
