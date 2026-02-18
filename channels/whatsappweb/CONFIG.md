# WhatsApp Web Channel — Config (HomeClaw)

Config and environment variables used by the **whatsappweb** channel and an optional bridge.

---

## Channel → Core

| Source | Key | Description |
|--------|-----|-------------|
| `channels/.env` | `core_host` | Core HTTP host (default `127.0.0.1`). |
| `channels/.env` | `core_port` | Core HTTP port (default `9000`). |
| `channels/.env` | `CORE_URL` | Override: full Core URL (e.g. `http://192.168.1.10:9000`). |

Core’s `/inbound` and `/process` are called using this URL. When Core has `auth_enabled: true`, the channel (or bridge) must send the required API key (e.g. `X-API-Key` or `Authorization: Bearer <key>`).

---

## Channel server (this process)

| Source | Key | Description |
|--------|-----|-------------|
| Env / defaults in `channel.py` | `WHATSAPPWEB_HOST` | Bind host (default `0.0.0.0`). |
| Env / defaults in `channel.py` | `WHATSAPPWEB_PORT` | Bind port (default e.g. `8010`). |

The bridge POSTs to `http://<WHATSAPPWEB_HOST>:<WHATSAPPWEB_PORT>/webhook` (or the endpoint defined in `channel.py`).

---

## Optional bridge (e.g. Baileys)

When you add a Node (or other) bridge in this repo or elsewhere:

| Purpose | Suggestion |
|---------|------------|
| **Channel URL** | Env var e.g. `HOMECLAW_CHANNEL_URL=http://127.0.0.1:8010` so the bridge knows where to POST. |
| **Auth dir** | Env var e.g. `WA_WEB_AUTH_DIR=./auth`; store credentials there, add `auth/` to `.gitignore`. |
| **Core auth** | If Core uses `auth_enabled`, pass the key to the channel or have the channel send it when calling Core; the bridge does not need to know the Core key if the channel does the Core HTTP calls. |

---

## Core config (core.yml) relevant to channels

- **auth_enabled / auth_api_key:** If enabled, channels (and any client calling `/inbound` or `/ws`) must send the API key.
- **session.dm_scope:** Affects how Core scopes sessions (e.g. per `user_id` for `whatsappweb`).
- **config/user.yml:** Allowlist / permissions; `user_id` from the channel should match the identity used there.

---

## Summary

- **Minimum to run the channel:** Set Core URL in `channels/.env` (`core_host`/`core_port` or `CORE_URL`).
- **To receive WhatsApp messages:** Run a WhatsApp Web bridge that POSTs to this channel’s ingestion endpoint; configure the bridge with this channel’s URL and, if needed, auth dir for its own credentials.
