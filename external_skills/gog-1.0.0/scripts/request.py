#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
gog skill runner for HomeClaw run_skill.
Wraps the gog CLI (Google Workspace) with structured output.

Usage:
  request.py gmail    --search "<query>" [--max N] [--account <email>]
  request.py send     --to <email> --subject "<subject>" --body "<body>" [--account <email>]
  request.py calendar --list-events [--calendar <id>] [--from <iso>] [--to <iso>]
  request.py drive    --search "<query>" [--max N]
  request.py contacts --list [--max N]
  request.py sheets   --get <sheetId> "<range>" [--json]
  request.py sheets   --update <sheetId> "<range>" --values-json <json>
  request.py docs     --cat <docId>
  request.py auth     --status
  request.py auth     --list
  request.py raw      <subcommand> [args...]

Subcommands: gmail, calendar, drive, contacts, sheets, docs, auth
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys


def _gog_binary() -> str:
    """Return path to gog binary, or raise ValueError if not found."""
    bin_path = shutil.which("gog")
    if not bin_path:
        raise ValueError(
            "gog not found. Install from https://gogcli.sh or run:\n"
            "  brew install gogcli/tap/gog"
        )
    return bin_path


def _run_gog(argv: list[str], timeout_sec: int = 60) -> tuple[int, str, str]:
    """Run gog with given argv. Returns (returncode, stdout, stderr)."""
    gog = _gog_binary()
    try:
        proc = subprocess.run(
            [gog] + argv,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        raise ValueError(f"gog command timed out after {timeout_sec}s")
    except Exception as e:
        raise ValueError(f"Failed to run gog: {e}")


def _ok(message: str, data: dict | None = None) -> None:
    out = {"success": True, "message": message}
    if data:
        out["data"] = data
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _fail(message: str, data: dict | None = None) -> None:
    out = {"success": False, "error": message}
    if data:
        out["data"] = data
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(1)


def cmd_gmail_search(query: str, max_results: int | None, account: str | None) -> None:
    argv = ["gmail", "search", query]
    if max_results:
        argv.extend(["--max", str(max_results)])
    if account:
        argv.extend(["--account", account])
    rc, stdout, stderr = _run_gog(argv)
    if rc != 0 and stderr:
        _fail(f"gog gmail search failed: {stderr.strip()}")
    _ok("Gmail search completed", {"output": stdout.strip(), "query": query})


def cmd_gmail_send(to: str, subject: str, body: str, account: str | None) -> None:
    argv = ["gmail", "send", "--to", to, "--subject", subject, "--body", body]
    if account:
        argv.extend(["--account", account])
    rc, stdout, stderr = _run_gog(argv)
    if rc != 0:
        _fail(f"gog gmail send failed: {stderr.strip() or stdout.strip()}")
    _ok(f"Email sent to {to}", {"to": to, "subject": subject})


def cmd_calendar_list(calendar_id: str | None, from_iso: str | None, to_iso: str | None) -> None:
    argv = ["calendar", "events"]
    if calendar_id:
        argv.append(calendar_id)
    if from_iso:
        argv.extend(["--from", from_iso])
    if to_iso:
        argv.extend(["--to", to_iso])
    rc, stdout, stderr = _run_gog(argv)
    if rc != 0:
        _fail(f"gog calendar events failed: {stderr.strip() or stdout.strip()}")
    _ok("Calendar events retrieved", {"output": stdout.strip()})


def cmd_drive_search(query: str, max_results: int | None) -> None:
    argv = ["drive", "search", query]
    if max_results:
        argv.extend(["--max", str(max_results)])
    rc, stdout, stderr = _run_gog(argv)
    if rc != 0:
        _fail(f"gog drive search failed: {stderr.strip() or stdout.strip()}")
    _ok("Drive search completed", {"output": stdout.strip(), "query": query})


def cmd_contacts_list(max_results: int | None) -> None:
    argv = ["contacts", "list"]
    if max_results:
        argv.extend(["--max", str(max_results)])
    rc, stdout, stderr = _run_gog(argv)
    if rc != 0:
        _fail(f"gog contacts list failed: {stderr.strip() or stdout.strip()}")
    _ok("Contacts retrieved", {"output": stdout.strip()})


def cmd_sheets_get(sheet_id: str, range_spec: str, as_json: bool) -> None:
    argv = ["sheets", "get", sheet_id, range_spec]
    if as_json:
        argv.append("--json")
    rc, stdout, stderr = _run_gog(argv)
    if rc != 0:
        _fail(f"gog sheets get failed: {stderr.strip() or stdout.strip()}")
    _ok(f"Sheets range {range_spec} retrieved", {"sheetId": sheet_id, "range": range_spec, "output": stdout.strip()})


def cmd_sheets_update(sheet_id: str, range_spec: str, values_json: str) -> None:
    argv = ["sheets", "update", sheet_id, range_spec, "--values-json", values_json, "--input", "USER_ENTERED"]
    rc, stdout, stderr = _run_gog(argv)
    if rc != 0:
        _fail(f"gog sheets update failed: {stderr.strip() or stdout.strip()}")
    _ok(f"Sheets range {range_spec} updated", {"sheetId": sheet_id, "range": range_spec})


def cmd_docs_cat(doc_id: str) -> None:
    argv = ["docs", "cat", doc_id]
    rc, stdout, stderr = _run_gog(argv)
    if rc != 0:
        _fail(f"gog docs cat failed: {stderr.strip() or stdout.strip()}")
    _ok("Docs content retrieved", {"docId": doc_id, "output": stdout.strip()})


def cmd_auth_status() -> None:
    rc, stdout, stderr = _run_gog(["auth", "status"])
    if rc != 0:
        _fail("gog auth status failed", {"stderr": stderr.strip()})
    _ok("Auth status retrieved", {"output": stdout.strip()})


def cmd_auth_list() -> None:
    rc, stdout, stderr = _run_gog(["auth", "list"])
    if rc != 0:
        _fail("gog auth list failed", {"stderr": stderr.strip()})
    _ok("Auth accounts retrieved", {"output": stdout.strip()})


def cmd_raw(subcommand: str, args: list[str]) -> None:
    """Pass through any gog subcommand with raw args."""
    try:
        _gog_binary()  # Verify gog exists
    except ValueError as e:
        _fail(str(e))
    argv = [subcommand] + args
    rc, stdout, stderr = _run_gog(argv)
    combined = stdout.strip()
    if stderr.strip():
        combined = f"{combined}\nstderr:\n{stderr.strip()}" if combined else stderr.strip()
    if rc != 0:
        _fail(f"gog {' '.join(argv)} failed (exit {rc})", {"output": combined})
    _ok(f"gog {subcommand} succeeded", {"output": combined})


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: request.py <gmail|calendar|drive|contacts|sheets|docs|auth|raw> [args...]", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 1

    sub = sys.argv[1].strip().lower()

    # Build per-subcommand parser to extract known args alongside extras
    if sub == "gmail":
        p = argparse.ArgumentParser(prog="request.py gmail")
        p.add_argument("--search", dest="search", default="")
        p.add_argument("--to", dest="to", default="")
        p.add_argument("--subject", dest="subject", default="")
        p.add_argument("--body", dest="body", default="")
        p.add_argument("--max", dest="max", type=int, default=None)
        p.add_argument("--account", dest="account", default=None)
        # Passthrough remaining args
        known, extra = p.parse_known_args(sys.argv[2:])
        if known.search:
            cmd_gmail_search(known.search, known.max, known.account)
        elif known.to:
            if not known.subject or not known.body:
                _fail("--subject and --body are required when using --to")
            cmd_gmail_send(known.to, known.subject, known.body, known.account)
        else:
            cmd_raw("gmail", extra)
        return 0

    if sub == "calendar":
        p = argparse.ArgumentParser(prog="request.py calendar")
        p.add_argument("--list-events", dest="list_events", action="store_true")
        p.add_argument("--calendar", dest="calendar", default=None)
        p.add_argument("--from", dest="from_iso", default=None)
        p.add_argument("--to", dest="to_iso", default=None)
        known, extra = p.parse_known_args(sys.argv[2:])
        cmd_calendar_list(known.calendar, known.from_iso, known.to_iso)
        return 0

    if sub == "drive":
        p = argparse.ArgumentParser(prog="request.py drive")
        p.add_argument("--search", dest="search", default="")
        p.add_argument("--max", dest="max", type=int, default=None)
        known, extra = p.parse_known_args(sys.argv[2:])
        if not known.search:
            cmd_raw("drive", extra)
        else:
            cmd_drive_search(known.search, known.max)
        return 0

    if sub == "contacts":
        p = argparse.ArgumentParser(prog="request.py contacts")
        p.add_argument("--list", dest="list_mode", action="store_true")
        p.add_argument("--max", dest="max", type=int, default=None)
        known, extra = p.parse_known_args(sys.argv[2:])
        cmd_contacts_list(known.max)
        return 0

    if sub == "sheets":
        p = argparse.ArgumentParser(prog="request.py sheets")
        p.add_argument("--get", dest="get", nargs=2, metavar=("SHEET_ID", "RANGE"))
        p.add_argument("--update", dest="update", nargs=2, metavar=("SHEET_ID", "RANGE"))
        p.add_argument("--values-json", dest="values_json", default="")
        p.add_argument("--json", dest="as_json", action="store_true")
        known, extra = p.parse_known_args(sys.argv[2:])
        if known.get:
            cmd_sheets_get(known.get[0], known.get[1], known.as_json)
        elif known.update:
            if not known.values_json:
                _fail("--values-json is required with --update")
            cmd_sheets_update(known.update[0], known.update[1], known.values_json)
        else:
            cmd_raw("sheets", extra)
        return 0

    if sub == "docs":
        p = argparse.ArgumentParser(prog="request.py docs")
        p.add_argument("--cat", dest="cat", default="")
        known, extra = p.parse_known_args(sys.argv[2:])
        if not known.cat:
            cmd_raw("docs", extra)
        else:
            cmd_docs_cat(known.cat)
        return 0

    if sub == "auth":
        _, extra = argparse.ArgumentParser().parse_known_args(sys.argv[2:])
        if not extra or extra[0] == "--status":
            cmd_auth_status()
        elif extra[0] == "--list":
            cmd_auth_list()
        else:
            cmd_raw("auth", extra)
        return 0

    if sub == "raw":
        if len(sys.argv) < 3:
            _fail("raw subcommand requires <gog-subcommand> [args...]")
        cmd_raw(sys.argv[2], sys.argv[3:])
        return 0

    _fail(f"Unknown subcommand: {sub}. Use: gmail, calendar, drive, contacts, sheets, docs, auth, raw")
    return 1


if __name__ == "__main__":
    sys.exit(main())
