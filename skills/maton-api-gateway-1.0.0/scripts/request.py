#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "httpx>=0.27.0",
# ]
# ///
"""
Maton API Gateway request script for run_skill.

Forward (app, path, method, body) to https://gateway.maton.ai/{app}/{path}.
The skill's references/ folder and Supported Services table tell the model the
correct app name and path; this script just makes the HTTP call.

Usage: request.py <app> <path> [method] [body_json_or_file@] [connection_id]
  app    - Service name (e.g. slack, hubspot, outlook, notion, google-mail)
  path   - Native API path for that service (e.g. api/chat.postMessage)
  method - GET (default), POST, PUT, PATCH, DELETE
  body   - JSON string, or path to JSON file prefixed with @ (e.g. @/path/to/body.json)
  connection_id - Optional; sets Maton-Connection header for multi-connection apps

Special subcommands:
  request.py discover              - List active connections via ctrl.maton.ai
  request.py connection <app>      - Check if app connection is active
  request.py services             - List all supported services from references/

API key: MATON_API_KEY env, or this skill's config.yml (maton_api_key).
  Env overrides config.

Headers auto-injected per service (Notion-Version, LinkedIn-Version, etc.).
httpx is used with retry logic for transient failures (429, 5xx).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Service-specific headers injected automatically
SERVICE_HEADERS: dict[str, dict[str, str]] = {
    "notion": {"Notion-Version": "2025-09-03"},
    "linkedin": {"LinkedIn-Version": "202506"},
    "github": {"X-GitHub-Api-Version": "2022-11-28"},
    "google-ads": {"developer-token": ""},   # token added below if set
    "google-ads-test": {"developer-token": ""},
}

# Base URL for the gateway
GATEWAY_BASE = "https://gateway.maton.ai"
CTRL_BASE = "https://ctrl.maton.ai"


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _get_api_key() -> str:
    """API key from (1) MATON_API_KEY env, (2) skill config.yml (maton_api_key). Env overrides."""
    key = (os.environ.get("MATON_API_KEY") or "").strip()
    if key:
        return key
    config_yml = _skill_root() / "config.yml"
    if config_yml.is_file():
        try:
            import yaml
            with open(config_yml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            key = (data.get("maton_api_key") or "").strip()
            if key and key != "YOUR_MATON_API_KEY":
                return key
        except Exception:
            pass
    return ""


def _is_multipart(body: str) -> bool:
    """Return True if body looks like multipart form data (starts with --)."""
    return bool(body and body.strip().startswith("--"))


def _resolve_body(body_arg: str) -> Optional[str]:
    """
    If body_arg starts with '@', treat the rest as a file path and read it.
    Otherwise return body_arg as-is.
    """
    if not body_arg or not body_arg.strip():
        return None
    body_arg = body_arg.strip()
    if body_arg.startswith("@"):
        file_path = body_arg[1:].strip()
        try:
            return Path(file_path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"Warning: could not read body file {file_path}: {e}", file=sys.stderr)
            return None
    return body_arg


def _get_service_headers(app: str) -> dict[str, str]:
    """Return auto-injected headers for a given app."""
    return dict(SERVICE_HEADERS.get(app.lower(), {}))


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Simple ASCII table formatter for list responses."""
    if not headers or not rows:
        return ""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    lines = []
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    lines.append(header_line)
    lines.append("  ".join("-" * w for w in col_widths))
    for row in rows:
        lines.append("  ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(row)))
    return "\n".join(lines)


def _format_json_list_as_table(data: Any, app: str) -> str:
    """
    Detect if data is a list of flat objects; if so, format as an ASCII table.
    """
    if not isinstance(data, list) or not data:
        return ""
    # Check if items are dicts with simple values
    if not all(isinstance(item, dict) for item in data[:3]):
        return ""
    # Use first item's keys as headers
    sample = data[0]
    flat_keys = [k for k, v in sample.items() if isinstance(v, (str, int, float, bool, type(None)))]
    if not flat_keys or len(flat_keys) > 8:
        return ""  # Too many or too few columns

    headers = flat_keys
    rows = []
    for item in data[:20]:  # cap at 20 rows
        rows.append([str(item.get(k, "")) for k in headers])

    return "\n" + _format_table(headers, rows) + f"\n\n({len(data)} total results)"


def _is_multipart(body: str) -> bool:
    """Return True if body looks like multipart form data (starts with --)."""
    return bool(body and body.strip().startswith("--"))


def _call_gateway(
    app: str,
    path: str,
    method: str = "GET",
    body: Optional[str] = None,
    connection_id: Optional[str] = None,
    api_key: str = "",
) -> dict[str, Any]:
    """
    Make an HTTP request to gateway.maton.ai with retry logic.
    Retries: 429 (with Retry-After), 500, 502, 503, 504.
    """
    import httpx

    url = f"{GATEWAY_BASE.rstrip('/')}/{app.strip('/')}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {api_key}"}
    headers.update(_get_service_headers(app))

    kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": httpx.Timeout(60.0, connect=10.0),
    }

    if body and method in ("POST", "PUT", "PATCH"):
        if _is_multipart(body):
            kwargs["content"] = body.encode("utf-8")
            # Don't set Content-Type for multipart; httpx will set multipart boundary
        else:
            kwargs["content"] = body.encode("utf-8")
            kwargs["headers"]["Content-Type"] = "application/json"

    if connection_id:
        kwargs["headers"]["Maton-Connection"] = connection_id

    retry_count = 0
    max_retries = 3

    while True:
        try:
            with httpx.Client() as client:
                response = client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            return {"success": False, "error": f"Request timed out after {retry_count + 1} attempt(s)"}
        except httpx.RequestError as e:
            return {"success": False, "error": f"Request failed: {e}"}

        status = response.status_code

        if status == 200:
            try:
                out = response.json()
            except json.JSONDecodeError:
                out = {"raw": response.text}
            return {"success": True, "data": out, "status_code": status}

        if status == 429 and retry_count < max_retries:
            retry_after = response.headers.get("Retry-After", "2")
            try:
                wait = float(retry_after)
            except (ValueError, TypeError):
                wait = 2.0
            time.sleep(wait)
            retry_count += 1
            continue

        if status >= 500 and retry_count < max_retries:
            wait = (2 ** retry_count) + 0.5
            time.sleep(wait)
            retry_count += 1
            continue

        # Non-retryable error
        try:
            err_body = response.json()
        except json.JSONDecodeError:
            err_body = {"raw": response.text}
        return {
            "success": False,
            "error": f"HTTP {status}: {response.reason_phrase}",
            "detail": err_body,
            "status_code": status,
        }


def _call_ctrl(
    path: str,
    method: str = "GET",
    body: Optional[str] = None,
    api_key: str = "",
) -> dict[str, Any]:
    """Call ctrl.maton.ai (connection management API)."""
    import httpx

    url = f"{CTRL_BASE.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    kwargs: dict[str, Any] = {"headers": headers, "timeout": httpx.Timeout(30.0)}

    if body and method in ("POST", "PUT", "PATCH"):
        kwargs["content"] = body.encode("utf-8")
        kwargs["headers"]["Content-Type"] = "application/json"

    try:
        with httpx.Client() as client:
            response = client.request(method, url, **kwargs)
        if response.status_code >= 400:
            try:
                err_body = response.json()
            except json.JSONDecodeError:
                err_body = {"raw": response.text}
            return {"success": False, "error": f"HTTP {response.status_code}", "detail": err_body}
        out = response.json() if response.text else {}
        return {"success": True, "data": out, "status_code": response.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}


def cmd_discover(api_key: str) -> dict[str, Any]:
    """List all active connections."""
    result = _call_ctrl("connections?status=ACTIVE&limit=50", api_key=api_key)
    if not result.get("success"):
        return result

    data = result.get("data", {})
    connections = data if isinstance(data, list) else data.get("connections", [])
    if not connections:
        print("No active connections found. Connect apps at https://www.maton.ai/")
        return {"success": True, "connections": []}

    lines = ["Active Maton Connections:", ""]
    headers = ["App", "Connection ID", "Status"]
    rows = []
    for conn in connections:
        rows.append([
            conn.get("app", ""),
            conn.get("id", "")[:20] + ("..." if len(conn.get("id", "")) > 20 else ""),
            conn.get("status", ""),
        ])
    lines.append(_format_table(headers, rows))
    lines.append("")
    lines.append("To add a new connection: https://www.maton.ai/")
    print("\n".join(lines))
    return {"success": True, "connections": connections}


def cmd_connection(app: str, api_key: str) -> dict[str, Any]:
    """Check if a specific app has an active connection."""
    result = _call_ctrl(f"connections?app={app}&status=ACTIVE&limit=5", api_key=api_key)
    if not result.get("success"):
        return result

    data = result.get("data", {})
    connections = data if isinstance(data, list) else data.get("connections", [])
    if not connections:
        print(f"No active connection for '{app}'. Connect it at https://www.maton.ai/")
        return {"success": True, "connected": False, "app": app}
    print(f"Active connection(s) for '{app}':")
    for conn in connections:
        print(f"  ID: {conn.get('id')}  Status: {conn.get('status')}")
    return {"success": True, "connected": True, "app": app, "connections": connections}


def cmd_services() -> dict[str, Any]:
    """List all supported services from the references/ folder."""
    ref_dir = _skill_root() / "references"
    if not ref_dir.is_dir():
        return {"success": False, "error": f"references/ folder not found at {ref_dir}"}
    services = sorted([p.stem for p in ref_dir.glob("*.md")])
    print(f"Supported services ({len(services)}):")
    # Print in columns
    cols = 4
    for i in range(0, len(services), cols):
        row = services[i : i + cols]
        print("  " + "  ".join(f"{s:<25}" for s in row))
    return {"success": True, "services": services}


def cmd_call(app: str, path: str, method: str, body: Optional[str], connection_id: Optional[str], api_key: str) -> dict[str, Any]:
    """Make a gateway API call."""
    result = _call_gateway(app, path, method, body, connection_id, api_key)

    if not result.get("success"):
        err_msg = f"Error: {result.get('error', 'unknown')}"
        detail = result.get("detail", {})
        if isinstance(detail, dict):
            # Surface structured error nicely
            code = detail.get("code") or detail.get("error_code") or detail.get("status")
            msg = detail.get("message") or detail.get("msg") or detail.get("error") or str(detail)
            if code or msg:
                err_msg = f"Error ({code}): {msg}" if code else f"Error: {msg}"
        print(err_msg, file=sys.stderr)
        return result

    data = result.get("data")

    # Try table formatting for list responses
    table = _format_json_list_as_table(data, app)
    if table:
        print(table)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))

    return result


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  request.py <app> <path> [method] [body|@file] [connection_id]", file=sys.stderr)
        print("  request.py discover", file=sys.stderr)
        print("  request.py connection <app>", file=sys.stderr)
        print("  request.py services", file=sys.stderr)
        return 1

    subcommand = sys.argv[1].strip().lower()

    api_key = _get_api_key()
    if not api_key or api_key == "YOUR_MATON_API_KEY":
        print(
            "Error: Maton API key not set.\n"
            "  1. Get your key at https://www.maton.ai/settings\n"
            "  2. Set: export MATON_API_KEY='your-key'\n"
            "  3. Or edit: skills/maton-api-gateway-1.0.0/config.yml",
            file=sys.stderr,
        )
        return 1

    # Subcommands
    if subcommand == "discover":
        result = cmd_discover(api_key)
        return 0 if result.get("success") else 1

    if subcommand == "connection":
        if len(sys.argv) < 3:
            print("Usage: request.py connection <app>", file=sys.stderr)
            return 1
        app = sys.argv[2].strip()
        result = cmd_connection(app, api_key)
        return 0 if result.get("success") else 1

    if subcommand == "services":
        result = cmd_services()
        return 0 if result.get("success") else 1

    # Gateway call: request.py <app> <path> [method] [body] [connection_id]
    if len(sys.argv) < 3:
        print("Usage: request.py <app> <path> [method] [body|@file] [connection_id]", file=sys.stderr)
        return 1

    app = sys.argv[1].strip()
    path = sys.argv[2].strip()
    method = (sys.argv[3].strip().upper() if len(sys.argv) > 3 else "GET") or "GET"
    body_raw = sys.argv[4].strip() if len(sys.argv) > 4 else ""
    connection_id = sys.argv[5].strip() if len(sys.argv) > 5 else ""

    body = _resolve_body(body_raw) if body_raw else None
    result = cmd_call(app, path, method, body, connection_id or None, api_key)

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
