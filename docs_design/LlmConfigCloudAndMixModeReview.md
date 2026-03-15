# llm.yml: Cloud-only and Mix mode logic review

This doc confirms how **llm.yml** (and core.yml `llm_config_file`) is loaded and how **cloud-only** and **mix** mode are applied in code.

---

## 1. Where llm.yml is loaded

- **core.yml** can set `llm_config_file: llm.yml` (path relative to config dir).
- In **base/base.py** (`CoreMetadata.from_yaml`), when that key is set, the file is read and a fixed set of keys is **merged** into the main config `data`:
  - `main_llm_mode`, `main_llm_local`, `main_llm_cloud`, `main_llm`, `local_models`, `cloud_models`, `vision_llm`, `hybrid_router`, `main_llm_language`, `embedding_llm`, `embedding_host`, `embedding_port`, `main_llm_host`, `main_llm_port`, plus llama_cpp, completion, vision_llm_*, etc.
- So **llm.yml** does not replace core.yml; it **adds/overrides** those keys. Valid values for lists/dicts/ints are enforced; invalid entries are skipped with a warning.

---

## 2. How main_llm_mode is interpreted (base/base.py)

After merging llm.yml into `data`:

```text
main_llm_mode_raw = data.get('main_llm_mode') or ''  →  stripped, lowercased
```

- If `main_llm_mode_raw` is **exactly** `'local'`, `'cloud'`, or `'mix'` → **main_llm_mode_val** = that value.
- Otherwise → **derived from main_llm**: if `main_llm` starts with `cloud_models/` then mode = `'cloud'`, else `'local'`.

Then **main_llm_ref** is set from mode and optional main_llm_local / main_llm_cloud:

| main_llm_mode_val | main_llm_ref set to |
|-------------------|----------------------|
| **local**         | main_llm_local (if non-empty) |
| **cloud**         | main_llm_cloud (if non-empty) |
| **mix**           | default_route from hybrid_router: if `default_route == 'local'` → main_llm_local, else main_llm_cloud; if still empty → main_llm_local or main_llm_cloud or main_llm |

So:

- **Cloud-only:** `main_llm_mode: cloud` + `main_llm_cloud: cloud_models/DeepSeek-Chat` → effective ref = **main_llm_cloud**.
- **Mix:** `main_llm_mode: mix` + `hybrid_router.default_route: local` → effective ref for “default” = **main_llm_local**; routing can override per request to cloud (main_llm_cloud).

---

## 3. How the effective model is used (base/util.py)

### _effective_main_llm_ref()

- **mode == "local"** → return **main_llm_local** (if set).
- **mode == "cloud"** → return **main_llm_cloud** (if set).
- **mode == "mix"** → return **default_route**’s ref: if `default_route == "local"` then main_llm_local, else main_llm_cloud (if set).
- Else → return **main_llm**.

So cloud-only always uses **main_llm_cloud**; mix uses default_route’s ref when no per-request route is set.

### main_llm()

- Calls **main_llm_name = _effective_main_llm_ref()**.
- Resolves that to an **entry** and **mtype** (local / ollama / litellm).
- **Host/port:**  
  - **Litellm (cloud):** When **mtype == 'litellm'**, **main_llm()**, **main_llm_for_route()**, and **_resolve_llm()** use **cloud_llm_host** and **cloud_llm_port** from config (defaults 127.0.0.1 and 14005). So cloud-only and mix (route=cloud or fallback) all use one defined cloud proxy address. Future: per-model host/port from the cloud_models entry can be used when needed.
  - **Local/ollama:** Host/port remain **main_llm_host** and **main_llm_port**.

### main_llm_for_route(route)

- If **main_llm_mode != "mix"** → returns **main_llm()** (route is ignored). So cloud-only always goes through **main_llm()**.
- If **main_llm_mode == "mix"** and **route in ("local", "cloud")** → uses **main_llm_local** or **main_llm_cloud** for that route, then resolves **host/port** the same way as in the current **main_llm_for_route** implementation (which uses **main_llm_host/main_llm_port** for the “main” model; for the **other** model in mix we use **_resolve_llm(llm_name)** which **does** use the entry’s host/port). So in mix, when we call with **llm_name=main_llm_cloud**, **_resolve_llm** uses the cloud entry’s host/port (14005). So **mix fallback to cloud** correctly uses 14005; **cloud-only** goes through **main_llm()** and currently uses 5023 unless we fix it.

---

## 4. LLM loop (core/llm_loop.py)

- **mix mode:**  
  - Router runs (heuristic → semantic → long-query → SLM → default_route).  
  - Sets **mix_route_this_request** to `"local"` or `"cloud"` and **effective_llm_name** to **main_llm_local** or **main_llm_cloud**.  
  - All LLM calls in that turn use **llm_name=effective_llm_name**. So the correct ref (local or cloud) is passed; **_resolve_llm(effective_llm_name)** then uses the **entry’s host/port** when the model is not the “current main” (e.g. cloud in mix uses 14005).
- **Cloud-only (and local-only):**  
  - **main_llm_mode != "mix"** so the router block is skipped; **effective_llm_name** stays **None**.  
  - LLM calls use **llm_name=None** → **resolved = main_llm()** → so **main_llm()** decides host/port. For cloud-only, **main_llm()** returns the cloud model but with **main_llm_host/main_llm_port**, which is wrong if the proxy is on 14005.

---

## 5. Summary table

| Config | main_llm_ref / effective ref | Host/port source | Correct? |
|--------|-----------------------------|-------------------|----------|
| **main_llm_mode: cloud**, main_llm_cloud set | main_llm_cloud | **main_llm()** → entry host/port for litellm (e.g. 14005) | ✅ |
| **main_llm_mode: mix**, route = local | main_llm_local | main_llm_for_route("local") → main_llm_host, main_llm_port | ✅ |
| **main_llm_mode: mix**, route = cloud | main_llm_cloud | _resolve_llm(main_llm_cloud) → **entry host/port** (e.g. 14005) | ✅ |
| **main_llm_mode: mix**, fallback to cloud | main_llm_cloud | _resolve_llm(main_llm_cloud) → entry host/port | ✅ |

So **cloud-only** and **mix** (including route=cloud and fallback) all use the cloud_models entry’s host/port when the model is litellm.

---

## 6. Cloud host/port: cloud_llm_host and cloud_llm_port

- **Config (llm.yml):** **cloud_llm_host** and **cloud_llm_port** define the single LiteLLM proxy address (defaults 127.0.0.1 and 14005). Used for all cloud model requests (cloud-only and mix when route=cloud or fallback).
- **base/util.py:** When **mtype == 'litellm'**, **main_llm()**, **main_llm_for_route()**, and **_resolve_llm()** use **cloud_llm_host** and **cloud_llm_port**. No use of cloud_models entry host/port for now; in the future, per-model host/port from the entry can be used if needed.

---

## 7. llm.yml keys quick reference

| Key | Purpose |
|-----|--------|
| **main_llm_mode** | `local` \| `cloud` \| `mix`. If missing, derived from main_llm (cloud_models/ → cloud, else local). |
| **main_llm_local** | Ref for local model (e.g. `local_models/Qwen3.5-9B-Q5_K_M`). Used when mode is local or (in mix) when route is local. |
| **main_llm_cloud** | Ref for cloud model (e.g. `cloud_models/DeepSeek-Chat`). Used when mode is cloud or (in mix) when route is cloud. |
| **main_llm_host** / **main_llm_port** | Used for the **local** main model (llama.cpp, etc.). |
| **cloud_llm_host** / **cloud_llm_port** | Used for the **cloud** (LiteLLM) model in cloud-only and mix. Single proxy address; defaults 127.0.0.1 and 14005. Set in llm.yml. |
| **cloud_models** | List of `{ id, path, api_key?, ... }`. Model id/path/api_key; host/port for cloud come from cloud_llm_host/cloud_llm_port (future: per-model host/port from entry if needed). |
| **hybrid_router** | Only affects **mix**. default_route, heuristic, semantic, slm, fallback_on_llm_error, show_route_in_response, etc. |

This matches the current code and the intended behavior for cloud-only and mix mode.
