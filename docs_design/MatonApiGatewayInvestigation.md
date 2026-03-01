# Maton API Gateway — investigation and HomeClaw integration

This doc explains how the [Maton API Gateway](https://github.com/maton-ai/api-gateway-skill) works with [maton.ai](https://www.maton.ai/), how it is used in **OpenClaw** (ClawHub / clawdbot), and how to leverage it in **HomeClaw** as a skill or plugin.

**References:**

- **Maton API Gateway skill (OpenClaw):** [github.com/maton-ai/api-gateway-skill](https://github.com/maton-ai/api-gateway-skill)
- **Maton:** [maton.ai](https://www.maton.ai/) — sign up, get API key, connect services (OAuth)
- **HomeClaw Outlook skill:** `skills/outlook-api-1.0.3/` — already uses Maton gateway for Microsoft Graph

---

## 1. What is the Maton API Gateway?

Maton provides an **API gateway with managed OAuth**: you call **native third-party APIs** (Slack, HubSpot, Outlook, Google Workspace, Notion, Airtable, etc.) through a **single API key** (`MATON_API_KEY`). Maton handles OAuth tokens for each service; you only manage one key and “connections” per app.

### Two base URLs

| Purpose | Base URL | Use |
|--------|----------|-----|
| **API calls** | `https://gateway.maton.ai` | Call third-party APIs: `GET/POST/PUT/PATCH/DELETE https://gateway.maton.ai/{app}/{native-api-path}` with `Authorization: Bearer MATON_API_KEY`. |
| **Connection management** | `https://ctrl.maton.ai` | List/create/get/delete OAuth “connections” per app. Create connection returns a URL to open in a browser to complete OAuth. |

### Request format

- **URL:** `https://gateway.maton.ai/{app}/{native-api-path}`
  - `{app}` = service name (e.g. `slack`, `outlook`, `hubspot`, `google-mail`, `notion`). **Must** match the app name so the gateway knows which OAuth connection to use.
  - `{native-api-path}` = the actual API path (e.g. `api/chat.postMessage` for Slack, `v1.0/me/messages` for Outlook).
- **Auth:** `Authorization: Bearer MATON_API_KEY` (your Maton key; gateway injects the right OAuth token for the target service).
- **Optional:** `Maton-Connection: {connection_id}` if you have multiple connections for the same app.

### Security model

- **MATON_API_KEY** authenticates you to Maton but **does not** grant access to third-party services by itself.
- Each service requires **explicit OAuth** by the user via Maton’s connect flow (open URL in browser, sign in, authorize).
- Access is scoped to **connections the user has authorized**. So: one key for Maton; per-app access only after connecting that app.

---

## 2. How it works with maton.ai

### Step 1: Get API key

1. Sign in or create an account at [maton.ai](https://www.maton.ai/).
2. Go to [maton.ai/settings](https://www.maton.ai/settings).
3. Copy your **API key** and set it where your app runs: `export MATON_API_KEY="YOUR_API_KEY"` (or in config for a plugin).

### Step 2: Connect an app (OAuth)

1. **Create connection:**  
   `POST https://ctrl.maton.ai/connections` with body `{"app": "slack"}` (or `outlook`, `hubspot`, etc.) and header `Authorization: Bearer MATON_API_KEY`.
2. **Response** includes a `url` (e.g. `https://connect.maton.ai/?session_token=...`). Open this URL in a browser.
3. Complete the OAuth flow (sign in to Slack/Outlook/etc. and authorize). After that, the connection status becomes **ACTIVE**.
4. **List connections:**  
   `GET https://ctrl.maton.ai/connections?app=slack&status=ACTIVE` to see active connections.

### Step 3: Call the third-party API via gateway

- **Example (Slack):**  
  `POST https://gateway.maton.ai/slack/api/chat.postMessage`  
  Headers: `Authorization: Bearer MATON_API_KEY`, `Content-Type: application/json`  
  Body: `{"channel": "C0123456", "text": "Hello!"}`

- **Example (Outlook):**  
  `GET https://gateway.maton.ai/outlook/v1.0/me/messages`  
  Header: `Authorization: Bearer MATON_API_KEY`

The gateway forwards the request to the real API (e.g. Slack, Microsoft Graph) and injects the OAuth token for the chosen connection.

### Supported services (examples)

From the [Maton SKILL.md](https://github.com/maton-ai/api-gateway-skill): Slack, HubSpot, Salesforce, Google Workspace (Gmail, Calendar, Sheets, Docs, Drive, etc.), Notion, Airtable, Outlook, Microsoft Excel/Teams/To Do, Trello, Stripe, GitHub, Calendly, Mailchimp, Twilio, and many more (100+). Each has an **app name** (e.g. `outlook`, `google-mail`, `slack`) used in the URL path.

---

## 3. How it is used in OpenClaw

The Maton repo is an **OpenClaw-style skill** (ClawHub / clawdbot):

- **SKILL.md** with YAML frontmatter: `name`, `description`, `compatibility`, `metadata` (author, version, `clawdbot:` emoji, homepage), `requires.env: MATON_API_KEY`.
- **Body:** Full documentation: base URL, auth, connection management (list/create/get/delete), supported services table, examples (Slack, HubSpot, Google Sheets, Salesforce, Airtable, Notion, Stripe), code snippets (Python, JavaScript), error handling, rate limits, tips.
- **No scripts** in the repo — it’s **instruction-only**: the model (or user) is expected to call the gateway via HTTP (e.g. with `exec` and a Python one-liner, or a generic HTTP tool if available).

So in OpenClaw, the “api-gateway” skill mainly **teaches the LLM** the pattern (URL shape, auth, connection flow); the actual HTTP calls are done by whatever tool OpenClaw has (e.g. exec, or a built-in HTTP tool).

---

## 4. HomeClaw: how to leverage it

HomeClaw already has one **service-specific** skill that uses Maton: **outlook-api-1.0.3** (Microsoft Graph via `gateway.maton.ai/outlook/...`). To support **all** Maton-backed services (Slack, HubSpot, Notion, etc.) in one place, you can add either a **skill** or a **plugin** (or both).

### Option A: Skill only (instruction + run_skill script)

- **Add a skill** (e.g. `skills/maton-api-gateway-1.0.0/`) with:
  - **SKILL.md** adapted from [Maton’s SKILL.md](https://github.com/maton-ai/api-gateway-skill): name, description, trigger patterns, instruction, and body (base URL, auth, connection management, supported services, examples). This gives the LLM the full pattern.
  - **Optional script** `scripts/request.py`: takes args `(app, path, method, body_json)` and performs one HTTP request to `https://gateway.maton.ai/{app}/{path}` with `Authorization: Bearer $MATON_API_KEY`. Then the LLM can call **run_skill**(skill_name=`maton-api-gateway-1.0.0`, script=`request.py`, args=[...]).
- **Requires:** `MATON_API_KEY` set in the **environment** where Core runs, or `maton_api_key` in the skill’s **config.yml** (`skills/maton-api-gateway-1.0.0/config.yml`); env overrides config. If you use a non-empty **tools.run_skill_allowlist** in `config/core.yml`, add `request.py` so the script can run.
- **Workflow:** User asks “Send a Slack message” → LLM uses skill → run_skill with app=`slack`, path=`api/chat.postMessage`, method=POST, body=... → script calls gateway → returns result to user.

### Option B: Plugin with a tool

- **Plugin** (e.g. `plugins/maton_gateway/` or external) that registers one tool, e.g. **maton_request**(app, path, method, body).
- The plugin reads **MATON_API_KEY** from plugin config or Core config (or env) and sends HTTP requests to `https://gateway.maton.ai/{app}/{path}`.
- **Advantages:** API key can live in config (no need to set env for Core); single place to maintain; can add connection-management helpers (list/create connections) as extra tools or capabilities.
- **Workflow:** User asks “Add a HubSpot contact” → LLM calls maton_request(app=`hubspot`, path=`crm/v3/objects/contacts`, method=POST, body=...) → plugin calls gateway → returns result.

### Option C: Skill only, no script (instruction + exec)

- Same SKILL.md as in A, but **no** request.py. The LLM is instructed to use **exec** (if available) to run a short Python/curl one-liner that calls the gateway. This depends on exec allowlist and the model generating correct commands.
- **Simpler** to add (no script, no allowlist entry) but **less reliable** (exec might be disabled or restricted; model may generate wrong commands).

**Recommendation:** Implement **Option A** (skill + optional request.py) so HomeClaw has one “Maton API Gateway” skill that works for any supported service; optionally add **Option B** later if you want the key in config and a stable tool interface.

---

## 5. Detailed workflow (end-to-end)

### 5.1 First-time setup (one-time per user/machine)

1. **Sign up at maton.ai** and copy **API key** from [maton.ai/settings](https://www.maton.ai/settings).
2. **Set key** where Core runs:  
   - **Skill (Option A):** `export MATON_API_KEY="..."` in the environment of the process that runs Core (e.g. systemd, terminal).  
   - **Plugin (Option B):** Put key in plugin config or Core config (e.g. `plugins.maton_gateway.maton_api_key` or a secret env).
3. **Connect an app** (e.g. Slack):  
   - Call `POST https://ctrl.maton.ai/connections` with `{"app": "slack"}` and Bearer token.  
   - Open the returned `url` in a browser and complete OAuth.  
   - (Optional) Implement a small “connection manager” script or tool that does POST and prints the URL for the user to open.

### 5.2 Per-request flow (e.g. “Send a Slack message”)

1. **User:** “Send a Slack message to #general: Hello team!”
2. **LLM** (with Maton API Gateway skill loaded):
   - Infers app=`slack`, path=`api/chat.postMessage`, method=POST, body=`{"channel": "C0123456", "text": "Hello team!"}` (channel id might come from a previous “list channels” call or from user context).
   - Either:
     - **With script:** Calls **run_skill**(skill_name=`maton-api-gateway-1.0.0`, script=`request.py`, args=[`slack`, `api/chat.postMessage`, `POST`, `{"channel":"C0123456","text":"Hello team!"}`]).
     - **With plugin:** Calls **maton_request**(app=`slack`, path=`api/chat.postMessage`, method=`POST`, body=`{"channel":"C0123456","text":"Hello team!"}`).
3. **Skill script or plugin:** Sends `POST https://gateway.maton.ai/slack/api/chat.postMessage` with `Authorization: Bearer MATON_API_KEY` and body; gateway injects Slack OAuth token and forwards to Slack API.
4. **Response** from Slack is returned to the script/plugin, then to the LLM, then to the user (e.g. “Message sent.”).

### 5.3 Other examples (same pattern)

- **Outlook:** Already covered by **outlook-api-1.0.3** (same gateway, app=`outlook`). User: “List my last 10 emails” → path=`v1.0/me/messages?$top=10`, method=GET.
- **HubSpot:** Create contact → app=`hubspot`, path=`crm/v3/objects/contacts`, method=POST, body=`{"properties": {"email": "...", "firstname": "...", "lastname": "..."}}`.
- **Notion:** Query database → app=`notion`, path=`v1/databases/{id}/query`, method=POST, body=`{}`.
- **Google Sheets:** Read range → app=`google-sheets`, path=`v4/spreadsheets/{id}/values/Sheet1!A1:B2`, method=GET.

The **skill body** (and optional references) documents these per-service paths; the **script or plugin** only needs (app, path, method, body).

---

## 6. Summary

| Topic | Summary |
|-------|---------|
| **Maton** | [maton.ai](https://www.maton.ai/) — one API key, OAuth per app via “connections”; gateway at `gateway.maton.ai`, control at `ctrl.maton.ai`. |
| **OpenClaw** | Uses the repo as an **instruction-only skill** (SKILL.md); LLM follows the doc to call APIs via gateway (e.g. with exec or an HTTP tool). |
| **HomeClaw** | **outlook-api-1.0.3** already uses Maton for Outlook. To support all services: add **maton-api-gateway** skill (SKILL.md + optional request.py) and/or a **plugin** with a **maton_request** tool. |
| **Workflow** | Get key → connect apps (OAuth via ctrl.maton.ai) → call `gateway.maton.ai/{app}/{path}` with Bearer key; script or plugin does the HTTP. |
| **Output** | Prefer **plain text or Markdown** in the reply; if the tool returns large JSON, the model can summarize or write to **output/** (see per-user sandbox doc). |

Implementing the **skill** (Option A) with **request.py** gives a single, reusable way for the LLM to call any Maton-backed service from HomeClaw, consistent with the existing Outlook skill and the OpenClaw usage of the same gateway.
