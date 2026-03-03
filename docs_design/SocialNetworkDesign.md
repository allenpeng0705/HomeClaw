# HomeClaw Social Network: Summary and Future Extension

This document **summarizes** the social network model for **one HomeClaw** (including security) and states how the design **extends to multiple HomeClaws** so that instances can connect and their users can communicate. Summarize first, then implement.

**Our design must consider the future upgrade: multi-HomeClaw for a bigger social network.** When we implement the single-instance social network today, we do not hard-code "one instance only." Identity, friend model, delivery, and encryption are chosen so that later we can connect multiple HomeClaws and let users on different instances be friends and message each other (Companion(A) → Core(A) → Core(B) → Companion(B)). The "Design for future upgrade" section and Part 2 make this explicit.

**The social network is for Companion app and Core only.** It has **nothing to do with channels**. Messages in the social network always go **from Companion app to Companion app** (via Core). Channels (Telegram, Slack, WhatsApp, etc.) are a separate path: User ↔ HomeClaw (AI) on that channel. User-to-user messaging and the “social network” are exclusively Companion ↔ Core ↔ Companion.

**Related docs:**
- [MultiUserSupport.md](MultiUserSupport.md) — users, friends, channels
- [UserFriendsModelFullDesign.md](UserFriendsModelFullDesign.md) — friends list, (user_id, friend_id)
- [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md) — user-to-user in one instance
- [CompanionEncryptionAndSecurity.md](CompanionEncryptionAndSecurity.md) — encryption Companion–Core, app-layer, E2E
- [CompanionPushNotifications.md](CompanionPushNotifications.md) — push, multi-user, multi-device

---

## Design for future upgrade (multi-HomeClaw = bigger social network)

When implementing the social network for **one** HomeClaw, we follow these rules so that the **future upgrade to multi-HomeClaw** (multiple instances connected, users across instances messaging) does not require a redesign:

| Rule | Why it matters for multi-HomeClaw |
|------|-----------------------------------|
| **Identity:** Use `user_id` as the primary key; do not assume "one instance" in the data model. | Later we add optional `instance_id` or `remote_id` to friend type `user` so a friend can be on another instance (e.g. `alice@instance-B`). |
| **Message path:** Always "Companion → Core → recipient." Core forwards; no LLM for user-to-user. | Same path works when recipient is on another instance: Core(A) forwards to Core(B), which delivers to Companion(B). |
| **Delivery:** Inbox + push keyed by recipient `user_id`; Core delivers to that user. | For cross-instance, Core(A) sends to Core(B); Core(B) delivers to its user (inbox + push). Same delivery model. |
| **Encryption:** Application-layer encrypt/decrypt between Companion and Core; optional E2E for user-to-user. | Instance–Instance can use TLS + app-layer; cross-instance user-to-user can use E2E so neither Core reads. |
| **Channels:** Social network is Companion + Core only; channels are separate. | Multi-HomeClaw social network stays Companion ↔ Core ↔ Companion; channels remain per instance (User ↔ HomeClaw). |
| **Friend relationship state:** Consider a state (e.g. pending vs accepted) for user-type friends. | For multi-HomeClaw, **friend request is required**; only after **accepted** can they communicate. One HomeClaw can start with "accepted" (both in user.yml); multi-HomeClaw reuses the same state for request/accept. |
| **Security between instances:** Design so Cores can authenticate and encrypt traffic. | **Security is more important** when multiple HomeClaws connect. Communications **between** HomeClaws (Core–Core and user-to-user across instances) must be secured; see Part 2. |

Part 2 below spells out multi-HomeClaw in more detail: **friend request and accept**, and **how to secure communications between HomeClaws**. When we implement Part 1, we respect these rules so the bigger social network is a natural extension.

---

## Part 1: Social network for one HomeClaw (summary)

### 1.1 Scope: Companion and Core only (not channels)

The **social network** (user-to-user messaging, friends, etc.) involves **only the Companion app and Core**. Channels (Telegram, Slack, WhatsApp, WebChat, etc.) are **not** part of the social network. Messages in the social network are **always sent from Companion to Companion** (via Core). Channels are used for User ↔ HomeClaw (AI) on that platform; they do not carry user-to-user social-network messages.

### 1.2 Actors and relationships (within the social network)

| Actor | Description |
|-------|-------------|
| **Users** | Real people in `config/user.yml`. Each has `id`, `name`, optional login (username/password), and a **friends** list. (Channel identities im/email/phone are for the separate channel path, not for the social network.) |
| **Friends (AI)** | Core roles: HomeClaw (system), Sabrina, Gary, etc. User chats with a friend via **Companion** → Core runs the LLM → reply to Companion. |
| **Friends (user)** | Another **user** in the same HomeClaw (`type: user`, `user_id`). User 1 sends from **Companion** to User 2; Core **forwards** (no LLM); User 2 receives in **Companion**. See [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md). The **Companion** receives the friend list (login, GET /api/me/friends) with `type` and `user_id` per friend, so it knows who is an AI friend vs a real-person friend and can show the right UI (e.g. push-to-talk only for user friends). |

**Channels** (Telegram, Slack, etc.) are a separate system: they connect users to **HomeClaw** (AI), not to each other in the social network. The social network is Companion ↔ Core ↔ Companion only.

**Data scope:** Chat, memory, sandbox, and push for the social network are keyed by **(user_id, friend_id)**. One login per Companion at a time; one user can have multiple devices (push tokens per user_id).

### 1.3 Communication paths: social network (Companion ↔ Core ↔ Companion)

| Path | How it works | Security (design) |
|------|--------------|-------------------|
| **User ↔ AI friend** | Companion → Core (user_id, friend_id, text); Core runs LLM; reply → Companion. | **Application-layer encryption** between Companion and Core (we implement). HTTPS with real cert needs no extra work; **do not break http** (localhost, LAN). [CompanionEncryptionAndSecurity.md](CompanionEncryptionAndSecurity.md) |
| **User ↔ User** | User 1 sends from **Companion** to “friend” User 2 (type: user). Core forwards; no LLM. User 2 receives **only in Companion** (inbox, push, WebSocket). Messages always **Companion → Companion** via Core. | Companion–Core: app-layer encryption. Optional E2E for user-to-user. |
| **Push** | Core delivers to user (reminder, user-to-user message, etc.) via push to Companion devices. Tokens stored per **user_id**; one user can have multiple devices. | Tokens sent over HTTPS; payload may contain preview. [CompanionPushNotifications.md](CompanionPushNotifications.md) |

**Channels** (Telegram, Slack, WhatsApp, etc.) are **not** part of the social network. They are a separate path: User ↔ HomeClaw (AI) on that channel. Social-network messages are only Companion → Core → Companion.

### 1.4 Security summary (one HomeClaw, social network only)

- **Companion ↔ Core:** We implement **application-layer encryption** (encrypt/decrypt in our app and Core). **HTTPS** with a real cert works as-is (no extra work); we **do not break http** (localhost, LAN). Channels: we don’t control their app; no custom encryption there.
- **User-to-user:** Forward today; optional **E2E** later so Core only stores/forwards ciphertext.
- **Identity and auth:** Login (username/password) per user; API key for Core when enabled. Push and data scoped by user_id.

---

## Part 2: Future extension — multi-HomeClaw (design considerations)

The design should allow **multiple HomeClaw instances** to **connect and communicate**, and **users on different instances** to communicate with each other. We do not implement this yet; we summarize the extension so that **current single-instance design does not block it**.

### 2.1 What “multi-HomeClaw” means

- **Instance A** and **Instance B** are two separate HomeClaw Cores (different machines or networks).
- **Users** can belong to one instance (as today) or be represented across instances (e.g. “User on A” can have a friend “User on B”).
- **Communication:**  
  - **Instance ↔ Instance:** Cores (or gateways) exchange messages, presence, or sync.  
  - **User on A ↔ User on B:** Message goes Companion(A) → Core(A) → Core(B) → Companion(B) (or similar). Core(A) and Core(B) must have a way to route and deliver.

### 2.2 Multi-HomeClaw: friend request and accept

**Basic idea:** For multi-HomeClaw, **a friend request is required**. User A sends a friend request to User B (who may be on another instance). Only **after User B accepts** can they communicate (send messages and files). Until then, no user-to-user messages are delivered.

- **One HomeClaw today:** We can implement a simple form of this (e.g. mutual add: both must list each other as user-type friends before delivery), or a full request/accept flow (User A sends request → User B sees "pending" → User B accepts → state becomes "accepted" → messages allowed). When we design the **one** HomeClaw social network first, we **consider** a friend-relationship state (e.g. `pending` | `accepted`) so that the same model works for multi-HomeClaw: cross-instance friend requests use the same state, and only "accepted" allows communication.
- **Multi-HomeClaw later:** User A (on Instance A) sends a friend request to User B (on Instance B). Core(A) forwards the request to Core(B); User B sees the request in the Companion and can accept or decline. On accept, both sides record the relationship as accepted; Core(A) and Core(B) can then route user-to-user messages between A and B. Design so that **no messages** are delivered until the relationship is accepted.

### 2.3 Multi-HomeClaw: security — how to secure communications between HomeClaws

**Security is more important** when multiple HomeClaws connect. We must secure **communications between HomeClaws** (Core–Core and user-to-user across instances). Document this now and consider it when designing the one HomeClaw social network first.

| Layer | What to secure | How (design direction) |
|-------|----------------|-------------------------|
| **Core–Core (Instance–Instance)** | Traffic between Core(A) and Core(B): friend requests, message routing, presence. | **Authentication:** Each Core authenticates the other (e.g. shared secret, or mutual TLS with client certs, or token exchange). **Encryption:** All traffic over **TLS** (HTTPS). Optionally **application-layer encryption** (payload encrypted with a key only the two Cores know) so that even on a compromised network, payloads are protected. Do not send plaintext user messages or tokens between Cores without encryption. |
| **User-to-user across instances** | Messages from User A (Instance A) to User B (Instance B). | Prefer **E2E (end-to-end encryption):** User A encrypts with User B's public key; Core(A) and Core(B) only see ciphertext and metadata (from, to, timestamp). Neither Core can read the content. If E2E is not in place, at least **Core–Core TLS + app-layer** so that inter-Core traffic is encrypted; then only the two Cores (and their admins) can read, not the network. |
| **Identity and trust** | How does Core(A) trust that a message really came from Core(B)? How does User B know the request is from a real User A? | **Instance identity:** Each instance has an identity (e.g. instance_id, or a key pair). Core–Core auth verifies "this request is from Instance B." **User identity:** Federated id (e.g. user_id@instance_id); optional public key per user for E2E. When we design one HomeClaw, we avoid hard-coding "one instance" so that later we can attach instance identity and verification. |
| **Friend request payload** | The friend request itself (who is asking, for whom). | Send over **authenticated, encrypted** Core–Core channel. Request payload should be signed or integrity-protected so Core(B) can verify it came from Core(A) and was not tampered with. |

When we implement the **one** HomeClaw social network first, we implement **Companion–Core** application-layer encryption and optional E2E for user-to-user; we do **not** yet implement Core–Core. But we **design** so that: (1) friend relationship can have a state (request/accept) for multi-HomeClaw; (2) identity and message format do not assume a single instance; (3) when we add Core–Core, we add authentication and encryption between Cores and prefer E2E for cross-instance user-to-user.

### 2.4 Design considerations for extension

So that we can add multi-HomeClaw later without breaking the current model, the following should be **considered** (and where easy, reflected in naming and data shape):

| Topic | Consideration |
|-------|----------------|
| **Identity** | Today: `user_id` is local to one instance. For cross-instance: need a **global or federated identity** (e.g. `user_id@instance_id`, or a public key / DID). Friend type `user` could later point to a **remote user** (e.g. `user_id: "alice"`, `instance_id: "homeclaw-B"` or `remote_id: "alice@B"`). |
| **Discovery and trust** | How does Instance A know about Instance B? Options: explicit config (URL + shared secret), directory, or invite links. How does User A add “User on B” as a friend? Either B’s instance exposes a minimal profile (e.g. name, public key) or users exchange a link/token. Design so that **friend type: user** can later carry an optional `instance_id` or `remote_id` without breaking current single-instance. |
| **Encryption between instances** | Instance–Instance traffic should be **authenticated and encrypted** (TLS and/or application-layer). User-to-user across instances: prefer **E2E** (sender encrypts for recipient’s key) so that neither Core reads content; Cores only route ciphertext. Application-layer encryption (Companion–Core) we implement for single-instance is a building block; cross-instance can use the same or a separate key agreement. |
| **Routing and delivery** | Core(A) must know how to reach Core(B) (URL, queue, or relay). Core(B) must accept messages for a user on B and deliver (inbox + push). Same delivery model as in [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md), but recipient may be on another instance. |
| **Channels** | Channels are **not** part of the social network. They stay per instance for User ↔ HomeClaw (AI). Multi-HomeClaw is about **user-to-user (Companion ↔ Core ↔ Companion)** and possibly instance-to-instance; channels are separate. |

### 2.5 Current design choices that help extension

- **Friend type: user** with `user_id` (and future `instance_id` or `remote_id`) separates “same-instance user” from “remote user” without changing the high-level flow: Core forwards, no LLM.
- **Application-layer encryption** Companion–Core gives us a pattern for “encrypt payload, only our side decrypts”; the same idea can apply to Core–Core or to E2E user-to-user across instances.
- **Push and delivery** are already per **user_id**; adding “user on another instance” is a matter of resolving that identity to the right Core and then using the same inbox/push model.
- **No hard-coded single-instance assumption in identity:** Keep `user_id` as the primary key; later add an optional scope (instance_id or federation id) so that “user” friends can be local or remote.

### 2.6 Summary: one HomeClaw today, multi-HomeClaw later

| Scope | What we have / do | What we leave room for |
|-------|-------------------|-------------------------|
| **One HomeClaw** | **Social network:** Companion + Core only. Users, friends (AI + user), user-to-user forward (Companion → Companion via Core), push (multi-user, multi-device). Channels are separate (User ↔ HomeClaw). Security: app-layer encryption Companion–Core; don’t break http; HTTPS works as-is. | — |
| **Multi-HomeClaw (future)** | Not implemented. | Instances connect and communicate; users on different instances can be friends and message. Identity: allow remote user (e.g. instance_id / remote_id). Encryption: instance–instance and E2E user-to-user. Routing: Core knows how to reach another Core and deliver to a user there. |

---

## Part 3: Implement after summary

- **Implement** the single-instance social network and security as in Part 1 and in the related docs (user-to-user, app-layer encryption, push, no breaking http).
- **Do not** hard-code “one instance only” in identity or friend model: e.g. friend type `user` can later get an optional `instance_id` or `remote_id` for cross-instance.
- **Design for the future upgrade:** While implementing, follow the "Design for future upgrade" rules above. Message path, delivery, and encryption are already expressed so that multi-HomeClaw is an extension (Core(A) → Core(B) → Companion(B)), not a rewrite.
- **Later:** Implement multi-HomeClaw (instance discovery, Core–Core link, cross-instance user identity, routing, and encryption) following Part 2. The bigger social network then builds on the same concepts: Companion ↔ Core ↔ Companion, with Cores talking to each other when the recipient is on another instance.

This keeps one HomeClaw’s social network and security clearly summarized and ensures the design **considers and supports** the future upgrade to multi-HomeClaw (bigger social network) without a redesign.

---

## Part 4: Summary and checklist

### One-page summary

| What | Summary |
|------|--------|
| **Scope** | Social network = **Companion app + Core only**. Nothing to do with channels. Messages always **Companion → Companion** (via Core). Channels = separate path (User ↔ HomeClaw AI). |
| **Actors** | **Users** (real people in user.yml). **Friends (AI):** HomeClaw, Sabrina, etc. — chat via Companion, Core runs LLM. **Friends (user):** another user in same instance (`type: user`, `user_id`) — Core forwards, no LLM. |
| **User-to-user flow** | User 1 sends from Companion to friend User 2. Core forwards (no LLM). User 2 receives **only in Companion** (inbox, push, WebSocket). Not to channel. Reply: same path (Companion → Core → Companion). |
| **Companion media (current)** | **User → Core (AI):** text and image only (no voice). **User → User:** text, image, and push-to-talk (voice). |
| **Delivery** | Inbox (poll or WebSocket) + push to User 2’s devices. One user, multiple devices; push tokens per user_id. Multi-user: one login per Companion at a time. |
| **Files** | Upload to Core → shared folder → link in message → Core serves file via token/signed URL to recipient (and optionally sender). |
| **Security** | **HTTPS** with real cert: no extra work; **do not break http**. **Application-layer encryption:** implement in Companion and Core (encrypt/decrypt payloads). Optional **E2E** later for user-to-user so Core doesn’t read. Channels: we don’t control; no our encryption there. |
| **Config** | `user.yml`: friends with optional `type: user`, `user_id`. Validate user_id exists. Backward compatible: no `type` = AI friend. |
| **Future upgrade (multi-HomeClaw)** | Design **considers** the bigger social network. Instances connect; users on different instances can message. Friend type `user` can later have `instance_id` / `remote_id`. Same path: Companion → Core(A) → Core(B) → Companion. Channels stay per instance. See "Design for future upgrade" and Part 2. |

### Did we miss anything?

| Topic | Status | Note |
|-------|--------|------|
| **Scope: Companion + Core only, no channels** | Done | Documented in all three docs. User-to-user delivery only to Companion; no channel delivery. |
| **Reply flow** | Implicit | Reply is same path: User 2 sends from Companion → Core → User 1’s Companion. No explicit “reply” section; same as “send message to user friend.” |
| **Friend request and accept (one + multi)** | Documented | **Multi-HomeClaw:** Friend request required; only after accept can they communicate (§2.2). **One HomeClaw:** Decide mutual add vs request/accept; consider state `pending` \| `accepted` so multi-HomeClaw reuses it. [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md) §6. |
| **Adding a user-type friend** | Open | Via Portal UI, or only by editing user.yml? Not specified; implementation choice. |
| **Presence / “online”** | Not designed | No “user online” or “last seen” for user friends. Can add later if needed. |
| **Block / mute** | Not designed | No block or mute for user-to-user. Can add later. |
| **Shared folder layout & cleanup** | Open | [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md) §6: per-conversation vs per-recipient, cleanup policy — to be decided with FileSandboxDesign. |
| **API endpoints** | To be defined | Dedicated `POST /api/user-message` or reuse inbound with `forward_only`; inbox/WebSocket endpoints — in implementation steps. |
| **Push payload for user-to-user** | Design done | Push includes `from_user` (or similar) so app can show “From AllenPeng”; see CompanionPushNotifications. |
| **Multi-HomeClaw upgrade (bigger social network)** | Design considered | Design **must** consider future multi-HomeClaw. We leave room: identity (optional `instance_id`/`remote_id`), same message path (Core forwards), same delivery (inbox + push), encryption (app-layer + optional E2E). Do not hard-code single instance. See "Design for future upgrade" and Part 2. |
| **Multi-HomeClaw identity** | Room left |
| **Multi-HomeClaw: security between HomeClaws** | Documented | §2.3: Core–Core auth + TLS (and optionally app-layer); user-to-user across instances prefer E2E; identity/trust and signed friend requests. Consider when designing one HomeClaw (identity, message format, no single-instance assumption). |
| **Multi-HomeClaw identity (duplicate row - fix)** | Room left | Friend type `user` can later get `instance_id` / `remote_id`; don’t hard-code single instance. |

If something important is missing, add it to the relevant doc and to this checklist.
