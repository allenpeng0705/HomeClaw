# MemOS (memos-local-openclaw) Investigation & Integration Options

This document summarizes [MemOS — OpenClaw Memory Plugin](https://github.com/MemTensor/MemOS/tree/main/apps/memos-local-openclaw), how it works with **local LLMs**, and whether HomeClaw can integrate or reuse it.

---

## 1. What MemOS Is

MemOS is a **Node.js/TypeScript plugin** for [OpenClaw](https://github.com/nicepkg/openclaw) (gateway/extensions ecosystem). It provides:

- **Persistent local memory** — SQLite + FTS5 + vector store; auto-capture on every agent turn via `agent_end` hook.
- **Hybrid retrieval** — FTS5 keyword + vector search with RRF (Reciprocal Rank Fusion), MMR (Maximal Marginal Relevance), recency decay.
- **Task summarization** — LLM-based topic-boundary detection (SAME/NEW), structured task summaries (Goal, Key Steps, Result, Key Details).
- **Skill evolution** — After task completion, LLM evaluates whether to create/upgrade a skill; generates SKILL.md + scripts + evals; versioning and quality scoring.
- **Multi-agent** — Memory isolation by owner; public memory and skill sharing; `memory_write_public`, `skill_publish` / `skill_unpublish`.
- **Memory Viewer** — Web UI at `http://127.0.0.1:18799` (memories, tasks, skills, analytics, import, settings).

It registers as OpenClaw’s **memory** slot (`plugins.slots.memory = "memos-local-openclaw-plugin"`) and requires **openclaw >= 2026.2.0**.

---

## 2. Local LLM Support in MemOS

MemOS supports **local** embedding and summarization as follows.

### Embedding

| Provider            | Config value           | Local? | Notes                                                                 |
|---------------------|------------------------|--------|----------------------------------------------------------------------|
| Local (offline)     | `provider: "local"`    | Yes    | Uses **Xenova/all-MiniLM-L6-v2** in-process; no API or key.           |
| OpenAI-compatible   | `provider: "openai_compatible"` | Yes | Point `endpoint` at a local embedding server (e.g. llama.cpp, Ollama `/v1/embeddings`). |

So you can run MemOS with **no cloud** for embedding: either `local` (on-device model) or `openai_compatible` with a local endpoint.

### Summarizer & skill evolution

- **Plugin config** — In `openclaw.json`, set `summarizer` (and optionally `skillEvolution.summarizer`) with `provider: "openai_compatible"`, `endpoint`, `apiKey`, `model` pointing at your **local** HTTP API (e.g. `http://127.0.0.1:5088/v1`, `apiKey: "local"`).
- **Fallback chain** — MemOS uses: **skillSummarizer** → **summarizer** → **OpenClaw native model** (from `~/.openclaw/openclaw.json`). The “native model” is read from `agents.defaults.model.primary` and `models.providers[providerKey]` (e.g. `baseUrl`, `apiKey`). If OpenClaw is configured to use a local endpoint (llama.cpp, Ollama, etc.), MemOS uses that for summarization/skill evolution when no plugin summarizer is set or when the plugin summarizer fails.

So **local LLM works** with MemOS in two ways:

1. Set MemOS `summarizer` (and optionally `skillSummarizer`) to `openai_compatible` with your local server URL.
2. Or leave summarizer unset and configure OpenClaw’s default model to your local server; MemOS will use it as fallback.

---

## 3. Why Direct “Plugin” Integration Into HomeClaw Is Not Possible

- MemOS is an **OpenClaw plugin**: it uses `OpenClawPluginApi`, `register()`, OpenClaw hooks (`before_agent_start`, `agent_end`), and OpenClaw config (`openclaw.json`). It runs inside the **OpenClaw gateway process** (Node.js).
- HomeClaw is a **separate stack**: Python Core, its own config (YAML), Cognee or Chroma for memory, no OpenClaw gateway or plugin runtime.

So you **cannot** “install” MemOS as a plugin into HomeClaw. The two run in different processes and ecosystems.

---

## 4. Integration Options

### Option A — Use MemOS when you use OpenClaw (no HomeClaw code change)

- **When:** You use or experiment with OpenClaw (e.g. another channel or workflow).
- **How:** Install MemOS in OpenClaw, set `plugins.slots.memory` to MemOS, disable OpenClaw’s built-in memory. Configure:
  - **Embedding:** `local` (Xenova) or `openai_compatible` with local embedding endpoint.
  - **Summarizer:** `openai_compatible` with local chat endpoint (e.g. same host:port as HomeClaw’s main LLM), or rely on OpenClaw’s native model pointing to that local server.
- **Result:** MemOS gives you task summarization, skill evolution, and Memory Viewer for that OpenClaw-based workflow. HomeClaw continues to use Cognee/chroma and its own summarization; no integration code.

### Option B — Port MemOS concepts into HomeClaw (Python)

Reimplement in HomeClaw the ideas that matter to you, e.g.:

- **Task boundary detection** — Segment conversations into tasks (e.g. LLM “SAME/NEW” topic + idle timeout); store task metadata.
- **Structured task summaries** — Per-task Goal / Key Steps / Result / Key Details (like MemOS), instead of or in addition to the current batch “summarize old raw memories then TTL.”
- **Skill evolution** — After a “task” is done, LLM decides if it’s worth a skill; generate SKILL.md (+ scripts + refs) and optionally install into `config/skills` or `external_skills`.
- **Hybrid search** — FTS + vector with RRF/MMR (e.g. in Chroma path or a new backend); MemOS uses SQLite FTS5 + vector; Cognee already has graph + vector.

This is a **feature port**, not “plug in MemOS.” Effort is significant (design, storage, LLM prompts, scheduling).

### Option C — HomeClaw as client of a MemOS-backed service (future)

- **If** MemOS (or a sibling service) exposed a **stable HTTP API** for memory read/write/search and optionally task/skill APIs, HomeClaw Core could call it as one of its memory backends.
- **Today:** MemOS does not expose such an API to external callers; it runs inside the gateway and serves the agent via OpenClaw’s tool/hook system. The Memory Viewer is a human UI, not an API for other apps.
- So this option would require either a new “MemOS API mode” or a separate service that wraps MemOS and exposes HTTP. Not available out of the box.

---

## 5. Comparison: MemOS vs HomeClaw Memory

| Aspect              | MemOS (OpenClaw plugin)           | HomeClaw (current)                          |
|---------------------|------------------------------------|--------------------------------------------|
| Runtime             | Node.js, inside OpenClaw gateway   | Python Core                                |
| Storage             | SQLite + FTS5 + vector             | Cognee (graph + vector + relational) or Chroma |
| Capture             | `agent_end` hook (per turn)        | After response, add to memory (Cognee/chroma) |
| Search              | Hybrid FTS + vector, RRF, MMR, recency | Cognee search or Chroma RAG                |
| Summarization       | Task-based (boundaries + summaries)| Batch: summarize old raw memories, TTL delete |
| Skills              | Auto task → evaluate → SKILL.md + scripts | Static skills (SKILL.md) + ClawHub import  |
| Multi-agent         | Owner, public memory, skill share  | Per-user/friend context; no shared “public” memory |
| Local LLM           | Embedding: local or openai_compatible; summarizer: config or OpenClaw native | main_llm / embedding_llm (llama.cpp, etc.) |
| Viewer / UI         | Memory Viewer (18799)              | Portal, Companion; no dedicated memory viewer |

---

## 6. Recommendation

- **If you want to use MemOS with a local LLM:** Use it **with OpenClaw** (Option A). Configure OpenClaw’s model (and optionally MemOS `summarizer`) to your local endpoint; use MemOS for memory/tasks/skills in that workflow. No changes to HomeClaw.
- **If you want MemOS-like behavior inside HomeClaw:** Plan a **Python feature port** (Option B): task segmentation, structured task summaries, and optionally skill evolution, reusing your existing main/embedding LLM and config.
- **If a future MemOS (or wrapper) exposes an HTTP API:** HomeClaw could add a “MemOS” memory backend that talks to that API (Option C).

---

## 7. References

- MemOS (memos-local-openclaw): <https://github.com/MemTensor/MemOS/tree/main/apps/memos-local-openclaw>
- MemOS README (install, config, local embedding/summarizer): <https://github.com/MemTensor/MemOS/blob/main/apps/memos-local-openclaw/README.md>
- OpenClaw: <https://github.com/nicepkg/openclaw>
- MemOS fallback chain (OpenClaw native model): `src/shared/llm-call.ts` — `loadOpenClawFallbackConfig()` reads `~/.openclaw/openclaw.json` for `agents.defaults.model.primary` and `models.providers[*].baseUrl` / `apiKey`.
