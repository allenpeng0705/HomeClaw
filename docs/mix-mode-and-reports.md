# Mix mode and reports

**Mix mode** lets HomeClaw choose **per request** whether to use a **local** or **cloud** main model. A **3-layer smart router** runs *before* tools, skills, and plugins are injected, using only the user message. You get one main model for the whole turn (local or cloud). **Reports** give you usage and cost visibility: router decisions and cloud request counts, via REST API and a built-in tool.

This page is the **unified guide**: how to use mix mode, how to see reports, and how to adjust parameters.

**In this page:**

- [What is mix mode?](#what-is-mix-mode) — Concepts and required config.
- [How to use mix mode (step-by-step)](#how-to-use-mix-mode-step-by-step) — Enable, configure, run, verify.
- [How to see reports](#how-to-see-reports) — Logs, REST API, and `usage_report` tool.
- [Parameter reference and tuning](#parameter-reference-and-tuning) — All knobs in one table and how to tune them.
- [When to use mix mode](#when-to-use-mix-mode) — Use cases.
- [Config (mix mode)](#config-mix-mode) — Full YAML reference.
- [The 3-layer router](#the-3-layer-router-overview) — Order and flow.
- [Layer 1 / 2 / 3](#layer-1-heuristic) — Heuristic, semantic, classifier/perplexity in detail.
- [Reports (structure)](#reports-structure-and-options) — Report fields and API options.
- [Quick reference](#quick-reference) — One-page cheat sheet.

---

## What is mix mode?

- **`main_llm_mode`** in `config/core.yml` can be:
  - **`local`** — always use the configured main model (local).
  - **`cloud`** — always use the configured main model (cloud).
  - **`mix`** — for each user message, the router picks **local** or **cloud**; then that model is used for the entire turn (including any tool calls).

When `main_llm_mode` is **mix**, you must set:

- **`main_llm_local`** — e.g. `local_models/main_vl_model_4B`.
- **`main_llm_cloud`** — e.g. `cloud_models/Gemini-2.5-Flash`.
- **`hybrid_router`** — `default_route`, and optionally layers: `heuristic`, `semantic`, `slm`.

If you omit `main_llm_mode`, it is derived from `main_llm` (cloud_models/ → cloud, else local), so existing configs keep working.

---

## How to use mix mode (step-by-step)

1. **Set main LLMs and mode** in `config/core.yml`:
   - `main_llm_mode: mix`
   - `main_llm_local: local_models/<your_local_id>` (must exist under `local_models`)
   - `main_llm_cloud: cloud_models/<your_cloud_id>` (must exist under `cloud_models`)

2. **Configure the router** under `hybrid_router`:
   - `default_route: local` or `cloud` (used when no layer selects a route).
   - Enable at least one layer: `heuristic`, `semantic`, and/or `slm` (see [Parameter reference](#parameter-reference-and-tuning) below).

3. **Prepare rule files** (if you use heuristic or semantic):
   - Heuristic: `config/hybrid/heuristic_rules.yml` (create or use [scripts](hybrid-router-scripts.md) to generate/merge).
   - Semantic: `config/hybrid/semantic_routes.yml` or `config/hybrid/generated_utterances.yml` (or generate/merge via scripts).

4. **Start Core** (and ensure your local model server and, if using classifier, the Layer 3 model are running). Send a few test messages. To see which layer chose the route, use one of the options in the next section.

5. **Optional:** Use the [usage report](#how-to-see-reports) (API or `usage_report` tool) to see router and cloud usage over time.

---

## How to see reports

You can see router decisions and cloud usage in three ways.

### 1. Per-request logs

Each mix-mode turn logs one line (JSON) with the routing decision:

- **Where:** Core log output (e.g. stdout or your log file).
- **Look for:** `"event": "hybrid_router_decision"` with `route`, `layer`, `score`, `latency_ms`.

**How to see which layer the routing happened (per request):**

1. **In the reply (easiest):** In `config/core.yml` set `hybrid_router.show_route_in_response: true`. Each reply is prefixed with the route and the layer that chose it, e.g. `[Local · heuristic]`, `[Cloud · semantic]`, `[Local · classifier]`, or `[Cloud · default_route]`.
2. **In Core logs:** At INFO level, each routing decision is logged as a JSON line: `Router decision: {"event": "hybrid_router_decision", "route": "cloud", "layer": "semantic", "score": 0.82, ...}`. The `layer` field is one of: `heuristic`, `semantic`, `classifier`, `perplexity`, `default_route`.
3. **Aggregated (usage report):** Call the usage report API or use the `usage_report` tool; the response includes `router.by_layer` with counts per layer (e.g. how many requests were routed by heuristic vs semantic vs default_route).
- **Layers:** `heuristic`, `semantic`, `classifier`, `perplexity`, or `default_route`.

Use this to debug why a given message went local or cloud.

### 2. REST API (aggregate report)

- **Endpoint:** `GET /api/reports/usage`
- **Auth:** Same as other Core APIs (e.g. `X-API-Key` header when `auth_enabled`).
- **Query:** `?format=json` (default) or `?format=csv`.

**Example:**

```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:9000/api/reports/usage"
```

**What you get:**

- **router**: `total_mix_requests`, `routed_local`, `routed_cloud`, `by_layer` (counts per layer).
- **cloud_usage**: `cloud_requests_total` (all cloud completions, mix + single-cloud).
- **summary**: high-level totals for cost/tuning.

Use this for dashboards, billing, or scripts.

### 3. In chat: `usage_report` tool

When the user asks for “usage”, “cost”, or “how many requests went to cloud”, the model can call the **`usage_report`** tool (no arguments). It returns a short text summary plus the full report as JSON so the model can answer and “review” the numbers.

---

## Parameter reference and tuning

All mix-mode and router parameters live under **`config/core.yml`** → `main_llm_*` and `hybrid_router`. Use this table to find and adjust behavior.

| Parameter | Where | What it does | How to tune |
|------------|--------|----------------|-------------|
| **main_llm_mode** | Top-level | `local` / `cloud` / `mix`. Set to `mix` to enable the router. | — |
| **main_llm_local** | Top-level | Local model ref (e.g. `local_models/main_4B`) used when route is local. | Must match an entry in `local_models`. |
| **main_llm_cloud** | Top-level | Cloud model ref used when route is cloud. | Must match an entry in `cloud_models`. |
| **default_route** | `hybrid_router` | Route when **no** layer selects (e.g. ambiguous or low score). | `local` = save cost; `cloud` = safer for unknown. |
| **show_route_in_response** | `hybrid_router` | When `true`, prepend route and **layer** to each reply, e.g. `[Local · heuristic]` or `[Cloud · semantic]` (for testing). | Default `false`. Turn on to see which layer chose the route in the UI without checking logs. |
| **heuristic.enabled** | `hybrid_router.heuristic` | Turn Layer 1 (keyword/long-input) on/off. | Off if you rely only on semantic + Layer 3. |
| **heuristic.threshold** | `hybrid_router.heuristic` | Min score to accept a heuristic match (keyword match gives 1.0). | Usually keep 0.5; rarely need to change. |
| **heuristic.rules_path** | `hybrid_router.heuristic` | Path to YAML with keywords and long_input_* rules. | Point to your `heuristic_rules.yml` (or generate via scripts). |
| **semantic.enabled** | `hybrid_router.semantic` | Turn Layer 2 (embedding similarity) on/off. | Off if you use only heuristic + Layer 3. |
| **semantic.threshold** | `hybrid_router.semantic` | Min similarity score to accept a semantic route. | **Higher** (e.g. 0.75–0.85) = fewer semantic matches, more fallback to Layer 3/default. **Lower** (e.g. 0.55–0.65) = more requests decided by semantic; use when local model is strong. |
| **semantic.routes_path** | `hybrid_router.semantic` | Path to YAML with local_utterances / cloud_utterances. | Your `semantic_routes.yml` or `generated_utterances.yml`. |
| **slm.enabled** | `hybrid_router.slm` | Turn Layer 3 on/off. | Off = after L2, go straight to default_route. |
| **slm.mode** | `hybrid_router.slm` | `classifier` = small model judge; `perplexity` = main model confidence probe. | Use `perplexity` when your **main local model is strong** and you want it to “vote” by logprob. |
| **slm.threshold** | `hybrid_router.slm` | For **classifier**: min score to accept Local/Cloud. | Only for mode=classifier; 0.5 is typical. |
| **slm.model** | `hybrid_router.slm` | For **classifier**: small model ref (e.g. `local_models/classifier_0_5b`). | Required when mode=classifier; must be in `local_models` with its own port. |
| **slm.perplexity_max_tokens** | `hybrid_router.slm` | For **perplexity**: how many tokens to generate for the probe. | Default 5; more = more signal, slower. |
| **slm.perplexity_threshold** | `hybrid_router.slm` | For **perplexity**: avg logprob above this → local, below → cloud. | **Higher** (e.g. -0.4) = stricter “stay local”. **Lower** (e.g. -0.8) = more stays local. Default -0.6. |

**Strong local model:** If your local model is powerful, consider: lower **semantic.threshold** (e.g. 0.65), **default_route: local**, and Layer 3 **mode: perplexity** with a **perplexity_threshold** that matches your confidence (e.g. -0.6). See `docs_design/StrongLocalModelAndPerplexityRouting.md`.

---

## When to use mix mode

- You want **local** for simple or private tasks (screenshot, lock screen, reminders) and **cloud** for search, latest news, or complex reasoning.
- You want to **limit cloud cost** by routing only when needed.
- You have both a local model and a cloud model configured and are fine with per-request routing.

---

## Config (mix mode)

In **`config/core.yml`**:

```yaml
main_llm_mode: mix
main_llm_local: local_models/main_vl_model_4B
main_llm_cloud: cloud_models/Gemini-2.5-Flash

hybrid_router:
  default_route: local   # used when no layer selects a route
  heuristic:
    enabled: true
    threshold: 0.5
    rules_path: config/hybrid/heuristic_rules.yml
  semantic:
    enabled: true
    threshold: 0.6
    routes_path: config/hybrid/semantic_routes.yml
  slm:
    enabled: false
    threshold: 0.5
    model: local_models/classifier_0_5b
```

- **`default_route`**: `local` or `cloud` when no layer returns a selection.
- **`heuristic`**: keyword and long-input rules; `rules_path` points to a YAML file (see below).
- **`semantic`**: semantic similarity over the **existing** embedding model; `routes_path` points to local/cloud example utterances.
- **`slm`**: small local classifier on a **separate port**; `model` is a `local_models/<id>` entry (e.g. a 0.5B GGUF). Core starts it when mix + slm.enabled.

You can enable only some layers; the router runs in order: **Layer 1 → Layer 2 → Layer 3 → default_route**.

---

## The 3-layer router (overview)

The router runs **once per user turn**, **before** building the system prompt with tools, skills, plugins, workspace, or routing block. Only the **user message** (and, for semantic/slm, minimal context) is used. No tool or plugin descriptions are sent to the router.

| Layer   | Name      | Input           | Output        | When it runs                          |
|---------|-----------|------------------|---------------|----------------------------------------|
| 1       | Heuristic | User message     | local / cloud | If enabled and score ≥ threshold       |
| 2       | Semantic  | User message     | local / cloud | If L1 did not select and score ≥ threshold |
| 3       | Classifier| User message     | local / cloud | If L2 did not select and score ≥ threshold |
| Fallback| —         | —                | default_route | If no layer selected                   |

**Scoring**: Each layer returns a **score** and a **selection** (local or cloud). The selection is used only when **score ≥ threshold** for that layer. If a layer’s selection is used, later layers are skipped.

---

## Routing simple conversation to local

Short chit-chat (greetings, thanks, bye, “ok”, “got it”) is a good fit for the **local** model: no web or deep reasoning needed. You can handle it in **Layer 1**, **Layer 2**, or rely on **Layer 3 / default**.

| Where | How | Pros / cons |
|-------|-----|--------------|
| **Layer 1** | Add a **local** rule with keywords: e.g. `hello`, `hi`, `thanks`, `bye`, `how are you`, `你好`, `谢谢`, `再见`, `ok`, `okay`, `got it`. | **Fast** (1 ms), explicit. Risk: a phrase like “say hello in an email” might match “hello” and route local; use more specific phrases if that’s a problem. |
| **Layer 2** | Add many **local_utterances** for chit-chat: “hi”, “hello”, “how are you”, “thanks”, “bye”, “just saying hi”, “what’s up”, “你好”, “谢谢”, “再见”. | Handles **paraphrases** (“hey there”, “thx”) via similarity; no need to list every variant. Needs enough examples in your routes file. |
| **Layer 3** | Classifier sees the full message and can learn “short, generic → local”. | Handles **ambiguous** cases; slower (~300 ms). |
| **Default** | Set `hybrid_router.default_route: local`. When no layer selects, the turn goes local. | Simple conversation that doesn’t match L1/L2 **already** goes local as fallback. Making it explicit in L1/L2 improves metrics (you see “heuristic” or “semantic” instead of “default_route”). |

**Recommendation:** Add **simple-conversation** keywords to Layer 1 (and optionally more phrases to Layer 2 local_utterances) so greetings and short replies are clearly routed to local without depending on Layer 3 or default. Use the [hybrid router scripts](hybrid-router-scripts.md) to generate or merge these (e.g. “Simple conversation” rule in the heuristic generator, and chit-chat phrases in the utterance generator).

---

## Layer 1: Heuristic

- **Config**: `hybrid_router.heuristic` (`enabled`, `threshold`, `rules_path`).
- **Rules file** (e.g. `config/hybrid/heuristic_rules.yml`):
  - **Keywords**: lists of phrases per route (multi-language in one list). If any phrase appears in the normalized user message (lowercase + Unicode NFC), that route is chosen with score 1.0.
  - **Templates** (optional): use `tmpl` with `{{a|b|c}}` to expand to all permutations (e.g. `{{open|launch}} {{browser|app}}`). No greedy `{{.*}}`. See `hybrid_router/template_expander.py` and `scripts/generate_heuristics.py`.
  - **Long input**: optional `long_input_chars` and `long_input_route`; if the message length &gt; `long_input_chars`, route to `long_input_route` (e.g. cloud).
- **User-editable**: you can add or change keywords in the YAML without code changes.
- **Example**: “screenshot”, “截图” → local; “latest news”, “实时新闻” → cloud.

---

## Layer 2: Semantic

- **Config**: `hybrid_router.semantic` (`enabled`, `threshold`, optional `routes_path`).
- Uses **[semantic-router](https://github.com/aurelio-labs/semantic-router)** with a **custom encoder** that calls your **existing** embedding model (llama.cpp). No second embedding model.
- **Routes**: two routes, “local” and “cloud”, each with example **utterances**. The user message is embedded and compared to these; the best-matching route and its similarity score are used. If score ≥ threshold, that route is selected.
- **Utterances**: in `config/hybrid/semantic_routes.yml` (or defaults in code). You can edit this file to add phrases in any language.

---

## Layer 3: Classifier or perplexity (configurable)

- **Config**: `hybrid_router.slm` (`enabled`, `threshold`, `model`, **`mode`**).
- **Mode** (default `classifier`):
  - **`classifier`**: Small local model (e.g. `local_models/classifier_0_5b`) on its own port. A short **judge prompt** + user message is sent to `/v1/chat/completions`; the reply is parsed for “Local” or “Cloud”. Use when you want a dedicated routing model.
  - **`perplexity`**: **Confidence probe** using the **main local model** (same as `main_llm_local`). Core sends a probe request with `max_tokens` (e.g. 5) and `logprobs=true`, then computes the average log probability of the generated tokens. If avg logprob ≥ **`perplexity_threshold`** (e.g. -0.6), route stays **local**; otherwise **cloud**. Best when your local model is strong and you want it to “vote” by confidence. See `docs_design/StrongLocalModelAndPerplexityRouting.md`.
- **Perplexity options** (when `mode: perplexity`): `perplexity_max_tokens` (default 5), `perplexity_threshold` (default -0.6; higher = stricter “stay local”).
- **Use case**: When L1 and L2 don’t select, Layer 3 decides; classifier is cheap and explicit; perplexity uses the main model’s own confidence.

---

## Logs and metrics (mix mode only)

- **Per-request log**: For each mix-mode routing decision, a structured log line (JSON) is written with:
  - `event`: `hybrid_router_decision`
  - `route`: `local` or `cloud`
  - `layer`: `heuristic` | `semantic` | `classifier` | `default_route`
  - `score`, optional `reason`, `request_id`, `session_id`, `latency_ms`
- **Aggregated counts** (in memory):
  - Total mix requests, routed to local, routed to cloud.
  - Counts **by layer** (how many times each layer decided the route).

These are **only** updated when `main_llm_mode == "mix"` and the router runs. Local-only and cloud-only modes are unchanged.

---

## Cloud usage (all modes)

- **Every** chat completion that uses a **cloud** model (whether in **mix** mode routed to cloud or in **single cloud** mode) increments a **cloud request** counter.
- So you see:
  - **Mix mode**: router stats (by layer, local vs cloud) **and** total cloud requests (including those routed to cloud by the router).
  - **Single cloud mode**: no router stats, but **cloud request count** still increases for cost visibility.

---

## Reports (structure and options)

Reports combine **router stats** (mix) and **cloud usage** into one place. For where to get them (logs, API, tool), see [How to see reports](#how-to-see-reports). Below: exact structure and options.

### What’s in the report

- **generated_at**: UTC timestamp.
- **router**: total_mix_requests, routed_local, routed_cloud, by_layer (heuristic, semantic, classifier, perplexity, default_route).
- **cloud_usage**: cloud_requests_total.
- **summary**: total_cloud_requests, mix_requests, mix_routed_local, mix_routed_cloud.

### REST API

- **Endpoint**: `GET /api/reports/usage`
- **Auth**: Same as other protected APIs (e.g. `X-API-Key` or `Authorization: Bearer` when `auth_enabled`).
- **Query**:
  - **`format=json`** (default): response is JSON (full report object).
  - **`format=csv`**: response is CSV (`section`, `key`, `value`) for dashboards or billing.

**Examples**:

```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:9000/api/reports/usage"
curl -H "X-API-Key: YOUR_KEY" "http://localhost:9000/api/reports/usage?format=csv"
```

### Built-in tool: `usage_report`

- **Name**: `usage_report`
- **Parameters**: none.
- **Description**: Get the current usage report (router stats + cloud counts). Use when the user asks for cost, usage, or how many requests went to cloud vs local.
- **Returns**: A short text summary (generated_at, summary lines, by-layer breakdown) plus the full report as JSON, so the model can answer questions and “review” the report.

---

## Quick reference

| Item | Where |
|------|--------|
| Enable mix | `main_llm_mode: mix`, `main_llm_local`, `main_llm_cloud`, `hybrid_router` in `config/core.yml` |
| Heuristic rules | `config/hybrid/heuristic_rules.yml` (keywords, long_input_chars/route) |
| Semantic utterances | `config/hybrid/semantic_routes.yml` (local_utterances, cloud_utterances) |
| Layer 3 mode | `hybrid_router.slm.mode`: `classifier` (small model) or `perplexity` (main model confidence probe). See docs_design/StrongLocalModelAndPerplexityRouting.md |
| Classifier model | When mode=classifier: add a `local_models` entry (e.g. port 5089), set `hybrid_router.slm.model` |
| Report (API) | `GET /api/reports/usage` or `?format=csv` |
| Report (in chat) | User asks for usage/cost → model calls **usage_report** tool |

---

## Design and implementation

- **Design**: `docs_design/HybridLocalCloudLLM.md`
- **Step-by-step implementation plan**: `docs_design/HybridRouterImplementationPlan.md`
- **Router runs before**: tools, skills, plugins, workspace, routing block (see implementation plan for the exact call site in `core/core.py`).
