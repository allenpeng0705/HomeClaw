# LLM service and cloud server review

## Summary

- **Logic is correct.** The cloud model uses a LiteLLM proxy (FastAPI app) that **is** started by this code when conditions are met. Core does **not** expect a separate “web server” process started elsewhere; `LLMServiceManager.run()` starts both local (llama.cpp) and cloud (LiteLLM) servers when configured.
- **Cloud-only** and **mix** both use the same host/port for the LiteLLM proxy: `cloud_llm_host` and `cloud_llm_port` from config.

## Cloud-only mode (`main_llm_mode: cloud`)

1. **Config:** Set `main_llm_mode: cloud` and `main_llm_cloud: cloud_models/<id>`. Set `cloud_llm_host` / `cloud_llm_port` where the LiteLLM proxy should listen.
2. **Startup:** `run_main_llm()` runs. Because `mode != "mix"` (it's "cloud"), it uses `Util().main_llm()` (not `main_llm_for_route("local")`).
3. **Resolution:** `main_llm()` uses `_effective_main_llm_ref()` → for mode "cloud" that returns `main_llm_cloud`. The cloud entry is looked up; for type `litellm`, `main_llm()` returns `cloud_llm_host` and `cloud_llm_port`.
4. **Starting the server:** In `run_main_llm()`, `llm_type == 'litellm'` and the branch `if mode == "mix" and local_ref` is false, so we call **`run_litellm_service()`**. That calls `main_llm()` again (same host/port), then starts `_serve_litellm_on_host_port(host, port, model)` in a background thread. So the LiteLLM proxy is started on **`cloud_llm_host:cloud_llm_port`**.
5. **Requests:** All completion requests use `main_llm()` (or equivalent), which for cloud-only returns the same cloud ref and `cloud_llm_host` / `cloud_llm_port`, so traffic goes to the proxy we started.

**Conclusion:** Cloud-only logic is correct; the same `cloud_llm_*` settings are used to start and to call the LiteLLM proxy.

## When the cloud server is started (mix mode)

1. **Core startup** (e.g. `python -m core.entry` or `main.py start`) runs `Core.run()`.
2. Early in `Core.run()`, `self.llmManager.run()` is called (sync).
3. `LLMServiceManager.run()` runs in order:
   - `run_embedding_llm()`
   - `run_main_llm()` — in **mix** mode this starts only the **local** LLM (main_llm_for_route("local")).
   - `run_classifier_llm()` — mix-only classifier if enabled.
   - **`run_mix_mode_cloud_llm()`** — in **mix** mode this starts the **LiteLLM proxy** on `cloud_llm_host:cloud_llm_port` in a **background thread**.

So the “web server” for cloud **is** the LiteLLM FastAPI app started inside `run_mix_mode_cloud_llm()` via `_serve_litellm_on_host_port()`. It runs in a separate thread with its own event loop; Core’s HTTP server is separate (main process).

## Host/port used

- **Config:** `config/llm.yml` (or core merge) sets `cloud_llm_host` and `cloud_llm_port` (e.g. `127.0.0.1` and `14005`).
- **Starting the server:** In **mix** mode, `run_mix_mode_cloud_llm()` calls `Util().main_llm_for_route("cloud")`, which returns `cloud_llm_host` and `cloud_llm_port`. In **cloud-only** mode, `run_main_llm()` → `run_litellm_service()` uses `Util().main_llm()`, which for a cloud (litellm) ref also returns `cloud_llm_host` and `cloud_llm_port`. The LiteLLM app is bound to that host/port (with `127.0.0.1` → `0.0.0.0` so it can accept connections).
- **Sending requests:** `base/util.py` uses the same `cloud_llm_host` and `cloud_llm_port` for all litellm (cloud) requests in cloud-only and mix modes. So the server and clients use the same address.

## Why the cloud model might not run

1. **Mode or ref not set**
   - `main_llm_mode` ≠ `"mix"` → `run_mix_mode_cloud_llm()` returns immediately.
   - `main_llm_cloud` empty → we skip starting the cloud server (debug log).

2. **Cloud ref not litellm**
   - `main_llm_cloud` must point to a **cloud_models** entry whose **type** is **litellm**. If the entry is missing or has another type, we log a **warning** and do not start LiteLLM.

3. **Port in use or startup failure**
   - LiteLLM runs in a background thread. If uvicorn fails to bind (e.g. port 14005 in use) or any exception occurs in that thread, we now log it with **logger.error** in `_serve_litellm_on_host_port`. Check logs for:  
     `LiteLLM (...) failed to start or run on ...`.

4. **Cloud-only mode**
   - When `main_llm_mode: cloud`, `run_main_llm()` starts the LiteLLM server (same `_serve_litellm_on_host_port`) using `main_llm()` which already uses `cloud_llm_host` / `cloud_llm_port` for litellm. So cloud-only also uses the same host/port.

## What was changed in this review

- **Logging**
  - **INFO** when mix-mode cloud LLM starts:  
    `Cloud LLM (LiteLLM) started for mix mode: <name> on <host>:<port>`
  - **WARNING** when we skip because the cloud ref is not litellm (with ref and type).
  - **ERROR** in the LiteLLM thread if the server fails to start or run (so binding errors or other exceptions are visible).

- **Robustness**
  - `run_mix_mode_cloud_llm` and `run_litellm_service` coerce `port` to int before starting the server.
  - `_serve_litellm_on_host_port` wraps the run in try/except and logs any exception.

## How to confirm the cloud server is running

1. After Core starts, look for the INFO line:  
   `Cloud LLM (LiteLLM) started for mix mode: ... on 127.0.0.1:14005`
2. If you see a WARNING about “not litellm” or “main_llm_cloud not set”, fix config (cloud_models entry and type, or set main_llm_cloud).
3. If you see an ERROR like `LiteLLM (...) failed to start or run on ...`, check port conflict (e.g. another process on 14005) or LiteLLM/uvicorn errors in the same log.
4. Optional: `curl -s http://127.0.0.1:14005/health` or similar if LiteLLM exposes a health route; or send a test completion to Core and ensure the request is routed to cloud (logs will show the route and the request to `cloud_llm_host:cloud_llm_port`).

## Files involved

- **Startup:** `core/core.py` → `llmManager.run()`  
- **LLM services:** `llm/llmService.py` — `run()`, `run_main_llm()`, `run_mix_mode_cloud_llm()`, `run_litellm_service()`, `_serve_litellm_on_host_port()`  
- **LiteLLM app:** `llm/litellmService.py` — FastAPI app and `/v1/chat/completions` etc.  
- **Config / resolution:** `base/util.py` — `main_llm()`, `main_llm_for_route()`, `cloud_llm_host`, `cloud_llm_port`  
- **Config schema / load:** `base/base.py` — `CoreMetadata`, `cloud_llm_host`, `cloud_llm_port`  
- **Config file:** `config/llm.yml` — `main_llm_mode`, `main_llm_cloud`, `cloud_llm_host`, `cloud_llm_port`
