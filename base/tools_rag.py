"""
RAG for tools (Phase 3.4): sync tool name+description to a vector store and retrieve by query.
Reuses the same vector store/embedder pattern as skills RAG. Off by default (tools_use_vector_search: false).
"""

from typing import Any, List, Tuple

from loguru import logger

from base.tools import ToolDefinition


def build_tool_refined_text(tool: ToolDefinition, include_short: bool = True) -> str:
    """
    Build text to embed for one tool: name + description (and optional short_description).
    Never raises; returns "" on error.
    """
    try:
        name = (getattr(tool, "name", None) or "").strip()
        desc = (getattr(tool, "description", None) or "").strip()
        parts = [name, desc] if name and desc else [name or desc]
        if include_short and getattr(tool, "short_description", None):
            short = (tool.short_description or "").strip()
            if short:
                parts.append(short)
        return "\n".join(parts).strip() or ""
    except Exception:
        return ""


async def sync_tools_to_vector_store(
    tools: List[ToolDefinition],
    vector_store: Any,
    embedder: Any,
) -> int:
    """
    Sync tool definitions to the vector store. Each tool is embedded as name + description (and short_description).
    Id = tool name. Returns the number of tools upserted.
    """
    if not tools or not vector_store or not embedder:
        return 0
    vectors_list: List[List[float]] = []
    ids_list: List[str] = []
    payloads_list: List[dict] = []
    for t in tools:
        name = getattr(t, "name", None) or ""
        if not name:
            continue
        refined = build_tool_refined_text(t)
        if not refined:
            continue
        try:
            emb = await embedder.embed(refined)
            if not emb:
                continue
            vectors_list.append(emb)
            ids_list.append(str(name))
            desc = (getattr(t, "description", None) or "").strip()[:500]
            payloads_list.append({"name": name, "description": desc})
        except Exception as e:
            logger.warning("Tool embed failed for {}: {}", name, e)
    if not ids_list:
        return 0
    try:
        vector_store.insert(vectors=vectors_list, ids=ids_list, payloads=payloads_list)
        return len(ids_list)
    except Exception as e:
        logger.warning("Tools vector insert failed: {}", e)
        return 0


async def search_tools_by_query(
    vector_store: Any,
    embedder: Any,
    query: str,
    limit: int = 10,
    min_similarity: float = 0.0,
) -> List[Tuple[str, float]]:
    """
    Search the tools vector store by query. Returns list of (tool_name, similarity).
    similarity = 1 - distance (for cosine distance). Results below min_similarity are dropped.
    """
    if not query or not query.strip():
        return []
    if not vector_store or not embedder:
        logger.debug("Tools vector search skipped: no store or embedder")
        return []
    try:
        emb = await embedder.embed(query.strip())
        if not emb:
            return []
    except Exception as e:
        logger.warning("Tools search embed failed: {}", e)
        return []
    try:
        results = vector_store.search(query=[emb], limit=limit, filters=None)
    except Exception as e:
        logger.warning("Tools vector search failed: {} ({})", e, type(e).__name__)
        return []
    out: List[Tuple[str, float]] = []
    for r in (results or []):
        try:
            vid = getattr(r, "id", None)
            if not vid and hasattr(r, "payload") and isinstance(getattr(r, "payload"), dict):
                vid = (getattr(r, "payload") or {}).get("name")
            if not vid:
                continue
            dist = getattr(r, "score", None)
            if dist is None:
                continue
            sim = 1.0 - float(dist)
            if sim >= min_similarity:
                out.append((str(vid), sim))
        except (TypeError, ValueError):
            continue
    return out
