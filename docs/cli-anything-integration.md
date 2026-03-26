# CLI-Anything Integration for HomeClaw

This document describes a practical way to use [CLI-Anything](https://github.com/HKUDS/CLI-Anything?tab=readme-ov-file#-openclaw-community) to extend HomeClaw with new capabilities while keeping behavior stable, secure, and maintainable.

## Goals

- Expand HomeClaw's ability to control external software through stable CLI interfaces.
- Keep HomeClaw as the orchestration layer (skills, scheduling, channels, output links).
- Avoid brittle direct UI automation when deterministic CLI execution is available.
- Roll out incrementally with testable boundaries.

## Non-Goals

- Import all CLI-Anything harnesses at once.
- Allow unrestricted command execution from user prompts.
- Replace existing HomeClaw built-in tools that are already stable and sufficient.

## Recommended Architecture

Use a thin-wrapper model:

**Bundled pilot:** `skills/cli-anything-bridge-1.0.0` runs allowlisted `cli-anything-*` binaries via `run_cli_anything.py` with timeouts, output caps, optional `--parse-json` (auto/strict/off), and a compact `data.normalized` object (`summary`, `items`, `artifacts`) when CLI output is JSON.

1. Generate or install a target CLI harness using CLI-Anything.
2. Create a HomeClaw skill wrapper script that:
   - validates/normalizes user args,
   - executes the harness command with strict limits,
   - parses output into a predictable JSON schema,
   - writes artifacts to `HOMECLAW_OUTPUT_DIR` when needed.
3. Expose this wrapper via `run_skill` and natural-language trigger patterns.

Data flow:

- User prompt -> HomeClaw skill (`SKILL.md`) -> wrapper script -> CLI harness -> structured output -> HomeClaw post-processing (links, channel delivery, optional summary polish).

## Security Guardrails (Required)

Treat CLI harnesses as untrusted external tools until proven safe.

- Command allowlist:
  - Permit only explicit subcommands/flags.
  - Reject arbitrary shell fragments and path traversal.
- Filesystem scope:
  - Read/write only under approved workspace dirs and `HOMECLAW_OUTPUT_DIR`.
  - Deny access to sensitive paths (`~/.ssh`, credentials, system dirs).
- Time and resource limits:
  - Enforce subprocess timeout per command.
  - Cap output size before parsing.
  - Optionally run with lower process priority.
- Network policy:
  - Enable only when required by target workflow.
  - Prefer explicit host allowlists.
- Output validation:
  - Require JSON parse success or deterministic fallback behavior.
  - Never pass raw command output to end users without sanitization.
- Auditing:
  - Log command, args, duration, exit code, and output truncation markers.

## Wrapper Script Template

For each integrated harness, use this pattern:

- Input:
  - strict argparse schema,
  - optional `--json` mode enforced to stabilize parsing.
- Execution:
  - `subprocess.run([...], capture_output=True, text=True, timeout=...)`
  - no `shell=True`.
- Output contract:
  - Always print one final JSON line:
    - `success` (bool),
    - `message` (str),
    - optional `data` (object),
    - optional `output_rel_path` (str).
- Error handling:
  - map known failures to actionable messages,
  - include stderr excerpt for debugging (bounded length).

## Candidate Pilot Integrations

Pick two to start:

1. Document workflow (lower operational risk):
   - Example: office/doc conversion or report export pipeline.
   - Value: produce polished artifacts for channels and Companion.
2. Diagram/media workflow (high visible value):
   - Example: Mermaid/Draw.io or controlled media transformation.
   - Value: richer outputs aligned with HomeClaw's "beautiful response" direction.

Avoid high-risk domains first (broad browser/system control, destructive operations).

## Phased Rollout Plan

### Phase 1: Feasibility (1-2 days)

- Select one harness and run it manually on your dev machine.
- Confirm:
  - install steps are reproducible,
  - command surface is stable,
  - JSON mode exists or can be normalized by wrapper.

Exit criteria:

- One command executes end-to-end with deterministic output.

### Phase 2: Skill Wrapper MVP (2-3 days)

- Add one HomeClaw skill folder:
  - `skills/<name>-1.0.0/SKILL.md`
  - `skills/<name>-1.0.0/scripts/<wrapper>.py`
  - `README.md` with natural-language examples.
- Implement strict arg mapping and timeout/output caps.
- Return standardized JSON for `run_skill`.

Exit criteria:

- Local `run_skill` call works and output link behavior is correct when files are produced.

### Phase 3: Reliability Hardening (2-3 days)

- Add tests:
  - valid command path,
  - invalid args rejected,
  - timeout path,
  - malformed output fallback,
  - output-size truncation behavior.
- Run cross-platform smoke tests (macOS/Linux/Windows where possible).

Exit criteria:

- Stable behavior under failure cases, no crashes, clear error messages.

### Phase 4: Controlled Expansion

- Add second harness only after Phase 3 passes.
- Reuse the same wrapper contract and guardrails.
- Document known platform differences and required dependencies.

## Testing Checklist

- Functional:
  - natural language triggers invoke correct skill,
  - `run_skill` manual calls succeed,
  - output artifacts appear in expected output scope.
- Robustness:
  - command timeout enforced,
  - non-zero exit code handled cleanly,
  - partial output still yields deterministic error JSON.
- Security:
  - disallowed flags rejected,
  - path traversal attempts rejected,
  - unexpected binary/ANSI output sanitized.
- Compatibility:
  - Python version compatibility,
  - shell/path handling for macOS/Linux/Windows.

## Versioning and Maintenance

- Pin harness versions and record source commit/tag.
- Keep wrapper compatibility notes in each skill README.
- Add a periodic validation task to detect upstream CLI behavior drift.
- Prefer additive updates (new flags) over changing existing argument semantics.

## Suggested Repo Conventions

- New doc: `docs/cli-anything-integration.md` (this file).
- For each integration:
  - `skills/<tool>-<semver>/`
  - clear ownership note in README,
  - explicit dependency install section.
- Optional index update:
  - add links in `skills/README.md` and `docs/install.md` once first integration lands.

## Go/No-Go Criteria for Production Use

Go when all are true:

- Wrapper has strict allowlist and timeout caps.
- Output contract is deterministic JSON.
- Cross-platform smoke tests pass for intended OS targets.
- Failure modes produce actionable user-facing messages.

No-go if any are true:

- Wrapper still accepts arbitrary pass-through shell args.
- Output parsing depends on fragile text scraping.
- Integration requires unsafe filesystem/network permissions by default.

