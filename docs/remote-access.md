# Remote access: Tailscale and Cloudflare Tunnel

HomeClaw Core runs on your machine (e.g. home PC or server). To use the **Companion app**, WebChat, or other clients from another network (e.g. phone on cellular, laptop away from home), you need a way for the client to reach Core. This page introduces two common options: **Tailscale** and **Cloudflare Tunnel**. No changes to Core or the app are required—you only expose Core and set the **Core URL** in the client.

---

## Overview

| Method | Who can reach Core | Best for |
|--------|--------------------|----------|
| **Tailscale (tailnet)** | Only devices on your Tailscale network | Home + your devices (phone, laptop); private, no public exposure |
| **Tailscale Funnel** | Anyone with the URL (public HTTPS) | Webhooks, bots; use with strong auth |
| **Cloudflare Tunnel** | Anyone with the tunnel URL (public HTTPS) | Simple public URL; use with Core `auth_enabled` |
| **Pinggy** | Anyone with the Pinggy URL (public HTTPS) | Similar to ngrok/Cloudflare; zero-config tunnel. See `docs_design/StrongLocalModelAndPerplexityRouting.md` §6 in the repo. |
| **SSH tunnel** | You, from the machine where the tunnel runs | Developers; desktop → Core over SSH |

The **Companion app** and other clients only need a **Core URL** and optional **API key**. They do not include Tailscale or Cloudflare SDKs—you choose how to expose Core, then set that URL in the app.

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

## 3. Auth when exposing Core

When Core is reachable from the internet (e.g. via Cloudflare Tunnel or Tailscale Funnel):

- Set **`auth_enabled: true`** and **`auth_api_key`** in `config/core.yml`.  
- Clients (Companion app, WebChat, etc.) must send **`X-API-Key`** or **`Authorization: Bearer <key>`** on **POST /inbound** and **WebSocket /ws**.

With **Tailscale tailnet-only** (no Funnel), only your Tailscale devices can reach Core; you can still set `auth_enabled` for extra safety.

For more detail (auth headers, Funnel + auth proxy), see [RemoteAccess.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/RemoteAccess.md) and [HomeClawCompanionConnectivity.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HomeClawCompanionConnectivity.md) in the repo.

---

## Summary

- **Tailscale (tailnet or Serve):** Private or HTTPS access from your devices; no public exposure. Set Core URL in the app to the Tailscale IP or Serve URL.  
- **Cloudflare Tunnel:** Public HTTPS URL; use with **auth_enabled** and a strong API key. Set Core URL in the app to the tunnel URL and the same API key.  
- The app only needs **Core URL** and optional **API key**; Tailscale and Cloudflare are ways to expose Core and get that URL.
