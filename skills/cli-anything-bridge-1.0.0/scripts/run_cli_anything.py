#!/usr/bin/env python3
"""
Run selected CLI-Anything binaries with safety guardrails.

Prints exactly one JSON line:
  {"success": true|false, "message": "...", "data": {...}}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _ok(message: str, data: Optional[dict] = None) -> None:
    print(json.dumps({"success": True, "message": message, "data": data or {}}, ensure_ascii=False))


def _fail(message: str, data: Optional[dict] = None, rc: int = 1) -> None:
    print(json.dumps({"success": False, "message": message, "data": data or {}}, ensure_ascii=False))
    sys.exit(rc)


def _parse_args_json(raw: str) -> List[str]:
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise ValueError(f"--args-json must be a JSON array: {e}") from e
    if not isinstance(obj, list):
        raise ValueError("--args-json must be a JSON array")
    out: List[str] = []
    for i, it in enumerate(obj):
        if not isinstance(it, str):
            raise ValueError(f"--args-json item #{i} must be a string")
        if "\x00" in it or "\n" in it or "\r" in it:
            raise ValueError(f"--args-json item #{i} contains unsupported control chars")
        if len(it) > 2000:
            raise ValueError(f"--args-json item #{i} is too long")
        out.append(it)
    if len(out) > 80:
        raise ValueError("too many args; max is 80")
    return out


def _is_bin_allowed(bin_name: str) -> bool:
    allowed = (os.environ.get("HOMECLAW_CLI_ANYTHING_BINS") or "").strip()
    if allowed:
        explicit = {x.strip() for x in allowed.split(",") if x.strip()}
        return bin_name in explicit
    return bin_name.startswith("cli-anything-")


def _sanitize_bin_name(bin_name: str) -> str:
    name = (bin_name or "").strip()
    if not name:
        raise ValueError("--bin is required")
    if "/" in name or "\\" in name:
        raise ValueError("--bin must be a command name on PATH, not a path")
    if not re.match(r"^[A-Za-z0-9._-]+$", name):
        raise ValueError("--bin has invalid characters")
    if not _is_bin_allowed(name):
        raise ValueError("binary not allowlisted by policy")
    return name


def _timeout_value(cli_timeout: int) -> int:
    if cli_timeout > 0:
        return cli_timeout
    env_v = (os.environ.get("HOMECLAW_CLI_ANYTHING_TIMEOUT_SEC") or "").strip()
    try:
        if env_v:
            t = int(env_v)
            if 1 <= t <= 600:
                return t
    except Exception:
        pass
    return 90


def _clamp_timeout_sec(v: int) -> int:
    if v <= 0:
        return 90
    return max(1, min(int(v), 600))


def _sanitize_output_name(name: str, fallback: str = "artifact.bin") -> str:
    s = (name or "").strip()
    if not s:
        return fallback
    s = s.replace("\\", "/").split("/")[-1]
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("._-")
    return s or fallback


def _output_dir() -> Path:
    out_env = (os.environ.get("HOMECLAW_OUTPUT_DIR") or "").strip()
    if out_env:
        p = Path(out_env).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = (Path.cwd() / "output").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _copy_to_output(source: str, out_name: str) -> Tuple[str, str]:
    src = Path((source or "").strip()).expanduser().resolve()
    if not src.is_file():
        raise ValueError(f"source file not found: {src}")
    dst_name = _sanitize_output_name(out_name, fallback=src.name or "artifact.bin")
    dst = (_output_dir() / dst_name).resolve()
    shutil.copy2(src, dst)
    # HomeClaw expects output_rel_path under output/ for link generation.
    return str(dst), f"output/{dst_name}"


def _extract_json_from_text(text: str) -> Optional[Any]:
    """
    Best-effort: parse a single JSON value from stdout (whole string, or last non-empty line).
    """
    s = (text or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        pass
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    for candidate in reversed(lines[-5:]):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    # Trim to outermost JSON object/array if extra noise prefix/suffix
    for opener, closer in (("{", "}"), ("[", "]")):
        start = s.find(opener)
        end = s.rfind(closer)
        if start != -1 and end != -1 and end > start:
            frag = s[start : end + 1]
            try:
                return json.loads(frag)
            except Exception:
                pass
    return None


def _collect_artifact_strings(val: str, out: List[str]) -> None:
    v = (val or "").strip()
    if not v or len(v) > 4096:
        return
    if re.search(
        r"\.(pdf|png|jpe?g|gif|webp|svg|od[tfp]|docx?|xlsx?|pptx?|zip|json|md|mscx|musicxml)\b",
        v,
        re.I,
    ):
        out.append(v)


def _walk_for_artifacts(obj: Any, out: List[str], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k in (
            "output",
            "path",
            "file",
            "filepath",
            "export_path",
            "out",
            "destination",
            "pdf",
            "png",
        ):
            if k in obj and isinstance(obj[k], str):
                _collect_artifact_strings(obj[k], out)
        for v in obj.values():
            _walk_for_artifacts(v, out, depth + 1)
    elif isinstance(obj, list):
        for it in obj[:50]:
            _walk_for_artifacts(it, out, depth + 1)


def _normalize_cli_json(obj: Any) -> Dict[str, Any]:
    """Compact schema for HomeClaw: summary, items, artifacts."""
    summary = ""
    items: List[Any] = []
    artifacts: List[str] = []

    if isinstance(obj, dict):
        for k in ("message", "name", "summary", "title", "status", "error"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                summary = v.strip()[:800]
                break
        if not summary:
            summary = json.dumps(obj, ensure_ascii=False)[:400]

        for key in ("items", "results", "data", "rows", "elements", "records"):
            if key in obj and isinstance(obj[key], list):
                for it in obj[key][:30]:
                    if isinstance(it, dict):
                        slim = {str(k): (str(v)[:400] if not isinstance(v, (dict, list)) else "...") for k, v in list(it.items())[:14]}
                        items.append(slim)
                    else:
                        items.append(str(it)[:400])
                break
        _walk_for_artifacts(obj, artifacts)
    elif isinstance(obj, list):
        summary = f"JSON array ({len(obj)} items)"
        for it in obj[:30]:
            if isinstance(it, dict):
                slim = {str(k): (str(v)[:400] if not isinstance(v, (dict, list)) else "...") for k, v in list(it.items())[:14]}
                items.append(slim)
            else:
                items.append(str(it)[:400])

    # Dedupe artifacts, keep order
    seen = set()
    uniq: List[str] = []
    for a in artifacts:
        if a not in seen:
            seen.add(a)
            uniq.append(a)

    return {
        "summary": summary[:2000],
        "items": items[:50],
        "artifacts": uniq[:50],
    }


def _maybe_parse_and_normalize(
    stdout: str,
    stderr: str,
    argv: List[str],
    mode: str,
) -> Tuple[Optional[Any], Optional[Dict[str, Any]], Optional[str]]:
    """
    mode: off | auto | strict
    Returns (parsed_obj, normalized, error_message_for_strict).
    """
    mode = (mode or "auto").strip().lower()
    if mode == "off":
        return None, None, None

    has_json_flag = "--json" in argv
    text = (stdout or "").strip()
    if not text and (stderr or "").strip():
        text = (stderr or "").strip()

    should_try = mode == "strict" or has_json_flag or text.startswith(("{", "["))
    if mode == "auto" and not should_try:
        return None, None, None

    parsed = _extract_json_from_text(text)
    if parsed is None:
        if mode == "strict":
            return None, None, "strict JSON parse failed: stdout did not contain valid JSON"
        return None, None, None

    return parsed, _normalize_cli_json(parsed), None


def main() -> None:
    p = argparse.ArgumentParser(prog="run_cli_anything.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_exec = sub.add_parser("exec", help="Execute an allowlisted CLI-Anything binary")
    p_exec.add_argument("--bin", required=True, help="Binary name on PATH, e.g. cli-anything-gimp")
    p_exec.add_argument("--args-json", default="[]", help="JSON array of args")
    p_exec.add_argument("--timeout-sec", type=int, default=0, help="Timeout in seconds (1..600), default from env or 90")
    p_exec.add_argument("--max-output-chars", type=int, default=12000, help="Max chars retained from stdout+stderr")
    p_exec.add_argument(
        "--parse-json",
        default="auto",
        choices=["off", "auto", "strict"],
        help="Parse JSON from stdout (auto: when --json in args or output looks like JSON; strict: require JSON)",
    )
    p_cp = sub.add_parser("copy-out", help="Copy a local artifact into HOMECLAW_OUTPUT_DIR")
    p_cp.add_argument("--source", required=True, help="Absolute or relative source file path")
    p_cp.add_argument("--out-name", default="", help="Output filename in HOMECLAW_OUTPUT_DIR")

    args = p.parse_args()

    try:
        if args.cmd == "copy-out":
            abs_dst, out_rel = _copy_to_output(str(args.source), str(args.out_name or ""))
            _ok(
                "Artifact copied to output",
                {"source": str(args.source), "output_abs_path": abs_dst, "output_rel_path": out_rel},
            )
            return

        if args.cmd != "exec":
            _fail("Unknown command")

        bin_name = _sanitize_bin_name(args.bin)
        cmd_path = shutil.which(bin_name)
        if not cmd_path:
            _fail(
                f"Command not found on PATH: {bin_name}",
                {"hint": "Install the generated harness and ensure the binary is on PATH."},
            )

        argv = _parse_args_json(args.args_json)
        timeout_sec = _clamp_timeout_sec(_timeout_value(int(args.timeout_sec)))
        max_chars = max(1000, min(int(args.max_output_chars), 200000))

        proc = subprocess.run(
            [cmd_path] + argv,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined = (stdout + ("\n" if stdout and stderr else "") + stderr).strip()
        truncated = False
        if len(combined) > max_chars:
            combined = combined[:max_chars]
            truncated = True

        parsed_obj, normalized, strict_err = _maybe_parse_and_normalize(
            stdout, stderr, argv, str(args.parse_json)
        )
        if strict_err:
            _fail(strict_err, {"binary": bin_name, "argv": argv, "output": combined[: max_chars]})

        payload = {
            "binary": bin_name,
            "argv": argv,
            "exit_code": proc.returncode,
            "output": combined,
            "output_truncated": truncated,
            "timeout_sec": timeout_sec,
        }
        if parsed_obj is not None:
            try:
                dumped = json.dumps(parsed_obj, ensure_ascii=False)
                if len(dumped) <= 100_000:
                    payload["parsed_json"] = parsed_obj
                else:
                    payload["parsed_json_omitted"] = True
                    payload["parsed_json_chars"] = len(dumped)
            except Exception:
                payload["parsed_json"] = str(parsed_obj)[:4000]
        if normalized is not None:
            payload["normalized"] = normalized

        if proc.returncode == 0:
            _ok(f"{bin_name} executed successfully", payload)
        _fail(f"{bin_name} exited with non-zero status {proc.returncode}", payload)

    except subprocess.TimeoutExpired:
        _fail("Command timed out", {"timeout_sec": _clamp_timeout_sec(_timeout_value(int(args.timeout_sec)))})
    except ValueError as e:
        _fail(str(e))
    except Exception as e:
        _fail(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()

