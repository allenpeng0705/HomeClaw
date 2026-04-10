"""
HomeClaw Claw-Code CLI — POST /api/clawcode/sessions, POST /inbound, optional trace SSE.

Usage:
  python3 -m main clawcode login [--url URL] [--key KEY] [--owner ID]
  python3 -m main clawcode session new [--cwd DIR]
  python3 -m main clawcode session list
  python3 -m main clawcode session show [--session ID]
  python3 -m main clawcode session set-meta [--session ID] [--git-remote-hint S] [--main-llm-ref S] [--tool-llm-ref S] [--mode plan|agent]
  python3 -m main clawcode session rebind [--session ID] --cwd DIR
  python3 -m main clawcode session worktree [--session ID]
  python3 -m main clawcode run [--session ID] [--stream] MESSAGE...
  python3 -m main clawcode attach
  python3 -m main clawcode approvals list
  python3 -m main clawcode approvals resolve --id UUID --decision approve|reject
  python3 -m main clawcode channel bind -s UUID --as-owner telegram_123
  python3 -m main clawcode channel status --as-owner telegram_123
  python3 -m main clawcode channel unbind --as-owner telegram_123
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Project root on path when run via python -m main
try:
    from base.util import Util
except ImportError:
    Util = None  # type: ignore


CONFIG_DIR_NAME = "homeclaw"
CONFIG_FILE_NAME = "clawcode.json"


def config_path() -> Path:
    return Path.home() / ".config" / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def load_config() -> Dict[str, Any]:
    p = config_path()
    if not p.is_file():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(cfg: Dict[str, Any]) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def default_core_base_url() -> str:
    if Util is None:
        return "http://127.0.0.1:9000"
    try:
        m = Util().get_core_metadata()
        h = (getattr(m, "host", None) or "127.0.0.1").strip() or "127.0.0.1"
        p = int(getattr(m, "port", None) or 9000)
        return f"http://{h}:{p}"
    except Exception:
        return "http://127.0.0.1:9000"


def normalize_base_url(url: str) -> str:
    """Strip trailing slash; caller supplies URL (no implicit default)."""
    return (url or "").strip().rstrip("/")


def auth_headers(cfg: Dict[str, Any]) -> Dict[str, str]:
    key = (cfg.get("api_key") or os.environ.get("HOMECLAW_API_KEY") or "").strip()
    if not key:
        return {}
    return {"X-API-Key": key}


def _client(timeout: float = 600.0) -> httpx.Client:
    return httpx.Client(timeout=timeout)


def cmd_login(ns: argparse.Namespace) -> int:
    cfg = load_config()
    url = (ns.url or cfg.get("core_base_url") or "").strip().rstrip("/")
    if not url:
        url = default_core_base_url()
    url = normalize_base_url(url)
    key = (ns.key or cfg.get("api_key") or os.environ.get("HOMECLAW_API_KEY") or "").strip()
    if not key and sys.stdin.isatty():
        try:
            key = input("API key (optional if Core auth disabled; press Enter to skip): ").strip()
        except EOFError:
            key = ""
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    cfg["core_base_url"] = url
    cfg["api_key"] = key
    cfg["owner_user_id"] = owner
    save_config(cfg)
    print(f"Saved Claw-Code CLI config: {config_path()}")
    print(f"  core_base_url={url}")
    print(f"  owner_user_id={owner}")
    print(f"  api_key={'(set)' if key else '(empty)'}")
    return 0


def _require_base_url(cfg: Dict[str, Any]) -> Optional[str]:
    raw = (cfg.get("core_base_url") or "").strip()
    if not raw:
        print("Run: python3 -m main clawcode login [--url http://127.0.0.1:9000] [--key KEY]")
        return None
    return normalize_base_url(raw)


def cmd_session_new(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    cwd = os.path.abspath(os.path.expanduser((ns.cwd or os.getcwd()).strip()))
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    body = {"owner_user_id": owner, "cwd": cwd}
    try:
        with _client(timeout=60.0) as client:
            r = client.post(
                f"{base}/api/clawcode/sessions",
                json=body,
                headers={**auth_headers(cfg), "Content-Type": "application/json"},
            )
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code == 404:
        print("Claw-Code API disabled on Core (set clawcode.enabled: true in core.yml).")
        return 1
    if r.status_code >= 400:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text
        print(f"Error {r.status_code}: {err}")
        return 1
    data = r.json()
    sid = data.get("clawcode_session_id") or data.get("session_id")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    if sid:
        cfg = load_config()
        cfg["default_clawcode_session_id"] = str(sid)
        cfg.setdefault("core_base_url", base)
        cfg.setdefault("owner_user_id", owner)
        save_config(cfg)
        print(f"\nSaved as default session (default_clawcode_session_id). Use: clawcode run -s {sid} \"hello\"")
    return 0


def cmd_session_list(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    try:
        with _client(timeout=60.0) as client:
            r = client.get(
                f"{base}/api/clawcode/sessions",
                params={"owner_user_id": owner},
                headers=auth_headers(cfg),
            )
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text[:2000]}")
        return 1
    data = r.json()
    sessions = data.get("sessions") or []
    if not sessions:
        print("No sessions.")
        return 0
    for s in sessions:
        lr = s.get("last_run_id")
        lr_s = f"  last_run={lr}" if lr else ""
        print(
            f"{s.get('clawcode_session_id')}  cwd={s.get('cwd')}  status={s.get('status')}  owner={s.get('owner_user_id')}{lr_s}"
        )
    return 0


def cmd_session_show(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    sid = (ns.session or cfg.get("default_clawcode_session_id") or "").strip()
    if not sid:
        print("Missing session: use --session UUID or run `session new` first.")
        return 2
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    try:
        with _client(timeout=60.0) as client:
            r = client.get(
                f"{base}/api/clawcode/sessions/{sid}",
                params={"owner_user_id": owner},
                headers=auth_headers(cfg),
            )
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text
        print(f"Error {r.status_code}: {err}")
        return 1
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)
    return 0


def cmd_session_set_meta(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    sid = (ns.session or cfg.get("default_clawcode_session_id") or "").strip()
    if not sid:
        print("Missing session: use --session UUID or run `session new` first.")
        return 2
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    body: Dict[str, Any] = {}
    if ns.git_remote_hint is not None:
        body["git_remote_hint"] = ns.git_remote_hint
    if ns.main_llm_ref is not None:
        body["main_llm_ref"] = ns.main_llm_ref
    if ns.tool_llm_ref is not None:
        body["tool_llm_ref"] = ns.tool_llm_ref
    if getattr(ns, "mode", None) is not None:
        body["mode"] = str(ns.mode).strip().lower()
    if not body:
        print("Provide at least one of --git-remote-hint, --main-llm-ref, --tool-llm-ref, --mode")
        return 2
    try:
        with _client(timeout=60.0) as client:
            r = client.patch(
                f"{base}/api/clawcode/sessions/{sid}",
                params={"owner_user_id": owner},
                headers=auth_headers(cfg),
                json=body,
            )
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text
        print(f"Error {r.status_code}: {err}")
        return 1
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)
    return 0


def cmd_session_rebind(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    sid = (ns.session or cfg.get("default_clawcode_session_id") or "").strip()
    if not sid:
        print("Missing session: use --session UUID or run `session new` first.")
        return 2
    cwd = (ns.cwd or "").strip()
    if not cwd:
        print("--cwd is required (absolute path on Core host).")
        return 2
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    try:
        with _client(timeout=60.0) as client:
            r = client.post(
                f"{base}/api/clawcode/sessions/{sid}/rebind",
                params={"owner_user_id": owner},
                headers=auth_headers(cfg),
                json={"cwd": cwd},
            )
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text
        print(f"Error {r.status_code}: {err}")
        return 1
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)
    return 0


def cmd_session_worktree(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    sid = (ns.session or cfg.get("default_clawcode_session_id") or "").strip()
    if not sid:
        print("Missing session: use --session UUID or run `session new` first.")
        return 2
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    try:
        with _client(timeout=60.0) as client:
            r = client.get(
                f"{base}/api/clawcode/sessions/{sid}",
                params={"owner_user_id": owner},
                headers=auth_headers(cfg),
            )
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text
        print(f"Error {r.status_code}: {err}")
        return 1
    try:
        data = r.json()
    except Exception:
        print(r.text)
        return 1
    hint = (data.get("worktree_hint") or "").strip()
    if hint:
        print(hint)
    else:
        print("(No worktree hint — session cwd missing or not a directory on Core.)")
    uh = (data.get("usage_hint") or "").strip()
    if uh:
        print()
        print("Usage / tokens:")
        print(uh)
    return 0


def _parse_inbound_sse(lines) -> tuple[bool, str, str]:
    """Consume iterable of line bytes/str; return (ok, text, error)."""
    final_text = ""
    err = ""
    ok = True
    saw_done = False
    for raw in lines:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        if not line.startswith("data: "):
            continue
        payload_s = line[6:].strip()
        if not payload_s or payload_s == "[DONE]":
            continue
        try:
            payload = json.loads(payload_s)
        except json.JSONDecodeError:
            continue
        ev = payload.get("event")
        if ev == "progress":
            msg = payload.get("message") or ""
            tool = payload.get("tool") or ""
            if msg or tool:
                print(f"[progress] {tool} {msg}".strip(), file=sys.stderr)
        elif ev == "done":
            saw_done = True
            ok = bool(payload.get("ok", True))
            final_text = str(payload.get("text") or "")
            err = str(payload.get("error") or "")
            if not ok and not err:
                err = "request failed"
    if not saw_done:
        return False, "", "inbound stream ended without a done event"
    return ok, final_text, err


def cmd_run(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    sid = (ns.session or cfg.get("default_clawcode_session_id") or "").strip()
    if not sid:
        print("Missing session: use --session UUID or run `session new` first.")
        return 2
    owner = (cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    message = " ".join(ns.message).strip()
    if not message:
        print("Message is required.")
        return 2
    body: Dict[str, Any] = {
        "user_id": owner,
        "user_name": owner,
        "text": message,
        "channel_name": "clawcode-cli",
        "clawcode_session_id": sid,
    }
    if ns.stream:
        body["stream"] = True
    h = {**auth_headers(cfg), "Content-Type": "application/json"}
    try:
        if ns.stream:
            with httpx.Client(timeout=600.0) as client:
                with client.stream("POST", f"{base}/inbound", json=body, headers=h) as r:
                    if r.status_code >= 400:
                        print(f"Error {r.status_code}: {r.text[:2000]}", file=sys.stderr)
                        return 1
                    ok, text, err = _parse_inbound_sse(r.iter_lines())
                    if not ok:
                        print(err or "failed", file=sys.stderr)
                        return 1
                    print(text)
                    return 0
        with _client() as client:
            r = client.post(f"{base}/inbound", json=body, headers=h)
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        try:
            j = r.json()
            err = j.get("error", r.text)
        except Exception:
            err = r.text
        print(f"Error {r.status_code}: {err}")
        return 1
    try:
        data = r.json()
    except Exception:
        print(r.text)
        return 0
    print(data.get("text") or "")
    if data.get("error"):
        print(data["error"], file=sys.stderr)
        return 1
    return 0


def cmd_attach(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    h = auth_headers(cfg)
    url = f"{base}/dev/workflow-trace/stream"
    print(f"Streaming {url} (Ctrl+C to stop)…", file=sys.stderr)
    try:
        with httpx.Client(timeout=None) as client:
            with client.stream("GET", url, headers=h) as r:
                if r.status_code >= 400:
                    print(f"Error {r.status_code}: {r.text[:2000]}", file=sys.stderr)
                    return 1
                for line in r.iter_lines():
                    if line:
                        s = line.decode("utf-8") if isinstance(line, bytes) else str(line)
                        if s.startswith("data: "):
                            print(s[6:])
                        elif s.startswith(":"):
                            pass
                        else:
                            print(s)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 0
    except httpx.RequestError as e:
        print(f"Stream failed: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_approvals_list(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    h = auth_headers(cfg)
    try:
        with _client() as client:
            r = client.get(f"{base}/api/clawcode/approvals", params={"owner_user_id": owner}, headers=h)
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text[:2000]}")
        return 1
    try:
        data = r.json()
    except Exception:
        print(r.text)
        return 0
    for row in data.get("approvals") or []:
        print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_approvals_resolve(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    owner = (ns.owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    aid = (ns.approval_id or "").strip()
    if not aid:
        print("Missing --id", file=sys.stderr)
        return 2
    h = {**auth_headers(cfg), "Content-Type": "application/json"}
    body = {"decision": ns.decision}
    try:
        with _client() as client:
            r = client.post(
                f"{base}/api/clawcode/approvals/{aid}/resolve",
                params={"owner_user_id": owner},
                json=body,
                headers=h,
            )
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text[:2000]}")
        return 1
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)
    return 0


def cmd_channel_status(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    owner = (ns.as_owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    h = auth_headers(cfg)
    try:
        with _client() as client:
            r = client.get(f"{base}/api/clawcode/channel-bindings", params={"owner_user_id": owner}, headers=h)
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text[:2000]}")
        return 1
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)
    return 0


def cmd_channel_bind(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    owner = (ns.as_owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    sid = (ns.session or "").strip()
    if not sid:
        print("Missing --session / -s", file=sys.stderr)
        return 2
    h = {**auth_headers(cfg), "Content-Type": "application/json"}
    try:
        with _client() as client:
            r = client.put(
                f"{base}/api/clawcode/channel-bindings",
                json={"owner_user_id": owner, "clawcode_session_id": sid},
                headers=h,
            )
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text[:2000]}")
        return 1
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)
    return 0


def cmd_channel_unbind(ns: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    base = _require_base_url(cfg)
    if not base:
        return 2
    owner = (ns.as_owner or cfg.get("owner_user_id") or "clawcode-cli").strip() or "clawcode-cli"
    h = auth_headers(cfg)
    try:
        with _client() as client:
            r = client.delete(f"{base}/api/clawcode/channel-bindings", params={"owner_user_id": owner}, headers=h)
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text[:2000]}")
        return 1
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawcode",
        description="HomeClaw Claw-Code CLI — sessions + inbound to Core",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_login = sub.add_parser("login", help="Save Core URL, optional API key, owner id")
    p_login.add_argument("--url", default="", help="Core base URL (default: from project core.yml or http://127.0.0.1:9000)")
    p_login.add_argument("--key", default="", help="X-API-Key when Core auth_enabled")
    p_login.add_argument("--owner", default="", help="owner_user_id for sessions/inbound (default: clawcode-cli)")

    p_sess = sub.add_parser("session", help="List or create coding sessions")
    sess_sub = p_sess.add_subparsers(dest="sess", required=True)
    p_new = sess_sub.add_parser("new", help="POST /api/clawcode/sessions")
    p_new.add_argument("--cwd", default="", help="Working directory (default: current directory)")
    p_new.add_argument("--owner", default="", help="Override owner_user_id (default: from login config)")
    p_list = sess_sub.add_parser("list", help="GET /api/clawcode/sessions")
    p_list.add_argument("--owner", default="", help="owner_user_id query (default: from config)")
    p_show = sess_sub.add_parser("show", help="GET /api/clawcode/sessions/{id}")
    p_show.add_argument("--session", "-s", default="", help="clawcode_session_id (default: saved default)")
    p_show.add_argument("--owner", default="", help="owner_user_id query (default: from config)")
    p_meta = sess_sub.add_parser(
        "set-meta",
        help="PATCH /api/clawcode/sessions/{id} (git_remote_hint, main_llm_ref, tool_llm_ref)",
    )
    p_meta.add_argument("--session", "-s", default="", help="clawcode_session_id (default: saved default)")
    p_meta.add_argument("--owner", default="", help="owner_user_id (default: from login config)")
    p_meta.add_argument(
        "--git-remote-hint",
        default=None,
        metavar="TEXT",
        help="set git_remote_hint (repeatable intent: pass \"\" to clear)",
    )
    p_meta.add_argument("--main-llm-ref", default=None, metavar="REF", help="set main_llm_ref")
    p_meta.add_argument("--tool-llm-ref", default=None, metavar="REF", help="set tool_llm_ref")
    p_meta.add_argument(
        "--mode",
        default=None,
        choices=("plan", "agent"),
        help="plan (read-biased tools) or agent (default tool policy)",
    )

    p_rebind = sess_sub.add_parser("rebind", help="POST /api/clawcode/sessions/{id}/rebind (change cwd)")
    p_rebind.add_argument("--session", "-s", default="", help="clawcode_session_id (default: saved default)")
    p_rebind.add_argument("--owner", default="", help="owner_user_id (default: from login config)")
    p_rebind.add_argument("--cwd", required=True, help="new working directory on Core host")

    p_wt = sess_sub.add_parser("worktree", help="Print git worktree + usage hints from session detail")
    p_wt.add_argument("--session", "-s", default="", help="clawcode_session_id (default: saved default)")
    p_wt.add_argument("--owner", default="", help="owner_user_id query (default: from config)")

    p_run = sub.add_parser("run", help="POST /inbound with clawcode_session_id")
    p_run.add_argument("--session", "-s", default="", help="Claw-Code session UUID (default: saved default)")
    p_run.add_argument("--stream", action="store_true", help="Inbound SSE (progress + final text)")
    p_run.add_argument("message", nargs="+", help="User message")

    sub.add_parser("attach", help="GET /dev/workflow-trace/stream (SSE JSON lines)")

    p_appr = sub.add_parser("approvals", help="Pending risky-tool approvals (P4)")
    appr_sub = p_appr.add_subparsers(dest="appr", required=True)
    p_alist = appr_sub.add_parser("list", help="GET /api/clawcode/approvals")
    p_alist.add_argument("--owner", default="", help="owner_user_id (default: from login config)")
    p_aresv = appr_sub.add_parser("resolve", help="POST /api/clawcode/approvals/{id}/resolve")
    p_aresv.add_argument("--id", dest="approval_id", required=True, help="approval_id from blocked tool message")
    p_aresv.add_argument("--decision", required=True, choices=["approve", "reject"])
    p_aresv.add_argument("--owner", default="", help="owner_user_id (default: from login config)")

    p_ch = sub.add_parser("channel", help="IM channel binding (Telegram/Discord identity → session, P5)")
    ch_sub = p_ch.add_subparsers(dest="chcmd", required=True)
    p_cst = ch_sub.add_parser("status", help="GET /api/clawcode/channel-bindings")
    p_cst.add_argument(
        "--as-owner",
        default="",
        help="Inbound user_id to query (e.g. telegram_123 or discord_456); default: login owner_user_id",
    )
    p_cbind = ch_sub.add_parser("bind", help="PUT /api/clawcode/channel-bindings")
    p_cbind.add_argument("--session", "-s", required=True, help="clawcode_session_id (session owner must match --as-owner)")
    p_cbind.add_argument(
        "--as-owner",
        default="",
        help="Must match session owner_user_id and channel inbound user_id (e.g. telegram_<chat_id>)",
    )
    p_cun = ch_sub.add_parser("unbind", help="DELETE /api/clawcode/channel-bindings")
    p_cun.add_argument(
        "--as-owner",
        default="",
        help="Inbound user_id to clear (default: login owner_user_id)",
    )

    return parser


def run_cli(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as e:
        code = getattr(e, "code", None)
        if code is None:
            return 0
        return int(code) if isinstance(code, int) else 2

    cfg = load_config()

    if ns.cmd == "login":
        return cmd_login(ns)
    if ns.cmd == "session":
        if ns.sess == "new":
            return cmd_session_new(ns, cfg)
        if ns.sess == "list":
            return cmd_session_list(ns, cfg)
        if ns.sess == "show":
            return cmd_session_show(ns, cfg)
        if ns.sess == "set-meta":
            return cmd_session_set_meta(ns, cfg)
        if ns.sess == "rebind":
            return cmd_session_rebind(ns, cfg)
        if ns.sess == "worktree":
            return cmd_session_worktree(ns, cfg)
        return 2
    if ns.cmd == "run":
        return cmd_run(ns, cfg)
    if ns.cmd == "attach":
        return cmd_attach(ns, cfg)
    if ns.cmd == "approvals":
        if ns.appr == "list":
            return cmd_approvals_list(ns, cfg)
        if ns.appr == "resolve":
            return cmd_approvals_resolve(ns, cfg)
        return 2
    if ns.cmd == "channel":
        if ns.chcmd == "status":
            return cmd_channel_status(ns, cfg)
        if ns.chcmd == "bind":
            return cmd_channel_bind(ns, cfg)
        if ns.chcmd == "unbind":
            return cmd_channel_unbind(ns, cfg)
        return 2
    return 2


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
