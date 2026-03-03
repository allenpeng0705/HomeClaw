# User thumbnail and friend icons / custom AI friends

Design for: (1) user profile thumbnail stored on Core and shown when added as friend, (2) friend type taxonomy (ai, user, remote_ai, remote_user), (3) icons for preset vs custom AI friends, (4) Companion UI to add/edit custom AI friends with name, relation, who, identity text, and thumbnail. **When no thumbnail is set, use the system default icon (same as today).**

---

## 1. Summary of ideas (as proposed)

| Idea | Description |
|------|-------------|
| **User thumbnail** | Each user uploads one thumbnail for themselves; stored on Core. When anyone adds them as a friend, that icon is shown next to the user (e.g. in friend list / chat). |
| **Friend types** | Explicit types only: **ai**, **user**, **remote_ai**, **remote_user**. No “omit = ai”; every friend has a type. Remote_* reserved for future multi-HomeClaw. |
| **Preset AI friends** | Icons for preset friends (Reminder, Note, Finder, HomeClaw, etc.) defined in **config/friend_presets.yml** (static). HomeClaw can be a preset with “nothing” (no icon or default). |
| **Custom AI friends** | Added from Companion by the user; thumbnail/avatar set at add time and uploaded to Core. **Friend entry (name, relation, who, identity, etc.) is persisted into user.yml** in that user’s `friends` section. One avatar per (user_id, friend_id) stored on Core. |
| **Identity** | Today: identity is a **filename** (e.g. `identity.md`) under `{user_id}/{friend_id}/`. Content is in that file. Proposal: allow Companion to set **identity content** (text) for custom AI friends; Core stores it as the identity file for that friend. |

---

## 2. Assessment and recommendations

### 2.1 User thumbnail on Core

- **Verdict: Good and consistent.** One avatar per user, stored on Core; any user who adds them as a friend sees that avatar.
- **Storage:** One file (or URL) per user, e.g. `data_path()/user_avatars/{user_id}.{ext}` or in a small “profile” store (e.g. JSON + blob path). Prefer a single canonical path so “current thumbnail” is unambiguous.
- **API:** e.g. `PUT /api/me/avatar` (Bearer) to upload; `GET /api/user/{user_id}/avatar` or `GET /api/me/avatar` to read. Companion “Add friend” / friend list can then load the other user’s avatar by user_id.
- **Format/size:** Limit format (e.g. JPEG/PNG) and size (e.g. 512×512 or 1MB) to avoid abuse and keep storage predictable.

### 2.2 Friend types: ai, user, remote_ai, remote_user

- **Verdict: Good for clarity and future multi-HomeClaw.**
- **Explicit types only (no “omit = ai”):**
  - **ai** — Local/custom AI friend (preset or custom).
  - **user** — Human in same HomeClaw.
  - **remote_ai** — AI friend on another HomeClaw (future).
  - **remote_user** — User on another HomeClaw (future).
- **No backward compatibility for missing type:** Every friend must have an explicit `type`. When adding or migrating, set `type: ai` for all non-user friends and `type: user` for user-type friends.
- **Presets:** Preset friends (Reminder, Note, Finder) have `type: ai` and `preset: reminder` etc.; HomeClaw is `type: ai` with an empty or “default” preset.

### 2.3 Icons: presets vs custom

- **Preset friends (friend_presets.yml):**  
  Add an optional **icon** (or **avatar**) field per preset: path or URL relative to config/assets or project root. Core (and Companion) resolve it and serve it. HomeClaw can have `icon: null` or a default asset.
- **Custom AI friends:**  
  One thumbnail per (user_id, friend_id), stored on Core (e.g. `user_friend_avatars/{user_id}/{friend_id}.{ext}`). Companion uploads via e.g. `PUT /api/me/friends/{friend_id}/avatar` and list/detail APIs return an avatar URL or path so the app can show the icon with the friend.

This keeps: presets = static, config-driven; custom = per-user, editable from Companion.

### 2.4 Companion: add/edit custom AI friends

- **Verdict: Fits the model well.**  
  Today custom AI friends are added by editing user.yml (name, relation, who, identity filename). Exposing this via Companion with a form is the right direction.
- **Fields to support:**
  - **name** (required) — friend_id and display name.
  - **relation** — e.g. girlfriend, friend (string or list).
  - **who** — sub-fields: description, gender, roles, personalities, language, response_length, idle_days_before_nudge (optional).
  - **identity** — **text** for the identity content (Core writes this to `{user_id}/{friend_id}/identity.md` or the configured filename).
  - **thumbnail** — one image upload; Core stores and associates with (user_id, friend_id).
- **Persistence:**  
  **Custom AI friends are persisted into user.yml:** when the user adds a custom AI friend from the Companion app, Core appends (or updates) the friend entry in that user’s `friends` section in **config/user.yml**. Avatar is uploaded to Core and stored on disk (see §6). So: one source of truth (user.yml) for who the friends are; avatars live under data_path. **YAML for now;** moving users/friends to a database can be considered later if needed.
- **HomeClaw:**  
  Treat as a special preset (e.g. name `HomeClaw`, preset empty or `homeclaw`). No need to create it from Companion; it’s always present. Icon from preset or default.

### 2.5 Identity: filename vs content

- **Current:** Friend has `identity: Optional[str]` = filename (e.g. `identity.md`). Content lives in `workspace_dir/{user_id}/{friend_id}/{identity_filename}` (see base/workspace.py `load_friend_identity_file`).
- **Proposal:** For custom AI friends, user supplies **identity content** (text). Core creates/updates the identity file for that (user_id, friend_id) (e.g. `identity.md`).
- **Recommendation:** Keep **identity** on the Friend model as the filename (default `identity.md`). Add an API “set identity content” that writes to that file. Companion then sends “identity text” and Core writes it to `{user_id}/{friend_id}/identity.md`. No change to the existing identity **contract** (file per friend); only the **source** of the content (Companion vs manual edit).

---

## 3. Suggested phasing

| Phase | Scope |
|-------|--------|
| **1** | User thumbnail: Core storage + upload/read API; Companion “my profile” upload and show in settings; show other users’ avatars in friend list when type=user. |
| **2** | Friend types: **ai**, **user**, **remote_ai**, **remote_user** (explicit only). Preset friends in friend_presets.yml get **icon** field; Core serves them; Companion shows in list; no thumbnail → default icon. |
| **3** | Custom AI friend: API to add/update/delete friend; Core **writes into user.yml** in that user’s section; set identity **content** (Core writes identity file). |
| **4** | User avatar + friend avatar: store under `data_path()/avatars/` (§6); Companion add/edit custom AI friend UI with name, relation, who, identity text, and one thumbnail (uploaded to Core). |
| **5** | (Future) remote_ai / remote_user and multi-HomeClaw. |

---

## 4. Data shape (for implementation)

- **User avatar:**  
  `GET/PUT /api/me/avatar` (Bearer). Optional: `GET /api/users/{user_id}/avatar` for others (for friend list).
- **Preset icon (friend_presets.yml):**  
  e.g. `presets.reminder.icon: "assets/friends/reminder.png"` (path relative to project or config). Core resolves and serves via e.g. `/api/assets/friends/reminder.png` or embeds in preset API response.
- **Custom AI friend:**  
  - Create: `POST /api/me/friends` body `{ name, relation?, who?, identity_text?, thumbnail? }`.  
  - Update: `PATCH /api/me/friends/{friend_id}`.  
  - Delete: `DELETE /api/me/friends/{friend_id}`.  
  - Avatar: `PUT /api/me/friends/{friend_id}/avatar` (image body or multipart).
- **Friend type:**  
  In Friend model and API: `type: "ai" | "user" | "remote_ai" | "remote_user"`. **Explicit only** (no default when omitted; new/migrated entries must set type).

---

## 5. Default icon when no thumbnail

- **User avatar:** If the user has not set a thumbnail, show the **system default icon** (same as current behaviour in the app).
- **Friend avatar (preset):** If a preset has no `icon` in friend_presets.yml, use the same default icon.
- **Friend avatar (custom AI):** If the user did not upload an avatar for that custom friend, use the default icon.
- **Friend avatar (type=user):** Show the other user’s profile avatar if they have one; otherwise default icon.

No “empty” or “no icon” state in the UI — always fall back to the default.

---

## 6. Where to save avatars (investigation)

Core uses **`Util().data_path()`** for mutable data (today: `root_path()/database` → e.g. `database/` under project root). Config (user.yml, friend_presets.yml) lives under **`Util().config_path()`** (e.g. `config/`). Uploads today go to **`root_path()/database/uploads`** (see `core/routes/files.py`); that is the same as `data_path()/uploads`.

**Recommended avatar paths (under `data_path()` = `database/`):**

| What | Path | Rationale |
|------|------|------------|
| **User avatar** (one per user) | `data_path()/avatars/users/{user_id}.{ext}` | One file per user; simple lookup. Use a single extension (e.g. `.png` or `.jpg`) per user; overwrite on re-upload. Sanitize `user_id` for path safety (e.g. alphanumeric + underscore). |
| **Friend avatar** (custom AI, per user) | `data_path()/avatars/friends/{user_id}/{friend_id}.{ext}` | One file per (user_id, friend_id). Custom AI friends only; preset icons stay in config/assets or friend_presets.yml. Sanitize both ids. |

**Why under `data_path()` (database/):**

- Keeps **config/** for YAML only (no binary blobs in version-controlled config).
- Consistent with existing patterns: `data_path()` already holds `user_inbox/`, `profiles/`, `push_tokens.json`, `friend_requests.json`, and uploads under `database/uploads/`.
- `profiles/` is under data_path and is per-user; avatars are a separate tree (`avatars/users/`, `avatars/friends/`) so we don’t mix profile JSON with image files in the same dir.

**Serving:** Core can expose e.g. `GET /api/me/avatar` and `GET /api/users/{user_id}/avatar` (and for friends, `GET /api/me/friends/{friend_id}/avatar`) that read from these paths and return the image (or 404 → client shows default icon). Alternatively, a single route like `GET /api/avatars/users/{user_id}` and `GET /api/avatars/friends/{user_id}/{friend_id}` with proper auth (e.g. only for logged-in user for “me”, or for users who are friends).

**File naming:** Use a fixed extension per record (e.g. always `.png` after first upload) so the path is deterministic; on upload, overwrite the file at that path. Limit size (e.g. 1MB) and format (JPEG/PNG) in the upload handler.

---

## 7. YAML vs database (later)

- **Current:** Users and their friends are stored in **config/user.yml** (read/write via `Util`, `User.to_yaml`, `add_friend_bidirectional` in base/util.py). Custom AI friends added from Companion will be written into this same file in the user’s section.
- **Later:** If we outgrow a single YAML (e.g. many users, concurrent edits, or richer schema), we can introduce a **database** for users and friends and keep user.yml as an optional export/import or legacy. For now, **sticking with user.yml is reasonable**; avatar storage is already separate under `data_path()/avatars/`.

---

## 8. Conclusion

- **Default icon when no thumbnail:** Always use the system default icon (no empty state).
- **Explicit friend types:** ai, user, remote_ai, remote_user only; no “omit = ai”.
- **Custom AI friends:** Added from Companion; **settings written into user.yml** in that user’s section; thumbnail uploaded to Core and stored under `data_path()/avatars/friends/{user_id}/{friend_id}.{ext}`.
- **User avatar:** Stored under `data_path()/avatars/users/{user_id}.{ext}`; when missing, show default icon.
- **YAML for now;** database for users/friends can be considered later.
- **Preset icons** in friend_presets.yml; **HomeClaw** as a preset with nothing (or default icon). Phasing as in §3 keeps each step shippable and testable.
