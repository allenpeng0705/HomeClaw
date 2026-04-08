# Tests

## Running tests

From the **project root** (directory containing `core/`, `tests/`, `config/`, etc.). Use **pytest** to run tests (do not use `python -m tests.test_core_routes`):

```bash
# Install pytest if needed
pip install pytest

# Run all tests
python -m pytest tests/ -v

# Run only Core route smoke tests
python -m pytest tests/test_core_routes.py -v

# Run only LiteLLM service tests
python -m pytest tests/test_litellm_service.py -v
```

Use `python3` instead of `python` if your environment uses `python3`.

## Workflow trace framework

Workflow trace tests validate end-to-end decision flow (model route, tool/skill/plugin calls, arg normalization, and fallbacks) and emit sequential JSONL traces.

```bash
# Run in-process mock scenario suite (fast, deterministic)
python scripts/workflow_trace_runner.py --mode in_process_mock

# Run real Core scenarios against running Core (api key optional: auto-discover from env or config/core.yml)
python scripts/workflow_trace_runner.py --mode real_core --base-url http://127.0.0.1:9000
python scripts/workflow_trace_runner.py --mode real_core --base-url http://127.0.0.1:9000 --api-key <YOUR_API_KEY>

# Or start Core from runner (slower)
python scripts/workflow_trace_runner.py --mode real_core --start-core --api-key <YOUR_API_KEY>

# Compare two traces
python scripts/workflow_trace_compare.py --baseline output/workflow_traces/<base>.jsonl --candidate output/workflow_traces/<cand>.jsonl

# Real Core smoke mode (opt-in)
HOMECLAW_RUN_REALCORE_WORKFLOW_TESTS=1 python -m pytest tests/test_workflow_runner_real_core.py -q
```

## Core route smoke tests (test_core_routes.py)

These tests verify that the refactored route modules in `core/routes/` can be imported and that every handler factory exists and returns a callable handler. They do **not** start Core or hit real HTTP endpoints.

- **What they do:** Import all route modules; check auth helpers; for each handler factory, call it with a mock Core and assert the result is callable.
- **How to run:** `python -m pytest tests/test_core_routes.py -v`
- **Full description:** See **docs_design/CoreRefactorPhaseSummary.md** → section **"Tests for Core routes"** (what the tests do, how to run them, how they work, and how to add new factories).

## Other tests

- **test_litellm_service.py** – LiteLLM service (chat completions). Requires pytest, pytest-asyncio, httpx; uses mocks, no real API keys.
