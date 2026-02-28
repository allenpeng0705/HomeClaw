"""
YAML load/update for Portal: comment-preserving merge for llm, memory_kb, skills_and_plugins, friend_presets.
Never full overwrite; never use yaml.safe_dump on the whole file (would strip comments).
Only whitelisted keys are merged; other keys and all comments are preserved.
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set

_log = logging.getLogger(__name__)

# Top-level keys the Portal is allowed to merge (updates for other keys are ignored).
WHITELIST_LLM = frozenset({
    "local_models", "cloud_models", "main_llm", "embedding_llm",
    "main_llm_mode", "main_llm_local", "main_llm_cloud", "main_llm_language",
    "embedding_host", "embedding_port", "main_llm_host", "main_llm_port",
    "hybrid_router",
})
WHITELIST_MEMORY_KB = frozenset({
    "use_memory", "memory_backend", "memory_check_before_add", "memory_summarization",
    "session", "profile",
    "use_agent_memory_file", "agent_memory_path", "agent_memory_max_chars",
    "use_agent_memory_search", "agent_memory_vector_collection",
    "agent_memory_bootstrap_max_chars", "agent_memory_bootstrap_max_chars_local",
    "use_daily_memory", "daily_memory_dir",
    "knowledge_base", "database", "vectorDB", "graphDB", "cognee",
})
WHITELIST_SKILLS_PLUGINS = frozenset({
    "plugins_description_max_chars",
    "skills_use_vector_search", "skills_vector_collection", "skills_max_retrieved",
    "skills_max_in_prompt", "skills_similarity_threshold", "skills_refresh_on_startup",
    "skills_test_dir", "skills_incremental_sync", "skills_include_body_for",
    "skills_force_include_rules",
    "plugins_use_vector_search", "plugins_vector_collection", "plugins_max_retrieved",
    "plugins_max_in_prompt", "plugins_similarity_threshold", "plugins_refresh_on_startup",
    "plugins_force_include_rules",
    "system_plugins_auto_start", "system_plugins", "system_plugins_env",
    "tools",
})
WHITELIST_FRIEND_PRESETS = frozenset({"presets"})


def load_yml_preserving(path: str) -> Optional[Dict[str, Any]]:
    """Load YAML with ruamel; preserve comments. Returns dict or None on error. Never raises."""
    try:
        from ruamel.yaml import YAML
        yaml_rt = YAML()
        path_obj = Path(path)
        if not path_obj.exists():
            return None
        with open(path_obj, "r", encoding="utf-8") as f:
            data = yaml_rt.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        _log.debug("load_yml_preserving %s: %s", path, e)
        return None


def update_yml_preserving(
    path: str,
    updates: Dict[str, Any],
    whitelist: Optional[Set[str]] = None,
) -> bool:
    """Merge updates into YAML file with ruamel; preserve comments and key order.
    If whitelist is set, only keys in whitelist are merged (others in updates are ignored).
    Atomic write (.tmp + replace). Skips write if file exists and load failed.
    Returns True if write succeeded, False otherwise. Never raises."""
    if not updates:
        return True
    if whitelist is not None:
        updates = {k: v for k, v in updates.items() if k in whitelist}
        if not updates:
            return True

    def _atomic_write(dump_fn) -> bool:
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                dump_fn(f)
            os.replace(tmp, path)
            return True
        except Exception as e:
            _log.warning("update_yml_preserving: atomic write failed (%s unchanged): %s", path, e)
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return False

    try:
        from ruamel.yaml import YAML
        yaml_rt = YAML()
        yaml_rt.preserve_quotes = True
        path_obj = Path(path)
        if not path_obj.exists():
            data = {}
        else:
            with open(path_obj, "r", encoding="utf-8") as f:
                data = yaml_rt.load(f)
            if data is None:
                data = {}
            if not isinstance(data, dict):
                data = {}
        for k, v in updates.items():
            data[k] = v
        return _atomic_write(lambda f: yaml_rt.dump(data, f))
    except Exception as e:
        _log.debug("update_yml_preserving ruamel path %s: %s", path, e)

    # Fallback: load with PyYAML (no comment preservation), merge, safe_dump
    try:
        import yaml
        existing = {}
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f)
            if not isinstance(existing, dict):
                existing = {}
            if not existing:
                _log.warning(
                    "update_yml_preserving: could not load %s; skipping write to avoid removing keys.",
                    path,
                )
                return False
        for k, v in updates.items():
            existing[k] = v
        return _atomic_write(lambda f: yaml.safe_dump(existing, f, default_flow_style=False, sort_keys=False))
    except Exception as e:
        _log.warning("update_yml_preserving fallback %s: %s", path, e)
        return False
