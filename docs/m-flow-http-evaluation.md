# M-flow evaluation via HTTP

This document is a **practical runbook** for evaluating [M-flow](https://github.com/FlowElement-ai/m_flow) as an **HTTP sidecar** (no HomeClaw Core `memory_backend` changes required until you choose to integrate). MCP is optional and not required for this path.

## 1. Goals and scope

### Goals

- Verify the stack runs and stays healthy (`/health`).
- Prove **ingest → memorize → search** over HTTP with the same shapes Core would use later.
- Measure **latency, reliability, and retrieval usefulness** on a **fixed corpus + fixed questions**.
- Record **config** (base URL, auth, dataset naming, recall modes) for a future Core adapter.

### Out of scope for this evaluation

- Implementing `MemoryBase` / `composite` in HomeClaw.
- Sharing Cognee’s data files with M-flow (separate stores; you may use the same *kinds* of database systems with **separate** paths/instances — see [Memory and database](../docs_design/MemoryAndDatabase.md)).
- MCP (you can add a parallel Cursor trial later).

## 2. Prerequisites

| Item | Notes |
|------|--------|
| **M-flow checkout** | Run the API from their repo (e.g. `./quickstart.sh` or Docker Compose). Default banner: **API** `http://localhost:8000`, **docs** `http://localhost:8000/docs`. |
| **LLM / embedding inside M-flow** | Memorization is LLM-heavy; configure keys/env per M-flow docs. Failures can look like “HTTP OK but empty or wrong memory.” |
| **Network** | Your evaluator can reach the API (prefer `http://127.0.0.1:8000` in scripts to avoid IPv6 quirks). |
| **Client** | `httpx` (HomeClaw already depends on it) or `curl` + `jq` for smoke tests. |
| **Timeouts** | Use **long** timeouts on `memorize` (e.g. 120–300 s); shorter on `search` (e.g. 60–120 s). |

## 3. Baseline URL and discovery

1. Start M-flow and confirm the printed **API base** (typically `http://localhost:8000`).
2. `GET {base}/health` — must succeed before loading data.
3. Open `{base}/docs` — OpenAPI is the source of truth if your M-flow version differs from this doc.

**Record in a runbook:** `BASE_URL`, whether `Authorization: Bearer …` is required, and M-flow version (git commit or any version endpoint they expose).

## 4. HTTP contract (reference implementation)

Upstream’s **`MflowClient` remote mode** in `m_flow-mcp/src/m_flow_client.py` is the canonical contract for JSON/multipart shapes.

### 4.1 Add (ingest)

- **POST** `{base}/api/v1/add`
- **Multipart form:**
  - File field **`data`** — `text/plain` body (e.g. filename `data.txt`).
  - Field **`datasetName`** — string (your isolation key, e.g. `hc_eval_001`).
  - Optional **`graph_scope`** — JSON string of a list of tags.
- **Success:** HTTP 2xx + JSON; log status and any ids returned.

### 4.2 Memorize (build graph)

- **POST** `{base}/api/v1/memorize`
- **JSON:**
  - **`datasets`**: e.g. `["hc_eval_001"]`
  - **`run_in_background`**: `false` for deterministic “add then search” runs
  - Optional: **`enable_content_routing`**, **`content_type`** (`"text"` / `"dialog"`)

### 4.3 Search

- **POST** `{base}/api/v1/search`
- **JSON:**
  - **`query`**: string
  - **`recall_mode`**: uppercase — e.g. **`EPISODIC`** (primary for their benchmarks), **`CHUNKS_LEXICAL`** (simpler baseline), **`TRIPLET_COMPLETION`**, **`PROCEDURAL`**, **`CYPHER`**
  - **`top_k`**: int
  - Optional: **`datasets`**, **`system_prompt`**, **`enable_hybrid_search`** (for episodic)

### 4.4 Remote limitations

In remote HTTP mode, their client does **not** implement some maintenance operations (e.g. certain **prune** / workflow status paths). Plan evaluation around **add → memorize → search**; use **delete** only if `/docs` exposes it and you need cleanup.

## 5. Dataset / isolation strategy

Pick one convention for all runs:

| Approach | Use when |
|----------|----------|
| **New `datasetName` per run** | Clean A/B without manual cleanup; e.g. `hc_eval_YYYYMMDD_n`. |
| **Stable name per “user”** | Simulating multi-user; e.g. `hc_user_alice`. |

Do **not** reuse one dataset name across conflicting corpora without a defined reset path.

## 6. Evaluation phases

### Phase A — Smoke

1. `GET /health`
2. `POST /add` with small text + `datasetName`
3. `POST /memorize` with `datasets=[that name]`, `run_in_background=false`
4. `POST /search` with `EPISODIC`, `top_k=5`, `datasets` set to that name
5. Log status codes, elapsed ms, and a short snippet of response

**Pass:** No 5xx; search returns non-empty useful context for a trivial fact in the text.

### Phase B — Fixed corpus

1. **Corpus:** 3–10 chunks (paragraphs or fake chat turns) with explicit facts (names, dates, numbers) and multi-hop relations.
2. **Ingest:** either one `add` per chunk or one combined blob — match how you intend to use Core later.
3. **Memorize:** once after all adds (or per chunk if testing incremental behavior).
4. **Query suite:** 10–30 questions (single-hop, multi-hop, distractor, “not in corpus”).

**Modes:** At minimum **`EPISODIC`** + **`CHUNKS_LEXICAL`** on the same queries for comparison.

### Phase C — Stress / ops

1. **Concurrency:** 2–3 parallel `search` requests (same dataset).
2. **Timeout:** deliberately lower client timeout once to observe failure mode (for Core retry policy).
3. **Cold vs warm:** first search after restart vs steady state.

### Phase D — Optional comparison

Same corpus + questions in a spreadsheet; manual score 0–2 per answer. Optionally compare behavior to **Cognee** (HomeClaw) on the **same** Q&A **without** merging stores — side-by-side evaluation only.

## 7. Metrics and logging

| Metric | How |
|--------|-----|
| **Availability** | % successful `health` + `add` + `memorize` + `search` in N trials |
| **Latency** | p50/p95 for `memorize` and `search` separately |
| **Quality** | Rubric or gold answers; note `recall_mode` |
| **Isolation** | Two datasets with conflicting facts; ensure `datasets` filter returns the correct one |
| **Errors** | HTTP code, response body excerpt, request id if present |

Keep raw JSON for a few runs under a local `logs/` path (gitignored).

## 8. Script in this repo (`scripts/eval_m_flow_http.py`)

This script **only** uses `httpx` and talks to M-flow’s HTTP API. It does **not** import HomeClaw Core, `memory`, or Cognee, so it cannot change or break your current memory system.

**Env vars**

| Variable | Default |
|----------|---------|
| `MFLOW_BASE_URL` | `http://127.0.0.1:8000` |
| `MFLOW_DATASET` | `--smoke`: `hc_eval_smoke`; `--full`: `hc_eval_YYYYMMDD` (UTC) |
| `MFLOW_BEARER` | unset (optional `Authorization: Bearer`) |

**Examples** (with M-flow API running):

```bash
# Phase A — minimal ingest + EPISODIC + CHUNKS_LEXICAL
export MFLOW_BASE_URL=http://127.0.0.1:8000
python3 scripts/eval_m_flow_http.py --smoke

# Phase B lite — embedded sample corpus + default questions
python3 scripts/eval_m_flow_http.py --full

# Custom corpus file (UTF-8)
python3 scripts/eval_m_flow_http.py --full --corpus-file path/to/corpus.txt
```

**Flags:** `--base-url`, `--dataset`, `--bearer`, `--memorize-timeout` (default 300 s), `--search-timeout` (default 120 s), `--top-k`.

Pytest integration is optional later (`@pytest.mark.integration`, skip if M-flow is not running).

## 9. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| **LLM misconfig inside M-flow** | Validate with a tiny corpus first; check M-flow logs. |
| **Memorize very slow** | Long timeout; use `run_in_background=false` only when you need a single barrier before search. |
| **Version drift** | Pin M-flow commit or Docker image; snapshot `/docs` or exported OpenAPI. |
| **Empty search results** | Confirm `datasets` matches `datasetName`; try `CHUNKS_LEXICAL` if `EPISODIC` is empty. |

## 10. Exit criteria

- Runbook is **reproducible** (steps + env vars documented).
- Phases **A** and **B** pass with **logged** metrics.
- **Decision:** proceed with a Core HTTP client / `MemoryBase` adapter, pause, or revisit after M-flow upgrades.

## 11. Related docs

- [Memory and database](../docs_design/MemoryAndDatabase.md) — Cognee vs in-house backends; separate stores from M-flow.
- [Memex with Cursor and Claude](memex-with-cursor-and-claude.md) — MCP-oriented memex; orthogonal to this HTTP evaluation.
