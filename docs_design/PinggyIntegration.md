# Pinggy integration design

This doc answers: (1) whether we can integrate Pinggy into HomeClaw, (2) config in core.yml, (3) displaying public URL and QR, and (4) whether the Companion app already supports QR scan-to-connect.

---

## 1. Is integration possible?

**Yes.** The [Pinggy Python SDK](https://pypi.org/project/pinggy/) supports:

- `tunnel = pinggy.start_tunnel(forwardto="localhost:PORT", token="...")`
- `tunnel.urls` — list of public URLs for the tunnel
- Optional non-blocking use (run tunnel in a background thread so Core keeps running)

Flow: when Core starts, if `pinggy.token` is set in config, start a Pinggy tunnel in a **background thread** that forwards `http://localhost:<core_port>` to the public URL. After the tunnel is up, expose that URL (and a QR for it) via an API or the CLI.

---

## 2. Config in core.yml

Proposed shape:

```yaml
# Optional: Pinggy tunnel for remote access. If token is set, Core starts a Pinggy
# tunnel to http://localhost:<port> and exposes the public URL (and QR) for the Companion app.
pinggy:
  token: ""   # empty = do not start Pinggy; set to your Pinggy token to enable
  # port is taken from server port (core port) above; no need to duplicate
```

- **Empty `token`** → do not start Pinggy.
- **Non-empty `token`** → start Pinggy after Core is listening, forwarding to `http://localhost:<core_port>` (using the same `host`/`port` from the server section).

Optional: `pinggy.enabled: true/false` to allow token in env while disabling without clearing the token.

---

## 3. Display public URL and QR

Options:

**A) API only (JSON)**  
- **GET /api/pinggy** (or **GET /api/pinggy/connect**) — returns JSON, e.g.:
  - `public_url`: the Pinggy HTTPS URL (e.g. `https://xxx.pinggy.io`)
  - `connect_url`: full string for the Companion app, e.g. `homeclaw://connect?url=<public_url>&api_key=<auth_api_key>` (if auth_enabled)
- No QR image served; caller (CLI or admin UI) generates QR from `connect_url`.

**B) API + QR image**  
- Same JSON from **GET /api/pinggy**.
- **GET /api/pinggy/qr** — returns a PNG (or HTML page with embedded QR) of the `connect_url` so any browser can show “scan this with Companion”.
- Core would need a QR library (e.g. `qrcode[pil]`) as an optional dependency.

**C) Log + CLI**  
- When Pinggy starts, Core logs the public URL (and optionally the `connect_url`).
- User runs `homeclaw pair --url <public_url>` (and `--api-key` if auth) to print a QR; the existing CLI already supports that.

**Recommended:** Implement **A** and **C** first: add **GET /api/pinggy** returning `public_url` and `connect_url`, and start Pinggy in a background thread when `pinggy.token` is set, logging the public URL at startup. Optionally add **B** later (e.g. **GET /api/pinggy/qr** returning HTML with QR) so users can open that page and scan.

**Implemented:** When Pinggy is enabled and `pinggy.open_browser` is true in core.yml, Core opens the default browser to **GET /pinggy** (e.g. `http://127.0.0.1:<port>/pinggy`). That page shows the public URL, the `homeclaw://connect?url=...&api_key=...` link, and an embedded QR code so the user can scan with Companion (Settings → Scan QR to connect). The /pinggy page is unauthenticated so it works before pairing.

---

## 4. Does the Companion app support QR scan to connect?

**Yes.** The Companion app already has “Scan QR to connect”:

- **Where:** Settings → **Scan QR to connect** (opens the scan screen).
- **What it expects:** A QR code (or URL) encoding:
  - **Scheme:** `homeclaw://connect?url=<Core URL>&api_key=<optional API key>`
- **What it does:** Parses `url` and `api_key`, saves them via `CoreService.saveSettings(baseUrl: url, apiKey: apiKey)`, then the app uses that Core URL and API key for all requests.

Relevant code:

- **Scan / parse:** `lib/screens/scan_connect_screen.dart` — parses `homeclaw://connect?url=...&api_key=...` and saves to CoreService.
- **Settings entry:** `lib/screens/settings_screen.dart` — “Scan QR to connect” with `Icons.qr_code_scanner` opens the scan screen.

So for Pinggy:

1. Core (or CLI) produces a **connect URL**: `homeclaw://connect?url=<Pinggy public URL>&api_key=<core auth_api_key>` (if auth_enabled).
2. That string is shown as a QR (e.g. via CLI `homeclaw pair --url <pinggy_url>` or a future **GET /api/pinggy/qr** page).
3. User opens Companion → Settings → Scan QR to connect → scans the QR.
4. Companion saves the Pinggy URL and API key and connects through the tunnel.

No change to the Companion app is required for this flow.

---

## 5. Implementation sketch

1. **core.yml**  
   - Add a `pinggy:` section with `token: ""`.

2. **Core startup (e.g. in `core/core.py`)**  
   - After the server is listening (e.g. in `run()` after uvicorn has started, or in a lifespan/startup hook):
     - If `pinggy.token` is set, start Pinggy in a **daemon thread**:
       - `tunnel = pinggy.start_tunnel(forwardto=f"localhost:{core_port}", token=pinggy_token)` then `tunnel.start()` (or the non-blocking API the SDK provides).
     - Store the tunnel instance and its `tunnel.urls` (e.g. first HTTPS URL) in a module-level or Core-instance variable.

3. **GET /api/pinggy**  
   - If Pinggy is not enabled or not ready, return 404 or `{ "enabled": false }`.
   - Otherwise return:
     - `public_url`: from `tunnel.urls`
     - `connect_url`: `homeclaw://connect?url=<public_url>&api_key=<auth_api_key>` (if auth_enabled; else omit api_key).

4. **CLI `homeclaw pair`**  
   - Optional flag, e.g. `homeclaw pair --use-pinggy`:
     - Call **GET /api/pinggy** on the configured Core URL (e.g. `http://127.0.0.1:9000`).
     - If the response contains `connect_url`, use that for the QR (and print it); otherwise fall back to current behavior (CLI URL + API key).

5. **Shutdown**  
   - On Core shutdown, call `tunnel.stop()` if the Pinggy tunnel is running.

6. **Dependencies**  
   - Add `pinggy` to `requirements.txt` (optional or required depending on whether we want Pinggy to be optional at runtime when token is set).

---

## 6. Summary

| Question | Answer |
|----------|--------|
| Can we integrate Pinggy? | Yes; use the Pinggy Python SDK in a background thread, forwarding `localhost:<core_port>`. |
| Token in core.yml; empty = don’t start? | Yes; add `pinggy.token`; only start the tunnel when token is non-empty. |
| Display public URL and QR? | Yes; e.g. GET /api/pinggy (JSON with `public_url` and `connect_url`) and optionally GET /api/pinggy/qr (HTML/PNG). CLI `homeclaw pair --url <pinggy_url>` already shows a QR. |
| Does the Companion app have QR scan to connect? | Yes; Settings → “Scan QR to connect” parses `homeclaw://connect?url=...&api_key=...` and saves URL + API key. No app change needed. |
