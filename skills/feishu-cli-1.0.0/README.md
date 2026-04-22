# Feishu / Lark CLI skill — operator guide

This skill runs the **Feishu / Lark official CLI** (`lark-cli`) on the **same machine as HomeClaw Core** (where `run_skill` executes subprocesses).

## Official references

- [飞书 CLI：给 Agent 一双操作飞书的手](https://open.feishu.cn/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu) — overview, install, auth, use cases.
- [GitHub: larksuite/cli](https://github.com/larksuite/cli) — source and issues.

## Install CLI (on Core host)

**Automatic (default):** the first `run_skill` that runs `discover` or `exec` and cannot find `lark-cli` / `feishu-cli` will run:

```bash
npx --yes @larksuite/cli@latest install
```

That needs **Node.js** and **`npx`** on `PATH` for the Core process. After install, the runner looks again on `PATH` plus common npm global bin dirs (`npm config get prefix`, `~/.local/bin`, etc.).

**Disable auto-install** (strict hosts): set **`LARK_CLI_AUTO_INSTALL=0`**.

**Manual install** (same as Feishu docs):

```bash
npx @larksuite/cli@latest install
```

Confirm the binary is available:

```bash
lark-cli help
# or, if the binary is named differently:
feishu-cli help
```

If the executable is not found after install, set **`LARK_CLI`** to its full path in the environment used by Core (systemd, Docker, etc.).

## Configure application

```bash
lark-cli config init
```

Follow prompts to create or select an open-platform app. Grant scopes in the Feishu/Lark admin console as needed for your workflows.

## User OAuth (optional)

For **personal** data (your calendar, private chats, inbox):

```bash
lark-cli auth login
```

Complete the browser consent on the Core host (or use SSH port-forward if headless). Without user login, many **bot / app** operations still work per Feishu docs.

Check status:

```bash
lark-cli auth status
lark-cli auth check
```

## HomeClaw usage

From the repo root (debug):

```bash
python3 skills/feishu-cli-1.0.0/scripts/lark_cli_runner.py discover
python3 skills/feishu-cli-1.0.0/scripts/lark_cli_runner.py exec help
python3 skills/feishu-cli-1.0.0/scripts/lark_cli_runner.py exec auth status
```

In chat, the model calls **`run_skill`** with `skill_name='feishu-cli-1.0.0'`, `script='lark_cli_runner.py'`, and `args` as documented in **SKILL.md**.

## Cron / automation

You can schedule **`run_skill`** (e.g. morning digest) via HomeClaw cron if the CLI is already authenticated on the server. Prefer **read-only** or **idempotent** jobs unless you add dedupe in a wrapper script.

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `No lark-cli or feishu-cli found` | Ensure Node + `npx` on PATH (auto-install), or install CLI manually and set `LARK_CLI`. Run `discover` via run_skill. |
| `npx not found on PATH` | Install Node.js; or install Feishu CLI without npx and set `LARK_CLI`. |
| Auto-install unwanted | Set `LARK_CLI_AUTO_INSTALL=0` and install/configure CLI yourself. |
| Permission / scope errors | `lark-cli auth check` and Feishu open-platform app permissions. |
| Timeout | Increase `LARK_CLI_TIMEOUT_SEC` (seconds). Large exports may need a higher value. |
| Wrong tenant (CN vs international Lark) | Re-run `config init` for the correct product / region. |
