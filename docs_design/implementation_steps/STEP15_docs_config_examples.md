# Step 15: Docs and config examples — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) implementation step 15.

**Goal:** Update README and config examples for user.yml (friends, identity). Update MultiUserSupport.md to describe the new model. Add a short Migration section. No code changes; documentation only.

---

## 1. What was implemented

### 1.1 README.md

- **Channels and multi-user:** Sentence updated to mention optional **username** / **password** (Companion login) and **friends** list with optional **identity** file per friend. Link to MultiUserSupport retained.

### 1.2 config/examples/user.yml.example

- New minimal example showing:
  - `id`, `name`
  - Optional `username`, `password` for Companion login
  - `friends` with HomeClaw first, then one friend (Sabrina) with `relation`, `who`, and `identity: identity.md`
- Comment at top explains channels vs Companion and that friends list has HomeClaw first.

### 1.3 docs_design/MultiUserSupport.md

- **Summary:** Updated to describe friends list, friend_id, TAM one-shot and last-channel per user, Companion login (username/password, no full user list). Flow now includes `request.friend_id` and (user_id, friend_id) storage.
- **§1 user.yml format:** Replaced minimal example with full example including `username`, `password`, `friends` (HomeClaw + Sabrina with relation, who, identity). Added bullet on friends list and link to STEP6 and config/examples/friend_identity.md.
- **§2:** Retitled to "What is per-user and per-(user_id, friend_id)". Table updated: chat/sessions with friend_id; RAG/KB/profile/AGENT_MEMORY/daily/TAM one-shot/last channel/file workspace and tool context all described with per-user and per-friend scoping.
- **§4:** Replaced "What is not per-user today" with "Last channel and TAM (per-user / per-friend)": last channel keyed by system_user_id; TAM one-shot has user_id and friend_id; AGENT_MEMORY/daily paths per (user_id, friend_id).
- **§5 Summary table:** Columns "Per-user / per-friend?"; rows updated for allowlist (friends, identity), chat, sessions, RAG, KB, last channel, TAM one-shot, AGENT_MEMORY/daily, file sandbox. Closing paragraph updated.
- **§6 Migration:** New section: existing user.yml without friends gets default [HomeClaw]; adding friends (format, HomeClaw first); Companion login (username/password optional).
- **§7:** Renumbered from former §6 (System user id).

### 1.4 Friend identity example

- **config/examples/friend_identity.md** already exists; MultiUserSupport links to it and to STEP6 for identity file semantics.

---

## 2. Files touched

| File | Change |
|------|--------|
| **README.md** | user.yml sentence: added username/password, friends, identity. |
| **config/examples/user.yml.example** | New minimal user.yml example (friends, identity). |
| **docs_design/MultiUserSupport.md** | Summary, §1 format, §2 table, §4 (last channel & TAM), §5 summary table, new §6 Migration, §7 renumber. |

---

## 3. Review

- **Logic:** Docs and example align with UserFriendsModelFullDesign and Steps 1–14 (user.yml schema, friends, identity, per (user_id, friend_id) data, Companion login, path resolution). ✓
- **Migration:** Clear guidance for existing config (default friends) and adding friends / Companion login. ✓

**Step 15 is complete.** Implementation steps 1–15 for the user/friends model are done.
