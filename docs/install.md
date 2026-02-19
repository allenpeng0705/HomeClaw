# Install

HomeClaw runs on **macOS**, **Windows**, and **Linux**. You need **Python** 3.10–3.12 (recommended).

---

## 1. Clone and install

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
pip install -r requirements.txt
```

For faster installs in China, you can use a mirror (e.g. `-i https://pypi.tuna.tsinghua.edu.cn/simple`).

---

## 2. Optional: cloud or local LLM

HomeClaw supports **cloud** and **local** models (or both together for better capability and cost).

- **Cloud:** Set the API key as an environment variable (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`) and add the model to `cloud_models` in `config/core.yml`. No extra install beyond `requirements.txt` (LiteLLM is included).
- **Local:** To run **local GGUF models**, you need a llama.cpp server. The repo includes `llama.cpp-master/` with platform-specific binaries. Download GGUF model files (e.g. from Hugging Face) into a `models/` folder and configure `local_models` in `config/core.yml`. See [Models](models.md) for paths and ports.

---

## 3. Next step

After install, see [Run](run.md) to start Core and a channel. For full setup (config, users, memory), see the main [HOW_TO_USE.md](https://github.com/allenpeng0705/HomeClaw/blob/main/HOW_TO_USE.md) in the repo.
