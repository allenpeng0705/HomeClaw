# Models

HomeClaw supports **cloud** LLMs (OpenAI, **Gemini**, DeepSeek, etc. via LiteLLM) and **local** LLMs (llama.cpp, GGUF). You can use one or both; main and embedding model are configured separately. **Cloud and local can work together** for better capability and cost. **Multimodal** (images, audio, video) works with both **cloud** (e.g. **Gemini**, GPT-4o) and **local models** (e.g. Qwen2-VL with mmproj)—tested with both; all work well.

---

## Cloud models

- In **`config/core.yml`**, under **`cloud_models`**, add entries with `id`, `path` (LiteLLM model name, e.g. `openai/gpt-4o`, `gemini/gemini-2.5-flash`), `host`, `port`, and **`api_key_name`** (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`).
- **API key:** You can set the API key in either of two ways:
  - **Environment variable (recommended):** Set the variable with that name where Core runs (e.g. `export GEMINI_API_KEY=...`). Keeps keys out of config files.
  - **In core.yml:** Under the same cloud model entry, you can set **`api_key: "your-key"`** (e.g. for convenience or local testing). For production or shared repos, prefer environment variables.
- Set **`main_llm`** or **`embedding_llm`** to e.g. `cloud_models/OpenAI-GPT4o` or `cloud_models/Gemini-2.5-Flash`.

Supported providers include OpenAI, Google Gemini, DeepSeek, Anthropic, Groq, Mistral, xAI, OpenRouter, and more. See [LiteLLM docs](https://docs.litellm.ai/docs/providers).

---

## Local models

- Run **GGUF** models via a **llama.cpp** server. Place model files in a `models/` directory (or path set by **`model_path`** in `config/core.yml`).
- In **`config/core.yml`**, under **`local_models`**, add entries with `id`, `path` (relative to `model_path`), `host`, `port`. Set **`main_llm`** and **`embedding_llm`** to e.g. `local_models/<id>`.
- **Copy llama.cpp's binary distribution** into `llama.cpp-master/<platform>/` for your device type (mac/, win_cuda/, linux_cpu/, etc.; see `llama.cpp-master/README.md` in the repo). Used for both main and embedding local models. Then start the llama.cpp server(s) for each model.

---

## Use cloud and local together

You can use a **cloud** model for chat and a **local** model for embedding (or the other way around). Set **`main_llm`** and **`embedding_llm`** to the appropriate `cloud_models/<id>` or `local_models/<id>`. Cloud and local can work together for better capability and cost. Switch at runtime via CLI: **`llm cloud`** (cloud) or **`llm set`** (local), or by editing `config/core.yml` and restarting Core. You can also switch from the **Companion app** (Manage Core → LLM).

---

## Multimodal (images, audio, video)

- **Cloud:** **Gemini**, GPT-4o, and other providers support images (and often audio/video). Set **`main_llm`** to e.g. `cloud_models/Gemini-2.5-Flash` in `config/core.yml`. **Gemini** works well for multimodal; tested with both cloud and local.
- **Local:** Use a vision-capable model (e.g. Qwen2-VL, LLaVA) with **mmproj** in `config/core.yml` under `local_models`. Set **`supported_media: [image]`** (or `[image, audio, video]` if the model supports it).
- The Companion app and WebChat can send images and files; Core converts them to the format the model expects (e.g. data URL for vision APIs).

---

## Tested configurations

These are **example configurations** we have tested. You can use them as a starting point or mix local and cloud.

### Local models (tested)

| Use | Model | Notes |
|-----|-------|--------|
| **Main (chat + vision)** | **Qwen3VL-4B** — small 4B model with vision (mmproj) | `local_models/main_vl_model_4B` in core.yml; path: `Qwen3VL-4B-Instruct-Q4_K_M.gguf`, mmproj: `mmproj-Qwen3VL-4B-Instruct-F16.gguf`; port 5023. **supported_media: [image]** for Companion/WebChat images. |
| **Embedding** | **Qwen3-Embedding-0.6B** | `local_models/embedding_text_model`; path: `Qwen3-Embedding-0.6B-Q8_0.gguf`; port 5066. |
| **Other local options** | LLaVA 1.5 7B, Qwen3VL-8B, etc. | Add entries under `local_models` with `path`, optional `mmproj`, `host`, `port`, `supported_media`. See `config/core.yml` in the repo for more examples. |

### Cloud models (tested)

| Use | Model | API key |
|-----|-------|--------|
| **Main (chat + vision)** | **Gemini 2.5 Flash** | Set **`GEMINI_API_KEY`** in the environment, or **`api_key`** in the `Gemini-2.5-Flash` entry in `config/core.yml`. |
| **Other cloud options** | OpenAI GPT-4o, Anthropic Claude, DeepSeek, Groq, Mistral, xAI, OpenRouter, Cohere, Perplexity, Ollama (no key) | Each has an **`api_key_name`** (e.g. `OPENAI_API_KEY`). Set that env var or **`api_key`** in the model entry in core.yml. |

### Mix mode (tested)

- **main_llm_mode: mix** — router picks **local** (e.g. main_vl_model_4B) or **cloud** (e.g. Gemini-2.5-Flash) per request.
- **main_llm_local:** `local_models/main_vl_model_4B`  
- **main_llm_cloud:** `cloud_models/Gemini-2.5-Flash`  
- **embedding_llm:** `local_models/embedding_text_model` (or a cloud embedding if you prefer).

API keys for cloud models: set via **environment variable** (recommended) or **`api_key`** in **`config/core.yml`** per model.
