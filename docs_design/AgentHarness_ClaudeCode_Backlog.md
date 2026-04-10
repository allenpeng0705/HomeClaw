# HomeClaw agent harness enhancement backlog (Claude Code–inspired)

This document turns **architectural lessons** from mature CLI agent harnesses (tool contracts, permissions, budgets, observability, deferred tool exposure) into a **prioritized, file-mapped backlog** for HomeClaw. It does **not** assume copying any third-party source code—only patterns.

**Related today:** `base/tools.py` (registry + execution), `core/llm_loop.py` (loop, compaction), `base/workflow_trace.py` + `tools/builtin.py` (trace events), `config/core.yml` (metadata), `docs/workflow-trace-testing.md`.

---

## Current strengths (keep)

- **Central `ToolRegistry`** with JSON Schema parameters and `execute_async` (`base/tools.py`).
- **Workflow trace JSONL** with `tool_call_started` / `tool_call_finished`, `skill_call_*`, `model_selected`, etc.
- **Compaction** and optional memory flush driven by `core.yml` → `compaction` (`core/llm_loop.py`).
- **Arg normalization** and multi-route LLM behavior already in the loop.

---

## Target principles (what “great” looks like)

1. **Every tool call is policy-checked** before execution, with a **stable deny reason** surfaced to logs/traces (and optionally to the user).
2. **Tool surface is bounded per request**: not every tool in the registry need appear in the model’s `tools=` list; support **filtering** and later **deferred discovery** (search/list tools).
3. **Hard ceilings** on agent work per inbound turn: **max tool rounds**, **token budget** (estimate + stop), **explicit stop reasons** in trace.
4. **Observability first**: same events power **tests** (workflow contracts) and a future **developer UI** (streaming or poll).
5. **Config-driven** behavior (`core.yml`) with safe defaults for production.

---

## P0 — Foundation (highest ROI, smallest vertical slices)

### P0.1 Tool metadata for policy hooks

**Goal:** Extend `ToolDefinition` so permissions can be decided without scattering `if name == ...` across Core.

**Files:** `base/tools.py`; callers that construct `ToolDefinition` (e.g. `tools/builtin.py`, plugin registration).

**Work:**

- Add optional fields on `ToolDefinition`, for example:
  - `risk_tier`: `"read"` | `"write"` | `"network"` | `"exec"` | `"user_data"` (string enum or literals).
  - `requires_confirmation`: `bool` (default `False` for backward compatibility).
- Document in docstring; default unset → treat as current behavior (always execute).

**Acceptance:** All existing tools register without changes; new fields are optional.

---

### P0.2 Permission gate in `ToolRegistry.execute_async`

**Goal:** Single choke point: **allow / deny / defer-to-user** before `execute_async` runs.

**Files:** `base/tools.py`; new small module e.g. `base/tool_permissions.py` (pure functions + types); `core/llm_loop.py` (pass `ToolPermissionContext` into `ToolContext` or parallel arg).

**Work:**

- Introduce `ToolPermissionContext` (user id, channel, friend scope, config snapshot, optional “mode”: `default` / `auto_approve_read` / etc.).
- `execute_async` calls `evaluate_tool_permission(tool, args, context)` → `allowed` | `denied(reason_code, message)`.
- On deny: return a **string** error for the model (same as today for tool errors), and emit a **workflow trace event** (see P0.3).

**Acceptance:** Denials never run executors; reason appears in logs; configurable allow-all for tests.

---

### P0.3 Trace schema: `permission_denied` (and optional `tool_call_blocked`)

**Goal:** Contracts and future UI can assert **policy** behavior, not only success paths.

**Files:** `base/workflow_trace.py` (`ALLOWED_EVENT_TYPES` if centralized—today partly in `tests/workflow_framework/trace_schema.py`), `tests/workflow_framework/trace_schema.py`, `tests/workflow_framework/contracts.yaml` (examples).

**Work:**

- Add event type e.g. `permission_denied` with `details`: `tool_name`, `reason_code`, `source` (`registry` / `policy`).
- Emit from `ToolRegistry.execute_async` when permission fails before execution.

**Acceptance:** Workflow trace tests can include a scenario that expects a denial when config forces it.

---

### P0.4 Per-request limits: max tool rounds + stop reason in trace

**Goal:** Claude-style **bounded agent loop**—prevent runaway tool chains on one inbound message.

**Files:** `core/llm_loop.py`; `config/core.yml` + metadata loading in `base/base.py` or `base/util.py`.

**Work:**

- Config keys under e.g. `agent_limits`: `max_tool_rounds_per_turn` (default high enough to not change behavior), `max_llm_rounds_per_turn` if distinct.
- When limit hit: stop loop, user-visible message, trace event `turn_finished` or new `agent_limit_reached` with `reason`.

**Acceptance:** Setting a low limit in test config reliably stops after N rounds; trace shows reason.

---

## P1 — Scale and operator experience

### P1.1 Filtered tool list for LLM (simple mode)

**Goal:** Reduce prompt bloat and wrong-tool selection—**subset of tools** per channel/user/skill context.

**Files:** `core/llm_loop.py` (where `get_openai_tools` is built); `base/tools.py` (helper `filter_tools_for_context`); config `skills_and_plugins.yml` / `core.yml` as needed.

**Work:**

- Build `tools=` from registry through a **filter** (allowlist by name prefix, skill bundle, or “core tools only”).
- Keep full registry for execution so **hidden** tools can still run if invoked (optional policy)—or deny unknown tools at execution (explicit choice; document).

**Acceptance:** Config can restrict WebChat to a small set without breaking server-side plugin registration.

---

### P1.2 Token budget estimate + graceful stop

**Goal:** Surface **budget exhaustion** like production harnesses—not only message count.

**Files:** `core/llm_loop.py`; optional `base/token_estimate.py` (reuse LiteLLM or rough tokenizer).

**Work:**

- Track cumulative **estimated** input+output tokens per turn (or per session segment).
- On exceed: stop with clear `stop_reason` in trace; user message explains limit.

**Acceptance:** With a tiny budget in config, run ends deterministically with trace reason.

---

### P1.3 Compaction: trace events + metrics

**Goal:** When compaction or memory flush runs, **emit trace events** (`context_compacted`, `memory_flush_started/finished`) so scenario tests and dashboards see it.

**Files:** `core/llm_loop.py` (compaction block ~2729+); `tests/workflow_framework/trace_schema.py`.

**Acceptance:** Workflow trace JSONL contains compaction markers when enabled.

---

### P1.4 Scenario tests for permission + limits

**Goal:** Lock P0/P1 behavior with **in-process** or **mock** scenarios (extend `tests/workflow_framework/`).

**Files:** `tests/workflow_scenarios/*.yaml`, `tests/workflow_framework/mock_harness.py` (if mocking policy), or dedicated pytest with patched registry.

**Acceptance:** At least: one **denied** tool scenario, one **max rounds** scenario.

---

## P2 — Platform and “developer console” path

### P2.1 Real-time trace stream (SSE or WebSocket)

**Goal:** Same events as JSONL, **pushed** to a subscribed client (local dev or admin).

**Files:** new route module under `core/routes/`; auth gate; subscribe to a **broadcast queue** fed from `emit_event` (optional async-safe queue).

**Work:**

- Minimal: SSE `GET /dev/trace/stream` (dev-only or API key).
- **No overhead when no subscribers** (buffer or drop—match Claude Code “zero subscribers” idea).

**Acceptance:** One browser or `curl` sees events during a live chat turn.

---

### P2.2 Deferred tool discovery (“tool search”)

**Goal:** When tool count grows, model first calls **`list_tools` / `search_tools`** then invokes—mirrors large harness behavior.

**Files:** `base/tools.py`; `core/llm_loop.py` system prompt; registration of meta-tools.

**Acceptance:** With many tools registered, default prompt uses discovery; narrow tool list still works in P1.1.

---

### P2.3 Structured progress for long tools

**Goal:** Long-running tools (bash, fetch) emit **progress** events for UI (optional).

**Files:** `base/workflow_trace.py`; selected executors in `tools/builtin.py`.

**Acceptance:** Trace shows progress chunks for a stub long operation in tests.

---

## Out of scope (for this backlog)

- Porting Claude Code’s **terminal UI** (Ink/React) to HomeClaw.
- **1:1** feature parity with any external product.
- Embedding **leaked** source; this backlog is **pattern-only**.

---

## Suggested PR sequence (small steps)

1. **P0.1** tool metadata only (no behavior change).
2. **P0.2** + **P0.3** permission deny path + trace event (default allow-all).
3. **P0.4** max tool rounds + trace stop reason.
4. **P1.4** scenario tests covering deny + limit.
5. **P1.1** filtered `tools=` list.
6. **P1.2** token budget (rough estimate OK at first).
7. **P2.1** SSE trace stream (optional flag).

---

## Config sketch (`config/core.yml`)

```yaml
# Illustrative — names may differ when implemented
agent_limits:
  max_tool_rounds_per_turn: 64
  max_estimated_tokens_per_turn: 200000

tool_policy:
  default_mode: allow_read_restrict_write  # example; exact enum TBD
  # per_channel overrides possible later
```

---

## Review cadence

After each P0/P1 slice: run `python -m pytest tests/ -v` and `python scripts/workflow_trace_runner.py --mode in_process_mock`; add scenarios when behavior is user-visible or security-relevant.
