# Companion app — FAQ (location, Markdown, combine, switch, plugin)

Answers to common questions about the Companion app and how it works with Core and the Friends plugin.

---

## 1. Does the Companion app send location back to Core when it has the data?

**Current state: No.** The app does **not** send location to Core today.

- **Core supports it:** The `/inbound` API and `InboundRequest` model include an optional `location` field. When present, Core stores it as the latest location for the user (or the shared "companion" key when not combined) and uses it in system context (e.g. for weather, scheduling). See `core/core.py` (e.g. `_handle_inbound_request`, `_set_latest_location`, `_normalize_location_to_address`).
- **App does not send it:** In `clients/homeclaw_companion/lib/core_service.dart`, `sendMessage()` builds the request body with `user_id`, `text`, `channel_name`, `conversation_type`, `session_id`, `images`, `videos`, `audios`, `files` — but **no `location`**. The app also does not use a geolocation package (e.g. `geolocator`) or request location permission for this purpose.
- **To add it:** (1) Add a way in the app to get current location (e.g. `geolocator` + permission), (2) Add an optional `location` argument to `sendMessage()`, and (3) include it in the JSON body (e.g. `"location": "lat,lng"` or an address string). Core will then store and use it as above.

---

## 2. Can the Companion app display Markdown beautifully?

**Current state: No.** Replies are shown as **plain text** only.

- In `lib/screens/chat_screen.dart`, each message is rendered with `SelectableText(entry.key, style: ...)`. There is no Markdown or rich-text widget (e.g. `flutter_markdown`).
- So **bold**, *italic*, lists, code blocks, and links appear as raw characters, not formatted.
- **To add it:** Use a Markdown widget (e.g. `flutter_markdown`) in the chat bubble for assistant messages, and pass the reply string into it. Keep `SelectableText` or add a “copy” action if needed.

---

## 3. How does the Companion app “combine with one user” or system?

**Design (Core + docs):**

- **Combined with a user:** The client sends a `user_id` that exists in `config/user.yml` (e.g. chosen from a picker). Core treats the request as that user’s conversation: main flow, that user’s memory and chat, with `channel_name: companion`. No companion plugin is used in this case.
- **Not combined (System):** The client sends `user_id: companion` (or a value that is not in user.yml). Core treats it as the special “companion” user and routes to the **Friends plugin** (external_plugins/friends). All uncombined Companion traffic belongs to this one “companion” user.

**Current state of the app:** There is **no “combine with user” UI** yet. The app always calls `sendMessage(..., userId: 'companion')` (default) and does not pass a different `userId`. So the app always behaves as **not combined** (System): every request goes to Core with `user_id: companion` and is routed to the Friends plugin when companion is enabled.

**To implement “combine with user”:** Add a picker (e.g. in Settings or chat header) that:
- Loads the list of users from Core (e.g. `GET /api/config/users`),
- Lets the user choose one user or “System”,
- Stores the selected `user_id` (or “companion” for System),
- Passes that `userId` into `sendMessage(..., userId: selectedUserId)`.

---

## 4. When switching the combined user, should the messages be empty?

**Yes.** When the user switches from one combined user to another (or to/from System), the **on-screen message list should reflect the new context**:

- **Option A — Clear and show empty:** Clear the in-memory message list so the screen shows no messages for the new user. This matches “new conversation for this user” and is simple.
- **Option B — Load history:** If Core (or an API) exposes chat history per user/channel, you could load that user’s companion (or main) history and display it. Today the Companion app does not load history from Core; it only shows messages from the current session.

So in practice, **clearing messages when switching user** (empty list) is the expected and consistent behavior until a history API is used.

---

## 5. How does the Companion app work with the Friends plugin in `external_plugins/`?

**Flow:**

1. **Companion app** sends `POST /inbound` to Core with:
   - `channel_name: "friend"`, `conversation_type: "friend"`, `session_id: "friend"` (matching Core's session_id_value; default is "friend"),
   - `user_id: "companion"` (when not combined; otherwise the chosen user_id from the picker).

2. **Core** (`core/core.py`, `_handle_inbound_request`):
   - Sees companion config enabled and that the request is for companion (by `conversation_type` / `session_id` / `channel_name` or keyword).
   - If **combined** (user_id is in user.yml and not "companion"): continues in the **main flow** (that user’s memory/chat, channel = companion); no plugin.
   - If **not combined** (user_id is "companion" or system): sets `pr.system_user_id = "companion"`, `pr.user_id = "companion"`, looks up the **Friends** plugin by id (e.g. `friends`), and calls `plugin_manager.run_external_plugin(plug, pr_companion)`.

3. **Friends plugin** (`external_plugins/friends/server.py`):
   - Is an HTTP server (e.g. port 3103) registered with Core.
   - Core forwards the request to the plugin’s `/run` (PluginRequest with `user_input`, `user_id`, etc.).
   - The plugin: reads chat history from its **own store** (`database/friends_store/`), builds messages, calls **Core’s LLM** (`POST /api/plugins/llm/generate`), appends the turn to its store, and returns the reply in a PluginResult.

4. **Core** returns the plugin’s reply (and optional images) in the `/inbound` HTTP response to the app.

5. **Companion app** displays the reply in the chat (currently as plain text).

So: when the app is **not** combined with a user, it talks to Core, and Core delegates to the **Friends** plugin (`external_plugins/friends`). That plugin owns companion chat storage and uses Core only for LLM. When the app **is** combined with a user (once implemented), Core uses the main flow and that user’s memory/chat, and does not call the Friends plugin for that request.

---

## Summary table

| Topic | Current behavior | To improve |
|-------|------------------|------------|
| **Location** | App does not send location to Core. | Add location permission + geolocator, and pass `location` in `sendMessage()` body. |
| **Markdown** | Replies shown as plain text only. | Use a Markdown widget (e.g. `flutter_markdown`) for assistant messages. |
| **Combine with user** | No picker; app always sends `user_id: companion` (System). | Add user picker (from `/api/config/users`) and pass chosen `userId` to `sendMessage()`. |
| **Switch user → messages** | No user switch in app yet. | When adding picker: clear (or replace) message list when user changes so messages are empty for the new user (or load that user’s history if API exists). |
| **Companion plugin** | When not combined, Core routes to `external_plugins/companion`; plugin stores chat and uses Core LLM. | No change needed for basic flow; optional: expose companion settings/history from plugin to app. |
