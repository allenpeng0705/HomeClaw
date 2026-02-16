# MkDocs plugin: rewrite URLs so the site works when served from a subpath
# (e.g. https://allenpeng0705.github.io/HomeClaw/). Fixes:
# - Root-relative /assets/... (would 404 at domain root).
# - Relative assets on the index page (e.g. href="assets/..." breaks when URL has no trailing slash).
# - Theme's __md_scope so instant loading and storage use the correct base path.

from __future__ import annotations

import re
from pathlib import Path

from mkdocs.plugins import BasePlugin


def _base_path_from_site_url(site_url: str | None) -> str:
    if not site_url or not site_url.strip():
        return ""
    url = site_url.strip().rstrip("/")
    try:
        after = url.split("://", 1)[-1]
        if "/" in after:
            path = "/" + after.split("/", 1)[-1]
            return path if path != "/" else ""
    except Exception:
        pass
    return ""


class SubpathPlugin(BasePlugin):
    config_scheme = ()

    def on_config(self, config, **kwargs):
        self.base_path = _base_path_from_site_url(config.get("site_url"))
        return config

    def on_post_build(self, config, **kwargs):
        if not self.base_path:
            return
        site_dir = Path(config["site_dir"])
        base = self.base_path.rstrip("/")
        base_slash = base + "/"
        if not base:
            return
        base_name = base.strip("/")

        # 1) Root-relative: /assets/... or /page/ -> /HomeClaw/assets/... (not already under base)
        root_rel = re.compile(
            r'(?P<attr>src|href)=["\']/(?!' + re.escape(base_name) + r'/)'
        )
        root_repl = r'\g<attr>="' + base + r'/'

        # 2) Relative assets (no leading slash): href="assets/ or src="assets/ or href="../assets/ or src="../assets/
        #    -> /HomeClaw/assets/ so they work when index is opened as .../HomeClaw (no trailing slash)
        rel_assets_same = re.compile(
            r'(?P<attr>src|href)=["\']assets/'
        )
        rel_assets_parent = re.compile(
            r'(?P<attr>src|href)=["\']\.\./assets/'
        )

        # 3) Theme scope: __md_scope=new URL("."|"..",location) -> new URL("/HomeClaw/",location)
        scope_rel = re.compile(
            r'__md_scope\s*=\s*new\s+URL\s*\(\s*["\']\.\.?["\']\s*,\s*location\s*\)',
            re.IGNORECASE
        )
        scope_repl = '__md_scope=new URL("' + base_slash + '",location)'

        for path in site_dir.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="replace")
            new_text = text
            new_text = root_rel.sub(root_repl, new_text)
            new_text = rel_assets_parent.sub(r'\g<attr>="' + base_slash + r'assets/', new_text)
            new_text = rel_assets_same.sub(r'\g<attr>="' + base_slash + r'assets/', new_text)
            new_text = scope_rel.sub(scope_repl, new_text)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
        return None
