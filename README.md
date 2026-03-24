<p align="center">
  <img src="HomeClaw_Banner.jpg" alt="HomeClaw Banner">
</p>

<p align="center">
  <a href="https://www.homeclaw.cn"><strong>www.homeclaw.cn</strong></a>
</p>

# HomeClaw

HomeClaw is a self-hosted AI assistant platform.

It gives you one `Core` backend that can serve many clients (Companion app + channels), use local/cloud/mix models, and extend behavior with tools, skills, and plugins. You can run it for personal use, family/team workflows, or multi-instance federation.

At a glance:

- one `Core` backend (FastAPI)
- local/cloud/mix LLM routing
- tools, skills, plugins
- companion app + channels
- multi-user and optional federation

## Quick Start

[Open `QuickStart.md`](QuickStart.md) for the full install and first-chat flow.

---

## What You Can Build

- Personal/local assistant (GGUF + llama.cpp)
- Cloud assistant (OpenAI/Gemini/DeepSeek/etc.)
- Mix-mode assistant (auto local vs cloud by task)
- Team assistant (multi-user in one Core)
- Channel bots (WebChat, Telegram, Discord, Slack, etc.)
- Federated network (multiple HomeClaw instances)

---

## Simple Examples

### Example A: Run WebChat channel

```bash
python -m channels.run webchat
```

Open the URL printed in terminal (default around `http://localhost:8014`).

### Example B: Local + cloud mix

In `config/llm.yml`, set:

- `main_llm_mode: mix`
- `main_llm_local: local_models/<your_local_model>`
- `main_llm_cloud: cloud_models/<your_cloud_model>`

Then ask normal questions; router chooses model per request.

### Example C: Generate document output

Use HomeClaw document tools to produce downloadable report files under `output/`.

---

## Documentation

- Main docs: [https://allenpeng0705.github.io/HomeClaw/](https://allenpeng0705.github.io/HomeClaw/)
- Quick start details: `QuickStart.md`
- Install details: `InstallationGuide.md`
- Full usage: `HOW_TO_USE.md`
- Design notes: `docs_design/`

---

## Contributing / License

- Contributing: `CONTRIBUTING.md`
- License: Apache 2.0 (`LICENSE`)
