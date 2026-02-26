# WebChat channel

Minimal **browser UI** that talks to the Core over **WebSocket /ws**. Run this channel to serve the page; the page loads the Core WebSocket URL from the server (which reads **channels/.env** only). No IM bot token; ensure the default user (e.g. `webchat_user`) exists in `config/user.yml` so Core accepts the request (match by user id/name).

**Synced with system plugin WebChat** (homeclaw-browser control-ui): same behavior — images are uploaded via **POST /api/upload** (channel proxies to Core), Core saves to `database/uploads/`, and the client sends the chat message with **paths** in `payload.images` so the model receives the image from disk. Video/audio/other files still go as data URLs.

**Features (Companion parity):**
- **Assistant vs Friend:** Dropdown "Assistant" (main chat) or "Friend" (Friends plugin). When Friend is selected, the client sends `session_id`, `conversation_type`, and `channel_name` = **friend** (Core config `companion.session_id_value`, default `friend`).
- **Location:** When the browser supports Geolocation API, the page requests position before each send (with permission). If granted, `payload.location` is set to `"lat,lng"` so Core can store latest location per user (see SystemContextDateTimeAndLocation.md). If denied or unavailable, the message is sent without location.

## Run

```bash
python -m channels.run webchat
```

Then open **http://127.0.0.1:8014/** in your browser. The page fetches `/config` (ws_url and user_id from channels/.env), connects to Core `/ws`, and sends/receives messages.

## Config

- **channels/.env**: Core URL (core_host, core_port or CORE_URL). Optional: `WEBCHAT_USER_ID` (default `webchat_user`), `WEBCHAT_HOST`, `WEBCHAT_PORT` (default 8014). If Core has **auth_enabled**, set **CORE_API_KEY** so the channel can proxy uploads to Core `/api/upload`.
- **config/user.yml**: Ensure a user with id matching WEBCHAT_USER_ID exists (e.g. `id: webchat_user`, `type: companion`). Core matches by user id/name for WebSocket /inbound.

## Settings (in-page, like Companion app)

The WebChat page has a **Settings** section (expand "Settings (Core URL, API key)"):
- **Core URL (optional override)**: Override the Core URL from channels/.env (e.g. `http://127.0.0.1:9000`). Leave empty to use the server default. Used for the WebSocket connection and for upload/KB sync (channel forwards your API key when proxying).
- **API Key (optional)**: Set when Core has **auth_enabled**. Stored in the browser (localStorage) and sent as query param on WebSocket and as `X-API-Key` on proxy requests. The channel forwards the client’s API key when proxying to Core; if the client does not send one, the channel uses **CORE_API_KEY** from channels/.env.

## From anywhere

Expose Core (or this WebChat server) via Tailscale or SSH tunnel, then open the WebChat URL in the browser.
