# Code review: why LiteLLM (cloud) request can fail

This doc traces the code path for the **cloud** model (LiteLLM) and explains why you see "connection refused" when the LiteLLM proxy is not running. **Conclusion: the code correctly sends to the proxy’s host:port; the only cause of connection refused is that nothing is listening on that port.**

---

## 1. How cloud/LiteLLM is invoked

- **Entry point:** `openai_chat_completion_message(messages, tools=..., llm_name=llm_name)` in `base/util.py`.
- In mix fallback, `llm_name` is set to `main_llm_cloud` (e.g. `"cloud_models/DeepSeek-Chat"`).
- We do **not** use the `litellm` Python package in this path. We always send an **HTTP POST** to a URL built from **host** and **port**.

---

## 2. Resolution: where does host:port come from?

**`_resolve_llm(llm_name)`** (e.g. `llm_name = "cloud_models/DeepSeek-Chat"`):

1. **`_get_model_entry(name)`** → finds the **cloud_models** entry for DeepSeek-Chat; type is **`litellm`**.
2. **`main_ref = _effective_main_llm_ref()`**  
   In **mix** mode with **default_route: local**, this returns **`main_llm_local`** (e.g. `"local_models/Qwen3.5-9B-Q5_K_M"`), not the cloud ref.
3. **`use_main_port = (main_ref and name.strip() == main_ref)`**  
   So `use_main_port` is **False** when we’re resolving the cloud model (name is cloud, main_ref is local).
4. So we take **host** and **port** from the **cloud_models entry**:
   - `host = entry.get('host') or '127.0.0.1'`
   - `port = int(entry.get('port', 5088))`
   For your DeepSeek-Chat entry that’s **127.0.0.1** and **14005**.
5. Return: `(path_or_model, raw_id, 'litellm', host, port)` → port is **14005**.

So for fallback to cloud, we **do** use the proxy’s host:port from config (127.0.0.1:14005). We do **not** use `main_llm_host` / `main_llm_port` (5023) for the cloud model.

---

## 3. Building the request and sending it

**`_openai_chat_completion_message_impl`**:

1. `path_or_model, raw_id, mtype, model_host, model_port = resolved`  
   So `model_host = "127.0.0.1"`, `model_port = 14005`, `mtype = "litellm"`.
2. **`_llm_request_model_and_headers(...)`** for litellm:
   - Uses **path_or_model** (e.g. `deepseek/deepseek-chat`) as the **model** in the body.
   - Puts **api_key** from the cloud_models entry (or env) into **Authorization**.
3. **URL:**  
   `chat_completion_api_url = "http://" + model_host + ":" + str(model_port) + "/v1/chat/completions"`  
   → **`http://127.0.0.1:14005/v1/chat/completions`**
4. **Single code path for both local and cloud:**  
   `async with session.post(chat_completion_api_url, headers=headers, data=data_json) as resp: ...`

So there is **no** separate “call litellm library” path. Local and LiteLLM (cloud) both go through the same HTTP POST to **host:port**. For cloud, that host:port is the **LiteLLM proxy** (e.g. 127.0.0.1:14005).

---

## 4. Why “connection refused” happens

- The OS returns “connection refused” when **no process is listening** on the target address (here 127.0.0.1:14005).
- So:
  - Either the **LiteLLM proxy** that used to listen on 14005 is **not running** now, or
  - Something else (firewall, different machine, etc.) is blocking that port.

The code is **not** using the wrong port or wrong host: it uses the cloud_models entry’s **host** and **port** (14005). So from a **code** perspective there is no bug; the failure is that the **proxy is not listening** on 14005.

---

## 5. How to confirm in logs

- A **DEBUG** log was added:  
  `LLM request: mtype=litellm url=http://127.0.0.1:14005/v1/chat/completions model=deepseek/deepseek-chat`  
  So you can confirm that when fallback runs, we really call **14005** and **litellm** with the expected model.

---

## 6. Summary

| Step | What the code does |
|------|---------------------|
| Resolve cloud model | `_resolve_llm("cloud_models/DeepSeek-Chat")` → host/port from **cloud_models** entry (127.0.0.1, 14005), **not** main_llm_host/port. |
| Request | Same HTTP POST path for local and litellm; URL = `http://{host}:{port}/v1/chat/completions`. |
| LiteLLM | We do **not** call the `litellm` Python package; we assume a **proxy** is running on that host:port and we POST to it. |
| Connection refused | Only possible if **nothing is listening** on 127.0.0.1:14005 (proxy not running or not reachable). |

So: **LiteLLM “didn’t work” because the proxy on 14005 was not running (or not reachable).** The code path and host/port resolution are correct. Start the LiteLLM proxy on 14005 (e.g. `litellm --port 14005`) so that it listens and forwards to the remote cloud API.
