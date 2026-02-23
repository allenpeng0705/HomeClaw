# Remote access: Tailscale and Cloudflare Tunnel

HomeClaw Core runs on your machine (e.g. home PC or server). To use the **Companion app**, WebChat, or other clients from another network (e.g. phone on cellular, laptop away from home), you need a way for the client to reach Core. This page introduces two common options: **Tailscale** and **Cloudflare Tunnel**. No changes to Core or the app are required—you only expose Core and set the **Core URL** in the client.

---

## Overview

| Method | Who can reach Core | Best for |
|--------|--------------------|----------|
| **Tailscale (tailnet)** | Only devices on your Tailscale network | Home + your devices (phone, laptop); private, no public exposure |
| **Tailscale Funnel** | Anyone with the URL (public HTTPS) | Webhooks, bots; use with strong auth |
| **Cloudflare Tunnel** | Anyone with the tunnel URL (public HTTPS) | Simple public URL; use with Core `auth_enabled` |
| **Pinggy** | Anyone with the Pinggy URL (public HTTPS) | **Built-in:** set `pinggy.token` in core.yml; Core starts the tunnel and serves **/pinggy** with public URL and QR for Companion scan-to-connect. |
| **Any public URL** | Anyone with the URL (Cloudflare, Tailscale Funnel, etc.) | Set **`core_public_url`** in core.yml to your public Core URL; **GET /pinggy** shows that URL and a QR code for Companion. No tunnel started by Core. |
| **SSH tunnel** | You, from the machine where the tunnel runs | Developers; desktop → Core over SSH |

The **Companion app** and other clients only need a **Core URL** and optional **API key**. They do not include Tailscale or Cloudflare SDKs—you choose how to expose Core, then set that URL in the app.

**Step-by-step: Companion on iPhone via Cloudflare Tunnel** — See [Companion on iPhone via Cloudflare Tunnel](companion-iphone-cloudflare-tunnel.md) for detailed steps (Core + auth, cloudflared, configure app, test on cellular).

---

## 1. Tailscale (recommended for home + mobile)

Tailscale gives you a private network (tailnet) so your devices can reach each other without opening ports to the internet.

### Setup on the machine that runs Core

1. **Install Tailscale**  
   - [tailscale.com/download](https://tailscale.com/download) — install on the host where Core runs (e.g. your home PC or server).  
   - Log in with your Tailscale account.

2. **Expose Core only on the tailnet (no public internet)**  
   - Core already listens on `0.0.0.0:9000` by default, so it accepts connections on all interfaces, including Tailscale’s.  
   - On the **Core host**, find the Tailscale IP:
     - Run: `tailscale ip`
     - Or open the Tailscale admin UI and check the machine’s IP (e.g. `100.x.x.x`).
   - From **another device** (phone, laptop), install Tailscale and log in with the **same** account. That device can now reach Core at `http://100.x.x.x:9000` (replace with your Core host’s Tailscale IP).

3. **Optional: HTTPS with Tailscale Serve**  
   - On the Core host:  
     `tailscale serve https / http://127.0.0.1:9000`  
   - Tailscale will show a URL like `https://your-machine.your-tailnet.ts.net`.  
   - Use this URL as the **Core URL** in the Companion app (and set API key if Core has `auth_enabled: true`).

### In the Companion app

- **Settings** → set **Core URL** to:
  - `http://<tailscale-ip>:9000` (e.g. `http://100.101.102.103:9000`), or  
  - `https://your-machine.your-tailnet.ts.net` if you use Tailscale Serve.  
- If Core has **auth_enabled**, set the same **API key** in the app.

No Tailscale app or SDK is required on the phone—only the Core URL (and optional API key).

---

## 2. Cloudflare Tunnel (public URL)

Cloudflare Tunnel gives you a public HTTPS URL that forwards to Core, without opening a port on your router.

### Setup

1. **Install cloudflared**  
   - [Developers: Cloudflare Tunnel (Quick Tunnel)](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/local/) — install `cloudflared` on the machine that runs Core.

2. **Start a quick tunnel to Core**  
   - Run:  
     `cloudflared tunnel --url http://127.0.0.1:9000`  
   - You’ll get a URL like `https://random-words.trycloudflare.com`.  
   - (For a stable hostname and more control, use a named tunnel and Cloudflare dashboard; see Cloudflare docs.)

3. **Secure Core**  
   - Because the URL is public, enable Core auth: in `config/core.yml` set `auth_enabled: true` and `auth_api_key: "<long-random-key>"`.  
   - Use a long, random API key (e.g. 32+ characters).

### In the Companion app

- **Settings** → set **Core URL** to the tunnel URL (e.g. `https://random-words.trycloudflare.com`).  
- Set the **API key** to the same value as `auth_api_key` in Core.

---

## 3. Public URL (Cloudflare, Tailscale Funnel, or any service)

If you expose Core with **Cloudflare Tunnel**, **Tailscale Funnel**, or any other service and have a **public URL**, you can show that URL and a **QR code** for the Companion app without using Pinggy.

### Setup

1. **Expose Core** with your chosen service (e.g. run `cloudflared tunnel --url http://127.0.0.1:9000` and get a URL like `https://xxx.trycloudflare.com`).
2. **Configure Core**  
   - In **`config/core.yml`**, set **`core_public_url`** to that URL (e.g. `https://xxx.trycloudflare.com`).  
   - Enable auth when using a public URL: set **`auth_enabled: true`** and **`auth_api_key`** in core.yml.
3. **Open the scan page**  
   - Open **http://127.0.0.1:&lt;port&gt;/pinggy** in your browser (e.g. after starting Core with `python -m main start`).  
   - The page shows the **public URL** and a **QR code** encoding `homeclaw://connect?url=...&api_key=...`.

### In the Companion app

- **Settings** → **Scan QR to connect** → scan the QR code on the /pinggy page.

The **/pinggy** page uses **`core_public_url`** from core.yml when set; otherwise it uses the Pinggy tunnel URL if **pinggy.token** is set. So you can use either Cloudflare (or any service) with **core_public_url**, or Pinggy with **pinggy.token**.

---

## 4. Pinggy (built-in tunnel + QR for Companion)

**Pinggy** gives you a public HTTPS URL that forwards to Core, similar to ngrok or Cloudflare Tunnel. HomeClaw has **built-in support**: when you set a Pinggy token in core.yml, Core starts the tunnel at startup and serves a **/pinggy** page with the public URL and a **QR code** so you can connect the Companion app with one scan.

### Setup

1. **Get a Pinggy token**  
   - Sign up at [pinggy.io](https://pinggy.io) (or [dashboard.pinggy.io](https://dashboard.pinggy.io)) and create a token.

2. **Configure Core**  
   - In **`config/core.yml`**, find the **`pinggy`** block and set:
     - **`token`** — Your Pinggy token (e.g. `"your-token-here"`). Leave empty to disable.
     - **`open_browser`** — `true` (default) to open the browser to the /pinggy page when the tunnel is ready.
   - Enable auth when using a public URL: set **`auth_enabled: true`** and **`auth_api_key`** in core.yml.

3. **Start Core**  
   - Run `python -m main start` (or start Core however you usually do).  
   - Core starts the Pinggy tunnel in the background. When the tunnel is ready, Core opens **http://127.0.0.1:&lt;port&gt;/pinggy** in your browser (if `open_browser: true`).  
   - The **/pinggy** page shows the **public URL** and a **QR code** encoding the Companion connection link (`homeclaw://connect?url=...&api_key=...`).

### In the Companion app

- **Settings** → **Scan QR to connect** → scan the QR code on the /pinggy page.  
- The app saves the Core URL and API key and connects through the tunnel. No need to type the URL or key.

If you prefer not to open the browser automatically, set **`pinggy.open_browser: false`** in core.yml; you can still open **http://127.0.0.1:9000/pinggy** (or your Core port) manually to see the QR.

For design details (tunnel lifecycle, optional CLI), see **docs_design/PinggyIntegration.md** in the repo.

---

## 5. Auth when exposing Core

When Core is reachable from the internet (e.g. via Cloudflare Tunnel or Tailscale Funnel):

- Set **`auth_enabled: true`** and **`auth_api_key`** in `config/core.yml`.  
- Clients (Companion app, WebChat, etc.) must send **`X-API-Key`** or **`Authorization: Bearer <key>`** on **POST /inbound** and **WebSocket /ws**.

With **Tailscale tailnet-only** (no Funnel), only your Tailscale devices can reach Core; you can still set `auth_enabled` for extra safety.

For more detail (auth headers, Funnel + auth proxy), see [RemoteAccess.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/RemoteAccess.md) and [HomeClawCompanionConnectivity.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HomeClawCompanionConnectivity.md) in the repo.

---

## Summary

- **Tailscale (tailnet or Serve):** Private or HTTPS access from your devices; no public exposure. Set Core URL in the app to the Tailscale IP or Serve URL.  
- **Cloudflare Tunnel:** Public HTTPS URL; use with **auth_enabled** and a strong API key. Set Core URL in the app to the tunnel URL and the same API key.  
- **Public URL:** Set **`core_public_url`** in core.yml to your public Core URL (e.g. from Cloudflare Tunnel, Tailscale Funnel). **GET /pinggy** shows that URL and a QR code for Companion; the same URL is used for file/report links. Enable **auth_enabled** when using a public URL.  
- **Pinggy:** Built-in tunnel; set **`pinggy.token`** in core.yml and optionally **`pinggy.open_browser: true`**. Core serves **/pinggy** with public URL and QR; use Companion **Scan QR to connect**. Enable **auth_enabled** when using the public URL.  
- The app only needs **Core URL** and optional **API key**; Tailscale, Cloudflare, **core_public_url**, and Pinggy are ways to expose or point to Core and get that URL.
