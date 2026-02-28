# Ollama as Local Model and CLI Integration

## Goals

1. **Treat Ollama as a local model** — Move Ollama out of `cloud_models` (LiteLLM) and support it under `local_models`, so users can choose Ollama for local inference without mixing it with cloud providers.
2. **Use Ollama CLI for model management** — Let users list, pull, and select models via `ollama list` / `ollama pull` (or equivalent API), and optionally set the selected model as the main local LLM without manually editing YAML.

## Current State

- **Local models:** Defined in `config/llm.yml` under `local_models`. Each entry has `id`, `path` (GGUF file path relative to `model_path`), `host`, `port`. Core starts a **llama.cpp** server per model (one process per port). Completion is sent to `http://host:port/v1/chat/completions` (OpenAI-compatible).
- **Cloud models:** Under `cloud_models`; each entry is served by **LiteLLM** (Core starts a LiteLLM proxy per model or shared). Path is provider/model (e.g. `openai/gpt-4o`).
- **Ollama today:** Documented in `llm.yml` as a commented cloud_models entry (`path: ollama/qwen2.5:7b`, host/port for LiteLLM). That works but (a) conceptually Ollama is local, (b) users must edit YAML to change model and cannot use `ollama pull` / `ollama list` from the product.

## Relevant facts

- **Ollama server:** Runs separately (e.g. `ollama serve` or auto-started by the app). Default: `http://127.0.0.1:11434`.
- **Ollama API:** OpenAI-compatible chat at `http://localhost:11434/v1/chat/completions`; request body uses `"model": "qwen2.5:7b"` (Ollama model name). No API key. So the same HTTP client code (host, port, `/v1/chat/completions`, `model` in body) works for both llama.cpp and Ollama.
- **Ollama CLI:** `ollama list` (or `ollama ls`) lists local models; `ollama pull <name>` downloads a model; `ollama run <name>` runs interactively. API: `GET /api/tags` for list, `POST /api/pull` for pull.
- **Embeddings:** Ollama uses `POST /api/embed`, not `/v1/embeddings`. Supporting Ollama as `embedding_llm` would require an adapter; this design focuses on **chat/main LLM** first.

---

## Design 1: Ollama as Local Model

### 1.1 Config: `local_models` entry type

- Add an optional **`type`** to each `local_models` entry:
  - **`llama_cpp`** (default) — Current behavior: Core starts a llama.cpp server; `path` = GGUF path relative to `model_path`; optional `mmproj`, `lora`, `lora_base`.
  - **`ollama`** — No process started by Core; `path` = **Ollama model name** (e.g. `qwen2.5:7b`, `llama3.2`, `gemma2:9b`). `host` / `port` = Ollama server (defaults below).

- Example in `llm.yml`:

```yaml
local_models:
  # Existing llama.cpp entries unchanged (type optional, default llama_cpp)
  - id: main_vl_model_8B
    alias: main_vl_model_8B
    path: Qwen3-VL-8B-Instruct-Q4_K_M.gguf
    mmproj: mmproj-Qwen3-VL-8B-BF16.gguf
    host: 127.0.0.1
    port: 5024
    capabilities: [Chat]
    supported_media: [image]

  # Ollama: no server started by Core; path = Ollama model name
  - id: Ollama-qwen2
    type: ollama
    alias: Ollama Qwen2
    path: qwen2.5:7b          # Ollama model name (ollama pull qwen2.5:7b)
    host: 127.0.0.1
    port: 11434
    capabilities: [Chat]
```

- Defaults when `type: ollama` and host/port omitted: `host: 127.0.0.1`, `port: 11434`.

### 1.2 Backend behavior

- **Model resolution (`base/util.py`):**
  - `_get_model_entry(model_id)`: For entries in `local_models`, if `entry.get("type") == "ollama"` return `(entry, "ollama")` instead of `(entry, "local")`. Otherwise keep returning `(entry, "local")`.
  - `main_llm()`, `main_llm_for_route()`, `_resolve_llm()`, `embedding_llm()`: When the resolved type is `"ollama"`, treat like local for routing (e.g. mix mode still uses “local” vs “cloud”), but:
    - **path_or_model:** use the entry’s `path` (Ollama model name), **not** joined with `models_path()`.
    - **host, port:** from entry or default 127.0.0.1, 11434.
  - `_llm_request_model_and_headers`: For `mtype == "ollama"` use `path_or_model` (Ollama model name) as `model_for_request`; no API key (same as local). So: `model_for_request = path_or_model if mtype in ("litellm", "ollama") else (raw_id or path_or_model)`.

- **LLM service manager (`llm/llmService.py`):**
  - In `run_main_llm()` (and any path that starts “local” LLM): when resolving the main local model, if the corresponding `local_models` entry has `type == "ollama"`, **do not** call `start_llama_cpp_server`. Only register the model name in `self.llms` so Core considers it “running” (no process to start; Ollama is already running elsewhere).
  - Classifier / SLM: can remain llama.cpp-only for now; if we later add an Ollama classifier, the same “type: ollama” + skip server start would apply.

- **Health / wait-for-LLM:** Existing logic that waits for `host:port` to become available still applies; for Ollama that’s the user’s Ollama server (e.g. 11434).

- **Embedding:** No change in this phase. `embedding_llm` continues to be llama.cpp or cloud; Ollama embedding (e.g. `/api/embed` adapter) can be a later extension.

### 1.3 Removal from cloud_models

- The commented example in `llm.yml` that puts Ollama under `cloud_models` (via LiteLLM) can be removed or replaced by a short comment pointing to “use `local_models` with `type: ollama` instead”.

---

## Design 2: Utilize Ollama CLI for Download and Select

### 2.1 Options

- **A) Core CLI subcommands** — e.g. `python -m core ollama list`, `python -m core ollama pull qwen2.5:7b`, `python -m core ollama set-main qwen2.5:7b` (updates `main_llm_local` or adds/updates an Ollama entry in `local_models`).
- **B) Settings UI (Gradio / Companion)** — “Ollama” section: list models (from `ollama list` or GET `/api/tags`), “Pull” button, dropdown to “Use as main local model”.
- **C) Both CLI and UI** — Recommended so both scriptable and user-friendly.

### 2.2 Shared “Ollama helper” module

- Add a small module, e.g. **`llm/ollama_client.py`** (or `tools/ollama.py`), used by both CLI and UI:
  - **`list_models(host, port)`** — Call `GET http://{host}:{port}/api/tags` (or subprocess `ollama list`), return list of `{name, ...}` (and optionally size, digest). Prefer HTTP so we don’t depend on `ollama` in PATH when server is remote.
  - **`pull_model(host, port, name)`** — Call `POST http://{host}:{port}/api/pull` with `{"name": "qwen2.5:7b"}` (or subprocess `ollama pull <name>`). Optionally poll until complete (Ollama API returns stream/status).
  - **`get_default_host_port(config)`** — From first `local_models` entry with `type: ollama`, or from a small config key (e.g. `ollama_host`, `ollama_port` in core.yml), or hardcode 127.0.0.1:11434.

- This gives one place for “list/pull” logic and keeps CLI/UI thin.

### 2.3 CLI

- Under the same entrypoint that runs Core (e.g. `python -m core` or existing CLI):
  - **`ollama list`** — Call `list_models()`, print table (name, size, etc.).
  - **`ollama pull <name>`** — Call `pull_model(name)`, print progress/result.
  - **`ollama set-main <name>`** — Ensure an Ollama `local_models` entry exists (e.g. id `Ollama-<sanitized_name>`, path = name, type ollama, host/port from config/default). Set `main_llm_local` to `local_models/Ollama-<id>` and optionally `main_llm_mode: local`. Write back to `llm.yml` (or merged config) so the user doesn’t have to edit YAML to switch models.

- This allows: “install Ollama → run `ollama pull qwen2.5:7b` (or Core’s `ollama pull`) → run `ollama set-main qwen2.5:7b`” and use that model without touching YAML.

### 2.4 UI (Gradio / Companion)

- **Gradio (Manage Core / LLM):** If any `local_models` entry has `type: ollama`, show an “Ollama” subsection:
  - Dropdown or list of models from `list_models()`.
  - “Pull model” input + button (calls `pull_model`).
  - “Use as main local model” that updates config to point `main_llm_local` at the chosen Ollama entry (or creates one and selects it).
- **Companion app:** Same idea if we add a “Manage Core / LLM” screen: list, pull, set main for Ollama.

### 2.5 Config write-back

- `ollama set-main <name>` (and UI “Use as main local model”) should:
  - Read current `llm.yml` (or merged config).
  - Ensure there is a `local_models` entry with `type: ollama` and `path: <name>` (create or update one, e.g. id `Ollama-<sanitized>`).
  - Set `main_llm_local` to `local_models/<that_id>`.
  - Optionally set `main_llm_mode: local` if desired.
  - Write back to `llm.yml` (and/or the place Core loads from) with minimal diff (e.g. preserve comments and order where possible).

---

## Summary

| Item | Action |
|------|--------|
| **1. Ollama as local** | Add `type: ollama` to `local_models`; path = Ollama model name; host/port = Ollama server (default 127.0.0.1:11434). Do not start llama.cpp for such entries; use existing `/v1/chat/completions` client with that host/port and model name. |
| **2. Model resolution** | `_get_model_entry` returns `(entry, "ollama")` for ollama entries; `main_llm()` etc. return path = model name, no `models_path()` join; request body uses that as `model`. |
| **3. No LiteLLM for Ollama** | Remove Ollama from cloud_models example; document Ollama under local_models only. |
| **4. List/Pull** | Add `llm/ollama_client.py` (or similar) with `list_models(host, port)` and `pull_model(host, port, name)` using Ollama HTTP API. |
| **5. CLI** | Add `ollama list`, `ollama pull <name>`, `ollama set-main <name>` that use the helper and optionally update llm.yml. |
| **6. UI** | In Manage Core / LLM, if Ollama is configured, show list/pull/set-main for Ollama models. |

## Open points / follow-ups

- **Embedding:** Ollama’s `/api/embed` is not OpenAI `/v1/embeddings`. Supporting Ollama as `embedding_llm` would need a small adapter (e.g. map our embedding call to `/api/embed` and normalize response). Defer unless requested.
- **Classifier (Layer 3):** Today classifier is llama.cpp. Using an Ollama model for the router classifier could reuse the same `type: ollama` + no-server-start logic later.
- **Comments in llm.yml:** When auto-adding an Ollama entry, keep a short comment so users understand it was added by “ollama set-main” / UI.

This design keeps Ollama as a first-class local option and lets users rely on `ollama` CLI (or our wrappers) to download and select models without editing YAML by hand.
