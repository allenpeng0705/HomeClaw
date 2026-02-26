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

## Core route smoke tests (test_core_routes.py)

These tests verify that the refactored route modules in `core/routes/` can be imported and that every handler factory exists and returns a callable handler. They do **not** start Core or hit real HTTP endpoints.

- **What they do:** Import all route modules; check auth helpers; for each handler factory, call it with a mock Core and assert the result is callable.
- **How to run:** `python -m pytest tests/test_core_routes.py -v`
- **Full description:** See **docs_design/CoreRefactorPhaseSummary.md** → section **"Tests for Core routes"** (what the tests do, how to run them, how they work, and how to add new factories).

## Other tests

- **test_litellm_service.py** – LiteLLM service (chat completions). Requires pytest, pytest-asyncio, httpx; uses mocks, no real API keys.
