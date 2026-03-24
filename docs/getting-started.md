# Getting Started

The shortest path:

1. Install
2. Configure in Portal
3. Start Core
4. Chat from Companion or channels

## 1) Install

| Platform | Command |
|---|---|
| macOS / Linux | `bash install.sh` |
| Windows | `install.bat` (or `.\install.ps1`) |

Portal opens at `http://127.0.0.1:18472`.

## 2) Prepare local model files (if using local/mix)

- Download GGUF model files and put them in `models/` (default from `config/core.yml` -> `model_path: models`).
- If you changed `model_path`, put GGUF files in that folder instead.
- If you install `llama.cpp` manually, put the binary distribution into `llama.cpp-master/<platform>/` (for example `mac/`, `win_cuda/`, `linux_cpu/`).
- Make sure each `local_models[].path` in `config/llm.yml` matches your GGUF filename.

## 3) Configure

In Portal:

- create admin
- choose model in LLM settings
- add user
- start Core

## 4) Start Core

```bash
python -m main start
```

Core default URL: `http://127.0.0.1:9000`

Check:

```bash
python -m main doctor
```

## 5) Chat

### Companion app

- set Core URL
- set API key if auth enabled
- select user and chat

### WebChat

```bash
python -m channels.run webchat
```

## 6) Useful next pages

- [install.md](install.md)
- [run.md](run.md)
- [portal.md](portal.md)
- [models.md](models.md)
- [examples.md](examples.md)
