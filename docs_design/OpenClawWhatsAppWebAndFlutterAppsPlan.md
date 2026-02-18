# WhatsApp Web Channel + Flutter Companion Apps & Connectivity

This document plans (1) a WhatsApp Web channel in a channels folder with detailed docs, and (2) companion apps (Flutter, CLI) and how they connect to the backend (Tailscale, Cloudflare Tunnel, or other). Implementation is step-by-step without breaking existing modules.

---

## HomeClaw implementation (done in this repo)

- **WhatsApp Web channel:** Implemented in **HomeClaw** as **`channels/whatsappweb/`** (name `whatsappweb`). Contains:
  - **README.md**, **ARCHITECTURE.md**, **CONFIG.md** — detailed docs.
  - **channel.py** — minimal HTTP channel: `POST /webhook` forwards to Core **`/inbound`** with `channel_name=whatsappweb`; sync response returned to caller. A future Baileys (or other) bridge can POST here.
- **Clients:** **`clients/`** folder with:
  - **README.md** — overview: Flutter app and CLI connect to Core (URL + optional API key); Tailscale/Cloudflare are deployment options.
  - **clients/flutter/README.md** — placeholder for Flutter companion app (iOS, Android, macOS, Windows; Linux later).
  - **clients/cli/README.md** — placeholder for future CLI.
- **Connectivity:** **`docs_design/HomeClawCompanionConnectivity.md`** — how clients connect to HomeClaw Core (local, Tailscale, Cloudflare Tunnel, SSH); no SDK in app.
- **Run channel:** `python -m channels.run whatsappweb`. Core URL from `channels/.env`.

---

## OpenClaw (clawdbot) reference plan

The sections below describe the **OpenClaw (clawdbot)** codebase layout and plan (for reference or if you also maintain OpenClaw). Paths are relative to the clawdbot repo unless noted.

---

## Part 1: WhatsApp Web Channel in Channels Folder with Detailed Docs

### Current state

- **Implementation:** All WhatsApp Web (Baileys) logic lives under `src/web/`:
  - `login.ts`, `session.ts`, `qr-image.ts`, `login-qr.ts`, `active-listener.ts`, `auth-store.ts`
  - `inbound/` (monitor, extract, types), `outbound.ts`, `auto-reply/`, `media.ts`, `accounts.ts`
- **Barrel:** `src/channel-web.ts` re-exports from `./web/*`.
- **Channel entry:** `src/channels/web/index.ts` re-exports from `../../channel-web.js`.
- **Consumers:** Many files import from `../web/` or `../../web/` (e.g. `plugins/runtime`, `plugin-sdk`, `telegram/send`, `slack/send`, `gateway/server-methods/web.js`).

### Goal

- Put the WhatsApp Web channel **inside** the channels folder so it’s clearly a channel with one place for code + docs.
- Add **detailed documentation** (README, architecture, config, troubleshooting) next to the code.
- **Do not break** existing behaviour or external APIs; only move files and update imports.

### Plan (step-by-step)

1. **Create structure under `src/channels/web/`**
   - Move all of `src/web/*` into `src/channels/web/` preserving subdirs (e.g. `inbound/`, `auto-reply/`).
   - Keep file names and public exports unchanged so behaviour stays the same.

2. **Update barrel and channel entry**
   - Change `src/channel-web.ts` to re-export from `./channels/web/` (e.g. `./channels/web/login.js`, `./channels/web/session.js`, etc.) so existing `import … from "./channel-web.js"` still works.
   - Optionally make `src/channels/web/index.ts` the single source of truth and have `channel-web.ts` re-export from `./channels/web/index.js` only (if exports align).

3. **Update all internal imports**
   - Replace every `from "../web/…"` / `from "../../web/…"` with the new path under `channels/web/` (e.g. `from "../channels/web/…"` or `from "../../channels/web/…"`). This touches:
     - `src/plugins/runtime/index.ts`, `src/plugin-sdk/index.ts`, `src/index.ts`
     - `src/telegram/send.ts`, `src/telegram/bot/delivery.ts`, `src/slack/send.ts`, `src/signal/send.ts`, `src/imessage/send.ts`, `src/discord/*.ts`, `src/infra/outbound/*.ts`, `src/config/plugin-auto-enable.ts`, `src/gateway/server-methods/web.js`, `src/web/qr-image.test.ts`, etc.
   - Run tests and build after each batch to avoid regressions.

4. **Add documentation under `src/channels/web/`**
   - **README.md:** Purpose of the channel, prerequisites (Baileys, Node), how to enable (plugin/channel config), auth (QR, session storage, `WA_WEB_AUTH_DIR`), main entry points (`monitorWebChannel`, `loginWeb`, `sendMessageWhatsApp`, etc.), and links to config/schema.
   - **ARCHITECTURE.md (or a section in README):** Inbound flow (monitor → extract → session), outbound (sendMessageWhatsApp, media), auto-reply/heartbeat, and how it plugs into the Gateway and channel dock.
   - **CONFIG.md (optional):** Channel-specific config keys, env vars, and `gateway`/plugin settings that affect WhatsApp Web.

5. **Remove old `src/web/`**
   - After all imports point to `src/channels/web/` and tests pass, delete the empty `src/web/` directory.

6. **Optional: channels-level index**
   - If desired, add a short `src/channels/README.md` listing channels (e.g. web/WhatsApp Web, telegram, slack, …) with one-line descriptions and links to each channel’s README.

### Non-goals (no break)

- No change to public plugin SDK or Gateway APIs.
- No change to channel “name” or external identifiers; it remains the “web” channel (WhatsApp Web).
- No change to auth storage location or CLI behaviour.

---

## Part 2: Flutter Companion Apps (iOS, Android, Mac, Windows) and Connectivity

### Current state

- **Existing apps:** Native apps in `apps/`: `ios/`, `android/`, `macos/`, `shared/` (OpenClawKit in Swift). They act as Gateway **nodes** or **control-plane clients** (menu bar, Voice Wake, Talk Mode, camera, canvas, etc.). They connect to the Gateway over **WebSocket** (`ws://` or `wss://`).
- **Gateway connectivity:** Clients (CLI, WebChat, macOS app, device nodes) use a **single WebSocket URL** (+ optional token/password). The Gateway does not care how that URL was obtained.

### How companion apps connect to the Gateway / Core

- **Local:** `ws://127.0.0.1:18789` (default port; configurable). Same machine as the Gateway.
- **Remote URL:** `gateway.remote.url` in config — any `ws://` or `wss://` URL. This can be:
  - **Tailscale:** OpenClaw can run Tailscale **Serve** (tailnet-only) or **Funnel** (public). The Gateway stays on loopback; Tailscale exposes HTTPS that proxies to the Gateway. Clients use the Tailscale-provided URL (e.g. `wss://machine.tailnet-name.ts.net`) as `gateway.remote.url` (or enter it in the app). No extra “Tailscale SDK” in the app — just WebSocket + auth.
  - **Cloudflare Tunnel:** You run `cloudflared tunnel` (or similar) and point it at the Gateway’s HTTP/WS endpoint. The public URL (e.g. `wss://your-tunnel.trycloudflare.com`) is then used as `gateway.remote.url`. Same as Tailscale from the app’s perspective: one wss URL + token/password if required.
  - **Other:** Any reverse proxy (ngrok, Caddy, nginx, etc.) that exposes the Gateway’s WebSocket. App behaviour is unchanged: configure URL + auth.

So: **Companion apps do not “use Tailscale” or “use Cloudflare” directly** — they use a **WebSocket URL**. Whether that URL comes from Tailscale, Cloudflare Tunnel, or SSH port-forward is a deployment choice. The app only needs:

- Gateway URL (e.g. `ws://127.0.0.1:18789` or `wss://…`)
- Optional: token or password (if `gateway.auth.mode` is token/password)

### Tailscale vs Cloudflare Tunnel (for exposing the Gateway)

| Aspect | Tailscale (OpenClaw built-in) | Cloudflare Tunnel |
|--------|-------------------------------|-------------------|
| **Setup** | OpenClaw can auto-configure Serve/Funnel via `gateway.tailscale.mode` | Manual: run `cloudflared` and point at Gateway; set `gateway.remote.url` to the tunnel URL |
| **Network** | Serve = tailnet-only; Funnel = public | Public (or scoped by Cloudflare config) |
| **Auth** | Token/password recommended for Funnel; optional for Serve | Same: Gateway auth (token/password) over wss |
| **App change** | None | None — app just uses `gateway.remote.url` |

Conclusion: Use **Tailscale** if you want OpenClaw to manage exposure out of the box. Use **Cloudflare Tunnel** (or anything else) if you prefer that stack; set `gateway.remote.url` and optionally token/password. No change to Core or Gateway code required; companion apps only need the single WebSocket URL + auth.

### Flutter: feasibility and scope

- **Flutter** supports iOS, Android, macOS, Windows, Linux (and web). Focusing **first on iOS, Android, Mac, Windows** is reasonable; Linux can follow.
- **Same protocol:** Flutter app implements the same Gateway WebSocket protocol (node list, node.invoke, sessions, etc.) as the existing Swift/Kotlin apps. No Gateway changes.
- **No break:** Flutter apps are an **additional** option; existing native apps remain supported.

### Plan (step-by-step)

1. **Document connectivity**
   - In OpenClaw docs (e.g. gateway/remote, gateway/tailscale): state clearly that “clients only need a WebSocket URL + optional auth”; Tailscale and Cloudflare Tunnel are two ways to obtain that URL. Add a short “Companion app connectivity” section that links to this.
   - Optionally add a small **Connectivity.md** (e.g. under `docs/`) summarizing: local WS, remote URL, Tailscale Serve/Funnel, Cloudflare Tunnel, SSH tunnel; and that the app does not need Tailscale/Cloudflare SDKs.

2. **Flutter project**
   - Create a new Flutter project under `apps/flutter/` (or `apps/companion_flutter/`) with targets: iOS, Android, macOS, Windows. Do not remove or replace `apps/ios/`, `apps/android/`, `apps/macos/`.
   - Structure: lib (shared UI + Gateway client), platform-specific code only where needed (e.g. permissions, notifications).

3. **Gateway WebSocket client in Flutter**
   - Implement a Dart WebSocket client that:
     - Connects to a configurable URL (ws/wss).
     - Sends/receives JSON messages per existing Gateway protocol (same methods as Swift/Kotlin).
     - Supports token/password auth (e.g. via query params or first message as per Gateway docs).
   - Reuse or mirror the protocol types (node.list, node.invoke, etc.) from OpenClaw docs or shared spec.

4. **Settings and URL configuration**
   - Add a settings screen: Gateway URL, optional token/password. Persist locally (e.g. secure storage). No “Tailscale” or “Cloudflare” specific UI required — just “Gateway URL” and “Auth”.

5. **Features parity (incremental)**
   - Start with: connect, show status, maybe node list. Then add: node.invoke for device actions (if the Flutter app runs as a node), or only control-plane (status, chat) if the app is a client only. Match existing app features incrementally so existing modules are not broken.

6. **Linux later**
   - Once iOS/Android/Mac/Windows are stable, add Linux as a target in the same Flutter project and test.

### Non-goals (no break)

- Do not remove or alter existing native apps (Swift/Kotlin).
- Do not change Gateway protocol or Core behaviour for existing clients.
- Do not require Tailscale or Cloudflare in the app; they are deployment options only.

---

## Implementation order (summary)

1. **Phase 1 – WhatsApp Web channel**
   - Move `src/web/` → `src/channels/web/`, update `channel-web.ts` and all imports, add README + ARCHITECTURE (and optional CONFIG) under `src/channels/web/`, remove `src/web/`, run tests.

2. **Phase 2 – Connectivity docs**
   - Add or update OpenClaw docs (and optional Connectivity.md) explaining WebSocket URL + auth, Tailscale vs Cloudflare Tunnel, and that companion apps only need URL + auth.

3. **Phase 3 – Flutter companion app**
   - Create `apps/flutter/`, implement Gateway WebSocket client and settings (URL + auth), then add features step by step (status, nodes, invoke, etc.) without changing existing modules.

This keeps existing behaviour intact and delivers the WhatsApp Web channel in the channels folder with clear docs, plus Flutter companion apps and a clear connectivity story (Tailscale, Cloudflare Tunnel, or any wss URL).

---

## Where the docs live (HomeClaw repo)

The following were added in **HomeClaw** so you can copy them into **clawdbot** when ready (no code changes required to use them):

- **WhatsApp Web channel docs:**  
  `docs_design/openclaw_channels_web/README.md` and `ARCHITECTURE.md`  
  Copy these into `clawdbot/src/channels/web/` (or into `clawdbot/src/channels/whatsapp-web/` if you add a dedicated subfolder). They document the channel and point to the current implementation under `src/web/`.

- **Companion connectivity:**  
  `docs_design/OpenClawCompanionConnectivity.md`  
  Copy into `clawdbot/docs/` (e.g. as `CompanionConnectivity.md`) or link from OpenClaw’s gateway/remote and Tailscale docs.
