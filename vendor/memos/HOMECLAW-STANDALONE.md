# MemOS standalone server for HomeClaw

This directory holds **MemOS** ([memos-local-openclaw](https://github.com/MemTensor/MemOS/tree/main/apps/memos-local-openclaw)) plus a small **standalone HTTP server** so HomeClaw can use MemOS memory without running OpenClaw.

## 1. Install (automatic)

**install.sh** and **install.ps1** (and **install.bat** on Windows) set up MemOS as a built-in module:

- If `vendor/memos/server-standalone.ts` exists but the MemOS app source is missing, the installer clones MemOS and copies `apps/memos-local-openclaw` into `vendor/memos` (without overwriting `server-standalone.ts`, this doc, or the example config).
- It adds the `standalone` script to `package.json` and runs `npm install`.

So after a normal HomeClaw install, you should have:

- `vendor/memos/src/` (MemOS core)
- `vendor/memos/package.json` (with `"standalone": "tsx server-standalone.ts"`)
- `vendor/memos/server-standalone.ts` (this repo’s server)
- `vendor/memos/HOMECLAW-STANDALONE.md` (this file)

## 2. Manual setup (if you skipped install or vendor/memos was incomplete)

Copy the MemOS app source here so that `src/`, `package.json`, etc. sit next to `server-standalone.ts`:

```bash
git clone --depth 1 https://github.com/MemTensor/MemOS.git /tmp/MemOS
cp -r /tmp/MemOS/apps/memos-local-openclaw/* vendor/memos/
# Do not overwrite server-standalone.ts or this doc. Then:
cd vendor/memos && npm install
```

Add to `package.json` under `"scripts"`: `"standalone": "tsx server-standalone.ts"`. If `tsx` is missing: `npm install -D tsx`.

## 3. Config

Copy the example config and edit:

```bash
cp memos-standalone.json.example memos-standalone.json
```

Set `embedding` and `summarizer` to your local LLM/embedding endpoints (or use `provider: "local"` for embedding). The server reads `memos-standalone.json` from the current working directory, or set `MEMOS_CONFIG=/path/to/memos-standalone.json`.

## 4. Run the standalone server

**Auto-start (default):** When `memory_backend` is `memos` or `composite` and `memos.url` is local (e.g. `http://127.0.0.1:39201`), HomeClaw Core **starts the MemOS server automatically** if it is not already running (see `memos.auto_start` in `config/memory_kb.yml`). No need to run the server by hand unless you want to run it separately or disable auto-start.

**Manual run:**

```bash
cd vendor/memos
MEMOS_STANDALONE_PORT=39201 npm run standalone
```

To also start the **Memory Viewer** (web UI for tasks/skills/memories), set `MEMOS_VIEWER_PORT` (e.g. 18799):

```bash
MEMOS_STANDALONE_PORT=39201 MEMOS_VIEWER_PORT=18799 npm run standalone
```

Default API port is **39201** (or set `MEMOS_STANDALONE_PORT`). The server exposes:

- `GET /health` — readiness
- `POST /memory/add` — add messages (body: `{ messages, sessionKey?, agentId? }`)
- `POST /memory/search` — search (body: `{ query, maxResults?, minScore?, agentId? }`)
- `GET /memory/task/:id/summary` — task summary (Goal, Key Steps, Result, Key Details)
- `POST /memory/skill_search` — skill search (body: `{ query, scope?, agentId? }`)
- `GET /memory/skill/:id` — skill metadata + SKILL.md content
- `GET /memory/tasks` — list tasks (query: `agentId?`, `status?`, `limit?`, `offset?`)
- `POST /memory/write_public` — write public memory (body: `{ content, summary? }`)
- `PUT /memory/skill/:id/visibility` — set skill visibility (body: `{ visibility: "public"|"private" }`)
- `POST /memory/reset` — clear all memories (and tasks/skills if the store supports it). Used when HomeClaw calls **Clear memory** (/memory/reset). The store (e.g. `SqliteStore`) must implement `reset()` for this to clear data; otherwise the server returns 501.

## 5. Use from HomeClaw

In `config/memory_kb.yml` set:

```yaml
memory_backend: memos
memos:
  url: http://127.0.0.1:39201
  timeout: 30
```

Core will auto-start the MemOS server when `memos.url` is local and `memos.auto_start` is true (default). Otherwise start the server manually (step 4), then start Core.

HomeClaw tools when MemOS is in use (`memory_backend: memos` or `composite`): **memory_task_summary**, **memory_skill_search**, **memory_skill_get**, **memory_task_list**, **memory_write_public**, **memory_skill_publish**, **memory_skill_unpublish**. Optional: set `memos.viewer_port` in `memory_kb.yml` (e.g. 18799) so the agent can tell users the Memory Viewer URL.
