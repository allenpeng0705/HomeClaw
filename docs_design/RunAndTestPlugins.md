# How to Run and Test Plugins

This document explains **how to run** and **how to test** both **built-in plugins** (Python, in-process) and **external plugins** (any language, HTTP servers). For authoring and design, see [PluginsGuide.md](PluginsGuide.md) and [PluginStandard.md](PluginStandard.md).

---

## 1. Overview

| Type | Where it runs | How Core uses it |
|------|----------------|-------------------|
| **Built-in** | In-process with Core | Core discovers plugins in `plugins/` at startup and loads Python classes. No separate process. |
| **External** | Separate HTTP server | You start the server; you register it with Core via `POST /api/plugins/register`. Core calls your server when the user intent matches. |

**Testing** is the same for both: send a user message through a **channel** (e.g. WebChat or the interactive `main.py start` chat). The orchestrator routes to the right plugin; you see the plugin’s response (optionally post-processed by the LLM) in the channel.

---

## 2. Prerequisites

- **Core** must be running (default: `http://127.0.0.1:9000`). Start with:  
  `python -m core.core` (from project root), or run Core as part of `python -m main start`.
- **LLM** must be reachable (main LLM and, if using memory/skills, embedding). Configure in `config/core.yml`; check with `python -m main doctor`.
- **Channel** to talk to Core: e.g. **WebChat** (browser) or the **interactive chat** from `python -m main start`.

---

## 3. Built-in Plugins (Python)

Built-in plugins live under `plugins/<PluginName>/` with `plugin.yaml`, `config.yml`, and `plugin.py`. Core discovers and loads them at startup; no registration step.

### 3.1 What’s included

Out of the box you typically have:

- **Weather** (`plugins/Weather/`) — current weather by city/district.
- **Headlines** (`plugins/Headlines/`) — top headlines from News API; parameters (country, category, sources, number) from user message; language defaults to main model. See [News API Top Headlines](https://newsapi.org/docs/endpoints/top-headlines) and [Sources](https://newsapi.org/docs/endpoints/sources).
- **News** (`plugins/News/`) — legacy news fetching (prefer Headlines for new use).
- **Mail** (`plugins/Mail/`) — send email (needs `config/email_account.yml` or similar).

Each has a `plugin.yaml` (id, description, capabilities) and `config.yml` (API keys, defaults). See [PluginsGuide.md](PluginsGuide.md) for the exact structure.

### 3.2 How to run

1. **Start Core** (from project root):

   ```bash
   python -m core.core
   ```

   Or start the full app (Core + interactive channel):

   ```bash
   python -m main start
   ```

   Core scans `plugins/` and loads every folder that has a valid `plugin.yaml` and a Python class extending `BasePlugin`. You’ll see plugin-related logs at startup.

2. **Optional: WebChat**  
   In another terminal, start the WebChat channel so you can test from the browser:

   ```bash
   python -m channels.run webchat
   ```

   Default URL: `http://0.0.0.0:8014/` (override with `WEBCHAT_PORT` / `WEBCHAT_HOST`). Set `CORE_URL` in `channels/.env` if Core is not at `http://127.0.0.1:9000`.

### 3.3 How to test

- **Via interactive chat** (`python -m main start`): type messages like “What’s the weather in Beijing?” or “Send an email to …”. The system routes to the right plugin and shows the reply.
- **Via WebChat**: open `http://localhost:8014/`, send the same kinds of messages. Replies (and any post-processed text) appear in the chat.

**Example prompts:**

- Weather: “What’s the weather today?”, “Weather in Shanghai”, “Do I need an umbrella?”
- Headlines (extract category, source, count from message; "top 5 from BBC" → page_size=5, sources=bbc-news; "5 headlines" → 5 with defaults + tip; "what sources?" → list_sources): “Top headlines”, “Latest news in Germany”, “10 tech headlines from BBC”, “Headlines in Chinese.”
- Mail: “Send an email to john@example.com with subject Hello and body Hi there.”

If a plugin needs **config** (e.g. API key, default city), set it in that plugin’s `config.yml`. For parameter collection (e.g. city from profile or config), see [PluginParameterCollection.md](PluginParameterCollection.md).

---

## 4. External Plugins (HTTP, any language)

External plugins run as **separate HTTP servers**. You **start the server**, then **register** it with Core. After that, testing is the same as for built-in plugins (send messages via a channel).

### 4.1 Contract (reminder)

- **Health:** `GET /health` → return 2xx.
- **Run:** `POST /run` (or your configured path) with body = PluginRequest JSON; response = PluginResult JSON (`request_id`, `plugin_id`, `success`, `text`, `error`).
- **Registration:** `POST http://<core>:9000/api/plugins/register` with plugin id, name, description, `health_check_url`, `type: "http"`, `config` (base_url, path, timeout_sec), and `capabilities`.

Details: [PluginStandard.md](PluginStandard.md) and [external_plugins/README.md](../external_plugins/README.md).

### 4.2 Run and register (by sample)

All commands assume **project root** for Python; Node/Go/Java samples are run from their own directories. Core default: `http://127.0.0.1:9000`. Set `CORE_URL` if different.

| Sample | Language | Port | Run | Register |
|--------|----------|------|-----|-----------|
| Time | Python | 3102 | `python -m external_plugins.time.server` | `python -m external_plugins.time.register` |
| Friends | Python | 3103 | `python -m external_plugins.friends.server` | `python -m external_plugins.friends.register` |
| Quote | Node.js | 3111 | `cd external_plugins/quote-node && npm install && node server.js` | `node register.js` (from that dir) |
| Time | Go | 3112 | `cd external_plugins/time-go && go run main.go` | `./register.sh` |
| Quote | Java | 3113 | `cd external_plugins/quote-java && mvn compile exec:java -Dexec.mainClass="QuotePlugin"` | `./register.sh` |

**Typical flow:**

1. **Terminal 1:** Start Core: `python -m core.core`
2. **Terminal 2:** Start the plugin server (see table above).
3. **Terminal 3:** Register the plugin (see table above). Only needed once per Core run (registrations persist in `config/external_plugins.json` until overwritten or Core clears them).
4. **Terminal 4 (optional):** Start WebChat: `python -m channels.run webchat`, then open `http://localhost:8014/`.

Or use `python -m main start` instead of Terminal 1 and use the interactive chat instead of WebChat.

### 4.3 How to test

- **Interactive chat:** `python -m main start` → e.g. “Give me an inspirational quote”, “What time is it in Tokyo?”, “Quote about success.”
- **WebChat:** Open WebChat, send the same prompts.

The orchestrator picks the registered plugin and capability; you see the plugin’s `text` in the reply (and, when `post_process: true`, the LLM’s refined message).

### 4.4 Verify registration

- **Health:**  
  `curl http://127.0.0.1:<port>/health`  
  (e.g. 3101 for Python quote, 3111 for Node quote).
- **Core has plugin:**  
  Check Core logs at startup or after register; or call Core’s API if you have an endpoint that lists plugins.

---

## 5. Quick reference

| Component | Default URL / command |
|-----------|------------------------|
| Core | `http://127.0.0.1:9000` |
| WebChat | `http://0.0.0.0:8014/` (`python -m channels.run webchat`) |
| Start Core | `python -m core.core` or `python -m main start` |
| Built-in plugins dir | `plugins/` (auto-loaded at Core startup) |
| External plugin registration | `POST http://127.0.0.1:9000/api/plugins/register` |
| Config for Core/channels | `config/core.yml`, `channels/.env` (e.g. `CORE_URL`) |

---

## 6. Troubleshooting

- **Plugin not found / no route**  
  - Built-in: ensure `plugins/<Name>/` has `plugin.yaml` + `plugin.py` and the class extends `BasePlugin`; restart Core.  
  - External: ensure the server is running, registration succeeded, and `health_check_url` is reachable by Core.

- **Wrong or empty response**  
  Check Core logs (`[plugin]`, `[orchestrator]`). For external plugins, ensure the server returns valid PluginResult JSON and that `capability_id` / `capability_parameters` in the request are handled correctly.

- **Parameter missing (e.g. city, recipient)**  
  Use `config_key` / `profile_key` in the capability and/or set defaults in the plugin’s `config.yml`. See [PluginParameterCollection.md](PluginParameterCollection.md).

- **WebChat can’t reach Core**  
  Set `CORE_URL` in `channels/.env` (e.g. `http://127.0.0.1:9000`). For WebSocket, Core must be on the same host or CORS/WS must be allowed.

- **Doctor check**  
  Run `python -m main doctor` to verify config, workspace, skills dir, and LLM connectivity.
