"""
Plugin registration and vector sync for RAG-based plugin discovery.

Same design as skills: plugins are synced to a vector store (description + description_long
embedded). Core uses search_plugins_by_query() to find relevant plugins by user query, then
injects only those into the system prompt (or tools) to avoid context length limits.

See docs/PluginRegistration.md for the unified registration schema (capabilities, parameters,
post_process, persistence).
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


def build_plugin_refined_text(plugin: Dict[str, Any], description_long_max_chars: int = 500) -> str:
    """
    Build the text to embed for a plugin (name + description + optional description_long).
    Used for vector storage and similarity search.
    """
    name = (plugin.get("name") or "").strip()
    desc = (plugin.get("description") or "").strip()
    parts = [name, desc] if name and desc else [name or desc]
    long_desc = (plugin.get("description_long") or "").strip()
    if description_long_max_chars and long_desc:
        parts.append(long_desc[:description_long_max_chars])
    return "\n".join(parts).strip() or ""


def build_plugins_system_block(plugins: List[Dict[str, Any]], include_capabilities: bool = False) -> str:
    """
    Build a system-prompt block listing available plugins (id, name, description).
    Optionally include capability ids so the LLM knows what to call.
    """
    if not plugins:
        return ""
    lines = ["## Available plugins", ""]
    for p in plugins:
        pid = p.get("id") or "(no-id)"
        name = p.get("name") or pid
        desc = (p.get("description") or "").strip()
        line = f"- **{name}** (plugin_id: `{pid}`): {desc}" if desc else f"- **{name}** (plugin_id: `{pid}`)"
        lines.append(line)
        if include_capabilities and p.get("capabilities"):
            caps = [c.get("id") or c.get("name") for c in p["capabilities"] if c]
            if caps:
                lines.append("  Capabilities: " + ", ".join(caps))
        lines.append("")
    return "\n".join(lines).strip() + "\n\n"


async def sync_plugins_to_vector_store(
    plugins: List[Dict[str, Any]],
    vector_store: Any,
    embedder: Any,
    description_long_max_chars: int = 500,
    incremental: bool = False,
) -> int:
    """
    Sync plugin registrations to the vector store.
    plugins: list of dicts with at least id, name, description; optional description_long.
    incremental: if True, skip plugins already in store (get(id) is not None).
    Returns the number of plugins upserted.
    """
    if not plugins:
        return 0
    vectors_list: List[List[float]] = []
    ids_list: List[str] = []
    payloads_list: List[Dict[str, Any]] = []
    for p in plugins:
        pid = (p.get("id") or "").strip().lower().replace(" ", "_")
        if not pid:
            continue
        if incremental:
            try:
                existing = vector_store.get(pid)
                if existing is not None:
                    continue
            except Exception:
                pass
        refined = build_plugin_refined_text(p, description_long_max_chars=description_long_max_chars)
        if not refined:
            continue
        try:
            emb = await embedder.embed(refined)
            if not emb:
                continue
            vectors_list.append(emb)
            ids_list.append(pid)
            payloads_list.append({
                "id": pid,
                "name": p.get("name") or "",
                "description": (p.get("description") or "").strip(),
            })
        except Exception as e:
            logger.warning("Plugin embed failed for %s: %s", pid, e)
    if not ids_list:
        return 0
    try:
        vector_store.insert(vectors=vectors_list, ids=ids_list, payloads=payloads_list)
        return len(ids_list)
    except Exception as e:
        logger.warning("Plugin vector insert failed: %s", e)
        return 0


async def search_plugins_by_query(
    vector_store: Any,
    embedder: Any,
    query: str,
    limit: int = 10,
    min_similarity: float = 0.0,
) -> List[Tuple[str, float]]:
    """
    Search the plugins vector store by query. Returns list of (plugin_id, similarity).
    similarity = 1 - distance (for cosine distance). Results below min_similarity are dropped.
    """
    if not query or not query.strip():
        return []
    try:
        emb = await embedder.embed(query.strip())
        if not emb:
            return []
    except Exception as e:
        logger.warning("Plugin search embed failed: %s", e)
        return []
    try:
        results = vector_store.search(query=[emb], limit=limit, filters=None)
    except Exception as e:
        logger.warning("Plugin vector search failed: %s", e)
        return []
    out: List[Tuple[str, float]] = []
    for r in results:
        vid = getattr(r, "id", None)
        if not vid and hasattr(r, "payload") and isinstance(r.payload, dict):
            vid = r.payload.get("id")
        if not vid:
            continue
        dist = getattr(r, "score", None)
        if dist is None:
            continue
        sim = 1.0 - float(dist)
        if sim >= min_similarity:
            out.append((str(vid), sim))
    return out
