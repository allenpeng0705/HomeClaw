# cli-anything-bridge-1.0.0

Safe pilot integration to run selected CLI-Anything generated binaries from HomeClaw.

## Natural language

- "Use cli-anything-gimp and show available commands."
- "Run cli-anything-libreoffice --help."
- "Use cli-anything-drawio and show version."

## run_skill examples

```text
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["exec", "--bin", "cli-anything-gimp", "--args-json", "[\"--help\"]"])
```

```text
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["exec", "--bin", "cli-anything-libreoffice", "--args-json", "[\"--version\"]"])
```

```text
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["exec", "--bin", "cli-anything-drawio", "--args-json", "[\"--json\", \"--help\"]"])
```

Copy an artifact into HomeClaw output scope (for stable links):

```text
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["copy-out", "--source", "/absolute/path/to/output.pdf", "--out-name", "report.pdf"])
```

If successful, the JSON includes `data.output_rel_path` (e.g. `output/report.pdf`) which HomeClaw can use for file links.

## JSON output (`--parse-json`)

When the CLI prints JSON (often with `--json` on the command line), the wrapper can parse stdout and add:

- `data.parsed_json` — full parsed object (omitted if larger than ~100k chars of serialized JSON)
- `data.normalized` — compact shape for the model: `summary`, `items`, `artifacts` (file-like paths)

Modes (pass as extra args on `exec`):

- `--parse-json auto` (default): parse when `--json` appears in args, or when stdout looks like `{` / `[`
- `--parse-json strict`: require valid JSON or fail with a clear error
- `--parse-json off`: raw text only in `data.output`

Example with strict JSON:

```text
run_skill(skill_name="cli-anything-bridge-1.0.0", script="run_cli_anything.py", args=["exec", "--bin", "cli-anything-drawio", "--args-json", "[\"--json\", \"document\", \"info\", \"--project\", \"report.json\"]", "--parse-json", "strict"])
```

## Optional environment variables

- `HOMECLAW_CLI_ANYTHING_BINS`:
  - Comma-separated explicit allowlist.
  - Example: `cli-anything-gimp,cli-anything-libreoffice,cli-anything-drawio`
- `HOMECLAW_CLI_ANYTHING_TIMEOUT_SEC`:
  - Default timeout in seconds (if `--timeout-sec` not passed).
  - Default: `90`.

