"""Runtime tests for VMPrint render functions (imported directly from tools.builtin)."""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Optional, Tuple

import pytest

from tools.builtin import _rewrite_vmprint_preview_asset_links, _vmprint_render_sync
from tools.vmprint_preview_loader import vmprint_hybrid_preview_loaders


class _Proc:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_fake_vmprint_tree(tmp_path: Path, with_vm_cli: bool = True) -> Path:
    vmp = tmp_path / "vmprint"
    (vmp / "draft2final" / "dist").mkdir(parents=True, exist_ok=True)
    (vmp / "draft2final" / "dist" / "cli.js").write_text("// fake", encoding="utf-8")
    if with_vm_cli:
        (vmp / "cli" / "dist").mkdir(parents=True, exist_ok=True)
        (vmp / "cli" / "dist" / "index.js").write_text("// fake", encoding="utf-8")
    # Stubs so HomeClaw resolves preview deps before subprocess.run (which tests monkeypatch).
    (vmp / "node_modules" / "@vmprint" / "standard-fonts" / "dist").mkdir(parents=True, exist_ok=True)
    (vmp / "node_modules" / "@vmprint" / "standard-fonts" / "dist" / "index.cjs").write_text(
        "module.exports = { StandardFontManager: class {} };", encoding="utf-8"
    )
    (vmp / "node_modules" / "@vmprint" / "context-canvas" / "dist").mkdir(parents=True, exist_ok=True)
    (vmp / "node_modules" / "@vmprint" / "context-canvas" / "dist" / "index.js").write_text(
        "module.exports = { CanvasContext: class {} };", encoding="utf-8"
    )
    return vmp


def test_vmprint_preview_asset_links_rewrite_signed_urls(monkeypatch):
    html_in = (
        "<link rel='stylesheet' href='./styles.css'>"
        "<script src='./_vmprint_assets/v1/vmprint-fontkit.js'></script>"
        "<script src='./_vmprint_assets/v1/vmprint-engine.js'></script>"
        "<script src='./_vmprint_assets/v1/vmprint-web-fonts.js'></script>"
        "<script src='./_vmprint_assets/v1/vmprint-context-canvas.js'></script>"
        "<script src='./assets/pipeline.js'></script>"
        "<script src='./assets/ui.js'></script>"
        "<script src='./assets/vmprint-client-engine-loader.js'></script>"
    )

    core_mod = types.ModuleType("core")
    rv_mod = types.ModuleType("core.result_viewer")

    def _fake_build_file_view_link(scope, path):  # noqa: ANN001
        return (f"https://example.test/files/out?token=signed123&path={path}", None)

    rv_mod.build_file_view_link = _fake_build_file_view_link
    monkeypatch.setitem(sys.modules, "core", core_mod)
    monkeypatch.setitem(sys.modules, "core.result_viewer", rv_mod)

    html_out = _rewrite_vmprint_preview_asset_links(html_in, "companion")
    assert "token=signed123" in html_out
    assert "./_vmprint_assets/v1/" not in html_out
    assert "./styles.css" not in html_out
    assert "./assets/pipeline.js" not in html_out
    assert "./assets/ui.js" not in html_out
    assert "./assets/vmprint-client-engine-loader.js" not in html_out
    assert "output/_vmprint_assets/v1/vmprint-engine.js" in html_out
    assert "output/styles.css" in html_out
    assert "output/assets/pipeline.js" in html_out
    assert "output/assets/ui.js" in html_out
    assert "output/assets/vmprint-client-engine-loader.js" in html_out


def test_vmprint_preview_asset_links_rewrite_dev_unsigned_urls(monkeypatch):
    html_in = (
        "<link rel='stylesheet' href='./styles.css'>"
        "<script src='./_vmprint_assets/v1/vmprint-fontkit.js'></script>"
        "<script src='./_vmprint_assets/v1/vmprint-engine.js'></script>"
        "<script src='./_vmprint_assets/v1/vmprint-web-fonts.js'></script>"
        "<script src='./_vmprint_assets/v1/vmprint-context-canvas.js'></script>"
        "<script src='./assets/pipeline.js'></script>"
        "<script src='./assets/ui.js'></script>"
        "<script src='./assets/vmprint-client-engine-loader.js'></script>"
    )

    core_mod = types.ModuleType("core")
    rv_mod = types.ModuleType("core.result_viewer")

    def _fake_build_file_view_link(scope, path):  # noqa: ANN001
        return (f"https://example.test/files/out?scope={scope}&path={path}&dev_unsigned=1", None)

    rv_mod.build_file_view_link = _fake_build_file_view_link
    monkeypatch.setitem(sys.modules, "core", core_mod)
    monkeypatch.setitem(sys.modules, "core.result_viewer", rv_mod)

    html_out = _rewrite_vmprint_preview_asset_links(html_in, "companion")
    assert "dev_unsigned=1" in html_out
    assert "./_vmprint_assets/v1/" not in html_out
    assert "./styles.css" not in html_out
    assert "./assets/pipeline.js" not in html_out
    assert "./assets/ui.js" not in html_out
    assert "./assets/vmprint-client-engine-loader.js" not in html_out
    assert "scope=companion" in html_out
    assert "output/assets/vmprint-client-engine-loader.js" in html_out


def test_vmprint_render_sync_rejects_unknown_output_format(tmp_path: Path):
    vmp = _make_fake_vmprint_tree(tmp_path)
    pdf, txt, err, side = _vmprint_render_sync(
        "hello",
        output_format="unknown",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert pdf is None
    assert txt is None
    assert side is None
    assert "output_format must be one of" in (err or "")


def test_vmprint_render_sync_layout_json_success(tmp_path: Path, monkeypatch):
    vmp = _make_fake_vmprint_tree(tmp_path, with_vm_cli=True)

    def _fake_run(cmd, cwd=None, capture_output=None, timeout=None, check=None):  # noqa: ANN001
        # draft2final call writes AST file
        if str(cmd[1]).endswith("draft2final/dist/cli.js"):
            out_flag = "--out" if "--out" in cmd else "--output"
            out_path = cmd[cmd.index(out_flag) + 1]
            Path(out_path).write_text('{"documentVersion":"1.1","layout":{},"styles":{},"elements":[]}', encoding="utf-8")
            return _Proc(0)
        # vmprint CLI call writes layout stream JSON
        if str(cmd[1]).endswith("cli/dist/index.js"):
            layout_path = cmd[cmd.index("--emit-layout") + 1]
            Path(layout_path).write_text('{"pages":[{"width":595,"height":842,"boxes":[{"x":1,"y":2,"w":3,"h":4}]}]}', encoding="utf-8")
            return _Proc(0)
        return _Proc(1, stderr=b"unexpected command")

    monkeypatch.setattr("tools.builtin.subprocess.run", _fake_run)

    pdf, txt, err, side = _vmprint_render_sync(
        "hello layout",
        output_format="layout_json",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert err is None
    assert pdf is None
    assert side is None
    assert txt is not None
    assert '"pages"' in txt


def test_vmprint_render_sync_browser_preview_html_success(tmp_path: Path, monkeypatch):
    vmp = _make_fake_vmprint_tree(tmp_path, with_vm_cli=True)

    def _fake_run(cmd, cwd=None, capture_output=None, timeout=None, check=None):  # noqa: ANN001
        if str(cmd[1]).endswith("draft2final/dist/cli.js"):
            out_flag = "--out" if "--out" in cmd else "--output"
            out_path = cmd[cmd.index(out_flag) + 1]
            Path(out_path).write_text('{"documentVersion":"1.1","layout":{},"styles":{},"elements":[]}', encoding="utf-8")
            return _Proc(0)
        if str(cmd[1]).endswith("cli/dist/index.js"):
            layout_path = cmd[cmd.index("--emit-layout") + 1]
            Path(layout_path).write_text('{"pages":[{"width":595,"height":842,"boxes":[{"type":"text","x":1,"y":2,"w":3,"h":4}]}]}', encoding="utf-8")
            return _Proc(0)
        if str(cmd[1]) == "-e":
            payload = '{"svgs":["<svg><text>Hello</text></svg>"]}'
            return _Proc(0, stdout=payload.encode("utf-8"))
        return _Proc(1, stderr=b"unexpected command")

    monkeypatch.setattr("tools.builtin.subprocess.run", _fake_run)

    pdf, txt, err, side = _vmprint_render_sync(
        "hello html",
        output_format="browser_preview_html",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert err is None
    assert pdf is None
    assert side is not None and '"pages"' in side
    assert txt is not None
    assert "VMPrint preview" in txt
    assert "svg-pages-data" in txt
    assert "layout-data" in txt
    assert "view-mode" not in txt
    assert "homeclaw-vmprint-client-engine" not in txt
    assert "vmprint-client-engine-loader" not in txt
    assert "window.__hcVmprintAsset" in txt
    assert "src='./_vmprint_assets/" not in txt


def test_vmprint_render_sync_browser_preview_html_includes_client_engine_when_enabled(tmp_path: Path, monkeypatch):
    vmp = _make_fake_vmprint_tree(tmp_path, with_vm_cli=True)

    def _fake_run(cmd, cwd=None, capture_output=None, timeout=None, check=None):  # noqa: ANN001
        if str(cmd[1]).endswith("draft2final/dist/cli.js"):
            out_flag = "--out" if "--out" in cmd else "--output"
            out_path = cmd[cmd.index(out_flag) + 1]
            Path(out_path).write_text('{"documentVersion":"1.1","layout":{},"styles":{},"elements":[]}', encoding="utf-8")
            return _Proc(0)
        if str(cmd[1]).endswith("cli/dist/index.js"):
            layout_path = cmd[cmd.index("--emit-layout") + 1]
            Path(layout_path).write_text('{"pages":[{"width":595,"height":842,"boxes":[]}]}', encoding="utf-8")
            return _Proc(0)
        if str(cmd[1]) == "-e":
            payload = '{"svgs":["<svg></svg>"]}'
            return _Proc(0, stdout=payload.encode("utf-8"))
        return _Proc(1, stderr=b"unexpected command")

    monkeypatch.setattr("tools.builtin.subprocess.run", _fake_run)
    monkeypatch.setattr("tools.builtin._vmprint_preview_client_engine_enabled", lambda: True)

    pdf, txt, err, _side = _vmprint_render_sync(
        "hello html client",
        output_format="browser_preview_html",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert err is None
    assert txt is not None
    assert "homeclaw-vmprint-client-engine" in txt
    assert "vmprint-client-engine-loader.js" in txt


def test_vmprint_render_sync_layout_json_requires_vmprint_cli(tmp_path: Path, monkeypatch):
    vmp = _make_fake_vmprint_tree(tmp_path, with_vm_cli=False)

    def _fake_run(cmd, cwd=None, capture_output=None, timeout=None, check=None):  # noqa: ANN001
        # Only draft2final should run in this test.
        if str(cmd[1]).endswith("draft2final/dist/cli.js"):
            out_flag = "--out" if "--out" in cmd else "--output"
            out_path = cmd[cmd.index(out_flag) + 1]
            Path(out_path).write_text('{"documentVersion":"1.1","layout":{},"styles":{},"elements":[]}', encoding="utf-8")
            return _Proc(0)
        return _Proc(1, stderr=b"unexpected command")

    monkeypatch.setattr("tools.builtin.subprocess.run", _fake_run)

    pdf, txt, err, side = _vmprint_render_sync(
        "hello layout",
        output_format="layout_json",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert pdf is None
    assert txt is None
    assert side is None
    assert "VMPrint CLI not built" in (err or "")


def test_vmprint_render_sync_browser_preview_allows_large_layout(tmp_path: Path, monkeypatch):
    vmp = _make_fake_vmprint_tree(tmp_path, with_vm_cli=True)

    huge_layout = '{"pages":[{"width":595,"height":842,"boxes":[' + ("{}," * 1_200_000) + '{}]}]}'

    def _fake_run(cmd, cwd=None, capture_output=None, timeout=None, check=None):  # noqa: ANN001
        if str(cmd[1]).endswith("draft2final/dist/cli.js"):
            out_flag = "--out" if "--out" in cmd else "--output"
            out_path = cmd[cmd.index(out_flag) + 1]
            Path(out_path).write_text('{"documentVersion":"1.1","layout":{},"styles":{},"elements":[]}', encoding="utf-8")
            return _Proc(0)
        if str(cmd[1]) == "-e":
            payload = '{"svgs":[' + json.dumps("<svg>" + ("x" * 2_100_000) + "</svg>") + "]}"
            return _Proc(0, stdout=payload.encode("utf-8"))
        if str(cmd[1]).endswith("cli/dist/index.js"):
            layout_path = cmd[cmd.index("--emit-layout") + 1]
            Path(layout_path).write_text(huge_layout, encoding="utf-8")
            return _Proc(0)
        return _Proc(1, stderr=b"unexpected command")

    monkeypatch.setattr("tools.builtin.subprocess.run", _fake_run)

    pdf, txt, err, side = _vmprint_render_sync(
        "hello html",
        output_format="browser_preview_html",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert pdf is None
    assert err is None
    assert txt is not None
    assert "<!doctype html>" in txt.lower()
    assert side is not None


def test_vmprint_render_sync_browser_preview_rejects_oversized_payload(tmp_path: Path, monkeypatch):
    """Layout JSON exceeding the size guard is rejected gracefully."""
    vmp = _make_fake_vmprint_tree(tmp_path, with_vm_cli=True)

    # Layout that is exactly at the limit should succeed; anything over 2 MiB fails.
    huge_layout = '{"pages":[{"width":595,"height":842,"boxes":[' + ("{}," * 1_200_000) + '{}]}]}'

    def _fake_run(cmd, cwd=None, capture_output=None, timeout=None, check=None):  # noqa: ANN001
        if str(cmd[1]).endswith("draft2final/dist/cli.js"):
            out_flag = "--out" if "--out" in cmd else "--output"
            out_path = cmd[cmd.index(out_flag) + 1]
            Path(out_path).write_text('{"documentVersion":"1.1","layout":{},"styles":{},"elements":[]}', encoding="utf-8")
            return _Proc(0)
        if str(cmd[1]) == "-e":
            # Payload size well over 2 MiB should be rejected by the size guard.
            oversized_payload = '{"svgs":[' + json.dumps("<svg>" + ("x" * 2_100_000) + "</svg>") + "]}"
            return _Proc(0, stdout=oversized_payload.encode("utf-8"))
        if str(cmd[1]).endswith("cli/dist/index.js"):
            layout_path = cmd[cmd.index("--emit-layout") + 1]
            Path(layout_path).write_text(huge_layout, encoding="utf-8")
            return _Proc(0)
        return _Proc(1, stderr=b"unexpected command")

    monkeypatch.setattr("tools.builtin.subprocess.run", _fake_run)

    pdf, txt, err, side = _vmprint_render_sync(
        "hello html",
        output_format="browser_preview_html",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    # The size guard should kick in and return an error or empty result.
    assert pdf is None
    assert "VMPrint layout emit failed" in (err or "") or side is None or "layout-data" not in (txt or "")
