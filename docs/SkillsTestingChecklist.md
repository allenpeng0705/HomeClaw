# Skills testing checklist

Use this checklist after adding many new skills to verify config, sync, selection, and execution.

---

## 1. Config (config/core.yml)

| Check | What to set |
|-------|-------------|
| Skills enabled | `use_skills: true` |
| Skills directory | `skills_dir: skills` (or your path) |
| Vector search (recommended for many skills) | `skills_use_vector_search: true` |
| Sync on startup | `skills_refresh_on_startup: true` so new skills are registered to the vector store |
| How many in prompt | When vector search on: `skills_max_retrieved: 10`, `skills_max_in_prompt: 5`. When off: all skills. |
| Similarity threshold | `skills_similarity_threshold: 0.3` (or 0.0 to include more; 0.5 can drop cross-lingual matches) |
| Script allowlist (if skills have scripts/) | Under `tools:`, set `run_skill_allowlist: ["run.sh", "main.py", "index.js", ...]` or leave empty to allow all |

---

## 2. Sync (register skills to vector store)

After adding new skills:

1. **Restart Core** so `skills_refresh_on_startup` runs and syncs `skills_dir` → vector store.
2. In logs, look for:
   - `[skills] synced N skill(s) to vector store`
   - On each request (when vector search is on): `[skills] retrieved N skill(s) by vector search` and `[skills] selected: folder1, folder2, ...`

If you use **skills_test_dir** for testing new skills first:

- Set `skills_test_dir: skills_test` (or another path).
- Put the new skill folder there (same structure: `skills_test/my-skill/SKILL.md`).
- Restart; test folder is fully synced every time (ids stored as `test__<folder>`).
- When ready, move the folder from `skills_test_dir` to `skills_dir` and restart.

---

## 3. Test by skill type

### Instruction-only skills (no scripts/ folder)

Examples: LinkedIn Writer, Summarize.

1. Send a message that matches the skill (e.g. “Write a LinkedIn post about …”).
2. Check logs: `[skills] selected: linkedin-writer-1.0.0, ...`.
3. The model should use the skill’s instructions in its response (no `run_skill` call).

Optional: If the model calls `run_skill(skill_name="linkedin-writer-1.0.0")` with no script, it should get the “instruction-only” message and then follow the skill’s guidelines.

### Script-based skills – Python (.py)

1. Ensure the skill has `scripts/` with e.g. `main.py` or `run.py`.
2. If you use an allowlist, add the script name to `tools.run_skill_allowlist`.
3. Send a message that should trigger the skill; the model should call `run_skill(skill_name="<folder>", script="main.py", args=[...])`.
4. Check that the script runs (Python must be in PATH).

### Script-based skills – Node.js (.js, .mjs, .cjs)

1. Ensure the skill has `scripts/` with e.g. `index.js`.
2. Install Node.js and ensure `node` is in PATH.
3. Add the script name to `run_skill_allowlist` if you use an allowlist.
4. Send a message that triggers the skill; the model should call `run_skill(skill_name="<folder>", script="index.js", args=[...])`.
5. Check that `node` runs the script (cwd is the skill folder).

### Script-based skills – Shell (.sh)

1. Ensure the skill has `scripts/` with e.g. `run.sh`.
2. On Windows, `bash` (e.g. Git Bash) or WSL must be in PATH for `.sh` to run.
3. Add the script name to `run_skill_allowlist` if needed.
4. Trigger the skill and confirm the script runs.

---

## 4. Test vector retrieval (selection)

When `skills_use_vector_search: true`:

1. Send a **query that clearly matches one or two skills** (e.g. “write a LinkedIn post”, “summarize this”, “check the weather”).
2. In logs, confirm:
   - `[skills] retrieved N skill(s) by vector search`
   - `[skills] selected: <folder1>, <folder2>, ...`
3. The listed folders should be the ones you expect for that query. If not, adjust `skills_similarity_threshold` or improve skill names/descriptions in SKILL.md.

**Why RAG might not select a skill:** (1) **Threshold too high** — similarity below `skills_similarity_threshold` (e.g. 0.5) is dropped; cross-lingual or short queries often score lower → lower to 0.3 or 0.0 or use force-include. (2) **Skill text too generic** — add `keywords: "..."` in SKILL.md frontmatter (e.g. English + Chinese) so the embedded text matches more queries; restart to re-sync. (3) **Store empty/stale** — restart with `skills_refresh_on_startup: true`; check for embedding errors at startup. (4) **Embedder down** — query isn’t embedded, so search returns nothing.

When vector search is **off** (`skills_use_vector_search: false`):

- All skills are loaded from disk (no cap). Check `[skills] included all N skill(s) (skills_use_vector_search=false)` and `[skills] selected: ...`.

---

## 5. Test run_skill allowlist (if used)

If `tools.run_skill_allowlist` is set (e.g. `["main.py", "index.js"]`):

1. Call `run_skill` with a script **in** the allowlist → should run.
2. Call `run_skill` with a script **not** in the allowlist → should get “Error: script 'X' is not in run_skill_allowlist”.

---

## 6. Optional: clear vector store (for testing)

To force a clean re-sync or debug retrieval:

- **Clear skills only:**  
  `POST /api/skills/clear-vector-store`  
  (requires Core to be running; next startup with `skills_refresh_on_startup: true` will re-sync.)
- **Clear skills and unregister plugins:**  
  `POST /api/testing/clear-all`

Then restart Core so skills are re-registered.

---

## 7. Quick checklist summary

| Step | Action |
|------|--------|
| 1 | Set `use_skills: true`, `skills_dir`, and (recommended) `skills_use_vector_search: true`, `skills_refresh_on_startup: true`. |
| 2 | Restart Core; confirm log: `[skills] synced N skill(s) to vector store`. |
| 3 | Send a query that matches a skill; confirm `[skills] selected: ...` includes the right folders. |
| 4 | For instruction-only skills: confirm the model follows the skill’s instructions. |
| 5 | For script skills: confirm `run_skill(skill_name, script, args)` runs (Python/Node/shell as appropriate). |
| 6 | If scripts are restricted: set `run_skill_allowlist` and test allowed vs disallowed script names. |

Full reference: **docs_design/SkillsGuide.md** (§4 How to test skills, §5 Config reference).
