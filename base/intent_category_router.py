"""
Semantic intent-category routing helpers.

Uses markdown files under config/intent_category as category docs, embeds the text,
stores vectors, and retrieves top matches for a user query.

Category identity, classifier blurbs, and optional regex fast paths can live in each
file's YAML frontmatter (see merge_intent_router_config_with_docs).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from loguru import logger

# Cached manifest by docs dir mtime (invalidates when any .md changes).
_manifest_cache_key: Optional[str] = None
_manifest_cache_val: Optional[Dict[str, Any]] = None


def _split_frontmatter_raw(text: str) -> Tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---", 4)
    if end < 0:
        return "", text
    return text[4:end].strip(), text[end + 4 :].lstrip()


def parse_intent_category_yaml_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter; return (dict, body after closing ---). Empty dict if unparseable."""
    fm_raw, body = _split_frontmatter_raw(text)
    if not fm_raw:
        return {}, text
    try:
        fm = yaml.safe_load(fm_raw)
    except Exception:
        return {}, text
    if not isinstance(fm, dict):
        return {}, text
    return fm, body


def _section(text: str, heading: str) -> str:
    pat = rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^\s*##\s+|\Z)"
    m = re.search(pat, text)
    return (m.group(1).strip() if m else "")


def _max_mtime_md(docs_dir: Path) -> float:
    m = 0.0
    try:
        for p in docs_dir.glob("*.md"):
            if p.name.startswith("_") or p.name.lower() == "readme.md":
                continue
            m = max(m, p.stat().st_mtime)
    except Exception:
        return 0.0
    return m


def clear_intent_category_manifest_cache() -> None:
    """Clear cached manifest (e.g. for tests)."""
    global _manifest_cache_key, _manifest_cache_val
    _manifest_cache_key = None
    _manifest_cache_val = None


def load_intent_category_manifest(docs_dir: Path) -> Dict[str, Any]:
    """
    Scan intent category markdown files and build:
    - categories: ordered list (priority desc, then id)
    - category_descriptions: id -> one-line blurb for classifier prompt
    - pattern_entries: list of {id, priority, patterns} for re.search fast path
    - category_tools_map: id -> category_tools dict (profile / tools / skills)
    """
    out: Dict[str, Any] = {
        "categories": [],
        "category_descriptions": {},
        "pattern_entries": [],
        "category_tools_map": {},
    }
    if not docs_dir.is_dir():
        return out
    rows: List[Tuple[int, str, str]] = []
    pattern_entries: List[Dict[str, Any]] = []
    for p in sorted(docs_dir.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, body = parse_intent_category_yaml_frontmatter(txt)
        if fm.get("enabled") is False:
            continue
        cid = str(fm.get("id") or p.stem).strip()
        if not cid:
            continue
        try:
            priority = int(fm.get("priority", 50) or 50)
        except (TypeError, ValueError):
            priority = 50
        classifier_blurb = fm.get("classifier_description")
        if isinstance(classifier_blurb, str) and classifier_blurb.strip():
            desc = " ".join(classifier_blurb.split()).strip()
        else:
            desc_block = _section(body, "Description")
            first = (desc_block.split("\n")[0] if desc_block else "").strip()
            desc = first
            if len(desc) > 320:
                desc = desc[:317] + "..."
        rows.append((priority, cid, desc))
        out["category_descriptions"][cid] = desc
        pats = fm.get("match_patterns")
        if isinstance(pats, list) and pats:
            clean = [str(x).strip() for x in pats if x is not None and str(x).strip()]
            if clean:
                pattern_entries.append({"id": cid, "priority": priority, "patterns": clean})
        ct = fm.get("category_tools")
        if isinstance(ct, dict) and ct:
            out["category_tools_map"][cid] = ct
    rows.sort(key=lambda x: (-x[0], x[1]))
    out["categories"] = [x[1] for x in rows]
    pattern_entries.sort(key=lambda x: (-int(x.get("priority") or 50), str(x.get("id") or "")))
    out["pattern_entries"] = pattern_entries
    return out


def get_intent_category_manifest_cached(docs_dir: Path) -> Dict[str, Any]:
    global _manifest_cache_key, _manifest_cache_val
    if not docs_dir.is_dir():
        return {"categories": [], "category_descriptions": {}, "pattern_entries": [], "category_tools_map": {}}
    mtime = _max_mtime_md(docs_dir)
    key = f"{docs_dir.resolve()}:{mtime}"
    if _manifest_cache_key == key and isinstance(_manifest_cache_val, dict):
        return _manifest_cache_val
    man = load_intent_category_manifest(docs_dir)
    _manifest_cache_key = key
    _manifest_cache_val = man
    return man


def _intent_category_docs_dir_resolved(config: Dict[str, Any]) -> Optional[Path]:
    """Return relative or absolute Path to category docs, or None when overlay is disabled."""
    raw = config.get("intent_category_docs_dir")
    if raw is None:
        rel = "config/intent_category"
    else:
        rel = str(raw).strip()
    low = rel.lower()
    if not rel or low in ("none", "false", "disabled", "-"):
        return None
    p = Path(rel)
    return p


def merge_intent_router_config_with_docs(
    config: Dict[str, Any],
    *,
    root_path: Path,
    default_descriptions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Load category ids, classifier blurbs, match_patterns, and category_tools from
    config/intent_category/*.md when intent_category_docs_dir is set (default: config/intent_category).
    Set intent_category_docs_dir to "" to disable and use only YAML categories / category_tools.

    Per-file frontmatter ``category_tools`` merges over YAML ``category_tools`` (markdown wins on conflict).
    """
    out = dict(config) if isinstance(config, dict) else {}
    rel_path = _intent_category_docs_dir_resolved(out)
    if rel_path is None:
        return out
    docs_path = rel_path if rel_path.is_absolute() else (root_path / rel_path)
    manifest = get_intent_category_manifest_cached(docs_path)
    cats = manifest.get("categories") if isinstance(manifest.get("categories"), list) else []
    if not cats:
        logger.warning(
            "No intent categories found under {}; using YAML categories if present",
            docs_path,
        )
        return out
    out["categories"] = cats
    merged_desc: Dict[str, str] = {}
    if isinstance(default_descriptions, dict):
        merged_desc.update(default_descriptions)
    md_desc = manifest.get("category_descriptions")
    if isinstance(md_desc, dict):
        merged_desc.update({str(k): str(v).strip() for k, v in md_desc.items() if k and v})
    out["category_descriptions"] = merged_desc
    out["_doc_pattern_entries"] = manifest.get("pattern_entries") or []
    yaml_ct = out.get("category_tools")
    if not isinstance(yaml_ct, dict):
        yaml_ct = {}
    doc_ct = manifest.get("category_tools_map")
    if not isinstance(doc_ct, dict):
        doc_ct = {}
    out["category_tools"] = {**yaml_ct, **doc_ct}
    return out


def load_intent_category_docs(
    docs_dir: Path,
    allowed_categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if not docs_dir.is_dir():
        return []
    allowed = {str(x).strip() for x in (allowed_categories or []) if str(x).strip()}
    docs: List[Dict[str, Any]] = []
    for p in sorted(docs_dir.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, body = parse_intent_category_yaml_frontmatter(txt)
        if fm.get("enabled") is False:
            continue
        cid = str(fm.get("id") or p.stem).strip()
        if not cid:
            continue
        if allowed and cid not in allowed:
            continue
        desc = _section(body, "Description")
        pos = _section(body, "Positive examples")
        neg = _section(body, "Negative boundaries")
        hints = _section(body, "Workflow hints")
        display = str(fm.get("display_name") or cid).strip()
        try:
            priority = int(fm.get("priority", 50) or 50)
        except (TypeError, ValueError):
            priority = 50
        mp = fm.get("match_patterns")
        if isinstance(mp, list) and mp:
            patt_lines = "\n".join(f"- {x}" for x in mp if x is not None and str(x).strip())
        else:
            patt_lines = ""
        parts = [
            f"id: {cid}",
            f"display_name: {display}",
            f"description: {desc}",
            f"positive_examples:\n{pos}",
            f"negative_boundaries:\n{neg}",
            f"workflow_hints:\n{hints}",
        ]
        if patt_lines:
            parts.append(f"match_patterns:\n{patt_lines}")
        docs.append(
            {
                "id": cid,
                "display_name": display,
                "priority": priority,
                "path": str(p),
                "text": "\n".join(parts).strip(),
            }
        )
    return docs


INTENT_CATEGORY_EMBED_STATE_VERSION = 1


def intent_category_embed_state_path() -> Path:
    """JSON path recording last embedded path+mtime per category id (under database/)."""
    from base.util import Util

    return Path(Util().data_path()) / "intent_category_vector_sync.json"


def _load_intent_category_embed_state(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": INTENT_CATEGORY_EMBED_STATE_VERSION, "entries": {}}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return {"version": INTENT_CATEGORY_EMBED_STATE_VERSION, "entries": {}}
    if not isinstance(data, dict):
        return {"version": INTENT_CATEGORY_EMBED_STATE_VERSION, "entries": {}}
    ent = data.get("entries")
    if not isinstance(ent, dict):
        ent = {}
    return {"version": int(data.get("version") or INTENT_CATEGORY_EMBED_STATE_VERSION), "entries": ent}


def _save_intent_category_embed_state(path: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": INTENT_CATEGORY_EMBED_STATE_VERSION, "entries": entries}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _resolved_source_path(path_str: str) -> Tuple[Optional[Path], str]:
    p = Path(path_str)
    try:
        rp = p.resolve()
        return rp, str(rp)
    except Exception:
        return None, str(p)


def _file_mtime(path: Path) -> float:
    try:
        return float(path.stat().st_mtime)
    except Exception:
        return 0.0


def _vector_store_upsert_intent_categories(
    vector_store: Any,
    vectors: List[List[float]],
    ids: List[str],
    payloads: List[Dict[str, Any]],
) -> None:
    """Chroma collection.add() fails on duplicate ids; Qdrant insert upserts."""
    if not ids:
        return
    if type(vector_store).__name__ == "ChromaDB":
        inserts_v: List[List[float]] = []
        inserts_i: List[str] = []
        inserts_p: List[Dict[str, Any]] = []
        for i, vid in enumerate(ids):
            try:
                ex = vector_store.get(vid)
            except Exception:
                ex = None
            if ex is not None:
                vector_store.update(vid, vector=vectors[i], payload=payloads[i])
            else:
                inserts_v.append(vectors[i])
                inserts_i.append(vid)
                inserts_p.append(payloads[i])
        if inserts_v:
            vector_store.insert(vectors=inserts_v, ids=inserts_i, payloads=inserts_p)
    else:
        vector_store.insert(vectors=vectors, ids=ids, payloads=payloads)


async def sync_intent_categories_to_vector_store(
    docs_dir: Path,
    vector_store: Any,
    embedder: Any,
    allowed_categories: Optional[List[str]] = None,
    incremental: bool = True,
    state_path: Optional[Path] = None,
) -> int:
    """
    Embed category docs and upsert into the vector store.

    When ``incremental`` is True (default), reads/writes ``intent_category_vector_sync.json``
    and only embeds categories whose source file path or mtime changed, or that are new.
    Removed categories are deleted from the store and state. Returns the number of vectors
    embedded (insert or update); 0 when nothing required re-embedding.
    """
    docs = load_intent_category_docs(docs_dir, allowed_categories=allowed_categories)
    sp = state_path if state_path is not None else intent_category_embed_state_path()
    state = _load_intent_category_embed_state(sp)
    entries: Dict[str, Dict[str, Any]] = {}
    raw_ent = state.get("entries")
    if isinstance(raw_ent, dict):
        for k, v in raw_ent.items():
            cid = str(k).strip()
            if cid and isinstance(v, dict):
                entries[cid] = dict(v)

    current_ids = {str(d["id"]).strip() for d in docs if str(d.get("id") or "").strip()}
    removed = 0
    for stale_id in list(entries.keys()):
        if stale_id not in current_ids:
            try:
                vector_store.delete(stale_id)
            except Exception as e:
                logger.debug("intent category delete stale id {}: {}", stale_id, e)
            entries.pop(stale_id, None)
            removed += 1

    to_embed: List[Dict[str, Any]] = []
    for d in docs:
        cid = str(d.get("id") or "").strip()
        if not cid:
            continue
        path_str = str(d.get("path") or "").strip()
        rp, resolved = _resolved_source_path(path_str)
        mtime = _file_mtime(rp) if rp and rp.is_file() else 0.0
        if incremental:
            prev = entries.get(cid)
            if isinstance(prev, dict):
                try:
                    pm = float(prev.get("mtime", 0.0))
                except (TypeError, ValueError):
                    pm = 0.0
                ppath = str(prev.get("path") or "")
                if ppath == resolved and abs(pm - mtime) < 1e-6:
                    continue
        to_embed.append(d)

    if not to_embed:
        if removed:
            _save_intent_category_embed_state(sp, entries)
        return 0

    vectors: List[List[float]] = []
    ids: List[str] = []
    payloads: List[Dict[str, Any]] = []
    for d in to_embed:
        text = (d.get("text") or "").strip()
        if not text:
            continue
        cid = str(d["id"])
        path_str = str(d.get("path") or "").strip()
        rp, resolved = _resolved_source_path(path_str)
        mtime = _file_mtime(rp) if rp and rp.is_file() else 0.0
        try:
            emb = await embedder.embed(text)
        except Exception as e:
            logger.debug("intent category embed failed {}: {}", cid, e)
            emb = None
        if not emb:
            continue
        vectors.append(emb)
        ids.append(cid)
        payloads.append(
            {
                "id": cid,
                "display_name": str(d.get("display_name") or cid),
                "priority": int(d.get("priority", 50) or 50),
                "path": path_str,
                "source_path": resolved,
                "source_mtime": mtime,
            }
        )
    if not ids:
        if removed:
            _save_intent_category_embed_state(sp, entries)
        return 0

    _vector_store_upsert_intent_categories(vector_store, vectors, ids, payloads)

    for d in to_embed:
        cid = str(d.get("id") or "").strip()
        if not cid:
            continue
        path_str = str(d.get("path") or "").strip()
        rp, resolved = _resolved_source_path(path_str)
        mtime = _file_mtime(rp) if rp and rp.is_file() else 0.0
        if cid in ids:
            entries[cid] = {"path": resolved, "mtime": mtime}

    _save_intent_category_embed_state(sp, entries)
    return len(ids)


async def search_intent_categories_by_query(
    vector_store: Any,
    embedder: Any,
    query: str,
    limit: int = 20,
    min_similarity: float = 0.0,
    allowed_categories: Optional[List[str]] = None,
) -> List[Tuple[str, float]]:
    q = (query or "").strip()
    if not q:
        return []
    emb = await embedder.embed(q)
    if not emb:
        return []
    out = vector_store.search([emb], limit=max(1, int(limit or 20)))
    allowed = {str(x).strip() for x in (allowed_categories or []) if str(x).strip()}
    hits: List[Tuple[str, float]] = []
    for item in out or []:
        try:
            cid = str(getattr(item, "id", "") or "").strip()
            if not cid:
                continue
            if allowed and cid not in allowed:
                continue
            dist = float(getattr(item, "score", 1.0) or 1.0)
            sim = max(0.0, min(1.0, 1.0 - dist))
            if sim >= float(min_similarity or 0.0):
                hits.append((cid, sim))
        except Exception:
            continue
    return hits


def rerank_intent_hits(query: str, hits: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """Lightweight lexical rerank on top of vector similarity."""
    q = (query or "").lower()
    if not q or not hits:
        return hits or []
    out: List[Tuple[str, float]] = []
    for cid, sim in hits:
        bonus = 0.0
        cid_l = (cid or "").lower()
        if cid_l and cid_l in q:
            bonus += 0.15
        for tok in re.split(r"[_\-\s]+", cid_l):
            tok = tok.strip()
            if tok and tok in q:
                bonus += 0.03
        out.append((cid, min(1.0, sim + bonus)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out
