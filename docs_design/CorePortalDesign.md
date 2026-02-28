# Core Portal — Unified Config UI, Launch, and Onboarding

This document designs a **Portal**: a small, stable local web server that provides unified configuration management, step-by-step onboarding, and launch of Core and Channels. Config must **not** break or rewrite YAML files and must **not** clear comments. **Remote** management is supported by having Core call the Portal over REST, so the Companion app can manage settings via Core.

---

## 1. Goals

- **Portal** = a **very small web server** that runs **locally**. It:
  - Guides the user through setup (install Python, requirements.txt, Node.js if needed, etc.).
  - Manages all Core-related config: `core.yml`, `llm.yml`, `memory_kb.yml`, `skills_and_plugins.yml`, `user.yml`, `friend_presets.yml`.
  - Lets the user start Core and Channels from the UI.
- **Stability**: When Core is running, the Portal web server **runs together** with Core and must remain stable (same machine, two processes).
- **Local access**: User opens a browser on the machine → Portal web server (e.g. `http://127.0.0.1:8000`) to manage settings and launch Core/Channels.
- **Remote access**: **Companion app** does not talk to the Portal directly. Instead, **Core** uses **REST API to access the Portal**. So: Companion → Core → (Core calls Portal REST API) → Portal. This way the Companion app can **manage settings remotely** (via Core), while the Portal stays local-only and does not need to be exposed to the internet.
- **YAML safety**: only add / remove / edit **fields**; preserve file structure, key order, and **all comments** (ruamel; never full overwrite with `yaml.safe_dump`).

---

## 2. Config Files and Edit Rules

| File | Purpose | Edit rule |
|------|---------|-----------|
| `config/core.yml` | Core server, auth, memory/KB refs, llama_cpp, completion, pinggy, etc. | Merge updates via `Util().update_yaml_preserving_comments()`; already used by Core PATCH, main.py, ui. **Never** replace whole file. |
| `config/llm.yml` | `local_models`, `cloud_models`, `main_llm`, `embedding_llm`, etc. | Same pattern: load full file (ruamel), apply only changed keys, dump. New helper or extend Util for multi-file support. |
| `config/memory_kb.yml` | Memory backend, session, profile, agent_memory, KB, DB. | Same as above. |
| `config/skills_and_plugins.yml` | Skills/plugins/tools settings. | Same as above. |
| `config/user.yml` | `users` list; already has `User.to_yaml()` merge. | Keep using existing merge (ruamel); portal only drives add/edit/remove user. |
| `config/friend_presets.yml` | Friend presets (reminder, note, finder, etc.). | Load → update presets section → dump with ruamel. |

**Invariants:**

- **No full-file overwrite** with a subset of keys (would drop keys and comments).
- **No `yaml.safe_dump`** on the whole file for any of these (strips comments).
- **Whitelist per file**: portal only allows editing keys we define (same idea as `CONFIG_CORE_WHITELIST` in `core/routes/config_api.py`). Unknown keys and comments stay untouched.
- **Sensitive fields**: redact in UI/API (e.g. `auth_api_key`, `api_key` → `***`); on save, treat `***` as “leave existing value” (already done for core PATCH).

---

## 3. Architecture: Portal, Core, and Companion

### 3.1 Portal = small local web server

- The **Portal** is a **very small web server** that:
  - Binds to **127.0.0.1** only (local access; no need to expose it to the network).
  - Serves the web UI for onboarding, config management, and “Start Core / Start Channels”.
  - Exposes a **REST API** for config (GET/PATCH per config file) and optionally for “list channels”, “start channel”, “doctor”, etc.
- It can be started **without** Python being the only way to run it: e.g. `python -m main portal` starts this small server. The important point is that it is a **dedicated, stable** process for the portal; when Core is running, **both** Portal and Core run (Portal does not exit when Core starts).

### 3.2 Run model: Portal and Core together

- **First time:** User starts the Portal (e.g. `python -m main portal`). Portal runs; user does onboarding and config in the browser. From the Portal UI, user clicks “Start Core” → Portal spawns Core (e.g. subprocess or `python -m main start`). Core runs; **Portal keeps running**.
- **Later runs:** User can start Portal first, then “Start Core” from the Portal; or start Core by other means (e.g. systemd, launcher). For **remote management via Companion**, we require that when Core is running, the Portal is **also** running on the same machine so Core can call it. So: start Portal → start Core; both stay up. Portal is the single place that owns config (YAML read/write).

### 3.3 Local access: manage settings via browser

- **Locally**, the user opens a browser on the same machine and goes to the Portal (e.g. `http://127.0.0.1:8000`). No auth needed (localhost only). They can:
  - Follow onboarding (install Python, requirements, etc.).
  - Edit all configs (Core, LLM, Memory/KB, Skills & Plugins, Users, Friend presets).
  - Start Core and Channels.

### 3.4 Remote access: Companion app via Core → Portal

- The **Companion app** (phone/tablet, remote) should be able to **manage settings remotely**. The Portal is **not** exposed to the internet. Instead:
  - **Companion** talks only to **Core** (over the existing channel: Core’s public URL or Tailscale, with auth).
  - **Core** talks to the **Portal** over REST (localhost, e.g. `http://127.0.0.1:8000`).
- Flow:
  1. Companion calls Core: e.g. `GET /api/config/core` or `PATCH /api/config/core`.
  2. Core **proxies** the request to the Portal: e.g. `GET http://127.0.0.1:8000/api/config/core`, or `PATCH http://127.0.0.1:8000/api/config/core` with body.
  3. Portal reads or updates the YAML (merge, comment-preserving) and returns JSON.
  4. Core returns the result to the Companion.
- So: **remote management of settings = Companion → Core → Portal**. The Portal stays local; only Core is exposed. Core needs a config key for the Portal base URL (e.g. `portal_url: http://127.0.0.1:8000` in `core.yml` or env). If `portal_url` is set, Core’s config (and optionally users, etc.) API can forward to the Portal; if not set, Core can keep current behavior (Core reads/writes files itself) for backward compatibility.

### 3.5 Auth (detailed in Section 8)

- **Portal (local):** Single **admin with password** (Section 8.1). Only that admin can access the Portal web UI.
- **Core → Portal:** Secured with a **shared secret** (Section 8.5).
- **Companion → Core (config):** Only **admin/super user** can manage settings; design in Section 8.7.

---

## 4. Portal REST API (for Core)

So that Core can proxy Companion requests to the Portal, the Portal exposes a small REST API (localhost only). Core calls these when `portal_url` is configured.

| Method / Path | Purpose |
|---------------|---------|
| `GET /api/config/core` | Return current core config (whitelisted keys; redact secrets). Same shape as Core’s current GET. |
| `PATCH /api/config/core` | Merge body into core.yml (comment-preserving). Return `{ "result": "ok" }`. |
| `GET /api/config/llm` | Return llm.yml content (or whitelisted subset). |
| `PATCH /api/config/llm` | Merge into llm.yml. |
| (Optional) `GET/PATCH /api/config/memory_kb`, `skills_and_plugins`, `friend_presets` | Same idea for other files. |
| `GET /api/config/users` | Return users from user.yml. |
| `POST/PATCH/DELETE /api/config/users` | Add/update/remove user (Portal calls Util / User.to_yaml). |
| (Optional) `GET /api/portal/channels` | List available channels (scan `channels/*/channel.py`). |
| (Optional) `POST /api/portal/doctor` | Run doctor checks; return report. |

Core’s existing `/api/config/core` and `/api/config/users` handlers can be updated to: if `portal_url` is set, **forward** the request to Portal and return the response; otherwise keep current behavior (Core reads/writes files). That way Companion and other clients do not need to change; only Core’s backend switches to “proxy to Portal” when the Portal is in use.

---

## 5. What the Portal Does (Features)

1. **Onboarding (step-by-step)**  
   - Check Python version (e.g. ≥3.9).  
   - Check/create venv, run `pip install -r requirements.txt`.  
   - Optionally check Node.js if any channel or tool needs it.  
   - Verify `config/` exists and key files exist (or create from templates if we add them).  
   - “Doctor” light checks: workspace_dir, skills_dir, optional LLM reachability (once Core or llama.cpp is up).

2. **Config UI (unified)**  
   - Tabs or sections per file: Core, LLM, Memory/KB, Skills & Plugins, Users, Friend presets.  
   - Each section: load current YAML (via backend), show form or structured editor; on save, **merge** only the edited fields (ruamel, preserve comments).  
   - Sensitive fields shown as `***`; `***` on save means “do not change”.

3. **Launch Core**  
   - Button “Start Core”: same as current UI — subprocess or thread running `core.main` (or `python -m main start` in a subprocess).  
   - Show status: “Core running at http://…” or “Core not running” (e.g. poll `/ready`).

4. **Launch Channels**  
   - List channels (scan `channels/*/channel.py`).  
   - “Start Core” + “Start channel X” (and optionally “Start all channels”). Same as current Portal tab.

5. **Optional**  
   - Link to “Companion / WebChat” (Core’s `/ui`) when Core is running.  
   - “Doctor” report in the portal (reuse `main.doctor` logic).

---

## 6. Technical Notes

### 6.1 YAML editing in the Portal

- **Portal** is the single writer for the six config files when the design is “Core proxies to Portal”. All edits go through the Portal (local UI or via Core proxy).
- **core.yml:** Use `Util().update_yaml_preserving_comments()` (same as today). Portal implements GET/PATCH for core and uses this for merge.
- **llm.yml, memory_kb.yml, skills_and_plugins.yml, friend_presets.yml:** Add a small layer: load with **ruamel**, apply **whitelisted** updates, dump. Per-file whitelists so we only touch known keys.
- **user.yml:** Use existing `User.to_yaml()` merge; Portal’s user API calls Util add/update/remove and save.

### 6.2 Portal process and entrypoint

- The Portal is a **small web server** (e.g. FastAPI or FastAPI + Gradio). Entrypoint: **`python -m main portal`** (main.py adds a `portal` command). It only runs the portal server; no need for a separate runtime—Python runs the server. The emphasis is on “small and stable”: minimal dependencies, single responsibility (serve UI + REST API for config and launch).
- Code can live in `ui/homeclaw.py` (extended) or a new `ui/portal/` module; the server binds to **127.0.0.1** and a configurable port (e.g. 8000). When Core is running, both processes run; Core knows Portal’s URL via `portal_url` in config and forwards Companion config requests to the Portal.

### 6.3 Portal auth (see Section 8)

- Portal requires **one admin user with password** (Section 8.1). Core → Portal is secured with a shared secret (Section 8.5).

---

## 7. Phased Plan

| Phase | Scope |
|-------|--------|
| **1** | Consolidate YAML write paths in the Portal: all six files updated via ruamel merge (no full overwrite, no comment stripping). Add whitelists for llm, memory_kb, skills_and_plugins, friend_presets. Portal exposes REST API for config (GET/PATCH per file) and users. |
| **2** | Portal web server: onboarding steps (Python, venv, requirements.txt, optional Node), config UI (all six files), “Launch Core” and “Launch Channels”. Portal runs as `python -m main portal`, binds 127.0.0.1, runs **together** with Core (both processes up when Core is running). |
| **3** | Core → Portal proxy: add `portal_url` to core.yml. When set, Core’s `/api/config/core` and `/api/config/users` (and optionally other config endpoints) **forward** to the Portal. Companion app can then **manage settings remotely** via Core (Companion → Core → Portal). |
| **4** | Optional: when user runs `python -m main start`, optionally start or prompt to start the Portal so both run together; or open browser to Portal URL. |

---

## 8. Detailed design: Web UI, auth, security, APIs, Companion

This section addresses: (1) Web UI structure and admin password, (2) guide to install, (3) start Core, (4) start channel, (5) securing Core → Portal, (6) APIs Core uses to manage settings, (7) how Core exposes these to an admin/super user via Companion, (8) Companion settings UI (WebView vs native).

### 8.1 Web UI structure and single admin with password

**Four areas of the Portal web UI:**

1. **Manage settings** — Tabs/sections for each config file: Core, LLM, Memory/KB, Skills & Plugins, Users, Friend presets. Forms or structured editors; save = merge-only (comment-preserving). Sensitive fields shown as `***`; `***` on save means “do not change”.
2. **Guide to install** — Step-by-step onboarding: check Python version, venv, `pip install -r requirements.txt`, optional Node.js, config dir and key files, optional “doctor” checks. Show status and next step; user proceeds at their own pace.
3. **Start Core** — Button to start Core (subprocess); status line “Core running at …” or “Core not running” (e.g. poll Core’s `/ready`).
4. **Start channel** — List of channels (from `channels/*/channel.py`); buttons “Start Core” (if not running) and “Start channel X”. Optional “Start all channels”.

**Access control:** The Portal is used by **one admin only**, protected by **username and password**.

- **Storage:** Store admin **username** and **password** (password as hash) in a small config file (e.g. `config/portal_admin.yml`) or env (`PORTAL_ADMIN_USERNAME`, `PORTAL_ADMIN_PASSWORD`). First-time setup: if not set, show “Set admin account” (username + password); once set, all subsequent access requires both.
- **Flow:** User opens Portal in browser → login screen: **username** + **password** → session (cookie or token) → access to the four areas. Session timeout optional (e.g. 24h or “remember until browser close”). Same credentials are used for Companion “Core setting” (Section 8.7): user enters this username and password in the app to access the proxied Portal UI.
- **Local only:** Portal still binds 127.0.0.1; only someone with physical or SSH access to the machine can open the Portal. The credentials protect against other local users or accidental access.

### 8.2 Guide user to install

- Implemented inside the “Guide to install” area of the Web UI (see 8.1). Steps: (1) Python version check, (2) venv create/activate and `pip install -r requirements.txt`, (3) optional Node.js check, (4) config dir and key YAML files present, (5) optional doctor (workspace_dir, skills_dir, LLM reachability). Each step shows pass/fail and short instructions; user clicks “Next” or “Retry” as needed. No automatic install of system Python/Node; guide only (links to docs or commands to copy).

### 8.3 Start Core

- Implemented in the “Start Core” area. Button “Start Core” triggers subprocess (e.g. `python -m main start` or `core.main` in a thread). Status: poll Core’s `GET /ready` (or configurable URL from core.yml); show “Core running at http://…” or “Core not running”. Optional “Stop Core” (call Core’s `/shutdown`) if desired.

### 8.4 Start channel

- Implemented in the “Start channel” area. Scan `channels/` for `*/channel.py`; list channel names. Buttons: “Start Core” (if not running), “Start channel &lt;name&gt;” (run that channel’s `channel.py` in a subprocess). Optional “Start all channels”. Status can be best-effort (e.g. “Started” without verifying each channel’s health).

### 8.5 Securing Core → Portal (Companion → Core → Portal)

**Threat model:** Only Core should be able to call the Portal. Other processes on the same machine (or a compromised Core) must not be able to use the Portal API without a secret.

**Design:**

- **Shared secret between Core and Portal:** Add to `core.yml` (or env):
  - `portal_url`: `http://127.0.0.1:8000` (or configurable port).
  - `portal_secret`: a random string (e.g. 32 chars). Same value is configured in the Portal (e.g. in `config/portal_admin.yml` or env `PORTAL_SECRET`). Core reads `portal_url` and `portal_secret` from config.
- **Portal API protection:** Every request from Core to the Portal must include the secret. Options:
  - **Header:** `X-Portal-Secret: <portal_secret>` or `Authorization: Bearer <portal_secret>`.
  - Portal validates the header on all `/api/config/*` and `/api/portal/*` requests; if missing or wrong, return **401**.
- **Core behavior:** When proxying a request from Companion to the Portal, Core adds the header (from config) and forwards. Core never exposes `portal_secret` to the client; only Core talks to the Portal.
- **Summary:** Companion → Core (existing auth: API key or session). Core → Portal (localhost + `portal_secret` header). Portal accepts only requests that carry the correct secret (and, for local Web UI, the admin password for browser sessions).

### 8.6 APIs that Core uses to manage settings (Portal REST API)

These are the APIs the **Portal** exposes and **Core** calls when `portal_url` is set. Core proxies Companion (or other) requests to these; Core does not implement config write logic when proxying—it forwards and returns the response.

| Method | Path | Request | Response | Notes |
|--------|------|---------|----------|--------|
| GET | `/api/config/core` | — | JSON: core config (whitelisted keys; secrets redacted) | Same shape as current Core GET. |
| PATCH | `/api/config/core` | JSON body: partial core config | `{ "result": "ok" }` or error | Merge into core.yml; comment-preserving. |
| GET | `/api/config/llm` | — | JSON: llm config (whitelisted) | |
| PATCH | `/api/config/llm` | JSON body: partial | `{ "result": "ok" }` | Merge into llm.yml. |
| GET | `/api/config/memory_kb` | — | JSON | Optional. |
| PATCH | `/api/config/memory_kb` | JSON body | `{ "result": "ok" }` | Optional. |
| GET | `/api/config/skills_and_plugins` | — | JSON | Optional. |
| PATCH | `/api/config/skills_and_plugins` | JSON body | `{ "result": "ok" }` | Optional. |
| GET | `/api/config/friend_presets` | — | JSON | Optional. |
| PATCH | `/api/config/friend_presets` | JSON body | `{ "result": "ok" }` | Optional. |
| GET | `/api/config/users` | — | JSON: `{ "users": [ ... ] }` | Same shape as Core’s current GET. |
| POST | `/api/config/users` | JSON body: new user | `{ "result": "ok" }` or error | |
| PATCH | `/api/config/users/{name}` | JSON body: partial user | `{ "result": "ok" }` | |
| DELETE | `/api/config/users/{name}` | — | `{ "result": "ok" }` | |
| GET | `/api/portal/channels` | — | JSON: `{ "channels": [ "telegram", "webchat", ... ] }` | Optional; for “Start channel” list. |
| POST | `/api/portal/doctor` | — | JSON: doctor report | Optional. |

**Auth for these endpoints:** Portal expects the **Core→Portal secret** in a header (e.g. `X-Portal-Secret` or `Authorization: Bearer`) on every request. No admin password here—the secret identifies the caller as Core. (Admin password is only for browser sessions to the Portal Web UI.)

### 8.7 How Core exposes this to an admin/super user via Companion (Option A — chosen)

**Goal:** Only an **admin/super user** can manage settings from the Companion app. Other users can chat but must not access config or portal proxy.

**Chosen approach: Option A — Portal admin username + password at entry.**

- Companion app has a **“Core setting”** (or “Manage Core” / “Settings”) **entry point**. When the user taps it, the app **does not** show settings immediately. Instead, it **forces** the user to enter:
  - **Admin username**
  - **Admin password**
  (Same credentials as the single Portal admin in Section 8.1.)
- The app sends these to Core (e.g. POST to an auth endpoint, or sends username + password in headers for the first request). Core validates against the configured portal admin credentials (stored in Core/Portal config or env). If wrong → **401/403** and Companion shows “Invalid username or password”; user must retry. If correct → Core returns a short-lived token or the app is allowed to load the settings UI (e.g. WebView of the Portal, see 8.8).
- **No access to settings without this step:** Every time the user enters “Core setting”, they must pass username + password (or, optionally, the app can cache a session token with short TTL so they don’t re-enter on every open; policy is configurable).
- **Concrete:** Store portal admin **username** and **password** (or hash) in Core/Portal config (e.g. `portal_admin_username`, `portal_admin_password` in core.yml or env). Core exposes e.g. `POST /api/portal/auth` with body `{ "username", "password" }`; if valid, return e.g. `{ "token": "<short-lived>" }`. Requests to `/portal-ui/*` (or config proxy) then require `Authorization: Bearer <token>` or the same username+password in headers. Companion “Core setting” screen: show login form first; on success, open the settings UI (WebView in Option A of 8.8).

### 8.8 Companion app settings UI: WebView of Portal (Option A — chosen)

**Chosen approach: Option A — Use the Portal’s web UI in a WebView.**

- Companion’s “Core setting” entry point (after admin username + password, Section 8.7) opens a **WebView** that loads the **Portal’s web UI** via Core. Core exposes e.g. `GET /portal-ui` and `GET /portal-ui/*` that **reverse-proxy** the Portal’s HTML/JS/CSS (Core fetches from Portal on localhost and streams back). Companion loads `https://core_public_url/portal-ui` (with auth token or API key) in the WebView; the user sees the **same** Portal web UI as in a desktop browser.
- **Rationale:**
  - **Single place to update:** When we change settings or UI (new fields, new tabs, onboarding steps), we only update the **Portal web UI**. No Companion app release or native UI changes needed.
  - **HTML5, mobile-friendly:** The Portal web UI should be built with **HTML5** and designed to **work well in a mobile WebView** (responsive layout, touch-friendly, no desktop-only assumptions). Then it works both on desktop browser and in Companion’s WebView.
  - **Remote config is not frequent:** We do not assume users will configure settings frequently from the Companion app remotely. So using a WebView (slightly less “native” than Flutter screens) is acceptable and keeps maintenance low.
- **Implications:**
  - Core must implement the **reverse proxy** for `/portal-ui` and `/portal-ui/*` (forward to Portal, add `portal_secret`, stream response; handle cookies/session if the Portal uses them).
  - Portal web UI: **one codebase**, optimized for both desktop and mobile WebView (responsive, HTML5).
  - Companion app: only provides the “Core setting” entry → login (username + password) → open WebView to Core’s `/portal-ui`. No duplicate native settings screens for each config file.

---

## 9. Summary

- **Portal** = small, stable **local web server** (e.g. `python -m main portal`). **Four areas:** (1) Manage settings (all six config files), (2) Guide to install (onboarding), (3) Start Core, (4) Start channel. Access: **one admin with password** (Section 8.1). Runs on 127.0.0.1 only.
- **Run together:** When Core is running, the Portal runs on the same machine so Core can call it. Both stay up.
- **Local management:** User opens browser → Portal → login (admin password) → manage settings, run onboarding, start Core/Channels.
- **Securing Core → Portal:** Shared **portal_secret** in config; Core sends it in a header when calling the Portal; Portal rejects requests without the correct secret (Section 8.5).
- **APIs:** Portal exposes REST APIs (Section 4 and 8.6); Core proxies Companion requests to the Portal when `portal_url` is set.
- **Companion admin access (Option A):** “Core setting” entry point → user **must** enter **admin username and password**; Core validates; only then can they access settings. No access without this step (Section 8.7).
- **Companion settings UI (Option A):** After login, Companion opens a **WebView** that loads the Portal’s web UI via Core’s `/portal-ui` proxy. **Single UI** (Portal web); HTML5, mobile-friendly for WebView; no Companion app changes when settings/UI are updated (Section 8.8).
- **YAML safety:** Portal is the single writer for config; all edits use ruamel merge (no full overwrite, no stripping comments).

This design gives one local portal (admin-only, username+password) for setup and config, and remote management via Companion → login (username+password) → WebView of Portal through Core, with Core→Portal secret and admin-only access.
