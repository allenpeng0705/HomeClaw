"""Claw-Code direct OpenAI-compatible HTTP (bypass LiteLLM proxy)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core import clawcode_store as cs


def test_direct_openai_none_without_clawcode_session():
    req = MagicMock()
    req.request_metadata = {}
    with patch.object(cs, "clawcode_feature_enabled", return_value=True):
        assert cs.clawcode_direct_openai_settings(req) is None


def test_direct_openai_none_when_disabled():
    req = MagicMock()
    req.request_metadata = {"clawcode_session_id": "s1"}
    with patch.object(cs, "clawcode_feature_enabled", return_value=False):
        assert cs.clawcode_direct_openai_settings(req) is None


def test_direct_openai_builds_url_and_uses_inline_key():
    req = MagicMock()
    req.request_metadata = {"clawcode_session_id": "s1"}
    with patch.object(cs, "clawcode_feature_enabled", return_value=True):
        with patch.object(
            cs,
            "_clawcode_config",
            return_value={
                "direct_openai": {
                    "base_url": "https://api.example.com/v1",
                    "model": "m1",
                    "api_key": "secret",
                },
            },
        ):
            out = cs.clawcode_direct_openai_settings(req)
    assert out is not None
    assert out["url"] == "https://api.example.com/v1/chat/completions"
    assert out["model"] == "m1"
    assert out["api_key"] == "secret"


def test_direct_openai_api_key_env(monkeypatch):
    monkeypatch.setenv("MY_LLM_KEY", "fromenv")
    req = MagicMock()
    req.request_metadata = {"clawcode_session_id": "s1"}
    with patch.object(cs, "clawcode_feature_enabled", return_value=True):
        with patch.object(
            cs,
            "_clawcode_config",
            return_value={
                "direct_openai": {
                    "base_url": "api.vendor.com/v1",
                    "model": "x",
                    "api_key_env": "MY_LLM_KEY",
                },
            },
        ):
            out = cs.clawcode_direct_openai_settings(req)
    assert out is not None
    assert out["url"] == "https://api.vendor.com/v1/chat/completions"
    assert out["api_key"] == "fromenv"


def test_direct_openai_full_path_url_no_double_completions():
    req = MagicMock()
    req.request_metadata = {"clawcode_session_id": "s1"}
    with patch.object(cs, "clawcode_feature_enabled", return_value=True):
        with patch.object(
            cs,
            "_clawcode_config",
            return_value={
                "direct_openai": {
                    "url": "https://x.com/custom/chat/completions",
                    "model": "m",
                    "api_key": "k",
                },
            },
        ):
            out = cs.clawcode_direct_openai_settings(req)
    assert out["url"] == "https://x.com/custom/chat/completions"
