---
name: cli-anything-bridge
description: |
  Safely run selected CLI-Anything generated CLIs from HomeClaw using run_skill.
  This is a pilot integration wrapper with allowlists, timeouts, output caps, and deterministic JSON output.
homepage: https://github.com/HKUDS/CLI-Anything
trigger:
  patterns:
    - "cli-anything"
    - "cli-anything-[a-z]+"
  instruction: |
    The user is asking to use a CLI-Anything generated CLI. Use run_skill:
      args=["exec", "--bin", "<cli-anything-toolname>", "--args-json", "[\"--help\"]"]
    Start with --help to discover available commands.
    When the CLI supports --json flag, add it to get structured output.
    To save generated artifacts to output folder:
      args=["copy-out", "--source", "<file_path>", "--out-name", "<output_name.ext>"]
    The copy-out command returns output_rel_path at the top level for run_skill link appending.
---

# cli-anything-bridge-1.0.0

Pilot wrapper for integrating CLI-Anything harnesses into HomeClaw.

## Scripts (run_skill)

| Action | Args |
|---|---|
| Show help for a generated CLI | `["exec", "--bin", "cli-anything-<tool>", "--args-json", "[\"--help\"]"]` |
| Show version | `["exec", "--bin", "cli-anything-<tool>", "--args-json", "[\"--version\"]"]` |
| Run specific command | `["exec", "--bin", "cli-anything-<tool>", "--args-json", "[\"--json\", \"<subcommand>\", \"...\"]"]` |
| Parse JSON + normalized summary | Add `"--parse-json", "auto"` or `"strict"` after other exec args |
| Copy artifact to output sandbox | `["copy-out", "--source", "<ABS_OR_REL_FILE_PATH>", "--out-name", "<NAME.EXT>"]` |

When JSON is parsed, `data.normalized` contains `summary`, `items`, and `artifacts` (paths) for easier model consumption.

## Guardrails

- Binary must be allowlisted:
  - Default allow pattern: names beginning with `cli-anything-`
  - Optional explicit allowlist via env `HOMECLAW_CLI_ANYTHING_BINS` (comma-separated exact names)
- Timeout and output-size caps are enforced.
- `shell=True` is never used.
- Returns deterministic one-line JSON for run_skill compatibility.

