"""
Entry point: main() and Windows console Ctrl handler for Core.
Extracted from core/core.py (Phase 8 refactor). main() uses lazy import of Core to avoid circular import.
"""

import asyncio
import os
import sys
import time
from loguru import logger

# Set by Core.__enter__ (in core.core) so Windows console Ctrl handler can trigger shutdown.
_core_instance_for_ctrl_c = None
# When Core runs in a daemon thread (python -m main start), ignore CTRL_C_EVENT in the first N seconds.
_core_ctrl_handler_ready_time = None
_CORE_CTRL_GRACE_SEC = 5.0


def _win_console_ctrl_handler(event):
    """Windows-only: handle Ctrl+C so shutdown works when Python signal is not delivered. Second Ctrl+C = force exit."""
    if event == 0:  # CTRL_C_EVENT
        core = _core_instance_for_ctrl_c
        if core is None:
            return False
        if getattr(core, "_shutdown_started", False):
            try:
                print("\nForce exit (second Ctrl+C).", flush=True)
            except Exception:
                pass
            os._exit(1)
        global _core_ctrl_handler_ready_time
        if _core_ctrl_handler_ready_time is not None:
            try:
                elapsed = time.time() - _core_ctrl_handler_ready_time
                if elapsed < _CORE_CTRL_GRACE_SEC:
                    return True  # ignore (don't shutdown)
            except Exception:
                pass
        core._shutdown_started = True
        try:
            print("\nShutting down (press Ctrl+C again to force exit)... 正在关闭...", flush=True)
            core.stop()
            time.sleep(2.0)
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            sys.exit(0)
        return True
    return False


def main():
    """Run Core: event loop, Core context, run(). Used by main.py (core.main) and python -m core.core."""
    try:
        import google.genai as _  # noqa: F401
        _google_ok = "ok"
    except Exception:
        _google_ok = "missing"
    print("Core startup: Python=%s ; google.genai=%s" % (sys.executable, _google_ok), file=sys.stderr, flush=True)
    loop = None
    core = None
    try:
        from core.core import Core
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with Core() as core:
            loop.run_until_complete(core.run())
    except KeyboardInterrupt:
        if core is not None:
            try:
                core.stop()
            except Exception:
                pass
        sys.exit(0)
    except Exception as e:
        logger.exception(e)
    finally:
        if loop is not None:
            if core is not None and getattr(core, "server", None) is not None:
                try:
                    core.server.should_exit = True
                    core.server.force_exit = True
                    loop.run_until_complete(asyncio.sleep(0.5))
                except Exception:
                    pass
            loop.close()
