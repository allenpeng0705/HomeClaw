# Packaging script review — can it work?

This doc confirms the packaging script and launcher behavior so the bundled app works end-to-end.

---

## 1. Core path resolution (must match bundle layout)

- **Util.root_path()** in `base/util.py`: `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → directory containing `base/`, i.e. the **Core root** (where `main.py`, `config/`, `system_plugins/` live).
- **Launcher** sets `cd "$CORE_ROOT"` with `CORE_ROOT="$RESOURCES"` = `HomeClaw.app/Contents/Resources`, then runs `python -m main start`.
- So at runtime, `__file__` is `Contents/Resources/base/util.py` → **root_path() = Contents/Resources**. That directory has `main.py`, `base/`, `core/`, `config/`, `system_plugins/`, etc. **Matches.**

**Conclusion:** Core will resolve `config/`, `system_plugins/`, `database/`, `logs/` under the bundle Resources dir. No code change needed.

---

## 2. Config (core.yml, user.yml)

- Packaged **full** `config/core.yml` and `config/user.yml` (with comments and all fields) into `OUTPUT_DIR/config/`, then moved to `Contents/Resources/config/`.
- Core reads `config_path() = root_path() + '/config'` → `Contents/Resources/config`. **Matches.**

**Conclusion:** Config is in the right place and complete.

---

## 3. Embedded Python

- **Download:** python-build-standalone (astral-sh) for current arch (`aarch64-apple-darwin` or `x86_64-apple-darwin`).
- **Extract:** Handles both `python/install/` layout and fallback for other top-level dirs; final tree is `OUTPUT_DIR/python/bin/python3` (or `python`).
- **Install deps:** `python -m pip install -r requirements.txt` into that Python (site-packages inside the bundle).
- **Launcher** uses `$RESOURCES/python/bin/python3` (or `python`) to run `python -m main start`. No system Python required.

**Conclusion:** Python is self-contained and correct for running Core.

---

## 4. Node.js and homeclaw-browser

- **Download:** Node.js LTS from nodejs.org for `darwin-arm64` or `darwin-x64`.
- **Extract:** `node-v20.x.x-darwin-arch` → renamed to `node`; `node/bin/node` and `node/bin/npm` used.
- **npm install:** Run in `OUTPUT_DIR/system_plugins/homeclaw-browser` with bundled npm; `node_modules` is created inside the plugin dir (and excluded from rsync is only for the *initial* copy; we then run npm in that copied dir, so node_modules is present before the move).
- **Launcher** sets `PATH="$RESOURCES/node/bin:$PATH"` before starting Core. Core subprocess runs `node server.js` and `node register.js` with `cwd=system_plugins/homeclaw-browser`; it inherits PATH and finds the bundled `node`.
- **Core** discovers plugins via `Util().system_plugins_path()` = `Contents/Resources/system_plugins`; `homeclaw-browser` has `register.js` and `package.json` with `"start": "node server.js"`. **Matches.**

**Conclusion:** homeclaw-browser will start with the bundled Node; no user-installed Node required (unless `--no-node`).

---

## 5. Companion app

- Built with `flutter build macos --release`; copied to `OUTPUT_DIR/companion/HomeClawApp.app`, then into `Contents/Resources/companion/`.
- Launcher runs `open "$COMPANION_APP"` only if `[[ -d "$COMPANION_APP" ]]` (so `--no-companion` does not error).

**Conclusion:** Companion is optional and opened when present.

---

## 6. Launcher script behavior

1. `RESOURCES="$SCRIPT_DIR/../Resources"` (correct for `Contents/MacOS/HomeClaw`).
2. `[[ -d "$RESOURCES/node/bin" ]] && export PATH="..."` so Node is used when bundled.
3. `cd "$CORE_ROOT"` (= Resources) then `"$PYTHON_BIN" -m main start --no-open-browser &`.
4. Loop: poll `http://127.0.0.1:9000/ready` up to 60s (curl).
5. `open "$COMPANION_APP"` if present.
6. `wait $CORE_PID` so the launcher does not exit immediately (Core keeps running in background until user stops it or shutdown).

**Conclusion:** Launcher starts Core with correct cwd and PATH, waits for readiness, then opens Companion. Core port is 9000 (from packaged core.yml).

---

## 7. What is excluded (intentional)

- **models**, **database**, **logs** — Not packaged; created at runtime under `Contents/Resources` when Core runs (or user can point config elsewhere). Models: user puts files in `~/HomeClaw/models` and sets `model_path` if needed.
- **node_modules** — Excluded in the *initial* rsync, but we run `npm install` in the copied `system_plugins/homeclaw-browser`, so the **plugin’s** node_modules exists before we move `system_plugins` into the app. So the bundle does include homeclaw-browser’s node_modules.
- **site**, **docs**, **tests**, **clients** — Not needed at runtime.

**Conclusion:** Exclusions are correct; plugin deps are still included via npm install step.

---

## 8. Edge cases handled

- **--no-companion:** Companion dir may be missing; copy and `open` are conditional.
- **--no-node:** Node dir may be missing; copy and PATH are conditional.
- **Python tarball layout:** Handles both `python/install/` and a fallback that finds any extracted dir with `bin/python3` or `install/bin/python3`.
- **Non-macOS:** `BUILD_LAUNCHER=0`; only folder package is produced.

**Conclusion:** Script is robust to options and tarball variations.

---

## 9. Summary

| Check | Status |
|-------|--------|
| Core root_path() matches bundle layout (Contents/Resources) | OK |
| config/ and system_plugins/ paths correct | OK |
| Embedded Python runs Core and has deps installed | OK |
| Node bundled and on PATH when Core starts plugins | OK |
| homeclaw-browser has node_modules via npm install | OK |
| Companion optional; launcher doesn’t fail if missing | OK |
| Launcher cwd and PATH correct; /ready poll then open Companion | OK |
| Exclusions and npm step leave plugin deps in bundle | OK |

**Verdict:** The packaging script and launcher are consistent with Core’s path resolution and plugin startup. The bundled app should work when the user runs HomeClaw.app, with models in a user-chosen path (e.g. ~/HomeClaw/models) and config editable inside the app bundle.
