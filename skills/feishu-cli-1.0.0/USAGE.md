# Feishu CLI skill — usage examples

Skill folder: **`feishu-cli-1.0.0`**. Script: **`lark_cli_runner.py`**.

## Natural language → `run_skill` (quick map)

Users speak normally; the model builds **`args`** as an argv list (no shell). Longer English/Chinese examples and “real work” guidance live in **`SKILL.md`** (“Example user intent → run_skill”).

| User says (idea) | `args` |
|------------------|--------|
| Check CLI / install resolution on Core | `["discover"]` |
| Top-level CLI help | `["exec", "help"]` |
| OAuth / session line | `["exec", "auth", "status"]` |
| Scope / permission probe | `["exec", "auth", "check"]` |
| Explore `schema` safely | `["exec", "schema", "--help"]` |
| Today’s calendar (shortcut) | `["exec", "calendar", "+agenda", "--as", "user"]` |
| Send IM (dry-run first) | `["exec", "im", "+messages-send", "--chat-id", "oc_xxx", "--text", "Hello", "--dry-run"]` |
| Create Doc from Markdown | `["exec", "docs", "+create", "--title", "Weekly Report", "--markdown", "# Progress\n- Item"]` |

Full intent → workflow table (Sheets, Base, Mail, raw `api`, pagination, formats) is in **`SKILL.md`** → *Real work*.

## Discover binary

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["discover"])
```

## Help and auth

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "help"])
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "auth", "status"])
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "auth", "check"])
```

## Schema / API exploration

Feishu documents `schema` for inspecting capabilities (exact subcommands depend on CLI version):

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "schema", "--help"])
```

## Real workflows (upstream examples; confirm with `exec … --help`)

Calendar agenda (identity explicit):

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "calendar", "+agenda", "--as", "user"])
```

Send a text message (preview, then send without `--dry-run` if appropriate):

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "im", "+messages-send", "--chat-id", "oc_xxx", "--text", "Hello", "--dry-run"])
```

Create a cloud document from Markdown:

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "docs", "+create", "--title", "Weekly Report", "--markdown", "# Progress\n- Completed feature X"])
```

API-style list calendars:

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "calendar", "calendars", "list"])
```

Schema for one method id:

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "schema", "calendar.events.instance_view"])
```

## Forwarding arbitrary `lark-cli` argv

Any tokens after `exec` are forwarded **without a shell**:

```text
run_skill(skill_name="feishu-cli-1.0.0", script="lark_cli_runner.py", args=["exec", "<subcommand>", ...])
```

Use **`exec … --help`** on the specific subcommand before running write/send operations.

## Notes

- **Binary install** can run automatically via `npx` when `lark-cli` is missing (unless `LARK_CLI_AUTO_INSTALL=0`). **`config init`** and **`auth login`** are still manual when the CLI prompts for them.
- Setup runs **on the Core host**, not on the Companion phone.
- Prefer narrow app scopes in Feishu open platform for production.
