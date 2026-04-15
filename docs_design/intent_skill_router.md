# Intent + Skill Router (Semantic, Configurable)

This document defines a complete design and rollout plan for a new, configurable routing system in HomeClaw:

- **Intent router**: category selection via semantic retrieve + rerank (optional hybrid with static preempts).
- **Skill router**: skill filtering via semantic retrieve + rerank (optional hybrid with current logic).

The goal is to keep the current stable path, but allow a more scalable routing mechanism as tools/skills grow.

---

## 1) Goals

1. **Scale routing quality** when categories/skills increase.
2. **Reduce maintenance** cost of static rules.
3. **Preserve current behavior by default** (feature flags OFF).
4. **Improve planner success** by narrowing the candidate set with better routing.
5. **Keep safe fallbacks**: DAG -> planner-executor -> ReAct remains unchanged.

---

## 2) Non-goals

- Replace DAG/planner/ReAct execution design.
- Remove all static routing; critical deterministic preempts remain valuable.
- Change permission model or category tool allowlists.

---

## 3) Current baseline (summary)

- Intent is currently resolved by static preempts + optional classifier prompt.
- Categories map to:
  - `category_tools`/skills filters
  - DAG flow selection
  - planner skip policy
- Skills already support vector retrieval mode (`skills_use_vector_search`) but not a full retrieve-then-rerank pipeline with explicit policy/config separation.

---

## 4) Target architecture

### 4.1 High-level flow

1. **Input query**
2. **Intent router** (`static` / `semantic` / `hybrid`)
3. **Category selected** (or top-2 if enabled)
4. **Skill router** (`legacy` / `semantic` / `hybrid`) within category policy scope
5. Existing execution ladder:
   - DAG (if mapped)
   - Planner-executor (if enabled and not skipped)
   - ReAct fallback

### 4.2 Design principle

- **Intent router** decides *domain policy* (what is allowed / likely workflow family).
- **Skill router** decides *which concrete skills* are injected.
- Never bypass category policy filters in semantic mode.

---

## 5) Configuration design

All new behavior must be fully switchable and backward compatible.

### 5.1 Intent router config

```yaml
intent_router:
  enabled: true
  mode: static            # static | semantic | hybrid
  timeout_seconds: 15
  router_llm: null        # existing behavior for static classifier path

  semantic:
    enabled: false
    docs_dir: config/intent_categories
    refresh_on_startup: true
    update_on_change: true
    top_k: 20
    rerank_top_n: 10
    final_top_n: 2
    accept_top_n: 1       # usually 1, optionally 2 for multi-category
    threshold: 0.60
    margin_threshold: 0.08
    fail_open_to_static: true
    shadow_mode: false
    include_examples_in_embedding: true
    include_workflow_hints: true
    reranker:
      enabled: true
      mode: cross_encoder # cross_encoder | llm_judge
      model: local_models/classifier_0_6b
      timeout_seconds: 5
```

### 5.2 Skill router config

```yaml
skills_router:
  enabled: false
  mode: legacy            # legacy | semantic | hybrid
  semantic:
    refresh_on_startup: true
    update_on_change: true
    top_k: 20
    rerank_top_n: 10
    final_top_n: 5
    threshold: 0.55
    margin_threshold: 0.05
    fail_open_to_legacy: true
    shadow_mode: false
    include_body_in_embedding: true
    inject:
      include_head: true
      include_description: true
      include_keywords: true
      include_body_mode: excerpt   # none | excerpt | full
      body_excerpt_max_chars: 1200
      max_total_chars: 12000
    reranker:
      enabled: true
      mode: cross_encoder
      model: local_models/classifier_0_6b
      timeout_seconds: 5
```

### 5.3 Defaults

- Defaults keep current behavior:
  - `intent_router.mode: static`
  - `skills_router.mode: legacy`

---

## 6) Data model and indexing

### 6.1 Intent category docs format

Directory: `config/intent_category/`

One markdown file per category, e.g. `weather.md`, `stock_monitor.md`.

Recommended frontmatter:

```md
---
id: weather
display_name: Weather
enabled: true
priority: 50
dag_key: weather
planner_skip: true
tool_profile: weather_profile
---

## Description
User asks about weather, forecast, temperature, rain, wind.

## Positive examples
- What's the weather in Seattle tomorrow?
- 北京明天会下雨吗？

## Negative boundaries
- climate policy discussion -> general_chat

## Workflow hints
- Usually route to DAG weather
- fallback to web_search if weather tool timeout
```

Index content for embedding:
- title/id
- description
- positive/negative examples
- workflow hints (optional)

### 6.2 Skill indexing unit

Use existing skill metadata + structured extraction:
- `name`, `description`, `keywords`, `trigger`, selected body sections.

Keep a stable document ID:
- `skill::<folder_name>::v<hash>`

### 6.3 Reindex triggers

1. Startup refresh (`refresh_on_startup`).
2. Optional file-change refresh (`update_on_change`).
3. Manual CLI/admin trigger (recommended):
   - `python -m main index intent-categories`
   - `python -m main index skills`

---

## 7) Retrieval and rerank pipeline

### 7.1 Intent semantic routing

1. Retrieve top-K categories from vector store.
2. Rerank top-N candidates with small reranker.
3. Apply confidence policy:
   - if top score < `threshold`: fallback (static or `general_chat`)
   - if top1-top2 < `margin_threshold`: optional multi-category
4. Return selected category list + score metadata.

### 7.2 Skill semantic routing

1. Build policy scope first:
   - category allowed skills (or all if no policy)
2. Retrieve top-K skills within scope.
3. Rerank top-N.
4. Select final top-M.
5. Build prompt block with injection budget.

### 7.3 Hybrid modes

- `intent_router.mode=hybrid`:
  - static preempts first
  - semantic route second
  - static/classifier fallback last (configurable)
- `skills_router.mode=hybrid`:
  - legacy filter pre-scope
  - semantic narrowing
  - legacy fallback on failure

---

## 8) Integration points in code

### 8.1 New modules

- `base/intent_router_semantic.py`
  - load category docs
  - index sync
  - retrieve + rerank
  - route API

- `base/skill_router.py`
  - retrieve + rerank for skills
  - policy-aware scope filtering
  - prompt injection packer

- `base/router_reranker.py`
  - shared reranker adapters (cross-encoder / llm judge)

### 8.2 Existing call sites

- `core/llm_loop.py`
  - intent routing branch chooses static/semantic/hybrid by config
  - skill filtering branch chooses legacy/semantic/hybrid by config
  - execution ladder unchanged

- `core/initialization.py`
  - add intent category index initialization/sync
  - reuse skill index refresh path

- `base/base.py`
  - extend config schema for new sections

---

## 9) Reliability and fallback rules

1. **Vector store unavailable**
   - intent: fallback to static or `general_chat` per config
   - skills: fallback to legacy list
2. **Reranker timeout/error**
   - use retrieval scores directly
3. **Low confidence**
   - intent: static fallback or clarifying question
   - skills: inject fewer skills + let planner/ReAct decide
4. **No candidates**
   - intent: `general_chat`
   - skills: category allowlist default set

---

## 10) Observability

Add structured trace events:

- `intent_semantic_retrieved`
- `intent_semantic_reranked`
- `intent_semantic_selected`
- `skills_semantic_retrieved`
- `skills_semantic_reranked`
- `skills_semantic_selected`

Include:
- `query_hash` (not raw text if privacy needed)
- candidate IDs + scores
- final IDs
- latencies per stage
- fallback reason

Add counters:
- semantic hit rate
- fallback rate
- low-confidence rate
- planner success delta by mode

---

## 11) Planner success improvements (required companion changes)

To improve planner-executor success after routing:

1. Add optional **plan validator** stage:
   - tool existence
   - arg schema compatibility
   - dependency completeness between steps
2. Add one-step **auto-repair** using validator errors.
3. Then execute; on failure fallback to ReAct.

This can be separately feature-flagged:

```yaml
planner_executor:
  plan_validation:
    enabled: false
    auto_repair: true
    max_repair_rounds: 1
```

---

## 12) Security and policy constraints

- Semantic routers **must not** bypass tool allowlists / profile constraints.
- Category policy remains source of truth for tool exposure.
- Multi-category union should remain bounded by explicit allowlists.

---

## 13) Performance budget

Target per request (semantic mode):

- Intent retrieval: 5-20 ms
- Intent rerank (top 10): 50-300 ms local small model
- Skill retrieval: 5-30 ms
- Skill rerank (top 10): 80-400 ms local small model

Mitigations:
- cache embeddings/rerank features
- skip rerank when top1 similarity >> top2
- lower `top_k`/`rerank_top_n` on constrained hosts

---

## 14) Rollout plan

### Phase 0: Config + shadow only

- Implement configs and semantic modules.
- `shadow_mode=true`, no behavioral change.
- Collect routing agreement stats vs current logic.

### Phase 1: Hybrid in limited categories

- Enable semantic intent for non-critical categories.
- Keep static preempts for critical routes.
- Enable skill semantic rerank with fail-open.

### Phase 2: Wider semantic primary

- `intent_router.mode=hybrid` or `semantic` by environment.
- `skills_router.mode=hybrid` -> `semantic` once stable.

### Phase 3: Cleanup

- Remove low-value static rules only after stable metrics.

---

## 15) Test plan

### Unit tests

- Intent doc parsing/frontmatter validation.
- Retrieval and rerank decision logic.
- Confidence/margin threshold branching.
- Fallback behavior on errors/timeouts.
- Skill prompt budget packing.

### Integration tests

- End-to-end route selection with DAG hit.
- Planner success rate changes with semantic skill filtering.
- Regression: static mode unchanged outputs.

### Offline evaluation

- Build labeled query set by category.
- Metrics:
  - top-1 accuracy
  - top-2 recall
  - planner success %
  - total latency

---

## 16) Migration and compatibility

- Backward compatible defaults.
- Default: categories and `category_tools` load from `config/intent_category/*.md`; optional YAML `category_tools` merges under (markdown wins per id). Set `intent_category_docs_dir: ""` to use YAML-only lists.
- Existing skills vector search logic remains valid and can be reused.

---

## 17) Open questions

1. Do we keep category docs in `config/intent_categories` or `docs/intent_categories`?
2. Should reranker default to local-only for privacy/cost?
3. Should low-confidence intent route ask user clarification vs `general_chat`?
4. How many body excerpts per skill are optimal for quality vs tokens?

---

## 18) Recommended initial defaults

- Intent: `mode=hybrid`, semantic enabled, `top_k=15`, `rerank_top_n=8`, `threshold=0.60`.
- Skills: `mode=hybrid`, `top_k=20`, `final_top_n=5`, body excerpt mode.
- Keep critical static preempts (weather/news_digest/stock_monitor/list_files/get_file_link).

This gives high maintainability gains while preserving deterministic behavior on hot paths.
