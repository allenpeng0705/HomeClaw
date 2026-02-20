# Hybrid local and cloud LLM (design)

**Status:** Design / discussion.  
**Goal:** Let local and cloud models work together so we get low cost and good capability—use local for simple or private tasks, cloud for complex or high-quality tasks, and decide per request which to use.

---

## 1. Context

HomeClaw already supports:

- **Cloud models** (LiteLLM: OpenAI, Gemini, DeepSeek, etc.) and **local models** (llama.cpp, GGUF).
- **Embedding** can be local or cloud; today we often use **local embedding** for RAG (cheap, private).
- **Main LLM** is a single choice: either one cloud model or one local model for chat.

We want a **hybrid** mode: **route each user request** to the right model (local or cloud) instead of using only one for everything.

---

## 2. Ideas from the discussion (Gemini)

### 2.1 Four strategies for mixing local and cloud

| Strategy | Idea | Pros / cons |
|----------|------|--------------|
| **Intent-based routing** | Small local model (or classifier) labels the user input (e.g. simple vs complex). Route by label. | Clear split; need good intent examples or a tiny classifier. |
| **Confidence-based escalation** | Always try local first; if confidence (e.g. logprobs) is low or model says “I don’t know”, send the same request to cloud. | Good quality; double latency when we escalate. |
| **Layered processing** | Preprocess and retrieve locally (keywords, NER, RAG); send only compressed context + instruction to cloud for reasoning. | Fewer tokens to cloud, lower cost; more moving parts. |
| **Task delegation** | Local model acts as “router”: it decides subtasks and calls local (e.g. read doc, summarize) or cloud (e.g. polish email). | Flexible; needs tool-calling and clear task boundaries. |

### 2.2 How to decide “local vs cloud” without adding much latency

- **Semantic router (< 10ms)**  
  Use **embedding** (we already have local embedding).  
  - Define intent examples: “local” intents (e.g. “today’s weather”, “remind me”, “summarize this file”) and “cloud” intents (e.g. “analyze 2024 global economy”, “write a complex React design”).  
  - Embed user input with the same embedding model; compare (e.g. cosine similarity) to precomputed intent vectors.  
  - Route to local or cloud by which side is closer (or by threshold).  
  No extra LLM call, so very fast.

- **Small local classifier (~100–300 ms)**  
  Tiny model (e.g. 0.5B–2B) only outputs a label like `{"target": "local"}` or `{"target": "cloud"}`.  
  Slightly smarter than pure similarity, but adds latency and one more model to run.

- **Heuristics (0 ms)**  
  Rules before any model: e.g. if input contains “private” / “my file” → local; if length > N words or “deep analysis” → cloud.  
  Can be combined with semantic router (e.g. heuristics first, then semantic for borderline cases).

### 2.3 “If local can’t do it, then route to cloud—won’t that be slow?”

- **Confidence-based escalation** (try local, then cloud if unsure) can indeed add latency when we escalate.
- Mitigations:
  - **Parallel / speculative:** Start both local and cloud; if local is confident quickly, use it and cancel cloud.
  - **Streaming:** Start with local; if the first few tokens look bad, switch to cloud.
  - **User feedback:** Show “Trying local…” and “Switched to cloud for better answer” so the wait is understandable.

**Recommendation from the discussion:** Start with **Semantic Router** (embedding + intent examples). We already have local embedding; we only add intent examples and a small “router” step before calling the main LLM.

### 2.4 Cascading Routing Filter System (级联路由过滤系统)

Gemini framed this as a **Cascading Routing Filter System**: a three-layer **funnel**. Each layer has an "outlet" (direct handling when score ≥ threshold) and a "downstream" (flow to the next layer when not). The design balances **speed** (Heuristics), **intelligence** (Semantic), and **depth** (Classifier).

| Step | Technique | Typical latency | Score | Threshold logic |
|------|-----------|------------------|-------|------------------|
| **1. Heuristics** | Regex, keywords, input length | **&lt; 1 ms** | e.g. 100 if keyword match else 0 (or 0–1 scale) | If score ≥ threshold (e.g. 90 or 0.9) → use this step's selection, done. |
| **2. Semantic** | Vector cosine similarity | **5–20 ms** | 0.0–1.0 (e.g. max cosine similarity to winning intent) | If score ≥ threshold (e.g. 0.85) → use this step's selection, done. |
| **3. Classifier** | Tiny model (e.g. Qwen-0.5B, FastText, small MLP) | **100–300 ms** | e.g. Softmax max probability | Optional: if score ≥ threshold (e.g. 0.6) → use selection; else use default fallback. Or no threshold (always use choice). |

**Why this system is critical:** Cold start (heuristics handle simple commands in &lt;1 ms); token cost (semantic routes "daily chat" to local); user control (threshold = 0 to skip a step, or force local/cloud via mode).

### 2.5 Desktop assistant: decision-maker vs executor (Gemini)

For a **desktop**, **remotely accessible** personal assistant that can **operate the computer** (browser, apps, documents), the design should separate **“decision maker”** (which model plans/reasons) and **“executor”** (where tools run). Below is a detailed layer-by-layer and tool-use design from Gemini.

#### Three-layer routing (detailed)

| Layer | Role (Gemini) | Logic | Examples |
|-------|----------------|-------|----------|
| **1. Heuristics** (语义嗅探层 — fast reflex, no AI) | **Security/privacy:** Keywords [密码, 银行, 个人文件, .ssh] → **100% local**. **System control:** [静音, 截图, 关机, 打开微信] → **100% local**; can dispatch **subprocess / pyautogui directly** without calling the LLM, response &lt;1 ms. **Context length:** `len(input) > 4096` → **100% cloud** (local slow + VRAM risk). **Tool linkage:** When “system control” matches, send Python subprocess/pyautogui directly. | Score + selection; threshold as in §4.6. | Privacy/system → local; long input → cloud. |
| **2. Semantic router** (意图映射层) | Maintain a **vector index** of hundreds of typical task vectors. **Local cluster:** e.g. “总结本地 Word 文档”, “读取最近的 PDF”, “在本地搜索文件”. **Cloud cluster:** e.g. “帮我制定一份 5 天的旅行计划”, “解释量子纠缠的原理”, “分析最新的科技新闻”. **Compute:** `CosineSimilarity(InputVector, ClusterCentroid)`; if similarity to **local** tasks &gt; 0.85 → route to local. | Faster than running an LLM; distinguishes “data source” (local vs internet). | Intent examples + centroids; threshold e.g. 0.85. |
| **3. Small local classifier** | If the first two layers cannot decide, run a tiny local model (e.g. Qwen-0.5B or FastText). **Prompt:** “判断该任务是否需要访问互联网或复杂的逻辑推理？” **Output:** JSON e.g. `{"target": "local", "reason": "file_access", "confidence": 0.9}`. **Tool pre-judgment:** e.g. “帮我查一下我的日程并回封邮件” → two steps (read local + write email) → can mark **Mix Mode** (local + cloud). | Optional threshold on confidence; fallback to default_route. | See §4.6 classifier step. |

#### Tool-use architecture (工具化协作)

So that **local** (e.g. llama.cpp) and **cloud** (litellm) can cooperate on **browser, apps, documents**:

1. **Task decomposition (Decomposition)**  
   For a complex instruction (e.g. “打开浏览器查一下 GPT-5 的最新消息，并把摘要保存到桌面的 my_notes.docx”):  
   - **Cloud (reasoning):** Produces a **plan** (steps: e.g. use `browser_tool` to search; use `file_tool` to write).  
   - **Local (execution):** Runs tools — e.g. `browser_tool` via local Python (Playwright/Selenium); `file_tool` via python-docx.  
   - **Local (observer):** Can monitor execution for sensitive data so that e.g. passwords seen in the browser are not sent to the cloud.

2. **Tool division (本地与云端的工具集分工)**

| Tool type | Prefer | Implementation |
|-----------|--------|-----------------|
| **Document processing** | Local | RAG (e.g. llama-cpp-python) to read local .txt/.pdf/.docx. |
| **Browser operation** | Local driver | Cloud generates logic (e.g. XPath); **local** Python drives browser (Playwright/Selenium). |
| **Third-party apps** | Local | pywinauto (Windows) or AppleScript (Mac) on the desktop. |
| **Complex decision / reasoning** | Cloud | Only **desensitized** context sent to litellm for deep reasoning. |

#### Implementation notes (Gemini)

- **State machine:** Use LangGraph or a simple state machine in Python to manage routing and tool flow.  
- **Global flag:** e.g. `USE_CLOUD = True/False` (or `main_llm_mode: "local" | "cloud" | "mix"`).  
- **Mix mode default:** All **tool execution** stays **local**; only **thought generation** (which model to use for planning/reply) is decided by the scoring cascade.  
- **Security:** Add a **filter layer** in the Python backend to intercept cloud API requests and strip or block tokens and privacy-sensitive content before sending to the cloud.

---

## 3. Decision matrix (when to use which model)

| Dimension | Prefer **local** | Prefer **cloud** |
|-----------|-------------------|-------------------|
| **Privacy** | PII, private notes, “my files” | General knowledge, public topics |
| **Task difficulty** | Simple Q&A, short summary, format change, reminders | Complex reasoning, long-form writing, math, code design |
| **Latency** | Need instant feedback (e.g. autocomplete) | OK with 2–3 s |
| **Cost** | High-frequency, repetitive tasks | Occasional, complex requests |

We can encode this as **intent examples** (for semantic router) and/or **rules** (for heuristics).

---

## 4. Proposed design for HomeClaw

### 4.1 Config

- **Mode flag**  
  - **`main_llm_mode`**: **`"local"`** | **`"cloud"`** | **`"mix"`**  
  - **`local`** — Always use local main LLM (no router).  
  - **`cloud`** — Always use cloud main LLM (no router).  
  - **`mix`** — Use the **scoring cascade** (heuristics → semantic → SLM) to choose local or cloud per request. See §4.6.

- **When mode = `mix`**  
  - **`main_llm_local`**, **`main_llm_cloud`** — Which main LLM to use when the router selects local or cloud.  
  - **Router config** — Per-step enable/disable and thresholds. Each step (heuristic, semantic, SLM) has a **score** and optional **threshold**; threshold 0 = step skipped. Only when a step’s score ≥ threshold do we use that step’s selection; otherwise we go to the next step. Last step (SLM) is final fallback (no threshold). See §4.6 for the full cascade and config sketch.  
  - **`default_route`** — When all steps are skipped or none pass: use `"local"` or `"cloud"`.

- **Embedding**  
  - Router reuses the **existing embedding** model (already local-friendly). No new service.

### 4.2 Data: intent examples and vectors

- **Intent examples (human-readable)**  
  - `config/hybrid/local_intent_examples.txt` (or yaml): one line per phrase/sentence that should go to **local** (e.g. “what’s the weather”, “remind me in 5 minutes”, “summarize this note”).  
  - `config/hybrid/cloud_intent_examples.txt`: examples for **cloud** (e.g. “write a long analysis”, “explain the proof”, “translate this formally”).

- **Precomputed vectors (optional)**  
  - At startup (or in a build step), embed all intent examples with the configured embedding model; store in `config/hybrid/intent_vectors.json` (or similar) so we don’t embed on every request.  
  - At request time: embed **user message** once; compare to these vectors (cosine similarity); choose local or cloud by which side wins (or by threshold).

### 4.3 Where it fits in the pipeline

- **Today:** User message → (optional orchestrator) → **one** main LLM (local or cloud) → tools/RAG/plugins → response.
- **With hybrid:** User message → **router** (heuristic + optional semantic) → **local** or **cloud** main LLM → same tools/RAG/plugins → response.

So the only new piece is a **routing step** before we call the main LLM. The rest (RAG, tools, plugins, TAM) stays unchanged.

- **Optional later:** Confidence-based escalation (call local first; if confidence low, retry same request with cloud). That would sit “around” the main LLM call (try local → if bad, try cloud).

### 4.4 Router implementation options

1. **Heuristic only**  
   - Keywords/length rules in code or small config.  
   - No embedding call.  
   - Easiest to ship; less accurate.

2. **Semantic only**  
   - Embed user message; compare to intent vectors; pick local or cloud.  
   - Reuses existing embedding API.  
   - Fast (< 10 ms if embedding is already fast).

3. **Heuristic + semantic**  
   - If heuristic is sure (e.g. “my secret file” → local), use it.  
   - Else use semantic similarity.  
   - Good balance of speed and quality.

4. **SLM classifier (later)**  
   - Tiny local model that outputs `local` or `cloud`.  
   - More flexible, but adds latency and dependency on another model.

### 4.5 Fallback and defaults

- If router fails (e.g. embedding error): use a **default_route** (e.g. `cloud` to be safe, or configurable).
- If **local** is chosen but local model is unavailable: fallback to cloud for that request (optional).
- **Embedding** remains local when possible (already the case); no change required for the router.

### 4.6 Scoring system and three-step cascade

When we use **mix** mode, we decide “local” vs “cloud” with a **cascade of three steps**, each with a **score** and an optional **threshold**. Each step can be turned on/off (e.g. threshold 0 = skip). Only when a step’s score meets its threshold do we use that step’s **selection** and stop; otherwise we go to the next step. The last step (SLM) is the final fallback and does not require passing a threshold.

#### Mode flag

- **`main_llm_mode`** (or equivalent): **`"local"`** | **`"cloud"`** | **`"mix"`**
  - **`local`** — Always use the local main LLM. No router; ignore cascade.
  - **`cloud`** — Always use the cloud main LLM. No router; ignore cascade.
  - **`mix`** — Use the routing cascade below to choose local or cloud per request.

**Summary (scoring + on/off + mode flag):**

1. **Heuristics first** — Run heuristics; get a **score** and a **selection** (local/cloud). If the score is **very high** (≥ threshold), use this step's selection **directly** and stop. Threshold is configurable; **threshold = 0** means this step is **turned off** (skipped).
2. **If heuristics didn't pass** — Run **semantic router**. It also returns a **score** and a **selection**. It must **pass its own threshold** to be used: if score ≥ threshold → use its selection and stop; if not → go to the next step.
3. **If both heuristics and semantic didn't get enough score** — Run the **small local classifier (SLM)** and use **its choice** (no threshold; it's the final fallback). SLM can be turned off; then we use **default_route** (e.g. cloud).

**Every step can be turned on/off** (e.g. `enabled: true/false` or **threshold = 0 = skip**). We also have a **global flag**: **`main_llm_mode`** = **`"local"`** | **`"cloud"`** | **`"mix"`** — only when **`mix`** do we run the cascade; `local`/`cloud` force one model and skip the router.

#### Three-step cascade (only when mode = `"mix"`)

| Step | What it does | Score | Threshold | On/off |
|------|----------------|------|-----------|--------|
| **1. Heuristics** | Rules (keywords, length, etc.) → selection (local/cloud) + score in [0, 1]. | e.g. 1.0 = strong rule match, 0.5 = weak match, 0 = no match. Configurable. | `threshold_heuristic`. If score ≥ threshold → use this step’s selection and **stop**. | **Skip** if threshold = 0 (or if `enabled: false`). |
| **2. Semantic router** | Embed user input; compare to intent vectors → selection + score (e.g. max similarity). | e.g. 0..1 (max cosine similarity to winning intent side). Must pass threshold to “win”. | `threshold_semantic`. If score ≥ threshold → use this step’s selection and **stop**. | **Skip** if threshold = 0 (or if `enabled: false`). |
| **3. Small local classifier (SLM)** | Tiny model (e.g. Qwen-0.5B, FastText, small MLP) → selection + optional score (e.g. Softmax max prob). | e.g. 0–1 (max probability). Optional threshold. | If threshold = 0: always use choice (final fallback). If threshold &gt; 0: use selection only when score ≥ threshold; else **default_route**. | **Skip** if disabled (e.g. no SLM configured); then use **default_route**. |

**Flow:**

1. If **heuristics** is enabled (threshold > 0): run heuristics → get `(score_h, selection_h)`. If `score_h >= threshold_heuristic` → **return selection_h**, done.
2. Else (heuristics skipped or didn’t pass): run **semantic router** (if enabled). Get `(score_s, selection_s)`. If `score_s >= threshold_semantic` → **return selection_s**, done.
3. Else (semantic skipped or didn’t pass): run **SLM** (if enabled). Get `(score_slm, selection_slm)`. If `threshold_slm === 0` or `score_slm >= threshold_slm` → **return selection_slm**, done; else use **default_route**.
4. If SLM is disabled or fails → use **default_route** (e.g. `"cloud"`).

So: **every step can be turned on/off** (e.g. threshold 0 = skip). We only use a step’s selection when it **passes its threshold**; otherwise we fall through to the next step. The last step (SLM): if threshold = 0 we always use its choice; if threshold &gt; 0 we use its selection only when score ≥ threshold, else default_route. We also have a **global mode** so we can force always-local, always-cloud, or mix.

#### Config sketch (for mix mode)

```yaml
# Example shape; actual keys can follow your config style
main_llm_mode: "mix"   # "local" | "cloud" | "mix"
main_llm_local: "local_models/Qwen3-14B"
main_llm_cloud: "cloud_models/Gemini-2.5-Flash"

hybrid_router:
  default_route: "cloud"   # when all steps skipped or all fail

  heuristic:
    enabled: true
    threshold: 0.9         # 0 = skip this step
    # rules: keywords, length, etc. (in code or config)

  semantic:
    enabled: true
    threshold: 0.7         # 0 = skip this step
    intent_examples_local: "config/hybrid/local_intent_examples.txt"
    intent_examples_cloud: "config/hybrid/cloud_intent_examples.txt"
    # optional: intent_vectors path for precomputed embeddings

  slm:
    enabled: true          # false = use default_route when step 1 and 2 don't pass
    threshold: 0           # optional: 0 = always use classifier choice; >0 = only use if score >= threshold
    model: "local_models/classifier_0_5b"   # small model e.g. Qwen3-0.5B; served by llama.cpp on its own port (see below)
```

#### Per-layer on/off and testing flexibility

**Any of the three layers can be turned off at any time.** This is important for both production tuning and **testing** (e.g. test only Layer 2, or only Layer 3, or bypass the router entirely).

| What you want | How to configure |
|---------------|------------------|
| **No router — always local** | `main_llm_mode: "local"`. No layer runs; every request uses main_llm_local. |
| **No router — always cloud** | `main_llm_mode: "cloud"`. No layer runs; every request uses main_llm_cloud. |
| **Only Layer 1** | `mix` + `heuristic.enabled: true`, `semantic.enabled: false`, `slm.enabled: false`. If heuristic doesn’t match → **default_route**. |
| **Only Layer 2** | `mix` + `heuristic.enabled: false` (or `threshold: 0`), `semantic.enabled: true`, `slm.enabled: false`. If semantic doesn’t pass → **default_route**. |
| **Only Layer 3** | `mix` + `heuristic.enabled: false`, `semantic.enabled: false`, `slm.enabled: true`. Every request goes to the classifier (e.g. Qwen3-0.5B). |
| **Layer 1 + 2** | `heuristic.enabled: true`, `semantic.enabled: true`, `slm.enabled: false`. Fallback when both don’t pass → **default_route**. |
| **Layer 1 + 3** | `heuristic.enabled: true`, `semantic.enabled: false`, `slm.enabled: true`. |
| **Layer 2 + 3** | `heuristic.enabled: false`, `semantic.enabled: true`, `slm.enabled: true`. |
| **All three** | All enabled. Cascade: L1 → L2 → L3 → default_route. |

**Rule:** For each step, **enabled: false** or **threshold: 0** means “skip this step” (don’t run it, don’t use its selection). When all enabled steps fail to produce a selection, use **default_route**.

#### Layer 3 (classifier) deployment: reuse llama.cpp server, separate port

Layer 3 uses a **small local model** (e.g. **Qwen3-0.5B**) as a classifier. To reuse the **current mechanism** (llama.cpp web server: load model, serve HTTP, accept requests, return results) and avoid a separate stack:

- **Run the classifier as another llama.cpp server on another port.** Same as main LLM and embedding: each local model can have its own `host` and `port` in config.
- **Config:** Add a dedicated entry in `local_models` for the classifier (e.g. `id: classifier_0_5b`, `path: .../Qwen3-0.5B.gguf`, `port: 5089`). Under `hybrid_router.slm` set `model: "local_models/classifier_0_5b"`. At startup (when mode is `mix` and `slm.enabled`), start this model’s server the same way as the main LLM (e.g. via llmManager or the same launcher), so it listens on its port and exposes the usual OpenAI-compatible chat endpoint.
- **Request flow:** To run the classifier, send a **single short prompt** (e.g. “Does this request require real-time internet or complex logic? Answer only: Cloud or Local.” + user input) to `http://{classifier_host}:{classifier_port}/v1/chat/completions`, parse the reply to get `local` or `cloud`, and optionally a confidence (e.g. from logprobs or a softmax). No new process manager; just one more local model in `local_models` with its own port.

Example `local_models` entry for the Layer 3 classifier (same structure as other local models; different port):

```yaml
# In config/core.yml local_models list
- id: classifier_0_5b
  path: "path/to/Qwen3-0.5B.gguf"
  host: 127.0.0.1
  port: 5089   # e.g. main LLM 5088, embedding 5066, classifier 5089
  # optional: n_ctx, n_gpu_layers, etc. Same llama.cpp server mechanism as main LLM.
```

**Equivalent config shape (TypeScript-style):**

```ts
interface RoutingConfig {
  mode: "local" | "cloud" | "mix";
  steps: {
    heuristics: { enabled: boolean; threshold: number };
    semantic:    { enabled: boolean; threshold: number };
    classifier:  { enabled: boolean; threshold: number };
  };
  defaultFallback: "local" | "cloud";
}
```

**Core routing logic (pseudo-code):** Each step returns `{ score, selection }`; heuristics and semantic must pass threshold to "win"; classifier can have optional threshold or always use its choice.

```ts
async function getRoute(userInput: string, config: RoutingConfig): Promise<"local" | "cloud"> {
  if (config.mode !== "mix") return config.mode;

  if (config.steps.heuristics.enabled && config.steps.heuristics.threshold > 0) {
    const { score, selection } = runHeuristics(userInput);
    if (score >= config.steps.heuristics.threshold) return selection;
  }

  if (config.steps.semantic.enabled && config.steps.semantic.threshold > 0) {
    const { score, selection } = await runSemanticRouter(userInput);
    if (score >= config.steps.semantic.threshold) return selection;
  }

  if (config.steps.classifier.enabled) {
    const { score, selection } = await runLocalClassifier(userInput);
    if (config.steps.classifier.threshold === 0 || score >= config.steps.classifier.threshold)
      return selection;
  }

  return config.defaultFallback;
}
```

- **Threshold = 0** for a step: that step is **skipped** (we don’t run it, and we don’t use its selection).
- **Heuristic / semantic**: only “win” when score ≥ threshold; otherwise fall through.
- **SLM**: optional threshold; if threshold = 0 we always use its choice; if threshold &gt; 0 we use selection only when score ≥ threshold; if disabled, use `default_route`.
- **How to define scores:** Heuristic score can be, for example: **1.0** when a strong rule matches (e.g. exact keyword list), **0.5** when a weak rule matches (e.g. length-only), **0** when no rule matches. Semantic score is typically **max cosine similarity** of the user input embedding to the winning intent side (local vs cloud); scale to [0, 1] and compare to `threshold_semantic`.

#### Gemini implementation suggestions

- **Classifier:** Do not use a full LLM. Prefer a **tiny FastText** or a small **MLP** (e.g. TensorFlow.js); they can run on device in tens of milliseconds and output a local/cloud label.
- **Semantic router:** Reuse the **existing local embedding** and intent vectors; this step is effectively "free" — one extra vector search (cosine similarity) per request.
- **Heuristics:** A simple `runHeuristics` can use **regex / `String.match`** (or keyword lists) and return `{ score, selection }` (e.g. score 100 or 1.0 when a rule matches, 0 otherwise). A **cosineSimilarity** helper supports the semantic step.

### 4.7 Using existing libraries: aurelio-labs/semantic-router

Using a mature library keeps focus on HomeClaw-specific logic (browser control, desktop automation) instead of implementing vector routing from scratch. Two repos have similar names but different goals; for a **desktop Python + llama.cpp + litellm** stack, **aurelio-labs/semantic-router** is the better fit.

#### Library comparison (Gemini)

| Aspect | [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router) **(recommended)** | [vllm-project/semantic-router](https://github.com/vllm-project/semantic-router) |
|--------|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| **Focus** | Lightweight, application-level; for Agents and RAG; “which path next?”. | System-level, cluster traffic scheduling; K8s/edge. |
| **Stack** | Python; works with llama-cpp-python. | Rust/Go core; heavier for local dev. |
| **Local** | Optimized for local execution; supports GGUF as encoder. | Aimed at data-center / edge concurrency. |
| **Integration** | Low: a few lines for cascade + scoring. | Higher: sidecar/Envoy-style setup. |

**Conclusion:** For a desktop personal assistant, use **aurelio-labs/semantic-router**. It has local/GGUF examples and fits the Heuristics + Semantic + Scoring cascade.

#### Three-layer design on top of aurelio-labs

**Layer 1 — Heuristic pre-route (before the library)**  
Run a lightweight pre-check; if it returns a route, skip semantic. Example (multilingual keywords, length):

```python
def pre_route_check(user_input: str) -> str | None:
    if len(user_input) > 4000:
        return "cloud"   # long context → cloud
    local_triggers = ["密码", "password", "截图", "screenshot", "localhost"]
    if any(w in user_input.lower() for w in local_triggers):
        return "local"
    return None   # continue to semantic layer
```

**Layer 2 — Semantic router (aurelio-labs)**  
- Define **Route** objects with example utterances; the encoder maps user input to the best route and returns a **similarity score**.  
- Use a **multilingual encoder** so Chinese and English map to the same space, e.g. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.  
- **Scoring bands (example):**  
  - `score > 0.82` → use this route (e.g. local or cloud).  
  - `0.5 < score <= 0.82` → send to **Step 3** (small classifier).  
  - `score <= 0.5` → **default fallback** (e.g. cloud).

Example route definition (English utterances; multilingual encoder handles Chinese input):

```python
from semantic_router import Route

local_task = Route(
    name="local_desktop_control",
    utterances=[
        "open the browser", "close the music", "check my local files",
        "take a screenshot", "adjust the volume"
    ]
)
# Routes can be appended/removed at runtime.
```

**Layer 3** — Keep our small local classifier (or FastText/MLP) as in §4.6 when semantic score is in the middle band.

#### Using our existing embedding model (not a second encoder)

aurelio-labs/semantic-router does **not** ship an encoder that “use your existing HTTP embedding endpoint” out of the box. The [local execution notebook](https://github.com/aurelio-labs/semantic-router/blob/main/docs/05-local-execution.ipynb) uses **HuggingFaceEncoder** (e.g. `sentence-transformers/all-MiniLM-L6-v2`) for embeddings and **LlamaCppLLM** only for the **LLM** (dynamic routes), not for the encoder. So by default you would run a **second** embedding model for the router.

HomeClaw already has one embedding model: **OpenAI-compatible** `http://{host}:{port}/v1/embeddings` (llama.cpp or other), configured via `embedding_llm` and used by skills, plugins, and RAG. To use that **same** model for Layer 2 (semantic router) and avoid a second encoder:

**Option A — OpenAIEncoder pointing at our server**  
[OpenAIEncoder](https://github.com/aurelio-labs/semantic-router/blob/main/semantic_router/encoders/openai.py) accepts `openai_base_url` and `openai_api_key`. Set `openai_base_url="http://{host}:{port}/v1"` (from `Util().embedding_llm()`) and e.g. `openai_api_key="local"`. It will POST to our endpoint. **Caveat:** The class uses `tiktoken.encoding_for_model(name)` for truncation; that only knows OpenAI model names. For a local model id (e.g. `embedding_text_model`) you must subclass and override `_truncate` (e.g. character-based or no truncation), or pass a name tiktoken accepts and rely on the server ignoring it.

**Option B — LiteLLMEncoder with custom base**  
[LiteLLM](https://docs.litellm.ai/docs/providers/openai_compatible) supports `api_base` for embeddings: `litellm.embedding(model="openai/<id>", api_base="http://host:port", input=...)`. LiteLLMEncoder does not expose `api_base` in its constructor; you would need to subclass and pass `api_base` into `litellm.embedding` (e.g. via kwargs in the encoder’s `__call__` or by patching the litellm call).

**Option C — Custom encoder (recommended): use existing embedder directly**  
Implement a small **DenseEncoder** that calls HomeClaw’s existing embedding path so the router uses the **same** model as skills/plugins/RAG:

- **Contract:** `DenseEncoder` implements `__call__(self, docs: List[str]) -> List[List[float]]`.
- **Implementation:** Resolve `(host, port, model_for_body, api_key)` from `Util().embedding_llm()` (same as `Util().embedding()`). Then either (1) **batch:** POST `{"input": docs}` to `http://{host}:{port}/v1/embeddings` (if the server supports batch) and return `[item["embedding"] for item in response["data"]]`, or (2) **loop:** for each doc, call `Util().embedding(doc)`; since `embedding()` is async, run in an event loop (e.g. `asyncio.run(_embed_all())` or a sync helper that POSTs once per doc). Return `List[List[float]]`.

Example sketch (sync batch or loop; reuse same URL/headers as `Util().embedding`):

```python
# In a HomeClaw router module, e.g. hybrid_router/encoder.py
from typing import List
from semantic_router.encoders import DenseEncoder
from base.util import Util
import asyncio

class HomeClawEmbeddingEncoder(DenseEncoder):
    """Encoder that uses HomeClaw's existing embedding model (same as skills/plugins/RAG)."""
    name: str = "homeclaw_embedding"
    type: str = "homeclaw"

    def __call__(self, docs: List[str]) -> List[List[float]]:
        resolved = Util().embedding_llm()
        if not resolved:
            raise RuntimeError("embedding_llm not configured")
        async def _embed():
            out = []
            for d in docs:
                emb = await Util().embedding(d)
                if emb is None:
                    raise RuntimeError("Embedding failed")
                out.append(emb)
            return out
        return asyncio.run(_embed())
```

Then pass this encoder into `SemanticRouter(encoder=HomeClawEmbeddingEncoder(...), routes=routes)`. No second embedding model; same vector space as the rest of HomeClaw.

**Summary:** Use **Option C** so Layer 2 (semantic router) uses your **existing** embedding model directly. Option A or B is possible if you prefer to avoid a custom class and are willing to handle truncation or subclass LiteLLMEncoder.

#### Local and cloud integration

- **Local encoder / LLM:** aurelio-labs provides **LlamaCppLLM** (e.g. `semantic_router.llms.llamacpp`) so you can load a `.gguf` model for **classification/dynamic routes**; for **embeddings** use the custom encoder above (our existing embedding server) or OpenAIEncoder with our base_url.  
- **Cloud:** The library is OpenAI-protocol friendly; you can use **OpenAIEncoder** or a thin wrapper around **litellm.completion()** for cloud-based encoding if needed.  
- **Install:** `pip install -U "semantic-router[local]"` (or `semantic-router`); use the **existing-embedding encoder** (Option C) when initialising the router so the router shares the same model as skills/plugins/RAG.  
- **Persistence:** `router.save("config.json")` and `router.load("config.json")` allow saving/loading routes so users can add or edit routing rules (e.g. from a desktop UI) without code changes.

### 4.8 Routing input: user-only vs context (and tools/plugins)

The system injects **memory**, **tool descriptions**, and **plugin descriptions** into the prompt as context so the LLM can select the right tools/plugins. Should routing use **only user input**, or the full context?

**Recommendation (Gemini):** Base routing **primarily on user input**. Do **not** feed the full injected context (memory + tools + plugins) into the router.

- **Why not full context?** Routing on everything makes the router slow and can cause **instruction conflict** (e.g. tool descriptions dominate and distort the intent signal).
- **Router’s job:** Decide **“which path”** (local vs cloud, or which skill cluster), not **“which tool”**. Tool/plugin selection happens **after** routing, inside the chosen agent.

#### Intent-aware routing (意图增强型路由)

Use a **two-phase** approach instead of changing the router’s input to “full context”:

| Phase | Input | Purpose |
|-------|--------|---------|
| **1. Raw intent (user input only)** | Only the **user message** | Fast classification (e.g. “check weather” vs “write code”). Keeps routing fast and stable. |
| **2. Contextual refinement (only when uncertain)** | If Phase 1 score is **below threshold**, add a **small** amount of context (e.g. last 3 turns of **chat history / memory**). | Reduces wrong routing when the user message is ambiguous. |
| **Do not inject** | **Tool or plugin descriptions** | These belong **after** routing. The router only picks “which agent/cluster”; the chosen agent then receives the **relevant** tool/plugin set. |

So: **routing logic is based on user input** (and optionally minimal context when Phase 1 is uncertain). Full memory/tools/plugins are **not** part of the router input.

#### Tools/plugins as “routing target”, not router input

- **Semantic router** should map the user to a **skill cluster** (e.g. `desktop_agent`, `cloud_creative`), not to a specific tool.
- **After** routing to e.g. `desktop_agent`, the **desktop agent** gets only the **desktop-related** plugin descriptions and tools. The router never sees all plugins.
- **Benefits:** Fewer tokens and less latency in the router; no “menu” in the router — the router only picks “which shop”, and the shop has the menu.

### 4.9 Cascading system demo (Gemini)

Condensed Python sketch using aurelio-labs and the above rules: **user input only** for heuristics and semantic; optional short `chat_history` only in Step 3 if needed.

**Config (e.g. `config.py`):** Heuristic rules as regex sets; keep rules in `.json`/`.yaml` so new plugins can add keywords without code changes.

```python
import re

HEURISTIC_RULES = {
    "LOCAL_SYSTEM": {
        "patterns": [
            r"(?i)\b(截图|screenshot|屏幕)\b",
            r"(?i)\b(静音|mute|音量|volume)\b",
            r"(?i)\b(关机|shutdown|重启|reboot)\b"
        ],
        "threshold": 1.0
    },
    "PRIVATE_DATA": {
        "patterns": [
            r"(?i)\b(密码|password|token|api[ _]key|secret)\b",
            r"(?i)\b(localhost|127\.0\.0\.1)\b"
        ],
        "threshold": 1.0
    }
}

def is_too_long(text, limit=4000):
    return len(text) > limit
```

**Router (e.g. `router_engine.py`):** Length → heuristics (user input only) → semantic router (user input only) → if scores below threshold, optional classifier (can use `chat_history[-100:]`) → default fallback.

```python
from semantic_router import Route, SemanticRouter
from semantic_router.encoders import HuggingFaceEncoder

class GPT4PeopleRouter:
    def __init__(self):
        self.encoder = HuggingFaceEncoder(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.routes = [
            Route(name="desktop_agent", utterances=[
                "open the chrome browser", "打开浏览器帮我搜一下",
                "find the word document on my desktop", "帮我查一下电脑里的文件"
            ]),
            Route(name="cloud_creative", utterances=[
                "write a long story about space", "帮我写一首关于未来的诗",
                "plan a 5-day trip to Tokyo", "制定一个旅行计划"
            ])
        ]
        self.router = SemanticRouter(encoder=self.encoder, routes=self.routes)

    def get_decision(self, user_input, chat_history=""):
        if is_too_long(user_input):
            return "CLOUD", "Input too long, using cloud."
        for category, rule in HEURISTIC_RULES.items():
            if any(re.search(p, user_input) for p in rule["patterns"]):
                return "LOCAL", f"Matched heuristic: {category}"
        guide = self.router(user_input)   # user_input only
        if guide.name == "desktop_agent" and guide.score > 0.82:
            return "LOCAL", f"Route to Desktop Agent (Score: {guide.score})"
        if guide.name == "cloud_creative" and guide.score > 0.85:
            return "CLOUD", f"Route to Cloud (Score: {guide.score})"
        # Step 3: optional classifier using chat_history[-100:] if needed
        return "LOCAL", "Default fallback to Local for privacy."
```

**Takeaways:** Isolate **routing** from **tool-calling**: router decides “which shop”, not “what’s on the menu”. Use a **multilingual** encoder and define utterances in one language (or mix); no need to manually translate keywords. Put **HEURISTIC_RULES** in a file (e.g. `.json`/`.yaml`) so new plugins can add patterns without retraining or restarting.

#### Final recommendations (Gemini — 给你的最终建议)

1. **隔离「路由」与「工具调用」** — **Isolate routing from tool-calling.** The router only decides "which shop" (去哪家店); it does not need to know "what's on the menu" (店里有哪些菜单). Tool/plugin descriptions are for the chosen agent after routing.
2. **多语言处理** — **Multilingual:** Do not manually translate keywords. With a **multilingual HuggingFaceEncoder**, define **utterances** in one language (e.g. English); it will understand Chinese automatically.
3. **动态性** — **Dynamicity:** Put **HEURISTIC_RULES** in a **`.json` or `.yaml`** file. When you add a new browser plugin (浏览器插件), add a keyword in that file; the system recognizes it **without retraining or restarting**.

### 4.10 Multi-language handling for Phase 1 (原始意图识别)

For systems that run across languages (e.g. Chinese, English, and more), **Phase 1 (raw intent)** does not require separate rule sets per language. Core idea (Gemini): **“规则层靠正则，语义层靠多语言共享空间”** — rules layer uses regex/config; semantic layer uses a **shared multilingual vector space**.

#### Phase 1 — Heuristic layer: multi-language strategy

- **Do not hardcode** per-language branches (e.g. `if "截图" in input or "screenshot" in input` in code).
- **Alias mapping table:** In a **config file (YAML/JSON)**, group all synonyms for the same intent in one place. Example: one entry for “screenshot” intent with keywords `[截图, screenshot, capture, 屏幕]`.
- **Normalization:** Before matching, **lowercase** the input and apply **Unicode normalization** (e.g. NFC) so that special characters (e.g. in German, French) do not break matches. Then run regex/keyword checks against this normalized string.

#### Phase 2 — Semantic layer: multilingual semantic space

You do **not** need separate utterance sets for Chinese and English.

- **Principle:** A **multilingual embedding model** (e.g. `paraphrase-multilingual-MiniLM-L12-v2`) maps “same meaning” in different languages to the **same** (or very close) vector. So you can define **only English** utterances in each `Route`; user input in Chinese (e.g. “帮我截个图”) will sit close in vector space to “take a screenshot” and match.
- **Practice:** Define routes with English utterances; the encoder handles Chinese (and other languages) automatically. If some Chinese phrases are missed, add **one or two Chinese example utterances** to that route; a small “mixed” set is enough for very reliable routing.
- **Robustness:** Semantic matching is fuzzy (vector distance), so typos (e.g. “截个土”) can still match the “screenshot” intent.

#### Python sketch: one pass for multi-language routing

```python
import re
from semantic_router import Route, SemanticRouter
from semantic_router.encoders import HuggingFaceEncoder

class MultilingualRouter:
    def __init__(self):
        self.encoder = HuggingFaceEncoder(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        # English utterances only; Chinese input still matches (shared vector space)
        self.routes = [
            Route(name="browser_control", utterances=[
                "open the browser", "search on google", "open a new tab"
            ]),
            Route(name="file_management", utterances=[
                "find my document", "read the local pdf", "where is my file"
            ])
        ]
        self.router = SemanticRouter(encoder=self.encoder, routes=self.routes)

    def heuristic_check(self, text: str):
        # Load patterns from YAML/JSON (alias mapping); normalize before match
        text_normalized = text.lower().strip()   # + Unicode normalize in production
        patterns = {
            "LOCAL": [r"截图", r"screenshot", r"capture", r"屏幕"],
            "PRIVATE": [r"密码", r"password", r"secret", r"api_key"]
        }
        for target, keywords in patterns.items():
            if any(re.search(k, text_normalized) for k in keywords):
                return target
        return None

    def get_route(self, user_input: str):
        fast_choice = self.heuristic_check(user_input)
        if fast_choice:
            return fast_choice, "Heuristic match"
        decision = self.router(user_input)   # Chinese input matches English utterances
        if decision.name and decision.score > 0.8:
            return decision.name, f"Semantic match (Score: {decision.score})"
        return "CLOUD", "Low confidence, fallback to cloud"
```

**Why this fits Phase 1 well:** One set of (mainly) English utterances gives global coverage; heuristic rules stay in config (alias table + normalization); MiniLM is light and fast (~20 ms on desktop). Optional: maintain a **bilingual system-control keyword list** in config for heuristic rules so new plugins only add entries there.

### 4.11 The 3-layer routing pipeline: blueprint (Air Traffic Controller)

To build a professional-grade assistant, treat the **router as the "Air Traffic Controller"**: it decides **where the data goes before the data gets heavy**.

**Golden rule:** All three layers operate **only** on **User Input** (and occasionally a tiny slice of history). **Do not** feed tool/plugin descriptions into the router. The router selects **which** descriptions to load **after** routing.

| Layer | When it fires | What it sees | Data dependencies | How it works | Result |
|-------|----------------|--------------|-------------------|--------------|--------|
| **1. Heuristic Filter** (“Hard” gate) | **0–1 ms** after user hits Send | **Pure User Input** (normalized/lowercased) | Local **JSON/YAML** of regex patterns and keywords | Checks **Power Commands** (e.g. “Volume up”, “Screenshot”, “Shutdown”) and **Privacy Triggers** (e.g. “API Key”, “Password”). | If match → **short-circuit**: bypass AI and go straight to a local Python function. **Why:** No LLM needed to know “Mute my PC” means “Mute my PC.” |
| **2. Semantic Router** (“Intent” gate) | **5–20 ms** after Layer 1 finds no match | **Pure User Input** + **last 1–2 turns** of Chat History (to resolve “Do it again”) | **Vector index** of example utterances (e.g. 50 ways to ask for file help, 50 for creative writing) | Encodes input with Multilingual Encoder; computes distance to predefined **Intent Clusters**. | If score &gt; threshold (e.g. 0.82) → assign **Route Label** (e.g. `DESKTOP_FILE_MANAGEMENT`). **Crucial:** This layer does **not** see plugin code; it only knows the intent matches the “File” category. |
| **3. Local Classifier** (“Reasoning” gate) | **100–300 ms** after Layer 2 score is too low (ambiguous intent) | **User Input** + **Summarized Chat History** + a **list of “Skill Names” only** (no full documentation) | Tiny local model (e.g. Qwen-0.5B or FastText) | Acts as a **Judge**. Tiny prompt: “Does this request require real-time internet or complex logic? Answer ‘Cloud’ or ‘Local’.” | **Final decision**: stay on llama.cpp (local) or move to litellm (cloud). |

**Summary:** Layer 1 = hard rules, no AI; Layer 2 = intent clusters, no tool docs; Layer 3 = minimal context + skill names only, then local vs cloud. Tool/plugin **descriptions** are loaded only **after** the router has chosen the route/skill cluster.

### 4.12 After-Router phase: context injection and data visibility

**After the router** is where **tools, skills, and memories** are finally injected. The router has already decided *where* the request goes; only then do we attach the right context.

#### Context injection by route decision

| If router decides… | Action taken | Data injected |
|--------------------|--------------|----------------|
| **LOCAL** | Load llama.cpp | Only the **tool/plugin descriptions relevant to the identified intent**. Plus **local RAG memories** (relevant snippets). |
| **CLOUD** | Load litellm | Only **high-level reasoning tools**. User input is **scrubbed of PII** (Privacy Filter) before sending. |
| **MIXED** (parallel/agentic) | Plan to Cloud, execution local | System sends the **plan** to Cloud; **Tool Descriptions stay local**. Cloud only sees the **API Schema**, never the raw data. |

#### Data visibility summary

| Layer | User input | History | Tool/plugin specs | Memory |
|-------|------------|---------|-------------------|--------|
| **1. Heuristic** | Yes | No | No | No |
| **2. Semantic** | Yes | Very short (1–2 turns) | No | No |
| **3. Classifier** | Yes | Summary | Names only | No |
| **Post-Router** | Yes (full) | Full, relevant | **Full detailed specs** (for chosen route) | **Relevant RAG snippets** |

So: routing layers see **minimal** data; **full** tool specs and relevant memory are injected **only after** the route is chosen.

#### Why this design avoids “bad things”

- **Speed:** By keeping tools and memories **out of** the routing layers, decision-making stays **under 300 ms**.
- **Privacy:** By routing **before** memory injection, “Local” memories are never accidentally bundled into a “Cloud” request.
- **Cost:** You never send a 2000-word “Plugin Documentation” to GPT-4 if the router already decided the task is a simple local file-move.

### 4.13 Routing metrics, logging, and reporting

To support **cost calculation**, **tuning**, and **evaluating whether most routings are correct**, the router should produce **detailed logs** and optional **aggregated metrics** and **reports**.

#### Per-request log (detail logs)

For each request when `main_llm_mode == "mix"`, log at least:

| Field | Description |
|-------|-------------|
| **timestamp** | When the routing decision was made. |
| **route** | Final decision: **`local`** or **`cloud`**. |
| **layer** | Which step produced the decision: **`heuristic`**, **`semantic`**, **`classifier`**, or **`default_route`** (fallback when all steps skipped or none passed). |
| **score** | (Optional) Score from the winning step (e.g. heuristic 1.0, semantic 0.85, classifier confidence). |
| **reason** | (Optional) Short reason (e.g. "Matched heuristic: PRIVATE_DATA", "Semantic match (local)", "Classifier: cloud"). |
| **request_id / session_id** | (Optional) For correlating with LLM or user feedback. |
| **latency_ms** | (Optional) Routing pipeline latency (e.g. 2 ms for heuristic, 15 ms for semantic). |

This answers "which was routed to local, which to cloud" and "which layer decided" for every request.

#### Aggregated counts (for cost and reports)

Maintain or compute from logs:

- **Total requests** (in mix mode) in the period.
- **Routed to local** count.
- **Routed to cloud** count — used directly for **cost calculation** (e.g. cloud_count × avg cost per request, or sum of tokens if logged).
- **By layer:** count decided by heuristic, by semantic, by classifier, by default_route (helps tune thresholds and see where traffic goes).

Optionally: **tokens** (input + output) per cloud request so cost = sum(tokens) × unit price.

#### Report generation

- **Periodic report** (e.g. daily or weekly): breakdown by **route** (local vs cloud), by **layer**, and **cloud count** (and optionally cloud tokens) for cost; optionally by session or user.
- **Export:** Same data as CSV or JSON (e.g. for dashboards, spreadsheets, or billing). Can be generated on demand (e.g. "last 7 days") or via a small script that reads logs / DB.

#### Assessing whether routings are correct

- **Logs + manual review:** Export (user input snippet, route, layer, timestamp) for a sample; humans label "should have been local/cloud" and compute accuracy. Useful for tuning thresholds and intent examples.
- **Optional feedback API:** If the UI allows "this should have been cloud" / "this should have been local", store (request_id, route_taken, user_correction) and later compute correction rate and use for tuning.
- **A/B or shadow mode:** Log "router said X" while actually using a fixed route (e.g. always cloud) and compare outcomes (e.g. user satisfaction); or run router in parallel and log without changing behaviour.

Implementation can start with **structured log lines** (e.g. JSON per request) and a **simple counter** (cloud_count, local_count) in memory or in a small DB; reports then aggregate from logs or from the counter store.


---

## 5. Phased plan

### 5.1 Implementation readiness: do we have enough design?

**Yes.** The design is sufficient to implement **mix mode** while **keeping current “only local” and “only cloud” behaviour unchanged**.

**Invariant to preserve**

- **`main_llm_mode: "local"`** — Same as today: single main LLM from config (local). No router; every request uses `main_llm` (or `main_llm_local` when we introduce it).
- **`main_llm_mode: "cloud"`** — Same as today: single main LLM from config (cloud). No router; every request uses `main_llm` (or `main_llm_cloud`).
- **`main_llm_mode: "mix"`** — New: **before** calling the main LLM, run the 3-layer router on **user input** (and optionally minimal history); get `"local"` or `"cloud"`; then use **main_llm_local** or **main_llm_cloud** for that request. Tool/plugin/memory injection stays **after** routing (§4.12).

**What the design already defines**

| Area | Covered in doc | Enough to implement? |
|------|----------------|------------------------|
| Config schema | §4.1, §4.6 (config sketch), §4.11 | Yes: `main_llm_mode`, `main_llm_local`, `main_llm_cloud`, `hybrid_router` (steps, thresholds, default_route). |
| Routing logic | §4.6 (cascade, flow, pseudo-code), §4.11 (when/what each layer sees) | Yes: heuristics → semantic → classifier; thresholds; default_route. |
| Router input | §4.8, §4.11 | Yes: user input only (+ 1–2 turns for semantic; summary + skill names for classifier). No tool/plugin docs in router. |
| After-router | §4.12 | Yes: inject only relevant tool specs + RAG per route; PII scrub for cloud; MIXED = plan to cloud, specs local. |
| Library choice | §4.7 | Yes: aurelio-labs/semantic-router for Layer 2; heuristic rules in YAML/JSON; optional classifier. |
| Multi-language | §4.10, §4.9 (final recommendations) | Yes: alias mapping + normalization for heuristics; multilingual encoder for semantic. |
| Integration point | (see below) | Single place: resolve “which main LLM for this request” then call existing completion path. |
| Metrics and reporting | §4.13 | Per-request log (route, layer, score, reason); aggregated counts (local/cloud for cost); report generation; options to assess correctness. |

**Where to plug into the codebase**

- **Config:** Add `main_llm_mode` (default `"local"` or `"cloud"` for backward compat), `main_llm_local`, `main_llm_cloud`, and `hybrid_router` to `config/core.yml` and to `CoreMetadata` in `base/base.py`. When mode is `local`/`cloud`, keep using existing `main_llm` as today (no new keys required for current behaviour).
- **Resolve main LLM per request:** Extend `Util().main_llm()` (or add `Util().main_llm_for_route(route: Optional[str])`) so that:
  - If `main_llm_mode != "mix"`: return current `main_llm` (unchanged).
  - If `main_llm_mode == "mix"`: `route` must be `"local"` or `"cloud"`; return the tuple for `main_llm_local` or `main_llm_cloud` (same shape as today’s `main_llm()`).
- **Call site:** In the path that builds the chat completion request (e.g. in `core/core.py` where the main LLM is resolved for a turn), add: **if** `main_llm_mode == "mix"`, **then** (1) run the router on the **user message** (and optionally last 1–2 turns), (2) get `route = "local" | "cloud"`, (3) call `Util().main_llm_for_route(route)` (or equivalent) and use that for the completion. Else use `Util().main_llm()` as today.
- **Startup:** When mode is `mix`, both local and cloud backends may need to be available (e.g. local server + litellm proxy). Today `llmManager.run_main_llm()` starts one; for mix you can either start both from `main_llm_local` and `main_llm_cloud` at startup, or start on first use; design doc leaves this to implementation.

**Minimal first slice**

1. Add config schema and `main_llm_mode` / `main_llm_local` / `main_llm_cloud` / `hybrid_router`; default mode so existing config stays “local” or “cloud” with no behaviour change.
2. Implement **Layer 1 (heuristics)** only: regex/keywords from YAML/JSON, return `local`/`cloud` or “no match”; when “no match”, use `default_route`. No semantic or classifier yet.
3. Wire the single call site: if mode is `mix`, run heuristic router → get route → resolve main LLM for that route → run existing completion. Then add Layer 2 (semantic), then optionally Layer 3 (classifier).
4. **Per-layer on/off:** Respect `enabled` / `threshold: 0` for each step so any combination (L1 only, L2 only, L3 only, L1+L2, L1+L3, L2+L3, or all three) works; when all steps are skipped or none pass, use `default_route`. Important for **testing** (e.g. test only L2 or only L3).
5. **Layer 3 (classifier):** Reuse the **current llama.cpp web server mechanism**: add a small model (e.g. Qwen3-0.5B) to `local_models` with its **own port** (e.g. 5089); start it the same way as main LLM when mode is mix and `slm.enabled`. Call its `/v1/chat/completions` with a short judge prompt and parse “Local”/“Cloud”.

This keeps the current only-local and only-cloud implementation intact and adds mix mode on top with a clear, documented integration point and full flexibility to turn off any layer.

| Phase | What | Notes |
|-------|------|--------|
| **1** | Design + config schema | Add `main_llm_mode`, `main_llm_local`, `main_llm_cloud`, router type, intent example paths. No code yet. |
| **2** | Heuristic router | Implement keyword/length rules; choose local vs cloud; call the chosen main LLM. |
| **3** | Intent examples + semantic router | Add intent example files; precompute or on-the-fly embed; route by similarity. Consider **aurelio-labs/semantic-router** (§4.7) for Layer 2. |
| **4** | (Optional) Confidence escalation | Try local first; if confidence low, retry with cloud; optional streaming switch. |
| **5** | (Optional) Layered processing | Local preprocessing/retrieval; send compressed context to cloud only when needed. |

---

## 6. Open questions

1. **Default when unclear**  
   Prefer “local” (cheap, private) or “cloud” (safer quality)? Configurable default_route is recommended.

2. **Per-user or per-channel override**  
   Allow “this user always use cloud” or “this channel is local-only”? Could be a later option in user/channel config.

3. **Metrics**  
   See §4.13: per-request log (route, layer, score, reason, latency), aggregated counts (local/cloud for cost), report generation, and options to assess routing correctness (manual review, feedback API, shadow mode).

4. **UI**  
   “Smart mode” switch in Companion app (or in core config only at first).

---

## 7. References

- Discussion with Gemini: intent-based routing, confidence-based escalation, layered processing, task delegation; semantic router recommended (&lt; 10 ms) using existing embedding. **Cascading Routing Filter System** (级联路由过滤系统): three-layer funnel, timing (Heuristics &lt;1 ms, Semantic 5–20 ms, Classifier 100–300 ms), config shape (`mode`, `steps.*.enabled/threshold`, `defaultFallback`), optional classifier threshold; suggestions: FastText/small MLP for classifier, reuse embedding for semantic, runHeuristics (String.match) and cosineSimilarity helpers. **Desktop assistant (decision-maker vs executor):** Heuristics layer — security/privacy keywords and system-control keywords → local, direct subprocess/pyautogui &lt;1 ms; long context (&gt;4096) → cloud; Semantic layer — vector index, local/cloud clusters, CosineSimilarity to centroid, threshold 0.85; Classifier — tiny model, JSON `{target, reason, confidence}`, optional Mix Mode; tool-use architecture — cloud plans, local executes (browser, file, app), local observer for sensitive data; tool division table (document/browser/app local, complex reasoning cloud); state machine, USE_CLOUD/mix default (tools local, thought by scoring), filter layer for token/privacy in cloud requests.
- HomeClaw today: `config/core.yml` (`main_llm`, `embedding_llm`, `local_models`, `cloud_models`), `core/core.py` (single main LLM per request), `Util().main_llm()` / `Util().embedding_llm()`.
- README roadmap: “Cloud and local model mix — routing and fallback rules”.
- **aurelio-labs/semantic-router:** [GitHub](https://github.com/aurelio-labs/semantic-router), [docs](https://docs.aurelio.ai/semantic-router). Python, Route + encoder, similarity score; local GGUF (LlamaCppLLM), OpenAI-compatible for cloud; `router.save`/`load` for persistence. vLLM semantic-router is cluster-oriented (Rust/Go), not for desktop. Gemini: pre_route_check heuristic, multilingual encoder (e.g. paraphrase-multilingual-MiniLM-L12-v2), score bands (&gt;0.82 use route, 0.5–0.82 → classifier, ≤0.5 → default). **Use existing embedding:** semantic-router does not ship an encoder for “your HTTP endpoint”; use **OpenAIEncoder** (base_url + api_key) with truncation caveat, **LiteLLMEncoder** (api_base via subclass), or **custom DenseEncoder** that calls `Util().embedding()` (recommended) so Layer 2 uses the same model as skills/plugins/RAG. **Routing input (Gemini):** Route on user input only; do not inject full memory/tools/plugins. Intent-aware: Phase 1 = user message; Phase 2 = if uncertain, add last N turns chat/memory only; tools/plugins as routing target (skill cluster); demo §4.9. **Multi-language Phase 1 (§4.10):** Rules layer = regex + alias mapping in YAML/JSON, normalize (lowercase + Unicode); semantic layer = multilingual encoder so English utterances match Chinese; optional 1–2 Chinese utterances per route; MiniLM ~20 ms; optional bilingual keyword list for heuristics. **Air Traffic Controller blueprint (§4.11):** Router decides where data goes before data gets heavy; all layers only on User Input (+ tiny history slice); no tool/plugin descriptions in router. Layer 1 (0–1 ms): pure input, JSON/YAML rules, power + privacy triggers → short-circuit to local Python. Layer 2 (5–20 ms): input + last 1–2 turns; vector index of utterances → route label; does not see plugin code. Layer 3 (100–300 ms): input + summarized history + skill names only → Judge prompt → local vs cloud. **After-Router (§4.12):** Context injection only after route: LOCAL → llama.cpp + relevant tool specs + local RAG; CLOUD → litellm + high-level tools + PII-scrubbed input; MIXED → plan to cloud, tool descriptions local, cloud sees API schema only. Data visibility table (routing layers see minimal data; full specs + RAG only post-router). Rationale: speed (&lt;300 ms), privacy (no local memory in cloud request), cost (no huge plugin docs to cloud when local suffices).
