# How friends' folders are created (and where it gets messy)

## Preset friends: one folder under homeclaw_root or per-user?

You might ask: every user has the same preset friends (e.g. HomeClaw, Note, Reminder). Should those have **one shared folder** under `homeclaw_root` (e.g. `homeclaw_root/Note/`) instead of one per user (`homeclaw_root/{user_id}/Note/`)?

- **If that single folder holds any user-specific data → yes, it causes data leaking.**  
  Today each friend folder holds:
  - **identity.md** — can be customized per user (Alice’s Note persona vs Bob’s).
  - **knowledge/** — files and RAG content for that (user, friend). Alice’s notes must not be visible to Bob.
  - **output/** — generated files for that (user, friend).

  If we put all users’ Note data in `homeclaw_root/Note/`, then Alice and Bob would share the same identity, knowledge, and output. That is **data leaking** and wrong.

- **Safe use of a shared folder:** only for **preset template** content that is not user-specific.  
  Example: `homeclaw_root/presets/Note/` (or `homeclaw_root/Note/` used only as template) could hold a **default** `identity.md` (and no user data). When a user has no custom identity for Note, Core could read that default. All **user** data (identity overrides, knowledge, output) must still live under `homeclaw_root/{user_id}/Note/`. So:
  - **One folder under homeclaw_root for preset “content” only** (read-only default identity/template): no leak, optional.
  - **One folder under homeclaw_root for all user data of that preset**: would leak; don’t do it.

**Recommendation:** Keep the current layout: **preset friends’ user-specific data stay under `homeclaw_root/{user_id}/{friend_id}/`** (e.g. `alice/Note/`, `bob/Note/`). Optionally add a separate **preset template** area (e.g. `homeclaw_root/presets/Note/`) for default identity/content only; that does not replace per-user folders.

## How friend folders are created today

- **Only at Core startup.** In `core/core.py`, after loading config:
  1. `Util().get_users()` is called (users come from **TinyDB** `database/users.json`, or from **config/user.yml** if DB is empty).
  2. For each user, the code builds **friends_by_user**: `{ user_id → [friend.name, ...] }` from each user’s `friends` list (e.g. HomeClaw, Sabrina).
  3. `ensure_user_sandbox_folders(homeclaw_root, user_ids, friends_by_user=friends_by_user)` is called (`base/workspace.py`).
  4. For each **(user_id, friend_id)** in that map, it creates:
     - `homeclaw_root/{user_id}/{friend_id}/` (friend root)
     - `homeclaw_root/{user_id}/{friend_id}/output/`
     - `homeclaw_root/{user_id}/{friend_id}/knowledge/`

So **friends’ folders exist only if** that user and that friend were in the users/friends data **at the last Core startup**. There is no other place that creates these directories.

## Two levels under one user

Under `homeclaw_root/{user_id}/` you have both:

| Level | Path | Purpose |
|--------|------|--------|
| **User** | `{user_id}/`, `{user_id}/knowledge/`, `{user_id}/output/`, … | The user’s own sandbox (documents, KB sync, outputs). |
| **Friend** | `{user_id}/{friend_id}/`, `{user_id}/{friend_id}/knowledge/`, `{user_id}/{friend_id}/output/` | Per-friend identity, KB, and output (e.g. Sabrina). |

- **User-level** `knowledge/` is for the **user’s** knowledge base (folder sync, RAG when talking to any friend can use it depending on design).
- **Friend-level** `{friend_id}/knowledge/` is for **that friend’s** knowledge (RAG scoped to that friend).

So “we put friends into the users” is correct: friends are **under** a user (`{user_id}/{friend_id}/`). The possible “mess” is: same names at two levels (e.g. `knowledge/` at user and at friend), and friend folders only created at startup.

## Where it gets messy

1. **Friend folders only at startup**  
   If you add a **user** via Config API (POST user), we call `ensure_user_sandbox_folders(root, [uid])` **without** `friends_by_user`, so that user gets only their **user-level** folders. Their **friend** subfolders (e.g. `{uid}/HomeClaw/`, `{uid}/Sabrina/`) are **not** created until the next Core startup.

2. **Adding a friend via Companion/API**  
   When you add a friend with `POST /api/me/friends` (or similar), we only update TinyDB/user data. We **do not** call `ensure_user_sandbox_folders` for that (user_id, friend_id). So the new friend’s folder (`{user_id}/{friend_id}/`, with `output/` and `knowledge/`) does **not** exist until the next Core restart.

3. **Two kinds of friends, same layout**  
   Friends can be **AI** (name + preset/identity) or **user-type** (another user in the same HomeClaw). Both use the same path layout: `{user_id}/{friend_id}/`. So “different friends” (AI vs user) are not messy in terms of folders—they’re the same—but the **source of the list** (user.yml vs TinyDB, and when we create folders) is what’s inconsistent.

4. **Single source of truth**  
   Users (and their friends) are loaded from **TinyDB** (`database/users.json`). If you still edit **user.yml** by hand, TinyDB wins after migration. So “friends” are whatever is in the user’s `friends` list in that store; folder creation only uses that at startup.

## What we did to reduce the mess

- **Friend folders when adding a friend (me_api)**  
  When you add an AI friend via `POST /api/me/friends`, Core now calls `ensure_friend_folders(homeclaw_root, user_id, friend_id)` so `{user_id}/{friend_id}/`, `.../output/`, and `.../knowledge/` exist immediately. No need to restart Core.

- **New user gets HomeClaw folder (config_api)**  
  When creating a user via Config API, we call `ensure_user_sandbox_folders(root, [uid], friends_by_user={uid: ["HomeClaw"]})` so the new user gets both user-level folders and the default friend (HomeClaw) folder in one go.

- **Startup still creates all**  
  At Core startup we still build `friends_by_user` from all users and their friends (TinyDB or user.yml) and create all user and friend folders. So any friends added by hand in config or DB get their folders on next restart.

## Further recommendations

- **User-type friends**  
  If you add a **user-type** friend (another user) via API, you could also call `ensure_friend_folders` for that (user_id, friend_name) so the folder exists without restart.

- **Keep naming as-is**  
  Using **knowledge** for both user and friend KB folders is already unified. No need to rename; the “mess” is **when** we create friend folders and **that** we have two levels (user vs friend) under the same `user_id`.

- **Document the layout**  
  In admin or user docs, state clearly: “Each user has their own folder `{user_id}/` with subfolders like `knowledge/`, `output/`. Each of their friends (e.g. HomeClaw, Sabrina) has a subfolder `{user_id}/{friend_name}/` with its own `knowledge/` and `output/`.” That should reduce confusion between “user” and “friend” folders.
