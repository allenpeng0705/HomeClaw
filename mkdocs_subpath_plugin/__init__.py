# MkDocs plugin: rewrite root-relative URLs so the site works when served from a subpath
# (e.g. https://allenpeng0705.github.io/HomeClaw/). Without this, theme assets and nav
# requested as /assets/... resolve to the domain root and 404 on GitHub Pages.

from __future__ import annotations

import re
from pathlib import Path

from mkdocs.plugins import BasePlugin


def _base_path_from_site_url(site_url: str | None) -> str:
    if not site_url or not site_url.strip():
        return ""
    url = site_url.strip().rstrip("/")
    try:
        # expect https://host/path or https://host/path/
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
        if not base:
            return
        # Rewrite root-relative URLs so they go under the subpath.
        # Match src="/ or href="/ but not already under base (e.g. href="/HomeClaw/...")
        pattern = re.compile(
            r'(?P<attr>src|href)=["\']/(?!' + re.escape(base.strip("/")) + r'/)'
        )
        replacement = r'\g<attr>="' + base + r'/'
        for path in site_dir.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="replace")
            new_text = pattern.sub(replacement, text)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
        return None
