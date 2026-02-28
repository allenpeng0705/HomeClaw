# Portal Phase 2.1: Manage settings UI — done

**Design ref:** [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 2.1.

**Goal:** One “Manage settings” page with tabs for each config; load via GET /api/config/{name}, edit, save via PATCH. Sensitive values show as ••• and are not changed on save.

---

## 1. What was implemented

### 1.1 Layout and nav

- **Logged-in layout** — `_logged_in_page(title, nav_active, content, card_class)`: nav bar (Dashboard | Manage settings | Log out) + main content. Used by dashboard and settings.
- **Dashboard** — Uses logged-in layout; “Manage settings” button links to `/settings`.
- **GET /logout** — Clears `portal_session` cookie and redirects to `/login`.

### 1.2 Manage settings page (GET /settings)

- **Tabs** — Core, LLM, Memory & KB, Skills & Plugins, Users, Friend presets. Query `?tab=<name>` opens that tab (default: core).
- **Per-tab** — On tab click (or load), fetch `GET /api/config/<name>`. Render a form:
  - Scalar values → text input (placeholder ••• for redacted).
  - Objects/arrays → textarea with JSON (placeholder ••• for redacted).
- **Save** — Collect non-empty, non-••• fields; parse JSON textareas; send `PATCH /api/config/<name>` with that body. Show “Saved.” or error message.
- **Redaction** — Values equal to `"***"` in API response are shown as placeholder ••• and omitted from PATCH so the file is not overwritten.

### 1.3 Tech

- Server-rendered HTML; minimal JS for fetch, form build, and PATCH. No separate SPA. Works in mobile WebView (touch-friendly, same styles as rest of Portal).

---

## 2. Files touched

| File | Change |
|------|--------|
| **portal/app.py** | Logout route; _logged_in_page(); dashboard uses nav + link to settings; GET /settings; _settings_html() with tabs and inline script; styles for nav, tabs, settings form, textarea. Removed duplicate setup_get. |
| **tests/test_portal_step3_routes.py** | test_settings_without_session_redirects_to_login, test_settings_with_session_returns_200, test_logout_clears_cookie_and_redirects. |
| **portal/README.md** | Phase 2.1 section. |
| **docs_design/implementation_steps/Portal_Phase2.1_manage_settings_ui.md** | This file. |

---

## 3. Tests

```bash
pytest tests/test_portal_step3_routes.py -v
```

- **test_settings_without_session_redirects_to_login** — GET /settings without cookie → 302 to /login.
- **test_settings_with_session_returns_200** — After login, GET /settings → 200 and “Manage settings” in body.
- **test_logout_clears_cookie_and_redirects** — GET /logout → 302 to /login and cookie cleared.

---

## 4. Next (Phase 2.2–2.4)

- **2.2** Guide to install UI (steps: Python, venv, config dir, optional doctor).
- **2.3** Start Core UI (button + status polling).
- **2.4** Start channel UI (list channels, start Core/channel).
