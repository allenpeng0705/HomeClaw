# Portal Phase 6: Companion — Core setting entry and WebView — done

**Design ref:** [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 6.

**Goal:** Companion has a "Core setting" entry; tapping it shows Portal admin login; after success opens WebView to Core's `/portal-ui` with token.

---

## 1. What was implemented

### 6.1 Core setting entry and login screen

- **Settings:** New button "Core setting (Portal)" in Settings screen; navigates to `PortalLoginScreen`.
- **PortalLoginScreen** (`lib/screens/portal_login_screen.dart`): Username and password fields, "Log in" button. On submit calls `CoreService.postPortalAuth(username, password)`. On 200 saves token (in CoreService + SharedPreferences) and `pushReplacement` to `PortalUiScreen`. On 401 shows "Invalid username or password". Uses same credentials as Portal admin (config/portal_admin.yml).
- **CoreService** (`lib/core_service.dart`): `_keyPortalAdminToken`, `portalAdminToken` getter, `postPortalAuth({username, password})` (POST `/api/portal/auth`), `clearPortalAdminToken()`. Token loaded/saved in `loadSettings` and after login.

### 6.2 WebView loading /portal-ui with auth

- **PortalUiScreen** (`lib/screens/portal_ui_screen.dart`): WebView loads `baseUrl/portal-ui?token=<token>`. `NavigationDelegate.onNavigationRequest`: for same-origin `/portal-ui` URLs without `token=`, appends `?token=...` or `&token=...` and loads that URL (so sub-navigations stay authenticated). AppBar "Log out" (close) clears token and pops back to Settings.
- **Logout:** Back/close clears token and pops; next "Core setting (Portal)" tap shows login again.

---

## 2. Files touched

| File | Change |
|------|--------|
| **lib/core_service.dart** | `_keyPortalAdminToken`, `_portalAdminToken`, `portalAdminToken`; `loadSettings` loads token; `postPortalAuth`, `clearPortalAdminToken`. |
| **lib/screens/portal_login_screen.dart** | New: Portal admin login form; on success pushReplacement to PortalUiScreen. |
| **lib/screens/portal_ui_screen.dart** | New: WebView with token in URL; inject token on sub-navigations; logout pops. |
| **lib/screens/settings_screen.dart** | Import PortalLoginScreen; new button "Core setting (Portal)" → PortalLoginScreen; kept "Manage Core (core.yml & user.yml)" → ConfigCoreScreen. |
| **docs_design/implementation_steps/Portal_Phase6_companion.md** | This file. |

---

## 3. Acceptance

- User taps "Core setting (Portal)" → sees login (username, password).
- Wrong credentials → "Invalid username or password".
- Correct credentials → WebView opens with Portal UI (Core’s /portal-ui proxy). User can navigate; token is appended to /portal-ui sub-requests.
- Log out (back/close) clears token; next tap shows login again.
