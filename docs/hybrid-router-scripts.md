# Hybrid router scripts

This page describes how to use the scripts that maintain **Layer 1 (heuristic)** and **Layer 2 (semantic)** routing rules for [mix mode](mix-mode-and-reports.md). Run all commands from the **repository root**.

---

## Overview

| Script | Purpose |
|--------|--------|
| **validate_heuristic_rules.py** | Check that no keyword appears in both local and cloud rules (avoids ambiguous routing). |
| **generate_utterances.py** | Generate many local/cloud example utterances for the semantic router (verb×object + expert list). |
| **generate_heuristics.py** | Generate heuristic keywords from a verb×noun matrix and/or `{{a|b}}` templates. |

**When to use**

- After editing `config/hybrid/heuristic_rules.yml` → run **validate_heuristic_rules.py**.
- To enrich Layer 2 utterances (more coverage, EN+ZH) → run **generate_utterances.py** (optionally with `--merge`).
- To enrich Layer 1 keywords (more verb/noun combos or templates) → run **generate_heuristics.py** (optionally with `--merge`), then validate.

**Prerequisites**

- **Python 3** and **PyYAML** (`pip install pyyaml`).
- No need to start Core or install full app dependencies to run these scripts.

---

## 1. validate_heuristic_rules.py

Validates **heuristic_rules.yml** for keyword conflicts: the same normalized phrase must not be assigned to both **local** and **cloud**. The router is first-match-wins; conflicts make behavior unclear.

**Usage**

```bash
python3 scripts/validate_heuristic_rules.py
python3 scripts/validate_heuristic_rules.py path/to/heuristic_rules.yml
```

**Behavior**

- Reads `config/hybrid/heuristic_rules.yml` (or the path you pass).
- Normalizes keywords (lowercase + Unicode NFC), same as the router.
- If any keyword appears in both a local and a cloud rule → prints conflicts and exits with code **1**.
- If no conflicts → prints `OK` and exits **0**.

**When to run**

- After hand-editing heuristic rules.
- After running **generate_heuristics.py --merge**.

---

## 2. generate_utterances.py (Layer 2 semantic routes)

Generates dense **local** and **cloud** example utterances for the semantic router. Uses:

- **Verb×object templates** (e.g. find+file, open+browser) in several categories.
- **Expert lists** of hand-written phrases (including **simple conversation**: hi, thanks, bye, 你好, 谢谢, etc.) so chit-chat routes to local in Layer 2.

**Usage**

```bash
# Generate to default file (config/hybrid/generated_utterances.yml)
python3 scripts/generate_utterances.py

# Custom output path
python3 scripts/generate_utterances.py -o path/to/output.yml

# Merge into semantic_routes.yml (existing + generated, deduped; no cross-list duplicates)
python3 scripts/generate_utterances.py --merge

# Limit size (for latency: ~300–500 local is a good balance)
python3 scripts/generate_utterances.py --max-local 500 --max-cloud 300
```

**Options**

| Option | Default | Description |
|--------|---------|-------------|
| `--output`, `-o` | `config/hybrid/generated_utterances.yml` | Output YAML path. |
| `--max-local` | 500 | Max local utterances. |
| `--max-cloud` | 300 | Max cloud utterances. |
| `--max-from-templates` | 450 | Max local utterances from verb×object combinations. |
| `--merge` | off | Merge into `config/hybrid/semantic_routes.yml` (existing first, then generated; deduped within and across lists). |

**Using the output**

- **Option A:** In `config/core.yml`, set `hybrid_router.semantic.routes_path: config/hybrid/generated_utterances.yml` so the router uses the generated file.
- **Option B:** Run with **`--merge`** to add generated utterances into **semantic_routes.yml** (one file, existing + generated).
- **Option C:** Run with `-o config/hybrid/semantic_routes.yml` to overwrite semantic_routes with only the generated lists (no merge).

**Tips**

- Keep local utterances around **300–500** so embedding lookup stays fast (~10 ms).
- When you add new features (e.g. a Spotify plugin), add verbs/objects in the script’s `LOCAL_TEMPLATES` or expert lists and re-run.

---

## 3. generate_heuristics.py (Layer 1 heuristic rules)

Generates **heuristic** keywords from:

- A **simple-conversation** rule (hello, hi, thanks, bye, ok, 你好, 谢谢, 再见, …) so chit-chat routes to local in Layer 1.
- A **verb×noun matrix** (e.g. open+wifi, search+file) per category (screen, system, files, app, cloud research, …).
- **Templates** using `{{a|b|c}}`: e.g. `{{open|launch}} {{browser|app}}` expands to all permutations.

**Usage**

```bash
# Generate to default file (config/hybrid/generated_heuristic_rules.yml)
python3 scripts/generate_heuristics.py

# Custom output
python3 scripts/generate_heuristics.py -o path/to/output.yml

# Merge into heuristic_rules.yml (existing first; generated local then cloud; skips keywords that would conflict with the opposite route)
python3 scripts/generate_heuristics.py --merge
```

**Options**

| Option | Default | Description |
|--------|---------|-------------|
| `--output`, `-o` | `config/hybrid/generated_heuristic_rules.yml` | Output YAML path. |
| `--merge` | off | Merge into `config/hybrid/heuristic_rules.yml` (existing rules kept; generated appended; conflicting keywords skipped). |

**Template syntax (in script or in YAML)**

- `{{a|b|c}}` → one of `a`, `b`, or `c`.
- Optional word: `{{a |}}` → `"a "` or empty (so you get “take a screenshot” and “take screenshot”).
- Be specific; **do not** use greedy patterns like `{{.*}}` (they are rejected).

**After merge**

Run the validator:

```bash
python3 scripts/validate_heuristic_rules.py
```

**Customization**

- Edit **MATRIX** (verbs/nouns per category) and **TEMPLATES** (list of `{route, tmpl}`) in `scripts/generate_heuristics.py`, then re-run.
- You can also put `tmpl` in **heuristic_rules.yml**; the router expands templates to keywords when loading (see [Mix mode and reports](mix-mode-and-reports.md)).

---

## Recommended workflow

1. **Heuristic rules**
   - Edit `config/hybrid/heuristic_rules.yml` by hand and/or run `generate_heuristics.py --merge`.
   - Run `validate_heuristic_rules.py`; fix any reported conflicts.
2. **Semantic utterances**
   - Edit `config/hybrid/semantic_routes.yml` by hand and/or run `generate_utterances.py --merge`.
   - Optionally point `routes_path` to `generated_utterances.yml` instead of merging.
3. **Restart Core** (if it’s running) so it reloads the updated YAML files.

---

## Config file locations

| File | Purpose |
|------|--------|
| `config/hybrid/heuristic_rules.yml` | Layer 1 rules (keywords / tmpl; long_input_*). Loaded by Core when mix mode is on. |
| `config/hybrid/semantic_routes.yml` | Layer 2 example utterances (local_utterances, cloud_utterances). |
| `config/hybrid/generated_utterances.yml` | Optional output of generate_utterances.py; use as semantic routes_path if desired. |
| `config/hybrid/generated_heuristic_rules.yml` | Optional output of generate_heuristics.py; merge into heuristic_rules or use as reference. |

Core chooses the heuristic and semantic files via `config/core.yml` under `hybrid_router.heuristic.rules_path` and `hybrid_router.semantic.routes_path` when `main_llm_mode: mix`.
