# Friends Plugin — Detailed Guide

The **Friends** plugin adds a dedicated conversational persona (girlfriend, boyfriend, friend, parent, etc.) with its own chat history and settings. All friends data is stored **separately** from the main assistant — it does not touch the main user database. Character and language settings make the persona interesting and useful by defining who they are and how they reply.

**Design doc:** [docs_design/CompanionFeatureDesign.md](../../docs_design/CompanionFeatureDesign.md)

---

## Table of contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Setup (step by step)](#3-setup-step-by-step)
4. [Configuration reference](#4-configuration-reference)
5. [Character and language](#5-character-and-language)
6. [Per-user settings](#6-per-user-settings)
7. [How to use the friends persona](#7-how-to-use-the-friends-persona)
8. [Plugin API reference](#8-plugin-api-reference)
9. [Data storage](#9-data-storage)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

- **What it does:** Provides a separate chat thread with a friend/persona. The persona uses Core's LLM to reply; chat history and settings are stored only in the plugin's store.
- **Who it's for:** One persona per user; each user can have different character/language (via per-user settings).
- **Where it runs:** As an external HTTP plugin (this folder). Core only **routes** requests to the plugin when the user is in "companion" mode (Companion app, WebChat companion tab, etc.); Core does not store name, character, or language.

---

## 2. Prerequisites

- **Python 3.8+** with `uvicorn`, `fastapi`, `pyyaml`, `httpx` (install if missing: `pip install uvicorn fastapi pyyaml httpx`).
- **HomeClaw Core** running and reachable (for LLM and for registering the plugin).
- **User allowlist:** When the Companion app is in **system mode** (not combined with a user), Core sends `user_id: "companion"` to the plugin; that must be allowed by Core. For combined-with-user mode, that user must exist in `config/user.yml`.

---

## 3. Setup (step by step)

### Step 1: Start HomeClaw Core

From the project root:

```bash
python -m core.core
```

Leave it running (default port 9000). For system (uncombined) mode, Core uses the special user **"companion"**; no entry in user.yml is required for that. For combined-with-user mode, ensure `config/user.yml` includes the user IDs you will use.

### Step 2: Configure the Friends plugin

Edit **`external_plugins/friends/config.yml`**:

```yaml
name: Veda
character: friend    # girlfriend, boyfriend, wife, husband, sister, brother, child, friend, parent
language: en         # en, zh, ja, ko, es, fr, de, pt, it, ru, ar, ...
response_length: medium   # short, medium, long
idle_days_before_nudge: 0 # 0 = disabled
```

Set `name` to the persona's name (used in prompts and, if you use keyword routing in Core, as the trigger). Set `character` and `language` as desired.

### Step 3: Start the Friends plugin server

From the **project root**:

```bash
python -m external_plugins.friends.server
```

Default port: **3103**. To use another port:

```bash
FRIENDS_PORT=3104 python -m external_plugins.friends.server
```

Check that it's up:

```bash
curl http://127.0.0.1:3103/health
# → {"status":"ok"}
```

### Step 4: Register the plugin with Core

With Core and the friends server both running, in another terminal (from project root):

```bash
python -m external_plugins.friends.register
```

If Core is not on localhost or uses auth:

```bash
CORE_URL=http://your-core:9000 CORE_API_KEY=your-key python -m external_plugins.friends.register
```

You should see: `Registered friends plugin: friends`.

### Step 5: Enable companion routing in Core

Edit **`config/core.yml`** and add (or uncomment) the **`companion`** section. **You must set `keyword`** (or `name`) when companion is enabled; otherwise Core will not route to the plugin and will log a warning.

```yaml
companion:
  enabled: true
  plugin_id: friends
  session_id_value: friend
  keyword: Veda   # Required. Use the same as plugin config name if you want "Veda, hello" to work on channels without session_id.
```

- **`plugin_id`** must be **`friends`** so Core calls this plugin when the user is in companion mode (system user "companion").
- **`keyword`** is used for channels that cannot send `session_id`/`conversation_type`: when the user's message starts with this (e.g. `Veda, how are you?`), Core routes to the Friends plugin and strips the prefix.
- Restart Core after changing `config/core.yml` (or rely on your config reload if you have it).

After this, the friends persona is ready to use from the Companion app, WebChat, homeclaw-browser, or any channel that sends the right session/conversation type or the keyword.

---

## 4. Configuration reference

### 4.1 Plugin config (`config.yml`)

| Option | Description | Example values |
|--------|-------------|----------------|
| **name** | Persona's name (used in system prompt and, if matched to Core's `keyword`, for keyword routing). | `Veda`, `Maya` |
| **character** | Who the persona is to the user; defines relationship and tone. | `friend`, `girlfriend`, `boyfriend`, `wife`, `husband`, `sister`, `brother`, `child`, `parent` |
| **language** | Reply language. | `en`, `zh`, `ja`, `ko`, `es`, `fr`, `de`, `pt`, `it`, `ru`, `ar` (or other 2-letter codes) |
| **response_length** | How long replies tend to be. | `short`, `medium`, `long` |
| **idle_days_before_nudge** | After this many days without a user message, the persona may nudge (0 = disabled; requires proactive/scheduler support). | `0`, `3`, `7` |

All of these can be overridden **per user** via the plugin store or the settings API (see [Per-user settings](#6-per-user-settings)).

### 4.2 Core config (`config/core.yml` → `companion`)

| Option | Required | Description |
|--------|----------|-------------|
| **enabled** | Yes | `true` to enable companion routing. |
| **plugin_id** | Yes | Plugin ID to call; use **`friends`** for this plugin. |
| **session_id_value** | Yes | Value that means "Friend chat" when sent as `session_id`, `conversation_type`, or `channel_name`. Default `friend`. |
| **keyword** | Yes when enabled | Message-prefix trigger for channels that don't send session. Must be set; otherwise companion routing is disabled and a warning is logged. |

Core does **not** store name, character, or language; those live only in the plugin.

### 4.3 Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| **FRIENDS_PORT** | HTTP port for the plugin server. | `3103` |
| **FRIENDS_NAME** / **FRIENDS_PERSONA_NAME** | Overrides `name` in `config.yml`. | (from config) |
| **FRIENDS_STORE_DIR** | Directory for chat and per-user settings files. | `database/friends_store` (under project root) |
| **FRIENDS_BASE_URL** | Base URL for registration (e.g. if behind a proxy). | `http://127.0.0.1:3103` |
| **CORE_URL** | Core base URL (used by plugin for LLM and by register script). | `http://127.0.0.1:9000` |
| **CORE_API_KEY** | When Core has **auth_enabled: true** in `config/core.yml`, Core requires an API key for `/inbound` and plugin APIs. Set **CORE_API_KEY** to the **same value** as Core's **auth_api_key** (from core.yml) so the Friends plugin can call Core (LLM, memory add/search). If auth is disabled, leave unset. See docs_design/RemoteAccess.md. | (none) |
| **HOMECLAW_ROOT** | Project root (for default store path). | (auto-detected) |

---

## 5. Character and language

**Character** and **language** are central to making the persona useful: they define who the persona is and how they reply.

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

Each user can override **character**, **language**, **response_length**, and **idle_days_before_nudge** so that the persona is dedicated to their preference.

### Option A: JSON file

Create or edit:

**`database/friends_store/<user_id>_settings.json`**

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
  curl http://127.0.0.1:3103/settings/companion
  ```

- **Update settings** (only provided keys are updated)
  ```bash
  curl -X POST http://127.0.0.1:3103/settings/companion \
    -H "Content-Type: application/json" \
    -d '{"character":"girlfriend","language":"zh","response_length":"short"}'
  ```

- **Set idle nudge**
  ```bash
  curl -X POST http://127.0.0.1:3103/settings/companion \
    -H "Content-Type: application/json" \
    -d '{"idle_days_before_nudge":3}'
  ```

---

## 7. How to use the friends persona

### From the Companion app

The app sends `channel_name: "companion"` and `conversation_type` / `session_id` for companion. No extra setup once Core and the Friends plugin are configured; just use the companion flow in the app.

### From WebChat

1. Open WebChat (e.g. from the channels or homeclaw-browser URL).
2. Use the **Assistant | Companion** dropdown and select **Companion**.
3. Send messages as usual. Those messages go to the Friends plugin with `session_id: companion` / `conversation_type: companion`.

### From homeclaw-browser control UI

1. Open the control UI (e.g. homeclaw-browser WebChat at its root URL).
2. Select **Companion** in the **Assistant | Companion** dropdown.
3. Chat; messages are sent with companion session/conversation type.

### From other channels (e.g. WhatsApp, Telegram) via keyword

When the channel cannot send `session_id` or `conversation_type`, the user can still trigger the persona by starting the message with the **keyword** configured in Core (e.g. the persona's name).

- Examples: **`Veda, how are you?`**, **`Veda good night`**, **`Hey Veda`**, **`Hi Veda`**.
- Core detects the prefix, routes to the Friends plugin, and strips the keyword (e.g. sends "how are you?" to the plugin).
- **Requirement:** In `config/core.yml`, `companion.keyword` must be set (e.g. `Veda`) and match how the user will address the persona.

---

## 8. Plugin API reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| **/health** | GET | Health check. Returns `{"status":"ok"}`. |
| **/run** | POST | Used by Core to run the "chat" capability. Body: PluginRequest (e.g. `user_id`, `user_input`, `metadata`). Returns PluginResult with `text` and optional `metadata`. |
| **/settings/{user_id}** | GET | Return per-user settings (character, language, response_length, idle_days_before_nudge). |
| **/settings/{user_id}** | POST | Update per-user settings. Body: JSON with any of `character`, `language`, `response_length`, `idle_days_before_nudge`. Omitted keys are unchanged. |

Registration with Core uses the default **base_url** (e.g. `http://127.0.0.1:3103`) and path **/run**. If you change port or host, re-run the register script with the same base URL (or set `FRIENDS_BASE_URL` when registering).

---

## 9. Data storage

- **Chat history:** One file per (user_id, persona_name):  
  `database/friends_store/<user_id>_<persona_name>.json`  
  (or under `FRIENDS_STORE_DIR`). Contains `turns` (list of `{role, content}`). This data is **not** in the main user database.
- **Memory (RAG):** The plugin uses **Core's memory** for the same long-term memory as the main assistant. On each turn it calls Core **POST /api/plugins/memory/add** (to store the user message) and **POST /api/plugins/memory/search** (to retrieve relevant memories and inject them into the prompt). When the app is in system mode (not combined with a user), the plugin uses a dedicated memory user_id `companion_friend` so Friend memories are not mixed with Assistant. Core must have memory enabled (use_memory, Cognee or Chroma).
- **Per-user settings:**  
  `database/friends_store/<user_id>_settings.json`  
  (or via GET/POST `/settings/{user_id}`).

All paths are under the project root unless `FRIENDS_STORE_DIR` or `HOMECLAW_ROOT` is set.

---

## 10. Troubleshooting

| Issue | What to check |
|-------|----------------|
| **"Companion is enabled but companion.keyword ... is not set"** | In `config/core.yml`, set `companion.keyword` (or `companion.name`) to a non-empty value. Companion routing is disabled until this is set. |
| **Persona never replies / request goes to main assistant** | Ensure Core config has `enabled: true`, `plugin_id: friends`, `session_id_value: friend`, and `keyword` set. For app/WebChat/browser, ensure the client sends `session_id: friend` or `conversation_type: friend` (or `channel_name: friend`) so Core routes to the Friends plugin. For keyword, ensure the message starts with the exact keyword (e.g. `Veda, `). |
| **Plugin not found** | Run the register script after starting the friends server. Check Core logs for "Registered friends plugin". Confirm `plugin_id` in Core is **`friends`**. |
| **Permission denied** | When the Companion app is in **system mode** (not combined with a user), Core sends user_id **"companion"** to the plugin; that must be allowed. For combined-with-user mode, the `user_id` in the request must exist in `config/user.yml`. |
| **Wrong language or character** | Check plugin `config.yml` and, if used, per-user settings (`_settings.json` or POST `/settings/{user_id}`). Character and language are applied in the system prompt on every request. |
| **Friends server not reachable** | Ensure the server is running (`python -m external_plugins.friends.server`) and that `FRIENDS_PORT` (default 3103) is not in use by another process. Core must be able to reach the plugin's base_url (e.g. `http://127.0.0.1:3103`). |
| **LLM errors / no reply** | Plugin calls Core's `POST /api/plugins/llm/generate`. Ensure Core is up, main LLM is configured, and if Core has `auth_enabled`, set `CORE_API_KEY` when starting the friends server. |

For more on design and separation of data, see [CompanionFeatureDesign.md](../../docs_design/CompanionFeatureDesign.md).
