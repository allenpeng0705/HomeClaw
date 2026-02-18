# OpenClaw companion app connectivity (Gateway URL, Tailscale, Cloudflare Tunnel)

Companion apps (macOS, iOS, Android, Flutter, WebChat, CLI) connect to the OpenClaw **Gateway** over a **single WebSocket URL** plus optional auth. The Gateway and Core do not care how that URL was obtained. This doc summarizes the options so you can choose Tailscale, Cloudflare Tunnel, or something else without changing app or Gateway code.

---

## How apps connect

- **Protocol:** WebSocket (`ws://` or `wss://`) to the Gateway (default port `18789`).
- **Auth:** Optional `token` or `password` when `gateway.auth.mode` is set (e.g. for remote or Funnel). Apps send the same token/password (e.g. query param or first message) as the CLI/WebChat.
- **No Tailscale/Cloudflare SDK in the app:** The app only needs:
  - **Gateway URL** (e.g. `ws://127.0.0.1:18789` or `wss://your-host.example.com`)
  - **Optional:** token or password

So: **Tailscale** and **Cloudflare Tunnel** are ways to *expose* the Gateway and get a `wss://` URL; the app just uses that URL.

---

## Local (same machine)

- **URL:** `ws://127.0.0.1:18789` (or the port from `gateway.port`).
- **Use case:** CLI, WebChat, or companion app running on the same host as the Gateway. No tunnel needed.

---

## Remote: Tailscale (OpenClaw built-in)

OpenClaw can auto-configure Tailscale so the Gateway stays on loopback but is reachable over the tailnet or publicly.

- **Serve (tailnet-only):** Only devices on your Tailnet can use the URL (e.g. `wss://machine.tailnet-name.ts.net`). Set `gateway.tailscale.mode: "serve"`.
- **Funnel (public):** Public HTTPS; set `gateway.tailscale.mode: "funnel"`. OpenClaw requires `gateway.auth.mode: "password"` (or token) for Funnel.
- **Companion app:** Set “Gateway URL” to the Tailscale URL (or use `gateway.remote.url` from config). No Tailscale SDK in the app — just WebSocket + token/password if required.

See OpenClaw docs: [Tailscale guide](https://docs.openclaw.ai/gateway/tailscale), [Remote access](https://docs.openclaw.ai/gateway/remote).

---

## Remote: Cloudflare Tunnel

You can expose the Gateway with **Cloudflare Tunnel** instead of Tailscale.

- **Setup:** Run `cloudflared tunnel` (or Cloudflare’s dashboard) and point the tunnel at the Gateway’s HTTP/WebSocket endpoint (e.g. `http://127.0.0.1:18789`). You get a public URL like `wss://your-tunnel.trycloudflare.com`.
- **Config:** Set `gateway.mode: "remote"` and `gateway.remote.url` to that `wss://` URL. Use `gateway.remote.token` or `gateway.remote.password` if you use Gateway auth.
- **Companion app:** Same as Tailscale — use `gateway.remote.url` (or type it in the app). No Cloudflare SDK in the app.

So: **Tailscale vs Cloudflare** is a deployment choice; the app only ever sees one WebSocket URL + auth.

---

## Remote: SSH tunnel

- **Setup:** On your client machine: `ssh -L 18789:127.0.0.1:18789 user@gateway-host`. Then connect to `ws://127.0.0.1:18789` as if local.
- **Companion app:** Set Gateway URL to `ws://127.0.0.1:18789` while the SSH tunnel is active. No change to Gateway or app logic.

---

## Summary

| Method            | Gateway config / setup              | App needs                    |
|-------------------|-------------------------------------|------------------------------|
| Local             | Default bind, port 18789            | URL: `ws://127.0.0.1:18789`  |
| Tailscale Serve   | `gateway.tailscale.mode: "serve"`   | URL: Tailscale wss URL + auth if required |
| Tailscale Funnel  | `gateway.tailscale.mode: "funnel"` + auth | URL: Funnel wss URL + password/token |
| Cloudflare Tunnel | `gateway.remote.url: "wss://…"` (+ optional token/password) | URL: tunnel wss URL + auth if required |
| SSH tunnel        | None on Gateway                     | URL: `ws://127.0.0.1:18789` while tunnel is up |

Implementing a **Flutter companion app** (or any new client) only requires: a configurable WebSocket URL, optional token/password, and the same Gateway protocol (node list, node.invoke, sessions, etc.) as the existing Swift/Kotlin apps. No Tailscale- or Cloudflare-specific code in the app.
