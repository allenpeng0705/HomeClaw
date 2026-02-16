# User profile: learn from the user and personalize (design discussion)

This doc is a **design discussion only**. No code changes yet. Goal: capture what we want to store, how it should be learned and updated, and how we use it to provide personal service — then decide implementation later.

---

## 1. What we want to store (examples)

Per-user information that can be **learned from chat** and **updated over time**:

| Category | Examples | Notes |
|----------|----------|--------|
| **Identity** | name, gender, preferred称呼 (e.g. 小张) | Often stated once, updated if wrong. |
| **Life events** | birthday, anniversary, important dates | Used for reminders, greetings, gifts. |
| **Personality / style** | character, tone preference (formal/casual), humor (yes/no) | Helps tailor reply style. |
| **Preferences** | favorite foods, drinks, cuisines; dietary restrictions; allergies | For recommendations, cooking, ordering. |
| **Interests** | hobbies, sports, books, music, travel preferences | For suggestions, small talk, gifts. |
| **Families** | family (spouse, kids, parents), close friends, pets (names, relations) | For context (“your wife”, “the kids”), reminders, greetings. |
| **Work / life** | job, timezone, typical schedule, important projects | For scheduling, context. |
| **Other** | anything the user mentions and we decide to remember | Open-ended. |

Important: the set of fields is **not fixed**. New attributes can appear (e.g. “my dog’s name is Max”), and existing ones can be **corrected** or **refined** (“actually my birthday is March 15, not March 10”).

---

## 2. Requirements (summary)

1. **Per-user:** Data is scoped by user (e.g. `user_id`, and optionally `app_id`). User A’s profile is independent of User B’s.
2. **Unstructured / flexible:** No single fixed schema. New keys can be created; values can be text, list, or structured (e.g. `families: [{name, relation}]`). Existing keys can be updated or removed.
3. **Learned from chat:** Information is extracted from normal conversation (and optionally from explicit “remember …” / “my X is Y”).
4. **Recorded and updated later:** User or assistant can add, correct, or update facts at any time (during chat or via a future “edit my profile” flow).
5. **Use for personalization:** Stored data is used to tailor replies, reminders, recommendations, and tone (e.g. use name, avoid allergens, mention interests).

---

## 3. Storage model (decided: Option A — one JSON file per user)

We need a store that supports **per-user** and **arbitrary keys + values**, with updates.

**Decision: Option A — one JSON file per user.**

- **Shape:** One JSON file per user, e.g. `profiles/{user_id}.json` (or under a configurable directory; `app_id` can be part of the path if multi-tenant). File content is a single JSON object.
- **Example content:** `{"name": "Zhang San", "birthday": "1990-03-15", "favorite_foods": ["spicy"], "families": [{"name": "Xiao Ming", "relation": "son"}]}`.
- **Updates:** To add or change a fact: read the file, parse JSON, merge in the new/updated keys (or remove keys for “forget”), write the file back. Implementation must support this read-modify-write flow so the profile is **always updatable**. Optional: atomic write (write to a temp file then rename) to avoid corruption on crash.
- **Testing:** For tests, the profile can be reset by simply deleting the user’s JSON file (or clearing its content).
- **Pros:** Simple; no DB required for profiles; easy to inspect and edit by hand; easy to load the whole profile for the prompt; new keys and nested structures are natural in JSON.
- **Cons:** Whole file read/write per update (acceptable for typical profile size and update frequency); no built-in history unless we add a separate log.

Other options (key-value rows, hybrid with history) can be considered later if we need per-key updates without full-file write or audit trail.

---

## 4. When and how we learn (sources of truth)

- **During chat (implicit):** User says “I’m Zhang San”, “my birthday is March 15”, “I don’t eat shellfish”, “my son is called Xiao Ming”. We need a way to **extract** these and **write** to the profile store. See **4.1 Extraction: LLM vs rules vs both** below.
- **Explicit “remember”:** User says “remember: my favorite restaurant is Y” or “add to my profile: …”. We treat as high-confidence and always write (LLM or rules can normalize key names).
- **Explicit update later:** User says “actually my birthday is March 10” or “remove my old job”. We **update** the existing key (or delete it). Same pipeline: extract intent (update/delete) + key + value, then apply to profile.
- **Add new things:** User says “we have a new dog, named Buddy”. We **create** a new key or extend a list (e.g. `pets: [{name: "Buddy", type: "dog"}]`). Schema stays flexible.

Important: we must decide **when** we run extraction (every message vs. only when user seems to state a fact) and **how** we avoid overwriting correct data with a wrong extraction (e.g. “I’m not Zhang San, I’m Li Si” → update name; “Zhang San said …” → do not set name to Zhang San). So we need a notion of **confidence** or **source** (user self-report vs. third-party mention) and possibly **conflict resolution** (prefer last correction, or ask user).

### 4.1 Extraction: LLM vs rules vs both (comparison)

Because the information comes from **chat**, we need to turn free-form messages into structured profile updates. Here are the options and a recommendation.

| Aspect | LLM-based extraction | Rules / patterns | Both (LLM + rules) |
|--------|----------------------|------------------|--------------------|
| **How it works** | After (or during) a user turn, call an LLM with a prompt like: “From this message, extract any facts the user stated about themselves (name, birthday, preferences, family, interests, etc.). Output JSON: { key: value } or list of updates. Ignore facts about other people.” Then merge the output into the profile. | Regex or simple patterns: “my name is X”, “I’m X”, “birthday is …”, “my [relation] is [name]”, “I don’t eat X”, “I’m allergic to X”. When a pattern matches, write that key-value to the profile. | Use rules for clear, high-confidence phrases (“my name is …”, “remember: …”); use LLM for the rest of the message or for ambiguous / long text. |
| **Pros** | Handles varied wording (“people call me Xiao Zhang”, “I was born on 15th March 1990”), new types of facts, and nuance (e.g. “I’m mostly vegetarian” → dietary preference). One model can also decide “this is about the user” vs “this is about someone else”. | No extra LLM call; fast and deterministic; easy to test; no risk of hallucinated keys. Good for very explicit phrases. | Combines reliability on obvious cases (rules) with coverage on the long tail (LLM). Rules can also catch “remember: …” and force a write. |
| **Cons** | Extra latency and cost; may occasionally hallucinate a key or mis-parse; need to guard against extracting “Zhang San” when user said “Zhang San said …” (about someone else). | Misses paraphrases and new kinds of facts; rigid; many rules to maintain for each language/style. | Slightly more moving parts; need a clear order (e.g. run rules first, then LLM on remainder). |
| **When to run** | Every user message, or only when a lightweight “does this look like profile info?” classifier says yes (to save cost). | On every user message (cheap). | Rules on every message; LLM when rules didn’t capture everything or when message is long/ambiguous. |

**Recommendation:** **Use both.**  
- **Rules** for clear, explicit forms: “my name is X”, “I’m X”, “remember: …”, “my birthday is …”, “I don’t eat X” / “I’m allergic to X”, “my [relation] is [name]”. These are high-confidence and don’t need an LLM.  
- **LLM** for the rest: paraphrased or indirect self-descriptions (“people usually call me …”, “I tend to avoid dairy”, “we have two kids, Ming and Mei”). The LLM can output structured updates (e.g. JSON) that we merge into the same JSON file.  
- Optionally: only run the LLM when the message is longer than a few words or when rules didn’t match, to reduce cost.  
- For “remember: …” and explicit corrections (“actually my birthday is …”), we can treat them as high-priority and always apply (rules or LLM).

---

## 5. How we use these data (personalization)

**Decision: support both usages.**

1. **Always-in-prompt (when profile exists):** When building the prompt for a user, load that user’s profile and append a block, e.g. “## About the user: name=…, birthday=…, favorite_foods=…, families=…, interests=…”. The model then:
   - Uses the user’s name and preferences in replies.
   - Avoids recommending shellfish if the user has an allergy.
   - Tailors tone (formal/casual) and content (hobbies, family) to the user.
2. **On demand via tools:** A tool or skill can **read** the profile (e.g. “get user’s birthday”, “get user’s dietary restrictions”) for reminders, gift suggestions, or recipe recommendations. So the model or a skill can request profile data when needed, and we inject that into context (or return it as tool result). This supports flows where profile is used only in certain turns.

Both can be active: we **always** inject a compact profile block for the current user when the profile file exists (so the model has context every time), **and** we provide a tool (or API) so that skills can explicitly read or update profile fields when needed.

- **Recorded events / TAM:** We can link reminders and events to the user (“remind me before my wife’s birthday”) and use “families” to resolve “my wife” and look up the date. So profile feeds into TAM and recorded events.
- **Memory (RAG) vs. profile:**  
  - **Profile:** Structured, short, “fact sheet” — name, birthday, preferences, families. Fast to load, easy to update by key.  
  - **Memory (RAG):** Unstructured, long-term recall of conversations and events. Profile is a **complement**: we use profile for “who is this user” and “what do they like”; we use RAG for “what did we talk about” and “what happened”. Both can be in the same system prompt (profile block + memory context).

---

## 6. Open points to align on

1. **Confidence / overwrite:** When we extract “name = X” from a message, do we always write, or only if “user said it about themselves” (and how do we detect that)? Do we support “this was wrong, revert”?
2. **Scope:** Profile key namespace: free-form (any string) or a suggested set (name, birthday, favorite_foods, …) that we extend over time? Both are possible with JSON.
3. **Privacy / retention:** Should the user be able to list, edit, or delete all stored profile fields (e.g. “what do you know about me?”, “forget my birthday”)? That implies a small “profile management” surface (tools or UI) and delete/update by key.
4. **Families and relations:** Store as free text (“wife: Li Hong, son: Xiao Ming”) or semi-structured list (`[{name, relation}]`) so we can use it for “remind me before [relation]’s birthday” and resolve [relation] to a name and then to a date (if we store their birthdays in profile or in recorded_events).

---

## 7. Summary (decisions so far)

- **Storage:** One JSON file per user (e.g. `profiles/{user_id}.json`). Read-modify-write for updates; for testing, delete the file to reset. No DB required for profiles.
- **What we store:** Per-user, flexible JSON for name, gender, birthday, character, favorite foods, interests, **families** (family members, close friends, pets), and any other learned facts. New keys can be added; existing ones updated or removed.
- **Extraction:** **Both** LLM and rules: rules for clear phrases (“my name is …”, “remember: …”, “my [relation] is [name]”); LLM for paraphrased or indirect self-descriptions. Explicit “remember” and corrections always applied.
- **Usage:** **Both** always-in-prompt and on-demand: always inject a compact profile block for the current user when the profile exists; also provide a tool (or API) so skills can read or update profile when needed. Profile is distinct from RAG memory (profile = who the user is; memory = what was said/done).
- **Next:** Resolve open points (confidence/overwrite, key namespace, privacy, families structure); then add automatic extraction (LLM or rules) if desired.

---

## 8. Implementation (done)

- **Storage:** `base/profile_store.py` — one JSON file per **system user id** under `database/profiles/` (or `profile.dir` in config). Filename is a safe version of the system user id. Read with `get_profile(system_user_id, base_dir)`, update with `update_profile(system_user_id, updates, remove_keys, base_dir)`. Atomic write (tmp then rename).
- **Config:** `config/core.yml` has a `profile:` section: `enabled: true`, `dir: ""` (empty = `database/profiles`). CoreMetadata has a `profile` dict field.
- **Prompt injection:** In `answer_from_memory`, when profile is enabled and we have a user id, we load the profile and append a block `## About the user` + formatted key-value text (max 2000 chars) to the system prompt. So the model always sees the current user’s profile when replying.
- **Tools (per-user, keyed by system user id from context):**
  - **profile_get** — get the current user’s profile (optional `keys` for a subset).
  - **profile_update** — merge key-value `updates` into the profile; optional `remove_keys` to forget. The model can call this when the user says “my name is …”, “remember I like …”, etc.
  - **profile_list** — list profile keys and a short preview (“what do you know about me?”).
- **Extraction:** Not automated yet. The model can use **profile_update** when it infers facts from chat. Automatic extraction (LLM or rules) can be added later.
- **Per-user:** All profile paths use the **system user id** (from `request.system_user_id` or user.yml `id`/`name`), so each user has their own sandbox.
