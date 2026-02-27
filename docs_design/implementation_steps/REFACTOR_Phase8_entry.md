# Core.py refactor — Phase 8: Extract entry point (main, Windows Ctrl handler)

**Status:** Done (8.1); 8.2 optional  
**Branch:** refactor/core-multi-module (or as created)

## Goal

Move `main()` and the Windows console Ctrl handler (and related globals) from `core/core.py` into `core/entry.py`. Ensure `core.main` and `python -m core.core` still work. main.py uses `core.main` (from `from core import core`).

## Changes

### 1. New file: core/entry.py

- **Globals:**  
  `_core_instance_for_ctrl_c`, `_core_ctrl_handler_ready_time`, `_CORE_CTRL_GRACE_SEC` — set/cleared by Core.__enter__/__exit__ in core.py so the Windows handler can trigger shutdown.

- **_win_console_ctrl_handler(event)**  
  Windows-only: handles CTRL_C_EVENT; uses the globals above. Second Ctrl+C forces exit. No top-level import of core.core (avoids circular import).

- **main()**  
  Prints startup line (Python, google.genai), then does **lazy** `from core.core import Core` and runs the same logic as before: new event loop, `with Core() as core`, `loop.run_until_complete(core.run())`, KeyboardInterrupt/cleanup. Lazy import ensures loading core.entry does not load core.core, so core.core can safely `from core.entry import main`.

### 2. core/core.py

- **Import:** `from core.entry import main` (at top with other core.* imports).
- **Core.__enter__:**  
  Instead of module-level globals, uses `import core.entry as _entry` and sets `_entry._core_instance_for_ctrl_c = self`, `_entry._core_ctrl_handler_ready_time = time.time()`, and on Windows registers `_entry._win_console_ctrl_handler` (and sets `_entry._win_console_ctrl_handler._handler` for the ctypes wrapper).
- **Core.__exit__:**  
  Clears `_entry._core_instance_for_ctrl_c` and `_entry._core_ctrl_handler_ready_time`, unregisters the Windows handler.
- **Removed:** The old `def main()`, the three globals, `def _win_console_ctrl_handler`, and the `if __name__ == "__main__": main()` body.
- **Kept at end:** `if __name__ == "__main__": main()` so `python -m core.core` and `python core/core.py` still invoke main.

## Logic and stability

- **Logic:** Unchanged; only location of main/handler/globals and __enter__/__exit__ wiring to entry module.
- **Circular import:** Avoided by having main() import Core only inside main(), so core.entry does not import core.core at import time.
- **main.py:** Still does `from core import core` and `core.main`; core.core re-exports main from core.entry, so behavior is unchanged.
- **Platforms:** Windows Ctrl handler and grace period unchanged; macOS/Linux unchanged.

## Testing

- **test_entry_module:** core.entry has main, _win_console_ctrl_handler, and the globals (entry does not pull in torch).
- **test_core_module_exposes_main:** core.core has callable main (may load heavy deps).
- **Manual:** `python -m main start` and `python -m core.core` both start Core; Ctrl+C shuts down; on Windows, second Ctrl+C force-exits.

## Phase 8.2 (final pass)

- **get_system_context_for_plugins** moved from core.py to **core.session_channel** as `get_system_context_for_plugins(core, system_user_id, request)`. Core keeps a one-line delegator. Callers (e.g. tools/builtin.py via `core.get_system_context_for_plugins`) unchanged.
- **core.py:** Removed commented `#import logging`. Added class docstring on Core: "Singleton. Attributes set in __init__; most methods delegate to core.* modules."
- **Tests:** test_session_channel_module now asserts get_system_context_for_plugins is present and callable.

No further extractions in 8.2; other methods (run, process_text_message, memory summarization, etc.) remain in Core as they are tightly coupled to Core state or are already thin. Full regression: run pytest and manual smoke (start Core, one message, tools).

## Summary

Phase 8.1 moves the entry point (main + Windows handler + globals) into core/entry.py. core.core imports main and keeps `if __name__ == "__main__": main()`; Core.__enter__/__exit__ wire the Windows handler via core.entry. main.py and `python -m core.core` continue to work as before.
