# Portal Step 2: YAML merge layer (llm, memory_kb, skills_and_plugins, friend_presets) — done

**Design ref:** [CorePortalDesign.md](../CorePortalDesign.md), [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 1.1.

**Goal:** One place to load/save the four config files (llm, memory_kb, skills_and_plugins, friend_presets) using ruamel so comments and key order are preserved. Only whitelisted keys are merged; never full overwrite with safe_dump.

---

## 1. What was implemented

### 1.1 `portal/yaml_config.py`

- **`load_yml_preserving(path: str) -> dict | None`** — Loads YAML with ruamel; returns dict or None on error. Never raises.
- **`update_yml_preserving(path, updates, whitelist=None) -> bool`** — Loads file with ruamel, merges only `updates` (optionally filtered by `whitelist`), writes with ruamel; atomic write (.tmp + replace). If file exists and load failed, skips write and returns False. Fallback: PyYAML load + merge + safe_dump when ruamel fails (no comment preservation in fallback). Never raises.
- **Whitelists:** `WHITELIST_LLM`, `WHITELIST_MEMORY_KB`, `WHITELIST_SKILLS_PLUGINS`, `WHITELIST_FRIEND_PRESETS` — top-level keys the Portal is allowed to merge. Keys in `updates` that are not in the whitelist are ignored.

### 1.2 Whitelist contents (summary)

- **llm.yml:** main_llm, embedding_llm, local_models, cloud_models, main_llm_mode, main_llm_local, main_llm_cloud, main_llm_language, embedding_host, embedding_port, main_llm_host, main_llm_port, hybrid_router.
- **memory_kb.yml:** use_memory, memory_backend, session, profile, knowledge_base, database, cognee, agent_memory_*, daily_memory_*, memory_summarization, vectorDB, graphDB, etc.
- **skills_and_plugins.yml:** skills_*, plugins_*, system_plugins_*, tools (all known top-level keys).
- **friend_presets.yml:** presets.

### 1.3 Stability

- `load_yml_preserving`: returns None on any exception; no raise.
- `update_yml_preserving`: returns False on write failure; skips write when file exists but could not be loaded (avoids corrupting file). Fallback path uses same skip-write guard.

---

## 2. Files touched

| File | Change |
|------|--------|
| **portal/yaml_config.py** | New: load/update + whitelists. |
| **tests/test_portal_yaml_config.py** | New: 7 tests (load missing, load returns dict, update creates file, update preserves comment, whitelist filters, empty updates, load real config no crash). |
| **docs_design/implementation_steps/Portal_Step2_yaml_layer.md** | New (this file). |

---

## 3. Tests

```bash
pytest tests/test_portal_yaml_config.py -v
```

- **test_load_yml_preserving_missing_file_returns_none** — Missing path → None.
- **test_load_yml_preserving_returns_dict** — Temp file with comment + key → dict.
- **test_update_yml_preserving_creates_file_if_missing** — Update to missing file creates it.
- **test_update_yml_preserving_merges_and_preserves_comment** — Merge main_llm; reload and assert value + comment still in raw file.
- **test_update_yml_preserving_whitelist_ignores_unknown_keys** — unknown_key in updates not in whitelist → not written.
- **test_update_yml_preserving_empty_updates_returns_true** — Empty updates or all filtered out → True, no write.
- **test_load_real_config_if_present_never_crashes** — Load config/llm.yml etc. if present; must not raise.

---

## 4. Next (Step 3)

Phase 1.2: Portal admin credentials (username + password, storage, verify). Then Phase 1.4: Portal config API (GET/PATCH for all six files).
