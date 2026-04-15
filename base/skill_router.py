from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from base.skills import (
    TEST_ID_PREFIX,
    get_all_skills_dirs,
    get_skills_dir,
    load_skill_by_folder,
    load_skill_by_folder_from_dirs,
    load_skills_from_dirs,
    search_skills_by_query,
    skills_with_lexical_overlap,
    skills_with_matching_trigger_patterns,
)
from base.router_reranker import rerank_with_local_model, apply_rerank_scores


def _skill_folder_key(s: Dict[str, Any]) -> str:
    return str((s.get("folder") or s.get("name") or "")).strip()


def skills_router_semantic_enabled(meta: Any) -> bool:
    cfg = getattr(meta, "skills_router_config", None) or {}
    if not isinstance(cfg, dict) or not cfg.get("enabled"):
        return False
    mode = str(cfg.get("mode") or "legacy").strip().lower()
    sem = cfg.get("semantic") if isinstance(cfg.get("semantic"), dict) else {}
    return mode in ("semantic", "hybrid") and bool(sem.get("enabled", True))


def skills_router_semantic_config(meta: Any) -> Dict[str, Any]:
    cfg = getattr(meta, "skills_router_config", None) or {}
    sem = cfg.get("semantic") if isinstance(cfg.get("semantic"), dict) else {}
    return sem if isinstance(sem, dict) else {}


def skills_semantic_embed_body_max_chars(meta: Any) -> int:
    """Cap of SKILL.md body chars included in vector embedding text (0 = omit body). SkillRouter-style full-text signal."""
    sem = skills_router_semantic_config(meta)
    try:
        v = int(sem.get("embed_body_max_chars", 0) or 0)
    except (TypeError, ValueError):
        v = 0
    return max(0, min(50000, v))


def skills_semantic_rerank_body_max_chars(meta: Any, rr_cfg: Dict[str, Any]) -> int:
    """Optional body chars appended to rerank candidate text (cross-encoder); 0 = name/desc/keywords only."""
    sem = skills_router_semantic_config(meta)
    try:
        v = sem.get("rerank_include_body_max_chars")
        if v is None or str(v).strip() == "":
            v = rr_cfg.get("include_body_max_chars", 0)
        v = int(v or 0)
    except (TypeError, ValueError):
        v = 0
    return max(0, min(32000, v))


async def load_skills_for_query(
    *,
    meta: Any,
    core: Any,
    query: str,
    root: Path,
    uid: str = "",
) -> Tuple[List[Dict[str, Any]], List[Path], bool, str, Optional[List[Dict[str, Any]]]]:
    """
    Return initial skills list for this turn.

    Output: (skills_list, skills_dirs, used_semantic_router, source_message, full_catalog_cache)

    full_catalog_cache: when non-None, the same list returned from a single load_skills_from_dirs
    call (metadata only). The caller can reuse it for per-skill trigger scans to avoid loading
    every SKILL.md twice in one turn. None when semantic path did not load a full catalog.
    """
    skills_dirs = get_all_skills_dirs(
        getattr(meta, "skills_dir", None) or "skills",
        (getattr(meta, "external_skills_dir", None) or "").strip(),
        getattr(meta, "skills_extra_dirs", None) or [],
        root,
    )
    disabled_folders = getattr(meta, "skills_disabled", None) or []
    use_semantic = skills_router_semantic_enabled(meta)
    sem_cfg = skills_router_semantic_config(meta)
    skills_list: List[Dict[str, Any]] = []

    if not use_semantic:
        skills_list = load_skills_from_dirs(skills_dirs, disabled_folders=disabled_folders, include_body=False)
        return (
            skills_list,
            skills_dirs,
            False,
            f"included all {len(skills_list)} skill(s) (skills_router semantic/hybrid disabled)",
            skills_list,
        )

    if getattr(core, "skills_vector_store", None) and getattr(core, "embedder", None):
        max_retrieved = max(1, min(100, int(sem_cfg.get("top_k", getattr(meta, "skills_max_retrieved", 10)) or 10)))
        threshold = float(sem_cfg.get("threshold", getattr(meta, "skills_similarity_threshold", 0.0)) or 0.0)
        hits = await search_skills_by_query(
            core.skills_vector_store, core.embedder, query or "",
            limit=max_retrieved, min_similarity=threshold,
        )
        max_hit_sim = 0.0
        for _it in hits or []:
            try:
                if isinstance(_it, (list, tuple)) and len(_it) >= 2:
                    max_hit_sim = max(max_hit_sim, float(_it[1]))
            except (TypeError, ValueError):
                continue
        if getattr(meta, "skills_usage_rerank_enabled", False) and hits:
            try:
                from base.skill_usage import rerank_skill_vector_hits

                w = float(getattr(meta, "skills_usage_rerank_weight", 0.12) or 0.12)
                hits = rerank_skill_vector_hits(hits, uid, weight=max(0.0, w), enabled=True)
            except Exception as e:
                logger.debug("skills usage rerank skipped: {}", e)
        skills_test_dir_str = (getattr(meta, "skills_test_dir", None) or "").strip()
        skills_test_path = get_skills_dir(skills_test_dir_str, root=root) if skills_test_dir_str else None
        for item in (hits or []):
            try:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                hit_id, _ = item[0], item[1]
            except (TypeError, IndexError, ValueError):
                continue
            if hit_id.startswith(TEST_ID_PREFIX):
                load_path = skills_test_path if skills_test_path and skills_test_path.is_dir() else None
                folder_name = hit_id[len(TEST_ID_PREFIX):]
                skill_dict = load_skill_by_folder(load_path, folder_name, include_body=False) if load_path else None
            else:
                folder_name = hit_id
                skill_dict = load_skill_by_folder_from_dirs(skills_dirs, folder_name, include_body=False)
            if skill_dict is None:
                try:
                    core.skills_vector_store.delete(hit_id)
                except Exception:
                    pass
                continue
            skills_list.append(skill_dict)

        try:
            _floor = float(sem_cfg.get("confidence_floor", 0.0) or 0.0)
        except (TypeError, ValueError):
            _floor = 0.0
        if _floor > 0.0 and hits and skills_list and max_hit_sim < _floor:
            skills_list = load_skills_from_dirs(skills_dirs, disabled_folders=disabled_folders, include_body=False)
            logger.debug(
                "skills_router: best hit similarity {:.3f} < confidence_floor {:.3f}; using full skill catalog",
                max_hit_sim,
                _floor,
            )
            return (
                skills_list,
                skills_dirs,
                False,
                f"semantic confidence_floor fallback: all {len(skills_list)} skill(s)",
                skills_list,
            )

        _all_skills_union: Optional[List[Dict[str, Any]]] = None
        _qstrip = (query or "").strip()
        _need_union_catalog = _qstrip and (
            bool(sem_cfg.get("union_trigger_matched_skills", True))
            or bool(sem_cfg.get("union_lexical_skills", False))
        )
        if _need_union_catalog:
            try:
                _all_skills_union = load_skills_from_dirs(
                    skills_dirs, disabled_folders=disabled_folders, include_body=False
                )
            except Exception as e:
                logger.debug("skills_router union catalog load skipped: {}", e)

        if bool(sem_cfg.get("union_trigger_matched_skills", True)) and _qstrip and _all_skills_union:
            try:
                _extra = skills_with_matching_trigger_patterns(_all_skills_union, query or "")
                if skills_list:
                    _seen = {
                        str((s.get("folder") or s.get("name") or "")).strip().lower()
                        for s in skills_list
                        if isinstance(s, dict)
                    }
                    for _s in _extra:
                        if not isinstance(_s, dict):
                            continue
                        _fn = str((_s.get("folder") or _s.get("name") or "")).strip().lower()
                        if not _fn or _fn in _seen:
                            continue
                        _seen.add(_fn)
                        skills_list.append(_s)
                elif _extra:
                    skills_list = list(_extra)
            except Exception as e:
                logger.debug("skills_router union_trigger_matched_skills skipped: {}", e)

        if bool(sem_cfg.get("union_lexical_skills", False)) and _qstrip and _all_skills_union:
            try:
                try:
                    _lex_max = max(1, min(30, int(sem_cfg.get("union_lexical_max_skills", 12) or 12)))
                except (TypeError, ValueError):
                    _lex_max = 12
                try:
                    _lex_mtl = max(2, min(12, int(sem_cfg.get("union_lexical_min_token_len", 3) or 3)))
                except (TypeError, ValueError):
                    _lex_mtl = 3
                _lex_extra = skills_with_lexical_overlap(
                    _all_skills_union,
                    query or "",
                    min_token_len=_lex_mtl,
                    max_skills=_lex_max,
                )
                if skills_list:
                    _seen = {
                        str((s.get("folder") or s.get("name") or "")).strip().lower()
                        for s in skills_list
                        if isinstance(s, dict)
                    }
                    for _s in _lex_extra:
                        if not isinstance(_s, dict):
                            continue
                        _fn = str((_s.get("folder") or _s.get("name") or "")).strip().lower()
                        if not _fn or _fn in _seen:
                            continue
                        _seen.add(_fn)
                        skills_list.append(_s)
                elif _lex_extra:
                    skills_list = list(_lex_extra)
            except Exception as e:
                logger.debug("skills_router union_lexical_skills skipped: {}", e)

        # Optional model rerank: score the merged pool (vector hits + unions), not only vector hits.
        rr_cfg = sem_cfg.get("reranker") if isinstance(sem_cfg.get("reranker"), dict) else {}
        if rr_cfg.get("enabled") and skills_list:
            try:
                by_folder = {_skill_folder_key(s): s for s in skills_list if isinstance(s, dict) and _skill_folder_key(s)}
                hit_sim_by_folder: Dict[str, float] = {}
                for item in hits or []:
                    try:
                        if not isinstance(item, (list, tuple)) or len(item) < 2:
                            continue
                        hit_id, hsc = item[0], item[1]
                        folder = str(
                            hit_id[len(TEST_ID_PREFIX) :]
                            if str(hit_id).startswith(TEST_ID_PREFIX)
                            else hit_id
                        ).strip()
                        if not folder:
                            continue
                        hit_sim_by_folder[folder] = max(
                            hit_sim_by_folder.get(folder, 0.0), float(hsc)
                        )
                    except (TypeError, ValueError, IndexError):
                        continue

                _rmc = sem_cfg.get("rerank_max_candidates")
                try:
                    if _rmc is not None and str(_rmc).strip() != "":
                        rr_cap = max(1, min(100, int(_rmc)))
                    else:
                        rr_cap = max(
                            1,
                            min(
                                100,
                                int(sem_cfg.get("rerank_top_n", 40) or 40),
                            ),
                        )
                except (TypeError, ValueError):
                    rr_cap = 40

                union_first = [
                    s
                    for s in skills_list
                    if isinstance(s, dict) and _skill_folder_key(s) not in hit_sim_by_folder
                ]
                hit_skills = [
                    s
                    for s in skills_list
                    if isinstance(s, dict) and _skill_folder_key(s) in hit_sim_by_folder
                ]
                hit_skills.sort(
                    key=lambda s: hit_sim_by_folder.get(_skill_folder_key(s), 0.0), reverse=True
                )
                ordered: List[Dict[str, Any]] = []
                _ord_seen: Set[str] = set()
                for s in union_first + hit_skills:
                    fk = _skill_folder_key(s)
                    if not fk or fk in _ord_seen:
                        continue
                    _ord_seen.add(fk)
                    ordered.append(s)
                ordered = ordered[:rr_cap]

                _rr_body_cap = skills_semantic_rerank_body_max_chars(meta, rr_cfg)
                pre_hits: List[Tuple[str, float]] = []
                candidates: List[Dict[str, str]] = []
                for sk in ordered:
                    folder = _skill_folder_key(sk)
                    hsc = hit_sim_by_folder.get(folder, 0.0)
                    k = sk.get("keywords")
                    ktxt = (
                        ", ".join([str(x).strip() for x in k if str(x).strip()])
                        if isinstance(k, list)
                        else str(k or "").strip()
                    )
                    lines = [
                        str(sk.get("name") or folder),
                        str(sk.get("description") or ""),
                        f"keywords: {ktxt}" if ktxt else "",
                    ]
                    if _rr_body_cap > 0 and folder:
                        try:
                            _loaded = load_skill_by_folder_from_dirs(
                                skills_dirs,
                                folder,
                                include_body=True,
                                body_max_chars=_rr_body_cap,
                            )
                            if isinstance(_loaded, dict):
                                _b = str(_loaded.get("body") or "").strip()
                                if _b:
                                    lines.append(f"body: {_b}")
                        except Exception:
                            pass
                    txt = "\n".join(x for x in lines if x).strip()
                    pre_hits.append((folder, float(hsc)))
                    candidates.append({"id": folder, "text": txt})
                rr_scores = await rerank_with_local_model(
                    query=query or "",
                    candidates=candidates,
                    reranker_cfg={**rr_cfg, "log_tag": "skills_router"},
                )
                reranked = apply_rerank_scores(pre_hits, rr_scores)
                order = [x[0] for x in reranked]
                keep = [by_folder[f] for f in order if f in by_folder]
                seen = {_skill_folder_key(s) for s in keep}
                keep.extend(
                    [
                        s
                        for s in skills_list
                        if isinstance(s, dict) and _skill_folder_key(s) not in seen
                    ]
                )
                skills_list = keep
                try:
                    _rfb = float(sem_cfg.get("rerank_fallback_min_combined_score", 0.0) or 0.0)
                except (TypeError, ValueError):
                    _rfb = 0.0
                if _rfb > 0.0 and reranked and len(reranked) >= 1:
                    try:
                        _best = float(reranked[0][1])
                    except (TypeError, ValueError):
                        _best = 0.0
                    if _best < _rfb:
                        skills_list = load_skills_from_dirs(
                            skills_dirs, disabled_folders=disabled_folders, include_body=False
                        )
                        logger.debug(
                            "skills_router: best combined score {:.3f} < rerank_fallback_min_combined_score {:.3f}; "
                            "using full skill catalog",
                            _best,
                            _rfb,
                        )
                        return (
                            skills_list,
                            skills_dirs,
                            False,
                            f"semantic rerank fallback: all {len(skills_list)} skill(s)",
                            skills_list,
                        )
            except Exception as e:
                logger.debug("skills model rerank skipped: {}", e)
        if skills_list:
            skills_max = max(0, int(sem_cfg.get("final_top_n", getattr(meta, "skills_max_in_prompt", 5)) or 5))
            if skills_max > 0 and len(skills_list) > skills_max:
                skills_list = skills_list[:skills_max]
            return (
                skills_list,
                skills_dirs,
                True,
                f"retrieved {len(skills_list)} skill(s) by semantic skills_router",
                _all_skills_union,
            )

    skills_list = load_skills_from_dirs(skills_dirs, disabled_folders=disabled_folders, include_body=False)
    return (
        skills_list,
        skills_dirs,
        use_semantic,
        f"loaded {len(skills_list)} skill(s) from disk (semantic router had no hits)",
        skills_list,
    )

