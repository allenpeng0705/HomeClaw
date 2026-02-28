# Portal Phase 2.4: Start channel UI — done

**Design ref:** [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 2.4.

**Goal:** List channels (from `channels/*/channel.py`); buttons to start Core (if not running) and to start a chosen channel.

---

## 1. What was implemented

### 1.1 Backend

- **GET /api/portal/channels** — Scans `channels/` for directories that contain `channel.py`; returns `{ "channels": ["bluebubbles", "discord", ...] }` (sorted). Never raises.
- **POST /api/portal/channels/{name}/start** — Starts channel via `python -m channels.run <name>` in project root (subprocess.Popen, start_new_session=True). Returns `{ "result": "started" }` or 400 if unknown channel, 500 on spawn error.

### 1.2 UI

- **Nav** — "Start channel" link in the logged-in nav bar (Dashboard, Start channel, Guide to install, Manage settings, Log out).
- **Start channel page (/channels)** — Title "Start channel"; link "Dashboard (Start Core)"; list of channels loaded from GET /api/portal/channels; each channel has a "Start &lt;name&gt;" button that POSTs to `/api/portal/channels/{name}/start` and shows an alert on success/failure.

---

## 2. Files touched

| File | Change |
|------|--------|
| **portal/app.py** | `_get_channels_list()`, GET /api/portal/channels, POST /api/portal/channels/{name}/start. Nav: added "Start channel" link. `_channels_page_content()`, GET /channels (protected). |
| **docs_design/implementation_steps/Portal_Phase2.4_start_channel_ui.md** | This file. |

---

## 3. Acceptance

- Channels list appears on the Start channel page.
- Clicking "Start &lt;channel&gt;" starts that channel’s process (e.g. `python -m channels.run telegram`).
- User can open Dashboard to start Core first, then Start channel to start individual channels.
