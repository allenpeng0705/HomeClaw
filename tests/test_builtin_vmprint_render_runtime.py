from __future__ import annotations

import html
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

class _Proc:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _load_vmprint_render_sync():
    root = Path(__file__).resolve().parents[1]
    src = (root / "tools" / "builtin.py").read_text(encoding="utf-8")
    start = src.index("def _vmprint_render_sync(")
    end = src.index("\n\nasync def _vmprint_render_executor", start)
    fn_src = src[start:end]

    class _DummyLogger:
        def debug(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return None

    ns = {
        "Path": Path,
        "tempfile": tempfile,
        "subprocess": subprocess,
        "html": html,
        "json": json,
        "os": os,
        "Optional": Optional,
        "Tuple": Tuple,
        "logger": _DummyLogger(),
    }
    exec(fn_src, ns)
    return ns["_vmprint_render_sync"], ns


def _make_fake_vmprint_tree(tmp_path: Path, with_vm_cli: bool = True) -> Path:
    vmp = tmp_path / "vmprint"
    (vmp / "draft2final" / "dist").mkdir(parents=True, exist_ok=True)
    (vmp / "draft2final" / "dist" / "cli.js").write_text("// fake", encoding="utf-8")
    if with_vm_cli:
        (vmp / "cli" / "dist").mkdir(parents=True, exist_ok=True)
        (vmp / "cli" / "dist" / "index.js").write_text("// fake", encoding="utf-8")
    return vmp


def test_vmprint_render_sync_rejects_unknown_output_format(tmp_path: Path):
    fn, _ = _load_vmprint_render_sync()
    vmp = _make_fake_vmprint_tree(tmp_path)
    pdf, txt, err = fn(
        "hello",
        output_format="unknown",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert pdf is None
    assert txt is None
    assert "output_format must be one of" in (err or "")


def test_vmprint_render_sync_layout_json_success(tmp_path: Path, monkeypatch):
    fn, ns = _load_vmprint_render_sync()
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

    monkeypatch.setattr(ns["subprocess"], "run", _fake_run)

    pdf, txt, err = fn(
        "hello layout",
        output_format="layout_json",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert err is None
    assert pdf is None
    assert txt is not None
    assert '"pages"' in txt


def test_vmprint_render_sync_browser_preview_html_success(tmp_path: Path, monkeypatch):
    fn, ns = _load_vmprint_render_sync()
    vmp = _make_fake_vmprint_tree(tmp_path, with_vm_cli=True)

    def _fake_run(cmd, cwd=None, capture_output=None, timeout=None, check=None):  # noqa: ANN001
        if str(cmd[1]).endswith("draft2final/dist/cli.js"):
            out_flag = "--out" if "--out" in cmd else "--output"
            out_path = cmd[cmd.index(out_flag) + 1]
            Path(out_path).write_text('{"documentVersion":"1.1","layout":{},"styles":{},"elements":[]}', encoding="utf-8")
            return _Proc(0)
        if str(cmd[1]) == "-e":
            payload = '{"svgs":["<svg><text>Hello</text></svg>"]}'
            return _Proc(0, stdout=payload.encode("utf-8"))
        if str(cmd[1]).endswith("cli/dist/index.js"):
            layout_path = cmd[cmd.index("--emit-layout") + 1]
            Path(layout_path).write_text('{"pages":[{"width":595,"height":842,"boxes":[{"type":"text","x":1,"y":2,"w":3,"h":4}]}]}', encoding="utf-8")
            return _Proc(0)
        return _Proc(1, stderr=b"unexpected command")

    monkeypatch.setattr(ns["subprocess"], "run", _fake_run)

    pdf, txt, err = fn(
        "hello html",
        output_format="browser_preview_html",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert err is None
    assert pdf is None
    assert txt is not None
    assert "VMPrint Hybrid Preview" in txt
    assert "svg-pages-data" in txt


def test_vmprint_render_sync_layout_json_requires_vmprint_cli(tmp_path: Path, monkeypatch):
    fn, ns = _load_vmprint_render_sync()
    vmp = _make_fake_vmprint_tree(tmp_path, with_vm_cli=False)

    def _fake_run(cmd, cwd=None, capture_output=None, timeout=None, check=None):  # noqa: ANN001
        # Only draft2final should run in this test.
        if str(cmd[1]).endswith("draft2final/dist/cli.js"):
            out_flag = "--out" if "--out" in cmd else "--output"
            out_path = cmd[cmd.index(out_flag) + 1]
            Path(out_path).write_text('{"documentVersion":"1.1","layout":{},"styles":{},"elements":[]}', encoding="utf-8")
            return _Proc(0)
        return _Proc(1, stderr=b"unexpected command")

    monkeypatch.setattr(ns["subprocess"], "run", _fake_run)

    pdf, txt, err = fn(
        "hello layout",
        output_format="layout_json",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert pdf is None
    assert txt is None
    assert "VMPrint CLI not built" in (err or "")


def test_vmprint_render_sync_browser_preview_rejects_oversized_layout(tmp_path: Path, monkeypatch):
    fn, ns = _load_vmprint_render_sync()
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

    monkeypatch.setattr(ns["subprocess"], "run", _fake_run)

    pdf, txt, err = fn(
        "hello html",
        output_format="browser_preview_html",
        vmprint_dir=str(vmp),
        vmprint_profile="literature",
        vmprint_style=None,
    )
    assert pdf is None
    assert txt is None
    assert "preview too large" in (err or "").lower()
