# HomeClaw Enhancement Plan: OpenClaw-Inspired Improvements (v2.0)

## Overview

This document outlines a phased plan to enhance HomeClaw by incorporating architectural patterns from OpenClaw, with a focus on **context management as a pluggable lifecycle** and **memory as a single-slot plugin**. The plan prioritizes refactoring existing infrastructure over creating parallel implementations.

**Key insight from OpenClaw:** The central architectural innovation is not "compaction" or "deduplication" in isolation — it's the **ContextEngine** as a pluggable protocol that owns the entire context pipeline: ingestion → assembly → compaction → maintenance. Everything else (memory search, hooks, diagnostics) flows from that foundation.

---

## TABLE OF CONTENTS

1. [Pre-Flight: What Already Exists](#pre-flight-what-already-exists)
2. [Phase 0: ContextEngine Protocol & Session Rotation](#phase-0-contextengine-protocol--session-rotation)
3. [Phase 1: Memory Plugin SDK & Single-Slot Architecture](#phase-1-memory-plugin-sdk--single-slot-architecture)
4. [Phase 2: Workspace Memory Files & Enhanced Assembly](#phase-2-workspace-memory-files--enhanced-assembly)
5. [Phase 3: Hooks, Lifecycle & Diagnostics](#phase-3-hooks-lifecycle--diagnostics)
6. [Phase 4: Subagent Registry & Task Lifecycle](#phase-4-subagent-registry--task-lifecycle)
7. [Phase 5: Approval System Enhancement](#phase-5-approval-system-enhancement)
8. [Phase 6: Session Repair, Model Auth & Tool Audit](#phase-6-session-repair-model-auth--tool-audit)
9. [Phase 0–3 Extensions](#phase-03-extensions-completed)
10. [Project Structure Changes](#project-structure-changes)
11. [Dependency Graph](#dependency-graph)
12. [Gantt Chart Summary](#gantt-chart-summary)
13. [Key Milestones](#key-milestones)
14. [Design Decisions](#design-decisions)

---

## PRE-FLIGHT: WHAT ALREADY EXISTS

Before building anything new, inventory what HomeClaw already ships:

| Capability | Location | Maturity | Plan Impact |
|---|---|---|---|
| Token estimation | `base/token_estimate.py` | Working | **Use, don't rebuild** |
| Message-count compaction | `core/llm_loop.py` L3122-3243 | Working | **Refactor into ContextEngine** |
| Message-based trimming | `base/friend_presets.py` | Working | Keep as auxiliary path |
| Memory base classes (ABC) | `memory/base.py` | Working | **Foundation for MemoryPlugin** |
| Composite memory backend | `memory/composite_memory.py` | Working | Refactor to implement MemoryPlugin |
| Content-based dedup | `memory/composite_memory.py` L24-34 | Working | Move to ContextEngine.ingest() |
| Dedup hashing | `memory/mem.py` (hashlib) | Working | Reuse |
| AGENT_MEMORY.md | `base/workspace.py` L19 | Working | Keep; add workspace MEMORY.md |
| Daily notes (YYYY-MM-DD.md) | `base/workspace.py` L567+ | Working | Keep; add vector-search indexing |
| Plugin manager | `base/PluginManager.py` | Working | Extend for memory slot |
| Vector store factory | `memory/vector_store_factory.py` | Working | Keep; memory plugin wraps this |
| Cognee adapter | `memory/cognee_adapter.py` | Working | Become one MemoryPlugin backend |
| MemOS adapter | `memory/memos_adapter.py` | Working | Become one MemoryPlugin backend |

**Rule:** Prefer refactoring existing code over creating parallel modules. If a capability exists, integrate it into the new architecture rather than duplicating it.

---

## PHASE 0: CONTEXTENGINE PROTOCOL & SESSION ROTATION

*(Foundation — Week 1-2)*

### Goal

Define a pluggable `ContextEngine` protocol (ABC) that owns the full context lifecycle, and refactor HomeClaw's existing compaction/message-trimming into a `LegacyContextEngine` that implements it. This is the **single most important architectural change** — every subsequent phase builds on it.

### Why This Matters

OpenClaw's `ContextEngine` (defined in `src/context-engine/types.ts`) treats context management as a **first-class lifecycle**, not an ad-hoc step inside the LLM loop:

```
bootstrap → maintain → ingest → assemble → compact → afterTurn
```

HomeClaw currently does context management inline in `core/llm_loop.py` (~6900 lines). The compaction logic at lines 3122-3243 trims messages in-place when the count exceeds a threshold. It works but:

- Can't rotate transcripts (audit trail is lost)
- Can't rewrite transcript entries safely
- Can't defer compaction debt across turns
- No abort signal support during long compaction runs
- Not pluggable — can't swap in alternative compaction strategies

### Tasks

| Task ID | Task | Description | Estimated Effort |
|---------|------|-------------|------------------|
| **0.1** | Define `ContextEngine` ABC | Create protocol with: `bootstrap()`, `maintain()`, `ingest()`, `ingestBatch()`, `afterTurn()`, `assemble()`, `compact()`, `dispose()`. Include token budget, abort signal, and runtime context params. | 3h |
| **0.2** | `LegacyContextEngine` implementation | Refactor existing compaction from `llm_loop.py` L3122-3243 into a class implementing the ContextEngine protocol. `ingest()` returns `{ingested: false}` (no-op; existing session manager handles persistence). `assemble()` returns messages as-is (pass-through). `compact()` wraps the existing flush+trim logic. | 5h |
| **0.3** | ContextEngine registry | Factory-based registration system with ownership tracking and slot resolution. Plugins register engines by id; the runtime resolves the active engine at session start. | 3h |
| **0.4** | Session rotation on compaction | When compaction fires, create a new session file, write a [`Previous conversation compacted`] summary as the first system message, and re-anchor the conversation. Keep the old session file for audit/debug. | 4h |
| **0.5** | Wire into LLM loop | Replace inline compaction calls in `llm_loop.py` with calls to the registered ContextEngine. `assemble()` runs before each LLM call to build the prompt; `compact()` runs when token budget is exceeded; `afterTurn()` runs after each successful response. | 4h |
| **0.6** | Inline dedup via `ingest()` | `LegacyContextEngine.ingest()` checks content hash against recent storage and returns `{ingested: false}` for duplicates. (Replaces the need for a standalone dedup phase.) | 2h |
| **0.7** | Abort signal + timeout | Add `abortSignal` support to `compact()` so long compactions can be cancelled on run abort or safety timeout. | 2h |
| **0.8** | Tests | Unit tests for LegacyContextEngine, context assembly, compaction with rotation, and dedup at ingestion. | 3h |

### Deliverables

- `core/context_engine/` — new module
  - `__init__.py`
  - `protocol.py` — `ContextEngine` ABC and result types
  - `registry.py` — engine registration and resolution
  - `legacy_engine.py` — `LegacyContextEngine`
  - `compact_runtime.py` — session rotation logic
- Refactored `core/llm_loop.py` — context management delegated to engine

### What This Replaces from the Old Plan

- Old Phase 1 "Memory Compaction" → integrated here at the protocol level
- Old Phase 2 "Memory Deduplication" → folded into `ingest()` contract
- No new `/memory/compact/` directory — refactor in place

---

## PHASE 1: MEMORY PLUGIN SDK & SINGLE-SLOT ARCHITECTURE

*(Medium Priority — Week 2-3, parallel with Phase 0 completion)*

### Goal

Define a **MemoryPlugin** interface (distinct from HomeClaw's existing `MemoryBase` ABC) and make memory a single-slot plugin system — only one memory plugin active per agent at a time. This follows OpenClaw's explicit design principle: *"Memory is a special plugin slot where only one memory plugin can be active at a time."*

### Why This Matters

HomeClaw's current `memory/base.py` defines abstract base classes for VectorStore, Embedding, and LLM — but these are **implementation interfaces**, not **plugin contracts**. They don't define:
- How to search memory with a query and get ranked results
- How to build the memory section of the system prompt
- How memory flush planning works (when/why to flush)
- How memory corpus supplements register with the engine

OpenClaw addresses this with a dedicated **MemoryHost SDK** (`packages/memory-host-sdk/`) and a clean plugin boundary in `src/plugins/memory-state.ts`. The `MemoryPlugin` interface is the contract; backends implement it.

### Tasks

| Task ID | Task | Description | Estimated Effort |
|---------|------|-------------|------------------|
| **1.1** | Define `MemoryPlugin` protocol | Create ABC with: `search(query, maxResults, agentSessionKey)` → `SearchResult[]`, `get(lookup, fromLine, lineCount)` → `DocumentContent | None`, `buildPromptSection(availableTools)` → `str`, `flush(params)` → `FlushResult`, `health()` → `HealthStatus`. | 3h |
| **1.2** | `CompositeMemoryPlugin` adapter | Wrap existing `memory/composite_memory.py` to implement `MemoryPlugin`. Preserve all existing behavior; add the search/get/prompt-building methods. | 4h |
| **1.3** | Single-slot registration | Extend `PluginManager` with `register_memory_plugin(plugin: MemoryPlugin)`. Only one plugin active per agent; registration replaces previous. Add `get_active_memory_plugin()` resolver. | 3h |
| **1.4** | `CogneeMemoryPlugin` adapter | Wrap `memory/cognee_adapter.py` as a standalone single-backend `MemoryPlugin` for users who want only Cognee. | 2h |
| **1.5** | `MemosMemoryPlugin` adapter | Wrap `memory/memos_adapter.py` as a standalone single-backend `MemoryPlugin`. | 2h |
| **1.6** | Wire into ContextEngine | ContextEngine calls active MemoryPlugin for: prompt section building during `assemble()`, memory search within tool execution, flush planning during `afterTurn()`. | 3h |
| **1.7** | Configuration | Add `memory.plugin` config key in `core.yml` to select the active memory plugin by id. Migration: existing `memory_backend` config maps to the appropriate plugin. | 2h |
| **1.8** | Tests | Unit tests for each MemoryPlugin adapter, single-slot registration, config migration. | 3h |

### Deliverables

- `core/memory_plugin/` — new module
  - `__init__.py`
  - `protocol.py` — `MemoryPlugin` ABC, `SearchResult`, `FlushResult`, `HealthStatus`
  - `composite_adapter.py` — wraps `memory/composite_memory.py`
  - `cognee_adapter.py` — wraps `memory/cognee_adapter.py`
  - `memos_adapter.py` — wraps `memory/memos_adapter.py`
  - `slot.py` — single-slot registration and resolution
- Extended `base/PluginManager.py` — memory slot support
- Updated `config/core.yml` — `memory.plugin` key

### What This Replaces from the Old Plan

- Old Phase 4 "Plugin Architecture for Memory" → redesigned as single-slot contract, not multi-backend registry
- Old Phase 1 deliverables (`/memory/compact/`) → replaced by Phase 0 ContextEngine
- Old Phase 2 deliverables (`/memory/deduplication/`) → folded into ContextEngine.ingest()

---

## PHASE 2: WORKSPACE MEMORY FILES & ENHANCED ASSEMBLY

*(Medium Priority — Week 3-4)*

### Goal

Add OpenClaw-style workspace memory capabilities while leveraging HomeClaw's existing daily notes and agent memory infrastructure. The key additions are: (1) `MEMORY.md` as a workspace-root shared memory file, (2) vector-searchable memory corpus (`memory/**/*.md`), and (3) improved context assembly that integrates memory search results.

### What's New vs What Already Exists

| Feature | Already in HomeClaw? | What Phase 2 Adds |
|---|---|---|
| `AGENT_MEMORY.md` | ✅ `base/workspace.py` L19 | Keep as-is |
| Daily notes `YYYY-MM-DD.md` | ✅ `base/workspace.py` L567+ | Add **vector-search indexing** |
| Workspace `MEMORY.md` | ❌ | New: shared across agents, vector-searchable |
| `memory/**/*.md` corpus | ❌ | New: multi-file memory with semantic search |
| Memory prompt section builder | ❌ (ad-hoc in llm_loop) | New: structured via MemoryPlugin |

### Tasks

| Task ID | Task | Description | Estimated Effort |
|---------|------|-------------|------------------|
| **2.1** | Workspace `MEMORY.md` support | Add `load_workspace_memory_file()` to `base/workspace.py`. Canonical name `MEMORY.md` at workspace root (legacy fallback: `memory.md`). Inject into system prompt via ContextEngine's `assemble()`. | 3h |
| **2.2** | Vector-search indexing for daily notes | Extend daily memory to be indexed by the vector store (not just file-injected). `MemoryPlugin.search()` includes daily note content. | 3h |
| **2.3** | `memory/**/*.md` corpus | Support an arbitrary directory of named memory files. Each file is indexed and searchable via `MemoryPlugin.search()`. Files are scoped per `(user_id, friend_id)`. | 3h |
| **2.4** | Structured memory prompt section | `MemoryPlugin.buildPromptSection()` produces the memory guidance block injected into the system prompt. Merges: workspace MEMORY.md, AGENT_MEMORY.md, relevant daily notes, and search hit citations. | 3h |
| **2.5** | Memory citation mode | Configurable citation style: inline references to specific memory files with line numbers, or summary-only. Controlled via `memory.citations_mode` in `core.yml`. | 2h |
| **2.6** | Context assembly integration | ContextEngine's `assemble()` calls MemoryPlugin's `buildPromptSection()` and appends the result as `systemPromptAddition`. Managed token budget ensures memory section doesn't crowd out conversation. | 2h |
| **2.7** | Tests | Unit tests for workspace MEMORY.md loading, corpus search, citation formatting, and assembly integration. | 2h |

### Deliverables

- Extended `base/workspace.py` — `MEMORY.md` loading, `memory/**/*.md` support
- Updated ContextEngine — `assemble()` calls MemoryPlugin for prompt section
- Updated MemoryPlugin — `search()` includes corpus, `buildPromptSection()` implemented
- Updated `config/core.yml` — `memory.citations_mode`

### What This Replaces from the Old Plan

- Old Phase 3 "Enhanced Memory Artifacts" → restructured; daily notes already exist, event log removed (no OpenClaw equivalent), MEMORY.md clarified as workspace-root file

---

## PHASE 3: HOOKS, LIFECYCLE & DIAGNOSTICS

*(Lower Priority — Week 4-5)*

### Goal

Add lifecycle hooks that enable memory flush scheduling, diagnostic health checks, and a `doctor` system for self-healing configuration. This phase makes the ContextEngine + MemoryPlugin architecture observable and maintainable.

### Tasks

| Task ID | Task | Description | Estimated Effort |
|---------|------|-------------|------------------|
| **3.1** | After-turn memory flush hook | ContextEngine's `afterTurn()` triggers `MemoryPlugin.flush()` when token budget or message count crosses a configurable threshold. The flush plan (soft threshold, force threshold, reserve floor) is resolved by the plugin. | 4h |
| **3.2** | Compaction hook | Expose a `compaction` hook that plugins can register for. Fires before and after compaction. Use case: log compaction events, trigger external sync. | 2h |
| **3.3** | Memory plugin health checks | `MemoryPlugin.health()` returns structured status: vector store connectivity, embedding model status, index size, last flush time, error count. Exposed via Core's health endpoint. | 3h |
| **3.4** | Doctor contracts for memory plugins | Each MemoryPlugin registers a `doctor()` method. The Core `doctor` CLI (`python -m main doctor`) detects broken config, explains the issue, backs up old config, and rewrites to canonical format. | 3h |
| **3.5** | Diagnostic events | Structured event emission for key lifecycle moments: compaction started/completed, memory flush started/completed, plugin registration, health status changes. Events are JSON-structured and loggable. | 2h |
| **3.6** | Prompt-cache telemetry | Track DeepSeek prompt-cache hit/miss in ContextEngine's runtime context. Surface in diagnostics. Useful for cost optimization when using cloud LLMs. | 2h |
| **3.7** | Tests | Unit tests for hooks, health checks, doctor contracts, and event emission. | 3h |

### Deliverables

- `core/hooks/` — lifecycle hook system
  - `__init__.py`
  - `lifecycle.py` — afterTurn, compaction hooks
- Extended MemoryPlugin protocol — `health()`, `doctor()` methods
- Extended ContextEngine — hook firing points
- Extended `core/routes/memory_routes.py` — health endpoint
- `core/doctor.py` extensions — memory plugin doctor

### What This Replaces from the Old Plan

- Old Phase 5 "Enhanced Error Handling & Diagnostics" → expanded with hooks, doctor contracts, and prompt-cache telemetry

---

## PROJECT STRUCTURE CHANGES

```
HomeClaw/
├── core/
│   ├── context_engine/            # NEW: Pluggable context management
│   │   ├── __init__.py
│   │   ├── protocol.py            # ContextEngine ABC + result types
│   │   ├── registry.py            # Engine registration + resolution
│   │   ├── legacy_engine.py       # LegacyContextEngine (refactored from llm_loop)
│   │   └── compact_runtime.py     # Session rotation + flush logic
│   ├── memory_plugin/             # NEW: Single-slot memory plugin system
│   │   ├── __init__.py
│   │   ├── protocol.py            # MemoryPlugin ABC + SearchResult/FlushResult/HealthStatus
│   │   ├── slot.py                # Single-slot registration + resolver
│   │   ├── composite_adapter.py   # Wraps memory/composite_memory.py
│   │   ├── cognee_adapter.py      # Wraps memory/cognee_adapter.py
│   │   └── memos_adapter.py       # Wraps memory/memos_adapter.py
│   ├── hooks/                     # NEW: Lifecycle hook system
│   │   ├── __init__.py
│   │   └── lifecycle.py           # afterTurn, compaction hook definitions
│   ├── llm_loop.py                # MODIFIED: delegates context to ContextEngine
│   └── doctor.py                  # MODIFIED: memory plugin doctor contracts
├── base/
│   ├── workspace.py               # MODIFIED: MEMORY.md loading, memory/**/*.md corpus
│   ├── PluginManager.py           # MODIFIED: memory slot registration
│   └── token_estimate.py          # UNCHANGED: reuse existing
├── memory/                        # UNCHANGED: existing backends remain
│   ├── base.py                    # UNCHANGED: existing ABCs for internal use
│   ├── mem.py                     # UNCHANGED
│   ├── composite_memory.py        # UNCHANGED: wrapped by composite_adapter
│   ├── cognee_adapter.py          # UNCHANGED: wrapped by cognee_adapter
│   ├── memos_adapter.py           # UNCHANGED: wrapped by memos_adapter
│   └── ...
├── config/
│   └── core.yml                   # MODIFIED: memory.plugin, memory.citations_mode keys
└── tests/
    ├── test_context_engine/        # NEW
    ├── test_memory_plugin/         # NEW
    └── test_hooks/                 # NEW
```

**Key principle:** New modules wrap and delegate to existing code. No parallel implementations. The existing `memory/` directory is untouched — adapters live in `core/memory_plugin/`.

---

## DEPENDENCY GRAPH

```
Phase 0 (ContextEngine Protocol)
    │
    ├──► Phase 1 (Memory Plugin SDK)
    │       │
    │       └──► Phase 2 (Workspace Memory + Assembly)
    │               │
    │               ├──► Phase 3 (Hooks + Diagnostics)
    │               │
    │               ├──► Phase 4 (Subagent Registry) ── independent of 3
    │               │
    │               └──► Phase 5 (Approval System) ── independent of 3-4
    │
    └──► Phase 6 (Session Repair, Auth, Audit) ── independent of 1-5
         (can start any time; only depends on Phase 0 for ContextEngine)

Phase 1 can start in parallel with Phase 0's final tasks.
Phases 4-6 are independent of each other and of Phase 3.
```

### Why This Order

| Dependency | Reason |
|---|---|
| Phase 0 first | ContextEngine is the foundation. Everything else plugs into it. |
| Phase 1 after Phase 0 core | MemoryPlugin's `buildPromptSection()` is called by `ContextEngine.assemble()`. Need the contract defined first. |
| Phase 2 after Phase 1 signature | MEMORY.md corpus search needs the MemoryPlugin `search()` contract stable. |
| Phase 3 after Phase 1-2 | Hooks and diagnostics observe the established pipeline. |
| Phase 4 independent of 3 | Subagent registry uses ContextEngine but doesn't need hooks or diagnostics. |
| Phase 5 independent of 3-4 | Approval system uses existing tool infrastructure; can be built alongside 4. |
| Phase 6 independent of 1-5 | Session repair and auth profiles only need Phase 0 ContextEngine foundation. |

---

## GANTT CHART SUMMARY

```
Week 1:  ██████████████████████  Phase 0 (ContextEngine protocol, legacy engine, session rotation)
Week 2:  ░░░░████████████████░░  Phase 0 finish + Phase 1 start (MemoryPlugin SDK)
Week 3:  ░░░░░░░░░░░░██████████  Phase 1 finish + Phase 2 start (workspace memory)
Week 4:  ░░░░░░░░░░░░░░░░██████  Phase 2 finish + Phase 3 start (hooks + diagnostics)
Week 5:  ░░░░░░░░░░░░░░░░░░░░██  Phase 3 finish
Week 6:  ░░░░░░░░░░░░░░░░░░░░░░  Integration testing, migration docs
Week 7:  ░░░░░░░░░░░░░░░░░░░░░░  Phase 4 (Subagent registry + task lifecycle)
Week 8:  ░░░░░░░░░░░░░░░░░░░░░░  Phase 5 (Approval system enhancement)
Week 9:  ░░░░░░░░░░░░░░░░░░░░░░  Phase 6 (Session repair, auth profiles, tool audit)
```

---

## KEY MILESTONES

| Milestone | Timeline | Success Criteria |
|-----------|----------|------------------|
| **M0** | End Week 1 | LegacyContextEngine replacing inline compaction; session rotation on compaction |
| **M1** | End Week 2 | MemoryPlugin protocol defined; CompositeMemory adapter passing all existing tests |
| **M2** | End Week 3 | Single-slot memory plugin active; ContextEngine.assemble() wired into LLM loop |
| **M3** | End Week 4 | Workspace MEMORY.md loaded; memory corpus search functional via MemoryPlugin |
| **M4** | End Week 5 | Hooks firing on afterTurn/compaction; health checks reporting per-plugin status |
| **M5** | End Week 6 | Full integration test suite passing; doctor CLI handles memory plugin config |
| **M6** | End Week 7 | Subagent/task registry tracking all spawned tasks with status lifecycle |
| **M7** | End Week 8 | Approval system with per-tool policies and channel-native delivery |
| **M8** | End Week 9 | Session repair, auth profile rotation, and tool audit trail operational |

---

## QUICK WINS (First 3 Days)

- **Day 1:** Define ContextEngine ABC + result types (`core/context_engine/protocol.py`)
- **Day 2:** LegacyContextEngine wrapping existing compaction + inline dedup
- **Day 3:** Session rotation on compaction (new session file, summary message)

After Day 3, HomeClaw has a clean context management boundary. Everything else builds on it.

---

## PHASE 0–3 EXTENSIONS (Completed)

These five enhancements extend the Phase 0–3 implementation. All are implemented and tested.

| # | Extension | Phase | Implementation |
|---|---|---|---|
| 1 | **LLM-based compaction summaries** | 0 | `generate_llm_compaction_summary()` in `compact_runtime.py` — calls LLM for meaningful summaries of trimmed messages, falls back to heuristic when LLM is unavailable |
| 2 | **assemble() full integration** | 2 | `LegacyContextEngine.assemble()` now integrates MemoryPlugin prompt section + cache-aware message ordering + prompt-cache telemetry estimates. The `system_prompt_addition` field carries the MemoryPlugin's prompt section to the LLM loop |
| 3 | **Transcript rewrite** | 0 | `LegacyContextEngine.maintain()` implemented — delegates to runtime's `rewrite_transcript_entries()` when available. Generic stub ready for session DAG manipulation |
| 4 | **Multi-engine support** | 0 | `resolve_context_engine()` accepts `agent_id` — reads `context_engine.{agent_id}` config for per-agent engine override. Defaults to `"legacy"` |
| 5 | **Prompt-cache-aware assembly** | 3 | `assemble()` reorders messages so the largest stable prefix (system messages) comes first for DeepSeek prefix-cache reuse. Emits `ContextEnginePromptCacheInfo` estimates for cache telemetry |

### Multi-engine config

```yaml
# config/core.yml
context_engine:
  default: legacy          # default for all agents
  clawcode: legacy         # per-agent override
  my-agent: custom-engine  # plugin-registered engine
```

---

## PHASE 4: SUBAGENT REGISTRY & TASK LIFECYCLE

*(High Priority — Week 6-7)*

### Goal

Implement a structured subagent/task registry inspired by OpenClaw's `src/tasks/task-registry.ts`. Every subagent invocation and long-running task gets a record with a tracked lifecycle (`queued → running → succeeded/failed/timed_out/cancelled`), persisted in SQLite, with audit events and completion delivery to the requesting channel.

### Why This Matters

HomeClaw's `core/skill_subagent.py` spawns subagents but has **no structured tracking** — tasks disappear when the session ends. Users have no way to:
- See what sub-tasks are running or completed
- Get notified when long-running tasks finish
- Audit what subagents did
- Recover from crashes (lost tasks are invisible)

OpenClaw solves this with a `TaskRegistry` backed by SQLite that tracks every task through its lifecycle and delivers completion notifications to the requesting channel.

### Tasks

| Task ID | Task | Description | Estimated Effort |
|---------|------|-------------|------------------|
| **4.1** | Task Record Types | Define `TaskRecord`, `TaskStatus`, `TaskEvent` dataclasses | 2h |
| **4.2** | SQLite Task Store | Persist tasks in `database/tasks.db` with status transitions | 4h |
| **4.3** | Task Registry Core | `TaskRegistry` class: create, update status, query, list | 4h |
| **4.4** | Subagent Integration | Hook skill_subagent.py to register tasks and update status on completion | 3h |
| **4.5** | Completion Delivery | Deliver task results back to the requesting channel when a task finishes | 4h |
| **4.6** | Task Summary & List | API endpoint `GET /api/tasks` + CLI `python -m main tasks` | 3h |
| **4.7** | Task Cleanup | Evict terminal tasks after configurable TTL (`task_retention_days`) | 2h |
| **4.8** | Tests | Unit + integration tests for task registry | 3h |

### Deliverables

- `core/task_registry/` — new module
  - `types.py` — `TaskRecord`, `TaskStatus`, `TaskEvent`, `TaskSummary`
  - `store.py` — SQLite persistence
  - `registry.py` — create, update, query, list, cleanup
  - `delivery.py` — channel-native completion notification
- Extended `core/skill_subagent.py` — task registration hooks
- `core/routes/task_routes.py` — `GET /api/tasks`
- `database/tasks.db` — SQLite schema

---

## PHASE 5: APPROVAL SYSTEM ENHANCEMENT

*(Medium Priority — Week 7-8)*

### Goal

Enhance HomeClaw's approval system following OpenClaw's operator approval patterns (`src/infra/approval-native-delivery.ts`, `src/agents/exec-approval-*.ts`). Add per-tool approval policies, channel-native delivery of approval prompts, and exec approval allowlists.

### Why This Matters

HomeClaw's `clawcode_approvals.py` currently only blocks tool calls on approval. OpenClaw's system:
- Delivers approval prompts **natively to any channel** (Telegram, Discord, WebChat) — the operator approves in-chat rather than a separate UI
- Supports **per-tool approval policies** — some tools auto-approved, some always require approval, some conditional
- Tracks **approval state** with timeouts and retry
- Caches **allowlist entries** (e.g., "always allow `git commit` in this repo")

### Tasks

| Task ID | Task | Description | Estimated Effort |
|---------|------|-------------|------------------|
| **5.1** | Approval Policy Types | Define `ApprovalPolicy`, `ApprovalRule`, `ApprovalRequest` | 2h |
| **5.2** | Per-Tool Policy Config | `approval.tools` config key: `{tool_name: {policy: "ask"|"allow"|"deny"}}` | 2h |
| **5.3** | Channel-Native Delivery | Deliver approval prompts as interactive messages in the user's active channel | 4h |
| **5.4** | Approval State Machine | Track pending approvals with timeout, retry, and resolution | 3h |
| **5.5** | Exec Approval Allowlists | Cache approved commands/paths per session (`approval.allowlist` config) | 3h |
| **5.6** | Audit Log | Record all approval decisions for security review | 2h |
| **5.7** | Tests | Unit tests for policy engine, delivery, and state machine | 3h |

### Deliverables

- `core/approvals/` — new module
  - `policy.py` — approval policy engine
  - `delivery.py` — channel-native approval prompts
  - `state.py` — approval state machine with timeouts
  - `audit.py` — audit log
- Extended `core/clawcode_approvals.py` — per-tool policy, allowlists
- Config key: `approval.tools` in `core.yml`

---

## PHASE 6: SESSION REPAIR, MODEL AUTH & TOOL AUDIT

*(Lower Priority — Week 8-9)*

### Goal

Three smaller enhancements bundled into one phase:
- **Session repair**: integrity checks and auto-repair for chat history (inspired by OpenClaw's `session-file-repair.ts`)
- **Model auth profiles**: per-agent API key rotation with fallback (inspired by `agents/model-auth.ts`)
- **Tool audit trail**: structured audit events for every tool execution (inspired by `agents/tool-policy-audit.ts`)

### Tasks

| Task ID | Task | Description | Estimated Effort |
|---------|------|-------------|------------------|
| **6.1** | Chat History Integrity Check | Scan SQLite chat tables for orphans, duplicates, gaps; report and optionally fix | 3h |
| **6.2** | Session Auto-Repair | When chat history is corrupted, repair by removing bad rows and re-linking | 2h |
| **6.3** | Auth Profile Types | Define `AuthProfile` with `{provider, api_key, rotation_strategy}` | 2h |
| **6.4** | Key Rotation Engine | Round-robin, weighted, and fallback strategies for API key rotation | 3h |
| **6.5** | Per-Agent Auth Config | `auth.profiles.{agent_id}` config block; auto-select by agent | 2h |
| **6.6** | Tool Audit Events | Structured `ToolAuditEvent` with timestamp, tool name, parameters (sanitized), result status, duration | 3h |
| **6.7** | Audit Store & Query | Persist audit events; query by tool, agent, time range | 2h |
| **6.8** | Tests | Unit tests for repair, auth rotation, and audit | 3h |

### Deliverables

- `core/session_repair.py` — chat history integrity check and repair
- `llm/auth_profiles.py` — API key rotation engine
- `config/auth_profiles.yml` — per-agent auth configuration
- `core/tool_audit.py` — structured audit events + persistence
- `database/audit.db` — SQLite audit store

---

## DESIGN DECISIONS

1. **Refactor, don't rebuild.** Existing `memory/` code stays in place. New modules in `core/` adapt and extend it. No parallel implementations.

2. **Single-slot memory, not multi-backend.** OpenClaw explicitly converges toward one memory backend per agent. HomeClaw's `CompositeMemory` is wrapped as one possible plugin — other plugins can be single-backend.

3. **ContextEngine, not "compaction module."** Compaction is one method on a broader lifecycle. Building only compaction misses the architectural insight.

4. **Session rotation, not message truncation.** OpenClaw compacts by creating new session files. This preserves audit trails and gives the LLM a cleaner context than a truncated message list.

5. **Ingest-level dedup, not storage-level.** Deduplication at ingestion (via content hash) is simpler and more correct than a separate dedup pass over stored records.

6. **Pythonic protocols, not TypeScript interfaces.** The ContextEngine and MemoryPlugin are Python ABCs — they map to OpenClaw's TypeScript interfaces but use Python conventions.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-27 | Initial release |
| 2.0 | 2026-05-27 | Restructured: ContextEngine-first architecture, removed duplicate work, added pre-flight inventory, session rotation, hooks, single-slot memory plugin |
| 3.0 | 2026-05-27 | Added Phase 4-6: Subagent registry + task lifecycle, approval system enhancement, session repair + model auth profiles + tool audit |
| 3.1 | 2026-05-27 | Added Phase 0–3 Extensions section: LLM summaries, assemble integration, transcript rewrite, multi-engine, cache-aware assembly |

---

*This plan is inspired by OpenClaw's architecture, specifically the ContextEngine pluggable lifecycle, single-slot memory plugin design, and session rotation on compaction. It prioritizes refactoring HomeClaw's existing capabilities over creating parallel implementations.*
