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

## 2) Configure

In Portal:

- create admin
- choose model in LLM settings
- add user
- start Core

## 3) Start Core

```bash
python -m main start
```

Core default URL: `http://127.0.0.1:9000`

Check:

```bash
python -m main doctor
```

## 4) Chat

### Companion app

- set Core URL
- set API key if auth enabled
- select user and chat

### WebChat

```bash
python -m channels.run webchat
```

## 5) Useful next pages

- [install.md](install.md)
- [run.md](run.md)
- [portal.md](portal.md)
- [models.md](models.md)
- [examples.md](examples.md)
