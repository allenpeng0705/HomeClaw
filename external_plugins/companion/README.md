# Companion Plugin — Detailed Guide

The **Companion** plugin adds a dedicated conversational companion (a persona that can be girlfriend, boyfriend, friend, parent, etc.) with its own chat history and settings. All companion data is stored **separately** from the main assistant — it does not touch the main user database. Character and language settings make the companion interesting and useful by defining who they are and how they reply.

**Design doc:** [docs_design/CompanionFeatureDesign.md](../../docs_design/CompanionFeatureDesign.md)

---

## Table of contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Setup (step by step)](#3-setup-step-by-step)
4. [Configuration reference](#4-configuration-reference)
5. [Character and language](#5-character-and-language)
6. [Per-user settings](#6-per-user-settings)
7. [How to use the companion](#7-how-to-use-the-companion)
8. [Plugin API reference](#8-plugin-api-reference)
9. [Data storage](#9-data-storage)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

- **What it does:** Provides a separate chat thread with a companion persona. The companion uses Core's LLM to reply; chat history and settings are stored only in the plugin's store.
- **Who it's for:** One companion per user; each user can have different character/language (via per-user settings).
- **Where it runs:** As an external HTTP plugin (this folder). Core only **routes** requests to the plugin when the user is in "companion" mode; Core does not store name, character, or language.

---

## 2. Prerequisites

- **Python 3.8+** with `uvicorn`, `fastapi`, `pyyaml`, `httpx` (install if missing: `pip install uvicorn fastapi pyyaml httpx`).
- **HomeClaw Core** running and reachable (for LLM and for registering the plugin).
- **User allowlist:** The `user_id` used when talking to the companion must exist in `config/user.yml` (Core checks permission for `/inbound`).

---

## 3. Setup (step by step)

### Step 1: Start HomeClaw Core

From the project root:

```bash
python -m core.core
```

Leave it running (default port 9000). Ensure `config/user.yml` includes the user IDs you will use (e.g. `webchat_user`, or the ID your companion app sends).

### Step 2: Configure the companion (plugin)

Edit **`external_plugins/companion/config.yml`**:

```yaml
name: Veda
character: friend    # girlfriend, boyfriend, wife, husband, sister, brother, child, friend, parent
language: en         # en, zh, ja, ko, es, fr, de, pt, it, ru, ar, ...
response_length: medium   # short, medium, long
idle_days_before_nudge: 0 # 0 = disabled
```

Set `name` to the companion's name (used in prompts and, if you use keyword routing, as the trigger). Set `character` and `language` as desired; these are what make the companion interesting and useful.

### Step 3: Start the companion plugin server

From the **project root**:

```bash
python -m external_plugins.companion.server
```

Default port: **3103**. To use another port:

```bash
COMPANION_PORT=3104 python -m external_plugins.companion.server
```

Check that it's up:

```bash
curl http://127.0.0.1:3103/health
# → {"status":"ok"}
```

### Step 4: Register the plugin with Core

With Core and the companion server both running, in another terminal (from project root):

```bash
python -m external_plugins.companion.register
```

If Core is not on localhost or uses auth:

```bash
CORE_URL=http://your-core:9000 CORE_API_KEY=your-key python -m external_plugins.companion.register
```

You should see: `Registered companion plugin: companion`.

### Step 5: Enable companion routing in Core

Edit **`config/core.yml`** and add (or uncomment) the **`companion`** section. **You must set `keyword`** (or `name`) when companion is enabled; otherwise Core will not route to the companion and will log a warning.

```yaml
companion:
  enabled: true
  plugin_id: companion
  session_id_value: companion
  keyword: Veda   # Required. Use the same as plugin config name if you want "Veda, hello" to work on channels without session_id.
```

- **`keyword`** is used for channels that cannot send `session_id`/`conversation_type`: when the user's message starts with this (e.g. `Veda, how are you?`), Core routes to the companion and strips the prefix. Use the same value as the companion's `name` in `config.yml` if you want that behaviour.
- Restart Core after changing `config/core.yml` (or rely on your config reload if you have it).

After this, the companion is ready to use from the Companion app, WebChat, homeclaw-browser, or any channel that sends the right session/conversation type or the keyword.

---

## 4. Configuration reference

### 4.1 Plugin config (`config.yml`)

| Option | Description | Example values |
|--------|-------------|----------------|
| **name** | Companion's name (used in system prompt and, if matched to Core's `keyword`, for keyword routing). | `Veda`, `Maya` |
| **character** | Who the companion is to the user; defines relationship and tone. | `friend`, `girlfriend`, `boyfriend`, `wife`, `husband`, `sister`, `brother`, `child`, `parent` |
| **language** | Reply language. | `en`, `zh`, `ja`, `ko`, `es`, `fr`, `de`, `pt`, `it`, `ru`, `ar` (or other 2-letter codes) |
| **response_length** | How long replies tend to be. | `short`, `medium`, `long` |
| **idle_days_before_nudge** | After this many days without a user message, the companion may nudge (0 = disabled; requires proactive/scheduler support). | `0`, `3`, `7` |

All of these can be overridden **per user** via the plugin store or the settings API (see [Per-user settings](#6-per-user-settings)).

### 4.2 Core config (`config/core.yml` → `companion`)

| Option | Required | Description |
|--------|----------|-------------|
| **enabled** | Yes | `true` to enable companion routing. |
| **plugin_id** | Yes | Plugin ID to call; use `companion` if you registered with the default script. |
| **session_id_value** | Yes | Value that means "companion" when sent as `session_id`, `conversation_type`, or `channel_name`. Typically `companion`. |
| **keyword** | Yes when enabled | Message-prefix trigger for channels that don't send session. Must be set; otherwise companion routing is disabled and a warning is logged. |

Core does **not** store name, character, or language; those live only in the plugin.

### 4.3 Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| **COMPANION_PORT** | HTTP port for the plugin server. | `3103` |
| **COMPANION_NAME** | Overrides `name` in `config.yml`. | (from config) |
| **COMPANION_STORE_DIR** | Directory for chat and per-user settings files. | `database/companion_store` (under project root) |
| **CORE_URL** | Core base URL (used by plugin for LLM and by register script). | `http://127.0.0.1:9000` |
| **CORE_API_KEY** | API key if Core has `auth_enabled`. | (none) |
| **HOMECLAW_ROOT** | Project root (for default store path). | (auto-detected) |

---

## 5. Character and language

**Character** and **language** are central to making the companion useful: they define who the companion is and how they reply.

### Characters

- **girlfriend** / **boyfriend** — Warm, affectionate/caring, supportive; match the user's energy.
- **wife** / **husband** — Loving, supportive, steady; thoughtful, optionally gently humorous.
- **sister** / **brother** — Caring, playful, supportive; can tease a little and keep it real.
- **child** — Warm, respectful, loving; shows they care about the user.
- **friend** — Warm, conversational, supportive; someone to relax and be themselves with.
- **parent** — Caring, wise, supportive; steady and nurturing without being overbearing.

The plugin builds the system prompt from the chosen character so the model stays in role.

### Languages

Supported codes include: **en**, **zh**, **ja**, **ko**, **es**, **fr**, **de**, **pt**, **it**, **ru**, **ar**. The plugin instructs the model to reply **only** in the configured language (e.g. "只用中文回复。" for `zh`). Other codes use a generic "Always reply in &lt;lang&gt;."

---

## 6. Per-user settings

Each user can override **character**, **language**, **response_length**, and **idle_days_before_nudge** so that the companion is dedicated to their preference.

### Option A: JSON file

Create or edit:

**`database/companion_store/<user_id>_settings.json`**

Example:

```json
{
  "character": "girlfriend",
  "language": "zh",
  "response_length": "short",
  "idle_days_before_nudge": 3
}
```

Omit any key to keep the plugin default (or existing value). The plugin merges this with `config.yml` (per-user overrides win).

### Option B: HTTP API

Plugin base URL default: `http://127.0.0.1:3103`.

- **Get current settings for a user**
  ```bash
  curl http://127.0.0.1:3103/settings/webchat_user
  ```

- **Update settings** (only provided keys are updated)
  ```bash
  curl -X POST http://127.0.0.1:3103/settings/webchat_user \
    -H "Content-Type: application/json" \
    -d '{"character":"girlfriend","language":"zh","response_length":"short"}'
  ```

- **Set idle nudge**
  ```bash
  curl -X POST http://127.0.0.1:3103/settings/webchat_user \
    -H "Content-Type: application/json" \
    -d '{"idle_days_before_nudge":3}'
  ```

---

## 7. How to use the companion

### From the Companion app

The app sends `channel_name: "companion"` and `conversation_type` / `session_id` for companion. No extra setup once Core and the plugin are configured; just use the companion flow in the app.

### From WebChat

1. Open WebChat (e.g. from the channels or homeclaw-browser URL).
2. Use the **Assistant | Companion** dropdown and select **Companion**.
3. Send messages as usual. Those messages go to the companion plugin with `session_id: companion` / `conversation_type: companion`.

### From homeclaw-browser control UI

1. Open the control UI (e.g. homeclaw-browser WebChat at its root URL).
2. Select **Companion** in the **Assistant | Companion** dropdown.
3. Chat; messages are sent with companion session/conversation type.

### From other channels (e.g. WhatsApp, Telegram) via keyword

When the channel cannot send `session_id` or `conversation_type`, the user can still trigger the companion by starting the message with the **keyword** configured in Core (e.g. the companion's name).

- Examples: **`Veda, how are you?`**, **`Veda good night`**, **`Hey Veda`**, **`Hi Veda`**.
- Core detects the prefix, routes to the companion, and strips the keyword (e.g. sends "how are you?" to the plugin).
- **Requirement:** In `config/core.yml`, `companion.keyword` must be set (e.g. `Veda`) and match how the user will address the companion.

---

## 8. Plugin API reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| **/health** | GET | Health check. Returns `{"status":"ok"}`. |
| **/run** | POST | Used by Core to run the "chat" capability. Body: PluginRequest (e.g. `user_id`, `user_input`, `metadata`). Returns PluginResult with `text` and optional `metadata`. |
| **/settings/{user_id}** | GET | Return per-user settings (character, language, response_length, idle_days_before_nudge). |
| **/settings/{user_id}** | POST | Update per-user settings. Body: JSON with any of `character`, `language`, `response_length`, `idle_days_before_nudge`. Omitted keys are unchanged. |

Registration with Core uses the default **base_url** (e.g. `http://127.0.0.1:3103`) and path **/run**. If you change port or host, re-run the register script with the same base URL (or set `COMPANION_BASE_URL` when registering).

---

## 9. Data storage

- **Chat history:** One file per (user_id, companion_name):  
  `database/companion_store/<user_id>_<companion_name>.json`  
  (or under `COMPANION_STORE_DIR`). Contains `turns` (list of `{role, content}`). This data is **not** in the main user database.
- **Per-user settings:**  
  `database/companion_store/<user_id>_settings.json`  
  (or via GET/POST `/settings/{user_id}`).

All paths are under the project root unless `COMPANION_STORE_DIR` or `HOMECLAW_ROOT` is set.

---

## 10. Troubleshooting

| Issue | What to check |
|-------|----------------|
| **"Companion is enabled but companion.keyword ... is not set"** | In `config/core.yml`, set `companion.keyword` (or `companion.name`) to a non-empty value. Companion routing is disabled until this is set. |
| **Companion never replies / request goes to main assistant** | Ensure Core config has `enabled: true`, `plugin_id: companion`, and `keyword` set. For app/WebChat/browser, ensure the client sends `session_id: companion` or `conversation_type: companion` (or `channel_name: companion`). For keyword, ensure the message starts with the exact keyword (e.g. `Veda, `). |
| **Plugin not found** | Run the register script after starting the companion server. Check Core logs for "Registered companion plugin". Confirm `plugin_id` in Core matches the registered plugin (default `companion`). |
| **Permission denied** | The `user_id` in the request must exist in `config/user.yml`. Add it under `users` with the appropriate channel identifiers. |
| **Wrong language or character** | Check plugin `config.yml` and, if used, per-user settings (`_settings.json` or POST `/settings/{user_id}`). Character and language are applied in the system prompt on every request. |
| **Companion server not reachable** | Ensure the server is running (`python -m external_plugins.companion.server`) and that `COMPANION_PORT` (default 3103) is not in use by another process. Core must be able to reach the plugin's base_url (e.g. `http://127.0.0.1:3103`). |
| **LLM errors / no reply** | Plugin calls Core's `POST /api/plugins/llm/generate`. Ensure Core is up, main LLM is configured, and if Core has `auth_enabled`, set `CORE_API_KEY` when starting the companion server. |

For more on design and separation of data, see [CompanionFeatureDesign.md](../../docs_design/CompanionFeatureDesign.md).
