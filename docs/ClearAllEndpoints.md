# Clear everything: curl commands

Based on **config/core.yml** (`host: 0.0.0.0`, `port: 9000`). Use `127.0.0.1:9000` (or `localhost:9000`) for curl.

If **auth_enabled** is true in config, add: `-H "X-API-Key: YOUR_API_KEY"` or `-H "Authorization: Bearer YOUR_API_KEY"` to each request.

---

## 1. Memory (conversation + agent memory + daily memory)

```bash
curl -X POST "http://127.0.0.1:9000/memory/reset"
# or
curl -X GET "http://127.0.0.1:9000/memory/reset"
```

Clears: memory backend store; AGENT_MEMORY.md (if use_agent_memory_file); yesterday/today daily memory files (if use_daily_memory).

---

## 2. Knowledge base (all users, all documents)

```bash
curl -X POST "http://127.0.0.1:9000/knowledge_base/reset"
# or
curl -X GET "http://127.0.0.1:9000/knowledge_base/reset"
```

Clears: all saved documents/web/notes in the knowledge base.

**If you get "Knowledge base not enabled or not initialized":** The KB is enabled in config but failed to initialize at startup. **To see why it failed:** restart Core and check the **startup logs** for a line like `Knowledge base (Cognee) not initialized: <reason>` — the full exception and traceback are logged there. **Common causes:** (1) Cognee not installed → run `pip install cognee`; (2) **main_llm** or **embedding_llm** not set in config → Core cannot fill Cognee’s LLM/embedding endpoints; (3) Cognee DB/vector/graph (the **cognee:** section) not reachable or misconfigured. Fix the cause and restart Core.

---

## 3. Skills (vector store only)

```bash
curl -X POST "http://127.0.0.1:9000/api/skills/clear-vector-store"
```

Clears: all skills in the skills vector store (no skills retrieved until next sync/restart).

---

## 4. Plugins (unregister all external plugins)

```bash
curl -X POST "http://127.0.0.1:9000/api/plugins/unregister-all"
```

Clears: all API-registered external plugins (e.g. homeclaw-browser if registered via API). Built-in/folder plugins remain.

---

## 5. One call: plugins + skills (testing)

```bash
curl -X POST "http://127.0.0.1:9000/api/testing/clear-all"
```

Clears: all external plugins (unregister-all) and the skills vector store. Does **not** clear memory or knowledge base.

---

## Clear everything (run all)

```bash
# Memory
curl -X POST "http://127.0.0.1:9000/memory/reset"

# Knowledge base
curl -X POST "http://127.0.0.1:9000/knowledge_base/reset"

# Plugins + skills (one call)
curl -X POST "http://127.0.0.1:9000/api/testing/clear-all"
```

**Note:** There is no API to "clear tools". Tools are the built-in registry (exec, run_skill, route_to_plugin, etc.) and are not stored data; they are always loaded from code.

---

## Different host/port

Replace `127.0.0.1` and `9000` with your core host and port, e.g.:

```bash
curl -X POST "http://YOUR_HOST:YOUR_PORT/memory/reset"
curl -X POST "http://YOUR_HOST:YOUR_PORT/knowledge_base/reset"
curl -X POST "http://YOUR_HOST:YOUR_PORT/api/testing/clear-all"
```
