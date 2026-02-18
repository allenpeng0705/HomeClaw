"""
Central prompt manager: load prompts from config/prompts with language and model overrides.

Layout: <prompts_dir>/<section>/<name>.<lang>.yml or <name>.<model>.<lang>.yml or <name>.yml
YAML: { content: "..." } for single string, or { messages: [ { role, content } ] } for chat format.
Placeholders in content use {placeholder}; pass kwargs to get_prompt() for formatting.

See docs/PromptManagement.md for design.
"""

import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from loguru import logger

# Project root: parent of base/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PROMPTS_DIR = _PROJECT_ROOT / "config" / "prompts"

# Cache: (section, name, lang, model) -> (payload, mtime). Optional TTL.
_cache: Dict[Tuple[str, str, str, str], Tuple[Any, float]] = {}
_cache_lock = threading.Lock()
_cache_ttl_seconds: float = 0  # 0 = no TTL, use mtime invalidation only


def _normalize_lang(lang: Optional[str]) -> str:
    if not lang or not str(lang).strip():
        return "en"
    return str(lang).strip().lower()[:10]


def _normalize_model(model: Optional[str]) -> str:
    if not model or not str(model).strip():
        return ""
    return re.sub(r"[^\w\-.]", "_", str(model).strip().lower())[:64]


def _resolve_path(
    base_dir: Path,
    section: str,
    name: str,
    lang: str,
    model: str,
) -> Optional[Path]:
    """Return first existing path in resolution order: model+lang, lang, default."""
    safe_section = re.sub(r"[^\w\-]", "_", section)
    safe_name = re.sub(r"[^\w\-]", "_", name)
    section_dir = base_dir / safe_section
    if not section_dir.is_dir():
        return None
    candidates: List[Path] = []
    if model:
        candidates.append(section_dir / f"{safe_name}.{model}.{lang}.yml")
        candidates.append(section_dir / f"{safe_name}.{model}.{lang}.yaml")
    candidates.append(section_dir / f"{safe_name}.{lang}.yml")
    candidates.append(section_dir / f"{safe_name}.{lang}.yaml")
    candidates.append(section_dir / f"{safe_name}.yml")
    candidates.append(section_dir / f"{safe_name}.yaml")
    for p in candidates:
        if p.is_file():
            return p
    return None


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("PromptManager: failed to load {}: {}", path, e)
        return None


def _format_string(template: str, kwargs: Dict[str, Any]) -> str:
    """Format template with kwargs; leave {{ and }} as literal { and }."""
    if not kwargs:
        return template
    # Replace {{ with \x00, }} with \x01, then format, then restore
    s = template.replace("{{", "\x00").replace("}}", "\x01")
    try:
        s = s.format(**kwargs)
    except KeyError as e:
        logger.debug("PromptManager: placeholder {} not provided, leaving as-is", e)
        for k, v in kwargs.items():
            s = s.replace("{" + k + "}", str(v))
    return s.replace("\x00", "{").replace("\x01", "}")


def get_prompts_dir(config_dir: Optional[str] = None, root: Optional[Path] = None) -> Path:
    """Return prompts directory. If config_dir is relative, resolve against root or project root."""
    base = root or _PROJECT_ROOT
    if config_dir:
        p = Path(config_dir)
        if not p.is_absolute():
            p = base / p
        return p
    return _DEFAULT_PROMPTS_DIR


class PromptManager:
    """
    Load and resolve prompts by (section, name, language, model) with fallback chain.
    Optional in-memory cache and TTL.
    """

    def __init__(
        self,
        prompts_dir: Optional[Union[str, Path]] = None,
        default_language: str = "en",
        cache_ttl_seconds: float = 0,
        root: Optional[Path] = None,
    ):
        self._root = root or _PROJECT_ROOT
        self._prompts_dir = get_prompts_dir(str(prompts_dir) if prompts_dir else None, self._root)
        if isinstance(prompts_dir, Path):
            self._prompts_dir = prompts_dir
        self._default_lang = _normalize_lang(default_language or "en")
        self._cache_ttl = max(0.0, float(cache_ttl_seconds))

    def resolve_language(self, lang: Optional[str] = None) -> str:
        """Return normalized language (from argument or default)."""
        return _normalize_lang(lang) if lang else self._default_lang

    def get_path(
        self,
        section: str,
        name: str,
        lang: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Optional[Path]:
        """Return first existing file path for (section, name, lang, model) or None."""
        l = self.resolve_language(lang)
        m = _normalize_model(model)
        return _resolve_path(self._prompts_dir, section, name, l, m)

    def get_raw(
        self,
        section: str,
        name: str,
        lang: Optional[str] = None,
        model: Optional[str] = None,
        use_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Load raw YAML payload for (section, name, lang, model) without formatting.
        Returns dict with 'content' (str) or 'messages' (list of {role, content}).
        """
        l = self.resolve_language(lang)
        m = _normalize_model(model)
        cache_key = (section, name, l, m)
        if use_cache and self._cache_ttl >= 0:
            with _cache_lock:
                if cache_key in _cache:
                    payload, mtime = _cache[cache_key]
                    if self._cache_ttl == 0 or (time.time() - mtime) < self._cache_ttl:
                        return payload
        path = self.get_path(section, name, lang, model)
        if not path:
            return None
        payload = _load_yaml(path)
        if payload and use_cache:
            with _cache_lock:
                _cache[cache_key] = (payload, time.time())
        return payload

    def get_content(
        self,
        section: str,
        name: str,
        lang: Optional[str] = None,
        model: Optional[str] = None,
        use_cache: bool = True,
        validate_placeholders: bool = False,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        Return single prompt string for (section, name). Formats with kwargs.
        YAML must have 'content' key. Returns None if not found or has 'messages' only.
        If validate_placeholders is True and YAML has 'required_placeholders' list, logs warning for missing kwargs.
        """
        raw = self.get_raw(section, name, lang, model, use_cache=use_cache)
        if not raw:
            return None
        content = raw.get("content")
        if content is None:
            return None
        if validate_placeholders:
            required = raw.get("required_placeholders")
            if isinstance(required, list):
                for k in required:
                    if k not in kwargs:
                        logger.debug("PromptManager: missing placeholder {} for {}/{}", k, section, name)
        return _format_string(str(content), kwargs)

    def get_messages(
        self,
        section: str,
        name: str,
        lang: Optional[str] = None,
        model: Optional[str] = None,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> Optional[List[Dict[str, str]]]:
        """
        Return list of {role, content} for (section, name). Formats each content with kwargs.
        YAML must have 'messages' key. Returns None if not found or has 'content' only.
        """
        raw = self.get_raw(section, name, lang, model, use_cache=use_cache)
        if not raw:
            return None
        messages = raw.get("messages")
        if not isinstance(messages, list):
            return None
        out: List[Dict[str, str]] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role") or "user"
            content = m.get("content")
            if content is not None:
                content = _format_string(str(content), kwargs)
            out.append({"role": str(role), "content": content or ""})
        return out if out else None

    def get_prompt(
        self,
        section: str,
        name: str,
        lang: Optional[str] = None,
        model: Optional[str] = None,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> Union[Optional[str], Optional[List[Dict[str, str]]]]:
        """
        Return prompt as string (if YAML has 'content') or list of messages (if 'messages').
        Returns None if not found.
        """
        raw = self.get_raw(section, name, lang, model, use_cache=use_cache)
        if not raw:
            return None
        if "content" in raw:
            return self.get_content(section, name, lang, model, use_cache=use_cache, **kwargs)
        if "messages" in raw:
            return self.get_messages(section, name, lang, model, use_cache=use_cache, **kwargs)
        return None

    def list_prompts(self, section: Optional[str] = None) -> List[Tuple[str, str, List[str]]]:
        """
        List available prompts as (section, name, [langs]).
        If section is None, scan all sections.
        """
        results: List[Tuple[str, str, List[str]]] = []
        base = Path(self._prompts_dir)
        if not base.is_dir():
            return results
        sections = [section] if section else [d.name for d in base.iterdir() if d.is_dir()]
        for sec in sections:
            sec_path = base / sec
            if not sec_path.is_dir():
                continue
            seen: Dict[str, List[str]] = {}
            for f in sec_path.iterdir():
                if not f.suffix.lower() in (".yml", ".yaml") or not f.is_file():
                    continue
                stem = f.stem
                # stem can be name, name.lang, or name.model.lang
                parts = stem.split(".")
                if len(parts) == 1:
                    name = parts[0]
                    lang = "default"
                elif len(parts) == 2:
                    name, lang = parts[0], parts[1]
                else:
                    name = parts[0]
                    lang = parts[-1]
                if name not in seen:
                    seen[name] = []
                if lang not in seen[name]:
                    seen[name].append(lang)
            for name, langs in seen.items():
                results.append((sec, name, sorted(langs)))
        return results

    def clear_cache(self) -> None:
        """Clear in-memory cache."""
        with _cache_lock:
            _cache.clear()


def get_prompt_manager(
    prompts_dir: Optional[str] = None,
    default_language: Optional[str] = None,
    cache_ttl_seconds: float = 0,
) -> PromptManager:
    """Factory: build PromptManager from optional config (e.g. from CoreMetadata)."""
    root = _PROJECT_ROOT
    dir_path = get_prompts_dir(prompts_dir, root) if prompts_dir else _DEFAULT_PROMPTS_DIR
    default_lang = _normalize_lang(default_language) if default_language else "en"
    return PromptManager(
        prompts_dir=dir_path,
        default_language=default_lang,
        cache_ttl_seconds=cache_ttl_seconds,
        root=root,
    )
