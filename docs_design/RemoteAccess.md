# Remote access and auth

When you expose HomeClaw Core on the internet (e.g. so a Telegram bot or WebChat can reach it from anywhere), you need to secure it. This doc describes two approaches: **built-in API key** and **recommended path (Tailscale + optional auth proxy)**.

---

## 1. Built-in API key (Core auth)

Core can require an API key for **POST /inbound** and **WebSocket /ws**. Other routes (/process, /local_chat, /register_channel, etc.) are **not** protected by this key; they are intended for same-machine or trusted channel processes.

### Config

In `config/core.yml`:

```yaml
auth_enabled: true
auth_api_key: "your-secret-key"   # use a long random string; do not commit real keys to git
```

- **auth_enabled: false** (default): no key required; anyone who can reach Core can call /inbound and /ws (still subject to user.yml allowlist for which user_id can chat).
- **auth_enabled: true** and **auth_api_key** set: every request to /inbound and every WebSocket connection to /ws must send the key.

### How to send the key

**POST /inbound**

- **Header** `X-API-Key: your-secret-key`, or  
- **Header** `Authorization: Bearer your-secret-key`

Example with curl:

```bash
curl -X POST http://your-core:9000/inbound \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"user_id": "telegram_123", "text": "Hello"}'
```

**WebSocket /ws**

Send the same header in the **handshake** when opening the WebSocket:

- `X-API-Key: your-secret-key`, or  
- `Authorization: Bearer your-secret-key`

If the key is missing or wrong, Core returns **401** for /inbound and closes the WebSocket with code **1008** (policy violation) for /ws.

### Security notes

- Use a long, random **auth_api_key** (e.g. 32+ characters). Do not commit it to version control; use env vars or a secrets manager and inject into config if needed.
- **auth_enabled** only protects /inbound and /ws. /process and /local_chat are used by full channel processes (e.g. Telegram channel) that run on your side; if those channels run on the same host or a trusted network, you may not need to expose them. If you expose the whole Core, put it behind a reverse proxy that restricts which paths are visible (e.g. only /inbound and /ws to the internet).

---

## 2. Recommended path: Tailscale + optional auth proxy

A simple and secure way to “access from anywhere” without opening Core to the whole internet is **Tailscale**.

1. **Install Tailscale** on the machine that runs Core (and on your phone/laptop if you want to use WebChat from there).
2. **Do not bind Core to 0.0.0.0 on a public port.** Either:
   - Bind to **127.0.0.1** and use **Tailscale Serve** to expose the Core port only on your Tailscale network, or  
   - Bind to **0.0.0.0** but **do not** forward port 9000 from the internet; only Tailscale IPs can reach it.
3. From another device on the same Tailscale network, use the machine’s **Tailscale IP** (e.g. `100.x.x.x:9000`) to reach Core. No API key strictly required if only Tailscale nodes can connect, but you can still set **auth_enabled** for defense in depth.

**Tailscale Funnel** (public HTTPS URL): If you want a public URL (e.g. for a webhook or a bot that cannot join Tailscale), you can use **Tailscale Funnel** to expose a single HTTPS endpoint. Put an **auth proxy** (e.g. Caddy with basic auth, or a small service that checks a shared secret and forwards to Core) in front of Core so that the funnel URL is not open to everyone. Then:

- Public internet → Funnel URL (HTTPS) → auth proxy (check key or basic auth) → Core /inbound (and optionally /ws).

This way Core itself can stay bound to localhost and only the auth proxy talks to Core.

### Summary

| Approach | When to use |
|----------|-------------|
| **auth_enabled + auth_api_key** | You expose Core (or a reverse proxy in front of it) to the internet; clients send the key in headers. |
| **Tailscale only** | You don’t expose Core to the public; only Tailscale devices can reach it. Optional: still set API key for extra safety. |
| **Tailscale Funnel + auth proxy** | You need a public HTTPS URL; the proxy does auth, then forwards to Core. |

For most “access from anywhere” use cases, **Tailscale without public exposure** is the simplest and safest; add **auth_enabled** when you need to allow non-Tailscale clients (e.g. a hosted bot) that know the key.
