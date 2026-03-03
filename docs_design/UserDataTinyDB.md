# User data: migrate from user.yml to TinyDB

## Why TinyDB

- **Document-oriented**: One document per user (like current YAML structure). Easy to add fields (e.g. avatar path, preferences) without schema migrations.
- **Schema-flexible**: No fixed columns; add/remove keys per document. Fits evolving user/friend model.
- **Lightweight**: Single JSON file on disk, no server, [pure Python](https://github.com/msiemens/tinydb). Good for "not much data."
- **Simple API**: `insert`, `search`, `update`, `remove`, `Query()`. No SQL or ORM.

SQLite was considered but is relational and heavier for this use case; we only need a small users + friends store.

## Where to store

- **TinyDB file**: `data_path()/users.json` (e.g. `database/users.json`). Mutable data lives under `data_path()`, not in `config/`.
- **user.yml**: Can remain in `config/` as optional **read-only fallback** or **one-time migration source**. After migration, Core uses TinyDB only for reads/writes.

## What stays the same

- **User and Friend dataclasses** (base/base.py): Rest of the codebase keeps using `List[User]`, `User`, `Friend`. No change to Core, channels, Companion auth, config API, or me_api.
- **Util.get_users()** still returns `List[User]`.
- **Util.save_users(users)** still accepts `List[User]` and persists them.

So we add a **storage layer** (TinyDB) behind the same interface; the only change is where the bytes go (users.json instead of user.yml).

## Implementation outline

1. **Add dependency**: `tinydb>=4.8.0` in requirements.txt.

2. **User ↔ document conversion** (base/base.py or base/user_store.py):
   - `user_to_doc(user: User) -> dict`: One dict per user (same shape as current YAML user entry: name, id, email, im, phone, permissions, username, password, skill_api_keys, type, who, friends as list of dicts). Reuse `User._friends_to_dict_list`.
   - `User.from_doc(doc: dict) -> User`: Build User from dict; reuse `User._parse_friends(doc.get('friends'))`. Same logic as current YAML parsing, but from a dict.

3. **User store module** (e.g. base/user_store.py):
   - Open TinyDB at `Util().data_path()/users.json`, table `"users"`.
   - `get_all() -> List[User]`: Get all docs, convert each with `User.from_doc(doc)`. If table is empty and `config/user.yml` exists, run **one-time migration**: load users from user.yml via `User.from_yaml`, convert to docs, insert into TinyDB, then return users.
   - `save_all(users: List[User])`: Convert each user to doc with `user_to_doc`, truncate table, `insert_multiple(docs)`. Never raises: wrap in try/except, log on failure.

4. **Util** (base/util.py):
   - `get_users()`: Call `user_store.get_all()` instead of `User.from_yaml(path)`. Keep in-memory cache (`self.users`) and validation (`validate_no_overlapping_channel_ids`) as today.
   - `save_users(users)`: Call `user_store.save_all(users)` instead of `User.to_yaml(users, path)`.

5. **Config watcher**: Today a watcher reloads on `user.yml` change. Options: (a) Watch `database/users.json` and call `Util().get_users()` (and clear cache) on change; (b) Remove user-file watch and rely on in-process updates. Prefer (b) for simplicity: only this process writes users; no external edits to users.json expected.

6. **Backward compatibility**:
   - **Migration**: First time TinyDB is used, if `users.json` is missing or empty and `config/user.yml` exists, load from user.yml and fill TinyDB. After that, use TinyDB only.
   - **Optional export**: We can add "Export to user.yml" in Portal/settings that writes current users to config/user.yml for backup. Not required for MVP.

## File layout

```
database/
  users.json          # TinyDB (user documents)
  avatars/
  ...
config/
  user.yml            # Optional: keep as backup or migration source; Core no longer writes it by default
  core.yml
  ...
```

## Risks and mitigations

- **Corruption**: TinyDB writes JSON atomically (one file). On crash, last write may be partial. Mitigation: optional backup of users.json before write, or use TinyDB middleware for safer writes if needed later.
- **Concurrency**: Single Core process = single writer. If we ever run multiple workers, we’d need a locking strategy or move to a shared DB; for now, one process is enough.
- **Validation**: Keep `User.validate_no_overlapping_channel_ids(users)` on load so we don’t regress.

## Summary

Use TinyDB as the single source of truth for user (and friend) data under `data_path()/users.json`, with lazy one-time migration from user.yml. Keep the existing User/Friend model and Util API; only the persistence layer switches from YAML to TinyDB.
