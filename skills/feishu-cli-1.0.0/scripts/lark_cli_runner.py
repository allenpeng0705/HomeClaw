#!/usr/bin/env python3
"""
HomeClaw skill runner for Feishu / Lark CLI (lark-cli).
Passes argv to the real CLI with no shell. See SKILL.md in the parent folder.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Module-level cache for resolved CLI path (survives multiple exec calls per runner process)
_cli_path_cache: str | None = None

# Write-operation subcommands that should suggest --dry-run first
_WRITE_OPS = frozenset({
    "messages-send", "messages-reply", "+create", "create",
    "mail send", "send",
    "task add", "task create",
    "approval submit", "submit",
})


def _is_write_op(forwarded: list[str]) -> bool:
    """Return True if forwarded argv contains a write/send operation."""
    # Check for domain subcommand patterns like "im messages-send"
    tokens = set(forwarded)
    # Also check consecutive pairs: ["im", "messages-send"]
    for i, tok in enumerate(forwarded):
        if tok in _WRITE_OPS:
            return True
        if i + 1 < len(forwarded) and tok in ("im", "docs", "mail", "task", "approval", "calendar") and forwarded[i + 1] in _WRITE_OPS:
            return True
    return False


def _check_dry_run(forwarded: list[str]) -> str:
    """Return a warning if a write op is attempted without --dry-run or -n."""
    if not _is_write_op(forwarded):
        return ""
    if any(tok in ("--dry-run", "-n", "--preview", "--check") for tok in forwarded):
        return ""
    return "[Warning: --dry-run missing for a write/send operation. Pass --dry-run first to preview what will be sent.]"


def _parse_feishu_error(proc: subprocess.CompletedProcess[str]) -> str:
    """
    Extract a clean Feishu API error message from stdout/stderr on non-zero exit.
    The CLI returns JSON like {"code": 99991663, "msg": "..."} on API failures.
    """
    for stream in (proc.stdout or "", proc.stderr or ""):
        stream = stream.strip()
        if stream.startswith("{"):
            try:
                obj = json.loads(stream)
                code = obj.get("code")
                msg = obj.get("msg", "")
                if code is not None or msg:
                    parts = []
                    if code is not None:
                        parts.append(f"code={code}")
                    if msg:
                        parts.append(msg)
                    return "Feishu API error: " + ", ".join(parts)
            except Exception:
                pass
    return ""


def _npm_global_bin() -> list[Path]:
    """Common locations for global npm binaries (PATH may omit them in long-running Core)."""
    out: list[Path] = []
    home = Path.home()
    out.extend(
        [
            home / ".local" / "bin",
            home / "bin",
            home / ".npm-global" / "bin",
        ]
    )
    npm = shutil.which("npm")
    if npm:
        try:
            proc = subprocess.run(
                [npm, "config", "get", "prefix"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            pref = (proc.stdout or "").strip()
            if pref and pref != "undefined":
                base = Path(pref)
                out.append(base / "bin")
        except Exception:
            pass
    return out


def _resolve_cli() -> str | None:
    global _cli_path_cache
    if _cli_path_cache:
        return _cli_path_cache
    env_bin = (os.environ.get("LARK_CLI") or "").strip()
    if env_bin and Path(env_bin).is_file():
        _cli_path_cache = env_bin
        return env_bin
    for name in ("lark-cli", "feishu-cli"):
        p = shutil.which(name)
        if p:
            _cli_path_cache = p
            return p
    for d in _npm_global_bin():
        for name in ("lark-cli", "feishu-cli"):
            cand = d / name
            if cand.is_file() and os.access(cand, os.X_OK):
                _cli_path_cache = str(cand)
                return _cli_path_cache
    return None


def _timeout_sec() -> int:
    raw = (os.environ.get("LARK_CLI_TIMEOUT_SEC") or "").strip()
    if not raw:
        return 180
    try:
        v = int(raw, 10)
        return max(5, min(v, 3600))
    except ValueError:
        return 180


def _install_timeout_sec() -> int:
    raw = (os.environ.get("LARK_CLI_INSTALL_TIMEOUT_SEC") or "").strip()
    if not raw:
        return 600
    try:
        v = int(raw, 10)
        return max(60, min(v, 7200))
    except ValueError:
        return 600


def _auto_install_enabled() -> bool:
    v = (os.environ.get("LARK_CLI_AUTO_INSTALL") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def _try_npx_install() -> tuple[int, str, str]:
    """
    Run official one-line install: npx --yes @larksuite/cli@latest install
    Returns (returncode, stdout, stderr).
    """
    npx = shutil.which("npx")
    if not npx:
        return (
            127,
            "",
            "npx not found on PATH. Install Node.js (https://nodejs.org) so npx is available, "
            "or install Feishu CLI manually and set LARK_CLI.\n",
        )
    cmd = [npx, "--yes", "@larksuite/cli@latest", "install"]
    print(
        "Feishu/Lark CLI not found; running:\n  "
        + " ".join(cmd)
        + "\n(This may take a few minutes on first run.)\n",
        file=sys.stderr,
        flush=True,
    )
    proc = subprocess.run(
        cmd,
        text=True,
        timeout=_install_timeout_sec(),
        capture_output=True,
        env=os.environ.copy(),
    )
    out = proc.stdout or ""
    err = proc.stderr or ""
    return (int(proc.returncode or 0), out, err)


def _ensure_cli() -> str | None:
    """Resolve lark-cli path, optionally running npx install once if missing."""
    path = _resolve_cli()
    if path:
        return path
    if not _auto_install_enabled():
        return None
    code, out, err = _try_npx_install()
    if out.strip():
        print(out, file=sys.stderr, end="" if out.endswith("\n") else "\n")
    if err.strip():
        print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
    if code != 0:
        print(
            f"npx install exited with code {code}. "
            "Fix network/Node/npm, set LARK_CLI to an existing binary, "
            "or set LARK_CLI_AUTO_INSTALL=0 and install manually.",
            file=sys.stderr,
        )
        return None
    return _resolve_cli()


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  lark_cli_runner.py discover\n"
            "  lark_cli_runner.py exec [<lark-cli args...>]\n"
            "Examples:\n"
            "  lark_cli_runner.py exec help\n"
            "  lark_cli_runner.py exec auth status\n",
            file=sys.stderr,
        )
        return 2

    cmd = sys.argv[1].strip().lower()
    if cmd == "discover":
        path = _ensure_cli()
        if not path:
            print(
                "No lark-cli or feishu-cli found after install attempt.\n"
                "Install manually: npx @larksuite/cli@latest install\n"
                "Or set LARK_CLI to the full path of the executable.\n"
                "To skip automatic install: LARK_CLI_AUTO_INSTALL=0",
                file=sys.stderr,
            )
            return 127
        print(path)
        try:
            ver = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            out = (ver.stdout or "").strip() or (ver.stderr or "").strip()
            if out:
                print(out)
        except Exception as e:
            print(f"(version check skipped: {e})", file=sys.stderr)
        return 0

    if cmd == "exec":
        cli = _ensure_cli()
        if not cli:
            print(
                "No lark-cli or feishu-cli found. Set LARK_CLI, install Node+npx, "
                "or run: npx @larksuite/cli@latest install\n"
                "To skip automatic install: LARK_CLI_AUTO_INSTALL=0",
                file=sys.stderr,
            )
            return 127
        forwarded = sys.argv[2:]

        # Issue dry-run warning for write operations
        dry_run_warning = _check_dry_run(forwarded)
        if dry_run_warning:
            sys.stderr.write(dry_run_warning + "\n")

        try:
            proc = subprocess.run(
                [cli, *forwarded],
                cwd=os.getcwd(),
                text=True,
                timeout=_timeout_sec(),
                capture_output=True,
            )
        except subprocess.TimeoutExpired:
            print(f"Error: lark-cli exceeded timeout ({_timeout_sec()}s).", file=sys.stderr)
            return 124
        except FileNotFoundError:
            print(f"Error: executable not found: {cli}", file=sys.stderr)
            return 127

        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)

        # On failure, try to parse Feishu API error JSON for cleaner output
        rc = int(proc.returncode or 0)
        if rc != 0:
            feishu_err = _parse_feishu_error(proc)
            if feishu_err:
                sys.stderr.write(feishu_err + "\n")

        return rc

    print(f"Unknown command: {sys.argv[1]!r}. Use discover or exec.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
