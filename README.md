<p align="center">
  <img src="HomeClaw_Banner.jpg" alt="HomeClaw Banner">
</p>

<p align="center">
  <a href="https://www.homeclaw.cn"><strong>www.homeclaw.cn</strong></a>
</p>

# HomeClaw

HomeClaw is a self-hosted AI assistant platform:

- one `Core` backend (FastAPI)
- local/cloud/mix LLM routing
- tools, skills, plugins
- companion app + channels
- multi-user and optional federation

## Quick Start

### 1) Install

| Platform | Command |
|---|---|
| macOS / Linux | `bash install.sh` |
| Windows | `install.bat` (or `.\install.ps1`) |

The installer sets dependencies and opens Portal at `http://127.0.0.1:18472`.

### 2) Configure in Portal

In Portal:

1. Create admin account
2. Set model(s) in **LLM settings**
3. Add users
4. Start Core

### 3) Run and chat

```bash
python -m main start
```

- Core URL: `http://127.0.0.1:9000`
- Quick check:

```bash
python -m main doctor
```

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

### Example C: Better PDF output (VMPrint)

Use tool `markdown_to_pdf` or `vmprint_render` with:

- `vmprint_profile`: `academic | manuscript | screenplay | literature`
- optional `vmprint_style`

---

## Documentation

- Main docs: [https://allenpeng0705.github.io/HomeClaw/](https://allenpeng0705.github.io/HomeClaw/)
- Quick start details: `QuickStart.md`
- Install details: `InstallationGuide.md`
- Full usage: `HOW_TO_USE.md`
- Design notes: `docs_design/`

---

## Language Versions

- [简体中文](README_zh.md)
- [日本語](README_jp.md)
- [한국어](README_kr.md)

---

## Contributing / License

- Contributing: `CONTRIBUTING.md`
- License: Apache 2.0 (`LICENSE`)
