# Per-user API keys for keyed skills (design review)

This doc reviews the design: **store API keys for maton-api-gateway, x-api-1.0.0, meta-social-1.0.0, hootsuite-1.0.0 in user.yml (per user)**; use one config block per user; if not set, the skill cannot be used by that user; Companion app uses these keys when the backend runs the skill.

---

## 1. Design summary (proposal)

- **Where:** API keys live in **config/user.yml**, **per user**.
- **One special place:** One config section (e.g. `skill_api_keys` or `api_keys`) holds all four keys per user — not one literal “master key,” but one **place** so we don’t scatter keys across env or per-skill config.
- **Rule:** If a key is **not** set in user.yml for a user, that **skill cannot be used** by that user (either hidden from their skill list or error at run_skill).
- **Companion:** “Companion app will use the API keys in the skills directly” — meaning the **backend** (Core) uses the **current user’s** keys from user.yml when running the skill. Companion does not need to store raw keys; it sends the request with user context, and Core injects that user’s keys into the skill run.

---

## 2. Is this reasonable?

**Yes.** The design is consistent with multi-user HomeClaw and keeps keys in one place per user.

| Aspect | Assessment |
|--------|------------|
| **Per-user keys** | Correct. User A has their own Maton/X/Meta/Hootsuite accounts; User B has different ones. user.yml is the right place for identity and permissions; adding keyed-skill keys there keeps everything per-user. |
| **One config block** | Good. One section (e.g. `skill_api_keys`) with keys like `maton_api_key`, `x_access_token`, `meta_access_token`, `hootsuite_access_token` is clear, documentable, and easy for Companion/config UI to edit. |
| **Skill disabled if key not set** | Good. Avoids “unauthorized” at runtime and makes capability explicit: no key → user doesn’t see or can’t run that skill. |
| **Companion uses keys “in the skills”** | Good. Interpret as: when Companion (or any channel) triggers a request, Core resolves the **current user** and injects **that user’s** keys into the skill run (env or equivalent). Companion does not need to hold API keys; Core reads from user.yml. |

**Clarification:** “One special key” is best read as **one special config block** (one place in user.yml) for these keys, not a single secret that unlocks all four services (no such token exists).

---

## 3. Recommended shape in user.yml

**Option A — Keys inside each user (recommended)**

```yaml
# user.yml
users:
  - id: AllenPeng
    name: AllenPeng
    email: []
    im: ['matrix:@pengshilei:matrix.org']
    permissions: []
    # Optional: API keys for keyed skills (maton, x-api, meta-social, hootsuite). If missing, that skill is not available for this user.
    skill_api_keys:
      maton_api_key: ""       # MATON_API_KEY for maton-api-gateway-1.0.0
      x_access_token: ""     # X_ACCESS_TOKEN for x-api-1.0.0
      meta_access_token: ""  # META_ACCESS_TOKEN for meta-social-1.0.0
      hootsuite_access_token: ""  # HOOTSUITE_ACCESS_TOKEN for hootsuite-1.0.0
  - id: webchat_user
    name: WebChat User
    # no skill_api_keys → none of the four keyed skills available
```

- **Pros:** One place per user; easy to document (“add your keys under your user in user.yml”); Companion can show/edit “my keys” by user id.
- **Cons:** Requires extending the `User` dataclass and `User.from_yaml` / `to_yaml` to read and write `skill_api_keys` (and to preserve it when updating other fields via config API).

**Option B — Top-level keyed by user id**

```yaml
# user.yml
users: [ ... ]

# Optional; keyed by user id. If a user has no entry or a key is missing, that skill is unavailable.
skill_api_keys_by_user:
  AllenPeng:
    maton_api_key: ""
    x_access_token: ""
    meta_access_token: ""
    hootsuite_access_token: ""
  webchat_user: {}
```

- **Pros:** No change to `User` dataclass; additive key in the same file.
- **Cons:** Two places to look for “user config” (users[] vs skill_api_keys_by_user); config API that updates “user” must know to update this block too when adding/renaming users.

**Recommendation:** **Option A** (keys inside each user) so one user object holds identity, permissions, and keyed-skill keys. Use a single block name: **`skill_api_keys`** (one “special” section per user for these four keys).

---

## 4. Runtime behavior

1. **Resolve current user**  
   When handling a request (Companion, WebChat, channel), Core already has `system_user_id` (from user.yml allowlist). Use that for the rest.

2. **run_skill for a keyed skill**  
   When the model (or cron, etc.) calls `run_skill` for one of:
   - `maton-api-gateway-1.0.0`
   - `x-api-1.0.0`
   - `meta-social-1.0.0`
   - `hootsuite-1.0.0`  
   Core:
   - Looks up the **current user** (from ToolContext / request) in user.yml.
   - Reads that user’s `skill_api_keys` and the key for this skill (e.g. `maton_api_key` for maton-api-gateway).
   - If the key is missing or empty: return a clear error: “This skill requires an API key. Add it under your user in config/user.yml (skill_api_keys).” and do **not** run the script.
   - If the key is set: **inject** it into the environment of the skill run:
     - **Subprocess:** Add to `skill_env` (e.g. `MATON_API_KEY`, `X_ACCESS_TOKEN`, `META_ACCESS_TOKEN`, `HOOTSUITE_ACCESS_TOKEN`) before `create_subprocess_exec(..., env=skill_env)`.
     - **In-process:** Temporarily set `os.environ` for the duration of the script run, then restore (or pass an env dict into the in-process runner and have the script read from it if we ever add that).
   - Skill scripts **do not change**: they still read from env (and optionally skill config.yml). Env is populated from user.yml by Core.

3. **Skill availability (optional but recommended)**  
   When building the “Available skills” block for the prompt, Core can **filter** these four skills by current user:
   - If the user has no `skill_api_keys` or the relevant key is missing/empty, **omit** that skill from the list (or mark it as “not available — add key in user.yml”).
   - So “if not set in user.yml, the skill cannot be used” is enforced both at run_skill (error) and at prompt (skill hidden or disabled).

4. **Companion**  
   Companion sends requests with user context (e.g. user_id in session/auth). Core uses that to resolve the user and, when running a keyed skill, injects that user’s keys from user.yml. No need for Companion to store or send API keys; it “uses the API keys in the skills” only in the sense that the backend applies the current user’s keys when executing the skill.

---

## 5. Key names and env mapping

| Skill folder | Key in user.yml (`skill_api_keys`) | Env var injected (for script) |
|--------------|-------------------------------------|-------------------------------|
| maton-api-gateway-1.0.0 | `maton_api_key` | `MATON_API_KEY` |
| x-api-1.0.0 | `x_access_token` | `X_ACCESS_TOKEN` |
| meta-social-1.0.0 | `meta_access_token` | `META_ACCESS_TOKEN` |
| hootsuite-1.0.0 | `hootsuite_access_token` | `HOOTSUITE_ACCESS_TOKEN` |

Skill scripts keep reading from env (and optionally from skill config.yml). For multi-user, **env wins** and is set from user.yml; for single-user / dev, existing env or skill config.yml can still be used if we keep a fallback: **prefer user’s key from user.yml; if none, fall back to current env or skill config.yml** (backward compatible).

---

## 6. Backward compatibility

- **Single-user / no user context:** If there is no `system_user_id` (e.g. cron without user, or legacy path), fall back to **current env** (and then skill config.yml) so existing deployments keep working.
- **Existing env / config.yml:** If we implement “prefer user.yml for current user, else env, else skill config.yml,” then existing users who set keys only in env or in skill config still work until they add keys to user.yml.

---

## 7. Summary

- **Store** per-user API keys for maton-api-gateway, x-api-1.0.0, meta-social-1.0.0, hootsuite-1.0.0 in **user.yml**, in one section per user: **`skill_api_keys`** (one “special” block for these four keys).
- **If not set** for a user, that skill **cannot be used** by that user (error at run_skill and optionally hidden from their skill list).
- **Companion** does not store keys; the **backend** uses the current user’s keys from user.yml when running the skill (“use the API keys in the skills directly” = Core injects them).
- **Implementation:** Extend User with optional `skill_api_keys`; in run_skill for these four skills, resolve current user → get key → inject into env (subprocess/in-process); optionally filter skill list by key presence; keep fallback to env/config for single-user.

This design is **reasonable** and fits multi-user HomeClaw and Companion well.

---

## 8. Companion without user (implemented)

When Companion is used **without combining with any user** (e.g. user_id is "system" or "companion"), Core does **not** inject keys from user.yml. The skill runs with **API keys in the skills directly** — i.e. the skill's own `config.yml` and environment variables (same as single-tenant / dev). So the device or server that runs Core can set `MATON_API_KEY`, `X_ACCESS_TOKEN`, etc. in env or in each skill's config.yml, and Companion-without-user will use those when invoking keyed skills.
