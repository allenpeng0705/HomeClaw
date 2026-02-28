# Portal Phase 2.3: Start Core UI — done

**Design ref:** [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 2.3.

**Goal:** Button "Start Core"; status "Core running at …" or "Core not running"; optional "Stop Core". Poll Core's `/ready` for status.

---

## 1. What was implemented

### 1.1 Backend

- **GET /api/portal/core/status** — Reads Core host/port from config (core.yml). If host is `0.0.0.0`, uses `127.0.0.1` for the request. Requests `GET {url}/ready` with 3s timeout. Returns `{ "running": true|false, "url": "http://..." }`.
- **POST /api/portal/core/start** — Spawns `python -m main start` via `subprocess.Popen` in project root; `start_new_session=True`, stdout/stderr to DEVNULL. Returns immediately with `{ "result": "started" }`.
- **POST /api/portal/core/stop** — Sends `GET {url}/shutdown` to Core (5s timeout). Returns `{ "result": "sent" }`.

### 1.2 Dashboard

- **Core card** — On the dashboard (logged-in): "Core" section with status line, "Start Core" and "Stop Core" buttons.
- **Polling** — On load and every 5s, `GET /api/portal/core/status`; status text shows "Core running at http://..." (green) or "Core not running" (grey).
- **Buttons** — Start Core: disabled when running; Stop Core: disabled when not running. Clicking Start/Stop triggers POST then refreshes status.

---

## 2. Files touched

| File | Change |
|------|--------|
| **portal/app.py** | Imports: subprocess, sys, urllib.request; `portal_config` for ROOT_DIR. `_get_core_base_url()`, GET/POST core/status, core/start, core/stop. Dashboard HTML: Core card + script (poll, start, stop). |
| **docs_design/implementation_steps/Portal_Phase2.3_start_core_ui.md** | This file. |

---

## 3. Acceptance

- Click "Start Core" → Core process runs; within a few seconds status updates to "Core running at http://127.0.0.1:9000" (or configured host/port).
- Click "Stop Core" → Core receives shutdown; status updates to "Core not running".
- Status polls every 5s and on page load.

---

## 4. Next (Phase 2.4)

- **2.4** Start channel UI: list channels, start Core (if not running), start channel process.
