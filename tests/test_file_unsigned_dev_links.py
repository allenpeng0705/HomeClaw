"""Unsigned dev file links when auth_api_key is empty (no real base.util import)."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytest.importorskip("fastapi")


def _push_fake_base_util(meta):
    util_mod = ModuleType("base.util")

    class Util:
        def get_core_metadata(self):
            return meta

    util_mod.Util = Util
    old = sys.modules.get("base.util")
    sys.modules["base.util"] = util_mod
    return old


def _pop_fake_base_util(old):
    if old is not None:
        sys.modules["base.util"] = old
    else:
        sys.modules.pop("base.util", None)


def test_build_file_view_link_uses_dev_unsigned_without_api_key():
    meta = SimpleNamespace(
        auth_api_key="",
        core_public_url="",
        host="127.0.0.1",
        port=9000,
        file_link_style="token",
        file_static_prefix="files",
        file_view_link_expiry_sec=None,
    )
    old = _push_fake_base_util(meta)
    try:
        import core.result_viewer as rv

        importlib.reload(rv)
        rv._warned_dev_unsigned_file_links = False
        url, err = rv.build_file_view_link("companion", "output/x.png")
        assert err is None
        assert url
        assert "dev_unsigned=1" in url
        assert "scope=" in url
        assert "path=" in url
        assert "9000" in url
    finally:
        _pop_fake_base_util(old)


def test_build_file_view_link_static_style_dev_unsigned():
    meta = SimpleNamespace(
        auth_api_key="",
        core_public_url="http://example.test",
        host="127.0.0.1",
        port=9000,
        file_link_style="static",
        file_static_prefix="files",
        file_view_link_expiry_sec=None,
    )
    old = _push_fake_base_util(meta)
    try:
        import core.result_viewer as rv

        importlib.reload(rv)
        rv._warned_dev_unsigned_file_links = False
        url, err = rv.build_file_view_link("companion", "images/a.jpg")
        assert err is None
        assert url
        assert "dev_unsigned=1" in url
        assert url.startswith("http://example.test/")
    finally:
        _pop_fake_base_util(old)
