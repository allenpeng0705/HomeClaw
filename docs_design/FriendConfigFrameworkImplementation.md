# Friend config framework: detailed design and step-by-step implementation

**Status:** Design + implementation plan. Implements the configurable per-friend behaviour described in `SystemFriendReminderDesign.md` (§10–10.4).

**Step 1 done:** Friend.preset added; config/friend_presets.yml and base/friend_presets.py (loader + TOOL_PRESETS); User parse/serialize preset; tests in tests/test_friend_presets.py (9 tests, all passing). No behaviour change in llm_loop yet.

**Step 2 done:** In core/llm_loop.py, resolve _current_friend.preset and filter tools by get_tool_names_for_preset(preset_name). When preset is set, only allowed tools are passed to the LLM; when not set, behaviour unchanged. Skip removing route_to_tam/route_to_plugin when filtered by preset. Test test_filter_tools_by_preset_logic added (10 tests passing).

**Step 3 done:** Filter skills and plugins by preset. When preset config has "skills" as a list (including []), skills_list is restricted to those folder/name in the list; when "plugins" as a list (including []), plugin_list is restricted to those ids. Reminder/Note/Finder (skills: [], plugins: []) get no skills and no plugins.

**Step 4 done:** Memory sources and system_prompt from preset. Resolve memory_sources list: inject agent_memory only if "agent_memory" or "md" in list; daily_memory only if "daily_memory" or "md"; Cognee (relevant_memories) only if "cognee". Note with memory_sources: [cognee] gets only Cognee, no agent/daily. Preset system_prompt (when set) is appended as "## Friend assistant" at end of system parts.

**Step 5 done:** model_routing and save_policy. When preset has model_routing: local_only and Core is in cloud-only mode, return early with a message that this friend requires local/mix mode. In mix mode with local_only, force effective_llm_name to main_llm_local for this friend. When preset has save_policy: full, append "In this conversation the user allows saving any content; no privacy restrictions." to system_parts.

**Step 6 done:** AllenPeng’s friends in `config/user.yml` include Reminder, Note, Finder with presets. Docs: `docs/companion-app.md` has a “Friends and presets” section describing how to add/remove friends (edit user.yml; use `preset: <name>` for system presets).

**Step 7 (review) done:** Logic, stability, and docs reviewed. All preset-related code paths are wrapped in try/except or use safe getattr/None checks; missing or invalid YAML/preset returns safe defaults; no code path raises uncaught. Unit tests: 12 tests in `tests/test_friend_presets.py` (all passing). See §5 Stability and robustness.

**Goal:** Make **limited tools/skills/plugins**, **optimized history**, **model routing**, **save policy**, and **memory sources** **configurable per friend**. Use "Reminder", "Note", and "Finder" as examples for user **AllenPeng**. Friends can be **added and removed easily** (via user.yml).

---

## 1. Overview

1. **Per-friend config** — When the user talks to a friend that has a config (or preset), Core uses it when building context: only inject allowed tools/skills/plugins, apply memory/history policy, optional model_routing and save_policy, and optional system_prompt.
2. **Presets** — Named presets (e.g. `reminder`, `note`, `finder`) define the set of tools, skills, plugins, memory_sources, model_routing, save_policy, system_prompt. A friend in user.yml can reference a preset by name (e.g. `preset: reminder`).
3. **Add/remove easily** — In user.yml, each user's `friends` list is a normal YAML list. Add a friend with `name: Reminder` and `preset: reminder`; remove by deleting that entry. No code change required.
4. **Example user** — AllenPeng: add friends Reminder, Note, Finder (with presets); they appear in GET /api/me/friends and in the Companion app; when the user chats with Reminder, Core applies the reminder preset (limited tools, etc.).

---

## 2. Data model

### 2.1 Friend (base/base.py)

- **Current:** `Friend(name, relation, who, identity)`.
- **Add (optional):** `preset: Optional[str] = None` — if set, e.g. `"reminder"`, Core looks up the preset and applies it when building context for this friend. If not set, behaviour is unchanged (full tools/skills/plugins as today).
- **Alternative:** instead of `preset`, allow inline `friend_config: Dict[str, Any]` (tools_preset, skills, plugins, memory_sources, model_routing, save_policy, system_prompt). For simplicity, **Step 1** uses **preset only**; inline config can be added later.

### 2.2 Friend preset (new)

A preset is a named config with:

| Key | Type | Meaning |
|-----|------|--------|
| `tools_preset` | str or list[str] | Single preset name (e.g. `reminder`) or **array** of preset names (e.g. `[reminder, finder]`) for union of tool sets. If absent or "all", use all tools (current behaviour). |
| `skills` | list[str] or "all" | **Array** of skill folder names (multiple allowed), or "all". Default "all". |
| `plugins` | list[str] or "all" | **Array** of plugin ids (multiple allowed), or "all". Default "all". |
| `memory_sources` | list[str] | e.g. `[cognee]`, `[cognee, agent_memory, daily_memory]`. If absent, use current behaviour (all). "md" = agent_memory + daily_memory; "cognee" = RAG/Cognee only. |
| `history` | str or dict | "full" (default) or "optimized" (e.g. last N turns only). Optional. |
| `model_routing` | str | "any" (default), "local_only", "cloud_only". When "local_only", Core does not use cloud for this friend; if only cloud is available, return a message that this friend requires local. |
| `save_policy` | str | "default" or "full". When "full", inject a line so the LLM knows the user allows saving any content; no privacy restriction. |
| `system_prompt` | str | Optional override: short prompt for this friend (e.g. "You are the Reminder assistant. You only schedule and list reminders. Use only the provided tools."). |

Presets are **defined in config** (e.g. `config/friend_presets.yml` or a section in `config/core.yml`). Core loads them at startup and resolves `preset` by name when handling a request.

### 2.3 Where presets live

- **Option A:** `config/friend_presets.yml` — top-level key `presets:`, then map of name → config. Easy to edit and version.
- **Option B:** `config/core.yml` — new section `friend_presets: { reminder: {...}, note: {...}, finder: {...} }`. Single file.
- **Recommendation:** **Option A** (`config/friend_presets.yml`) so friend presets are separate and can be added/removed without touching core.yml.

---

## 3. Config examples

### 3.1 config/friend_presets.yml (new file)

```yaml
# Friend presets: named configs for limited context per friend.
# Reference from user.yml with preset: <name> (e.g. preset: reminder).
# Omitted keys = use default (same as current behaviour).

presets:
  reminder:
    tools_preset: reminder   # only cron/reminder tools (see tools registry or constant)
    skills: []              # no skills
    plugins: []             # no plugins (or list TAM-related if any)
    memory_sources: [cognee, agent_memory, daily_memory]  # or [cognee] if we want minimal
    history: full
    model_routing: any
    save_policy: default
    system_prompt: "You are the Reminder assistant. You only schedule and list reminders. Use only the provided tools."

  note:
    tools_preset: note      # note-related tools (append_agent_memory, file_write, document_read, etc.)
    skills: []              # or list note-related skills
    plugins: []
    memory_sources: [cognee]  # only Cognee/RAG; no MD (agent_memory, daily_memory)
    history: optimized      # e.g. last N turns
    model_routing: local_only
    save_policy: full
    system_prompt: "You are the Note assistant. The user allows saving any content here; no privacy restrictions. Use only the provided tools and Cognee memory."

  finder:
    tools_preset: finder    # file_find, folder_list, document_read, file_read, file_write, etc.
    skills: []
    plugins: []
    memory_sources: [cognee]
    history: optimized
    model_routing: any
    save_policy: default
    system_prompt: "You are the Finder assistant. You search and handle files. Use only the provided tools."
```

### 3.2 Tool preset definitions

We need a **mapping from preset name to list of tool names**. Options:

- **In friend_presets.yml:** under each preset, `tools: [remind_me, list_reminders, ...]` (explicit list) **or** `tools_preset: reminder` and a separate **tool preset registry** in code (e.g. `TOOL_PRESETS = {"reminder": ["remind_me", "list_reminders", "record_date", "cron_schedule", "route_to_tam"], "note": [...], "finder": ["file_find", "folder_list", "document_read", "file_read", "file_write", ...]}`). For **Step 1** we can define `TOOL_PRESETS` in code (one place, easy to test); later move to YAML if desired.
- **Recommendation:** `tools_preset` in YAML + `TOOL_PRESETS` (or similar) in code so we don’t duplicate long lists in YAML. If a preset has `tools_preset: reminder`, Core resolves the list from the registry.

### 3.3 user.yml — AllenPeng with Reminder, Note, Finder

```yaml
users:
  - id: AllenPeng
    name: AllenPeng
    username: pengshilei
    password: "123456"
    email: []
    im: ['matrix:@pengshilei:matrix.org']
    phone: []
    permissions: []
    friends:
      - name: HomeClaw
      - name: Sabrina
        relation: girlfriend
        who: { ... }
      - name: Gary
        relation: [friend]
        who: { ... }
      - name: Reminder
        preset: reminder
      - name: Note
        preset: note
      - name: Finder
        preset: finder
```

Removing a system friend: delete the corresponding `- name: Reminder` / `Note` / `Finder` block. Adding: add a new `- name: X; preset: x` (and define preset `x` in friend_presets.yml if new).

---

## 4. Implementation steps (with review, summary, tests)

Each step ends with: **Review** (logic correct, stable, no crash), **Summary** (what changed), **Tests** (if needed), then move to next step.

---

### Step 1: Schema, preset loading, and Friend.preset

**Scope:**

1. Add `preset: Optional[str] = None` to `Friend` in `base/base.py`.
2. In `User._parse_friends`, read `preset` from YAML for each friend (optional key).
3. In `User._friends_to_dict_list` and any serialization, include `preset` when present (so config round-trip preserves it).
4. Create `config/friend_presets.yml` with presets `reminder`, `note`, `finder` (as in §3.1). Define a loader (e.g. `base/friend_presets.py` or in `base/util.py`) that returns `Dict[str, Dict[str, Any]]` (preset name → config). Load from `config/friend_presets.yml`; if file missing or invalid, return `{}`.
5. Define tool preset registry in code: e.g. `base/friend_presets.py` or `core/friend_config.py` with `TOOL_PRESETS = {"reminder": ["remind_me", "list_reminders", "record_date", "cron_schedule", "route_to_tam"], "note": [...], "finder": ["file_find", "folder_list", "document_read", "file_read", "file_write", ...]}`. Use exact tool names from the tool registry. Document that adding a new preset requires adding the list here (or later in YAML).

**Deliverables:**

- `base/base.py`: `Friend` has `preset`.
- `User._parse_friends`: parse `preset`; `_friends_to_dict_list`: emit `preset`.
- `config/friend_presets.yml`: new file with reminder, note, finder.
- `base/friend_presets.py` (or equivalent): `load_friend_presets() -> Dict[str, Dict]`, `get_tool_names_for_preset(preset_name: str) -> Optional[List[str]]` (returns None if preset missing or tools_preset not defined; otherwise list of tool names).
- No behaviour change in llm_loop yet; only loading and data model.

**Review:** Logic correct; no crash if YAML missing or malformed; Friend serialization round-trip.

**Summary:** Document: "Step 1: Friend.preset added; friend_presets.yml and loader; tool preset registry. No context behaviour change."

**Tests:** Unit test: `User._parse_friends` with a friend that has `preset: reminder`; assert friend.preset == "reminder". Unit test: `load_friend_presets()` with missing file returns `{}`. Unit test: `get_tool_names_for_preset("reminder")` returns expected list.

---

### Step 2: Resolve friend config in LLM loop and filter tools

**Scope:**

1. In `core/llm_loop.py`, before building the tool list: get `request.friend_id` and the current user’s friend list; find the `Friend` with matching `name` (case-insensitive). If that friend has `preset` set, load preset config via `load_friend_presets()` and get `tools_preset`; resolve tool names with `get_tool_names_for_preset(preset_name)`.
2. If we have a list of allowed tool names for this friend, filter `registry.get_openai_tools()` to only include tools whose name is in that list. Otherwise use all tools (current behaviour).
3. Pass the (possibly filtered) tool list into the rest of the loop as today.

**Deliverables:**

- `core/llm_loop.py`: resolve friend preset; filter tools by preset when preset is set and tool list is defined.
- No change to skills/plugins/memory yet.

**Review:** When `friend_id=Reminder` and Reminder has `preset: reminder`, only reminder tools are available. When `friend_id=Sabrina` (no preset), all tools as today. No crash when preset file missing or preset name typo (fallback to all tools).

**Summary:** "Step 2: In llm_loop, resolve friend preset and filter tools by preset. Reminder friend gets only reminder tools."

**Tests:** Integration test or manual: send inbound with `friend_id=Reminder` for user AllenPeng; verify in logs or response that only reminder tools are in the list. Unit test: helper that, given preset name, returns filtered tool list from a mock registry.

---

### Step 3: Filter skills and plugins by preset

**Scope:**

1. In preset config, we have `skills: []` or `skills: [list]` and `plugins: []` or `plugins: [list]`. If preset is set and `skills` is a list (possibly empty), filter `skills_list` in llm_loop to only include skills whose folder/name is in that list. If `skills` is "all" or absent, keep current behaviour (all skills). Same for `plugins`: filter `plugin_list` to only include plugins whose id is in the list when preset specifies a list.
2. When preset has `skills: []` or `plugins: []`, inject no skills / no plugins for that friend.

**Deliverables:**

- `core/llm_loop.py`: after building skills_list and plugin_list, if friend has preset with `skills` / `plugins` defined, filter to allowed set (or empty).

**Review:** Reminder with `skills: []`, `plugins: []` gets no skills and no plugins. Other friends unchanged.

**Summary:** "Step 3: Filter skills and plugins by preset. Reminder/Note/Finder get only allowed skills/plugins (or none)."

**Tests:** As in Step 2, verify for Reminder that skills and plugins blocks are empty or minimal.

---

### Step 4: Memory sources and history policy

**Scope:**

1. When preset has `memory_sources: [cognee]`, skip injecting agent_memory and daily_memory for this request; only inject Cognee/RAG. When `memory_sources` includes `agent_memory` and `daily_memory` (or "md"), keep current behaviour. When `memory_sources` is absent, keep current behaviour.
2. When preset has `history: optimized`, optionally limit chat history to last N turns (e.g. 10) for this friend. (If complex, defer to a later step and document.)
3. When preset has `system_prompt`, append (or override a section) with that string so the LLM sees it (e.g. "You are the Reminder assistant...").

**Deliverables:**

- `core/llm_loop.py`: if friend preset has `memory_sources`, skip or include agent_memory/daily_memory accordingly; if preset has `system_prompt`, inject it (e.g. at end of system parts or in a dedicated section).
- Optional: `history: optimized` → limit history to last N turns.

**Review:** Note friend (memory_sources: [cognee]) does not get agent_memory/daily_memory. Reminder gets its short system_prompt. No crash when keys missing.

**Summary:** "Step 4: Apply memory_sources (Cognee-only for Note) and system_prompt from preset. Optional history policy."

**Tests:** For Note, verify no agent_memory/daily_memory in system prompt; for Reminder, verify custom system_prompt appears.

---

### Step 5: model_routing and save_policy ✓

**Scope:**

1. When preset has `model_routing: local_only`, before calling the LLM (or at the start of the request): if Core is in cloud-only mode (no local model), return a polite message that this friend requires the local model and do not call the LLM. If mix mode and local is available, prefer local for this friend (or keep current mix behaviour and only enforce "no cloud-only").
2. When preset has `save_policy: full`, append to system prompt a line like: "In this conversation the user allows saving any content; no privacy restrictions."

**Deliverables:**

- `core/llm_loop.py` (or core.py): when preset has `model_routing: local_only`, check effective mode; if cloud-only, return early with message. When `save_policy: full`, inject the line into system prompt.

**Review:** Note (local_only) in cloud-only mode gets a clear message; no LLM call. Note with save_policy full gets the privacy line.

**Summary:** "Step 5: model_routing (local_only) and save_policy (full) applied from preset."

**Tests:** When only cloud is configured and user talks to Note, expect message that Note requires local. When save_policy full, expect the line in system content.

---

### Step 6: AllenPeng config and API ✓

**Scope:**

1. Add to `config/user.yml` for user AllenPeng the three friends: Reminder (preset: reminder), Note (preset: note), Finder (preset: finder). Ensure `User.from_yaml` and `/api/me/friends` return them so the Companion app shows them.
2. Document in README or docs: how to add/remove these friends (edit user.yml; add or delete the friend entry with `preset: ...`). No code change needed to add/remove.

**Deliverables:**

- `config/user.yml`: AllenPeng’s friends include Reminder, Note, Finder with presets.
- Short doc (e.g. in `docs/companion-app.md` or `docs_design/FriendConfigFrameworkImplementation.md`): "Adding/removing system friends: edit user.yml; add or remove the friend entry; use preset: <name> to apply a preset."

**Review:** GET /api/me/friends for AllenPeng returns Reminder, Note, Finder. Companion shows them. Removing one from user.yml and restarting removes it from the list.

**Summary:** "Step 6: AllenPeng has Reminder, Note, Finder in user.yml; documented add/remove."

**Tests:** API test: login as AllenPeng, GET /api/me/friends, assert response contains names Reminder, Note, Finder.

---

### Step 7: Review and tests (full flow) ✓

**Scope:**

1. Full regression: default friends (no preset) still get full tools/skills/plugins and unchanged behaviour.
2. Reminder: only reminder tools, no skills/plugins, custom system prompt; scheduling works.
3. Note: Cognee only, local_only, save_policy full, note tools; add a note and verify.
4. Finder: finder tools only; run a file search and verify.
5. Document final tool lists for reminder, note, finder in `docs_design/FriendConfigFrameworkImplementation.md` or in code comments so future changes are consistent.

**Deliverables:**

- Test plan and results (manual or automated).
- Update design doc with any corrections and "Implementation status: Step 7 done."

---

## 5. Stability and robustness (never crash Core)

All friend-preset code is written so that **Core never crashes** due to preset logic:

- **base/friend_presets.py:** `load_friend_presets()` returns `{}` on missing file, invalid YAML, or missing `presets` key; never raises. `get_tool_names_for_preset` / `get_tool_names_for_preset_value` / `get_friend_preset_config` return `None` or empty list for unknown or invalid input; no exceptions.
- **base/base.py:** `_parse_friends` and `_friends_to_dict_list` are documented "Never raises"; malformed or missing `preset` is ignored or defaulted; exceptions inside the loop are caught and the entry is skipped.
- **core/llm_loop.py:** Every use of `_current_friend`, `preset_cfg`, and preset-based filtering (tools, skills, plugins, memory_sources, model_routing, save_policy, system_prompt) is inside a `try/except` that logs and continues; on exception, behaviour falls back to default (full tools/skills/plugins/memory, no preset overrides).
- **core/routes/companion_auth.py:** `_user_to_friends_list` is documented "Never raises"; uses `getattr(..., None)` for `preset`; on exception returns a safe default list including HomeClaw.

No preset or user.yml preset typo (e.g. `preset: unknown`) can crash Core; at worst the friend gets default (full) context.

---

## 6. File and code touch points

| Item | File(s) |
|------|--------|
| Friend.preset, parse/serialize | base/base.py |
| Preset loader, tool preset registry | base/friend_presets.py (or core/friend_config.py) |
| Preset config | config/friend_presets.yml |
| Resolve preset, filter tools/skills/plugins, memory, routing, save_policy, system_prompt | core/llm_loop.py |
| Optional: local_only check | core/llm_loop.py or core/core.py |
| User config example | config/user.yml |
| Docs | docs_design/FriendConfigFrameworkImplementation.md, docs/companion-app.md (or README) |
| Tests | tests/test_friend_presets.py, tests/test_friend_config_integration.py (or existing test files) |

---

## 7. Tool names reference (for TOOL_PRESETS in code)

Use the exact names from the tool registry. Suggested lists (verify against `tools/builtin.py` and any plugin-registered tools):

- **reminder:** `remind_me`, `list_reminders`, `record_date`, `list_recorded_dates`, `cron_schedule`, `route_to_tam` (and any other TAM/cron tools if present).
- **note:** `append_agent_memory`, `append_daily_memory`, `document_read`, `file_read`, `file_write`, `folder_list`, `file_find`, `save_result_page`, `get_file_view_link` (note-taking and file save; no routing/sessions).
- **finder:** `file_find`, `folder_list`, `document_read`, `file_read`, `file_write`, `get_file_view_link` (search and file handling only).

Implement Step 1 by resolving actual tool names from `get_tool_registry().list_tools()` and filtering by name; keep TOOL_PRESETS as the allowed-name list per preset so names stay in sync with the registry.

---

## 8. Summary

- **Framework:** Per-friend config via optional `preset` on Friend; presets defined in `config/friend_presets.yml`; tool preset names resolved from a registry in code. Reminder, Note, Finder are presets; they can be assigned to any friend (e.g. Reminder, Note, Finder) in any user’s friends list.
- **Add/remove:** Edit user.yml; add or remove friend entries with `name` and `preset`. No code change.
- **Steps:** 1) Schema + preset load + tool registry; 2) Filter tools; 3) Filter skills/plugins; 4) Memory + system_prompt; 5) model_routing + save_policy; 6) AllenPeng + API + docs; 7) Full review and tests. After each step: review, summary, tests, then next step.
