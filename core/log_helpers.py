"""
Logging and string helpers for Core. Extracted from core/core.py (Phase 1 refactor).
No dependency on core.core; safe to import from core. Never raises; defensive.
"""
import json
import logging
import re
from typing import Optional

from loguru import logger

from base.util import Util


def _component_log(component: str, message: str) -> None:
    """Log component activity when core is not silent (silent: false in core.yml). Toggle via config/core.yml silent: true/false."""
    try:
        if not Util().is_silent():
            logger.info(f"[{component}] {message}")
    except Exception:
        pass


def _truncate_for_log(s: str, max_len: int = 2000) -> str:
    """Truncate string for logging; append ... if truncated."""
    if not s or len(s) <= max_len:
        return s or ""
    return s[:max_len] + "\n... (truncated)"


def _strip_leading_route_label(s: str) -> str:
    """Remove leading [Local], [Cloud], or [Local · ...] / [Cloud · ...] so we don't duplicate labels."""
    if not s or not isinstance(s, str):
        return s or ""
    t = s.strip()
    # Match [Local], [Cloud], or [Local · heuristic], [Cloud · semantic], etc.
    if re.match(r"^\[(?:Local|Cloud)(?:\s*·\s*[^\]]*)?\]\s*", t):
        return re.sub(r"^\[(?:Local|Cloud)(?:\s*·\s*[^\]]*)?\]\s*", "", t, count=1).strip()
    return s


def format_folder_list_file_find_result(raw: str, is_file_find: bool = False) -> Optional[str]:
    """
    Parse folder_list or file_find JSON result and return user-friendly text (header + bullet list).
    Returns None if raw is not valid list JSON or looks like an error message — caller can show raw or a fallback.
    Never raises.
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    # Do not try to parse error messages as JSON
    if s.startswith("That ") or s.startswith("Error") or s.startswith("Path is required") or s.startswith("No file") or s.startswith("No entries") or s.startswith("No files") or s.startswith("Could not") or s.startswith("View link") or "wasn't found" in s[:80] or "sandbox" in s[:100]:
        return None
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, list) or not data:
        return None
    lines = []
    for e in data:
        if not isinstance(e, dict):
            continue
        try:
            path_val = e.get("path") or e.get("name")
            if path_val == "(truncated)":
                continue
            name = str(e.get("name") or e.get("path") or "?").strip() or "?"
            p = str(e.get("path") or "").strip()
            typ = str(e.get("type") or "file").strip() or "file"
        except (TypeError, AttributeError, ValueError):
            continue
        if p and p != name and "/" in p:
            lines.append(f"- **{name}** ({typ}) — `{p}`")
        else:
            lines.append(f"- **{name}** ({typ})" + (f" — `{p}`" if p else ""))
    if not lines:
        return None
    header = "## 找到的文件 / Files found\n\n" if is_file_find else "## 目录下的内容 / Folder contents\n\n"
    return header + "\n".join(lines)


def format_web_search_result(raw: str) -> Optional[str]:
    """
    Parse web_search tool result (JSON with "results" array of {title, url, description}) and return readable list.
    Handles raw JSON or text containing a JSON object (e.g. "- **results:** {...}"). Returns None if not web_search format. Never raises.
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    if s.startswith("Error") or "error" in s[:100].lower():
        return None
    data = None
    try:
        # Try direct parse
        try:
            data = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            pass
        # If wrapped (e.g. header + JSON, or "Tool (web_search): {...}"), find JSON object. Prefer one containing "results".
        if data is None and "{" in s and '"results"' in s:
            start = s.index("{")
            # Try from first { to last }; if that fails (truncated), try shortening from the end until valid JSON
            for end in range(len(s), start, -1):
                if end <= start + 10:
                    break
                if s[end - 1] != "}":
                    continue
                try:
                    data = json.loads(s[start:end])
                    if isinstance(data, dict) and isinstance(data.get("results"), list):
                        break
                except (json.JSONDecodeError, TypeError):
                    pass
            else:
                data = None
        if data is None and "{" in s:
            start = s.index("{")
            end = s.rfind("}") + 1
            if end > start:
                try:
                    data = json.loads(s[start:end])
                except (json.JSONDecodeError, TypeError):
                    pass
        if data is None:
            return None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    try:
        if not isinstance(data, dict):
            return None
        results = data.get("results")
        if not isinstance(results, list) or not results:
            return None
        lines = []
        for i, e in enumerate(results[:15]):  # cap at 15
            if not isinstance(e, dict):
                continue
            try:
                title = str(e.get("title") or e.get("name") or "").strip() or "(no title)"
                url = str(e.get("url") or "").strip()
                desc = str(e.get("description") or "").strip()
                if url:
                    lines.append(f"- **{title}**\n  {url}" + (f"\n  {desc[:200]}…" if len(desc) > 200 else (f"\n  {desc}" if desc else "")))
                else:
                    lines.append(f"- **{title}**" + (f"\n  {desc[:200]}…" if len(desc) > 200 else (f"\n  {desc}" if desc else "")))
            except (TypeError, AttributeError, ValueError):
                continue
        if not lines:
            return None
        return "## 搜索结果 / Search results\n\n" + "\n\n".join(lines)
    except Exception:
        return None


def format_json_for_user(raw: str) -> Optional[str]:
    """
    Convert JSON to user-friendly text so we never show raw JSON to the end user.
    Returns None if raw is not JSON or conversion fails. Never raises.
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or (not s.startswith("[") and not s.startswith("{")):
        return None
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        if isinstance(data, list):
            if not data:
                return "No items."
            first = data[0]
            if isinstance(first, dict) and ("name" in first or "path" in first):
                lines = []
                for e in data:
                    if not isinstance(e, dict):
                        continue
                    try:
                        name = str(e.get("name") or e.get("path") or "?").strip() or "?"
                        p = str(e.get("path") or "").strip()
                        typ = str(e.get("type") or "file").strip() or "file"
                    except (TypeError, AttributeError, ValueError):
                        continue
                    if p and p != name and "/" in p:
                        lines.append(f"- **{name}** ({typ}) — `{p}`")
                    else:
                        lines.append(f"- **{name}** ({typ})" + (f" — `{p}`" if p else ""))
                if lines:
                    return "## 目录下的内容 / Folder contents\n\n" + "\n".join(lines)
            return "\n".join(f"- {_item_to_line(x)}" for x in data)
        if isinstance(data, dict):
            if "session_id" in data and "app_id" in data and "user_name" in data:
                app_id_val = str(data.get("app_id") or "HomeClaw")
                user_name_val = str(data.get("user_name") or "")
                if user_name_val:
                    return f"You're chatting with **{app_id_val}** as **{user_name_val}**. How can I help? （你正在与 {app_id_val} 对话，用户 {user_name_val}。需要什么帮助？）"
                return f"You're chatting with **{app_id_val}**. How can I help? （你正在与 {app_id_val} 对话。需要什么帮助？）"
            if data.get("scheduled") and ("job_id" in data or "cron_expr" in data):
                msg = str(data.get("message", "Scheduled reminder") or "Scheduled reminder")
                return f"**Recurring reminder scheduled.** I'll remind you: {msg}."
            if data.get("recorded") and ("event_name" in data or "when" in data):
                ev = str(data.get("event_name") or "event")
                wh = str(data.get("when") or "")
                return f"**Recorded:** {ev} on {wh}."
            return "\n".join(f"- **{k}:** {_item_to_line(v)}" for k, v in data.items())
        return str(data)
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def _item_to_line(x) -> str:
    """Convert a single JSON value to a short display line. Never raises."""
    try:
        if x is None:
            return ""
        if isinstance(x, bool):
            return "yes" if x else "no"
        if isinstance(x, (int, float)):
            return str(x)
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            return ", ".join(f"{k}={v}" for k, v in x.items())
        if isinstance(x, (list, tuple)):
            return ", ".join(str(i) for i in x)
        return str(x)
    except Exception:
        return str(x) if x is not None else ""


class _SuppressConfigCoreAccessFilter(logging.Filter):
    """Filter out uvicorn access log lines for GET /api/config/core (Companion connection checks)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage() if hasattr(record, "getMessage") else (getattr(record, "msg", "") or "")
            if "/api/config/core" in str(msg) and " 200 " in str(msg):
                return False
        except Exception:
            pass
        return True
