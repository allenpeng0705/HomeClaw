# Companion app (Flutter)

The **HomeClaw Companion** app is a **Flutter-based** client for **Mac, Windows, iPhone, and Android**. It makes HomeClaw much easier to use from any device.

---

## What it does

- **Chat** — Send messages, attach images and files; voice input and TTS (speak replies).
- **Manage Core** — Edit **core.yml** and **user.yml** from the app: server, LLM, memory, session, completion, profile, skills, tools, auth, and users. No need to SSH or edit config files by hand.
- **One app, all platforms** — Same codebase for desktop and mobile; install from the store or build from source.

---

## Friends and presets

Each user has a **friends** list in `config/user.yml`. The Companion app shows these friends so you can chat with different “assistants” (e.g. HomeClaw, or custom friends with their own identity). You can also add **system friends** that use a **preset**: a limited set of tools and context for a specific task (e.g. Reminder for scheduling, Note for notes, Finder for file search). Presets are defined in `config/friend_presets.yml`.

**Adding or removing friends (including system friends):** Edit `config/user.yml` for the user. Under that user’s `friends:` list, add or remove an entry. To use a preset, set `preset: <name>` (e.g. `preset: reminder`). Example:

```yaml
friends:
  - name: HomeClaw
  - name: Reminder
    preset: reminder
  - name: Note
    preset: note
```

To remove a friend, delete that entry and restart Core. No code change is required. The list is returned by Core’s `/api/me/friends` and shown in the Companion app.

---

## Where to get it

- **Source:** `clients/HomeClawApp/` in the repo.
- **Build:** Use Flutter; see `clients/HomeClawApp/README.md` for build instructions.
- **Connect:** Set the Core URL and optional API key in the app (e.g. in Settings or on first launch). The app talks to your Core over HTTP (e.g. `http://127.0.0.1:9000` or your server URL). To use the app on your **iPhone** when Core is at home, expose Core with [Tailscale](remote-access.md#1-tailscale-recommended-for-home--mobile) or [Cloudflare Tunnel](remote-access.md#2-cloudflare-tunnel-public-url); see [Companion on iPhone via Cloudflare Tunnel](companion-iphone-cloudflare-tunnel.md) for detailed steps.

You can use the companion app **instead of** or **together with** WebChat, CLI, Telegram, and other channels—all talk to the same Core and memory.

**macOS users:** For permissions (network, and future voice/notifications/screen), see [Companion app (macOS permissions)](companion-app-macos-permissions.md).

---

## Canvas (agent-driven UI)

**Target and feature:** The **Canvas** in the Companion app is an **agent-driven UI** viewer. It loads a URL you configure (usually the **homeclaw-browser** plugin’s canvas page). The plugin serves a page at **/canvas** where the **LLM can push live UI** (title, text blocks, buttons) via the `canvas_update` capability. So Canvas lets you see and interact with UI that the agent sends in real time (e.g. forms, choices, status), without leaving the app.

### What you can use the Canvas for

- **Status / info** — The agent can push a title and text blocks to the Canvas so you see a live status or summary (e.g. “Current task”, “Search results”, “Reminder”).
- **Choices / actions** — The agent can add **buttons** (e.g. “OK”, “Cancel”, “Retry”). When you tap a button, the canvas page can send that back (today the Companion only displays the UI; button actions depend on the canvas page implementation).
- **Simple forms** — The agent can show a small “form” as title + text + buttons (e.g. “Confirm?”, “Yes” / “No”).

So in practice: you **chat with the agent**, and when you ask it to **“show something on the canvas”** or **“update the canvas”**, it calls the plugin to push that content; the **Canvas screen in the app** shows it in real time.

### How to use it (step by step)

1. **Prerequisites**
   - **homeclaw-browser** plugin is running (e.g. Core auto-starts it, or you run `node server.js` in `system_plugins/homeclaw-browser`).
   - Plugin is registered with Core (`node register.js` or Core auto-registers it).
   - In the Companion app, **Canvas URL** is set (e.g. `http://<host>:3020/canvas`). You can set it in **Settings** or on the Login screen if you use the same host as Core.

2. **Open the Canvas in the app**  
   From the app (e.g. from the main menu or the place you open “Canvas”), open the Canvas screen. It will load the Canvas URL and connect to the plugin’s canvas session.

3. **Ask the agent to update the canvas**  
   In **Chat**, say something that clearly asks to show content on the canvas. The agent will then call `canvas_update` and the Canvas screen will update. Example phrases:
   - *“Update the canvas.”*
   - *“Show on the canvas: Hello world.”*
   - *“Put a title and a button on the canvas.”*
   - *“更新画布”* / *“画布显示 …”* (Chinese triggers are also configured.)

4. **See the result**  
   The Canvas screen in the app should show the title and blocks (text, buttons) the agent pushed. If nothing appears, check that the session name on the canvas page matches what the agent uses (usually your user/session; see plugin README for `session_id`).

**How the canvas is shown (WebView) and desktop:** The Companion shows the canvas in an **embedded WebView** ([webview_flutter](https://pub.dev/packages/webview_flutter)). On **desktop** (macOS, Windows, Linux) the native platform view often has a **fixed frame** and may not resize with the window; use the **Open in browser** toolbar button on the Canvas screen to open the URL in your system browser for a resizable view.

So: **Canvas = “second screen”** where the agent can push live UI (title, text, buttons) while you chat; you use it by opening Canvas in the app and then asking the agent in chat to “update the canvas” or “show … on the canvas”.

---

- **Core** = your HomeClaw Core (e.g. `http://host:9000`). Chat, config, and APIs talk to Core.
- **Canvas URL** = the page that shows that agent-pushed UI. It is served by the **homeclaw-browser** plugin on a **different port** (default **3020**), e.g. `http://host:3020/canvas`.

So you have **two endpoints**: Core (e.g. 9000) and the plugin (e.g. 3020). Both must be reachable from the Companion app.

### Connecting when Core and Canvas use different ports

If Core and the plugin run on the same machine but different ports, you have two main options.

**Option A — Same network (e.g. home Wi‑Fi or Tailscale)**  
- Set **Core URL** to `http://<host>:9000` (or your Core URL).  
- Set **Canvas URL** to `http://<host>:3020/canvas` (or your plugin URL + `/canvas`).  
- No tunnel needed if the phone and the host are on the same network (or both on Tailscale). Use the host’s LAN or Tailscale IP for `<host>`.

**Option B — Remote access (two tunnels)**  
Expose both services with **two tunnels** (e.g. two Cloudflare quick tunnels or two Tailscale Serve entries):

1. **Tunnel 1 → Core**  
   - Example: `cloudflared tunnel --url http://127.0.0.1:9000`  
   - Use the resulting URL as **Core URL** in the app.

2. **Tunnel 2 → Plugin (Canvas)**  
   - Example: `cloudflared tunnel --url http://127.0.0.1:3020`  
   - Use the resulting URL + `/canvas` as **Canvas URL**, e.g. `https://other-words.trycloudflare.com/canvas`.

You then set **Core URL** and **Canvas URL** in the app to these two public URLs. No change to Core or the plugin is required.

**Option C — Single host with a reverse proxy (one tunnel)**  
Run a **reverse proxy** on the machine (e.g. nginx or Caddy) that listens on one port and routes:

- `/` (and `/api`, `/inbound`, `/ws`, etc.) → Core (e.g. `http://127.0.0.1:9000`)
- `/canvas`, `/nodes`, `/ws` for the plugin → plugin (e.g. `http://127.0.0.1:3020`)

Then expose **that** proxy with **one** tunnel. In the app:

- **Core URL** = proxy base URL (e.g. `https://my-tunnel.trycloudflare.com`).
- **Canvas URL** = same base + path to the canvas page (e.g. `https://my-tunnel.trycloudflare.com/canvas`).

This way you only run one tunnel and one public URL; the proxy splits traffic by path to Core vs plugin.
