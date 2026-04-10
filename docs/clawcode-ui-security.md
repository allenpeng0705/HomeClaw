# Claw-Code Web UI — security notes

**Primary UI (single port):** Core serves **`GET /clawcode`** (static HTML) and **`GET /clawcode/config`** (`{"user_id": "…"}` for the default field; optional `clawcode.web_ui_default_user_id` in merged config). The page uses **same-origin** **`/api/clawcode/*`**, **`/inbound`**, and **`X-API-Key`** when Core has **`auth_enabled`**.

**Optional:** The **WebChat** channel also serves **`/clawcode`** and can proxy **`/api/clawcode/*`** and **`POST /api/inbound`** to Core using **`CORE_URL`** in `channels/.env` and the channel’s API key — useful if you already terminate TLS on the WebChat origin.

## Threat model (self-hosted)

- HomeClaw assumes a **trusted LAN/VPN/Tailscale** audience. The Claw-Code page is a **powerful client**: it can start long-running agent turns and approve risky tools if the bound Core user matches session ownership.
- **Do not** expose Core (**9000**) or WebChat (**8014**) to the open internet **without** TLS, firewall rules, and **`auth_enabled` + API key** on Core. If you publish **only** Core, **`/clawcode`** is on the same surface as the rest of the API.

## CSRF and cookies

- Browser calls from the Claw-Code page use **`fetch`** with **`X-API-Key`** (or WebChat’s channel key when the page is served from WebChat). That is **not** the same as a cookie session: arbitrary third-party sites cannot set `X-API-Key` in cross-origin requests from the user’s browser (forbidden header names). Classic **cookie-based CSRF** against Core does not apply to this header pattern.
- If you add **cookie auth** to the same origin in the future, review CSRF for those routes separately.

## Rate limiting

- Core does not ship per-IP rate limits on `/inbound` by default. For Claw-Code exposed beyond a small trusted group, put a **reverse proxy** (nginx, Caddy) rate limits in front of Core (and WebChat if you use it).

## File listing API

- **`GET /api/clawcode/sessions/{id}/files`** only resolves paths **under the session `cwd`** and requires **`owner_user_id`** to match the session owner. It is intended for IDE-style UIs, not public directory browsing.

## Companion app

- The Companion uses the **same Core API key** (or Bearer where applicable) as other direct Core calls. Default **Open in browser** uses Core’s **`/clawcode`**. **`clawcode_web_ui_url`** (optional override) should be **`https://`** when the UI is behind TLS.

## Reverse proxy (TLS + single hostname)

Put **Caddy** or **nginx** in front so browsers and phones use `https://` while upstream stays HTTP on localhost.

**Upstream ports (defaults):** Core **9000** (includes **`/clawcode`**). WebChat **8014** only if you use that channel’s UI or proxy.

### Caddy (example — Core only, Claw-Code on same host)

```caddyfile
homeclaw.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:9000
}
```

### Caddy (example — WebChat in front, Core separate)

```caddyfile
claw.example.com {
    encode gzip

    # WebChat proxies /api/clawcode/* and /inbound to Core (see channels/webchat)
    handle /clawcode* {
        reverse_proxy 127.0.0.1:8014
    }
    handle /api/clawcode/* {
        reverse_proxy 127.0.0.1:8014
    }
    handle /* {
        reverse_proxy 127.0.0.1:8014
    }
}

core.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:9000
}
```

Point **`channels/.env`** `CORE_URL` at `https://core.example.com` when WebChat proxies to Core. Use **`wss://`** if you terminate TLS on the proxy and WebChat exposes WebSockets on the same origin.

### nginx (example)

```nginx
server {
    listen 443 ssl http2;
    server_name claw.example.com;

    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8014;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name core.example.com;

    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
    }
}
```

Add **`limit_req`** or WAF rules if exposing beyond a small trusted group. Keep **`auth_enabled`** and API keys on Core.

## WebSockets and SSE (Companion / long requests)

- **Server-Sent Events:** `POST /inbound` with `stream: true` needs a **long-lived** response. Set **`proxy_read_timeout`** (nginx) or **`flush_interval`** / equivalent on Caddy so the proxy does not close the stream early (the examples above use `proxy_read_timeout 600s` on Core; use the same or higher on the WebChat vhost if streaming is proxied there).
- **WebSockets:** If clients connect to **`/ws`** (or similar) on Core or WebChat through the proxy, enable upgrade headers, for example:

```nginx
location /ws {
    proxy_pass http://127.0.0.1:9000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400s;
}
```

Adjust **`proxy_pass`** port and path to match where your channel or Core exposes the socket.

## Companion deep links (Android)

The app registers **`homeclaw://`** hosts **`agent`**, **`chat`**, **`clawcode`**, and **`connect`** (QR pairing) so notification links and `homeclaw://connect?...` open the correct activity. iOS uses the **`homeclaw`** URL scheme without per-host manifest entries.
