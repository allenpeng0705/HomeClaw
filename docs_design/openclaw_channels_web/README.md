# WhatsApp Web Channel (OpenClaw)

This channel connects OpenClaw to **WhatsApp** using the **WhatsApp Web** protocol via [Baileys](https://github.com/WhiskeySockets/Baileys). It is exposed in OpenClaw as the **`web`** channel (internal name; user-facing it is “WhatsApp Web”).

**Implementation location (clawdbot):** `src/web/` — channel entry and barrel: `src/channel-web.ts`, `src/channels/web/index.ts`.

---

## Prerequisites

- **Node.js** (LTS) and OpenClaw (clawdbot) runtime.
- **Baileys** (`@whiskeysockets/baileys`) — used for WhatsApp Web socket, auth, and message send/receive.
- **First-time linking:** A phone with WhatsApp and the ability to scan a QR code (or use pairing code if supported by Baileys).

---

## Enabling the channel

- The channel is enabled when the **web** (WhatsApp) plugin/channel is turned on in OpenClaw config.
- Ensure `channels.whatsapp` (and optionally `channels.whatsapp.accounts`) is configured if you use multi-account.
- Use the CLI to link a device:  
  `openclaw channels login --channel web`  
  (and optionally `--account <accountId>` for multiple accounts).

---

## Auth and session storage

- **Auth directory:** Stored under OpenClaw’s OAuth/state directory. Default: `<stateDir>/oauth/whatsapp/<accountId>` (e.g. `default`).
- **`WA_WEB_AUTH_DIR`:** Exported constant for the default auth dir (single-account). Multi-account dirs are derived from `channels.whatsapp.accounts[accountId]` or `<oauth>/whatsapp/<accountId>`.
- **Files:** `creds.json` (and optional `creds.json.bak` backup) hold Baileys auth state. Do not share these; they grant full access to the linked WhatsApp account.
- **QR / pairing:** First link is done by running `openclaw channels login --channel web`. The runtime shows a QR code (or pairing code); scan with WhatsApp on your phone (Linked devices). After that, reconnects use stored credentials.

---

## Main entry points and exports

| Export / concept | Description |
|------------------|-------------|
| `monitorWebChannel` | Starts the WhatsApp Web listener: socket, inbound monitor, auto-reply/heartbeat. Called by the main runtime when the web channel is enabled. |
| `monitorWebInbox` | Inbound message stream: receives messages, applies access control, dedupe, and forwards to the Gateway/session layer. |
| `loginWeb` | Interactive login: create socket, wait for connection (QR or pairing), save credentials. |
| `createWaSocket` / `waitForWaConnection` | Low-level: create Baileys socket and wait until connected. |
| `sendMessageWhatsApp` | Send a text (and optional media) to a JID. Used by the outbound delivery layer. |
| `sendPollWhatsApp` | Send a poll (if supported by Baileys). |
| `loadWebMedia` | Download/optimize media from a URL for sending (e.g. images). Used by WhatsApp and other channels that send the same media. |
| `pickWebChannel` / `logWebSelfId` | Resolve which WhatsApp account/channel to use; log self JID. |
| `webAuthExists` / `WA_WEB_AUTH_DIR` | Check if credentials exist; default auth dir. |

---

## Config and environment

- **Channel config:** Under `channels.whatsapp` (and `channels.whatsapp.accounts` for multi-account). Options include: `allowFrom`, `groupAllowFrom`, `groupPolicy`, `dmPolicy`, `messagePrefix`, `sendReadReceipts`, `mediaMaxMb`, `ackReaction`, `blockStreaming`, etc.
- **Auth path:** Derived from `resolveOAuthDir()` and optional account id; not usually set directly except for overrides.
- **Plugin auto-enable:** OpenClaw may auto-enable the web channel when WhatsApp auth exists (e.g. `hasAnyWhatsAppAuth`).

See OpenClaw config schema and `config/schema.hints.ts` for full keys.

---

## Troubleshooting

- **“WhatsApp asked for a restart (515)”:** Creds are saved; the login flow will retry once. Run login again if it still fails.
- **Session logged out:** Run `openclaw channels login --channel web` again to relink.
- **No messages received:** Check `allowFrom` / `groupAllowFrom` and group policy; ensure the sender is allowed.
- **Send fails:** Ensure an active listener is running (`monitorWebChannel`) and the target JID is correct (e.g. `1234567890@s.whatsapp.net`).
- **Media send fails:** Check `loadWebMedia` and size limits (`mediaMaxMb`); see `media.ts` and outbound tests.

---

## Related files (clawdbot)

- **Session / socket:** `src/web/session.ts`, `src/web/login.ts`, `src/web/auth-store.ts`
- **Inbound:** `src/web/inbound.ts`, `src/web/inbound/monitor.ts`, `src/web/inbound/extract.ts`, `src/web/inbound/access-control.ts`, `src/web/inbound/dedupe.ts`, `src/web/inbound/types.ts`
- **Outbound:** `src/web/outbound.ts`, `src/web/active-listener.ts`
- **Auto-reply / heartbeat:** `src/web/auto-reply.ts`, `src/web/auto-reply/` (impl, monitor)
- **Media:** `src/web/media.ts`
- **Accounts:** `src/web/accounts.ts`
- **Barrel / channel:** `src/channel-web.ts`, `src/channels/web/index.ts`

For architecture and data flow, see **ARCHITECTURE.md** in this folder.
