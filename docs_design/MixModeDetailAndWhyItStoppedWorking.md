# Mix mode in detail — and why it can stop working

This doc explains **how mix mode works** (routing, which server is used for “local” vs “cloud”) and **why it may have worked before but fails now**.

---

## 1. What mix mode is

With `main_llm_mode: mix` in `config/llm.yml` you have **two** models:

- **main_llm_local** — e.g. `local_models/Qwen3.5-9B-Q5_K_M`
- **main_llm_cloud** — e.g. `cloud_models/DeepSeek-Chat`

For **each user request**, the hybrid router picks **one** of them:

1. **Route choice** (local or cloud) is made by heuristic → semantic → long-query rule → SLM (perplexity/classifier) → default_route. See `MixModeWhyAlwaysLocal.md`.
2. **One LLM call** is made to the chosen model. If that call **fails** (HTTP 500, connection refused, timeout, empty response), and `hybrid_router.fallback_on_llm_error` is true, Core **retries once** with the **other** model.

So “mix” = **per-request routing** (local or cloud) + **optional fallback** to the other model when the first fails.

---

## 2. Where does each model actually run? (Host and port)

### Local model (main_llm_local)

- Comes from **local_models** (e.g. `local_models/Qwen3.5-9B-Q5_K_M`).
- Core uses **main_llm_host** and **main_llm_port** (e.g. `127.0.0.1:5023`).
- So “local” = your **llama.cpp** (or similar) server on that host:port.

### Cloud model (main_llm_cloud) — LiteLLM → remote API

- Comes from **cloud_models** (e.g. `cloud_models/DeepSeek-Chat`). In code, cloud_models use **LiteLLM** to call the **remote** cloud API (DeepSeek, OpenAI, etc.).
- Core does **not** call the cloud provider directly. It sends the request to the **LiteLLM proxy** at the cloud_models entry’s **host** and **port** (e.g. `127.0.0.1:14005`). The **proxy** then forwards to the real cloud API using the entry’s `path` (e.g. `deepseek/deepseek-chat`) and `api_key`.
- So **cloud** = **LiteLLM proxy** (on the configured host:port) → **remote** cloud. It is not “just a label”; the cloud model really uses LiteLLM to talk to the remote service. When the proxy is running, mix/fallback to cloud works; when nothing is listening on that port, you get “connection refused”.

**Typical config:**

```yaml
# llm.yml
main_llm_mode: mix
main_llm_local: local_models/Qwen3.5-9B-Q5_K_M
main_llm_cloud: cloud_models/DeepSeek-Chat

main_llm_host: 127.0.0.1
main_llm_port: 5023

cloud_models:
  - id: DeepSeek-Chat
    path: deepseek/deepseek-chat
    host: 127.0.0.1
    port: 14005
    api_key: ...
```

- **Local** → `127.0.0.1:5023` (llama.cpp).
- **Cloud** → `127.0.0.1:14005` = **LiteLLM proxy**; the proxy calls the remote DeepSeek (or other) API.

So: **cloud** = LiteLLM proxy on 14005 → remote cloud. When the proxy is up, cloud works; when it’s down, fallback to cloud fails with connection refused.

---

## 3. Why mix mode “worked well before”

It works when **all** of the following are true:

1. **Routing** chooses local or cloud per request (heuristic, semantic, etc.).
2. **Local model (5023)** answers successfully when chosen — no HTTP 500, no timeout, no empty response.
3. **When cloud is chosen or fallback runs**, the **LiteLLM proxy** is running on the cloud model’s host:port (e.g. 127.0.0.1:14005), so Core can reach it and the proxy can call the remote API.

So mix “worked well before” because: the **LiteLLM proxy** (14005) was **running**. Then when you routed to cloud or fell back to cloud, Core → proxy → remote API worked. It stopped working when the proxy on 14005 is no longer running (or not reachable).

---

## 4. Why it doesn’t work now (two separate issues)

### Issue 1: Local returns HTTP 500 (“Failed to parse input at pos 665: &lt;tool_call&gt;...”)

- **What happens:** The request is sent to **local** (5023). The server returns **HTTP 500** and a message like “Failed to parse input at pos 665: &lt;tool_call&gt;...”.
- **Cause:** The **request body** we send includes **message content** that contains raw `<tool_call>...</tool_call>` (e.g. from a previous assistant turn). The local server (with tool grammar / GBNF) tries to parse the whole input and **fails** when it hits that text inside a message.
- **Why “before” it might have worked:** Earlier, either:
  - Conversations were **short**, so no previous turn had that raw `<tool_call>` in content, or
  - The **server or model** was different and didn’t use such strict parsing.
- **Fix (already in code):** We now **sanitize** message content before sending to local/ollama when tools are present: any `<tool_call>...</tool_call>` in content is replaced with `[tool call]`, so the server no longer sees that string and doesn’t fail at that position.

### Issue 2: Cloud unreachable (connection refused to 127.0.0.1:14005)

- **What happens:** Local failed (e.g. 500 above) → Core tries **fallback** to **cloud** → request goes to **127.0.0.1:14005** (the LiteLLM proxy) → “The remote computer refused the network connection”.
- **Cause:** The **cloud** model uses **LiteLLM** to call the remote API; Core talks to the **proxy** at the entry’s host:port (14005). Nothing is listening on 14005, so the connection is refused — the **LiteLLM proxy is not running**.
- **Why it worked before:** The LiteLLM proxy was running on 14005, so Core → proxy → remote cloud worked. When the proxy is stopped or not started, fallback to cloud fails.

---

## 5. What to do so mix works again

### Option A: Fix local so fallback is rarely needed

- Keep the **sanitization** of `<tool_call>` in message content (already done). That should prevent the HTTP 500 on 5023 when history contains raw tool-call text.
- Then most requests will be answered by **local** and you won’t depend on 14005.

### Option B: Start the LiteLLM proxy again (recommended)

- Your cloud model **already** uses LiteLLM to call the remote API. Core sends requests to the proxy at the cloud_models entry’s host:port (e.g. 127.0.0.1:14005).
- **Start the LiteLLM proxy** so it listens on **14005** (e.g. `litellm --port 14005` or however you normally run it). Once the proxy is up, fallback to cloud (and direct routing to cloud) will work again: Core → proxy → remote API.

### Option C: Disable fallback

- In `llm.yml`: `hybrid_router.fallback_on_llm_error: false`.
- Then when local fails (500, timeout, etc.), Core **won’t** retry with cloud. You’ll get a single model and no fallback; mix still chooses local vs cloud per request, but no second attempt on failure.

---

## 6. Short summary

| Question | Answer |
|----------|--------|
| How does mix work? | Router picks local or cloud per request; one LLM call to that model; on failure, optional retry with the other model. |
| Where does “local” run? | main_llm_host:main_llm_port (e.g. 127.0.0.1:5023). |
| Where does “cloud” run? | **LiteLLM proxy** at the cloud_models entry’s host:port (e.g. 127.0.0.1:14005); the proxy calls the **remote** cloud API (DeepSeek, etc.). So cloud = LiteLLM → remote. |
| Why did it work before? | Local was stable and/or the **LiteLLM proxy** (14005) was **running**, so cloud and fallback worked. |
| Why doesn’t it work now? | (1) Local fails with 500 when request contains raw `<tool_call>` in history — fixed by sanitization. (2) **LiteLLM proxy** on 14005 is not running, so fallback to cloud gets connection refused. |
| How to fix? | Keep sanitization; **start the LiteLLM proxy** on 14005 so cloud/fallback work again, or disable fallback. |

See also: `MixModeWhyAlwaysLocal.md`, `MixFallbackBehavior.md`, and routing in `core/llm_loop.py`.
