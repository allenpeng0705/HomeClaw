# Strong local model and perplexity-based Layer 3

This document captures design choices for when the **local model is powerful** (e.g. 30B or strong 8B): how to adjust the 3-layer router, and how to use **perplexity / confidence** (logprobs from the local model) in Layer 3 as an alternative to the small classifier. It also notes **Pinggy** and similar tunnels for the companion app.

---

## 1. When the local model is strong: mindset shift

- **Weak local:** Cloud is the “main” option; local is for simple, clear tasks. Thresholds are conservative (e.g. semantic local only when score > 0.85).
- **Strong local:** Local is the default; cloud is the “expensive add-on”. Goal: **offline-first**; only send to cloud when the task clearly needs it (real-time web, huge context, or model clearly unsure).

---

## 2. Adjusting the three layers for a strong local model

### Layer 1 (Heuristic)

- **Fewer cloud triggers:** Move phrases like “write code”, “translate”, “summarize” from cloud to local (or remove them from cloud rules). Keep cloud rules only for things that truly need the internet or very large context (e.g. “latest market trends”, “live news”, “search academic papers”).
- **More local triggers:** Broaden local keywords so more intents are caught early and stay local.
- **Order:** Keep “specific local” rules before “generic cloud” so local wins when both could match.

### Layer 2 (Semantic)

- **Lower local threshold:** e.g. from 0.85 to **0.65–0.75**. With a strong local model, slightly ambiguous queries can still be handled locally; only very low similarity should fall through to Layer 3 or cloud.
- **Utterances:** Ensure local_utterances cover “simple conversation”, file/code/translate-style tasks so they cluster to local in embedding space.

### Layer 3: two modes

- **Classifier (current):** Small local model (e.g. 0.5B) with a judge prompt: “Does this need real-time web / complex reasoning? Answer Local or Cloud.” Good when the main model is not used for routing.
- **Perplexity (confidence) probe:** Use the **main local model** (same one that will generate the reply). Send a **probe request** (e.g. first 5 tokens, with `logprobs=true`). Compute **average log probability** over those tokens:
  - **High confidence** (avg logprob above threshold, e.g. > -0.6): keep the request **local**.
  - **Low confidence** (avg logprob below threshold): **escalate to cloud**.

So Layer 3 becomes **configurable**: `mode: classifier` (small model judge) or `mode: perplexity` (main model confidence probe).

---

## 3. Perplexity-based Layer 3 in detail

### Idea

- The model’s **logprobs** tell you how “sure” it is about the next tokens.
- If the main model is already strong, we can **probe it** with a tiny generation (e.g. 5 tokens). If it’s confident (high logprob), it can handle the task; if it’s confused (low logprob), we send to cloud.
- This is **confidence-based routing**: the same model that might answer is used to decide local vs cloud.

### Flow

1. After Layer 1 and Layer 2, if no route is chosen, run **Layer 3**.
2. **If mode = perplexity:**
   - Call the **main local model** (llama.cpp server) with:
     - `messages = [user message]`
     - `max_tokens = 5` (or configurable)
     - `logprobs = true`
   - Parse the response: `choices[0].logprobs.content[]` → list of `{ "logprob": ... }`.
   - Compute **average logprob** over those tokens.
   - If **avg_logprob ≥ threshold** (e.g. -0.6): route = **local** (model is confident).
   - If **avg_logprob < threshold**: route = **cloud** (escalate).
3. **If mode = classifier:** Keep existing behavior: call the small classifier model with the judge prompt and parse “Local” / “Cloud”.

### Why it fits llama.cpp web server

- We use **llama-server** (OpenAI-compatible). It supports `logprobs` in the chat completions API.
- No need to parse binary stdout; a single HTTP POST with `max_tokens=5` and `logprobs=true` gives the token logprobs.
- Server is long-lived; the probe is a normal request. Optionally, the **full** reply can reuse the same context (e.g. KV cache) if the backend supports it and we use the same prompt again for the real generation.

### Config (conceptual)

```yaml
hybrid_router:
  slm:
    enabled: true
    mode: classifier   # or perplexity
    threshold: 0.5     # for classifier: min score to accept
    model: local_models/classifier_0_5b   # used when mode=classifier
    # When mode=perplexity we use main_llm_local for the probe:
    perplexity_max_tokens: 5
    perplexity_threshold: -0.6   # avg logprob above this → local
```

- **perplexity_threshold:** Higher (e.g. -0.4) = stricter “stay local” (only very confident). Lower (e.g. -0.8) = more requests stay local.
- **perplexity_max_tokens:** Number of tokens to generate for the probe (5 is a good default; more tokens = more signal but slower and more cost).

### Bad things to avoid

- **Don’t show probe output to the user.** The 5-token probe is for routing only; the user sees either the full local reply or the cloud reply, not a truncated “half sentence”.
- **Slot / concurrency:** If the server has limited slots, probe requests can queue. Prefer a short timeout (e.g. 2–5 s) and fall back to default_route (e.g. local) on timeout so the system doesn’t hang.
- **Tool use:** If the turn will involve tools, the probe only sees the user message. That’s acceptable: we’re measuring “does the model understand this kind of request?”. If tool-call format is a concern, we could later add a separate rule (e.g. always local for known tool intents) or a post-check.

---

## 4. Strong-model “cascade” (reference)

| Dimension        | Weak local                         | Strong local (e.g. 30B)                    |
|-----------------|-------------------------------------|--------------------------------------------|
| Code tasks      | Often cloud                         | Local; cloud only for very complex design  |
| Translation     | Cloud for “native” quality          | Local first                                |
| File / RAG       | Local extract, cloud rewrite        | Full pipeline local                        |
| Long context    | Send to cloud above ~2k tokens     | Only above 32k/128k (if local supports it) |
| Layer 3         | “Can local do it?”                  | “Is cloud worth the cost?” / confidence    |

These are tuning guidelines; actual thresholds and rules live in heuristic_rules.yml, semantic_routes, and hybrid_router config.

---

## 5. Keep model alive, cache, multi-model

- **Keep model alive:** With llama-server, the process is long-lived; no need to “start binary per request”. For Layer 3 perplexity, we reuse the same server as for the main local reply.
- **Cache:** For identical prompts, we could cache the routing decision (e.g. “this prompt → local”) to avoid repeated probes. Not implemented in the first version; can be added later.
- **Multi-model (8B vs 32B):** In the future, Layer 3 (or a separate selector) could choose **which** local model to use (e.g. 8B for simple, 32B for hard). That would require multiple local_models entries and a policy (e.g. by intent or by perplexity band). Design is out of scope here but the same perplexity idea can apply per model.

---

## 6. Pinggy tunnel (and similar)

- **What it is:** [Pinggy](https://pinggy.io/) provides **tunnels** (similar to ngrok or Cloudflare Tunnel): you run a client that forwards a **public HTTPS URL** to a **local port** (e.g. 5000 or the Core port). No need to open ports on your router or have a static IP.
- **Typical use:** Run Core (and optionally a proxy) on your desktop; start a Pinggy tunnel that maps `https://xxx.pinggy.link` → `localhost:9000`. The **companion app** on your phone then points to that URL to talk to your home Core.
- **vs Cloudflare Tunnel:** Same idea: expose a local service via a stable public URL and TLS. Cloudflare Tunnel uses `cloudflared` and Cloudflare’s network; Pinggy uses its own relay. Both avoid exposing your home IP and simplify mobile access.
- **For HomeClaw:** We don’t implement the tunnel inside the repo; we **document** that users can use Pinggy, Cloudflare Tunnel, or similar to expose Core (or a single FastAPI proxy in front of Core) so the companion app can reach it from outside the home network. A startup script that launches Core + tunnel (and prints the public URL) can be a convenience; implementation can live in scripts or a separate small tool.

---

## 7. Implementation status

- **Layer 3 mode = classifier:** Implemented (small model + judge prompt).
- **Layer 3 mode = perplexity:** Implemented: probe main local model with `max_tokens` + `logprobs`, compute avg logprob, compare to `perplexity_threshold`; route local or cloud accordingly. Config: `slm.mode`, `slm.perplexity_max_tokens`, `slm.perplexity_threshold`.
- **Pinggy / tunnel:** Documented only; no code in Core. Companion app docs can reference “expose Core via tunnel (e.g. Pinggy or Cloudflare Tunnel)” for remote access.
- **Cache / multi-model selection:** Not implemented; left for future work.

See [Mix mode and reports](../docs/mix-mode-and-reports.md) and `config/core.yml` (`hybrid_router.slm`) for current config and usage.
