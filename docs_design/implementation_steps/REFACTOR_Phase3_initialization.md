# Core.py refactor — Phase 3: Extract initialization

**Status:** Done  
**Branch:** refactor/core-multi-module (or as created)

## Goal

Move the “heavy” initialization logic (vector stores, embedder, knowledge base, memory backend) from `Core.initialize()` into a dedicated module. `Core.initialize()` becomes a thin wrapper that calls `run_initialize(self)` and then continues with queue tasks, tool registration, plugin manager, and route registration (unchanged).

## Changes

### 1. New file: core/initialization.py

- **run_initialize(core)**  
  Performs:
  - `core.initialize_vector_store(collection_name="memory")`
  - `core.embedder = LlamaCppEmbedding()`
  - `_create_skills_vector_store(core)`, `_create_plugins_vector_store(core)`, `_create_agent_memory_vector_store(core)`
  - `core.knowledge_base = None` then `_create_knowledge_base(core)`
  - Memory backend: if `memory_backend == "cognee"` and `Util().has_memory()`, creates Cognee memory (with LLM/embedding config resolution); on failure falls back to chroma. Otherwise builds graph_store (if configured) and sets `core.mem_instance = Memory(...)` when not already set.
  - All attributes are set on `core`; no dependency on `core.core`.

- **Helpers (take `core` as first argument):**
  - `_create_skills_vector_store(core)` — skills vector store when `skills_use_vector_search`.
  - `_create_plugins_vector_store(core)` — plugins vector store when `plugins_use_vector_search`.
  - `_create_agent_memory_vector_store(core)` — agent memory vector store when `use_agent_memory_search`; on failure sets `core.agent_memory_vector_store = None`.
  - `_create_knowledge_base(core)` — dispatches to Cognee or built-in RAG (chroma) per config.
  - `_create_knowledge_base_cognee(core, meta, kb_cfg)` — Cognee KB with LLM/embedding auto-fill from `Util().main_llm()` / `Util().embedding_llm()`.

- **Imports:** `Util`, `LlamaCppEmbedding`, `LlamaCppLLM`, `Memory`, `create_vector_store`, `CogneeMemory`, `CogneeKnowledgeBase`, `KnowledgeBase`, `get_graph_store`, `logger`. No import of `core.core`.

### 2. core/core.py

- **Import:** `from core.initialization import run_initialize`
- **Core.initialize():** Replaced the previous long body (and the five helper methods) with:
  - `run_initialize(self)`
  - Then unchanged: `self.request_queue_task = ...`, `self.response_queue_task = ...`, `self.memory_queue_task = ...`, `self.memory_summarization_scheduler_task = ...`, `self.kb_folder_sync_task = ...`, `register_builtin_tools(...)`, `register_routing_tools(...)`, `self.plugin_manager = PluginManager(self)`, `self._pinggy_state_getter = ...`, `register_all_routes(self)`.
- **Removed from Core:**  
  `_create_skills_vector_store`, `_create_plugins_vector_store`, `_create_agent_memory_vector_store`, `_create_knowledge_base`, `_create_knowledge_base_cognee`, and the inlined vector store/embedder/KB/Cognee/chroma block that was inside `initialize()`.
- **Unchanged:** `initialize_vector_store()` remains on Core (used by `run_initialize` via `core.initialize_vector_store(...)`).

## Logic and stability

- **Correctness:** Behavior is unchanged; only the definition location and the use of `core` instead of `self` in the extracted helpers. Cognee/chroma fallback and config resolution match the original.
- **Robustness:** Same try/except and defensive checks; no new code paths that could crash Core.
- **Completeness:** All initialization that was inside `initialize()` (up to “memory backend done”) is now in `run_initialize()`; the rest (queue tasks, tools, plugin_manager, routes) stays in `Core.initialize()` in core.py.

## Tests

- Run Core startup (e.g. `run()` or entry point) and confirm vector store, embedder, knowledge base, and memory backend initialize as before. If your env uses Cognee, confirm Cognee memory is used; if chroma, confirm chroma memory and optional graph store.
- Existing tests that depend on Core or routes should still pass (e.g. `tests/test_core_routes.py` with project env).

## Summary

| Item | Before | After |
|------|--------|--------|
| Core.initialize() body (vector store → memory backend) | ~235 lines in core.py | Delegated to run_initialize(self) |
| Helper methods in core.py | 5 methods (~190 lines) | Removed |
| core/initialization.py | — | ~295 lines (run_initialize + 5 helpers) |

Phase 3 is complete. Proceed to Phase 4 (inbound handlers) when ready.
