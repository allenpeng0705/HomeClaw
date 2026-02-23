# Skills and plugins: never break Core

Skills and plugins run in or are invoked by Core. This document states the **stability contract**: failures must be contained so that Core never crashes or hangs.

---

## 1. Contract

- **Skills** (run_skill) and **plugins** (route_to_plugin) must **never break Core**.
- Any failure (exception, timeout, script crash) is turned into an **error string** returned to the model/user. Core keeps running.
- Timeouts apply so a stuck skill or plugin does not hang Core indefinitely.

---

## 2. Skills (run_skill)

| Mechanism | How it keeps Core stable |
|-----------|---------------------------|
| **Default: subprocess** | Python scripts run in a **subprocess** by default. A script crash, `os._exit()`, or segfault only kills the subprocess; Core is unaffected. |
| **In-process allowlist** | Only skills whose folder name is in **run_skill_py_in_process_skills** run in Core's process (in a thread). Exceptions are caught; state is restored in `finally`. Remaining risk: C extension crash or `os._exit()` can still affect the process, so list only trusted skills. |
| **Timeout** | `run_skill_timeout` (config, default 60s) is applied. A stuck script is aborted and the tool returns an error string. |
| **Executor try/except** | The run_skill executor catches `BaseException` (and re-raises `KeyboardInterrupt`/`SystemExit` so Ctrl+C and process exit still work). Any other exception is returned as `"Error: ..."`. |

---

## 3. Plugins (route_to_plugin)

**Built-in (inline) plugins** (e.g. ppt-generation, News): run **in the same process as Core**. They are Python objects; `route_to_plugin` calls `plugin.run()` or a capability method with `await` in Core’s event loop. There is no subprocess; exceptions and timeouts are the only containment.

**External plugins** (type http / subprocess / MCP): run **in a separate process or service**. `plugin_manager.run_external_plugin()` invokes them over HTTP or via a subprocess; a crash there does not affect Core.

| Mechanism | How it keeps Core stable |
|-----------|---------------------------|
| **Try/except** | The entire plugin invocation (inline or external) is inside a `try`. Any exception is caught and returned as `"Error running plugin: ..."`. `KeyboardInterrupt` and `SystemExit` are re-raised so the process can exit normally. |
| **Config restore** | When calling a capability method, `plugin.config` is restored in a `finally` block so a plugin exception does not leave the plugin in a bad state. |
| **Inline plugins** | Run in Core’s process; use try/except and timeouts. No isolation from Core. |
| **External plugins** | HTTP/subprocess/MCP plugins run in separate processes; a crash there does not affect Core. |

---

## 4. Tool execution in Core

Core wraps **all** tool calls (including run_skill and route_to_plugin) in:

- **Timeout:** `tool_timeout_seconds` (config) when > 0; otherwise no extra timeout (run_skill still has its own timeout).
- **Exception handling:** `asyncio.TimeoutError` and `Exception` are caught and converted to an error string for the model.

So even if a tool executor were to raise, Core would catch it and continue.

---

## 5. Recommendations

- **Leave run_skill_py_in_process_skills empty** (or list only trusted skills) so Python skills run in subprocess by default and cannot crash Core.
- **Skills:** Avoid `os._exit()`, uncaught exceptions, or infinite loops; use timeouts and return clear error messages.
- **Plugins:** Wrap risky work in try/except and return error strings; do not raise into Core.
