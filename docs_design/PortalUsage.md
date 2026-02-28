# Using the Portal (Web and Companion)

The **Portal** is HomeClaw’s local config and onboarding server. You can use it from a **web browser** on the same machine, or from the **Companion app** (which reaches it via Core).

---

## 1. What the Portal does

- **Manage config** — Edit Core, LLM, Memory/KB, Skills & Plugins, Users, and Friend presets (YAML; comments preserved).
- **Guide to install** — Step-by-step checks: Python, dependencies, Node.js, llama.cpp, GGUF models, and an optional doctor run.
- **Start Core** — From the Dashboard, start or stop the Core process.
- **Start channel** — List channels and start a channel (e.g. Telegram, WebChat) with one click.

---

## 2. Using the Portal from a web browser (local)

Use this when you are on the **same machine** as the project (e.g. your dev machine or server).

### 2.1 Start the Portal

From the project root:

```bash
python -m portal
```

Or, if the repo is run via `main`:

```bash
python -m main portal
```

By default the Portal listens on **http://127.0.0.1:18472**. Override with env:

- `PORTAL_HOST` (default: 127.0.0.1)
- `PORTAL_PORT` (default: 18472)

### 2.2 First-time setup and login

1. Open **http://127.0.0.1:18472** in a browser.
2. If no admin account exists, you are sent to **Set admin account**: choose a **username** and **password**. These are stored in `config/portal_admin.yml` (or use `PORTAL_ADMIN_USERNAME` / `PORTAL_ADMIN_PASSWORD` for dev).
3. After setup you are sent to **Log in**. Use the same username and password.
4. After login you land on the **Dashboard**.

### 2.3 The four areas (nav bar)

| Link | What it does |
|------|----------------|
| **Dashboard** | Overview; **Start** / **Stop** for Core; links to Guide and Manage settings. |
| **Start channel** | List of channels (e.g. telegram, webchat); **Start &lt;name&gt;** starts that channel. Start Core from the Dashboard first if needed. |
| **Guide to install** | Step-by-step checks (Python, deps, Node, llama.cpp, GGUF, doctor). Use **Next** / **Back** to move. |
| **Manage settings** | Tabs: Core, LLM, Memory & KB, Skills & Plugins, Users, Friend presets. Edit and save; sensitive fields show as `***`. |

### 2.4 Start Core and channels

- **Dashboard** → **Start** starts Core (`python -m main start`). **Stop** sends a shutdown request to Core.
- **Start channel** → pick a channel and click **Start &lt;channel&gt;** to run that channel (e.g. `python -m channels.run telegram`).

Core and channels run as separate processes; the Portal keeps running.

---

## 3. Using the Portal from the Companion app (remote)

Use this when you manage HomeClaw **from your phone or another device** via the Companion app. Companion does **not** talk to the Portal directly; it goes through **Core**, which proxies to the Portal.

### 3.1 Prerequisites

1. **Portal is running** on the same machine as Core (e.g. `python -m portal`).
2. **Core is running** and can reach the Portal (same host).
3. **Core is configured to use the Portal:**
   - In `config/core.yml` (or env), set:
     - `portal_url`: base URL of the Portal (e.g. `http://127.0.0.1:18472`)
     - `portal_secret`: a shared secret (e.g. 32 random characters)
   - **Portal** must use the **same** secret:
     - Env: `PORTAL_SECRET=<same value>`, or
     - File: `config/portal_secret.txt` with the same value on the first line (recommended to add to `.gitignore`).

Generate the secret once and put it in both places. Without this, Companion cannot use “Core setting (Portal)”.

### 3.2 In the Companion app

1. Open **Settings**.
2. Set **Core URL** to the address of your Core (e.g. `http://192.168.1.10:9000` or your public URL). Save if needed.
3. Tap **Core setting (Portal)**.
4. Enter your **Portal admin** username and password (same as in section 2.2; from `config/portal_admin.yml` or env).
5. Tap **Log in**.
   - If credentials are wrong, you see “Invalid username or password”.
   - If correct, a **WebView** opens and loads the Portal (via Core’s `/portal-ui`). You see the same Portal UI (Dashboard, Start channel, Guide, Manage settings) inside the app.
6. Use the Portal as usual inside the WebView. Use the **close / Log out** button in the app bar to leave; your session is cleared and the next time you tap **Core setting (Portal)** you will need to log in again.

### 3.3 Notes for Companion

- **Same credentials** as in the browser: the Portal admin account (username + password) is the same everywhere.
- **Token in URL** — The app sends your auth as a token in the URL (e.g. `/portal-ui?token=...`). Core validates it and proxies requests to the Portal. Do not share screenshots or URLs that contain the token.
- **Start Core first** — If Core is not running, you cannot open the Portal from Companion. Start Core (and Portal) on the server, then use Companion to open “Core setting (Portal)”.

---

## 4. When to use which

| Situation | Use |
|-----------|-----|
| On the same machine as the project (desktop, server) | **Web browser** → http://127.0.0.1:18472 (or your PORTAL_HOST:PORT). |
| On phone/tablet or another machine, Core reachable | **Companion app** → Settings → **Core setting (Portal)** → log in with Portal admin. |
| Only changing Core URL / API key / chat users from Companion | You can still use **Manage Core (core.yml & user.yml)** in Settings for the native config screen; use **Core setting (Portal)** when you want the full Portal UI (guide, start channel, all config tabs). |

---

## 5. Config reference

| Item | Where | Purpose |
|------|--------|---------|
| **Portal URL** | Browser | Default http://127.0.0.1:18472. Override: `PORTAL_HOST`, `PORTAL_PORT`. |
| **Admin account** | First visit to Portal | Stored in `config/portal_admin.yml`. Override: `PORTAL_ADMIN_USERNAME`, `PORTAL_ADMIN_PASSWORD`. |
| **portal_url** | Core: `config/core.yml` or `PORTAL_URL` | Base URL of the Portal so Core can proxy config and `/portal-ui`. |
| **portal_secret** | Core: `config/core.yml` or `PORTAL_SECRET` | Secret Core sends to Portal (header `X-Portal-Secret`). Must match Portal’s secret. |
| **Portal secret** | Portal: `PORTAL_SECRET` env or `config/portal_secret.txt` | Same value as Core’s `portal_secret`. Used to allow requests from Core. |

**Related docs:** [CorePortalDesign.md](CorePortalDesign.md), [CorePortalImplementationPlan.md](CorePortalImplementationPlan.md).
