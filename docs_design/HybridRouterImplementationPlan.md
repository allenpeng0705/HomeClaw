# Hybrid router implementation plan (step-by-step)

**Goal:** Add **mix mode** for the main model using a **3-layer smart router**, without breaking any existing behaviour (local-only and cloud-only must remain unchanged). After each step, a short summary keeps context for the next.

**Design reference:** `docs_design/HybridLocalCloudLLM.md`

---

## Exact call site (core/core.py)

The **only** place the router runs is inside **`answer_from_memory`** (starts ~3146). Insert the router logic **immediately before** the block that builds the system prompt (i.e. before `use_memory = ...`, `system_parts = []`, workspace, agent memory, skills, plugins, routing block).

- **Insert point:** Right after the pending-plugin block (after line ~3217) and **before** line 3219 (`use_memory = Util().has_memory()`). At that point we have: `query` (user message), optional `request` (for last 1–2 turns if needed), and no tools/skills/plugins injected yet.
- **Flow:** (1) If `main_llm_mode == "mix"`, call router with `query` (and optionally minimal history from `request`); get `route`. (2) Resolve LLM with `main_llm_for_route(route)` and store it in a request-scoped variable (or pass through to completion). (3) Then run the existing block from 3219 onward (build `system_parts`, then `llm_input`, then `openai_chat_completion`). The completion call at ~3646 must use the **request-scoped** resolved LLM when in mix mode (e.g. pass `llm_name` or a resolved LLM tuple that the completion path respects).

This keeps routing **before** any injection of tools, skills, plugins, workspace, or routing block.

---

## Principles (never break)

1. **Existing behaviour:** When `main_llm_mode` is `"local"` or `"cloud"` (or unset/legacy), the system must behave exactly as today: single `main_llm`, no router, same code path.
2. **Router runs before complex context:** The router must run **before** injecting tools, skills, plugins, workspace, agent memory, and other heavy context. Only **user input** (and optionally minimal history) is used for routing. After routing, the chosen model is fixed and **then** we build the full prompt with skills/plugins/etc.
3. **Scoring is critical:** Each layer returns a **score** and a **selection**; we use the selection only when score ≥ threshold. Threshold = 0 or enabled = false means skip that layer.
4. **Layer 1:** Multi-language via alias mapping + normalization; allow user-addable keywords (config file now, optional UI later).
5. **Layer 2:** Use **aurelio-labs/semantic-router** with a **custom encoder** that calls the **existing local llama.cpp embedding** (no second embedding model).
6. **Layer 3:** Use **existing llama.cpp model loading** (same mechanism as main LLM) for a small model (e.g. Qwen3-0.5B) on **another port**; user can place the GGUF in the models folder.
7. **Logs and reports:** Detail logs and reporting for (a) **router** in mix mode (which route, which layer, counts, cost), and (b) **existing single cloud model usage** (so cloud cost and usage are visible even when not using mix).

---

## Step 1: Config schema and mode flag (no router yet)

**What to do**

- Add to `config/core.yml` (with defaults so current config is unchanged):
  - `main_llm_mode`: `"local"` | `"cloud"` | `"mix"`. Default: derive from current `main_llm` (if ref starts with `cloud_models/` → `"cloud"`, else `"local"`) so existing config stays valid.
  - When mode is `"mix"`: `main_llm_local`, `main_llm_cloud` (refs like `local_models/...`, `cloud_models/...`), and `hybrid_router` with:
    - `default_route`: `"local"` | `"cloud"`
    - `heuristic`: `enabled`, `threshold`, path to rules (e.g. YAML/JSON)
    - `semantic`: `enabled`, `threshold`, intent example paths (local/cloud)
    - `slm`: `enabled`, `threshold`, `model` (e.g. `local_models/classifier_0_5b`)
- In `base/base.py` (CoreMetadata), add optional fields: `main_llm_mode`, `main_llm_local`, `main_llm_cloud`, `hybrid_router` (dict). Ensure YAML loader fills them and that missing values don’t break existing code.
- In `base/util.py`: add `main_llm_for_route(route: Optional[str])` (or extend `main_llm()` with an optional `route` argument):
  - If `main_llm_mode != "mix"`: ignore `route`, return current `main_llm()` (unchanged).
  - If `main_llm_mode == "mix"` and `route in ("local", "cloud")`: return the tuple for `main_llm_local` or `main_llm_cloud` (same shape as `main_llm()`). Do not change any existing call sites yet.

**Testing**

- With existing config (no `main_llm_mode` or mode = local/cloud), `main_llm()` and `main_llm_for_route(None)` behave as today. With mode = mix and a test config, `main_llm_for_route("local")` and `main_llm_for_route("cloud")` return the correct model tuples.

**Summary after Step 1**

- Config schema and CoreMetadata support mix mode and hybrid_router. Resolving “which main LLM for this request” is available via `main_llm_for_route(route)` when mode is mix; existing single-model path is untouched.

---

## Step 2: Single call site — run router only when mode is mix, before context injection

**What to do**

- Locate the **single place** in `core/core.py` where the main chat turn is built and sent: where we have the **user message** (and latest chat history) and **before** we build the big system prompt that includes skills, plugins, workspace, routing block, etc. That is the **only** place the router runs.
- Add:
  1. Read `main_llm_mode` from config.
  2. If mode is **not** `"mix"`: set `effective_route = None` and keep using current `Util().main_llm()` for this request (no router). Proceed to build prompt and call completion as today.
  3. If mode is `"mix"`:
     - Run the router with **only** the user message (and optionally last 1–2 turns of history for semantic/classifier). Input to the router must **not** include tools, skills, plugins, or other injected context.
     - Get `route = "local"` | `"cloud"` and optional `(layer, score, reason)` for logging.
     - Resolve main LLM with `Util().main_llm_for_route(route)` and use that for the completion call (host, port, model, type) for this request only.
- Ensure the completion path (e.g. `openai_chat_completion`) uses the **request-scoped** resolved LLM (e.g. pass it through or set a thread-local / context that the completion function reads). Do **not** change `main_llm` in global config.
- **Temporary router implementation:** If the real 3-layer router is not ready, use a **stub** that always returns `default_route` from config so the rest of the pipeline (resolve LLM by route, then build prompt with skills/plugins) is exercised without breaking anything.

**Testing**

- With mode = local or cloud: behaviour identical to today (no router, same LLM).
- With mode = mix and stub router returning default_route: every request goes to one model (local or cloud per default_route); prompt still includes skills/plugins; no crashes.

**Summary after Step 2**

- Router is invoked only when mode is mix, and only **before** tools/skills/plugins are injected. The completion for the turn uses the route-chosen LLM. Stub router allows end-to-end testing without the real layers.

---

## Step 3: Layer 1 — Heuristics (multi-language, user-addable keywords)

**What to do**

- Implement **Layer 1** in a small module (e.g. `hybrid_router/heuristic.py` or under `core/`):
  - Load rules from a **config file** (YAML/JSON): e.g. lists of keywords/patterns per category (e.g. `LOCAL_SYSTEM`, `PRIVATE_DATA`) and optional `len(input) > N` → cloud. Structure: alias mapping (same intent in multiple languages in one list) and normalization (lowercase + Unicode NFC) before matching.
  - Return `(score, selection)` or “no match”: e.g. score 1.0 when a rule matches (→ local or cloud per rule), 0 when no match. Support **enabled** and **threshold** from config; if threshold is 0 or heuristic disabled, skip (return no match).
- **Multi-language:** Use **alias mapping** in the config file: one entry per intent with keywords in several languages (e.g. screenshot: `["截图", "screenshot", "capture", "屏幕"]`). Normalize user input (lowercase, Unicode normalize) before matching. No hardcoded `if "x" in input or "y" in input` in code.
- **User-addable keywords:** Store rules in a file (e.g. `config/hybrid/heuristic_rules.yml`) so users can add keywords without code changes. Document the format; later, a UI can edit the same file or an API can append to it.
- Wire Layer 1 into the router: if heuristic enabled and threshold > 0, run it; if score ≥ threshold, **return** that selection and **do not** run Layer 2 or 3. Otherwise fall through to default_route (until Layer 2/3 exist) or to Layer 2.

**Testing**

- With heuristic disabled or threshold 0: no match, fall through.
- With a rule matching (e.g. “screenshot” or “截图”): score 1.0, selection local; route = local for that request.
- Long input (e.g. > 4000 chars) → cloud if so configured.

**Summary after Step 3**

- Layer 1 is in place: config-driven, multi-language via alias mapping and normalization, user-addable keywords via file. Scoring and threshold respected. When it wins, no later layers run.

---

## Step 4: Layer 2 — Semantic router (aurelio-labs + existing embedding)

**What to do**

- Add dependency: `semantic-router` (and optionally `semantic-router[local]` if needed). Do **not** add a second embedding model.
- Implement a **custom encoder** that implements the library’s `DenseEncoder` interface and calls **existing** embedding: same endpoint as `Util().embedding()` (llama.cpp embedding server). In `__call__(docs: List[str])` return `List[List[float]]` by calling `Util().embedding(d)` per doc (or batch if the server supports it), e.g. via asyncio.run. Register or pass this encoder when creating the semantic router.
- Define **Route**s for “local” vs “cloud” (or skill clusters) with example utterances; load intent examples from config paths if needed. Create the semantic router with the custom encoder and routes.
- In the router flow: if Layer 2 is enabled and threshold > 0, run the semantic router on the **user message only** (no tools/plugins). Get (route name, score). Map route name to `local` or `cloud`. If score ≥ threshold, return that selection; else fall through to Layer 3 or default_route.
- **Scoring:** Use the library’s similarity score; ensure it’s in [0, 1] and compare to `threshold_semantic`.

**Testing**

- With semantic disabled or threshold 0: skip Layer 2.
- With a few test utterances that match “local” or “cloud” routes: check that the returned route and score are correct and that the chosen main LLM is used for the completion.

**Summary after Step 4**

- Layer 2 uses aurelio-labs/semantic-router with the **existing** llama.cpp embedding model via a custom encoder. No second embedding; scoring and threshold control when Layer 2 wins.

---

## Step 5: Layer 3 — Small local classifier (existing llama.cpp loading, another port)

**What to do**

- **Reuse existing llama.cpp model loading:** Add a `local_models` entry for the classifier (e.g. `id: classifier_0_5b`, `path: "path/to/Qwen3-0.5B.gguf"` or similar under the project’s models folder, `host`, `port: 5089`). User downloads the GGUF and puts it in the models folder; path in config points to it.
- At startup, when `main_llm_mode == "mix"` and `hybrid_router.slm.enabled`, start the classifier model’s server the **same way** as the main LLM (e.g. via the same llmManager/launcher that starts other local models), so it listens on its port and exposes `/v1/chat/completions`.
- Implement the classifier step: build a **short judge prompt** (e.g. “Does this request require real-time internet or complex logic? Answer only: Cloud or Local.” + user input; optionally last 1–2 turns or summary). POST to `http://{classifier_host}:{classifier_port}/v1/chat/completions`, parse the reply for “Local”/“Cloud”, and optionally confidence (e.g. from logprobs). Return `(score, selection)`. If classifier threshold is 0, always use its choice; if threshold > 0, use selection only when score ≥ threshold.
- Wire Layer 3 into the router: when Layer 1 and 2 don’t produce a selection (or are disabled), run Layer 3 if enabled; else use `default_route`.

**Testing**

- With classifier disabled: fallback to default_route.
- With classifier enabled and a small model running on the configured port: ambiguous queries get a local/cloud decision from the small model; completion uses the chosen main LLM.

**Summary after Step 5**

- Layer 3 uses the **existing** llama.cpp server mechanism (same as main LLM), on a **separate port**, with a small model the user can download. Full 3-layer cascade is in place with per-layer on/off and thresholds.

---

## Step 6: Per-request routing logs and aggregated counts (mix mode)

**What to do**

- After each routing decision in mix mode, write a **structured log line** (e.g. JSON) with: timestamp, route (local/cloud), layer (heuristic | semantic | classifier | default_route), score, reason (short string), request_id/session_id if available, latency_ms (optional).
- Maintain **aggregated counts** (in memory or a small store): total mix requests, routed to local, routed to cloud, and optionally by layer. Optionally tokens per cloud request if available. Expose these for reports (e.g. a simple API or a function that returns the counters).
- Ensure logs and counts are **only** for mix-mode requests when the router runs; do not change logging for local-only or cloud-only mode.

**Testing**

- Trigger a few mix-mode requests with different outcomes (L1 win, L2 win, L3 win, default_route). Check that logs contain the expected route and layer and that counts increment correctly.

**Summary after Step 6**

- Detail logs answer “which was routed to local/cloud and by which layer”; aggregated counts support cost calculation (e.g. cloud count) and reporting.

---

## Step 7: Reports and cloud-usage logging (router + existing single cloud)

**What to do**

- **Report generation:** Add a way to produce a **report** (e.g. daily or on demand) from the aggregated data: breakdown by route (local vs cloud), by layer, cloud request count (and optionally tokens) for cost. Export as CSV or JSON for dashboards or billing.
- **Existing single cloud model usage:** Ensure that when the main model is **cloud** (mode = cloud or main_llm = cloud_models/...), we also log or count **cloud usage** (e.g. requests and optionally tokens) so that cost and usage are visible even when **not** using mix mode. Reuse or extend the same report format so one report can show “cloud usage” whether from mix-mode router or from single cloud mode.
- Prefer a single logging/reporting path: e.g. “main model used for this request” (local vs cloud) + “if cloud, log/count it”. Then the report can aggregate all cloud usage (mix + single cloud).

**Testing**

- With mode = cloud only: verify cloud requests are logged/counted and appear in the report.
- With mode = mix: verify router logs and cloud count; report includes both router decisions and cloud usage.

**Summary after Step 7**

- Reports and cloud-usage visibility are in place for both the hybrid router (mix) and existing single cloud usage. Cost and “how many routed to cloud” are available for tuning and billing.

---

## Step 8: Startup and lifecycle (mix mode: two backends + classifier)

**What to do**

- When `main_llm_mode == "mix"`:
  - Ensure **main_llm_local** and **main_llm_cloud** are started or available (local: llama.cpp server on its port; cloud: litellm proxy or API key configured). Reuse existing startup (e.g. llmManager) to start the local main model and, when `slm.enabled`, the classifier model on **another port**.
  - Do not start the router or classifier when mode is local or cloud; no extra processes.
- Document in config comments: for mix, user must have both local and cloud models configured and (if Layer 3 enabled) a small model GGUF in the models folder with a dedicated port.

**Testing**

- With mode = local or cloud: only one main LLM server as today.
- With mode = mix: local main + classifier (if enabled) and cloud available; router can use both.

**Summary after Step 8**

- Mix mode has correct startup and lifecycle; classifier reuses existing llama.cpp loading on a separate port; existing single-model modes are unchanged.

---

## Order summary and dependency

| Step | Content | Depends on |
|------|---------|------------|
| 1 | Config schema, `main_llm_mode`, `main_llm_for_route()` | — |
| 2 | Single call site: run router (stub) **before** tools/skills/plugins; use `main_llm_for_route(route)` for completion | 1 |
| 3 | Layer 1 heuristics (multi-language, user-addable keywords, scoring) | 2 |
| 4 | Layer 2 semantic (aurelio-labs + custom encoder = existing embedding) | 2 |
| 5 | Layer 3 classifier (existing llama.cpp, another port, small model) | 2, 4 (optional: can do before 4) |
| 6 | Per-request logs + aggregated counts (mix) | 2 |
| 7 | Reports + cloud-usage logging (router + single cloud) | 6 |
| 8 | Startup/lifecycle for mix (two backends + classifier) | 1, 5 |

**Critical reminder:** The router runs **before** injecting tools, skills, plugins, and other complex context. Only after the route is chosen do we build the full prompt and call the chosen main LLM. Scoring (and thresholds) decide whether each layer’s selection is used; otherwise we fall through to the next layer or default_route.
