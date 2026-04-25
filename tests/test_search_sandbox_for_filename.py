"""Sandbox filename search: user tree + global share folder."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


def test_search_finds_files_in_sandbox_and_share(ctx_u1):
    from tools import builtin as bi

    with TemporaryDirectory() as td:
        root = Path(td)
        hc = root / "hc"
        hc.mkdir()
        (hc / "u1" / "documents").mkdir(parents=True)
        (hc / "share" / "pub").mkdir(parents=True)
        (hc / "u1" / "documents" / "in_sandbox.pdf").write_text("a", encoding="utf-8")
        (hc / "share" / "pub" / "in_share.pdf").write_text("b", encoding="utf-8")

        with patch.object(bi, "_get_homeclaw_root", return_value=str(hc)):
            sandbox_only = bi._search_sandbox_for_filename(ctx_u1, "in_sandbox.pdf")
            share_only = bi._search_sandbox_for_filename(ctx_u1, "in_share.pdf")
            combined = bi._search_sandbox_for_filename(ctx_u1, "in_")

        assert "documents/in_sandbox.pdf" in sandbox_only
        assert "share/pub/in_share.pdf" in share_only
        assert "documents/in_sandbox.pdf" in combined
        assert "share/pub/in_share.pdf" in combined

        with patch.object(bi, "_get_homeclaw_root", return_value=str(hc)):
            r = bi._resolve_file_path("share/pub/in_share.pdf", ctx_u1, for_write=False)
        assert r is not None
        full, _base = r
        assert full.is_file()
        assert full.name == "in_share.pdf"
