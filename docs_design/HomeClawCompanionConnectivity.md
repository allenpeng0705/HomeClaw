# HomeClaw client connectivity (Core URL, Tailscale, Cloudflare Tunnel)

Companion apps (Flutter, CLI, WebChat, any custom client) connect to **HomeClaw Core** over **HTTP and WebSocket**. Core does not care how the client obtained the URL. This doc summarizes the options so you can use Tailscale, Cloudflare Tunnel, or something else without changing Core or client code.

**How iOS, Android, and desktop connect when remote:** See **RemoteConnectionIOSAndroidDesktop.md** for the full picture (Tailscale, QR pairing, SSH) and what HomeClaw already supports.

---

## How clients connect

- **Base URL:** Core’s HTTP server (from `config/core.yml`: `host`, `port`; default `http://127.0.0.1:9000`).
- **Endpoints:**
  - **POST /inbound** — Send a message; get sync JSON response (`text`, optional media). Same shape as channels use.
  - **WebSocket /ws** — Interactive chat; send/receive messages.
  - **GET /api/sessions**, **POST /api/plugins/llm/generate**, etc. — When enabled; same base URL.
- **Auth:** When `auth_enabled: true` in Core, clients must send `X-API-Key` or `Authorization: Bearer <key>` (e.g. in headers for HTTP, in handshake for WS).

So: clients only need a **Core URL** and optional **API key**. No Tailscale or Cloudflare SDK inside the app — those are ways to *expose* Core and get a URL.

---

## Local (same machine)

- **URL:** `http://127.0.0.1:9000` (or the host/port from `core.yml`).
- **Use case:** Flutter app or CLI running on the same host as Core. No tunnel needed.

---

## Remote: Tailscale

Expose Core over your tailnet or publicly using Tailscale.

- **Serve (tailnet-only):** Only devices on your Tailnet can reach Core. Run Tailscale and e.g. `tailscale serve https / http://127.0.0.1:9000`. Clients use the Tailscale URL (e.g. `https://machine.tailnet-name.ts.net`).
- **Funnel (public):** Public HTTPS; use with care and with Core `auth_enabled: true` and a strong API key.
- **Client:** Set “Core URL” (or `HOMECLAW_CORE_URL`) to the Tailscale URL. No Tailscale SDK in the app — just HTTP/WS + API key if required.

---

## Remote: Cloudflare Tunnel

Expose Core with **Cloudflare Tunnel** instead of Tailscale.

- **Setup:** Run `cloudflared tunnel` (or use Cloudflare dashboard) and point the tunnel at `http://127.0.0.1:9000`. You get a URL like `https://your-tunnel.trycloudflare.com`.
- **Client:** Set Core URL to that `https://...` URL. If Core has `auth_enabled`, send the API key. No Cloudflare SDK in the app.

---

## Remote: SSH tunnel

- **Setup:** On the client machine: `ssh -L 9000:127.0.0.1:9000 user@core-host`. Then connect to `http://127.0.0.1:9000` as if local.
- **Client:** Use `http://127.0.0.1:9000` while the SSH tunnel is active.

---

## Summary

| Method            | Core exposure              | Client sets                |
|-------------------|----------------------------|----------------------------|
| Local             | None (bind 0.0.0.0:9000)   | URL: `http://127.0.0.1:9000` |
| Tailscale Serve   | Tailscale URL (tailnet)    | URL: Tailscale base + API key if auth |
| Tailscale Funnel  | Tailscale URL (public)     | URL: Funnel base + API key (recommended) |
| Cloudflare Tunnel | Tunnel URL                 | URL: tunnel base + API key if auth |
| SSH tunnel        | None                       | URL: `http://127.0.0.1:9000` while tunnel up |

**Flutter app and CLI** only need: configurable Core URL and optional API key. Implement once; deployment chooses the URL (Tailscale, Cloudflare, or other).
