"""
Plugin parameter resolution: LLM args -> profile -> config.
See docs/PluginParameterCollection.md.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)


def _normalize_key(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_")


def _get_plugin_config(plugin: Any) -> Dict[str, Any]:
    """
    Get plugin config (default_parameters, use_defaults_directly, use_default_directly_for).
    For inline: plugin.config. For external: descriptor.config or load from _folder/config.yml.
    """
    config = {}
    if hasattr(plugin, "config") and plugin.config:
        config = dict(plugin.config)
    elif isinstance(plugin, dict):
        config = dict(plugin.get("config") or {})
        folder = plugin.get("_folder")
        if folder:
            config_path = Path(folder) / "config.yml"
            if config_path.is_file():
                try:
                    import yaml
                    with open(config_path, "r", encoding="utf-8") as f:
                        folder_config = yaml.safe_load(f) or {}
                    for k in ("default_parameters", "use_defaults_directly", "use_default_directly_for"):
                        if folder_config.get(k) is not None:
                            config[k] = folder_config[k]
                except Exception as e:
                    logger.debug("Failed to load plugin config from {}: {}", config_path, e)
    return config


def _get_capability_params_schema(capability: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract parameters schema from capability. Handles both dict and list of dicts."""
    if not capability:
        return []
    params = capability.get("parameters")
    if isinstance(params, list):
        return params
    return []


def resolve_and_validate_plugin_params(
    llm_params: Dict[str, Any],
    capability: Optional[Dict[str, Any]],
    profile: Dict[str, Any],
    plugin_config: Dict[str, Any],
    plugin_id: str,
    capability_id: Optional[str],
) -> Tuple[Dict[str, Any], Optional[str], Optional[Dict[str, Any]]]:
    """
    Resolve parameters: LLM args -> profile (by profile_key) -> config (default_parameters).
    Validate: required params present; confirm_if_uncertain when source is profile/config
    (unless use_defaults_directly or use_default_directly_for).
    Returns (resolved_params, error_message, ask_user_data).
    If error_message is not None, do not invoke plugin.
    ask_user_data is set when the caller should ask the user and retry: {"missing": [param_names]} or {"uncertain": [...]}.
    """
    schema = _get_capability_params_schema(capability)
    if not schema:
        # No capability params schema - use LLM params as-is
        return dict(llm_params), None, None

    default_params = plugin_config.get("default_parameters") or {}
    use_defaults_directly = plugin_config.get("use_defaults_directly") is True
    use_directly_for = plugin_config.get("use_default_directly_for") or []
    if not isinstance(use_directly_for, list):
        use_directly_for = list(use_directly_for) if use_directly_for else []
    use_directly_for = [_normalize_key(p) for p in use_directly_for]

    resolved: Dict[str, Any] = {}
    sources: Dict[str, str] = {}  # param_name -> "user_message" | "profile" | "config"
    missing: List[str] = []
    uncertain: List[Tuple[str, str, str]] = []  # (param_name, value, source)

    for p in schema:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        key = _normalize_key(name)
        required = p.get("required", True)
        profile_key = (p.get("profile_key") or "").strip() or key
        config_key = (p.get("config_key") or "").strip() or key
        confirm_if_uncertain = p.get("confirm_if_uncertain") is True

        value = None
        source = "user_message"

        # 1. Explicit from LLM
        if key in llm_params and llm_params[key] not in (None, ""):
            val = llm_params[key]
            if isinstance(val, str) and val.strip():
                value = val.strip() if isinstance(val, str) else val
                source = "user_message"
            elif not isinstance(val, str) and val is not None:
                value = val
                source = "user_message"

        # 2. Profile
        if value is None and profile:
            pv = profile.get(profile_key)
            if pv not in (None, "") and (not isinstance(pv, str) or pv.strip()):
                value = pv.strip() if isinstance(pv, str) else pv
                source = "profile"

        # 3. Config: default_parameters first, then top-level config (for plugins like Weather)
        if value is None:
            cv = default_params.get(config_key) or default_params.get(name)
            if cv is None:
                cv = plugin_config.get(config_key) or plugin_config.get(name)
            if cv not in (None, "") and (not isinstance(cv, str) or cv.strip()):
                value = cv.strip() if isinstance(cv, str) else cv
                source = "config"

        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                missing.append(name)
            continue

        resolved[key] = value
        sources[key] = source

        if confirm_if_uncertain and source in ("profile", "config"):
            use_directly = use_defaults_directly or (key in use_directly_for or name in use_directly_for)
            if not use_directly:
                uncertain.append((name, str(value)[:100], source))

    cap_id = capability_id or (capability.get("id") if capability else None) or "run"

    if missing:
        have = []
        for k, v in resolved.items():
            src = sources.get(k, "?")
            have.append(f"  - {k}: {str(v)[:80]} (from {src})")
        have_str = "\n".join(have) if have else "  (none)"
        err = (
            f'Plugin "{plugin_id}" (capability: {cap_id}) requires parameters that are missing:\n'
            f"  Missing: {', '.join(missing)}\n\n"
            f"Parameters we have:\n{have_str}\n\n"
            "Please ask the user for the missing values."
        )
        return resolved, err, {"missing": missing}

    if uncertain:
        unc_lines = []
        for name, val, src in uncertain:
            unc_lines.append(f"  - {name}: {val} (from {src}) — please confirm with the user")
        have_ok = []
        for k, v in resolved.items():
            if sources.get(k) == "user_message":
                have_ok.append(f"  - {k}: {str(v)[:80]} (from user message)")
        have_ok_str = "\n".join(have_ok) if have_ok else "  (none)"
        err = (
            f'Plugin "{plugin_id}" (capability: {cap_id}) has parameters that need confirmation before use:\n'
            f"{chr(10).join(unc_lines)}\n\n"
            f"Parameters we have (no confirmation needed):\n{have_ok_str}\n\n"
            "Please ask the user to confirm the values above before proceeding."
        )
        return resolved, err, {"uncertain": uncertain}

    return resolved, None, None
