# Using Cognee (cognee-main) with a Local LLM

This doc summarizes the **latest Cognee** source (e.g. `../cognee-main`) and how to run it with a **local LLM** from HomeClaw.

---

## 1. How Cognee works

- **Entry points:** `cognee.add(...)` → `cognee.cognify()` → `cognee.search(...)`.
- **Config:** Environment variables (`.env` or `os.environ`) and optional runtime overrides via `cognee.config.set_llm_config({...})`.
- **LLM usage:** Used in `add` (pipeline setup: `test_llm_connection`), and in **cognify** (graph extraction, summarization, etc.) via `LLMGateway.acreate_structured_output(...)`.
- **Structured output:** Default is **Instructor + LiteLLM** (`STRUCTURED_OUTPUT_FRAMEWORK=instructor`). Alternative: BAML.

---

## 2. Cognee LLM config (env)

From `cognee/infrastructure/llm/config.py` and `.env.template`:

| Env var | Purpose | Example (local) |
|--------|---------|------------------|
| `LLM_PROVIDER` | Which adapter to use | `openai`, `ollama`, `custom`, `llama_cpp` |
| `LLM_MODEL` | Model name for LiteLLM / server | `openai/gpt-4o`, `ollama/llama3.1:8b`, `openai/<local_model>` |
| `LLM_ENDPOINT` | API base URL | `http://127.0.0.1:8080/v1` (llama-server, Ollama, etc.) |
| `LLM_API_KEY` | API key; use `local` for local servers | `local` or your key |
| `LLM_INSTRUCTOR_MODE` | Instructor mode | `json_schema_mode`, `json_mode`, or leave empty |
| `LLM_MAX_TOKENS` | Max completion tokens | `16384` |
| `STRUCTURED_OUTPUT_FRAMEWORK` | `instructor` or `baml` | `instructor` |

**Ollama (local):**

```bash
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b
LLM_ENDPOINT=http://localhost:11434/v1
LLM_API_KEY=ollama
```

**OpenAI-compatible local server (e.g. llama-server, LiteLLM proxy, your own):**

Use `LLM_PROVIDER=custom` (or `openai`) and point to your server:

```bash
LLM_PROVIDER=custom
LLM_MODEL=openai/your-model-name
LLM_ENDPOINT=http://127.0.0.1:8080/v1
LLM_API_KEY=local
```

**Llama.cpp server mode (OpenAI-compatible server):**

```bash
LLM_PROVIDER=llama_cpp
LLM_MODEL=your-model-name
LLM_ENDPOINT=http://127.0.0.1:8080/v1
LLM_API_KEY=local
```

**Llama.cpp local (in-process):** set `LLAMA_CPP_MODEL_PATH` and omit endpoint; see Cognee `get_llm_client` / `LlamaCppAPIAdapter`.

---

## 3. Adapters and local LLM

- **`openai`:** Uses `OpenAIAdapter` → `instructor.from_litellm(litellm.acompletion)` with your `LLM_ENDPOINT` / `LLM_MODEL`. Works with any OpenAI-compatible server (including local).
- **`custom`:** Uses `GenericAPIAdapter` → same LiteLLM + Instructor path; same as above for local endpoints.
- **`ollama`:** Uses `OllamaAPIAdapter` → `instructor.from_openai(OpenAI(base_url=..., api_key=...))` (sync client); no LiteLLM.
- **`llama_cpp`:** Uses `LlamaCppAPIAdapter` → server mode (OpenAI-compatible) or local mode (in-process).

For a **local server that speaks OpenAI API** (e.g. llama-server, vLLM, LiteLLM proxy), use either:

- `LLM_PROVIDER=openai` with `LLM_ENDPOINT=http://127.0.0.1:PORT/v1` and `LLM_MODEL=openai/model-name`, or  
- `LLM_PROVIDER=custom` with the same endpoint/model.

---

## 4. Connection test and skip

Before the first real run, the add pipeline calls `setup_and_check_environment()` → `test_llm_connection()` (and embedding test). That uses `LLMGateway.acreate_structured_output(...)` with a tiny prompt. If your local LLM is slow or you want to avoid the check:

```bash
COGNEE_SKIP_CONNECTION_TEST=true
```

---

## 5. Embeddings (for local)

Cognee also needs an embedding model (vector DB). From `.env.template`:

- **Ollama:** e.g. `EMBEDDING_PROVIDER=ollama`, `EMBEDDING_MODEL=nomic-embed-text:latest`, `EMBEDDING_ENDPOINT=http://localhost:11434/api/embed`, `EMBEDDING_DIMENSIONS=768`, `HUGGINGFACE_TOKENIZER=nomic-ai/nomic-embed-text-v1.5`.
- Or use a cloud embedding (e.g. OpenAI) and only the **LLM** local.

---

## 6. How HomeClaw uses Cognee

- **Config source:** `config/core.yml` → `cognee` section. HomeClaw’s `apply_cognee_config(cognee_section)` maps that into `os.environ` (and optional `cognee.config.set_llm_config` for fallback).
- **Mapping:**  
  - `cognee.llm.provider` → `LLM_PROVIDER`  
  - `cognee.llm.model` → `LLM_MODEL`  
  - `cognee.llm.endpoint` → `LLM_ENDPOINT`  
  - `cognee.llm.api_key` → `LLM_API_KEY`  
  (and embedding similarly.)
- **When Cognee runs:** On `CogneeMemory.add()` we call `cognee.add(...)` then `cognee.cognify()`. So the **same** LLM config (env + any `set_llm_config` applied before) is used for both the connection test (inside `add`) and cognify.
- **Fallback:** HomeClaw can set `cognee.llm_fallback` in config; on cognify failure (e.g. local template/Instructor error) it temporarily applies fallback via `_apply_llm_only()` and `set_llm_config`, then retries cognify.

---

## 7. Using the latest Cognee source (cognee-main)

To use the repo at `../cognee-main` instead of the installed package:

1. **Editable install (recommended):**
   ```bash
   pip install -e ../cognee-main
   ```
   Then your app (and HomeClaw) will use the code under `cognee-main/cognee/`.

2. **Or add to path:** Ensure `../cognee-main` (or the folder containing the `cognee` package) is on `sys.path` before any `import cognee`.

3. **Config stays the same:** Env vars and `set_llm_config` still drive provider/model/endpoint; no change required for local LLM.

---

## 8. Instructor + LiteLLM async issue (local)

When Cognee uses **Instructor + LiteLLM** with an **async** path (e.g. `litellm.acompletion`), Instructor can still choose the **sync** wrapper (`new_create_sync` → `retry_sync`). Then `retry_sync` calls `func(...)` where `func` is async, gets a coroutine, and does not `await` it → **"’coroutine’ object is not callable"**.

HomeClaw mitigates this with **memory/instructor_patch.py**:

- Patches `instructor.core.retry.retry_sync` to run any returned coroutine (and to treat a coroutine `func` as runnable).
- Updates `instructor.core.patch.retry_sync` (and `sys.modules` if the patch module was already loaded) so the sync path uses this wrapper.

So when using a **local LLM** with Cognee (OpenAI-compatible or custom via LiteLLM), ensure the Instructor patch is applied **before** Cognee/instructor are used (HomeClaw does this in `core/initialization.py` and in `CogneeMemory.__init__` / before `add()`). If you run Cognee in another process or without HomeClaw’s init, apply the same patch at startup there.

---

## 9. Minimal local LLM checklist

1. **Start local server** (e.g. llama-server, Ollama, or LiteLLM) so it exposes an OpenAI-compatible `/v1/chat/completions` (and embedding endpoint if you use local embeddings).
2. **Set env (or cognee section in core.yml):**  
   `LLM_PROVIDER=openai` or `custom`, `LLM_MODEL=openai/your-model`, `LLM_ENDPOINT=http://127.0.0.1:PORT/v1`, `LLM_API_KEY=local`.
3. **Embedding:** Either local (Ollama + `HUGGINGFACE_TOKENIZER` etc.) or cloud (e.g. OpenAI).
4. **Optional:** `COGNEE_SKIP_CONNECTION_TEST=true` if the connection test is too slow or flaky.
5. **HomeClaw:** Apply Instructor patch early; use `cognee.llm` (and optionally `cognee.llm_fallback`) in config so `apply_cognee_config` and fallback set the same env/`set_llm_config` for Cognee.

---

## 10. Key files in cognee-main (reference)

| Path | Purpose |
|------|--------|
| `cognee/api/v1/add/add.py` | `add()`; calls pipeline that runs `setup_and_check_environment` → `test_llm_connection` |
| `cognee/modules/pipelines/layers/setup_and_check_environment.py` | Runs LLM and embedding connection tests (unless skipped) |
| `cognee/infrastructure/llm/utils.py` | `test_llm_connection()` → `LLMGateway.acreate_structured_output(...)` |
| `cognee/infrastructure/llm/LLMGateway.py` | Dispatches to BAML or Instructor LLM client |
| `cognee/infrastructure/llm/config.py` | `LLMConfig` (env-based); `get_llm_config()` (cached) |
| `cognee/infrastructure/llm/structured_output_framework/litellm_instructor/llm/get_llm_client.py` | Builds adapter by `LLM_PROVIDER` (openai, ollama, custom, llama_cpp, …) |
| `cognee/infrastructure/llm/structured_output_framework/litellm_instructor/llm/openai/adapter.py` | `OpenAIAdapter`; uses `instructor.from_litellm(litellm.acompletion)` |
| `cognee/api/v1/config/config.py` | `config.set_llm_config(config_dict)` updates in-memory `get_llm_config()` |
| `.env.template` | All env vars and examples (Ollama, Azure, OpenRouter, etc.) |

---

## 11. HomeClaw + local llama.cpp (how we use Cognee)

When you use **local llama.cpp** (llama-server) for the main chat model, Cognee uses the **same** server for add/cognify if you leave its LLM config empty.

**What you have (llm.yml):** `main_llm` (e.g. `local_models/Qwen3.5-9B-Q5_K_M`), `main_llm_host`, `main_llm_port` (e.g. `127.0.0.1`, `5023`), and `embedding_llm` / embedding port.

**What to set (memory_kb.yml):** (1) `memory_backend: cognee`. (2) Leave **cognee.llm** and **cognee.embedding** empty. Core then fills them from `main_llm` + `main_llm_host`/`main_llm_port` and from `embedding_llm`, so Cognee uses the same llama-server and embedding server for the connection test and cognify.

**Optional:** Set **cognee.llm** explicitly (e.g. `provider: openai`, `model: openai/Qwen3.5-9B-Q5_K_M`, `endpoint: http://127.0.0.1:5023/v1`, `api_key: local`) if you want a different endpoint. Use **COGNEE_SKIP_CONNECTION_TEST=true** to skip the first-add connection check. Use **cognee.llm_fallback** to retry cognify with a cloud model when the local one fails.

---

Using the latest Cognee with a local LLM is mainly: point `LLM_PROVIDER` / `LLM_MODEL` / `LLM_ENDPOINT` (and embedding) correctly, optionally skip the connection test, and keep HomeClaw’s Instructor patch applied when using the Instructor+LiteLLM path.
