"""Unsigned dev file links when auth_api_key is empty (no real base.util import)."""

import importlib

import pytest

pytest.importorskip("fastapi")


def test_build_file_view_link_uses_dev_unsigned_without_api_key(fake_base_util):
    """When auth_api_key is empty, file links include dev_unsigned=1."""
    fake_base_util.auth_api_key = ""
    fake_base_util.core_public_url = ""
    fake_base_util.host = "127.0.0.1"
    fake_base_util.port = 9000
    fake_base_util.file_link_style = "token"
    fake_base_util.file_static_prefix = "files"
    fake_base_util.file_view_link_expiry_sec = None

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


def test_build_file_view_link_static_style_dev_unsigned(fake_base_util):
    """Static file link style with empty auth_api_key still uses dev_unsigned=1."""
    fake_base_util.auth_api_key = ""
    fake_base_util.core_public_url = "http://example.test"
    fake_base_util.host = "127.0.0.1"
    fake_base_util.port = 9000
    fake_base_util.file_link_style = "static"
    fake_base_util.file_static_prefix = "files"
    fake_base_util.file_view_link_expiry_sec = None

    import core.result_viewer as rv

    importlib.reload(rv)
    rv._warned_dev_unsigned_file_links = False
    url, err = rv.build_file_view_link("companion", "images/a.jpg")
    assert err is None
    assert url
    assert "dev_unsigned=1" in url
    assert url.startswith("http://example.test/")
