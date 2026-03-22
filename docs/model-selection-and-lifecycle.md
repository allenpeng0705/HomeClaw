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
| Normal chat and tool loop | **`main_llm`** | `main_llm` in `config/core.yml` / merged `llm.yml` (`local_models/...` or `cloud_models/...`). |
| Optional smaller tool-picker pass | **`tool_selection_llm`** | If `use_tool_selection_llm` is enabled; that pass uses this ref, then the main model may continue the turn. |
| RAG, memory indexing, skill/plugin embedding | **`embedding_llm`** | Separate ref; often a small local embedding GGUF or a cloud embedding model. |
| User sends an image and main is not vision-capable | **`vision_llm`** (or describe-then-main) | `vision_llm` ref; may use **on-demand** start/stop via `vision_llm_start_on_demand` and `vision_llm_idle_stop_seconds` in config. |
| Mix mode (local + cloud) | **Local leg** and/or **cloud leg** | Hybrid router / classifier (`hybrid_router`, SLM) chooses route; local uses `main_llm_local` (or equivalent), cloud uses `main_llm_cloud`. |
| **`sessions_spawn` tool** | **`llm_name`** ref or **`capability`** match | Explicit `local_models/<id>` wins; if only `capability` is set, `get_llm_ref_by_capability` picks a model that lists that capability (**main is preferred if it also has the tag**). One completion, **no tools** inside spawn. |
| Code calls `openai_chat_completion(..., llm_name=…)` | Named ref | Used for spawn, vision analysis helpers, cron post-processing, etc. |

Cloud models are reached via LiteLLM (or your provider); **HomeClaw does not load or unload** their weights.

---

## Diagram: selection decision (typical paths)

![Model selection decision flow](assets/model-selection-decision.svg)

*Sources: `docs/diagrams/model-selection-decision.mmd`.*

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

1. **One default brain:** `main_llm` handles almost all chat and tools.
2. **Side services:** embedding for memory; optional tool-selection and vision models; mix-mode classifier.
3. **One-shot side thoughts:** `sessions_spawn` runs a **separate** completion (optionally another model) and returns text to the main agent — not a second long-lived agent.
4. **Soon:** specialists declared with **capabilities** + **load_policy**, selected dynamically without typing paths every time.

---

## See also

- [LLM catalog how-to](llm-catalog-howto.md) — fill in `llm.yml`, `available`, capabilities, spawn  
- [Models](models.md) — cloud vs local, multimodal, examples  
- [Mix mode and reports](mix-mode-and-reports.md) — routing local/cloud  
- [Tools](tools.md) — `sessions_spawn`, `models_list`  
- [Design: load policy & capability routing](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/LocalModelLoadPolicyAndCapabilityRouting.md)
