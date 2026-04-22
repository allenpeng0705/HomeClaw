---
name: feishu-cli
description: |
  Run Feishu / Lark official CLI (lark-cli) from HomeClaw: messages, docs, calendar, mail, Bitable, etc. If lark-cli is missing on the Core host, the runner runs `npx --yes @larksuite/cli@latest install` once (needs Node + npx on PATH), then resolves the binary again. Set LARK_CLI_AUTO_INSTALL=0 to disable. App config (`config init`) and optional user OAuth still manual. Not retry-safe — may send messages or write data.
homepage: https://open.feishu.cn/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu
keywords: "feishu 飞书 lark lark-cli feishu-cli 云文档 日历 多维表格 妙记 邮箱 群消息"
trigger:
  patterns:
    - "feishu|飞书|lark\\s*cli|lark-cli|飞书cli|用飞书|在飞书"
  instruction: |
    The user wants Feishu/Lark operations via the official CLI.

    1) If unsure the CLI is installed, run:
       run_skill(skill_name='feishu-cli-1.0.0', script='lark_cli_runner.py', args=['discover'])
    2) For read-only checks: auth status / help / schema snippets, e.g.
       run_skill(skill_name='feishu-cli-1.0.0', script='lark_cli_runner.py', args=['exec', 'auth', 'status'])
       run_skill(skill_name='feishu-cli-1.0.0', script='lark_cli_runner.py', args=['exec', 'help'])
    3) For real work (calendar +agenda, im +messages-send, docs +create, calendar API list, schema, api, sheets/base/mail/wiki, etc.), pass the same argv as after `lark-cli` — see body section "Real work — user intent → what the model should do" for copy-paste-style examples from upstream README.
       run_skill(skill_name='feishu-cli-1.0.0', script='lark_cli_runner.py', args=['exec', '<subcommand>', ...])
    Do not invent flags; prefer `exec help` then `exec <subcommand> --help` when uncertain.

    Natural-language → argv: see "Example user intent → run_skill" and the "Real work" table (English and Chinese).

    Remind the user: the Core host needs Node+npx for auto-install of the CLI; then `lark-cli config init` and optional `lark-cli auth login`. See README.md.
---

# Feishu / Lark CLI (`feishu-cli-1.0.0`)

Wrapper around the **official Feishu / Lark CLI** so the agent can operate Feishu from HomeClaw via **`run_skill`**.

- **Upstream docs:** [飞书 CLI（Feishu CLI）](https://open.feishu.cn/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu) — install, auth, capability map (messages, docs, calendar, mail, Bitable, …).
- **Source:** [larksuite/cli](https://github.com/larksuite/cli) on GitHub.

## Natural language in HomeClaw

Users do **not** type `run_skill`. They ask in normal language (“Is Feishu CLI installed?”, “帮我查飞书登录状态”). The **model** picks this skill when **`trigger.patterns`** / **`keywords`** / the skill list match, then builds **`args`** for **`lark_cli_runner.py`**.

Important differences from skills that take a single free-text query:

- **`args`** is a **token list**: `["exec", "auth", "status"]` is exactly **`lark-cli` `auth` `status`** (no shell; no quotes inside one token unless the CLI expects a literal quote).
- For **write/send** flows, **do not guess** flags or IDs. Use **`exec help`**, then **`exec <subcommand> --help`**, then the smallest argv the help text shows. Subcommands change between CLI versions—**README.md** and **USAGE.md** stay conservative.

## Example user intent → `run_skill`

Same pattern for every row: **`run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=[...])`**.

### Safe / diagnostic (start here)

| User intent (examples) | `args` |
|------------------------|--------|
| “Is `lark-cli` available on Core?” / “飞书 CLI 在服务器上装好了吗？” | `["discover"]` |
| “Show Feishu CLI help” / “飞书命令行有哪些命令？” | `["exec", "help"]` |
| “Am I logged in to Feishu from this machine?” / “飞书 OAuth 登录了吗？” | `["exec", "auth", "status"]` |
| “Check Feishu app / user permissions” / “查一下飞书权限够不够” | `["exec", "auth", "check"]` |
| “What does the `schema` command do?” (explore only) | `["exec", "schema", "--help"]` |
| “List options for a subcommand” (name taken from `exec help`) | `["exec", "<name>", "--help"]` — replace the second token with a subcommand listed by `exec help` |

### Operator setup (still on Core; user may ask in chat)

The runner **cannot** complete interactive **`config init`** / **`auth login`** for the user. The model can **document** the steps and, where non-interactive flags exist in their CLI version, forward them:

| User intent | Typical `args` (verify with `--help` first) |
|-------------|---------------------------------------------|
| “Run Feishu app configuration” | Often manual terminal: `lark-cli config init`. If the CLI supports non-interactive flags, use `["exec", "config", ...]` exactly as documented. |
| “Start Feishu user login / OAuth” | Usually manual: `lark-cli auth login`. |

### Real work — user intent → what the model should do

Upstream **`lark-cli`** documents a **three-layer** style: **shortcuts** (often `+name` after a domain), **API-style** commands (`domain subcommand …`), **`api`** for raw HTTP, and **`schema`** for parameter shapes ([larksuite/cli README](https://github.com/larksuite/cli)). Commands evolve—always confirm with **`exec <…> --help`** on the Core host before high-impact calls.

**Defaults for side effects:** Prefer **`--dry-run`** when the command supports it (e.g. message send). Use **`--format pretty`** or **`table`** when explaining output to a human. Use **`--as user`** / **`--as bot`** when identity matters (see upstream auth docs).

| User intent (examples) | What the model should do (typical `args` — verify with `--help`) |
|------------------------|---------------------------------------------------------------------|
| “What’s on my calendar today?” / “今天飞书日程” / “Lark agenda” | `["exec", "calendar", "+agenda"]` — often with identity: `["exec", "calendar", "+agenda", "--as", "user"]` |
| “Send *Hello* to chat `oc_xxx`” / “给群 oc_xxx 发一条文字消息” | Preview: `["exec", "im", "+messages-send", "--chat-id", "oc_xxx", "--text", "Hello", "--dry-run"]` then same without `--dry-run` if OK. Send **as bot**: `["exec", "im", "+messages-send", "--as", "bot", "--chat-id", "oc_xxx", "--text", "Hello"]` (see upstream **Authentication** examples). |
| “Create a Feishu Doc from Markdown titled …” / “用 Markdown 新建飞书文档” | `["exec", "docs", "+create", "--title", "Weekly Report", "--markdown", "# Progress\n- Done item"]` — adjust title/body to the user; escape newlines as `\n` inside the single `--markdown` token. |
| “List my calendars (API-style)” | `["exec", "calendar", "calendars", "list"]` |
| “Show busy / instance view for a time range” | Build JSON for **`--params`** as **one argv token** (per upstream), e.g. `["exec", "calendar", "events", "instance_view", "--params", "{\"calendar_id\":\"primary\",\"start_time\":\"1700000000\",\"end_time\":\"1700086400\"}"]` — replace times/ids from the user or from a prior list call. |
| “Inspect parameters for a calendar API method” | `["exec", "schema", "calendar.events.instance_view"]` — swap method id from **`exec schema --help`** / docs. |
| “Call an Open Platform endpoint directly” | Raw: `["exec", "api", "GET", "/open-apis/calendar/v4/calendars"]` or `["exec", "api", "POST", "/open-apis/im/v1/messages", "--params", "…", "--data", "…"]` — **only** after **`exec api --help`**; **`--data`/`--params`** are usually one string token each with valid JSON. |
| “Work with Sheets / 电子表格” | Run `["exec", "sheets", "--help"]` (or `exec help` and pick the sheets entry), then e.g. create/read/append per help — upstream lists create/read/write/append/find/export. |
| “Bitable / 多维表格 / Base” | `["exec", "base", "--help"]` then tables/records/views per help (upstream **Base** domain). |
| “Wiki / 知识库” | `["exec", "wiki", "--help"]` then space/node operations per help. |
| “Mail / 邮箱” | `["exec", "mail", "--help"]` — browse/search/read/send per help and scopes. |
| “Tasks / 任务” | `["exec", "task", "--help"]` (name may vary slightly by version). |
| “Meeting minutes / 妙记 / VC” | `["exec", "vc", "--help"]` or search help output for **minutes** / **meeting** skills (upstream **Meetings** / **Minutes**). |
| “Search contacts / 按邮箱找人” | `["exec", "contact", "--help"]` — upstream documents search by name/email/phone. |
| “Approvals / 审批” | `["exec", "approval", "--help"]` — query/approve/reject per help and tenant policy. |
| “Pull everything across pages” | Add flags from upstream when supported, e.g. **`--page-all`**, **`--page-limit`**, **`--page-delay`** (see README **Pagination**). |
| “Machine-readable output for scripting” | Append **`--format json`** (or **`ndjson`**, **`csv`**) where the command supports **Output formats** in upstream docs. |

**Note:** The upstream project also documents **`npx skills add larksuite/cli`** so the CLI loads packaged **Agent Skills**; HomeClaw only wraps the binary. If a shortcut is missing, run **`exec help`** on Core and align with the installed version.

### English phrases that should still match this skill

Examples: *“Use Lark CLI to …”*, *“Run lark-cli auth status”*, *“Feishu open platform from the command line”* — all map to **`discover`** / **`exec`, …** as above.

## Prerequisites (on the Core host)

1. **Node.js** on the Core host so **`npx`** exists; otherwise install the CLI manually and set **`LARK_CLI`**. If `lark-cli` is missing, the skill runs **`npx --yes @larksuite/cli@latest install`** once (disable with **`LARK_CLI_AUTO_INSTALL=0`**).
2. After install, **`lark-cli`** should be on `PATH` or discoverable under the npm prefix; or set **`LARK_CLI`** to the full path.
3. **`lark-cli config init`** — create or bind a Feishu/Lark open-platform app.
4. Optional **user OAuth** (personal calendar, DMs, …): `lark-cli auth login` once on that host (browser flow).
5. International **Lark** tenants: configure via `config init` for Lark endpoints (see official FAQ).

## `run_skill` (script: `lark_cli_runner.py`)

| Intent | Example `args` |
|--------|------------------|
| See which binary is used | `["discover"]` |
| Forward to CLI (same as `lark-cli …`) | `["exec", "help"]` |
| Auth status | `["exec", "auth", "status"]` |
| Auth permission check | `["exec", "auth", "check"]` |
| Inspect `schema` command | `["exec", "schema", "--help"]` |
| Arbitrary CLI (after you know argv) | `["exec", "<subcommand>", "<flag>", "value"]` — one list element per argv token |

Everything after **`exec`** is passed **verbatim** to `lark-cli` (no shell). The model must pass **one string per argv token** (same as a normal argv list).

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "help"])
```

## Environment (optional)

| Variable | Meaning |
|----------|---------|
| `LARK_CLI` | Full path to CLI if not named `lark-cli` / `feishu-cli` on `PATH` |
| `LARK_CLI_AUTO_INSTALL` | If unset or `1`/`true`: when CLI is missing, run `npx --yes @larksuite/cli@latest install` once. Set to `0`/`false`/`no`/`off` to disable. |
| `LARK_CLI_INSTALL_TIMEOUT_SEC` | Timeout for the install step (default `600`). |
| `LARK_CLI_TIMEOUT_SEC` | Timeout for each `exec` … CLI run (default `180`) |

## Safety

- **Do not** set `retry_safe: true` for this skill — CLI calls can send messages, create docs, or send mail.
- Tenant policy and app scopes still apply (Feishu admin controls).
- Prefer **`discover`** and **`exec … --help`** before destructive or high-volume operations.

## More docs

- **`README.md`** — install, auth, troubleshooting, cron ideas.
- **`USAGE.md`** — copy-paste examples for operators and agents.
