# RAG memory summarization — design (long-term memory)

This doc outlines a **summary logic** for stored RAG memories so that we can keep long-term value without unbounded growth or relying on a per-message “should we store?” LLM call.

---

## 1. Context and goals

- **Current:** User messages are added to RAG memory (vector store) when `use_memory` is true. We no longer rely on an extra LLM call to judge each message (default `memory_check_before_add: false`). Retrieval (top-k, similarity) filters at read time.
- **Problem:** Over time, the number of raw memories grows. Old, low-relevance or redundant items can dilute search and use storage; we still want a compact “long-term” view.
- **Goal:** Periodically **summarize a group of memories** into one or more summary chunks and treat them as long-term memory. Decide how to handle the **originals** (delete, or keep for some time).

---

## 2. High-level flow

1. **Trigger** — When to run summarization (e.g. every N new memories per user, or on a schedule).
2. **Group** — Which memories to batch (e.g. by `user_id`, by time window or by count).
3. **Summarize** — One LLM call over the batch → summary text(s). Store as memory with metadata marking it as a summary and linking to originals.
4. **Handle originals** — Either delete them, or keep them for a TTL (e.g. 7 days) then delete, or keep forever (no delete).

Search stays unchanged: summaries are stored as normal memories (same `user_id`, etc.) so they appear in `_fetch_relevant_memories` and `memory_search` like any other chunk. Optionally we can add metadata (e.g. `is_summary: true`, `summarized_ids: [...]`) so that later we can tune ranking or dedup (e.g. prefer raw when recent).

---

## 3. When to run summarization (trigger)

| Option | Description | Pros / cons |
|--------|-------------|-------------|
| **Count-based** | After every N new memories per user (e.g. 50). | Simple; predictable batch size. Need to track “last summarized count” per user. |
| **Time-based (cron)** | Daily or weekly job: “summarize memories older than T” (e.g. older than 7 days). | Decouples from real-time path; easy to run in background. Need a scheduler or external cron. |
| **Hybrid** | Cron job that, per user, selects oldest K memories that are older than D days and summarizes them. | Combines “batch by time” with “don’t summarize very recent”. |

**Recommendation:** Start with **time-based (cron)** or **hybrid**: e.g. once per day, for each user, take memories with `created_at` older than 7 days, group into batches of up to 50, summarize each batch. That avoids touching the hot path (process_memory_queue) and keeps implementation simple.

---

## 4. How to group memories

- **By user:** Always restrict to one `user_id` (and optionally `agent_id` / `run_id` if we want per-session summarization). So “a group” = one user’s memories.
- **By time:** e.g. “all memories with `created_at` in the range [T − 7d, T − 1d]” so we don’t summarize the last 24 hours.
- **By count:** From the oldest, take up to K items (e.g. 30–50) so the LLM prompt stays bounded.

So: **group = same user_id, created_at before (now − min_age_days), ordered by created_at ascending, limit K.**  
We may have multiple groups per user (e.g. one batch per week). Each batch becomes one summary (or a few if we split by topic later).

---

## 5. Summarization step

- **Input:** List of memory texts (and optionally ids, created_at) for one batch.
- **LLM prompt:** e.g. “Summarize the following set of conversation-derived memories into a concise long-term summary. Preserve important facts, preferences, and decisions; drop trivial chitchat and one-off questions. Output one or more short paragraphs.”
- **Output:** One or more summary paragraphs. Each is stored via the same `mem_instance.add(...)` (or a dedicated “summary” path) with metadata, e.g.:
  - `is_summary: true`
  - `summarized_memory_ids: ["id1", "id2", ...]`
  - `summarized_until: "2025-02-10"` (latest created_at in the batch)
  - `user_id`, `agent_id`, etc. same as originals so search returns them.

Storing summaries as normal memories keeps search simple; metadata allows future ranking (e.g. prefer raw for “last 7 days”, prefer summary for “older than 30 days”).

---

## 6. What to do with the original memories

| Policy | Description | Pros | Cons |
|--------|-------------|------|------|
| **Delete immediately** | After storing the summary, delete all `summarized_memory_ids` from the vector store. | Saves space; store stays small. | No way to recover detail for that period; search only sees the summary. |
| **Keep for TTL** | Delete originals only after X days (e.g. 7) from their `created_at`. So we have: raw for recent, summary for old. | Good balance: recent = full detail, long-term = summary. | Slightly more logic (delete in a separate pass when age > TTL). |
| **Keep forever** | Never delete; summaries are additional chunks. | No loss of detail; search can return both. | Store grows; may need to down-rank or dedup summaries when raw exists. |

**Chosen policy:** **Keep for TTL** with a **long TTL** (e.g. **365 days**). Originals are deleted only when `created_at` is older than `keep_original_days`; until then both raw and summary can exist. **Summaries are kept forever** (never deleted). So we never need a per-message LLM call; summarization runs at free time (scheduler or cron).

---

## 7. When to run (configurable)

| Option | Config | Behavior |
|--------|--------|----------|
| **daily** | `schedule: daily` | Run once per day; next run = now + 1 day (or `interval_days`). |
| **weekly** | `schedule: weekly` | Run once per week; next run = now + 7 days. |
| **next_run** | `schedule: next_run`, `interval_days: N` | After each run, store next run time = now + N days; internal scheduler or cron calls `POST /memory/summarize` when due. |

Summarization is done **at free time** (background scheduler every hour checks `next_run`, or external cron hits the endpoint). No extra LLM call on every user message.

---

## 8. Config (implemented)

In `config/core.yml`:

```yaml
memory_summarization:
  enabled: false
  schedule: daily              # daily | weekly | next_run
  interval_days: 1             # for next_run: run again after this many days
  keep_original_days: 365       # TTL for raw memories; after this they are deleted (summary stays forever)
  min_age_days: 7              # only summarize memories older than this (days)
  max_memories_per_batch: 50    # max raw memories per summary batch
```

- **Endpoint:** `POST /memory/summarize` runs one pass (optional: call from cron).
- **State file:** `database/memory_summarization_state.json` stores `last_run` and `next_run` (ISO datetime).
- **Backend:** **Chroma** and **Cognee** both support summarization when the backend exposes list + get_data + delete by id. Cognee uses `datasets.list_datasets`, `get_data`/`get_dataset_data`, and `delete_data`/`delete`; ids are composite `dataset_id:data_id`. Summaries are stored with a text marker `[HomeClaw summary] ` when the backend does not store metadata (Cognee).

---

## 9. Implementation outline (done)

1. **Remove (or keep off) the per-message judge LLM**  
   Already done: `memory_check_before_add` defaults to false.

2. **Memory backend**  
   Ensure we can:
   - List memories by `user_id` with `created_at` (and optional ordering). Chroma/in-memory already store metadata; we may need to sort in application code if the vector DB doesn’t support order by.
   - Delete by a list of ids (already have `delete(memory_id)`; batch delete or loop).

3. **Summarization job**  
   - For each `user_id` that has memories:
     - Fetch memories with `created_at` < now − min_age_days, ordered by created_at asc, limit max_memories_per_batch.
     - If none, skip.
     - Build LLM prompt with the batch of texts → get summary.
     - Store summary with `mem_instance.add(..., metadata={is_summary: true, summarized_memory_ids: [...], ...})`.
     - If original_policy is "delete", delete the batch ids; if "ttl", record them (or store in summary metadata) and delete in a separate TTL pass.

4. **TTL pass**  
   - If original_policy is "ttl": list all memories that have `is_summary: true`, read `summarized_memory_ids`, and delete any of those ids whose `created_at` is older than keep_original_days. (Or: scan all raw memories and delete if created_at older than keep_original_days and id is in any summarized_memory_ids; depends how we store the mapping.)

5. **API**  
   - `POST /memory/summarize`: trigger one run. Called by cron or by Core’s internal scheduler (when `enabled` and schedule are set).
   - Internal scheduler: background task checks every hour; if `now >= next_run`, runs the job and updates `next_run` in the state file.

---

## 10. Summary

| Question | Choice |
|----------|--------|
| Remove judge LLM? | Yes — `memory_check_before_add` defaults to false; no per-message LLM call. |
| Summarize? | Yes — periodic summarization of a **group** of memories (by user, by age, by count). |
| How to handle originals? | **Keep for TTL** (default **365 days**); then delete. **Summaries kept forever.** |
| When to run? | Configurable: **daily**, **weekly**, or **next_run** (next run time stored after each run). Runs at free time (scheduler or cron). |
| Where are summaries stored? | Same RAG memory store (Chroma); same add/search path. Metadata: `is_summary`, `summarized_memory_ids`, `summarized_until`. |

Implementation: Chroma and Cognee memory backends (Cognee when package exposes `datasets.get_data` and `delete_data`). `POST /memory/summarize` + optional internal scheduler that checks `next_run` every hour.
