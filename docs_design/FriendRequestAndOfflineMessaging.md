# Friend Request Flow and Offline User-to-User Messaging

This doc describes: (1) **Add Friend** UI and friend request/accept/reject flow, and (2) **offline handling** for user-to-user messages (text, friend request, audio, video) so messages appear when the app is opened.

**Related:** [SocialNetworkDesign.md](SocialNetworkDesign.md), [UserToUserMessagingViaCompanion.md](UserToUserMessagingViaCompanion.md), [CompanionPushNotifications.md](CompanionPushNotifications.md).

---

## 1. Add Friend and Friend Request Flow

### 1.1 Goal

- Users cannot add each other by editing `user.yml` manually only. The **Companion app** should let a user **discover other users** (for now: same HomeClaw; later: other HomeClaws), **send a friend request**, and the recipient **accept or reject** in the app. On accept, both users are added to each other's friends (type: user) and persisted to `user.yml`.

### 1.2 Flow

1. **User1** opens **Add Friend** in the Companion. The app calls **GET /api/users** (authenticated). Core returns all users from `user.yml` **except the logged-in user** (so you cannot add yourself). For now only users from the same HomeClaw; later can include users from other instances.
2. **User1** selects **User2** and taps **Send request** (optional: one-line message, or system text like "X wants to add you as a friend").
3. Core stores the request in a **friend_requests** store (e.g. `data_path()/friend_requests.json`) with state **pending**. (No push is sent for friend requests; push is used only for reminders.)
4. **User2** opens the app and sees **Friend requests** (e.g. a tab or a section). **GET /api/friend-requests?user_id=...** returns pending requests where `to_user_id == user_id`. Each entry: from_user_id, from_user_name, request_id, optional message, created_at.
5. **User2** taps **Accept** or **Reject**.
   - **Accept:** Core adds User1 to User2's friends (type: user, user_id: User1.id, name: User1.name) and User2 to User1's friends (type: user, user_id: User2.id, name: User2.name), then **persists to user.yml** (read users, mutate both friends lists, write back). Core marks the request as accepted and can **notify User1** (push or a system message): "PengXiaoFeng accepted your friend request." Both users now see each other in their friends list in the Companion.
   - **Reject:** Core marks the request as rejected and **notifies User1** (push): "PengXiaoFeng declined your friend request."
6. **Friend request is a special type:** It is not a normal chat message. It is stored in the friend_requests store until accepted/rejected. Optionally we can add a short "message" field (e.g. "Hi, let's connect!") that the recipient sees with the request.

### 1.3 Core APIs (summary)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/users | Bearer or API key | List users (id, name) excluding the authenticated user. For "Add Friend" dropdown. |
| POST | /api/friend-request | Bearer or API key | Body: from_user_id, to_user_id, message? (optional). Create pending request; push to to_user_id. |
| GET | /api/friend-requests | Bearer or API key | Query: user_id (or from auth). Return pending requests for this user (to_user_id == user_id). |
| POST | /api/friend-request/accept | Bearer or API key | Body: request_id (or from_user_id + to_user_id). Caller must be to_user. Add each other to friends; save user.yml; push to from_user. |
| POST | /api/friend-request/reject | Bearer or API key | Body: request_id. Caller must be to_user. Mark rejected; push to from_user. |

### 1.4 Companion UI

- **Add Friend** screen: List from GET /api/users (exclude self already done by Core). Tap a user → confirm "Send friend request to X?" → POST /api/friend-request. Show "Request sent."
- **Friend requests** entry point: e.g. a badge or a row on the friend list screen ("Requests (2)"), or a tab. Opens **Friend requests** screen: list pending requests (from GET /api/friend-requests); each row: "X wants to add you as a friend" + [Accept] [Reject]. On Accept/Reject call the corresponding API and refresh.

---

## 2. Offline Handling for User-to-User Messages

### 2.1 Problem

When the Companion app is **offline** (closed or in background), user-to-user messages (text, friend request notification, audio, video) must still (1) **reach the recipient** and (2) **appear in the message list** when they open the app.

### 2.2 Current behaviour

- **Core** stores every user-message in the **inbox** (per recipient user_id) and calls **deliver_to_user**, which:
  1. Sends the payload (text, images, audios, videos) to any **WebSocket** sessions for that user_id (when app is in foreground).
  2. **Push is used only for reminders** (source `reminder` or `cron`). User-to-user messages and friend requests **do not** trigger push (push is not stable on all setups). They stay in the **inbox** and **friend_requests** store; the user sees them when opening the app and the relevant screen (chat or Friend requests).
- So when the app is **offline**, the user **does not** get a push for a new user message or friend request. When they **open the app** and open that friend's chat (or Friend requests), the Companion loads from **GET /api/user-inbox** or **GET /api/friend-requests** and **messages/requests are in the list**. Reminders still use push so the user can be notified when the app is killed or in background.

### 2.3 What we need to ensure

| Scenario | What happens | How |
|----------|---------------------|-----|
| **App in foreground, WebSocket connected** | Message delivered via WebSocket. | deliver_to_user sends WS only (no push for user_message). Companion _onPushMessage adds to list. |
| **App in background or killed** | No push for user messages. When they open app and open the chat, messages are visible from inbox. | Inbox already has messages; opening chat calls _loadUserInbox. |
| **Friend request** | No push. User2 sees pending requests when they open the Friend requests screen. | GET /api/friend-requests when the user opens that screen. |
| **Audio / video message** | Same as text: stored in inbox with audios/videos. When they open the chat, full message (with playable audio/video) loads from inbox. | deliver_to_user sends WS when connected; inbox stores them; Companion displays them. |
| **Reminder** | Push is sent so user can be notified when app is killed or in background. | deliver_to_user sends push only when source is `reminder` or `cron`. |

### 2.4 Optional improvements

- **Refresh inbox on app resume:** Implemented. When the app comes to the **foreground**, if the current screen is a **user-friend chat**, ChatScreen calls **GET /api/user-inbox** again so new messages appear without leaving and re-entering the chat.

### 2.5 Summary

- **Push:** Used **only for reminders** (source `reminder` or `cron`). User messages and friend requests do not trigger push; delivery is WebSocket (when app in foreground) + storage in inbox / friend_requests.
- **User-to-user messages (text, audio, video):** Stored in inbox; when the user opens that chat, GET /api/user-inbox loads messages (and media). ChatScreen refreshes inbox on app resume when on a user-friend chat.
- **Friend requests:** Stored in friend_requests; when the user opens the Friend requests screen, GET /api/friend-requests loads them. No push for friend requests.
- **Core→user (AI) messages:** Core stores every user message and AI reply in its chat DB (per user_id, friend_id). There is no separate "inbox" for AI replies; the **conversation** is the source of truth. When the Companion opens an **AI friend** chat, it calls **GET /api/chat-history** (Bearer) to load the transcript from Core. So if the app was offline when the reply was produced, the reply is still in Core's DB and appears when the user opens the chat (or when the app resumes on that chat). This makes the "inbox" behaviour work for Core→user: messages are stored on Core; the app loads them when it can.
