# Cognee Integration & Upgrade Guide

This document describes how HomeClaw integrates with Cognee (vendored in `vendor/cognee`) and how to upgrade Cognee safely.

---

## 1. Integration strategy (no Cognee source changes)

We **do not modify Cognee’s source**. Integration is done by:

- **Configuration:** `apply_cognee_config()` in `memory/cognee_adapter.py` maps our config (e.g. `config/memory_kb.yml` → `cognee` section) to Cognee’s environment variables. Core also fills `cognee.llm` / `cognee.embedding` from `main_llm` and `embedding_llm` when empty.
- **Instructor patch:** `memory/instructor_patch.py` patches Instructor (and LiteLLM) so that cognify works with local LLMs (system message first, no “coroutine not callable” when using sync paths). Applied at memory import and again when creating CogneeMemory / CogneeKnowledgeBase.
- **sys.path:** `main.py` and `core/core.py` add `vendor/cognee` to `sys.path` so `import cognee` resolves to the vendored package.

After an upgrade, only our adapter and config mapping might need small changes if Cognee’s **public** API or env var names change.

---

## 2. Where Cognee is used

| Location | Purpose |
|----------|---------|
| **main.py** | Add `vendor/cognee` to `sys.path` before any imports; apply instructor patch early. |
| **core/core.py** | Add `vendor/cognee` to `sys.path` (when Core is loaded first). |
| **core/initialization.py** | Create `CogneeMemory` / `CogneeKnowledgeBase`; fill `cognee.llm` and `cognee.embedding` from `main_llm` / `embedding_llm` when empty. |
| **memory/__init__.py** | Apply instructor patch on memory package import. |
| **memory/cognee_adapter.py** | `apply_cognee_config()`, `CogneeMemory`: add → cognify → search; reset via `datasets.delete_all()`; summarization via `list_datasets` + `list_data`/`get_data` + `delete_data`. |
| **memory/cognee_knowledge_base.py** | `CogneeKnowledgeBase`: add/search/delete by source; Starlette `HTTP_422_UNPROCESSABLE_CONTENT` compatibility shim. |
| **memory/instructor_patch.py** | Patch Instructor + LiteLLM for local LLM cognify (system message first, retry_sync coroutine handling). |

---

## 3. Cognee API we rely on

These are the **public** entry points we use. When upgrading Cognee, check their signatures and behavior.

| API | Used in | Notes |
|-----|---------|--------|
| `cognee.add(data, dataset_name=...)` | cognee_adapter.add, cognee_knowledge_base.add | Async; `data` is string or list. |
| `cognee.cognify(datasets=[...])` | cognee_adapter.add | Async; runs after add. |
| `cognee.search(query, datasets=[...], top_k=...)` | cognee_adapter.search | Async; returns list of results. |
| `cognee.datasets.list_datasets(user=None)` | cognee_adapter (search, get_all_async), cognee_knowledge_base | Async; returns list of dataset-like objects with `.id`, `.name`. |
| `cognee.datasets.list_data(dataset_id: UUID, user=None)` | cognee_adapter.get_all_async | Async; returns list of data items (id, content/text, created_at, etc.). We use this when `get_data` / `get_dataset_data` are not present. |
| `cognee.datasets.delete_data(dataset_id, data_id, user=None)` | cognee_adapter.delete_async | Async; we pass UUIDs. |
| `cognee.datasets.delete_all(user=None)` | cognee_adapter.reset | Async; clears all datasets for the default user. We use this when available; fallback to deprecated `cognee.delete(all=True)` for older Cognee. |
| `cognee.config.set_llm_config({...})` | cognee_adapter._apply_llm_only (fallback LLM retry) | Optional; for cognify retry with cloud fallback. |

---

## 4. Config → Cognee env mapping

`apply_cognee_config(config)` in `memory/cognee_adapter.py` sets:

- **Relational:** `relational.provider` → `DB_PROVIDER`, `relational.name` → `DB_NAME`, plus host/port/username/password → `DB_*`.
- **Vector:** `vector.provider` → `VECTOR_DB_PROVIDER` (e.g. chroma → ChromaDB, lancedb → LanceDB), plus url/port/key.
- **Graph:** `graph.provider` → `GRAPH_DATABASE_PROVIDER`, plus url/username/password.
- **LLM:** `llm.provider/model/endpoint/api_key` → `LLM_PROVIDER`, `LLM_MODEL`, `LLM_ENDPOINT`, `LLM_API_KEY`. Sets `LLM_API_KEY=local` when endpoint is set and key is missing.
- **Embedding:** `embedding.*` → `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_ENDPOINT`, `EMBEDDING_API_KEY`, `HUGGINGFACE_TOKENIZER`, etc. Drops `EMBEDDING_DIMENSIONS` for local embedding; sets `litellm.drop_params = True`.
- **Access control:** If `ENABLE_BACKEND_ACCESS_CONTROL` is not set, we set it to `"false"` so Cognee does not require a default user.

If Cognee adds or renames env vars, update `apply_cognee_config()` and, if needed, `config/memory_kb.yml` comments.

---

## 5. Upgrade steps

1. **Replace vendored Cognee**  
   Replace the contents of `vendor/cognee` with the new Cognee version (e.g. copy from upstream repo or release tarball). Do not remove the folder; keep the same layout so `sys.path` still points to the directory that contains the `cognee` package.

2. **Reinstall Cognee dependencies**  
   ```bash
   pip install -r requirements-cognee-deps.txt -i https://pypi.org/simple
   ```  
   Align `requirements-cognee-deps.txt` with Cognee’s current dependencies if their `pyproject.toml` or `requirements` changed.

3. **Check API compatibility**  
   - In `vendor/cognee/cognee/__init__.py`, confirm `add`, `cognify`, `search`, `delete`, `config`, `datasets` are still exported.  
   - In `vendor/cognee/cognee/api/v1/datasets/datasets.py` (or equivalent), confirm:
     - `list_datasets(user=None)`
     - `list_data(dataset_id, user=None)` (or `get_data`/`get_dataset_data` if we ever rely on them)
     - `delete_data(dataset_id, data_id, user=None)`
     - `delete_all(user=None)`
   - If `cognee.delete(all=True)` is removed, our adapter already prefers `cognee.datasets.delete_all(user=None)` and only falls back to `cognee.delete(all=True)` for older versions.

4. **Check env var names**  
   Compare Cognee’s `.env.template` or `infrastructure/llm/config.py` (and DB/vector/graph config) with the keys we set in `apply_cognee_config()`. Adjust our mapping if names or semantics changed.

5. **Run tests and smoke test**  
   - Run HomeClaw tests (including any Cognee-related tests).  
   - Manually: start with `memory_backend: cognee`, add a message, trigger cognify, run a search, and optionally memory reset. Confirm no import errors, no “coroutine not callable”, and no missing env/config errors.

6. **Instructor / LiteLLM**  
   If Cognee bumps Instructor or LiteLLM and we see “coroutine not callable” or “system message first” again, update `memory/instructor_patch.py` (and possibly patch application order in `main.py` / `memory/__init__.py`).

---

## 6. Fragile points to watch

- **Instructor patch:** Must be applied before any code imports `instructor` or `cognee`. Applied in `main.py`, `memory/__init__.py`, and when constructing `CogneeMemory` / `CogneeKnowledgeBase`. If Cognee changes how it uses Instructor (e.g. different entry points), the patch might need to target different functions or modules.
- **Starlette 422 constant:** `memory/cognee_knowledge_base.py` sets `HTTP_422_UNPROCESSABLE_CONTENT = HTTP_422_UNPROCESSABLE_ENTITY` if missing (for older Starlette). If Cognee drops that usage, the shim can be removed.
- **Dataset object shape:** We assume objects returned by `list_datasets()` have `.id` and `.name` (or dict with `"id"`, `"name"`). If Cognee changes the return type (e.g. to Pydantic models with different attribute names), update `cognee_adapter` and `cognee_knowledge_base` accordingly.
- **UUID vs string:** We pass UUIDs to `list_data` and `delete_data` when the Cognee API expects UUID; we convert from our composite id strings. If Cognee switches to string IDs, adjust the adapter.

---

## 7. Quick reference: key files to touch after upgrade

- **Adapter / config:** `memory/cognee_adapter.py` (`apply_cognee_config`, `CogneeMemory.add/search/reset/get_all_async/delete_async`, `supports_summarization`).
- **KB:** `memory/cognee_knowledge_base.py` (Starlette shim, Cognee add/search/delete by source).
- **Init:** `core/initialization.py` (filling `cognee.llm` / `cognee.embedding` from main/embedding LLM).
- **Patch:** `memory/instructor_patch.py` (if cognify or local LLM behavior breaks).
- **Path:** `main.py`, `core/core.py` (only if you change where Cognee is vendored).

For local LLM setup (llama.cpp, Ollama, etc.), see **docs_design/CogneeLocalLLM.md**.
