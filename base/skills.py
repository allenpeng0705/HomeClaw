"""
Skill loader: read SKILL.md (YAML frontmatter + body) from a directory.

Skills are folders containing SKILL.md. Used to inject "Available skills" into the system
prompt so the model knows about them. See Design.md §3.6 and config/skills/README.md.

Vector retrieval: sync_skills_to_vector_store() and search_skills_by_query() for persistent
registration and retrieval by user query (docs/ToolsSkillsPlugins.md §8).
"""
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import yaml
from loguru import logger

# Project root: parent of base/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SKILLS_DIR = _PROJECT_ROOT / "config" / "skills"

SKILL_FILENAME = "SKILL.md"
USAGE_FILENAME = "USAGE.md"


def _parse_skill_md(content: str) -> Dict[str, Any]:
    """
    Parse SKILL.md: YAML frontmatter between --- and ---, then body.
    Returns {"name": str, "description": str, "body": str, **frontmatter}.
    """
    result: Dict[str, Any] = {"name": "", "description": "", "body": ""}
    if not content or "---" not in content:
        result["body"] = content or ""
        return result
    parts = content.split("---", 2)
    if len(parts) < 3:
        result["body"] = content
        return result
    # parts[0] may be empty or whitespace before first ---
    frontmatter_str = parts[1].strip()
    result["body"] = parts[2].strip()
    if not frontmatter_str:
        return result
    try:
        fm = yaml.safe_load(frontmatter_str)
        if isinstance(fm, dict):
            result["name"] = fm.get("name") or ""
            result["description"] = fm.get("description") or ""
            for k, v in fm.items():
                if k not in result:
                    result[k] = v
    except Exception as e:
        logger.warning("Failed to parse SKILL.md frontmatter: {}", e)
    return result


# Max chars of USAGE.md to append to skill body (0 = do not append). Keeps context small; full USAGE.md stays on disk for file_read.
USAGE_APPEND_MAX_CHARS = 2200


def _append_usage_if_present(skill_dir: Path, parsed: Dict[str, Any]) -> None:
    """If USAGE.md exists in skill_dir, append up to USAGE_APPEND_MAX_CHARS to parsed['body']. Modifies parsed in place."""
    if not USAGE_APPEND_MAX_CHARS or not parsed.get("body"):
        return
    usage_file = skill_dir / USAGE_FILENAME
    if not usage_file.is_file():
        return
    try:
        usage_content = usage_file.read_text(encoding="utf-8", errors="replace").strip()
        if usage_content:
            if len(usage_content) > USAGE_APPEND_MAX_CHARS:
                usage_content = usage_content[: USAGE_APPEND_MAX_CHARS] + "\n\n*(Full list: see USAGE.md in this skill folder.)*"
            parsed["body"] = (parsed["body"] or "").strip() + "\n\n## User guide (how to ask)\n\n" + usage_content
    except Exception as e:
        logger.warning("Failed to read {}: {}", usage_file, e)


def get_skills_dir(config_dir: Optional[str] = None, root: Optional[Path] = None) -> Path:
    """Return skills directory. If config_dir is relative, resolve against root or project root."""
    base = root or _PROJECT_ROOT
    if config_dir:
        p = Path(config_dir)
        if not p.is_absolute():
            p = base / p
        return p
    return _DEFAULT_SKILLS_DIR


def load_skills(skills_dir: Optional[Path] = None, include_body: bool = True) -> List[Dict[str, Any]]:
    """
    Scan skills_dir for subdirs containing SKILL.md; parse each and return list of skill dicts.
    Each dict has at least: name, description, body (if include_body), path (folder path).
    """
    root = skills_dir if skills_dir is not None else _DEFAULT_SKILLS_DIR
    skills: List[Dict[str, Any]] = []
    if not root.is_dir():
        return skills
    for item in sorted(root.iterdir()):
        if not item.is_dir():
            continue
        skill_file = item / SKILL_FILENAME
        if not skill_file.is_file():
            continue
        try:
            content = skill_file.read_text(encoding="utf-8", errors="replace")
            parsed = _parse_skill_md(content)
            parsed["path"] = str(item)
            parsed["folder"] = item.name  # folder name under skills_dir; use as skill_name in run_skill
            if not include_body:
                parsed.pop("body", None)
            elif parsed.get("body") is not None:
                _append_usage_if_present(item, parsed)
            if parsed.get("name") or parsed.get("description") or parsed.get("body"):
                skills.append(parsed)
                logger.debug("Loaded skill: {} from {}", parsed.get("name") or item.name, item)
        except Exception as e:
            logger.warning("Failed to load skill from {}: {}", skill_file, e)
    return skills


def _normalize_folder_for_disable(folder: str) -> str:
    """Normalize folder name for disabled-list matching (case-insensitive)."""
    return (folder or "").strip().lower()


def _normalize_skill_name_for_match(name: str) -> str:
    """Normalize skill name for matching: lowercase, spaces/underscores to single hyphen, strip."""
    try:
        s = str(name or "").strip().lower()
        s = re.sub(r"[\s_]+", "-", s)
        return s.strip("-") or ""
    except Exception:
        return ""


def resolve_skill_folder_name(skills_base: Path, skill_name: str) -> Optional[str]:
    """
    Resolve a user- or LLM-provided skill name to the actual folder name under skills_base.
    Supports exact match and flexible match so 'html-slides', 'html slides', 'html_slides'
    all resolve to 'html-slides-1.0.0'. Only considers subdirs that contain SKILL.md.
    Returns the actual folder name (e.g. html-slides-1.0.0) or None if not found.
    Never raises: returns None on any error so Core does not crash.
    """
    try:
        if not skill_name or skills_base is None:
            return None
        base = Path(skills_base)
        if not base.is_dir():
            return None
        normalized_input = _normalize_skill_name_for_match(skill_name)
        if not normalized_input:
            return None
        candidates: List[Tuple[str, str]] = []
        for item in sorted(base.iterdir()):
            try:
                if not item.is_dir():
                    continue
                if not (item / SKILL_FILENAME).is_file():
                    continue
                folder_name = item.name
                norm = _normalize_skill_name_for_match(folder_name)
                if norm:
                    candidates.append((norm, folder_name))
            except (OSError, TypeError):
                continue
        for norm, orig in candidates:
            if orig == skill_name or norm == normalized_input:
                return orig
        for norm, orig in candidates:
            if norm.startswith(normalized_input + "-") or norm == normalized_input:
                return orig
        for norm, orig in candidates:
            if normalized_input.startswith(norm + "-") or normalized_input == norm:
                return orig
        return None
    except Exception:
        return None


def load_skills_from_dirs(
    dirs: List[Path],
    disabled_folders: Optional[Iterable[str]] = None,
    include_body: bool = True,
) -> List[Dict[str, Any]]:
    """
    Load skills from multiple directories. First occurrence of each folder name wins.
    Exclude any skill whose folder is in disabled_folders (case-insensitive).
    """
    disabled_set: Set[str] = set()
    if disabled_folders is not None:
        disabled_set = {_normalize_folder_for_disable(f) for f in disabled_folders if (f or "").strip()}
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for d in dirs:
        if not d or not Path(d).is_dir():
            continue
        for s in load_skills(Path(d), include_body=include_body):
            folder = (s.get("folder") or "").strip()
            if not folder:
                continue
            if _normalize_folder_for_disable(folder) in disabled_set:
                continue
            key = _normalize_folder_for_disable(folder)
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
    return out


def load_skill_by_folder_from_dirs(
    dirs: List[Path],
    folder: str,
    include_body: bool = False,
    body_max_chars: int = 0,
) -> Optional[Dict[str, Any]]:
    """Load a single skill by folder name from the first dir that contains it. body_max_chars caps body when include_body True."""
    folder = (folder or "").strip()
    if not folder:
        return None
    for d in dirs:
        if not d or not Path(d).is_dir():
            continue
        skill_dict = load_skill_by_folder(
            Path(d), folder, include_body=include_body, body_max_chars=body_max_chars
        )
        if skill_dict is not None:
            return skill_dict
    return None


def load_skill_by_folder(
    skills_dir: Path,
    folder: str,
    include_body: bool = False,
    body_max_chars: int = 0,
) -> Optional[Dict[str, Any]]:
    """
    Load a single skill by folder name. Returns skill dict or None if folder/SKILL.md missing.
    When include_body is True and body_max_chars > 0, truncate body to that many chars (keeps prompt bounded).
    """
    root = skills_dir if isinstance(skills_dir, Path) else Path(skills_dir)
    item = root / folder
    if not item.is_dir():
        return None
    skill_file = item / SKILL_FILENAME
    if not skill_file.is_file():
        return None
    try:
        content = skill_file.read_text(encoding="utf-8", errors="replace")
        parsed = _parse_skill_md(content)
        parsed["path"] = str(item)
        parsed["folder"] = item.name
        if not include_body:
            parsed.pop("body", None)
        elif parsed.get("body") is not None:
            _append_usage_if_present(item, parsed)
            if body_max_chars > 0 and len(parsed["body"]) > body_max_chars:
                parsed["body"] = (
                    parsed["body"][:body_max_chars].rstrip()
                    + "\n\n*(Body truncated; see SKILL.md in skill folder for full text.)*"
                )
        return parsed
    except Exception as e:
        logger.warning("Failed to load skill from {}: {}", skill_file, e)
        return None


def _skill_keywords_line(skill: Dict[str, Any]) -> str:
    """Build a single 'Keywords: a, b, c' line from skill frontmatter (keywords + trigger.patterns). Never raises."""
    try:
        parts: List[str] = []
        keywords = skill.get("keywords")
        if keywords:
            if isinstance(keywords, (list, tuple)):
                for k in keywords:
                    try:
                        s = str(k).strip()
                        if s and s not in parts:
                            parts.append(s)
                    except Exception:
                        continue
            else:
                try:
                    s = str(keywords).strip()
                    if s:
                        parts.append(s)
                except Exception:
                    pass
        trigger = skill.get("trigger") if isinstance(skill.get("trigger"), dict) else None
        if trigger:
            raw = trigger.get("patterns")
            if raw is None:
                raw = [trigger.get("pattern")] if trigger.get("pattern") else []
            elif isinstance(raw, str):
                raw = [raw] if raw.strip() else []
            elif not isinstance(raw, (list, tuple)):
                raw = []
            for pat in raw:
                if not pat or not isinstance(pat, str):
                    continue
                try:
                    words = re.sub(r"[\\^$.*+?()\[\]{}|]", " ", pat).replace("'", " ").split()
                    for w in words:
                        w = w.strip()
                        if w and len(w) >= 2 and w not in parts:
                            parts.append(w)
                except Exception:
                    continue
        if not parts:
            return ""
        return "Keywords: " + ", ".join(parts[:15])
    except Exception:
        return ""


def build_skills_system_block(skills: List[Dict[str, Any]], include_body: bool = False) -> str:
    """
    Build a system-prompt block listing available skills (name + description, keywords, optionally body).
    Includes folder and short-name hints so the LLM can call run_skill(skill_name=<folder or short name>) accurately.
    """
    if not skills:
        return ""
    lines = [
        "## Available skills",
        "Match the user's request to one skill by name, description, or keywords. Call run_skill(skill_name=<folder or short name>); short names (e.g. html-slides, html slides) work.",
        "",
    ]
    for s in skills:
        try:
            name = str(s.get("name") or "(unnamed)").strip() or "(unnamed)"
            folder = str(s.get("folder") or "").strip()
            desc = str(s.get("description") or "").strip()
            if folder and folder != name:
                line = f"- **{name}** (run_skill skill_name: `{folder}` or `{name}`): {desc}" if desc else f"- **{name}** (run_skill skill_name: `{folder}` or `{name}`)"
            else:
                line = f"- **{name}**: {desc}" if desc else f"- **{name}**"
            lines.append(line)
            kw_line = _skill_keywords_line(s)
            if kw_line:
                lines.append("  " + kw_line)
            if include_body and s.get("body"):
                body = str(s.get("body") or "").replace("\n", "\n  ").strip()
                if body:
                    lines.append("  " + body)
        except Exception:
            continue
        lines.append("")
    lines.append("Skills without a scripts/ folder are instruction-only: call run_skill(skill_name=<folder or short name>) with no script, then follow that skill's instructions.")
    return "\n".join(lines).strip() + "\n\n"


def build_skill_refined_text(skill: Dict[str, Any], body_max_chars: int = 0) -> str:
    """
    Build the text to embed for a skill. Used as the single index vector for RAG.
    Embedded: name, description, keywords, trigger (instruction snippet + pattern terms), optionally body.
    body_max_chars=0 (default): do not include body; body is in the prompt when skill is selected.
    """
    name = (skill.get("name") or "").strip()
    desc = (skill.get("description") or "").strip()
    parts = [name, desc] if name and desc else [name or desc]
    if body_max_chars and skill.get("body"):
        body = (skill["body"] or "").strip()[:body_max_chars]
        if body:
            parts.append(body)
    # Optional frontmatter "keywords" (string or list) for better RAG match across languages
    keywords = skill.get("keywords")
    if keywords:
        kw_str = " ".join(keywords) if isinstance(keywords, (list, tuple)) else str(keywords).strip()
        if kw_str:
            parts.append(kw_str)
    # Trigger: include instruction snippet and pattern terms so RAG matches user phrases (e.g. "how's the weather", "天气")
    trigger = skill.get("trigger") if isinstance(skill.get("trigger"), dict) else None
    if trigger:
        instr = (trigger.get("instruction") or "").strip()[:200]
        if instr:
            parts.append(instr)
        patterns = trigger.get("patterns") or ([trigger.get("pattern")] if trigger.get("pattern") else [])
        for pat in patterns:
            if not pat or not isinstance(pat, str):
                continue
            # Turn regex into searchable words: "weather|forecast|天气" -> "weather forecast 天气"
            words = re.sub(r"[\\^$.*+?()\[\]{}|]", " ", pat).replace("'", " ").split()
            if words:
                parts.append(" ".join(words))
    return "\n".join(parts).strip() or ""


TEST_ID_PREFIX = "test__"


async def sync_skills_to_vector_store(
    skills_dir: Path,
    vector_store: Any,
    embedder: Any,
    refined_body_max_chars: int = 0,
    skills_test_dir: Optional[Path] = None,
    incremental: bool = False,
    skills_extra_dirs: Optional[List[Path]] = None,
    disabled_folders: Optional[Iterable[str]] = None,
) -> int:
    """
    Resync skills to the vector store.
    refined_body_max_chars: 0 = do not store body (recommended; body is in prompt when skill is selected). >0 = store first N chars of body.
    - If skills_test_dir is set: full sync of that dir (all folders embedded and upserted with id = test__<folder>).
    - skills_dir (and skills_extra_dirs): merged with first-wins by folder; disabled_folders excluded. If incremental is True, only process folders not already in the store.
    Returns the total number of skills upserted.
    """
    total = 0
    test_dir = skills_test_dir if skills_test_dir is not None else None
    if test_dir is not None and test_dir.is_dir():
        test_skills = load_skills(test_dir, include_body=True)
        current_test_folders = {s.get("folder") or "" for s in test_skills}
        if test_skills:
            vectors_list: List[List[float]] = []
            ids_list: List[str] = []
            payloads_list: List[Dict[str, Any]] = []
            for s in test_skills:
                folder = s.get("folder") or ""
                if not folder:
                    continue
                refined = build_skill_refined_text(s, body_max_chars=refined_body_max_chars)
                if not refined:
                    continue
                try:
                    emb = await embedder.embed(refined)
                    if not emb:
                        continue
                    vectors_list.append(emb)
                    ids_list.append(TEST_ID_PREFIX + folder)
                    payloads_list.append({"folder": TEST_ID_PREFIX + folder, "name": s.get("name") or "", "description": (s.get("description") or "").strip()})
                except Exception as e:
                    logger.warning("Skill (test) embed failed for %s: %s", folder, e)
            if ids_list:
                try:
                    vector_store.insert(vectors=vectors_list, ids=ids_list, payloads=payloads_list)
                    total += len(ids_list)
                    logger.debug("Synced {} test skill(s) from {}", len(ids_list), test_dir)
                except Exception as e:
                    logger.warning("Skill (test) vector insert failed: %s", e)
        # Delete test__ ids that are no longer in the test folder (e.g. skill moved to production or removed)
        list_ids_fn = getattr(vector_store, "list_ids", None)
        if list_ids_fn:
            try:
                all_ids = list_ids_fn(limit=10000)
                for vid in all_ids:
                    if vid.startswith(TEST_ID_PREFIX):
                        folder = vid[len(TEST_ID_PREFIX):]
                        if folder not in current_test_folders:
                            try:
                                vector_store.delete(vid)
                                logger.debug("Removed stale test skill id from store: {}", vid)
                            except Exception as e:
                                logger.warning("Failed to delete stale test id {}: {}", vid, e)
            except Exception as e:
                logger.warning("Failed to list ids for test cleanup: {}", e)

    main_dirs: List[Path] = [Path(skills_dir)]
    if skills_extra_dirs:
        main_dirs.extend(Path(p) for p in skills_extra_dirs)
    skills = load_skills_from_dirs(main_dirs, disabled_folders=disabled_folders, include_body=True)
    if not skills:
        return total
    vectors_list = []
    ids_list = []
    payloads_list = []
    for s in skills:
        folder = s.get("folder") or ""
        if not folder:
            continue
        if incremental:
            try:
                existing = vector_store.get(folder)
                if existing is not None:
                    continue
            except Exception:
                pass
        refined = build_skill_refined_text(s, body_max_chars=refined_body_max_chars)
        if not refined:
            continue
        try:
            emb = await embedder.embed(refined)
            if not emb:
                continue
            vectors_list.append(emb)
            ids_list.append(folder)
            payloads_list.append({"folder": folder, "name": s.get("name") or "", "description": (s.get("description") or "").strip()})
        except Exception as e:
            logger.warning("Skill embed failed for {}: {}", folder, e)
    if not ids_list:
        return total
    try:
        vector_store.insert(vectors=vectors_list, ids=ids_list, payloads=payloads_list)
        return total + len(ids_list)
    except Exception as e:
        logger.warning("Skill vector insert failed: {}", e)
        return total


async def search_skills_by_query(
    vector_store: Any,
    embedder: Any,
    query: str,
    limit: int = 10,
    min_similarity: float = 0.0,
) -> List[Tuple[str, float]]:
    """
    Search the skills vector store by query. Returns list of (folder, similarity).
    similarity = 1 - distance (for cosine distance). Results below min_similarity are dropped.
    """
    if not query or not query.strip():
        return []
    if not vector_store:
        logger.debug("Skill vector search skipped: no vector store")
        return []
    try:
        emb = await embedder.embed(query.strip())
        if not emb:
            return []
    except Exception as e:
        logger.warning("Skill search embed failed: {}", e)
        return []
    try:
        results = vector_store.search(query=[emb], limit=limit, filters=None)
    except Exception as e:
        logger.warning("Skill vector search failed: {} ({})", e, type(e).__name__)
        return []
    out: List[Tuple[str, float]] = []
    for r in results:
        vid = getattr(r, "id", None)
        if not vid and hasattr(r, "payload") and isinstance(r.payload, dict):
            vid = r.payload.get("folder")
        if not vid:
            continue
        dist = getattr(r, "score", None)
        if dist is None:
            continue
        sim = 1.0 - float(dist)
        if sim >= min_similarity:
            out.append((str(vid), sim))
    return out
