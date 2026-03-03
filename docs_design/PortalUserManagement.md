# Portal user management (TinyDB)

With user data in TinyDB (see UserDataTinyDB.md), users are no longer added by editing user.yml. **Portal admin** logs in and creates/edits users. This doc describes the flow and rules.

---

## 1. Who can manage users

- **Portal admin** (portal_admin.yml or session): can create, edit, delete users and reset passwords.
- **Companion app**: user can change **their own** password (change-password flow). User cannot create other users or edit email/im/phone (those are only in Portal).

---

## 2. Create user (Portal)

When creating a user, the admin provides:

| Field | Required | Default | Notes |
|-------|----------|---------|--------|
| **name** | Yes | — | Display name. |
| **id** | No | same as name | Unique user id (storage, chat, memory). |
| **username** | Yes for Companion login | — | Used with password to log in from Companion. |
| **password** | No | e.g. `changeme` | Default password; user should change in Companion or admin resets in Portal. |
| **type** | No | `normal` | `normal` or `companion`. |
| **email** | No | `[]` | List of email addresses for channel routing. **Empty = no email channel access.** |
| **im** | No | `[]` | List of IM ids (e.g. `dingtalk_xxx`, `slack_yyy`). **Empty = no IM channel access.** |
| **phone** | No | `[]` | List of phone numbers. **Empty = no phone channel access.** |
| **friend_preset_names** | No | `[]` | List of preset names from friend_presets.yml (e.g. `reminder`, `note`, `finder`). **HomeClaw is always added first**; then selected presets as AI friends. |

**Channel access rule:** A user only receives messages from a channel (email, IM, phone) if the incoming id is in that user’s corresponding list. Empty list = no access from that channel type. So there is no “all IM connect to this user” unless the admin explicitly adds the ids in Portal.

---

## 3. Edit user (Portal)

- Admin can change: name, id, username, email, im, phone, permissions, type, who, **friend list** (or friend_preset_names if we support “replace by presets”).
- **Reset password**: action in Portal sets a new password (e.g. back to default or admin-chosen).

---

## 4. Password

- **Default on create**: If no password is sent, use a default (e.g. `changeme`). User should change via Companion or admin resets in Portal.
- **Change in Companion**: User logs in with username/password; Settings (or profile) has “Change password”. Core/Portal need an API (e.g. `PUT /api/me/password` or Portal `PATCH /api/config/users/me/password`) to update password for the logged-in user.
- **Reset in Portal**: Admin selects user and “Reset password”, sets new value (stored in TinyDB).

---

## 5. AI friends from presets

- **Friend presets** are defined in `config/friend_presets.yml` (e.g. `reminder`, `note`, `finder`).
- When **creating** a user, the admin can select a list of preset names. Core builds the user’s `friends` list as:
  1. **HomeClaw** (always first, type `ai`, no preset or preset `homeclaw`).
  2. One Friend per selected preset: `name` = display name (e.g. “Reminder”), `preset` = preset key (e.g. `reminder`), `type` = `ai`.
- HomeClaw is **forced** and added by default; presets are optional additions.

---

## 6. API outline

- **GET /api/config/friend-presets**  
  Returns list of `{ "id": "reminder", "name": "Reminder" }` from friend_presets.yml so Portal can show a multi-select.

- **POST /api/config/users**  
  Body can include `friend_preset_names: ["reminder", "note"]`. If present, build `friends` as HomeClaw + one Friend per preset (name from preset id, preset=id, type=ai). If `password` omitted, set default (e.g. `changeme`). email/im/phone can be `[]` (empty = no channel access).

- **PATCH /api/config/users/{name}**  
  Already exists. Can add support for `friend_preset_names` to replace AI friends by presets, and “reset password” via a dedicated action or field.

- **Companion “Change password”**  
  Requires an API (e.g. `PUT /api/me/password` with Bearer token and body `{ "old_password", "new_password" }`) and corresponding handler that updates the user’s password in TinyDB.

---

## 7. Summary

- Users are **created and edited in Portal** by the admin; TinyDB is the store.
- **Email, im, phone** are only set in Portal; empty = no channel access (no “match all”).
- **HomeClaw** is always the first friend; additional AI friends come from **friend presets** selected at create (and optionally at edit).
- **Password**: default on create; user can change in Companion; admin can reset in Portal.
