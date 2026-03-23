# Local model load policy & capability-first routing

**Status:** design (ready for implementation)  
**Related:** `llm/llmService.py` (vision on-demand), `base/util.py` (`get_llm_ref_by_capability`, `_resolve_llm`), `config/llm.yml`, `Design.md` §3.1 (one Core, multiple LLMs)

**User-facing overview (diagrams + tables):** [Model selection and lifecycle](../docs/model-selection-and-lifecycle.md) in `docs/` (published on the doc site under **Configure → Model selection & lifecycle**).

---

## 1. Problem

- VRAM/RAM are limited; not every GGUF in `local_models` should stay loaded.
- Users think in **capabilities** (“vision”, “math”, “cheap chat”), not `local_models/foo_q4.gguf` paths.
- Today: **main** and **embedding** servers start with Core; **vision** already supports **start on demand + idle stop** (`vision_llm_start_on_demand`, `vision_llm_idle_stop_seconds`). Other specialists still assume a **pre-running** llama-server on their host/port or share the main server.

---

## 2. Goals

1. **Pin always-loaded** (never unload via this feature): models used for **`main_llm`** (including mix-mode local leg), **`embedding_llm`**, and any other ref Core treats as “boot critical” (see §5).
2. **Global + per-model `load_policy`** for **other** `local_models` entries (GGUF via Core-started llama-server).
3. **Capability-first selection** with clear tie-breaking; optional **`description`** metadata for a later semantic-routing phase.
4. **Generalize** the vision pattern: `ensure_running` before a completion, `schedule_stop` after (with idle timeout or immediate), **safe under concurrent requests** (refcount).

## 3. Non-goals (initial release)

- Unloading **cloud** models (provider-managed).
- Changing **Ollama** lifecycle beyond documenting “external daemon; optional future: `keep_alive` tuning” — no unload API in v1 unless we add an explicit Ollama adapter.
- Automatic **quantization** or **model download**.
- Replacing **hybrid_router** semantics; only ensure router/spawn paths can resolve by capability consistently.

---

## 4. Config schema (proposed)

### 4.1 Global defaults (`config/llm.yml`)

Place under `llama_cpp` (or a sibling block `local_model_lifecycle:` — implementer chooses one; prefer **`llama_cpp.local_model_defaults`** to keep one tree):

```yaml
llama_cpp:
  local_model_defaults:
    load_policy: always          # always | on_demand
    idle_stop_seconds: 300       # after last use; 0 = stop when request completes (after refcount hits 0)
    # optional: max_concurrent_starts: 2  # throttle cold starts
```

- **`always`**: Core starts this model’s server at startup (if not Ollama) — same as today for entries we already start; new entries marked `always` get started with Core.
- **`on_demand`**: start llama-server on first request targeting that ref; stop per `idle_stop_seconds` / immediate when refcount 0.

### 4.2 Per `local_models` entry (override)

Each item may include:

```yaml
local_models:
  - id: qwen_math_7b
    path: ...
    host: 127.0.0.1
    port: 5031
    capabilities: [Math, Chat]
    description: "Strong at step-by-step math; use for derivation checks."
    priority: 10                 # higher wins when multiple models share a capability (optional; default 0)
    load_policy: on_demand       # omit = use local_model_defaults
    idle_stop_seconds: 120       # omit = use global default
    available: true              # false = catalog placeholder; omit capability routing; see llm.yml §2 header
```

**Semantics:**

- **`capabilities`**: list of strings (case-insensitive match in code). Standardize doc’d tags: `Chat`, `Vision`, `Embedding`, `Math`, `Code`, `ToolSelection`, `Classifier`, … (extensible).
- **`description`**: free text; **v1** = exposed in **`models_list`** JSON for the main LLM to choose **`llm_name`** (capabilities stay coarse); **v2** = optional embedding match for “task text → best model” (see §8).
- **`priority`**: when multiple locals match a capability, pick highest `priority`; tie-breaker = stable order in YAML, then `id`.

### 4.3 Pins (hard rules in code — not configurable)

The following refs **must** behave as **`load_policy: always`** and **must not** be stopped by idle timers:

| Ref role | Resolution |
|----------|------------|
| Effective **main** local server | `main_llm` / mix `main_llm_local` |
| **embedding_llm** | resolved entry |
| **tool_selection_llm** | if Core starts it at boot |
| **vision_llm** | keep existing `vision_llm_start_on_demand`: when `false`, pinned; when `true`, use existing vision stop logic (can later unify under same manager) |
| **hybrid_router.slm** classifier | if started by Core |

Implement **`Util.is_pinned_llm_ref(ref: str) -> bool`** centralizing the above so unload paths cannot regress.

---

## 5. Selection algorithm: capability → ref

### 5.1 Today

`Util.get_llm_ref_by_capability(cap)` prefers **main_llm** if it lists the capability, else first **local** then **cloud** match.

### 5.2 Proposed changes

1. **`get_llm_ref_by_capability(capability, *, prefer_main: bool = True, only_local: bool = False)`**  
   - For **`sessions_spawn`** specialists, callers may set **`prefer_main: false`** so a dedicated “Math” model wins over main that also tagged `Chat`.
2. **Scoring**: collect all matches with the capability; sort by **`priority` desc**, then **`local_models` order**, then **`id`**.
3. **Optional filter**: `load_policy` / availability — if `on_demand` and server down, either start it (`ensure_running`) or skip to next candidate (config flag **`on_demand_fallback_next: true`**).

### 5.3 Explicit ref unchanged

`llm_name: local_models/foo` remains the override for reproducibility and debugging.

---

## 6. Lifecycle: ensure / stop / concurrency

### 6.1 Process identity

- For each **local** `local_models/<id>` managed on-demand, use a stable process name, e.g. **`local_model_<id>`** (sanitize `id` for alphanumeric + underscore), registered in `llama_cpp_processes` like `VISION_LLM_PROCESS_NAME`.

### 6.2 Refcount

- **`ensure_local_model_running(ref)`** increments refcount, cancels pending stop timer for that ref.
- **`release_local_model_slot(ref)`** decrements refcount in `finally` around the completion path.
- When refcount reaches **0**, start **`idle_stop_seconds`** timer (or stop immediately if **0**).

### 6.3 Integration point

- **`Util.openai_chat_completion`** (or a thin wrapper used by Core) after `_resolve_llm`:
  - If type is **local** and entry has **`on_demand`** (effective) and ref is **not pinned** → `ensure_local_model_running` before HTTP call; after response → `release_local_model_slot`.
- **`run_spawn`**: same hook when `llm_name` resolves to on-demand local.
- **Vision path**: either keep separate timer code path for one release, or migrate vision to the generalized manager (phase 2 cleanup).

### 6.4 Port / host

- On-demand models **must** have **unique host:port** per entry (already required for parallel servers). Validate at config load: no duplicate `(host, port)` among locals that can run simultaneously.

---

## 7. API / UX surfaces

| Surface | Change |
|---------|--------|
| **`models_list` tool** | Include `load_policy` (effective), `idle_stop_seconds`, `description`, `priority`, `capabilities`. |
| **`sessions_spawn`** | Document `capability` + optional flag to **not** prefer main when a specialist exists. |
| **Portal / docs** | Short section: “Specialist models & VRAM”; link this doc. |

---

## 8. Phase 2: description-based routing (optional)

- At startup or config change: embed each model’s **`description`** + capability tags into a small index (same embedder as RAG or a tiny cloud call — configurable).
- At runtime: given user task snippet, embed query, cosine match to top-k models, intersect with capability filter, then score with **`priority`**.
- Guardrails: never pick unpinned on-demand model without user/tool consent if cold-start latency > N seconds (log + fallback to main).

---

## 9. Implementation plan (phased)

### Phase A — Config & pins (low risk)

1. Extend **Core metadata** / YAML merge for `local_model_defaults` and per-model `load_policy`, `idle_stop_seconds`, `priority`, `description`.
2. Implement **`is_pinned_llm_ref`**; unit tests for mix-mode + embedding + main.
3. Config validation: duplicate ports, pinned models must be `always` or legacy “no policy” treated as `always` for pinned refs only.

### Phase B — Selection

4. Upgrade **`get_llm_ref_by_capability`** with priority ordering and optional `prefer_main=False`.
5. Wire **`sessions_spawn`** / tool descriptions to use new parameter if needed.
6. Update **`models_list`** JSON fields.

### Phase C — Lifecycle manager

7. Generalize **`LLMServiceManager`**: per-ref refcount, timers, `ensure_local_model_running` / `release_local_model_slot` / `stop_local_model`.
8. Hook **`openai_chat_completion`** (or single internal `_completion_with_lifecycle`) for on-demand locals.
9. Integration tests: concurrent two requests same model (refcount), idle stop after completion, pinned ref never stopped.

### Phase D — Consolidation (optional)

10. Migrate **vision** stop/start to the same manager or shared timer/refcount helpers to reduce duplication.

### Phase E — Description routing

11. Behind **`experimental_model_routing_by_description: true`**, implement §8.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Cold-start latency on first spawn | Log timing; document; optional “warm on Core start” list |
| Stop mid-flight | Refcount + only stop when 0 |
| Wrong model picked by capability | Explicit `llm_name` override; priority; tests |
| VRAM still exhausted | User caps concurrent on-demand models; doc “fewer capabilities per giant model” |

---

## 11. Success criteria

- With two specialist GGUFs on **on_demand**, only **main + embedding** stay loaded at idle after timeout.
- `sessions_spawn` with `capability: Math` hits the highest-priority Math model without manual path.
- Pinned refs never receive stop from this subsystem.

---

## 12. Doc updates after merge

- **Done (overview):** [docs/model-selection-and-lifecycle.md](../docs/model-selection-and-lifecycle.md) — diagrams + selection table; linked from [docs/models.md](../docs/models.md).
- `config/llm.yml` header comments: example block for `local_model_defaults` and one specialist entry (when implemented).
