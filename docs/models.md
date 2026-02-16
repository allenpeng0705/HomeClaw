# Models

HomeClaw supports **local** LLMs (llama.cpp, GGUF) and **cloud** LLMs (OpenAI, Gemini, DeepSeek, etc. via LiteLLM). You can use one or both; main and embedding model are configured separately.

---

## Local models

- Run **GGUF** models via a **llama.cpp** server. Place model files in a `models/` directory (or path set by **`model_path`** in `config/core.yml`).
- In **`config/core.yml`**, under **`local_models`**, add entries with `id`, `path` (relative to `model_path`), `host`, `port`. Set **`main_llm`** and **`embedding_llm`** to e.g. `local_models/<id>`.
- Start the llama.cpp server(s) for each model (see `llama.cpp-master/README.md` in the repo). You can use the bundled binaries in `llama.cpp-master/<platform>/`.

---

## Cloud models

- In **`config/core.yml`**, under **`cloud_models`**, add entries with `id`, `path` (LiteLLM model name, e.g. `openai/gpt-4o`), `host`, `port`, and **`api_key_name`** (e.g. `OPENAI_API_KEY`).
- Set the **environment variable** with that name where Core runs (e.g. `export OPENAI_API_KEY=...`). Do not put API keys in the config file.
- Set **`main_llm`** or **`embedding_llm`** to e.g. `cloud_models/OpenAI-GPT4o`.

Supported providers include OpenAI, Google Gemini, DeepSeek, Anthropic, Groq, Mistral, xAI, OpenRouter, and more. See [LiteLLM docs](https://docs.litellm.ai/docs/providers).

---

## Mix local and cloud

You can use a **local** model for chat and a **cloud** model for embedding (or the other way around). Set **`main_llm`** and **`embedding_llm`** to the appropriate `local_models/<id>` or `cloud_models/<id>`. Switch at runtime via CLI: **`llm set`** (local) or **`llm cloud`** (cloud), or by editing `config/core.yml` and restarting Core.
