# Federated Companion user messaging (guide)

This document is the **single operator and user guide** for cross-instance user-to-user chat in the HomeClaw Companion, including optional end-to-end encryption (**P5 / hc-e2e-v1**). For original architecture notes and phase history, see [FederatedCompanionUserMessaging.md](../docs_design/FederatedCompanionUserMessaging.md).

---

## 1. What you get

| Capability | When it works |
|------------|----------------|
| **Same-instance chat** | Unchanged: `type: user` friend with local `user_id` in `user.yml`. |
| **Cross-instance chat** | Both Cores set **`federation_enabled: true`**, **`peers.yml`** links them, each user has a **`user`** friend with **`peer_instance_id`** + remote **`user_id`**, and (by default) a **mutual accepted** federated friendship in SQLite. |
| **Optional E2E** | Both Cores set **`federation_e2e_enabled: true`**. Companion generates an X25519 key pair, registers the **public** key on its Core, and can encrypt **text-only** federated messages so relaying Cores see ciphertext only. **`federation_e2e_require_encrypted: true`** forces E2E for federated user messages (no plaintext, no attachments on that path). |

**Visual cues in the Companion:** remote friends show a cloud/remote badge; the chat app bar can show **Remote · &lt;instance&gt;**; messages that arrived via federation may be prefixed with **◇** in the thread.

---

## 2. Prerequisites (both instances)

1. **`config/instance_identity.yml`** — each Core has a distinct **`instance_id`** (used in federated IDs `user_id@instance_id`).
2. **`config/peers.yml`** — each Core lists the other with **`instance_id`**, **`base_url`** (HTTPS recommended), and auth (e.g. **`api_key_env`** pointing to an env var). See `config/peers.yml.example`.
3. **`config/core.yml`** — see §3.
4. **Companion** — same Core URL + API key as today; users log in with username/password.

---

## 3. Core configuration (`config/core.yml`)

Typical federation block (adjust to your policy):

```yaml
# Cross-instance user messaging
federation_enabled: true
# Optional: only allow listed remote instance_id values (empty list = no extra filter beyond friendship rules)
# federation_trusted_instances: []
# Optional: require SQLite federated_friendships row in "accepted" state for delivery
# federation_require_accepted_relationship: true

# Optional E2E (Companion encrypts; Core stores/validates envelope only)
federation_e2e_enabled: true
# Optional: reject federated user messages without hc-e2e-v1 envelope
# federation_e2e_require_encrypted: true
```

**Flags:**

| Key | Effect |
|-----|--------|
| `federation_enabled` | Master switch for federation ingress and Companion→Core remote send path. |
| `federation_trusted_instances` | If non-empty, only those remote `instance_id` values may send inbound federated traffic (when enforced by Core). |
| `federation_require_accepted_relationship` | Stricter delivery: requires accepted relationship in `federated_friendships` store. |
| `federation_e2e_enabled` | Allows **hc-e2e-v1** on federated user messages; exposes key registration and peer key lookup APIs. |
| `federation_e2e_require_encrypted` | Federated user messages **must** include a valid E2E envelope (text only for encrypted messages in current version). |

After editing YAML, restart Core so metadata reloads.

---

## 4. Friend configuration (`user.yml`)

**Local user friend** (same machine):

```yaml
friends:
  - name: Alice
    type: user
    user_id: alice
```

**Remote user friend** (other Core):

```yaml
friends:
  - name: Bob (garage)
    type: user
    user_id: Bob
    peer_instance_id: garage-core   # must match peers.yml instance_id on THIS Core
```

Rules:

- Without **`peer_instance_id`**, the friend is treated as **local** (recipient must exist in local `users`).
- With **`peer_instance_id`**, the remote user id is the id **on their** Core, not necessarily a local account.

---

## 5. Companion usage (operators & users)

### 5.1 Login and flags

On login (and when refreshing friends), the app reads:

- `federation_enabled`
- `federation_e2e_enabled`
- `federation_e2e_require_encrypted`

If **`federation_e2e_enabled`** is true, the app **best-effort** registers an X25519 public key on the user’s Core (`PUT /api/me/federation-e2e-key`) when the user has no key yet. The **private** key stays in **secure storage** on the device.

### 5.2 Adding a remote friend

1. Ensure federation is enabled on **both** Cores and peers are configured.
2. In the Companion: **Add friend** → **Remote** tab (when federation is on).
3. Enter the other user’s **local user id** on their instance and the **peer instance id** (from `peers.yml`).
4. Complete the **federated friend request** flow on both sides (**Friend requests** → **Remote** tab): accept on the recipient’s Core/user as prompted.

Until the relationship is **accepted** (per your Core policy), cross-instance messages may be rejected.

### 5.3 Chatting

- Open the user friend from the friend list; remote chats show the remote instance indicator when configured.
- **Plaintext federated messages** work like local user chat when E2E is off or not required.
- **Encrypted federated messages (hc-e2e-v1):**
  - **Text only** in the current implementation (images, video, voice, and files are not encrypted on the federated path; **`federation_e2e_require_encrypted`** disallows sending them from the Companion for remote chats).
  - The sender’s app fetches the recipient’s public key via **`GET /api/me/federation-peer-e2e-public-key`** (Core proxies to the peer Core). If the recipient has not registered a key, encryption is skipped when optional; if encryption is **required**, sending fails with a clear error.
- **Receiving:** messages with an **`e2e`** object in the inbox are decrypted on-device when the app still has the same private key. If the key is lost (e.g. app reinstall), ciphertext may show as **[Encrypted message]**.

### 5.4 Push and WebSocket

For encrypted messages, push and WebSocket payloads avoid exposing body text; the app refreshes the **inbox thread** when it receives a **user_message** push (including when **`e2e_encrypted`** is set). Open the chat to read decrypted content.

---

## 6. Cryptography reference (hc-e2e-v1)

| Item | Value |
|------|--------|
| Algorithm id | `hc-e2e-v1` |
| Key agreement | X25519 (ephemeral sender key × recipient long-term public key) |
| KDF | HKDF-SHA256, salt `homeclaw-fed-e2e-v1`, empty info |
| AEAD | AES-256-GCM, 12-byte random nonce |
| Stored envelope | `algo`, `ephemeral_public_key_b64`, `nonce_b64`, `ciphertext_b64` (ciphertext includes 16-byte GCM tag, same as Python `cryptography` AESGCM) |

Core **validates envelope shape and sizes** only; it does **not** decrypt message content in the hot path. Reference tests: `tests/test_federation_e2e.py`.

---

## 7. API summary (quick reference)

**Companion (Bearer session)**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/login` | Returns federation + E2E flags among other fields. |
| GET | `/api/me`, `/api/me/friends` | Refreshes federation/E2E flags. |
| POST | `/api/user-message` | User-to-user send; Core forwards to peer if friend has `peer_instance_id`. Optional JSON **`e2e`** for hc-e2e-v1. |
| GET | `/api/user-inbox`, `/api/user-inbox/thread` | Inbox / thread; entries may include **`e2e`**. |
| POST | `/api/federated-friend-request` | Send cross-instance friend request. |
| GET | `/api/federated-friend-requests` | List pending remote requests. |
| POST | `/api/federated-friend-request/accept`, `/reject` | Accept or reject. |
| PUT | `/api/me/federation-e2e-key` | Register X25519 public key (32 bytes, standard base64). |
| GET | `/api/me/federation-e2e-key-status` | Whether current user has a registered key. |
| GET | `/api/me/federation-peer-e2e-public-key` | Query params: `peer_instance_id`, `remote_user_id` — proxy fetch of peer’s public key. |

**Core ↔ Core (API key / inbound auth)**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/federation/user-message` | Deliver federated message to local user. |
| POST | `/api/federation/friend-request` | Inbound friend request. |
| POST | `/api/federation/friend-relationship-reciprocal` | Reciprocal accept helper. |
| GET | `/api/federation/e2e-public-key` | Peer lookup: `local_user_id` — returns registered public key for E2E. |

---

## 8. Operational notes and limitations

- **Companion robustness:** The app treats malformed JSON, bad base64, and non-string envelope fields defensively (no crash): decryption falls back to placeholder text; optional E2E is skipped if the peer key is invalid unless the Core requires encryption (then the user sees an error). UTF-8 after decrypt uses a malformed-tolerant decode so a corrupt payload does not tear down the UI thread.
- **TLS:** Use HTTPS between Cores in production; federation credentials must stay out of logs and git.
- **Key backup:** There is no cloud key escrow. Reinstalling the Companion generates a new device key; users should register again. Old ciphertext remains undecryptable without the old private key.
- **Attachment policy:** E2E + media on the federated path is a **future** improvement; today Core rejects **`e2e`** combined with images/audio/video/file_links.
- **Trust model:** Federation builds on configured peers and friend/relationship state; it is **not** an open public network.

---

## 9. Future work (suggested)

| Area | Idea |
|------|------|
| **Discovery** | Invite links, deep links (`homeclaw://…`), QR for out-of-band exchange (design §5). |
| **Media E2E** | Encrypt attachments or use hybrid encryption with per-message keys. |
| **Key rotation** | Versioned keys, re-encrypt not supported — document “forward secrecy” limits. |
| **Same-instance E2E** | Optional encryption for local user messages (different trust story). |
| **Admin UX** | Portal or CLI to inspect federated relationships and rate limits. |
| **Hardening** | Separate `federation_inbound_api_key` from `peer_call` keys; stricter rate limits per FID. |
| **Tests** | Integration tests: two Cores, full friend accept + message + optional E2E round-trip. |

---

## 10. Changelog (this guide)

| Date | Change |
|------|--------|
| 2026-03-22 | Initial consolidated guide: config, Companion usage, APIs, crypto, limitations, future work. |
