# Portal web (SPA shell)

React + Vite UI for first-time setup and sign-in. Production assets are written to `portal/static/app/` and served by FastAPI at `/app` (HTML) with scripts under `/static/app/`.

## Build

From repo root:

```bash
cd portal/web
npm install
npm run build
```

After changing TypeScript/React, run `npm run build` before shipping; CI can add this step later.

## Local dev

With Portal running on port 18472:

```bash
cd portal/web
npm run dev -- --port 5176
```

Vite defaults do not match production `base`; for local API calls, either:

- open the built app via Portal at `http://127.0.0.1:18472/app`, or
- add a `server.proxy` in `vite.config.ts` for `/api` → `http://127.0.0.1:18472` and set `base: '/'` temporarily.
