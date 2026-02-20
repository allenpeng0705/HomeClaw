# How iOS, Android, and desktop connect to HomeClaw (local and remote)

This doc explains how **mobile (iOS, Android)** and **desktop (Mac, Windows)** clients connect to **HomeClaw Core** when they run on the same machine vs when they run **remotely** (e.g. phone on cellular, Core on home PC). It aligns with the approach used by **OpenClaw** (WebSocket control plane + Tailscale / QR pairing / SSH) and states what HomeClaw already supports and what can be added.

---

## Core architecture: Core as “control plane”

In HomeClaw, **Core** is the central service (like OpenClaw’s Gateway):

- **Protocol:** HTTP + **WebSocket** (`/ws`). Core listens on `host:port` (default `0.0.0.0:9000` from `config/core.yml`).
- **Bidirectional:** WebSocket lets Core push to clients (e.g. streaming replies, status). HTTP is used for POST /inbound, GET /api/sessions, etc.
- **Auth:** When `auth_enabled: true`, clients send **API key** (`X-API-Key` or `Authorization: Bearer <key>`). This is the equivalent of OpenClaw’s gateway auth token for “who can connect.”
- **No client-side tunnel SDK:** The app only needs a **Core URL** and optional **API key**. How that URL is reached (Tailscale, Cloudflare, SSH, QR) is a deployment/setup choice.

So: **iOS, Android, and desktop all connect the same way** — they use the same Core URL (and API key if required). The only difference is how that URL is obtained when Core is not on localhost.

---

## The “remote” problem

- **Local:** App and Core on the same machine → use `http://127.0.0.1:9000` (or the configured host/port). No extra setup.
- **Remote:** Core runs at home (e.g. on a PC behind Wi‑Fi), app runs on a phone (e.g. on 5G) or another computer. The phone cannot reach `localhost` or the PC’s LAN IP from the internet. So we need a way to **expose** Core or **tunnel** to it.

HomeClaw does **not** implement “inner network penetration” inside Core. Instead, it **reuses standard solutions** (Tailscale, Cloudflare Tunnel, SSH). The app does not need to know which one is used; it only needs the final **Core URL**.

---

## Three ways to connect remotely (OpenClaw-style, applied to HomeClaw)

### 1. Tailscale (recommended for home + mobile)

**Idea:** Core runs on a machine that has **Tailscale** installed. The same Tailscale account is used on the phone (and optionally on another desktop). Tailscale gives a stable virtual IP (e.g. `100.x.x.x`) that is reachable from any device on the tailnet.

**HomeClaw today:**

- Core binds to `0.0.0.0:9000` by default, so it accepts connections on all interfaces, including Tailscale’s.
- On the **Core host:** Install Tailscale and log in. Other devices (phone, laptop) log in with the **same** Tailscale account.
- **No need to change Core code.** On the phone/app, set **Core URL** to `http://<tailscale-ip>:9000` (e.g. `http://100.101.102.103:9000`). You can find the Tailscale IP on the Core host with `tailscale ip` or in the Tailscale admin UI.
- **HTTPS (optional):** For TLS, use **Tailscale Serve** (e.g. `tailscale serve https / http://127.0.0.1:9000`). Then the Core URL becomes `https://<machine>.tailnet-name.ts.net` (or the URL Tailscale shows). App still only uses this URL + API key if auth is on.

**Summary:** HomeClaw **already supports** remote connection via Tailscale: run Core and Tailscale on the same machine; point iOS/Android/desktop at the Tailscale URL. No Tailscale SDK in the app.

---

### 2. QR code pairing (one-tap setup for mobile)

**Idea (OpenClaw):** A CLI or UI generates a **QR code** that encodes the gateway URL, port, and auth token. The mobile app scans the QR and saves these as the connection config, so the user doesn’t type URLs or tokens by hand.

**HomeClaw today:**

- We do **not** yet have a built-in “onboard” or “pair” command that prints a QR. Users type Core URL (and API key) in the Flutter app Settings or set env for the CLI.

**Proposed addition (optional):**

- **CLI:** e.g. `homeclaw pair` or `homeclaw onboard` that:
  - Reads Core URL (from env or config) and API key (if `auth_enabled`).
  - Prints a **QR code** (terminal or opens a small HTML page) that encodes a **connection payload**, e.g.:
    - URL only: `homeclaw://connect?url=https://100.x.x.x:9000`
    - With auth: `homeclaw://connect?url=https://...&api_key=...` (or a short-lived pairing token if we add one).
  - Flutter app (and any future app) **scans the QR**, parses the URL (and optional api_key), and saves them in Settings. After that, the app connects as today (HTTP/WS + API key).
- **QR content format:** A simple URL scheme (`homeclaw://connect?url=...&api_key=...`) or a JSON object `{"url":"...","api_key":"..."}` so other clients can support it too.

So: **remote connection itself is already solved** (via Tailscale or other tunnel); **QR pairing** is a UX improvement so mobile users don’t have to type the Tailscale URL and API key.

---

### 3. SSH tunnel (developer / advanced)

**Idea:** The user runs an SSH tunnel from the **client** machine to the **Core host**. The tunnel forwards a local port to Core’s port. The app then connects to `localhost` on the client.

**HomeClaw today:**

- **On the client machine** (e.g. your laptop or a machine that can SSH to the Core host):
  ```bash
  ssh -L 9000:127.0.0.1:9000 user@core-host
  ```
- **App on that client:** Set Core URL to `http://127.0.0.1:9000`. As long as the SSH session is open, Core is reachable.
- **Phone:** Typically the phone cannot run the SSH client and have the app use “localhost,” so SSH tunnel is more useful for **desktop-to-Core** (e.g. laptop → home server). For **phone → Core**, Tailscale or Cloudflare is more practical.

**Summary:** HomeClaw **already supports** SSH tunnel: no change to Core; user runs `ssh -L 9000:127.0.0.1:9000 user@core-host` and points the app at `http://127.0.0.1:9000`.

---

## What HomeClaw already solves

| Scenario | Solved? | How |
|----------|--------|-----|
| **Desktop app (same machine as Core)** | Yes | Core URL = `http://127.0.0.1:9000`. |
| **Desktop app (remote Core)** | Yes | Tailscale URL or Cloudflare Tunnel URL, or SSH tunnel + localhost. |
| **iOS/Android (remote Core)** | Yes | Core URL = Tailscale URL (or Cloudflare URL). No SDK in app; just HTTP/WS + API key. |
| **One-tap mobile setup (no typing URL/token)** | Not yet | Can add: CLI `homeclaw pair` that shows QR; app scans and saves URL + API key. |

So: **how iOS, Android, and desktop connect to HomeClaw when they run remotely is already addressed** by using Tailscale (or Cloudflare or SSH) and setting the Core URL in the app. The only gap is **convenience** (QR pairing) for mobile.

---

## Security note (exposing Core)

When Core is reachable beyond localhost (Tailscale, Cloudflare, or binding to 0.0.0.0 on a LAN):

- Set **`auth_enabled: true`** in `config/core.yml` and a strong **`auth_api_key`**.
- Prefer **Tailscale (tailnet-only)** or **Tailscale Funnel with auth** so Core is not open to the whole internet without a key.
- QR codes that contain an API key should be shown only to the user who will scan them (don’t leave them on a public screen).

---

## Summary

- **Core = “control plane”:** HTTP + WebSocket on port 9000; auth via API key when `auth_enabled`.
- **iOS, Android, desktop:** All use the same Core URL and API key; no special logic per platform.
- **Remote connection:** HomeClaw **does** support it: use **Tailscale** (or Cloudflare Tunnel or SSH). Core does not need to “solve” penetration; the user exposes Core with one of these tools and gives the app the resulting URL.
- **Optional improvement:** Add **QR pairing** (`homeclaw pair` + app scan) so mobile users can connect without typing URL and API key.

See **HomeClawCompanionConnectivity.md** for a short table of connection methods (local, Tailscale, Cloudflare, SSH).
