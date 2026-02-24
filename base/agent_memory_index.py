"""
Index AGENT_MEMORY.md and daily memory (memory/YYYY-MM-DD.md) for semantic search.
Used when use_agent_memory_search is True: chunk files, embed, store in vector DB;
agent_memory_search / agent_memory_get tools then pull only relevant parts.
"""
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from base.workspace import (
    get_agent_memory_file_path,
    get_daily_memory_dir,
    get_daily_memory_path_for_date,
    ensure_daily_memory_file_exists,
    ensure_agent_memory_file_exists,
    _is_global_agent_memory_user,
    _sanitize_system_user_id,
)
from loguru import logger

# Relative path strings for display (markdown files). Global: AGENT_MEMORY.md, memory/YYYY-MM-DD.md. Per-user: agent_memory/{user_id}.md, daily_memory/{user_id}/YYYY-MM-DD.md
AGENT_MEMORY_REL = "AGENT_MEMORY.md"


def chunk_text_with_lines(text: str, max_chars: int = 1200) -> List[Dict[str, Any]]:
    """
    Chunk text by paragraphs (\\n\\n), then by size if a paragraph is too long.
    Returns list of {"snippet": str, "start_line": int, "end_line": int} (1-based lines). Never raises.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    try:
        max_chars = max(200, int(max_chars)) if max_chars is not None else 1200
    except (TypeError, ValueError):
        max_chars = 1200
    lines = text.split("\n")
    chunks = []
    current = []
    current_start = 1
    current_len = 0

    for i, line in enumerate(lines):
        line_num = i + 1
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > max_chars and current:
            snippet = "\n".join(current)
            chunks.append({
                "snippet": snippet,
                "start_line": current_start,
                "end_line": line_num - 1 if line_num > 1 else 1,
            })
            current = [line]
            current_start = line_num
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        snippet = "\n".join(current)
        chunks.append({
            "snippet": snippet,
            "start_line": current_start,
            "end_line": len(lines),
        })
    return chunks


def get_agent_memory_files_to_index(
    workspace_dir: Path,
    agent_memory_path: Optional[str],
    daily_memory_dir: Optional[str],
    date_today: Optional[date] = None,
    system_user_id: Optional[str] = None,
) -> List[Tuple[Path, str]]:
    """
    Return list of (absolute Path, relative_path_str) for markdown files to index.
    Global: "AGENT_MEMORY.md", "memory/YYYY-MM-DD.md". Per-user: "agent_memory/{user_id}.md", "daily_memory/{user_id}/YYYY-MM-DD.md". Never raises.
    """
    out: List[Tuple[Path, str]] = []
    try:
        workspace_dir = Path(workspace_dir) if workspace_dir is not None else None
        if workspace_dir is None:
            return []
    except Exception:
        return []
    try:
        today = date_today or date.today()
    except Exception:
        return []
    scope = "" if _is_global_agent_memory_user(system_user_id) else _sanitize_system_user_id(system_user_id)

    # AGENT_MEMORY (markdown): global AGENT_MEMORY.md or per-user agent_memory/{user_id}.md
    try:
        ensure_agent_memory_file_exists(workspace_dir=workspace_dir, agent_memory_path=agent_memory_path, system_user_id=system_user_id)
        agent_path = get_agent_memory_file_path(workspace_dir=workspace_dir, agent_memory_path=agent_memory_path, system_user_id=system_user_id)
        if agent_path is not None and agent_path.is_file():
            if scope:
                rel = f"agent_memory/{scope}.md"
            elif workspace_dir in agent_path.parents or agent_path == workspace_dir / AGENT_MEMORY_REL:
                rel = AGENT_MEMORY_REL
            else:
                rel = getattr(agent_path, "name", AGENT_MEMORY_REL)
            out.append((agent_path, rel))
    except Exception:
        pass

    # Daily memory (markdown): global memory/YYYY-MM-DD.md or per-user daily_memory/{user_id}/YYYY-MM-DD.md
    try:
        ensure_daily_memory_file_exists(today, workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
        base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
        for d in (today - timedelta(days=1), today):
            path = get_daily_memory_path_for_date(d, workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
            if path.is_file():
                if scope:
                    out.append((path, f"daily_memory/{scope}/{d.isoformat()}.md"))
                else:
                    out.append((path, f"memory/{d.isoformat()}.md"))
    except Exception:
        pass
    return out


async def sync_agent_memory_to_vector_store(
    workspace_dir: Path,
    agent_memory_path: Optional[str],
    daily_memory_dir: Optional[str],
    vector_store: Any,
    embedder: Any,
    date_today: Optional[date] = None,
    system_user_ids: Optional[List[Optional[str]]] = None,
) -> int:
    """
    (Re)index AGENT_MEMORY and daily memory markdown (yesterday + today) into the vector store.
    When system_user_ids is None: index global only (delete all, then insert). Backward compatible.
    When system_user_ids is provided: for each id delete that scope's chunks (delete_where), then index that scope. Payload includes system_user_id ("" for global).
    Returns total number of chunks indexed. Never raises.
    """
    if not vector_store or not embedder:
        return 0
    try:
        workspace_dir = Path(workspace_dir) if workspace_dir is not None else None
    except Exception:
        return 0
    if workspace_dir is None:
        return 0

    # Default: index global only (company app / single-tenant)
    scopes: List[Optional[str]] = list(system_user_ids) if system_user_ids is not None else [None]
    total = 0
    prefix = "agent_mem_"

    for system_user_id in scopes:
        scope_key = "" if _is_global_agent_memory_user(system_user_id) else _sanitize_system_user_id(system_user_id)
        scope_label = "global" if not scope_key else scope_key

        files = get_agent_memory_files_to_index(
            workspace_dir=workspace_dir,
            agent_memory_path=agent_memory_path,
            daily_memory_dir=daily_memory_dir,
            date_today=date_today,
            system_user_id=system_user_id,
        )
        if not files:
            continue

        # Delete existing chunks for this scope only (so we can re-index this user without wiping others)
        delete_where_fn = getattr(vector_store, "delete_where", None)
        if delete_where_fn:
            try:
                delete_where_fn({"system_user_id": scope_key})
            except Exception as e:
                logger.warning("Agent memory index: delete_where failed for scope {}: {}", scope_label, e)
        else:
            # Fallback: delete all when re-syncing (single scope at a time) so we don't leave stale chunks
            list_ids_fn = getattr(vector_store, "list_ids", None)
            if list_ids_fn and len(scopes) == 1:
                try:
                    existing = list_ids_fn(limit=10000)
                    for eid in existing:
                        try:
                            vector_store.delete(eid)
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("Agent memory index: list_ids failed: {}", e)

        vectors_list: List[List[float]] = []
        ids_list: List[str] = []
        payloads_list: List[Dict[str, Any]] = []

        for file_path, rel_path in files:
            try:
                content = file_path.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.warning("Agent memory index: could not read {}: {}", file_path, e)
                continue
            if not content:
                continue
            chunks = chunk_text_with_lines(content)
            safe_rel = rel_path.replace("/", "_").replace(".", "_")
            for idx, ch in enumerate(chunks):
                snippet = (ch.get("snippet") or "").strip()
                if not snippet:
                    continue
                try:
                    emb = await embedder.embed(snippet)
                    if not emb:
                        continue
                    vectors_list.append(emb)
                    vid = f"{prefix}{scope_label}_{safe_rel}_{idx}"
                    ids_list.append(vid)
                    payloads_list.append({
                        "path": rel_path,
                        "start_line": ch.get("start_line", 1),
                        "end_line": ch.get("end_line", 1),
                        "snippet": snippet[:2000],
                        "system_user_id": scope_key,
                    })
                except Exception as e:
                    logger.warning("Agent memory index: embed failed for {} chunk {}: {}", rel_path, idx, e)

        if ids_list:
            try:
                vector_store.insert(vectors=vectors_list, ids=ids_list, payloads=payloads_list)
                total += len(ids_list)
                logger.debug("Agent memory index: synced {} chunks for scope {}", len(ids_list), scope_label)
            except Exception as e:
                logger.warning("Agent memory index: insert failed for scope {}: {}", scope_label, e)

    return total
