# Common startup logs

This note explains log lines you may see when starting Core. None of these indicate a failure if the system then runs normally.

## Cognee

At startup you may see structlog lines like:

```
[info] Logging initialized [cognee.shared.logging_utils] cognee_version=0.5.2 database_path=... graph_database_name= ...
[info] Database storage: ...
```

**Meaning:** Cognee (memory/graph backend) is initializing its logging and database paths. This is normal.

## "Task was destroyed but it is pending!"

On Windows you may see:

```
Task was destroyed but it is pending!
task: <Task pending ... coro=<IocpProactor.accept.<locals>.accept_coro() running at ... windows_events.py ...>
```

**Meaning:** Python’s asyncio (with the Windows `IocpProactor` event loop) is reporting that a TCP “accept” coroutine was still pending when something closed or cleaned up. This often happens during startup or shutdown because of how the Proactor handles the listening socket.

**Is it a problem?** Usually no. If Core starts and responds (e.g. GET /ready returns 200, or the UI loads), you can ignore this message. It’s a known asyncio/Windows quirk rather than a bug in your code. If the process actually crashes or fails to serve requests, the cause is elsewhere (check the traceback or error that follows).

**Optional:** To reduce log noise you can raise the asyncio logger level (e.g. in your logging config), but that may hide other asyncio warnings, so only do it if you’re sure you don’t need those messages.

---

## Crash when browser opens (Windows, “Task was destroyed … Server.serve()”)

**Symptom:** You run `python -m main start`, the browser opens for `/ui`, and the command line then shows “Task was destroyed but it is pending! … Server.serve()” and Core stops.

**Cause:** When Core is started from `main.py` in a **daemon thread**, it used to register the Windows console Ctrl handler (and overwrite main’s SIGINT). Opening the default browser on Windows can trigger a console control event; that called `exit_gracefully()`, which shut down Core and closed the event loop while the uvicorn server task was still running.

**Fix (in code):**

1. **Windows Ctrl handler with grace period**  
   On Windows we always register `SetConsoleCtrlHandler` so Ctrl+C works when Core runs from `python -m main start` (daemon thread). To avoid the browser-open spurious event killing the process, we ignore `CTRL_C_EVENT` in the first **5 seconds** after Core starts; after that, Ctrl+C runs the handler: it prints “Shutting down…”, calls `core.stop()`, waits 2s, then `os._exit(0)`.

2. **Clean loop shutdown**  
   In `core.main()`’s `finally`, before `loop.close()`, Core sets `server.should_exit` and `server.force_exit` and runs the loop for 0.5s so the uvicorn `Server.serve()` task can exit. That avoids “Task was destroyed but it is pending!” when the loop is closed for any reason.

**Ctrl+C:** After the 5-second grace period, the first Ctrl+C starts shutdown (same as before). **Second Ctrl+C = force exit 100%** (same as old Core): if shutdown is slow (e.g. plugin cleanup), press Ctrl+C again to exit immediately with `os._exit(1)`.

---

## Core stuck at "core initializing..."

**Symptom:** Log shows "core initializing..." and never reaches "core init: vector_store done" (or later steps); the web UI may not become ready (GET /ready stays 503).

**Semaphore:** The LLM/embedding semaphores (`_get_llm_semaphore`, `llm_max_concurrent_local` / `llm_max_concurrent_cloud`) are **not** used during `initialize()`. They are only used when handling requests (e.g. `openai_chat_completion`, classifier). So the block is **not** caused by semaphore logic.

**Likely causes:**

1. **Port already in use** (e.g. 5024 for main LLM, or embedding port). The LLM/embedding server fails to bind; then Cognee or other init may try to connect and hang. Fix: free the port or change the port in `config/core.yml`.
2. **Cognee init** – When `memory_backend: cognee`, `CogneeMemory(config=...)` runs and `import cognee` can trigger Cognee’s own DB/LLM/embedding setup. If the embedding or LLM endpoint is unreachable (e.g. wrong port or server not bound), Cognee may block. Fix: ensure embedding/LLM ports are free and reachable, or temporarily set `memory_backend: chroma` to skip Cognee.
3. **Chroma / vector store** – `initialize_vector_store` or Chroma client creation can block if the DB path is locked or slow. Less common.

**Progress logs:** Core logs "core init: vector_store done", "embedder done", "knowledge_base done", "creating Cognee memory...", "Cognee memory done" after each step. The **last** of these that appears in the log is where init is stuck.
