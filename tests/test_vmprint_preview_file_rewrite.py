"""VMPrint preview HTML: relative ./assets must become real /files/out URLs when served from /files/out?path=..."""

from __future__ import annotations

import pytest

import core.result_viewer as rv


def test_rewrite_vmprint_preview_rewrites_relative_assets(monkeypatch):
    def fake_link(scope: str, path: str):
        return (f"https://core.test/files/out?scope={scope}&path={path}&dev_unsigned=1", None)

    monkeypatch.setattr(rv, "build_file_view_link", fake_link)
    html = (
        "<!doctype html><head><meta name='homeclaw-vmprint-ui-hint' content='link'>"
        "<link rel='stylesheet' href='./styles.css'></head>"
        "<script src='./_vmprint_assets/v1/vmprint-engine.js'></script>"
        "<script src='./assets/pipeline.js'></script></html>"
    )
    out = rv.rewrite_vmprint_preview_html_assets(html, "AllenPeng", "output/daily_brief.preview.html")
    # & in query string is escaped as &amp; inside single-quoted HTML attributes (browser resolves correctly).
    q = "https://core.test/files/out?scope=AllenPeng&amp;path=output/styles.css&amp;dev_unsigned=1"
    assert f"href='{q}'" in out
    q2 = "https://core.test/files/out?scope=AllenPeng&amp;path=output/_vmprint_assets/v1/vmprint-engine.js&amp;dev_unsigned=1"
    assert f"src='{q2}'" in out
    q3 = "https://core.test/files/out?scope=AllenPeng&amp;path=output/assets/pipeline.js&amp;dev_unsigned=1"
    assert f"src='{q3}'" in out


def test_rewrite_skips_non_vmprint_html():
    html = "<html><link href='./styles.css'></html>"
    assert rv.rewrite_vmprint_preview_html_assets(html, "U", "output/x.preview.html") == html
