# Platform

Config, deployment, and multi-user behavior.

---

## Configuration files

| File | Purpose |
|------|---------|
| **`config/core.yml`** | Core host/port, `main_llm`, `embedding_llm`, `local_models`, `cloud_models`, `use_memory`, `use_tools`, `use_skills`, memory backend (Cognee/Chroma), `tools.*`, auth, etc. |
| **`config/user.yml`** | Allowlist of users: `name`, `id`, `email`, `im`, `phone`, `permissions`. Required for channels. |
| **`channels/.env`** | `CORE_URL` (e.g. `http://127.0.0.1:9000`), bot tokens (e.g. `TELEGRAM_BOT_TOKEN`). |
| **`config/email_account.yml`** | IMAP/SMTP for the email channel (if used). |

---

## Multi-user

Chat history, memory, and profile are **keyed by system user id** (from `config/user.yml`). Each user has isolated data. Add users under **`users:`** in `config/user.yml` with the correct `im` / `email` / `phone` for the channel. See [MultiUserSupport.md](../docs_design/MultiUserSupport.md) in the repo.

---

## Memory backend

- **Default:** **Cognee** (SQLite + Chroma + Kuzu by default; configurable to Postgres, Qdrant, Neo4j via Cognee).
- **Alternative:** **Chroma** (in-house): set `memory_backend: chroma` in `config/core.yml`; configure `database`, `vectorDB`, `graphDB` there. See [MemoryAndDatabase.md](../docs_design/MemoryAndDatabase.md) in the repo.

---

## Remote access and auth

If you expose Core on the internet, set **`auth_enabled: true`** and **`auth_api_key`** in `config/core.yml`. Clients must send **`X-API-Key`** or **`Authorization: Bearer <key>`** on `/inbound` and `/ws`. See [RemoteAccess.md](../docs_design/RemoteAccess.md) in the repo. Use Tailscale or SSH for secure access when needed.
