# Models

HomeClaw supports **cloud** LLMs (OpenAI, **Gemini**, DeepSeek, etc. via LiteLLM) and **local** LLMs (llama.cpp, GGUF). You can use one or both; main and embedding model are configured separately. **Cloud and local can work together** for better capability and cost. **Multimodal** (images, audio, video) works with both **cloud** (e.g. **Gemini**, GPT-4o) and **local models** (e.g. Qwen2-VL with mmproj)—tested with both; all work well.

---

## Cloud models

- In **`config/core.yml`**, under **`cloud_models`**, add entries with `id`, `path` (LiteLLM model name, e.g. `openai/gpt-4o`, `gemini/gemini-2.5-flash`), `host`, `port`, and **`api_key_name`** (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`).
- Set the **environment variable** with that name where Core runs (e.g. `export OPENAI_API_KEY=...`). Do not put API keys in the config file.
- Set **`main_llm`** or **`embedding_llm`** to e.g. `cloud_models/OpenAI-GPT4o` or `cloud_models/Gemini-2.5-Flash`.

Supported providers include OpenAI, Google Gemini, DeepSeek, Anthropic, Groq, Mistral, xAI, OpenRouter, and more. See [LiteLLM docs](https://docs.litellm.ai/docs/providers).

---

## Local models

- Run **GGUF** models via a **llama.cpp** server. Place model files in a `models/` directory (or path set by **`model_path`** in `config/core.yml`).
- In **`config/core.yml`**, under **`local_models`**, add entries with `id`, `path` (relative to `model_path`), `host`, `port`. Set **`main_llm`** and **`embedding_llm`** to e.g. `local_models/<id>`.
- Start the llama.cpp server(s) for each model (see `llama.cpp-master/README.md` in the repo). You can use the bundled binaries in `llama.cpp-master/<platform>/`.

---

## Use cloud and local together

You can use a **cloud** model for chat and a **local** model for embedding (or the other way around). Set **`main_llm`** and **`embedding_llm`** to the appropriate `cloud_models/<id>` or `local_models/<id>`. Cloud and local can work together for better capability and cost. Switch at runtime via CLI: **`llm cloud`** (cloud) or **`llm set`** (local), or by editing `config/core.yml` and restarting Core. You can also switch from the **Companion app** (Manage Core → LLM).

---

## Multimodal (images, audio, video)

- **Cloud:** **Gemini**, GPT-4o, and other providers support images (and often audio/video). Set **`main_llm`** to e.g. `cloud_models/Gemini-2.5-Flash` in `config/core.yml`. **Gemini** works well for multimodal; tested with both cloud and local.
- **Local:** Use a vision-capable model (e.g. Qwen2-VL, LLaVA) with **mmproj** in `config/core.yml` under `local_models`. Set **`supported_media: [image]`** (or `[image, audio, video]` if the model supports it).
- The Companion app and WebChat can send images and files; Core converts them to the format the model expects (e.g. data URL for vision APIs).
