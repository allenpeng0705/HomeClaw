# Companion App: Encryption and Security

Security and privacy are important for messages between the **Companion app and Core** and, in the multi-user case, **between Companion app and Companion app** (user-to-user). This document describes what is in place, what is recommended, and a possible future direction for stronger guarantees.

**Key point:** For **channels** (Telegram, Slack, WhatsApp, etc.) we do **not** control the client app — those are third-party. We cannot add our own encryption or decryption there; the channel provider’s app handles (or doesn’t) encryption. So for channel traffic we rely on whatever the channel uses; we can’t “encrypt by ourselves” inside their app.

For the **Companion app**, we **do** control both the app and the Core. **(1) HTTPS with a real certificate:** When the user points the Companion at an **https://** URL (e.g. from a tunnel or Let’s Encrypt), we **don’t need to do anything special** — standard TLS and the system trust store handle it. We must **not break** the **http://** setting: localhost and LAN users can keep using `http://` as today. **(2) Application-layer encryption:** We **should implement** encryption and decryption in the Companion app and in Core — our app encrypts message payloads before sending, our Core decrypts; Core encrypts responses, our app decrypts. That way we secure the content ourselves regardless of http vs https.

**Related docs:**
- [SocialNetworkDesign.md](SocialNetworkDesign.md) — summary of social network and security; future multi-HomeClaw
- [RemoteAccess.md](RemoteAccess.md) — Core auth, API key, Tailscale
- [CompanionPushNotifications.md](CompanionPushNotifications.md) — push tokens, multi-user
- [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md) — user-to-user message path

---

## 1. Companion ↔ Core: transport encryption (TLS/HTTPS)

**Goal:** No one on the network (Wi‑Fi, ISP, tunnel provider) can read or alter traffic between the Companion app and Core.

**Mechanism:** Use **TLS (HTTPS)** for all Companion–Core communication. The Companion’s **Core URL** should point to an **https://** endpoint whenever Core is not strictly on the same machine and same network you control.

| Scenario | Recommendation |
|----------|-----------------|
| **Core on same device / localhost** | `http://127.0.0.1:9000` is acceptable; traffic does not leave the device. |
| **Core on LAN (same Wi‑Fi)** | Prefer **HTTPS** (e.g. reverse proxy with a certificate, or Tailscale with HTTPS). If you use `http://` on LAN, assume the same network could sniff traffic. |
| **Core reachable via internet** (Cloudflare Tunnel, Ngrok, Tailscale Funnel, etc.) | **Always use HTTPS.** Set Core URL to the **https://** URL provided by the tunnel. The tunnel terminates TLS; traffic from Companion to the tunnel is encrypted. |

**What TLS gives you:**
- **Confidentiality:** Request/response bodies (messages, tokens, config) are encrypted in transit.
- **Integrity:** Tampering is detectable (TLS MAC).
- **Server authentication:** With a proper certificate, the app can verify it is talking to your Core (or your tunnel), not an impostor.

**What TLS does not do:**
- It does **not** hide content from the **Core server** (or the machine/tunnel that terminates TLS). Core and anyone with access to that server can read plaintext. So: **Companion–Core encryption protects against network eavesdroppers; it does not protect against a compromised or malicious Core.**

**Our behaviour:** **Do not break http.** The Companion and Core must continue to support **http://** (e.g. `http://127.0.0.1:9000`, LAN). Users who use a tunnel or reverse proxy with a real cert can set **https://** and it should work with no extra work on our side (standard TLS). We can recommend HTTPS for remote URLs or show a warning for `http://` to a non-localhost host, but we must not remove or disable the http setting.

**Channels (Telegram, Slack, WhatsApp, etc.):** We **cannot** add our own encryption or decryption for channel traffic. The user’s Telegram/Slack/WhatsApp app is made by the channel provider; we don’t control it. We only receive and send via the channel’s API; security is whatever the channel provider gives. **User-to-user messages** are delivered **only via the Companion** (inbox, push, WebSocket), not to the recipient’s channel — otherwise the recipient wouldn’t know how to reply and Core wouldn’t know how to route the reply (channels are for User ↔ HomeClaw). For Companion–Core we control both ends, so we can secure the link ourselves (HTTPS and/or application-layer encryption).

### 1.1 HTTPS and certificates

**HTTPS uses a certificate** on the server (or on the tunnel that terminates TLS). You have a few options so you don’t have to manage certificates yourself on the Core host:

| Option | Who provides the certificate | What you do |
|--------|------------------------------|-------------|
| **Tunnel with built-in HTTPS** | **Cloudflare Tunnel**, **Ngrok**, **Pinggy**, **Tailscale Funnel** | You run a tunnel client; the service gives you an **https://** URL and handles the certificate. Companion uses that URL; no cert on your machine. |
| **Tailscale (LAN / tailnet)** | Tailscale | Use `https://your-machine.your-tailnet.ts.net` with **Tailscale Serve** or **Funnel**; Tailscale can provide TLS. Or use Tailscale’s IP with `http://` if you accept LAN-only, unencrypted traffic. |
| **Reverse proxy (e.g. Caddy, nginx)** | **Let’s Encrypt** (free) | You run a proxy in front of Core; the proxy gets a cert (e.g. Caddy auto-obtains Let’s Encrypt) and terminates HTTPS. Core stays on `http://127.0.0.1:9000`. |

**We do not recommend self-signed certificates.** They cause browser/app warnings and require users to trust the cert manually. Prefer a tunnel (above) or Let’s Encrypt so the certificate is valid and the Companion can connect without warnings.

**HTTPS with a real cert — we don’t need to do anything.** When the user sets Core URL to an **https://** address (e.g. from Cloudflare Tunnel, Ngrok, Pinggy, Tailscale Funnel, or a reverse proxy with Let’s Encrypt), the OS and HTTP client use standard TLS and the system trust store. No custom certificate handling or pinning in our app. It just works. **We do not break http:** users who use **http://** (localhost, LAN) must continue to be able to connect; we keep the http setting supported.

### 1.2 Application-layer encryption (Companion–Core): we should implement this

We **should implement** application-layer encryption between the Companion app and Core. Both ends are under our control, so we encrypt and decrypt the message payloads ourselves:

- **Companion** encrypts the request body (e.g. message, user_id, metadata) before sending. Only Core has the key or the other half of the key agreement to decrypt.
- **Core** decrypts the payload, processes it, then encrypts the response body and sends it back.
- **Companion** decrypts the response. On the wire an eavesdropper sees only ciphertext (sensitive data in the body is protected).

Then the message content is secured by our code whether the user connects with **http://** or **https://**. Options for the key:

- **Shared secret:** Derived at login (e.g. from password + nonce) or stored per device after first auth; used with a symmetric cipher (e.g. AES-GCM). Simple; key must be kept secure on both sides.
- **Key agreement:** Companion and Core exchange or derive a session key (e.g. ECDH) so that only the two of them can encrypt/decrypt. No shared secret in config; better for forward secrecy if we rotate.

**Summary:** HTTPS with a real cert needs no extra work from us and we don’t break http. Application-layer encryption is what we implement in Companion and Core to secure the content.

---

## 2. Companion ↔ Core: authentication and secrets

**Goal:** Only the right user (and their devices) can access their data and send messages as that user.

**Current / recommended:**
- **API key (Core):** When Core has `auth_enabled: true`, the Companion sends the **auth_api_key** (e.g. in `X-API-Key` or `Authorization: Bearer`) with every request. See [RemoteAccess.md](RemoteAccess.md). This protects against unauthorized clients; anyone with the key can call Core.
- **Login (Companion):** User logs in with **username + password**; Core returns a session (or user_id) so that subsequent requests are scoped to that user. Push tokens are stored per **user_id**. So: **multi-user is supported;** each user only gets their own data and push. One login per app instance; one user can have multiple devices (each registers its token under the same user_id). See [CompanionPushNotifications.md](CompanionPushNotifications.md).

**Privacy on the server:**
- **Core and storage:** Today, messages and user data are stored in plaintext on the machine running Core (and in any DB or files Core uses). Admins and anyone with filesystem/DB access can read them. To reduce exposure: restrict filesystem/DB access, use disk encryption at rest, and avoid logging message bodies in production.
- **Push:** Push payloads (title/body) may contain message previews. They are encrypted in transit (APNs/FCM use TLS) but can be visible to the device and to the push provider (Apple/Google). Avoid putting highly sensitive content in the notification body if possible.

---

## 3. Companion ↔ Companion (user-to-user): who can read the message?

When User 1 sends a message to User 2 via the Companion (Core forwards it; see [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md)):

**Today (forward plaintext):**
- Message goes: **Companion (User 1)** → **Core** → **Companion (User 2)**.
- If the whole path uses **HTTPS**, the message is encrypted **in transit**. But **Core sees and stores plaintext**. So: safe from network sniffing; **not** safe from a compromised Core or server admin.

**Stronger guarantee (future): end-to-end encryption (E2E)**

If we want **Core to be unable to read** user-to-user messages:

- **User 1** encrypts the message with **User 2’s public key** (and optionally signs with User 1’s private key).
- **Core** only sees and forwards **ciphertext** (and metadata: from_user_id, to_user_id, timestamp). Core does not have User 2’s private key, so it cannot decrypt.
- **User 2** decrypts with their **private key** (kept only on their device(s) or in a secure enclave).

**Requirements for E2E:**
- **Key exchange:** Each user has a key pair (e.g. generated in the Companion or on first login). Public keys must be available to senders (e.g. stored on Core per user_id, or exchanged when two users become “user” friends). Private keys must never be sent to Core.
- **Key storage:** Private keys on device (e.g. in app secure storage / Keychain / Keystore). Multi-device: either per-device keys (each device has its own key pair; senders encrypt for each of the recipient’s device public keys) or a single key per user with secure sync (harder).
- **Protocol:** Use a standard (e.g. Signal Protocol, or X3DH + Double Ratchet, or a simpler sign‑encrypt with ECDH) so that keys are used correctly and we avoid replay/forgery.

**Scope:** E2E can apply to **user-to-user** text (and optionally file content or file keys). **AI chats** (user ↔ HomeClaw/friend) typically cannot be E2E with the same strength because Core must read the message to run the LLM; here, transport encryption + trust in Core is the model.

---

## 4. Summary and recommendations

| Path | Today | Recommendation | Future option |
|------|--------|-----------------|----------------|
| **Channels** (Telegram, Slack, etc.) | Provider’s app and API | We **cannot** add our own encrypt/decrypt; the channel app is not ours. Rely on the provider’s security (and HTTPS to Core if we expose it). | — |
| **Companion → Core** | Depends on Core URL (http vs https) | **HTTPS with real cert:** we do nothing special (standard TLS). **Don’t break http** (localhost, LAN). **Application-layer encryption:** we **implement** encrypt/decrypt in Companion and Core. | — |
| **Core → Companion** | Same as above | Same: http remains supported; HTTPS works as-is; we implement app-layer encrypt/decrypt. | — |
| **User-to-user (via Core)** | Plaintext on Core; TLS in transit | HTTPS or app-layer encryption for transit; Core can read. | **E2E:** Encrypt on sender device with recipient’s public key; Core only forwards ciphertext; recipient decrypts. |

**Implementation:**
- **HTTPS with a real cert:** No extra work; standard TLS. **Do not break http** — keep supporting `http://` for localhost and LAN.
- **Application-layer encryption:** **Implement** in Companion app and Core: encrypt request/response bodies with our own keys/agreement; decrypt on the other side. We secure the message content regardless of http vs https.
- **Channels:** We do not add our own encryption; the channel app is not under our control.
- Remind users: one login per app; one user can have multiple devices; push is per user and multi-device; keep API keys and passwords secure.

**Later (design / implementation):**
- If we add **user-to-user messaging**, consider an **E2E option** so that Core only stores and forwards ciphertext for those messages. Design would go in [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md) (e.g. a section “Optional: end-to-end encryption”) and a separate key-exchange and protocol doc.

This keeps security and privacy explicit and gives a path to stronger guarantees for user-to-user messages without changing the current Companion–Core trust model for AI chats.
