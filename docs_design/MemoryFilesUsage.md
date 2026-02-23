# How memory .md files are used

This doc summarizes how **AGENT_MEMORY.md** and **daily memory** (`memory/YYYY-MM-DD.md`) are used so you can configure them safely and avoid filling the context window.

---

## Format (recommended)

Both files are **plain Markdown** (`.md`). The code does not enforce a schema; it only appends the `content` you pass (with a blank line before each new append). For consistent, search-friendly entries, use this convention:

| File | Recommended format | Why |
|------|--------------------|-----|
| **AGENT_MEMORY.md** | One fact or preference per **paragraph** (blank line between). Optionally prefix with date: `YYYY-MM-DD: ...`. Use `## Section` headings to group (e.g. `## Preferences`, `## Decisions`). | Indexing chunks by size; one paragraph per entry keeps retrieval precise. Dates help traceability. |
| **Daily memory** (`memory/YYYY-MM-DD.md`) | One note per paragraph. Optionally start with a bullet and short label: `- **Session:** ...` or `- 14:30 Summarized the report.` | Same chunking; labels make the file scannable. The filename already is the date, so time-in-day is optional. |

**Examples**

- **AGENT_MEMORY.md:**  
  `2025-02-19: User prefers dark mode for the app.`  
  or with headings:  
  `## Preferences\n\n- Dark mode for the app.\n\n- Notifications off after 22:00.`

- **Daily memory:**  
  `- **Session:** Discussed project timeline; user will confirm by Friday.`  
  or  
  `Summarized the PDF; key points saved. User asked to remind next week.`

You can write in any Markdown you like; the above is a **recommendation** so the model and humans produce consistent, easy-to-search entries.

---

## Two kinds of memory files

| File(s) | Purpose | When loaded | Bounded? |
|--------|---------|-------------|----------|
| **AGENT_MEMORY.md** | Curated long-term memory (facts, preferences, decisions). Human- and model-editable. | When **use_agent_memory_search: true** (default): **no content injected**; model uses **agent_memory_search** + **agent_memory_get** to pull only relevant parts. When false: last 5k chars injected. | Retrieval-first by default; no bulk inject, so context stays small. |
| **Daily memory** (`memory/YYYY-MM-DD.md`) | Short-term notes for yesterday and today. | Every request when `use_daily_memory: true`. Only **yesterday** and **today** are loaded. | Yes — at most two files (yesterday + today), so context stays bounded. |

You can use **both** at once: AGENT_MEMORY for long-term, daily memory for recent context. The two are **independent** only in the sense that they use different config flags and different files — we don’t sync or merge them. Both are injected into the same system prompt when enabled, so the model sees both sections.

---

## Can they duplicate?

**Yes.** There is no automatic deduplication. If the same (or similar) information is written to both AGENT_MEMORY.md and to a daily file (e.g. via `append_agent_memory` and `append_daily_memory`), it will appear in both sections and the model will see it twice.

**Recommended use to avoid clutter:**

- **Daily memory** — Short-lived notes: “what we did this session,” reminders for today, scratch. Let old dates roll off (only yesterday + today are loaded).
- **AGENT_MEMORY.md** — Facts you want to keep long-term: preferences, decisions, important context. When something from a conversation should persist, the agent (or you) appends it here.

If the same fact appears in both, the system prompt already says that **AGENT_MEMORY (curated)** is authoritative when it conflicts with other context; the model is instructed to prefer it. So duplication is mostly a matter of prompt size and clarity, not correctness.

---

## Do we load the whole AGENT_MEMORY.md into context?

**It depends on `use_agent_memory_search`.**

- **When use_agent_memory_search is true (default):** We use the **same approach as OpenClaw**: (1) **Bootstrap:** We inject a capped chunk of AGENT_MEMORY.md and daily memory (yesterday + today) into the system prompt every time, so memory is always in context. The combined block is trimmed to `agent_memory_bootstrap_max_chars` (default 20k for cloud) or `agent_memory_bootstrap_max_chars_local` (default 8k when the request uses the local model in mix mode). (2) **When content exceeds the cap:** We keep **head (70% of cap) + tail (20% of cap)** with a marker in between, so the model still sees structure and recent content. (3) **Tools:** The model can still use **agent_memory_search** and **agent_memory_get** to pull more. So memory is always used (bootstrap) and the model can retrieve more via tools.
- **When use_agent_memory_search is false:** We inject the last `agent_memory_max_chars` (default 5k) of AGENT_MEMORY into the prompt, and optionally the full daily memory block (legacy behavior).

**OpenClaw (from `../clawdbot`):** They do **not** load the whole MEMORY.md into context. Their approach:

1. **Bootstrap injection with a cap:** MEMORY.md (or memory.md) is included in **workspace bootstrap**: the file is read and injected into the session context, but **each bootstrap file** is trimmed to at most `bootstrapMaxChars` (default **20_000**). So MEMORY.md is never more than 20k chars in the prompt; if longer, they keep head (70%) + tail (20%) and a truncation marker (`pi-embedded-helpers/bootstrap.ts`: `trimBootstrapContent`, `buildBootstrapContextFiles`).
2. **Retrieval tools:** The agent is given **memory_search** (semantic search over MEMORY.md + memory/*.md) and **memory_get** (read a snippet by path + from/lines). The system prompt tells the model: “Before answering anything about prior work… run memory_search on MEMORY.md + memory/*.md; then use memory_get to pull only the needed lines.” So additional context is **retrieved on demand** as tool results (snippets), not as a full-file block (`agents/tools/memory-tool.ts`, `agents/system-prompt.ts`).
3. **Indexing:** MEMORY.md and memory/*.md are indexed (vector + optional keyword/SQLite) so memory_search returns relevant snippets; there is even a `maxInjectedChars`-style clamp on search results for the qmd backend.

So OpenClaw avoids loading the whole MEMORY.md by: (a) capping its bootstrap copy at 20k chars, and (b) relying on memory_search + memory_get to pull only relevant parts when needed. **HomeClaw now aligns with OpenClaw (bootstrap + tools):** when `use_agent_memory_search: true`, we inject a capped bootstrap of agent/daily memory and the model uses agent_memory_search + agent_memory_get to pull only what’s needed.

---

## When is AGENT_MEMORY.md used?

- **When:** When `use_agent_memory_file` is `true`, the file is either (1) bootstrap-injected (capped) + indexed for tools when `use_agent_memory_search: true`, or (2) read and injected (last N chars) when `use_agent_memory_search: false`.
- **How (retrieval + bootstrap, default):** A capped bootstrap of AGENT_MEMORY + daily is injected (see **Do we load the whole AGENT_MEMORY.md** above); over cap we use head 70% + tail 20% + marker. The model is also instructed to use **agent_memory_search** then **agent_memory_get** for more. Indexing runs at startup.
- **How (legacy):** The last `agent_memory_max_chars` (default 5k) is injected as **"## Agent memory (curated)"**. The model is told this section is authoritative when it conflicts with RAG.
- **Writing:** The agent (or user) can append via the `append_agent_memory` tool. Users can also edit the file manually. After manual edits, restart Core to reindex when using retrieval.

## When is daily memory used?

- **When:** On every request where memory is used, if `use_daily_memory` is `true`.
- **How:** The files `memory/YYYY-MM-DD.md` for **yesterday** and **today** are read and concatenated (with `## YYYY-MM-DD` headers) and injected as **"## Recent (daily memory)"**.
- **Writing:** The agent can append to today’s file via the `append_daily_memory` tool. Older dates are never loaded, so the context window is not filled by history.

---

## What if AGENT_MEMORY.md gets very long?

If the file grows without bound, the full content is injected every time and can:

- Exceed the model’s context window and cause errors or truncation.
- Leave less room for RAG, chat history, and tools.

**What we do:**

- **Default cap:** `agent_memory_max_chars` defaults to **5000** (5k). Only the last N characters are injected; the loader adds a one-line note if content was omitted. Set to `0` for no truncation.
- **Pull more on demand:** When `use_agent_memory_search: true`, the model can use **agent_memory_search** (semantic search over AGENT_MEMORY + daily memory) and **agent_memory_get** (read a file by path and optional line range) to pull only relevant parts when needed, similar to OpenClaw.

Daily memory does not need a cap: only two files (yesterday + today) are ever loaded.

---

## Why do I see "AGENT_MEMORY size 0" or "synced 0 chunk(s)"?

The **size** is the number of **chunks** indexed into the vector store for agent memory (AGENT_MEMORY.md + daily memory). It is logged at Core startup as `[agent_memory] synced N chunk(s) to vector store`. It is **0** when:

1. **No files to index** — Indexing only includes:
   - **AGENT_MEMORY.md** at `workspace_dir/AGENT_MEMORY.md` (default: `config/workspace/AGENT_MEMORY.md`). The file must **exist** and have content.
   - **Daily memory** for yesterday and today: `workspace_dir/memory/YYYY-MM-DD.md` (e.g. `config/workspace/memory/2025-02-21.md`). If those two files don’t exist, they aren’t indexed.
2. **Indexing runs only at startup** — So if you create or edit AGENT_MEMORY.md or daily files *after* Core has started, the vector store is not updated until you **restart Core** (or use the tools below to re-sync).
3. **Embedder or vector store not ready** — If the embedding server or Chroma isn’t ready at startup, sync can fail and you get 0 chunks.

**What to do:**

- **Create the file so indexing has something to index:**  
  Create `config/workspace/AGENT_MEMORY.md` (and optionally `config/workspace/memory/YYYY-MM-DD.md` for today). You can leave them empty or add a line; empty files produce 0 chunks, but the file existing allows the sync to run. Then **restart Core** so startup sync runs again.
- **Use the tools to populate and re-sync:**  
  When the model (or you) uses **append_agent_memory** or **append_daily_memory**, the file is created if missing and content is appended. Core can then **re-sync** agent memory so the new content is searchable without a restart (see implementation).
- **Check config:**  
  Ensure `use_agent_memory_search: true` and `use_agent_memory_file: true` in `config/core.yml`, and `workspace_dir: config/workspace` (or your chosen path).

**How agent memory and daily memory are used:**

- With **use_agent_memory_search: true** (default), the model does **not** get the full file in the prompt. It is told to use **agent_memory_search** (semantic search over the indexed chunks) and **agent_memory_get** (read by path and line range) to pull only relevant parts when answering questions about prior work, preferences, or facts. So the "size" is the number of searchable chunks; 0 means no chunks were indexed, so search returns nothing until you add content and re-sync or restart.

---

## Summary

- **AGENT_MEMORY.md** = long-term, one file. When **use_agent_memory_search: true** (default): no content injected; model uses **agent_memory_search** + **agent_memory_get** to pull only relevant parts. When false: last 5k chars injected.
- **Daily memory** = short-term, `memory/YYYY-MM-DD.md`. With retrieval on, it is indexed and recalled via the same tools; with retrieval off, yesterday + today are injected.
- Both can be enabled together. They can duplicate if you write the same content to both — use daily for session/scratch and AGENT_MEMORY for lasting facts to minimize duplication.
- On `/memory/reset`, if daily memory is enabled, yesterday’s and today’s daily files are cleared as well. See **SessionAndDualMemoryDesign.md** for the dual-memory (RAG + AGENT_MEMORY) design.
