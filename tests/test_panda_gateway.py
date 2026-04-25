"""Panda Gateway URL routing when panda.enabled is true (see config/llm.yml panda:)."""

import pytest

from base.util import Util


def test_panda_openai_chat_urls(util_with_panda):
    u = util_with_panda
    assert u.panda_openai_chat_url("local") == "http://10.0.1.2:9090/v1/chat"
    assert u.panda_openai_chat_url("ollama") == "http://10.0.1.2:9090/v1/chat"
    assert u.panda_openai_chat_url("litellm") == "http://10.0.1.2:9090/v1/cloud"


def test_panda_embedding_and_completions_urls(util_with_panda):
    u = util_with_panda
    assert u.panda_openai_embedding_url() == "http://10.0.1.2:9090/v1/embeddings"
    assert u.panda_openai_completions_url() == "http://10.0.1.2:9090/v1/completions"
    assert u.panda_ollama_embed_url() == "http://10.0.1.2:9090/api/embed"


def test_panda_disabled_returns_none(monkeypatch):
    """Test that panda disabled returns None URLs. Creates fresh Util with panda disabled."""
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    original = Util._instance
    Util._instance = None
    try:
        u = Util()

        class _Meta:
            panda = {"enabled": False}

        monkeypatch.setattr(u, "core_metadata", _Meta())
        assert u.panda_openai_chat_url("litellm") is None
        assert u.panda_openai_embedding_url() is None
    finally:
        Util._instance = original


def test_panda_http_timeout_override(util_with_panda):
    assert util_with_panda.panda_http_timeout_seconds() == 45
    t = util_with_panda._client_timeout_for_llm_http()
    assert t.total == 45
