# Remote access and auth

When you expose HomeClaw Core on the internet (e.g. so a Telegram bot or WebChat can reach it from anywhere), you need to secure it. This doc describes two approaches: **built-in API key** and **recommended path (Tailscale + optional auth proxy)**. For **encryption** between Companion and Core (TLS/HTTPS) and user-to-user messaging, see [CompanionEncryptionAndSecurity.md](CompanionEncryptionAndSecurity.md).

---

## 1. Built-in API key (Core auth)

### How to store the API key (detailed steps)

You can store the API key in **plain text** (simplest) or **encrypted at rest** (recommended if the config file is on shared or untrusted storage).

#### Option A: Plain text in config (default)

1. **Edit Core config**  
   Open `config/core.yml` and set:
   ```yaml
   auth_enabled: true
   auth_api_key: "your-long-random-key-here"   # e.g. 32+ characters
   ```
2. **Generate a strong key** (optional but recommended):
   - Linux/macOS: `openssl rand -base64 32`
   - Or use a password manager to generate a long random string.
3. **Restart Core** so it loads the new key.
4. **Companion / channels**  
   - In Companion: Settings → Core URL and API key, or scan the QR from Core’s `/pinggy` page (the connect URL includes the key).  
   - For channels or scripts: set `X-API-Key: your-long-random-key-here` (or `Authorization: Bearer your-long-random-key-here`) on every request to Core.

**Security:** Do not commit real keys to git. Use a secrets manager or env vars and inject into `core.yml` if needed.

---

#### Option B: Encrypted at rest (recommended for shared/untrusted storage)

With this option, the value in `config/core.yml` is stored as `encrypted:<base64>` instead of plain text. Core and Portal encrypt when saving and decrypt when loading using a key from the environment.

**Prerequisites**

- `pip install cryptography` (same as for app-layer encryption / APNs).
- A secret string to use as the encryption key (e.g. a long random value or a passphrase). This is **not** the API key itself; it is used only to encrypt/decrypt the API key in the config file.

**Steps**

1. **Set the encryption key in the environment**  
   Before starting Core (and Portal, if you use it to edit config), set:
   - **Linux/macOS (current shell):**
     ```bash
     export HOMECLAW_AUTH_KEY="your-encryption-secret"
     ```
   - **Linux/macOS (systemd):** add to the service file:
     ```ini
     [Service]
     Environment="HOMECLAW_AUTH_KEY=your-encryption-secret"
     ```
   - **Windows (PowerShell, current session):**
     ```powershell
     $env:HOMECLAW_AUTH_KEY = "your-encryption-secret"
     ```
   - **Windows (persistent):** System Properties → Environment variables → New (user or system) → `HOMECLAW_AUTH_KEY` = `your-encryption-secret`.

   Use a strong value (e.g. `openssl rand -base64 32`). Anyone with this value can decrypt the API key; keep it secret and do not commit it.

2. **Install cryptography (if not already):**
   ```bash
   pip install cryptography
   ```

3. **Set or update the API key** (Core will store it encrypted):
   - **Via Portal:** Open Portal → Core config → set **Auth API key** and save. The file will show `auth_api_key: "encrypted:..."`.
   - **Via Core API:** `PATCH /api/config/core` with `{"auth_api_key": "your-actual-api-key"}` (with API key or session auth as required). Core encrypts before writing.
   - **Manually in config:** You can still paste a **plain** key in `core.yml` and save; on next load Core uses it as-is. The **next time** Core or Portal writes the config (e.g. after a PATCH or Portal save), the value will be written encrypted as long as `HOMECLAW_AUTH_KEY` is set.

4. **Restart Core** so it reads the config and decrypts the API key in memory.

5. **Companion and channels**  
   No change: they still send the **plain** API key in headers (`X-API-Key` or `Authorization: Bearer <key>`). Encryption only affects how the key is stored in `core.yml`.

**Important**

- If you **remove** `HOMECLAW_AUTH_KEY` or run Core without it, an existing `encrypted:...` value in config will **not** decrypt (Core will treat it as missing/invalid). Set the env again or replace the value in config with the plain API key temporarily, then set the env and save again to re-encrypt.
- **Backup:** Back up `config/core.yml` and keep `HOMECLAW_AUTH_KEY` safe; both are needed to recover the stored API key.
- **Rotation:** To change the API key, set the new key via Portal or PATCH (with current auth). Core/Portal will write it encrypted if `HOMECLAW_AUTH_KEY` is set.

---

Core can require an API key for **POST /inbound**, **WebSocket /ws**, **POST /process**, **POST /local_chat**, **GET /shutdown**, and all routes under **/api/config/** and **/api/** that use the same auth. When **auth_enabled** is true, these entry points require `X-API-Key` or `Authorization: Bearer <key>`. Routes such as **GET /ready**, **GET /pinggy**, **POST /api/portal/auth**, and **GET /portal-ui** (or mount) may remain unauthenticated by design (health check, login, Portal UI).

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
- **Optional: store auth_api_key encrypted at rest.** Set the environment variable **HOMECLAW_AUTH_KEY** (any secret string) before starting Core. When set, Core and Portal will save `auth_api_key` in config as `encrypted:<base64>` and decrypt it on load. Requires `pip install cryptography`. Plain values in config continue to work if the env is not set. For a full design description (module, key derivation, load/save paths, compatibility), see [AuthApiKeyEncryptedStorage.md](AuthApiKeyEncryptedStorage.md).
- When **auth_enabled** is true, /inbound, /ws, /process, /local_chat, /shutdown, and protected /api/* routes require the key. Channels and Companion must send the key in headers when calling these endpoints. If you expose Core to the internet, put it behind a reverse proxy or use Tailscale so only trusted clients can reach it.

### Companion app compatibility

The Companion app works with both **plain** and **encrypted** API key storage. Encryption is transparent to the app.

**Auth flow**

1. **Connect to Core**  
   User sets **Core URL** (and optionally **API key**) in Settings, or scans the QR from Core’s `/pinggy` page (URL and API key are in the connect link). The app stores URL and API key in device storage (SharedPreferences).
2. **Login**  
   User logs in with **username + password** via `POST /api/auth/login`. That request is sent with the **API key** in headers (`X-API-Key` / `Authorization: Bearer <key>`). Core returns a **session token** and user id.
3. **After login**  
   - **API-key–protected routes** (config, inbound, WebSocket, push token, user-message, user-inbox): the app sends the **stored API key** in headers.  
   - **Session-only routes** (me, friends, chat-history, skills list/search/install/remove, friend-requests): the app sends the **session token** (`Authorization: Bearer <session_token>`).

**Features checked**

| Feature | Auth used | Works with encrypted API key? |
|--------|-----------|--------------------------------|
| Connect (URL + API key from scan or manual) | — | Yes (Companion never sees encrypted value; user enters or scans plain key). |
| Login (username/password) | API key | Yes. |
| Chat (send/receive, sync, WebSocket push) | API key for /inbound, /ws | Yes. |
| Config Core (read/edit core.yml, auth_api_key field) | API key | Yes. Saving a new API key from Companion sends plain text; Core/Portal encrypt on save when `HOMECLAW_AUTH_KEY` is set. |
| Config Users (list/add/edit/delete users) | API key | Yes. |
| Me, Friends, Avatars, Password change | Session token | Yes. |
| Chat history (per user/friend) | Session token | Yes. |
| Skills (list, search, install, remove) | Session token | Yes. |
| Friend requests (list, send, accept, reject) | Session token | Yes. |
| User-to-user messages, Inbox | API key | Yes. |
| Push token registration | API key | Yes. |
| File upload to Core | API key | Yes. |

**When auth is disabled** (`auth_enabled: false`): leave the API key empty in Companion. All requests succeed without the key. Session login and session-only routes still work.

**Summary:** No Companion code changes are required for encrypted API key storage. The app only ever handles the plain API key (entered or from QR). Core and Portal are responsible for encrypting/decrypting in config.

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
