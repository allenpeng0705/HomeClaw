# Claw-Code operator checklist

Short path from **zero** to **first agent turn** on a self-hosted Core. For threat model, TLS, and API keys, see [clawcode-ui-security.md](clawcode-ui-security.md).

---

## 1. Prerequisites

1. **Core running** on your usual URL (default `http://127.0.0.1:9000`).
2. In **`config/core.yml`**, enable Claw-Code and constrain workspaces:

   - `clawcode.enabled: true`
   - Optional but recommended: `clawcode.allowed_roots` — list of directories sessions may use as `cwd` (sessions reject paths outside these roots).

3. **Auth:** If Core uses `auth_enabled`, have the **API key** ready for REST and `/inbound`.

4. **Owner id:** Decide the Core **`owner_user_id`** for the session. It must be the same id you send as `user_id` on `/inbound` and as `owner_user_id` on Claw-Code APIs — typically your entry in **`config/user.yml`** (e.g. `webchat_user`, or a Companion login id). IM channels often resolve to ids like `telegram_<chat_id>`; bindings must use the id Core actually uses after permission resolution.

---

## 2. Create a session

**CLI (recommended):**

```bash
conda activate pytorch   # or your env matching requirements.txt
python3 -m main clawcode login --url http://127.0.0.1:9000 --key YOUR_API_KEY --owner YOUR_USER_ID
python3 -m main clawcode session new --cwd /absolute/path/to/project
```

Note the printed **`clawcode_session_id`** (UUID).

**Alternative:** `POST /api/clawcode/sessions` with JSON `{ "owner_user_id": "…", "cwd": "/abs/path" }` (same auth as other Claw-Code routes).

---

## 3. Attach the session to how you chat

Pick **one** (or combine explicit session id + user id where the client supports it).

| How you interact | What to do |
|------------------|------------|
| **Web UI** | Open **`http://<core-host>:9000/clawcode`** (same port as Core). Set API key / user id in the page. *Optional:* WebChat on 8014 also serves `/clawcode` if you run the channel. |
| **Companion app** | Add **`Clawcode`** (or any name) with **`preset: clawcode`** in `user.yml` (same idea as Cursor/ClaudeCode). Open that friend in the list → **terminal** or **More → Claw-Code** → pick a session → use the **normal composer**. Core gets `clawcode_session_id`, **`friend_id`**, and `user_id` = session `owner_user_id`. Approvals / files / browser: **Approvals, workspace, browser…** in the sheet. |
| **Telegram / Discord / Slack** | Either send **`/clawcode bind <session_uuid>`** (Discord: `!clawcode bind …`) with the channel identity already allowed in `user.yml`, or **`PUT /api/clawcode/channel-bindings`** with `owner_user_id` = that Core user id and `clawcode_session_id` = UUID. Then normal messages on that channel include the bound session. |
| **Webhook / other channels** | If the channel uses `apply_clawcode_inbound_flow`, set binding via API as above, or include `clawcode_session_id` in the JSON body to Core **`POST /inbound`** together with the correct **`user_id`**. |

**Validation rule:** Core checks that the session’s **`owner_user_id`** matches the inbound **`user_id`** or resolved **`system_user_id`**. If it does not match, you get **403** (session access denied).

---

## 4. First message (run a turn)

| Client | Action |
|--------|--------|
| **CLI** | `python3 -m main clawcode run --session <UUID> "Your task"` (add `--stream` if you want SSE-style progress where supported). |
| **Web `/clawcode`** | Type in the run box and send; ensure `user_id` matches the session owner. |
| **Companion** | Main chat with a bound session — send like any other message. (Optional: tools screen compose box.) |
| **Bound IM channel** | Send a normal message (not a `/clawcode` command line). |

**Tool approvals:** If a tool is gated, approve or reject from the Web UI, Companion **Claw-Code tools** screen (from the chat session picker), or CLI (`clawcode approvals list` / `resolve`).

---

## 5. After the first run

- **Success:** Core updates the session file (`last_run_id`, `last_usage`, clears `last_run_error`).
- **Failure:** Web or Companion may PATCH **`last_run_error`**; the next turn’s system prompt can include that note. Use **Plan & recovery** (Web or Companion) to edit **`task_plan`**, **`checkpoint`**, **`resume_hint`** when you use that workflow.
- **MCP:** Use **`GET /api/clawcode/mcp/servers`** and **`POST /api/clawcode/mcp/health`** (or the Companion **MCP** sheet) to verify configured servers; health probes can be slow.

---

## 6. Quick reference

| Goal | Command or route |
|------|-------------------|
| CLI help | `python3 -m main clawcode --help` |
| List sessions | `python3 -m main clawcode session list` |
| Rebind cwd | `python3 -m main clawcode session rebind --session UUID --cwd /new/path` |
| API sketch | `docs_design/ClawCode_API_Sketch.md` |
| OpenAPI | `docs/openapi/clawcode.yaml` |

---

## 7. Common mistakes

- **403 session access denied** — `user_id` on `/inbound` does not match the session’s `owner_user_id` (and does not match `system_user_id` after Core resolves the user).
- **404 Claw-Code API disabled** — `clawcode.enabled` is false in `core.yml`.
- **400/403 cwd** — New or rebound `cwd` is not under `allowed_roots`, or directory does not exist on the **Core host** (not on your laptop if Core runs elsewhere).
- **Empty sessions in Companion** — No sessions for that `owner_user_id`; create one with the CLI/API using the **same** owner id as the logged-in Companion user.
