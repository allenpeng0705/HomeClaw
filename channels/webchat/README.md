# WebChat channel

Minimal **browser UI** that talks to the Core over **WebSocket /ws**. Run this channel to serve the page; the page loads the Core WebSocket URL from the server (which reads **channels/.env** only). No IM bot token; add `webchat_local` (or the value of `WEBCHAT_USER_ID`) to `config/user.yml` under `im` if you restrict by user.

## Run

```bash
python -m channels.run webchat
```

Then open **http://127.0.0.1:8014/** in your browser. The page fetches `/config` (ws_url and user_id from channels/.env), connects to Core `/ws`, and sends/receives messages.

## Config

- **channels/.env**: Core URL (core_host, core_port or CORE_URL). Optional: `WEBCHAT_USER_ID` (default `webchat_local`), `WEBCHAT_HOST`, `WEBCHAT_PORT` (default 8014).
- **config/user.yml**: Add `webchat_local` (or your WEBCHAT_USER_ID) under `im` for a user with `IM` permission if you use allowlists.

## From anywhere

Expose Core (or this WebChat server) via Tailscale or SSH tunnel, then open the WebChat URL in the browser.
