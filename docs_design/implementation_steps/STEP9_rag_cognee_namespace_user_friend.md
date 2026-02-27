# Step 9: RAG / Cognee namespace by (user_id, friend_id) — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) implementation step 9.

**Goal:** Add (user_id, friend_id) to RAG/memory namespace so add and search are scoped per friend. KB path is already per-friend under sandbox; ensure Cognee KB search can scope by friend_id when provided. Never crash Core.

---

## 1. What was implemented

### 1.1 Memory (Cognee / RAG) — core and tools

- **process_text_message (memory add):** When adding to memory, pass **agent_id=_fid** (friend_id from request) instead of app_id, so Cognee memory dataset is per (user_id, friend_id). _fid was already resolved in that block.
- **answer_from_memory:** Resolve **_mem_scope** from request: `(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw")` if request else agent_id. Pass _mem_scope to **_fetch_relevant_memories** as the agent_id argument so memory search is scoped to that friend.
- **search_memory:** Add optional **friend_id** parameter. When provided, use it as **agent_id** (and in filters) for mem.search; otherwise fall back to app_id. So memory_search tool can scope by friend.
- **memory_search tool (builtin):** Pass **context.friend_id** into **core.search_memory(..., friend_id=friend_id)** so results are scoped to the current friend.

Cognee memory backend already keys datasets by (user_id, agent_id); we now pass friend_id as agent_id from Core and tools, so namespace is (user_id, friend_id).

### 1.2 Knowledge base (Cognee) — optional friend_id scope

- **_kb_dataset_prefix(user_id, friend_id=None):** When friend_id is set, return `kb_{user}_{friend}`; otherwise `kb_{user}` (backward compat). Safe _safe() used for both.
- **_list_user_kb_datasets_async(user_id, friend_id=None):** When friend_id is set, list only datasets with prefix `kb_{user}_{friend}_`; otherwise unchanged.
- **search(user_id, query, limit, friend_id=None):** Pass friend_id into _list_user_kb_datasets_async so search only hits that friend’s datasets when friend_id is provided. Existing datasets (kb_{user}_*) are used when friend_id is None.
- **Core (answer_from_memory):** When calling **kb.search**, pass **friend_id=_mem_scope**. If the backend does not accept friend_id (TypeError), fall back to search without friend_id so other backends keep working.

Note: **add()** and sidecar do not yet take friend_id; new documents added via add() remain under kb_{user}_*. To fully scope KB by friend, add() (and sidecar) would need friend_id in a follow-up; search scoping is in place for when those datasets exist.

---

## 2. Robustness and safety

- **_mem_scope / _fid:** Normalized with str().strip() or "HomeClaw"; request may be None — handled.
- **search_memory:** friend_id normalized; scope default "HomeClaw"; mem.search in try/except; returns [] on exception.
- **KB search:** friend_id optional; _kb_dataset_prefix uses _safe(); TypeError fallback in Core so non-Cognee KB backends do not break.
- No new code path raises; existing try/except and defaults preserved.

---

## 3. Files touched

| File | Change |
|------|--------|
| **core/core.py** | process_text_message: memory add with agent_id=_fid. answer_from_memory: _mem_scope from request; _fetch_relevant_memories(_mem_scope); kb.search(..., friend_id=_mem_scope) with TypeError fallback. search_memory: friend_id param, pass as agent_id. |
| **tools/builtin.py** | memory_search: pass context.friend_id to core.search_memory(..., friend_id=friend_id). |
| **memory/cognee_knowledge_base.py** | _kb_dataset_prefix(user_id, friend_id=None); _list_user_kb_datasets_async(..., friend_id=None); search(..., friend_id=None). |

---

## 4. Review

- **Logic:** Memory add/search and KB search scoped by (user_id, friend_id) when friend_id is provided; backward compat when not. ✓
- **Robustness:** Normalized ids; try/except and fallbacks; no new raises. ✓

**Step 9 is complete.** Next: Step 10 (Cron / reminders: (user_id, friend_id)).
