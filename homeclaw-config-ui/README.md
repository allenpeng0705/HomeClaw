# HomeClaw configuration (web UI)

A small standalone app to **configure** HomeClaw on an ongoing basis (not only first-time setup). It talks to the **Portal** HTTP API (`GET` / `PATCH` `/api/config/{name}`) and does **not** change the built-in Portal or Core UIs.

## Prerequisites

- Portal running (default `http://127.0.0.1:18472`).
- Your `portal_secret` from HomeClaw config (same value Portal uses for API auth).

## Development

```bash
cd homeclaw-config-ui
npm install
npm run dev
```

Open the URL Vite prints (default dev server port **5175**). The Vite dev server **proxies** `/api` to Portal so the browser does not need CORS on Portal.

If Portal runs on another host/port:

```bash
PORTAL_TARGET=http://127.0.0.1:18472 npm run dev
```

## Usage

1. Enter the **Portal secret** (stored in `sessionStorage` for this tab only).
2. Pick a config tab (LLM, Skills & plugins, etc.).
3. Edit the JSON and **Save** (merge PATCH via Portal).

Invalid JSON is rejected before send. Errors from the API are shown in the banner.

## Production build

`npm run build` outputs `dist/`. Serve `dist/` behind any static host. **You still need** either:

- The same **reverse proxy** pattern (proxy `/api` → Portal), or
- CORS enabled on Portal for your UI origin (not added in this repo by default).

For a single-machine workflow, pointing nginx at both the static files and `/api` → Portal is typical.
