# User-to-User Messaging via Companion App

This document describes a **design idea** for letting **real users** of the same HomeClaw instance send messages and files to each other through the Companion app, by treating **another user** as a **friend** (a new friend type). Core **forwards** these messages and file links without invoking the LLM.

**The social network (user-to-user) is for Companion app and Core only; it has nothing to do with channels.** Messages are always sent **from Companion app to Companion app** (via Core). Channels (Telegram, Slack, etc.) are a separate path (User ↔ HomeClaw AI) and do not carry user-to-user messages.

**Related docs:**
- [SocialNetworkDesign.md](SocialNetworkDesign.md) — summary of one HomeClaw social network + security; future multi-HomeClaw extension
- [MultiUserSupport.md](MultiUserSupport.md) — user allowlist, channel matching, per-user data
- [UserFriendsModelFullDesign.md](UserFriendsModelFullDesign.md) — friends list, (user_id, friend_id) scoping, Companion flows
- [FileSandboxDesign.md](FileSandboxDesign.md) — sandbox layout, file tools, sharing
- [CompanionEncryptionAndSecurity.md](CompanionEncryptionAndSecurity.md) — encryption Companion–Core (TLS/HTTPS) and optional E2E for user-to-user

---

## 1. Goal

- **Multi-user HomeClaw:** Several real people (User 1, User 2, …) use the same Core (each has an entry in `config/user.yml`).
- **Friends today:** A user’s friends are **roles of Core** (AI companions: HomeClaw, Sabrina, Gary, etc.) — each has a `name`, optional `who` (persona), and optional `identity` file.
- **New capability:** A user can have a **new type of friend** that is **another user** in the same HomeClaw (a real person). When User 1 sends a message to “User 2” (listed as a user-type friend), Core **only forwards** the message to User 2. No LLM, no tools, no other handling. User 2 sees the message in the Companion app because User 2 is on User 1’s friend list (and can appear as a chat like “PengXiaoFeng”).
- **Files:** When users send files to each other, Core stores the file in a **shared folder**, generates a **link**, and sends that link to the recipient in the forwarded message.

---

## 2. Friend type: `user`

Extend the existing **friend** entry in `config/user.yml` with an optional **type** and, when type is `user`, a reference to the target user.

**Current friend (AI role):**
```yaml
friends:
  - name: HomeClaw
  - name: Sabrina
    relation: girlfriend
    who: { gender: female, roles: ['girlfriend'], ... }
```

**New: friend type = user (real person):**
```yaml
friends:
  - name: HomeClaw
  - name: Sabrina
    relation: girlfriend
    who: { ... }
  # New: friend is another user in this HomeClaw
  - name: PengXiaoFeng
    type: user
    user_id: PengXiaoFeng   # id of the user in user.yml (must exist)
```

- **`type`** (optional): Omitted or `core_role` = current behavior (AI companion). `user` = this friend is another user in the same HomeClaw.
- **`user_id`** (required when `type: user`): The **system user id** of that user (must match an `id` in `users` in the same `user.yml`). Used by Core to route the message to the correct recipient.
- **`name`**: Display name in the Companion list (can match the other user’s `name` or be a nickname). Used as the **friend_id** for this “user friend” in the sender’s context (e.g. chat thread title).

**Validation:** On load, Core should check that every `type: user` friend has a valid `user_id` that exists in `users`. If User B is not in `users`, User A cannot add User B as a user-type friend.

**Visibility:** User 2 appears on User 1’s Companion **only if** User 1 has added User 2 as a friend with `type: user`. Optionally, we can require **mutual** add (User 2 also adds User 1) before allowing delivery; see **§6 Open points**.

**Companion knows who is AI vs real person:** The Companion gets the friend list from **POST /api/auth/login** (response includes `friends`) and **GET /api/me/friends**. Each friend entry includes **`type`** and, when type is `user`, **`user_id`**. So the Companion can tell: **AI friend** = no `type` or type ≠ `"user"` (e.g. HomeClaw, Sabrina) → chat goes to Core (LLM); **real person friend** = `type: "user"` and `user_id` set → use user-to-user flow (e.g. POST /api/user-message, show push-to-talk). The app can show different UI and route messages accordingly.

---

## 3. Message path: forward only (no LLM)

When the Companion sends a message **to a friend** that has `type: user`:

1. **Companion** sends the message to Core with: `user_id` (sender), `friend_id` (the name of the friend, e.g. `PengXiaoFeng`), and message content (text, optional attachment).
2. **Core** resolves the sender’s friend list and finds that this `friend_id` corresponds to a friend with `type: user` and `user_id: PengXiaoFeng`.
3. **Core** does **not** call the LLM. It **forwards** the message to the recipient user (PengXiaoFeng):
   - Store or enqueue the message for the recipient (see **§4 Delivery**).
   - Optionally persist a copy in the sender’s context under (user_id, friend_id) for “sent to PengXiaoFeng” history.
4. **Recipient (User 2)** receives the message in the Companion (push and/or in-app inbox). The message is shown in a **user-to-user** thread (e.g. “From AllenPeng”) so it is clear it is from a real person, not from an AI friend.

**API shape (to be defined):** Either reuse existing `POST /inbound` (or chat endpoint) with an extra parameter indicating “deliver to user friend, do not call LLM”, or add a dedicated endpoint, e.g.:

- `POST /api/user-message`  
  Body: `{ "from_user_id", "to_user_id", "text", "attachment_link?" }`  
  Core: validate both users exist and that sender has `to_user_id` as a user-type friend; then forward.

Or:

- Existing inbound with `friend_id` = user-type friend and a flag `forward_only: true` so Core skips LLM and only forwards.

---

## 4. Delivery: how the recipient gets the message

The recipient (User 2) receives the message **only via the Companion app** (inbox, push, WebSocket). **Do not deliver user-to-user messages to the recipient’s channel** (Telegram, Slack, etc.). If we sent the message to User 2’s channel, User 2 would see it there but would not know how to reply in a way that goes back to User 1 — and Core would not know either (channel messages are treated as User ↔ HomeClaw, not as user-to-user replies). So user-to-user delivery is Companion-only.

- **Inbox / queue:** Core stores “user-to-user” messages in a per-recipient store (e.g. a table or file per `to_user_id`). Companion polls (e.g. `GET /api/users/me/inbox`) or subscribes via **WebSocket** for new messages. When the app gets a new message, it shows it in the thread “From &lt;User 1&gt;”.
- **Push notification:** When Core forwards a message, it triggers a **push** to User 2’s device(s) with `from_user: AllenPeng` (or similar) so the notification shows “AllenPeng: &lt;preview&gt;”. Tapping opens the Companion to the user-to-user chat with AllenPeng. See [CompanionPushNotifications.md](CompanionPushNotifications.md).
- **WebSocket:** If the Companion holds a WebSocket connection to Core, Core can push the message over that connection when User 2 is online.

Implementation can combine these (e.g. persist in inbox + push so that when User 2 opens the app, they also see the message in the inbox).

---

## 5. Files: shared folder and link

When User 1 sends a **file** to User 2:

1. **Companion** uploads the file to Core (e.g. `POST /api/upload` or similar) with metadata: from_user_id, to_user_id (or friend_id of type user).
2. **Core** stores the file in a **shared folder** with clear access control. Options:
   - **Instance-wide shared folder:** e.g. `workspace/shared/user_messages/` with subdirs by conversation or by date, e.g. `workspace/shared/user_messages/AllenPeng_to_PengXiaoFeng/2025-03-03/<filename>`.
   - Or a **per-recipient** folder: `workspace/shared/inbox/PengXiaoFeng/from_AllenPeng/<id>_<filename>`.
3. **Core** generates a **link** that only the recipient (and optionally the sender) can use to access the file. For example:
   - A short token stored in Core that maps to the file path; e.g. `GET /api/shared-file/<token>` returns the file only if the requester is the recipient (or sender). Or use a signed URL with expiry.
4. **Core** includes this **link** in the forwarded message to User 2 (e.g. in the message body or as an `attachment_link` field). The Companion shows it as a clickable attachment; when User 2 opens the link (in-app or in browser), Core serves the file if the user is authorized.

**Security:** Only the intended recipient (and optionally the sender) should be able to access the file via the link. Do not expose the raw file path to the client; use tokens or signed URLs.

**Images:** User-to-user messages can include **images** directly. The Companion sends `POST /api/user-message` with an `images` array. Each item can be a **data URL** or a **file path**; Core forwards them to the recipient via WebSocket and stores them in the inbox.

**Current design — what the Companion supports:**
- **User → Core (AI):** **Text and image only.** The Companion does not support voice or push-to-talk when chatting with the AI (HomeClaw, Sabrina, etc.).
- **User → User:** **Text, image, and push-to-talk (voice).** When messaging another user, the Companion can send text, images, and voice recordings.

**Voice / push-to-talk (user-to-user only):** User-to-user messages can include **voice (audio)** so one user can send a short recording directly to another. Voice is not used for user→AI in the current design. The Companion sends `POST /api/user-message` with an `audios` array. Each item can be:
- A **data URL** (e.g. `data:audio/webm;base64,...` or `data:audio/mpeg;base64,...`) — Core forwards it as-is to the recipient via WebSocket and stores it in the inbox.
- A **file path** that Core can read — Core converts it to a data URL (supports mp3, ogg, wav, webm, m4a) and includes it in the push payload.

So both images and voice are transferred directly to the other user: stored in their inbox and delivered over WebSocket (and push when applicable).

**Not a link — inline data.** Audio (and images) are sent as **data URLs**, not as links to a file on the server. A data URL is the **entire audio content** encoded in the message, e.g. `data:audio/webm;base64,<base64-encoded-bytes>`. The recipient gets the full audio in the WebSocket payload or inbox JSON; there is no separate “click to download” step.

**How the recipient plays it (Companion app):** The Companion receives `audios` (array of data URLs) or `audio` (first item). To play:
1. **Option A:** If the platform audio API or package accepts a data URL (e.g. some Web or Flutter players), pass the data URL directly as the source.
2. **Option B:** Decode the data URL: strip the `data:audio/...;base64,` prefix, base64-decode the rest to raw bytes, then feed those bytes to the audio player (e.g. from a temporary file or in-memory stream). Flutter: `audioplayers` or `just_audio` can play from a file path — write the decoded bytes to a temp file and pass that path. Web: use `<audio src="data:audio/webm;base64,...">` and the browser plays it natively.

So the other user **plays it inside the Companion**: tap the voice message → app plays the audio from the embedded data (no external link, no extra download).

---

## 6. Open points

- **Consent / friend request and accept:** For **multi-HomeClaw**, a **friend request is required**; only **after acceptance** can two users communicate (see [SocialNetworkDesign.md](SocialNetworkDesign.md) Part 2). For **one HomeClaw**, we decide: (a) **Mutual add** — both must list each other as user-type friends before messages are delivered; or (b) **Request/accept flow** — User 1 sends a friend request, User 2 sees "pending" and accepts (or declines); only then can they message. Option (b) reuses the same state (`pending` | `accepted`) that multi-HomeClaw will use. Either way, no messages are delivered until the relationship is established (mutual or accepted). Design the one HomeClaw social network with this in mind so it extends to multi-HomeClaw.
- **Delivery mechanism:** Prefer inbox + WebSocket for real-time, plus push for when the app is in background. Exact endpoints and payloads to be defined in implementation steps.
- **Companion UX:** Distinguish “Chat with AI friend (HomeClaw, Sabrina, …)” from “Chat with User (PengXiaoFeng)”. For user-to-user chats, the UI should show “From &lt;name&gt;” and not show an AI reply; only the forwarded message and any file link.
- **Shared folder layout:** Final layout (per-conversation vs per-recipient, naming, cleanup policy) to be decided with [FileSandboxDesign.md](FileSandboxDesign.md) and existing sandbox semantics.
- **Backward compatibility:** Existing friends without `type` continue to be treated as `core_role` (AI). New user-type friends require `type: user` and `user_id`.
- **Security and multi-HomeClaw:** When we design the one HomeClaw social network, we consider how **communications between HomeClaws** will be secured later (Core–Core auth and encryption, E2E for user-to-user across instances). See [SocialNetworkDesign.md](SocialNetworkDesign.md) §2.3 (security between HomeClaws). Identity and message format should not assume a single instance so that inter-instance security (TLS, app-layer, E2E) can be added without redesign.

---

## 7. Summary

| Item | Description |
|------|-------------|
| **Friend type** | Add `type: user` and `user_id` to a friend entry in `user.yml` so that friend refers to another user in the same HomeClaw. |
| **Message path** | Companion → Core with (from_user_id, to_user_id or friend_id). Core forwards to recipient; **no LLM**, no tools. |
| **Delivery** | Inbox and/or WebSocket and/or push so the recipient sees the message in the Companion (e.g. “From AllenPeng”). |
| **Files** | Store in shared folder; generate a link; send link in the forwarded message. Core serves file via token/signed URL with recipient (and optionally sender) access only. |
| **Images** | Send as `images` array (data URLs or file paths). Core forwards directly: data URLs passed through; paths read and converted to data URLs. Recipient gets them via WebSocket and in inbox. |
| **Voice / push-to-talk (user→user only)** | Send as `audios` array. User→AI = text + image only; User→User = text + image + voice. |
| **Config** | Extend `user.yml` friends with `type`, `user_id`. Validate `user_id` exists in `users`. |

This design allows multiple real users in one HomeClaw to communicate via the Companion app by adding each other as “user” friends and sending messages and files that Core forwards without involving the AI.
