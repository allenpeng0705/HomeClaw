# Plugin LLM Access and Request Handling

This document describes how plugins (built-in and external) use Core’s LLM features (e.g. `generateText`, post_process, file understanding), how Core’s request queue works, and how plugin-originated LLM calls are handled.

## 1. Current behaviour

### 1.1 Post-process (LLM on plugin output)

- **Where:** `tools/builtin.py` → `_route_to_plugin_executor`, and capability params in `base/base.py` (`PluginCapabilityParam.post_process`, `post_process_prompt`).
- **Logic:** After the plugin returns `result_text`, if the capability has `post_process: true` and a `post_process_prompt`, Core runs **one** LLM call:
  - **System:** `post_process_prompt` (no extra instructions).
  - **User:** the plugin’s raw output only.
- **Outbound:** The refined text is sent with `core.send_response_to_request_channel(result_text, request)`, which applies **markdown outbound** via `_format_outbound_text` (config: `outbound_markdown_format`). No extra text is added around the refined output.
- **Scope:** Same behaviour for built-in and external plugins when invoked via `route_to_plugin`; only the prompt and plugin output are used, and the result is formatted for the channel.

### 1.2 Built-in and external plugins: same REST API

- **Unified API:** Both built-in and external plugins use the **same** REST API for LLM calls: `POST /api/plugins/llm/generate`.
- **Built-in:** Use the helper `await Util().plugin_llm_generate(messages, llm_name=None)`. It POSTs to Core’s own `/api/plugins/llm/generate` (same contract as external). No need to call `coreInst.openai_chat_completion` from plugins.
- **External:** POST to Core’s `POST /api/plugins/llm/generate` with body `{ "messages": [...], "llm_name": null }`; get `{ "text": "..." }` in the response.
- **Sending the reply:** Built-in plugins still use `await self.coreInst.send_response_to_request_channel(response, self.promptRequest)` to send the final reply (Core applies markdown outbound). External plugins return text in `PluginResult`; Core sends it (and may post_process with LLM).

### 1.3 Concurrency: channel queue vs plugin API

- **Issue:** The channel request queue processes one message at a time, but the plugin LLM API is a normal HTTP endpoint. So we can have: (1) a channel request being processed (calling the LLM), and (2) a plugin (external or built-in via helper) calling the API at the same time → two concurrent LLM calls.
- **Control:** Core limits concurrent LLM calls with **two semaphores** (local vs cloud). Config in `core.yml`: **`llm_max_concurrent_local`** (default **1**), **`llm_max_concurrent_cloud`** (default **4**). All LLM use goes through `Util().openai_chat_completion` or `openai_chat_completion_message`; each call acquires the semaphore for the resolved backend (local/llama.cpp or cloud/LiteLLM). So local stays at 1 (single GPU/process); cloud can run several in parallel (channel + plugin API).
- **Tuning:** Set `llm_max_concurrent_cloud: 2`–`10` for more parallel cloud calls; keep `llm_max_concurrent_local: 1` for single local GPU/process.

### 1.4 Channel request queue (multi-channel)

- **Flow:** Channels push requests into `request_queue`. A **single** asyncio task `process_request_queue()` consumes them **one at a time**. So multiple channels are serialized: Channel A → request in queue → processed → response out; then Channel B → request in queue → processed → response out.
- **Response:** After processing, Core puts an `AsyncResponse` on `response_queue`. Another task `process_response_queue()` sends it to the channel’s `host:port/get_response` (except sync inbound, where the HTTP/WS handler already returned the response).
- **Concurrency:** Only one channel request is processed at a time. No extra queue or special handling is required for “multiple channels sending at once”; the single queue provides ordering and avoids overlapping processing of channel requests.

### 1.5 Plugin-originated LLM requests

- **Built-in:** Plugin calls `await Util().plugin_llm_generate(messages, llm_name=None)`, which POSTs to Core’s `/api/plugins/llm/generate`. Same API contract as external; result returned from the helper.
- **External:** Plugin sends HTTP `POST /api/plugins/llm/generate` to Core. Core runs LLM, returns JSON. **Synchronous** from the plugin’s perspective (request in → response back). Core does **not** put these on the channel `request_queue`; they are normal HTTP requests. The **semaphores** (`llm_max_concurrent_local` / `llm_max_concurrent_cloud`) ensure channel work and plugin API don’t overload the LLM backend when they happen concurrently.

## 2. Core APIs for plugins

### 2.1 Same REST API for both plugin types

- **POST /api/plugins/llm/generate** — single entry point for LLM generation.
  - **Body:** `{ "messages": [ {"role": "user"|"assistant"|"system", "content": "..."}, ... ], "llm_name": null | "optional_model_key" }`
  - **Response:** `{ "text": "..." }` or `{ "error": "..." }` on failure.
  - **Auth:** When `auth_enabled` and `auth_api_key` are set: `X-API-Key` or `Authorization: Bearer <key>` (same as `/inbound`).
- **Built-in plugins:** Call `await Util().plugin_llm_generate(messages, llm_name=None)` instead of `coreInst.openai_chat_completion`. The helper POSTs to this API (Core’s own URL from config) and returns the text.
- **External plugins:** POST to Core’s base URL + `/api/plugins/llm/generate`; read `text` from the response.
- **Sending the reply (built-in only):** `coreInst.send_response_to_request_channel(response, request)` — applies markdown outbound and enqueues to the channel.

File understanding (multimodal documents) is currently applied inside Core for **channel** requests (e.g. `/inbound` with `files`). Exposing a dedicated “understand file” API for plugins can be added later if needed; plugins can already use `generate` with messages that include content produced elsewhere.

## 3. Concurrency (llm_max_concurrent_local, llm_max_concurrent_cloud)

- **Config:** `core.yml` → **`llm_max_concurrent_local`** (default **1**), **`llm_max_concurrent_cloud`** (default **4**). Separate limits for local (llama.cpp) and cloud (LiteLLM).
- **Mechanism:** `Util().openai_chat_completion` and `openai_chat_completion_message` acquire an asyncio semaphore for the resolved backend (local or cloud) before calling the LLM backend. The REST handler for `/api/plugins/llm/generate` calls Core’s `openai_chat_completion`, so it uses the same semaphores. So queue work and plugin API requests are serialized (when default 1) and don’t overload the backend.
- **Recommendation — local model:** Use **1** (default). Keeps at most one request in flight to your local server (e.g. one GPU) and avoids overloading the process.
- **Recommendation — cloud model:** May use **2–10** (or per-provider limit) so channel and plugin API can run in parallel. Stay under provider rate limits (RPM/TPM) and cost; adjust per provider.
- **Tuning:** Set `llm_max_concurrent_cloud: 2` or more for parallel cloud calls; keep `llm_max_concurrent_local: 1` unless you run multiple local workers.

### 3.1 Logic in detail

The two flags limit concurrency **by backend type** (local vs cloud), not by “role” (main vs embedding vs classifier).

**Step-by-step (chat completion path):**

1. Caller invokes `Util().openai_chat_completion(messages, llm_name=...)` or `openai_chat_completion_message(...)`.
2. **Resolve backend:** Core resolves `llm_name` (or main_llm when omitted) via `_resolve_llm(llm_name)` or `main_llm()`. The result includes **mtype**: `'local'` (llama.cpp) or `'litellm'` (cloud).
3. **Acquire semaphore:** Core calls `_get_llm_semaphore(mtype)` and gets the **local** or **cloud** semaphore. It then does `async with sem:` so only `llm_max_concurrent_local` concurrent local calls and `llm_max_concurrent_cloud` concurrent cloud calls run at once.
4. **Call backend:** Inside the semaphore, Core sends the request to the resolved host:port (local server or LiteLLM proxy).

So **every call that goes through `openai_chat_completion` / `openai_chat_completion_message`** is counted against either the local or the cloud limit, depending only on whether the **resolved model** is local or cloud. Main chat, plugin generate, post_process, TAM/cron LLM, memory summarization, etc. all use this path and share the same two semaphores.

### 3.2 What is controlled: main, embedding, classifier, per-user

| Use | Goes through openai_chat_completion? | Controlled by the two flags? |
|-----|--------------------------------------|-------------------------------|
| **Main model (chat)** | Yes | Yes — resolved to local or cloud → uses that semaphore. |
| **Plugin generate / post_process** | Yes | Yes — same path. |
| **Classifier (routing SLM)** | No — direct HTTP to classifier host:port | **Yes** — acquires the **local** semaphore before the HTTP call (classifier is always local). |
| **Embedding model** | No — direct HTTP to embedding host:port | **Yes** — acquires the semaphore for the embedding backend type (local or cloud) before the HTTP call. |
| **Per-user different models (future)** | Yes, if invoked via openai_chat_completion with that user’s llm_name | Yes — each user’s model resolves to local or cloud, so they share the same two semaphores. |

**Summary:**

- The two flags control **all chat completion traffic** that goes through `Util().openai_chat_completion` or `openai_chat_completion_message`. That includes: main chat, plugin API generate, post_process, TAM/cron LLM, memory summarization, and any future per-user chat model invoked via that path.
- Control is **by backend type (local vs cloud)**, not by role. So if main_llm is local and a plugin calls with a cloud model, one request uses the local semaphore and another the cloud semaphore; they do not block each other.
- **Embedding** and **classifier** use **direct** HTTP to their host:port but **do** acquire the same two semaphores before calling: embedding uses the semaphore for its resolved backend type (local or cloud); classifier always uses the **local** semaphore. So `llm_max_concurrent_local` / `llm_max_concurrent_cloud` limit main chat, plugin chat, embedding, and classifier together. If you run main + embedding + classifier all on the same machine/GPU, total concurrent local work is bounded by `llm_max_concurrent_local` (e.g. 1).
- **Per-user different models:** If in the future different users use different models (e.g. user A → local_models/A, user B → cloud_models/B), each request still resolves to local or cloud and uses the corresponding semaphore. So the same two flags still apply: local concurrency and cloud concurrency are shared across all users and all roles that use the chat completion path.

## 4. Summary

| Caller              | How they use LLM                         | How result is returned                    |
|---------------------|------------------------------------------|--------------------------------------------|
| Channel (async)     | Core processes request from queue       | Response queue → channel `get_response`    |
| Built-in plugin     | `Util().plugin_llm_generate(messages)` (same API) | Return value; send via `send_response_to_request_channel` |
| External plugin     | `POST /api/plugins/llm/generate`        | HTTP response body `{ "text": "..." }`     |
| Post-process       | Core runs LLM on plugin output           | `send_response_to_request_channel` (with markdown) |

- **Same API:** Built-in and external plugins both use the same REST API; built-in via `Util().plugin_llm_generate()`.
- **Concurrency:** `llm_max_concurrent_local` (default 1) and `llm_max_concurrent_cloud` (default 4) limit concurrent LLM use so queue + plugin API don’t overload the backend.
- **Post-process:** Only the capability’s `post_process_prompt` and plugin output are used; markdown outbound is applied when sending to the channel.
- **Multi-channel:** One `request_queue` and one consumer; no extra handling for “multiple channels at once.”
