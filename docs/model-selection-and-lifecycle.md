# Model selection and lifecycle

This page explains **which model HomeClaw uses for what**, **how that choice is made**, and (for upcoming work) **when specialist models load and unload**. For everyday setup, start with [Models](models.md).

**Design spec (implementation plan):** [LocalModelLoadPolicyAndCapabilityRouting.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/LocalModelLoadPolicyAndCapabilityRouting.md) in the repo.

---

## Diagram: model roles (overview)

![Model roles overview](assets/model-roles-overview.svg)

*Sources: `docs/diagrams/model-roles-overview.mmd` — edit in [Mermaid Live](https://mermaid.live) or run `npm run diagrams` from `docs/`.*

---

## When each model runs (today)

| Trigger | Model used | How it is chosen |
|--------|-------------|-------------------|
| Normal chat and tool loop | **Main chat model** | **`main_llm_mode`** in merged config (`config/core.yml` + `llm.yml`): **`local`** → `main_llm_local`; **`cloud`** → `main_llm_cloud`; **`mix`** → per-request route (see [Mix mode](#mix-mode-configuration-and-per-request-routing) below). Legacy: `main_llm` ref when mode fields are unset. |
| Optional smaller tool-picker pass | **`tool_selection_llm`** | If `use_tool_selection_llm` is enabled; that pass uses this ref, then the main model may continue the turn. |
| RAG, memory indexing, skill/plugin embedding | **`embedding_llm`** | Separate ref; often a small local embedding GGUF or a cloud embedding model. |
| User sends an image and main is not vision-capable | **`vision_llm`** (or describe-then-main) | `vision_llm` ref; may use **on-demand** start/stop via `vision_llm_start_on_demand` and `vision_llm_idle_stop_seconds` in config. |
| Mix mode (local + cloud) | **Exactly one of `main_llm_local` or `main_llm_cloud` per turn** | **Hybrid router** in `llm_loop` runs **before** tools/skills/plugins; result selects **`main_llm_for_route(route)`** in `Util` (`base/util.py`). See below. |
| **`sessions_spawn` tool** | **`llm_name`** ref or **`capability`** match | Explicit `local_models/<id>` wins; if only `capability` is set, `get_llm_ref_by_capability` picks a model that lists that capability (**main is preferred if it also has the tag**). One completion, **no tools** inside spawn. |
| Code calls `openai_chat_completion(..., llm_name=…)` | Named ref | Used for spawn, vision analysis helpers, cron post-processing, etc. |

Cloud models are reached via LiteLLM (or your provider); **HomeClaw does not load or unload** their weights.

---

## Mix mode: configuration and per-request routing

Mix mode is **`main_llm_mode: mix`** with two catalog refs and a **hybrid router** block. Config is merged from **`config/llm.yml`** (and overrides from `core.yml`) into **`CoreMetadata`** — see [LlmConfigCloudAndMixModeReview.md](../docs_design/LlmConfigCloudAndMixModeReview.md) for merge rules.

**Operational guide** (YAML examples, reports, tuning tables): [Mix mode and reports](mix-mode-and-reports.md). This section focuses on **how selection is wired in code** and how requests reach **different HTTP endpoints**.

### Prerequisites

| Setting | Role |
|--------|------|
| `main_llm_local` | e.g. `local_models/<id>` — local llama.cpp, Ollama, etc. |
| `main_llm_cloud` | e.g. `cloud_models/<id>` — LiteLLM proxy to a provider |
| `hybrid_router` | At minimum **`default_route`**: `local` or `cloud` (fallback when no layer sets a route). Optional layers: `heuristic`, `semantic`, `slm`, plus `prefer_cloud_if_long_chars`, `show_route_in_response`. |

If `main_llm_mode` is omitted, it may be **derived** from `main_llm` (`cloud_models/` → cloud, else local).

### Where routing runs in the pipeline

In **`answer_from_memory`** (`core/llm_loop.py`), when `main_llm_mode == "mix"`:

1. The **hybrid router** evaluates the **user query** (and uses **request images** for the vision override). It does **not** use intent categories yet.
2. Routing completes **before** intent router, tool lists, and skills are assembled for the main turn.
3. The chosen route drives **`effective_llm_name`** (`main_llm_local` vs `main_llm_cloud` string) and downstream calls that resolve **`main_llm_for_route("local"|"cloud")`** to `(path, raw_id, mtype, host, port)`.

So for **one user message**, the main chat path uses **either** the local stack **or** the cloud stack for that **entire** turn (including tool loops), unless later code applies **mix-specific fallbacks** (e.g. retry the **other** model on empty output or certain tool failures — see `llm_loop` comments around “retry with other model”).

### Default route vs “effective main” when not in a per-request router

For **metadata helpers** that need a single “nominal” main ref when **`mix`** is enabled (e.g. `_effective_main_llm_ref()` in `Util`), HomeClaw uses **`hybrid_router.default_route`**: if `default_route == local`, the effective ref is **`main_llm_local`**; otherwise **`main_llm_cloud`**. That is **not** the same as the per-request route; it is only the default **label** when the router does not override.

### Layer order (first decision wins)

The implementation **stops** as soon as **`route`** is set, except that **final** fallback uses **`default_route`**. Order:

| Step | `route_layer` (when this step sets the route) | Behavior |
|------|-----------------------------------------------|----------|
| 0 | *(optional)* `vision_fallback` | Request has **images**; local ref does not support **`image`** in capabilities; cloud ref does → **cloud**. |
| 1 | `scheduling_prefer_cloud` | Query looks like **scheduling/reminders** and **`main_llm_cloud`** is non-empty → **cloud**. |
| 2 | `heuristic` | If `hybrid_router.heuristic.enabled` and rules load from `rules_path` → first matching **local** or **cloud** from rules. |
| 3 | `semantic` | If `semantic.enabled` and `threshold > 0` → embedding similarity vs **local** vs **cloud** utterance lists; route if **score ≥ threshold**. |
| 4 | `default_route` | If `prefer_cloud_if_long_chars` is set and query length exceeds it → **`default_route`** (often mistaken for “long = cloud”; it actually copies **default_route**, not cloud specifically). |
| 5 | `perplexity` or `classifier` | If `slm.enabled`: **perplexity** probes **main local** logprobs; **classifier** asks a small model for Local vs Cloud. |
| 6 | `default_route` | If still unset → **`hybrid_router.default_route`** (typically **local**). |

After this, **`mix_route_this_request`** and **`mix_route_layer_this_request`** record the outcome; **`hybrid_router.show_route_in_response`** can optionally expose the route in the reply.

### How the route becomes a concrete model and socket

1. **`route`** is `local` or `cloud`.
2. **`effective_llm_name`** is **`main_llm_local`** or **`main_llm_cloud`** (trimmed).
3. **`Util.main_llm_for_route(route)`** resolves the catalog entry and returns:
   - **`mtype: litellm`** → **`cloud_llm_host` / `cloud_llm_port`** (LiteLLM or your proxy).
   - **`mtype: local` or `ollama`** → **`main_llm_host` / `main_llm_port`** (llama.cpp server, Ollama, etc.).

That split is **one place** to remember: **cloud** and **local** legs do **not** share the same host/port keys.

### Panda gateway

When **`panda.enabled`** is true, **`Util.panda_openai_chat_url("litellm")`** routes cloud completions to the **`cloud_llm`** path under Panda; **`"local"`** uses the **`main_llm`** path (`base/util.py`). Embedding and other paths are separate.

### Observability

- **Logs:** `Mix mode: route=%s (layer=%s)` after routing.
- **Metrics:** `hybrid_router.metrics.log_router_decision` (mix only): route, layer, score, latency.
- **Workflow trace:** `model_selected` with `mode: mix`, `route`, `layer`, `model` ref.

### Non-mix modes (local / cloud only)

The hybrid router **block is skipped**. For tracing and fallbacks, **`mix_route_this_request`** is still set to **`local`** or **`cloud`** to match **`main_llm_mode`**, and **`effective_llm_name`** is taken from the corresponding ref or **`_effective_main_llm_ref()`** (`llm_loop`).

---

## Diagram: selection decision (typical paths)

![Model selection decision flow](assets/model-selection-decision.svg)

*Sources: `docs/diagrams/model-selection-decision.mmd`.*

For **mix mode**, the **first** branch in the main turn is **local vs cloud** (hybrid router); **intent routing** (category) is a **separate** step later. See [Intent router flow](intent_router_flow.md) for how that interacts with latency.

---

## Capability tags and `models_list`

- **`local_models`** and **`cloud_models`** in **`config/llm.yml`** are the **catalog**: define every ref you want to configure, even before all GGUF files exist. See the header comments in `llm.yml` §2–3.
- Optional **`available: false`** on an entry: still a valid ref for explicit **`llm_name`**, but skipped for **automatic capability** selection; **`models_list`** includes **`available`** per row.
- In each entry, **`capabilities`** (e.g. `Chat`, `Vision`, `embedding`) describe what the model is for.
- The **`models_list`** tool (for the main agent) lists refs, capabilities, and **`available`** so the model can choose a **`sessions_spawn`** target or reason about options.
- **Selection rule today:** first match after optional **main** preference — see `Util.get_llm_ref_by_capability` in the codebase. **Planned:** priority ordering and `prefer_main=False` for specialists — see the design doc.

---

## Lifecycle: pinned vs specialist (**planned**)

**Today**

- **Main** and **embedding** local servers are started **with Core** and stay up.
- **Vision** can be started on first image use and stopped after idle (existing settings).

**Planned (load policy)**

- Same **pinned** rule for **main** and **embedding** (never idle-unloaded by the new subsystem).
- Other **local** GGUF entries may use **`load_policy: on_demand`** and **`idle_stop_seconds`** so VRAM is freed between rare tasks (math, huge specialist, etc.).

![Planned specialist lifecycle](assets/model-lifecycle-planned.svg)

*Sources: `docs/diagrams/model-lifecycle-planned.mmd`.*

---

## Quick mental model

1. **Default brain:** `main_llm_mode` picks **local**, **cloud**, or **mix**. In **mix**, a **hybrid router** chooses **`main_llm_local`** vs **`main_llm_cloud`** per message before tools/skills; **`main_llm_for_route`** maps that to the right **host/port** (local vs LiteLLM).
2. **Side services:** embedding for memory; optional tool-selection and vision models; optional **SLM** (classifier or perplexity) inside **`hybrid_router.slm`** for mix.
3. **One-shot side thoughts:** `sessions_spawn` runs a **separate** completion (optionally another model) and returns text to the main agent — not a second long-lived agent.
4. **Soon:** specialists declared with **capabilities** + **load_policy**, selected dynamically without typing paths every time.

---

## See also

- [LLM catalog how-to](llm-catalog-howto.md) — fill in `llm.yml`, `available`, capabilities, spawn  
- [Models](models.md) — cloud vs local, multimodal, examples  
- [Mix mode and reports](mix-mode-and-reports.md) — full mix-mode guide, 3-layer router, reports API, YAML tables  
- [Intent router flow](intent_router_flow.md) — intent categories, planner/DAG, latency (orthogonal to hybrid routing)  
- [Tools](tools.md) — `sessions_spawn`, `models_list`  
- [Design: load policy & capability routing](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/LocalModelLoadPolicyAndCapabilityRouting.md)  
- [Design: cloud/mix config merge](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/LlmConfigCloudAndMixModeReview.md)
