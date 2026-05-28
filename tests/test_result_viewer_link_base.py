"""File link base URL: inbound-derived Host / forwarded headers + resolve_file_link_base_url."""

import core.result_viewer as rv
from unittest.mock import MagicMock

from core.result_viewer import (
    infer_public_base_url_from_http_request,
    normalize_public_url_for_clients,
    resolve_file_link_base_url,
)


def test_infer_http_handles_missing_headers_object():
    req = MagicMock()
    req.headers = None
    req.base_url = "http://192.168.0.99:9000/"
    req.url.scheme = "http"
    assert infer_public_base_url_from_http_request(req) == "http://192.168.0.99:9000"


def test_infer_http_uses_x_forwarded_host():
    req = MagicMock()
    req.headers = {"x-forwarded-host": "mymac.example.com", "x-forwarded-proto": "https"}
    req.url.scheme = "http"
    assert infer_public_base_url_from_http_request(req) == "https://mymac.example.com"


def test_infer_http_falls_back_to_base_url():
    req = MagicMock()
    req.headers = {}
    req.base_url = "http://127.0.0.1:9000/"
    assert infer_public_base_url_from_http_request(req) == "http://127.0.0.1:9000"


def test_resolve_prefers_preferred():
    assert resolve_file_link_base_url("https://a.com") == "https://a.com"


def test_resolve_strips_whitespace_in_config_style_url():
    assert resolve_file_link_base_url("https://a.com ") == "https://a.com"
    assert resolve_file_link_base_url("https://a.com/foo ") == "https://a.com/foo"


def test_normalize_public_url_removes_whitespace_keeps_percent_encoded():
    s = "https://x.com/files/out?path=output%2Fa%20b.html&token=abc"
    assert normalize_public_url_for_clients(s) == s
    assert (
        normalize_public_url_for_clients("https://x.com /files/out?a=1")
        == "https://x.com/files/out?a=1"
    )


def test_resolve_signed_mode_rejects_malformed_preferred_without_tunnel(monkeypatch):
    """Do not emit bases with no real host when public URL is unset and auth (signed links) mode."""
    monkeypatch.setattr(rv, "get_result_link_base_url", lambda: "")
    monkeypatch.setattr(rv, "file_unsigned_dev_mode_active", lambda: False)
    assert rv.resolve_file_link_base_url("http://") == ""
