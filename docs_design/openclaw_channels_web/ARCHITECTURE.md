# WhatsApp Web Channel — Architecture and data flow

This document describes how the WhatsApp Web channel fits into OpenClaw: inbound flow, outbound flow, auto-reply/heartbeat, and integration with the Gateway and channel dock.

---

## High-level flow

```
Phone (WhatsApp) ←→ Baileys (WhatsApp Web) ←→ OpenClaw src/web ←→ Gateway / Channel dock / Sessions
```

- **Baileys** maintains the WebSocket and protocol with WhatsApp servers.
- **`src/web`** provides: session/socket lifecycle, inbound parsing and access control, outbound send, auto-reply/heartbeat, and media handling. It does **not** implement the WebChat UI; that is separate.

---

## Inbound flow

1. **Socket and listener**  
   `createWaSocket` (in `session.ts`) creates a Baileys socket with `useMultiFileAuthState(authDir)`. When the channel is enabled, `monitorWebChannel` starts the socket and wires it to the inbound pipeline.

2. **Inbound monitor**  
   `monitorWebInbox` (backed by `inbound/monitor.ts`) consumes Baileys events (messages, presence, etc.). It:
   - Filters to relevant message types.
   - Applies **access control** (`inbound/access-control.ts`): allowlists (`allowFrom`, `groupAllowFrom`), group policy, DM policy, pairing history.
   - **Dedupes** messages (`inbound/dedupe.ts`) to avoid double delivery.
   - **Extracts** text, media placeholders, location (`inbound/extract.ts`), and builds a normalized `WebInboundMessage` for the rest of OpenClaw.

3. **Send to Gateway / dock**  
   Normalized messages are passed to the channel dock (and session layer). The dock routes them to the right session, runs the agent, and may trigger outbound replies or tools.

4. **Types**  
   `inbound/types.ts` defines `WebInboundMessage`, `WebListenerCloseReason`, and related types used by the monitor and the rest of the stack.

---

## Outbound flow

1. **Caller**  
   When the agent (or a tool) decides to send a reply to WhatsApp, the outbound layer calls `sendMessageWhatsApp` (and optionally `sendPollWhatsApp`). These live in `outbound.ts`.

2. **Active listener**  
   Outbound send requires an **active** WhatsApp Web listener (socket connected). `requireActiveWebListener` (in `active-listener.ts`) ensures we have a running listener for the chosen account; it may throw or guide the user to run `openclaw channels login --channel web` if not.

3. **Markdown and media**  
   Outbound converts markdown to WhatsApp-friendly format (`markdownToWhatsApp`). If a `mediaUrl` is provided, `loadWebMedia` (in `media.ts`) fetches and optionally optimizes the file (e.g. image to JPEG), then attaches it to the message.

4. **Send**  
   Baileys socket sends the message to the target JID. Result (messageId, toJid) is returned to the caller.

---

## Auto-reply and heartbeat

- **Auto-reply** (e.g. “thinking” or “received” replies) and **heartbeat** (periodic pings to keep the session alive or show status) are implemented in `auto-reply.ts` and the `auto-reply/` folder (e.g. `auto-reply.impl.ts`, `auto-reply/monitor.ts`).
- They use the same outbound path: require active listener, then send messages or reactions as configured. Tuning (e.g. when to send, which recipients) is controlled by channel config and heartbeat visibility (e.g. `resolveHeartbeatVisibility` for “webchat” vs other channels).

---

## Integration with the Gateway and channel dock

- **Channel registration:** The “web” channel is registered like other channels. The main process (or plugin runtime) calls `monitorWebChannel` when the web channel is enabled; that starts the Baileys socket and the inbound monitor.
- **Gateway methods:** Gateway can expose web-specific methods (e.g. QR login, status); these are implemented in `gateway/server-methods/web.js` and call into `src/web` (login, auth store, etc.).
- **Other channels reusing web:** Telegram, Slack, Signal, iMessage, Discord, etc. can use `loadWebMedia` to send the same media URL on their channel; only the web channel owns the Baileys socket and WhatsApp send.

---

## Multi-account

- **Accounts:** `accounts.ts` resolves per-account config and auth dirs from `channels.whatsapp.accounts`. Each account has its own auth dir and can have its own allowlists, policies, and options.
- **Listener:** The runtime may run one listener per account (or a single listener that can switch). `pickWebChannel` / `requireActiveWebListener(accountId)` select the account for outbound.
- **Login:** `openclaw channels login --channel web --account <id>` logs in the given account; credentials are stored in that account’s auth dir.

---

## Security and untrusted content

- Inbound messages from WhatsApp are treated as **external/untrusted**. Links, media, and user text are sanitized or handled with care in the Gateway and agent (e.g. external-content checks, no arbitrary code execution from message content).
- Auth files (`creds.json`) must be kept private; they allow full access to the linked WhatsApp account.

---

## Moving this channel into `channels/web/` (future)

The plan (see **OpenClawWhatsAppWebAndFlutterAppsPlan.md** in `docs_design/`) is to move all of `src/web/` into `src/channels/web/` and keep the barrel at `channel-web.ts` (or under `channels/web/index.ts`) so that the WhatsApp Web channel fully lives under the channels folder. This document and README will then live next to the implementation under `src/channels/web/`.
