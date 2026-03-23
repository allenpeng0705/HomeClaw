# Federated Companion user-to-user messaging (cross-instance)

**Operator & user guide (single doc):** [docs/federated-companion-messaging.md](../docs/federated-companion-messaging.md) — configuration, how to use the Companion, API cheat sheet, crypto summary, limitations, and future work.

**Status:** P1–P5 (partial): Core + SQLite as before; **Companion (Flutter)** exposes `federation_enabled` / **`federation_e2e_enabled`** / **`federation_e2e_require_encrypted`** on login and **`GET /api/me/friends`**; **Add friend** / **Friend requests** **Remote** tabs; friend list **remote** badge; chat **Remote · instance** chip; federated lines prefixed **◇**. **P5:** optional **hc-e2e-v1** (X25519 ephemeral + HKDF-SHA256 + AES-256-GCM): Core validates/stores ciphertext; Companion registers public key (`PUT /api/me/federation-e2e-key`), encrypts/decrypts in-app; no Core decrypt on hot path.  
**Goal:** Let Companion users on **different HomeClaw instances** discover (within defined trust boundaries), become friends, and chat **peer-to-peer** through their respective Cores — **without breaking** single-instance behavior or existing APIs.

**Related:** [SocialNetworkDesign.md](SocialNetworkDesign.md) Part 2, [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md), [MultiInstanceIdentityRosterAndPairing.md](MultiInstanceIdentityRosterAndPairing.md), existing **`POST /api/user-message`** / **`GET /api/user-inbox`**.

---

## 1. Problem statement

Today, user-to-user messaging is **same-instance only**: sender must have **`type: user`** friend with **`user_id`** that exists in **local** `user.yml`; Core forwards to local inbox/push.

We want: **User A on Instance A** ↔ **User B on Instance B** in the Companion, reusing the same **mental model** (Companion → Core → … → Core → Companion), **no LLM** on the social path, but **no regression** for users who never enable federation.

---

## 2. Non-breaking principles (must hold)

| Principle | How |
|-----------|-----|
| **Default off** | No `remote_id` / `peer_instance_id` on friends → behavior identical to today. |
| **Local-first resolution** | If friend is local `type: user` with only `user_id`, use **existing** `user_message` path unchanged. |
| **Explicit opt-in per instance** | e.g. `federation_enabled: true` (or under `companion:` / new top-level key) in `core.yml`; when false, Core **rejects** cross-instance relay and **does not** expose federated discovery APIs. |
| **Same user APIs where possible** | Companion keeps using **`POST /api/user-message`** and **`GET /api/user-inbox`**; Core **internally** branches: local deliver vs forward to peer Core. Optional: new optional JSON fields on the same request (see §6). |
| **Channels unchanged** | Social network remains Companion ↔ Core only; IM channels do not carry federated P2P. |
| **Peer infra reuse** | Routing uses **`peers.yml`** (or equivalent roster) already used for **`peer_call`** — same **`base_url`**, auth, and trust model; **separate** optional **`federation_api_key`** or scoped use of existing peer credentials (see §8). |

---

## 3. Federated identity

### 3.1 Canonical handle (logical)

- **`local_user_id`**: as today (`user.yml` `id`).
- **`instance_id`**: from **`config/instance_identity.yml`** (already planned for multi-instance).
- **Federated id (FID)**: `local_user_id@instance_id` (string form; `instance_id` must not contain `@`).

Internal storage can use a structured object instead of parsing strings.

### 3.2 Friend model extension (`user.yml`)

Extend **`type: user`** friend entries **optionally**:

```yaml
friends:
  - name: BobOnGarage
    type: user
    user_id: Bob                    # recipient's local id on THEIR instance
    peer_instance_id: garage-core  # must match a peers.yml instance_id OR new federation roster
    # optional explicit FID for future tooling:
    # remote_id: Bob@garage-core
```

**Rules:**

- If **`peer_instance_id` is absent** → friend is **local** (current validation: `user_id` must exist in local `users`).
- If **`peer_instance_id` is present** → Core does **not** require `user_id` to exist locally; validation checks roster + relationship state (accepted) instead.

**Backward compatibility:** Existing entries without `peer_instance_id` unchanged.

### 3.3 Relationship state

Align with [SocialNetworkDesign.md](SocialNetworkDesign.md) §2.2:

- **`pending` | `accepted` | `blocked`** (minimal).
- **Cross-instance:** no message delivery until **`accepted`** on **both** sides (or asymmetric rule documented — default **mutual accept**).
- **Same-instance:** can keep current “mutual friend in yml” or adopt same state machine in one codebase path.

Store state in:

- **Option A (phase 1):** SQLite/table `federated_friendships` (sender FID, recipient FID, state, timestamps).
- **Option B:** Extend user.yml via automation — **not** recommended for high churn.

---

## 4. Architecture: message path

```
Companion(A) ──► Core(A) ──► [local?] ──► inbox(B local)
                     │
                     └── remote? ──► HTTPS ──► Core(B) ──► inbox(B) + push(B)
```

1. **Companion(A)** sends user message (existing endpoint + optional metadata).
2. **Core(A)** resolves friend: local `user_id` → **existing forward** to local inbox.
3. If friend has **`peer_instance_id`**, Core(A):
   - Verifies **`federation_enabled`**, roster entry, relationship **accepted**, rate limits.
   - **POST** to Core(B) **federation ingress** (dedicated path, not `/inbound` LLM) with signed/authenticated payload.
4. **Core(B)** verifies source instance, maps to local **`user_id`**, writes **same inbox schema** as local user-message, triggers **push** / WebSocket as today.

**Important:** Use a **dedicated Core–Core API** (e.g. **`POST /api/federation/user-message`**) so federated traffic is **not** confused with **`/inbound`** (LLM) and can have **different** auth and body validation.

---

## 5. Discovery (“find users on other instances”)

There is **no global phone book** in phase 1. Options (can combine):

| Mechanism | UX | Trust |
|-----------|-----|--------|
| **Invite link / deep link** | `homeclaw://federate?instance=…&user=…&token=…` or HTTPS page | Token proves invite; B accepts in Companion |
| **QR** at family gathering | Same payload in QR | Out-of-band |
| **Operator adds friend row** | Admin edits `user.yml` + `peers.yml` | High trust, small deployments |
| **Directory service** | Later hardening (item 8 in multi-instance roadmap) | Org-controlled registry |

**Companion UX (later phase):** “Add remote friend” → paste link or scan QR → Core(A) resolves token with Core(B) or validates static invite → creates **pending** relationship → notification on B → accept.

---

## 6. API sketch

### 6.1 Companion → own Core (extend existing)

**`POST /api/user-message`** (existing auth):

- Keep **`from_user_id`**, **`to_user_id`**, **`text`**, attachments.
- When recipient is a **local** user friend: **no change**.
- When recipient is **remote** friend: **`to_user_id`** is the **remote user’s local id** on their instance; Core(A) looks up friend row with **`peer_instance_id`**, resolves **`to_fid`**, checks state **accepted**, then forwards.

Optional explicit fields (additive, ignored by old clients):

```json
{
  "to_peer_instance_id": "garage-core",
  "to_user_id": "Bob"
}
```

Server may derive `to_peer_instance_id` from friend list by `to_user_id` + friend name — product choice.

### 6.2 Core(A) → Core(B) (new)

**`POST /api/federation/user-message`** on **B**:

- Auth: **instance-to-instance** (see §8).
- Body (example):

```json
{
  "from_fid": "Alice@home-core",
  "to_local_user_id": "Bob",
  "text": "...",
  "client_message_id": "uuid",
  "attachments": []
}
```

- **B** validates: A is allowed to send (relationship accepted, optional allowlist).
- **B** delivers via **same** `user_inbox` + push code paths as local **`user-message`**.

**Friend request / accept** (phase 3 — implemented):

- Core–Core: `POST /api/federation/friend-request` (inbound), `POST /api/federation/friend-relationship-reciprocal` (reciprocal accept on requester’s Core).
- Companion (Bearer): `POST /api/federated-friend-request` (outbound to peer), `GET /api/federated-friend-requests`, `POST /api/federated-friend-request/accept`, `POST /api/federated-friend-request/reject`.

---

## 7. Phased implementation plan

| Phase | Scope | Breaks existing? |
|-------|--------|------------------|
| **P0** | This document + config flags stub + README links | No |
| **P1** | `federation_enabled` in `core.yml`; parse optional `peer_instance_id` on friends (**ignore** if federation off); validation: if set and federation off → treat as error at **load** or **first use** (document) | No if federation default false and no new fields in yml |
| **P2** | `POST /api/federation/user-message` on Core; auth plugin using **`peers.yml`** + env key; **only** delivers to local inbox when relationship row exists | No impact if endpoint unused |
| **P3** | Relationship store + **friend-request/accept** flow (same-instance optional unify); Core(A)→Core(B) request relay | **Partially done:** SQLite + federation + Companion APIs; same-instance unify still optional / unchanged |
| **P4** | Companion UI: remote friend badge, add-by-invite, inbox thread source “remote” | **Partial:** Flutter badges + remote add/request tabs gated on `federation_enabled`; invite links / QR not implemented |
| **P5** | Optional E2E (**hc-e2e-v1**): `federation_e2e_enabled` / `federation_e2e_require_encrypted`; keys in SQLite; federated `user-message` + inbox carry optional `e2e` envelope | Optional (off by default) |

**Order recommendation:** P1 schema → P2 secure ingress → P3 state machine → P4 UX → P5 crypto.

---

## 8. Security (summary)

- **TLS** for all Core–Core calls; never downgrade federated traffic to plaintext over WAN.
- **Authentication:** Reuse **`peers.yml`** **`api_key_env`** or introduce **`federation_inbound_api_key_env`** on **receiving** Core so compromise of **`peer_call`** key can be separated from social relay if desired.
- **Authorization:** Per-pair **accepted** relationship; optional **instance allowlist** (`federation_trusted_instances: [garage-core]`).
- **Abuse:** Rate limits per source instance + per FID; same patterns as peer invite consume.
- **E2E (P5):** X25519 public keys registered per user on each Core; cross-instance messages may carry **hc-e2e-v1** envelope (Companion encrypt/decrypt).

---

## 9. What we are **not** doing in this design

- Replacing **`peer_call`** or **`/inbound`** with federation.
- Automatic LAN user discovery (optional future).
- Changing channel behavior.
- Requiring federated ids for **local-only** installs.

---

## 10. Checklist before coding P1

- [ ] Agree **`federation_enabled`** name and default **`false`**.
- [ ] Agree friend schema keys: **`peer_instance_id`** vs **`remote_instance_id`**.
- [ ] Decide: single **`peers.yml`** roster for both **`peer_call`** and federation, or split file.
- [ ] Companion contract: version gate so old apps ignore unknown friend fields safely.

---

## 11. Changelog

| Date | Change |
|------|--------|
| 2025-03-22 | Initial design: federated Companion P2P, non-breaking rules, phases, APIs, security. |
| 2026-03-22 | Link to consolidated guide `docs/federated-companion-messaging.md` (how-to, APIs, E2E, future work). |
