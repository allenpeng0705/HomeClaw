# Getting started

Full path from zero to chatting with HomeClaw. The **[Companion App](companion-app.md)** is the recommended way to use HomeClaw — it works on Mac, Windows, iPhone, and Android.

---

## 1. Install

Clone the repo and run the install script:

- **Mac/Linux:** `git clone https://github.com/allenpeng0705/HomeClaw.git && cd HomeClaw && bash install.sh`
- **Windows (PowerShell):** `git clone https://github.com/allenpeng0705/HomeClaw.git; cd HomeClaw; .\install.ps1`

The script checks Python, installs dependencies, and opens the **Portal** at http://127.0.0.1:18472.

Manual alternative: `pip install -r requirements.txt` after cloning. See [Install](install.md) for details.

## 2. Configure

Edit `config/core.yml` (LLM, memory) and `config/user.yml` (allowed users). Or use the **Portal** (`python -m main portal`) to manage settings in a web UI.

- **Cloud models (fastest start):** Set an API key in the environment (e.g. `export GEMINI_API_KEY=...`) and point `main_llm` to a cloud model in `core.yml`.
- **Local models:** Copy llama.cpp binaries into `llama.cpp-master/<platform>/` and configure `local_models` in `core.yml`. See [Models](models.md).

## 3. Start Core

```bash
python -m main start
```

Core listens on **port 9000** by default. Verify: `curl -s http://127.0.0.1:9000/ready` should return 200.

## 4. Use the Companion App

1. Build from `clients/HomeClawApp/` (see [Companion App](companion-app.md#build-from-source-recommended)) or install from TestFlight/App Store.
2. In the app's **Settings**, set **Core URL** to `http://127.0.0.1:9000` (same machine) or your remote URL.
3. Open **Chat** and send a message.

That's it — you're talking to HomeClaw.

## 5. Optional: add a channel

With Core running, you can also connect via WebChat, Telegram, Discord, and more:

```bash
python -m channels.run webchat   # open http://localhost:8014
```

The Companion App and channels share the same Core, memory, and user identity. See [Channels](channels.md).

---

For troubleshooting, run `python -m main doctor`. See [Help](help.md) for common issues.
