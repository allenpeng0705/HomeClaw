# Portal Step 1: Minimal server and entrypoint — done

**Design ref:** [CorePortalDesign.md](../CorePortalDesign.md), [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 1.3.

**Goal:** Portal as a separate module in project root `portal/`. Minimal web server that runs with `python -m main portal`; never crash (global exception handler); tests and docs.

---

## 1. What was implemented

### 1.1 `portal/` package (project root)

- **`portal/__init__.py`** — Exposes `app` and `config`.
- **`portal/config.py`** — No dependency on `base.util`. `ROOT_DIR` = parent of `portal/`; `get_host()` (default `127.0.0.1`, override `PORTAL_HOST`); `get_port()` (default `8000`, override `PORTAL_PORT`); `get_config_dir()` = `ROOT_DIR / "config"`.
- **`portal/app.py`** — FastAPI app:
  - **`GET /`** — Plain text `"HomeClaw Portal\n"`.
  - **`GET /ready`** — Plain text `"ok"` (readiness).
  - **`GET /api/portal/status`** — JSON: `service`, `config_dir`, `config_dir_exists`.
  - **Global exception handler** for `Exception`: returns 500 JSON `{"detail": "Internal server error", "error": "..."}` so the server never crashes.

### 1.2 Entrypoint in `main.py`

- **Command:** `portal` added to `choices` (start, onboard, doctor, portal).
- **`run_portal()`** — Imports `uvicorn`, `portal.app`, `portal.config`; runs `uvicorn.run(app, host=get_host(), port=get_port())`. Catches import/runtime errors and logs + `sys.exit(1)`.

### 1.3 Dependencies

- **requirements.txt:** `uvicorn>=0.20.0` added so `python -m main portal` works after `pip install -r requirements.txt`.

### 1.4 Tests

- **`tests/test_portal_step1.py`** — Uses FastAPI `TestClient` (no live server):
  - `test_root_returns_200_and_text` — GET / returns 200 and body contains "Portal".
  - `test_ready_returns_200` — GET /ready returns 200 and "ok".
  - `test_status_returns_json` — GET /api/portal/status returns 200 and JSON with `service`, `config_dir`, `config_dir_exists`.
  - `test_404_for_unknown_path` — GET /nonexistent returns 404.

### 1.5 Documentation

- **`portal/README.md`** — How to run (main portal + direct uvicorn), host/port env, Step 1 routes, how to run tests.

---

## 2. Files touched

| File | Change |
|------|--------|
| **portal/__init__.py** | New. |
| **portal/config.py** | New. |
| **portal/app.py** | New. |
| **portal/README.md** | New. |
| **main.py** | Add `portal` command; `run_portal()`; `elif args.command == "portal"`. |
| **requirements.txt** | Add `uvicorn>=0.20.0`. |
| **tests/test_portal_step1.py** | New. |
| **docs_design/implementation_steps/Portal_Step1_minimal_server.md** | New (this file). |

---

## 3. Stability and no-crash

- **Global exception handler:** Any unhandled exception in a route returns 500 JSON; process does not crash.
- **run_portal():** Import or uvicorn failure logs and exits with code 1; no uncaught exception.
- **config.py:** `get_port()` falls back to 8000 on invalid env; `get_config_dir()` uses `Path`; no I/O that can raise.

---

## 4. How to run and verify

```bash
# From project root, with venv activated (and pip install -r requirements.txt)
python -m main portal
# In another terminal:
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/api/portal/status
```

```bash
pytest tests/test_portal_step1.py -v
```

---

## 5. Next (Step 2)

Per implementation plan: **Phase 1.1** YAML merge layer for llm, memory_kb, skills_and_plugins, friend_presets; then **Phase 1.2** admin credentials; then **Phase 1.4** Portal config API.
