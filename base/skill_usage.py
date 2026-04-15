"""
Per-user skill invocation counts for RAG reranking (design F).

Stores JSON under database/skill_usage.json. Safe no-op if IO fails.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger

from base.skills import TEST_ID_PREFIX

_USAGE_FILENAME = "skill_usage.json"


def _usage_path() -> Path:
    try:
        from base.util import Util

        return Path(Util().data_path()) / _USAGE_FILENAME
    except Exception:
        return Path("database") / _USAGE_FILENAME


def _load_store() -> Dict[str, Any]:
    p = _usage_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if not p.is_file():
        return {}
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("skill_usage load failed: {}", e)
        return {}


def _save_store(data: Dict[str, Any]) -> None:
    p = _usage_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
        os.replace(tmp, p)
    except Exception as e:
        logger.debug("skill_usage save failed: {}", e)


def _norm_user(user_id: str) -> str:
    s = (user_id or "").strip() or "_global"
    return s[:256]


def _norm_folder(folder: str) -> str:
    return (folder or "").strip()[:512]


def record_skill_invocation(user_id: str, skill_folder: str) -> None:
    """Increment count and last_ts for skill_folder under user_id. Never raises."""
    folder = _norm_folder(skill_folder)
    if not folder:
        return
    uid = _norm_user(user_id)
    try:
        store = _load_store()
        users = store.get("users")
        if not isinstance(users, dict):
            users = {}
            store["users"] = users
        ent_u = users.get(uid)
        if not isinstance(ent_u, dict):
            ent_u = {}
            users[uid] = ent_u
        cur = ent_u.get(folder)
        if not isinstance(cur, dict):
            cur = {"count": 0, "last_ts": 0.0}
        cur["count"] = int(cur.get("count") or 0) + 1
        cur["last_ts"] = time.time()
        ent_u[folder] = cur
        _save_store(store)
    except Exception as e:
        logger.debug("record_skill_invocation failed: {}", e)


def top_skill_folders(user_id: str, *, limit: int = 12) -> List[Tuple[str, int]]:
    """
    Return (skill_folder, count) for the user (or _global) sorted by descending count.
    Use to tune skills_include_body_for from real usage (see database/skill_usage.json).
    Never raises.
    """
    uid = _norm_user(user_id)
    lim = max(1, min(50, int(limit) if limit else 12))
    try:
        store = _load_store()
        users = store.get("users")
        if not isinstance(users, dict):
            return []
        ent_u = users.get(uid) or users.get("_global") or {}
        if not isinstance(ent_u, dict):
            return []
        rows: List[Tuple[str, int]] = []
        for folder, cur in ent_u.items():
            if not folder or not isinstance(cur, dict):
                continue
            c = max(0, int(cur.get("count") or 0))
            if c > 0:
                rows.append((str(folder), c))
        rows.sort(key=lambda x: -x[1])
        return rows[:lim]
    except Exception as e:
        logger.debug("top_skill_folders failed: {}", e)
        return []


def usage_boost_score(user_id: str, skill_folder: str) -> float:
    """
    Return a score in ~[0, 1] from frequency + recency for reranking.
    """
    folder = _norm_folder(skill_folder)
    if not folder:
        return 0.0
    uid = _norm_user(user_id)
    try:
        store = _load_store()
        users = store.get("users")
        if not isinstance(users, dict):
            return 0.0
        ent_u = users.get(uid) or users.get("_global") or {}
        if not isinstance(ent_u, dict):
            return 0.0
        cur = ent_u.get(folder)
        if not isinstance(cur, dict):
            return 0.0
        c = max(0, int(cur.get("count") or 0))
        last = float(cur.get("last_ts") or 0.0)
        freq = min(1.0, math.log1p(c) / math.log1p(25.0))
        if last <= 0:
            rec = 0.25
        else:
            age_days = max(0.0, (time.time() - last) / 86400.0)
            rec = 0.25 + 0.75 * math.exp(-age_days / 21.0)
        return max(0.0, min(1.0, 0.55 * freq + 0.45 * rec))
    except Exception:
        return 0.0


def rerank_skill_vector_hits(
    hits: List[Tuple[str, float]],
    user_id: str,
    *,
    weight: float = 0.12,
    enabled: bool = True,
) -> List[Tuple[str, float]]:
    """
    Reorder (skill_id, similarity) by effective_score = min(1.0, sim + weight * usage_boost).
    skill_id may be test__folder; boost uses the folder part after prefix.
    """
    if not enabled or not hits or weight <= 0:
        return hits

    def folder_key(sid: str) -> str:
        sid = str(sid or "")
        if sid.startswith(TEST_ID_PREFIX):
            return sid[len(TEST_ID_PREFIX) :]
        return sid

    scored: List[Tuple[str, float, float]] = []
    for sid, sim in hits:
        try:
            s = float(sim)
        except (TypeError, ValueError):
            s = 0.0
        b = usage_boost_score(user_id, folder_key(sid))
        eff = min(1.0, max(0.0, s + float(weight) * b))
        scored.append((sid, s, eff))
    scored.sort(key=lambda x: -x[2])
    return [(sid, sim) for sid, sim, _ in scored]
